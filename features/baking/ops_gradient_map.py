import bpy
import math
import time
import numpy as np
from ...core.color_attribute import (
    read_color_attribute_colors,
    refresh_color_attribute_reference,
    resolve_target_color_attribute,
)
from ...core.selection_scope import (
    resolve_loop_auto_mask_for_object,
    resolve_vertex_auto_mask_for_object,
)
from ...core.operator_poll import has_active_mesh
from ...core.write_engine import restore_color_array_to_attribute, write_blended_color_array_to_attribute
from ...i18n import tr, tr_format
from ...services import display, transactions
from ..gradients.core_color_engine import adapt_gradient_source_for_channel, build_ramp_lut, find_ramp_node, sample_lut_array_out
from ..gradients.core_overlay import draw_gradient_overlay_callback


LIVE_WRITE_MAX_COLOR_ENTRIES = 150_000
LIVE_WRITE_MAX_POLYGONS = 50_000
LARGE_MESH_OVERLAY_INTERVAL = 1.0 / 20.0
LARGE_MESH_OVERLAY_MOUSE_THRESHOLD_SQ = 16.0


# ==========================================
# Helpers
# ==========================================

def _resolve_directional_color_target(context, obj):
    target, error = resolve_target_color_attribute(context, activate=False)
    if error:
        return None, error
    if target.obj != obj:
        return None, tr("Active mesh changed while preparing directional lighting.")
    if target.domain not in {"POINT", "CORNER"}:
        return None, tr_format("Unsupported color domain: {domain}", domain=target.domain)
    if target.data_type not in {"FLOAT_COLOR", "BYTE_COLOR"}:
        return None, tr("Select a color attribute first.")
    try:
        has_color_data = len(target.color_attr.data) == 0 or hasattr(target.color_attr.data[0], "color")
    except Exception:
        has_color_data = False
    if not has_color_data:
        return None, tr("Select a color attribute first.")
    return target, None


