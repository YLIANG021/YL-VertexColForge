# -*- coding: utf-8 -*-
"""Compatibility exports for context, attribute, and selection helpers.

New code should import from the focused modules directly:
color_attribute.py, selection_scope.py, and mode_session.py.
"""

from .color_attribute import (
    ColorTarget,
    EditColorTarget,
    resolve_active_mesh,
    resolve_edit_color_layer,
    resolve_target_color_attribute,
)
from .selection_scope import (
    SelectionScope,
    resolve_component_selection_masks_for_object,
    resolve_loop_auto_mask_for_object,
    resolve_polygon_auto_mask_for_object,
    resolve_selection_scope,
    resolve_vertex_auto_mask_for_object,
    resolve_vertex_selection_mask_for_object,
)

__all__ = (
    "ColorTarget",
    "EditColorTarget",
    "SelectionScope",
    "resolve_active_mesh",
    "resolve_component_selection_masks_for_object",
    "resolve_edit_color_layer",
    "resolve_loop_auto_mask_for_object",
    "resolve_polygon_auto_mask_for_object",
    "resolve_selection_scope",
    "resolve_target_color_attribute",
    "resolve_vertex_auto_mask_for_object",
    "resolve_vertex_selection_mask_for_object",
)
