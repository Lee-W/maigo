"""Tests for the Work Board MkDocs presentation hook."""

from types import SimpleNamespace

import pytest

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


def test_parse_item_new_grammar_title_before_judgment_sentence():
    """新行文法：title 前移到判斷句之前，且不再有 `→ 命令`（點 A.1/A.2）。"""
    item = hook.parse_item(
        '- [ ] 🐛 #9101 (alice) **待 triage** — "CLI 在空設定檔時會 crash" '
        "— 能重現嗎——不能就 NEEDS_INFO"
    )

    assert item is not None
    assert item.title == "CLI 在空設定檔時會 crash"
    assert item.reason == "能重現嗎——不能就 NEEDS_INFO"
    assert item.action is None


def test_parse_item_own_pr_row_omits_you_person_and_defaults_to_you():
    """🔀 列可省略 `(你)`（點 A.3）；parser 仍需正確 fullmatch 並補上預設作者。"""
    item = hook.parse_item('- [ ] 🔀 #9201 **CI 紅** Δ +52/-9 — "Add stale badge"')

    assert item is not None
    assert item.kind == "🔀"
    assert item.person == "你"
    assert item.title == "Add stale badge"


@pytest.mark.parametrize("kind", ["🐛", "👀"])
def test_parse_item_non_own_pr_row_still_requires_author(kind):
    line = f'- [ ] {kind} #9201 **待 review** Δ +52/-9 — "Missing author"'

    assert hook.parse_item(line) is None


def test_render_board_uses_section_tables_and_scan_friendly_columns():
    rendered = hook.render_board(BOARD)

    assert rendered.count('<table class="work-table">') == 2
    assert '<th class="handled-cell">✓</th>' in rendered
    assert "<th>球</th>" in rendered
    assert "<th>動作</th>" in rendered
    # 7 欄舊表頭已收斂成 3 欄——舊欄位標題不該再出現（handled-cell 的 aria-label
    # 仍沿用「我處理過」措辭，只檢查表頭本身已改掉）
    assert '<th class="handled-cell">我處理過</th>' not in rendered
    assert "現況" not in rendered
    assert "下一步" not in rendered
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
    assert rendered.count('data-kind="🐛"') == 2
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

    assert '<option value="author">' not in rendered
    assert 'data-author="bob"' not in rendered
    assert 'data-status="NEEDS_CHANGES"' in rendered
    assert 'data-title="tighten validation"' in rendered
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


def test_render_board_forces_section_open_when_it_holds_unknown_status():
    """`status-unknown` 不能只在列級大聲失敗——如果它所在的 section 不是 🎯（預設
    收合），使用者不點開就永遠看不到。任何 marker 只要含有 status-unknown 的列都
    要強制展開（點 2，對照 SKILL.md §6 的「不會靜默落灰」宣稱）。"""
    board = (
        "# Work Board — Lee-W/maigo\n"
        "## 📥 無法分類（1）\n"
        '- [ ] 🐛 #9299 (jack) **手改壞的狀態詞** — "title"\n'
    )

    rendered = hook.render_board(board)

    details_index = rendered.index('<details class="board-section-body"')
    assert rendered[details_index : details_index + 60].startswith(
        '<details class="board-section-body" open markdown="1">'
    )


def test_render_board_marks_unparseable_title_with_warning_text():
    """title 解析失敗（整行找不到 `— "…"` 欄位）比照 status-unknown 大聲顯示，
    不靜默留空成 `<em>無標題</em>`（點 3/4 (c)）。"""
    board = (
        "# Work Board — Lee-W/maigo\n"
        "## 🎯 你的球（1）\n"
        "- [ ] 🐛 #1 (alice) **READY** — no quotes anywhere in this line\n"
    )

    rendered = hook.render_board(board)

    assert "⚠ 無法解析此列" in rendered
    assert "<em>無標題</em>" not in rendered


def test_render_board_forces_section_open_when_title_unparseable():
    """title 解析失敗也要強制展開所在 section，理由同 status-unknown（點 2 的通用
    化：「任何 section 只要含有需要注意的列」，不是只硬寫死 📥／status-unknown）。"""
    board = (
        "# Work Board — Lee-W/maigo\n"
        "## ⏳ 等別人（1）\n"
        "- [ ] 🐛 #1 (alice) **READY** — no quotes anywhere in this line\n"
    )

    rendered = hook.render_board(board)

    details_index = rendered.index('<details class="board-section-body"')
    assert rendered[details_index : details_index + 60].startswith(
        '<details class="board-section-body" open markdown="1">'
    )


