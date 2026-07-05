# -*- coding: utf-8 -*-
"""Native Blender color-attribute viewport display helpers."""

import json
import time

import bpy
import numpy as np

from ...core.color_attribute import (
    INTERNAL_PREVIEW_ATTRIBUTE_NAME,
    color_attribute_data_matches_mesh,
    get_active_color_attribute_safe,
    get_color_attribute_by_name,
    get_scene_selected_color_attribute_name,
    read_color_attribute_colors,
    refresh_color_attribute_reference,
    set_active_color_attribute,
    set_scene_selected_color_attribute_name,
    user_color_attributes,
    write_color_attribute_colors,
)
from ...core.color_attribute import resolve_active_mesh
from ...core.operator_poll import active_mesh_has_color_attributes, has_active_mesh
from ...i18n import tr


_NATIVE_PREVIEW_FLAG = "ylvc_native_color_preview"
_NATIVE_PREVIEW_SPACES = "ylvc_native_color_preview_spaces"
_NATIVE_PREVIEW_SOURCE = "ylvc_native_color_preview_source"
_NATIVE_PREVIEW_ATTR_SOURCE = "ylvc_native_color_preview_attr_source"
_NATIVE_PREVIEW_ATTR_CHANNEL = "ylvc_native_color_preview_attr_channel"
_NATIVE_PREVIEW_FLAT = "ylvc_native_color_preview_flat"
_PREVIEW_CHANNEL_INDEX = {"R": 0, "G": 1, "B": 2, "A": 3}
_PENDING_PREVIEW_SYNCS = {}
_PREVIEW_SYNC_TIMER_ACTIVE = False
_PREVIEW_DEFER_INTERVAL = 0.12
_PREVIEW_RETRY_INTERVAL = 0.1
_PREVIEW_SPARSE_UPDATE_LIMIT = 20000


def _active_view3d_space(context=None):
    context = context or bpy.context

    space = getattr(context, "space_data", None)
    if getattr(space, "type", None) == "VIEW_3D":
        return space

    area = getattr(context, "area", None)
    if getattr(area, "type", None) == "VIEW_3D":
        for item in getattr(area, "spaces", []):
            if getattr(item, "type", None) == "VIEW_3D":
                return item

    return None


def _active_view3d_area(context=None):
    context = context or bpy.context
    area = getattr(context, "area", None)
    return area if getattr(area, "type", None) == "VIEW_3D" else None


def _iter_view3d_spaces(context=None):
    context = context or bpy.context
    seen = set()

    window_manager = getattr(context, "window_manager", None)
    if window_manager is not None:
        for window in getattr(window_manager, "windows", []):
            screen = getattr(window, "screen", None)
            if screen is None:
                continue
            for screen_area in getattr(screen, "areas", []):
                if getattr(screen_area, "type", None) != "VIEW_3D":
                    continue
                for item in getattr(screen_area, "spaces", []):
                    if getattr(item, "type", None) != "VIEW_3D":
                        continue
                    ptr = item.as_pointer()
                    if ptr in seen:
                        continue
                    seen.add(ptr)
                    yield item

    space = getattr(context, "space_data", None)
    if getattr(space, "type", None) == "VIEW_3D" and space.as_pointer() not in seen:
        seen.add(space.as_pointer())
        yield space

    area = getattr(context, "area", None)
    if getattr(area, "type", None) == "VIEW_3D":
        for item in getattr(area, "spaces", []):
            if getattr(item, "type", None) == "VIEW_3D" and item.as_pointer() not in seen:
                seen.add(item.as_pointer())
                yield item


def _set_shading_to_color_attribute(space):
    shading = getattr(space, "shading", None)
    if shading is None:
        return False

    changed = False
    try:
        if getattr(shading, "type", "") != "SOLID":
            return False
    except Exception:
        return False

    try:
        if getattr(shading, "color_type", "") != "VERTEX":
            shading.color_type = "VERTEX"
            changed = True
    except Exception:
        pass

    return changed


def _capture_space_state(space, area=None):
    shading = getattr(space, "shading", None)
    if shading is None:
        return None
    return {
        "space_ptr": str(space.as_pointer()),
        "area_ptr": _area_pointer(area),
        "type": getattr(shading, "type", ""),
        "color_type": getattr(shading, "color_type", ""),
        "light": getattr(shading, "light", ""),
    }


def _restore_space_state(space, state):
    shading = getattr(space, "shading", None)
    if shading is None or not state:
        return False
    for attr_name in ("type", "color_type", "light"):
        value = state.get(attr_name, "")
        if not value:
            continue
        try:
            setattr(shading, attr_name, value)
        except Exception:
            pass
    return True