def get_world_normals_numpy(obj, mesh):
    """Read vertex normals, convert them to world space, and normalize them."""
    vert_count = len(mesh.vertices)

    normals = np.empty(vert_count * 3, dtype=np.float32)
    mesh.vertices.foreach_get("normal", normals)
    normals.shape = (-1, 3)

    normal_matrix = np.array(
        obj.matrix_world.to_3x3().inverted().transposed(),
        dtype=np.float32,
    )

    world_normals = normals @ normal_matrix.T

    norms = np.linalg.norm(world_normals, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0

    world_normals /= norms
    return world_normals


# ==========================================
# Directional Lighting Operator
# ==========================================

class MESH_OT_YLVCLightMask(bpy.types.Operator):
    bl_idname = "mesh.ylvc_light_mask"
    bl_label = "Light Mask"
    bl_description = "Drag in the viewport to project directional lighting through the shared color ramp"
    bl_options = {"REGISTER", "UNDO"}

    # Skip tiny mouse moves to avoid unnecessary updates.
    mouse_move_threshold: int = 2

    # Skip redraws when the direction barely changes.
    direction_dot_threshold: float = 0.99995

    @classmethod
    def poll(cls, context):
        return has_active_mesh(context)

    def invoke(self, context, event):
        obj = context.active_object

        if not obj or obj.type != "MESH":
            self.report({"WARNING"}, tr("Select a mesh object first."))
            return {"CANCELLED"}

        if obj.mode != "OBJECT":
            transactions.ensure_object_mode_for(context, obj)
        if obj.mode != "OBJECT":
            self.report({"WARNING"}, tr("Could not switch to Object Mode for directional lighting."))
            return {"CANCELLED"}

        ramp_node = find_ramp_node()
        if ramp_node is None or not getattr(ramp_node, "color_ramp", None):
            self.report({"WARNING"}, tr("Create the gradient ramp first."))
            return {"CANCELLED"}

        target, error = _resolve_directional_color_target(context, obj)
        if error:
            self.report({"WARNING"}, error)
            return {"CANCELLED"}

        mesh = target.mesh
        color_attr = target.color_attr

        self.obj = obj
        self.mesh = mesh
        self.color_attr = color_attr
        self.layer_name = color_attr.name
        self.domain = color_attr.domain

        vert_count = len(mesh.vertices)
        data_count = len(color_attr.data)
        polygon_count = len(mesh.polygons)

        if vert_count == 0 or data_count == 0:
            self.report({"WARNING"}, tr("The object has no writable color data."))
            return {"CANCELLED"}

        # Cache world-space normals.
        self.world_normals_np = get_world_normals_numpy(obj, mesh)

        # Cache original colors so cancel can restore them.
        self.orig_colors = read_color_attribute_colors(mesh, self.color_attr)

        affect_selection = getattr(context.scene, "ylvc_affect_selection", True)

        if self.domain == "POINT":
            self.data_mask = resolve_vertex_auto_mask_for_object(
                obj,
                use_live_edit=False,
                affect_selection=affect_selection,
            )
        else:
            self.data_mask = None

        # Preallocate packed buffers for the modal session.
        self.work_colors = np.empty_like(self.orig_colors)
        self.ramp_colors = np.empty((data_count, 4), dtype=np.float32)

        # Per-vertex lighting values.
        self.tmp_t_vert = np.empty(vert_count, dtype=np.float32)

        # CORNER attributes need a vertex-to-loop remap.
        self.loop_vi = None
        self.tmp_t_data = None

        if self.domain == "CORNER":
            self.loop_vi = np.empty(data_count, dtype=np.int32)
            mesh.loops.foreach_get("vertex_index", self.loop_vi)
            self.tmp_t_data = np.empty(data_count, dtype=np.float32)
            self.data_mask = resolve_loop_auto_mask_for_object(
                obj,
                self.loop_vi,
                use_live_edit=False,
                affect_selection=affect_selection,
            )

        self.start_pos = None
        self.mouse_pos = None
        self._handle = None
        self.last_mouse_pos = None
        self.last_direction = None
        self.has_dragged = False
        self._last_overlay_time = 0.0
        self._last_overlay_mouse_pos = None
        self._live_write_enabled = (
            data_count <= LIVE_WRITE_MAX_COLOR_ENTRIES
            and polygon_count <= LIVE_WRITE_MAX_POLYGONS
        )
        self.lut = build_ramp_lut(ramp_node.color_ramp, 512)
        context.scene.ylvc_is_tracing = True
        if hasattr(context.scene, "ylvc_tracing_type"):
            context.scene.ylvc_tracing_type = "LIGHT_DIRECTION"

        self._draw_state = {
            "start_pos": None,
            "mouse_pos": None,
            "lut": self.lut,
            "grad_type": "LINEAR",
        }

        self._handle = bpy.types.SpaceView3D.draw_handler_add(
            draw_gradient_overlay_callback,
            (self._draw_state,),
            "WINDOW",
            "POST_PIXEL",
        )

        try:
            context.window_manager.modal_handler_add(self)
            context.workspace.status_text_set(tr("Drag with LMB to define the light direction. RMB or Esc cancels."))
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
            restore_color_array_to_attribute(self.color_attr, self.orig_colors, mesh=self.mesh, update_mesh=False)
            self._refresh_color_display(context, self.orig_colors)
        except Exception:
            pass
        self._finish(context)

    def _modal_impl(self, context, event):
        if self.obj is None or self.obj.name not in bpy.data.objects:
            self._finish(context)
            return {"CANCELLED"}

        if event.type in {"RIGHTMOUSE", "ESC"}:
            try:
                restore_color_array_to_attribute(self.color_attr, self.orig_colors, mesh=self.mesh, update_mesh=False)
                self._refresh_color_display(context, self.orig_colors)
            except Exception:
                pass

            self._finish(context)
            return {"CANCELLED"}

        if event.type == "LEFTMOUSE":
            if event.value == "PRESS":
                self.start_pos = (event.mouse_region_x, event.mouse_region_y)
                self.mouse_pos = self.start_pos
                self.last_mouse_pos = self.start_pos
                self.last_direction = None
                self.has_dragged = False
                self._draw_state["start_pos"] = self.start_pos
                self._update_overlay_mouse(context, self.start_pos, force=True)
                self._last_overlay_time = 0.0
                self._last_overlay_mouse_pos = self.start_pos

            elif event.value == "RELEASE" and self.start_pos is not None:
                self.mouse_pos = (event.mouse_region_x, event.mouse_region_y)
                if not getattr(self, "_live_write_enabled", True):
                    self.execute_mask_engine(context)
                self._finish(context)
                return {"FINISHED"}

        if event.type == "MOUSEMOVE" and self.start_pos is not None:
            new_mouse_pos = (event.mouse_region_x, event.mouse_region_y)

            if self.last_mouse_pos is not None:
                dxp = new_mouse_pos[0] - self.last_mouse_pos[0]
                dyp = new_mouse_pos[1] - self.last_mouse_pos[1]
                threshold_sq = self.mouse_move_threshold * self.mouse_move_threshold
                if not getattr(self, "_live_write_enabled", True):
                    threshold_sq = LARGE_MESH_OVERLAY_MOUSE_THRESHOLD_SQ
                if (dxp * dxp + dyp * dyp) < threshold_sq:
                    return {"RUNNING_MODAL"}

            self.mouse_pos = new_mouse_pos
            self.last_mouse_pos = new_mouse_pos
            self._update_overlay_mouse(context, self.mouse_pos)

            if not getattr(self, "_live_write_enabled", True):
                return {"RUNNING_MODAL"}

            if self.execute_mask_engine(context):
                self.has_dragged = True

        return {"RUNNING_MODAL"}

    def execute_mask_engine(self, context):
        if not self._refresh_writable_color_attribute(context):
            return False

        if self.start_pos is None or self.mouse_pos is None:
            return False

        if self.lut is None:
            return False

        region_data = context.region_data
        if region_data is None:
            return False

        x1, y1 = self.start_pos
        x2, y2 = self.mouse_pos

        # Keep the original direction logic based on start minus end.
        dx = x1 - x2
        dy = y1 - y2

        length = math.hypot(dx, dy)
        if length < 1e-6:
            return False

        nx = dx / length
        ny = dy / length

        view_inv = region_data.view_matrix.inverted()

        right = np.array(view_inv.col[0][:3], dtype=np.float32)
        up = np.array(view_inv.col[1][:3], dtype=np.float32)

        direction = right * nx + up * ny

        direction_len = np.linalg.norm(direction)
        if direction_len < 1e-6:
            return False

        direction /= direction_len

        # Skip redundant updates when the direction is effectively unchanged.
        if self.last_direction is not None:
            similarity = float(np.dot(self.last_direction, direction))
            if similarity > self.direction_dot_threshold:
                return False

        self.last_direction = direction.copy()

        # Project the light direction onto the vertex normals.
        np.dot(self.world_normals_np, direction, out=self.tmp_t_vert)
        np.clip(self.tmp_t_vert, 0.0, 1.0, out=self.tmp_t_vert)

        if self.domain == "POINT":
            t_data = self.tmp_t_vert
        else:
            np.take(self.tmp_t_vert, self.loop_vi, out=self.tmp_t_data)
            t_data = self.tmp_t_data

        sample_lut_array_out(self.lut, t_data, self.ramp_colors)
        channel_key = getattr(context.scene, "ylvc_channel", "RGB")
        blend_mode = getattr(context.scene, "ylvc_blend_mode", "REPLACE")
        adapt_gradient_source_for_channel(self.ramp_colors, channel_key)

        self.work_colors = write_blended_color_array_to_attribute(
            self.color_attr,
            self.orig_colors,
            self.ramp_colors,
            channel_key=channel_key,
            blend_mode=blend_mode,
            mask=self.data_mask,
            mesh=self.mesh,
        )
        self._refresh_color_display(context, self.work_colors)

        return True

    def _refresh_writable_color_attribute(self, context):
        layer_name = getattr(self, "layer_name", "")
        mesh = getattr(self, "mesh", None)
        if mesh is None or not layer_name:
            return False

        expected_count = len(getattr(self, "orig_colors", ()))
        color_attr = refresh_color_attribute_reference(mesh, getattr(self, "color_attr", None))
        if color_attr is None:
            try:
                named_attr = mesh.color_attributes.get(layer_name)
            except Exception:
                named_attr = None
            color_attr = refresh_color_attribute_reference(mesh, named_attr)
        data_count = len(color_attr.data) if color_attr is not None else 0

        if color_attr is not None and data_count == expected_count:
            self.color_attr = color_attr
            return True

        target, error = _resolve_directional_color_target(context, getattr(self, "obj", None))
        if error or target is None or target.layer_name != layer_name:
            message = error or tr("Active color attribute changed during directional lighting.")
            try:
                self.report({"WARNING"}, message)
            except Exception:
                pass
            return False

        try:
            data_count = len(target.color_attr.data)
        except Exception:
            data_count = 0
        if data_count != expected_count:
            try:
                self.report(
                    {"WARNING"},
                    tr_format(
                        "Color data count changed during directional lighting. Expected {expected}, got {actual}.",
                        expected=expected_count,
                        actual=data_count,
                    ),
                )
            except Exception:
                pass
            return False

        self.color_attr = target.color_attr
        return True

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
            if (dx * dx + dy * dy) < LARGE_MESH_OVERLAY_MOUSE_THRESHOLD_SQ:
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

    def _refresh_color_display(self, context, colors):
        channel_key = getattr(context.scene, "ylvc_channel", "RGB")
        if channel_key == "RGB":
            return
        display.finish_color_write(
            context,
            self.mesh,
            getattr(self, "layer_name", self.color_attr.name),
            obj=self.obj,
            ensure_preview=False,
            source_colors=colors,
            defer_preview_sync=True,
        )

    def _finish(self, context):
        if getattr(self, "_handle", None) is not None:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(self._handle, "WINDOW")
            except Exception:
                pass
            finally:
                self._handle = None

        if hasattr(context.scene, "ylvc_is_tracing"):
            context.scene.ylvc_is_tracing = False
        if hasattr(context.scene, "ylvc_tracing_type"):
            context.scene.ylvc_tracing_type = ""

        try:
            if context.workspace:
                context.workspace.status_text_set(None)
        except Exception:
            pass

        if context.area:
            context.area.tag_redraw()


classes = (
    MESH_OT_YLVCLightMask,
)
