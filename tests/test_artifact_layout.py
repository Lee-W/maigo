"""Script-written markdown artifacts must already be a formatter's fixed point.

Only the structural rules a general markdown formatter enforces are checked:
blank lines around headings and lists, no consecutive blank lines, and a
blank line after a closing code fence.
"""

from __future__ import annotations

import re
import unicodedata
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

    def test_new_detail_file_with_related_files(self):
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
            related_files=["review/1/review.md", "pr/1/plan.md"],
        )
        assert "  - `../review/1/review.md`\n" in facts
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


_TEMPLATE = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "teammate-flow"
    / "references"
    / "run-summary-template.md"
)


def _template_markdown_blocks() -> list[str]:
    text = _TEMPLATE.read_text(encoding="utf-8")
    return re.findall(r"^````markdown\n(.*?)^````\n", text, re.S | re.M)


def _display_width(line: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in line)


class TestRunSummaryTemplate:
    def test_template_has_a_skeleton_and_a_filled_example(self):
        assert len(_template_markdown_blocks()) == 2

    def test_skeleton_and_example_are_fixed_points(self):
        for block in _template_markdown_blocks():
            assert layout_violations(block) == []

    def test_skeleton_and_example_have_the_required_sections_in_order(self):
        for block in _template_markdown_blocks():
            headings = [line for line in block.splitlines() if line.startswith("## ")]
            assert headings == [
                "## 為什麼做",
                "## 做了什麼",
                "## 怎麼做",
                "## 驗證",
                "## 沒處理的",
            ]

    def test_skeleton_and_example_have_three_text_diagrams(self):
        for block in _template_markdown_blocks():
            assert len(re.findall(r"^```text\n(.*?)^```\n", block, re.S | re.M)) == 3
            assert "```" not in re.sub(
                r"^```text\n.*?^```\n", "", block, flags=re.S | re.M
            )

    def test_skeleton_and_example_open_with_the_four_header_fields_in_order(self):
        for block in _template_markdown_blocks():
            lines = block.splitlines()
            assert lines[0].startswith("# ")
            assert lines[1] == ""
            fields = [re.match(r"- \*\*(.+?)\*\*：", line) for line in lines[2:6]]
            assert [m.group(1) if m else None for m in fields] == [
                "日期",
                "結果",
                "計畫",
                "commit",
            ]
            assert lines[6] == ""

    def test_skeleton_plan_field_is_a_placeholder_not_a_hard_coded_file(self):
        skeleton = _template_markdown_blocks()[0]
        assert "- **計畫**：`<本次實際的 plan 檔名>`" in skeleton.splitlines()

    def test_example_agent_names_outside_diagrams_carry_the_emoji_prefix(self):
        example = _template_markdown_blocks()[1]
        prose = re.sub(r"^```text\n.*?^```\n", "", example, flags=re.S | re.M)
        prefixes = {
            "樂奈": "🐱",
            "燈": "🩵",
            "愛音": "🎀",
            "爽世": "🟡",
            "立希": "🟣",
        }
        mentioned = 0
        for name, emoji in prefixes.items():
            mentioned += prose.count(name)
            assert prose.count(name) == prose.count(f"{emoji} {name}"), name
        assert mentioned > 0

    def test_example_diagrams_follow_the_text_diagram_rules(self):
        example = _template_markdown_blocks()[1]
        diagrams = re.findall(r"^```text\n(.*?)^```\n", example, re.S | re.M)
        assert len(diagrams) == 3
        for diagram in diagrams:
            for line in diagram.splitlines():
                assert line.isascii(), line
                assert line == line.rstrip(), line
                assert _display_width(line) <= 80, line

    def test_example_has_no_markdown_table(self):
        example = _template_markdown_blocks()[1]
        assert not [line for line in example.splitlines() if line.startswith("|")]