def _preview_states(scene):
    if scene is None:
        return []
    states = scene.get(_NATIVE_PREVIEW_SPACES, [])
    if isinstance(states, str):
        try:
            parsed_states = json.loads(states)
        except Exception:
            return []
        return parsed_states if isinstance(parsed_states, list) else []
    return list(states) if isinstance(states, (list, tuple)) else []


def _area_pointer(area):
    if area is None:
        return ""
    try:
        return str(area.as_pointer())
    except Exception:
        return ""


def _space_pointer(space):
    if space is None:
        return ""
    try:
        return str(space.as_pointer())
    except Exception:
        return ""


def _preview_state_map(scene):
    state_map = {}
    for state in _preview_states(scene):
        if not isinstance(state, dict):
            continue
        ptr = state.get("space_ptr")
        if isinstance(ptr, str) and ptr:
            state_map[ptr] = state
    return state_map


def _preview_state_for_view(scene, space=None, area=None):
    ptr = _space_pointer(space)
    if ptr:
        state = _preview_state_map(scene).get(ptr)
        if state is not None:
            return state

    area_ptr = _area_pointer(area)
    if not area_ptr:
        return None

    for state in _preview_states(scene):
        if isinstance(state, dict) and state.get("area_ptr") == area_ptr:
            return state
    return None


def _store_preview_states(scene, states):
    if scene is None:
        return
    try:
        scene[_NATIVE_PREVIEW_SPACES] = json.dumps(states, separators=(",", ":"))
    except Exception:
        pass


def _clear_preview_states(scene):
    if scene is None:
        return
    try:
        if _NATIVE_PREVIEW_SPACES in scene:
            del scene[_NATIVE_PREVIEW_SPACES]
    except Exception:
        pass


def _set_preview_state(scene, state):
    if scene is None or not isinstance(state, dict):
        return
    ptr = state.get("space_ptr")
    if not isinstance(ptr, str) or not ptr:
        return
    state_map = _preview_state_map(scene)
    state_map[ptr] = state
    _store_preview_states(scene, list(state_map.values()))


def _remove_preview_state(scene, space, area=None):
    if scene is None:
        return
    ptr = _space_pointer(space)
    area_ptr = _area_pointer(area)
    if not ptr and not area_ptr:
        return

    states = []
    removed = False
    for state in _preview_states(scene):
        if not isinstance(state, dict):
            continue
        if (ptr and state.get("space_ptr") == ptr) or (area_ptr and state.get("area_ptr") == area_ptr):
            removed = True
            continue
        states.append(state)

    if not removed:
        return
    if states:
        _store_preview_states(scene, states)
    else:
        _clear_preview_states(scene)


def _has_preview_spaces(scene):
    return bool(_preview_state_map(scene))


def _sync_preview_flag(scene):
    if scene is None:
        return
    try:
        scene[_NATIVE_PREVIEW_FLAG] = _has_preview_spaces(scene)
    except Exception:
        pass


def _is_space_preview_enabled(scene, space, area=None):
    return _preview_state_for_view(scene, space, area) is not None


def _clear_preview_source(scene):
    if scene is None:
        return
    try:
        if _NATIVE_PREVIEW_SOURCE in scene:
            del scene[_NATIVE_PREVIEW_SOURCE]
    except Exception:
        pass


def _clear_preview_attribute_state(scene):
    if scene is None:
        return
    for key in (_NATIVE_PREVIEW_ATTR_SOURCE, _NATIVE_PREVIEW_ATTR_CHANNEL):
        try:
            if key in scene:
                del scene[key]
        except Exception:
            pass


def _flat_preview_space_pointers(scene):
    if scene is None:
        return set()
    try:
        value = scene.get(_NATIVE_PREVIEW_FLAT, [])
    except Exception:
        return set()

    if isinstance(value, str) and value.startswith("["):
        try:
            parsed_value = json.loads(value)
        except Exception:
            return set()
        value = parsed_value

    if isinstance(value, str):
        return {value} if value else set()
    if not isinstance(value, (list, tuple)):
        return set()

    pointers = set()
    for item in value:
        if isinstance(item, str) and item:
            pointers.add(item)
    return pointers


def _get_preview_flat_enabled(scene, space=None):
    pointers = _flat_preview_space_pointers(scene)
    ptr = _space_pointer(space)
    if ptr:
        return ptr in pointers
    return bool(pointers)


