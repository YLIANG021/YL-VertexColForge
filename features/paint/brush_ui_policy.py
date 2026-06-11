# -*- coding: utf-8 -*-
"""UI event policy for the local paint brush."""

import time

from . import brush_context


_BRUSH_PANEL_DRAW = {
    "timestamp": 0.0,
    "area_ptr": 0,
    "ui_region_ptr": 0,
}

_DRAW_FRESH_SECONDS = 0.75


def mark_brush_panel_draw(context):
    area = getattr(context, "area", None)
    region = brush_context.find_area_region(area, "UI")
    _BRUSH_PANEL_DRAW["timestamp"] = time.monotonic()
    _BRUSH_PANEL_DRAW["area_ptr"] = brush_context.safe_pointer(area)
    _BRUSH_PANEL_DRAW["ui_region_ptr"] = brush_context.safe_pointer(region)


def brush_panel_draw_is_fresh(*, area_ptr=None, ui_region_ptr=None):
    if time.monotonic() - float(_BRUSH_PANEL_DRAW.get("timestamp", 0.0)) > _DRAW_FRESH_SECONDS:
        return False
    if area_ptr and int(_BRUSH_PANEL_DRAW.get("area_ptr", 0)) != int(area_ptr):
        return False
    if ui_region_ptr and int(_BRUSH_PANEL_DRAW.get("ui_region_ptr", 0)) != int(ui_region_ptr):
        return False
    return True


def event_requests_undo(event):
    return event.type == "Z" and event.value == "PRESS" and (event.ctrl or event.oskey)


def event_commits_ui_session(event):
    return event.value == "PRESS" and event.type in {"LEFTMOUSE", "RIGHTMOUSE"}


def event_is_ui_mouse_event(event):
    return event.type in {"LEFTMOUSE", "RIGHTMOUSE"} and event.value in {"PRESS", "RELEASE"}


def is_brush_ui_section(context):
    scene = getattr(context, "scene", None)
    if scene is None:
        return False
    return getattr(scene, "ylvc_ui_section", "BRUSH") == "BRUSH"


def event_in_brush_panel_ui(context, event, *, area_ptr=None, ui_region_ptr=None):
    if not event_is_ui_mouse_event(event):
        return False
    if not is_brush_ui_section(context):
        return False
    if not brush_panel_draw_is_fresh(area_ptr=area_ptr, ui_region_ptr=ui_region_ptr):
        return False

    _area, region = brush_context.find_view3d_region_at_mouse(
        context,
        event.mouse_x,
        event.mouse_y,
        area_ptr=area_ptr or None,
        region_type="UI",
    )
    if region is None:
        return False
    if ui_region_ptr and brush_context.safe_pointer(region) != ui_region_ptr:
        return False

    try:
        ui_scale = float(context.preferences.system.ui_scale)
    except Exception:
        ui_scale = 1.0
    tab_width = min(max(28.0 * ui_scale, 24.0), max(float(region.width) * 0.25, 0.0))
    return event.mouse_x >= region.x + tab_width
