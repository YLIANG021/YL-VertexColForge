# -*- coding: utf-8 -*-
"""Shared Blender operator poll helpers."""


def active_mesh_object(context):
    obj = getattr(context, "active_object", None)
    return obj if obj is not None and getattr(obj, "type", None) == "MESH" else None


def has_active_mesh(context):
    return active_mesh_object(context) is not None


def active_mesh_has_color_attributes(context):
    obj = active_mesh_object(context)
    color_attributes = getattr(getattr(obj, "data", None), "color_attributes", None) if obj else None
    return bool(color_attributes and len(color_attributes) > 0)


def active_mesh_in_mode(context, modes):
    obj = active_mesh_object(context)
    return obj is not None and getattr(obj, "mode", None) in set(modes)


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
