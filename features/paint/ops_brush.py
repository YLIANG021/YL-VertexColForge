# -*- coding: utf-8 -*-
"""Small modal brush for local color-attribute painting."""

import math
import time

import bpy
import numpy as np

from ...core.color_attribute import resolve_target_color_attribute
from ...core.operator_poll import active_mesh_has_color_attributes
from ...core.selection_scope import resolve_selection_scope
from ...core.write_engine import write_color_array_to_attribute
from ...i18n import tr, tr_format
from ...services import display, transactions
from ..color import ops_preview
from . import brush_context, brush_engine, brush_ui_policy, overlay


_YLVC_PAINT_SESSION = {
    "is_active": False,
    "finish_requested": False,
    "obj_name": "",
    "layer_name": "",
}

_PAINT_WRITE_INTERVAL = 1.0 / 15.0
_PREVIEW_LIVE_SMALL_COLOR_ENTRIES = 150_000
_PREVIEW_LIVE_MEDIUM_COLOR_ENTRIES = 500_000
_PREVIEW_LIVE_SMALL_INTERVAL = 1.0 / 30.0
_PREVIEW_LIVE_MEDIUM_INTERVAL = 1.0 / 20.0
_PREVIEW_LIVE_LARGE_INTERVAL = 1.0 / 12.0
_PAINT_SAMPLE_SPACING_FACTOR = 0.08
_PAINT_INTERPOLATE_START_FACTOR = 0.45
_PAINT_INTERPOLATE_STEP_FACTOR = 0.35
_PAINT_MAX_INTERPOLATED_SAMPLES = 4
_PAINT_UNDO_STROKE_LIMIT = 20
_BRUSH_RADIUS_MIN = 2.0
_BRUSH_SOFTNESS_ADJUST_PIXELS = 240.0


def is_paint_session_active():
    return bool(_YLVC_PAINT_SESSION["is_active"])


def clear_ylvc_paint_session():
    _YLVC_PAINT_SESSION["is_active"] = False
    _YLVC_PAINT_SESSION["finish_requested"] = False
    _YLVC_PAINT_SESSION["obj_name"] = ""
    _YLVC_PAINT_SESSION["layer_name"] = ""


def request_finish_ylvc_paint_session():
    if _YLVC_PAINT_SESSION["is_active"]:
        _YLVC_PAINT_SESSION["finish_requested"] = True


def _set_paint_session(obj, layer_name):
    _YLVC_PAINT_SESSION["is_active"] = True
    _YLVC_PAINT_SESSION["finish_requested"] = False
    _YLVC_PAINT_SESSION["obj_name"] = obj.name if obj is not None else ""
    _YLVC_PAINT_SESSION["layer_name"] = layer_name or ""


def _snapshot_plugin_state():
    try:
        from ... import _snapshot_plugin_state as snapshot_plugin_state
        snapshot_plugin_state()
    except Exception:
        pass


def _empty_stroke_undo(color_count):
    return {
        "mask": np.zeros(color_count, dtype=bool),
        "indices": [],
        "colors": [],
    }


