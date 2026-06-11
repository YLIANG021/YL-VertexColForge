# -*- coding: utf-8 -*-
"""Undo/load state snapshot support for runtime-only add-on properties."""

import bpy
from bpy.app.handlers import persistent

from .. import utils
from ..features import color, paint

UNDO_GUARD_KEYS = (
    "ylvc_preview_channel",
    "ylvc_channel",
    "ylvc_source_channel",
    "ylvc_cached_rgb_fg",
    "ylvc_cached_rgb_bg",
    "ylvc_cached_rgb_valid",
    "ylvc_pure_fg_values",
    "ylvc_pure_bg_values",
    "ylvc_channel_updating",
    "ylvc_previous_channel",
    "ylvc_alpha_fg",
    "ylvc_alpha_bg",
    "ylvc_brush_radius",
    "ylvc_brush_strength",
    "ylvc_brush_softness",
    "ylvc_write_blend_mode",
    "ylvc_select_tolerance",
    "ylvc_blend_mode",
    "ylvc_light_blend_mode",
    "ylvc_mirror_tolerance",
    "ylvc_is_tracing",
    "ylvc_tracing_type",
    "ylvc_use_live_gradient",
    "ylvc_random_mode",
    "ylvc_random_angle_threshold",
    "ylvc_random_vertex_group",
    "ylvc_sync_preview_channel",
    "ylvc_prev_shading_type",
    "ylvc_prev_shading_light",
    "ylvc_prev_shading_color_type",
    "ylvc_prev_shading_was_saved",
    "ylvc_tex_image",
    "ylvc_tex_source",
    "ylvc_bake_margin",
    "ylvc_show_texture_advanced",
    "ylvc_weight_source",
    "ylvc_weight_group_name",
    "ylvc_transfer_mode",
    "ylvc_show_mesh_advanced",
    "ylvc_ui_section",
    "ylvc_curvature_props",
)

AO_UNDO_KEYS = (
    "ao_samples",
    "use_ground_plane",
)

ADJUST_UNDO_KEYS = (
    "use_levels",
    "show_levels_settings",
    "lvl_black",
    "lvl_white",
    "lvl_gamma",
    "use_gradient",
    "show_gradient_settings",
    "use_hsv",
    "show_hsv_settings",
    "hsv_hue",
    "hsv_sat",
    "hsv_val",
)

BLUR_UNDO_KEYS = (
    "smooth_iterations",
)

_SESSION_STATE = {}


def _iter_scenes():
    data = getattr(bpy, "data", None)
    scenes = getattr(data, "scenes", None)
    if scenes is None:
        return
    for scene in scenes:
        yield scene


def _snapshot_group(group, keys):
    if group is None:
        return {}

    group_state = {}
    for key in keys:
        try:
            value = getattr(group, key)
        except Exception:
            continue

        if isinstance(value, bpy.types.ID):
            group_state[key] = value.name_full
            group_state[f"{key}__idtype"] = value.__class__.__name__
        elif isinstance(value, (list, tuple)):
            group_state[key] = tuple(value)
        elif hasattr(value, "__len__") and hasattr(value, "__getitem__") and not isinstance(value, (str, bytes, dict)):
            try:
                group_state[key] = tuple(value)
            except Exception:
                group_state[key] = value
        else:
            group_state[key] = value
    return group_state


def _resolve_id_pointer(id_type_name, value_name):
    if not id_type_name or not value_name:
        return None

    collection_map = {
        "Image": bpy.data.images,
        "Palette": bpy.data.palettes,
    }
    collection = collection_map.get(id_type_name)
    if collection is None:
        return None
    return collection.get(value_name)


def _restore_group(group, group_state, keys):
    if group is None or not group_state:
        return

    for key in keys:
        if key not in group_state:
            continue
        try:
            id_type_name = group_state.get(f"{key}__idtype")
            if id_type_name:
                setattr(group, key, _resolve_id_pointer(id_type_name, group_state[key]))
            else:
                setattr(group, key, group_state[key])
        except Exception:
            pass


def _snapshot_brush_holder():
    holder = utils.get_color_holder()
    if holder is None:
        return {}

    holder_state = {}
    try:
        holder_state["color"] = tuple(utils.clamp_factor(component) for component in holder.color[:3])
    except Exception:
        pass
    try:
        holder_state["secondary_color"] = tuple(utils.clamp_factor(component) for component in holder.secondary_color[:3])
    except Exception:
        pass

    try:
        if isinstance(holder, bpy.types.Brush):
            holder_state["holder_type"] = "Brush"
            holder_state["holder_name"] = holder.name_full
        else:
            holder_state["holder_type"] = "Current"
    except Exception:
        holder_state["holder_type"] = "Current"

    return holder_state


def _assign_vertex_paint_brush(brush):
    if brush is None:
        return

    try:
        vertex_paint = getattr(bpy.context.tool_settings, "vertex_paint", None)
        if vertex_paint is not None:
            vertex_paint.brush = brush
    except Exception:
        pass


