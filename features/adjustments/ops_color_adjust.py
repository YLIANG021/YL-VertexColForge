import time

import bmesh
import bpy
import numpy as np

from ... import utils
from ...core.color_attribute import find_color_layer, read_color_attribute_colors
from ...core.context import resolve_edit_color_layer, resolve_selection_scope, resolve_target_color_attribute
from ...core.logging import debug
from ...core.mesh_topology import corner_inverse_counts, edge_vertex_pairs, loop_vertex_indices
from ...core.operator_poll import active_mesh_has_color_attributes, has_scene
from ...core.write_engine import (
    read_edit_element_colors,
    restore_color_array_to_attribute,
    write_color_array_to_attribute,
    write_edit_element_colors,
)
from ...i18n import tr
from ...services import display
from ..gradients.core_color_engine import (
    build_ramp_lut,
    ensure_adjust_ramp_node,
    reset_ramp_to_default,
    sample_lut_array_out,
)
from . import ops_smooth_blur

LUMINANCE_WEIGHTS = np.array((0.2126, 0.7152, 0.0722), dtype=np.float32)
_YLVC_ADJUST_CACHE = {
    "is_active": False,
    "obj_name": "",
    "layer_name": "",
    "selection_mask": None,
    "original_colors": None,
    "work_buffer": None,
    "domain": None,
    "vert_count": 0,
    "loop_vi": None,
    "smooth_src": None,
    "smooth_dst": None,
    "smooth_inv_div": None,
    "corner_inv_counts": None,
    "point_rgb": None,
    "point_scalar": None,
    "smooth_r": None,
    "smooth_g": None,
    "smooth_b": None,
    "smooth_scalar": None,
    "smooth_sum_r": None,
    "smooth_sum_g": None,
    "smooth_sum_b": None,
    "smooth_sum_scalar": None,
    "smooth_edge_r": None,
    "smooth_edge_g": None,
    "smooth_edge_b": None,
    "smooth_edge_scalar": None,
    "selected_indices": None,
    "selected_loop_vi": None,
    "ramp_signature": None,
    "invert_passes": 0,
    "context_signature": None,
    "edit_mode": False,
    "edit_bm": None,
    "edit_layer": None,
    "edit_elements": None,
    "edit_domain": "",
}

# Legacy alias kept to avoid breaking older internal references while the
# YLVC naming cleanup rolls through the remaining modules.
_VCMC_CACHE = _YLVC_ADJUST_CACHE


def _stop_gradient_timer():
    try:
        if bpy.app.timers.is_registered(_poll_gradient_updates):
            bpy.app.timers.unregister(_poll_gradient_updates)
    except Exception:
        pass


def _ensure_gradient_timer():
    try:
        if not bpy.app.timers.is_registered(_poll_gradient_updates):
            bpy.app.timers.register(_poll_gradient_updates, first_interval=0.1)
    except Exception:
        pass


def _tag_context_redraw(context=None, include_sidebar=False):
    if context is None:
        context = bpy.context

    area = getattr(context, "area", None)
    if area is None:
        return
    try:
        area.tag_redraw()
    except Exception:
        pass
    if not include_sidebar:
        return
    for region in getattr(area, "regions", []):
        if region.type != "UI":
            continue
        try:
            region.tag_redraw()
        except Exception:
            pass


def _is_live_preview_context(context):
    if context is None:
        return False

    scene = getattr(context, "scene", None)
    if scene is None:
        return False

    if getattr(scene, "ylvc_ui_section", "") != "POST":
        return False

    return bool(_VCMC_CACHE["is_active"])


def mark_adjust_session_visible():
    return


