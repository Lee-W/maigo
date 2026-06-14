#!/usr/bin/env python3
"""Lazy schema validator for Maigo cross-project and project-specific memory.

掃描兩個來源的 memory 目錄，逐一檢查 entry frontmatter schema：
- cross-project:      ~/.config/maigo/memory/
- project-specific:   ~/.claude/projects/*/memory/

規則：warn-not-block。有問題只印 warning，預設 exit 0。
加 --strict flag 時，有任何 warning 則 exit 1。

跑：`python3 scripts/validate_memory.py`
    `python3 scripts/validate_memory.py --strict`
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _frontmatter import parse_frontmatter  # noqa: E402

VALID_TYPES: frozenset[str] = frozenset({"user", "feedback", "project", "reference"})
REQUIRED_FIELDS: tuple[str, ...] = ("name", "description")

# Regex to parse MEMORY.md index lines:
# - [Title](slug.md) — description
_INDEX_RE = re.compile(r"^\s*-\s+\[.*?\]\(([^)]+\.md)\)")


class MemoryCheckResult:
    """Accumulates warnings for one memory directory scan."""

    def __init__(self, display_name: str, path: Path) -> None:
        self.display_name = display_name
        self.path = path
        self.warnings: list[str] = []
        self.entry_count: int = 0

    def warn(self, slug: str, msg: str) -> None:
        self.warnings.append(f"  ! {slug}: {msg}")

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)


def _parse_index(memory_md: Path) -> list[str]:
    """Return list of slug filenames declared in MEMORY.md."""
    slugs: list[str] = []
    for line in memory_md.read_text(encoding="utf-8").splitlines():
        m = _INDEX_RE.match(line)
        if m:
            slugs.append(m.group(1))
    return slugs


def _extract_metadata_type(text: str) -> str | None:
    """Extract type from a nested ``metadata:`` block in raw frontmatter text.

    The flat ``parse_frontmatter`` parser skips indented lines, so
    ``metadata.type`` written by the Claude Code harness (indented under
    ``metadata:``) is invisible to it.  This helper scans the raw frontmatter
    body directly.

    Returns the stripped type string if found and non-empty, otherwise None.
    Does not raise on malformed input.
    """
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    body = text[4:end]

    in_metadata_block = False
    for line in body.splitlines():
        stripped = line.lstrip()
        is_indented = line != stripped and line.startswith((" ", "\t"))

        if not is_indented:
            # Top-level key: enter or leave the metadata block.
            in_metadata_block = stripped.startswith("metadata:")
            continue

        if in_metadata_block and ":" in stripped:
            k, _, v = stripped.partition(":")
            if k.strip() == "type":
                val = v.strip()
                return val if val else None

    return None


def _check_entry(result: MemoryCheckResult, slug: str, path: Path) -> None:
    """Run schema check on a single entry file, appending warnings to result."""
    result.entry_count += 1
    text = path.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    if fm is None:
        result.warn(slug, "frontmatter missing or malformed")
        return

    for field in REQUIRED_FIELDS:
        if not fm.get(field):
            result.warn(slug, f"missing field: `{field}`")

    # Resolve effective type: top-level `type` takes priority; fall back to
    # `metadata.type` for entries written by the Claude Code harness auto-memory
    # system (which nests type under a `metadata` dict).
    #
    # Note: parse_frontmatter is a flat parser that skips indented lines, so
    # `metadata.type` (indented) is not returned as a dict — it returns the
    # `metadata` key with an empty-string value.  We extract the nested type
    # directly from the raw frontmatter text instead.
    type_val = fm.get("type") or None
    if not type_val:
        type_val = _extract_metadata_type(text)

    if not type_val:
        result.warn(slug, "missing field: `type`")
    elif type_val not in VALID_TYPES:
        enum_str = "{" + ", ".join(sorted(VALID_TYPES)) + "}"
        result.warn(slug, f"type=`{type_val}` not in {enum_str}")


def scan_directory(mem_dir: Path, display_name: str) -> MemoryCheckResult:
    """Scan one memory directory and return a MemoryCheckResult."""
    result = MemoryCheckResult(display_name, mem_dir)

    if not mem_dir.is_dir():
        return result

    memory_md = mem_dir / "MEMORY.md"
    if not memory_md.is_file():
        return result

    slugs = _parse_index(memory_md)
    for slug in slugs:
        entry_path = mem_dir / slug
        if not entry_path.is_file():
            result.warn(slug, "declared in MEMORY.md but file not found")
            continue
        _check_entry(result, slug, entry_path)

    return result


def discover_directories() -> list[tuple[Path, str]]:
    """Return list of (path, display_name) for all memory directories to scan."""
    dirs: list[tuple[Path, str]] = []

    # cross-project
    cross = Path.home() / ".config" / "maigo" / "memory"
    dirs.append((cross, "Cross-project memory"))

    # project-specific: glob ~/.claude/projects/*/memory/
    projects_root = Path.home() / ".claude" / "projects"
    if projects_root.is_dir():
        for project_dir in sorted(projects_root.iterdir()):
            mem_dir = project_dir / "memory"
            slug = project_dir.name
            dirs.append((mem_dir, f"Project memory ({slug})"))

    return dirs


def print_result(result: MemoryCheckResult) -> None:
    """Print the result for one directory to stdout."""
    print(f"## {result.display_name}: {result.path}")
    if not result.has_warnings:
        print(f"  ✓ {result.entry_count} entries passed schema check")
    else:
        for line in result.warnings:
            print(line)
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Lazy schema validator for Maigo memory entries.",
        epilog=(
            "Exit 0 by default (warn-not-block). "
            "With --strict, exit 1 if any warnings are found."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if any warnings are found (for CI / power users).",
    )
    args = parser.parse_args(argv)

    all_results: list[MemoryCheckResult] = []
    for mem_dir, display_name in discover_directories():
        result = scan_directory(mem_dir, display_name)
        if mem_dir.is_dir():
            print_result(result)
            all_results.append(result)

    total_warnings = sum(len(r.warnings) for r in all_results)

    if args.strict and total_warnings > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