def test_parse_item_tolerates_missing_whitespace_around_status_annotation():
    """狀態詞旁註 `（…）` 與緊接著的 `Δ`／`—` 之間可以沒有空格——nvim 手改最容易漏
    這格空白，曾經讓要求 `\\s+` 的欄位 regex 完全吃不到、Δ 改動量與 title 被靜默
    丟掉（點 3/4 (b)，對照 `.maigo/board.md`/SKILL.md 曾經踩過的真實壞行）。
    現在旁註是位置式消耗掉的，空格有沒有留都不影響後面欄位的定位。"""
    diff_item = hook.parse_item(
        '- [x] 👀 #700 (dave) **APPROVE**（merged 07-07）Δ +31/-9 — "no space before delta"'
    )
    assert diff_item is not None
    assert diff_item.additions == 31
    assert diff_item.deletions == 9

    title_item = hook.parse_item(
        "- [ ] 🐛 #99 (eve) **已放棄**（`--drop` 軟刪，7 天後可清）"
        '— "no space before dash"'
    )
    assert title_item is not None
    assert title_item.title_ok is True
    assert title_item.title == "no space before dash"


def test_parse_item_title_ok_false_when_title_grammar_completely_missing():
    """跟「旁註空白容錯」（上一條測試）不同：這裡整行根本沒有 `"<title>"` 語法，
    `title_ok` 要能分辨「格式壞掉」跟「有引號但故意留空 `""`」兩種情況。"""
    broken = hook.parse_item(
        "- [ ] 🐛 #1 (alice) **READY** — no quotes at all in this line"
    )
    assert broken is not None
    assert broken.title_ok is False
    assert broken.title == ""

    explicitly_empty = hook.parse_item('- [ ] 🐛 #2 (bob) **READY** — ""')
    assert explicitly_empty is not None
    assert explicitly_empty.title_ok is True
    assert explicitly_empty.title == ""


# 判斷句是自由文字：它含什麼字元都不得污染前面的欄位。
#
# 下面這批測試釘住的是行文法的根本限制：欄位分隔符 `—` 本身會自然出現在使用者
# 手寫的判斷句裡（中文引述、`——` 強調），所以欄位不能靠「掃整行找 pattern」來
# 認。歷史上兩種掃描鬆緊都各自壞過一次：
#   1. `\\s+`（要求分隔符前有空白）→ 使用者少打一個空格就靜默丟掉整個 title；
#   2. `\\s*`（不要求空白）→ 判斷句裡的 `—"…"`、`Δ+N/-M` 被誤判成本行的欄位。
# 現在改成由左而右逐欄消耗、判斷句是「其餘剩下的」，兩種壞法都不成立。


def test_parse_item_judgment_may_quote_with_em_dash_without_stealing_title():
    """判斷句用 em dash 引述別人的話（`使用者說—"先別動"`）時，那組引號不是
    title 欄位——title 已經在它前面的位置被消耗掉了。"""
    item = hook.parse_item(
        '- [ ] 🐛 #701 (alice) **待 triage** — "真 title" '
        '— 使用者說—"先別動" 要不要照做'
    )

    assert item is not None
    assert item.title == "真 title"
    assert item.title_ok is True
    assert item.reason == '使用者說—"先別動" 要不要照做'


def test_parse_item_quoted_judgment_without_title_stays_intact_and_loud():
    """同樣的引述，但這行**根本沒有** title 欄位：不能把判斷句裡的引號當成
    title 撿來用（那會讓判斷句被腰斬且無人察覺），要整句留著並回報格式壞掉。"""
    item = hook.parse_item(
        '- [ ] 🐛 #702 (alice) **待 triage** 使用者說—"先別動" 要不要照做'
    )

    assert item is not None
    assert item.title_ok is False
    assert item.title == ""
    assert item.reason == '使用者說—"先別動" 要不要照做'


def test_parse_item_judgment_mentioning_another_items_delta_is_not_this_rows_diff():
    """判斷句提到「別的 PR 改了多少行」時，那個 `Δ+N/-M` 不是本行的改動量——
    🐛 issue 本來就沒有 Δ 欄位，不該憑空長出一個。"""
    issue = hook.parse_item(
        '- [ ] 🐛 #703 (alice) **待 triage** — "t" — 相關 PR 改了Δ+5/-3的部分'
    )

    assert issue is not None
    assert issue.additions is None
    assert issue.deletions is None
    assert issue.reason == "相關 PR 改了Δ+5/-3的部分"


