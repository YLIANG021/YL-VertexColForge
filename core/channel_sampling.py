# -*- coding: utf-8 -*-
"""Shared source-channel sampling rules for color transfer tools."""

import numpy as np

SOURCE_CHANNEL_INDEX = {
    "R": 0,
    "G": 1,
    "B": 2,
    "A": 3,
}

SOURCE_CHANNELS = ("RGB", "R", "G", "B", "A")

RGB_LUMINANCE = np.array((0.2126, 0.7152, 0.0722), dtype=np.float32)


def normalize_source_key(source_key, default="RGB"):
    return source_key if source_key in SOURCE_CHANNELS else default


def source_channel_index(source_key):
    source_key = normalize_source_key(source_key, default="")
    if source_key not in SOURCE_CHANNEL_INDEX:
        raise KeyError(f"Source channel '{source_key}' does not map to a single component.")
    return SOURCE_CHANNEL_INDEX[source_key]


def sample_scalar_from_colors(colors, source_key, *, rgb_mode="luminance", write_channel=None):
    """Sample a scalar value from RGBA colors using a consistent source rule."""
    colors = np.asarray(colors, dtype=np.float32).reshape(-1, 4)
    source_key = normalize_source_key(source_key)

    if source_key == "RGB":
        if write_channel in SOURCE_CHANNEL_INDEX:
            return np.clip(colors[:, SOURCE_CHANNEL_INDEX[write_channel]], 0.0, 1.0)
        if rgb_mode == "mean":
            return np.clip(np.mean(colors[:, 0:3], axis=1), 0.0, 1.0)
        return np.clip(np.dot(colors[:, 0:3], RGB_LUMINANCE), 0.0, 1.0)

    return np.clip(colors[:, SOURCE_CHANNEL_INDEX[source_key]], 0.0, 1.0)


def sample_scalar_from_image_pixels(sampled_pixels, source_key, *, write_channel=None):
    """Sample texture pixels with existing texture-transfer RGB-to-channel behavior."""
    return sample_scalar_from_colors(
        sampled_pixels,
        source_key,
        rgb_mode="mean",
        write_channel=write_channel,
    )
