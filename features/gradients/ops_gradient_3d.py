# -*- coding: utf-8 -*-
import math
import time

import bpy
import numpy as np

from ...core.blend import blend_colors_np
from ...core.color_attribute import read_color_attribute_colors
from ...core.color_attribute import resolve_target_color_attribute
from ...core.mesh_topology import loop_vertex_indices as cached_loop_vertex_indices
from ...core.selection_scope import resolve_selection_scope
from ...core.operator_poll import active_mesh_has_color_attributes, has_scene
from ...core.write_engine import (
    restore_color_array_to_attribute,
    write_color_array_to_attribute,
)
from ...i18n import tr, tr_format
from ...services import display
from .core_color_engine import (
    adapt_gradient_source_for_channel,
    build_ramp_lut,
    ensure_ramp_node,
    find_ramp_node,
    sample_lut_array_out,
)
from .core_overlay import draw_gradient_overlay_callback


LIVE_WRITE_MAX_COLOR_ENTRIES = 150_000
LIVE_WRITE_MAX_POLYGONS = 50_000
LARGE_MESH_OVERLAY_INTERVAL = 1.0 / 60.0
LARGE_MESH_OVERLAY_MOUSE_THRESHOLD_SQ = 0.0


def _get_object_mode_layer_info(context):
    target, error = resolve_target_color_attribute(context)
    if error:
        return None, None, error

    return target.obj, (target.mesh, target.color_attr, target.domain, target.data_type, target.layer_name), None


class MESH_OT_YLVCInitRampData(bpy.types.Operator):
    bl_idname = "mesh.ylvc_init_ramp_data"
    bl_label = "Create Ramp"
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


