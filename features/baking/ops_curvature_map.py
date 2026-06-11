import gc
import time
from functools import partial

import bpy
import numpy as np

from ... import utils
from ...core.color_attribute import read_color_attribute_colors
from ...core.context import (
    resolve_component_selection_masks_for_object,
    resolve_loop_auto_mask_for_object,
    resolve_target_color_attribute,
    resolve_vertex_auto_mask_for_object,
)
from ...core.logging import debug
from ...core.mesh_topology import edge_vertex_pairs, loop_vertex_indices, vertex_normals, vertex_positions
from ...core.operator_poll import active_mesh_has_color_attributes
from ...core.write_engine import restore_color_array_to_attribute, write_blended_color_array_to_attribute
from ...i18n import tr
from ..gradients.core_color_engine import (
    build_ramp_lut,
    ensure_light_ramp_node,
    sample_lut_array_out,
)
from ...services import display, transactions

_CURVATURE_CACHE = {}
_CURVATURE_SESSION = {}
_TIMER_RUNNING = False
TIMER_INTERVAL = 0.03
DEFERRED_REFRESH_DELAY = 0.18


def _stop_curvature_timer():
    global _TIMER_RUNNING
    try:
        if bpy.app.timers.is_registered(curvature_timer):
            bpy.app.timers.unregister(curvature_timer)
    except Exception:
        pass
    _TIMER_RUNNING = False


def _snapshot_curvature_state():
    try:
        from ... import _snapshot_plugin_state
        _snapshot_plugin_state()
    except Exception:
        pass


def _tag_view3d_sidebar_redraw():
    wm = getattr(bpy.context, "window_manager", None)
    if wm is None:
        return

    for window in wm.windows:
        screen = getattr(window, "screen", None)
        if screen is None:
            continue
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            try:
                area.tag_redraw()
            except Exception:
                pass
            for region in area.regions:
                if region.type != "UI":
                    continue
                try:
                    region.tag_redraw()
                except Exception:
                    pass


def mark_curvature_session_visible(context):
    return


def _get_cache_key(obj):
    return obj.as_pointer()


def _get_topology_signature(mesh):
    return (len(mesh.vertices), len(mesh.edges), len(mesh.loops))


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


def _get_session_vertex_mask(obj):
    if obj is None or _CURVATURE_SESSION.get("obj_name") != obj.name:
        return None

    vertex_mask = _CURVATURE_SESSION.get("vertex_mask")
    if vertex_mask is None or vertex_mask.size != len(obj.data.vertices):
        return None
    return vertex_mask


def _restore_session_context(context=None):
    context_transaction = _CURVATURE_SESSION.pop("context_transaction", None)
    if context_transaction is None:
        return

    try:
        context_transaction.restore()
    except Exception as exc:
        debug(f"YLVC curvature context restore failed: {exc}")

    if context is not None and getattr(context, "area", None):
        try:
            context.area.tag_redraw()
        except Exception:
            pass


def _resolve_active_color_attribute(mesh, scene):
    target, error = resolve_target_color_attribute(bpy.context)
    if error:
        return None
    return target.color_attr if target and target.mesh == mesh else None


def _resolve_session_color_attribute(mesh, scene):
    settings = getattr(scene, "ylvc_curvature_props", None) if scene else None
    session_layer_name = getattr(settings, "session_layer_name", "") if settings else ""
    if session_layer_name:
        color_attr = mesh.color_attributes.get(session_layer_name)
        if color_attr is not None:
            return color_attr
    return _resolve_active_color_attribute(mesh, scene)


def _cleanup_invalid_caches():
    if not _CURVATURE_CACHE:
        return

    valid_ptrs = set()
    for obj in bpy.data.objects:
        try:
            valid_ptrs.add(obj.as_pointer())
        except Exception:
            pass

    stale_keys = [key for key in _CURVATURE_CACHE if key not in valid_ptrs]
    for key in stale_keys:
        del _CURVATURE_CACHE[key]


