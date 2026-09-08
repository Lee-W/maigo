"""Tests for scripts.board_index — cross-repo, read-only Work Board index.

全程只對 `tmp_path` 底下的假 repo 操作，不觸碰任何真實的其他 12 個 repo。
"""

from __future__ import annotations

from pathlib import Path

from scripts import board_index as bi

_NEW_STYLE_BOARD = """\
# Work Board — Lee-W/maigo
> 最後刷新：2026-08-18 14:30 ｜ 🎯 3 ｜ ⏳ 2 ｜ ✅ 1 ｜ 🧠 待學習盤點 1

## 🎯 下一件（3）

1. [ ] 🔀 CHANGES_REQUESTED i/9201.md — Redesign Work Board reading view
2. [x] 👀 ↩︎ 回你的球 i/9301.md — Avoid duplicate GitHub requests
3. [ ] 🐛 待 triage 💤 i/9101.md — CLI 在空設定檔時會 crash

## ⏳ 等別人（2）

- [ ] 🔀 等 review i/9202.md — Document plugin installation flow

## ✅ 最近結案（1）

- [x] 👀 APPROVE（merged 07-12） 🧠 i/9303.md — Add structured review verdicts
"""

# 真實抽樣（2026-09-08，commitizen 的 .maigo/board.md）——舊版三分區行文法，
# heading 是「## 🎯 你的球」而非「## 🎯 下一件」，header 計數仍抽得到。
_OLD_STYLE_BOARD = """\
# Work Board — commitizen-tools/commitizen
> 最後刷新：2026-05-30 ｜ 🎯 28 ｜ ⏳ 0 ｜ ✅ 3 ｜ 🧠 待學習盤點 0 ｜ **全 28 顆已 review 完成**

## 🎯 你的球（28）

### 已 review — verdict 待貼上 GitHub（28）

**🟢 APPROVE / APPROVE_WITH_NITS（6）**
- [ ] 👀 #1967 (bearomorphism) **APPROVE** Δ +12/-0 — some title
"""

_HEADER_BROKEN_BOARD = """\
# Work Board — broken/repo
> this line has no counts at all

## 🎯 下一件（0）
"""


class TestParseBoardText:
    def test_new_style_board_parses_ok(self):
        result = bi.parse_board_text(_NEW_STYLE_BOARD)

        assert result.ok is True
        assert result.header.date == "2026-08-18 14:30"
        assert result.header.todo == 3
        assert result.header.waiting == 2
        assert result.header.done == 1
        assert any("i/9201.md" in line for line in result.next_section_lines)
        assert any("i/9101.md" in line for line in result.next_section_lines)
        # 只到下一個 section 為止，不吃進 ⏳ 等別人 的內容
        assert not any("i/9202.md" in line for line in result.next_section_lines)

    def test_old_style_three_section_board_is_unparseable(self):
        result = bi.parse_board_text(_OLD_STYLE_BOARD)

        assert result.ok is False
        assert result.header is None
        assert result.next_section_lines is None

    def test_header_regex_failure_is_unparseable(self):
        result = bi.parse_board_text(_HEADER_BROKEN_BOARD)

        assert result.ok is False

    def test_missing_next_section_heading_is_unparseable(self):
        text = "# Work Board — x\n> 最後刷新：2026-01-01 ｜ 🎯 0 ｜ ⏳ 0 ｜ ✅ 0\n\n## 其他\n"
        result = bi.parse_board_text(text)

        assert result.ok is False


class TestScanRepoBoard:
    def test_repo_without_maigo_dir_reports_no_board(self, tmp_path: Path):
        repo = tmp_path / "no-maigo-repo"
        repo.mkdir()

        entry = bi.scan_repo_board(repo)

        assert entry.status == "no_board"
        assert entry.name == "no-maigo-repo"

    def test_repo_with_new_style_board_reports_ok(self, tmp_path: Path):
        repo = tmp_path / "maigo"
        (repo / ".maigo").mkdir(parents=True)
        (repo / ".maigo" / "board.md").write_text(_NEW_STYLE_BOARD, encoding="utf-8")

        entry = bi.scan_repo_board(repo)

        assert entry.status == "ok"
        assert entry.result.header.todo == 3

    def test_repo_with_old_style_board_reports_unparseable(self, tmp_path: Path):
        repo = tmp_path / "commitizen"
        (repo / ".maigo").mkdir(parents=True)
        (repo / ".maigo" / "board.md").write_text(_OLD_STYLE_BOARD, encoding="utf-8")

        entry = bi.scan_repo_board(repo)

        assert entry.status == "unparseable"


class TestBuildIndex:
    def test_mixed_statuses_all_appear_and_dont_block_each_other(self, tmp_path: Path):
        ok_repo = tmp_path / "maigo"
        (ok_repo / ".maigo").mkdir(parents=True)
        (ok_repo / ".maigo" / "board.md").write_text(_NEW_STYLE_BOARD, encoding="utf-8")

        broken_repo = tmp_path / "commitizen"
        (broken_repo / ".maigo").mkdir(parents=True)
        (broken_repo / ".maigo" / "board.md").write_text(
            _OLD_STYLE_BOARD, encoding="utf-8"
        )

        empty_repo = tmp_path / "pelican-osm"
        empty_repo.mkdir()

        entries = [
            bi.scan_repo_board(ok_repo),
            bi.scan_repo_board(broken_repo),
            bi.scan_repo_board(empty_repo),
        ]

        index = bi.build_index(entries, generated_at="2026-09-08 00:00 UTC")

        assert "# maigo Cross-repo Board Index" in index
        assert "3 個 repo（1 有 board）" in index
        assert "## maigo（" in index
        assert "i/9201.md" in index
        assert "## commitizen（" in index
        assert "⚠️ 格式無法解析" in index
        assert "board.md` 手動查" in index
        assert "## pelican-osm（" in index
        assert "(no board)" in index

    def test_empty_entries_produces_zero_counts(self):
        index = bi.build_index([], generated_at="2026-09-08 00:00 UTC")

        assert "0 個 repo（0 有 board）" in index
