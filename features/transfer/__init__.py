# -*- coding: utf-8 -*-
"""Texture, weight, and mesh color transfer tools."""

from . import ops_mesh_transfer, ops_texture, ops_weight

CLASSES = (
    *ops_texture.CLASSES,
    *ops_weight.CLASSES,
    *ops_mesh_transfer.CLASSES,
)


def register_properties():
    ops_mesh_transfer.register_properties()


def unregister_properties():
    ops_mesh_transfer.unregister_properties()
