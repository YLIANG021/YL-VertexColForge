# -*- coding: utf-8 -*-
"""Selection and fill operators."""

from . import ops_fill_select, ops_pick_select

CLASSES = (
    *ops_fill_select.CLASSES,
    *ops_pick_select.CLASSES,
)