def clear_ylvc_adjust_cache():
    """Reset the shared live preview session."""
    _stop_gradient_timer()
    _YLVC_ADJUST_CACHE["is_active"] = False
    _YLVC_ADJUST_CACHE["obj_name"] = ""
    _YLVC_ADJUST_CACHE["layer_name"] = ""
    _YLVC_ADJUST_CACHE["selection_mask"] = None
    _YLVC_ADJUST_CACHE["original_colors"] = None
    _YLVC_ADJUST_CACHE["work_buffer"] = None
    _YLVC_ADJUST_CACHE["domain"] = None
    _YLVC_ADJUST_CACHE["vert_count"] = 0
    _YLVC_ADJUST_CACHE["loop_vi"] = None
    _YLVC_ADJUST_CACHE["smooth_src"] = None
    _YLVC_ADJUST_CACHE["smooth_dst"] = None
    _YLVC_ADJUST_CACHE["smooth_inv_div"] = None
    _YLVC_ADJUST_CACHE["corner_inv_counts"] = None
    _YLVC_ADJUST_CACHE["point_rgb"] = None
    _YLVC_ADJUST_CACHE["point_scalar"] = None
    _YLVC_ADJUST_CACHE["smooth_r"] = None
    _YLVC_ADJUST_CACHE["smooth_g"] = None
    _YLVC_ADJUST_CACHE["smooth_b"] = None
    _YLVC_ADJUST_CACHE["smooth_scalar"] = None
    _YLVC_ADJUST_CACHE["smooth_sum_r"] = None
    _YLVC_ADJUST_CACHE["smooth_sum_g"] = None
    _YLVC_ADJUST_CACHE["smooth_sum_b"] = None
    _YLVC_ADJUST_CACHE["smooth_sum_scalar"] = None
    _YLVC_ADJUST_CACHE["smooth_edge_r"] = None
    _YLVC_ADJUST_CACHE["smooth_edge_g"] = None
    _YLVC_ADJUST_CACHE["smooth_edge_b"] = None
    _YLVC_ADJUST_CACHE["smooth_edge_scalar"] = None
    _YLVC_ADJUST_CACHE["selected_indices"] = None
    _YLVC_ADJUST_CACHE["selected_loop_vi"] = None
    _YLVC_ADJUST_CACHE["ramp_signature"] = None
    _YLVC_ADJUST_CACHE["invert_passes"] = 0
    _YLVC_ADJUST_CACHE["context_signature"] = None
    _YLVC_ADJUST_CACHE["edit_mode"] = False
    _YLVC_ADJUST_CACHE["edit_bm"] = None
    _YLVC_ADJUST_CACHE["edit_layer"] = None
    _YLVC_ADJUST_CACHE["edit_elements"] = None
    _YLVC_ADJUST_CACHE["edit_domain"] = ""


def _resolve_channel_key(scene):
    channel = getattr(scene, "ylvc_channel", "RGB")
    return channel if channel in {"RGB", "R", "G", "B", "A"} else "RGB"


def _build_attribute_mask(context, color_attr):
    return resolve_selection_scope(context, color_attr).data_mask.copy()


def _active_edit_component_mode(context, vert_mask, edge_mask, face_mask):
    tool_settings = getattr(context, "tool_settings", None)
    mesh_select_mode = tuple(getattr(tool_settings, "mesh_select_mode", (False, False, False))) if tool_settings else (False, False, False)
    if mesh_select_mode[2]:
        return "FACE"
    if mesh_select_mode[1]:
        return "EDGE"
    if mesh_select_mode[0]:
        return "POINT"
    if np.any(face_mask):
        return "FACE"
    if np.any(edge_mask):
        return "EDGE"
    return "POINT"


def _build_edit_session_data(context, edit_target):
    bm = edit_target.bm
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bm.verts.index_update()
    bm.edges.index_update()
    bm.faces.index_update()

    vert_count = len(bm.verts)
    vert_sel = np.fromiter((vert.select for vert in bm.verts), dtype=bool, count=vert_count)
    edge_sel = np.fromiter((edge.select for edge in bm.edges), dtype=bool, count=len(bm.edges))
    face_sel = np.fromiter((face.select for face in bm.faces), dtype=bool, count=len(bm.faces))
    has_selection = bool(np.any(vert_sel) or np.any(edge_sel) or np.any(face_sel))
    component_mode = _active_edit_component_mode(context, vert_sel, edge_sel, face_sel)

    vertex_mask = np.zeros(vert_count, dtype=bool)
    selected_faces = set()
    if has_selection:
        if component_mode == "FACE":
            for face in bm.faces:
                if face.select:
                    selected_faces.add(face.index)
                    for vert in face.verts:
                        vertex_mask[vert.index] = True
        elif component_mode == "EDGE":
            for edge in bm.edges:
                if edge.select:
                    for vert in edge.verts:
                        vertex_mask[vert.index] = True
        else:
            vertex_mask[:] = vert_sel
    else:
        vertex_mask[:] = True

    edge_pairs = np.array(
        [(edge.verts[0].index, edge.verts[1].index) for edge in bm.edges],
        dtype=np.int32,
    )
    if edge_pairs.size == 0:
        edge_pairs = np.zeros((0, 2), dtype=np.int32)

    if edit_target.domain == "POINT":
        elements = list(bm.verts)
        data_mask = vertex_mask.copy()
        loop_vi = None
    else:
        elements = []
        loop_vertices = []
        loop_mask_values = []
        for face in bm.faces:
            face_selected = face.index in selected_faces
            for loop in face.loops:
                elements.append(loop)
                loop_vertices.append(loop.vert.index)
                if not has_selection:
                    loop_mask_values.append(True)
                elif component_mode == "FACE":
                    loop_mask_values.append(face_selected)
                else:
                    loop_mask_values.append(bool(vertex_mask[loop.vert.index]))
        loop_vi = np.asarray(loop_vertices, dtype=np.int32)
        data_mask = np.asarray(loop_mask_values, dtype=bool)

    return {
        "elements": elements,
        "selection_mask": data_mask,
        "edge_pairs": edge_pairs,
        "loop_vi": loop_vi,
        "vert_count": vert_count,
    }


