# -*- coding: utf-8 -*-
import math
import time

import bmesh
import bpy
import numpy as np
from bpy_extras import view3d_utils

from ...core.color_attribute import read_color_attribute_colors
from ...core.color_attribute import resolve_target_color_attribute
from ...core.color_channels import CHANNEL_COMPONENTS, clamp_factor, sample_channel_value
from ...core.mesh_color_sampling import sample_hit_color
from ...core.mesh_topology import loop_vertex_indices, vertex_positions
from ...core.operator_poll import active_mesh_has_color_attributes
from ...i18n import tr
from ...services import transactions
from . import overlay
from .ops_fill_select import build_corner_vertex_match_mask

PICK_SELECT_START_TOLERANCE = 0.0
PICK_SELECT_ZERO_SNAP_RADIUS = 10.0
PICK_SELECT_TOLERANCE_DRAG_SCALE = 600.0
PREVIEW_FACE_COLOR = np.array((1.0, 0.78, 0.08, 0.34), dtype=np.float32)


def _sync_picked_value_to_selection_input(context, sampled_rgba, picked_value):
    channel_key = getattr(context.scene, "ylvc_channel", "RGB")
    if channel_key == "RGB":
        try:
            context.scene.ylvc_fill_rgb_fg = tuple(sampled_rgba[:3])
            context.scene.ylvc_alpha_fg = float(sampled_rgba[3])
        except Exception:
            pass
        return

    if channel_key == "A":
        try:
            context.scene.ylvc_alpha_fg = float(picked_value)
        except Exception:
            pass

    try:
        context.scene.ylvc_single_fg = float(picked_value)
    except Exception:
        pass


def _capture_mesh_selection_state(obj):
    mesh = obj.data
    state = {
        "vertex": np.zeros(len(mesh.vertices), dtype=bool),
        "edge": np.zeros(len(mesh.edges), dtype=bool),
        "face": np.zeros(len(mesh.polygons), dtype=bool),
    }

    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(mesh)
        state["vertex"] = np.fromiter((vert.select for vert in bm.verts), dtype=bool, count=len(mesh.vertices))
        state["edge"] = np.fromiter((edge.select for edge in bm.edges), dtype=bool, count=len(mesh.edges))
        state["face"] = np.fromiter((face.select for face in bm.faces), dtype=bool, count=len(mesh.polygons))
        return state

    mesh.vertices.foreach_get("select", state["vertex"])
    mesh.edges.foreach_get("select", state["edge"])
    mesh.polygons.foreach_get("select", state["face"])
    return state


def _restore_mesh_selection_state(obj, state):
    if obj is None or obj.type != "MESH" or state is None:
        return

    mesh = obj.data
    restore_edit_mode = obj.mode == "EDIT"

    if restore_edit_mode:
        try:
            switched = transactions.ensure_object_mode_for(bpy.context, obj)
        except RuntimeError:
            switched = False
        if not switched:
            bm = bmesh.from_edit_mesh(mesh)
            for index, vert in enumerate(bm.verts):
                vert.select = bool(state["vertex"][index]) if index < len(state["vertex"]) else False
            for index, edge in enumerate(bm.edges):
                edge.select = bool(state["edge"][index]) if index < len(state["edge"]) else False
            for index, face in enumerate(bm.faces):
                face.select = bool(state["face"][index]) if index < len(state["face"]) else False
            bm.select_flush(True)
            bmesh.update_edit_mesh(mesh)
            return

    mesh.vertices.foreach_set("select", state["vertex"])
    mesh.edges.foreach_set("select", state["edge"])
    mesh.polygons.foreach_set("select", state["face"])
    mesh.update()

    if restore_edit_mode:
        try:
            transactions.set_mode(bpy.context, "EDIT")
            bm = bmesh.from_edit_mesh(mesh)
            bm.select_flush(True)
            bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
        except Exception:
            pass


