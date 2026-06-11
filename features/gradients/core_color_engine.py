# -*- coding: utf-8 -*-
import math

import bpy
import numpy as np

from ...core.blend import blend_colors_np

RAMP_MATERIAL_NAME = "YLVC_Internal_Ramp_Data"
RAMP_NODE_NAME = "YLVC_ColorRamp"
ADJUST_RAMP_MATERIAL_NAME = "YLVC_Adjust_Ramp_Data"
ADJUST_RAMP_NODE_NAME = "YLVC_Adjust_ColorRamp"
LIGHT_RAMP_MATERIAL_NAME = "YLVC_Light_Ramp_Data"
LIGHT_RAMP_NODE_NAME = "YLVC_Light_ColorRamp"


def linear_to_srgb(val):
    """Convert a linear color component to sRGB for viewport drawing."""
    if val <= 0.0031308:
        return 12.92 * val
    return 1.055 * math.pow(max(val, 0.0), 1.0 / 2.4) - 0.055


def build_ramp_lut(ramp, lut_size=512):
    """Bake a Blender ColorRamp into a float32 LUT."""
    lut = np.empty((lut_size, 4), dtype=np.float32)
    for index in range(lut_size):
        color = ramp.evaluate(index / (lut_size - 1.0))
        lut[index] = (color[0], color[1], color[2], color[3])
    return lut


def sample_lut_scalar(lut, t):
    """Sample one RGBA value from a LUT."""
    lut_size = len(lut)
    t = max(0.0, min(1.0, t))
    f_idx = t * (lut_size - 1)
    idx0 = int(math.floor(f_idx))
    idx1 = min(idx0 + 1, lut_size - 1)
    weight = f_idx - idx0

    c0 = lut[idx0]
    c1 = lut[idx1]
    return (
        c0[0] * (1.0 - weight) + c1[0] * weight,
        c0[1] * (1.0 - weight) + c1[1] * weight,
        c0[2] * (1.0 - weight) + c1[2] * weight,
        c0[3] * (1.0 - weight) + c1[3] * weight,
    )


def sample_lut_array(lut, t_arr):
    """Sample the LUT for an array of factors."""
    out = np.empty((len(t_arr), 4), dtype=np.float32)
    return sample_lut_array_out(lut, t_arr, out)


def sample_lut_array_out(
    lut,
    t_arr,
    out,
    *,
    work_t=None,
    idx0_buf=None,
    idx1_buf=None,
    sample0_buf=None,
    sample1_buf=None,
    inv_weight_buf=None,
):
    """Sample the LUT into a preallocated output array."""
    count = len(t_arr)
    if count == 0:
        return out

    lut_size = len(lut)
    if work_t is None or len(work_t) < count:
        work_t = np.empty(count, dtype=np.float32)
    if idx0_buf is None or len(idx0_buf) < count:
        idx0_buf = np.empty(count, dtype=np.int32)
    if idx1_buf is None or len(idx1_buf) < count:
        idx1_buf = np.empty(count, dtype=np.int32)
    if sample0_buf is None or len(sample0_buf) < count:
        sample0_buf = np.empty((count, 4), dtype=np.float32)
    if sample1_buf is None or len(sample1_buf) < count:
        sample1_buf = np.empty((count, 4), dtype=np.float32)
    if inv_weight_buf is None or len(inv_weight_buf) < count:
        inv_weight_buf = np.empty(count, dtype=np.float32)

    work_view = work_t[:count]
    idx0_view = idx0_buf[:count]
    idx1_view = idx1_buf[:count]
    sample0_view = sample0_buf[:count]
    sample1_view = sample1_buf[:count]
    inv_weight_view = inv_weight_buf[:count]
    out_view = out[:count]

    np.clip(t_arr, 0.0, 1.0, out=work_view)
    np.multiply(work_view, lut_size - 1, out=work_view)
    idx0_view[:] = work_view
    np.add(idx0_view, 1, out=idx1_view)
    np.minimum(idx1_view, lut_size - 1, out=idx1_view)
    np.subtract(work_view, idx0_view, out=work_view)

    np.take(lut, idx0_view, axis=0, out=sample0_view)
    np.take(lut, idx1_view, axis=0, out=sample1_view)

    np.subtract(1.0, work_view, out=inv_weight_view)
    np.multiply(sample0_view, inv_weight_view[:, None], out=sample0_view)
    np.multiply(sample1_view, work_view[:, None], out=sample1_view)
    np.add(sample0_view, sample1_view, out=out_view)
    np.clip(out_view, 0.0, 1.0, out=out_view)
    return out


def _get_materials_collection():
    data = getattr(bpy, "data", None)
    return getattr(data, "materials", None)


def get_ramp_material(material_name=RAMP_MATERIAL_NAME):
    materials = _get_materials_collection()
    if materials is None:
        return None
    return materials.get(material_name)


