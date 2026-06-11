# -*- coding: utf-8 -*-
"""Shared UI context helpers."""

import bmesh

from ..core.context import resolve_vertex_selection_mask_for_object
from ..i18n import tr, tr_format

PANEL_CATEGORY = "YL VertexColForge"
HINT_ICON = "KEYTYPE_KEYFRAME_VEC"


def get_mesh_context(context):
    obj = context.active_object
    if not obj or obj.type != "MESH":
        return None, None, None

    mesh = obj.data
    active_color_attr = None
    if mesh.color_attributes:
        idx = mesh.color_attributes.active_color_index
        if 0 <= idx < len(mesh.color_attributes):
            active_color_attr = mesh.color_attributes[idx]
        elif len(mesh.color_attributes) > 0:
            active_color_attr = mesh.color_attributes[0]
    return obj, mesh, active_color_attr


def has_mesh(context):
    _, mesh, _ = get_mesh_context(context)
    return mesh is not None


def has_active_color_attr(context):
    _, _, active_color_attr = get_mesh_context(context)
    return active_color_attr is not None


def is_point_domain(active_color_attr):
    return active_color_attr is not None and active_color_attr.domain == "POINT"


def get_partial_selection_state(context):
    obj, mesh, _ = get_mesh_context(context)
    if obj is None or mesh is None:
        return None

    total_vertices = len(mesh.vertices)
    if total_vertices == 0:
        return None

    if obj.mode == "EDIT":
        try:
            bm = bmesh.from_edit_mesh(mesh)
            has_selected = False
            has_unselected = False
            for vert in bm.verts:
                if vert.select:
                    has_selected = True
                else:
                    has_unselected = True
                if has_selected and has_unselected:
                    break
        except Exception:
            selected_mask = resolve_vertex_selection_mask_for_object(obj)
            has_selected = bool(selected_mask.any())
            has_unselected = bool((~selected_mask).any())
    else:
        selected_mask = resolve_vertex_selection_mask_for_object(obj, use_live_edit=False)
        has_selected = bool(selected_mask.any())
        has_unselected = bool((~selected_mask).any())

    if not has_selected or not has_unselected:
        return None

    return {
        "mode_label": obj.mode.replace("_", " ").title(),
    }


def draw_selection_scope_hint(layout, context):
    selection_state = get_partial_selection_state(context)
    if selection_state is None:
        return

    row = layout.row()
    row.label(text=tr("Some vertices selected. Operations affect selected vertices only."), icon=HINT_ICON)


def section_body(layout):
    return layout.column()


def draw_hint(layout, text):
    layout.label(text=tr(text), icon=HINT_ICON)


def draw_missing(layout, item):
    layout.label(text=tr_format("Missing: {item}", item=tr(item)), icon=HINT_ICON)


def draw_requires(layout, item):
    layout.label(text=tr_format("Requires: {item}", item=tr(item)), icon=HINT_ICON)


def draw_unavailable(layout, item):
    layout.label(text=tr_format("Unavailable: {item}", item=tr(item)), icon=HINT_ICON)


def draw_status(layout, text, icon=None):
    layout.label(text=tr(text), icon=icon or "INFO")


def draw_point_domain_hint(layout, active_color_attr):
    if not is_point_domain(active_color_attr):
        return

    draw_hint(layout, "Point domain works, but Face Corner is better for UV tools.")
