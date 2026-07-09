"""Tests for scripts.board_render."""

from __future__ import annotations

from pathlib import Path

import pytest
import scripts.board_render as br

FIXTURE_BOARD = """\
# Work Board — Lee-W/maigo
> 最後刷新：2026-07-09 14:30 ｜ 🎯 3 ｜ ⏳ 2 ｜ ✅ 1 ｜ 🧠 待學習盤點 2

## 🎯 你的球（3）
- [ ] 🐛 #123 (alice) **READY** — triage 完可接 → `/maigo:take-issue 123` — "fix xxx"
- [ ] 🔀 #456 (你) **CHANGES_REQUESTED** — reviewer 要改 → `/maigo:address-comments` — "feat yyy"
- [x] 👀 #789 (bob) **↩︎ 回你的球** — 你回過後又推新 commit → `/maigo:review 789` — "…"

## ⏳ 等別人（2）
- [ ] 🔀 #460 (你) **等 review** — 最後活動是你 07-08 — "…"
- [ ] 🐛 #130 (carol) **NEEDS_INFO** — 等回報者補資訊 — "…"

## 📥 無法分類（1）
<!-- 只放 gh 抓不到的（權限 / 打錯號碼 / 網路失敗），抓得到的一律直接分桶 -->
- weird unparseable line without checkbox

## ✅ Merged / closed（最近 7 天）
- [x] 👀 #700 (dave) **APPROVE** 🧠 — merged 07-07 — "…"
"""


class TestParseLine:
    def test_ready_issue_with_command(self):
        item = br.parse_line(
            '- [ ] 🐛 #123 (alice) **READY** — triage 完可接 → `/maigo:take-issue 123` — "fix xxx"'
        )
        assert item.parsed
        assert not item.checked
        assert item.type_emoji == "🐛"
        assert item.ref == "#123"
        assert item.who == "alice"
        assert item.status == "READY"
        assert item.reason == "triage 完可接"
        assert item.command == "/maigo:take-issue 123"
        assert item.title == "fix xxx"
        assert not item.learned

    def test_checked_status_with_spaces(self):
        item = br.parse_line(
            '- [x] 👀 #789 (bob) **↩︎ 回你的球** — 你回過後又推新 commit → `/maigo:review 789` — "…"'
        )
        assert item.checked
        assert item.status == "↩︎ 回你的球"
        assert item.command == "/maigo:review 789"

    def test_no_command_line(self):
        item = br.parse_line('- [ ] 🔀 #460 (你) **等 review** — 最後活動是你 07-08 — "…"')
        assert item.parsed
        assert item.command == ""
        assert item.reason == "最後活動是你 07-08"
        assert item.title == "…"

    def test_doc_link_with_command(self):
        item = br.parse_line(
            "- [ ] 👀 #300 (bob) **APPROVE_WITH_NITS** — 測試綠 → "
            '`貼 nit→approve` 📄 `../files/review-300.md` — "streaming log"'
        )
        assert item.command == "貼 nit→approve"
        assert item.doc == "../files/review-300.md"
        assert item.reason == "測試綠"
        assert item.title == "streaming log"
        assert "doc-link" in br.render_card(item, "apache/airflow")

    def test_doc_link_without_command(self):
        item = br.parse_line(
            '- [x] 👀 #366 (bob) **你已 APPROVE** — 無新活動 📄 `../files/review-366.md` — "states"'
        )
        assert item.command == ""
        assert item.doc == "../files/review-366.md"
        assert item.reason == "無新活動"
        assert item.title == "states"

    def test_no_doc_link(self):
        item = br.parse_line('- [ ] 👀 #239 (jason) **APPROVE** — 待送 → `approve on GH` — "gradle"')
        assert item.doc == ""
        assert "doc-link" not in br.render_card(item, "apache/airflow")


