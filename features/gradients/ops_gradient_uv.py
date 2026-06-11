# -*- coding: utf-8 -*-
import bmesh
import bpy
import numpy as np

from ...i18n import tr, tr_format
from ...core.color_attribute import find_color_layer, read_color_attribute_colors
from ...core.context import resolve_target_color_attribute
from ...core.mesh_topology import polygon_loop_totals
from ...core.write_engine import (
    blend_source_values_into_colors,
    restore_color_array_to_attribute,
    write_color_array_to_attribute,
    write_edit_element_colors,
)
from ...services import display, transactions
from .core_color_engine import (
    build_ramp_lut,
    ensure_ramp_node,
    sample_lut_array_out,
)
from .core_overlay import draw_gradient_overlay_callback


def _get_corner_color_attribute(context, mesh):
    target, error = resolve_target_color_attribute(context, required_domain="CORNER")
    if error:
        return None, None, error
    if target.mesh != mesh:
        return None, None, "Active mesh changed while preparing the UV gradient."
    return target.color_attr, target.layer_name, None


def _extract_uv_coords(mesh, uv_layer, loop_count):
    uvs = np.empty(loop_count * 2, dtype=np.float32)
    try:
        uv_layer.data.foreach_get("uv", uvs)
    except AttributeError:
        mesh.attributes[uv_layer.name].data.foreach_get("vector", uvs)
    uvs.shape = (-1, 2)
    return uvs


def _build_uv_selection_mask(mesh, uv_layer, loop_count):
    uv_mask = np.zeros(loop_count, dtype=np.bool_)
    has_uv_selection = False

    if ".select_uv" in mesh.attributes:
        mesh.attributes[".select_uv"].data.foreach_get("value", uv_mask)
        has_uv_selection = bool(np.any(uv_mask))
    else:
        try:
            uv_layer.data.foreach_get("select", uv_mask)
            has_uv_selection = bool(np.any(uv_mask))
        except AttributeError:
            pass

    if not has_uv_selection:
        poly_count = len(mesh.polygons)
        poly_mask = np.zeros(poly_count, dtype=np.bool_)
        mesh.polygons.foreach_get("select", poly_mask)

        if np.any(poly_mask):
            uv_mask = np.repeat(poly_mask, polygon_loop_totals(mesh))
            has_uv_selection = True

    return uv_mask, has_uv_selection


