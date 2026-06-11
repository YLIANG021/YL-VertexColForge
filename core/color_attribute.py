# -*- coding: utf-8 -*-
"""Color attribute lookup, conversion, and raw array IO helpers."""

from dataclasses import dataclass

import bmesh
import bpy
import numpy as np

from ..i18n import tr_format


@dataclass
class ColorTarget:
    obj: bpy.types.Object
    mesh: bpy.types.Mesh
    color_attr: object
    layer_name: str
    domain: str
    data_type: str


@dataclass
class EditColorTarget:
    obj: bpy.types.Object
    mesh: bpy.types.Mesh
    bm: bmesh.types.BMesh
    color_attr: object
    layer_name: str
    domain: str
    data_type: str
    layer: object


def color_data_count(mesh, color_attr):
    if color_attr is None:
        return 0
    if mesh is None:
        return len(color_attr.data)
    if color_attr.domain == "POINT":
        return len(mesh.vertices)
    if color_attr.domain == "CORNER":
        return len(mesh.loops)
    return len(color_attr.data)


def read_color_attribute_colors(mesh, color_attr, *, shaped=True):
    count = color_data_count(mesh, color_attr)
    colors = np.empty(count * 4, dtype=np.float32)
    if count > 0:
        color_attr.data.foreach_get("color", colors)
    if shaped:
        colors.shape = (-1, 4)
    return colors


def write_color_attribute_colors(color_attr, colors):
    colors = np.asarray(colors, dtype=np.float32)
    color_attr.data.foreach_set("color", colors.ravel())


def get_active_color_attribute_safe(mesh):
    color_attributes = getattr(mesh, "color_attributes", None)
    if not color_attributes or len(color_attributes) == 0:
        return None

    for attr_name in ("active_color", "active"):
        try:
            active_attr = getattr(color_attributes, attr_name)
            if active_attr is not None:
                return active_attr
        except Exception:
            pass

    try:
        idx = color_attributes.active_color_index
        if 0 <= idx < len(color_attributes):
            return color_attributes[idx]
    except Exception:
        pass

    return color_attributes[0]


def set_active_color_attribute(mesh, layer_name):
    if not layer_name:
        return

    color_attributes = mesh.color_attributes
    if not color_attributes.get(layer_name):
        return

    try:
        color_attributes.active_color_name = layer_name
    except Exception:
        pass

    for index, item in enumerate(color_attributes):
        if item.name != layer_name:
            continue
        for attr_name in ("active_color_index", "active_index", "render_color_index"):
            try:
                setattr(color_attributes, attr_name, index)
            except Exception:
                pass
        break


def find_color_layer(bm, layer_name):
    if not layer_name:
        return None, None, None

    collections = (
        ("POINT", "FLOAT_COLOR", bm.verts.layers.float_color),
        ("POINT", "BYTE_COLOR", bm.verts.layers.color),
        ("CORNER", "FLOAT_COLOR", bm.loops.layers.float_color),
        ("CORNER", "BYTE_COLOR", bm.loops.layers.color),
    )

    for domain, data_type, layer_collection in collections:
        layer = layer_collection.get(layer_name)
        if layer is not None:
            return layer, domain, data_type
    return None, None, None


def resolve_active_mesh(context):
    obj = context.active_object
    if obj is None or obj.type != "MESH":
        return None, None, tr_format("Select a mesh object first.")
    return obj, obj.data, None


def resolve_target_color_attribute(context, prefer_scene_layer=True, fallback_active=True, required_domain=None):
    obj, mesh, error = resolve_active_mesh(context)
    if error:
        return None, error

    layer_name = ""
    color_attr = None
    if prefer_scene_layer:
        layer_value = getattr(context.scene, "ylvc_layer_name", "")
        layer_name = layer_value.strip() if isinstance(layer_value, str) else ""
        color_attr = mesh.color_attributes.get(layer_name) if layer_name else None

    if color_attr is None and fallback_active:
        color_attr = get_active_color_attribute_safe(mesh)
        if color_attr is not None:
            layer_name = color_attr.name

    if color_attr is None:
        return None, tr_format("No active color attribute found.")

    if required_domain is not None and color_attr.domain != required_domain:
        return None, tr_format(
            "{required_domain} color attribute required, found {domain}.",
            required_domain=required_domain,
            domain=color_attr.domain,
        )

    if layer_name:
        try:
            context.scene.ylvc_layer_name = layer_name
        except Exception:
            pass
        set_active_color_attribute(mesh, layer_name)

    return ColorTarget(
        obj=obj,
        mesh=mesh,
        color_attr=color_attr,
        layer_name=color_attr.name,
        domain=color_attr.domain,
        data_type=color_attr.data_type,
    ), None