def _set_preview_flat_enabled(scene, enabled, space=None):
    if scene is None:
        return
    ptr = _space_pointer(space)
    if not ptr:
        return
    pointers = _flat_preview_space_pointers(scene)
    if enabled:
        pointers.add(ptr)
    else:
        pointers.discard(ptr)
    try:
        if pointers:
            scene[_NATIVE_PREVIEW_FLAT] = json.dumps(sorted(pointers), separators=(",", ":"))
        elif _NATIVE_PREVIEW_FLAT in scene:
            del scene[_NATIVE_PREVIEW_FLAT]
    except Exception:
        pass


def _clear_preview_flat_enabled(scene):
    if scene is None:
        return
    try:
        if _NATIVE_PREVIEW_FLAT in scene:
            del scene[_NATIVE_PREVIEW_FLAT]
    except Exception:
        pass


def is_flat_preview_enabled(context=None):
    context = context or bpy.context
    scene = getattr(context, "scene", None)
    return _get_preview_flat_enabled(scene, _active_view3d_space(context))


def is_solid_viewport(context=None):
    space = _active_view3d_space(context)
    shading = getattr(space, "shading", None)
    return bool(shading is not None and getattr(shading, "type", "") == "SOLID")


def is_color_attribute_display_active(context=None):
    space = _active_view3d_space(context)
    shading = getattr(space, "shading", None)
    return bool(
        shading is not None
        and getattr(shading, "type", "") == "SOLID"
        and getattr(shading, "color_type", "") == "VERTEX"
    )


def is_vertex_paint_single_channel(context=None):
    context = context or bpy.context
    obj = getattr(context, "active_object", None)
    scene = getattr(context, "scene", None)
    return bool(
        obj is not None
        and getattr(obj, "mode", "") == "VERTEX_PAINT"
        and scene is not None
        and getattr(scene, "ylvc_channel", "RGB") != "RGB"
    )


def is_edit_mode(context=None):
    context = context or bpy.context
    obj = getattr(context, "active_object", None)
    return bool(obj is not None and getattr(obj, "mode", "") == "EDIT")


def _get_preview_source_name(scene):
    if scene is None:
        return ""
    try:
        value = scene.get(_NATIVE_PREVIEW_SOURCE, "")
    except Exception:
        return ""
    return value if isinstance(value, str) else ""


def _set_preview_source_name(scene, source_name):
    if scene is None:
        return
    try:
        if source_name:
            scene[_NATIVE_PREVIEW_SOURCE] = source_name
        elif _NATIVE_PREVIEW_SOURCE in scene:
            del scene[_NATIVE_PREVIEW_SOURCE]
    except Exception:
        pass


def _remove_internal_preview_attribute(mesh):
    attr = get_color_attribute_by_name(mesh, INTERNAL_PREVIEW_ATTRIBUTE_NAME, allow_internal=True)
    if attr is None:
        return False
    try:
        mesh.color_attributes.remove(attr)
        return True
    except Exception:
        return False


def has_preview_residue(context=None):
    context = context or bpy.context
    obj = getattr(context, "active_object", None)
    if obj is None or getattr(obj, "type", None) != "MESH":
        return False
    mesh = getattr(obj, "data", None)
    return get_color_attribute_by_name(mesh, INTERNAL_PREVIEW_ATTRIBUTE_NAME, allow_internal=True) is not None


def clear_preview_residue_for_context(context=None, *, restore_active=True, clear_attribute_state=True):
    context = context or bpy.context
    obj = getattr(context, "active_object", None)
    if obj is None or getattr(obj, "type", None) != "MESH":
        return False
    mesh = getattr(obj, "data", None)
    if mesh is None:
        return False

    scene = getattr(context, "scene", None)
    source_attr = _get_work_color_attribute(mesh, scene)
    removed = _remove_internal_preview_attribute(mesh)

    if clear_attribute_state:
        _clear_preview_attribute_state(scene)

    if removed and restore_active and source_attr is not None:
        set_scene_selected_color_attribute_name(scene, source_attr.name)
        set_active_color_attribute(mesh, source_attr.name)

    if removed:
        _tag_view3d_redraw(context)
    return removed


def _get_preview_channel_for_context(context):
    scene = getattr(context, "scene", None)
    return get_preview_channel(scene)


def _get_work_color_attribute(mesh, scene=None):
    selected_name = get_scene_selected_color_attribute_name(scene)
    attr = get_color_attribute_by_name(mesh, selected_name)
    if attr is not None and color_attribute_data_matches_mesh(mesh, attr):
        return attr

    source_name = _get_preview_source_name(scene)
    attr = get_color_attribute_by_name(mesh, source_name)
    if attr is not None and color_attribute_data_matches_mesh(mesh, attr):
        return attr

    attr = get_active_color_attribute_safe(mesh)
    return refresh_color_attribute_reference(mesh, attr)