def _cache_topology_arrays(vert_count, edge_pairs, domain, loop_vi):
    selection_mask = _VCMC_CACHE["selection_mask"]
    _VCMC_CACHE["domain"] = domain
    _VCMC_CACHE["vert_count"] = vert_count
    _VCMC_CACHE["point_rgb"] = np.empty((vert_count, 3), dtype=np.float32)
    _VCMC_CACHE["point_scalar"] = np.empty(vert_count, dtype=np.float32)
    _VCMC_CACHE["smooth_r"] = np.empty(vert_count, dtype=np.float32)
    _VCMC_CACHE["smooth_g"] = np.empty(vert_count, dtype=np.float32)
    _VCMC_CACHE["smooth_b"] = np.empty(vert_count, dtype=np.float32)
    _VCMC_CACHE["smooth_scalar"] = np.empty(vert_count, dtype=np.float32)
    _VCMC_CACHE["smooth_sum_r"] = np.empty(vert_count, dtype=np.float32)
    _VCMC_CACHE["smooth_sum_g"] = np.empty(vert_count, dtype=np.float32)
    _VCMC_CACHE["smooth_sum_b"] = np.empty(vert_count, dtype=np.float32)
    _VCMC_CACHE["smooth_sum_scalar"] = np.empty(vert_count, dtype=np.float32)
    _VCMC_CACHE["selected_indices"] = None
    _VCMC_CACHE["selected_loop_vi"] = None

    edge_count = len(edge_pairs)
    if edge_count > 0:
        v1 = edge_pairs[:, 0].astype(np.int32, copy=False)
        v2 = edge_pairs[:, 1].astype(np.int32, copy=False)

        smooth_src = np.empty(edge_count * 2, dtype=np.int32)
        smooth_dst = np.empty(edge_count * 2, dtype=np.int32)
        smooth_src[:edge_count] = v1
        smooth_src[edge_count:] = v2
        smooth_dst[:edge_count] = v2
        smooth_dst[edge_count:] = v1

        _VCMC_CACHE["smooth_src"] = smooth_src
        _VCMC_CACHE["smooth_dst"] = smooth_dst
        _VCMC_CACHE["smooth_edge_r"] = np.empty(edge_count * 2, dtype=np.float32)
        _VCMC_CACHE["smooth_edge_g"] = np.empty(edge_count * 2, dtype=np.float32)
        _VCMC_CACHE["smooth_edge_b"] = np.empty(edge_count * 2, dtype=np.float32)
        _VCMC_CACHE["smooth_edge_scalar"] = np.empty(edge_count * 2, dtype=np.float32)

        neighbor_count = np.bincount(smooth_dst, minlength=vert_count).astype(np.float32)
        _VCMC_CACHE["smooth_inv_div"] = 1.0 / (neighbor_count + 1.0)
    else:
        _VCMC_CACHE["smooth_src"] = np.array([], dtype=np.int32)
        _VCMC_CACHE["smooth_dst"] = np.array([], dtype=np.int32)
        _VCMC_CACHE["smooth_inv_div"] = np.ones(vert_count, dtype=np.float32)
        _VCMC_CACHE["smooth_edge_r"] = None
        _VCMC_CACHE["smooth_edge_g"] = None
        _VCMC_CACHE["smooth_edge_b"] = None
        _VCMC_CACHE["smooth_edge_scalar"] = None

    if domain == "CORNER":
        _VCMC_CACHE["loop_vi"] = loop_vi
        _VCMC_CACHE["corner_inv_counts"] = corner_inverse_counts(loop_vi, vert_count)
        if selection_mask is not None and selection_mask.size == len(loop_vi) and np.any(~selection_mask):
            selected_indices = np.flatnonzero(selection_mask)
            _VCMC_CACHE["selected_indices"] = selected_indices
            _VCMC_CACHE["selected_loop_vi"] = loop_vi[selected_indices]
    else:
        _VCMC_CACHE["loop_vi"] = None
        _VCMC_CACHE["corner_inv_counts"] = None
        if selection_mask is not None and selection_mask.size == vert_count and np.any(~selection_mask):
            _VCMC_CACHE["selected_indices"] = np.flatnonzero(selection_mask)