def _resolve_brush_holder(holder_state):
    if not holder_state:
        return None

    if holder_state.get("holder_type") == "Brush":
        brush = bpy.data.brushes.get(holder_state.get("holder_name", ""))
        if brush is not None:
            _assign_vertex_paint_brush(brush)
            return brush

    return utils.get_color_holder(assign_brush=True)


def _restore_brush_holder(holder_state):
    holder = _resolve_brush_holder(holder_state)
    if holder is None:
        return

    if "color" in holder_state:
        try:
            holder.color = holder_state["color"]
        except Exception:
            pass
    if "secondary_color" in holder_state:
        try:
            holder.secondary_color = holder_state["secondary_color"]
        except Exception:
            pass


def _set_snapshot_suspended(value):
    _SESSION_STATE["suspend_snapshot"] = bool(value)


def snapshot_plugin_state():
    if _SESSION_STATE.get("suspend_snapshot", False):
        return

    scene_states = {}
    for scene in _iter_scenes():
        scene_states[scene.name_full] = {
            "scene": _snapshot_group(scene, UNDO_GUARD_KEYS),
            "ao": _snapshot_group(getattr(scene, "ylvc_ao_props", None), AO_UNDO_KEYS),
            "adjust": _snapshot_group(getattr(scene, "ylvc_adjust_props", None), ADJUST_UNDO_KEYS),
            "blur": _snapshot_group(getattr(scene, "ylvc_blur_props", None), BLUR_UNDO_KEYS),
        }
    _SESSION_STATE["scenes"] = scene_states
    _SESSION_STATE["brush_holder"] = _snapshot_brush_holder()


def restore_plugin_state():
    scene_states = _SESSION_STATE.get("scenes", {})
    brush_holder_state = _SESSION_STATE.get("brush_holder", {})
    if not scene_states and not brush_holder_state:
        return

    _set_snapshot_suspended(True)
    try:
        for scene_name, state in scene_states.items():
            scene = bpy.data.scenes.get(scene_name)
            if scene is None:
                continue
            _restore_group(scene, state.get("scene", {}), UNDO_GUARD_KEYS)
            _restore_group(getattr(scene, "ylvc_ao_props", None), state.get("ao", {}), AO_UNDO_KEYS)
            _restore_group(getattr(scene, "ylvc_adjust_props", None), state.get("adjust", {}), ADJUST_UNDO_KEYS)
            _restore_group(getattr(scene, "ylvc_blur_props", None), state.get("blur", {}), BLUR_UNDO_KEYS)
        _restore_brush_holder(brush_holder_state)
    finally:
        _set_snapshot_suspended(False)


def refresh_plugin_session_state():
    try:
        paint.ops_brush.request_finish_ylvc_paint_session()
    except Exception:
        pass
    color.ops_preview.sync_preview_monitor_state(force_scan=True)
    restore_plugin_state()
    snapshot_plugin_state()


@persistent
def ylvc_undo_pre(_dummy):
    _set_snapshot_suspended(True)


@persistent
def ylvc_undo_post(_dummy):
    refresh_plugin_session_state()


@persistent
def ylvc_redo_pre(_dummy):
    _set_snapshot_suspended(True)


@persistent
def ylvc_redo_post(_dummy):
    refresh_plugin_session_state()


@persistent
def ylvc_load_post(_dummy):
    _set_snapshot_suspended(False)
    color.ops_preview.sync_preview_monitor_state(force_scan=True)
    snapshot_plugin_state()


def register_handlers():
    if ylvc_undo_pre not in bpy.app.handlers.undo_pre:
        bpy.app.handlers.undo_pre.append(ylvc_undo_pre)
    if ylvc_undo_post not in bpy.app.handlers.undo_post:
        bpy.app.handlers.undo_post.append(ylvc_undo_post)
    if ylvc_redo_pre not in bpy.app.handlers.redo_pre:
        bpy.app.handlers.redo_pre.append(ylvc_redo_pre)
    if ylvc_redo_post not in bpy.app.handlers.redo_post:
        bpy.app.handlers.redo_post.append(ylvc_redo_post)
    if ylvc_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(ylvc_load_post)


def unregister_handlers():
    for handler_list, handler in (
        (bpy.app.handlers.undo_pre, ylvc_undo_pre),
        (bpy.app.handlers.undo_post, ylvc_undo_post),
        (bpy.app.handlers.redo_pre, ylvc_redo_pre),
        (bpy.app.handlers.redo_post, ylvc_redo_post),
        (bpy.app.handlers.load_post, ylvc_load_post),
    ):
        try:
            if handler in handler_list:
                handler_list.remove(handler)
        except Exception:
            pass


# Compatibility for modules that still import from the package root.
_snapshot_plugin_state = snapshot_plugin_state
