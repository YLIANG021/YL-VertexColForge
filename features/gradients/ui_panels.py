# -*- coding: utf-8 -*-
import bpy

from .core_color_engine import find_adjust_ramp_node, find_light_ramp_node, find_ramp_node
from ...services import display
from ...i18n import tr, tr_format
from ...ui.common import draw_missing, draw_requires, draw_unavailable, section_body

PANEL_CATEGORY = "YL VertexColForge"


def _get_mesh_context(context):
    obj = context.active_object
    if not obj or obj.type != "MESH":
        return None, None, None

    mesh = obj.data
    active_color_attr = None
    if mesh.color_attributes:
        index = mesh.color_attributes.active_color_index
        if 0 <= index < len(mesh.color_attributes):
            active_color_attr = mesh.color_attributes[index]
        elif len(mesh.color_attributes) > 0:
            active_color_attr = mesh.color_attributes[0]
    return obj, mesh, active_color_attr


def _has_active_color_attr(context):
    _, _, active_color_attr = _get_mesh_context(context)
    return active_color_attr is not None


def _is_gradient_tool_active(context):
    return getattr(context.scene, "ylvc_ui_section", "") == "GRADIENT"


def _is_viewport_gradient_enabled(context, obj):
    return _is_gradient_tool_active(context) and display.is_plugin_preview_enabled(obj)


def _draw_ramp_controls(layout, context, show_blend=True):
    scene = context.scene
    ramp_node = find_ramp_node()
    if ramp_node is None:
        layout.operator("mesh.ylvc_init_ramp_data", text=tr("Create Ramp"), icon="ADD")
    else:
        layout.template_color_ramp(ramp_node, "color_ramp", expand=True)

    if show_blend:
        layout.prop(scene, "ylvc_blend_mode", text=tr("Gradient Blend"))


def draw_shared_ramp_controls(layout, context, show_blend=True):
    _draw_ramp_controls(layout, context, show_blend=show_blend)


def draw_adjust_ramp_controls(layout, context):
    ramp_node = find_adjust_ramp_node()
    if ramp_node is None:
        layout.operator("mesh.ylvc_init_adjust_ramp_data", text=tr("Create Ramp"), icon="ADD")
    else:
        layout.template_color_ramp(ramp_node, "color_ramp", expand=True)


def draw_light_ramp_controls(layout, context):
    ramp_node = find_light_ramp_node()
    if ramp_node is None:
        layout.operator("mesh.ylvc_init_light_ramp_data", text=tr("Create Ramp"), icon="ADD")
    else:
        layout.template_color_ramp(ramp_node, "color_ramp", expand=True)


def draw_viewport_gradient_content(layout, context):
    scene = context.scene
    obj, _, active_color_attr = _get_mesh_context(context)
    content = section_body(layout)

    _draw_ramp_controls(content, context)

    needs_face_corner_in_edit = (
        obj is not None
        and obj.mode == "EDIT"
        and active_color_attr is not None
        and active_color_attr.domain == "POINT"
    )
    row_gradient = content.row(align=True)
    row_gradient.scale_y = 1.5
    row_gradient.enabled = not needs_face_corner_in_edit
    is_tracing = scene.ylvc_is_tracing
    tracing_type = getattr(scene, "ylvc_tracing_type", "")

    op_linear = row_gradient.operator(
        "mesh.ylvc_trace_ramp",
        text=tr_format("Linear {channel_key}", channel_key=scene.ylvc_channel),
        icon="EMPTY_SINGLE_ARROW",
        depress=(is_tracing and tracing_type == "LINEAR"),
    )
    if op_linear:
        op_linear.grad_type = "LINEAR"

    op_radial = row_gradient.operator(
        "mesh.ylvc_trace_ramp",
        text=tr_format("Radial {channel_key}", channel_key=scene.ylvc_channel),
        icon="MESH_CIRCLE",
        depress=(is_tracing and tracing_type == "RADIAL"),
    )
    if op_radial:
        op_radial.grad_type = "RADIAL"

    row_gradient.prop(
        scene,
        "ylvc_use_live_gradient",
        icon="RESTRICT_VIEW_OFF" if scene.ylvc_use_live_gradient else "RESTRICT_VIEW_ON",
        text="",
        toggle=True,
    )

    if needs_face_corner_in_edit:
        draw_requires(content, "Face Corner color attribute in Edit Mode")


class VIEW3D_PT_YLVC_Gradient(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = PANEL_CATEGORY
    bl_label = "Screen Gradient"
    bl_parent_id = "VIEW3D_PT_YLVCPanel"
    bl_order = 20

    @classmethod
    def poll(cls, context):
        return _has_active_color_attr(context)

    def draw(self, context):
        draw_viewport_gradient_content(self.layout, context)


class IMAGE_EDITOR_PT_YLVC_Gradient(bpy.types.Panel):
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"
    bl_category = PANEL_CATEGORY
    bl_label = "UV Gradient"

    @classmethod
    def poll(cls, context):
        obj, mesh, active_color_attr = _get_mesh_context(context)
        return context.area is not None and context.area.type == "IMAGE_EDITOR" and obj is not None and mesh is not None and active_color_attr is not None

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        obj, mesh, active_color_attr = _get_mesh_context(context)
        content = section_body(layout)

        viewport_gradient_enabled = _is_viewport_gradient_enabled(context, obj)
        gradient_controls = content.column()
        gradient_controls.enabled = viewport_gradient_enabled
        _draw_ramp_controls(gradient_controls, context)

        if not mesh.uv_layers.active:
            draw_missing(content, "active UV map")
        if not display.is_plugin_preview_enabled(obj):
            draw_unavailable(content, "viewport preview")
        elif not _is_gradient_tool_active(context):
            draw_unavailable(content, "Viewport Gradient tool")

        row_action = content.row(align=True)
        row_action.scale_y = 1.5
        row_action.enabled = (
            viewport_gradient_enabled
            and mesh.uv_layers.active is not None
            and active_color_attr.domain == "CORNER"
        )
        row_action.operator(
            "image.ylvc_test_gradient",
            text=tr_format("Draw {channel_key} Gradient", channel_key=scene.ylvc_channel),
            icon="COLOR",
            depress=(scene.ylvc_is_tracing and getattr(scene, "ylvc_tracing_type", "") == "UV_LINEAR"),
        )
        row_action.prop(
            scene,
            "ylvc_use_live_gradient",
            icon="RESTRICT_VIEW_OFF" if scene.ylvc_use_live_gradient else "RESTRICT_VIEW_ON",
            text="",
            toggle=True,
        )

        if active_color_attr and active_color_attr.domain != "CORNER":
            draw_requires(content, "Face Corner color attribute")


CLASSES = (
    IMAGE_EDITOR_PT_YLVC_Gradient,
)