def _cache_topology(mesh, color_attr):
    loop_vi = loop_vertex_indices(mesh) if color_attr.domain == "CORNER" else None
    _cache_topology_arrays(len(mesh.vertices), edge_vertex_pairs(mesh), color_attr.domain, loop_vi)


def _get_session_target():
    obj = bpy.data.objects.get(_VCMC_CACHE["obj_name"])
    if obj is None or obj.type != "MESH" or not obj.data.color_attributes:
        return None, None

    color_attr = obj.data.color_attributes.get(_VCMC_CACHE["layer_name"])
    if color_attr is None:
        return None, None

    return obj, color_attr


def _restore_edit_original_colors(context, obj):
    original_colors = _VCMC_CACHE.get("original_colors")
    if obj is None or obj.mode != "EDIT" or original_colors is None:
        debug("YLVC adjust: missing edit restore target or original colors.")
        return False

    try:
        elements, layer = _cached_edit_elements_and_layer(obj)
        if not elements or layer is None:
            debug("YLVC adjust: missing cached target for edit restore.")
            return False
        if len(elements) != len(original_colors):
            debug(
                "YLVC adjust: edit restore color count mismatch "
                f"({len(elements)} elements, {len(original_colors)} colors)."
            )
            return False
        write_edit_element_colors(elements, layer, original_colors)
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        display.refresh_after_color_write(
            context,
            obj.data,
            _VCMC_CACHE["layer_name"],
            obj=obj,
            ensure_preview=False,
            force_view_update=True,
        )
        _tag_context_redraw(context, include_sidebar=True)
        return True
    except Exception as exc:
        debug(f"YLVC adjust: edit restore write failed: {exc}")
        return False


def _write_edit_preview_colors(context, obj, colors):
    if obj is None or obj.mode != "EDIT":
        debug("YLVC adjust: current object is not in Edit Mode for preview write.")
        return False

    try:
        elements, layer = _cached_edit_elements_and_layer(obj)
        if not elements or layer is None:
            debug("YLVC adjust: missing cached target for edit preview write.")
            return False
        if len(elements) != len(colors):
            debug(
                "YLVC adjust: edit preview color count mismatch "
                f"({len(elements)} elements, {len(colors)} colors)."
            )
            return False
        write_edit_element_colors(elements, layer, colors)
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        display.refresh_after_color_write(
            context,
            obj.data,
            _VCMC_CACHE["layer_name"],
            obj=obj,
            ensure_preview=False,
            force_view_update=True,
        )
        _tag_context_redraw(context, include_sidebar=False)
        return True
    except Exception as exc:
        debug(f"YLVC adjust: edit preview write failed: {exc}")
        return False


def _resolve_cached_edit_layer(_obj):
    bm = _VCMC_CACHE.get("edit_bm")
    layer_name = _VCMC_CACHE.get("layer_name", "")
    if bm is None or not layer_name:
        debug("YLVC adjust: missing cached edit BMesh or layer name.")
        return None

    layer, domain, _data_type = find_color_layer(bm, layer_name)
    if layer is None:
        debug(f'YLVC adjust: cached edit layer "{layer_name}" was not found.')
        return None

    cached_domain = _VCMC_CACHE.get("edit_domain")
    if cached_domain and domain != cached_domain:
        debug(f"YLVC adjust: cached edit layer domain changed ({cached_domain} -> {domain}).")
        return None

    _VCMC_CACHE["edit_layer"] = layer
    return layer


def _cached_edit_elements_and_layer(obj):
    if obj is None or obj.mode != "EDIT":
        debug("YLVC adjust: cached edit target object is not in Edit Mode.")
        return None, None

    elements = _VCMC_CACHE.get("edit_elements")
    layer = _resolve_cached_edit_layer(obj)
    if not elements:
        debug("YLVC adjust: no cached edit elements.")
        return None, None
    if layer is None:
        return None, None
    return elements, layer


def _get_ramp_signature():
    ramp_node = ensure_adjust_ramp_node()
    if ramp_node is None or not getattr(ramp_node, "color_ramp", None):
        return None

    return tuple(
        (
            round(float(element.position), 6),
            tuple(round(float(component), 6) for component in element.color[:4]),
        )
        for element in ramp_node.color_ramp.elements
    )


def _get_context_signature(context):
    obj = getattr(context, "active_object", None)
    area = getattr(context, "area", None)
    area_type = getattr(area, "type", "") if area else ""
    mode = getattr(obj, "mode", "") if obj else ""
    obj_name = getattr(obj, "name", "") if obj else ""
    return (obj_name, mode, area_type)


