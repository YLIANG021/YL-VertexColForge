import bpy

from .. import utils
from ..features.color import ops_preview
from . import transactions


def _update_mesh_tag(mesh):
    if mesh is None:
        return
    try:
        mesh.update_tag()
    except Exception:
        pass


def _find_object_for_mesh(context, mesh):
    if mesh is None:
        return None

    active_obj = getattr(context, "active_object", None)
    if active_obj is not None and active_obj.type == "MESH" and active_obj.data == mesh:
        return active_obj

    scene = getattr(context, "scene", None)
    if scene is None:
        return None

    for obj in scene.objects:
        if obj.type == "MESH" and obj.data == mesh:
            return obj
    return None


def sync_active_layer(mesh, layer_name):
    if layer_name:
        utils.set_active_color_attribute(mesh, layer_name)
        try:
            ops_preview.sync_preview_color_layer(layer_name)
        except Exception:
            pass


def is_plugin_preview_enabled(obj):
    if obj is None or obj.type != "MESH":
        return False
    return obj.modifiers.get(ops_preview.PREVIEW_MODIFIER_NAME) is not None


def _find_view3d_area_and_region(context):
    area = getattr(context, "area", None)
    if area is not None and getattr(area, "type", None) == "VIEW_3D":
        for region in getattr(area, "regions", []):
            if getattr(region, "type", None) == "WINDOW":
                return area, region

    window = getattr(context, "window", None)
    screen = getattr(window, "screen", None) if window is not None else None
    if screen is None:
        return None, None

    for screen_area in getattr(screen, "areas", []):
        if getattr(screen_area, "type", None) != "VIEW_3D":
            continue
        for region in getattr(screen_area, "regions", []):
            if getattr(region, "type", None) == "WINDOW":
                return screen_area, region
    return None, None


def _toggle_preview_for_object(context, obj):
    area, region = _find_view3d_area_and_region(context)
    window = getattr(context, "window", None)
    screen = getattr(window, "screen", None) if window is not None else None
    if area is None or region is None or window is None or screen is None:
        return False

    override = context.copy()
    override["window"] = window
    override["screen"] = screen
    override["area"] = area
    override["region"] = region
    override["scene"] = context.scene
    override["view_layer"] = context.view_layer
    override["active_object"] = obj
    override["object"] = obj
    override["selected_objects"] = [obj]
    override["selected_editable_objects"] = [obj]

    try:
        with transactions.CleanupStack() as cleanup:
            cleanup.push_object_context(context)
            transactions.ensure_object_mode_for(context, obj)
            transactions.make_single_active_object(context, obj)
            bpy.ops.mesh.ylvc_toggle_preview(override)
        return True
    except Exception:
        return False


def ensure_preview_visible(context, layer_name="", obj=None):
    if obj is None:
        obj = getattr(context, "active_object", None)
    if obj is None or obj.type != "MESH":
        return

    if layer_name:
        sync_active_layer(obj.data, layer_name)

    preview_modifier = obj.modifiers.get(ops_preview.PREVIEW_MODIFIER_NAME)
    if preview_modifier is None and ops_preview.is_preview_supported(context):
        try:
            if _toggle_preview_for_object(context, obj):
                preview_modifier = obj.modifiers.get(ops_preview.PREVIEW_MODIFIER_NAME)
            else:
                preview_modifier = None
        except Exception:
            preview_modifier = None

    if preview_modifier is not None:
        try:
            ops_preview.set_preview_channel(preview_modifier, ops_preview.get_preview_channel(context.scene), context)
        except Exception:
            pass


def refresh_after_color_write(context, mesh, layer_name, obj=None, ensure_preview=True, force_view_update=False):
    if obj is None:
        obj = _find_object_for_mesh(context, mesh)

    _update_mesh_tag(mesh)
    sync_active_layer(mesh, layer_name)

    preview_enabled = obj is not None and is_plugin_preview_enabled(obj)
    if obj is not None and (ensure_preview or preview_enabled):
        ensure_preview_visible(context, layer_name, obj=obj)

    if force_view_update or preview_enabled:
        view_layer = getattr(context, "view_layer", None)
        try:
            if view_layer:
                view_layer.update()
        except Exception:
            pass

    area = getattr(context, "area", None)
    if area:
        try:
            area.tag_redraw()
        except Exception:
            pass
