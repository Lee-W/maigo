#!/usr/bin/env python3
"""Validate frontmatter of Maigo agent/command markdown files.

Agent 與 command 缺欄位或格式錯誤會讓 Claude Code 載不到該 agent/command，
是最容易在 PR 階段沒人發現、上線才炸的錯誤。pre-commit 階段擋下。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _frontmatter import parse_frontmatter  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
AGENT_REQUIRED = {"name", "description", "model", "tools"}
COMMAND_REQUIRED = {"description"}
SKILL_REQUIRED = {"name", "description"}


def check_file(
    path: Path, required: set[str], expected_name: str | None = None
) -> list[str]:
    """Return list of error messages for one file (empty = OK)."""
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)

    if fm is None:
        return [f"{path}: 缺少或損壞的 frontmatter（需以 `---` 包夾）"]

    missing = required - fm.keys()
    if missing:
        errors.append(f"{path}: frontmatter 缺欄位 {sorted(missing)}")

    for key in fm.keys() & required:
        if not fm[key]:
            errors.append(f"{path}: frontmatter 欄位 `{key}` 是空值")

    if expected_name is not None and "name" in fm:
        if fm["name"] != expected_name:
            errors.append(
                f"{path}: agent `name: {fm['name']}` 跟 `{expected_name}` 不一致"
            )

    return errors


def main() -> int:
    errors: list[str] = []

    agents_dir = ROOT / "agents"
    if agents_dir.is_dir():
        for path in sorted(agents_dir.glob("*.md")):
            errors.extend(check_file(path, AGENT_REQUIRED, expected_name=path.stem))

    commands_dir = ROOT / "commands"
    if commands_dir.is_dir():
        for path in sorted(commands_dir.glob("*.md")):
            errors.extend(check_file(path, COMMAND_REQUIRED))

    skills_dir = ROOT / "skills"
    if skills_dir.is_dir():
        for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
            skill_file = skill_dir / "SKILL.md"
            if skill_file.is_file():
                errors.extend(
                    check_file(skill_file, SKILL_REQUIRED, expected_name=skill_dir.name)
                )

    if errors:
        sys.stderr.write("\n".join(errors) + "\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