class TestMaterializeDocs:
    def _sections(self, doc: str):
        item = br.parse_line(f'- [ ] 👀 #1 (bob) **APPROVE** — ok 📄 `{doc}` — "t"')
        return [br.Section(emoji="🎯", name="你的球", items=[item])], item

    def test_no_pandoc_leaves_md_untouched(self, tmp_path, monkeypatch):
        monkeypatch.setattr(br.shutil, "which", lambda _: None)
        sections, item = self._sections("review-1.md")
        assert br.materialize_docs(sections, tmp_path) == 0
        assert item.doc == "review-1.md"

    def test_non_md_doc_ignored(self, tmp_path, monkeypatch):
        monkeypatch.setattr(br.shutil, "which", lambda _: "/usr/bin/pandoc")
        sections, item = self._sections("review-1.html")
        assert br.materialize_docs(sections, tmp_path) == 0
        assert item.doc == "review-1.html"

    def test_md_repointed_to_html(self, tmp_path, monkeypatch):
        monkeypatch.setattr(br.shutil, "which", lambda _: "/usr/bin/pandoc")
        (tmp_path / "review-1.md").write_text("# hi", encoding="utf-8")
        calls = {}

        def fake_run(cmd, **kw):
            calls["out"] = cmd[cmd.index("-o") + 1]
            Path(calls["out"]).write_text("<html></html>", encoding="utf-8")
            return __import__("subprocess").CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(br.subprocess, "run", fake_run)
        sections, item = self._sections("review-1.md")
        assert br.materialize_docs(sections, tmp_path) == 1
        assert item.doc == "review-1.html"

    def test_learned_badge(self):
        item = br.parse_line('- [x] 👀 #700 (dave) **APPROVE** 🧠 — merged 07-07 — "…"')
        assert item.parsed
        assert item.checked
        assert item.learned
        assert item.status == "APPROVE"
        assert item.reason == "merged 07-07"

    def test_unparseable_line_falls_back(self):
        raw = "- weird unparseable line without checkbox"
        item = br.parse_line(raw)
        assert not item.parsed
        assert item.raw == raw


class TestParseBoard:
    def test_repo_and_section_order(self):
        repo, sections = br.parse_board(FIXTURE_BOARD)
        assert repo == "Lee-W/maigo"
        assert [s.emoji for s in sections] == ["🎯", "⏳", "📥", "✅"]

    def test_section_item_counts(self):
        _, sections = br.parse_board(FIXTURE_BOARD)
        by_emoji = {s.emoji: s for s in sections}
        assert len(by_emoji["🎯"].items) == 3
        assert len(by_emoji["⏳"].items) == 2
        assert len(by_emoji["📥"].items) == 1
        assert len(by_emoji["✅"].items) == 1

    def test_unparseable_item_kept_in_its_section(self):
        _, sections = br.parse_board(FIXTURE_BOARD)
        by_emoji = {s.emoji: s for s in sections}
        item = by_emoji["📥"].items[0]
        assert not item.parsed
        assert "weird unparseable line" in item.raw

    def test_section_name_strips_trailing_count_only(self):
        _, sections = br.parse_board(FIXTURE_BOARD)
        by_emoji = {s.emoji: s for s in sections}
        assert by_emoji["🎯"].name == "你的球"
        # non-numeric parenthetical (最近 7 天) is not a bare count, so it's kept
        assert by_emoji["✅"].name == "Merged / closed（最近 7 天）"

    def test_empty_text_returns_no_sections(self):
        repo, sections = br.parse_board("")
        assert repo == ""
        assert sections == []


class TestIssueUrl:
    def test_bare_ref_uses_header_repo(self):
        assert br.issue_url("Lee-W/maigo", "#123") == "https://github.com/Lee-W/maigo/issues/123"

    def test_owner_repo_ref_ignores_header_repo(self):
        assert br.issue_url("Lee-W/maigo", "other/repo#9") == "https://github.com/other/repo/issues/9"

    def test_bare_ref_without_repo_header_returns_empty(self):
        assert br.issue_url("", "#123") == ""

    def test_unrecognized_ref_returns_empty(self):
        assert br.issue_url("Lee-W/maigo", "not-a-ref") == ""