def _get_context_signature(context):
    obj = getattr(context, "active_object", None)
    area = getattr(context, "area", None)
    area_type = getattr(area, "type", "") if area else ""
    mode = getattr(obj, "mode", "") if obj else ""
    obj_name = getattr(obj, "name", "") if obj else ""
    return (obj_name, mode, area_type)


def _get_session_target():
    context = bpy.context
    scene = getattr(context, "scene", None)
    if scene is None:
        return None, None, None

    settings = getattr(scene, "ylvc_curvature_props", None)
    if settings is None or not settings.is_live:
        return None, None, None

    obj_name = getattr(settings, "session_obj_name", "")
    layer_name = getattr(settings, "session_layer_name", "")
    if not obj_name or not layer_name:
        return None, None, None

    obj = bpy.data.objects.get(obj_name)
    if obj is None or obj.type != "MESH":
        return None, None, None

    color_attr = obj.data.color_attributes.get(layer_name)
    if color_attr is None:
        return None, None, None

    return scene, obj, color_attr


def _restore_original_colors():
    _scene, obj, color_attr = _get_session_target()
    if obj is None or color_attr is None:
        return

    cache = _CURVATURE_CACHE.get(_get_cache_key(obj))
    if cache is None:
        return

    if len(color_attr.data) == cache["data_count"]:
        if obj.mode != "OBJECT" and _CURVATURE_SESSION.get("context_transaction") is not None:
            transactions.ensure_object_mode_for(bpy.context, obj)
        restore_color_array_to_attribute(color_attr, cache["original_colors"], mesh=obj.data, update_mesh=False)
        display.refresh_after_color_write(bpy.context, obj.data, color_attr.name, obj=obj)


def clear_curvature_session():
    _stop_curvature_timer()
    scene = getattr(bpy.context, "scene", None)
    settings = getattr(scene, "ylvc_curvature_props", None) if scene else None
    if settings is not None:
        settings.is_live = False
        settings.session_obj_name = ""
        settings.session_layer_name = ""
        settings.context_signature = ""
    _CURVATURE_CACHE.clear()
    _restore_session_context(bpy.context)
    _CURVATURE_SESSION.clear()


def cancel_curvature_live_session():
    _restore_original_colors()
    clear_curvature_session()


def _should_drop_live_preview(context):
    scene = getattr(context, "scene", None)
    if scene is None:
        return True

    settings = getattr(scene, "ylvc_curvature_props", None)
    if settings is None or not settings.is_live:
        return False

    if getattr(scene, "ylvc_ui_section", "") != "LIGHT":
        return True

    obj = getattr(context, "active_object", None)
    if obj is None or obj.type != "MESH":
        return True
    if obj.name != getattr(settings, "session_obj_name", ""):
        return True

    if obj.mode not in {"OBJECT", "EDIT", "VERTEX_PAINT"}:
        return True

    cached_signature = getattr(settings, "context_signature", "")
    if not cached_signature:
        return False

    current_signature = _get_context_signature(context)
    cached_parts = tuple(cached_signature.split("|", 2))
    if len(cached_parts) != 3:
        return False
    if current_signature[0] != cached_parts[0] or current_signature[1] != cached_parts[1]:
        return True
    return False


def clear_object_cache(obj):
    if obj is None:
        return
    _CURVATURE_CACHE.pop(_get_cache_key(obj), None)


def _build_cache(obj):
    mesh = obj.data
    color_attr = _resolve_session_color_attribute(mesh, bpy.context.scene)
    if color_attr is None or color_attr.domain not in {"POINT", "CORNER"}:
        return None

    num_verts = len(mesh.vertices)
    num_edges = len(mesh.edges)
    data_count = len(color_attr.data)
    if num_verts == 0 or num_edges == 0 or data_count == 0:
        return None

    edges = edge_vertex_pairs(mesh)

    loop_vi = None
    if color_attr.domain == "CORNER":
        loop_vi = loop_vertex_indices(mesh)

    cache = {
        "mesh_ptr": mesh.as_pointer(),
        "topo_sig": _get_topology_signature(mesh),
        "attr_name": color_attr.name,
        "attr_domain": color_attr.domain,
        "num_verts": num_verts,
        "num_edges": num_edges,
        "data_count": data_count,
        "edges": edges,
        "loop_vi": loop_vi,
        "v_co": np.empty((num_verts, 3), dtype=np.float32),
        "v_no": np.empty((num_verts, 3), dtype=np.float32),
        "avg_curv": np.zeros(num_verts, dtype=np.float32),
        "target_rgba": np.empty((data_count, 4), dtype=np.float32),
        "base_colors": np.empty((data_count, 4), dtype=np.float32),
        "original_colors": np.empty((data_count, 4), dtype=np.float32),
        "work_colors": np.empty((data_count, 4), dtype=np.float32),
        "selection_mask": None,
        "geometry_dirty": True,
        "display_dirty": True,
    }

    _CURVATURE_CACHE[_get_cache_key(obj)] = cache
    return cache


