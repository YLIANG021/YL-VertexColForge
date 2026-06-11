# -*- coding: utf-8 -*-
import math
import time

import bmesh
import bpy
import numpy as np

from ...core.blend import blend_colors_np
from ...core.color_attribute import read_color_attribute_colors
from ...core.context import resolve_edit_color_layer, resolve_selection_scope, resolve_target_color_attribute
from ...core.operator_poll import active_mesh_has_color_attributes, has_scene
from ...core.selection_scope import bm_use_vert_selection
from ...core.write_engine import (
    blend_source_values_into_colors,
    read_edit_element_colors,
    restore_color_array_to_attribute,
    write_color_array_to_attribute,
    write_edit_element_colors,
)
from ...i18n import tr, tr_format
from ...services import display
from .core_color_engine import (
    build_ramp_lut,
    ensure_light_ramp_node,
    ensure_ramp_node,
    sample_lut_array_out,
)
from .core_overlay import draw_gradient_overlay_callback


def _get_object_mode_layer_info(context):
    target, error = resolve_target_color_attribute(context)
    if error:
        return None, None, error

    return target.obj, (target.mesh, target.color_attr, target.domain, target.data_type, target.layer_name), None


def _read_edit_loop_colors(loops, layer):
    return read_edit_element_colors(loops, layer)


class MESH_OT_YLVCInitRampData(bpy.types.Operator):
    bl_idname = "mesh.ylvc_init_ramp_data"
    bl_label = "Create Gradient Ramp"
    bl_description = "Create the gradient ramp used by the viewport gradient tools."
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return has_scene(context)

    def execute(self, context):
        ensure_ramp_node()
        if context.area:
            context.area.tag_redraw()
        self.report({"INFO"}, tr("Gradient ramp created."))
        return {"FINISHED"}


class MESH_OT_YLVCInitLightRampData(bpy.types.Operator):
    bl_idname = "mesh.ylvc_init_light_ramp_data"
    bl_label = "Create Light Ramp"
    bl_description = "Create the gradient ramp used by the lighting tools."
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return has_scene(context)

    def execute(self, context):
        ensure_light_ramp_node()
        if context.area:
            context.area.tag_redraw()
        self.report({"INFO"}, tr("Light ramp created."))
        return {"FINISHED"}


