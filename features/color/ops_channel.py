# -*- coding: utf-8 -*-
"""Channel copy and math operators."""

import bpy
import numpy as np

from ...core.color_attribute import read_color_attribute_colors, write_color_attribute_colors
from ...core.channel_sampling import RGB_LUMINANCE, source_channel_index
from ...core.color_channels import channel_indices
from ...core.color_attribute import resolve_target_color_attribute
from ...core.selection_scope import resolve_selection_scope
from ...core.operator_poll import active_mesh_has_color_attributes
from ...i18n import tr, tr_format
from ...services import display, transactions


TARGET_CHANNEL_INDEX = {"R": 0, "G": 1, "B": 2, "A": 3}


def can_copy_channels(source_key, target_key):
    return source_key != target_key


def can_swap_channels(source_key, target_key):
    if source_key == target_key:
        return False
    if source_key == "RGB" and target_key == "RGB":
        return False
    return True


def _resolve_channel_context(context):
    target, error = resolve_target_color_attribute(context)
    if error:
        return None, error

    scene = context.scene
    attribute = target.color_attr
    mask = resolve_selection_scope(context, attribute).data_mask
    if not np.any(mask):
        return None, tr("No mesh data to process.")

    return {
        "obj": target.obj,
        "mesh": target.mesh,
        "attribute": attribute,
        "layer_name": target.layer_name,
        "source_key": getattr(scene, "ylvc_source_channel", "RGB"),
        "target_key": getattr(scene, "ylvc_copy_target_channel", "RGB"),
        "mask": mask,
        "colors": read_color_attribute_colors(target.mesh, attribute),
    }, None


def _sample_source_values(colors, source_key):
    if source_key == "RGB":
        return np.clip(np.dot(colors[:, 0:3], RGB_LUMINANCE), 0.0, 1.0)
    return colors[:, source_channel_index(source_key)]


def _finish_channel_write(context, payload):
    write_color_attribute_colors(payload["attribute"], payload["colors"])
    if payload["layer_name"]:
        display.finish_color_write(
            context,
            payload["mesh"],
            payload["layer_name"],
            obj=payload["obj"],
            source_colors=payload["colors"],
            defer_preview_sync=True,
        )


def _execute_with_context_restore(context, callback):
    return transactions.execute_with_context_restore(context, callback)


class MESH_OT_YLVCCopyChannel(bpy.types.Operator):
    bl_idname = "mesh.ylvc_copy_channel"
    bl_label = "Copy Channel"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return active_mesh_has_color_attributes(context)

    def execute(self, context):
        def run():
            payload, error = _resolve_channel_context(context)
            if error:
                self.report({"WARNING"}, error)
                return {"CANCELLED"}

            source_key = payload["source_key"]
            target_key = payload["target_key"]
            if not can_copy_channels(source_key, target_key):
                self.report({"WARNING"}, tr("Invalid channel selection."))
                return {"CANCELLED"}
            try:
                channel_indices(target_key)
            except KeyError:
                self.report({"WARNING"}, tr("Invalid channel selection."))
                return {"CANCELLED"}

            colors = payload["colors"]
            mask = payload["mask"]
            source_values = _sample_source_values(colors, source_key)
            if target_key == "RGB":
                colors[mask, 0:3] = source_values[mask][:, None]
            else:
                target_index = TARGET_CHANNEL_INDEX[target_key]
                colors[mask, target_index] = source_values[mask]
            _finish_channel_write(context, payload)

            self.report({"INFO"}, tr("Channel copied."))
            return {"FINISHED"}

        return _execute_with_context_restore(context, run)


