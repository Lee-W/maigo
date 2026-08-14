"""MkDocs hook that renders the line-oriented Work Board as scan-friendly tables."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import quote

try:
    from scripts import board_state
except (
    ImportError
):  # pragma: no cover - mkdocs 用檔案路徑直接載入本檔，不經 `scripts` 套件
    import board_state  # type: ignore[no-redef,import-not-found]

BOARD_REPO_RE = re.compile(
    r"^# Work Board — (?P<repo>[\w.-]+/[\w.-]+)\s*$", re.MULTILINE
)
SECTION_MARKER_RE = re.compile(r"^##\s+(?P<marker>\S+)")
# 只有 🎯 你的球預設展開；⏳/✅/🗄️ 都預設收合（見 `render_board` 的 section 收合）。
# 任何 section 只要含有需要注意的列（`_item_needs_attention`），一律強制展開，
# 不管 marker 是誰——見該函式的說明。
_DEFAULT_OPEN_SECTION_MARKERS = frozenset({"🎯"})
ITEM_RE = re.compile(
    r"^\s*-\s+\[(?P<checked>[ xX])\]\s+"
    r"(?P<kind>🐛|🔀|👀)\s+"
    r"(?P<item>(?:[\w.-]+/[\w.-]+)?#\d+)\s+"
    r"(?:\((?P<person>[^)]*)\)\s+)?"
    r"\*\*(?P<status>[^*]+)\*\*"
    r"(?P<tail>.*)$"
)
# Tail 逐欄消耗用的錨點。
#
# 行文法用 `—` 當欄位分隔符，而 `—` 本身會自然出現在判斷句這種自由文字裡
# （中文引述、`——` 強調），所以**不能**用「各自 global 掃整行」的 regex 分欄：
# 掃描鬆（`\s*`）會把判斷句裡的 `—"…"`、`Δ+5/-3` 誤判成本行的欄位；掃描緊
# （`\s+`）則會在使用者少打一個空格時把整個 title 靜默丟掉。兩者只是把失敗
# 位置搬來搬去。
#
# 這裡改成**位置式解析**：從 `**狀態詞**` 之後由左而右逐欄消耗，每消耗一欄就把
# 它從剩餘字串前緣切掉，順序固定為
#   旁註（…）? → Δ +A/-D? → badges? → — "title" → 判斷句 → 📄 `產物`?
# 判斷句是「其餘剩下的」，因此它含什麼字元都不可能影響前面欄位的判定——
# 所有 pattern 都錨定在剩餘字串的**開頭**（`^`）或**結尾**（`$`），沒有一個是
# 對整行做無邊界感知的 `search()`。
#
# title 不靠破折號定位，靠它必然存在的引號：讀到 `— "` 之後，往右在「頂層」
# （沒有正在跳過一組巢狀引號）找第一個「後面接著判斷句分隔符 `—`／`📄` 產物／
# 行尾」的引號當結尾——所以 title 內含引號（`"Fix "foo" handling"`）不會被
# 提早截斷，判斷句裡的引號也不會被誤認成 title。頂層引號若沒接到這三種收尾，
# 只允許它是「開啟一段巢狀引號」（typographic 慣例：開引號前面接空白／行首，
# 收引號直接貼著前一個字）——貼字的頂層引號沒接到收尾，代表 title／判斷句之間
# 的分隔符被漏打了，整段解析立刻放棄（不是繼續往右找別的引號硬湊出一個看似
# 合理的切法）。這裡不再用「跳過的引號數是奇是偶」判斷收尾合不合法：漏打分隔
# 符的殘句只要恰好含一組成對引號（偶數），奇偶檢查完全抓不到，會把整段判斷句
# 靜默黏進 title；貼字／空白的開闔字元判定才是真正能區分「合法巢狀引號」跟
# 「漏打分隔符」的訊號，見 `_consume_leading_title`。
_NOTE_PAIRS = {"（": "）", "(": ")"}
_EM_DASH_RE = re.compile("—")
_LEADING_DIFF_RE = re.compile(r"^\s*Δ\s*\+(?P<additions>\d+)\s*/\s*-(?P<deletions>\d+)")
_LEADING_BADGE_RE = re.compile(r"^\s*(?P<badge>🧠|💤)")
_TITLE_OPEN_RE = re.compile(r'^\s*—\s*"')
# title 收尾引號後面接的**明確分隔符**：判斷句的 `—`，或產物欄的 `📄`。「行尾」
# 也是合法收尾，但不是靠這個 regex 判斷——見 `_consume_leading_title`。
_TITLE_SEPARATOR_END_RE = re.compile(r"^\s*(?:—|📄)")
_TRAILING_ARTIFACT_RE = re.compile(r"\s*📄\s*`(?P<artifact>[^`]+)`\s*$")
_TRAILING_ACTION_RE = re.compile(r"\s*→\s*`(?P<action>[^`]+)`\s*$")
# 舊行文法獨有的欄位（新文法已拿掉 `→ 命令`）——出現它就代表這行是舊格式，
# title 在行尾而不是判斷句之前。新舊格式的判定不能對整個 tail 做無邊界
# `search()`——新格式的判斷句是自由文字，常會提到「→ `command`」這種措辭
# （例如引用某個 maigo 命令），若整行掃描就會把合法的新格式行誤判成舊格式，
# 判斷句被腰斬。判定改為結果導向：先試著把 tail 當新格式解出 leading title，
# 失敗才試舊格式的 trailing title——哪一次成功就決定 `is_legacy`（見
# `_consume_title`）；只有 `is_legacy=True` 時才會再去消耗 `_TRAILING_ACTION_RE`，
# 新格式判斷句就算恰好以 `→ \`command\`` 收尾，也只是自由文字，不會被腰斬。

CHECKBOX_NOTE = """\
<details class="board-checkbox-note" markdown="1">
<summary>打勾 checkbox 是什麼意思？</summary>

