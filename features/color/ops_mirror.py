# -*- coding: utf-8 -*-
import math

import bmesh
import bpy
import gpu
import mathutils
import numpy as np
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from ... import utils
from ...core.color_attribute import read_color_attribute_colors
from ...core.color_channels import channel_indices
from ...core.context import resolve_edit_color_layer, resolve_selection_scope, resolve_target_color_attribute
from ...core.mesh_topology import average_loop_values_to_vertices, loop_vertex_indices, vertex_positions
from ...core.write_engine import blend_source_values_into_colors, write_color_array_to_attribute
from ...i18n import tr_format
from ...services import display


AXIS_CONFIG = {
    "+X": {"axis": "X", "direction": "NEG_TO_POS", "color": (1.0, 0.35, 0.35, 1.0)},
    "-X": {"axis": "X", "direction": "POS_TO_NEG", "color": (1.0, 0.35, 0.35, 1.0)},
    "+Y": {"axis": "Y", "direction": "NEG_TO_POS", "color": (0.35, 1.0, 0.45, 1.0)},
    "-Y": {"axis": "Y", "direction": "POS_TO_NEG", "color": (0.35, 1.0, 0.45, 1.0)},
    "+Z": {"axis": "Z", "direction": "NEG_TO_POS", "color": (0.4, 0.65, 1.0, 1.0)},
    "-Z": {"axis": "Z", "direction": "POS_TO_NEG", "color": (0.4, 0.65, 1.0, 1.0)},
}

AXIS_VECTORS = {
    "+X": Vector((1.0, 0.0, 0.0)),
    "-X": Vector((-1.0, 0.0, 0.0)),
    "+Y": Vector((0.0, 1.0, 0.0)),
    "-Y": Vector((0.0, -1.0, 0.0)),
    "+Z": Vector((0.0, 0.0, 1.0)),
    "-Z": Vector((0.0, 0.0, -1.0)),
}

OPPOSITE_KEYS = {
    "+X": "-X",
    "-X": "+X",
    "+Y": "-Y",
    "-Y": "+Y",
    "+Z": "-Z",
    "-Z": "+Z",
}

AXIS_PAIRS = (
    ("+X", "-X"),
    ("+Y", "-Y"),
    ("+Z", "-Z"),
)

MIRROR_DRAG_ZERO_SNAP_RADIUS = 10.0
MIRROR_DRAG_TOLERANCE_SCALE = 600.0
MIRROR_AXIS_SNAP_DOT_THRESHOLD = 0.975


def _draw_polygon_2d(shader, vertices, color):
    if len(vertices) < 3:
        return
    indices = [(0, index, index + 1) for index in range(1, len(vertices) - 1)]
    batch = batch_for_shader(shader, "TRIS", {"pos": [tuple(vertex) for vertex in vertices]}, indices=indices)
    shader.uniform_float("color", color)
    batch.draw(shader)


def _draw_circle_2d(shader, center, radius, color, segments=24):
    vertices = [tuple(center)]
    for index in range(segments + 1):
        angle = (index / float(segments)) * math.tau
        vertices.append((center[0] + math.cos(angle) * radius, center[1] + math.sin(angle) * radius))
    batch = batch_for_shader(shader, "TRI_FAN", {"pos": vertices})
    shader.uniform_float("color", color)
    batch.draw(shader)


def _dim_color(_color, alpha=0.25):
    return (0.45, 0.45, 0.45, alpha)


def _with_alpha(color, alpha):
    return (color[0], color[1], color[2], alpha)


def _build_shaft_polygon(start, end, *, shaft_half_width=6.0):
    start_vec = Vector(start)
    end_vec = Vector(end)
    direction = end_vec - start_vec
    length = direction.length
    if length <= 1e-6:
        return None

    direction.normalize()
    normal = Vector((-direction.y, direction.x))
    return [
        start_vec + normal * shaft_half_width,
        end_vec + normal * shaft_half_width,
        end_vec - normal * shaft_half_width,
        start_vec - normal * shaft_half_width,
    ]


