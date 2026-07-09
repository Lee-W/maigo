#!/usr/bin/env python3
"""Render `.maigo/board.md` into a self-contained, read-only `.maigo/board.html`.

`/maigo:board`（skills/work-board）的閱讀層：把 board.md 的行文法（型別 emoji /
`#n` / 相對人 / 狀態詞 / 下一步命令 / checkbox / 🧠 標記）畫成一個球權三欄
kanban（🎯 你的球 / ⏳ 等別人 / ✅ Merged / closed）。`📥 無法分類` 若有內容會
另外附一段，不計入三欄主板（board-design.md §8 只定義三欄）。

跑：`python3 scripts/board_render.py [board.md 路徑] [輸出路徑]`
預設輸入 `.maigo/board.md`，輸出同目錄的 `board.html`（`<board 路徑>.with_suffix(".html")`）。

python3 stdlib-only：不引第三方套件、不發任何網路請求。輸出的 HTML 全部
inline CSS/JS，`file://` 離線開啟即可使用；深淺色跟隨
`prefers-color-scheme`，`<meta http-equiv="refresh" content="30">` 每 30 秒自動重載。

解析容錯：認不得的行（沒有 checkbox 前綴等）原樣包成一張卡片顯示，不 crash、
不丟資料。找不到輸入檔 → exit 1 + stderr 一行。
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

TITLE_RE = re.compile(r"^#\s*Work Board\s*—\s*(?P<repo>\S+)\s*$")
SECTION_HEADER_RE = re.compile(r"^##\s*(?P<emoji>\S+)\s+(?P<rest>.+)$")
_TRAILING_COUNT_RE = re.compile(r"[（(]\d+[）)]\s*$")

LINE_PREFIX_RE = re.compile(
    r"^-\s*\[(?P<check>[ xX])\]\s*"
    r"(?P<type_emoji>\S+)\s+"
    r"(?P<ref>\S+)\s+"
    r"\((?P<who>[^)]*)\)\s+"
    r"\*\*(?P<status>[^*]+)\*\*"
    r"(?P<learned>\s*🧠)?"
    r"\s*(?P<rest>.*)$"
)
COMMAND_RE = re.compile(r"→\s*`(?P<cmd>[^`]+)`")
TITLE_TAIL_RE = re.compile(r'"(?P<title>[^"]*)"\s*$')
REF_OWNER_REPO_RE = re.compile(r"^(?P<slug>[\w.-]+/[\w.-]+)#(?P<num>\d+)$")
REF_BARE_RE = re.compile(r"^#(?P<num>\d+)$")

# 三欄 kanban（board-design.md §8）。順序固定，跟 board.md 的 section 順序無關。
KANBAN_ORDER = ("🎯", "⏳", "✅")
KANBAN_TITLES = {"🎯": "你的球", "⏳": "等別人", "✅": "Merged / closed"}
KANBAN_CLASSES = {"🎯": "todo", "⏳": "waiting", "✅": "done"}


@dataclass
class BoardItem:
    """One board.md checklist line, parsed or raw fallback."""

    raw: str
    parsed: bool
    checked: bool = False
    type_emoji: str = ""
    ref: str = ""
    who: str = ""
    status: str = ""
    learned: bool = False
    reason: str = ""
    command: str = ""
    title: str = ""


@dataclass
class Section:
    """A `## <emoji> <name>` block and the items under it."""

    emoji: str
    name: str
    items: list[BoardItem] = field(default_factory=list)


def parse_line(line: str) -> BoardItem:
    """Parse one `- [ ] ...` board line. Falls back to an unparsed raw item."""
    m = LINE_PREFIX_RE.match(line)
    if not m:
        return BoardItem(raw=line, parsed=False)

    rest = m.group("rest")

    title_m = TITLE_TAIL_RE.search(rest)
    title = title_m.group("title") if title_m else ""
    if title_m:
        rest = rest[: title_m.start()]

    cmd_m = COMMAND_RE.search(rest)
    command = cmd_m.group("cmd") if cmd_m else ""
    if cmd_m:
        rest = rest[: cmd_m.start()] + rest[cmd_m.end() :]

    reason = re.sub(r"^\s*—\s*", "", rest)
    reason = re.sub(r"\s*—\s*$", "", reason).strip()

    return BoardItem(
        raw=line,
        parsed=True,
        checked=m.group("check").lower() == "x",
        type_emoji=m.group("type_emoji"),
        ref=m.group("ref"),
        who=m.group("who"),
        status=m.group("status").strip(),
        learned=bool(m.group("learned")),
        reason=reason,
        command=command,
        title=title,
    )


def parse_board(text: str) -> tuple[str, list[Section]]:
    """Parse a full board.md. Returns (repo slug from header, sections in file order)."""
    repo = ""
    sections: list[Section] = []
    current: Section | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()

        title_m = TITLE_RE.match(line)
        if title_m:
            repo = title_m.group("repo")
            continue

        section_m = SECTION_HEADER_RE.match(line)
        if section_m:
            name = _TRAILING_COUNT_RE.sub("", section_m.group("rest")).strip()
            current = Section(emoji=section_m.group("emoji"), name=name)
            sections.append(current)
            continue

        stripped = line.strip()
        if current is None or not stripped.startswith("-"):
            continue
        current.items.append(parse_line(stripped))
    return repo, sections


def issue_url(repo: str, ref: str) -> str:
    """Best-effort GitHub URL for *ref* (`#n` against *repo*, or `owner/repo#n`).

    GitHub's `/issues/<n>` URL redirects to `/pull/<n>` when `n` is actually a
    PR, so a single `/issues/<n>` link works for both 🐛/🔀/👀 rows.
    """
    m = REF_OWNER_REPO_RE.match(ref)
    if m:
        return f"https://github.com/{m.group('slug')}/issues/{m.group('num')}"
    m = REF_BARE_RE.match(ref)
    if m and repo:
        return f"https://github.com/{repo}/issues/{m.group('num')}"
    return ""


def render_card(item: BoardItem, repo: str) -> str:
    """Render one board item as an HTML card. Unparsed items get a bare fallback card."""
    if not item.parsed:
        return f'<div class="card unparsed"><code>{html.escape(item.raw)}</code></div>'

    check_class = "checked" if item.checked else "unchecked"
    check_glyph = "☑" if item.checked else "☐"
    learned_badge = '<span class="badge learned">🧠</span>' if item.learned else ""

    url = issue_url(repo, item.ref)
    ref_html = (
        f'<a class="ref-link" href="{html.escape(url)}" target="_blank" '
        f'rel="noopener">{html.escape(item.ref)}</a>'
        if url
        else f'<span class="ref-link">{html.escape(item.ref)}</span>'
    )

    cmd_html = ""
    if item.command:
        escaped_cmd = html.escape(item.command)
        cmd_html = (
            '<div class="cmd-row">'
            f'<code class="cmd">{escaped_cmd}</code>'
            f'<button class="copy-btn" data-cmd="{escaped_cmd}" '
            'onclick="copyCmd(this)">複製</button>'
            "</div>"
        )

    title_html = (
        f'<div class="title">&ldquo;{html.escape(item.title)}&rdquo;</div>'
        if item.title
        else ""
    )

    return (
        f'<div class="card {check_class}">'
        '<div class="card-head">'
        f'<span class="check">{check_glyph}</span>'
        f'<span class="type-emoji">{html.escape(item.type_emoji)}</span>'
        f"{ref_html}"
        f'<span class="who">({html.escape(item.who)})</span>'
        f"{learned_badge}"
        "</div>"
        f'<div class="status">{html.escape(item.status)}</div>'
        f'<div class="reason">{html.escape(item.reason)}</div>'
        f"{cmd_html}"
        f"{title_html}"
        "</div>"
    )


def render_column(emoji: str, items: list[BoardItem], repo: str) -> str:
    cards = (
        "\n".join(render_card(item, repo) for item in items)
        or '<p class="empty">（空）</p>'
    )
    title = KANBAN_TITLES.get(emoji, emoji)
    css_class = KANBAN_CLASSES.get(emoji, "extra")
    return (
        f'<section class="column column-{css_class}">'
        f"<h2>{emoji} {html.escape(title)} ({len(items)})</h2>"
        f'<div class="cards">{cards}</div>'
        "</section>"
    )


def render_extra_section(section: Section, repo: str) -> str:
    cards = "\n".join(render_card(item, repo) for item in section.items)
    return (
        '<section class="column column-extra">'
        f"<h2>{section.emoji} {html.escape(section.name)} ({len(section.items)})</h2>"
        f'<div class="cards">{cards}</div>'
        "</section>"
    )


def render_html(repo: str, sections: list[Section]) -> str:
    """Assemble the full self-contained HTML page."""
    kanban: dict[str, list[BoardItem]] = {emoji: [] for emoji in KANBAN_ORDER}
    extra: list[Section] = []
    for section in sections:
        if section.emoji in kanban:
            kanban[section.emoji].extend(section.items)
        else:
            extra.append(section)

    columns_html = "\n".join(
        render_column(emoji, kanban[emoji], repo) for emoji in KANBAN_ORDER
    )
    extra_html = "\n".join(
        render_extra_section(section, repo) for section in extra if section.items
    )

    repo_label = html.escape(repo) if repo else "(unknown repo)"

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="30">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Work Board — {repo_label}</title>
<style>
:root {{
  --bg: #ffffff;
  --fg: #1b1b1f;
  --card-bg: #f5f5f7;
  --card-border: #d8d8dc;
  --muted: #6b6b70;
  --todo: #c62828;
  --waiting: #6b6b70;
  --done: #2e7d32;
  --accent: #3455db;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #1b1b1f;
    --fg: #e8e8ec;
    --card-bg: #2a2a30;
    --card-border: #3c3c44;
    --muted: #a0a0a8;
    --todo: #ff6b6b;
    --waiting: #a0a0a8;
    --done: #6fd17f;
    --accent: #82a0ff;
  }}
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  padding: 1.5rem;
  background: var(--bg);
  color: var(--fg);
  font-family: -apple-system, "Segoe UI", "Noto Sans TC", sans-serif;
}}
h1 {{ font-size: 1.3rem; margin: 0 0 1rem; }}
.board {{
  display: flex;
  gap: 1rem;
  align-items: flex-start;
  flex-wrap: wrap;
}}
.column {{
  flex: 1 1 260px;
  min-width: 260px;
  background: transparent;
}}
.column h2 {{ font-size: 1rem; margin: 0 0 .5rem; }}
.cards {{ display: flex; flex-direction: column; gap: .6rem; }}
.card {{
  border: 1px solid var(--card-border);
  background: var(--card-bg);
  border-radius: .5rem;
  padding: .6rem .7rem;
  font-size: .85rem;
}}
.card.checked {{ opacity: .7; }}
.card.unparsed {{ font-family: monospace; opacity: .8; }}
.card-head {{ display: flex; align-items: center; gap: .35rem; flex-wrap: wrap; }}
.check {{ font-size: 1rem; }}
.ref-link {{ color: var(--accent); text-decoration: none; font-weight: 600; }}
.ref-link:hover {{ text-decoration: underline; }}
.who {{ color: var(--muted); }}
.badge.learned {{ margin-left: auto; }}
.column-todo .status {{ color: var(--todo); font-weight: 600; }}
.column-waiting .status {{ color: var(--waiting); font-weight: 600; }}
.column-done .status {{ color: var(--done); font-weight: 600; }}
.status {{ margin-top: .2rem; font-weight: 600; }}
.reason {{ color: var(--muted); margin-top: .15rem; }}
.title {{ margin-top: .3rem; font-style: italic; color: var(--muted); }}
.cmd-row {{ display: flex; align-items: center; gap: .4rem; margin-top: .35rem; }}
.cmd {{
  flex: 1;
  background: var(--bg);
  border: 1px solid var(--card-border);
  border-radius: .3rem;
  padding: .2rem .4rem;
  overflow-x: auto;
  white-space: nowrap;
}}
.copy-btn {{
  border: 1px solid var(--accent);
  background: transparent;
  color: var(--accent);
  border-radius: .3rem;
  padding: .15rem .5rem;
  cursor: pointer;
  font-size: .8rem;
}}
.empty {{ color: var(--muted); font-style: italic; }}
</style>
</head>
<body>
<h1>Work Board — {repo_label}</h1>
<div class="board">
{columns_html}
{extra_html}
</div>
<script>
function copyCmd(btn) {{
  var cmd = btn.getAttribute("data-cmd");
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    navigator.clipboard.writeText(cmd).then(function () {{
      btn.textContent = "已複製";
      setTimeout(function () {{ btn.textContent = "複製"; }}, 1500);
    }}, function () {{ fallbackSelect(btn); }});
  }} else {{
    fallbackSelect(btn);
  }}
}}
function fallbackSelect(btn) {{
  var code = btn.previousElementSibling;
  var range = document.createRange();
  range.selectNodeContents(code);
  var sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  btn.textContent = "已全選，請 Cmd/Ctrl+C";
  setTimeout(function () {{ btn.textContent = "複製"; }}, 2500);
}}
</script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board", nargs="?", default=".maigo/board.md")
    parser.add_argument("output", nargs="?", default=None)
    args = parser.parse_args(argv)

    board_path = Path(args.board)
    output_path = Path(args.output) if args.output else board_path.with_suffix(".html")

    if not board_path.is_file():
        sys.stderr.write(f"board_render: `{board_path}` 不存在\n")
        return 1

    text = board_path.read_text(encoding="utf-8")
    repo, sections = parse_board(text)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html(repo, sections), encoding="utf-8")
    print(f"wrote {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