def _should_drop_live_preview(context):
    if not _VCMC_CACHE["is_active"]:
        return False

    scene = getattr(context, "scene", None)
    if scene is None:
        return True
    if getattr(scene, "ylvc_ui_section", "") != "POST":
        return True

    obj = getattr(context, "active_object", None)
    if obj is None or obj.type != "MESH":
        return True
    if obj.name != _VCMC_CACHE["obj_name"]:
        return True

    if obj.mode not in {"OBJECT", "EDIT", "VERTEX_PAINT"}:
        return True

    cached_signature = _VCMC_CACHE["context_signature"]
    if cached_signature is None:
        return False

    current_signature = _get_context_signature(context)
    if current_signature[0] != cached_signature[0] or current_signature[1] != cached_signature[1]:
        return True

    return False


def cancel_live_preview_session():
    restore_original_colors()
    clear_ylvc_adjust_cache()


def _poll_gradient_updates():
    try:
        if not _VCMC_CACHE["is_active"]:
            return None

        context = bpy.context
        _tag_context_redraw(context, include_sidebar=True)
        if _should_drop_live_preview(context):
            cancel_live_preview_session()
            return None

        scene = getattr(context, "scene", None)
        if scene is not None:
            props = getattr(scene, "ylvc_adjust_props", None)
            if props is not None and props.use_gradient:
                signature = _get_ramp_signature()
                if signature != _VCMC_CACHE["ramp_signature"]:
                    _VCMC_CACHE["ramp_signature"] = signature
                    apply_color_adjust_filters(None, context)
    except Exception:
        pass
    return 0.1


def rgb_to_hsv_numpy(rgb):
    cmax = np.max(rgb, axis=1)
    cmin = np.min(rgb, axis=1)
    delta = cmax - cmin

    hsv = np.zeros_like(rgb)
    hsv[:, 2] = cmax

    s_mask = cmax > 0.0
    hsv[s_mask, 1] = delta[s_mask] / cmax[s_mask]

    r, g, b = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    d_mask = delta > 0.0

    idx_r = d_mask & (cmax == r)
    idx_g = d_mask & (cmax == g)
    idx_b = d_mask & (cmax == b)

    hsv[idx_r, 0] = (60.0 * ((g[idx_r] - b[idx_r]) / delta[idx_r]) + 360.0) % 360.0
    hsv[idx_g, 0] = (60.0 * ((b[idx_g] - r[idx_g]) / delta[idx_g]) + 120.0) % 360.0
    hsv[idx_b, 0] = (60.0 * ((r[idx_b] - g[idx_b]) / delta[idx_b]) + 240.0) % 360.0
    hsv[:, 0] /= 360.0

    return hsv


def hsv_to_rgb_numpy(hsv):
    h, s, v = hsv[:, 0], hsv[:, 1], hsv[:, 2]
    i = np.floor(h * 6.0).astype(np.int32)
    f = h * 6.0 - i

    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)
    i = i % 6

    rgb = np.empty_like(hsv)

    idx = i == 0
    rgb[idx, 0], rgb[idx, 1], rgb[idx, 2] = v[idx], t[idx], p[idx]
    idx = i == 1
    rgb[idx, 0], rgb[idx, 1], rgb[idx, 2] = q[idx], v[idx], p[idx]
    idx = i == 2
    rgb[idx, 0], rgb[idx, 1], rgb[idx, 2] = p[idx], v[idx], t[idx]
    idx = i == 3
    rgb[idx, 0], rgb[idx, 1], rgb[idx, 2] = p[idx], q[idx], v[idx]
    idx = i == 4
    rgb[idx, 0], rgb[idx, 1], rgb[idx, 2] = t[idx], p[idx], v[idx]
    idx = i == 5
    rgb[idx, 0], rgb[idx, 1], rgb[idx, 2] = v[idx], p[idx], q[idx]

    return rgb


def _build_operating_rgb(active, channel_key):
    if channel_key == "RGB":
        return active[:, :3].copy()

    if channel_key == "A":
        scalar = active[:, 3:4]
    else:
        channel_index = {"R": 0, "G": 1, "B": 2}[channel_key]
        scalar = active[:, channel_index:channel_index + 1]

    return np.repeat(scalar, 3, axis=1)


def _write_operating_rgb(active, original_active, channel_key, rgb):
    if channel_key == "RGB":
        active[:, :3] = rgb
        active[:, 3] = original_active[:, 3]
        return

    scalar = np.dot(rgb, LUMINANCE_WEIGHTS)
    if channel_key == "A":
        active[:] = original_active
        active[:, 3] = scalar
        return

    channel_index = {"R": 0, "G": 1, "B": 2}[channel_key]
    active[:] = original_active
    active[:, channel_index] = scalar


