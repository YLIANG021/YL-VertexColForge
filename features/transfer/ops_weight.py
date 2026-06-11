# -*- coding: utf-8 -*-
import bpy
import numpy as np

from ... import utils
from ...core.channel_sampling import SOURCE_CHANNELS, sample_scalar_from_colors
from ...core.color_attribute import read_color_attribute_colors
from ...core.color_channels import CHANNEL_COMPONENTS
from ...core.context import resolve_selection_scope, resolve_target_color_attribute
from ...core.mesh_topology import average_loop_values_to_vertices, loop_vertex_indices
from ...core.write_engine import blend_source_values_into_colors, write_color_array_to_attribute
from ...i18n import tr, tr_format
from ...services import display, transactions


def _ensure_vertex_group(obj, group_name):
    clean_name = (group_name or "").strip() or "Weights"
    group = obj.vertex_groups.get(clean_name)
    if group is None:
        group = obj.vertex_groups.new(name=clean_name)
    return group, clean_name


def _get_active_or_first_vertex_group(obj):
    if obj is None or obj.type != "MESH" or not obj.vertex_groups:
        return None

    active_index = getattr(obj.vertex_groups, "active_index", -1)
    if 0 <= active_index < len(obj.vertex_groups):
        return obj.vertex_groups[active_index]
    return obj.vertex_groups[0] if len(obj.vertex_groups) > 0 else None


def _get_selected_or_active_vertex_group(obj, group_name):
    if obj is None or obj.type != "MESH" or not obj.vertex_groups:
        return None

    clean_name = (group_name or "").strip()
    if clean_name:
        selected_group = obj.vertex_groups.get(clean_name)
        if selected_group is not None:
            return selected_group

    return _get_active_or_first_vertex_group(obj)


def _get_vertex_group_weights(obj, vertex_count, group):
    return utils.get_vertex_group_weights(obj, group, vertex_count=vertex_count)


class MESH_OT_YLVCColorToWeights(bpy.types.Operator):
    bl_idname = "mesh.ylvc_color_to_weights"
    bl_label = "Colors to Weights"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != "MESH":
            self.report({"WARNING"}, tr("Please select a mesh object."))
            return {"CANCELLED"}

        with transactions.CleanupStack() as cleanup:
            cleanup.push_object_context(context)
            transactions.ensure_object_mode_for(context, obj)
            mesh = obj.data
            scene = context.scene
            target, error = resolve_target_color_attribute(context)
            if error:
                self.report({"WARNING"}, error)
                return {"CANCELLED"}
            attribute = target.color_attr

            if attribute.domain not in {"POINT", "CORNER"}:
                self.report({"WARNING"}, tr_format("Unsupported color domain: {domain}", domain=attribute.domain))
                return {"CANCELLED"}

            source_mode = getattr(scene, "ylvc_weight_source", "RGB")
            if source_mode not in SOURCE_CHANNELS:
                self.report({"WARNING"}, tr("Invalid weight source."))
                return {"CANCELLED"}

            group, group_name = _ensure_vertex_group(obj, getattr(scene, "ylvc_weight_group_name", "Weights"))

            selection_scope = resolve_selection_scope(context, attribute)
            vertex_mask = selection_scope.vertex_mask
            if vertex_mask.size == 0:
                self.report({"WARNING"}, tr("Mesh has no vertices."))
                return {"CANCELLED"}

            if attribute.domain == "POINT":
                colors = read_color_attribute_colors(mesh, attribute)
                weights = sample_scalar_from_colors(colors, source_mode, rgb_mode="luminance")
                valid_mask = vertex_mask
            else:
                loop_count = len(mesh.loops)
                if loop_count == 0:
                    self.report({"WARNING"}, tr("Mesh has no loops."))
                    return {"CANCELLED"}

                loop_vert_indices = loop_vertex_indices(mesh)
                loop_mask = selection_scope.data_mask
                if not np.any(loop_mask):
                    self.report({"WARNING"}, tr("No loops match the current selection."))
                    return {"CANCELLED"}

                colors = read_color_attribute_colors(mesh, attribute)

                loop_weights = sample_scalar_from_colors(colors, source_mode, rgb_mode="luminance")
                weights, valid = average_loop_values_to_vertices(loop_weights, loop_vert_indices, len(mesh.vertices), loop_mask)
                valid_mask = valid & vertex_mask

            if not np.any(valid_mask):
                self.report({"WARNING"}, tr("No vertices match the current selection."))
                return {"CANCELLED"}

            target_indices = np.flatnonzero(valid_mask).astype(np.int32, copy=False)
            utils.assign_vertex_group_weights(group, target_indices, weights[target_indices])

            if context.area:
                context.area.tag_redraw()

            self.report(
                {"INFO"},
                tr_format(
                    "Wrote {count} weights to '{group_name}' from {source_mode}.",
                    count=len(target_indices),
                    group_name=group_name,
                    source_mode=source_mode,
                ),
            )
            return {"FINISHED"}


