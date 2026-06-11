# -*- coding: utf-8 -*-
import bpy
import numpy as np

from ...core.channel_sampling import SOURCE_CHANNELS, sample_scalar_from_image_pixels, source_channel_index
from ...core.color_attribute import read_color_attribute_colors
from ...core.color_channels import CHANNEL_COMPONENTS
from ...core.context import resolve_selection_scope, resolve_target_color_attribute
from ...core.mesh_topology import average_loop_values_to_vertices, loop_vertex_indices
from ...core.write_engine import blend_source_values_into_colors, write_color_array_to_attribute
from ...i18n import tr, tr_format
from ...services import display, transactions


def _srgb_to_linear(rgb):
    rgb = np.clip(rgb, 0.0, 1.0)
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(rgb):
    rgb = np.clip(rgb, 0.0, 1.0)
    return np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * (rgb ** (1.0 / 2.4)) - 0.055)


def _configure_emit_source(scene, channel, node_attr, node_emit, node_tree):
    source_mode = getattr(scene, "ylvc_tex_source", "RGB")
    links = node_tree.links

    if source_mode == "RGB":
        if channel == "RGB":
            links.new(node_attr.outputs["Color"], node_emit.inputs["Color"])
            return
        if channel == "A":
            links.new(node_attr.outputs["Alpha"], node_emit.inputs["Color"])
            return
        node_sep = node_tree.nodes.new("ShaderNodeSeparateColor")
        links.new(node_attr.outputs["Color"], node_sep.inputs["Color"])
        output_name = {"R": "Red", "G": "Green", "B": "Blue"}[channel]
        links.new(node_sep.outputs[output_name], node_emit.inputs["Color"])
        return

    if source_mode == "A":
        links.new(node_attr.outputs["Alpha"], node_emit.inputs["Color"])
        return

    node_sep = node_tree.nodes.new("ShaderNodeSeparateColor")
    links.new(node_attr.outputs["Color"], node_sep.inputs["Color"])
    output_name = {"R": "Red", "G": "Green", "B": "Blue"}[source_mode]
    links.new(node_sep.outputs[output_name], node_emit.inputs["Color"])


class MESH_OT_YLVCTextureToColor(bpy.types.Operator):
    bl_idname = "mesh.ylvc_texture_to_color"
    bl_label = "Sample Image to Color"
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
            image = scene.ylvc_tex_image

            if not image:
                self.report({"WARNING"}, tr("Please choose an image first."))
                return {"CANCELLED"}
            if not mesh.uv_layers.active:
                self.report({"WARNING"}, tr("Mesh has no active UV map."))
                return {"CANCELLED"}

            target, error = resolve_target_color_attribute(context)
            if error:
                self.report({"WARNING"}, error)
                return {"CANCELLED"}
            attribute = target.color_attr

            width, height = image.size
            if width <= 0 or height <= 0:
                self.report({"WARNING"}, tr("Invalid image size."))
                return {"CANCELLED"}

            channel_key = scene.ylvc_channel
            if channel_key not in CHANNEL_COMPONENTS:
                self.report({"WARNING"}, tr("Invalid write channel."))
                return {"CANCELLED"}

            source_mode = getattr(scene, "ylvc_tex_source", "RGB")
            if source_mode not in SOURCE_CHANNELS:
                self.report({"WARNING"}, tr("Invalid texture source."))
                return {"CANCELLED"}

            loop_count = len(mesh.loops)
            if loop_count == 0:
                self.report({"WARNING"}, tr("Mesh has no loops to sample."))
                return {"CANCELLED"}

            pixels = np.empty(width * height * 4, dtype=np.float32)
            image.pixels.foreach_get(pixels)
            pixels.shape = (-1, 4)

            uv_data = np.empty(loop_count * 2, dtype=np.float32)
            mesh.uv_layers.active.data.foreach_get("uv", uv_data)
            uv_data.shape = (-1, 2)

            uv_clamped = np.clip(uv_data, 0.0, 1.0)
            u = (uv_clamped[:, 0] * (width - 1)).astype(np.int32)
            v = (uv_clamped[:, 1] * (height - 1)).astype(np.int32)
            pixel_indices = v * width + u
            sampled = pixels[pixel_indices].copy()

            is_img_srgb = image.colorspace_settings.name == "sRGB"
            is_attr_float = attribute.data_type == "FLOAT_COLOR"
            is_attr_byte = attribute.data_type == "BYTE_COLOR"
            if is_img_srgb and is_attr_float:
                sampled[:, 0:3] = _srgb_to_linear(sampled[:, 0:3])
            elif (not is_img_srgb) and is_attr_byte:
                sampled[:, 0:3] = _linear_to_srgb(sampled[:, 0:3])

            domain = attribute.domain
            if domain == "CORNER":
                mask = resolve_selection_scope(context, attribute).data_mask
                if not np.any(mask):
                    self.report({"WARNING"}, tr("No loops match the current selection."))
                    return {"CANCELLED"}

                colors = read_color_attribute_colors(mesh, attribute)

                if channel_key == "RGB":
                    if source_mode == "RGB":
                        source_values = sampled[:, 0:3]
                    else:
                        source_values = sampled[:, source_channel_index(source_mode)]
                else:
                    source_values = sample_scalar_from_image_pixels(sampled, source_mode, write_channel=channel_key)

                blend_source_values_into_colors(colors, source_values, channel_key, "REPLACE", mask)
                write_color_array_to_attribute(attribute, colors, update_mesh=False)
                affected = int(np.sum(mask))

            elif domain == "POINT":
                vert_count = len(mesh.vertices)
                if vert_count == 0:
                    self.report({"WARNING"}, tr("Mesh has no vertices."))
                    return {"CANCELLED"}

                loop_vert_indices = loop_vertex_indices(mesh)
                selection_scope = resolve_selection_scope(context, attribute)
                vertex_mask = selection_scope.vertex_mask
                loop_mask = vertex_mask[loop_vert_indices]
                if not np.any(loop_mask):
                    self.report({"WARNING"}, tr("No loops match the current selection."))
                    return {"CANCELLED"}

                colors = read_color_attribute_colors(mesh, attribute)

                if channel_key == "RGB":
                    if source_mode == "RGB":
                        mean_rgb, valid = average_loop_values_to_vertices(sampled[:, 0:3], loop_vert_indices, vert_count, loop_mask)
                        source_values = mean_rgb
                    else:
                        mean_gray, valid = average_loop_values_to_vertices(
                            sampled[:, source_channel_index(source_mode)],
                            loop_vert_indices,
                            vert_count,
                            loop_mask,
                        )
                        source_values = mean_gray
                else:
                    scalar_full = sample_scalar_from_image_pixels(sampled, source_mode, write_channel=channel_key)
                    mean_gray, valid = average_loop_values_to_vertices(scalar_full, loop_vert_indices, vert_count, loop_mask)
                    source_values = mean_gray

                blend_source_values_into_colors(colors, source_values, channel_key, "REPLACE", valid)
                write_color_array_to_attribute(attribute, colors, update_mesh=False)
                affected = int(np.sum(valid))
            else:
                self.report({"WARNING"}, tr_format("Unsupported color domain: {domain}", domain=domain))
                return {"CANCELLED"}

            mesh.update()
            display.refresh_after_color_write(context, mesh, attribute.name, obj=obj)
            if context.area:
                context.area.tag_redraw()

            self.report(
                {"INFO"},
                tr_format(
                    "Sampled image source {source_mode} into channel {channel_key} ({affected} targets).",
                    source_mode=source_mode,
                    channel_key=channel_key,
                    affected=affected,
                ),
            )
            return {"FINISHED"}


