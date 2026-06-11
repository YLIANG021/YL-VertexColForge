# -*- coding: utf-8 -*-
"""Interactive local paint tools."""

from . import ops_brush, ops_eyedropper

CLASSES = (
    *ops_brush.CLASSES,
    *ops_eyedropper.CLASSES,
)