def test_parse_item_own_delta_wins_over_delta_mentioned_in_judgment():
    """本行真的有 Δ 欄位時，判斷句裡另一組 `Δ+N/-M` 不得覆蓋它。"""
    item = hook.parse_item(
        '- [ ] 🔀 #704 **CI 紅** Δ +52/-9 — "t" — 另一個改動Δ+9/-1 要不要跟'
    )

    assert item is not None
    assert (item.additions, item.deletions) == (52, 9)
    assert item.reason == "另一個改動Δ+9/-1 要不要跟"


def test_parse_item_judgment_may_contain_dashes_badges_and_artifact_emoji():
    """`——`（強調）、`🧠`/`💤`（badge 字面）、裸 `📄`（沒有 backtick 路徑）
    出現在判斷句裡都只是文字，不得被當成欄位吃掉。"""
    item = hook.parse_item(
        '- [ ] 🐛 #705 (alice) **待 triage** — "t" '
        "— 能重現嗎——不能就 NEEDS_INFO；這要 🧠 想一下，別 💤，附件 📄 也還沒收到"
    )

    assert item is not None
    assert item.reason == (
        "能重現嗎——不能就 NEEDS_INFO；這要 🧠 想一下，別 💤，附件 📄 也還沒收到"
    )
    assert item.learned is False
    assert item.stale is False
    assert item.artifact is None


def test_parse_item_title_may_contain_quotes():
    """title 內含未跳脫的引號（GitHub PR 標題很常見，如 `Fix "foo" handling`）
    不得在第一個內層引號就被截斷——收尾引號是「後面接行尾／`—`／`📄`」的那個。"""
    with_judgment = hook.parse_item(
        '- [ ] 🐛 #709 (alice) **READY** — "Fix "foo" handling" — 要不要改'
    )
    assert with_judgment is not None
    assert with_judgment.title == 'Fix "foo" handling'
    assert with_judgment.reason == "要不要改"

    at_line_end = hook.parse_item(
        '- [ ] 🐛 #710 (alice) **READY** — "Fix "foo" handling"'
    )
    assert at_line_end is not None
    assert at_line_end.title == 'Fix "foo" handling'
    assert at_line_end.reason == ""


def test_parse_item_judgment_ending_with_a_quote_does_not_extend_the_title():
    """判斷句以引號收尾（`他說"不要"`）時，title 仍然是前面那一組——
    收尾引號的判定是「第一個合法收尾」，不是「整行最後一個引號」。"""
    item = hook.parse_item('- [ ] 🐛 #711 (alice) **READY** — "t" — 他說"不要"')

    assert item is not None
    assert item.title == "t"
    assert item.reason == '他說"不要"'


def test_parse_item_empty_judgment_sentence():
    """判斷句 optional：省略時 reason 是空字串，不是把 title 或分隔符撿進來。"""
    item = hook.parse_item('- [ ] 🐛 #712 (alice) **READY** — "t"')

    assert item is not None
    assert item.title == "t"
    assert item.reason == ""


def test_parse_item_status_annotation_may_nest_brackets_and_backticks():
    """旁註 `（…）` 內含巢狀全形括號、以及 backtick code span 裡的 `）`——
    括號配對要跳過 code span，否則旁註會在錯的地方被切斷、Δ 跟著解析不到。"""
    item = hook.parse_item(
        "- [ ] 🐛 #713 (alice) **IN_PROGRESS**（分支 `feat/a）b`（外層））"
        'Δ +1/-2 — "t" — 判斷'
    )

    assert item is not None
    assert (item.additions, item.deletions) == (1, 2)
    assert item.title == "t"
    assert item.note == "（分支 `feat/a）b`（外層））"
    assert item.reason == "判斷"


def test_parse_item_legacy_grammar_without_next_action_command():
    """向下相容：舊格式沒有 `→ 命令` 的行（title 一樣在行尾）。"""
    item = hook.parse_item(
        '- [ ] 🔀 #460 (你) **等 review** Δ +88/-12 — 最後活動是你 07-12 — "add board tables"'
    )

    assert item is not None
    assert item.person == "你"
    assert item.title == "add board tables"
    assert item.reason == "最後活動是你 07-12"
    assert item.action is None
    assert (item.additions, item.deletions) == (88, 12)