def get_or_build_cache(obj, scene):
    if obj is None or obj.type != "MESH":
        return None

    key = _get_cache_key(obj)
    mesh = obj.data
    topo_sig = _get_topology_signature(mesh)
    color_attr = _resolve_session_color_attribute(mesh, scene)
    if color_attr is None or color_attr.domain not in {"POINT", "CORNER"}:
        return None

    cache = _CURVATURE_CACHE.get(key)
    if cache is None:
        cache = _build_cache(obj)
        if cache is None:
            return None

    settings = getattr(scene, "ylvc_curvature_props", None) if scene else None
    preserve_snapshot_cache = bool(
        cache is not None
        and settings is not None
        and settings.is_live
        and getattr(settings, "session_obj_name", "") == obj.name
        and getattr(settings, "session_layer_name", "") == cache["attr_name"]
    )

    if not preserve_snapshot_cache and (
        cache["mesh_ptr"] != mesh.as_pointer()
        or cache["topo_sig"] != topo_sig
        or cache["attr_name"] != color_attr.name
        or cache["attr_domain"] != color_attr.domain
        or cache["data_count"] != len(color_attr.data)
    ):
        clear_object_cache(obj)
        cache = _build_cache(obj)
        if cache is None:
            return None

    session_vertex_mask = _get_session_vertex_mask(obj)
    if session_vertex_mask is not None:
        if color_attr.domain == "POINT":
            cache["selection_mask"] = session_vertex_mask
        else:
            if cache["loop_vi"] is None or len(cache["loop_vi"]) != len(mesh.loops):
                if preserve_snapshot_cache:
                    cache["selection_mask"] = None
                    return cache
                cache["loop_vi"] = loop_vertex_indices(mesh)
            cache["selection_mask"] = session_vertex_mask[cache["loop_vi"]]
        return cache

    if color_attr.domain == "POINT":
        if len(mesh.vertices) == cache["num_verts"]:
            cache["selection_mask"] = resolve_vertex_auto_mask_for_object(obj)
        else:
            cache["selection_mask"] = None
    else:
        if cache["loop_vi"] is None or len(cache["loop_vi"]) != len(mesh.loops):
            if preserve_snapshot_cache:
                cache["selection_mask"] = None
                return cache
            cache["loop_vi"] = loop_vertex_indices(mesh)
        cache["selection_mask"] = resolve_loop_auto_mask_for_object(obj, cache["loop_vi"])

    return cache


def invalidate_object_cache(obj, geometry=True, display=True):
    if obj is None:
        return
    cache = _CURVATURE_CACHE.get(_get_cache_key(obj))
    if cache is None:
        return
    if geometry:
        cache["geometry_dirty"] = True
    if display:
        cache["display_dirty"] = True


