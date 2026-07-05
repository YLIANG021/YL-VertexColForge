# -*- coding: utf-8 -*-
"""Color attribute lookup, conversion, and raw array IO helpers."""

from dataclasses import dataclass

import bpy
import numpy as np

from ..i18n import tr_format
from .mesh_topology import loop_vertex_indices

INTERNAL_PREVIEW_ATTRIBUTE_NAME = "__YLVC_PREVIEW__"
SELECTED_LAYER_STATE_KEY = "ylvc_selected_layer_name"


@dataclass
class ColorTarget:
    obj: bpy.types.Object
    mesh: bpy.types.Mesh
    color_attr: object
    layer_name: str
    domain: str
    data_type: str


def color_data_count(mesh, color_attr):
    if color_attr is None:
        return 0
    try:
        return len(color_attr.data)
    except Exception:
        pass
    if color_attr.domain == "POINT":
        return len(mesh.vertices)
    if color_attr.domain == "CORNER":
        return len(mesh.loops)
    return 0


def expected_color_data_count(mesh, color_attr):
    if color_attr is None:
        return 0
    if mesh is None:
        return color_data_count(mesh, color_attr)
    if color_attr.domain == "POINT":
        return len(mesh.vertices)
    if color_attr.domain == "CORNER":
        return len(mesh.loops)
    return color_data_count(mesh, color_attr)


def color_attribute_data_matches_mesh(mesh, color_attr):
    actual_count = color_data_count(mesh, color_attr)
    expected_count = expected_color_data_count(mesh, color_attr)
    return actual_count == expected_count


def refresh_color_attribute_reference(mesh, color_attr, *, allow_internal=False):
    if mesh is None or color_attr is None:
        return None
    name = getattr(color_attr, "name", "")
    refreshed = get_color_attribute_by_name(mesh, name, allow_internal=allow_internal)
    if refreshed is None:
        return None
    if not color_attribute_data_matches_mesh(mesh, refreshed):
        return None
    return refreshed


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


def is_internal_color_attribute_name(name):
    return name == INTERNAL_PREVIEW_ATTRIBUTE_NAME


def get_scene_selected_color_attribute_name(scene):
    if scene is None:
        return ""
    try:
        value = scene.get(SELECTED_LAYER_STATE_KEY, "")
    except Exception:
        return ""
    return value if isinstance(value, str) else ""


def set_scene_selected_color_attribute_name(scene, layer_name):
    if scene is None:
        return
    try:
        if layer_name:
            scene[SELECTED_LAYER_STATE_KEY] = str(layer_name)
        elif SELECTED_LAYER_STATE_KEY in scene:
            del scene[SELECTED_LAYER_STATE_KEY]
    except Exception:
        pass


def get_color_attribute_by_name(mesh, layer_name, *, allow_internal=False):
    color_attributes = getattr(mesh, "color_attributes", None)
    if not color_attributes or not layer_name:
        return None
    if not allow_internal and is_internal_color_attribute_name(layer_name):
        return None
    try:
        attr = color_attributes.get(layer_name)
    except Exception:
        attr = None
    if attr is None:
        return None
    if not allow_internal and is_internal_color_attribute_name(getattr(attr, "name", "")):
        return None
    return attr


def user_color_attributes(mesh):
    color_attributes = getattr(mesh, "color_attributes", None)
    if not color_attributes:
        return []
    return [
        attr
        for attr in color_attributes
        if not is_internal_color_attribute_name(getattr(attr, "name", ""))
    ]


def get_active_color_attribute_safe(mesh, *, allow_internal=False):
    color_attributes = getattr(mesh, "color_attributes", None)
    if not color_attributes or len(color_attributes) == 0:
        return None

    for attr_name in ("active_color", "active"):
        try:
            active_attr = getattr(color_attributes, attr_name)
            if active_attr is not None and (
                allow_internal or not is_internal_color_attribute_name(getattr(active_attr, "name", ""))
            ):
                return active_attr
        except Exception:
            pass

    try:
        idx = color_attributes.active_color_index
        if 0 <= idx < len(color_attributes):
            attr = color_attributes[idx]
            if allow_internal or not is_internal_color_attribute_name(getattr(attr, "name", "")):
                return attr
    except Exception:
        pass

    if not allow_internal:
        user_attrs = user_color_attributes(mesh)
        if user_attrs:
            return user_attrs[0]

    if allow_internal:
        try:
            return color_attributes[0]
        except Exception:
            pass

    return None


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
        for attr_name in ("active_color_index", "active_index"):
            try:
                setattr(color_attributes, attr_name, index)
            except Exception:
                pass
        break


def resolve_active_mesh(context):
    obj = context.active_object
    if obj is None or obj.type != "MESH":
        return None, None, tr_format("Select a mesh object first.")
    return obj, obj.data, None


def resolve_target_color_attribute(context, prefer_scene_layer=True, fallback_active=True, required_domain=None, activate=True):
    obj, mesh, error = resolve_active_mesh(context)
    if error:
        return None, error
    if getattr(obj, "mode", "OBJECT") != "OBJECT":
        try:
            context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:
            pass

    layer_name = ""
    color_attr = None
    if prefer_scene_layer:
        layer_name = get_scene_selected_color_attribute_name(context.scene).strip()
        color_attr = get_color_attribute_by_name(mesh, layer_name) if layer_name else None

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
            set_scene_selected_color_attribute_name(context.scene, layer_name)
        except Exception:
            pass
        if activate:
            set_active_color_attribute(mesh, layer_name)

    return ColorTarget(
        obj=obj,
        mesh=mesh,
        color_attr=color_attr,
        layer_name=color_attr.name,
        domain=color_attr.domain,
        data_type=color_attr.data_type,
    ), None


def point_colors_to_corner_colors(mesh, point_colors):
    return np.asarray(point_colors, dtype=np.float32).reshape(-1, 4)[loop_vertex_indices(mesh)]


def corner_colors_to_point_colors(mesh, corner_colors):
    loop_count = len(mesh.loops)
    vert_count = len(mesh.vertices)
    if loop_count == 0 or vert_count == 0:
        return np.zeros((vert_count, 4), dtype=np.float32)

    loop_vert_indices = loop_vertex_indices(mesh)
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
