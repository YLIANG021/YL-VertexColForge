#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate the local extension tree before release packaging."""

from __future__ import annotations

import ast
import compileall
import importlib.util
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ID = "yl_vertexcolforge"
BLENDER_EXE = Path(r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe")

REQUIRED_FILES = (
    "blender_manifest.toml",
    "__init__.py",
    "LICENSE",
    "assets/VertexDisplay.blend",
)

FORBIDDEN_FILE_SUFFIXES = (
    ".log",
    ".pyc",
    ".pyo",
    ".tmp",
    ".bak",
    ".blend1",
    ".blend2",
)

FORBIDDEN_ROOT_FILES = (
    "VertexDisplay.blend",
)

IGNORED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
}

IGNORED_FILE_NAMES = {
    ".DS_Store",
    "Thumbs.db",
}

REQUIRED_MANIFEST_FIELDS = (
    "schema_version",
    "id",
    "version",
    "name",
    "tagline",
    "maintainer",
    "type",
    "license",
    "blender_version_min",
    "tags",
)

AUDITED_BPY_OPS = {
    "core/mode_session.py": {
        "bpy.ops.object.mode_set",
        "bpy.ops.object.select_all",
    },
    "services/display.py": {
        "bpy.ops.mesh.ylvc_toggle_preview",
    },
    "features/baking/ops_bake_ao.py": {
        "bpy.ops.object.bake",
    },
    "features/transfer/ops_texture.py": {
        "bpy.ops.object.bake",
    },
    "features/transfer/ops_mesh_transfer.py": {
        "bpy.ops.object.data_transfer",
    },
}

WRITE_ENGINE_MIGRATED_MODULES = {
    "features/adjustments/ops_color_adjust.py",
    "features/baking/ops_bake_ao.py",
    "features/baking/ops_curvature_map.py",
    "features/baking/ops_gradient_map.py",
    "features/color/ops_channel.py",
    "features/color/ops_layer.py",
    "features/color/ops_mirror.py",
    "features/color/ops_random.py",
    "features/gradients/ops_gradient_uv.py",
    "features/transfer/ops_mesh_transfer.py",
    "features/transfer/ops_texture.py",
    "features/transfer/ops_weight.py",
}

RAW_COLOR_WRITE_ALLOWED = {
    "core/color_attribute.py",
}

DIRECT_COLOR_WRITE_ALLOWED = {
    "core/write_engine.py",
}

SOURCE_CHANNEL_ALLOWED = {
    "core/channel_sampling.py",
    "properties/scene.py",
    "properties/state.py",
    "ui/sections/channel.py",
    "ui/sections/transfer.py",
}

DOMAIN_MAPPING_ALLOWED = {
    "core/color_attribute.py",
    "core/domain_mapping.py",
}

DIRECT_REFRESH_ALLOWED = {
    "services/display.py",
    "features/color/ops_preview.py",
}

TRANSACTION_BOUNDARY_ALLOWED = {
    "core/mode_session.py",
    "services/session.py",
    "services/transactions.py",
}

TEMP_STATE_DIRECT_ALLOWED = {
    "core/mode_session.py",
    "services/transactions.py",
}


@dataclass
class Reporter:
    failures: list[str]
    warnings: list[str]

    def pass_(self, message: str) -> None:
        print(f"PASS {message}")

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        print(f"WARN {message}")

    def fail(self, message: str) -> None:
        self.failures.append(message)
        print(f"FAIL {message}")


def iter_files(root: Path):
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if any(part in IGNORED_DIRS for part in rel.parts):
            continue
        if "__pycache__" in rel.parts:
            continue
        if path.is_file():
            yield path


def iter_dirs(root: Path):
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if any(part in IGNORED_DIRS for part in rel.parts):
            continue
        if path.is_dir():
            yield path


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_manifest(reporter: Reporter) -> dict:
    manifest_path = ROOT / "blender_manifest.toml"
    if not manifest_path.exists():
        reporter.fail("blender_manifest.toml is missing")
        return {}
    try:
        data = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        reporter.fail(f"blender_manifest.toml could not be parsed: {exc}")
        return {}
    reporter.pass_("manifest parses as TOML")
    return data


def check_required_files(reporter: Reporter) -> None:
    for item in REQUIRED_FILES:
        path = ROOT / item
        if path.exists():
            reporter.pass_(f"required file exists: {item}")
        else:
            reporter.fail(f"required file missing: {item}")


