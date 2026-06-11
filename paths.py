# -*- coding: utf-8 -*-
"""Package resource paths."""

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = PACKAGE_DIR / "assets"
LOCALES_DIR = PACKAGE_DIR / "locales"
PREVIEW_BLEND_PATH = ASSETS_DIR / "VertexDisplay.blend"


def preview_blend_path():
    return PREVIEW_BLEND_PATH


def locales_dir():
    return LOCALES_DIR


def user_data_path(path="", create=False):
    """Return Blender's per-extension user data path for writable files."""
    import bpy

    return Path(bpy.utils.extension_path_user(__package__, path=path, create=create))
