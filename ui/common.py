# -*- coding: utf-8 -*-
"""Shared UI context helpers."""

from ..core.color_attribute import (
    get_active_color_attribute_safe,
    get_color_attribute_by_name,
    get_scene_selected_color_attribute_name,
)
from ..i18n import tr, tr_format

PANEL_CATEGORY = "YL VertexColForge"
HINT_ICON = "KEYTYPE_KEYFRAME_VEC"


def get_mesh_context(context):
    obj = context.active_object
    if not obj or obj.type != "MESH":
        return None, None, None

    mesh = obj.data
    active_color_attr = None
    selected_name = get_scene_selected_color_attribute_name(getattr(context, "scene", None))
    if selected_name:
        active_color_attr = get_color_attribute_by_name(mesh, selected_name)
    if active_color_attr is None:
        active_color_attr = get_active_color_attribute_safe(mesh)
    return obj, mesh, active_color_attr


def has_mesh(context):
    _, mesh, _ = get_mesh_context(context)
    return mesh is not None


def has_active_color_attr(context):
    _, _, active_color_attr = get_mesh_context(context)
    return active_color_attr is not None


def is_point_domain(active_color_attr):
    return active_color_attr is not None and active_color_attr.domain == "POINT"


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