class MESH_OT_YLVCTraceRamp(bpy.types.Operator):
    bl_idname = "mesh.ylvc_trace_ramp"
    bl_label = "Draw Viewport Gradient"
    bl_description = "Draw a viewport gradient in the 3D View."
    bl_options = {"REGISTER", "UNDO"}

    grad_type: bpy.props.EnumProperty(
        items=(
            ("LINEAR", "Linear", "Linear screen-space gradient."),
            ("RADIAL", "Radial", "Radial screen-space gradient."),
        ),
        default="LINEAR",
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return active_mesh_has_color_attributes(context) and obj.mode in {"EDIT", "OBJECT"}

    @staticmethod
    def _matrix_bytes(matrix):
        return np.array(matrix, dtype=np.float32).tobytes()

    def _fill_gradient_factors(self, dx, dy, length, length_sq, is_radial, tmp_dx, tmp_dy, tmp_t):
        if is_radial:
            np.multiply(tmp_dx, tmp_dx, out=tmp_t)
            np.multiply(tmp_dy, tmp_dy, out=tmp_dx)
            np.add(tmp_t, tmp_dx, out=tmp_t)
            np.sqrt(tmp_t, out=tmp_t)
            np.divide(tmp_t, max(length, 1e-12), out=tmp_t)
        else:
            np.multiply(tmp_dx, dx, out=tmp_t)
            np.multiply(tmp_dy, dy, out=tmp_dx)
            np.add(tmp_t, tmp_dx, out=tmp_t)
            np.divide(tmp_t, max(length_sq, 1e-12), out=tmp_t)
        np.clip(tmp_t, 0.0, 1.0, out=tmp_t)

    def _refresh_edit_projection_cache(self, context, force=False):
        if getattr(self, "_cached_mode", None) != "EDIT":
            return False
        if context.region is None or context.region_data is None:
            return False

        region_size = (context.region.width, context.region.height)
        world_bytes = self._matrix_bytes(context.active_object.matrix_world)
        perspective_bytes = self._matrix_bytes(context.region_data.perspective_matrix)

        if (
            not force
            and region_size == getattr(self, "_edit_cached_region_size", None)
            and world_bytes == getattr(self, "_edit_cached_world_matrix_bytes", b"")
            and perspective_bytes == getattr(self, "_edit_cached_perspective_matrix_bytes", b"")
        ):
            return True

        homo = getattr(self, "_edit_homo", None)
        if homo is None or len(homo) == 0:
            return False

        mvp_matrix = context.region_data.perspective_matrix @ context.active_object.matrix_world
        mvp_np = np.array(mvp_matrix, dtype=np.float32)
        clip_co = homo @ mvp_np.T
        w_values = clip_co[:, 3]
        valid_mask = w_values > 1e-4

        pts_2d = self._edit_cached_pts_2d
        pts_2d.fill(0.0)
        if np.any(valid_mask):
            ndc = clip_co[valid_mask, :2] / w_values[valid_mask, None]
            pts_2d[valid_mask, 0] = (ndc[:, 0] + 1.0) * 0.5 * context.region.width
            pts_2d[valid_mask, 1] = (ndc[:, 1] + 1.0) * 0.5 * context.region.height

        self._edit_valid_mask[:] = valid_mask
        self._edit_cached_region_size = region_size
        self._edit_cached_world_matrix_bytes = world_bytes
        self._edit_cached_perspective_matrix_bytes = perspective_bytes
        return True

    def _get_valid_edit_cache(self, context):
        if getattr(self, "_cached_mode", None) != "EDIT":
            return False
        obj = context.active_object
        if obj is None or obj.type != "MESH" or obj.mode != "EDIT":
            return False
        return self._refresh_edit_projection_cache(context, force=False)

    def _write_edit_loop_colors(self, colors):
        cached_loops = getattr(self, "_edit_selected_loops", None)
        if not cached_loops:
            return
        layer = getattr(self, "_cached_layer", None)
        write_edit_element_colors(cached_loops, layer, colors)

    def _execute_edit_gradient_fill(self, context, obj, dx, dy, length, length_sq, is_radial, blend_mode, channel_key, is_live):
        if not hasattr(self, "_cached_bm") or not self._get_valid_edit_cache(context):
            return False

        selected_loops = getattr(self, "_edit_selected_loops", None)
        loop_vert_map = getattr(self, "_edit_loop_vert_map", None)
        original_loop_colors = getattr(self, "_edit_original_loop_colors", None)
        if not selected_loops or loop_vert_map is None or original_loop_colors is None:
            return False

        np.subtract(self._edit_cached_pts_2d[:, 0], self.start_pos[0], out=self._edit_tmp_dx_vert)
        np.subtract(self._edit_cached_pts_2d[:, 1], self.start_pos[1], out=self._edit_tmp_dy_vert)
        self._fill_gradient_factors(dx, dy, length, length_sq, is_radial, self._edit_tmp_dx_vert, self._edit_tmp_dy_vert, self._edit_tmp_t_vert)
        self._edit_tmp_t_vert[~self._edit_valid_mask] = 0.0

        np.take(self._edit_tmp_t_vert, loop_vert_map, out=self._edit_tmp_t_loop)
        sample_lut_array_out(
            self.lut,
            self._edit_tmp_t_loop,
            self._edit_target_rgba,
            work_t=self._edit_lut_work_t,
            idx0_buf=self._edit_lut_idx0,
            idx1_buf=self._edit_lut_idx1,
            sample0_buf=self._edit_lut_sample0,
            sample1_buf=self._edit_lut_sample1,
            inv_weight_buf=self._edit_lut_inv_weight,
        )
        np.copyto(self._edit_work_loop_colors, original_loop_colors)
        np.take(self._edit_valid_mask, loop_vert_map, out=self._edit_loop_mask)
        edit_loop_mask_indices = np.flatnonzero(self._edit_loop_mask).astype(np.int32, copy=False)
        blend_colors_np(
            self._edit_work_loop_colors,
            self._edit_target_rgba,
            channel_key,
            blend_mode,
            self._edit_loop_mask,
            mask_indices=edit_loop_mask_indices,
            current_buf=self._edit_blend_current,
            gradient_buf=self._edit_blend_gradient,
            low_mask_buf=self._edit_blend_low_mask,
        )

        self._write_edit_loop_colors(self._edit_work_loop_colors)
        bmesh.update_edit_mesh(obj.data)
        if not is_live:
            display.refresh_after_color_write(
                context,
                obj.data,
                getattr(self, "_cached_edit_layer_name", "") or getattr(context.scene, "ylvc_layer_name", ""),
                obj=obj,
            )
            count = int(edit_loop_mask_indices.size)
            self.report(
                {"INFO"},
                tr_format(
                    "Applied a {grad_type} gradient to {count} corners.",
                    grad_type=self.grad_type.lower(),
                    count=count,
                ),
            )
        return True

    def _execute_object_gradient_fill(self, context, obj, dx, dy, length, length_sq, is_radial, blend_mode, channel_key, is_live):
        cache = self._get_valid_object_cache(context)
        if cache is None:
            if not is_live:
                self.report({"WARNING"}, tr("Gradient cache became invalid. Start the drag again."))
            return False

        mesh, attribute = cache
        np.subtract(self._cached_pts_2d[:, 0], self.start_pos[0], out=self._tmp_dx_vert)
        np.subtract(self._cached_pts_2d[:, 1], self.start_pos[1], out=self._tmp_dy_vert)
        self._fill_gradient_factors(dx, dy, length, length_sq, is_radial, self._tmp_dx_vert, self._tmp_dy_vert, self._tmp_t_vert)
        self._tmp_t_vert[~self._valid_mask] = 0.0

        if self._cached_domain == "POINT":
            sample_lut_array_out(
                self.lut,
                self._tmp_t_vert,
                self._target_rgba,
                work_t=self._lut_work_t,
                idx0_buf=self._lut_idx0,
                idx1_buf=self._lut_idx1,
                sample0_buf=self._lut_sample0,
                sample1_buf=self._lut_sample1,
                inv_weight_buf=self._lut_inv_weight,
            )
        else:
            np.take(self._tmp_t_vert, self._loop_vert_indices, out=self._tmp_t_data)
            sample_lut_array_out(
                self.lut,
                self._tmp_t_data,
                self._target_rgba,
                work_t=self._lut_work_t,
                idx0_buf=self._lut_idx0,
                idx1_buf=self._lut_idx1,
                sample0_buf=self._lut_sample0,
                sample1_buf=self._lut_sample1,
                inv_weight_buf=self._lut_inv_weight,
            )

        np.copyto(self._work_colors_np, self._cached_colors_np)
        blend_source_values_into_colors(
            self._work_colors_np,
            self._target_rgba,
            channel_key,
            blend_mode,
            self._data_mask,
        )
        write_color_array_to_attribute(attribute, self._work_colors_np, mesh=mesh)
        if not is_live:
            display.refresh_after_color_write(context, mesh, self._cached_layer_name, obj=obj)
            count = getattr(self, "_data_mask_count", 0)
            target_label = tr("vertices") if self._cached_domain == "POINT" else tr("corners")
            self.report(
                {"INFO"},
                tr_format(
                    "Applied a {grad_type} gradient to {count} {target_label}.",
                    grad_type=self.grad_type.lower(),
                    count=count,
                    target_label=target_label,
                ),
            )
        return True

    def _cache_original_data(self, context):
        obj = context.active_object
        self._cached_mode = obj.mode

        if obj.mode == "EDIT":
            target, error = resolve_edit_color_layer(context)
            if error:
                return

            self._cached_bm = target.bm
            self._cached_layer = target.layer
            self._cached_edit_layer_name = target.layer_name
            bm = target.bm
            layer = target.layer
            use_selection = bm_use_vert_selection(bm)
            self._edit_use_selection = use_selection
            bm.verts.ensure_lookup_table()
            bm.verts.index_update()

            selected_verts = [vert for vert in bm.verts if vert.select] if use_selection else list(bm.verts)
            selected_loops = [loop for face in bm.faces for loop in face.loops if (not use_selection or loop.vert.select)]
            if not selected_verts or not selected_loops:
                self._edit_selected_verts = []
                self._edit_selected_loops = []
                self._live_vertex_count = 0
                return

            vert_count = len(bm.verts)
            self._edit_selected_verts = selected_verts
            self._edit_selected_loops = selected_loops
            self._edit_selected_vert_indices = np.array([vert.index for vert in selected_verts], dtype=np.int32)
            self._edit_local_coords = np.array([vert.co[:] for vert in selected_verts], dtype=np.float32)
            self._edit_original_loop_colors = _read_edit_loop_colors(selected_loops, layer)
            self._edit_work_loop_colors = np.empty_like(self._edit_original_loop_colors)
            self._edit_target_rgba = np.empty_like(self._edit_original_loop_colors)
            self._edit_cached_pts_2d = np.zeros((len(selected_verts), 2), dtype=np.float32)
            self._edit_valid_mask = np.zeros(len(selected_verts), dtype=bool)
            self._edit_tmp_dx_vert = np.empty(len(selected_verts), dtype=np.float32)
            self._edit_tmp_dy_vert = np.empty(len(selected_verts), dtype=np.float32)
            self._edit_tmp_t_vert = np.empty(len(selected_verts), dtype=np.float32)
            self._edit_tmp_t_loop = np.empty(len(selected_loops), dtype=np.float32)
            self._edit_loop_mask = np.empty(len(selected_loops), dtype=bool)
            self._edit_homo = np.empty((len(selected_verts), 4), dtype=np.float32)
            self._edit_homo[:, :3] = self._edit_local_coords
            self._edit_homo[:, 3] = 1.0
            self._edit_lut_work_t = np.empty(len(selected_loops), dtype=np.float32)
            self._edit_lut_idx0 = np.empty(len(selected_loops), dtype=np.int32)
            self._edit_lut_idx1 = np.empty(len(selected_loops), dtype=np.int32)
            self._edit_lut_sample0 = np.empty((len(selected_loops), 4), dtype=np.float32)
            self._edit_lut_sample1 = np.empty((len(selected_loops), 4), dtype=np.float32)
            self._edit_lut_inv_weight = np.empty(len(selected_loops), dtype=np.float32)
            self._edit_blend_current = np.empty((len(selected_loops), 4), dtype=np.float32)
            self._edit_blend_gradient = np.empty((len(selected_loops), 4), dtype=np.float32)
            self._edit_blend_low_mask = np.empty((len(selected_loops), 4), dtype=bool)

            vert_lookup = np.full(vert_count, -1, dtype=np.int32)
            vert_lookup[self._edit_selected_vert_indices] = np.arange(len(selected_verts), dtype=np.int32)
            self._edit_loop_vert_map = vert_lookup[np.array([loop.vert.index for loop in selected_loops], dtype=np.int32)]
            self._live_vertex_count = len(selected_loops)
            self._refresh_edit_projection_cache(context, force=True)
            return

        if context.region is None or context.region_data is None:
            return

        obj_info, layer_info, error = _get_object_mode_layer_info(context)
        if error or obj_info != obj:
            return

        mesh, attribute, domain, _, layer_name = layer_info
        vert_count = len(mesh.vertices)
        data_count = len(attribute.data)
        selection_scope = resolve_selection_scope(context, attribute)

        local_co = np.empty(vert_count * 3, dtype=np.float32)
        mesh.vertices.foreach_get("co", local_co)
        local_co.shape = (-1, 3)

        mvp_matrix = context.region_data.perspective_matrix @ obj.matrix_world
        mvp_np = np.array(mvp_matrix, dtype=np.float32)

        homo = np.empty((vert_count, 4), dtype=np.float32)
        homo[:, :3] = local_co
        homo[:, 3] = 1.0

        clip_co = homo @ mvp_np.T
        w_values = clip_co[:, 3]
        valid_mask = w_values > 1e-4

        pts_2d = np.zeros((vert_count, 2), dtype=np.float32)
        if np.any(valid_mask):
            ndc = clip_co[valid_mask, :2] / w_values[valid_mask, None]
            pts_2d[valid_mask, 0] = (ndc[:, 0] + 1.0) * 0.5 * context.region.width
            pts_2d[valid_mask, 1] = (ndc[:, 1] + 1.0) * 0.5 * context.region.height

        loop_vert_indices = None
        if domain == "POINT":
            data_mask = valid_mask.copy()
            data_mask &= selection_scope.data_mask
        else:
            loop_vert_indices = np.empty(data_count, dtype=np.int32)
            mesh.loops.foreach_get("vertex_index", loop_vert_indices)
            data_mask = valid_mask[loop_vert_indices]
            data_mask &= selection_scope.data_mask

        self._cached_colors_np = read_color_attribute_colors(mesh, attribute)
        self._work_colors_np = np.empty_like(self._cached_colors_np)
        self._target_rgba = np.empty((data_count, 4), dtype=np.float32)
        self._tmp_dx_vert = np.empty(vert_count, dtype=np.float32)
        self._tmp_dy_vert = np.empty(vert_count, dtype=np.float32)
        self._tmp_t_vert = np.empty(vert_count, dtype=np.float32)
        self._tmp_t_data = np.empty(data_count, dtype=np.float32) if domain == "CORNER" else None

        self._cached_obj_name = obj.name
        self._cached_layer_name = layer_name
        self._cached_domain = domain
        self._cached_data_type = attribute.data_type
        self._cached_data_count = data_count
        self._cached_vert_count = vert_count
        self._cached_region_size = (context.region.width, context.region.height)
        self._cached_world_matrix_np = np.array(obj.matrix_world, dtype=np.float32)
        self._cached_perspective_matrix_np = np.array(context.region_data.perspective_matrix, dtype=np.float32)
        self._cached_pts_2d = pts_2d
        self._valid_mask = valid_mask
        self._loop_vert_indices = loop_vert_indices
        self._data_mask = data_mask
        self._data_mask_indices = np.flatnonzero(data_mask).astype(np.int32, copy=False)
        self._data_mask_count = int(np.count_nonzero(data_mask))
        self._cached_mesh = mesh
        self._cached_attribute = attribute
        self._live_vertex_count = self._data_mask_count
        self._cached_world_matrix_bytes = self._cached_world_matrix_np.tobytes()
        self._cached_perspective_matrix_bytes = self._cached_perspective_matrix_np.tobytes()
        self._lut_work_t = np.empty(data_count, dtype=np.float32)
        self._lut_idx0 = np.empty(data_count, dtype=np.int32)
        self._lut_idx1 = np.empty(data_count, dtype=np.int32)
        self._lut_sample0 = np.empty((data_count, 4), dtype=np.float32)
        self._lut_sample1 = np.empty((data_count, 4), dtype=np.float32)
        self._lut_inv_weight = np.empty(data_count, dtype=np.float32)
        self._blend_current = np.empty((max(data_count, 1), 4), dtype=np.float32)
        self._blend_gradient = np.empty((max(data_count, 1), 4), dtype=np.float32)
        self._blend_low_mask = np.empty((max(data_count, 1), 4), dtype=bool)

    def _get_valid_object_cache(self, context):
        if getattr(self, "_cached_mode", None) != "OBJECT":
            return None
        if context.region is None or context.region_data is None:
            return None

        obj = context.active_object
        if obj is None or obj.type != "MESH" or obj.mode != "OBJECT":
            return None
        if obj.name != getattr(self, "_cached_obj_name", ""):
            return None

        obj_info, layer_info, error = _get_object_mode_layer_info(context)
        if error or obj_info != obj:
            return None

        mesh, attribute, domain, data_type, layer_name = layer_info
        if layer_name != getattr(self, "_cached_layer_name", ""):
            return None
        if domain != getattr(self, "_cached_domain", ""):
            return None
        if data_type != getattr(self, "_cached_data_type", ""):
            return None
        if len(mesh.vertices) != getattr(self, "_cached_vert_count", -1):
            return None
        if len(attribute.data) != getattr(self, "_cached_data_count", -1):
            return None
        if (context.region.width, context.region.height) != getattr(self, "_cached_region_size", (0, 0)):
            return None

        world_bytes = self._matrix_bytes(obj.matrix_world)
        perspective_bytes = self._matrix_bytes(context.region_data.perspective_matrix)
        if world_bytes != getattr(self, "_cached_world_matrix_bytes", b""):
            return None
        if perspective_bytes != getattr(self, "_cached_perspective_matrix_bytes", b""):
            return None

        return mesh, attribute

    def _should_run_live_preview(self):
        now = time.perf_counter()
        if now - getattr(self, "_last_live_time", 0.0) < getattr(self, "_live_interval", 0.0):
            return None

        last_pos = getattr(self, "_last_live_mouse_pos", None)
        if last_pos is not None and self.mouse_pos is not None:
            dx = self.mouse_pos[0] - last_pos[0]
            dy = self.mouse_pos[1] - last_pos[1]
            if (dx * dx + dy * dy) < getattr(self, "_live_mouse_threshold_sq", 0.0):
                return None

        return now

    @staticmethod
    def _get_view3d_shading(context):
        space = getattr(context, "space_data", None)
        if space and space.type == "VIEW_3D":
            return space.shading
        return None

    def _capture_viewport_state(self, context):
        self._viewport_state = None
        shading = self._get_view3d_shading(context)
        if not shading:
            return

        self._viewport_state = {
            "color_type": getattr(shading, "color_type", ""),
            "light": getattr(shading, "light", ""),
        }

    def _restore_viewport_state(self, context):
        state = getattr(self, "_viewport_state", None)
        if not state:
            return

        shading = self._get_view3d_shading(context)
        if not shading:
            return

        color_type = state.get("color_type", "")
        light = state.get("light", "")
        if color_type:
            try:
                shading.color_type = color_type
            except Exception:
                pass
        if light:
            try:
                shading.light = light
            except Exception:
                pass

    def invoke(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D":
            self.report({"WARNING"}, tr("Run this tool in the 3D View."))
            return {"CANCELLED"}

        obj = context.active_object
        if obj is not None and obj.mode == "EDIT":
            target, error = resolve_edit_color_layer(context)
            if error:
                self.report({"WARNING"}, error)
                return {"CANCELLED"}
            if target.domain == "POINT":
                self.report({"WARNING"}, tr("Viewport Gradient needs a Face Corner color attribute in Edit Mode."))
                return {"CANCELLED"}

        ramp_node = ensure_ramp_node()
        if ramp_node is None or not ramp_node.color_ramp:
            self.report({"ERROR"}, tr("Could not create the gradient ramp."))
            return {"CANCELLED"}

        self.lut = build_ramp_lut(ramp_node.color_ramp, 512)
        context.scene.ylvc_is_tracing = True
        if hasattr(context.scene, "ylvc_tracing_type"):
            context.scene.ylvc_tracing_type = self.grad_type

        self.state = "WAITING"
        self.start_pos = None
        self.mouse_pos = None
        self._handle = None
        self._live_vertex_count = 0
        self._edit_use_selection = False
        self._last_live_time = 0.0
        self._live_interval = 1.0 / 30.0
        self._last_live_mouse_pos = None
        self._live_mouse_threshold_sq = 4.0
        self._capture_viewport_state(context)

        self._draw_state = {
            "start_pos": None,
            "mouse_pos": None,
            "lut": self.lut,
            "grad_type": self.grad_type,
            "area_ptr": context.area.as_pointer() if context.area is not None else None,
            "region_ptr": context.region.as_pointer() if context.region is not None else None,
        }

        display.ensure_preview_visible(context)

        self._handle = bpy.types.SpaceView3D.draw_handler_add(
            draw_gradient_overlay_callback,
            (self._draw_state,),
            "WINDOW",
            "POST_PIXEL",
        )

        context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set(tr("Drag with LMB to draw. Hold Ctrl to snap. RMB or Esc cancels."))
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if context.area:
            context.area.tag_redraw()

        if event.type in {"RIGHTMOUSE", "ESC"}:
            self._restore_cached_preview(context)
            self._finish(context)
            return {"CANCELLED"}

        if self.state == "WAITING":
            if event.type == "LEFTMOUSE" and event.value == "PRESS":
                self.start_pos = (event.mouse_region_x, event.mouse_region_y)
                self.mouse_pos = self.start_pos
                self._draw_state["start_pos"] = self.start_pos
                self._draw_state["mouse_pos"] = self.mouse_pos
                self._last_live_mouse_pos = self.start_pos
                self._last_live_time = 0.0
                self.state = "DRAWING"
                self._cache_original_data(context)
            return {"RUNNING_MODAL"}

        if self.state == "DRAWING":
            if event.type == "MOUSEMOVE":
                mx = event.mouse_region_x
                my = event.mouse_region_y

                if event.ctrl:
                    dx = mx - self.start_pos[0]
                    dy = my - self.start_pos[1]
                    if dx != 0 or dy != 0:
                        angle = math.atan2(dy, dx)
                        snap_angle = round(angle / (math.pi / 12.0)) * (math.pi / 12.0)
                        length = math.hypot(dx, dy)
                        self.mouse_pos = (
                            self.start_pos[0] + math.cos(snap_angle) * length,
                            self.start_pos[1] + math.sin(snap_angle) * length,
                        )
                    else:
                        self.mouse_pos = (mx, my)
                else:
                    self.mouse_pos = (mx, my)

                self._draw_state["mouse_pos"] = self.mouse_pos

                if getattr(context.scene, "ylvc_use_live_gradient", False):
                    live_time = self._should_run_live_preview()
                    if live_time is not None and self.execute_gradient_fill(context, is_live=True):
                        self._last_live_time = live_time
                        self._last_live_mouse_pos = self.mouse_pos

            elif event.type == "LEFTMOUSE" and event.value == "RELEASE":
                success = self.execute_gradient_fill(context, is_live=False)
                self._finish(context)
                return {"FINISHED"} if success else {"CANCELLED"}

        return {"RUNNING_MODAL"}

    def _finish(self, context):
        if getattr(self, "_handle", None) is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, "WINDOW")
            self._handle = None
        context.workspace.status_text_set(None)
        self._restore_viewport_state(context)
        context.scene.ylvc_is_tracing = False
        if hasattr(context.scene, "ylvc_tracing_type"):
            context.scene.ylvc_tracing_type = ""
        if context.area:
            context.area.tag_redraw()

    def _restore_cached_preview(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            return

        if getattr(self, "_cached_mode", None) == "EDIT":
            bm = getattr(self, "_cached_bm", None)
            layer = getattr(self, "_cached_layer", None)
            cached_colors = getattr(self, "_edit_original_loop_colors", None)
            cached_loops = getattr(self, "_edit_selected_loops", None)
            if bm is None or layer is None or cached_colors is None or not cached_loops:
                return

            for loop, color in zip(cached_loops, cached_colors):
                try:
                    loop[layer] = color.tolist()
                except Exception:
                    pass
            bmesh.update_edit_mesh(obj.data)
            return

        mesh = getattr(self, "_cached_mesh", None)
        attribute = getattr(self, "_cached_attribute", None)
        cached_colors = getattr(self, "_cached_colors_np", None)
        if mesh is None or attribute is None or cached_colors is None:
            return

        try:
            restore_color_array_to_attribute(attribute, cached_colors, mesh=mesh)
            display.refresh_after_color_write(context, mesh, getattr(self, "_cached_layer_name", ""), obj=obj)
        except Exception:
            pass

    def execute_gradient_fill(self, context, is_live=False):
        obj = context.active_object
        if context.region is None or context.region_data is None or self.lut is None:
            return False

        x1, y1 = self.start_pos
        x2, y2 = self.mouse_pos
        dx = x2 - x1
        dy = y2 - y1
        length_sq = dx * dx + dy * dy
        if length_sq <= 1e-6:
            return False

        length = math.sqrt(length_sq)
        is_radial = self.grad_type == "RADIAL"
        blend_mode = context.scene.ylvc_blend_mode
        channel_key = context.scene.ylvc_channel

        if obj.mode == "EDIT":
            return self._execute_edit_gradient_fill(context, obj, dx, dy, length, length_sq, is_radial, blend_mode, channel_key, is_live)

        return self._execute_object_gradient_fill(context, obj, dx, dy, length, length_sq, is_radial, blend_mode, channel_key, is_live)


CLASSES = (
    MESH_OT_YLVCInitRampData,
    MESH_OT_YLVCInitLightRampData,
    MESH_OT_YLVCTraceRamp,
)