def _apply_adjust_stage(context, active, active_original):
    props = context.scene.ylvc_adjust_props
    channel_key = _resolve_channel_key(context.scene)
    rgb = _build_operating_rgb(active, channel_key)

    black = props.lvl_black
    white = max(props.lvl_white, black + 1e-5)
    gamma = max(props.lvl_gamma, 1e-5)

    np.subtract(rgb, black, out=rgb)
    np.divide(rgb, (white - black), out=rgb)
    np.clip(rgb, 0.0, 1.0, out=rgb)

    if gamma != 1.0:
        np.power(rgb, 1.0 / gamma, out=rgb)

    if props.use_gradient:
        ramp_node = ensure_adjust_ramp_node()
        if ramp_node is not None and getattr(ramp_node, "color_ramp", None):
            ramp_lut = build_ramp_lut(ramp_node.color_ramp, 512)
            lum = np.dot(rgb, LUMINANCE_WEIGHTS).astype(np.float32, copy=False)
            mapped = np.empty((len(active), 4), dtype=np.float32)
            sample_lut_array_out(ramp_lut, lum, mapped)
            rgb[:] = mapped[:, :3]

    if channel_key == "RGB":
        hsv = rgb_to_hsv_numpy(rgb)
        hsv[:, 0] = (hsv[:, 0] + props.hsv_hue) % 1.0
        hsv[:, 1] *= props.hsv_sat
        hsv[:, 2] *= props.hsv_val
        np.clip(hsv, 0.0, 1.0, out=hsv)
        rgb[:] = hsv_to_rgb_numpy(hsv)

    if _VCMC_CACHE["invert_passes"] % 2 == 1:
        np.subtract(1.0, rgb, out=rgb)

    _write_operating_rgb(active, active_original, channel_key, rgb)


def restore_original_colors():
    if not _VCMC_CACHE["is_active"] or _VCMC_CACHE["original_colors"] is None:
        return

    obj_name = _VCMC_CACHE["obj_name"]
    layer_name = _VCMC_CACHE["layer_name"]
    obj = bpy.data.objects.get(obj_name)
    if obj is None or obj.type != "MESH" or not getattr(obj, "data", None):
        clear_ylvc_adjust_cache()
        return

    if _VCMC_CACHE.get("edit_mode"):
        if not _restore_edit_original_colors(bpy.context, obj):
            debug("YLVC adjust: failed to restore cached edit preview colors.")
        return

    color_attr = obj.data.color_attributes.get(layer_name) if obj.data.color_attributes else None
    if color_attr is None:
        debug(f'YLVC adjust: cached layer "{layer_name}" was not found; cancel restore skipped.')
        clear_ylvc_adjust_cache()
        return

    original_colors = _VCMC_CACHE["original_colors"]
    if len(color_attr.data) != len(original_colors):
        clear_ylvc_adjust_cache()
        return

    restore_color_array_to_attribute(color_attr, original_colors, update_mesh=False)
    display.refresh_after_color_write(
        bpy.context,
        obj.data,
        color_attr.name,
        obj=obj,
        ensure_preview=False,
        force_view_update=True,
    )


def apply_color_adjust_filters(_self, context):
    """Rebuild the full shared preview stack from the cached source colors."""
    if not _VCMC_CACHE["is_active"]:
        return
    if context is None:
        return

    obj, color_attr = _get_session_target()
    if obj is None or color_attr is None:
        clear_ylvc_adjust_cache()
        return

    original_colors = _VCMC_CACHE["original_colors"]
    work_colors = _VCMC_CACHE["work_buffer"]
    mask = _VCMC_CACHE["selection_mask"]

    if original_colors is None or work_colors is None or mask is None:
        clear_ylvc_adjust_cache()
        return

    np.copyto(work_colors, original_colors)
    active = work_colors[mask]
    active_original = original_colors[mask]

    if len(active) > 0:
        _apply_adjust_stage(context, active, active_original)
        work_colors[mask] = active

    ops_smooth_blur.apply_blur_filter(context, _VCMC_CACHE)

    np.clip(work_colors, 0.0, 1.0, out=work_colors)
    if _VCMC_CACHE.get("edit_mode"):
        _write_edit_preview_colors(context, obj, work_colors)
        area = getattr(context, "area", None)
        if area:
            _tag_context_redraw(context, include_sidebar=False)
        return

    write_color_array_to_attribute(color_attr, work_colors, update_mesh=False)
    display.refresh_after_color_write(
        context,
        obj.data,
        color_attr.name,
        obj=obj,
        ensure_preview=False,
    )
    area = getattr(context, "area", None)
    if area:
        _tag_context_redraw(context, include_sidebar=False)


def _snapshot_adjust_state():
    if _is_live_preview_context(bpy.context):
        return
    try:
        from ... import _snapshot_plugin_state
        _snapshot_plugin_state()
    except Exception:
        pass