def _build_single_channel_preview_colors(source_colors, channel_key):
    channel_index = _PREVIEW_CHANNEL_INDEX[channel_key]
    source_colors = np.asarray(source_colors, dtype=np.float32).reshape(-1, 4)
    gray = np.clip(source_colors[:, channel_index], 0.0, 1.0)
    preview_colors = np.empty_like(source_colors)
    preview_colors[:, 0] = gray
    preview_colors[:, 1] = gray
    preview_colors[:, 2] = gray
    preview_colors[:, 3] = 1.0
    return preview_colors


def _get_preview_attribute_state(scene):
    if scene is None:
        return "", ""
    source_name = _get_preview_source_name(scene)
    try:
        attr_source = scene.get(_NATIVE_PREVIEW_ATTR_SOURCE, "")
    except Exception:
        attr_source = ""
    try:
        attr_channel = scene.get(_NATIVE_PREVIEW_ATTR_CHANNEL, "")
    except Exception:
        attr_channel = ""
    return (
        source_name if isinstance(source_name, str) else "",
        attr_source if isinstance(attr_source, str) else "",
        attr_channel if isinstance(attr_channel, str) else "",
    )


def _set_preview_attribute_state(scene, source_name, channel_key):
    if scene is None:
        return
    try:
        scene[_NATIVE_PREVIEW_ATTR_SOURCE] = source_name or ""
        scene[_NATIVE_PREVIEW_ATTR_CHANNEL] = channel_key or ""
    except Exception:
        pass


def _ensure_preview_attribute(mesh, source_attr, channel_key, scene=None, source_colors=None, *, force=False):
    source_attr = refresh_color_attribute_reference(mesh, source_attr)
    if source_attr is None:
        return None

    source_name = getattr(source_attr, "name", "")
    source_count = len(source_attr.data)
    preview_attr = get_color_attribute_by_name(mesh, INTERNAL_PREVIEW_ATTRIBUTE_NAME, allow_internal=True)
    _prev_source_name, prev_attr_source, prev_attr_channel = _get_preview_attribute_state(scene)
    if (
        not force
        and preview_attr is not None
        and preview_attr.domain == source_attr.domain
        and preview_attr.data_type == source_attr.data_type
        and len(preview_attr.data) == source_count
        and prev_attr_source == source_name
        and prev_attr_channel == channel_key
    ):
        return preview_attr

    if source_colors is None:
        source_colors = read_color_attribute_colors(mesh, source_attr)
    else:
        source_colors = np.asarray(source_colors, dtype=np.float32).reshape(-1, 4)
        if len(source_colors) != source_count:
            source_colors = read_color_attribute_colors(mesh, source_attr)

    if (
        preview_attr is not None
        and (
            preview_attr.domain != source_attr.domain
            or preview_attr.data_type != source_attr.data_type
            or len(preview_attr.data) != source_count
            or prev_attr_source != source_name
        )
    ):
        try:
            mesh.color_attributes.remove(preview_attr)
        except Exception:
            preview_attr = None
        else:
            preview_attr = None

    if preview_attr is None:
        preview_attr = mesh.color_attributes.new(
            name=INTERNAL_PREVIEW_ATTRIBUTE_NAME,
            type=source_attr.data_type,
            domain=source_attr.domain,
        )

    preview_colors = _build_single_channel_preview_colors(source_colors, channel_key)
    write_color_attribute_colors(preview_attr, preview_colors)
    try:
        mesh.update()
    except Exception:
        try:
            mesh.update_tag()
        except Exception:
            pass
    _set_preview_attribute_state(scene, source_name, channel_key)
    return preview_attr


def _tag_view3d_redraw(context=None):
    context = context or bpy.context
    area = getattr(context, "area", None)
    if getattr(area, "type", None) == "VIEW_3D":
        try:
            area.tag_redraw()
        except Exception:
            pass
    return


def sync_preview_color_layer_for_context(layer_name="", context=None, source_colors=None, *, force=False):
    context = context or bpy.context
    context_transaction = None
    if is_edit_mode(context):
        try:
            from ...services import transactions
            context_transaction = transactions.ObjectContextTransaction(context)
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:
            context_transaction = None
            return False

    try:
        return _sync_preview_color_layer_for_context_impl(
            layer_name,
            context=context,
            source_colors=source_colors,
            force=force,
        )
    finally:
        if context_transaction is not None:
            context_transaction.restore()


