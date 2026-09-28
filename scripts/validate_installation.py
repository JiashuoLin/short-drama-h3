#!/usr/bin/env python3
"""Read-only installation checks; no imports, production calls or servers."""
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit


def validate(suite_parent: Path) -> dict:
    skills = sorted(suite_parent.glob("short-drama-h3*"))
    errors = []
    checked_files = 0
    external_skills = {"minimax-h3-comfyui-video"}
    for skill in skills:
        if not skill.is_dir():
            continue
        entry = skill / "SKILL.md"
        if not entry.is_file():
            errors.append(f"Missing entry: {entry}")
            continue
        if not re.search(rf"^name: {re.escape(skill.name)}$", entry.read_text(encoding="utf-8"), re.M):
            errors.append(f"Skill identity mismatch: {entry}")
        for path in skill.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            checked_files += 1
            if path.name == "dashboard_server.py" or "dashboard" in path.parts:
                errors.append(f"Excluded presentation resource: {path}")
            if path.suffix == ".py":
                try:
                    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                except SyntaxError as error:
                    errors.append(str(error))
            if path.suffix not in {".md", ".yaml"}:
                continue
            text = path.read_text(encoding="utf-8")
            for invocation in re.findall(r"\$([a-z][a-z0-9-]+)", text):
                if invocation.startswith("short-drama") and not (suite_parent / invocation / "SKILL.md").is_file():
                    errors.append(f"Missing skill route {invocation}: {path}")
                elif invocation.startswith("short-drama") and not invocation.startswith("short-drama-h3"):
                    errors.append(f"Original-suite runtime route {invocation}: {path}")
                elif invocation == "minimax-h3-comfyui-video":
                    external_skills.add(invocation)
            if path.suffix != ".md":
                continue
            # Check concrete inline Markdown file links, excluding fragments and URLs.
            for target in re.findall(r"\]\(([^\n)]+)\)", text):
                target = target.strip().strip("<>")
                if target.startswith("#") or urlsplit(target).scheme or "{" in target or "<" in target:
                    continue
                relative = unquote(target.split("#", 1)[0])
                if relative and not (path.parent / relative).exists():
                    errors.append(f"Missing linked file {target}: {path}")
    return {"skills": len(skills), "files": checked_files, "errors": errors,
            "external_skills": sorted(external_skills), "quality_review": "not_performed"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite-parent", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    report = validate(args.suite_parent)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