def check_forbidden_artifacts(reporter: Reporter) -> None:
    for item in FORBIDDEN_ROOT_FILES:
        if (ROOT / item).exists():
            reporter.fail(f"forbidden root file exists: {item}")
        else:
            reporter.pass_(f"forbidden root file absent: {item}")

    for path in iter_files(ROOT):
        if path.name in IGNORED_FILE_NAMES:
            reporter.fail(f"forbidden system file: {rel(path)}")
            continue
        if path.suffix.lower() in FORBIDDEN_FILE_SUFFIXES:
            reporter.fail(f"forbidden generated file: {rel(path)}")

    pycache_dirs = [
        path
        for path in ROOT.rglob("__pycache__")
        if path.is_dir() and not any(part in IGNORED_DIRS for part in path.relative_to(ROOT).parts)
    ]
    if pycache_dirs:
        reporter.warn(f"local __pycache__ directories found and must be excluded from packages: {len(pycache_dirs)}")
    else:
        reporter.pass_("no local __pycache__ directories found")


def check_manifest(data: dict, reporter: Reporter) -> None:
    if not data:
        return

    for field in REQUIRED_MANIFEST_FIELDS:
        if field in data:
            reporter.pass_(f"manifest field present: {field}")
        else:
            reporter.fail(f"manifest field missing: {field}")

    if data.get("id") != PACKAGE_ID:
        reporter.fail(f"manifest id should be {PACKAGE_ID!r}, got {data.get('id')!r}")

    if data.get("type") != "add-on":
        reporter.fail("manifest type should be 'add-on'")

    version = str(data.get("version", ""))
    if re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9_.-]+)?", version):
        reporter.pass_("manifest version looks semantic")
    else:
        reporter.fail(f"manifest version is not semantic: {version!r}")

    licenses = data.get("license", [])
    if "SPDX:GPL-3.0-or-later" in licenses:
        reporter.pass_("manifest includes GPL-3.0-or-later for add-on code")
    else:
        reporter.fail("manifest license should include SPDX:GPL-3.0-or-later")

    has_assets = (ROOT / "assets").exists() and any((ROOT / "assets").rglob("*"))
    if has_assets and "SPDX:CC0-1.0" in licenses:
        reporter.pass_("manifest includes CC0-1.0 for bundled assets")
    elif has_assets:
        reporter.fail("manifest should include SPDX:CC0-1.0 for bundled assets")

    tagline = str(data.get("tagline", ""))
    if 0 < len(tagline) <= 64 and tagline.isascii():
        reporter.pass_("manifest tagline is short English/ASCII text")
    else:
        reporter.fail("manifest tagline should be non-empty ASCII text no longer than 64 characters")

    tags = data.get("tags", [])
    if isinstance(tags, list) and tags:
        reporter.pass_("manifest tags are present")
    else:
        reporter.fail("manifest tags should be a non-empty list")

    permissions = data.get("permissions", {})
    if permissions:
        for key, reason in permissions.items():
            if isinstance(reason, str) and reason.strip():
                reporter.pass_(f"permission has reason: {key}")
            else:
                reporter.fail(f"permission reason is missing: {key}")


def check_python_compile(reporter: Reporter) -> None:
    ok = compileall.compile_dir(str(ROOT), quiet=1, maxlevels=20)
    if ok:
        reporter.pass_("Python files compile")
    else:
        reporter.fail("Python compile failed")


def check_operator_poll(reporter: Reporter) -> None:
    missing = []
    for path in iter_files(ROOT):
        if path.suffix != ".py":
            continue
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except UnicodeDecodeError:
            reporter.fail(f"Python file is not UTF-8: {rel(path)}")
            continue
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            base_names = {base_name(base) for base in node.bases}
            if "bpy.types.Operator" not in base_names and "Operator" not in base_names:
                continue
            has_poll = any(isinstance(item, ast.FunctionDef) and item.name == "poll" for item in node.body)
            if not has_poll:
                missing.append(f"{rel(path)}:{node.lineno} {node.name}")

    if missing:
        for item in missing:
            reporter.fail(f"operator missing poll(): {item}")
    else:
        reporter.pass_("all operator classes define poll()")


