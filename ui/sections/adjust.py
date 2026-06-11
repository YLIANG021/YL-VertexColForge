# -*- coding: utf-8 -*-
"""Color adjustment and blur UI."""

from ...features.adjustments import ops_color_adjust
from ...features.gradients import ui_panels as gradient_ui
from ...i18n import tr, tr_format
from ..common import section_body


def draw_post_processing_content(layout, context):
    scene = context.scene
    content = section_body(layout)
    adjust_props = scene.ylvc_adjust_props
    blur_props = scene.ylvc_blur_props

    is_live = ops_color_adjust._YLVC_ADJUST_CACHE["is_active"]

    box_session = content.box()
    if not is_live:
        row_init = box_session.row(align=True)
        row_init.scale_y = 1.5
        row_init.operator(
            "mesh.vcmc_init_adjust",
            text=tr_format("Adjust {channel_key}", channel_key=scene.ylvc_channel),
        )
        return

    ops_color_adjust.mark_adjust_session_visible()
    row_session = box_session.row(align=True)
    row_session.scale_y = 1.5
    row_session.operator("mesh.vcmc_apply_adjust", text=tr("Apply"))
    row_session.operator("mesh.vcmc_cancel_adjust", text=tr("Cancel"))

    box_adjust = content.box()
    row_adjust = box_adjust.row(align=True)
    row_adjust.prop(
        adjust_props,
        "show_levels_settings",
        text="",
        emboss=False,
        icon="TRIA_DOWN" if adjust_props.show_levels_settings else "TRIA_RIGHT",
    )
    row_adjust.label(text=tr("Color Adjust"))
    if adjust_props.show_levels_settings:
        col_adjust = box_adjust.column()
        col_adjust.prop(adjust_props, "lvl_black", slider=True)
        col_adjust.prop(adjust_props, "lvl_white", slider=True)
        col_adjust.prop(adjust_props, "lvl_gamma", slider=True)
        col_adjust.separator(factor=0.35)
        col_adjust.prop(adjust_props, "hsv_hue", slider=True)
        col_adjust.prop(adjust_props, "hsv_sat", slider=True)
        col_adjust.prop(adjust_props, "hsv_val", slider=True)
        col_adjust.separator(factor=0.5)
        col_adjust.operator(
            "mesh.vcmc_invert_colors",
            text=tr("Invert Colors"),
        )

    box_grad = content.box()
    row_grad = box_grad.row(align=True)
    row_grad.prop(
        adjust_props,
        "show_gradient_settings",
        text="",
        emboss=False,
        icon="TRIA_DOWN" if adjust_props.show_gradient_settings else "TRIA_RIGHT",
    )
    row_grad.label(text=tr("Ramp Remap"))
    row_grad_enabled = row_grad.row(align=True)
    row_grad_enabled.enabled = is_live
    row_grad_enabled.prop(
        adjust_props,
        "use_gradient",
        text="",
        icon="RESTRICT_VIEW_OFF" if adjust_props.use_gradient else "RESTRICT_VIEW_ON",
        toggle=True,
    )
    if adjust_props.show_gradient_settings:
        col_grad = box_grad.column()
        col_grad.enabled = is_live
        gradient_ui.draw_adjust_ramp_controls(col_grad, context)

    box_blur = content.box()
    box_blur.label(text=tr("Smooth Blur"))
    col_blur = box_blur.column()
    col_blur.prop(blur_props, "smooth_iterations", slider=True)