def _build_arrow_shape(start, end, *, shaft_half_width=6.0, head_length=23.1, head_half_width=None):
    start_vec = Vector(start)
    end_vec = Vector(end)
    direction = end_vec - start_vec
    length = direction.length
    if length <= 1e-6:
        return None

    direction.normalize()
    normal = Vector((-direction.y, direction.x))
    head_length = min(head_length, max(length * 0.22, 1.0))
    if head_half_width is None:
        head_half_width = head_length / math.sqrt(3.0)
    head_base = end_vec - direction * head_length
    shaft = _build_shaft_polygon(start_vec, head_base, shaft_half_width=shaft_half_width)
    head = [
        head_base + normal * head_half_width,
        end_vec,
        head_base - normal * head_half_width,
    ]
    outline = [
        shaft[0],
        shaft[1],
        head[0],
        head[1],
        head[2],
        shaft[2],
        shaft[3],
    ]
    return {
        "shaft": shaft,
        "head": head,
        "outline": outline,
    }


def _draw_arrow_shape(shader, start, end, color, *, shaft_half_width=6.0, head_length=23.1, head_half_width=None):
    shape = _build_arrow_shape(
        start,
        end,
        shaft_half_width=shaft_half_width,
        head_length=head_length,
        head_half_width=head_half_width,
    )
    if shape is None:
        return None
    _draw_polygon_2d(shader, shape["shaft"], color)
    _draw_polygon_2d(shader, shape["head"], color)
    return shape["outline"]


def _draw_arrow_without_head(shader, start, end, color, *, shaft_half_width=6.0, head_length=23.1, head_half_width=None):
    shape = _build_arrow_shape(
        start,
        end,
        shaft_half_width=shaft_half_width,
        head_length=head_length,
        head_half_width=head_half_width,
    )
    if shape is None:
        return None
    _draw_polygon_2d(shader, shape["shaft"], color)
    return shape


def _draw_line_shape(shader, start, end, color, *, shaft_half_width=3.0):
    polygon = _build_shaft_polygon(start, end, shaft_half_width=shaft_half_width)
    if polygon is None:
        return None
    _draw_polygon_2d(shader, polygon, color)
    return polygon


def _drag_distance_to_tolerance(drag_distance):
    if drag_distance <= MIRROR_DRAG_ZERO_SNAP_RADIUS:
        return 0.0
    effective_distance = drag_distance - MIRROR_DRAG_ZERO_SNAP_RADIUS
    return utils.clamp_factor(effective_distance / MIRROR_DRAG_TOLERANCE_SCALE)


