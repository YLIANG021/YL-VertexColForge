# -*- coding: utf-8 -*-
"""Main YL VertexColForge UI panels."""

import bpy

from ..features.color import ops_preview
from ..i18n import tr
from .common import (
    HINT_ICON,
    PANEL_CATEGORY,
    draw_selection_scope_hint,
    has_mesh,
)
from .sections import adjust, attributes, brush, channel, gradient, light_ao, randomize, selection, transfer


def draw_tool_tabs(layout, context):
    scene = context.scene
    col = layout.column()
    col.scale_y = 1.75
    grid = col.grid_flow(row_major=True, columns=8, even_columns=True, even_rows=True, align=True)
    grid.prop_enum(scene, "ylvc_ui_section", "BRUSH", text="", icon="BRUSHES_ALL")
    grid.prop_enum(scene, "ylvc_ui_section", "GRADIENT", text="", icon="COLORSET_07_VEC")
    grid.prop_enum(scene, "ylvc_ui_section", "SELECT", text="", icon="VIEW_PAN")
    grid.prop_enum(scene, "ylvc_ui_section", "COPY", text="", icon="MOD_MIRROR")
    grid.prop_enum(scene, "ylvc_ui_section", "LIGHT", text="", icon="LIGHT_SUN")
    grid.prop_enum(scene, "ylvc_ui_section", "POST", text="", icon="OPTIONS")
    grid.prop_enum(scene, "ylvc_ui_section", "RANDOM", text="", icon="IMGDISPLAY")
    grid.prop_enum(scene, "ylvc_ui_section", "TRANSFER", text="", icon="AREA_SWAP")


def draw_active_section(layout, context):
    section = context.scene.ylvc_ui_section

    if section == "BRUSH":
        brush.draw_brush_values_content(layout, context)
    elif section == "GRADIENT":
        gradient.draw_gradient_content(layout, context)
    elif section == "SELECT":
        selection.draw_selection_content(layout, context)
    elif section == "COPY":
        channel.draw_channel_tools_content(layout, context)
    elif section == "LIGHT":
        light_ao.draw_light_shadow_content(layout, context)
    elif section == "POST":
        adjust.draw_post_processing_content(layout, context)
    elif section == "RANDOM":
        randomize.draw_random_fill_content(layout, context)
    elif section == "TRANSFER":
        transfer.draw_texture_transfer_content(layout, context)


def get_active_section_header(scene):
    section = scene.ylvc_ui_section
    if section == "BRUSH":
        return "Paint and Fill", "BRUSHES_ALL"
    if section == "GRADIENT":
        return "Viewport Gradient", "COLORSET_07_VEC"
    if section == "SELECT":
        return "Color Select", "VIEW_PAN"
    if section == "COPY":
        return "Channel Blend", "MOD_MIRROR"
    if section == "LIGHT":
        return "Light and AO", "LIGHT_SUN"
    if section == "POST":
        return "Color Adjust", "OPTIONS"
    if section == "RANDOM":
        return "Randomize Colors", "IMGDISPLAY"
    if section == "TRANSFER":
        return "Color Transfer", "AREA_SWAP"
    return "Tools", "TOOL_SETTINGS"


class VIEW3D_PT_YLVCPanel(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = PANEL_CATEGORY
    bl_label = "YL VertexColForge"

    def draw(self, context):
        layout = self.layout
        if not has_mesh(context):
            layout.label(text=tr("Select a mesh object first."), icon=HINT_ICON)
            return

        top_panel = layout.box()
        has_attr = attributes.draw_color_attributes_section(top_panel, context)
        if not has_attr:
            return

        layout.separator(factor=0.35)

        content_panel = layout.box()
        title_text, _title_icon = get_active_section_header(context.scene)
        title_row = content_panel.row(align=True)
        title_row.label(text=tr(title_text))
        obj = context.active_object
        is_previewing = bool(
            obj
            and obj.type == "MESH"
            and obj.modifiers.get(ops_preview.PREVIEW_MODIFIER_NAME) is not None
        )

        tabs_box = content_panel.column()
        tabs_box.enabled = is_previewing
        draw_tool_tabs(tabs_box, context)

        if not is_previewing:
            return

        draw_selection_scope_hint(content_panel, context)

        content_box = content_panel.column()
        draw_active_section(content_box, context)


CLASSES = (
    VIEW3D_PT_YLVCPanel,
)