class MESH_OT_YLVCColorToTexture(bpy.types.Operator):
    bl_idname = "mesh.ylvc_color_to_texture"
    bl_label = "Bake Color to Image"
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

        scene = context.scene
        image = scene.ylvc_tex_image
        if not image:
            self.report({"WARNING"}, tr("Please choose a target image first."))
            return {"CANCELLED"}
        if not obj.data.uv_layers.active:
            self.report({"WARNING"}, tr("Mesh has no active UV map."))
            return {"CANCELLED"}

        target, error = resolve_target_color_attribute(context)
        if error:
            self.report({"WARNING"}, error)
            return {"CANCELLED"}
        attribute = target.color_attr

        layer_name = attribute.name
        channel = scene.ylvc_channel
        source_mode = getattr(scene, "ylvc_tex_source", "RGB")
        bake_margin = max(0, int(getattr(scene, "ylvc_bake_margin", 16)))

        result = {"CANCELLED"}
        message = ""
        level = {"ERROR"}

        with transactions.CleanupStack() as cleanup:
            cleanup.push_attributes(scene.render, "engine")
            cleanup.push_object_context(context)
            material_state = cleanup.push_material_slots(obj)

            try:
                transactions.ensure_object_mode_for(context, obj)
                transactions.make_single_active_object(context, obj)
                transactions.set_render_engine(scene, "CYCLES")

                temp_material = bpy.data.materials.new(name="YLVC_Temp_Bake_Mat")
                cleanup.add(transactions.remove_datablock_if_unused, bpy.data.materials, temp_material)
                temp_material.use_nodes = True
                node_tree = temp_material.node_tree
                nodes = node_tree.nodes
                links = node_tree.links
                nodes.clear()

                node_attr = nodes.new("ShaderNodeAttribute")
                node_attr.attribute_name = layer_name
                node_emit = nodes.new("ShaderNodeEmission")
                node_output = nodes.new("ShaderNodeOutputMaterial")
                node_image = nodes.new("ShaderNodeTexImage")
                node_image.image = image
                nodes.active = node_image
                node_image.select = True

                _configure_emit_source(scene, channel, node_attr, node_emit, node_tree)
                links.new(node_emit.outputs["Emission"], node_output.inputs["Surface"])

                transactions.cover_material_slots(obj, temp_material, material_state)

                # Blender baking is exposed through operators, not a complete data API.
                bpy.ops.object.bake(type="EMIT", margin=bake_margin, target="IMAGE_TEXTURES")
                message = tr_format(
                    "Baked source {source_mode} with channel {channel_key} to image '{image_name}'.",
                    source_mode=source_mode,
                    channel_key=channel,
                    image_name=image.name,
                )
                level = {"INFO"}
                result = {"FINISHED"}
            except Exception as exc:
                message = tr_format("Bake failed: {message}", message=str(exc))

        self.report(level, message)
        return result


CLASSES = (MESH_OT_YLVCTextureToColor, MESH_OT_YLVCColorToTexture)