def _mirror_edit_mode(context, obj, mesh, axis, direction, channel_key, tolerance, report_fn):
    target, error = resolve_edit_color_layer(context)
    if error:
        report_fn({"WARNING"}, error)
        return {"CANCELLED"}

    mesh = target.mesh
    bm = target.bm
    layer_name = target.layer_name
    layer = target.layer
    domain = target.domain
    axis_index = {"X": 0, "Y": 1, "Z": 2}[axis]
    source_sign = 1 if direction == "POS_TO_NEG" else -1

    source_verts = []
    for vert in bm.verts:
        coord_value = vert.co[axis_index]
        if (source_sign == 1 and coord_value >= -1e-5) or (source_sign == -1 and coord_value <= 1e-5):
            source_verts.append(vert)

    if not source_verts:
        report_fn({"WARNING"}, "No source-side vertices were found.")
        return {"CANCELLED"}

    kd_tree = mathutils.kdtree.KDTree(len(source_verts))
    source_by_index = {}
    for vert in source_verts:
        kd_tree.insert(vert.co, vert.index)
        source_by_index[vert.index] = vert
    kd_tree.balance()

    source_color_cache = {}

    def get_source_color(match_idx):
        if match_idx not in source_color_cache:
            src_vert = source_by_index[match_idx]
            if domain == "POINT":
                source_color_cache[match_idx] = utils.ensure_rgba_sequence(src_vert[layer])
            else:
                source_color_cache[match_idx] = utils.average_loop_colors(src_vert.link_loops, layer)
        return source_color_cache[match_idx]

    count = 0
    use_sel = utils.bm_use_vert_selection(bm)
    for vert in bm.verts:
        if not utils.bm_vert_in_auto_scope(vert, use_sel):
            continue

        coord_value = vert.co[axis_index]
        if not ((source_sign == 1 and coord_value < 0.0) or (source_sign == -1 and coord_value > 0.0)):
            continue

        search_co = vert.co.copy()
        search_co[axis_index] *= -1.0

        _, match_index, distance = kd_tree.find(search_co)
        if distance > tolerance:
            continue

        src_color = get_source_color(match_index)
        if domain == "POINT":
            vert[layer] = utils.copy_channel_values(vert[layer], src_color, channel_key)
            count += 1
        else:
            for loop in vert.link_loops:
                loop[layer] = utils.copy_channel_values(loop[layer], src_color, channel_key)
                count += 1

    bmesh.update_edit_mesh(mesh)
    display.refresh_after_color_write(context, mesh, layer_name, obj=obj)
    report_fn(
        {"INFO"},
        tr_format(
            "Mirror copy finished on axis {axis}, direction {direction}, channel {channel_key}, affected {count} entries.",
            axis=axis,
            direction=direction,
            channel_key=channel_key,
            count=count,
        ),
    )
    return {"FINISHED"}