def test_parse_item_badges_written_before_delta_still_count():
    """badge 與 Δ 的相對順序寫反（手改常見）不該讓 badge 靜默消失。"""
    item = hook.parse_item('- [ ] 🔀 #714 **CI 紅** 💤 Δ +5/-1 — "t"')

    assert item is not None
    assert item.stale is True
    assert (item.additions, item.deletions) == (5, 1)


def test_parse_item_new_format_judgment_mentioning_arrow_command_is_not_legacy():
    """`_LEGACY_ACTION_RE` 曾經對整個 tail 做無邊界 `search()`——新格式的判斷句只要
    提到 `→ \\`command\\`` 這種措辭（引用某個 maigo 命令很常見），就會被誤判成舊格式，
    title 平白消失。legacy 偵測必須錨定在「title 之前的字串是否真的以此收尾」，
    而不是整行掃描。"""
    item = hook.parse_item(
        '- [ ] 🐛 #9101 (alice) **待 triage** — "CLI crash" '
        "— 之前建議 → `/maigo:review 123` 但user拒絕"
    )

    assert item is not None
    assert item.title_ok is True
    assert item.title == "CLI crash"
    assert item.reason == "之前建議 → `/maigo:review 123` 但user拒絕"
    assert item.action is None


def test_parse_item_missing_title_separator_with_trailing_quote_fails_loudly():
    """新舊格式共用 `_consume_leading_title`：使用者漏打 title 與判斷句之間的分隔
    符，且判斷句恰好以孤立引號收尾時，最右邊的引號本來會被誤認成 title 的收尾
    引號，把判斷句整段靜默黏進 title（`title_ok` 仍為 `True`，沒有任何警告）。
    現在必須大聲失敗，不能靜默腐蝕資料。"""
    item = hook.parse_item(
        '- [ ] 🐛 #1 (alice) **READY** — "real title"忘記加分隔符，判斷句以引號結尾"'
    )

    assert item is not None
    assert item.title_ok is False
    assert item.title == ""


def test_parse_item_missing_separator_with_paired_stray_quotes_fails_loudly():
    """同一個「漏打分隔符」壞法的另一種形狀：舊版靠「跳過的引號數是奇是偶」判斷
    收尾引號合不合法，這裡漏打分隔符後的殘句恰好含**一組成對**引號（`他說 "先
    別動"`，偶數），parity 檢查完全抓不到，會把整段判斷句連著兩個引號一起黏進
    title。分隔符必須是強制的，不是猜出來的——這裡也要 `title_ok=False`。"""
    item = hook.parse_item(
        '- [ ] 🔀 #6 **有衝突** Δ +1/-1 — "Real Title" 他說 "先別動"'
    )

    assert item is not None
    assert item.title_ok is False
    assert item.title == ""


def test_parse_item_new_format_judgment_ending_in_arrow_command_keeps_full_reason():
    """`_TRAILING_ACTION_RE` 曾經對所有格式無條件套用——新格式的判斷句就算恰好
    以 `→ \\`command\\`` **收尾**（不像上一條那樣後面還有文字），也只是自由文字引
    用了某個 maigo 命令，不是舊格式的 action 欄位，不該被腰斬掉。"""
    item = hook.parse_item(
        '- [ ] 🔀 #11 **有衝突** Δ +1/-1 — "Real Title" — 之後跑 → `/maigo:review 123`'
    )

    assert item is not None
    assert item.title_ok is True
    assert item.title == "Real Title"
    assert item.reason == "之後跑 → `/maigo:review 123`"
    assert item.action is None