def base_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = base_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def check_forbidden_code_patterns(reporter: Reporter) -> None:
    forbidden_calls = {"eval", "exec"}
    found = []

    for path in iter_files(ROOT):
        if path.suffix != ".py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (UnicodeDecodeError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in forbidden_calls:
                found.append(f"{rel(path)}:{node.lineno} {node.func.id}()")

    if found:
        for item in found:
            reporter.fail(f"forbidden dynamic code call: {item}")
    else:
        reporter.pass_("no eval()/exec() calls found")


def full_attribute_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = full_attribute_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def check_bpy_ops_usage(reporter: Reporter) -> None:
    usages = []
    audited_count = 0
    for path in iter_files(ROOT):
        parts = path.relative_to(ROOT).parts
        if path.suffix != ".py" or "scripts" in parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (UnicodeDecodeError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = full_attribute_name(node.func)
                if name.startswith("bpy.ops."):
                    rel_path = rel(path)
                    if name in AUDITED_BPY_OPS.get(rel_path, set()):
                        audited_count += 1
                    else:
                        usages.append(f"{rel_path}:{node.lineno} {name}()")

    if not usages:
        if audited_count:
            reporter.pass_(f"all runtime bpy.ops calls are audited ({audited_count} call(s))")
        else:
            reporter.pass_("no bpy.ops calls found in runtime code")
        return

    reporter.warn(f"bpy.ops usage should be audited for data API replacements: {len(usages)} call(s)")
    for item in usages[:40]:
        print(f"     {item}")
    if len(usages) > 40:
        print(f"     ... {len(usages) - 40} more")


def check_runtime_prints(reporter: Reporter) -> None:
    prints = []
    allowed = {"core/logging.py"}
    for path in iter_files(ROOT):
        if path.suffix != ".py":
            continue
        parts = path.relative_to(ROOT).parts
        if "scripts" in parts or "locales" in parts:
            continue
        if rel(path) in allowed:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (UnicodeDecodeError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
                prints.append(f"{rel(path)}:{node.lineno}")

    if not prints:
        reporter.pass_("no runtime print() calls found")
        return

    reporter.warn(f"runtime print() calls should be reviewed for console noise: {len(prints)} call(s)")
    for item in prints[:40]:
        print(f"     {item}")
    if len(prints) > 40:
        print(f"     ... {len(prints) - 40} more")


def check_private_bpy_api(reporter: Reporter) -> None:
    usages = []
    for path in iter_files(ROOT):
        if path.suffix != ".py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (UnicodeDecodeError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            name = full_attribute_name(node)
            if not name.startswith("bpy."):
                continue
            parts = name.split(".")
            if any(part.startswith("_") for part in parts[1:]):
                usages.append(f"{rel(path)}:{node.lineno} {name}")

    if not usages:
        reporter.pass_("no private bpy API usage found")
        return

    reporter.warn(f"potential private bpy API usage should be reviewed: {len(usages)} occurrence(s)")
    for item in usages[:40]:
        print(f"     {item}")
    if len(usages) > 40:
        print(f"     ... {len(usages) - 40} more")


def check_runtime_ascii(reporter: Reporter) -> None:
    non_ascii_files = []
    for path in iter_files(ROOT):
        if path.suffix != ".py":
            continue
        parts = path.relative_to(ROOT).parts
        if "locales" in parts or "scripts" in parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            reporter.fail(f"Python file is not UTF-8: {rel(path)}")
            continue
        if any(ord(char) > 127 for char in text):
            non_ascii_files.append(rel(path))

    if non_ascii_files:
        reporter.warn(f"non-ASCII runtime Python files should be checked for English defaults: {len(non_ascii_files)} file(s)")
        for item in non_ascii_files[:40]:
            print(f"     {item}")
    else:
        reporter.pass_("runtime Python source is ASCII outside locales/scripts")


def check_resource_paths(reporter: Reporter) -> None:
    root_blend = ROOT / "VertexDisplay.blend"
    asset_blend = ROOT / "assets" / "VertexDisplay.blend"
    paths_py = ROOT / "paths.py"
    preview_py = ROOT / "features" / "color" / "ops_preview.py"

    if asset_blend.exists() and not root_blend.exists():
        reporter.pass_("preview blend is stored under assets/")

    if paths_py.exists() and preview_py.exists():
        preview_text = preview_py.read_text(encoding="utf-8")
        if "preview_blend_path" in preview_text:
            reporter.pass_("preview code uses centralized path helper")
        else:
            reporter.fail("preview code should use paths.preview_blend_path()")


def check_centralized_file_paths(reporter: Reporter) -> None:
    offenders = []
    allowed = {
        "paths.py",
        "scripts/build_package.py",
        "scripts/runtime_smoke.py",
        "scripts/validate_package.py",
    }
    for path in iter_files(ROOT):
        if path.suffix != ".py":
            continue
        rel_path = rel(path)
        if rel_path in allowed:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "__file__" in text:
            offenders.append(rel_path)

    if offenders:
        for item in offenders:
            reporter.fail(f"runtime path logic should be centralized in paths.py: {item}")
    else:
        reporter.pass_("runtime __file__ usage is centralized")


def check_migrated_write_engine_usage(reporter: Reporter) -> None:
    offenders = []
    for rel_path in sorted(WRITE_ENGINE_MIGRATED_MODULES):
        path = ROOT / rel_path
        if not path.exists():
            reporter.fail(f"write-engine migrated module missing: {rel_path}")
            continue
        text = path.read_text(encoding="utf-8")
        if "write_color_attribute_colors" in text:
            offenders.append(rel_path)

    if offenders:
        for item in offenders:
            reporter.fail(f"migrated module should use core.write_engine for color writes: {item}")
    else:
        reporter.pass_("migrated color writers use core.write_engine")


def check_color_write_boundaries(reporter: Reporter) -> None:
    raw_offenders = []
    direct_write_offenders = []
    for path in iter_files(ROOT):
        if path.suffix != ".py":
            continue
        if "scripts" in path.relative_to(ROOT).parts:
            continue
        rel_path = rel(path)
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        if 'foreach_set("color"' in text and rel_path not in RAW_COLOR_WRITE_ALLOWED:
            raw_offenders.append(rel_path)
        if "write_color_attribute_colors" in text and rel_path not in RAW_COLOR_WRITE_ALLOWED | DIRECT_COLOR_WRITE_ALLOWED:
            direct_write_offenders.append(rel_path)

    if raw_offenders:
        for item in sorted(set(raw_offenders)):
            reporter.fail(f"raw color foreach_set must stay in core/color_attribute.py: {item}")
    else:
        reporter.pass_("raw color foreach_set is centralized")

    if direct_write_offenders:
        for item in sorted(set(direct_write_offenders)):
            reporter.fail(f"direct write_color_attribute_colors() must use core.write_engine or be audited: {item}")
    else:
        reporter.pass_("direct color attribute writes are centralized")


def check_source_channel_boundaries(reporter: Reporter) -> None:
    offenders = []
    patterns = (
        "_SOURCE_INDEX",
        "SOURCE_CHANNEL_INDEX",
        "source_channel_index",
        "sample_scalar_from_colors",
        "sample_scalar_from_image_pixels",
        "transfer_source_values_for_rgb_target",
    )
    for path in iter_files(ROOT):
        if path.suffix != ".py":
            continue
        if "scripts" in path.relative_to(ROOT).parts:
            continue
        rel_path = rel(path)
        if rel_path in SOURCE_CHANNEL_ALLOWED:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        if "_SOURCE_INDEX" in text:
            offenders.append(f"{rel_path}: local _SOURCE_INDEX")
            continue

        if rel_path.startswith("features/") and any(pattern in text for pattern in patterns):
            if "core.channel_sampling" not in text:
                offenders.append(f"{rel_path}: source channel logic should import core.channel_sampling")

    if offenders:
        for item in sorted(set(offenders)):
            reporter.fail(item)
    else:
        reporter.pass_("source channel logic uses core.channel_sampling")


def check_domain_mapping_boundaries(reporter: Reporter) -> None:
    offenders = []
    patterns = (
        "point_colors_to_corner_colors",
        "corner_colors_to_point_colors",
        "convert_colors_between_domains",
    )
    for path in iter_files(ROOT):
        if path.suffix != ".py":
            continue
        if "scripts" in path.relative_to(ROOT).parts:
            continue
        rel_path = rel(path)
        if rel_path in DOMAIN_MAPPING_ALLOWED:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(pattern in text for pattern in patterns):
            offenders.append(rel_path)

    if offenders:
        for item in sorted(set(offenders)):
            reporter.fail(f"POINT/CORNER conversion should use core.domain_mapping: {item}")
    else:
        reporter.pass_("POINT/CORNER conversions use core.domain_mapping")


def check_refresh_boundaries(reporter: Reporter) -> None:
    offenders = []
    for path in iter_files(ROOT):
        if path.suffix != ".py":
            continue
        if "scripts" in path.relative_to(ROOT).parts:
            continue
        rel_path = rel(path)
        if rel_path in DIRECT_REFRESH_ALLOWED:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if ".update_tag(" in text or "sync_active_layer(" in text:
            offenders.append(rel_path)

    if offenders:
        for item in sorted(set(offenders)):
            reporter.fail(f"color write refresh should use services.display.refresh_after_color_write(): {item}")
    else:
        reporter.pass_("color write refresh uses centralized display helper")


def check_transaction_boundaries(reporter: Reporter) -> None:
    import_offenders = []
    state_offenders = []
    state_patterns = (
        "context.view_layer.objects.active",
        "view_layer.objects.active",
        ".select_set(",
        ".hide_set(",
        ".hide_viewport",
        "render.engine =",
    )
    import_patterns = (
        "services.session",
        "core.mode_session",
        "from ...services import session",
        "from ..services import session",
        "from ...services.session",
        "from ..services.session",
        "from ...core.mode_session",
        "from ..core.mode_session",
    )

    for path in iter_files(ROOT):
        if path.suffix != ".py":
            continue
        if "scripts" in path.relative_to(ROOT).parts:
            continue

        rel_path = rel(path)
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        if rel_path not in TRANSACTION_BOUNDARY_ALLOWED and any(pattern in text for pattern in import_patterns):
            import_offenders.append(rel_path)

        if rel_path.startswith("features/") or rel_path.startswith("services/"):
            if rel_path not in TEMP_STATE_DIRECT_ALLOWED and any(pattern in text for pattern in state_patterns):
                state_offenders.append(rel_path)

    if import_offenders:
        for item in sorted(set(import_offenders)):
            reporter.fail(f"temporary object/mode state should use services.transactions, not session helpers: {item}")
    else:
        reporter.pass_("temporary object/mode imports use services.transactions")

    if state_offenders:
        for item in sorted(set(state_offenders)):
            reporter.fail(f"temporary active/selection/visibility/render state should use services.transactions: {item}")
    else:
        reporter.pass_("temporary active/selection/visibility/render state uses services.transactions")


def run_blender_command(args: list[str], reporter: Reporter, label: str) -> None:
    if not BLENDER_EXE.exists():
        reporter.warn(f"Blender executable not found, skipped {label}: {BLENDER_EXE}")
        return

    command = [str(BLENDER_EXE), "--background", "--factory-startup", *args]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if result.returncode == 0:
        reporter.pass_(label)
        return

    reporter.fail(f"{label} failed with exit code {result.returncode}")
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    if stdout:
        print(stdout[-2000:])
    if stderr:
        print(stderr[-2000:])


def check_blender_import(reporter: Reporter) -> None:
    if not BLENDER_EXE.exists():
        reporter.warn(f"Blender executable not found, skipped import/register check: {BLENDER_EXE}")
        return

    parent = ROOT.parent
    code = f"""
import importlib
import sys
sys.path.insert(0, r'{parent}')
mod = importlib.import_module('{PACKAGE_ID}')
print('IMPORT_OK')
mod.register()
print('REGISTER_OK')
mod.unregister()
print('UNREGISTER_OK')
"""
    run_blender_command(["--python-expr", code], reporter, "Blender import/register/unregister")


def check_blender_preview_resource(reporter: Reporter) -> None:
    if not BLENDER_EXE.exists():
        reporter.warn(f"Blender executable not found, skipped preview resource check: {BLENDER_EXE}")
        return

    parent = ROOT.parent
    code = f"""
import importlib
import sys
sys.path.insert(0, r'{parent}')
mod = importlib.import_module('{PACKAGE_ID}')
mod.register()
try:
    from {PACKAGE_ID}.features.color import ops_preview
    path = ops_preview.preview_blend_path()
    print('PREVIEW_PATH', path)
    node_group = ops_preview.load_preview_node_group()
    print('NODE_GROUP_OK', bool(node_group))
    if not node_group:
        raise SystemExit(2)
finally:
    mod.unregister()
"""
    run_blender_command(["--python-expr", code], reporter, "Blender preview resource load")


def check_blender_empty_scene_register(reporter: Reporter) -> None:
    if not BLENDER_EXE.exists():
        reporter.warn(f"Blender executable not found, skipped empty scene register check: {BLENDER_EXE}")
        return

    parent = ROOT.parent
    code = f"""
import importlib
import sys
import bpy
sys.path.insert(0, r'{parent}')
for obj in tuple(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
mod = importlib.import_module('{PACKAGE_ID}')
mod.register()
print('EMPTY_SCENE_REGISTER_OK')
mod.unregister()
"""
    run_blender_command(["--python-expr", code], reporter, "Blender empty-scene register/unregister")


def check_blender_operator_poll_smoke(reporter: Reporter) -> None:
    if not BLENDER_EXE.exists():
        reporter.warn(f"Blender executable not found, skipped operator poll smoke check: {BLENDER_EXE}")
        return

    parent = ROOT.parent
    operator_ids = [
        "mesh.ylvc_ensure_color_layer",
        "mesh.ylvc_remove_color_layer",
        "mesh.ylvc_random_fill",
        "mesh.ylvc_channel_mixer",
        "mesh.ylvc_toggle_preview",
        "mesh.vcm_bake_ao_gpu",
        "mesh.ylvc_texture_to_color",
        "mesh.ylvc_color_to_texture",
        "mesh.ylvc_color_to_weights",
        "mesh.ylvc_weights_to_color",
        "mesh.ylvc_transfer_mesh_colors",
        "mesh.ylvc_pick_select_value",
        "image.ylvc_test_gradient",
    ]
    code = f"""
import importlib
import sys
import bpy
sys.path.insert(0, r'{parent}')
mod = importlib.import_module('{PACKAGE_ID}')
mod.register()
try:
    for obj in tuple(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for op_id in {operator_ids!r}:
        group_name, op_name = op_id.split('.', 1)
        op = getattr(getattr(bpy.ops, group_name), op_name)
        try:
            op.poll()
        except Exception as exc:
            raise RuntimeError(f'poll failed for {{op_id}} in empty scene: {{exc}}')

    mesh = bpy.data.meshes.new('YLVC_PollSmokeMesh')
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    mesh.update()
    obj = bpy.data.objects.new('YLVC_PollSmokeObject', mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    for op_id in {operator_ids!r}:
        group_name, op_name = op_id.split('.', 1)
        op = getattr(getattr(bpy.ops, group_name), op_name)
        try:
            op.poll()
        except Exception as exc:
            raise RuntimeError(f'poll failed for {{op_id}} without color attribute: {{exc}}')
    print('OPERATOR_POLL_SMOKE_OK')
finally:
    mod.unregister()
"""
    run_blender_command(["--python-expr", code], reporter, "Blender operator poll smoke")


def check_blender_runtime_smoke(reporter: Reporter) -> None:
    script_path = ROOT / "scripts" / "runtime_smoke.py"
    if not script_path.exists():
        reporter.fail("runtime smoke script is missing: scripts/runtime_smoke.py")
        return

    run_blender_command(
        [
            "--python",
            str(script_path),
            "--",
            "--package-id",
            PACKAGE_ID,
            "--package-parent",
            str(ROOT.parent),
        ],
        reporter,
        "Blender runtime operator smoke",
    )


def check_blender_extension_validate(reporter: Reporter) -> None:
    run_blender_command(["--command", "extension", "validate", str(ROOT)], reporter, "Blender extension validate")


def main() -> int:
    reporter = Reporter(failures=[], warnings=[])

    print(f"Validating: {ROOT}")
    check_required_files(reporter)
    manifest = load_manifest(reporter)
    check_manifest(manifest, reporter)
    check_forbidden_artifacts(reporter)
    check_resource_paths(reporter)
    check_centralized_file_paths(reporter)
    check_migrated_write_engine_usage(reporter)
    check_color_write_boundaries(reporter)
    check_source_channel_boundaries(reporter)
    check_domain_mapping_boundaries(reporter)
    check_refresh_boundaries(reporter)
    check_transaction_boundaries(reporter)
    check_python_compile(reporter)
    check_operator_poll(reporter)
    check_forbidden_code_patterns(reporter)
    check_bpy_ops_usage(reporter)
    check_runtime_prints(reporter)
    check_private_bpy_api(reporter)
    check_runtime_ascii(reporter)
    check_blender_import(reporter)
    check_blender_empty_scene_register(reporter)
    check_blender_operator_poll_smoke(reporter)
    check_blender_runtime_smoke(reporter)
    check_blender_preview_resource(reporter)
    check_blender_extension_validate(reporter)

    print()
    print(f"Summary: {len(reporter.failures)} failure(s), {len(reporter.warnings)} warning(s)")
    if reporter.failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