def _mirror_object_mode(context, obj, mesh, axis, direction, channel_key, tolerance, report_fn):
    target, error = resolve_target_color_attribute(context)
    if error:
        report_fn({"WARNING"}, error)
        return {"CANCELLED"}

    attribute = target.color_attr
    layer_name = target.layer_name
    domain = attribute.domain
    axis_index = {"X": 0, "Y": 1, "Z": 2}[axis]
    source_sign = 1 if direction == "POS_TO_NEG" else -1
    target_channel_indices = channel_indices(channel_key)

    vert_count = len(mesh.vertices)
    if vert_count == 0:
        report_fn({"WARNING"}, "Mesh has no vertices.")
        return {"CANCELLED"}

    coords = vertex_positions(mesh)

    if source_sign == 1:
        source_side_mask = coords[:, axis_index] >= -1e-5
        target_side_mask = coords[:, axis_index] < 0.0
    else:
        source_side_mask = coords[:, axis_index] <= 1e-5
        target_side_mask = coords[:, axis_index] > 0.0

    selection_mask = resolve_selection_scope(context, attribute).vertex_mask
    target_side_mask &= selection_mask

    source_indices = np.where(source_side_mask)[0]
    target_indices = np.where(target_side_mask)[0]

    if len(source_indices) == 0:
        report_fn({"WARNING"}, "No source-side vertices were found.")
        return {"CANCELLED"}
    if len(target_indices) == 0:
        report_fn({"WARNING"}, "No target vertices matched the current selection.")
        return {"CANCELLED"}

    source_kd = mathutils.kdtree.KDTree(len(source_indices))
    for idx in source_indices:
        source_kd.insert(coords[idx], int(idx))
    source_kd.balance()

    target_coords = coords[target_indices].copy()
    target_coords[:, axis_index] *= -1.0

    matched_t_indices = []
    matched_s_indices = []
    for i, t_idx in enumerate(target_indices):
        _, match_idx, distance = source_kd.find(target_coords[i])
        if distance <= tolerance:
            matched_t_indices.append(int(t_idx))
            matched_s_indices.append(int(match_idx))

    if not matched_t_indices:
        report_fn({"INFO"}, tr_format("No matching vertices found within tolerance {tolerance}.", tolerance=tolerance))
        return {"FINISHED"}

    matched_t_indices = np.array(matched_t_indices, dtype=np.int32)
    matched_s_indices = np.array(matched_s_indices, dtype=np.int32)

    count = 0
    if domain == "CORNER":
        loop_count = len(mesh.loops)
        loop_vert_indices = loop_vertex_indices(mesh)

        colors = read_color_attribute_colors(mesh, attribute)
        vert_avg_colors, _valid = average_loop_values_to_vertices(colors, loop_vert_indices, vert_count)

        v_target_to_source = np.full(vert_count, -1, dtype=np.int32)
        v_target_to_source[matched_t_indices] = matched_s_indices

        l_target_to_source = v_target_to_source[loop_vert_indices]
        valid_loops_mask = l_target_to_source != -1

        if np.any(valid_loops_mask):
            source_colors_for_loops = vert_avg_colors[l_target_to_source[valid_loops_mask]]
            source_values = colors.copy()
            for ch in target_channel_indices:
                source_values[valid_loops_mask, ch] = source_colors_for_loops[:, ch]

            blend_source_values_into_colors(colors, source_values, channel_key, "REPLACE", valid_loops_mask)
            write_color_array_to_attribute(attribute, colors, update_mesh=False)
            count = int(np.sum(valid_loops_mask))

    elif domain == "POINT":
        point_colors = read_color_attribute_colors(mesh, attribute)

        source_values = point_colors.copy()
        for ch in target_channel_indices:
            source_values[matched_t_indices, ch] = point_colors[matched_s_indices, ch]

        blend_source_values_into_colors(point_colors, source_values, channel_key, "REPLACE", matched_t_indices)
        write_color_array_to_attribute(attribute, point_colors, update_mesh=False)
        count = int(len(matched_t_indices))
    else:
        report_fn({"WARNING"}, f"Unsupported domain: {domain}")
        return {"CANCELLED"}

    mesh.update()
    display.refresh_after_color_write(context, mesh, layer_name, obj=obj)
    report_fn(
        {"INFO"},
        tr_format(
            "Mirror copy finished on axis {axis}, direction {direction}, channel {channel_key}, affected {count} entries.",
            axis=axis,
            direction=direction,
            channel_key=channel_key,
            count=count,
        ),
    )
    return {"FINISHED"}


def _execute_mirror(context, axis, direction, report_fn):
    obj = context.active_object
    mesh = obj.data
    channel_key = context.scene.ylvc_channel
    tolerance = context.scene.ylvc_mirror_tolerance

    if obj.mode == "EDIT":
        return _mirror_edit_mode(context, obj, mesh, axis, direction, channel_key, tolerance, report_fn)
    return _mirror_object_mode(context, obj, mesh, axis, direction, channel_key, tolerance, report_fn)


