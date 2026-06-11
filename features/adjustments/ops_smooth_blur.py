import bpy
import numpy as np


def corner_to_point_rgb_into(out_rgb, colors_rgb, loop_vi, vert_count, inv_counts):
    """Average CORNER colors into POINT space."""
    out_rgb[:, 0] = np.bincount(loop_vi, weights=colors_rgb[:, 0], minlength=vert_count)
    out_rgb[:, 1] = np.bincount(loop_vi, weights=colors_rgb[:, 1], minlength=vert_count)
    out_rgb[:, 2] = np.bincount(loop_vi, weights=colors_rgb[:, 2], minlength=vert_count)
    out_rgb *= inv_counts[:, None]
    return out_rgb


def corner_to_point_scalar_into(out_values, values, loop_vi, vert_count, inv_counts):
    """Average CORNER scalar values into POINT space."""
    out_values[:] = np.bincount(loop_vi, weights=values, minlength=vert_count)
    out_values *= inv_counts
    return out_values


def laplacian_smooth_rgb_cached(
    point_rgb,
    src,
    dst,
    inv_div,
    vert_count,
    iterations,
    buf_r,
    buf_g,
    buf_b,
    sum_r,
    sum_g,
    sum_b,
    edge_r,
    edge_g,
    edge_b,
):
    """Smooth RGB data in POINT space using cached topology buffers."""
    if iterations <= 0 or src is None or dst is None or inv_div is None or len(src) == 0:
        return point_rgb

    buf_r[:] = point_rgb[:, 0]
    buf_g[:] = point_rgb[:, 1]
    buf_b[:] = point_rgb[:, 2]

    for _ in range(iterations):
        sum_r.fill(0.0)
        np.take(buf_r, src, out=edge_r)
        np.add.at(sum_r, dst, edge_r)
        np.add(sum_r, buf_r, out=buf_r)
        np.multiply(buf_r, inv_div, out=buf_r)

        sum_g.fill(0.0)
        np.take(buf_g, src, out=edge_g)
        np.add.at(sum_g, dst, edge_g)
        np.add(sum_g, buf_g, out=buf_g)
        np.multiply(buf_g, inv_div, out=buf_g)

        sum_b.fill(0.0)
        np.take(buf_b, src, out=edge_b)
        np.add.at(sum_b, dst, edge_b)
        np.add(sum_b, buf_b, out=buf_b)
        np.multiply(buf_b, inv_div, out=buf_b)

    point_rgb[:, 0] = buf_r
    point_rgb[:, 1] = buf_g
    point_rgb[:, 2] = buf_b
    return point_rgb


def laplacian_smooth_scalar_cached(
    point_values,
    src,
    dst,
    inv_div,
    vert_count,
    iterations,
    work_buffer,
    sum_buffer,
    edge_buffer,
):
    """Smooth one scalar channel in POINT space using cached topology buffers."""
    if iterations <= 0 or src is None or dst is None or inv_div is None or len(src) == 0:
        return point_values

    work_buffer[:] = point_values
    for _ in range(iterations):
        sum_buffer.fill(0.0)
        np.take(work_buffer, src, out=edge_buffer)
        np.add.at(sum_buffer, dst, edge_buffer)
        np.add(sum_buffer, work_buffer, out=work_buffer)
        np.multiply(work_buffer, inv_div, out=work_buffer)

    point_values[:] = work_buffer
    return point_values


