import bpy
import math
import numpy as np
from ...core.color_attribute import (
    get_active_color_attribute_safe,
    read_color_attribute_colors,
    set_active_color_attribute,
)
from ...core.context import (
    resolve_component_selection_masks_for_object,
    resolve_loop_auto_mask_for_object,
    resolve_vertex_auto_mask_for_object,
)
from ...core.operator_poll import has_active_mesh
from ...core.write_engine import restore_color_array_to_attribute, write_blended_color_array_to_attribute
from ...i18n import tr, tr_format
from ...services import transactions
from ..gradients.core_color_engine import build_ramp_lut, ensure_light_ramp_node, sample_lut_array_out
from ..gradients.core_overlay import draw_gradient_overlay_callback


# ==========================================
# Helpers
# ==========================================

def ensure_active_color_attribute(mesh, name="DirectionalMask", domain="POINT"):
    """Return the active color attribute, or create a fallback attribute when needed."""
    color_attr = get_active_color_attribute_safe(mesh)

    if color_attr is not None:
        return color_attr

    try:
        color_attr = mesh.color_attributes.get(name)
    except Exception:
        color_attr = None

    if color_attr is None:
        color_attr = mesh.color_attributes.new(
            name=name,
            type="FLOAT_COLOR",
            domain=domain,
        )

    set_active_color_attribute(mesh, color_attr.name)

    return color_attr


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


def _edit_component_vertex_auto_mask(obj):
    """Collapse the current Edit Mode component selection into a vertex mask."""
    vert_mask, edge_mask, face_mask = resolve_component_selection_masks_for_object(obj, use_live_edit=True)
    if vert_mask.size == 0:
        return vert_mask

    if not (np.any(vert_mask) or np.any(edge_mask) or np.any(face_mask)):
        return np.ones(vert_mask.shape[0], dtype=bool)

    mesh = obj.data
    result = vert_mask.copy()

    if edge_mask.size > 0 and np.any(edge_mask):
        edge_vertices = np.empty(len(mesh.edges) * 2, dtype=np.int32)
        mesh.edges.foreach_get("vertices", edge_vertices)
        edge_vertices.shape = (-1, 2)
        selected_edges = edge_vertices[edge_mask[: len(mesh.edges)]]
        if selected_edges.size > 0:
            result[selected_edges.ravel()] = True

    if face_mask.size > 0 and np.any(face_mask):
        for polygon in mesh.polygons:
            if polygon.index >= face_mask.size or not face_mask[polygon.index]:
                continue
            result[np.asarray(polygon.vertices, dtype=np.int32)] = True

    return result


# ==========================================
# Directional Lighting Operator
# ==========================================