def recompute_base_curvature(obj, cache):
    mesh = obj.data
    num_verts = cache["num_verts"]
    edges = cache["edges"]

    cache["v_co"][:] = vertex_positions(mesh)
    cache["v_no"][:] = vertex_normals(mesh)

    v0 = cache["v_co"][edges[:, 0]]
    v1 = cache["v_co"][edges[:, 1]]
    vec = v1 - v0

    lengths = np.linalg.norm(vec, axis=1)
    lengths[lengths == 0.0] = 1e-8
    dir_vec = vec / lengths[:, None]

    n0 = cache["v_no"][edges[:, 0]]
    n1 = cache["v_no"][edges[:, 1]]

    dot0 = np.sum(n0 * dir_vec, axis=1)
    dot1 = -np.sum(n1 * dir_vec, axis=1)

    all_idx = np.concatenate((edges[:, 0], edges[:, 1]))
    all_val = np.concatenate((dot0, dot1))

    curvature_sum = np.bincount(all_idx, weights=all_val, minlength=num_verts).astype(np.float32)
    edge_counts = np.bincount(all_idx, minlength=num_verts).astype(np.float32)

    avg_curv = cache["avg_curv"]
    avg_curv[:] = curvature_sum / np.maximum(edge_counts, 1.0)

    cache["geometry_dirty"] = False
    cache["display_dirty"] = True


def apply_curvature_display(context, obj, cache):
    scene = context.scene
    settings = scene.ylvc_curvature_props
    mesh = obj.data
    color_attr = _resolve_session_color_attribute(mesh, scene)
    if color_attr is None:
        return False

    data_count = len(color_attr.data)
    if data_count != cache["data_count"]:
        return False

    val = settings.offset - cache["avg_curv"] * settings.intensity
    val = (val - settings.offset) * settings.contrast + settings.offset
    val = val.astype(np.float32, copy=False)
    np.clip(val, 0.0, 1.0, out=val)

    if color_attr.domain == "POINT":
        gray_values = val
    else:
        gray_values = val[cache["loop_vi"]]

    sample_lut_array_out(build_ramp_lut(ensure_light_ramp_node().color_ramp, 512), gray_values, cache["target_rgba"])

    np.copyto(cache["base_colors"], cache["original_colors"])
    blend_mode = getattr(scene, "ylvc_light_blend_mode", "REPLACE")
    cache["work_colors"] = write_blended_color_array_to_attribute(
        color_attr,
        cache["original_colors"],
        cache["target_rgba"],
        channel_key=getattr(scene, "ylvc_channel", "RGB"),
        blend_mode=blend_mode,
        mask=cache["selection_mask"],
        mesh=mesh,
    )
    display.refresh_after_color_write(context, mesh, color_attr.name, obj=obj)

    cache["display_dirty"] = False
    return True


def refresh_curvature_if_needed(context):
    obj = context.active_object
    if obj is None or obj.type != "MESH":
        return False

    settings = context.scene.ylvc_curvature_props
    if not settings.is_live:
        return False

    cache = get_or_build_cache(obj, context.scene)
    if cache is None:
        return False

    if cache["geometry_dirty"]:
        recompute_base_curvature(obj, cache)

    if cache["display_dirty"]:
        return apply_curvature_display(context, obj, cache)
    return True


def curvature_timer():
    global _TIMER_RUNNING

    try:
        _cleanup_invalid_caches()

        context = bpy.context
        scene = context.scene
        if scene is None:
            _TIMER_RUNNING = False
            return None

        settings = scene.ylvc_curvature_props
        if not settings.is_live:
            _TIMER_RUNNING = False
            return None

        _tag_view3d_sidebar_redraw()

        if _should_drop_live_preview(context):
            cancel_curvature_live_session()
            return None

        obj = context.active_object
        if obj is None or obj.type != "MESH":
            return TIMER_INTERVAL

        if settings.use_live_preview:
            refresh_curvature_if_needed(context)
        else:
            deadline = getattr(settings, "deferred_refresh_deadline", 0.0)
            if deadline > 0.0 and time.monotonic() >= deadline:
                refresh_curvature_if_needed(context)
                settings.deferred_refresh_deadline = 0.0
        return TIMER_INTERVAL
    except Exception as exc:
        debug(f"YLVC curvature preview error: {exc}")
        _TIMER_RUNNING = False
        return None


def ensure_timer_running():
    global _TIMER_RUNNING
    if not _TIMER_RUNNING:
        bpy.app.timers.register(curvature_timer, first_interval=TIMER_INTERVAL)
        _TIMER_RUNNING = True


