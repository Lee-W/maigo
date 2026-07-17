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
ITEM_RE = re.compile(
    r"^\s*-\s+\[(?P<checked>[ xX])\]\s+"
    r"(?P<kind>🐛|🔀|👀)\s+"
    r"(?P<item>(?:[\w.-]+/[\w.-]+)?#\d+)\s+"
    r"\((?P<person>[^)]*)\)\s+"
    r"\*\*(?P<status>[^*]+)\*\*"
    r"(?P<tail>.*)$"
)
TITLE_RE = re.compile(r'\s+—\s+"(?P<title>.*)"\s*$')
ACTION_RE = re.compile(r"\s+→\s+`(?P<action>[^`]+)`")
ARTIFACT_RE = re.compile(r"\s+📄\s+`(?P<artifact>[^`]+)`")
DIFF_RE = re.compile(r"\s+Δ\s+\+(?P<additions>\d+)\s*/\s*-(?P<deletions>\d+)")

KIND_LABELS = {
    "🐛": "Issue",
    "🔀": "你的 PR",
    "👀": "Review PR",
}

FILTER_CONTROLS = """\
<div class="work-controls" aria-label="Work Board 篩選與排序">
  <label class="search-control"><span>搜尋</span><input id="board-search" type="search" placeholder="標題、作者、狀態…"></label>
  <label><span>類型</span><select id="board-kind"><option value="">全部類型</option><option value="🐛">Issue</option><option value="🔀">你的 PR</option><option value="👀">Review PR</option></select></label>
  <label><span>狀態</span><select id="board-status"><option value="">全部狀態</option></select></label>
  <label><span>排序</span><select id="board-sort"><option value="board">原本順序</option><option value="author">作者 A→Z</option><option value="title">標題 A→Z</option><option value="changes-desc">改動量：大→小</option><option value="changes-asc">改動量：小→大</option></select></label>
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
    reason: str
    title: str
    action: str | None
    artifact: str | None
    learned: bool
    stale: bool
    additions: int | None
    deletions: int | None


def parse_item(line: str) -> BoardItem | None:
    """Parse one canonical board line; unknown lines stay untouched by the hook."""
    match = ITEM_RE.fullmatch(line)
    if match is None:
        return None

    tail = match.group("tail")
    title_match = TITLE_RE.search(tail)
    title = title_match.group("title") if title_match else ""
    if title_match:
        tail = tail[: title_match.start()]

    action_match = ACTION_RE.search(tail)
    artifact_match = ARTIFACT_RE.search(tail)
    action = action_match.group("action") if action_match else None
    artifact = artifact_match.group("artifact") if artifact_match else None
    learned = "🧠" in tail
    stale = "💤" in tail
    diff_match = DIFF_RE.search(tail)
    additions = int(diff_match.group("additions")) if diff_match else None
    deletions = int(diff_match.group("deletions")) if diff_match else None

    tail = DIFF_RE.sub("", tail)
    tail = ACTION_RE.sub("", tail)
    tail = ARTIFACT_RE.sub("", tail)
    tail = tail.replace("🧠", "")
    tail = tail.replace("💤", "")
    reason = tail.strip().removeprefix("—").strip()

    return BoardItem(
        checked=match.group("checked").lower() == "x",
        kind=match.group("kind"),
        item=match.group("item"),
        person=match.group("person"),
        status=match.group("status"),
        reason=reason,
        title=title,
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


def render_table(items: list[BoardItem], default_repo: str | None) -> str:
    """Render a section as one semantic table with compact, layered cells."""
    rows: list[str] = []
    for order, item in enumerate(items):
        issue_url = _github_url(item, default_repo)
        item_label = html.escape(item.item)
        if issue_url:
            item_label = f'<a class="work-item-id" href="{html.escape(issue_url)}">{item_label}</a>'

        title = html.escape(item.title) if item.title else "<em>無標題</em>"
        learned = (
            '<span class="learned" title="已完成學習盤點">🧠</span>'
            if item.learned
            else ""
        )
        stale_badge = (
            '<span class="stale" title="逾期未更新">💤</span>' if item.stale else ""
        )
        work_cell = (
            f'<div class="work-item-title">{item.kind} {item_label} {learned}{stale_badge}</div>'
            f'<div class="work-title">{title}</div>'
            f'<div class="work-meta">{html.escape(KIND_LABELS[item.kind])}</div>'
        )
        author_cell = f'<span class="work-author">{html.escape(item.person)}</span>'

        if item.additions is not None and item.deletions is not None:
            changed = item.additions + item.deletions
            diff_cell = (
                f'<span class="diff-add">+{item.additions}</span> '
                f'<span class="diff-delete">−{item.deletions}</span>'
            )
        else:
            changed = -1
            diff_cell = '<span class="muted">—</span>'

        checkbox = " checked" if item.checked else ""
        done_cell = (
            '<input class="learn-checkbox" type="checkbox" disabled'
            f'{checkbox} aria-label="我處理過 {html.escape(item.item)}">'
        )
        status_class = _status_class(item.status)
        status_text = (
            f"⚠ 未知狀態 {html.escape(item.status)}"
            if status_class == "status-unknown"
            else html.escape(item.status)
        )
        status_cell = f'<span class="work-status {status_class}">{status_text}</span>'
        reason_cell = (
            html.escape(item.reason) if item.reason else '<span class="muted">—</span>'
        )

        next_parts: list[str] = []
        if item.action:
            next_parts.append(
                f'<code class="work-command">{html.escape(item.action)}</code>'
            )
        if item.artifact:
            artifact_url = _artifact_url(item.artifact)
            if artifact_url:
                next_parts.append(
                    f'<a class="artifact-link" href="{html.escape(artifact_url)}">'
                    f"📄 {html.escape(item.artifact)}</a>"
                )
            else:
                next_parts.append(f"<code>📄 {html.escape(item.artifact)}</code>")
        target = _command_target(item.item)
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
        next_cell = "".join(next_parts) + row_actions

        search_text = " ".join(
            value
            for value in (
                item.item,
                item.person,
                item.status,
                item.reason,
                item.title,
                item.action,
            )
            if value
        ).casefold()
        rows.append(
            f'<tr data-kind="{item.kind}" '
            f'data-author="{html.escape(item.person.casefold())}" '
            f'data-status="{html.escape(item.status)}" '
            f'data-title="{html.escape(item.title.casefold())}" '
            f'data-changes="{changed}" data-order="{order}" '
            f'data-search="{html.escape(search_text)}">'
            f'<td class="handled-cell">{done_cell}</td>'
            f'<td class="item-cell">{work_cell}</td>'
            f'<td class="author-cell">{author_cell}</td>'
            f'<td class="diff-cell">{diff_cell}</td>'
            f'<td class="status-cell">{status_cell}</td>'
            f'<td class="reason-cell">{reason_cell}</td>'
            f'<td class="next-cell">{next_cell}</td>'
            "</tr>"
        )

    return (
        '<div class="work-table-wrap">\n'
        '<table class="work-table">\n'
        '<thead><tr><th class="handled-cell">我處理過</th><th>項目</th>'
        "<th>作者</th><th>改動</th><th>狀態</th><th>現況</th>"
        "<th>下一步</th></tr></thead>\n"
        "<tbody>\n" + "\n".join(rows) + "\n</tbody>\n</table>\n</div>"
    )


def render_board(markdown: str) -> str:
    """Replace each board section's canonical items with one sortable table."""
    repo_match = BOARD_REPO_RE.search(markdown)
    default_repo = repo_match.group("repo") if repo_match else None
    lines = markdown.splitlines()
    output: list[str] = []
    pending: list[BoardItem] = []
    deferred: list[str] = []

    def flush() -> None:
        if pending:
            output.extend(["", render_table(pending, default_repo), ""])
            pending.clear()
            output.extend(deferred)
            deferred.clear()

    controls_added = False
    for line in lines:
        if line.startswith("## ") and not controls_added:
            output.extend(["", FILTER_CONTROLS, ""])
            controls_added = True
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