打勾 `[ ]`/`[x]` 只代表「我親自處理過了」，會影響之後 `--learn` 記憶學習閘門的判斷；
跟項目在哪個分區（🎯/⏳/✅）完全**正交**——**打勾不會換分區**。

真正讓項目換分區的，是你在 GitHub 上的實際動作（push 修正、回覆、送出 review）
加上下次 `/maigo:board` 刷新——分區是依最新 GitHub 狀態自動判定的，不是手動控制的。

</details>
"""

FILTER_CONTROLS = """\
<div class="work-controls" aria-label="Work Board 篩選與排序">
  <label class="search-control"><span>搜尋</span><input id="board-search" type="search" placeholder="標題、作者、狀態…"></label>
  <label><span>類型</span><select id="board-kind"><option value="">全部類型</option><option value="🐛">Issue</option><option value="🔀">你的 PR</option><option value="👀">Review PR</option></select></label>
  <label><span>狀態</span><select id="board-status"><option value="">全部狀態</option></select></label>
  <label><span>排序</span><select id="board-sort"><option value="board">原本順序</option><option value="title">標題 A→Z</option><option value="changes-desc">改動量：大→小</option><option value="changes-asc">改動量：小→大</option></select></label>
  <button id="board-reset" type="button">清除</button>
  <span id="board-visible-count" class="visible-count" aria-live="polite"></span>
