"""Tests for the Work Board MkDocs presentation hook."""

from types import SimpleNamespace

from scripts import board_serve_hook as hook


BOARD = """\
# Work Board — Lee-W/maigo
> 最後刷新：2026-07-13 12:00 ｜ 🎯 2 ｜ ⏳ 1 ｜ ✅ 0

## 🎯 你的球（2）
- [ ] 🐛 #123 (alice) **READY** — triage 完可接 → `/maigo:take-issue 123` — "fix parser"
- [x] 👀 other/repo#9 (bob) **NEEDS_CHANGES** Δ +120/-45 🧠 — 有兩個 must-fix 📄 `review-9.md` — "tighten validation"

## ⏳ 等別人（1）
- [ ] 🔀 #460 (你) **等 review** Δ +88/-12 — 最後活動是你 07-12 — "add board tables"
"""


def test_parse_item_extracts_action_artifact_and_learning_state():
    first = hook.parse_item(
        "- [x] 👀 #9 (bob) **NEEDS_CHANGES** Δ +120/-45 🧠 — 有 must-fix "
        '→ `/maigo:review 9` 📄 `review-9.md` — "title"'
    )

    assert first is not None
    assert first.checked is True
    assert first.learned is True
    assert first.reason == "有 must-fix"
    assert first.action == "/maigo:review 9"
    assert first.artifact == "review-9.md"
    assert first.title == "title"
    assert first.additions == 120
    assert first.deletions == 45


def test_parse_item_accepts_markdown_whitespace_variations():
    item = hook.parse_item(
        "  -   [ ]   🐛   #123   (alice)   **READY** — ready to start"
    )

    assert item is not None
    assert item.item == "#123"
    assert item.person == "alice"
    assert item.status == "READY"


def test_render_board_uses_section_tables_and_scan_friendly_columns():
    rendered = hook.render_board(BOARD)

    assert rendered.count('<table class="work-table">') == 2
    assert "我處理過" in rendered
    assert "項目" in rendered
    assert "作者" in rendered
    assert "改動" in rendered
    assert "狀態" in rendered
    assert "現況" in rendered
    assert "下一步" in rendered
    assert "<th>球權</th>" not in rendered
    assert "- [ ] 🐛 #123" not in rendered
    assert 'class="work-controls"' in rendered


def test_render_board_keeps_blank_lines_and_comments_in_one_section_table():
    board = """\
# Work Board — Lee-W/maigo
## 🎯 你的球（2）
- [ ] 🐛 #123 (alice) **READY** — ready — "first"

<!-- refresh note -->
- [ ] 🐛 #124 (bob) **待 triage** — new — "second"
"""

    rendered = hook.render_board(board)

    assert rendered.count('<table class="work-table">') == 1
    assert rendered.count("<tr data-kind=") == 2
    assert "<!-- refresh note -->" in rendered


def test_render_board_links_github_items_and_local_artifacts():
    rendered = hook.render_board(BOARD)

    assert 'href="https://github.com/Lee-W/maigo/issues/123"' in rendered
    assert 'href="https://github.com/other/repo/pull/9"' in rendered
    assert 'href="../review-9/"' in rendered


def test_artifact_link_cannot_escape_maigo_docs_root():
    board = (
        "# Work Board — Lee-W/maigo\n"
        "## 🎯 你的球（1）\n- [ ] 👀 #9 (bob) **NEEDS_CHANGES** "
        '— must-fix 📄 `../private.md` — "title"\n'
    )

    rendered = hook.render_board(board)

    assert 'href="../../private/' not in rendered
    assert "📄 ../private.md" in rendered


def test_render_board_preserves_checkbox_and_badge_semantics():
    rendered = hook.render_board(BOARD)

    assert 'type="checkbox" disabled checked' in rendered
    assert 'title="已完成學習盤點"' in rendered
    # NEEDS_CHANGES verdict retained (no new author activity) => ⏳ wait tier;
    # READY => 🎯 act tier. See scripts/board_state.py `_STATUS_META`.
    assert "status-wait" in rendered
    assert "status-act" in rendered


def test_render_board_exposes_sort_and_filter_metadata():
    rendered = hook.render_board(BOARD)

    assert 'data-author="bob"' in rendered
    assert 'data-status="NEEDS_CHANGES"' in rendered
    assert 'data-changes="165"' in rendered
    assert '<span class="diff-add">+120</span>' in rendered
    assert '<span class="diff-delete">−45</span>' in rendered


def test_render_board_offers_copy_only_check_uncheck_and_drop_commands():
    rendered = hook.render_board(BOARD)

    assert 'data-copy-command="maigo:board --check 123"' in rendered
    assert 'data-copy-command="maigo:board --drop 123"' in rendered
    assert 'data-copy-command="maigo:board --uncheck other/repo#9"' in rendered
    assert "標記已處理" in rendered
    assert "取消標記" in rendered
    assert "停止追蹤" in rendered


def test_status_class_maps_all_five_tiers():
    # One representative status word per tier — see scripts/board_state.py
    # `_STATUS_META` (this is the canonical source; this test is the mirror check).
    assert hook._status_class("CI 紅") == "status-blocked"
    assert hook._status_class("待 triage") == "status-act"
    assert hook._status_class("IN_PROGRESS") == "status-wip"
    assert hook._status_class("等 review") == "status-wait"
    assert hook._status_class("closed") == "status-done"


def test_status_class_unknown_status_is_loud_not_silent_neutral():
    assert hook._status_class("這不是合法狀態詞") == "status-unknown"


def test_render_board_marks_unknown_status_with_warning_text():
    board = (
        "# Work Board — Lee-W/maigo\n"
        "## 🎯 你的球（1）\n"
        '- [ ] 🐛 #1 (alice) **手改壞的狀態詞** — ??? — "title"\n'
    )

    rendered = hook.render_board(board)

    assert 'class="work-status status-unknown"' in rendered
    assert "⚠ 未知狀態" in rendered
    assert "手改壞的狀態詞" in rendered


def test_render_board_renders_stale_badge():
    board = (
        "# Work Board — Lee-W/maigo\n"
        "## ⏳ 等別人（1）\n"
        '- [ ] 🔀 #100 (你) **CI 等待** Δ +5/-1 💤 — no activity — "title"\n'
    )

    rendered = hook.render_board(board)

    assert '<span class="stale" title="逾期未更新">💤</span>' in rendered


def test_render_board_renders_archived_section_as_its_own_table():
    board = (
        "# Work Board — Lee-W/maigo\n"
        "## 🎯 你的球（1）\n"
        '- [ ] 🐛 #1 (alice) **READY** — ready — "first"\n'
        "\n"
        "## 🗄️ 已放棄（1）\n"
        '- [ ] 🐛 #99 (eve) **已放棄** — dropped — "second"\n'
    )

    rendered = hook.render_board(board)

    assert rendered.count('<table class="work-table">') == 2
    assert "## 🗄️ 已放棄（1）" in rendered
    assert "status-done" in rendered  # 已放棄 => Tier.DONE


def test_malformed_line_is_left_untouched():
    malformed = "- [ ] 這是使用者自訂備註"
    assert malformed in hook.render_board(malformed)


def test_hook_only_changes_board_page():
    page = SimpleNamespace(file=SimpleNamespace(src_uri="review-9.md"))
    assert hook.on_page_markdown(BOARD, page) == BOARD