def _run_deferred_curvature_refresh(token):
    context = bpy.context
    scene = getattr(context, "scene", None)
    if scene is None:
        return None

    settings = getattr(scene, "ylvc_curvature_props", None)
    if settings is None or not settings.is_live or settings.use_live_preview:
        return None

    if token != getattr(settings, "deferred_refresh_token", 0):
        return None

    refresh_curvature_if_needed(context)
    return None


def _schedule_deferred_curvature_refresh(settings):
    settings.deferred_refresh_token += 1
    settings.deferred_refresh_deadline = time.monotonic() + DEFERRED_REFRESH_DELAY
    bpy.app.timers.register(
        partial(_run_deferred_curvature_refresh, settings.deferred_refresh_token),
        first_interval=DEFERRED_REFRESH_DELAY,
    )


def _update_curvature_preview_mode(self, context):
    if not self.is_live:
        self.deferred_refresh_deadline = 0.0
        return

    obj = context.active_object
    if obj is not None and obj.type == "MESH":
        invalidate_object_cache(obj, geometry=False, display=True)
        if self.use_live_preview:
            self.deferred_refresh_deadline = 0.0
            refresh_curvature_if_needed(context)
        else:
            _schedule_deferred_curvature_refresh(self)
            ensure_timer_running()
    _snapshot_curvature_state()


def _update_curvature_live(self, context):
    if not self.is_live:
        return

    obj = context.active_object
    if obj is not None and obj.type == "MESH":
        invalidate_object_cache(obj, geometry=False, display=True)
        if self.use_live_preview:
            self.deferred_refresh_deadline = 0.0
            refresh_curvature_if_needed(context)
        else:
            _schedule_deferred_curvature_refresh(self)
            ensure_timer_running()
    _snapshot_curvature_state()


class YLVCCurvatureSettings(bpy.types.PropertyGroup):
    is_live: bpy.props.BoolProperty(
        name="Is Live",
        default=False,
        description="Internal state used by the live curvature preview",
    )
    session_obj_name: bpy.props.StringProperty(
        name="Session Object",
        default="",
        options={"SKIP_SAVE"},
    )
    session_layer_name: bpy.props.StringProperty(
        name="Session Layer",
        default="",
        options={"SKIP_SAVE"},
    )
    context_signature: bpy.props.StringProperty(
        name="Context Signature",
        default="",
        options={"SKIP_SAVE"},
    )
    use_live_preview: bpy.props.BoolProperty(
        name="Live Preview",
        default=True,
        options={"SKIP_SAVE"},
        update=_update_curvature_preview_mode,
    )
    deferred_refresh_deadline: bpy.props.FloatProperty(
        name="Deferred Refresh Deadline",
        default=0.0,
        options={"HIDDEN", "SKIP_SAVE"},
    )
    deferred_refresh_token: bpy.props.IntProperty(
        name="Deferred Refresh Token",
        default=0,
        options={"HIDDEN", "SKIP_SAVE"},
    )

    intensity: bpy.props.FloatProperty(
        name="Intensity",
        default=2.5,
        min=0.1,
        max=10.0,
        update=_update_curvature_live,
    )

    offset: bpy.props.FloatProperty(
        name="Offset",
        default=0.5,
        min=0.0,
        max=1.0,
        update=_update_curvature_live,
    )

    contrast: bpy.props.FloatProperty(
        name="Contrast",
        default=1.0,
        min=0.1,
        max=50.0,
        update=_update_curvature_live,
    )


