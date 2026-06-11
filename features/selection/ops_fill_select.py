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


def build_scene_selection_value(context):
    scene = context.scene
    channel = scene.ylvc_channel
    holder = utils.get_color_holder(context)
    if not holder:
        return None

    if channel == "RGB":
        return [holder.color[0], holder.color[1], holder.color[2], scene.ylvc_alpha_fg]
    return scene.ylvc_single_fg


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

    is_color = isinstance(value, (list, tuple))
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

    ch_list = list(selected_channel_indices)
    if is_color:
        target_arr = np.array(value if len(value) == 4 else [value[0], value[1], value[2], 1.0], dtype=np.float32)
        diff = np.abs(colors[:, ch_list] - target_arr[ch_list])
        match_mask = np.all(diff <= tolerance, axis=1)
    else:
        target_val = float(value)
        sampled = np.mean(colors[:, ch_list], axis=1)
        match_mask = np.abs(sampled - target_val) <= tolerance

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
    mesh.edges.foreach_set("select", np.zeros(len(mesh.edges), dtype=bool))
    mesh.polygons.foreach_set("select", np.zeros(len(mesh.polygons), dtype=bool))
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
