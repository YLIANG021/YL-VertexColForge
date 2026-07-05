# -*- coding: utf-8 -*-
"""Shared RGBA channel rules used by all vertex color tools."""

import numpy as np

CHANNEL_COMPONENTS = {
    "R": (0,),
    "G": (1,),
    "B": (2,),
    "A": (3,),
    "RGB": (0, 1, 2),
}

CHANNEL_LABELS = {key: key for key in CHANNEL_COMPONENTS}

PREVIEW_CHANNEL_INDEX = {
    "RGB": 4,
    "R": 0,
    "G": 2,
    "B": 3,
    "A": 1,
}


def normalize_channel_key(channel_key, default="RGB"):
    return channel_key if channel_key in CHANNEL_COMPONENTS else default


def channel_indices(channel_key):
    return CHANNEL_COMPONENTS[normalize_channel_key(channel_key)]


def channel_slice(channel_key):
    channel_key = normalize_channel_key(channel_key)
    if channel_key == "RGB":
        return slice(0, 3)
    if channel_key == "R":
        return slice(0, 1)
    if channel_key == "G":
        return slice(1, 2)
    if channel_key == "B":
        return slice(2, 3)
    return slice(3, 4)


def clamp_factor(value):
    return max(0.0, min(1.0, float(value)))


def ensure_rgba_sequence(color_value):
    rgba = list(color_value[:4])
    while len(rgba) < 4:
        rgba.append(1.0 if len(rgba) == 3 else 0.0)
    return rgba


def apply_channel_value(color_value, channel_key, value):
    rgba = ensure_rgba_sequence(color_value)
    indices = channel_indices(channel_key)
    if isinstance(value, (list, tuple, np.ndarray)):
        source = ensure_rgba_sequence(value)
        for index in indices:
            rgba[index] = clamp_factor(source[index])
    else:
        channel_value = clamp_factor(value)
        for index in indices:
            rgba[index] = channel_value
    return tuple(rgba)


def sample_channel_value(color_value, channel_key):
    rgba = ensure_rgba_sequence(color_value)
    indices = channel_indices(channel_key)
    return sum(rgba[index] for index in indices) / len(indices)


def copy_channel_values(target_color, source_color, channel_key):
    target = ensure_rgba_sequence(target_color)
    source = ensure_rgba_sequence(source_color)
    for index in channel_indices(channel_key):
        target[index] = clamp_factor(source[index])
    return tuple(target)


def normalize_write_value(value, channel_key):
    """Return values aligned with the requested write channel indices."""
    indices = channel_indices(channel_key)
    if isinstance(value, (list, tuple, np.ndarray)):
        rgba = ensure_rgba_sequence(value)
        return tuple(clamp_factor(rgba[index]) for index in indices)
    scalar = clamp_factor(value)
    return tuple(scalar for _index in indices)