def apply_blur_filter(context, cache):
    """Apply the blur stage on top of the current shared preview buffer."""
    props = context.scene.ylvc_blur_props
    iterations = props.smooth_iterations
    if iterations <= 0:
        return

    work_colors = cache["work_buffer"]
    original_colors = cache["original_colors"]
    mask = cache["selection_mask"]
    if work_colors is None or original_colors is None or mask is None:
        return

    channel_key = getattr(context.scene, "ylvc_channel", "RGB")
    channel_key = channel_key if channel_key in {"RGB", "R", "G", "B", "A"} else "RGB"
    domain = cache["domain"]
    vert_count = cache["vert_count"]
    loop_vi = cache["loop_vi"]
    smooth_src = cache["smooth_src"]
    smooth_dst = cache["smooth_dst"]
    smooth_inv_div = cache["smooth_inv_div"]
    selected_indices = cache.get("selected_indices")
    selected_loop_vi = cache.get("selected_loop_vi")

    if channel_key == "RGB":
        point_rgb = cache["point_rgb"]
        if point_rgb is None:
            return

        if domain == "CORNER":
            corner_inv_counts = cache["corner_inv_counts"]
            if loop_vi is None or corner_inv_counts is None:
                return
            corner_to_point_rgb_into(point_rgb, work_colors[:, :3], loop_vi, vert_count, corner_inv_counts)
        else:
            point_rgb[:] = work_colors[:, :3]

        laplacian_smooth_rgb_cached(
            point_rgb,
            smooth_src,
            smooth_dst,
            smooth_inv_div,
            vert_count,
            iterations,
            cache["smooth_r"],
            cache["smooth_g"],
            cache["smooth_b"],
            cache["smooth_sum_r"],
            cache["smooth_sum_g"],
            cache["smooth_sum_b"],
            cache["smooth_edge_r"],
            cache["smooth_edge_g"],
            cache["smooth_edge_b"],
        )

        if domain == "CORNER":
            if selected_indices is not None and selected_loop_vi is not None:
                work_colors[selected_indices, :3] = point_rgb[selected_loop_vi, :3]
                return
            smoothed = point_rgb[loop_vi]
        else:
            if selected_indices is not None:
                work_colors[selected_indices, :3] = point_rgb[selected_indices, :3]
                return
            smoothed = point_rgb

        work_colors[mask, :3] = smoothed[mask, :3]
        return

    point_scalar = cache["point_scalar"]
    smooth_scalar = cache["smooth_scalar"]
    if point_scalar is None or smooth_scalar is None:
        return

    channel_index = 3 if channel_key == "A" else {"R": 0, "G": 1, "B": 2}[channel_key]
    source_values = work_colors[:, channel_index]

    if domain == "CORNER":
        corner_inv_counts = cache["corner_inv_counts"]
        if loop_vi is None or corner_inv_counts is None:
            return
        corner_to_point_scalar_into(point_scalar, source_values, loop_vi, vert_count, corner_inv_counts)
    else:
        point_scalar[:] = source_values

    laplacian_smooth_scalar_cached(
        point_scalar,
        smooth_src,
        smooth_dst,
        smooth_inv_div,
        vert_count,
        iterations,
        smooth_scalar,
        cache["smooth_sum_scalar"],
        cache["smooth_edge_scalar"],
    )

    if domain == "CORNER":
        if selected_indices is not None and selected_loop_vi is not None:
            work_colors[selected_indices, channel_index] = point_scalar[selected_loop_vi]
            return
        smoothed = point_scalar[loop_vi]
    else:
        if selected_indices is not None:
            work_colors[selected_indices, channel_index] = point_scalar[selected_indices]
            return
        smoothed = point_scalar

    work_colors[mask, channel_index] = smoothed[mask]


def _update_blur_props(_self, context):
    from . import ops_color_adjust

    ops_color_adjust.apply_color_adjust_filters(None, context)
    ops_color_adjust._snapshot_adjust_state()


class YLVCBlurSettings(bpy.types.PropertyGroup):
    smooth_iterations: bpy.props.IntProperty(
        name="Iterations",
        description="Number of Laplacian smoothing iterations. Keeping this under 40 is usually best on dense meshes.",
        default=0,
        min=0,
        max=100,
        soft_max=40,
        update=_update_blur_props,
    )


classes = (
    YLVCBlurSettings,
)
