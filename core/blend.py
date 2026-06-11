# -*- coding: utf-8 -*-
"""Shared color blend operations for scalar and numpy color data."""

import numpy as np

from .color_channels import (
    channel_indices,
    channel_slice,
    clamp_factor,
    ensure_rgba_sequence,
)

BLEND_MODES = ("REPLACE", "MULTIPLY", "ADD", "SUBTRACT", "OVERLAY")


def normalize_blend_mode(blend_mode, default="REPLACE"):
    return blend_mode if blend_mode in BLEND_MODES else default


def blend_scalar_value(current_value, source_value, blend_mode):
    current_value = clamp_factor(current_value)
    source_value = clamp_factor(source_value)
    blend_mode = normalize_blend_mode(blend_mode)

    if blend_mode == "REPLACE":
        return source_value
    if blend_mode == "MULTIPLY":
        return clamp_factor(current_value * source_value)
    if blend_mode == "ADD":
        return clamp_factor(current_value + source_value)
    if blend_mode == "SUBTRACT":
        return clamp_factor(current_value - source_value)
    if current_value < 0.5:
        return clamp_factor(2.0 * current_value * source_value)
    return clamp_factor(1.0 - 2.0 * (1.0 - current_value) * (1.0 - source_value))


def blend_channel_values(old_color, new_color, channel_key, blend_mode):
    result = ensure_rgba_sequence(old_color)
    source = ensure_rgba_sequence(new_color)
    for index in channel_indices(channel_key):
        result[index] = blend_scalar_value(result[index], source[index], blend_mode)
    return tuple(result)


def blend_color_scalar(current_color, source_color, channel_key, blend_mode):
    return blend_channel_values(current_color, source_color, channel_key, blend_mode)


def blend_colors_np(
    cur_full,
    source_full,
    channel_key,
    blend_mode,
    mask=None,
    *,
    mask_indices=None,
    current_buf=None,
    source_buf=None,
    gradient_buf=None,
    low_mask_buf=None,
):
    """Blend source_full into cur_full in place for selected channels."""
    blend_mode = normalize_blend_mode(blend_mode)
    channels = channel_indices(channel_key)
    resolved_slice = channel_slice(channel_key)
    channel_count = len(channels)

    if mask_indices is None:
        if mask is None:
            mask = slice(None)

        current = cur_full[mask, resolved_slice]
        source = source_full[mask, resolved_slice]

        if blend_mode == "REPLACE":
            result = source
        elif blend_mode == "MULTIPLY":
            result = current * source
        elif blend_mode == "ADD":
            result = np.clip(current + source, 0.0, 1.0)
        elif blend_mode == "SUBTRACT":
            result = np.clip(current - source, 0.0, 1.0)
        else:
            low_mask = current < 0.5
            result = np.empty_like(current)
            result[low_mask] = np.clip(2.0 * current[low_mask] * source[low_mask], 0.0, 1.0)
            result[~low_mask] = np.clip(
                1.0 - 2.0 * (1.0 - current[~low_mask]) * (1.0 - source[~low_mask]),
                0.0,
                1.0,
            )

        cur_full[mask, resolved_slice] = result
        return cur_full

    if mask_indices.size == 0:
        return cur_full

    if source_buf is None and gradient_buf is not None:
        source_buf = gradient_buf

    count = len(mask_indices)
    if current_buf is None or current_buf.shape[0] < count or current_buf.shape[1] < channel_count:
        current_buf = np.empty((count, channel_count), dtype=np.float32)
    if source_buf is None or source_buf.shape[0] < count or source_buf.shape[1] < channel_count:
        source_buf = np.empty((count, channel_count), dtype=np.float32)
    if low_mask_buf is None or low_mask_buf.shape[0] < count or low_mask_buf.shape[1] < channel_count:
        low_mask_buf = np.empty((count, channel_count), dtype=bool)

    current = current_buf[:count, :channel_count]
    source = source_buf[:count, :channel_count]
    low_mask = low_mask_buf[:count, :channel_count]

    for offset, channel in enumerate(channels):
        np.take(cur_full[:, channel], mask_indices, out=current[:, offset])
        np.take(source_full[:, channel], mask_indices, out=source[:, offset])

    if blend_mode == "REPLACE":
        np.copyto(current, source)
    elif blend_mode == "MULTIPLY":
        np.multiply(current, source, out=current)
    elif blend_mode == "ADD":
        np.add(current, source, out=current)
        np.clip(current, 0.0, 1.0, out=current)
    elif blend_mode == "SUBTRACT":
        np.subtract(current, source, out=current)
        np.clip(current, 0.0, 1.0, out=current)
    else:
        np.less(current, 0.5, out=low_mask)
        current[low_mask] = np.clip(2.0 * current[low_mask] * source[low_mask], 0.0, 1.0)
        current[~low_mask] = np.clip(
            1.0 - 2.0 * (1.0 - current[~low_mask]) * (1.0 - source[~low_mask]),
            0.0,
            1.0,
        )

    for offset, channel in enumerate(channels):
        channel_view = cur_full[:, channel]
        channel_view[mask_indices] = current[:, offset]
    return cur_full


def apply_channel_result_np(cur_full, result_full, channel_key, mask=None):
    return blend_colors_np(cur_full, result_full, channel_key, "REPLACE", mask)
