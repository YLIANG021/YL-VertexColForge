# -*- coding: utf-8 -*-
import time

import bpy
import numpy as np

from ...core.channel_sampling import SOURCE_CHANNELS, sample_scalar_from_image_pixels, source_channel_index
from ...core.color_attribute import read_color_attribute_colors
from ...core.color_channels import CHANNEL_COMPONENTS
from ...core.color_attribute import resolve_target_color_attribute
from ...core.selection_scope import resolve_selection_scope
from ...core.mesh_topology import average_loop_values_to_vertices, loop_vertex_indices
from ...core.write_engine import blend_source_values_into_colors, write_color_array_to_attribute
from ...i18n import tr, tr_format
from ...services import display, transactions

VECTOR_RASTER_MAX_PIXELS = 262_144


def _srgb_to_linear(rgb):
    rgb = np.clip(rgb, 0.0, 1.0)
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(rgb):
    rgb = np.clip(rgb, 0.0, 1.0)
    return np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * (rgb ** (1.0 / 2.4)) - 0.055)


def _image_uses_srgb(image):
    colorspace = getattr(getattr(image, "colorspace_settings", None), "name", "")
    return colorspace == "sRGB"


def _loop_source_colors(mesh, attribute):
    colors = read_color_attribute_colors(mesh, attribute)
    if attribute.domain == "CORNER":
        return colors
    if attribute.domain == "POINT":
        return colors[loop_vertex_indices(mesh)]
    raise ValueError(tr_format("Unsupported color domain: {domain}", domain=attribute.domain))


def _build_image_pixels_from_colors(colors, channel, source_mode, attribute, image):
    colors = np.asarray(colors, dtype=np.float32).reshape(-1, 4)

    if source_mode == "RGB" and channel == "RGB":
        rgb = colors[:, 0:3].copy()
    else:
        source_key = channel if source_mode == "RGB" else source_mode
        if source_key == "A":
            scalar = colors[:, 3]
        else:
            scalar = colors[:, source_channel_index(source_key)]
        rgb = np.repeat(scalar[:, None], 3, axis=1).astype(np.float32, copy=False)

    if _image_uses_srgb(image) and attribute.data_type == "FLOAT_COLOR":
        rgb = _linear_to_srgb(rgb)
    elif not _image_uses_srgb(image) and attribute.data_type == "BYTE_COLOR":
        rgb = _srgb_to_linear(rgb)

    out = np.empty((len(colors), 4), dtype=np.float32)
    out[:, 0:3] = np.clip(rgb, 0.0, 1.0)
    out[:, 3] = 1.0
    return out


def _loop_triangle_indices(loop_triangles):
    tri_count = len(loop_triangles)
    indices = np.empty(tri_count * 3, dtype=np.int32)
    try:
        loop_triangles.foreach_get("loops", indices)
    except Exception:
        for index, loop_tri in enumerate(loop_triangles):
            indices[index * 3:index * 3 + 3] = loop_tri.loops
    indices.shape = (-1, 3)
    return indices


def _rasterize_pixel_triangle(image_pixels, coverage, pts, color_tri):
    height, width = coverage.shape

    min_x = max(0, int(np.floor(np.min(pts[:, 0]))))
    max_x = min(width - 1, int(np.ceil(np.max(pts[:, 0]))))
    min_y = max(0, int(np.floor(np.min(pts[:, 1]))))
    max_y = min(height - 1, int(np.ceil(np.max(pts[:, 1]))))
    if min_x > max_x or min_y > max_y:
        return 0

    x0, y0 = pts[0]
    x1, y1 = pts[1]
    x2, y2 = pts[2]
    denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    if abs(float(denom)) <= 1e-12:
        return 0

    color_tri = np.asarray(color_tri, dtype=np.float32).reshape(3, 4)
    is_constant_color = bool(np.all(np.abs(color_tri - color_tri[0]) <= 1e-6))

    bbox_width = max_x - min_x + 1
    bbox_height = max_y - min_y + 1
    bbox_area = bbox_width * bbox_height
    if bbox_area <= VECTOR_RASTER_MAX_PIXELS:
        xs = np.arange(min_x, max_x + 1, dtype=np.float32) + 0.5
        ys = np.arange(min_y, max_y + 1, dtype=np.float32) + 0.5
        xx, yy = np.meshgrid(xs, ys)
        w0 = ((y1 - y2) * (xx - x2) + (x2 - x1) * (yy - y2)) / denom
        w1 = ((y2 - y0) * (xx - x2) + (x0 - x2) * (yy - y2)) / denom
        w2 = 1.0 - w0 - w1
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not np.any(inside):
            return 0

        y_indices, x_indices = np.nonzero(inside)
        dst_y = min_y + y_indices
        dst_x = min_x + x_indices
        if is_constant_color:
            image_pixels[dst_y, dst_x, :] = color_tri[0]
        else:
            row_pixels = (
                w0[inside, None] * color_tri[0]
                + w1[inside, None] * color_tri[1]
                + w2[inside, None] * color_tri[2]
            )
            image_pixels[dst_y, dst_x, :] = row_pixels
        coverage[dst_y, dst_x] = True
        return len(dst_y)

    xs = np.arange(min_x, max_x + 1, dtype=np.float32) + 0.5
    written = 0

    for y in range(min_y, max_y + 1):
        yc = np.float32(y + 0.5)
        w0 = ((y1 - y2) * (xs - x2) + (x2 - x1) * (yc - y2)) / denom
        w1 = ((y2 - y0) * (xs - x2) + (x0 - x2) * (yc - y2)) / denom
        w2 = 1.0 - w0 - w1
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not np.any(inside):
            continue

        indices = np.flatnonzero(inside)
        x_indices = min_x + indices
        if is_constant_color:
            image_pixels[y, x_indices, :] = color_tri[0]
        else:
            row_pixels = (
                w0[indices, None] * color_tri[0]
                + w1[indices, None] * color_tri[1]
                + w2[indices, None] * color_tri[2]
            )
            image_pixels[y, x_indices, :] = row_pixels
        coverage[y, x_indices] = True
        written += len(indices)

    return written


