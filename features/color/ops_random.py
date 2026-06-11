# -*- coding: utf-8 -*-
import math

import bmesh
import bpy
import numpy as np

from ...i18n import tr, tr_format
from ... import utils
from ...core.color_attribute import read_color_attribute_colors
from ...core.context import resolve_polygon_auto_mask_for_object, resolve_target_color_attribute, resolve_vertex_auto_mask_for_object, resolve_loop_auto_mask_for_object
from ...core.operator_poll import active_mesh_has_color_attributes
from ...core.write_engine import blend_source_values_into_colors, write_color_array_to_attribute
from ...services import display, transactions


def _resolve_random_group(obj, group_name):
    clean_name = (group_name or "").strip()
    if clean_name:
        group = obj.vertex_groups.get(clean_name)
        if group is not None:
            return group

    active_index = getattr(obj.vertex_groups, "active_index", -1)
    if 0 <= active_index < len(obj.vertex_groups):
        return obj.vertex_groups[active_index]

    return obj.vertex_groups[0] if obj.vertex_groups else None


def _vertex_group_weights(obj, group):
    return utils.get_vertex_group_weights(obj, group, vertex_count=len(obj.data.vertices))


def _expand_face_loop_indices(loops_start, loops_total, face_indices):
    face_indices = np.asarray(face_indices, dtype=np.int32).reshape(-1)
    if face_indices.size == 0:
        return np.empty(0, dtype=np.int32)

    starts = loops_start[face_indices]
    totals = loops_total[face_indices]
    total_loop_count = int(np.sum(totals))
    if total_loop_count <= 0:
        return np.empty(0, dtype=np.int32)

    chunk_offsets = np.cumsum(np.r_[0, totals[:-1]], dtype=np.int32)
    local_offsets = np.arange(total_loop_count, dtype=np.int32) - np.repeat(chunk_offsets, totals)
    return np.repeat(starts, totals) + local_offsets


def _assign_last_group_ids(target_size, indices, values):
    group_ids = np.full(target_size, -1, dtype=np.int32)
    if target_size <= 0:
        return group_ids

    indices = np.asarray(indices, dtype=np.int32).reshape(-1)
    values = np.asarray(values, dtype=np.int32).reshape(-1)
    if indices.size == 0:
        return group_ids

    rev_indices = indices[::-1]
    rev_values = values[::-1]
    unique_indices, first_rev_positions = np.unique(rev_indices, return_index=True)
    group_ids[unique_indices] = rev_values[first_rev_positions]
    return group_ids


def _flatten_island_faces(islands):
    face_chunks = []
    group_chunks = []
    for group_id, island_faces in enumerate(islands):
        if not island_faces:
            continue
        island_faces_arr = np.asarray(island_faces, dtype=np.int32)
        face_chunks.append(island_faces_arr)
        group_chunks.append(np.full(island_faces_arr.size, group_id, dtype=np.int32))

    if not face_chunks:
        return np.empty(0, dtype=np.int32), np.empty(0, dtype=np.int32)

    return np.concatenate(face_chunks), np.concatenate(group_chunks)


