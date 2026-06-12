# -*- coding: utf-8 -*-
import bmesh

import bpy
import numpy as np

from ... import utils
from ...core.color_attribute import read_color_attribute_colors
from ...core.color_channels import channel_indices
from ...core.context import resolve_target_color_attribute
from ...core.mesh_topology import loop_vertex_indices
from ...core.operator_poll import active_mesh_has_color_attributes, has_active_mesh
from ...core.write_engine import write_value_result
from ...services import display, transactions


def build_corner_vertex_match_mask(loop_vert_indices, match_mask, vert_count, require_all=False):
    if loop_vert_indices.size == 0 or match_mask.size == 0 or vert_count <= 0:
        return np.zeros(vert_count, dtype=bool)

    if require_all:
        total_counts = np.bincount(loop_vert_indices, minlength=vert_count)
        matched_counts = np.bincount(loop_vert_indices[match_mask], minlength=vert_count)
        return (total_counts > 0) & (matched_counts == total_counts)

    vertex_mask = np.zeros(vert_count, dtype=bool)
    vertex_mask[loop_vert_indices[match_mask]] = True
    return vertex_mask


def clear_edge_face_selection(mesh):
    for edge in mesh.edges:
        edge.select = False
    for polygon in mesh.polygons:
        polygon.select = False


def build_scene_selection_value(context):
    scene = context.scene
    channel = scene.ylvc_channel
    holder = utils.get_color_holder(context)
    if not holder:
        return None

    if channel == "RGB":
        return [holder.color[0], holder.color[1], holder.color[2], scene.ylvc_alpha_fg]
    return scene.ylvc_single_fg


def _linear_rgb_to_srgb_array(rgb_values):
    rgb = np.clip(np.asarray(rgb_values, dtype=np.float32), 0.0, 1.0)
    return np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * np.power(rgb, 1.0 / 2.4) - 0.055)


def _rgb_to_hsv_array(rgb_values):
    rgb = _linear_rgb_to_srgb_array(rgb_values)
    r = rgb[:, 0]
    g = rgb[:, 1]
    b = rgb[:, 2]

    maxc = np.maximum(np.maximum(r, g), b)
    minc = np.minimum(np.minimum(r, g), b)
    delta = maxc - minc
    safe_delta = np.where(delta > 1e-8, delta, 1.0)

    hue = np.zeros_like(maxc)
    red_max = (maxc == r) & (delta > 1e-8)
    green_max = (maxc == g) & (delta > 1e-8)
    blue_max = (maxc == b) & (delta > 1e-8)
    hue[red_max] = np.mod((g[red_max] - b[red_max]) / safe_delta[red_max], 6.0) / 6.0
    hue[green_max] = (((b[green_max] - r[green_max]) / safe_delta[green_max]) + 2.0) / 6.0
    hue[blue_max] = (((r[blue_max] - g[blue_max]) / safe_delta[blue_max]) + 4.0) / 6.0

    saturation = np.where(maxc > 1e-8, delta / maxc, 0.0)
    return np.column_stack((hue, saturation, maxc)).astype(np.float32, copy=False)


def build_color_match_mask(colors, value, selected_channel_indices, tolerance):
    tolerance = max(float(tolerance), 1e-6)
    ch_list = list(selected_channel_indices)
    is_color = isinstance(value, (list, tuple, np.ndarray))

    if is_color and tuple(ch_list) == (0, 1, 2):
        target_arr = np.array(value if len(value) == 4 else [value[0], value[1], value[2], 1.0], dtype=np.float32)
        source_hsv = _rgb_to_hsv_array(colors[:, :3])
        target_hsv = _rgb_to_hsv_array(target_arr[:3].reshape(1, 3))[0]

        hue_diff = np.abs(source_hsv[:, 0] - target_hsv[0])
        hue_diff = np.minimum(hue_diff, 1.0 - hue_diff)
        sat_diff = np.abs(source_hsv[:, 1] - target_hsv[1])
        val_diff = np.abs(source_hsv[:, 2] - target_hsv[2])
        distance = np.sqrt((hue_diff * 2.0) ** 2 + sat_diff**2 + val_diff**2)
        return distance <= tolerance

    if is_color:
        target_arr = np.array(value if len(value) == 4 else [value[0], value[1], value[2], 1.0], dtype=np.float32)
        diff = np.abs(colors[:, ch_list] - target_arr[ch_list])
        return np.all(diff <= tolerance, axis=1)

    target_val = float(value)
    sampled = np.mean(colors[:, ch_list], axis=1)
    return np.abs(sampled - target_val) <= tolerance