def _coverage_boundary(coverage):
    height, width = coverage.shape
    boundary = np.zeros_like(coverage)
    directions = (
        (-1, -1), (-1, 0), (-1, 1),
        (0, -1),           (0, 1),
        (1, -1),  (1, 0),  (1, 1),
    )

    for dy, dx in directions:
        src_y0 = max(0, -dy)
        src_y1 = height - max(0, dy)
        dst_y0 = max(0, dy)
        dst_y1 = height - max(0, -dy)
        src_x0 = max(0, -dx)
        src_x1 = width - max(0, dx)
        dst_x0 = max(0, dx)
        dst_x1 = width - max(0, -dx)

        src_mask = coverage[src_y0:src_y1, src_x0:src_x1]
        dst_mask = coverage[dst_y0:dst_y1, dst_x0:dst_x1]
        boundary[src_y0:src_y1, src_x0:src_x1] |= src_mask & ~dst_mask

    return boundary


def _dilate_covered_pixels(image_pixels, coverage, margin):
    margin = max(0, int(margin))
    if margin <= 0 or not np.any(coverage):
        return 0

    height, width = coverage.shape
    flat_pixels = image_pixels.reshape(-1, 4)
    flat_coverage = coverage.reshape(-1)
    frontier = _coverage_boundary(coverage)
    filled_total = 0
    directions = (
        (-1, -1), (-1, 0), (-1, 1),
        (0, -1),           (0, 1),
        (1, -1),  (1, 0),  (1, 1),
    )

    for _ in range(margin):
        frontier_y, frontier_x = np.nonzero(frontier)
        if frontier_y.size == 0:
            break

        candidate_indices = []
        candidate_colors = []

        for dy, dx in directions:
            dst_y = frontier_y + dy
            dst_x = frontier_x + dx
            valid = (
                (dst_y >= 0)
                & (dst_y < height)
                & (dst_x >= 0)
                & (dst_x < width)
                & ~coverage[dst_y.clip(0, height - 1), dst_x.clip(0, width - 1)]
            )
            if not np.any(valid):
                continue

            src_y = frontier_y[valid]
            src_x = frontier_x[valid]
            dst_y = dst_y[valid]
            dst_x = dst_x[valid]
            candidate_indices.append((dst_y * width + dst_x).astype(np.int64, copy=False))
            candidate_colors.append(image_pixels[src_y, src_x, :])

        if not candidate_indices:
            break

        flat_indices = np.concatenate(candidate_indices)
        colors = np.concatenate(candidate_colors, axis=0)
        unique_indices, inverse = np.unique(flat_indices, return_inverse=True)

        acc = np.zeros((len(unique_indices), 4), dtype=np.float32)
        counts = np.zeros(len(unique_indices), dtype=np.float32)
        np.add.at(acc, inverse, colors)
        np.add.at(counts, inverse, 1.0)

        flat_pixels[unique_indices, :] = acc / counts[:, None]
        flat_coverage[unique_indices] = True
        filled_total += len(unique_indices)

        frontier = np.zeros_like(coverage)
        frontier.reshape(-1)[unique_indices] = True

    return filled_total