def _sync_preview_color_layer_for_context_impl(layer_name="", context=None, source_colors=None, *, force=False):
    context = context or bpy.context
    obj = getattr(context, "active_object", None)
    if obj is None or getattr(obj, "type", None) != "MESH":
        return False
    mesh = getattr(obj, "data", None)
    if mesh is None:
        return False

    scene = getattr(context, "scene", None)
    source_attr = get_color_attribute_by_name(mesh, layer_name)
    if source_attr is None:
        source_attr = _get_work_color_attribute(mesh, scene)
    if source_attr is None:
        return False

    set_scene_selected_color_attribute_name(scene, source_attr.name)
    _set_preview_source_name(scene, source_attr.name)
    channel = _get_preview_channel_for_context(context)
    display_attr = source_attr
    if is_native_preview_enabled(context) and channel in _PREVIEW_CHANNEL_INDEX:
        display_attr = _ensure_preview_attribute(
            mesh,
            source_attr,
            channel,
            scene=scene,
            source_colors=source_colors,
            force=force,
        )
        if display_attr is None:
            return False
    else:
        _remove_internal_preview_attribute(mesh)
        _clear_preview_attribute_state(scene)

    set_active_color_attribute(mesh, display_attr.name)
    return True


def update_preview_color_indices_for_context(layer_name="", context=None, source_colors=None, indices=None):
    context = context or bpy.context
    if not is_native_preview_enabled(context):
        return False

    channel = _get_preview_channel_for_context(context)
    if channel not in _PREVIEW_CHANNEL_INDEX:
        return False

    obj = getattr(context, "active_object", None)
    if obj is None or getattr(obj, "type", None) != "MESH":
        return False
    mesh = getattr(obj, "data", None)
    if mesh is None:
        return False

    scene = getattr(context, "scene", None)
    source_attr = get_color_attribute_by_name(mesh, layer_name)
    if source_attr is None:
        source_attr = _get_work_color_attribute(mesh, scene)
    source_attr = refresh_color_attribute_reference(mesh, source_attr)
    if source_attr is None:
        return False

    source_count = len(source_attr.data)
    if source_colors is None:
        source_colors = read_color_attribute_colors(mesh, source_attr)
    else:
        source_colors = np.asarray(source_colors, dtype=np.float32).reshape(-1, 4)
        if len(source_colors) != source_count:
            source_colors = read_color_attribute_colors(mesh, source_attr)

    preview_attr = get_color_attribute_by_name(mesh, INTERNAL_PREVIEW_ATTRIBUTE_NAME, allow_internal=True)
    _prev_source_name, prev_attr_source, _prev_attr_channel = _get_preview_attribute_state(scene)
    if (
        preview_attr is None
        or preview_attr.domain != source_attr.domain
        or preview_attr.data_type != source_attr.data_type
        or len(preview_attr.data) != source_count
        or prev_attr_source != source_attr.name
    ):
        return sync_preview_color_layer_for_context(layer_name, context=context, source_colors=source_colors)

    if indices is None:
        return sync_preview_color_layer_for_context(layer_name, context=context, source_colors=source_colors)

    dirty_indices = np.asarray(indices, dtype=np.int64).reshape(-1)
    if dirty_indices.size == 0:
        return True
    dirty_indices = dirty_indices[(dirty_indices >= 0) & (dirty_indices < source_count)]
    if dirty_indices.size == 0:
        return True
    dirty_indices = np.unique(dirty_indices)

    channel_index = _PREVIEW_CHANNEL_INDEX[channel]
    gray = np.clip(source_colors[dirty_indices, channel_index], 0.0, 1.0).astype(np.float32, copy=False)

    if dirty_indices.size > _PREVIEW_SPARSE_UPDATE_LIMIT:
        preview_colors = read_color_attribute_colors(mesh, preview_attr)
        preview_colors[dirty_indices, 0] = gray
        preview_colors[dirty_indices, 1] = gray
        preview_colors[dirty_indices, 2] = gray
        preview_colors[dirty_indices, 3] = 1.0
        write_color_attribute_colors(preview_attr, preview_colors)
    else:
        data = preview_attr.data
        for data_index, value in zip(dirty_indices, gray):
            value = float(value)
            data[int(data_index)].color = (value, value, value, 1.0)

    try:
        mesh.update()
    except Exception:
        try:
            mesh.update_tag()
        except Exception:
            pass

    _set_preview_source_name(scene, source_attr.name)
    _set_preview_attribute_state(scene, source_attr.name, channel)
    set_scene_selected_color_attribute_name(scene, source_attr.name)
    set_active_color_attribute(mesh, preview_attr.name)
    _tag_view3d_redraw(context)
    return True


