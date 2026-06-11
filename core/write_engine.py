# -*- coding: utf-8 -*-
"""Unified color write helpers for object and edit mode tools."""

from dataclasses import dataclass

import bmesh
import numpy as np

from .blend import blend_colors_np, normalize_blend_mode
from .color_attribute import (
    read_color_attribute_colors,
    resolve_edit_color_layer,
    resolve_target_color_attribute,
    write_color_attribute_colors,
)
from .color_channels import channel_indices, normalize_write_value
from .selection_scope import resolve_selection_scope
from ..i18n import tr, tr_format


@dataclass
class WriteResult:
    success: bool
    message: str
    obj: object = None
    mesh: object = None
    layer_name: str = ""
    domain: str = ""
    affected_count: int = 0

    def as_tuple(self):
        return self.success, self.message


def _target_label(domain):
    return tr("vertices") if domain == "POINT" else tr("corners")


def read_edit_element_colors(elements, layer):
    if not elements:
        return np.empty((0, 4), dtype=np.float32)
    return np.array([tuple(float(component) for component in elem[layer][:4]) for elem in elements], dtype=np.float32)


def write_edit_element_colors(elements, layer, colors):
    for elem, color in zip(elements, colors):
        elem[layer] = tuple(float(component) for component in color)


def build_source_color_array(count, value, channel_key, base_colors=None):
    if base_colors is None:
        source = np.zeros((count, 4), dtype=np.float32)
        source[:, 3] = 1.0
    else:
        source = np.asarray(base_colors, dtype=np.float32).reshape(-1, 4).copy()
        if len(source) != count:
            raise ValueError("Base color count does not match target count.")

    values = normalize_write_value(value, channel_key)
    for offset, channel in enumerate(channel_indices(channel_key)):
        source[:, channel] = values[offset]
    return source


def build_source_color_array_from_values(base_colors, values, channel_key):
    """Build a full RGBA source array from scalar, RGB, or RGBA values."""
    base_colors = np.asarray(base_colors, dtype=np.float32).reshape(-1, 4)
    source = base_colors.copy()
    values = np.asarray(values, dtype=np.float32)
    count = len(base_colors)

    if values.ndim == 0:
        values = np.full(count, float(values), dtype=np.float32)
    elif values.shape[0] != count:
        raise ValueError("Source value count does not match target color count.")

    channels = channel_indices(channel_key)
    if values.ndim == 1:
        for channel in channels:
            source[:, channel] = values
    else:
        value_width = values.shape[1]
        if channel_key == "RGB":
            if value_width >= 3:
                source[:, 0:3] = values[:, 0:3]
            else:
                source[:, 0:3] = values[:, 0:1]
        elif value_width >= 4:
            for channel in channels:
                source[:, channel] = values[:, channel]
        elif value_width >= len(channels):
            for offset, channel in enumerate(channels):
                source[:, channel] = values[:, offset]
        else:
            for channel in channels:
                source[:, channel] = values[:, 0]

    np.clip(source, 0.0, 1.0, out=source)
    return source


def _blend_with_strength(colors, source, channel_key, blend_mode, strength, mask=None):
    strength = max(0.0, min(1.0, float(strength)))
    if strength <= 0.0:
        return colors

    blend_mode = normalize_blend_mode(blend_mode)
    if strength >= 1.0 and blend_mode == "REPLACE":
        blend_colors_np(colors, source, channel_key, blend_mode, mask)
        return colors

    original = colors.copy()
    blend_colors_np(colors, source, channel_key, blend_mode, mask)
    if strength < 1.0:
        colors[:] = original + (colors - original) * strength
    return colors


