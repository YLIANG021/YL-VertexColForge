# -*- coding: utf-8 -*-
"""Main YL VertexColForge UI panels."""

import bpy

from ..i18n import tr
from ..features.color import ops_preview
from .common import (
    HINT_ICON,
    PANEL_CATEGORY,
    has_mesh,
)
from .sections import attributes, brush, channel, gradient, randomize, selection, transfer


def draw_tool_tabs(layout, context):
    scene = context.scene
    col = layout.column()
    col.scale_y = 1.75
    grid = col.grid_flow(row_major=True, columns=6, even_columns=True, even_rows=True, align=True)
    grid.prop_enum(scene, "ylvc_ui_section", "BRUSH", text="", icon="BRUSHES_ALL")
    grid.prop_enum(scene, "ylvc_ui_section", "SELECTION", text="", icon="RESTRICT_SELECT_OFF")
    grid.prop_enum(scene, "ylvc_ui_section", "GRADIENT", text="", icon="COLORSET_03_VEC")
    grid.prop_enum(scene, "ylvc_ui_section", "COPY", text="", icon="MODIFIER")
    grid.prop_enum(scene, "ylvc_ui_section", "RANDOM", text="", icon="IMGDISPLAY")
    grid.prop_enum(scene, "ylvc_ui_section", "TRANSFER", text="", icon="AREA_SWAP")


def draw_active_section(layout, context):
    section = context.scene.ylvc_ui_section

    if section == "BRUSH":
        brush.draw_brush_values_content(layout, context)
    elif section == "SELECTION":
        selection.draw_selection_content(layout, context)
    elif section == "GRADIENT":
        gradient.draw_gradient_content(layout, context)
    elif section == "COPY":
        channel.draw_channel_tools_content(layout, context)
    elif section == "RANDOM":
        randomize.draw_random_fill_content(layout, context)
    elif section == "TRANSFER":
        transfer.draw_texture_transfer_content(layout, context)


def get_active_section_header(scene):
    section = scene.ylvc_ui_section
    if section == "BRUSH":
        return "Channel Fill", "BRUSHES_ALL"
    if section == "SELECTION":
        return "Select by Channel", "RESTRICT_SELECT_OFF"
    if section == "GRADIENT":
        return "Mask Generate", "COLORSET_03_VEC"
    if section == "COPY":
        return "Channel Ops", "MODIFIER"
    if section == "RANDOM":
        return "Channel Random", "IMGDISPLAY"
    if section == "TRANSFER":
        return "Convert", "AREA_SWAP"
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

        if not ops_preview.is_solid_viewport(context):
            layout.label(text=tr("Only available in Solid mode."), icon=HINT_ICON)
            return

        top_panel = layout.box()
        has_attr = attributes.draw_color_attributes_section(top_panel, context)
        if not has_attr:
            return

        if not ops_preview.is_native_preview_enabled(context):
            return

        if ops_preview.is_vertex_paint_single_channel(context):
            return

        layout.separator(factor=0.35)

        content_panel = layout.box()
        title_text, _title_icon = get_active_section_header(context.scene)
        title_row = content_panel.row(align=True)
        title_row.label(text=tr(title_text))

        tabs_box = content_panel.column()
        draw_tool_tabs(tabs_box, context)

        content_box = content_panel.column()
        draw_active_section(content_box, context)


CLASSES = (
    VIEW3D_PT_YLVCPanel,
)
