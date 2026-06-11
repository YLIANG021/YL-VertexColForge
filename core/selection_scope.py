# -*- coding: utf-8 -*-
"""Selection masks normalized across object/edit mode and color domains."""

from dataclasses import dataclass

import bmesh
import numpy as np


@dataclass
class SelectionScope:
    vertex_mask: np.ndarray
    data_mask: np.ndarray
    has_selection: bool
    selected_count: int | None


def resolve_component_selection_masks_for_object(obj, use_live_edit=True):
    if obj is None or obj.type != "MESH":
        empty = np.zeros(0, dtype=bool)
        return empty, empty, empty

    mesh = obj.data
    vert_count = len(mesh.vertices)
    edge_count = len(mesh.edges)
    face_count = len(mesh.polygons)

    if use_live_edit and obj.mode == "EDIT":
        try:
            bm = bmesh.from_edit_mesh(mesh)
            vert_mask = np.fromiter((vert.select for vert in bm.verts), dtype=bool, count=vert_count)
            edge_mask = np.fromiter((edge.select for edge in bm.edges), dtype=bool, count=edge_count)
            face_mask = np.fromiter((face.select for face in bm.faces), dtype=bool, count=face_count)
            if vert_mask.size == vert_count and edge_mask.size == edge_count and face_mask.size == face_count:
                return vert_mask, edge_mask, face_mask
        except Exception:
            pass

    vert_mask = np.zeros(vert_count, dtype=bool)
    edge_mask = np.zeros(edge_count, dtype=bool)
    face_mask = np.zeros(face_count, dtype=bool)
    if vert_count > 0:
        mesh.vertices.foreach_get("select", vert_mask)
    if edge_count > 0:
        mesh.edges.foreach_get("select", edge_mask)
    if face_count > 0:
        mesh.polygons.foreach_get("select", face_mask)
    return vert_mask, edge_mask, face_mask


def resolve_vertex_selection_mask_for_object(obj, use_live_edit=True):
    if obj is None or obj.type != "MESH":
        return np.zeros(0, dtype=bool)

    selected, _edges, _faces = resolve_component_selection_masks_for_object(obj, use_live_edit=use_live_edit)
    return selected


def resolve_vertex_auto_mask_for_object(obj, use_live_edit=True):
    selected = resolve_vertex_selection_mask_for_object(obj, use_live_edit=use_live_edit)
    if selected.size == 0:
        return selected
    if np.any(selected):
        return selected
    return np.ones(selected.shape[0], dtype=bool)


def resolve_loop_auto_mask_for_object(obj, loop_vert_indices=None, use_live_edit=True):
    if obj is None or obj.type != "MESH":
        return np.zeros(0, dtype=bool)

    mesh = obj.data
    loop_count = len(mesh.loops)
    if loop_count == 0:
        return np.zeros(0, dtype=bool)

    if loop_vert_indices is None:
        loop_vert_indices = np.empty(loop_count, dtype=np.int32)
        mesh.loops.foreach_get("vertex_index", loop_vert_indices)

    vert_mask = resolve_vertex_auto_mask_for_object(obj, use_live_edit=use_live_edit)
    return vert_mask[loop_vert_indices]


def resolve_polygon_auto_mask_for_object(obj):
    if obj is None or obj.type != "MESH":
        return np.zeros(0, dtype=bool)

    mesh = obj.data
    count = len(mesh.polygons)
    if count == 0:
        return np.zeros(0, dtype=bool)

    selected = np.empty(count, dtype=bool)
    mesh.polygons.foreach_get("select", selected)
    if np.any(selected):
        return selected
    return np.ones(count, dtype=bool)


def bm_use_vert_selection(bm):
    return any(vert.select for vert in bm.verts)


def bm_use_face_selection(bm):
    return any(face.select for face in bm.faces)


def bm_vert_in_auto_scope(vert, use_selection):
    return vert.select if use_selection else True


def bm_face_in_auto_scope(face, use_selection):
    return face.select if use_selection else True


def _resolve_active_component_mode(context, vert_mask, edge_mask, face_mask):
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
    if np.any(vert_mask):
        return "POINT"
    return "POINT"


def _build_vertex_mask_from_selected_edges(mesh, edge_mask):
    vert_mask = np.zeros(len(mesh.vertices), dtype=bool)
    if not np.any(edge_mask):
        return vert_mask

    edge_vertices = np.empty(len(mesh.edges) * 2, dtype=np.int32)
    mesh.edges.foreach_get("vertices", edge_vertices)
    edge_vertices.shape = (-1, 2)
    selected_edge_vertices = edge_vertices[edge_mask]
    if selected_edge_vertices.size > 0:
        vert_mask[selected_edge_vertices.ravel()] = True
    return vert_mask


def _build_masks_from_selected_faces(mesh, face_mask):
    vert_mask = np.zeros(len(mesh.vertices), dtype=bool)
    loop_mask = np.zeros(len(mesh.loops), dtype=bool)
    if not np.any(face_mask):
        return vert_mask, loop_mask

    for polygon in mesh.polygons:
        if not face_mask[polygon.index]:
            continue
        vert_mask[np.array(polygon.vertices, dtype=np.int32)] = True
        loop_start = polygon.loop_start
        loop_mask[loop_start : loop_start + polygon.loop_total] = True

    return vert_mask, loop_mask


def resolve_selection_scope(context, color_attr, use_live_edit=True):
    obj = context.active_object
    mesh = obj.data

    vert_sel, edge_sel, face_sel = resolve_component_selection_masks_for_object(obj, use_live_edit=use_live_edit)
    component_mode = _resolve_active_component_mode(context, vert_sel, edge_sel, face_sel)
    has_selection = bool(np.any(vert_sel) or np.any(edge_sel) or np.any(face_sel))

    loop_count = len(mesh.loops)
    loop_vert_indices = np.empty(loop_count, dtype=np.int32) if loop_count > 0 else np.zeros(0, dtype=np.int32)
    if loop_count > 0:
        mesh.loops.foreach_get("vertex_index", loop_vert_indices)

    if component_mode == "FACE":
        vertex_mask, loop_mask = _build_masks_from_selected_faces(mesh, face_sel)
    elif component_mode == "EDGE":
        vertex_mask = _build_vertex_mask_from_selected_edges(mesh, edge_sel)
        loop_mask = vertex_mask[loop_vert_indices] if loop_count > 0 and vertex_mask.size > 0 else np.zeros(loop_count, dtype=bool)
    else:
        vertex_mask = vert_sel.copy()
        loop_mask = vertex_mask[loop_vert_indices] if loop_count > 0 and vertex_mask.size > 0 else np.zeros(loop_count, dtype=bool)

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
    )