class MESH_OT_YLVCWeightsToColor(bpy.types.Operator):
    bl_idname = "mesh.ylvc_weights_to_color"
    bl_label = "Weights to Colors"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and len(obj.vertex_groups) > 0

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != "MESH":
            self.report({"WARNING"}, tr("Please select a mesh object."))
            return {"CANCELLED"}

        with transactions.CleanupStack() as cleanup:
            cleanup.push_object_context(context)
            transactions.ensure_object_mode_for(context, obj)
            mesh = obj.data
            scene = context.scene
            target, error = resolve_target_color_attribute(context)
            if error:
                self.report({"WARNING"}, error)
                return {"CANCELLED"}
            attribute = target.color_attr

            if attribute.domain not in {"POINT", "CORNER"}:
                self.report({"WARNING"}, tr_format("Unsupported color domain: {domain}", domain=attribute.domain))
                return {"CANCELLED"}

            group = _get_selected_or_active_vertex_group(obj, getattr(scene, "ylvc_weight_group_name", ""))
            if group is None:
                self.report({"WARNING"}, tr("No vertex group found."))
                return {"CANCELLED"}

            channel_key = getattr(scene, "ylvc_channel", "RGB")
            if channel_key not in CHANNEL_COMPONENTS:
                self.report({"WARNING"}, tr("Invalid write channel."))
                return {"CANCELLED"}

            selection_scope = resolve_selection_scope(context, attribute)
            vertex_mask = selection_scope.vertex_mask
            if vertex_mask.size == 0:
                self.report({"WARNING"}, tr("Mesh has no vertices."))
                return {"CANCELLED"}

            weights = _get_vertex_group_weights(obj, len(mesh.vertices), group)

            if attribute.domain == "POINT":
                colors = read_color_attribute_colors(mesh, attribute)

                valid_mask = vertex_mask
                if not np.any(valid_mask):
                    self.report({"WARNING"}, tr("No vertices match the current selection."))
                    return {"CANCELLED"}

                blend_source_values_into_colors(colors, weights, channel_key, "REPLACE", valid_mask)
                write_color_array_to_attribute(attribute, colors, update_mesh=False)
                affected = int(np.sum(valid_mask))
            else:
                loop_count = len(mesh.loops)
                if loop_count == 0:
                    self.report({"WARNING"}, tr("Mesh has no loops."))
                    return {"CANCELLED"}

                loop_vert_indices = loop_vertex_indices(mesh)
                loop_mask = selection_scope.data_mask
                if not np.any(loop_mask):
                    self.report({"WARNING"}, tr("No loops match the current selection."))
                    return {"CANCELLED"}

                colors = read_color_attribute_colors(mesh, attribute)

                loop_weights = weights[loop_vert_indices]
                blend_source_values_into_colors(colors, loop_weights, channel_key, "REPLACE", loop_mask)
                write_color_array_to_attribute(attribute, colors, update_mesh=False)
                affected = int(np.sum(loop_mask))

            mesh.update()
            display.refresh_after_color_write(context, mesh, attribute.name, obj=obj)
            if context.area:
                context.area.tag_redraw()

            self.report(
                {"INFO"},
                tr_format(
                    "Wrote group '{group_name}' into {channel_key} for {affected} targets.",
                    group_name=group.name,
                    channel_key=channel_key,
                    affected=affected,
                ),
            )
            return {"FINISHED"}


CLASSES = (MESH_OT_YLVCColorToWeights, MESH_OT_YLVCWeightsToColor)
