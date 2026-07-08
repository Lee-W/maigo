#!/usr/bin/env python3
"""Read-only summary for Maigo retry / failure JSONL logs."""

from __future__ import annotations

import argparse
import collections
import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = (
    ("soyo", ".maigo/soyo-must-fix.jsonl", "must_fix_keys"),
    ("taki", ".maigo/test-failures.jsonl", "failures"),
)


@dataclass(frozen=True)
class LogSummary:
    label: str
    path: Path
    field: str
    total_entries: int
    counts: collections.Counter[str]
    recent: tuple[dict, ...]
    malformed_lines: int = 0


def read_jsonl(path: Path) -> tuple[list[dict], int]:
    """Return parsed JSON object lines and malformed-line count.

    Missing files and unreadable paths are treated as empty logs; doctor should
    report them as normal new-environment state, not as errors.
    """
    entries: list[dict] = []
    malformed = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return entries, malformed

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if isinstance(entry, dict):
            entries.append(entry)
        else:
            malformed += 1
    return entries, malformed


def summarize_log(label: str, path: Path, field: str) -> LogSummary:
    entries, malformed = read_jsonl(path)
    counts: collections.Counter[str] = collections.Counter()
    for entry in entries:
        values = entry.get(field, [])
        if isinstance(values, list):
            counts.update(str(value) for value in values)
    return LogSummary(
        label=label,
        path=path,
        field=field,
        total_entries=len(entries),
        counts=counts,
        recent=tuple(entries[-3:]),
        malformed_lines=malformed,
    )


def summarize_repo(root: Path) -> list[LogSummary]:
    return [
        summarize_log(label, root / rel_path, field)
        for label, rel_path, field in SOURCES
    ]


def format_summary(summary: LogSummary) -> str:
    display_path = str(summary.path)
    if summary.path.is_relative_to(ROOT):
        display_path = str(summary.path.relative_to(ROOT))

    if summary.total_entries == 0:
        line = f"{display_path}: 無紀錄（正常，尚未觸發過 retry）"
        if summary.malformed_lines:
            line += f"；略過 {summary.malformed_lines} 行損壞 JSON"
        return line

    count_text = ", ".join(
        f"{key}×{count}" for key, count in summary.counts.most_common()
    )
    lines = [f"{display_path}（{summary.total_entries} 筆）：{count_text}"]
    if summary.malformed_lines:
        lines.append(f"  略過損壞 JSON：{summary.malformed_lines} 行")
    for entry in summary.recent:
        lines.append(f"  最近：{entry.get('ts')} — {entry.get(summary.field)}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize Maigo retry / failure logs under .maigo/."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repo root to inspect. Defaults to current directory.",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    for summary in summarize_repo(root):
        print(format_summary(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
