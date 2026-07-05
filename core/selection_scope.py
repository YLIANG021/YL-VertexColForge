# -*- coding: utf-8 -*-
"""Selection masks normalized across object/edit mode and color domains."""

from dataclasses import dataclass

import numpy as np

from .mesh_topology import loop_vertex_indices as cached_loop_vertex_indices
from .mesh_topology import edge_vertex_pairs
from .mesh_topology import polygon_loop_starts_totals


@dataclass
class SelectionScope:
    vertex_mask: np.ndarray
    data_mask: np.ndarray
    has_selection: bool
    selected_count: int | None
    loop_vertex_indices: np.ndarray | None = None


def selection_affects_operations(context):
    scene = getattr(context, "scene", None)
    if scene is None:
        return True
    return bool(getattr(scene, "ylvc_affect_selection", True))


def _full_selection_scope(mesh, color_attr, *, need_loop_indices=False):
    loop_count = len(mesh.loops)
    vertex_mask = np.ones(len(mesh.vertices), dtype=bool)
    loop_mask = np.ones(loop_count, dtype=bool)
    loop_vert_indices = cached_loop_vertex_indices(mesh) if need_loop_indices and loop_count > 0 else None

    if color_attr.domain == "POINT":
        data_mask = vertex_mask
    elif color_attr.domain == "CORNER":
        data_mask = loop_mask
    else:
        data_mask = np.ones(len(color_attr.data), dtype=bool)

    selected_count = int(data_mask.size)
    return SelectionScope(
        vertex_mask=vertex_mask,
        data_mask=data_mask,
        has_selection=False,
        selected_count=selected_count,
        loop_vertex_indices=loop_vert_indices,
    )


def _mesh_select_mode(context):
    tool_settings = getattr(context, "tool_settings", None)
    if tool_settings is None:
        return (False, False, False)
    return tuple(getattr(tool_settings, "mesh_select_mode", (False, False, False)))


def _single_component_mode_from_context(context):
    mesh_select_mode = _mesh_select_mode(context)
    if sum(1 for item in mesh_select_mode if item) != 1:
        return None
    if mesh_select_mode[2]:
        return "FACE"
    if mesh_select_mode[1]:
        return "EDGE"
    if mesh_select_mode[0]:
        return "POINT"
    return None


def resolve_component_selection_masks_for_object(
    obj,
    use_live_edit=True,
    *,
    read_vertices=True,
    read_edges=True,
    read_faces=True,
):
    if obj is None or obj.type != "MESH":
        empty = np.zeros(0, dtype=bool)
        return empty, empty, empty

    mesh = obj.data
    vert_count = len(mesh.vertices)
    edge_count = len(mesh.edges)
    face_count = len(mesh.polygons)

    vert_mask = np.zeros(vert_count, dtype=bool)
    edge_mask = np.zeros(edge_count, dtype=bool)
    face_mask = np.zeros(face_count, dtype=bool)
    if read_vertices and vert_count > 0:
        mesh.vertices.foreach_get("select", vert_mask)
    if read_edges and edge_count > 0:
        mesh.edges.foreach_get("select", edge_mask)
    if read_faces and face_count > 0:
        mesh.polygons.foreach_get("select", face_mask)
    return vert_mask, edge_mask, face_mask


def resolve_vertex_selection_mask_for_object(obj, use_live_edit=True):
    if obj is None or obj.type != "MESH":
        return np.zeros(0, dtype=bool)

    selected, _edges, _faces = resolve_component_selection_masks_for_object(obj, use_live_edit=use_live_edit)
    return selected


def resolve_vertex_auto_mask_for_object(obj, use_live_edit=True, *, affect_selection=True):
    if obj is not None and obj.type == "MESH" and not affect_selection:
        return np.ones(len(obj.data.vertices), dtype=bool)

    selected = resolve_vertex_selection_mask_for_object(obj, use_live_edit=use_live_edit)
    if selected.size == 0:
        return selected
    if np.any(selected):
        return selected
    return np.ones(selected.shape[0], dtype=bool)


def resolve_loop_auto_mask_for_object(obj, loop_vert_indices=None, use_live_edit=True, *, affect_selection=True):
    if obj is None or obj.type != "MESH":
        return np.zeros(0, dtype=bool)

    mesh = obj.data
    loop_count = len(mesh.loops)
    if loop_count == 0:
        return np.zeros(0, dtype=bool)
    if not affect_selection:
        return np.ones(loop_count, dtype=bool)

    if loop_vert_indices is None:
        loop_vert_indices = cached_loop_vertex_indices(mesh)

    vert_mask = resolve_vertex_auto_mask_for_object(
        obj,
        use_live_edit=use_live_edit,
        affect_selection=affect_selection,
    )
    return vert_mask[loop_vert_indices]


def resolve_polygon_auto_mask_for_object(obj, *, affect_selection=True):
    if obj is None or obj.type != "MESH":
        return np.zeros(0, dtype=bool)

    mesh = obj.data
    count = len(mesh.polygons)
    if count == 0:
        return np.zeros(0, dtype=bool)
    if not affect_selection:
        return np.ones(count, dtype=bool)

    selected = np.empty(count, dtype=bool)
    mesh.polygons.foreach_get("select", selected)
    if np.any(selected):
        return selected
    return np.ones(count, dtype=bool)


def _resolve_active_component_mode(context, vert_mask, edge_mask, face_mask):
    mesh_select_mode = _mesh_select_mode(context)

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
    if np.any(vert_mask):
        return "POINT"
    return "POINT"