def test_parse_item_line_grammar_reference_cases_stay_correct():
    """釘住行文法的一批代表性形狀，逐條核對斷言值：note-only reason、判斷句提到
    別行的 Δ、embedded quote title、判斷句裡的裸 `📄`、以及三種舊格式（純
    action／純 action 無 artifact／action ＋ artifact 都有）。任何一條壞掉都代表
    上面兩個修復動到了不該動的地方。"""
    with_own_dashed_quote = hook.parse_item(
        '- [ ] 🔀 #1 **CI 紅** Δ +5/-2 — "Real Title" — 使用者說—"先別動" 要不要照做'
    )
    assert with_own_dashed_quote is not None
    assert with_own_dashed_quote.title == "Real Title"
    assert with_own_dashed_quote.reason == '使用者說—"先別動" 要不要照做'

    other_items_delta = hook.parse_item(
        '- [ ] 🐛 #2 (alice) **READY** — "Real Title" — 對照 #99 的 Δ+3/-1 決定要不要跟'
    )
    assert other_items_delta is not None
    assert other_items_delta.additions is None
    assert other_items_delta.deletions is None

    note_only_reason = hook.parse_item(
        '- [x] 👀 #3 (bob) **APPROVE**（merged 07-12）Δ +143/-52 — "Real Title"'
    )
    assert note_only_reason is not None
    assert (note_only_reason.additions, note_only_reason.deletions) == (143, 52)
    assert note_only_reason.note == "（merged 07-12）"
    assert note_only_reason.reason == ""

    note_no_diff = hook.parse_item(
        '- [ ] 🐛 #4 (eve) **已放棄**（`--drop` 軟刪）— "Real Title"'
    )
    assert note_no_diff is not None
    assert note_no_diff.title == "Real Title"

    embedded_quote_title = hook.parse_item(
        '- [ ] 🐛 #9 (alice) **READY** — "標題 "內嵌" 結束" — 判斷 "甲" 或 "乙"'
    )
    assert embedded_quote_title is not None
    assert embedded_quote_title.title == '標題 "內嵌" 結束'
    assert embedded_quote_title.reason == '判斷 "甲" 或 "乙"'

    bare_artifact_emoji_in_judgment = hook.parse_item(
        '- [ ] 🐛 #12 (alice) **READY** — "Real Title" — 記得看 📄 那份設計稿'
    )
    assert bare_artifact_emoji_in_judgment is not None
    assert bare_artifact_emoji_in_judgment.artifact is None

    legacy_action_only = hook.parse_item(
        "- [ ] 🔀 #14 (你) **CHANGES_REQUESTED** Δ +286/-74 — reviewer 要改 "
        '→ `/maigo:address-comments` — "Old Title"'
    )
    assert legacy_action_only is not None
    assert legacy_action_only.title == "Old Title"
    assert legacy_action_only.action == "/maigo:address-comments"
    assert legacy_action_only.reason == "reviewer 要改"

    legacy_action_no_diff = hook.parse_item(
        "- [ ] 🐛 #15 (alice) **READY** — triage 完可接 "
        '→ `/maigo:take-issue 15` — "Old Title"'
    )
    assert legacy_action_no_diff is not None
    assert legacy_action_no_diff.title == "Old Title"
    assert legacy_action_no_diff.action == "/maigo:take-issue 15"

    legacy_action_and_artifact = hook.parse_item(
        "- [x] 👀 #16 (carol) **↩︎ 回你的球** Δ +91/-38 — 又推了 commit "
        '→ `/maigo:review 16` 📄 `review-16.md` — "Old Title"'
    )
    assert legacy_action_and_artifact is not None
    assert legacy_action_and_artifact.title == "Old Title"
    assert legacy_action_and_artifact.action == "/maigo:review 16"
    assert legacy_action_and_artifact.artifact == "review-16.md"
    assert legacy_action_and_artifact.reason == "又推了 commit"


def test_render_board_keeps_section_headings_as_real_markdown_for_toc():
    """MkDocs 的 TOC regression 修復：`## ` 這行必須原封不動輸出（讓 MkDocs 發出真
    正的 `<h2>`），不能被改寫成 `<summary>`——那樣 Material 右側目錄會整個是空的
    （點 1）。只有表格本體才收進 `<details class="board-section-body">`。"""
    rendered = hook.render_board(BOARD)

    assert "## 🎯 你的球（2）" in rendered
    assert "## ⏳ 等別人（1）" in rendered
    assert "<summary>🎯 你的球（2）</summary>" not in rendered
    assert "<summary>⏳ 等別人（1）</summary>" not in rendered
    assert 'class="board-section-body"' in rendered


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
    # heading 保留為真正的 `## ` markdown（見 TOC 相關測試），不再被改寫成 summary
    assert "## 🗄️ 已放棄（1）" in rendered
    assert "status-done" in rendered  # 已放棄 => Tier.DONE


def test_malformed_line_is_left_untouched():
    malformed = "- [ ] 這是使用者自訂備註"
    assert malformed in hook.render_board(malformed)


