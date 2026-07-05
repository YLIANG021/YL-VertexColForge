# -*- coding: utf-8 -*-
"""Unified color write helpers for object and edit mode tools."""

from dataclasses import dataclass

import numpy as np

from .blend import blend_colors_np, normalize_blend_mode
from .color_attribute import (
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
    mesh_updated: bool = False

    def as_tuple(self):
        return self.success, self.message


def _target_label(domain):
    return tr("vertices") if domain == "POINT" else tr("corners")


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


def _mask_to_indices(mask, count):
    if mask is None:
        return None
    if isinstance(mask, slice):
        start, stop, step = mask.indices(count)
        if start == 0 and stop == count and step == 1:
            return None
        return np.arange(start, stop, step, dtype=np.int32)

    mask_array = np.asarray(mask)
    if mask_array.dtype == bool:
        return np.flatnonzero(mask_array).astype(np.int32, copy=False)
    return mask_array.astype(np.int32, copy=False).reshape(-1)


def _values_for_targets(values, target_indices, full_count):
    values = np.asarray(values, dtype=np.float32)
    if values.ndim == 0 or target_indices is None:
        return values
    if values.shape[0] == len(target_indices):
        return values
    if values.shape[0] == full_count:
        return values[target_indices]
    return values


def _assign_values_to_channels(colors, values, channel_key, target_indices=None):
    channels = channel_indices(channel_key)
    values = np.asarray(values, dtype=np.float32)

    def assign_channel(channel, channel_values):
        clipped = np.clip(channel_values, 0.0, 1.0)
        if target_indices is None:
            colors[:, channel] = clipped
        else:
            colors[:, channel][target_indices] = clipped

    if values.ndim == 0:
        for channel in channels:
            assign_channel(channel, float(values))
        return colors

    if values.ndim == 1:
        for channel in channels:
            assign_channel(channel, values)
        return colors

    value_width = values.shape[1]
    if channel_key == "RGB":
        if value_width >= 3:
            if target_indices is None:
                colors[:, 0:3] = np.clip(values[:, 0:3], 0.0, 1.0)
            else:
                colors[target_indices, 0:3] = np.clip(values[:, 0:3], 0.0, 1.0)
        else:
            gray = values[:, 0]
            for channel in channels:
                assign_channel(channel, gray)
    elif value_width >= 4:
        for channel in channels:
            assign_channel(channel, values[:, channel])
    elif value_width >= len(channels):
        for offset, channel in enumerate(channels):
            assign_channel(channel, values[:, offset])
    else:
        for channel in channels:
            assign_channel(channel, values[:, 0])
    return colors


def blend_source_values_into_colors(colors, source_values, channel_key, blend_mode="REPLACE", mask=None, strength=1.0):
    """Blend source values into an existing RGBA array in place."""
    colors = np.asarray(colors, dtype=np.float32).reshape(-1, 4)
    values = np.asarray(source_values, dtype=np.float32)
    count = len(colors)
    target_indices = _mask_to_indices(mask, count)
    target_count = count if target_indices is None else len(target_indices)

    if values.ndim > 0 and values.shape[0] not in {count, target_count}:
        raise ValueError("Source value count does not match target color count or mask count.")

    strength = max(0.0, min(1.0, float(strength)))
    blend_mode = normalize_blend_mode(blend_mode)
    if strength <= 0.0:
        return colors

    if blend_mode == "REPLACE":
        target_values = _values_for_targets(values, target_indices, count)
        if strength >= 1.0:
            _assign_values_to_channels(colors, target_values, channel_key, target_indices)
            return colors

        original = colors.copy() if target_indices is None else colors[target_indices].copy()
        _assign_values_to_channels(colors, target_values, channel_key, target_indices)
        if target_indices is None:
            colors[:] = original + (colors - original) * strength
        else:
            colors[target_indices] = original + (colors[target_indices] - original) * strength
        np.clip(colors, 0.0, 1.0, out=colors)
        return colors

    if target_indices is not None and values.ndim > 0 and values.shape[0] == target_count:
        base_colors = colors[target_indices]
        source = build_source_color_array_from_values(base_colors, values, channel_key)
        original = None
        if strength < 1.0:
            original = base_colors[:, channel_indices(channel_key)].copy()
        blend_colors_np(colors, source, channel_key, blend_mode, mask_indices=target_indices, source_is_compact=True)
        if strength < 1.0:
            for offset, channel in enumerate(channel_indices(channel_key)):
                channel_view = colors[:, channel]
                blended = channel_view[target_indices]
                channel_view[target_indices] = original[:, offset] + (blended - original[:, offset]) * strength
        np.clip(colors, 0.0, 1.0, out=colors)
        return colors

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


def write_value_result(context, value, *, channel_key="RGB", blend_mode="REPLACE", strength=1.0):
    obj = context.active_object
    if obj is None or obj.type != "MESH":
        return WriteResult(False, tr("Select a mesh object first."))

    target = resolve_target_color_attribute(context)[0]
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
        mesh_updated=True,
        affected_count=affected,
    )
