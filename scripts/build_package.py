#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a clean Blender extension package."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"
BLENDER_EXE = Path(r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe")

EXCLUDE_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "dist",
}

EXCLUDE_FILE_SUFFIXES = {
    ".log",
    ".pyc",
    ".pyo",
    ".tmp",
    ".bak",
    ".blend1",
    ".blend2",
    ".zip",
}

EXCLUDE_FILE_NAMES = {
    ".DS_Store",
    "Thumbs.db",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--blender",
        default=str(BLENDER_EXE),
        help="Path to Blender executable.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DIST_DIR),
        help="Directory for generated package artifacts.",
    )
    parser.add_argument(
        "--skip-validate",
        action="store_true",
        help="Skip scripts/validate_package.py before building.",
    )
    return parser.parse_args()


def load_manifest() -> dict:
    manifest_path = ROOT / "blender_manifest.toml"
    return tomllib.loads(manifest_path.read_text(encoding="utf-8"))


def should_skip(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(part in EXCLUDE_DIR_NAMES for part in rel.parts):
        return True
    if path.is_file():
        if path.name in EXCLUDE_FILE_NAMES:
            return True
        if path.suffix.lower() in EXCLUDE_FILE_SUFFIXES:
            return True
    return False


def copy_clean_tree(destination: Path) -> None:
    for source in ROOT.rglob("*"):
        if should_skip(source):
            continue

        target = destination / source.relative_to(ROOT)
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def run(command: list[str], cwd: Path) -> None:
    print(" ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def main() -> int:
    args = parse_args()
    blender = Path(args.blender)
    output_dir = Path(args.output_dir).resolve()

    if not blender.exists():
        print(f"ERROR Blender executable not found: {blender}", file=sys.stderr)
        return 1

    if not args.skip_validate:
        run([sys.executable, str(ROOT / "scripts" / "validate_package.py")], ROOT)

    manifest = load_manifest()
    package_name = f"{manifest['id']}-{manifest['version']}.zip"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / package_name

    if output_path.exists():
        output_path.unlink()

    with tempfile.TemporaryDirectory(prefix="ylvc_package_") as temp_dir:
        clean_source = Path(temp_dir) / manifest["id"]
        clean_source.mkdir(parents=True)
        copy_clean_tree(clean_source)
        run(
            [
                str(blender),
                "--background",
                "--factory-startup",
                "--command",
                "extension",
                "build",
                "--source-dir",
                str(clean_source),
                "--output-filepath",
                str(output_path),
            ],
            clean_source,
        )
        run(
            [
                str(blender),
                "--background",
                "--factory-startup",
                "--command",
                "extension",
                "validate",
                str(output_path),
            ],
            clean_source,
        )

    print(f"Built package: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