</div>
"""


@dataclass(frozen=True)
class BoardItem:
    checked: bool
    kind: str
    item: str
    person: str
    status: str
    note: str
    reason: str
    title: str
    title_ok: bool
    action: str | None
    artifact: str | None
    learned: bool
    stale: bool
    additions: int | None
    deletions: int | None


def _matching_close_index(text: str) -> int | None:
    """Index of the `）` closing `text[0]`'s bracket, or `None` when unbalanced.

    Nested brackets are counted, and backtick code spans are skipped whole — a
    branch name annotation like ``（分支 `feat/a）b`）`` must not be cut at the
    bracket that lives inside the code span.
    """
    opener = text[0]
    closer = _NOTE_PAIRS[opener]
    depth = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char == "`":
            close = text.find("`", index + 1)
            if close == -1:
                return None
            index = close + 1
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _consume_notes(rest: str) -> tuple[str, str]:
    """Consume the 旁註 `（…）` groups that sit right after the status word."""
    notes: list[str] = []
    while True:
        stripped = rest.lstrip()
        if not stripped or stripped[0] not in _NOTE_PAIRS:
            break
        close = _matching_close_index(stripped)
        if close is None:
            break
        notes.append(stripped[: close + 1])
        rest = stripped[close + 1 :]
    return " ".join(notes), rest


def _consume_diff(rest: str) -> tuple[int | None, int | None, str]:
    """Consume `Δ +A/-D` **only** at the field position, never mid-sentence."""
    match = _LEADING_DIFF_RE.match(rest)
    if match is None:
        return None, None, rest
    return (
        int(match.group("additions")),
        int(match.group("deletions")),
        rest[match.end() :],
    )


def _consume_badges(rest: str) -> tuple[bool, bool, str]:
    """Consume 🧠/💤 badges at the field position (a badge inside the judgment
    sentence is prose, not a badge)."""
    learned = stale = False
    while (match := _LEADING_BADGE_RE.match(rest)) is not None:
        if match.group("badge") == "🧠":
            learned = True
        else:
            stale = True
        rest = rest[match.end() :]
    return learned, stale, rest


def _consume_leading_title(text: str) -> tuple[str, str] | None:
    """Consume a mandatory `— "<title>"` field at the front of `text`.

    Returns `(title, remainder)`, or `None` when the front of `text` is not a
    well-formed title field — the separator is required, not guessed.

    Scanning is done at "top level" (`inside_nested_quote is False`) unless
    we've deliberately stepped inside an embedded quoted sub-phrase. At top
    level, a quote is a valid title-boundary candidate — accepted when it is
    followed by an explicit separator (`_TITLE_SEPARATOR_END_RE`: ` — `
    starting 判斷句, or ` 📄 ` starting the artifact field) **or** when
    nothing else follows on the line at all (a title with no 判斷句).

    A top-level quote that matches neither shape is only allowed to be the
    *opening* of a legitimate embedded sub-phrase (`"Fix "foo" handling"`) —
    and typographically, an opening quote is preceded by whitespace (or sits
    right at the start of the title). If it instead hugs the previous
    character (`"real title"忘記加分隔符...`), that shape can only be a
    genuine title's own closing quote that failed to land on a separator —
    proof the line is malformed, not an embedded quote to skip past. Give up
    right there instead of continuing to scan for some other quote further
    down the line that happens to end the string; that used to be decided by
    whether an even or odd number of quotes were skipped, but a missing
    separator whose runaway 判斷句 happens to contain one *paired* quote
    (`"real title"忘記加分隔符 "先別動"`) is structurally indistinguishable
    from a legitimate nested title under quote-count parity alone — nothing
    short of the open/close adjacency check actually tells them apart.

    Once inside a nested sub-phrase, the next quote unconditionally closes it
    (back to top level) — it is not itself evaluated as a boundary candidate,
    since it's the *inner* phrase's own quote, not the title's.
    """
    opening = _TITLE_OPEN_RE.match(text)
    if opening is None:
        return None
    start = opening.end()
    cursor = start
    inside_nested_quote = False
    while (close := text.find('"', cursor)) != -1:
        remainder = text[close + 1 :]
        if inside_nested_quote:
            inside_nested_quote = False
        else:
            if _TITLE_SEPARATOR_END_RE.match(remainder) or not remainder.strip():
                return text[start:close], remainder
            preceding = text[close - 1] if close > start else ""
            if preceding and not preceding.isspace():
                return None
            inside_nested_quote = True
        cursor = close + 1
    return None


def _consume_trailing_title(text: str) -> tuple[str, str] | None:
    """Legacy layout: the title is the last field on the line.

    Anchored from the right — try each `—` from the end backwards and keep the
    first one whose title field consumes everything up to end-of-line.
    """
    for dash in reversed([match.start() for match in _EM_DASH_RE.finditer(text)]):
        consumed = _consume_leading_title(text[dash:])
        if consumed is not None and not consumed[1].strip():
            return consumed[0], text[:dash]
    return None


def _consume_title(text: str) -> tuple[str, str, bool] | None:
    """Consume the mandatory title field, new-format position first, legacy
    trailing position as fallback.

    Returns `(title, remainder, is_legacy)`, or `None` when neither position
    yields a well-formed `— "<title>"` field. `is_legacy` tells
    `parse_item()` whether a `→ \\`command\\`` still sitting in `remainder`
    is the legacy action field (only true legacy layout carries one) or just
    free-text 判斷句 prose that happens to quote a maigo command — see the
    module-level comment above `_TRAILING_ACTION_RE`.
    """
    consumed = _consume_leading_title(text)
    if consumed is not None:
        return consumed[0], consumed[1], False
    consumed = _consume_trailing_title(text)
    if consumed is not None:
        return consumed[0], consumed[1], True
    return None


def _strip_trailing(
    text: str, pattern: re.Pattern[str], group: str
) -> tuple[str, str | None]:
    """Consume an end-anchored field (`📄 產物` / legacy `→ 命令`) off `text`."""
    match = pattern.search(text)
    if match is None:
        return text, None
    return text[: match.start()], match.group(group)


def parse_item(line: str) -> BoardItem | None:
    """Parse one canonical board line; unknown lines stay untouched by the hook.

    Fields are consumed positionally left-to-right (see the anchor block above),
    so the free-text 判斷句 — the one field users hand-write — is simply
    "whatever is left" and can contain `—`, `——`, `Δ`, `📄` or quotes without
    corrupting any earlier field.
    """
    match = ITEM_RE.fullmatch(line)
    if match is None:
        return None
    person = match.group("person")
    if person is None and match.group("kind") != "🔀":
        return None

    rest = match.group("tail")
    note, rest = _consume_notes(rest)
    # Δ 在文法上排在 badges 之前，但手改時容易寫反——兩側都掃一次，寫反了
    # 也不會讓某個 badge 靜默消失。
    learned, stale, rest = _consume_badges(rest)
    additions, deletions, rest = _consume_diff(rest)
    trailing_learned, trailing_stale, rest = _consume_badges(rest)
    learned, stale = learned or trailing_learned, stale or trailing_stale

    # 新格式的 title 就在這個位置；舊格式（有 `→ 命令`）的 title 在行尾。
    consumed_title = _consume_title(rest)
    # `consumed_title is None` ＝ 這行沒有可辨識的 `— "…"` title 欄位——不是
    # 「標題留空」（那會是 `— ""`，仍然解析得到），而是格式壞掉。這種情況不能
    # 靜默留空，`render_table()` 要大聲顯示、`render_board()` 要強制展開 section
    # （見 `_item_needs_attention`）。
    title_ok = consumed_title is not None
    if consumed_title is not None:
        title, rest, is_legacy = consumed_title
    else:
        title, rest, is_legacy = "", rest, False

    rest, artifact = _strip_trailing(rest, _TRAILING_ARTIFACT_RE, "artifact")
    # 只有舊格式才有 `→ 命令` 這個欄位；新格式的判斷句是自由文字，就算恰好以
    # `→ \`command\`` 收尾也不該被腰斬——見 `_TRAILING_ACTION_RE` 上方註解。
    action = None
    if is_legacy:
        rest, action = _strip_trailing(rest, _TRAILING_ACTION_RE, "action")
    judgment = rest.strip().removeprefix("—").strip()

    return BoardItem(
        checked=match.group("checked").lower() == "x",
        kind=match.group("kind"),
        item=match.group("item"),
        # 🔀 列（「你的 PR」）可省略 `(你)`——person group 因此是 optional；
        # 省略時預設顯示「你」。
        person=person or "你",
        status=match.group("status"),
        note=note,
        reason=judgment,
        title=title,
        title_ok=title_ok,
        action=action,
        artifact=artifact,
        learned=learned,
        stale=stale,
        additions=additions,
        deletions=deletions,
    )


def _github_url(item: BoardItem, default_repo: str | None) -> str | None:
    repo, _, number = item.item.rpartition("#")
    repo = repo or default_repo or ""
    if not repo:
        return None
    resource = "issues" if item.kind == "🐛" else "pull"
    return f"https://github.com/{quote(repo, safe='/')}/{resource}/{number}"


def _artifact_url(path: str) -> str | None:
    artifact = PurePosixPath(path)
    if artifact.is_absolute() or ".." in artifact.parts:
        return None
    if artifact.suffix == ".md":
        artifact = artifact.with_suffix("")
        return "../" + quote(str(artifact), safe="/") + "/"
    return "../" + quote(str(artifact), safe="/")


_TIER_CLASS = {
    board_state.Tier.BLOCKED: "status-blocked",
    board_state.Tier.ACT: "status-act",
    board_state.Tier.WIP: "status-wip",
    board_state.Tier.WAIT: "status-wait",
    board_state.Tier.DONE: "status-done",
}


def _status_class(status: str) -> str:
    """5-tier class 由 `board_state` 查表；不在 enum 內的狀態大聲回 `status-unknown`。"""
    tier = board_state.tier_for_status(status)
    if tier is None:
        return "status-unknown"
    return _TIER_CLASS[tier]


def _item_needs_attention(item: BoardItem) -> bool:
    """列的哪些壞法不能被 section 收合藏住：未知狀態詞（手改壞）、title 解析
    失敗（格式壞掉靜默丟資料）。`render_board()` 用這個決定要不要強制展開整個
    section——只在單列層級大聲失敗（`status-unknown`／title 警告框）不夠，
    使用者要先展開才看得到的話，等於還是靜默落灰。"""
    return not item.title_ok or _status_class(item.status) == "status-unknown"


def _command_target(item: str) -> str:
    """Use a short target in the bound repo and a full target across repos."""
    return item.removeprefix("#")


def _copy_button(label: str, command: str, css_class: str = "") -> str:
    class_name = f"copy-command {css_class}".strip()
    return (
        f'<button class="{class_name}" type="button" '
        f'data-copy-command="{html.escape(command, quote=True)}">'
        f"{html.escape(label)}</button>"
    )


def _next_action_command(status: str, target: str) -> str | None:
    """`next_action_for_status()` ＋ item id 組出可複製命令；沒有下一步就回 `None`。"""
    next_action = board_state.next_action_for_status(status)
    if not next_action:
        return None
    return f"{next_action} {target}"


def render_table(items: list[BoardItem], default_repo: str | None) -> str:
    """Render a section as one semantic table with 3 scan-friendly columns:
    `✓`（checkbox ＋ 操作選單）／`球`（型別＋標題＋判斷句，其餘細節收進 `⌄`）／
    `動作`（可複製的下一步命令）。tier 改用列左側色條呈現，不再獨立一欄。"""
    rows: list[str] = []
    for order, item in enumerate(items):
        target = _command_target(item.item)

        # ✓ 欄：checkbox、🧠 與 board 寫入操作。
        learned = (
            '<span class="learned" title="已完成學習盤點">🧠</span>'
            if item.learned
            else ""
        )
        checkbox = " checked" if item.checked else ""
        if item.checked:
            check_action = _copy_button("取消標記", f"maigo:board --uncheck {target}")
        else:
            check_action = _copy_button("標記已處理", f"maigo:board --check {target}")
        row_actions = (
            '<details class="row-actions"><summary aria-label="項目操作">操作</summary>'
            '<div class="row-actions-menu">'
            f"{check_action}"
            f"{_copy_button('停止追蹤', f'maigo:board --drop {target}', 'drop-command')}"
            "</div></details>"
        )
        done_cell = (
            '<input class="learn-checkbox" type="checkbox" disabled'
            f'{checkbox} aria-label="我處理過 {html.escape(item.item)}">'
            f"{learned}{row_actions}"
        )

        # 球欄：型別、id、標題與判斷句；其餘細節收進 ⌄。
        issue_url = _github_url(item, default_repo)
        item_label = html.escape(item.item)
        if issue_url:
            item_label = f'<a class="work-item-id" href="{html.escape(issue_url)}">{item_label}</a>'
        if item.title_ok:
            title_html = html.escape(item.title) if item.title else "<em>無標題</em>"
            title_cell = f'<div class="work-title">{title_html}</div>'
        else:
            # title 解析失敗（見 `parse_item` 的 `title_ok`）——比照 status-unknown
            # 大聲顯示，不留空、不假裝這行沒有標題。
            title_cell = (
                '<div class="work-title work-status status-unknown">'
                "⚠ 無法解析此列（標題遺失，檢查原始格式）</div>"
            )

        status_class = _status_class(item.status)
        status_unknown = status_class == "status-unknown"
        judgment_cell = (
            f'<div class="work-reason">{html.escape(item.reason)}</div>'
            if item.reason
            else ""
        )
        # `status-unknown` 必須大聲失敗——不能被收進預設收合的 ⌄ 展開區，
        # 否則使用者不掃到那一列就永遠看不到手改壞的狀態詞。
        unknown_warning = (
            f'<div class="work-status status-unknown">'
            f"⚠ 未知狀態 {html.escape(item.status)}</div>"
            if status_unknown
            else ""
        )

        detail_items: list[str] = [
            f'<span class="work-author">{html.escape(item.person)}</span>'
        ]
        if item.additions is not None and item.deletions is not None:
            changed = item.additions + item.deletions
            detail_items.append(
                f'<span class="diff-add">+{item.additions}</span> '
                f'<span class="diff-delete">−{item.deletions}</span>'
            )
        else:
            changed = -1
        if not status_unknown:
            note_html = (
                f' <span class="work-note">{html.escape(item.note)}</span>'
                if item.note
                else ""
            )
            detail_items.append(
                f'<span class="work-status {status_class}">'
                f"{html.escape(item.status)}</span>{note_html}"
            )
        elif item.note:
            detail_items.append(
                f'<span class="work-note">{html.escape(item.note)}</span>'
            )
        if item.artifact:
            artifact_url = _artifact_url(item.artifact)
            if artifact_url:
                detail_items.append(
                    f'<a class="artifact-link" href="{html.escape(artifact_url)}">'
                    f"📄 {html.escape(item.artifact)}</a>"
                )
            else:
                detail_items.append(f"<code>📄 {html.escape(item.artifact)}</code>")
        if item.stale:
            detail_items.append('<span class="stale" title="逾期未更新">💤</span>')
        row_detail = (
            '<details class="row-detail"><summary aria-label="更多細節">⌄</summary>'
            '<div class="row-detail-body">'
            + "".join(
                f'<div class="row-detail-item">{part}</div>' for part in detail_items
            )
            + "</div></details>"
        )

        ball_cell = (
            f'<div class="work-item-title">{item.kind} {item_label}</div>'
            f"{title_cell}"
            f"{judgment_cell}{unknown_warning}{row_detail}"
        )

        # 動作欄：next_action_for_status() ＋ item id 組出的可複製命令。
        action_command = _next_action_command(item.status, target)
        action_cell = (
            _copy_button(action_command, action_command, "action-command")
            if action_command
            else ""
        )

        search_text = " ".join(
            value
            for value in (
                item.item,
                item.person,
                item.status,
                item.note,
                item.reason,
                item.title,
                item.action,
            )
            if value
        ).casefold()
        rows.append(
            f'<tr class="tier-row {status_class}" data-kind="{item.kind}" '
            f'data-status="{html.escape(item.status)}" '
            f'data-title="{html.escape(item.title.casefold())}" '
            f'data-changes="{changed}" data-order="{order}" '
            f'data-search="{html.escape(search_text)}">'
            f'<td class="handled-cell">{done_cell}</td>'
            f'<td class="ball-cell">{ball_cell}</td>'
            f'<td class="action-cell">{action_cell}</td>'
            "</tr>"
        )

    return (
        '<div class="work-table-wrap">\n'
        '<table class="work-table">\n'
        '<thead><tr><th class="handled-cell">✓</th><th>球</th>'
        "<th>動作</th></tr></thead>\n"
        "<tbody>\n" + "\n".join(rows) + "\n</tbody>\n</table>\n</div>"
    )


def render_board(markdown: str) -> str:
    """Replace each board section's canonical items with one sortable table.

    Each `## ` line stays a **real markdown heading** — MkDocs turns it into an
    `<h2>` (with an id), which is exactly what feeds Material's right-hand TOC
    nav. Only the *table itself* collapses into a `<details>`: 🎯 你的球
    defaults open; ⏳/✅/🗄️ default collapsed, showing just the heading (which
    already carries the count, e.g. `⏳ 等別人（3）`) until clicked open.

    A section's table forces itself open regardless of marker whenever it
    contains a row that `_item_needs_attention()` — an unknown status word or
    an unparseable title. Otherwise a hand-broken row could sit inside a
    collapsed non-🎯 section and never be seen, which is exactly the "silent
    fade to gray" this hook promises not to do.
    """
    repo_match = BOARD_REPO_RE.search(markdown)
    default_repo = repo_match.group("repo") if repo_match else None
    lines = markdown.splitlines()
    output: list[str] = []
    pending: list[BoardItem] = []
    deferred: list[str] = []
    current_marker = ""

    def flush() -> None:
        if not pending:
            return
        force_open = current_marker in _DEFAULT_OPEN_SECTION_MARKERS or any(
            _item_needs_attention(item) for item in pending
        )
        open_attr = " open" if force_open else ""
        output.extend(
            [
                "",
                f'<details class="board-section-body"{open_attr} markdown="1">',
                '<summary class="board-section-toggle">顯示列表</summary>',
                "",
                render_table(pending, default_repo),
                "",
            ]
        )
        pending.clear()
        if deferred:
            output.extend(deferred)
            deferred.clear()
        output.extend(["", "</details>", ""])

    controls_added = False
    note_added = False

    for line in lines:
        if not note_added and line.startswith("# ") and not line.startswith("## "):
            output.append(line)
            output.extend(["", CHECKBOX_NOTE, ""])
            note_added = True
            continue
        if line.startswith("## "):
            flush()
            if not controls_added:
                output.extend(["", FILTER_CONTROLS, ""])
                controls_added = True
            marker_match = SECTION_MARKER_RE.match(line)
            current_marker = marker_match.group("marker") if marker_match else ""
            # 原封不動輸出真正的 `## ` heading——MkDocs 才會發出 `<h2>`，TOC
            # 條目才會回來。不要再把它改寫成 `<summary>`（那樣 Material 的
            # 右側目錄完全認不到，是這次要修的 regression）。
            output.extend(["", line, ""])
            continue
        item = parse_item(line)
        if item is not None:
            pending.append(item)
            continue
        if pending and (not line.strip() or line.lstrip().startswith("<!--")):
            # Blank lines and invisible notes are harmless inside a section. Keep
            # them after the table instead of fragmenting one sortable list into
            # multiple one-row tables.
            deferred.append(line)
            continue
        flush()
        output.append(line)
    flush()
    return "\n".join(output) + ("\n" if markdown.endswith("\n") else "")


def on_page_markdown(markdown: str, page, **_kwargs) -> str:
    """MkDocs event hook; other `.maigo` reports render without modification."""
    if page.file.src_uri != "board.md":
        return markdown
    return render_board(markdown)