class MESH_OT_YLVCTraceRamp(bpy.types.Operator):
    bl_idname = "mesh.ylvc_trace_ramp"
    bl_label = "Draw Screen Gradient"
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
        return active_mesh_has_color_attributes(context) and obj is not None

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

    def _execute_object_gradient_fill(self, context, obj, dx, dy, length, length_sq, is_radial, blend_mode, channel_key, *, report=True, live=False):
        cache = self._get_valid_object_cache(context, full_check=not live)
        if cache is None:
            self.report({"WARNING"}, tr("Gradient cache became invalid. Start the drag again."))
            return False

        mesh, attribute = cache
        count = getattr(self, "_data_mask_count", 0)
        if count <= 0:
            return True

        np.subtract(self._active_pts_2d[:, 0], self.start_pos[0], out=self._tmp_dx_active)
        np.subtract(self._active_pts_2d[:, 1], self.start_pos[1], out=self._tmp_dy_active)
        self._fill_gradient_factors(dx, dy, length, length_sq, is_radial, self._tmp_dx_active, self._tmp_dy_active, self._tmp_t_active)

        sample_lut_array_out(
            self.lut,
            self._tmp_t_active,
            self._target_rgba_active,
            work_t=self._lut_work_t,
            idx0_buf=self._lut_idx0,
            idx1_buf=self._lut_idx1,
            sample0_buf=self._lut_sample0,
            sample1_buf=self._lut_sample1,
            inv_weight_buf=self._lut_inv_weight,
        )
        adapt_gradient_source_for_channel(self._target_rgba_active, channel_key)

        if getattr(self, "_work_colors_initialized", False):
            if self._data_mask_indices is None:
                np.copyto(self._work_colors_np, self._cached_colors_np)
            else:
                self._work_colors_np[self._data_mask_indices] = self._cached_colors_np[self._data_mask_indices]
        else:
            np.copyto(self._work_colors_np, self._cached_colors_np)
            self._work_colors_initialized = True
        if self._data_mask_indices is None:
            blend_colors_np(
                self._work_colors_np,
                self._target_rgba_active,
                channel_key,
                blend_mode,
            )
        else:
            blend_colors_np(
                self._work_colors_np,
                self._target_rgba_active,
                channel_key,
                blend_mode,
                mask_indices=self._data_mask_indices,
                current_buf=self._blend_current,
                source_buf=self._blend_gradient,
                low_mask_buf=self._blend_low_mask,
                source_is_compact=True,
            )
        write_color_array_to_attribute(attribute, self._work_colors_np, mesh=mesh, update_mesh=False)
        display.finish_color_write(
            context,
            mesh,
            self._cached_layer_name,
            obj=obj,
            ensure_preview=False,
            force_view_update=not live,
            source_colors=self._work_colors_np,
            defer_preview_sync=True,
        )
        target_label = tr("vertices") if self._cached_domain == "POINT" else tr("corners")
        if report:
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

    def _cache_light_context(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            return False

        self._cached_mode = obj.mode
        self._write_cache_ready = False
        self._data_mask_count = 0

        if context.region is None or context.region_data is None:
            return False

        obj_info, layer_info, error = _get_object_mode_layer_info(context)
        if error or obj_info != obj:
            return False

        mesh, attribute, domain, data_type, layer_name = layer_info
        vert_count = len(mesh.vertices)
        data_count = len(attribute.data)
        polygon_count = len(mesh.polygons)

        self._cached_obj_name = obj.name
        self._cached_layer_name = layer_name
        self._cached_domain = domain
        self._cached_data_type = data_type
        self._cached_data_count = data_count
        self._cached_polygon_count = polygon_count
        self._cached_vert_count = vert_count
        self._cached_region_size = (context.region.width, context.region.height)
        self._cached_world_matrix_np = np.array(obj.matrix_world, dtype=np.float32)
        self._cached_perspective_matrix_np = np.array(context.region_data.perspective_matrix, dtype=np.float32)
        self._cached_world_matrix_bytes = self._cached_world_matrix_np.tobytes()
        self._cached_perspective_matrix_bytes = self._cached_perspective_matrix_np.tobytes()
        self._cached_mesh = mesh
        self._cached_attribute = attribute
        self._live_vertex_count = data_count
        self._live_write_enabled = (
            data_count <= LIVE_WRITE_MAX_COLOR_ENTRIES
            and polygon_count <= LIVE_WRITE_MAX_POLYGONS
        )
        return True

    def _cache_original_data(self, context):
        if not getattr(self, "_cached_mesh", None) and not self._cache_light_context(context):
            return False

        cache = self._get_valid_object_cache(context)
        if cache is None:
            return False

        obj = context.active_object
        mesh, attribute = cache
        domain = self._cached_domain
        vert_count = self._cached_vert_count
        data_count = self._cached_data_count
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
            loop_vert_indices = selection_scope.loop_vertex_indices
            if loop_vert_indices is None or len(loop_vert_indices) != data_count:
                loop_vert_indices = cached_loop_vertex_indices(mesh)
            data_mask = valid_mask[loop_vert_indices]
            data_mask &= selection_scope.data_mask

        self._cached_colors_np = read_color_attribute_colors(mesh, attribute)
        self._work_colors_np = np.empty_like(self._cached_colors_np)
        data_mask_count = int(np.sum(data_mask)) if data_mask.size > 0 else 0
        data_mask_indices = None if data_mask_count == data_count else np.flatnonzero(data_mask).astype(np.int32, copy=False)
        if domain == "POINT":
            active_pts_2d = pts_2d if data_mask_indices is None else pts_2d[data_mask_indices].copy()
        else:
            active_pts_2d = pts_2d[loop_vert_indices].copy() if data_mask_indices is None else pts_2d[loop_vert_indices[data_mask_indices]].copy()

        self._target_rgba_active = np.empty((data_mask_count, 4), dtype=np.float32)
        self._tmp_dx_active = np.empty(data_mask_count, dtype=np.float32)
        self._tmp_dy_active = np.empty(data_mask_count, dtype=np.float32)
        self._tmp_t_active = np.empty(data_mask_count, dtype=np.float32)

        self._cached_pts_2d = pts_2d
        self._valid_mask = valid_mask
        self._loop_vert_indices = loop_vert_indices
        self._data_mask_indices = data_mask_indices
        self._data_mask_count = data_mask_count
        self._active_pts_2d = active_pts_2d
        self._cached_mesh = mesh
        self._cached_attribute = attribute
        self._work_colors_initialized = False
        self._live_vertex_count = self._data_mask_count
        buffer_count = max(data_mask_count, 1)
        self._lut_work_t = np.empty(buffer_count, dtype=np.float32)
        self._lut_idx0 = np.empty(buffer_count, dtype=np.int32)
        self._lut_idx1 = np.empty(buffer_count, dtype=np.int32)
        self._lut_sample0 = np.empty((buffer_count, 4), dtype=np.float32)
        self._lut_sample1 = np.empty((buffer_count, 4), dtype=np.float32)
        self._lut_inv_weight = np.empty(buffer_count, dtype=np.float32)
        self._blend_current = np.empty((buffer_count, 4), dtype=np.float32)
        self._blend_gradient = np.empty((buffer_count, 4), dtype=np.float32)
        self._blend_low_mask = np.empty((buffer_count, 4), dtype=bool)
        self._write_cache_ready = True
        return True

    def _ensure_write_cache(self, context):
        if getattr(self, "_write_cache_ready", False):
            return self._get_valid_object_cache(context) is not None
        return self._cache_original_data(context)

    def _get_valid_object_cache(self, context, *, full_check=True):
        if getattr(self, "_cached_mode", None) != "OBJECT":
            return None
        if context.region is None or context.region_data is None:
            return None

        obj = context.active_object
        if obj is None or obj.type != "MESH" or obj.mode != "OBJECT":
            return None
        if obj.name != getattr(self, "_cached_obj_name", ""):
            return None

        if not full_check:
            mesh = getattr(self, "_cached_mesh", None)
            attribute = getattr(self, "_cached_attribute", None)
            if mesh is None or attribute is None:
                return None
            return mesh, attribute

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

    def _should_update_overlay(self, mouse_pos):
        if getattr(self, "_live_write_enabled", True):
            return True

        now = time.perf_counter()
        last_time = getattr(self, "_last_overlay_time", 0.0)
        if now - last_time < LARGE_MESH_OVERLAY_INTERVAL:
            return False

        last_pos = getattr(self, "_last_overlay_mouse_pos", None)
        if last_pos is not None and mouse_pos is not None:
            dx = mouse_pos[0] - last_pos[0]
            dy = mouse_pos[1] - last_pos[1]
            if LARGE_MESH_OVERLAY_MOUSE_THRESHOLD_SQ > 0.0 and (dx * dx + dy * dy) < LARGE_MESH_OVERLAY_MOUSE_THRESHOLD_SQ:
                return False

        self._last_overlay_time = now
        self._last_overlay_mouse_pos = mouse_pos
        return True

    def _update_overlay_mouse(self, context, mouse_pos, *, force=False):
        if force or self._should_update_overlay(mouse_pos):
            self._draw_state["mouse_pos"] = mouse_pos
            if context.area:
                context.area.tag_redraw()
            return True
        return False

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
        if obj is not None and getattr(obj, "mode", "OBJECT") != "OBJECT":
            try:
                context.view_layer.objects.active = obj
                bpy.ops.object.mode_set(mode="OBJECT")
            except Exception:
                pass

        ramp_node = find_ramp_node()
        if ramp_node is None or not ramp_node.color_ramp:
            self.report({"WARNING"}, tr("Create the gradient ramp first."))
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
        self._last_live_time = 0.0
        self._live_interval = 1.0 / 30.0
        self._last_live_mouse_pos = None
        self._live_mouse_threshold_sq = 4.0
        self._last_overlay_time = 0.0
        self._last_overlay_mouse_pos = None
        self._live_write_enabled = False
        self._write_cache_ready = False
        self._capture_viewport_state(context)

        self._draw_state = {
            "start_pos": None,
            "mouse_pos": None,
            "lut": self.lut,
            "grad_type": self.grad_type,
            "area_ptr": context.area.as_pointer() if context.area is not None else None,
            "region_ptr": context.region.as_pointer() if context.region is not None else None,
        }

        self._handle = bpy.types.SpaceView3D.draw_handler_add(
            draw_gradient_overlay_callback,
            (self._draw_state,),
            "WINDOW",
            "POST_PIXEL",
        )

        try:
            context.window_manager.modal_handler_add(self)
            context.workspace.status_text_set(tr("Drag with LMB to draw. Hold Ctrl to snap. RMB or Esc cancels."))
        except Exception as exc:
            self._finish(context)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        try:
            return self._modal_impl(context, event)
        except Exception as exc:
            self._handle_modal_exception(context, exc)
            return {"CANCELLED"}

    def cancel(self, context):
        self._finish(context)

    def _handle_modal_exception(self, context, exc):
        try:
            self.report({"ERROR"}, str(exc))
        except Exception:
            pass
        try:
            self._restore_cached_preview(context)
        except Exception:
            pass
        self._finish(context)

    def _modal_impl(self, context, event):
        if event.type in {"RIGHTMOUSE", "ESC"}:
            self._restore_cached_preview(context)
            self._finish(context)
            return {"CANCELLED"}

        if self.state == "WAITING":
            if event.type == "LEFTMOUSE" and event.value == "PRESS":
                self.start_pos = (event.mouse_region_x, event.mouse_region_y)
                self.mouse_pos = self.start_pos
                self._draw_state["start_pos"] = self.start_pos
                self._update_overlay_mouse(context, self.mouse_pos, force=True)
                self._last_live_mouse_pos = self.start_pos
                self._last_live_time = 0.0
                self._last_overlay_time = 0.0
                self._last_overlay_mouse_pos = self.start_pos
                self.state = "DRAWING"
                if self._cache_light_context(context) and self._live_write_enabled:
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

                self._update_overlay_mouse(context, self.mouse_pos)
                if getattr(self, "_live_write_enabled", True):
                    live_now = self._should_run_live_preview()
                    if live_now is not None:
                        success = self.execute_gradient_fill(context, report=False, live=True)
                        if success:
                            self._last_live_time = live_now
                            self._last_live_mouse_pos = self.mouse_pos

            elif event.type == "LEFTMOUSE" and event.value == "RELEASE":
                self.mouse_pos = (event.mouse_region_x, event.mouse_region_y)
                success = self.execute_gradient_fill(context, report=True)
                self._finish(context)
                return {"FINISHED"} if success else {"CANCELLED"}

        return {"RUNNING_MODAL"}

    def _finish(self, context):
        if getattr(self, "_handle", None) is not None:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(self._handle, "WINDOW")
            except Exception:
                pass
            finally:
                self._handle = None
        try:
            context.workspace.status_text_set(None)
        except Exception:
            pass
        self._restore_viewport_state(context)
        scene = getattr(context, "scene", None)
        if scene is not None:
            try:
                scene.ylvc_is_tracing = False
            except Exception:
                pass
            if hasattr(scene, "ylvc_tracing_type"):
                scene.ylvc_tracing_type = ""
        area = getattr(context, "area", None)
        if area:
            area.tag_redraw()

    def _restore_cached_preview(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            return

        mesh = getattr(self, "_cached_mesh", None)
        attribute = getattr(self, "_cached_attribute", None)
        cached_colors = getattr(self, "_cached_colors_np", None)
        if mesh is None or attribute is None or cached_colors is None:
            return

        try:
            restore_color_array_to_attribute(attribute, cached_colors, mesh=mesh, update_mesh=False)
            display.finish_color_write(context, mesh, getattr(self, "_cached_layer_name", ""), obj=obj)
        except Exception:
            pass

    def execute_gradient_fill(self, context, report=True, live=False):
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

        if not self._ensure_write_cache(context):
            self.report({"WARNING"}, tr("Gradient cache became invalid. Start the drag again."))
            return False

        length = math.sqrt(length_sq)
        is_radial = self.grad_type == "RADIAL"
        blend_mode = context.scene.ylvc_blend_mode
        channel_key = context.scene.ylvc_channel

        return self._execute_object_gradient_fill(context, obj, dx, dy, length, length_sq, is_radial, blend_mode, channel_key, report=report, live=live)


CLASSES = (
    MESH_OT_YLVCInitRampData,
    MESH_OT_YLVCTraceRamp,
)
