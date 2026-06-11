# -*- coding: utf-8 -*-
import bpy
import bpy.utils.previews

from ... import utils
from ...core.operator_poll import has_scene
from ...i18n import tr, tr_format

DEFAULT_PALETTE_NAME = "YLVC Palette"
PALETTE_SLOT_LIMIT = 48
SWATCH_SIZE = 24
SWATCH_BORDER_SIZE = 2
_SWATCH_PREVIEWS = {}


def get_palette_owner(context):
    tool_settings = getattr(context, "tool_settings", None)
    if tool_settings is None:
        return None
    return getattr(tool_settings, "vertex_paint", None)


def ensure_palette(scene):
    palette = getattr(scene, "ylvc_palette", None)
    if palette is None:
        palette = bpy.data.palettes.get(DEFAULT_PALETTE_NAME)
        if palette is None:
            palette = bpy.data.palettes.new(DEFAULT_PALETTE_NAME)
        scene.ylvc_palette = palette
    return palette


def get_palette(scene):
    return getattr(scene, "ylvc_palette", None)


def get_context_palette(context):
    owner = get_palette_owner(context)
    if owner is not None and getattr(owner, "palette", None) is not None:
        return owner.palette
    scene = getattr(context, "scene", None)
    if scene is None:
        return None
    return get_palette(scene)


def ensure_context_palette(context):
    scene = getattr(context, "scene", None)
    owner = get_palette_owner(context)
    palette = get_context_palette(context)
    if palette is None:
        palette = bpy.data.palettes.get(DEFAULT_PALETTE_NAME)
        if palette is None:
            palette = bpy.data.palettes.new(DEFAULT_PALETTE_NAME)

    if scene is not None and getattr(scene, "ylvc_palette", None) != palette:
        scene.ylvc_palette = palette
    if owner is not None and getattr(owner, "palette", None) != palette:
        owner.palette = palette
    return palette


def get_active_palette_color(scene):
    palette = get_palette(scene)
    if palette is None or len(palette.colors) == 0:
        return None

    active = getattr(palette.colors, "active", None)
    if active is not None:
        return active
    return palette.colors[0]


def get_active_palette_index(scene):
    palette = get_palette(scene)
    active = get_active_palette_color(scene)
    if palette is None or active is None:
        return -1
    for index, color in enumerate(palette.colors):
        if color == active:
            return index
    return -1


def set_active_palette_index(scene, index):
    palette = get_palette(scene)
    if palette is None or index < 0 or index >= len(palette.colors):
        return None
    palette.colors.active = palette.colors[index]
    return palette.colors[index]


def _linear_to_srgb(c):
    if c <= 0.0031308:
        return c * 12.92
    return 1.055 * (c ** (1.0 / 2.4)) - 0.055


def get_color_icon(color, selected=False):
    if "main" not in _SWATCH_PREVIEWS:
        _SWATCH_PREVIEWS["main"] = bpy.utils.previews.new()
    pcoll = _SWATCH_PREVIEWS["main"]

    r = max(0.0, min(1.0, float(color[0])))
    g = max(0.0, min(1.0, float(color[1])))
    b = max(0.0, min(1.0, float(color[2])))
    rs = _linear_to_srgb(r)
    gs = _linear_to_srgb(g)
    bs = _linear_to_srgb(b)
    key = f"ylvc_{int(rs * 255):03d}_{int(gs * 255):03d}_{int(bs * 255):03d}_{'sel' if selected else 'base'}"

    if key not in pcoll:
        icon = pcoll.new(key)
        icon_size = SWATCH_SIZE + (SWATCH_BORDER_SIZE * 2 if selected else 0)
        icon.icon_size = (icon_size, icon_size)
        pixels = []
        for y in range(icon_size):
            for x in range(icon_size):
                if selected:
                    is_outer_border = (
                        x < SWATCH_BORDER_SIZE
                        or x >= icon_size - SWATCH_BORDER_SIZE
                        or y < SWATCH_BORDER_SIZE
                        or y >= icon_size - SWATCH_BORDER_SIZE
                    )
                    is_color_area = (
                        SWATCH_BORDER_SIZE <= x < SWATCH_BORDER_SIZE + SWATCH_SIZE
                        and SWATCH_BORDER_SIZE <= y < SWATCH_BORDER_SIZE + SWATCH_SIZE
                    )
                    if is_outer_border:
                        pixels.extend((0.32, 0.55, 0.88, 1.0))
                    elif is_color_area:
                        pixels.extend((rs, gs, bs, 1.0))
                    else:
                        pixels.extend((0.0, 0.0, 0.0, 0.0))
                else:
                    pixels.extend((rs, gs, bs, 1.0))
        icon.icon_pixels_float = pixels

    return pcoll[key].icon_id


class MESH_OT_YLVCInvertValue(bpy.types.Operator):
    bl_idname = "mesh.ylvc_invert_value"
    bl_label = "Invert Value"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return has_scene(context)

    def execute(self, context):
        scene = context.scene
        channel = scene.ylvc_channel

        if channel == "RGB":
            holder = utils.get_color_holder(context)
            if not holder:
                self.report({"WARNING"}, tr("No vertex paint brush found."))
                return {"CANCELLED"}
            holder.color = (1.0 - holder.color[0], 1.0 - holder.color[1], 1.0 - holder.color[2])
        else:
            scene.ylvc_single_fg = 1.0 - float(scene.ylvc_single_fg)

        return {"FINISHED"}


class MESH_OT_YLVCAddPaletteColor(bpy.types.Operator):
    bl_idname = "mesh.ylvc_add_palette_color"
    bl_label = "Add Palette Color"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return has_scene(context)

    def execute(self, context):
        palette = ensure_context_palette(context)
        if len(palette.colors) >= PALETTE_SLOT_LIMIT:
            self.report({"INFO"}, tr_format("You can only store up to {count} colors.", count=PALETTE_SLOT_LIMIT))
            return {"CANCELLED"}

        color = utils.get_current_fg_rgb(context) or (1.0, 1.0, 1.0)
        item = palette.colors.new()
        item.color = color
        return {"FINISHED"}


class MESH_OT_YLVCRemovePaletteColor(bpy.types.Operator):
    bl_idname = "mesh.ylvc_remove_palette_color"
    bl_label = "Remove Palette Color"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return has_scene(context)

    def execute(self, context):
        scene = context.scene
        palette = get_palette(scene)
        if palette is None or len(palette.colors) == 0:
            return {"CANCELLED"}

        active = get_active_palette_color(scene)
        if active is None:
            return {"CANCELLED"}
        palette.colors.remove(active)
        return {"FINISHED"}


def cleanup_previews():
    for pcoll in _SWATCH_PREVIEWS.values():
        bpy.utils.previews.remove(pcoll)
    _SWATCH_PREVIEWS.clear()


CLASSES = (
    MESH_OT_YLVCInvertValue,
    MESH_OT_YLVCAddPaletteColor,
    MESH_OT_YLVCRemovePaletteColor,
)