def _deferred_preview_sync_timer():
    global _PREVIEW_SYNC_TIMER_ACTIVE

    now = time.perf_counter()
    due_items = []
    next_due_time = None
    for obj_name, payload in list(_PENDING_PREVIEW_SYNCS.items()):
        due_time = float(payload.get("due_time", now))
        if due_time <= now:
            due_items.append((obj_name, payload))
            _PENDING_PREVIEW_SYNCS.pop(obj_name, None)
        elif next_due_time is None or due_time < next_due_time:
            next_due_time = due_time

    if not due_items:
        if next_due_time is not None:
            _PREVIEW_SYNC_TIMER_ACTIVE = True
            return max(0.01, next_due_time - now)
        _PREVIEW_SYNC_TIMER_ACTIVE = False
        return None

    context = bpy.context
    active_obj = getattr(context, "active_object", None)
    for obj_name, payload in due_items:
        if active_obj is None or getattr(active_obj, "name", "") != obj_name:
            retries = int(payload.get("retries", 0))
            if retries > 0:
                payload["retries"] = retries - 1
                payload["due_time"] = time.perf_counter() + _PREVIEW_RETRY_INTERVAL
                _PENDING_PREVIEW_SYNCS[obj_name] = payload
            continue
        sync_preview_color_layer_for_context(
            payload.get("layer_name", ""),
            context=context,
            source_colors=payload.get("source_colors"),
        )
    _tag_view3d_redraw(context)
    if _PENDING_PREVIEW_SYNCS:
        next_due_time = min(float(payload.get("due_time", now)) for payload in _PENDING_PREVIEW_SYNCS.values())
        _PREVIEW_SYNC_TIMER_ACTIVE = True
        return max(0.01, next_due_time - time.perf_counter())
    _PREVIEW_SYNC_TIMER_ACTIVE = False
    return None


def defer_sync_preview_color_layer_for_context(layer_name="", context=None, source_colors=None):
    global _PREVIEW_SYNC_TIMER_ACTIVE

    context = context or bpy.context
    obj = getattr(context, "active_object", None)
    if obj is None or getattr(obj, "type", None) != "MESH":
        return False
    if not is_native_preview_enabled(context):
        return False

    _PENDING_PREVIEW_SYNCS[obj.name] = {
        "layer_name": layer_name,
        "source_colors": source_colors,
        "retries": 3,
        "due_time": time.perf_counter() + _PREVIEW_DEFER_INTERVAL,
    }
    if not _PREVIEW_SYNC_TIMER_ACTIVE:
        try:
            bpy.app.timers.register(_deferred_preview_sync_timer, first_interval=_PREVIEW_DEFER_INTERVAL)
            _PREVIEW_SYNC_TIMER_ACTIVE = True
        except Exception:
            _PREVIEW_SYNC_TIMER_ACTIVE = False
            return sync_preview_color_layer_for_context(layer_name, context=context, source_colors=source_colors)
    return True


def clear_deferred_preview_syncs():
    global _PREVIEW_SYNC_TIMER_ACTIVE

    _PENDING_PREVIEW_SYNCS.clear()
    if _PREVIEW_SYNC_TIMER_ACTIVE:
        try:
            bpy.app.timers.unregister(_deferred_preview_sync_timer)
        except Exception:
            pass
    _PREVIEW_SYNC_TIMER_ACTIVE = False


def sync_preview_color_layer(layer_name):
    return sync_preview_color_layer_for_context(layer_name, context=bpy.context)


def set_preview_channel(_modifier=None, _channel="RGB", context=None):
    scene = getattr(context or bpy.context, "scene", None)
    return sync_preview_color_layer_for_context(getattr(scene, "ylvc_layer_name", ""), context=context)


def get_preview_channel(scene):
    if not scene:
        return "RGB"
    return getattr(scene, "ylvc_channel", "RGB")


def update_channel_preview(_self, context):
    scene = getattr(context, "scene", None)
    if scene is not None and scene.get("ylvc_preview_channel_update_suspended", False):
        return
    sync_preview_color_layer_for_context(getattr(scene, "ylvc_layer_name", ""), context=context)
    _tag_view3d_redraw(context)


def is_native_preview_enabled(context=None):
    context = context or bpy.context
    scene = getattr(context, "scene", None)
    if scene is None:
        return False
    space = _active_view3d_space(context)
    area = _active_view3d_area(context)
    if space is not None:
        return _is_space_preview_enabled(scene, space, area) or is_color_attribute_display_active(context)
    return _has_preview_spaces(scene)