class IMAGE_EDITOR_OT_YLVCTestGradient(bpy.types.Operator):
    bl_idname = "image.ylvc_test_gradient"
    bl_label = "Draw UV Gradient"
    bl_description = "Draw a gradient in the UV Editor."
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        scene = getattr(context, "scene", None)
        return (
            context.area is not None
            and context.area.type == "IMAGE_EDITOR"
            and obj is not None
            and obj.type == "MESH"
            and scene is not None
            and getattr(scene, "ylvc_ui_section", "") == "GRADIENT"
            and display.is_plugin_preview_enabled(obj)
        )

    def invoke(self, context, event):
        if context.area.type != "IMAGE_EDITOR":
            self.report({"WARNING"}, tr("Run this tool in the Image Editor."))
            return {"CANCELLED"}

        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({"WARNING"}, tr("Active object must be a mesh."))
            return {"CANCELLED"}

        if getattr(context.scene, "ylvc_ui_section", "") != "GRADIENT":
            self.report({"WARNING"}, tr("Enable the Viewport Gradient tool first."))
            return {"CANCELLED"}

        if not display.is_plugin_preview_enabled(obj):
            self.report({"WARNING"}, tr("Enable Viewport Preview first."))
            return {"CANCELLED"}

        ramp_node = ensure_ramp_node()
        if ramp_node is None or not ramp_node.color_ramp:
            self.report({"ERROR"}, tr("Could not create the gradient ramp."))
            return {"CANCELLED"}

        self.lut = build_ramp_lut(ramp_node.color_ramp, 512)
        self.original_mode = obj.mode
        if self.original_mode == "EDIT":
            transactions.set_mode(context, "OBJECT")

        mesh = obj.data
        color_attr, layer_name, error = _get_corner_color_attribute(context, mesh)
        if error:
            if self.original_mode == "EDIT":
                transactions.set_mode(context, "EDIT")
            self.report({"WARNING"}, error)
            return {"CANCELLED"}

        uv_layer = mesh.uv_layers.active
        if uv_layer is None:
            if self.original_mode == "EDIT":
                transactions.set_mode(context, "EDIT")
            self.report({"WARNING"}, tr("Active UV map was not found."))
            return {"CANCELLED"}

        self._color_attr = color_attr
        self.layer_name = layer_name
        display.ensure_preview_visible(context, layer_name)
        self.loop_count = len(mesh.loops)
        self.uvs = _extract_uv_coords(mesh, uv_layer, self.loop_count)
        self.uv_mask, self.has_selection = _build_uv_selection_mask(mesh, uv_layer, self.loop_count)
        self.active_loop_indices = np.flatnonzero(self.uv_mask) if self.has_selection else None
        self.selected_count = int(len(self.active_loop_indices)) if self.has_selection else self.loop_count

        self.initial_colors = read_color_attribute_colors(mesh, self._color_attr)
        self.work_colors = np.empty_like(self.initial_colors)
        self.target_rgba = np.empty((self.loop_count, 4), dtype=np.float32)
        self.t_arr_full = np.empty(self.loop_count, dtype=np.float32)
        self.active_uvs = self.uvs[self.active_loop_indices].copy() if self.has_selection else None
        self.target_rgba_active = np.empty((self.selected_count, 4), dtype=np.float32) if self.has_selection else None
        self.t_arr_active = np.empty(self.selected_count, dtype=np.float32) if self.has_selection else None

        self.bm = None
        self.bm_color_layer = None
        self.active_bm_loops = []
        self.active_bm_loop_indices = None
        self.cached_loop_colors = {}
        self.active_loop_colors = None
        self.active_work_colors = None

        if self.original_mode == "EDIT":
            transactions.set_mode(context, "EDIT")
            self.bm = bmesh.from_edit_mesh(mesh)
            layer, domain, _ = find_color_layer(self.bm, layer_name)
            if layer is None or domain != "CORNER":
                self.report({"WARNING"}, tr("Could not access the Face Corner color attribute in Edit Mode."))
                self._finish(context)
                return {"CANCELLED"}

            self.bm_color_layer = layer
            active_indices = []
            active_loop_refs = []
            active_base_colors = []
            global_loop_index = 0
            for face in self.bm.faces:
                for loop in face.loops:
                    if not self.has_selection or self.uv_mask[global_loop_index]:
                        active_indices.append(global_loop_index)
                        active_loop_refs.append(loop)
                        active_base_colors.append(tuple(loop[layer][:]))
                    global_loop_index += 1

            self.active_bm_loops = active_loop_refs
            if active_indices:
                self.active_bm_loop_indices = np.array(active_indices, dtype=np.int32)
                self.active_loop_colors = np.array(active_base_colors, dtype=np.float32)
                self.active_work_colors = np.empty_like(self.active_loop_colors)
                self.cached_loop_colors = {
                    loop: tuple(color) for loop, color in zip(active_loop_refs, active_base_colors)
                }
            else:
                self.active_bm_loop_indices = np.empty(0, dtype=np.int32)
                self.active_loop_colors = np.empty((0, 4), dtype=np.float32)
                self.active_work_colors = np.empty((0, 4), dtype=np.float32)

        self.start_uv = None
        self.end_uv = None
        self._draw_state = {
            "start_pos": None,
            "mouse_pos": None,
            "lut": self.lut,
            "grad_type": "LINEAR",
            "area_ptr": context.area.as_pointer() if context.area is not None else None,
            "region_ptr": context.region.as_pointer() if context.region is not None else None,
        }
        self._handle = bpy.types.SpaceImageEditor.draw_handler_add(
            draw_gradient_overlay_callback,
            (self._draw_state,),
            "WINDOW",
            "POST_PIXEL",
        )

        context.scene.ylvc_is_tracing = True
        if hasattr(context.scene, "ylvc_tracing_type"):
            context.scene.ylvc_tracing_type = "UV_LINEAR"
        context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set(tr("Drag with LMB to draw in the UV Editor. RMB or Esc cancels."))
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if context.area:
            context.area.tag_redraw()

        if event.type in {"RIGHTMOUSE", "ESC"}:
            self._restore_cached_preview(context)
            self._finish(context)
            return {"CANCELLED"}

        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            start_pos = (event.mouse_region_x, event.mouse_region_y)
            self._draw_state["start_pos"] = start_pos
            self._draw_state["mouse_pos"] = start_pos
            self.start_uv = context.region.view2d.region_to_view(*start_pos)
            return {"RUNNING_MODAL"}

        if event.type == "MOUSEMOVE" and self._draw_state["start_pos"]:
            self._draw_state["mouse_pos"] = (event.mouse_region_x, event.mouse_region_y)
            self.end_uv = context.region.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y)
            if getattr(context.scene, "ylvc_use_live_gradient", False):
                self.execute_uv_gradient(context, is_live=True)
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" and event.value == "RELEASE" and self._draw_state["start_pos"]:
            self.end_uv = context.region.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y)
            success = self.execute_uv_gradient(context, is_live=False)
            self._finish(context)
            return {"FINISHED"} if success else {"CANCELLED"}

        return {"RUNNING_MODAL"}

    def execute_uv_gradient(self, context, is_live=False):
        obj = context.active_object
        if obj is None or self.start_uv is None or self.end_uv is None:
            return False

        u1, v1 = self.start_uv
        u2, v2 = self.end_uv
        dx = u2 - u1
        dy = v2 - v1
        length_sq = dx * dx + dy * dy

        blend_mode = context.scene.ylvc_blend_mode
        channel_key = context.scene.ylvc_channel

        if obj.mode == "EDIT":
            if self.bm_color_layer is None or self.active_bm_loop_indices is None:
                return False
            if len(self.active_bm_loops) == 0:
                return False

            if length_sq > 1e-6:
                active_uvs = self.active_uvs if self.has_selection else self.uvs
                t_arr = self.t_arr_active if self.has_selection else self.t_arr_full
                np.subtract(active_uvs[:, 0], u1, out=t_arr)
                t_arr *= dx
                off_v = active_uvs[:, 1] - v1
                t_arr += off_v * dy
                t_arr /= length_sq
                np.clip(t_arr, 0.0, 1.0, out=t_arr)
            else:
                t_arr = self.t_arr_active if self.has_selection else self.t_arr_full
                t_arr.fill(0.0)

            grad_colors = self.target_rgba_active if self.has_selection else self.target_rgba
            sample_lut_array_out(self.lut, t_arr, grad_colors)
            np.copyto(self.active_work_colors, self.active_loop_colors)
            blend_source_values_into_colors(self.active_work_colors, grad_colors, channel_key, blend_mode, slice(None))

            write_edit_element_colors(self.active_bm_loops, self.bm_color_layer, self.active_work_colors)

            bmesh.update_edit_mesh(obj.data)
            if not is_live:
                display.refresh_after_color_write(context, obj.data, self.layer_name, obj=obj)
        else:
            if length_sq > 1e-6:
                if self.has_selection:
                    np.subtract(self.active_uvs[:, 0], u1, out=self.t_arr_active)
                    self.t_arr_active *= dx
                    off_v = self.active_uvs[:, 1] - v1
                    self.t_arr_active += off_v * dy
                    self.t_arr_active /= length_sq
                    np.clip(self.t_arr_active, 0.0, 1.0, out=self.t_arr_active)
                    sample_lut_array_out(self.lut, self.t_arr_active, self.target_rgba_active)
                else:
                    np.subtract(self.uvs[:, 0], u1, out=self.t_arr_full)
                    self.t_arr_full *= dx
                    off_v = self.uvs[:, 1] - v1
                    self.t_arr_full += off_v * dy
                    self.t_arr_full /= length_sq
                    np.clip(self.t_arr_full, 0.0, 1.0, out=self.t_arr_full)
                    sample_lut_array_out(self.lut, self.t_arr_full, self.target_rgba)
            else:
                if self.has_selection:
                    self.t_arr_active.fill(0.0)
                    sample_lut_array_out(self.lut, self.t_arr_active, self.target_rgba_active)
                else:
                    self.t_arr_full.fill(0.0)
                    sample_lut_array_out(self.lut, self.t_arr_full, self.target_rgba)

            np.copyto(self.work_colors, self.initial_colors)
            if self.has_selection:
                blend_source_values_into_colors(self.work_colors, self.target_rgba_active, channel_key, blend_mode, self.active_loop_indices)
            else:
                blend_source_values_into_colors(self.work_colors, self.target_rgba, channel_key, blend_mode, slice(None))
            write_color_array_to_attribute(self._color_attr, self.work_colors, mesh=obj.data)
            if not is_live:
                display.refresh_after_color_write(context, obj.data, self.layer_name, obj=obj)

        if not is_live:
            count = len(self.active_bm_loops) if obj.mode == "EDIT" else self.selected_count
            self.report({"INFO"}, tr_format("Applied a UV gradient to {count} corners.", count=count))
        return True

    def _finish(self, context):
        if getattr(self, "_handle", None) is not None:
            bpy.types.SpaceImageEditor.draw_handler_remove(self._handle, "WINDOW")
            self._handle = None

        context.scene.ylvc_is_tracing = False
        if hasattr(context.scene, "ylvc_tracing_type"):
            context.scene.ylvc_tracing_type = ""
        context.workspace.status_text_set(None)
        if context.area:
            context.area.tag_redraw()

        self._draw_state = {
            "start_pos": None,
            "mouse_pos": None,
            "lut": None,
            "grad_type": "LINEAR",
            "area_ptr": None,
            "region_ptr": None,
        }
        self.bm = None
        self.bm_color_layer = None

    def _restore_cached_preview(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            return

        if obj.mode == "EDIT":
            if self.bm_color_layer is None or not self.cached_loop_colors:
                return

            for bm_loop in self.active_bm_loops:
                base_color = self.cached_loop_colors.get(bm_loop)
                if base_color is None:
                    continue
                try:
                    bm_loop[self.bm_color_layer] = base_color
                except Exception:
                    pass
            bmesh.update_edit_mesh(obj.data)
            return

        if getattr(self, "initial_colors", None) is None:
            return

        try:
            restore_color_array_to_attribute(self._color_attr, self.initial_colors, mesh=obj.data)
            display.refresh_after_color_write(context, obj.data, self.layer_name, obj=obj)
        except Exception:
            pass


CLASSES = (
    IMAGE_EDITOR_OT_YLVCTestGradient,
)