class TestRenderCard:
    def test_unparsed_item_renders_raw_fallback(self):
        item = br.BoardItem(raw="- some raw line", parsed=False)
        rendered = br.render_card(item, "Lee-W/maigo")
        assert "unparsed" in rendered
        assert "some raw line" in rendered

    def test_checked_item_has_checked_class(self):
        item = br.parse_line('- [x] 👀 #700 (dave) **APPROVE** 🧠 — merged 07-07 — "…"')
        rendered = br.render_card(item, "Lee-W/maigo")
        assert 'class="card checked"' in rendered
        assert '<span class="badge learned">🧠</span>' in rendered

    def test_unchecked_item_has_unchecked_class(self):
        item = br.parse_line('- [ ] 🐛 #130 (carol) **NEEDS_INFO** — 等回報者補資訊 — "…"')
        rendered = br.render_card(item, "Lee-W/maigo")
        assert 'class="card unchecked"' in rendered

    def test_ref_renders_github_link(self):
        item = br.parse_line('- [ ] 🐛 #123 (alice) **READY** — x → `/maigo:take-issue 123` — "t"')
        rendered = br.render_card(item, "Lee-W/maigo")
        assert 'href="https://github.com/Lee-W/maigo/issues/123"' in rendered

    def test_command_renders_copy_button(self):
        item = br.parse_line('- [ ] 🐛 #123 (alice) **READY** — x → `/maigo:take-issue 123` — "t"')
        rendered = br.render_card(item, "Lee-W/maigo")
        assert "copy-btn" in rendered
        assert "/maigo:take-issue 123" in rendered


class TestRenderHtml:
    def test_three_kanban_columns_present(self):
        repo, sections = br.parse_board(FIXTURE_BOARD)
        out = br.render_html(repo, sections)
        assert "column-todo" in out
        assert "column-waiting" in out
        assert "column-done" in out

    def test_extra_section_rendered_when_non_empty(self):
        repo, sections = br.parse_board(FIXTURE_BOARD)
        out = br.render_html(repo, sections)
        assert "column-extra" in out
        assert "weird unparseable line" in out

    def test_extra_section_omitted_when_empty(self):
        board = FIXTURE_BOARD.replace("- weird unparseable line without checkbox\n", "")
        repo, sections = br.parse_board(board)
        out = br.render_html(repo, sections)
        assert "column-extra" not in out

    def test_refresh_meta_and_dark_mode_present(self):
        repo, sections = br.parse_board(FIXTURE_BOARD)
        out = br.render_html(repo, sections)
        assert '<meta http-equiv="refresh" content="30">' in out
        assert "prefers-color-scheme: dark" in out

    def test_checkbox_glyphs_present(self):
        repo, sections = br.parse_board(FIXTURE_BOARD)
        out = br.render_html(repo, sections)
        assert "☑" in out
        assert "☐" in out


class TestMain:
    def test_renders_fixture_to_default_html_path(self, tmp_path: Path):
        board = tmp_path / "board.md"
        board.write_text(FIXTURE_BOARD, encoding="utf-8")
        assert br.main([str(board)]) == 0
        out_path = tmp_path / "board.html"
        assert out_path.is_file()
        text = out_path.read_text(encoding="utf-8")
        assert "column-todo" in text

    def test_renders_to_explicit_output_path(self, tmp_path: Path):
        board = tmp_path / "board.md"
        board.write_text(FIXTURE_BOARD, encoding="utf-8")
        out = tmp_path / "nested" / "out.html"
        assert br.main([str(board), str(out)]) == 0
        assert out.is_file()

    def test_missing_board_file_exits_1(self, tmp_path: Path, capsys: pytest.CaptureFixture):
        missing = tmp_path / "nope.md"
        assert br.main([str(missing)]) == 1
        assert "不存在" in capsys.readouterr().err