def resolve_edit_color_layer(context, prefer_scene_layer=True, fallback_active=True, required_domain=None):
    target, error = resolve_target_color_attribute(
        context,
        prefer_scene_layer=prefer_scene_layer,
        fallback_active=fallback_active,
        required_domain=required_domain,
    )
    if error:
        return None, error

    obj = target.obj
    mesh = target.mesh
    if obj.mode != "EDIT":
        return None, tr_format("Switch to Edit Mode to use this tool.")

    try:
        bm = bmesh.from_edit_mesh(mesh)
    except Exception:
        return None, tr_format("Failed to access the edit mesh.")

    layer, domain, data_type = find_color_layer(bm, target.layer_name)
    if layer is None:
        return None, tr_format('Color layer "{layer_name}" was not found in Edit Mode.', layer_name=target.layer_name)

    if required_domain is not None and domain != required_domain:
        return None, tr_format(
            "{required_domain} color attribute required, found {domain}.",
            required_domain=required_domain,
            domain=domain,
        )

    return EditColorTarget(
        obj=obj,
        mesh=mesh,
        bm=bm,
        color_attr=target.color_attr,
        layer_name=target.layer_name,
        domain=domain,
        data_type=data_type,
        layer=layer,
    ), None


def point_colors_to_corner_colors(mesh, point_colors):
    loop_count = len(mesh.loops)
    loop_vert_indices = np.empty(loop_count, dtype=np.int32)
    if loop_count > 0:
        mesh.loops.foreach_get("vertex_index", loop_vert_indices)
    return np.asarray(point_colors, dtype=np.float32).reshape(-1, 4)[loop_vert_indices]


def corner_colors_to_point_colors(mesh, corner_colors):
    loop_count = len(mesh.loops)
    vert_count = len(mesh.vertices)
    if loop_count == 0 or vert_count == 0:
        return np.zeros((vert_count, 4), dtype=np.float32)

    loop_vert_indices = np.empty(loop_count, dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", loop_vert_indices)
    corner_colors = np.asarray(corner_colors, dtype=np.float32).reshape(-1, 4)

    counts = np.bincount(loop_vert_indices, minlength=vert_count).astype(np.float32)
    counts[counts == 0.0] = 1.0
    point_colors = np.empty((vert_count, 4), dtype=np.float32)
    for channel in range(4):
        point_colors[:, channel] = np.bincount(
            loop_vert_indices,
            weights=corner_colors[:, channel],
            minlength=vert_count,
        ) / counts
    return point_colors


def convert_colors_between_domains(mesh, colors, source_domain, target_domain):
    colors = np.asarray(colors, dtype=np.float32).reshape(-1, 4)
    if source_domain == target_domain:
        return colors.copy()
    if source_domain == "POINT" and target_domain == "CORNER":
        return point_colors_to_corner_colors(mesh, colors)
    if source_domain == "CORNER" and target_domain == "POINT":
        return corner_colors_to_point_colors(mesh, colors)
    raise ValueError(f"Unsupported domain conversion: {source_domain} -> {target_domain}")


def create_color_attribute(mesh, name, domain="CORNER", data_type="FLOAT_COLOR", *, replace=False):
    if replace and name in mesh.color_attributes:
        mesh.color_attributes.remove(mesh.color_attributes[name])
    attr = mesh.color_attributes.get(name)
    if attr is None:
        attr = mesh.color_attributes.new(name=name, type=data_type, domain=domain)
    set_active_color_attribute(mesh, attr.name)
    return attr