def blend_source_values_into_colors(colors, source_values, channel_key, blend_mode="REPLACE", mask=None, strength=1.0):
    """Blend source values into an existing RGBA array in place."""
    colors = np.asarray(colors, dtype=np.float32).reshape(-1, 4)
    values = np.asarray(source_values, dtype=np.float32)
    if mask is not None and not isinstance(mask, slice) and values.ndim > 0 and values.shape[0] != len(colors):
        mask_array = np.asarray(mask)
        mask_count = int(np.count_nonzero(mask_array)) if mask_array.dtype == bool else int(mask_array.size)
        if values.shape[0] != mask_count:
            raise ValueError("Source value count does not match target color count or mask count.")
        if values.ndim == 1:
            full_values = np.zeros(len(colors), dtype=np.float32)
        else:
            full_values = np.zeros((len(colors), values.shape[1]), dtype=np.float32)
        full_values[mask_array] = values
        values = full_values
    source = build_source_color_array_from_values(colors, values, channel_key)
    _blend_with_strength(colors, source, channel_key, blend_mode, strength, mask)
    np.clip(colors, 0.0, 1.0, out=colors)
    return colors


def write_color_array_to_attribute(color_attr, colors, *, mesh=None, update_mesh=True):
    write_color_attribute_colors(color_attr, colors)
    if update_mesh and mesh is not None:
        mesh.update()


def write_blended_color_array_to_attribute(
    color_attr,
    base_colors,
    source_colors,
    *,
    channel_key="RGB",
    blend_mode="REPLACE",
    mask=None,
    strength=1.0,
    mesh=None,
    update_mesh=True,
):
    """Blend an RGBA source array into base colors and write the result."""
    colors = np.asarray(base_colors, dtype=np.float32).reshape(-1, 4).copy()
    blend_source_values_into_colors(colors, source_colors, channel_key, blend_mode, mask, strength)
    write_color_array_to_attribute(color_attr, colors, mesh=mesh, update_mesh=update_mesh)
    return colors


def restore_color_array_to_attribute(color_attr, colors, *, mesh=None, update_mesh=True):
    write_color_array_to_attribute(color_attr, colors, mesh=mesh, update_mesh=update_mesh)


def write_source_values_to_color_attribute_result(
    context,
    source_values,
    *,
    channel_key="RGB",
    blend_mode="REPLACE",
    strength=1.0,
    target=None,
    mask=None,
):
    target = target or resolve_target_color_attribute(context)[0]
    if target is None:
        return WriteResult(False, tr("No active color attribute found."))

    attribute = target.color_attr
    if mask is None:
        mask = resolve_selection_scope(context, attribute).data_mask
    if not np.any(mask):
        return WriteResult(
            True,
            tr_format("Wrote {count} {target_label} on channel {channel_key}.", count=0, target_label=_target_label(target.domain), channel_key=channel_key),
            obj=target.obj,
            mesh=target.mesh,
            layer_name=target.layer_name,
            domain=target.domain,
        )

    colors = read_color_attribute_colors(target.mesh, attribute)
    blend_source_values_into_colors(colors, source_values, channel_key, blend_mode, mask, strength)
    write_color_array_to_attribute(attribute, colors, mesh=target.mesh)
    affected = int(np.sum(mask))
    return WriteResult(
        True,
        tr_format("Wrote {count} {target_label} on channel {channel_key}.", count=affected, target_label=_target_label(target.domain), channel_key=channel_key),
        obj=target.obj,
        mesh=target.mesh,
        layer_name=target.layer_name,
        domain=target.domain,
        affected_count=affected,
    )


def write_value_to_color_attribute_result(context, value, *, channel_key="RGB", blend_mode="REPLACE", strength=1.0, target=None):
    target = target or resolve_target_color_attribute(context)[0]
    if target is None:
        return WriteResult(False, tr("No active color attribute found."))

    attribute = target.color_attr
    scope = resolve_selection_scope(context, attribute)
    mask = scope.data_mask
    if not np.any(mask):
        return WriteResult(
            True,
            tr_format("Wrote {count} {target_label} on channel {channel_key}.", count=0, target_label=_target_label(target.domain), channel_key=channel_key),
            obj=target.obj,
            mesh=target.mesh,
            layer_name=target.layer_name,
            domain=target.domain,
        )

    count = len(attribute.data)
    colors = np.empty(count * 4, dtype=np.float32)
    attribute.data.foreach_get("color", colors)
    colors.shape = (-1, 4)

    source = build_source_color_array(count, value, channel_key, base_colors=colors)
    _blend_with_strength(colors, source, channel_key, blend_mode, strength, mask)
    write_color_attribute_colors(attribute, colors)
    target.mesh.update()
    affected = int(np.sum(mask))
    return WriteResult(
        True,
        tr_format("Wrote {count} {target_label} on channel {channel_key}.", count=affected, target_label=_target_label(target.domain), channel_key=channel_key),
        obj=target.obj,
        mesh=target.mesh,
        layer_name=target.layer_name,
        domain=target.domain,
        affected_count=affected,
    )


