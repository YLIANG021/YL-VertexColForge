# -*- coding: utf-8 -*-
"""Brush color eyedropper for sampling mesh color attributes."""

import bpy
from bpy_extras import view3d_utils

from ...core.color_channels import clamp_factor, sample_channel_value
from ...core.color_attribute import resolve_target_color_attribute
from ...core.mesh_color_sampling import sample_hit_color
from ...core.operator_poll import active_mesh_has_color_attributes
from ...i18n import tr
from ...services import transactions
from . import ops_brush


def _find_view3d_window_at_mouse(context, mouse_x, mouse_y):
    screen = getattr(context, "screen", None)
    if screen is None:
        window = getattr(context, "window", None)
        screen = getattr(window, "screen", None) if window is not None else None
    if screen is None:
        return None, None, None

    for area in getattr(screen, "areas", []):
        if getattr(area, "type", None) != "VIEW_3D":
            continue
        if not (area.x <= mouse_x <= area.x + area.width and area.y <= mouse_y <= area.y + area.height):
            continue

        for item in getattr(area, "regions", []):
            if getattr(item, "type", None) == "WINDOW":
                continue
            if item.x <= mouse_x <= item.x + item.width and item.y <= mouse_y <= item.y + item.height:
                return None, None, None

        for region in getattr(area, "regions", []):
            if getattr(region, "type", None) != "WINDOW":
                continue
            if not (region.x <= mouse_x <= region.x + region.width and region.y <= mouse_y <= region.y + region.height):
                continue
            space = getattr(getattr(area, "spaces", None), "active", None)
            region_data = getattr(space, "region_3d", None)
            if region_data is None:
                return None, None, None
            return area, region, region_data

    return None, None, None


def _event_region_coords(event, region):
    return event.mouse_x - region.x, event.mouse_y - region.y


def _normalize_sampled_rgba(sampled_rgba):
    if sampled_rgba is None:
        return None
    rgba = [clamp_factor(component) for component in sampled_rgba[:4]]
    while len(rgba) < 4:
        rgba.append(1.0 if len(rgba) == 3 else 0.0)
    return rgba


def _snapshot_brush_value(context):
    scene = context.scene
    return {
        "fg_rgb": tuple(getattr(scene, "ylvc_fill_rgb_fg", (1.0, 1.0, 1.0))),
        "single_fg": getattr(scene, "ylvc_single_fg", 1.0),
        "alpha_fg": getattr(scene, "ylvc_alpha_fg", 1.0),
    }


def _restore_brush_value(context, snapshot):
    scene = context.scene
    try:
        scene.ylvc_fill_rgb_fg = snapshot["fg_rgb"]
    except Exception:
        pass
    try:
        scene.ylvc_single_fg = snapshot["single_fg"]
    except Exception:
        pass
    try:
        scene.ylvc_alpha_fg = snapshot["alpha_fg"]
    except Exception:
        pass


def _apply_sampled_color_to_brush(context, sampled_rgba):
    scene = context.scene
    channel_key = getattr(scene, "ylvc_channel", "RGB")

    if channel_key == "RGB":
        try:
            scene.ylvc_fill_rgb_fg = tuple(sampled_rgba[:3])
            scene.ylvc_alpha_fg = sampled_rgba[3]
        except Exception:
            return False
        return True

    if channel_key == "A":
        try:
            scene.ylvc_alpha_fg = sampled_rgba[3]
            scene.ylvc_single_fg = sampled_rgba[3]
            return True
        except Exception:
            return False

    value = sample_channel_value(sampled_rgba, channel_key)
    try:
        scene.ylvc_single_fg = value
        return True
    except Exception:
        return False


def _snapshot_plugin_state():
    try:
        from ... import _snapshot_plugin_state as snapshot_plugin_state
        snapshot_plugin_state()
    except Exception:
        pass


