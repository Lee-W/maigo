#!/usr/bin/env python3
"""Validate frontmatter of Maigo agent/command markdown files.

Agent 與 command 缺欄位或格式錯誤會讓 Claude Code 載不到該 agent/command，
是最容易在 PR 階段沒人發現、上線才炸的錯誤。pre-commit 階段擋下。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT_REQUIRED = {"name", "description", "model", "tools"}
COMMAND_REQUIRED = {"description"}


def parse_frontmatter(text: str) -> dict[str, str] | None:
    """Return flat key→value dict from frontmatter, or None if missing/malformed."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    body = text[4:end]
    keys: dict[str, str] = {}
    for line in body.splitlines():
        # Skip nested / continuation lines
        if not line or line.startswith((" ", "\t")):
            continue
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        keys[k.strip()] = v.strip()
    return keys


def check_file(path: Path, required: set[str], expect_name_match: bool) -> list[str]:
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

    if expect_name_match and "name" in fm:
        expected = path.stem
        if fm["name"] != expected:
            errors.append(
                f"{path}: agent `name: {fm['name']}` 跟檔名 `{expected}` 不一致"
            )

    return errors


def main() -> int:
    errors: list[str] = []

    agents_dir = ROOT / "agents"
    if agents_dir.is_dir():
        for path in sorted(agents_dir.glob("*.md")):
            errors.extend(check_file(path, AGENT_REQUIRED, expect_name_match=True))

    commands_dir = ROOT / "commands"
    if commands_dir.is_dir():
        for path in sorted(commands_dir.glob("*.md")):
            errors.extend(check_file(path, COMMAND_REQUIRED, expect_name_match=False))

    if errors:
        sys.stderr.write("\n".join(errors) + "\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