def _update_adjust_numeric(self, context):
    apply_color_adjust_filters(self, context)
    _snapshot_adjust_state()


def _update_adjust_ui_only(_self, _context):
    _snapshot_adjust_state()


def _update_use_levels(self, context):
    if self.use_levels:
        self.show_levels_settings = True
    apply_color_adjust_filters(self, context)
    _snapshot_adjust_state()


def _update_use_gradient(self, context):
    if self.use_gradient:
        self.show_gradient_settings = True
    apply_color_adjust_filters(self, context)
    _snapshot_adjust_state()


def _update_use_hsv(self, context):
    if self.use_hsv:
        self.show_hsv_settings = True
    apply_color_adjust_filters(self, context)
    _snapshot_adjust_state()


class MESH_OT_VCMC_InitAdjust(bpy.types.Operator):
    bl_idname = "mesh.vcmc_init_adjust"
    bl_label = "Color Adjust"
    bl_description = "Start a non-destructive color adjustment session"

    @classmethod
    def poll(cls, context):
        return active_mesh_has_color_attributes(context)

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != "MESH" or not obj.data.color_attributes:
            self.report({"WARNING"}, tr("Active object must be a mesh with color attributes."))
            return {"CANCELLED"}

        edit_mode = obj.mode == "EDIT"
        if edit_mode:
            edit_target, error = resolve_edit_color_layer(context)
            if error:
                self.report({"WARNING"}, error)
                return {"CANCELLED"}
            color_attr = edit_target.color_attr
            edit_data = _build_edit_session_data(context, edit_target)
            original_colors = read_edit_element_colors(edit_data["elements"], edit_target.layer)
            data_count = len(original_colors)
            layer_name = edit_target.layer_name
        else:
            target, error = resolve_target_color_attribute(context)
            if error:
                self.report({"WARNING"}, error)
                return {"CANCELLED"}
            color_attr = target.color_attr
            data_count = len(color_attr.data)
            if data_count > 0:
                original_colors = read_color_attribute_colors(obj.data, color_attr)
            else:
                original_colors = None
            layer_name = color_attr.name

        if data_count <= 0:
            self.report({"WARNING"}, tr("The active color attribute has no writable data."))
            return {"CANCELLED"}

        clear_ylvc_adjust_cache()

        adjust_props = context.scene.ylvc_adjust_props
        adjust_props.show_levels_settings = True
        adjust_props.property_unset("lvl_black")
        adjust_props.property_unset("lvl_white")
        adjust_props.property_unset("lvl_gamma")
        adjust_props.property_unset("use_gradient")
        adjust_props.show_gradient_settings = True
        adjust_props.show_hsv_settings = True
        adjust_props.property_unset("hsv_hue")
        adjust_props.property_unset("hsv_sat")
        adjust_props.property_unset("hsv_val")

        blur_props = context.scene.ylvc_blur_props
        blur_props.property_unset("smooth_iterations")

        ramp_node = ensure_adjust_ramp_node()
        if ramp_node is not None and getattr(ramp_node, "color_ramp", None):
            reset_ramp_to_default(ramp_node.color_ramp)

        _VCMC_CACHE["obj_name"] = obj.name
        _VCMC_CACHE["layer_name"] = layer_name
        _VCMC_CACHE["selection_mask"] = edit_data["selection_mask"] if edit_mode else _build_attribute_mask(context, color_attr)
        _VCMC_CACHE["original_colors"] = original_colors
        _VCMC_CACHE["work_buffer"] = np.empty_like(original_colors)
        _VCMC_CACHE["ramp_signature"] = _get_ramp_signature()
        _VCMC_CACHE["invert_passes"] = 0
        _VCMC_CACHE["context_signature"] = _get_context_signature(context)
        _VCMC_CACHE["edit_mode"] = edit_mode
        if edit_mode:
            _VCMC_CACHE["edit_bm"] = edit_target.bm
            _VCMC_CACHE["edit_layer"] = edit_target.layer
            _VCMC_CACHE["edit_elements"] = edit_data["elements"]
            _VCMC_CACHE["edit_domain"] = edit_target.domain
            _cache_topology_arrays(
                edit_data["vert_count"],
                edit_data["edge_pairs"],
                edit_target.domain,
                edit_data["loop_vi"],
            )
        else:
            _cache_topology(obj.data, color_attr)
        _VCMC_CACHE["is_active"] = True

        if not edit_mode:
            display.ensure_preview_visible(context, color_attr.name)
        _ensure_gradient_timer()
        apply_color_adjust_filters(None, context)

        self.report({"INFO"}, tr("Color adjust preview started."))
        return {"FINISHED"}