class MESH_OT_YLVCLocalPaintBrush(bpy.types.Operator):
    bl_idname = "mesh.ylvc_local_paint_brush"
    bl_label = "Paint"
    bl_description = "Paint the active color attribute with the current value. Existing mesh selections limit the painted area."
    bl_options = {"REGISTER", "UNDO"}

    _handle = None
    _handle_2d = None

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (
            context.area is not None
            and context.area.type == "VIEW_3D"
            and active_mesh_has_color_attributes(context)
            and obj is not None
            and obj.mode in {"OBJECT", "EDIT"}
        )

    def invoke(self, context, event):
        if context.area is None or context.area.type != "VIEW_3D":
            self.report({"WARNING"}, tr("Run this tool in the 3D View."))
            return {"CANCELLED"}

        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({"WARNING"}, tr("Select a mesh object first."))
            return {"CANCELLED"}

        if obj.mode == "EDIT":
            try:
                switched = transactions.ensure_object_mode_for(context, obj)
            except RuntimeError:
                switched = False
            if not switched:
                self.report({"WARNING"}, tr("Could not switch to Object Mode for painting."))
                return {"CANCELLED"}
            obj = context.active_object
            if obj is None or obj.type != "MESH":
                self.report({"WARNING"}, tr("Select a mesh object first."))
                return {"CANCELLED"}

        value = brush_engine.current_brush_value(context)
        if value is None:
            self.report({"WARNING"}, tr("No vertex paint brush available."))
            return {"CANCELLED"}

        target, error = resolve_target_color_attribute(context, activate=False)
        if error:
            self.report({"WARNING"}, error)
            return {"CANCELLED"}

        self._started_mode = obj.mode
        self._obj = obj
        self._mesh = obj.data
        self._color_attr = target.color_attr
        self._obj_name = obj.name
        self._obj_ptr = brush_context.safe_pointer(obj)
        self._mesh_ptr = brush_context.safe_pointer(self._mesh)
        self._color_attr_ptr = brush_context.safe_pointer(self._color_attr)
        self._layer_name = target.layer_name
        self._domain = target.domain
        self._channel_key = context.scene.ylvc_channel

        self._selection_scope = resolve_selection_scope(context, self._color_attr, use_live_edit=False)
        self._selection_mask = self._selection_scope.data_mask.astype(bool, copy=True)

        if len(self._selection_mask) != len(self._color_attr.data):
            self._restore_started_mode(context)
            self.report({"WARNING"}, tr("Selection scope did not match the active color attribute."))
            return {"CANCELLED"}

        self._bvh = brush_engine.build_bvh_for_object(obj)
        if self._bvh is None:
            self._restore_started_mode(context)
            self.report({"WARNING"}, tr("Active mesh has no paintable surface."))
            return {"CANCELLED"}

        self._colors, self._world_positions, self._data_positions = brush_engine.build_paint_cache(
            obj,
            self._color_attr,
            self._domain,
        )

        if len(self._data_positions) != len(self._color_attr.data):
            self._restore_started_mode(context)
            self.report({"WARNING"}, tr("Paint cache did not match the active color attribute."))
            return {"CANCELLED"}

        self._paintable_indices, self._paintable_positions = brush_engine.paintable_data_subset(
            self._data_positions,
            self._selection_mask,
        )
        self._paintable_spatial_index = brush_engine.build_position_spatial_index(self._paintable_positions)
        self._world_matrix = obj.matrix_world.copy()
        self._world_matrix_inv = self._world_matrix.inverted_safe()
        self._area_ptr = context.area.as_pointer() if context.area is not None else None
        self._ui_region_ptr = brush_context.safe_pointer(brush_context.find_area_region(context.area, "UI"))
        self._is_painting = False
        self._did_paint = False
        self._colors_dirty = False
        self._last_write_time = 0.0
        self._preview_dirty_batches = []
        self._preview_dirty_count = 0
        self._last_preview_update_time = 0.0
        self._last_paint_hit_world = None
        self._active_stroke_undo = None
        self._stroke_undo_stack = []
        self._session_closed = False
        self._brush_adjust_mode = None
        self._brush_adjust_start_mouse_x = 0
        self._brush_adjust_start_value = 0.0
        self._hit_world = None
        self._hit_normal = None
        self._brush_world_radius = 0.0
        self._draw_state = {
            "visible": False,
            "center": None,
            "normal": None,
            "radius": 0.0,
            "hardness": self._brush_hardness(context),
            "screen_visible": False,
            "screen_center": None,
            "screen_radius": context.scene.ylvc_brush_radius,
            "area_ptr": context.area.as_pointer() if context.area is not None else None,
            "region_ptr": None,
        }
        region, _region_data = brush_context.find_view3d_window(context)
        if region is not None:
            self._draw_state["region_ptr"] = region.as_pointer()

        self._handle = bpy.types.SpaceView3D.draw_handler_add(
            overlay.draw_brush_overlay,
            (self._draw_state,),
            "WINDOW",
            "POST_VIEW",
        )
        self._handle_2d = bpy.types.SpaceView3D.draw_handler_add(
            overlay.draw_brush_overlay_2d,
            (self._draw_state,),
            "WINDOW",
            "POST_PIXEL",
        )
        _set_paint_session(obj, self._layer_name)
        context.window_manager.modal_handler_add(self)
        self._set_status_text(context, self._paint_status_text())
        self.report({"INFO"}, tr("Paint session started."))
        brush_context.tag_area_redraw(context.area, include_regions=True)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        brush_context.tag_area_redraw(context.area)

        if not self._is_context_valid(context):
            return self._finish_modal_result(context, passthrough=True, restore_mode=False)

        if self._brush_adjust_mode is not None:
            return self._handle_brush_adjust_event(context, event)

        if brush_ui_policy.event_requests_undo(event):
            if self._undo_last_stroke(context):
                return {"RUNNING_MODAL"}
            _snapshot_plugin_state()
            return self._finish_modal_result(context, passthrough=True)

        if event.type == "ESC" and event.value == "PRESS":
            return self._finish_modal_result(context)

        inside_viewport, region, region_data, mouse_x, mouse_y = self._view3d_window_from_event(context, event)
        if _YLVC_PAINT_SESSION["finish_requested"]:
            return self._finish_modal_result(context, passthrough=(not inside_viewport and brush_ui_policy.event_is_ui_mouse_event(event)))

        if inside_viewport and event.type == "F" and event.value == "PRESS" and not self._is_painting:
            self._begin_brush_adjust(context, event, "SOFTNESS" if event.shift else "RADIUS")
            return {"RUNNING_MODAL"}

        if not inside_viewport:
            if self._is_painting and not self._flush_colors(context):
                return self._finish_modal_result(context)
            if self._is_painting:
                self._last_paint_hit_world = None
                if event.type == "LEFTMOUSE" and event.value == "RELEASE":
                    self._is_painting = False
                    self._finish_active_stroke()
                else:
                    self._set_overlay_visible(False)
                    brush_context.tag_area_redraw(context.area)
                    return {"RUNNING_MODAL"}
            self._set_overlay_visible(False)
            brush_context.tag_area_redraw(context.area)
            if brush_ui_policy.event_commits_ui_session(event):
                if brush_ui_policy.event_in_brush_panel_ui(
                    context,
                    event,
                    area_ptr=getattr(self, "_area_ptr", None),
                    ui_region_ptr=getattr(self, "_ui_region_ptr", 0),
                ):
                    return {"PASS_THROUGH"}
                return self._finish_modal_result(context, passthrough=True, restore_mode=False)
            return {"PASS_THROUGH"}

        if event.type == "RIGHTMOUSE" and event.value == "PRESS":
            return self._finish_modal_result(context)

        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            return {"PASS_THROUGH"}

        if event.type in {"MOUSEMOVE", "LEFTMOUSE"}:
            self._update_hit(context, region, region_data, mouse_x, mouse_y)

        if event.type == "LEFTMOUSE":
            if event.value == "PRESS":
                self._is_painting = True
                self._last_paint_hit_world = None
                self._begin_stroke()
                if self._paint_at_hit(context, force=True) < 0:
                    return self._finish_modal_result(context)
            elif event.value == "RELEASE":
                self._is_painting = False
                self._last_paint_hit_world = None
                self._finish_active_stroke()
                if not self._flush_colors(context):
                    return self._finish_modal_result(context)
            return {"RUNNING_MODAL"}

        if event.type == "MOUSEMOVE" and self._is_painting:
            if self._paint_at_hit(context) < 0:
                return self._finish_modal_result(context)
            return {"RUNNING_MODAL"}

        return {"PASS_THROUGH"}

    def _finish_modal_result(self, context, passthrough=False, restore_mode=True):
        result = {"FINISHED"} if self._did_paint else {"CANCELLED"}
        self._finish(context, restore_mode=restore_mode)
        if passthrough:
            result.add("PASS_THROUGH")
        return result

    def _is_context_valid(self, context):
        return brush_context.is_paint_context_valid(
            context,
            obj_name=getattr(self, "_obj_name", ""),
            obj_ptr=getattr(self, "_obj_ptr", 0),
            mesh_ptr=getattr(self, "_mesh_ptr", 0),
            layer_name=getattr(self, "_layer_name", ""),
            color_attr_ptr=getattr(self, "_color_attr_ptr", 0),
        )

    def _resolve_current_paint_target(self, context, require_same_mesh):
        return brush_context.resolve_current_paint_target(
            context,
            obj_name=getattr(self, "_obj_name", ""),
            obj_ptr=getattr(self, "_obj_ptr", 0),
            mesh_ptr=getattr(self, "_mesh_ptr", 0),
            layer_name=getattr(self, "_layer_name", ""),
            require_same_mesh=require_same_mesh,
        )

    def _resolve_current_object(self, context):
        return brush_context.resolve_current_object(
            context,
            getattr(self, "_obj_name", ""),
            getattr(self, "_obj_ptr", 0),
        )

    def _view3d_window_from_event(self, context, event):
        _area, region, region_data = brush_context.find_view3d_window_at_mouse(
            context,
            event.mouse_x,
            event.mouse_y,
            area_ptr=getattr(self, "_area_ptr", None),
        )
        if region is None or region_data is None:
            return False, None, None, 0, 0

        mouse_x = event.mouse_x - region.x
        mouse_y = event.mouse_y - region.y
        inside = 0 <= mouse_x <= region.width and 0 <= mouse_y <= region.height
        if not inside:
            return False, None, None, mouse_x, mouse_y
        return True, region, region_data, mouse_x, mouse_y

    def _update_hit(self, context, region, region_data, mouse_x, mouse_y):
        self._draw_state["screen_center"] = (mouse_x, mouse_y)
        hit_world, hit_normal = brush_engine.raycast_surface_hit(
            region,
            region_data,
            mouse_x,
            mouse_y,
            bvh=self._bvh,
            world_matrix=self._world_matrix,
            world_matrix_inv=self._world_matrix_inv,
        )
        if hit_world is None:
            self._hit_world = None
            self._hit_normal = None
            if self._is_painting:
                self._last_paint_hit_world = None
            self._brush_world_radius = 0.0
            self._set_overlay_visible(False, screen_visible=True)
            self._draw_state["screen_radius"] = self._screen_brush_radius(context)
            self._draw_state["hardness"] = self._brush_hardness(context)
            return

        self._hit_world = hit_world
        self._hit_normal = hit_normal
        world_radius = brush_engine.view_depth_world_radius_for_screen_radius(
            region,
            region_data,
            self._hit_world,
            context.scene.ylvc_brush_radius,
        )
        if world_radius <= 0.0:
            world_radius = max(self._brush_world_radius, 1e-6)
        self._brush_world_radius = world_radius
        self._draw_state["visible"] = False
        self._draw_state["screen_visible"] = True
        self._draw_state["center"] = tuple(self._hit_world)
        self._draw_state["normal"] = tuple(self._hit_normal)
        self._draw_state["radius"] = world_radius
        self._draw_state["screen_radius"] = self._screen_brush_radius(context)
        self._draw_state["hardness"] = self._brush_hardness(context)

    def _set_overlay_visible(self, visible, screen_visible=False):
        self._draw_state["visible"] = bool(visible)
        self._draw_state["screen_visible"] = bool(screen_visible)
        if not visible:
            self._draw_state["center"] = None
            self._draw_state["normal"] = None
        if not screen_visible:
            self._draw_state["screen_center"] = None

    def _screen_brush_radius(self, context):
        return max(float(context.scene.ylvc_brush_radius), _BRUSH_RADIUS_MIN)

    def _brush_hardness(self, context):
        return float(np.clip(context.scene.ylvc_brush_softness, 0.0, 1.0))

    def _paint_status_text(self):
        return tr("Paint session active. LMB paints; F adjusts Size; Shift+F adjusts Hardness; RMB or Esc finishes.")

    def _set_status_text(self, context, text):
        try:
            context.workspace.status_text_set(text)
        except Exception:
            pass

    def _begin_brush_adjust(self, context, event, mode):
        scene = context.scene
        self._brush_adjust_mode = mode
        self._brush_adjust_start_mouse_x = event.mouse_x
        if mode == "SOFTNESS":
            self._brush_adjust_start_value = float(scene.ylvc_brush_softness)
        else:
            self._brush_adjust_start_value = float(scene.ylvc_brush_radius)
        self._set_status_text(context, self._brush_adjust_status_text(context))

    def _handle_brush_adjust_event(self, context, event):
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            self._finish_brush_adjust(context, cancelled=True)
            return {"RUNNING_MODAL"}

        if event.type in {"LEFTMOUSE", "RET", "NUMPAD_ENTER", "SPACE"} and event.value == "PRESS":
            self._finish_brush_adjust(context, cancelled=False)
            return {"RUNNING_MODAL"}

        if event.type == "MOUSEMOVE":
            self._update_brush_adjust_value(context, event)
            return {"RUNNING_MODAL"}

        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE"}:
            return {"PASS_THROUGH"}

        return {"RUNNING_MODAL"}

    def _update_brush_adjust_value(self, context, event):
        mode = self._brush_adjust_mode
        delta_x = float(event.mouse_x - self._brush_adjust_start_mouse_x)

        if mode == "SOFTNESS":
            value = self._brush_adjust_start_value + delta_x / _BRUSH_SOFTNESS_ADJUST_PIXELS
            context.scene.ylvc_brush_softness = float(np.clip(value, 0.0, 1.0))
            self._draw_state["hardness"] = self._brush_hardness(context)
        else:
            context.scene.ylvc_brush_radius = max(_BRUSH_RADIUS_MIN, self._brush_adjust_start_value + delta_x)
            self._refresh_brush_radius_after_property_change(context)

        self._set_status_text(context, self._brush_adjust_status_text(context))
        brush_context.tag_area_redraw(context.area, include_regions=True)

    def _finish_brush_adjust(self, context, cancelled):
        mode = self._brush_adjust_mode
        if cancelled:
            if mode == "SOFTNESS":
                context.scene.ylvc_brush_softness = float(self._brush_adjust_start_value)
                self._draw_state["hardness"] = self._brush_hardness(context)
            elif mode == "RADIUS":
                context.scene.ylvc_brush_radius = max(_BRUSH_RADIUS_MIN, self._brush_adjust_start_value)
                self._refresh_brush_radius_after_property_change(context)

        self._brush_adjust_mode = None
        self._brush_adjust_start_mouse_x = 0
        self._brush_adjust_start_value = 0.0
        self._set_status_text(context, self._paint_status_text())
        brush_context.tag_area_redraw(context.area, include_regions=True)

    def _brush_adjust_status_text(self, context):
        if self._brush_adjust_mode == "SOFTNESS":
            return tr_format(
                "Adjust Hardness: {value:.3f}. LMB/Enter confirms; RMB/Esc cancels.",
                value=context.scene.ylvc_brush_softness,
            )
        return tr_format(
            "Adjust Size: {value:.1f} px. LMB/Enter confirms; RMB/Esc cancels.",
            value=context.scene.ylvc_brush_radius,
        )

    def _refresh_brush_radius_after_property_change(self, context):
        self._draw_state["screen_radius"] = self._screen_brush_radius(context)
        self._draw_state["hardness"] = self._brush_hardness(context)
        if self._hit_world is None:
            return

        region, region_data = brush_context.find_view3d_window(context)
        world_radius = brush_engine.view_depth_world_radius_for_screen_radius(
            region,
            region_data,
            self._hit_world,
            context.scene.ylvc_brush_radius,
        )
        if world_radius <= 0.0:
            return
        self._brush_world_radius = world_radius
        self._draw_state["radius"] = world_radius

    def _paint_at_hit(self, context, force=False):
        if self._hit_world is None:
            return 0
        if not force and self._should_skip_paint_sample(context):
            return 0

        channel_key = getattr(context.scene, "ylvc_channel", getattr(self, "_channel_key", "RGB"))
        painted_count = 0
        painted_index_batches = []
        for hit_world in self._paint_samples_for_hit(context):
            result = brush_engine.paint_at_hit(
                context,
                hit_world=hit_world,
                data_indices=self._paintable_indices,
                data_positions=self._paintable_positions,
                spatial_index=self._paintable_spatial_index,
                colors=self._colors,
                channel_key=channel_key,
                radius=self._brush_world_radius,
                undo_recorder=self._active_stroke_undo,
                painted_indices_out=painted_index_batches,
            )
            if result < 0:
                return result
            painted_count += result

        self._last_paint_hit_world = self._hit_world.copy()
        if painted_count > 0:
            self._did_paint = True
            self._colors_dirty = True
            self._queue_preview_indices(painted_index_batches)
            preview_live = self._uses_live_preview(context, channel_key=channel_key)
            if not self._flush_preview_indices(context, force=False):
                preview_live = False
                self._preview_dirty_batches = []
                self._preview_dirty_count = 0
            if not preview_live and not self._flush_colors(context, throttled=True):
                return -1
        return painted_count

    def _begin_stroke(self):
        self._active_stroke_undo = _empty_stroke_undo(len(self._colors))

    def _finish_active_stroke(self):
        stroke = getattr(self, "_active_stroke_undo", None)
        self._active_stroke_undo = None
        if not stroke or not stroke.get("indices"):
            return

        stroke["mask"] = None
        self._stroke_undo_stack.append(stroke)
        if len(self._stroke_undo_stack) > _PAINT_UNDO_STROKE_LIMIT:
            del self._stroke_undo_stack[0]

    def _undo_last_stroke(self, context):
        if getattr(self, "_is_painting", False):
            self._is_painting = False
            self._finish_active_stroke()

        if not getattr(self, "_stroke_undo_stack", None):
            return False

        stroke = self._stroke_undo_stack.pop()
        for indices, colors in zip(stroke.get("indices", []), stroke.get("colors", [])):
            self._colors[indices] = colors

        self._colors_dirty = True
        self._did_paint = True
        self._last_paint_hit_world = None
        self._queue_preview_indices(stroke.get("indices", []))
        if not self._flush_colors(context):
            return False
        brush_context.tag_area_redraw(context.area, include_regions=True)
        return True

    def _paint_samples_for_hit(self, context):
        last_hit = getattr(self, "_last_paint_hit_world", None)
        if last_hit is None:
            return (self._hit_world,)

        radius = max(float(self._brush_world_radius), 1e-6)
        distance = (self._hit_world - last_hit).length
        if distance <= radius * _PAINT_INTERPOLATE_START_FACTOR:
            return (self._hit_world,)

        step = max(radius * _PAINT_INTERPOLATE_STEP_FACTOR, 1e-6)
        sample_count = min(
            _PAINT_MAX_INTERPOLATED_SAMPLES,
            max(0, math.ceil(distance / step) - 1),
        )
        if sample_count <= 0:
            return (self._hit_world,)

        samples = [
            last_hit.lerp(self._hit_world, index / (sample_count + 1))
            for index in range(1, sample_count + 1)
        ]
        samples.append(self._hit_world)
        return samples

    def _should_skip_paint_sample(self, context):
        if self._hit_world is None:
            return False

        last_hit = getattr(self, "_last_paint_hit_world", None)
        if last_hit is None:
            return False

        radius = max(float(self._brush_world_radius), 1e-6)
        min_spacing = radius * _PAINT_SAMPLE_SPACING_FACTOR
        return (self._hit_world - last_hit).length < min_spacing

    def _uses_live_preview(self, context, *, channel_key=None):
        channel_key = channel_key or getattr(context.scene, "ylvc_channel", getattr(self, "_channel_key", "RGB"))
        if channel_key == "RGB":
            return False
        try:
            return ops_preview.is_native_preview_enabled(context)
        except Exception:
            return False

    def _preview_live_interval(self):
        color_count = len(getattr(self, "_colors", ()))
        if color_count <= _PREVIEW_LIVE_SMALL_COLOR_ENTRIES:
            return _PREVIEW_LIVE_SMALL_INTERVAL
        if color_count <= _PREVIEW_LIVE_MEDIUM_COLOR_ENTRIES:
            return _PREVIEW_LIVE_MEDIUM_INTERVAL
        return _PREVIEW_LIVE_LARGE_INTERVAL

    def _queue_preview_indices(self, index_batches):
        if not index_batches:
            return
        batches = getattr(self, "_preview_dirty_batches", None)
        if batches is None:
            self._preview_dirty_batches = []
            self._preview_dirty_count = 0
            batches = self._preview_dirty_batches

        for indices in index_batches:
            indices = np.asarray(indices, dtype=np.int64).reshape(-1)
            if indices.size == 0:
                continue
            batches.append(indices)
            self._preview_dirty_count = getattr(self, "_preview_dirty_count", 0) + int(indices.size)

    def _flush_preview_indices(self, context, *, force=False):
        batches = getattr(self, "_preview_dirty_batches", None)
        if not batches:
            return True

        channel_key = getattr(context.scene, "ylvc_channel", getattr(self, "_channel_key", "RGB"))
        if not self._uses_live_preview(context, channel_key=channel_key):
            self._preview_dirty_batches = []
            self._preview_dirty_count = 0
            return True

        now = time.monotonic()
        if not force and now - getattr(self, "_last_preview_update_time", 0.0) < self._preview_live_interval():
            return True

        try:
            dirty_indices = np.unique(np.concatenate(batches))
        except ValueError:
            self._preview_dirty_batches = []
            self._preview_dirty_count = 0
            return True

        if dirty_indices.size == 0:
            self._preview_dirty_batches = []
            self._preview_dirty_count = 0
            return True

        try:
            updated = ops_preview.update_preview_color_indices_for_context(
                self._layer_name,
                context=context,
                source_colors=self._colors,
                indices=dirty_indices,
            )
        except Exception:
            return False

        if not updated:
            return False

        self._preview_dirty_batches = []
        self._preview_dirty_count = 0
        self._last_preview_update_time = now
        return True

    def _flush_colors(self, context, throttled=False):
        if not throttled and not self._flush_preview_indices(context, force=True):
            return False

        if not getattr(self, "_colors_dirty", False):
            return True

        now = time.monotonic()
        if throttled and now - getattr(self, "_last_write_time", 0.0) < _PAINT_WRITE_INTERVAL:
            return True

        try:
            write_color_array_to_attribute(self._color_attr, self._colors, mesh=self._mesh, update_mesh=True)
        except ReferenceError:
            return False
        display.finish_color_write(
            context,
            self._mesh,
            self._layer_name,
            obj=self._obj,
            source_colors=self._colors,
            mesh_updated=True,
        )

        self._colors_dirty = False
        self._last_write_time = now
        return True

    def _restore_started_mode(self, context):
        if getattr(self, "_started_mode", None) == "EDIT":
            try:
                transactions.set_mode(context, "EDIT")
            except Exception:
                pass

    def _finish(self, context, restore_mode=True):
        if getattr(self, "_session_closed", False):
            return
        self._session_closed = True

        if self._handle is not None:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(self._handle, "WINDOW")
            except Exception:
                pass
            self._handle = None
        if self._handle_2d is not None:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(self._handle_2d, "WINDOW")
            except Exception:
                pass
            self._handle_2d = None

        self._flush_colors(context)

        if self._did_paint:
            obj, mesh, _color_attr = self._resolve_current_paint_target(context, require_same_mesh=True)
            if obj is not None and mesh is not None:
                try:
                    display.refresh_after_color_write(context, mesh, self._layer_name, obj=obj)
                except ReferenceError:
                    pass

        clear_ylvc_paint_session()
        if restore_mode:
            self._restore_started_mode(context)
        try:
            context.workspace.status_text_set(None)
        except Exception:
            pass
        brush_context.tag_area_redraw(context.area, include_regions=True)


CLASSES = (
    MESH_OT_YLVCLocalPaintBrush,
)
