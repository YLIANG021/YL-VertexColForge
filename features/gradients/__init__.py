# -*- coding: utf-8 -*-
"""Gradient ramp engines, overlays, operators, and panels."""

from . import core_color_engine, core_overlay, ops_gradient_3d, ops_gradient_uv, ui_panels

OPERATOR_CLASSES = (
    *ops_gradient_3d.CLASSES,
    *ops_gradient_uv.CLASSES,
)

UI_CLASSES = (
    *ui_panels.CLASSES,
)

CLASSES = (
    *OPERATOR_CLASSES,
    *UI_CLASSES,
)