class MESH_OT_YLVCInitAdjustRampData(bpy.types.Operator):
    bl_idname = "mesh.ylvc_init_adjust_ramp_data"
    bl_label = "Create Adjust Ramp"
    bl_description = "Create the gradient ramp used by color adjust ramp remap."
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return has_scene(context)

    def execute(self, context):
        ramp_node = ensure_adjust_ramp_node()
        if ramp_node is not None and getattr(ramp_node, "color_ramp", None):
            reset_ramp_to_default(ramp_node.color_ramp)
        if context.area:
            context.area.tag_redraw()
        self.report({"INFO"}, tr("Adjust ramp created."))
        return {"FINISHED"}


class MESH_OT_VCMC_ApplyAdjust(bpy.types.Operator):
    bl_idname = "mesh.vcmc_apply_adjust"
    bl_label = "Apply Preview"
    bl_description = "Keep the current preview result and close the preview session"

    @classmethod
    def poll(cls, _context):
        return _VCMC_CACHE["is_active"]

    def execute(self, context):
        clear_ylvc_adjust_cache()
        self.report({"INFO"}, tr("Color preview applied."))
        return {"FINISHED"}


class MESH_OT_VCMC_CancelAdjust(bpy.types.Operator):
    bl_idname = "mesh.vcmc_cancel_adjust"
    bl_label = "Cancel Preview"
    bl_description = "Restore the original colors and close the preview session"

    @classmethod
    def poll(cls, _context):
        return _VCMC_CACHE["is_active"]

    def execute(self, context):
        cancel_live_preview_session()
        self.report({"INFO"}, tr("Color preview canceled. Original colors restored."))
        return {"FINISHED"}


class MESH_OT_VCMC_InvertColors(bpy.types.Operator):
    bl_idname = "mesh.vcmc_invert_colors"
    bl_label = "Invert Colors"
    bl_description = "Apply one invert step inside the current color preview session"

    @classmethod
    def poll(cls, _context):
        return _VCMC_CACHE["is_active"]

    def execute(self, context):
        _VCMC_CACHE["invert_passes"] += 1
        apply_color_adjust_filters(None, context)
        self.report({"INFO"}, tr("Invert step applied."))
        return {"FINISHED"}


class YLVCAdjustSettings(bpy.types.PropertyGroup):
    use_levels: bpy.props.BoolProperty(
        name="Use Levels",
        default=False,
        update=_update_use_levels,
    )

    show_levels_settings: bpy.props.BoolProperty(
        name="Show Levels Settings",
        default=False,
        update=_update_adjust_ui_only,
    )

    lvl_black: bpy.props.FloatProperty(
        name="Black Point",
        default=0.0,
        min=0.0,
        max=1.0,
        update=_update_adjust_numeric,
    )

    lvl_white: bpy.props.FloatProperty(
        name="White Point",
        default=1.0,
        min=0.0,
        max=1.0,
        update=_update_adjust_numeric,
    )

    lvl_gamma: bpy.props.FloatProperty(
        name="Gamma",
        default=1.0,
        min=0.01,
        max=5.0,
        update=_update_adjust_numeric,
    )

    use_gradient: bpy.props.BoolProperty(
        name="Use Ramp Remap",
        default=False,
        update=_update_use_gradient,
    )

    show_gradient_settings: bpy.props.BoolProperty(
        name="Show Ramp Remap Settings",
        default=False,
        update=_update_adjust_ui_only,
    )

    use_hsv: bpy.props.BoolProperty(
        name="Use Hue/Saturation/Value",
        default=False,
        update=_update_use_hsv,
    )

    show_hsv_settings: bpy.props.BoolProperty(
        name="Show Hue/Saturation/Value Settings",
        default=False,
        update=_update_adjust_ui_only,
    )

    hsv_hue: bpy.props.FloatProperty(
        name="Hue",
        default=0.0,
        min=-0.5,
        max=0.5,
        update=_update_adjust_numeric,
    )

    hsv_sat: bpy.props.FloatProperty(
        name="Saturation",
        default=1.0,
        min=0.0,
        max=3.0,
        update=_update_adjust_numeric,
    )

    hsv_val: bpy.props.FloatProperty(
        name="Value",
        default=1.0,
        min=0.0,
        max=3.0,
        update=_update_adjust_numeric,
    )


classes = (
    MESH_OT_YLVCInitAdjustRampData,
    MESH_OT_VCMC_InitAdjust,
    MESH_OT_VCMC_ApplyAdjust,
    MESH_OT_VCMC_CancelAdjust,
    MESH_OT_VCMC_InvertColors,
    YLVCAdjustSettings,
)


# Legacy alias kept for older internal references.
clear_vcmc_cache = clear_ylvc_adjust_cache
