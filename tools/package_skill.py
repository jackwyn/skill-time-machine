#!/usr/bin/env python3
"""Build uploadable Agent Skills or an OpenAI plugin ZIP from the canonical skill folder."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skill"
SKILL_NAME = "skill-time-machine"
PLUGIN_VERSION = "0.1.0"


def skill_files() -> list[Path]:
    files = [p for p in SKILL_DIR.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    if not any(path.name == "SKILL.md" for path in files):
        raise SystemExit("skill/SKILL.md is missing")
    return sorted(files)


def build_skill_zip(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in skill_files():
            archive.write(source, f"{SKILL_NAME}/{source.relative_to(SKILL_DIR).as_posix()}")


def build_plugin_zip(output: Path) -> None:
    description = "Review API and workflow drift, propose repairs, verify revisions, and roll back safely."
    manifest = {
        "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
        "name": SKILL_NAME,
        "version": PLUGIN_VERSION,
        "description": description,
        "repository": "https://github.com/jackwyn/skill-time-machine",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("plugin.json", json.dumps(manifest, indent=2) + "\n")
        for source in skill_files():
            target = f"skills/{SKILL_NAME}/{source.relative_to(SKILL_DIR).as_posix()}"
            archive.write(source, target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("skill", "openai-plugin"), default="skill")
    parser.add_argument("--output", type=Path, help="Output ZIP path (defaults under dist/)")
    args = parser.parse_args()
    if args.format == "skill":
        output = args.output or ROOT / "dist" / f"{SKILL_NAME}-skill.zip"
        build_skill_zip(output)
    else:
        output = args.output or ROOT / "dist" / f"{SKILL_NAME}-plugin.zip"
        build_plugin_zip(output)
    print(f"Created {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