class MESH_OT_YLVCRandomFill(bpy.types.Operator):
    bl_idname = "mesh.ylvc_random_fill"
    bl_label = "Random Fill"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return active_mesh_has_color_attributes(context)

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({"WARNING"}, tr("Active object must be a mesh."))
            return {"CANCELLED"}

        mesh = obj.data
        scene = context.scene

        mode = scene.ylvc_random_mode
        channel = scene.ylvc_channel

        if mode == "UV_ISLAND" and not mesh.uv_layers.active:
            self.report({"WARNING"}, tr("No active UV map found."))
            return {"CANCELLED"}

        if mode == "VERTEX_GROUP" and len(obj.vertex_groups) == 0:
            self.report({"WARNING"}, tr("No vertex groups found."))
            return {"CANCELLED"}

        with transactions.CleanupStack() as cleanup:
            cleanup.push_object_context(context)
            transactions.ensure_object_mode_for(context, obj)
            target, error = resolve_target_color_attribute(context)
            if error:
                self.report({"WARNING"}, error)
                return {"CANCELLED"}
            attribute = target.color_attr
            layer_name = target.layer_name

            if mode in {"FACE", "UV_ISLAND", "ANGLE_ISLAND"} and attribute.domain == "POINT":
                self.report({"WARNING"}, tr("This random mode requires a Face Corner color attribute."))
                return {"CANCELLED"}

            try:
                group_ids, data_count, label = self._build_group_ids(context, attribute, mode)
            except RuntimeError as exc:
                self.report({"WARNING"}, str(exc))
                return {"CANCELLED"}
            if group_ids is None:
                return {"CANCELLED"}

            colors = read_color_attribute_colors(mesh, attribute)

            valid_mask = group_ids >= 0
            if not np.any(valid_mask):
                self.report({"WARNING"}, tr("No valid targets found for current selection."))
                return {"CANCELLED"}

            valid_group_ids = group_ids[valid_mask]
            unique_groups, inverse = np.unique(valid_group_ids, return_inverse=True)
            group_count = len(unique_groups)

            if channel == "RGB":
                random_values = np.random.rand(group_count, 3).astype(np.float32)[inverse]
            else:
                random_gray = np.random.rand(group_count).astype(np.float32)
                random_values = random_gray[inverse]

            blend_source_values_into_colors(colors, random_values, channel, "REPLACE", valid_mask)
            write_color_array_to_attribute(attribute, colors, mesh=mesh)
            display.refresh_after_color_write(context, mesh, layer_name, obj=obj)

            self.report({"INFO"}, tr_format("Successfully filled {count} {label}.", count=group_count, label=label))
            return {"FINISHED"}

    def _build_group_ids(self, context, attribute, mode):
        obj = context.active_object
        mesh = obj.data

        if mode == "FACE":
            group_ids, data_count = self._build_per_face_group_map(mesh, attribute.domain)
            return group_ids, data_count, tr("faces")

        if mode == "VERTEX":
            group_ids, data_count = self._build_per_vertex_group_map(context, attribute.domain)
            return group_ids, data_count, tr("vertices")

        if mode in {"CONNECTED", "UV_ISLAND", "SHARP_EDGE", "ANGLE_ISLAND"}:
            islands = self._collect_face_groups(mesh, mode)
            if not islands:
                self.report({"WARNING"}, tr("No polygons found for current selection."))
                return None, None, None

            group_ids, data_count = self._build_face_group_index_map(mesh, islands, attribute.domain)
            label = tr("independent elements")
            if mode == "SHARP_EDGE":
                label = tr("sharp-edge islands")
            elif mode == "UV_ISLAND":
                label = tr("UV islands")
            elif mode == "ANGLE_ISLAND":
                label = tr("angle islands")
            return group_ids, data_count, label

        if mode == "MATERIAL":
            group_ids, data_count = self._build_material_group_map(mesh, attribute.domain)
            return group_ids, data_count, tr("material groups")

        if mode == "VERTEX_GROUP":
            group_ids, data_count = self._build_vertex_group_map(context, attribute.domain)
            return group_ids, data_count, tr("vertex group buckets")

        self.report({"WARNING"}, tr_format("Unsupported random mode: {mode}", mode=mode))
        return None, None, None

    def _collect_face_groups(self, mesh, mode):
        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            bm.normal_update()
            bm.faces.ensure_lookup_table()
            uv_layer = bm.loops.layers.uv.active if mode == "UV_ISLAND" else None
            angle_threshold = float(getattr(bpy.context.scene, "ylvc_random_angle_threshold", math.radians(45.0)))
            angle_cos_threshold = math.cos(max(0.0, min(math.pi, angle_threshold)))

            use_selection = utils.bm_use_face_selection(bm)

            def in_scope(face):
                return utils.bm_face_in_auto_scope(face, use_selection)

            face_loop_lookup = self._build_face_loop_lookup(bm.faces, uv_layer, in_scope)

            visited = np.zeros(len(bm.faces), dtype=bool)
            islands = []

            for face in bm.faces:
                if visited[face.index] or not in_scope(face):
                    continue

                island = []
                stack = [face]
                visited[face.index] = True

                while stack:
                    current = stack.pop()
                    island.append(current.index)

                    for edge in current.edges:
                        if mode == "SHARP_EDGE" and not edge.smooth:
                            continue

                        for linked_face in edge.link_faces:
                            if visited[linked_face.index] or not in_scope(linked_face):
                                continue
                            if mode == "ANGLE_ISLAND" and current.normal.dot(linked_face.normal) < angle_cos_threshold:
                                continue
                            if mode == "UV_ISLAND" and not self._uv_edge_connected(
                                edge,
                                current,
                                linked_face,
                                uv_layer,
                                face_loop_lookup,
                            ):
                                continue
                            visited[linked_face.index] = True
                            stack.append(linked_face)

                islands.append(island)

            return islands
        finally:
            bm.free()

    @staticmethod
    def _build_face_loop_lookup(faces, uv_layer, in_scope):
        if uv_layer is None:
            return None

        return {
            face.index: {loop.vert.index: loop for loop in face.loops}
            for face in faces
            if in_scope(face)
        }

    @staticmethod
    def _uv_edge_connected(edge, face_a, face_b, uv_layer, face_loop_lookup=None, tolerance=1e-4):
        if uv_layer is None:
            return True

        v1_index = edge.verts[0].index
        v2_index = edge.verts[1].index

        a_loops = face_loop_lookup.get(face_a.index) if face_loop_lookup else None
        b_loops = face_loop_lookup.get(face_b.index) if face_loop_lookup else None

        a_v1 = a_loops.get(v1_index) if a_loops else None
        a_v2 = a_loops.get(v2_index) if a_loops else None
        b_v1 = b_loops.get(v1_index) if b_loops else None
        b_v2 = b_loops.get(v2_index) if b_loops else None

        if not (a_v1 and a_v2 and b_v1 and b_v2):
            return False

        return (
            (a_v1[uv_layer].uv - b_v1[uv_layer].uv).length <= tolerance
            and (a_v2[uv_layer].uv - b_v2[uv_layer].uv).length <= tolerance
        )

    @staticmethod
    def _build_face_group_index_map(mesh, islands, domain):
        poly_count = len(mesh.polygons)
        loops_start = np.empty(poly_count, dtype=np.int32)
        loops_total = np.empty(poly_count, dtype=np.int32)
        mesh.polygons.foreach_get("loop_start", loops_start)
        mesh.polygons.foreach_get("loop_total", loops_total)
        face_indices, face_group_values = _flatten_island_faces(islands)

        if domain == "CORNER":
            loop_count = len(mesh.loops)
            loop_group_id = np.full(loop_count, -1, dtype=np.int32)
            loop_indices = _expand_face_loop_indices(loops_start, loops_total, face_indices)
            if loop_indices.size > 0:
                loop_group_id[loop_indices] = np.repeat(face_group_values, loops_total[face_indices])
            return loop_group_id, loop_count

        if domain == "POINT":
            vert_count = len(mesh.vertices)
            loop_vert_indices = np.empty(len(mesh.loops), dtype=np.int32)
            mesh.loops.foreach_get("vertex_index", loop_vert_indices)
            loop_indices = _expand_face_loop_indices(loops_start, loops_total, face_indices)
            loop_group_values = np.repeat(face_group_values, loops_total[face_indices]) if loop_indices.size > 0 else np.empty(0, dtype=np.int32)
            vert_group_id = _assign_last_group_ids(vert_count, loop_vert_indices[loop_indices], loop_group_values)
            return vert_group_id, vert_count

        raise ValueError(f"Unsupported color domain: {domain}")

    @staticmethod
    def _build_per_face_group_map(mesh, domain):
        poly_count = len(mesh.polygons)
        poly_mask = resolve_polygon_auto_mask_for_object(bpy.context.active_object)
        face_indices = np.flatnonzero(poly_mask).astype(np.int32, copy=False)
        loops_start = np.empty(poly_count, dtype=np.int32)
        loops_total = np.empty(poly_count, dtype=np.int32)
        mesh.polygons.foreach_get("loop_start", loops_start)
        mesh.polygons.foreach_get("loop_total", loops_total)

        if domain == "CORNER":
            loop_count = len(mesh.loops)
            loop_group_id = np.full(loop_count, -1, dtype=np.int32)
            loop_indices = _expand_face_loop_indices(loops_start, loops_total, face_indices)
            if loop_indices.size > 0:
                loop_group_id[loop_indices] = np.repeat(face_indices, loops_total[face_indices])
            return loop_group_id, loop_count

        raise ValueError(f"Unsupported color domain: {domain}")

    @staticmethod
    def _build_per_vertex_group_map(context, domain):
        obj = context.active_object
        mesh = obj.data
        vertex_mask = resolve_vertex_auto_mask_for_object(obj, use_live_edit=False)

        if domain == "POINT":
            group_ids = np.full(len(mesh.vertices), -1, dtype=np.int32)
            group_ids[vertex_mask] = np.flatnonzero(vertex_mask).astype(np.int32, copy=False)
            return group_ids, len(mesh.vertices)

        if domain == "CORNER":
            loop_count = len(mesh.loops)
            loop_vert_indices = np.empty(loop_count, dtype=np.int32)
            mesh.loops.foreach_get("vertex_index", loop_vert_indices)
            loop_mask = resolve_loop_auto_mask_for_object(obj, loop_vert_indices, use_live_edit=False)
            group_ids = np.full(loop_count, -1, dtype=np.int32)
            group_ids[loop_mask] = loop_vert_indices[loop_mask]
            return group_ids, loop_count

        raise ValueError(f"Unsupported color domain: {domain}")

    @staticmethod
    def _build_material_group_map(mesh, domain):
        poly_count = len(mesh.polygons)
        poly_mask = resolve_polygon_auto_mask_for_object(bpy.context.active_object)
        material_indices = np.empty(poly_count, dtype=np.int32)
        mesh.polygons.foreach_get("material_index", material_indices)
        face_indices = np.flatnonzero(poly_mask).astype(np.int32, copy=False)
        loops_start = np.empty(poly_count, dtype=np.int32)
        loops_total = np.empty(poly_count, dtype=np.int32)
        mesh.polygons.foreach_get("loop_start", loops_start)
        mesh.polygons.foreach_get("loop_total", loops_total)

        if domain == "CORNER":
            loop_count = len(mesh.loops)
            loop_group_id = np.full(loop_count, -1, dtype=np.int32)
            loop_indices = _expand_face_loop_indices(loops_start, loops_total, face_indices)
            if loop_indices.size > 0:
                loop_group_id[loop_indices] = np.repeat(material_indices[face_indices], loops_total[face_indices])
            return loop_group_id, loop_count

        if domain == "POINT":
            vert_count = len(mesh.vertices)
            loop_vert_indices = np.empty(len(mesh.loops), dtype=np.int32)
            mesh.loops.foreach_get("vertex_index", loop_vert_indices)
            loop_indices = _expand_face_loop_indices(loops_start, loops_total, face_indices)
            loop_group_values = np.repeat(material_indices[face_indices], loops_total[face_indices]) if loop_indices.size > 0 else np.empty(0, dtype=np.int32)
            vert_group_id = _assign_last_group_ids(vert_count, loop_vert_indices[loop_indices], loop_group_values)
            return vert_group_id, vert_count

        raise ValueError(f"Unsupported color domain: {domain}")

    @staticmethod
    def _build_vertex_group_map(context, domain):
        obj = context.active_object
        mesh = obj.data
        scene = context.scene
        group = _resolve_random_group(obj, getattr(scene, "ylvc_random_vertex_group", ""))
        if group is None:
            raise RuntimeError("No vertex group found.")

        weights = _vertex_group_weights(obj, group)
        vertex_mask = resolve_vertex_auto_mask_for_object(obj, use_live_edit=False)
        quantized = np.floor(np.clip(weights, 0.0, 1.0) * 255.0 + 0.5).astype(np.int32)

        if domain == "POINT":
            group_ids = np.full(len(mesh.vertices), -1, dtype=np.int32)
            group_ids[vertex_mask] = quantized[vertex_mask]
            return group_ids, len(mesh.vertices)

        if domain == "CORNER":
            loop_count = len(mesh.loops)
            loop_vert_indices = np.empty(loop_count, dtype=np.int32)
            mesh.loops.foreach_get("vertex_index", loop_vert_indices)
            loop_mask = resolve_loop_auto_mask_for_object(obj, loop_vert_indices, use_live_edit=False)
            group_ids = np.full(loop_count, -1, dtype=np.int32)
            group_ids[loop_mask] = quantized[loop_vert_indices[loop_mask]]
            return group_ids, loop_count

        raise ValueError(f"Unsupported color domain: {domain}")


CLASSES = (MESH_OT_YLVCRandomFill,)
