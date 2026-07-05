# -*- coding: utf-8 -*-
"""Shared Blender operator poll helpers."""

from .color_attribute import user_color_attributes


def active_mesh_object(context):
    obj = getattr(context, "active_object", None)
    return obj if obj is not None and getattr(obj, "type", None) == "MESH" else None


def has_active_mesh(context):
    return active_mesh_object(context) is not None


def active_mesh_has_color_attributes(context):
    obj = active_mesh_object(context)
    mesh = getattr(obj, "data", None) if obj else None
    return bool(user_color_attributes(mesh))


def active_mesh_in_mode(context, modes):
    obj = active_mesh_object(context)
    if obj is None:
        return False

    if isinstance(modes, str):
        modes = {modes}
    else:
        modes = set(modes or ())

    return getattr(obj, "mode", None) in modes


def active_mesh_with_color_attributes_in_mode(context, modes):
    return active_mesh_has_color_attributes(context) and active_mesh_in_mode(context, modes)


def active_mesh_has_uv_map(context):
    obj = active_mesh_object(context)
    return bool(obj and getattr(obj.data, "uv_layers", None) and obj.data.uv_layers.active)


def active_mesh_has_vertex_groups(context):
    obj = active_mesh_object(context)
    return bool(obj and len(getattr(obj, "vertex_groups", ())) > 0)


def has_scene(context):
    return getattr(context, "scene", None) is not None