class MESH_OT_YLVCBrushEyedropper(bpy.types.Operator):
    bl_idname = "mesh.ylvc_brush_eyedropper"
    bl_label = "Pick Brush Color"
    bl_description = "Sample a mesh color attribute into the current brush value"

    @classmethod
    def poll(cls, context):
        return active_mesh_has_color_attributes(context)

    def invoke(self, context, _event):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({"WARNING"}, tr("Select a mesh object first."))
            return {"CANCELLED"}

        self._context_transaction = transactions.ObjectContextTransaction(context)
        if obj.mode != "OBJECT":
            try:
                switched = transactions.ensure_object_mode_for(context, obj)
            except RuntimeError:
                switched = False
            if not switched:
                self.report({"WARNING"}, tr("Could not switch to Object Mode for color sampling."))
                return {"CANCELLED"}

        target, error = resolve_target_color_attribute(context, activate=False)
        if error:
            self._restore_started_mode(context)
            self.report({"WARNING"}, error)
            return {"CANCELLED"}

        ops_brush.request_finish_ylvc_paint_session()
        self._target_obj_name = target.obj.name
        self._layer_name = target.layer_name
        self._original_value = _snapshot_brush_value(context)
        self._has_sample = False
        self._status_text = tr("Hover over a mesh color to preview. LMB confirms; RMB or Esc cancels.")

        if context.window is not None:
            try:
                context.window.cursor_modal_set("EYEDROPPER")
            except Exception:
                pass

        context.window_manager.modal_handler_add(self)
        try:
            context.workspace.status_text_set(self._status_text)
        except Exception:
            pass
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        area = getattr(context, "area", None)
        if area is not None:
            try:
                area.tag_redraw()
            except Exception:
                pass
        try:
            context.workspace.status_text_set(self._status_text)
        except Exception:
            pass

        if event.type in {"RIGHTMOUSE", "ESC"} and event.value == "PRESS":
            _restore_brush_value(context, self._original_value)
            self._finish(context)
            return {"CANCELLED"}

        if event.type in {"MOUSEMOVE", "LEFTMOUSE"}:
            sampled_rgba, error = self._sample_from_event(context, event)
            if sampled_rgba is not None:
                if _apply_sampled_color_to_brush(context, sampled_rgba):
                    self._has_sample = True
            else:
                self._has_sample = False
                if event.type == "LEFTMOUSE" and event.value == "PRESS" and error:
                    self.report({"WARNING"}, error)

        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            if self._has_sample:
                _snapshot_plugin_state()
                self._finish(context)
                return {"FINISHED"}
            return {"RUNNING_MODAL"}

        return {"RUNNING_MODAL"}

    def _sample_from_event(self, context, event):
        _area, region, region_data = _find_view3d_window_at_mouse(context, event.mouse_x, event.mouse_y)
        if region is None or region_data is None:
            return None, tr("Hover over the 3D View and try again.")

        mouse_x, mouse_y = _event_region_coords(event, region)
        coord = (mouse_x, mouse_y)
        origin = view3d_utils.region_2d_to_origin_3d(region, region_data, coord)
        direction = view3d_utils.region_2d_to_vector_3d(region, region_data, coord)
        depsgraph = context.evaluated_depsgraph_get()

        hit, location, _normal, poly_index, hit_obj, _matrix = context.scene.ray_cast(depsgraph, origin, direction)
        if not hit or hit_obj is None or hit_obj.type != "MESH":
            return None, tr("Click on a mesh surface.")
        if hit_obj.name != self._target_obj_name:
            return None, tr("Please sample the active target object.")

        color_attr = hit_obj.data.color_attributes.get(self._layer_name)
        if color_attr is None:
            return None, tr("The target color attribute is no longer available.")

        sampled_rgba = sample_hit_color(hit_obj, hit_obj.data, color_attr, poly_index, location)
        sampled_rgba = _normalize_sampled_rgba(sampled_rgba)
        if sampled_rgba is None:
            return None, tr("Could not sample color from the surface.")
        return sampled_rgba, None

    def _restore_started_mode(self, context):
        try:
            transaction = getattr(self, "_context_transaction", None)
            if transaction is not None:
                transaction.restore()
        except Exception:
            pass

    def _finish(self, context):
        if context.window is not None:
            try:
                context.window.cursor_modal_restore()
            except Exception:
                pass
        try:
            context.workspace.status_text_set(None)
        except Exception:
            pass
        area = getattr(context, "area", None)
        if area is not None:
            try:
                area.tag_redraw()
            except Exception:
                pass
        self._restore_started_mode(context)


CLASSES = (
    MESH_OT_YLVCBrushEyedropper,
)
