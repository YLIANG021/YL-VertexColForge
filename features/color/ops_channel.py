# -*- coding: utf-8 -*-
import bmesh
import bpy
import numpy as np

from ...core.channel_sampling import source_channel_index
from ...core.color_attribute import read_color_attribute_colors
from ...core.color_channels import channel_indices
from ...core.context import resolve_edit_color_layer, resolve_selection_scope, resolve_target_color_attribute
from ...core.operator_poll import active_mesh_has_color_attributes
from ...core.write_engine import (
    blend_source_values_into_colors,
    read_edit_element_colors,
    write_color_array_to_attribute,
    write_edit_element_colors,
)
from ...i18n import tr, tr_format
from ...services import display
from ... import utils


def _get_edit_channel_targets(bm, domain):
    use_selection = utils.bm_use_vert_selection(bm)
    if domain == "POINT":
        return [vert for vert in bm.verts if utils.bm_vert_in_auto_scope(vert, use_selection)]
    return [loop for face in bm.faces for loop in face.loops if utils.bm_vert_in_auto_scope(loop.vert, use_selection)]


def _read_edit_channel_colors(elements, layer):
    return read_edit_element_colors(elements, layer)


def _write_edit_channel_colors(elements, layer, colors):
    write_edit_element_colors(elements, layer, colors)


class MESH_OT_YLVCCopyChannel(bpy.types.Operator):
    bl_idname = "mesh.ylvc_copy_channel"
    bl_label = "Channel Mixer"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return active_mesh_has_color_attributes(context)

    def execute(self, context):
        target, error = resolve_target_color_attribute(context)
        if error:
            self.report({"WARNING"}, error)
            return {"CANCELLED"}

        obj = target.obj
        mesh = target.mesh
        attribute = target.color_attr
        layer_name = target.layer_name
        scene = context.scene

        source_key = scene.ylvc_source_channel
        target_key = scene.ylvc_channel
        blend_mode = scene.ylvc_blend_mode
        try:
            source_index = source_channel_index(source_key)
            channel_indices(target_key)
        except KeyError:
            self.report({"WARNING"}, tr("Invalid channel selection."))
            return {"CANCELLED"}

        domain = attribute.domain
        count = 0

        if obj.mode == "EDIT":
            edit_target, error = resolve_edit_color_layer(context)
            if error:
                self.report({"WARNING"}, error)
                return {"CANCELLED"}

            mesh = edit_target.mesh
            bm = edit_target.bm
            layer_name = edit_target.layer_name
            layer = edit_target.layer
            domain = edit_target.domain
            edit_targets = _get_edit_channel_targets(bm, domain)
            cur = _read_edit_channel_colors(edit_targets, layer)
            if cur.size > 0:
                source_vals = cur[:, source_index].copy()
                blend_source_values_into_colors(cur, source_vals, target_key, blend_mode, None)
                _write_edit_channel_colors(edit_targets, layer, cur)
                count = len(edit_targets)
            bmesh.update_edit_mesh(mesh)
        else:
            if domain not in {"POINT", "CORNER"}:
                self.report({"WARNING"}, tr_format("Unsupported color domain: {domain}", domain=domain))
                return {"CANCELLED"}

            data_count = len(attribute.data)
            if data_count == 0:
                self.report({"WARNING"}, tr("No mesh data to process."))
                return {"CANCELLED"}

            mask = resolve_selection_scope(context, attribute).data_mask
            cur = read_color_attribute_colors(mesh, attribute)

            if np.any(mask):
                source_vals = cur[:, source_index].copy()
                blend_source_values_into_colors(cur, source_vals, target_key, blend_mode, mask)
                write_color_array_to_attribute(attribute, cur, mesh=mesh)
                count = int(np.sum(mask))

        if layer_name:
            display.refresh_after_color_write(context, mesh, layer_name, obj=obj)

        self.report(
            {"INFO"},
            tr_format(
                "Applied {blend_mode} from {source_key} into {target_key} for {count} {target_label}.",
                blend_mode=blend_mode.title(),
                source_key=source_key,
                target_key=target_key,
                count=count,
                target_label=(tr("vertices") if domain == "POINT" else tr("corners")),
            ),
        )
        return {"FINISHED"}


CLASSES = (
    MESH_OT_YLVCCopyChannel,
)