def test_render_board_action_cell_uses_next_action_for_status_plus_target():
    """動作欄由 `next_action_for_status()` ＋ item id 組出可複製命令（點 C）。"""
    rendered = hook.render_board(BOARD)

    assert (
        'data-copy-command="/maigo:take-issue 123">/maigo:take-issue 123</button>'
        in rendered
    )


def test_render_board_action_cell_blank_when_no_next_action():
    """`NEEDS_CHANGES`（WAITING）／`等 review`（AWAITING_REVIEW）都沒有預設
    下一步——動作欄留白（點 C）。"""
    rendered = hook.render_board(BOARD)

    assert rendered.count('<td class="action-cell"></td>') == 2


def test_render_board_moves_author_diff_status_artifact_into_row_detail():
    """作者/Δ/狀態詞原文/📄 產物移入每列的 ⌄ 展開區，不再各自成欄（點 C）。"""
    rendered = hook.render_board(BOARD)

    assert (
        '<div class="row-detail-item"><span class="work-author">bob</span></div>'
        in rendered
    )
    assert (
        '<div class="row-detail-item"><span class="diff-add">+120</span> '
        '<span class="diff-delete">−45</span></div>' in rendered
    )
    assert (
        '<div class="row-detail-item"><span class="work-status status-wait">'
        "NEEDS_CHANGES</span></div>" in rendered
    )
    assert (
        '<div class="row-detail-item"><a class="artifact-link" '
        'href="../review-9/">📄 review-9.md</a></div>' in rendered
    )


def test_render_board_keeps_status_note_in_detail_and_judgment_in_ball_cell():
    board = (
        "# Work Board — Lee-W/maigo\n"
        "## ⏳ 等別人（1）\n"
        "- [ ] 🐛 #9103 (erin) **NEEDS_INFO**（已請補完整 log） "
        '— "Hook exits" — 能不能穩定重現\n'
    )

    rendered = hook.render_board(board)

    assert '<div class="work-reason">能不能穩定重現</div>' in rendered
    assert (
        '<span class="work-status status-wait">NEEDS_INFO</span> '
        '<span class="work-note">（已請補完整 log）</span>' in rendered
    )
    assert '<div class="work-reason">（已請補完整 log）' not in rendered


def test_render_board_tier_shown_as_row_left_border_class_not_column():
    """tier 改用列左側色條（tr class）呈現，不再獨立成欄（點 C）。"""
    rendered = hook.render_board(BOARD)

    assert "tier-row status-act" in rendered  # READY => Tier.ACT
    assert '<td class="status-cell">' not in rendered


def test_render_board_no_muted_placeholder_dashes_for_empty_values():
    """空值（無 Δ、無判斷句）不再印 `—` 佔位（點 C 最後一項）。"""
    board = (
        "# Work Board — Lee-W/maigo\n"
        "## 🎯 你的球（1）\n"
        '- [ ] 🐛 #501 (carol) **待 triage** — "no diff no reason"\n'
    )

    rendered = hook.render_board(board)

    assert 'class="muted"' not in rendered


def test_render_board_default_open_state_only_target_section_expanded():
    """只有 🎯 你的球預設展開；其餘分區（如 ⏳）預設收合（點 D）。"""
    rendered = hook.render_board(BOARD)

    target_index = rendered.index("## 🎯 你的球（2）")
    target_details = rendered.index('<details class="board-section-body"', target_index)
    assert rendered[target_details : target_details + 60].startswith(
        '<details class="board-section-body" open markdown="1">'
    )

    wait_index = rendered.index("## ⏳ 等別人（1）")
    wait_details = rendered.index('<details class="board-section-body"', wait_index)
    assert rendered[wait_details : wait_details + 60].startswith(
        '<details class="board-section-body" markdown="1">'
    )


def test_render_board_explains_checkbox_is_orthogonal_to_tiers():
    rendered = hook.render_board(BOARD)

    assert "正交" in rendered
    assert "--learn" in rendered
    assert "打勾不會換分區" in rendered

    header_index = rendered.index("# Work Board")
    note_index = rendered.index("正交")
    first_table_index = rendered.index('<table class="work-table">')
    assert header_index < note_index < first_table_index


def test_hook_only_changes_board_page():
    page = SimpleNamespace(file=SimpleNamespace(src_uri="review-9.md"))
    assert hook.on_page_markdown(BOARD, page) == BOARD