def find_ramp_node(material=None, material_name=RAMP_MATERIAL_NAME, node_name=RAMP_NODE_NAME):
    material = material or get_ramp_material(material_name)
    if material is None or material.node_tree is None:
        return None

    nodes = material.node_tree.nodes
    named = nodes.get(node_name)
    if named is not None and named.bl_idname == "ShaderNodeValToRGB":
        return named

    for node in nodes:
        if node.bl_idname == "ShaderNodeValToRGB" and (
            node.name == node_name or node.label == node_name
        ):
            return node

    for node in nodes:
        if node.bl_idname == "ShaderNodeValToRGB":
            return node
    return None


def cleanup_ramp_nodes(material=None, material_name=RAMP_MATERIAL_NAME, node_name=RAMP_NODE_NAME):
    """Normalize the internal ramp node and remove managed duplicates."""
    material = material or get_ramp_material(material_name)
    if material is None or material.node_tree is None:
        return None

    nodes = material.node_tree.nodes
    primary = find_ramp_node(material, material_name=material_name, node_name=node_name)
    if primary is None:
        return None

    primary.name = node_name
    primary.label = node_name

    duplicates = []
    for node in nodes:
        if node == primary or node.bl_idname != "ShaderNodeValToRGB":
            continue
        if node.name == node_name or node.label == node_name:
            duplicates.append(node)

    for node in duplicates:
        nodes.remove(node)

    return primary


def ensure_ramp_node(material_name=RAMP_MATERIAL_NAME, node_name=RAMP_NODE_NAME):
    materials = _get_materials_collection()
    if materials is None:
        return None

    material = get_ramp_material(material_name)
    if material is None:
        material = materials.new(material_name)

    material.use_fake_user = True
    if material.node_tree is None or not material.use_nodes:
        material.use_nodes = True

    node = find_ramp_node(material, material_name=material_name, node_name=node_name)
    if node is None:
        node = material.node_tree.nodes.new("ShaderNodeValToRGB")

    node.name = node_name
    node.label = node_name
    node.location = (0.0, 0.0)
    cleanup_ramp_nodes(material, material_name=material_name, node_name=node_name)
    return node


def get_or_create_ramp_node():
    return ensure_ramp_node()


def ensure_adjust_ramp_node():
    return ensure_ramp_node(
        material_name=ADJUST_RAMP_MATERIAL_NAME,
        node_name=ADJUST_RAMP_NODE_NAME,
    )


def find_adjust_ramp_node():
    return find_ramp_node(
        material_name=ADJUST_RAMP_MATERIAL_NAME,
        node_name=ADJUST_RAMP_NODE_NAME,
    )


def ensure_light_ramp_node():
    return ensure_ramp_node(
        material_name=LIGHT_RAMP_MATERIAL_NAME,
        node_name=LIGHT_RAMP_NODE_NAME,
    )


def find_light_ramp_node():
    return find_ramp_node(
        material_name=LIGHT_RAMP_MATERIAL_NAME,
        node_name=LIGHT_RAMP_NODE_NAME,
    )


def serialize_ramp_data(ramp):
    if ramp is None:
        return None

    return {
        "color_mode": getattr(ramp, "color_mode", "RGB"),
        "interpolation": getattr(ramp, "interpolation", "LINEAR"),
        "hue_interpolation": getattr(ramp, "hue_interpolation", "NEAR"),
        "elements": [
            {
                "position": float(element.position),
                "color": tuple(float(component) for component in element.color[:4]),
            }
            for element in ramp.elements
        ],
    }


def restore_ramp_data(ramp, data):
    if ramp is None or not data:
        return

    elements = ramp.elements
    target_count = max(2, len(data.get("elements", [])))

    while len(elements) > target_count:
        elements.remove(elements[-1])
    while len(elements) < target_count:
        elements.new(1.0)

    try:
        ramp.color_mode = data.get("color_mode", "RGB")
    except Exception:
        pass
    try:
        ramp.interpolation = data.get("interpolation", "LINEAR")
    except Exception:
        pass
    try:
        ramp.hue_interpolation = data.get("hue_interpolation", "NEAR")
    except Exception:
        pass

    for index, element_data in enumerate(data.get("elements", ())):
        element = elements[index]
        try:
            element.position = float(element_data.get("position", element.position))
        except Exception:
            pass
        try:
            element.color = tuple(float(component) for component in element_data.get("color", element.color[:4]))
        except Exception:
            pass


def reset_ramp_to_default(ramp):
    if ramp is None:
        return

    restore_ramp_data(
        ramp,
        {
            "color_mode": "RGB",
            "interpolation": "LINEAR",
            "hue_interpolation": "NEAR",
            "elements": (
                {"position": 0.0, "color": (0.0, 0.0, 0.0, 1.0)},
                {"position": 1.0, "color": (1.0, 1.0, 1.0, 1.0)},
            ),
        },
    )


def cleanup_ramp_material(remove_material=False, material_name=RAMP_MATERIAL_NAME, node_name=RAMP_NODE_NAME):
    """Cleanup helper for the internal ramp datablock."""
    material = get_ramp_material(material_name)
    if material is None:
        return False

    cleanup_ramp_nodes(material, material_name=material_name, node_name=node_name)
    if remove_material:
        materials = _get_materials_collection()
        if materials is not None:
            materials.remove(material)
    return True
