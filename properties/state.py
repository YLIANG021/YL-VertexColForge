# -*- coding: utf-8 -*-
"""Undo/load state snapshot support for runtime-only add-on properties."""

import bpy
from bpy.app.handlers import persistent

USER_SETTING_KEYS = (
    "ylvc_channel",
    "ylvc_source_channel",
    "ylvc_copy_target_channel",
    "ylvc_fill_rgb_fg",
    "ylvc_fill_rgb_bg",
    "ylvc_single_fg",
    "ylvc_single_bg",
    "ylvc_alpha_fg",
    "ylvc_alpha_bg",
    "ylvc_brush_radius",
    "ylvc_brush_strength",
    "ylvc_brush_softness",
    "ylvc_write_blend_mode",
    "ylvc_blend_mode",
    "ylvc_affect_selection",
    "ylvc_select_tolerance",
)

TOOL_SETTING_KEYS = (
    "ylvc_random_mode",
    "ylvc_random_angle_threshold",
    "ylvc_tex_image",
    "ylvc_tex_source",
    "ylvc_image_padding",
    "ylvc_show_texture_advanced",
    "ylvc_weight_source",
    "ylvc_weight_group_name",
    "ylvc_transfer_mode",
    "ylvc_ui_section",
)

RUNTIME_STATE_KEYS = (
    "ylvc_previous_channel",
    "ylvc_is_tracing",
    "ylvc_tracing_type",
)

UNDO_GUARD_KEYS = USER_SETTING_KEYS + TOOL_SETTING_KEYS + RUNTIME_STATE_KEYS

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
            library = getattr(value, "library", None)
            group_state[f"{key}__library"] = getattr(library, "filepath", "") if library else ""
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


def _resolve_id_pointer(id_type_name, value_name, library_path=""):
    if not id_type_name or not value_name:
        return None

    collection_map = {
        "Image": bpy.data.images,
    }
    collection = collection_map.get(id_type_name)
    if collection is None:
        return None

    candidates = [item for item in collection if getattr(item, "name_full", "") == value_name]
    if library_path:
        for item in candidates:
            library = getattr(item, "library", None)
            if library and getattr(library, "filepath", "") == library_path:
                return item
        return None

    for item in candidates:
        if getattr(item, "library", None) is None:
            return item
    return candidates[0] if candidates else None


def _restore_group(group, group_state, keys):
    if group is None or not group_state:
        return

    for key in keys:
        if key not in group_state:
            continue
        try:
            id_type_name = group_state.get(f"{key}__idtype")
            if id_type_name:
                resolved_id = _resolve_id_pointer(
                    id_type_name,
                    group_state[key],
                    group_state.get(f"{key}__library", ""),
                )
                if resolved_id is not None:
                    setattr(group, key, resolved_id)
            else:
                setattr(group, key, group_state[key])
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
        }
    _SESSION_STATE["scenes"] = scene_states


def restore_plugin_state():
    scene_states = _SESSION_STATE.get("scenes", {})
    if not scene_states:
        return

    _set_snapshot_suspended(True)
    try:
        for scene_name, state in scene_states.items():
            scene = bpy.data.scenes.get(scene_name)
            if scene is None:
                continue
            _restore_group(scene, state.get("scene", {}), UNDO_GUARD_KEYS)
    finally:
        _set_snapshot_suspended(False)


def refresh_plugin_session_state():
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
