# -*- coding: utf-8 -*-
"""Color adjustment and blur tools."""

from . import ops_color_adjust, ops_smooth_blur

CLASSES = (
    *ops_color_adjust.classes,
    *ops_smooth_blur.classes,
)