def show_active_color_attribute(context=None):
    context = context or bpy.context
    space = _active_view3d_space(context)
    if space is None:
        return False
    if not is_solid_viewport(context):
        return False
    area = _active_view3d_area(context)

    obj = getattr(context, "active_object", None)
    if obj is None or getattr(obj, "type", None) != "MESH":
        return False

    mesh = getattr(obj, "data", None)
    color_attributes = getattr(mesh, "color_attributes", None)
    if not color_attributes or len(color_attributes) == 0:
        return False

    active_attr = _get_work_color_attribute(mesh, getattr(context, "scene", None))

    if active_attr is not None:
        set_scene_selected_color_attribute_name(getattr(context, "scene", None), active_attr.name)

    scene = getattr(context, "scene", None)
    if scene is not None and active_attr is not None:
        try:
            _set_preview_source_name(scene, active_attr.name)
        except Exception:
            pass

    if not _is_space_preview_enabled(scene, space, area):
        state = _capture_space_state(space, area)
        if state is not None:
            _set_preview_state(scene, state)

    _set_shading_to_color_attribute(space)
    if _get_preview_flat_enabled(scene, space):
        shading = getattr(space, "shading", None)
        if shading is not None:
            try:
                shading.light = "FLAT"
            except Exception:
                pass
    _sync_preview_flag(scene)

    if scene is not None:
        try:
            scene["ylvc_preview_channel_update_suspended"] = True
            scene.ylvc_channel = "RGB"
        except Exception:
            pass
        finally:
            try:
                del scene["ylvc_preview_channel_update_suspended"]
            except Exception:
                pass
    sync_preview_color_layer_for_context(getattr(active_attr, "name", ""), context=context)

    _tag_view3d_redraw(context)
    return True


def restore_viewport_display(context=None, *, restore_shading=True, disable_manual_display=True):
    context = context or bpy.context
    space = _active_view3d_space(context)
    if space is None:
        return False
    area = _active_view3d_area(context)

    scene = getattr(context, "scene", None)
    state = _preview_state_for_view(scene, space, area)
    restored_any = _restore_space_state(space, state) if restore_shading else False
    if (
        disable_manual_display
        and state is None
        and restore_shading
        and is_color_attribute_display_active(context)
    ):
        shading = getattr(space, "shading", None)
        try:
            shading.color_type = "MATERIAL"
            restored_any = True
        except Exception:
            pass
    _remove_preview_state(scene, space, area)
    _sync_preview_flag(scene)

    if scene is not None and not _has_preview_spaces(scene):
        _clear_preview_attribute_state(scene)

        obj = getattr(context, "active_object", None)
        if obj is not None and getattr(obj, "type", None) == "MESH":
            mesh = getattr(obj, "data", None)
            source_name = _get_preview_source_name(scene)
            source_attr = get_color_attribute_by_name(mesh, source_name) if mesh else None
            if source_attr is None and mesh is not None:
                source_attr = _get_work_color_attribute(mesh, scene)
            if mesh is not None:
                _remove_internal_preview_attribute(mesh)
            if source_attr is not None:
                set_scene_selected_color_attribute_name(scene, source_attr.name)
                set_active_color_attribute(mesh, source_attr.name)
        _clear_preview_source(scene)

    _tag_view3d_redraw(context)
    return restored_any


def restore_preview_flat_shading(context=None):
    context = context or bpy.context
    space = _active_view3d_space(context)
    if space is None:
        return False
    area = _active_view3d_area(context)

    scene = getattr(context, "scene", None)
    shading = getattr(space, "shading", None)
    if shading is None:
        _set_preview_flat_enabled(scene, False, space)
        return False

    state = _preview_state_for_view(scene, space, area)
    light = state.get("light", "") if state else ""
    if not light:
        _set_preview_flat_enabled(scene, False, space)
        return False

    restored_any = False
    try:
        shading.light = light
        restored_any = True
    except Exception:
        pass

    _set_preview_flat_enabled(scene, False, space)
    _tag_view3d_redraw(context)
    return restored_any


def _restore_mesh_preview_source(mesh, scene_states=()):
    if mesh is None:
        return

    source_attr = None
    for source_name, _selected_name in scene_states:
        source_attr = get_color_attribute_by_name(mesh, source_name) if source_name else None
        if source_attr is not None:
            break
    if source_attr is None:
        for _source_name, selected_name in scene_states:
            source_attr = get_color_attribute_by_name(mesh, selected_name)
            if source_attr is not None:
                break
    if source_attr is None:
        user_attrs = user_color_attributes(mesh)
        source_attr = user_attrs[0] if user_attrs else None

    _remove_internal_preview_attribute(mesh)
    if source_attr is not None:
        set_active_color_attribute(mesh, source_attr.name)


