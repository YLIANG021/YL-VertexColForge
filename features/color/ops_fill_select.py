# -*- coding: utf-8 -*-
"""Fill operators."""

import bpy

from ...core.operator_poll import active_mesh_has_color_attributes, has_active_mesh
from ...core.write_engine import write_value_result
from ...services import display, transactions


def build_scene_selection_value(context):
    scene = context.scene
    channel = scene.ylvc_channel

    if channel == "RGB":
        fill_rgb = scene.ylvc_fill_rgb_fg
        return [fill_rgb[0], fill_rgb[1], fill_rgb[2], scene.ylvc_alpha_fg]
    return scene.ylvc_single_fg


def write_value_to_selection(context, value):
    context_state = transactions.ObjectContextTransaction(context)
    try:
        scene = context.scene
        result = write_value_result(
            context,
            value,
            channel_key=scene.ylvc_channel,
        )
        if result.success and result.layer_name:
            display.finish_color_write(
                context,
                result.mesh,
                result.layer_name,
                obj=result.obj,
                mesh_updated=result.mesh_updated,
                defer_preview_sync=True,
            )
        return result.as_tuple()
    finally:
        context_state.restore()


class MESH_OT_YLVCSwapColors(bpy.types.Operator):
    bl_idname = "mesh.ylvc_swap_colors"
    bl_label = "Swap Values"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return has_active_mesh(context)

    def execute(self, context):
        scene = context.scene
        channel = scene.ylvc_channel

        if channel == "RGB":
            fg_rgb = tuple(scene.ylvc_fill_rgb_fg)
            bg_rgb = tuple(scene.ylvc_fill_rgb_bg)
            scene.ylvc_fill_rgb_fg = bg_rgb
            scene.ylvc_fill_rgb_bg = fg_rgb
        elif channel != "A":
            fg_value = scene.ylvc_single_fg
            bg_value = scene.ylvc_single_bg
            scene.ylvc_single_fg = bg_value
            scene.ylvc_single_bg = fg_value

        fg_alpha, bg_alpha = scene.ylvc_alpha_fg, scene.ylvc_alpha_bg
        scene.ylvc_alpha_fg, scene.ylvc_alpha_bg = bg_alpha, fg_alpha
        return {"FINISHED"}


class MESH_OT_YLVCApplySceneValue(bpy.types.Operator):
    bl_idname = "mesh.ylvc_apply_scene_value"
    bl_label = "Quick Fill"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return active_mesh_has_color_attributes(context)

    def execute(self, context):
        value = build_scene_selection_value(context)
        if value is None:
            return {"CANCELLED"}

        success, message = write_value_to_selection(context, value)
        self.report({"INFO"} if success else {"WARNING"}, message)
        return {"FINISHED"} if success else {"CANCELLED"}


CLASSES = (MESH_OT_YLVCSwapColors, MESH_OT_YLVCApplySceneValue)