def _build_vertex_mask_from_selected_edges(mesh, edge_mask):
    vert_mask = np.zeros(len(mesh.vertices), dtype=bool)
    if not np.any(edge_mask):
        return vert_mask

    edge_vertices = edge_vertex_pairs(mesh)
    selected_edge_vertices = edge_vertices[edge_mask]
    if selected_edge_vertices.size > 0:
        vert_mask[selected_edge_vertices.ravel()] = True
    return vert_mask


def _expand_face_loop_indices(loops_start, loops_total, face_indices):
    face_indices = np.asarray(face_indices, dtype=np.int32).reshape(-1)
    if face_indices.size == 0:
        return np.zeros(0, dtype=np.int32)

    starts = loops_start[face_indices]
    totals = loops_total[face_indices]
    total_loop_count = int(np.sum(totals))
    if total_loop_count <= 0:
        return np.zeros(0, dtype=np.int32)

    chunk_offsets = np.cumsum(np.r_[0, totals[:-1]], dtype=np.int32)
    local_offsets = np.arange(total_loop_count, dtype=np.int32) - np.repeat(chunk_offsets, totals)
    return np.repeat(starts, totals) + local_offsets


def _build_masks_from_selected_faces(mesh, face_mask, loop_vert_indices=None):
    vert_mask = np.zeros(len(mesh.vertices), dtype=bool)
    loop_mask = np.zeros(len(mesh.loops), dtype=bool)
    if not np.any(face_mask):
        return vert_mask, loop_mask

    face_indices = np.flatnonzero(face_mask).astype(np.int32, copy=False)
    loops_start, loops_total = polygon_loop_starts_totals(mesh)
    loop_indices = _expand_face_loop_indices(loops_start, loops_total, face_indices)
    if loop_indices.size == 0:
        return vert_mask, loop_mask

    loop_mask[loop_indices] = True
    if loop_vert_indices is None:
        loop_vert_indices = cached_loop_vertex_indices(mesh)
    vert_mask[loop_vert_indices[loop_indices]] = True

    return vert_mask, loop_mask


def resolve_selection_scope(context, color_attr, use_live_edit=True, *, need_loop_indices=False):
    obj = context.active_object
    mesh = obj.data
    if not selection_affects_operations(context):
        return _full_selection_scope(mesh, color_attr, need_loop_indices=need_loop_indices)

    component_mode = _single_component_mode_from_context(context)
    read_vertices = component_mode in {None, "POINT"}
    read_edges = component_mode in {None, "EDGE"}
    read_faces = component_mode in {None, "FACE"}
    vert_sel, edge_sel, face_sel = resolve_component_selection_masks_for_object(
        obj,
        use_live_edit=use_live_edit,
        read_vertices=read_vertices,
        read_edges=read_edges,
        read_faces=read_faces,
    )
    if component_mode is None:
        component_mode = _resolve_active_component_mode(context, vert_sel, edge_sel, face_sel)
    has_selection = bool(np.any(vert_sel) or np.any(edge_sel) or np.any(face_sel))

    loop_count = len(mesh.loops)
    needs_loop_mask = color_attr.domain == "CORNER"
    needs_face_to_vertex = color_attr.domain == "POINT" and component_mode == "FACE" and has_selection
    needs_edge_or_point_to_loop = needs_loop_mask and component_mode in {"EDGE", "POINT"}
    needs_face_to_loop = needs_loop_mask and component_mode == "FACE"
    loop_vert_indices = None
    if loop_count > 0 and (need_loop_indices or needs_face_to_vertex or needs_edge_or_point_to_loop or needs_face_to_loop):
        loop_vert_indices = cached_loop_vertex_indices(mesh)

    if component_mode == "FACE":
        vertex_mask, loop_mask = _build_masks_from_selected_faces(mesh, face_sel, loop_vert_indices)
    elif component_mode == "EDGE":
        vertex_mask = _build_vertex_mask_from_selected_edges(mesh, edge_sel)
        if needs_loop_mask and loop_vert_indices is not None and vertex_mask.size > 0:
            loop_mask = vertex_mask[loop_vert_indices]
        else:
            loop_mask = np.zeros(loop_count, dtype=bool)
    else:
        vertex_mask = vert_sel.copy()
        if needs_loop_mask and loop_vert_indices is not None and vertex_mask.size > 0:
            loop_mask = vertex_mask[loop_vert_indices]
        else:
            loop_mask = np.zeros(loop_count, dtype=bool)

    if not has_selection:
        vertex_mask = np.ones(len(mesh.vertices), dtype=bool)
        loop_mask = np.ones(loop_count, dtype=bool)

    if color_attr.domain == "POINT":
        data_mask = vertex_mask
    elif color_attr.domain == "CORNER":
        data_mask = loop_mask
    else:
        data_mask = np.ones(len(color_attr.data), dtype=bool)

    selected_count = int(np.sum(data_mask)) if data_mask.size > 0 else 0
    return SelectionScope(
        vertex_mask=vertex_mask,
        data_mask=data_mask,
        has_selection=has_selection,
        selected_count=selected_count,
        loop_vertex_indices=loop_vert_indices,
    )


def resolve_data_mask_only(context, color_attr, use_live_edit=True):
    return resolve_selection_scope(context, color_attr, use_live_edit=use_live_edit, need_loop_indices=False).data_mask