def exit_preview_mode(context=None, *, restore_shading=True, clear_flat_state=False):
    context = context or bpy.context
    data = getattr(bpy, "data", None)
    scenes = list(getattr(data, "scenes", []) or [])
    state_map = {}
    scene_states = [
        (_get_preview_source_name(scene), get_scene_selected_color_attribute_name(scene))
        for scene in scenes
    ]

    for scene in scenes:
        if restore_shading:
            for state in _preview_states(scene):
                ptr = state.get("space_ptr")
                if ptr and ptr not in state_map:
                    state_map[ptr] = state

        _clear_preview_states(scene)
        _clear_preview_source(scene)
        _clear_preview_attribute_state(scene)
        if clear_flat_state:
            _clear_preview_flat_enabled(scene)
        _sync_preview_flag(scene)

    if restore_shading:
        for space in _iter_view3d_spaces(context):
            _restore_space_state(space, state_map.get(str(space.as_pointer())))

    meshes = getattr(data, "meshes", None)
    if meshes is not None:
        for mesh in meshes:
            _restore_mesh_preview_source(mesh, scene_states)

    _tag_view3d_redraw(context)
    return False


class MESH_OT_YLVCTogglePreview(bpy.types.Operator):
    bl_idname = "mesh.ylvc_toggle_preview"
    bl_label = "Toggle Channel Preview"
    bl_description = "Toggle Blender's native active attribute viewport display"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return has_active_mesh(context) and active_mesh_has_color_attributes(context)

    def execute(self, context):
        _obj, _mesh, error = resolve_active_mesh(context)
        if error:
            self.report({"WARNING"}, error)
            return {"CANCELLED"}

        if is_native_preview_enabled(context):
            restore_viewport_display(context)
            self.report({"INFO"}, tr("Attribute preview disabled."))
            return {"FINISHED"}

        if not is_solid_viewport(context):
            self.report({"WARNING"}, tr("Only available in Solid mode."))
            return {"CANCELLED"}

        if show_active_color_attribute(context):
            self.report({"INFO"}, tr("Attribute preview enabled."))
            return {"FINISHED"}

        self.report({"WARNING"}, tr("No active color attribute found."))
        return {"CANCELLED"}


class MESH_OT_YLVCTogglePreviewFlat(bpy.types.Operator):
    bl_idname = "mesh.ylvc_toggle_preview_flat"
    bl_label = "Toggle Flat Preview"
    bl_description = "Toggle viewport flat shading for channel preview"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return has_active_mesh(context) and active_mesh_has_color_attributes(context)

    def execute(self, context):
        scene = getattr(context, "scene", None)
        if scene is None:
            return {"CANCELLED"}

        obj = getattr(context, "active_object", None)
        if obj is None or getattr(obj, "type", None) != "MESH":
            return {"CANCELLED"}

        space = _active_view3d_space(context)
        if space is None:
            return {"CANCELLED"}
        if not is_solid_viewport(context):
            self.report({"WARNING"}, tr("Only available in Solid mode."))
            return {"CANCELLED"}

        if _get_preview_flat_enabled(scene, space):
            restore_preview_flat_shading(context)
            self.report({"INFO"}, tr("Flat preview disabled."))
            return {"FINISHED"}

        if show_active_color_attribute(context):
            shading = getattr(space, "shading", None)
            if shading is not None:
                try:
                    shading.light = "FLAT"
                except Exception:
                    pass
            _set_preview_flat_enabled(scene, True, space)
            _tag_view3d_redraw(context)
            self.report({"INFO"}, tr("Flat preview enabled."))
            return {"FINISHED"}

        self.report({"WARNING"}, tr("No active color attribute found."))
        return {"CANCELLED"}


class MESH_OT_YLVCSwitchRGBPreview(bpy.types.Operator):
    bl_idname = "mesh.ylvc_switch_rgb_preview"
    bl_label = "Switch to RGB Preview"
    bl_description = "Switch the plugin channel preview back to RGB for native painting"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return has_active_mesh(context) and active_mesh_has_color_attributes(context)

    def execute(self, context):
        scene = getattr(context, "scene", None)
        if scene is None:
            return {"CANCELLED"}
        if not is_solid_viewport(context):
            self.report({"WARNING"}, tr("Only available in Solid mode."))
            return {"CANCELLED"}

        scene.ylvc_channel = "RGB"
        if show_active_color_attribute(context):
            self.report({"INFO"}, tr("Switched to RGB preview."))
            return {"FINISHED"}

        self.report({"WARNING"}, tr("No active color attribute found."))
        return {"CANCELLED"}


CLASSES = (MESH_OT_YLVCTogglePreview, MESH_OT_YLVCTogglePreviewFlat, MESH_OT_YLVCSwitchRGBPreview)