def write_value_to_selection(context, value):
    scene = context.scene
    result = write_value_result(
        context,
        value,
        channel_key=scene.ylvc_channel,
        blend_mode=getattr(scene, "ylvc_write_blend_mode", "REPLACE"),
        strength=getattr(scene, "ylvc_brush_strength", 1.0),
    )
    if result.success and result.layer_name:
        display.refresh_after_color_write(context, result.mesh, result.layer_name, obj=result.obj)
    return result.as_tuple()


def select_by_value(context, value, tolerance=None):
    obj = context.active_object
    mesh = obj.data
    scene = context.scene

    channel_key = scene.ylvc_channel
    selected_channel_indices = channel_indices(channel_key)
    tol_value = scene.ylvc_select_tolerance if tolerance is None else tolerance
    tolerance = max(float(tol_value), 1e-6)
    was_edit_mode = obj.mode == "EDIT"
    if was_edit_mode:
        try:
            transactions.ensure_object_mode_for(context, obj)
        except RuntimeError as exc:
            return False, str(exc)

    target, error = resolve_target_color_attribute(context)
    if error:
        if was_edit_mode:
            try:
                transactions.set_mode(context, "EDIT")
            except RuntimeError:
                pass
        return False, error

    attribute = target.color_attr
    domain = attribute.domain
    vert_count = len(mesh.vertices)

    colors = read_color_attribute_colors(mesh, attribute)

    match_mask = build_color_match_mask(colors, value, selected_channel_indices, tolerance)

    if domain == "POINT":
        select_array = np.zeros(vert_count, dtype=bool)
        select_array[match_mask] = True
    else:
        loop_vert_indices = loop_vertex_indices(mesh)
        select_array = build_corner_vertex_match_mask(
            loop_vert_indices,
            match_mask,
            vert_count,
            require_all=True,
        )

    mesh.vertices.foreach_set("select", select_array)
    clear_edge_face_selection(mesh)
    mesh.update()
    count = int(np.sum(select_array))

    if was_edit_mode:
        try:
            transactions.set_mode(context, "EDIT")
        except RuntimeError as exc:
            return False, str(exc)
        tool_settings = getattr(context, "tool_settings", None)
        if tool_settings is not None:
            try:
                tool_settings.mesh_select_mode = (True, False, False)
            except Exception:
                pass
        try:
            bm = bmesh.from_edit_mesh(mesh)
            bm.select_flush_mode()
            bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
        except Exception:
            pass

    if context.area:
        context.area.tag_redraw()
    return True, f"Selected {count} matching vertices."


class MESH_OT_YLVCSwapColors(bpy.types.Operator):
    bl_idname = "mesh.ylvc_swap_colors"
    bl_label = "Swap Colors"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return has_active_mesh(context)

    def execute(self, context):
        holder = utils.get_color_holder(context)
        if not holder:
            return {"CANCELLED"}

        scene = context.scene
        channel = scene.ylvc_channel

        if channel in utils.PURE_VISUAL_CHANNELS:
            fg = tuple(scene.ylvc_pure_fg_values)
            bg = tuple(scene.ylvc_pure_bg_values)
            scene.ylvc_pure_fg_values = bg
            scene.ylvc_pure_bg_values = fg
            index = utils.PURE_VISUAL_CHANNELS[channel]
            holder.color = utils.build_pure_channel_color(channel, bg[index])
            holder.secondary_color = utils.build_pure_channel_color(channel, fg[index])
        else:
            temp = list(holder.color)
            holder.color = holder.secondary_color
            holder.secondary_color = temp

        fg_alpha, bg_alpha = scene.ylvc_alpha_fg, scene.ylvc_alpha_bg
        scene.ylvc_alpha_fg, scene.ylvc_alpha_bg = bg_alpha, fg_alpha
        return {"FINISHED"}


class MESH_OT_YLVCApplySceneValue(bpy.types.Operator):
    bl_idname = "mesh.ylvc_apply_scene_value"
    bl_label = "Fill with Current Value"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return active_mesh_has_color_attributes(context)

    def execute(self, context):
        value = build_scene_selection_value(context)
        if value is None:
            return {"CANCELLED"}

        success, message = write_value_to_selection(context, value)
        self.report({"INFO"} if success else {"WARNING"}, message)
        return {"FINISHED"} if success else {"CANCELLED"}


class MESH_OT_YLVCSelectSceneValue(bpy.types.Operator):
    bl_idname = "mesh.ylvc_select_scene_value"
    bl_label = "Select by Current Value"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return active_mesh_has_color_attributes(context)

    def execute(self, context):
        value = build_scene_selection_value(context)
        if value is None:
            return {"CANCELLED"}

        success, message = select_by_value(context, value)
        self.report({"INFO"} if success else {"WARNING"}, message)
        return {"FINISHED"} if success else {"CANCELLED"}


CLASSES = (MESH_OT_YLVCSwapColors, MESH_OT_YLVCApplySceneValue, MESH_OT_YLVCSelectSceneValue)