class MESH_OT_YLVCMirrorVertexColors(bpy.types.Operator):
    bl_idname = "mesh.ylvc_mirror_vertex_colors"
    bl_label = "Mirror Color Channel"
    bl_description = "Mirror the active color channel across the chosen axis."
    bl_options = {"REGISTER", "UNDO"}

    axis: bpy.props.EnumProperty(
        items=(("X", "X", ""), ("Y", "Y", ""), ("Z", "Z", "")),
    )
    direction: bpy.props.EnumProperty(
        items=(("POS_TO_NEG", "+ to -", ""), ("NEG_TO_POS", "- to +", "")),
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and obj.mode in {"EDIT", "OBJECT"}

    def execute(self, context):
        return _execute_mirror(context, self.axis, self.direction, self.report)


class VIEW3D_OT_YLVCMirrorPicker(bpy.types.Operator):
    bl_idname = "view3d.ylvc_mirror_picker"
    bl_label = "Start Mirror"
    bl_description = "Pick a mirror target side directly in the 3D View."
    bl_options = {"REGISTER", "UNDO"}

    shaft_half_width = 6.0
    head_length = 23.1
    head_half_width = None
    screen_arrow_length = 170.0
    axis_shaft_scale = 0.25
    axis_head_scale = 0.825

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (
            context.area is not None
            and context.area.type == "VIEW_3D"
            and obj is not None
            and obj.type == "MESH"
            and obj.mode in {"OBJECT", "EDIT"}
        )

    @staticmethod
    def _navigation_event_types():
        return {
            "MIDDLEMOUSE",
            "WHEELUPMOUSE",
            "WHEELDOWNMOUSE",
            "WHEELINMOUSE",
            "WHEELOUTMOUSE",
            "TRACKPADPAN",
            "TRACKPADZOOM",
            "MOUSEROTATE",
            "NDOF_MOTION",
            "NDOF_BUTTON_MENU",
            "NDOF_BUTTON_FIT",
        }

    def _get_origin_and_axes(self, obj):
        origin = obj.matrix_world.translation.copy()
        orientation = obj.matrix_world.to_quaternion()
        return origin, {name: (orientation @ axis).normalized() for name, axis in AXIS_VECTORS.items()}

    def _get_handle_length(self, obj):
        size = max(obj.dimensions.x, obj.dimensions.y, obj.dimensions.z)
        return max(size * 0.35, 0.25)

    @staticmethod
    def _matrix_bytes(matrix):
        return np.array(matrix, dtype=np.float32).tobytes()

    def _project_handles(self, context, force=False):
        obj = context.active_object
        if obj is None:
            self._screen_handles = {}
            self._projection_key = None
            return

        region = self._region
        rv3d = self._region_data
        projection_key = (
            obj.name,
            region.width,
            region.height,
            self._matrix_bytes(obj.matrix_world),
            self._matrix_bytes(rv3d.perspective_matrix),
        )
        if not force and projection_key == getattr(self, "_projection_key", None):
            return

        origin, world_axes = self._get_origin_and_axes(obj)
        handle_length = self._get_handle_length(obj)

        screen_handles = {}
        center_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, origin)
        if center_2d is None:
            self._screen_handles = {}
            self._projection_key = None
            return

        screen_handles["_CENTER"] = {
            "world": origin,
            "screen": Vector(center_2d),
            "color": (0.92, 0.92, 0.92, 1.0),
        }

        for key, axis_dir in world_axes.items():
            sample_world_pos = origin + axis_dir * handle_length
            sample_screen_pos = view3d_utils.location_3d_to_region_2d(region, rv3d, sample_world_pos)
            if sample_screen_pos is None:
                continue
            sample_vec = Vector(sample_screen_pos) - Vector(center_2d)
            if sample_vec.length <= 1e-5:
                continue
            sample_vec.normalize()
            screen_pos = Vector(center_2d) + sample_vec * self.screen_arrow_length
            screen_handles[key] = {
                "world": sample_world_pos,
                "screen": screen_pos,
                "color": AXIS_CONFIG[key]["color"],
            }

        self._screen_handles = screen_handles
        self._projection_key = projection_key

    def invoke(self, context, event):
        self._area = context.area
        self._region = context.region
        self._region_data = context.region_data
        self._screen_handles = {}
        self._projection_key = None
        self._state = "READY"
        self._drag_mouse = None
        self._active_snap_key = None
        self._current_tolerance = float(getattr(context.scene, "ylvc_mirror_tolerance", 0.0))
        self._original_tolerance = self._current_tolerance
        self._display_tolerance = self._current_tolerance

        self._project_handles(context, force=True)

        self._draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            self._draw_callback,
            (),
            "WINDOW",
            "POST_PIXEL",
        )

        context.window_manager.modal_handler_add(self)
        if context.area:
            context.area.tag_redraw()
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if context.area != self._area:
            self._finish(context)
            return {"CANCELLED"}

        obj = context.active_object
        if obj is None or obj.type != "MESH" or obj.mode not in {"OBJECT", "EDIT"}:
            self._finish(context)
            return {"CANCELLED"}

        if event.type in self._navigation_event_types():
            return {"PASS_THROUGH"}

        if event.type in {"ESC", "RIGHTMOUSE"}:
            context.scene.ylvc_mirror_tolerance = self._original_tolerance
            self._finish(context)
            return {"CANCELLED"}

        if self._state == "READY":
            if event.type == "LEFTMOUSE" and event.value == "PRESS":
                self._state = "DRAGGING"
                self._drag_mouse = (float(event.mouse_region_x), float(event.mouse_region_y))
                self._project_handles(context, force=True)
                self._update_drag_state(context)
                if context.area:
                    context.area.tag_redraw()
                return {"RUNNING_MODAL"}
            if event.type in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
                return {"RUNNING_MODAL"}
            return {"RUNNING_MODAL"}

        if self._state == "DRAGGING" and event.type in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
            self._drag_mouse = (float(event.mouse_region_x), float(event.mouse_region_y))
            self._update_drag_state(context)
            if context.area:
                context.area.tag_redraw()
            return {"RUNNING_MODAL"}

        if self._state == "DRAGGING" and event.type == "LEFTMOUSE" and event.value == "RELEASE":
            self._project_handles(context)
            self._drag_mouse = (float(event.mouse_region_x), float(event.mouse_region_y))
            self._update_drag_state(context)
            if not self._active_snap_key:
                context.scene.ylvc_mirror_tolerance = self._original_tolerance
                self._finish(context)
                return {"CANCELLED"}

            context.scene.ylvc_mirror_tolerance = self._current_tolerance
            config = AXIS_CONFIG[self._active_snap_key]
            result = _execute_mirror(context, config["axis"], config["direction"], self.report)
            self._finish(context)
            if "FINISHED" in result:
                return {"FINISHED"}
            return {"CANCELLED"}

        return {"RUNNING_MODAL"}

    def _update_drag_state(self, context):
        center = self._screen_handles.get("_CENTER")
        if center is None or self._drag_mouse is None:
            self._active_snap_key = None
            return

        center_point = Vector(center["screen"])
        drag_point = Vector(self._drag_mouse)
        drag_vec = drag_point - center_point
        drag_length = drag_vec.length
        self._current_tolerance = _drag_distance_to_tolerance(drag_length)
        if abs(self._current_tolerance - self._display_tolerance) > 1e-6:
            context.scene.ylvc_mirror_tolerance = self._current_tolerance
            self._display_tolerance = self._current_tolerance

        if drag_length <= 1e-6:
            self._active_snap_key = None
            return

        drag_dir = drag_vec.normalized()
        best_key = None
        best_dot = MIRROR_AXIS_SNAP_DOT_THRESHOLD

        for key, handle in self._screen_handles.items():
            if key == "_CENTER":
                continue
            axis_vec = Vector(handle["screen"]) - center_point
            if axis_vec.length <= 1e-6:
                continue
            axis_dir = axis_vec.normalized()
            dot = drag_dir.dot(axis_dir)
            if dot > best_dot:
                best_dot = dot
                best_key = key

        self._active_snap_key = best_key

    def _finish(self, context):
        if getattr(self, "_draw_handle", None) is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._draw_handle, "WINDOW")
            self._draw_handle = None
        context.workspace.status_text_set(None)
        if context.area:
            context.area.tag_redraw()

    def _draw_callback(self):
        context = bpy.context
        if getattr(self, "_region", None) is None or getattr(self, "_region_data", None) is None:
            return
        if context.area != self._area:
            return
        if context.region is None or context.region_data is None:
            return

        self._region = context.region
        self._region_data = context.region_data
        self._project_handles(context)

        if not self._screen_handles:
            return

        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        gpu.state.blend_set("ALPHA")

        center = self._screen_handles.get("_CENTER")
        if center is None:
            return

        center_point = Vector(center["screen"])
        active_pair = None
        if self._active_snap_key:
            for positive_key, negative_key in AXIS_PAIRS:
                if self._active_snap_key in {positive_key, negative_key}:
                    active_pair = (positive_key, negative_key)
                    break

        for positive_key, negative_key in AXIS_PAIRS:
            positive_handle = self._screen_handles.get(positive_key)
            negative_handle = self._screen_handles.get(negative_key)
            if positive_handle is None or negative_handle is None:
                continue

            pair_active = self._active_snap_key in {positive_key, negative_key}
            if pair_active:
                active_key = self._active_snap_key
                passive_key = OPPOSITE_KEYS[active_key]
                active_handle = self._screen_handles.get(active_key)
                passive_handle = self._screen_handles.get(passive_key)
                if active_handle is None or passive_handle is None:
                    continue

                active_color = active_handle["color"]
                active_color = (
                    min(active_color[0] + 0.2, 1.0),
                    min(active_color[1] + 0.2, 1.0),
                    min(active_color[2] + 0.2, 1.0),
                    1.0,
                )
                active_shaft_half_width = self.shaft_half_width * self.axis_shaft_scale
                passive_color = _dim_color(passive_handle["color"])
                _draw_arrow_without_head(
                    shader,
                    center_point,
                    Vector(active_handle["screen"]),
                    active_color,
                    shaft_half_width=active_shaft_half_width,
                    head_length=self.head_length * self.axis_head_scale,
                    head_half_width=self.head_half_width,
                )
                _draw_arrow_without_head(
                    shader,
                    center_point,
                    Vector(passive_handle["screen"]),
                    passive_color,
                    shaft_half_width=self.shaft_half_width * self.axis_shaft_scale,
                    head_length=self.head_length * self.axis_head_scale,
                    head_half_width=self.head_half_width,
                )
            else:
                for key in (positive_key, negative_key):
                    handle = self._screen_handles[key]
                    color = handle["color"]
                    if active_pair is None:
                        color = _with_alpha(color, 0.5)
                    elif active_pair != (positive_key, negative_key):
                        color = _dim_color(color)
                    _draw_line_shape(
                        shader,
                        center_point,
                        Vector(handle["screen"]),
                        color,
                        shaft_half_width=self.shaft_half_width * self.axis_shaft_scale,
                    )

        if self._state == "DRAGGING" and self._drag_mouse is not None:
            drag_point = Vector(self._drag_mouse)
            line_end = drag_point
            line_color = (0.85, 0.85, 0.85, 0.9)
            line_half_width = max(self.shaft_half_width * 0.25, 1.0)
            drag_radius = (drag_point - center_point).length
            if self._active_snap_key:
                active_handle = self._screen_handles.get(self._active_snap_key)
                if active_handle is not None:
                    axis_dir = Vector(active_handle["screen"]) - center_point
                    if axis_dir.length > 1e-6:
                        axis_dir.normalize()
                        drag_length = max(drag_radius, MIRROR_DRAG_ZERO_SNAP_RADIUS)
                        line_end = center_point + axis_dir * drag_length
                        line_color = AXIS_CONFIG[self._active_snap_key]["color"]
            if self._active_snap_key:
                _draw_arrow_shape(
                    shader,
                    center_point,
                    line_end,
                    line_color,
                    shaft_half_width=line_half_width,
                    head_length=self.head_length * self.axis_head_scale,
                    head_half_width=self.head_half_width,
                )
            else:
                _draw_line_shape(
                    shader,
                    center_point,
                    line_end,
                    line_color,
                    shaft_half_width=line_half_width,
                )

        _draw_circle_2d(shader, center_point, 2.5, (1.0, 1.0, 1.0, 1.0))

        gpu.state.blend_set("NONE")


CLASSES = (
    MESH_OT_YLVCMirrorVertexColors,
    VIEW3D_OT_YLVCMirrorPicker,
)