class MESH_OT_YLVCTextureToColor(bpy.types.Operator):
    bl_idname = "mesh.ylvc_texture_to_color"
    bl_label = "Sample Image to Channel"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        def run():
            return self._execute_impl(context)

        return transactions.execute_with_context_restore(context, run)

    def _execute_impl(self, context):
        obj = context.active_object
        if not obj or obj.type != "MESH":
            self.report({"WARNING"}, tr("Please select a mesh object."))
            return {"CANCELLED"}

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

        display.finish_color_write(
            context,
            mesh,
            attribute.name,
            obj=obj,
            source_colors=colors,
            defer_preview_sync=True,
        )
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
    bl_label = "Write Channel to Image"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        def run():
            return self._execute_impl(context)

        return transactions.execute_with_context_restore(context, run)

    def _execute_impl(self, context):
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

        target, error = resolve_target_color_attribute(context, activate=False)
        if error:
            self.report({"WARNING"}, error)
            return {"CANCELLED"}
        attribute = target.color_attr

        channel = scene.ylvc_channel
        source_mode = getattr(scene, "ylvc_tex_source", "RGB")
        image_margin = max(0, int(getattr(scene, "ylvc_image_padding", 2)))

        if channel not in CHANNEL_COMPONENTS:
            self.report({"WARNING"}, tr("Invalid write channel."))
            return {"CANCELLED"}
        if source_mode not in SOURCE_CHANNELS:
            self.report({"WARNING"}, tr("Invalid texture source."))
            return {"CANCELLED"}
        if attribute.domain not in {"POINT", "CORNER"}:
            self.report({"WARNING"}, tr_format("Unsupported color domain: {domain}", domain=attribute.domain))
            return {"CANCELLED"}

        width, height = image.size
        if width <= 0 or height <= 0:
            self.report({"WARNING"}, tr("Invalid image size."))
            return {"CANCELLED"}

        start_time = time.perf_counter()
        prep_time = start_time
        raster_time = start_time
        padding_time = start_time
        write_time = start_time

        try:
            transactions.ensure_object_mode_for(context, obj)
            mesh = obj.data
            mesh.calc_loop_triangles()
            loop_triangles = mesh.loop_triangles
            if len(loop_triangles) == 0:
                self.report({"WARNING"}, tr("Mesh has no polygons to write."))
                return {"CANCELLED"}

            uv_layer = mesh.uv_layers.active
            uv_data = np.empty(len(mesh.loops) * 2, dtype=np.float32)
            uv_layer.data.foreach_get("uv", uv_data)
            uv_data.shape = (-1, 2)

            source_colors = _loop_source_colors(mesh, attribute)
            if len(source_colors) != len(mesh.loops):
                self.report({"WARNING"}, tr("Color data does not match mesh loops."))
                return {"CANCELLED"}
            source_pixels = _build_image_pixels_from_colors(source_colors, channel, source_mode, attribute, image)

            pixels = np.empty(width * height * 4, dtype=np.float32)
            image.pixels.foreach_get(pixels)
            pixels.shape = (height, width, 4)
            coverage = np.zeros((height, width), dtype=bool)
            uv_pixels = uv_data.copy()
            uv_pixels[:, 0] *= width
            uv_pixels[:, 1] *= height
            triangle_loop_indices = _loop_triangle_indices(loop_triangles)
            prep_time = time.perf_counter()

            written_pixels = 0
            for loops in triangle_loop_indices:
                written_pixels += _rasterize_pixel_triangle(
                    pixels,
                    coverage,
                    uv_pixels[loops],
                    source_pixels[loops],
                )
            raster_time = time.perf_counter()

            padded_pixels = _dilate_covered_pixels(pixels, coverage, image_margin)
            padding_time = time.perf_counter()
            image.pixels.foreach_set(np.clip(pixels, 0.0, 1.0).ravel())
            image.update()
            write_time = time.perf_counter()
            if context.area:
                context.area.tag_redraw()
        except Exception as exc:
            self.report({"ERROR"}, tr_format("Image write failed: {message}", message=str(exc)))
            return {"CANCELLED"}

        self.report(
            {"INFO"},
            tr_format(
                "Wrote source {source_mode} with channel {channel_key} to image '{image_name}' ({pixel_count} pixels, {padding_count} padding, {total_time}s total: prep {prep_time}s, raster {raster_time}s, padding {padding_time}s, image {write_time}s).",
                source_mode=source_mode,
                channel_key=channel,
                image_name=image.name,
                pixel_count=int(np.sum(coverage)),
                padding_count=padded_pixels,
                total_time=f"{write_time - start_time:.2f}",
                prep_time=f"{prep_time - start_time:.2f}",
                raster_time=f"{raster_time - prep_time:.2f}",
                padding_time=f"{padding_time - raster_time:.2f}",
                write_time=f"{write_time - padding_time:.2f}",
            ),
        )
        return {"FINISHED"}


CLASSES = (MESH_OT_YLVCTextureToColor, MESH_OT_YLVCColorToTexture)