class MESH_OT_YLVCSwapChannel(bpy.types.Operator):
    bl_idname = "mesh.ylvc_swap_channel"
    bl_label = "Swap Channels"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return active_mesh_has_color_attributes(context)

    def execute(self, context):
        def run():
            payload, error = _resolve_channel_context(context)
            if error:
                self.report({"WARNING"}, error)
                return {"CANCELLED"}

            source_key = payload["source_key"]
            target_key = payload["target_key"]
            if not can_swap_channels(source_key, target_key):
                self.report({"WARNING"}, tr("Invalid channel selection."))
                return {"CANCELLED"}

            colors = payload["colors"]
            mask = payload["mask"]

            if source_key == "RGB":
                target_index = TARGET_CHANNEL_INDEX[target_key]
                rgb_values = colors[mask, 0:3].copy()
                target_values = colors[mask, target_index].copy()
                colors[mask, target_index] = np.clip(np.dot(rgb_values, RGB_LUMINANCE), 0.0, 1.0)
                colors[mask, 0:3] = target_values[:, None]
            elif target_key == "RGB":
                source_index = source_channel_index(source_key)
                source_values = colors[mask, source_index].copy()
                rgb_values = colors[mask, 0:3].copy()
                colors[mask, source_index] = np.clip(np.dot(rgb_values, RGB_LUMINANCE), 0.0, 1.0)
                colors[mask, 0:3] = source_values[:, None]
            else:
                source_index = source_channel_index(source_key)
                target_index = TARGET_CHANNEL_INDEX[target_key]
                source_values = colors[mask, source_index].copy()
                colors[mask, source_index] = colors[mask, target_index]
                colors[mask, target_index] = source_values

            _finish_channel_write(context, payload)
            self.report(
                {"INFO"},
                tr_format("Swapped {source_channel} and {target_channel}.", source_channel=source_key, target_channel=target_key),
            )
            return {"FINISHED"}

        return _execute_with_context_restore(context, run)


class MESH_OT_YLVCInvertChannel(bpy.types.Operator):
    bl_idname = "mesh.ylvc_invert_channel"
    bl_label = "Invert Channel"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return active_mesh_has_color_attributes(context)

    def execute(self, context):
        def run():
            payload, error = _resolve_channel_context(context)
            if error:
                self.report({"WARNING"}, error)
                return {"CANCELLED"}

            target_key = getattr(context.scene, "ylvc_channel", "RGB")
            colors = payload["colors"]
            mask = payload["mask"]

            if target_key == "RGB":
                colors[mask, 0:3] = 1.0 - colors[mask, 0:3]
            else:
                target_index = TARGET_CHANNEL_INDEX[target_key]
                colors[mask, target_index] = 1.0 - colors[mask, target_index]

            _finish_channel_write(context, payload)
            self.report({"INFO"}, tr_format("Inverted {target_channel}.", target_channel=target_key))
            return {"FINISHED"}

        return _execute_with_context_restore(context, run)


class MESH_OT_YLVCNormalizeChannel(bpy.types.Operator):
    bl_idname = "mesh.ylvc_normalize_channel"
    bl_label = "Normalize Channel"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return active_mesh_has_color_attributes(context)

    def execute(self, context):
        def run():
            payload, error = _resolve_channel_context(context)
            if error:
                self.report({"WARNING"}, error)
                return {"CANCELLED"}

            target_key = getattr(context.scene, "ylvc_channel", "RGB")
            colors = payload["colors"]
            mask = payload["mask"]

            if target_key == "RGB":
                values = colors[mask, 0:3]
                min_value = float(np.min(values))
                max_value = float(np.max(values))
                if abs(max_value - min_value) <= 1e-8:
                    self.report({"INFO"}, tr("Nothing to normalize."))
                    return {"CANCELLED"}
                colors[mask, 0:3] = (values - min_value) / (max_value - min_value)
            else:
                target_index = TARGET_CHANNEL_INDEX[target_key]
                values = colors[mask, target_index]
                min_value = float(np.min(values))
                max_value = float(np.max(values))
                if abs(max_value - min_value) <= 1e-8:
                    self.report({"INFO"}, tr("Nothing to normalize."))
                    return {"CANCELLED"}
                colors[mask, target_index] = (values - min_value) / (max_value - min_value)

            _finish_channel_write(context, payload)
            self.report({"INFO"}, tr_format("Normalized {target_channel}.", target_channel=target_key))
            return {"FINISHED"}

        return _execute_with_context_restore(context, run)


CLASSES = (
    MESH_OT_YLVCCopyChannel,
    MESH_OT_YLVCSwapChannel,
    MESH_OT_YLVCInvertChannel,
    MESH_OT_YLVCNormalizeChannel,
)
