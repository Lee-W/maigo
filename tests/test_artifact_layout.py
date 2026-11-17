"""Script-written markdown artifacts must already be a formatter's fixed point.

Only the structural rules a general markdown formatter enforces are checked:
blank lines around headings and lists, no consecutive blank lines, and a
blank line after a closing code fence.
"""

from __future__ import annotations

import re
from pathlib import Path

from scripts import board_refresh as refresh
from scripts import pr_context_cache as pcc
from scripts import review_report as report

_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_HEADING = re.compile(r"^#{1,6}\s")
_ITEM = re.compile(r"^\s*(?:[-*+]|\d+\.)\s")
_COMMENT = re.compile(r"^\s*<!--.*-->\s*$")


def _is_blank(line: str | None) -> bool:
    """Missing neighbour (file edge) and HTML comment lines count as blank."""
    return line is None or not line.strip() or bool(_COMMENT.match(line))


def layout_violations(text: str) -> list[str]:
    """Violations outside fenced code; each is `line N: reason`."""
    lines = text.splitlines()
    problems: list[str] = []
    fence: str | None = None
    closing: list[int] = []
    in_fence = [False] * len(lines)
    for index, line in enumerate(lines):
        marker = _FENCE.match(line)
        if marker:
            if fence is None:
                fence = marker[1]
            elif marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                fence = None
                closing.append(index)
            in_fence[index] = True
        elif fence is not None:
            in_fence[index] = True

    def at(index: int) -> str | None:
        return lines[index] if 0 <= index < len(lines) else None

    for index, line in enumerate(lines):
        if in_fence[index]:
            continue
        before, after = at(index - 1), at(index + 1)
        if _HEADING.match(line):
            if not _is_blank(before):
                problems.append(f"line {index + 1}: heading needs a blank line before")
            if not _is_blank(after):
                problems.append(f"line {index + 1}: heading needs a blank line after")
        if _ITEM.match(line):
            starts_block = not (
                before is not None
                and not in_fence[index - 1]
                and (_ITEM.match(before) or (before.strip() and before[0] in " \t"))
            )
            if starts_block and not _is_blank(before):
                problems.append(f"line {index + 1}: list needs a blank line before")
        if (
            line.strip()
            and (_ITEM.match(line) or line[0] in " \t")
            and after is not None
            and after.strip()
            and not _COMMENT.match(after)
            and not _ITEM.match(after)
            and after[0] not in " \t"
            and not in_fence[index + 1]
            and not _FENCE.match(after)
        ):
            problems.append(f"line {index + 1}: list needs a blank line after")
        if not line.strip() and before is not None and not before.strip():
            problems.append(f"line {index + 1}: consecutive blank lines")
    for index in closing:
        following = at(index + 1)
        if following is not None and following.strip():
            problems.append(f"line {index + 1}: closing fence needs a blank line after")
    return problems


class TestLayoutHelper:
    def test_clean_document_has_no_violations(self):
        text = (
            "# Title\n\nintro\n\n## Sub\n\n- a\n  continued\n- b\n\n"
            "```text\nx\n\n\ny\n```\n\n<!-- end -->\n"
        )
        assert layout_violations(text) == []

    def test_heading_followed_by_text_is_a_violation(self):
        assert any("heading" in v for v in layout_violations("# T\ntext\n"))

    def test_heading_preceded_by_text_is_a_violation(self):
        assert any("before" in v for v in layout_violations("text\n## T\n\nx\n"))

    def test_list_glued_to_heading_or_text_is_a_violation(self):
        assert layout_violations("# T\n\n- a\n- b\ntext\n")
        assert any("list" in v for v in layout_violations("text\n- a\n"))

    def test_consecutive_blank_lines_are_a_violation(self):
        assert any("consecutive" in v for v in layout_violations("a\n\n\nb\n"))

    def test_marker_glued_to_closing_fence_is_a_violation(self):
        text = "```diff\n+x\n```\n<!-- end -->\n"
        assert any("closing fence" in v for v in layout_violations(text))

    def test_blank_lines_inside_fences_are_exempt(self):
        assert layout_violations("```text\na\n\n\nb\n```\n") == []


def _row(detail: str, title: str) -> dict:
    return {
        "checked": False,
        "type": "👀",
        "status": "待 review",
        "note": None,
        "author": "carol",
        "badges": "",
        "detail": detail,
        "title": title,
    }


class TestScriptArtifactsAreFixedPoints:
    def test_board_with_rows_and_with_empty_sections(self):
        full = refresh.render_board(
            repo="o/r",
            refreshed_at_local="2026-10-01 12:00",
            rows_by_section={
                "🎯": [_row("i/1.md", "One"), _row("i/2.md", "Two")],
                "⏳": [_row("i/3.md", "Three")],
                "✅": [_row("i/4.md", "Four")],
            },
            learn_pending_count=1,
        )
        empty = refresh.render_board(
            repo="o/r",
            refreshed_at_local="2026-10-01 12:00",
            rows_by_section={},
            learn_pending_count=0,
        )
        assert layout_violations(full) == []
        assert layout_violations(empty) == []

    def test_new_detail_file(self):
        facts = refresh.render_detail_facts(
            type="👀",
            status="待 review",
            title="Some PR",
            url="https://github.com/o/r/pull/1",
            additions=3,
            deletions=1,
            author="carol",
            next_action="run `x`",
            number=1,
            last_reviewed_at=None,
            review_time_source=None,
            acknowledged_at=None,
        )
        assert layout_violations(facts + refresh.NEW_PRESERVED) == []

    def test_old_preserved_area_is_normalised_on_refresh(self):
        old = "## 判斷\n\n\n## 筆記\n\n\n<!-- 手寫區 -->\n"
        assert layout_violations(old) != []
        assert layout_violations(refresh.collapse_blank_runs(old)) == []

    def test_report_header(self, tmp_path: Path):
        url = "https://github.com/o/r/pull/7"
        result = report.publish(
            tmp_path,
            url,
            "o/r",
            "Fix",
            "## Context\n\nA fix.\n\n## Verdict\n\nAPPROVE\n",
            "a" * 40,
            "APPROVE",
            owner="others",
        )
        text = Path(result["path"]).read_text()
        assert f"**Source:** <{url}>" in text
        assert layout_violations(text) == []

    def test_cache_section(self):
        section = pcc.render_cache(
            {
                "source": "https://github.com/o/r/pull/7",
                "fetched_at": "2026-10-01T00:00:00Z",
                "pr_number": "7",
                "head_sha": "a" * 40,
                "title": "t",
                "body": "b",
                "linked_issues": "none",
                "ci_status": "ok",
                "diff_stat": "1 file changed",
                "review_threads": "none",
                "reviews": "none",
                "comments": "none",
                "diff_sha": "d" * 64,
                "diff": "+a\n\n\n-b",
            }
        )
        assert layout_violations(section) == []