def _drag_distance_to_tolerance(drag_distance, base_tolerance=0.0):
    if drag_distance <= PICK_SELECT_ZERO_SNAP_RADIUS:
        return 0.0

    effective_distance = drag_distance - PICK_SELECT_ZERO_SNAP_RADIUS
    return clamp_factor(float(base_tolerance) + (effective_distance / PICK_SELECT_TOLERANCE_DRAG_SCALE))


class MESH_OT_YLVCPickSelectValue(bpy.types.Operator):
    bl_idname = "mesh.ylvc_pick_select_value"
    bl_label = "Pick to Select"
    bl_description = "Pick a visible mesh color, then drag away from the pick point to adjust tolerance"
    bl_options = {"REGISTER", "UNDO"}

    _handle = None
    _surface_handle = None

    @classmethod
    def poll(cls, context):
        return (
            context.area is not None
            and context.area.type == "VIEW_3D"
            and active_mesh_has_color_attributes(context)
        )

    def invoke(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D":
            self.report({"WARNING"}, tr("Run this tool in the 3D View."))
            return {"CANCELLED"}

        active_obj = context.active_object
        if active_obj is None or active_obj.type != "MESH":
            self.report({"WARNING"}, tr("Select a mesh object first."))
            return {"CANCELLED"}

        self._context_state = transactions.ObjectContextTransaction(context)
        self._selection_state = _capture_mesh_selection_state(active_obj)
        self._target_obj_name = active_obj.name
        tool_settings = getattr(context, "tool_settings", None)
        self._original_mesh_select_mode = tuple(tool_settings.mesh_select_mode) if tool_settings else None
        self._state = "WAITING_PICK"
        self._picked_value = None
        self._picked_swatch = None
        self._base_tolerance = PICK_SELECT_START_TOLERANCE
        self._current_tolerance = self._base_tolerance
        self._anchor_mouse_x = 0
        self._anchor_mouse_y = 0
        self._last_live_time = 0.0
        self._last_live_mouse_pos = None
        self._live_interval = 1.0 / 24.0
        self._live_mouse_threshold = 2.0
        self._preview_cache_ready = False
        self._current_vertex_mask = None
        self._old_single_fg = getattr(context.scene, "ylvc_single_fg", 0.0)
        self._old_select_tolerance = getattr(context.scene, "ylvc_select_tolerance", 0.0)
        self._last_synced_tolerance = None

        if active_obj.mode != "OBJECT":
            try:
                switched = transactions.ensure_object_mode_for(context, active_obj)
            except RuntimeError:
                switched = False
            if not switched:
                self.report({"WARNING"}, tr("Could not switch to Object Mode for color sampling."))
                return {"CANCELLED"}

        target, error = resolve_target_color_attribute(context, activate=False)
        if error:
            self._context_state.restore()
            self.report({"WARNING"}, error)
            return {"CANCELLED"}

        self._build_preview_cache(context, target.obj, target.color_attr)

        self._draw_state = {
            "visible": False,
            "center_pos": None,
            "tolerance": self._current_tolerance,
            "swatch": None,
            "area_ptr": context.area.as_pointer() if context.area is not None else None,
            "region_ptr": None,
        }
        self._surface_draw_state = {
            "visible": False,
            "positions": self._preview_positions if self._preview_cache_ready else None,
            "colors": None,
            "area_ptr": context.area.as_pointer() if context.area is not None else None,
            "region_ptr": None,
        }
        self._handle = bpy.types.SpaceView3D.draw_handler_add(
            overlay.draw_pick_select_overlay,
            (self._draw_state,),
            "WINDOW",
            "POST_PIXEL",
        )
        self._surface_handle = bpy.types.SpaceView3D.draw_handler_add(
            overlay.draw_pick_select_surface_overlay,
            (self._surface_draw_state,),
            "WINDOW",
            "POST_VIEW",
        )

        if context.window is not None:
            try:
                context.window.cursor_modal_set("EYEDROPPER")
            except Exception:
                pass

        context.window_manager.modal_handler_add(self)
        try:
            context.workspace.status_text_set(tr("Click a mesh color, keep holding LMB, then drag away from the pick point to adjust tolerance."))
        except Exception:
            pass
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if context.area is not None:
            context.area.tag_redraw()

        if event.type in {"RIGHTMOUSE", "ESC"}:
            self._cancel(context)
            return {"CANCELLED"}

        if self._state == "WAITING_PICK":
            if event.type == "LEFTMOUSE" and event.value == "PRESS":
                picked_value, picked_swatch, error = self._pick_value_from_view(context, event)
                if error:
                    self.report({"WARNING"}, error)
                    return {"RUNNING_MODAL"}

                self._picked_value = picked_value
                self._picked_swatch = picked_swatch
                _sync_picked_value_to_selection_input(context, picked_swatch, picked_value)
                self._base_tolerance = PICK_SELECT_START_TOLERANCE
                self._current_tolerance = self._base_tolerance
                self._anchor_mouse_x = float(event.mouse_region_x)
                self._anchor_mouse_y = float(event.mouse_region_y)
                self._last_live_mouse_pos = (self._anchor_mouse_x, self._anchor_mouse_y)
                self._draw_state["visible"] = True
                self._draw_state["center_pos"] = (event.mouse_region_x, event.mouse_region_y)
                self._draw_state["tolerance"] = self._current_tolerance
                self._draw_state["swatch"] = picked_swatch
                self._draw_state["region_ptr"] = context.region.as_pointer() if context.region is not None else None
                self._surface_draw_state["region_ptr"] = context.region.as_pointer() if context.region is not None else None

                if context.active_object is None or context.active_object.type != "MESH":
                    self.report({"WARNING"}, tr("Select a mesh object first."))
                    self._cancel(context)
                    return {"CANCELLED"}

                self._state = "ADJUSTING"
                self._update_object_preview()
                try:
                    context.workspace.status_text_set(tr("Drag away from the pick point to increase tolerance. Release LMB to confirm. RMB or Esc cancels."))
                except Exception:
                    pass
            return {"RUNNING_MODAL"}

        if self._state == "ADJUSTING":
            if event.type == "MOUSEMOVE":
                delta_x = float(event.mouse_region_x) - self._anchor_mouse_x
                delta_y = float(event.mouse_region_y) - self._anchor_mouse_y
                drag_distance = math.hypot(delta_x, delta_y)
                self._current_tolerance = _drag_distance_to_tolerance(drag_distance, self._base_tolerance)
                self._draw_state["tolerance"] = self._current_tolerance
                self._sync_tolerance_to_scene(context)

                if self._should_update_live(event.mouse_region_x, event.mouse_region_y):
                    self._update_object_preview()
            elif event.type == "LEFTMOUSE" and event.value == "RELEASE":
                self._update_object_preview()
                self._sync_tolerance_to_scene(context)
                self._commit_preview_selection(context)
                self._finish(context)
                return {"FINISHED"}

        return {"RUNNING_MODAL"}

    def _should_update_live(self, mouse_x, mouse_y):
        now = time.time()
        current_pos = (float(mouse_x), float(mouse_y))
        if self._last_live_mouse_pos is None:
            self._last_live_mouse_pos = current_pos
            self._last_live_time = now
            return True
        move_distance = math.hypot(
            current_pos[0] - self._last_live_mouse_pos[0],
            current_pos[1] - self._last_live_mouse_pos[1],
        )
        if move_distance < self._live_mouse_threshold and (now - self._last_live_time) < self._live_interval:
            return False
        self._last_live_mouse_pos = current_pos
        self._last_live_time = now
        return True

    def _pick_value_from_view(self, context, event):
        if context.region is None or context.region_data is None:
            return None, None, tr("Hover the mouse over the 3D viewport and try again.")

        region = context.region
        rv3d = context.region_data
        coord = (event.mouse_region_x, event.mouse_region_y)
        origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        depsgraph = context.evaluated_depsgraph_get()

        hit, location, _normal, poly_index, hit_obj, _matrix = context.scene.ray_cast(depsgraph, origin, direction)
        if not hit or hit_obj is None or hit_obj.type != "MESH":
            return None, None, tr("Click on a mesh surface.")
        if hit_obj != self._preview_obj:
            return None, None, tr("Please click the active target object.")

        color_attr = hit_obj.data.color_attributes.get(self._preview_layer_name)
        if color_attr is None:
            return None, None, tr("The target color attribute is no longer available on the active object.")

        sampled_rgba = sample_hit_color(hit_obj, hit_obj.data, color_attr, poly_index, location)
        if sampled_rgba is None:
            return None, None, tr("Could not sample color from the clicked surface.")

        sampled_rgba = [clamp_factor(component) for component in sampled_rgba[:4]]
        while len(sampled_rgba) < 4:
            sampled_rgba.append(1.0 if len(sampled_rgba) == 3 else 0.0)

        channel_key = context.scene.ylvc_channel
        if channel_key == "RGB":
            picked_value = sampled_rgba
        else:
            picked_value = sample_channel_value(sampled_rgba, channel_key)

        swatch = (sampled_rgba[0], sampled_rgba[1], sampled_rgba[2], 1.0)
        return picked_value, swatch, None

    def _build_preview_cache(self, context, obj, color_attr):
        mesh = obj.data
        self._preview_obj = obj
        self._preview_mesh = mesh
        self._preview_layer_name = color_attr.name
        self._preview_domain = color_attr.domain
        self._preview_channel = getattr(context.scene, "ylvc_channel", "RGB")
        self._preview_channel_indices = list(CHANNEL_COMPONENTS[self._preview_channel])
        self._preview_vert_count = len(mesh.vertices)

        self._preview_colors = read_color_attribute_colors(mesh, color_attr)

        self._preview_loop_vert_idx = None
        if self._preview_domain == "CORNER":
            self._preview_loop_vert_idx = loop_vertex_indices(mesh)

        mesh.calc_loop_triangles()
        tri_count = len(mesh.loop_triangles)
        tri_vertices = np.empty(tri_count * 3, dtype=np.int32)
        mesh.loop_triangles.foreach_get("vertices", tri_vertices)
        self._preview_tri_flat = tri_vertices

        vert_coords = vertex_positions(mesh)

        world_matrix = np.array(obj.matrix_world, dtype=np.float32)
        rotation = world_matrix[:3, :3]
        translation = world_matrix[:3, 3]
        world_positions = vert_coords @ rotation.T + translation
        self._preview_positions = world_positions[self._preview_tri_flat].astype(np.float32, copy=False)
        self._preview_overlay_colors = np.zeros((len(self._preview_tri_flat), 4), dtype=np.float32)
        self._preview_cache_ready = True

    def _compute_vertex_mask(self):
        if not self._preview_cache_ready or self._picked_value is None:
            return np.zeros(0, dtype=bool)

        colors = self._preview_colors
        tolerance = self._current_tolerance
        channel_indices = self._preview_channel_indices
        is_color = isinstance(self._picked_value, (list, tuple))

        if is_color:
            target_arr = np.array(
                self._picked_value if len(self._picked_value) == 4 else [self._picked_value[0], self._picked_value[1], self._picked_value[2], 1.0],
                dtype=np.float32,
            )
            diff = np.abs(colors[:, channel_indices] - target_arr[channel_indices])
            match_mask = np.all(diff <= tolerance, axis=1)
        else:
            sampled = np.mean(colors[:, channel_indices], axis=1)
            match_mask = np.abs(sampled - float(self._picked_value)) <= tolerance

        if self._preview_domain == "POINT":
            return match_mask

        return build_corner_vertex_match_mask(
            self._preview_loop_vert_idx,
            match_mask,
            self._preview_vert_count,
            require_all=True,
        )

    def _update_object_preview(self):
        vertex_mask = self._compute_vertex_mask()
        self._current_vertex_mask = vertex_mask
        if not self._preview_cache_ready:
            return

        vertex_alpha = np.zeros(self._preview_vert_count, dtype=np.float32)
        if vertex_mask.size > 0:
            vertex_alpha[vertex_mask] = PREVIEW_FACE_COLOR[3]

        tri_alpha = vertex_alpha[self._preview_tri_flat]
        colors = self._preview_overlay_colors
        colors[:, :3] = PREVIEW_FACE_COLOR[:3]
        colors[:, 3] = tri_alpha
        self._surface_draw_state["visible"] = True
        self._surface_draw_state["colors"] = colors

    def _commit_preview_selection(self, context):
        obj = self._preview_obj
        if obj is None or obj.type != "MESH":
            return

        vertex_mask = self._current_vertex_mask
        if vertex_mask is None or vertex_mask.size != len(obj.data.vertices):
            vertex_mask = self._compute_vertex_mask()
            self._current_vertex_mask = vertex_mask

        edge_mask = np.zeros(len(obj.data.edges), dtype=bool)
        face_mask = np.zeros(len(obj.data.polygons), dtype=bool)

        obj.data.vertices.foreach_set("select", vertex_mask)
        obj.data.edges.foreach_set("select", edge_mask)
        obj.data.polygons.foreach_set("select", face_mask)
        obj.data.update()

        try:
            transactions.set_mode(context, "EDIT")
        except RuntimeError as exc:
            self.report({"WARNING"}, str(exc))
            return

        tool_settings = getattr(context, "tool_settings", None)
        if tool_settings is not None:
            try:
                tool_settings.mesh_select_mode = (True, False, False)
            except Exception:
                pass

        try:
            bm = bmesh.from_edit_mesh(obj.data)
            bm.select_flush_mode()
            bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        except Exception:
            pass

    def _sync_tolerance_to_scene(self, context):
        scene = getattr(context, "scene", None)
        if scene is None:
            return
        tolerance = clamp_factor(self._current_tolerance)
        if self._last_synced_tolerance is not None and abs(self._last_synced_tolerance - tolerance) < 0.001:
            return
        try:
            scene.ylvc_select_tolerance = tolerance
            self._last_synced_tolerance = tolerance
        except Exception:
            pass

    def _cancel(self, context):
        try:
            context.scene.ylvc_select_tolerance = clamp_factor(self._old_select_tolerance)
        except Exception:
            pass
        self._restore_original_state(context)
        self._finish(context)

    def _restore_original_state(self, context):
        try:
            context.scene.ylvc_single_fg = self._old_single_fg
        except Exception:
            pass
        self._context_state.restore()
        obj = bpy.data.objects.get(self._target_obj_name)
        if obj is not None and obj.type == "MESH":
            _restore_mesh_selection_state(obj, self._selection_state)

    def _finish(self, context):
        if getattr(self, "_handle", None) is not None:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(self._handle, "WINDOW")
            except Exception:
                pass
            self._handle = None
        if getattr(self, "_surface_handle", None) is not None:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(self._surface_handle, "WINDOW")
            except Exception:
                pass
            self._surface_handle = None
        if context.window is not None:
            try:
                context.window.cursor_modal_restore()
            except Exception:
                pass
        try:
            context.workspace.status_text_set(None)
        except Exception:
            pass
        self._draw_state["visible"] = False
        if hasattr(self, "_surface_draw_state"):
            self._surface_draw_state["visible"] = False
        if context.area is not None:
            context.area.tag_redraw()


CLASSES = (MESH_OT_YLVCPickSelectValue,)
