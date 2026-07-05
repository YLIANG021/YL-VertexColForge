from ..core.color_attribute import set_active_color_attribute, set_scene_selected_color_attribute_name


def _update_mesh_tag(mesh):
    if mesh is None:
        return
    try:
        mesh.update_tag()
    except Exception:
        pass


def _find_object_for_mesh(context, mesh):
    if mesh is None:
        return None

    active_obj = getattr(context, "active_object", None)
    if active_obj is not None and active_obj.type == "MESH" and active_obj.data == mesh:
        return active_obj

    scene = getattr(context, "scene", None)
    if scene is None:
        return None

    for obj in scene.objects:
        if obj.type == "MESH" and obj.data == mesh:
            return obj
    return None


def sync_active_layer(mesh, layer_name, context=None, source_colors=None, defer_preview_sync=False, force_preview_sync=False):
    if not layer_name:
        return
    if context is not None:
        try:
            from ..features.color import ops_preview
            if ops_preview.is_native_preview_enabled(context):
                scene = getattr(context, "scene", None)
                channel = getattr(scene, "ylvc_channel", "RGB")
                should_defer = defer_preview_sync and channel == "RGB"
                if should_defer and ops_preview.defer_sync_preview_color_layer_for_context(
                    layer_name,
                    context=context,
                    source_colors=source_colors,
                ):
                    return
                if ops_preview.sync_preview_color_layer_for_context(
                    layer_name,
                    context=context,
                    source_colors=source_colors,
                    force=force_preview_sync,
                ):
                    return
        except Exception:
            pass
    set_active_color_attribute(mesh, layer_name)


def refresh_after_color_write(
    context,
    mesh,
    layer_name,
    obj=None,
    ensure_preview=True,
    force_view_update=False,
    source_colors=None,
    mesh_updated=False,
    defer_preview_sync=False,
):
    if obj is None:
        obj = _find_object_for_mesh(context, mesh)

    _update_mesh_tag(mesh)
    try:
        set_scene_selected_color_attribute_name(getattr(context, "scene", None), layer_name)
    except Exception:
        pass

    preview_enabled = False
    try:
        from ..features.color import ops_preview
        preview_enabled = bool(obj is not None and ops_preview.is_native_preview_enabled(context))
    except Exception:
        preview_enabled = False

    if mesh is not None and not mesh_updated and (force_view_update or ensure_preview or not preview_enabled):
        try:
            mesh.update()
        except Exception:
            pass

    if preview_enabled:
        should_defer_preview = defer_preview_sync or source_colors is not None
        force_preview_sync = True
        sync_active_layer(
            mesh,
            layer_name,
            context=context,
            source_colors=source_colors,
            defer_preview_sync=should_defer_preview,
            force_preview_sync=force_preview_sync,
        )
    else:
        set_active_color_attribute(mesh, layer_name)

    area = getattr(context, "area", None)
    if area:
        try:
            area.tag_redraw()
        except Exception:
            pass


def finish_color_write(
    context,
    mesh,
    layer_name,
    obj=None,
    ensure_preview=True,
    force_view_update=False,
    source_colors=None,
    mesh_updated=False,
    defer_preview_sync=False,
):
    """Finalize a user-visible write to a real color attribute."""
    refresh_after_color_write(
        context,
        mesh,
        layer_name,
        obj=obj,
        ensure_preview=ensure_preview,
        force_view_update=force_view_update,
        source_colors=source_colors,
        mesh_updated=mesh_updated,
        defer_preview_sync=defer_preview_sync,
    )