def write_value_to_color_attribute(context, value, *, channel_key="RGB", blend_mode="REPLACE", strength=1.0, target=None):
    return write_value_to_color_attribute_result(
        context,
        value,
        channel_key=channel_key,
        blend_mode=blend_mode,
        strength=strength,
        target=target,
    ).as_tuple()


def write_value_to_edit_color_layer_result(context, value, *, channel_key="RGB", blend_mode="REPLACE", strength=1.0, target=None):
    target = target or resolve_edit_color_layer(context)[0]
    if target is None:
        return WriteResult(False, tr("No active edit color layer found."))

    scope = resolve_selection_scope(context, target.color_attr)
    mask = scope.data_mask
    if not np.any(mask):
        return WriteResult(
            True,
            tr_format("Wrote {count} {target_label} on channel {channel_key}.", count=0, target_label=_target_label(target.domain), channel_key=channel_key),
            obj=target.obj,
            mesh=target.mesh,
            layer_name=target.layer_name,
            domain=target.domain,
        )

    if target.domain == "POINT":
        target.bm.verts.ensure_lookup_table()
        indices = np.flatnonzero(mask)
        elements = [target.bm.verts[index] for index in indices.tolist()]
    else:
        elements = []
        for face in target.bm.faces:
            for loop in face.loops:
                if loop.index < mask.size and mask[loop.index]:
                    elements.append(loop)

    colors = read_edit_element_colors(elements, target.layer)
    if colors.size == 0:
        return WriteResult(
            True,
            tr_format("Wrote {count} {target_label} on channel {channel_key}.", count=0, target_label=_target_label(target.domain), channel_key=channel_key),
            obj=target.obj,
            mesh=target.mesh,
            layer_name=target.layer_name,
            domain=target.domain,
        )

    source = build_source_color_array(len(colors), value, channel_key, base_colors=colors)
    _blend_with_strength(colors, source, channel_key, blend_mode, strength, None)
    write_edit_element_colors(elements, target.layer, colors)
    bmesh.update_edit_mesh(target.mesh)
    return WriteResult(
        True,
        tr_format("Wrote {count} {target_label} on channel {channel_key}.", count=len(elements), target_label=_target_label(target.domain), channel_key=channel_key),
        obj=target.obj,
        mesh=target.mesh,
        layer_name=target.layer_name,
        domain=target.domain,
        affected_count=len(elements),
    )


def write_value_to_edit_color_layer(context, value, *, channel_key="RGB", blend_mode="REPLACE", strength=1.0, target=None):
    return write_value_to_edit_color_layer_result(
        context,
        value,
        channel_key=channel_key,
        blend_mode=blend_mode,
        strength=strength,
        target=target,
    ).as_tuple()


def write_value_result(context, value, *, channel_key="RGB", blend_mode="REPLACE", strength=1.0):
    obj = context.active_object
    if obj is None or obj.type != "MESH":
        return WriteResult(False, tr("Select a mesh object first."))
    if obj.mode == "EDIT":
        return write_value_to_edit_color_layer_result(context, value, channel_key=channel_key, blend_mode=blend_mode, strength=strength)
    return write_value_to_color_attribute_result(context, value, channel_key=channel_key, blend_mode=blend_mode, strength=strength)


def write_value(context, value, *, channel_key="RGB", blend_mode="REPLACE", strength=1.0):
    return write_value_result(context, value, channel_key=channel_key, blend_mode=blend_mode, strength=strength).as_tuple()