class MESH_OT_VCM_TestDirectionalMask(bpy.types.Operator):
    bl_idname = "mesh.vcm_test_dir_mask"
    bl_label = "Directional Lighting"
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
        self._context_state = None
        obj = context.active_object

        if not obj or obj.type != "MESH":
            self.report({"WARNING"}, tr("Select a mesh object first."))
            return {"CANCELLED"}

        edit_vertex_mask = None
        if obj.mode == "EDIT":
            self._context_state = transactions.ObjectContextTransaction(context)
            edit_vertex_mask = _edit_component_vertex_auto_mask(obj)
            transactions.ensure_object_mode_for(context, obj)
            if obj.mode != "OBJECT":
                self._restore_initial_context(context)
                self.report({"WARNING"}, tr("Could not switch to Object Mode for directional lighting."))
                return {"CANCELLED"}
        elif obj.mode != "OBJECT":
            self.report({"WARNING"}, tr("Run this tool in Object or Edit Mode."))
            return {"CANCELLED"}

        ramp_node = ensure_light_ramp_node()
        if ramp_node is None or not getattr(ramp_node, "color_ramp", None):
            self._restore_initial_context(context)
            self.report({"ERROR"}, tr("Could not create the gradient ramp."))
            return {"CANCELLED"}

        mesh = obj.data

        color_attr = ensure_active_color_attribute(mesh)

        if color_attr is None:
            self._restore_initial_context(context)
            self.report({"WARNING"}, tr("Could not access the active color attribute."))
            return {"CANCELLED"}

        if color_attr.domain not in {"POINT", "CORNER"}:
            self._restore_initial_context(context)
            self.report({"WARNING"}, tr_format("Unsupported color domain: {domain}", domain=color_attr.domain))
            return {"CANCELLED"}

        self.obj = obj
        self.mesh = mesh
        self.color_attr = color_attr
        self.domain = color_attr.domain

        vert_count = len(mesh.vertices)
        data_count = len(color_attr.data)

        if vert_count == 0 or data_count == 0:
            self._restore_initial_context(context)
            self.report({"WARNING"}, tr("The object has no writable color data."))
            return {"CANCELLED"}

        # Cache world-space normals.
        self.world_normals_np = get_world_normals_numpy(obj, mesh)

        # Cache original colors so cancel can restore them.
        self.orig_colors = read_color_attribute_colors(mesh, self.color_attr)

        if edit_vertex_mask is not None and edit_vertex_mask.size == vert_count:
            self.data_mask = edit_vertex_mask.copy()
        elif self.domain == "POINT":
            self.data_mask = resolve_vertex_auto_mask_for_object(obj, use_live_edit=False)
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
            if edit_vertex_mask is not None and edit_vertex_mask.size == vert_count:
                self.data_mask = edit_vertex_mask[self.loop_vi]
            else:
                self.data_mask = resolve_loop_auto_mask_for_object(obj, self.loop_vi, use_live_edit=False)

        self.start_pos = None
        self.mouse_pos = None
        self.last_mouse_pos = None
        self.last_direction = None
        self.has_dragged = False
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

        context.window_manager.modal_handler_add(self)

        try:
            context.workspace.status_text_set(tr("Drag with LMB to define the light direction. RMB or Esc cancels."))
        except Exception:
            pass

        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if context.area:
            context.area.tag_redraw()

        if self.obj is None or self.obj.name not in bpy.data.objects:
            self._finish(context)
            return {"CANCELLED"}

        if event.type in {"RIGHTMOUSE", "ESC"}:
            try:
                restore_color_array_to_attribute(self.color_attr, self.orig_colors, mesh=self.mesh)
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
                self._draw_state["mouse_pos"] = self.start_pos

            elif event.value == "RELEASE" and self.start_pos is not None:
                self._finish(context)
                return {"FINISHED"}

        if event.type == "MOUSEMOVE" and self.start_pos is not None:
            new_mouse_pos = (event.mouse_region_x, event.mouse_region_y)

            if self.last_mouse_pos is not None:
                dxp = new_mouse_pos[0] - self.last_mouse_pos[0]
                dyp = new_mouse_pos[1] - self.last_mouse_pos[1]
                if (dxp * dxp + dyp * dyp) < (self.mouse_move_threshold * self.mouse_move_threshold):
                    return {"RUNNING_MODAL"}

            self.mouse_pos = new_mouse_pos
            self.last_mouse_pos = new_mouse_pos
            self._draw_state["mouse_pos"] = self.mouse_pos

            if self.execute_mask_engine(context):
                self.has_dragged = True

        return {"RUNNING_MODAL"}

    def execute_mask_engine(self, context):
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
        blend_mode = getattr(context.scene, "ylvc_light_blend_mode", "REPLACE")

        self.work_colors = write_blended_color_array_to_attribute(
            self.color_attr,
            self.orig_colors,
            self.ramp_colors,
            channel_key=channel_key,
            blend_mode=blend_mode,
            mask=self.data_mask,
            mesh=self.mesh,
        )

        return True

    def _restore_initial_context(self, context):
        context_state = getattr(self, "_context_state", None)
        if context_state is None:
            return
        try:
            context_state.restore()
        except Exception:
            pass
        self._context_state = None

    def _finish(self, context):
        if getattr(self, "_handle", None) is not None:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(self._handle, "WINDOW")
            except Exception:
                pass
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

        self._restore_initial_context(context)

        if context.area:
            context.area.tag_redraw()


# ==========================================
# Registration
# ==========================================

classes = (
    MESH_OT_VCM_TestDirectionalMask,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