class MESH_OT_VCM_StartCurvatureLive(bpy.types.Operator):
    bl_idname = "mesh.vcm_start_curvature_live"
    bl_label = "Curvature"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return active_mesh_has_color_attributes(context)

    def execute(self, context):
        obj = context.active_object
        settings = context.scene.ylvc_curvature_props
        clear_curvature_session()
        _CURVATURE_SESSION.clear()

        if obj is None or obj.type != "MESH":
            self.report({"WARNING"}, tr("No valid active color attribute found for curvature preview."))
            return {"CANCELLED"}

        started_in_edit_mode = obj.mode == "EDIT"
        if started_in_edit_mode:
            _CURVATURE_SESSION["context_transaction"] = transactions.ObjectContextTransaction(context)
            _CURVATURE_SESSION["obj_name"] = obj.name
            _CURVATURE_SESSION["vertex_mask"] = _edit_component_vertex_auto_mask(obj).copy()
            transactions.ensure_object_mode_for(context, obj)
            if obj.mode != "OBJECT":
                _restore_session_context(context)
                _CURVATURE_SESSION.clear()
                self.report({"WARNING"}, tr("No valid active color attribute found for curvature preview."))
                return {"CANCELLED"}
        elif obj.mode != "OBJECT":
            self.report({"WARNING"}, tr("No valid active color attribute found for curvature preview."))
            return {"CANCELLED"}

        settings = context.scene.ylvc_curvature_props
        settings.is_live = True

        cache = get_or_build_cache(obj, context.scene)
        if cache is None:
            self.report({"WARNING"}, tr("No valid active color attribute found for curvature preview."))
            settings.is_live = False
            _restore_session_context(context)
            _CURVATURE_SESSION.clear()
            return {"CANCELLED"}

        color_attr = _resolve_session_color_attribute(obj.data, context.scene)
        if color_attr is None:
            self.report({"WARNING"}, tr("No valid active color attribute found for curvature preview."))
            settings.is_live = False
            _restore_session_context(context)
            _CURVATURE_SESSION.clear()
            return {"CANCELLED"}

        cache["original_colors"][:] = read_color_attribute_colors(obj.data, color_attr)
        np.copyto(cache["base_colors"], cache["original_colors"])
        settings.session_obj_name = obj.name
        settings.session_layer_name = color_attr.name
        settings.context_signature = "|".join(_get_context_signature(context))
        settings.deferred_refresh_deadline = 0.0

        cache["geometry_dirty"] = True
        cache["display_dirty"] = True

        refresh_curvature_if_needed(context)
        ensure_timer_running()
        self.report({"INFO"}, tr("Curvature preview started."))
        return {"FINISHED"}


class MESH_OT_VCM_ApplyCurvatureLive(bpy.types.Operator):
    bl_idname = "mesh.vcm_apply_curvature_live"
    bl_label = "Apply Curvature"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(getattr(getattr(context, "scene", None), "ylvc_curvature_props", None) and context.scene.ylvc_curvature_props.is_live)

    def execute(self, context):
        clear_curvature_session()
        _cleanup_invalid_caches()
        gc.collect()
        self.report({"INFO"}, tr("Curvature applied."))
        return {"FINISHED"}


class MESH_OT_VCM_CancelCurvatureLive(bpy.types.Operator):
    bl_idname = "mesh.vcm_cancel_curvature_live"
    bl_label = "Cancel Curvature"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(getattr(getattr(context, "scene", None), "ylvc_curvature_props", None) and context.scene.ylvc_curvature_props.is_live)

    def execute(self, context):
        cancel_curvature_live_session()
        _cleanup_invalid_caches()
        gc.collect()
        self.report({"INFO"}, tr("Curvature preview canceled."))
        return {"FINISHED"}


class MESH_OT_VCM_RebuildCurvatureGeometry(bpy.types.Operator):
    bl_idname = "mesh.vcm_rebuild_curvature_geometry"
    bl_label = "Recalculate Curvature"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return active_mesh_has_color_attributes(context) and bool(
            getattr(getattr(context, "scene", None), "ylvc_curvature_props", None)
            and context.scene.ylvc_curvature_props.is_live
        )

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            return {"CANCELLED"}

        if not context.scene.ylvc_curvature_props.is_live:
            self.report({"WARNING"}, tr("Curvature is not active."))
            return {"CANCELLED"}

        invalidate_object_cache(obj, geometry=True, display=True)
        refresh_curvature_if_needed(context)
        self.report({"INFO"}, tr("Curvature recalculated."))
        return {"FINISHED"}


classes = (
    YLVCCurvatureSettings,
    MESH_OT_VCM_StartCurvatureLive,
    MESH_OT_VCM_ApplyCurvatureLive,
    MESH_OT_VCM_CancelCurvatureLive,
    MESH_OT_VCM_RebuildCurvatureGeometry,
)
