# -*- coding: utf-8 -*-
"""Context helpers for the local paint brush."""

import bpy


def safe_pointer(item):
    try:
        return item.as_pointer() if item is not None else 0
    except (AttributeError, ReferenceError):
        return 0


def tag_area_redraw(area, include_regions=False):
    if area is None:
        return
    try:
        area.tag_redraw()
    except Exception:
        pass
    if not include_regions:
        return
    for region in getattr(area, "regions", []):
        try:
            region.tag_redraw()
        except Exception:
            pass


def find_area_region(area, region_type):
    if area is None:
        return None
    for region in getattr(area, "regions", []):
        if getattr(region, "type", None) == region_type:
            return region
    return None


def find_view3d_window(context):
    area = getattr(context, "area", None)
    if area is None or getattr(area, "type", None) != "VIEW_3D":
        return None, None

    region = find_area_region(area, "WINDOW")
    region_data = getattr(context, "region_data", None)
    if region_data is None:
        space = getattr(area, "spaces", None)
        active_space = getattr(space, "active", None) if space is not None else None
        region_data = getattr(active_space, "region_3d", None)

    if region is None or region_data is None:
        return None, None
    return region, region_data


def _screen_from_context(context):
    screen = getattr(context, "screen", None)
    if screen is not None:
        return screen
    window = getattr(context, "window", None)
    return getattr(window, "screen", None) if window is not None else None


def _area_matches(area, mouse_x, mouse_y, area_ptr=None):
    if area_ptr is not None:
        try:
            if area.as_pointer() != area_ptr:
                return False
        except Exception:
            pass
    return (
        getattr(area, "type", None) == "VIEW_3D"
        and area.x <= mouse_x <= area.x + area.width
        and area.y <= mouse_y <= area.y + area.height
    )


def find_view3d_window_at_mouse(context, mouse_x, mouse_y, area_ptr=None):
    screen = _screen_from_context(context)
    if screen is None:
        return None, None, None

    for area in getattr(screen, "areas", []):
        if not _area_matches(area, mouse_x, mouse_y, area_ptr=area_ptr):
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


def find_view3d_region_at_mouse(context, mouse_x, mouse_y, area_ptr=None, region_type=None):
    screen = _screen_from_context(context)
    if screen is None:
        return None, None

    for area in getattr(screen, "areas", []):
        if not _area_matches(area, mouse_x, mouse_y, area_ptr=area_ptr):
            continue

        for region in getattr(area, "regions", []):
            if region_type is not None and getattr(region, "type", None) != region_type:
                continue
            if region.x <= mouse_x <= region.x + region.width and region.y <= mouse_y <= region.y + region.height:
                return area, region
        return area, None

    return None, None


def event_in_view3d_window(context, event, area_ptr=None):
    _area, region, _region_data = find_view3d_window_at_mouse(
        context,
        event.mouse_x,
        event.mouse_y,
        area_ptr=area_ptr or None,
    )
    if region is None:
        return False, None

    mouse_x = event.mouse_x - region.x
    mouse_y = event.mouse_y - region.y
    return 0 <= mouse_x <= region.width and 0 <= mouse_y <= region.height, (mouse_x, mouse_y)


def resolve_current_object(context, obj_name, obj_ptr):
    candidates = []
    if obj_name:
        candidates.append(bpy.data.objects.get(obj_name))
    candidates.append(getattr(context, "active_object", None))

    for obj in candidates:
        if obj is None:
            continue
        try:
            if obj.type != "MESH":
                continue
            if obj_ptr and safe_pointer(obj) == obj_ptr:
                return obj
            if obj_name and obj.name == obj_name:
                return obj
        except ReferenceError:
            continue
    return None


def resolve_current_paint_target(context, *, obj_name, obj_ptr, mesh_ptr, layer_name, require_same_mesh):
    obj = resolve_current_object(context, obj_name, obj_ptr)
    if obj is None:
        return None, None, None

    try:
        mesh = obj.data
        if require_same_mesh and safe_pointer(mesh) != mesh_ptr:
            return None, None, None
        color_attr = mesh.color_attributes.get(layer_name or "")
    except ReferenceError:
        return None, None, None

    if color_attr is None:
        return None, mesh, None
    return obj, mesh, color_attr


def is_paint_context_valid(context, *, obj_name, obj_ptr, mesh_ptr, layer_name, color_attr_ptr):
    obj, _mesh, color_attr = resolve_current_paint_target(
        context,
        obj_name=obj_name,
        obj_ptr=obj_ptr,
        mesh_ptr=mesh_ptr,
        layer_name=layer_name,
        require_same_mesh=True,
    )
    if obj is None or color_attr is None:
        return False
    try:
        if obj.mode != "OBJECT":
            return False
    except ReferenceError:
        return False
    return safe_pointer(color_attr) == color_attr_ptr
