#!/usr/bin/env python3
"""
`board_sync.py refresh`：零 token 的 Work Board 完整刷新（取代 `/maigo:board` 手動流程的
抓料、分類、渲染與寫回）。stdlib-only，由 `board_sync.main()` 以 function-level import 轉交。

- 不帶 `--apply` ＝預覽：整套流程照算（含 gh 抓料），但一個檔都不寫、不建 `_internal/`、
  不 append ledger、不寫 snapshot、**不 ack**（ack 只模擬）。輸出 board.md 的 unified diff。
- `--apply`：取得該 repo 狀態目錄 `_internal/board/` 下的刷新鎖後，依序 CAS 預檢 #1 → ack → 渲染 → CAS 預檢 #2 →
  備份 → 寫細節檔 → 寫 board.md →
  刪老化細節檔 → append ledger → 寫 snapshot。CAS 不一致（別人動過檔）→ exit 2，除了 ack 已寫的
  review.md 標記外不寫任何檔；寫細節檔／board 失敗 → 從備份還原、exit 3（`write_failed`）；
  board 已寫成功後 ledger／snapshot 失敗 → exit 3 但不還原（`post_write_failed`，重跑安全）。步驟與失敗語義見 `skills/work-board/SKILL.md` §3(b)。

渲染器（`render_line` / `render_board` / `render_detail_facts` / `split_detail`）是
`skills/work-board/references/format-spec.md` §1 / §1a 文法的程式鏡像，由 `tests/test_board_refresh.py`
的 round-trip 守著。外部指令一律走 `board_sync.run`（以 module attribute 存取，
測試只要 monkeypatch 那一個 seam）。

cwd 或 `--maigo-root` 在集中狀態目錄 `<state>/<owner>/<repo>`（或其子目錄）時，以系統暫存目錄合成
root（內含指向該目錄的 `.maigo` symlink），結束即清；不在狀態目錄或 checkout 留任何東西。

exit code：0 成功（含無變動）／預覽；1 前置條件拒絕；2 CAS 衝突或另一輪刷新持鎖；3 寫入階段失敗。
"""

from __future__ import annotations

import argparse
import contextlib
import difflib
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

if __package__:
    from . import artifact_path, board_state, maigo_state, review_report
    from . import board_sync as sync
else:  # run as a script: scripts/ is on sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import artifact_path  # type: ignore[no-redef]  # noqa: E402
    import board_state  # type: ignore[no-redef]  # noqa: E402
    import maigo_state  # type: ignore[no-redef]  # noqa: E402
    import board_sync as sync  # type: ignore[no-redef]  # noqa: E402
    import review_report  # type: ignore[no-redef]  # noqa: E402

SECTIONS = ("🎯", "👀", "⏳", "✅")
SECTION_TITLES = {
    "🎯": "## 🎯 我的下一件",
    "👀": "## 👀 待我 review",
    "⏳": "## ⏳ 等別人",
    "✅": "## ✅ 最近結案",
}
ACTION_SECTIONS = ("🎯", "👀")  # numbered, rank-sorted; the other two are reference
# Display columns budget, measured as if the detail path still sat before ` — ` (the path now
# closes the line, but the threshold stays where it was; best effort).
LINE_BUDGET = 80
BADGE_ORDER = "🧠🔖💤"
# ✅ retention: how long a closed row stays, by whose it is; learning-pending rows are
# exempt until LEARN_PENDING_LIMIT; the section keeps at most DONE_CAP of the rest.
AGE_LIMIT_REVIEW = timedelta(days=3)  # 👀: someone else's PR
AGE_LIMIT_OWN = timedelta(days=7)  # 🔀 / 🐛
LEARN_PENDING_LIMIT = timedelta(days=30)
LEARN_PENDING_WARN = timedelta(days=7)  # list rows expiring within this much
DONE_CAP = 10
BACKUP_KEEP = 10
WEIGHTS_FILENAME = "board-weights.txt"
WEIGHT_PREFIXES = ("author", "title")
LOAD_FILENAME = "board-load.txt"
TAKEOVER_FILENAME = "board-takeover.txt"
# `board-load.txt` keys and the placeholders each one may use
LOAD_KEYS = {"pr": {"number"}, "branch": {"branch", "number"}}
_PLACEHOLDER_RE = re.compile(r"\{([^{}]*)\}")
_SAFE_BRANCH_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._/-]*")  # use fullmatch
_SAME_REPO_DETAIL_RE = re.compile(r"^i/\d+\.md$")
NOTE_MAX = 80
JUDGMENT_HEADING = "## 判斷"
_FENCE_LINE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
NEW_PRESERVED = "## 判斷\n\n## 筆記\n\n<!-- 手寫區 -->\n"
UNREACHABLE = "抓不到"
ERROR_NOTE_PREFIX = "（gh 失敗："
_DETAIL_H1_RE = re.compile(r"^# \S+ (?P<status>.+?) — ")
PR_FIELDS = (
    "title,state,isDraft,mergedAt,closedAt,mergeable,reviewDecision,createdAt,"
    "updatedAt,headRefOid,headRefName,commits,reviews,comments,author,"
    "statusCheckRollup,additions,deletions,body,closingIssuesReferences"
)
ISSUE_FIELDS = (
    "title,state,stateReason,closedAt,assignees,author,comments,createdAt,"
    "updatedAt,labels,closedByPullRequestsReferences"
)
_URL_RE = re.compile(
    r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?P<kind>pull|issues)/(?P<number>\d+)/?$"
)
_SHORT_REF_RE = re.compile(r"^(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)#(?P<number>\d+)$")
CAS_MESSAGE = "{what}在刷新期間被改過，未寫任何檔；直接重跑即可"
CAS2_MESSAGE = (
    "{what}在刷新期間被改過；除了 review.md 的 ack 標記外未寫任何檔，直接重跑即可"
)


class RefreshError(Exception):
    """A refresh stop with a defined exit code (1 reject / 2 CAS / 3 write failure)."""

    def __init__(
        self, code: int, message: str, *, reason: str | None = None, **extra: object
    ) -> None:
        super().__init__(message)
        self.code = code
        self.reason = reason
        self.message = message
        self.extra = extra


@dataclass(frozen=True)
class WeightRule:
    """One `board-weights.txt` rule: exact author login, or a title regex."""

    kind: str  # "author" | "title"
    author: str = ""  # lowercased login (kind == "author")
    pattern: re.Pattern | None = None  # case-insensitive (kind == "title")


def parse_weights(text: str, source: str) -> list[WeightRule]:
    """Parse one weights file; any bad line is a RefreshError(1) naming file:line."""
    rules: list[WeightRule] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        prefix, _, value = line.partition(":")
        value = value.strip()
        if (
            prefix not in WEIGHT_PREFIXES
            or not value
            or (prefix == "author" and any(c.isspace() for c in value))
        ):
            raise RefreshError(
                1,
                f"{source}:{number}: 無法解析加權規則 {line!r}"
                "（只接受 `author:<login>` 或 `title:<regex>`）",
            )
        if prefix == "author":
            rules.append(WeightRule("author", author=value.lower()))
            continue
        try:
            pattern = re.compile(value, re.IGNORECASE)
        except re.error as error:
            raise RefreshError(
                1, f"{source}:{number}: regex 編譯失敗 {value!r}（{error}）"
            ) from error
        rules.append(WeightRule("title", pattern=pattern))
    return rules


def load_weights(root: Path, explicit: Path | None = None) -> list[WeightRule]:
    """`--weights` reads only that file (must exist); else repo layer, then user layer.

    Both layers absent means no weighting. Repo-layer rules come first, so they win.
    """
    if explicit is not None:
        sources = [explicit.expanduser()]
    else:
        sources = [
            root / ".maigo" / WEIGHTS_FILENAME,
            Path("~/.config/maigo").expanduser() / WEIGHTS_FILENAME,
        ]
    rules: list[WeightRule] = []
    for path in sources:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            if explicit is not None:
                raise RefreshError(1, f"找不到加權檔 {path}") from None
            continue
        except (OSError, UnicodeDecodeError) as error:
            raise RefreshError(1, f"{path}: 無法讀取加權檔（{error}）") from error
        rules.extend(parse_weights(text, str(path)))
    return rules


def parse_takeover(text: str, source: str, repo: str) -> dict[tuple, str]:
    """Parse one `board-takeover.txt`: one PR per line, `ref` then optional `# note`.

    Returns `sync.ref_key` -> display `owner/repo#N`. A line starting with `#` is a
    comment unless what follows `#` is all digits (`#76991` is a PR ref).
    """
    found: dict[tuple, str] = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        token, *tail = line.split(None, 1)
        rest = tail[0].strip() if tail else ""
        if token.startswith("#") and not token[1:].isdigit():
            continue
        display: str | None = None
        key: tuple | None = None
        digits = token[1:] if token.startswith("#") else token
        if digits.isdigit():
            if not digits.isdecimal():  # `²`: isdigit() but int() raises
                raise RefreshError(
                    1, f"{source}:{number}: 無法解析接棒清單 {raw.strip()!r}"
                )
            display = f"{repo}#{int(digits)}"
            key = sync.ref_key(f"https://github.com/{repo}/pull/{int(digits)}")
        elif (short := _SHORT_REF_RE.match(token)) is not None:
            display = f"{short['owner']}/{short['repo']}#{int(short['number'])}"
            key = sync.ref_key(
                f"https://github.com/{short['owner']}/{short['repo']}/pull/{short['number']}"
            )
        elif (url := sync._URL_RE.match(token)) is not None and url["kind"] == "pull":
            display = f"{url['owner']}/{url['repo']}#{int(url['number'])}"
            key = sync.ref_key(token)
        if key is None or display is None or (rest and not rest.startswith("#")):
            raise RefreshError(
                1,
                f"{source}:{number}: 無法解析接棒清單 {raw.strip()!r}"
                "（只接受 76991、#76991、owner/repo#76991 或 PR URL）",
            )
        found.setdefault(key, display)
    return found


def load_takeover(root: Path, repo: str) -> dict[tuple, str]:
    """Repo-layer `.maigo/board-takeover.txt` only; absent file means no take-overs."""
    path = root / ".maigo" / TAKEOVER_FILENAME
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError) as error:
        raise RefreshError(1, f"{path}: 無法讀取接棒清單（{error}）") from error
    return parse_takeover(text, str(path), repo)


def parse_load_templates(text: str, source: str) -> dict[str, str]:
    """Parse one `board-load.txt`: `pr:<template>` / `branch:<template>` per line.

    Unknown key, unknown placeholder or empty template is a RefreshError(1) naming
    file:line. Templates are only ever displayed, never executed by maigo.
    """
    templates: dict[str, str] = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        if key not in LOAD_KEYS or not value:
            raise RefreshError(
                1,
                f"{source}:{number}: 無法解析載入樣板 {line!r}"
                "（只接受 `pr:<樣板>` 或 `branch:<樣板>`，樣板不可為空）",
            )
        unknown = sorted(set(_PLACEHOLDER_RE.findall(value)) - LOAD_KEYS[key])
        if unknown:
            raise RefreshError(
                1,
                f"{source}:{number}: `{key}:` 樣板含未知佔位字 {unknown}"
                f"（可用：{sorted(LOAD_KEYS[key])}）",
            )
        templates[key] = value
    return templates


def load_load_templates(root: Path, user_dir: Path | None = None) -> dict[str, str]:
    """Merge the user layer under the repo layer, key by key (repo wins).

    Neither file present means no templates: maigo ships no default load command.
    """
    user_dir = (user_dir or Path("~/.config/maigo")).expanduser()
    merged: dict[str, str] = {}
    for path in (user_dir / LOAD_FILENAME, root / ".maigo" / LOAD_FILENAME):
        try:
            text = path.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            continue
        except (OSError, UnicodeDecodeError) as error:
            raise RefreshError(1, f"{path}: 無法讀取載入樣板檔（{error}）") from error
        merged.update(parse_load_templates(text, str(path)))
    return merged


def load_command_for(
    row: dict, templates: dict[str, str], warnings: list[str]
) -> str | None:
    """The `載入` command for one row, or None (nothing configured / not applicable).

    👀 uses `pr`; own 🔀 prefers `branch` (falls back to `pr`); issues, cross-repo rows
    and closed rows get none. An unsafe branch name omits the line and warns.
    """
    if not templates or row["section"] == "✅" or row["type"] == "🐛":
        return None
    if not _SAME_REPO_DETAIL_RE.match(row["detail"] or ""):
        return None
    match = _URL_RE.match(row["url"])
    if not match:
        return None
    number = match["number"]
    if row["type"] == "🔀" and "branch" in templates:
        branch = (row.get("gh_meta") or {}).get("headRefName")
        if branch:
            if not _SAFE_BRANCH_RE.fullmatch(branch) or ".." in branch:
                warnings.append(f"#{number} 的 branch 名含不安全字元，略過載入指令")
                return None
            return (
                templates["branch"]
                .replace("{branch}", branch)
                .replace("{number}", number)
            )
    if "pr" in templates:
        return templates["pr"].replace("{number}", number)
    return None


# --- pure rendering (no I/O) ---------------------------------------------------


def _merge_author_pending(note: str | None, has_author: bool) -> str | None:
    """
    Fold `作者待補` into the one allowed `（旁註）`; drop it once an author is known.

    The body grammar admits a single note group, so the marker joins the existing
    note with `；` instead of sitting next to it. Idempotent.
    """
    parts = [part for part in sync.note_segments(note) if part != sync.AUTHOR_PENDING]
    if not has_author:
        parts.append(sync.AUTHOR_PENDING)
    return f"（{'；'.join(parts)}）" if parts else None


def strip_duplicate_verdict_note(note: str | None, verdict: str | None) -> str | None:
    """
    Drop the segments of a `（a；b）` note that merely repeat the report verdict.

    A segment goes only when, trimmed, it equals `本地 <verdict>` exactly (`verdict` is the
    report's current one). Everything else — `本地 NEEDS_CHANGES，must-fix 5`, a different
    verdict word, ASCII parens — stays byte for byte; remaining segments rejoin with `；`
    and an empty note disappears.
    """
    if not note or not verdict:
        return note
    segments = sync.note_segments(note)
    kept = [seg for seg in segments if seg.strip() != f"本地 {verdict}"]
    if len(kept) == len(segments):
        return note
    kept = [seg for seg in kept if seg.strip()]  # 退場後留下的空段不留空括號
    return f"（{'；'.join(kept)}）" if kept else None


def author_token(author: str | None) -> str:
    """`@login` when known, else the pending marker; never a bare `@`."""
    return f"@{author}" if author else f"（{sync.AUTHOR_PENDING}）"


def render_line(
    *,
    number: int | None,
    checked: bool,
    type: str,  # noqa: A002 - mirrors the grammar's field name
    status: str,
    note: str | None,
    author: str | None,
    badges: list[str],
    detail: str,
    title: str,
    action: str | None = None,
    size: str | None = None,
    ended: str | None = None,
    result: str | None = None,
) -> str:
    """One board line per work-board references/format-spec.md §1「行文法」: `… — [<title> ]<detail>`.

    The detail path is the last token of the line (one ASCII space before it, nothing after
    it), so `$` then `gf` lands on it. `action` / `size` (🎯/👀 rows) and `ended` (✅ rows)
    sit between the badges and ` — `. The head plus ` <detail>` is kept within `LINE_BUDGET`
    display columns by dropping `→action` first; note, author, size, detail and title are
    never cut, so a line with a very long note can still run over (best effort).
    `result` (review verdict / 已核准, in the `→action` slot) takes priority over size: a row
    with a result drops `+A/-D` first when over budget and never cuts the result (nor its
    `上次 ` prefix, which would turn a stale verdict into a current-looking one).
    """
    prefix = f"{number}. " if number is not None else "- "
    note = _merge_author_pending(note, bool(author))
    line = f"{prefix}[{'x' if checked else ' '}] {type} {status}{note or ''}"
    if author:
        line += f" @{author}"
    shown = "".join(b for b in BADGE_ORDER if b in badges)
    if shown:
        line += f" {shown}"

    def head(act: str | None, shown_size: str | None = size) -> str:
        extras = [f"→{act}" if act else None, result, shown_size, ended]
        return line + "".join(f" {extra}" for extra in extras if extra)

    def measured(act: str | None, shown_size: str | None = size) -> int:
        return board_state.display_width(f"{head(act, shown_size)} {detail}")

    lead = head(action)
    if result:
        if measured(action) > LINE_BUDGET:
            lead = head(action, None)
    elif action and measured(action) > LINE_BUDGET:
        lead = head(None)
    clean_title = " ".join(title.split())
    tail = f"{clean_title} {detail}" if clean_title else detail
    return f"{lead} — {tail}".rstrip()


def render_row(row: dict, number: int | None, section: str) -> str:
    """`render_line` for one row dict (shared by the board body and the summary).

    The section decides which derived fields show: `→action` and size only in 🎯/👀,
    the closing date only in ✅, none in ⏳.
    """
    actionable = section in ACTION_SECTIONS
    return render_line(
        number=number,
        checked=row["checked"],
        type=row["type"],
        status=row["status"],
        note=row.get("note"),
        author=row.get("author"),
        badges=row["badges"],
        detail=row["detail"],
        title=row["title"],
        action=row.get("action") if actionable else None,
        result=row.get("result") if actionable else None,
        size=row.get("size") if actionable else None,
        ended=row.get("ended") if section == "✅" else None,
    )


def count_learn_pending(rows: list[dict]) -> int:
    """Rows that are (`[x]` or `🔖`) and have no `🧠` (work-board references/format-spec.md §1, learning-gate.md §5)."""
    return sum(
        1
        for row in rows
        if (row["checked"] or "🔖" in row["badges"]) and "🧠" not in row["badges"]
    )


def render_board(
    *,
    repo: str,
    refreshed_at_local: str,
    rows_by_section: dict[str, list[dict]],
    learn_pending_count: int,
) -> str:
    """Whole board.md per work-board references/format-spec.md §1「Sections」; 🎯 and 👀 are each numbered from 1."""
    counts = {s: len(rows_by_section.get(s, [])) for s in SECTIONS}
    header = (
        f"> 最後刷新：{refreshed_at_local} ｜ 🎯 {counts['🎯']} ｜ 👀 {counts['👀']} ｜ "
        f"⏳ {counts['⏳']} ｜ ✅ {counts['✅']}"
    )
    if learn_pending_count > 0:
        header += f" ｜ 🧠 待學習盤點 {learn_pending_count}"
    out = [f"# Work Board — {repo}", "", header, ""]
    blocks: list[list[str]] = []
    for section in SECTIONS:
        rows = rows_by_section.get(section, [])
        block = [f"{SECTION_TITLES[section]}（{len(rows)}）"]
        if rows:
            block.append("")
            for index, row in enumerate(rows, start=1):
                block.append(
                    render_row(
                        row, index if section in ACTION_SECTIONS else None, section
                    )
                )
        blocks.append(block)
    for index, block in enumerate(blocks):
        if index:
            out.append("")
        out.extend(block)
    return "\n".join(out) + "\n"


def _epoch(value: str | None) -> float:
    if not value:
        return float("-inf")
    try:
        return board_state._parse_ts(value).timestamp()
    except ValueError:
        return float("-inf")


def compute_boost(row: dict, rules: list[WeightRule]) -> int:
    """Index of the first matching rule; no match sorts after every rule."""
    author = (row.get("author") or "").lower()
    title = row.get("title") or ""
    for index, rule in enumerate(rules):
        if rule.kind == "author":
            if author and author == rule.author:
                return index
        elif rule.pattern is not None and rule.pattern.search(title):
            return index
    return len(rules)


def sort_rows(
    section: str, rows: list[dict], rules: list[WeightRule] | None = None
) -> list[dict]:
    """🎯/👀: rank asc, boost asc, updated_at asc. ⏳/✅: own rows (🔀/🐛) before 👀 rows,
    each group updated_at desc (no boost).

    Missing time = oldest. Boost only reorders within one rank; it never moves a row
    across ranks or sections.
    """

    def tiebreak(row: dict) -> tuple:
        return row.get("key") or ("", "", 0)

    if section in ACTION_SECTIONS:
        active = rules or []
        return sorted(
            rows,
            key=lambda r: (
                r["rank"],
                compute_boost(r, active),
                _epoch(r.get("updated_at")),
                tiebreak(r),
            ),
        )
    return sorted(
        rows,
        key=lambda r: (
            r.get("type") == "👀",
            -_epoch(r.get("updated_at")),
            tiebreak(r),
        ),
    )


def split_detail(text: str) -> tuple[str, str]:
    """Split at the first line that is exactly `## 判斷`; `preserved` is that line to EOF."""
    offset = 0
    for line in text.split("\n"):
        if line.rstrip("\r") == JUDGMENT_HEADING:
            facts = text[:offset]
            if any(ln.startswith("## ") for ln in facts.split("\n")):
                # generated facts never contain a `## ` heading: hand-written
                # content sits above `## 判斷` and would be overwritten
                raise ValueError(
                    f"`{JUDGMENT_HEADING}` 之前有 `## ` 段落（手寫內容會被覆蓋）；請把它移到 `## 筆記` 之後"
                )
            return facts, text[offset:]
        offset += len(line) + 1
    raise ValueError(f"細節檔缺少 `{JUDGMENT_HEADING}` 行")


def collapse_blank_runs(text: str) -> str:
    """Squeeze runs of blank lines outside code fences to one plain blank line.

    A formatter (MD012, MD009) rewrites consecutive blank lines and trailing whitespace,
    so a preserved area written by an older template would be re-edited on every save.
    Outside code fences a whitespace-only line becomes an empty line (a CRLF file keeps
    its `\\r`) and only the first of each run is kept; a run at the end of the text is
    dropped, leaving the single final newline. Fenced code and every other byte stay put.
    A run followed by a line indented 4+ spaces or a tab is left untouched (it may be an
    indented code block, which a formatter does not rewrite). A fence opens on any
    indentation and closes only on a same-character fence at least as long with nothing
    but whitespace after it, so an unclosed or odd fence errs towards
    leaving blank lines alone.
    """
    ends_with_newline = text.endswith("\n")
    lines = text.split("\n")
    if ends_with_newline:
        lines.pop()
    out: list[str] = []
    fence: str | None = None
    pending_blank = False
    i = 0
    while i < len(lines):
        line = lines[i]
        marker = _FENCE_LINE.match(line)
        if marker:
            if fence is None:
                fence = marker[1]
            elif (
                marker[1][0] == fence[0]
                and len(marker[1]) >= len(fence)
                and not marker[2].strip()
            ):
                fence = None
        if fence is None and not marker and not line.strip():
            j = i
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and lines[j].startswith(("    ", "\t")):
                out.extend(
                    lines[i:j]
                )  # may be an indented code block: leave the run alone
                pending_blank = False
            else:
                out.append("\r" if line.endswith("\r") else "")
                pending_blank = True
            i = j
            continue
        pending_blank = False
        out.append(line)
        i += 1
    if ends_with_newline:
        if pending_blank and len(out) > 1:
            out.pop()
        out.append("")
    return "\n".join(out)


# --- own-PR why / what (PR description and local run summary) -------------------------
#
# Every source is free-form multi-line markdown, but the fact section may not hold a
# line starting with `## ` and must stay a formatter fixed point. So source text is
# always flattened to one line and only ever placed inside `- <field>：` list items
# (or their two-space sub-items): no emitted line can start with `## `.

BODY_FIELD_MAX = 200
CLOSING_ISSUES_MAX = 5
_WHY_HEADINGS = frozenset({"why", "為什麼", "動機", "motivation", "背景"})
_WHAT_HEADINGS = frozenset({"what", "做了什麼", "changes", "summary", "變更"})
_HEADING_LINE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_HTML_TAG_RE = re.compile(r"</?(?![A-Za-z][A-Za-z0-9+.-]*:)[A-Za-z][^>]*>")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_LIST_MARKER_RE = re.compile(r"^(?:[-*+]|\d+[.)])\s+")


def _clean_body_lines(text: str) -> list[str]:
    """Drop fenced code, HTML comments, table rows, image lines, whole-line HTML and
    inline HTML tags from `text`; returns the remaining lines (headings kept)."""
    kept: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        marker = _FENCE_LINE.match(line)
        if marker:
            if fence is None:
                fence = marker[1]
            elif (
                marker[1][0] == fence[0]
                and len(marker[1]) >= len(fence)
                and not marker[2].strip()
            ):
                fence = None
            continue
        if fence is None:
            kept.append(line)
    decommented = _HTML_COMMENT_RE.sub("", "\n".join(kept))
    out: list[str] = []
    for line in decommented.splitlines():
        stripped = line.strip()
        if stripped.startswith(("|", "![", "<")):
            continue
        out.append(_HTML_TAG_RE.sub("", line))
    return out


def _encodable(text: str) -> str:
    """`text` with characters UTF-8 cannot encode (lone surrogates from a JSON `\\ud800`
    escape) replaced by `?`, so writing the detail file cannot raise."""
    return text.encode("utf-8", "replace").decode("utf-8")


def _one_line(text: str) -> str:
    """Collapse every whitespace run (newlines, `\\r`, tabs included) to one space; the
    single choke point every PR body / summary field passes through."""
    return _encodable(" ".join(text.split()))


def _clip(text: str | None) -> str | None:
    """One-line `text` capped at `BODY_FIELD_MAX` characters; empty becomes `None`."""
    if text is None:
        return None
    flat = _one_line(text)
    if not flat:
        return None
    if len(flat) > BODY_FIELD_MAX:
        return flat[: BODY_FIELD_MAX - 1] + "…"
    return flat


def _join_fragments(lines: Sequence[str]) -> str | None:
    """List items each start a fragment; other lines continue the current one;
    fragments are joined with `；`."""
    fragments: list[list[str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        marker = _LIST_MARKER_RE.match(stripped)
        if marker:
            fragments.append([stripped[marker.end() :]])
        elif fragments:
            fragments[-1].append(stripped)
        else:
            fragments.append([stripped])
    flat = [_one_line("\n".join(f)) for f in fragments]
    joined = "；".join(f for f in flat if f)
    return joined or None


def _section_text(lines: Sequence[str], headings: frozenset[str]) -> str | None:
    """Body of the first heading whose lowercased title (trailing colon dropped) is in
    `headings`, up to the next heading of the same or a higher level; sub-heading lines
    are dropped, their content kept. `None` when absent or empty."""
    start: int | None = None
    level = 0
    for index, line in enumerate(lines):
        match = _HEADING_LINE.match(line.strip())
        if match and match[2].rstrip(":：").strip().lower() in headings:
            start, level = index + 1, len(match[1])
            break
    if start is None:
        return None
    body: list[str] = []
    for line in lines[start:]:
        match = _HEADING_LINE.match(line.strip())
        if match:
            if len(match[1]) <= level:
                break
            continue
        body.append(line)
    return _join_fragments(body)


def extract_why_what(
    body: str | None,
) -> tuple[str | None, str | None, str | None]:
    """`(why, what, summary)` from a PR description; `summary` (the first non-heading
    paragraph) is only set when neither a Why nor a What section exists."""
    if not body or not body.strip():
        return None, None, None
    lines = _clean_body_lines(body)
    why = _clip(_section_text(lines, _WHY_HEADINGS))
    what = _clip(_section_text(lines, _WHAT_HEADINGS))
    if why or what:
        return why, what, None
    paragraph: list[str] = []
    for line in lines:
        if _HEADING_LINE.match(line.strip()):
            continue
        if line.strip():
            paragraph.append(line)
        elif paragraph:
            break
    return None, None, _clip(_join_fragments(paragraph))


def format_closing_issues(refs: Sequence[dict] | None, url: str) -> str | None:
    """`#12` for an issue in the PR's repo, `owner/repo#7` for another; de-duplicated in
    order, at most `CLOSING_ISSUES_MAX` shown. `None` when there is nothing to show."""
    if not isinstance(refs, list):
        return None
    match = _URL_RE.match(url)
    own = (match["owner"].lower(), match["repo"].lower()) if match else None
    seen: set[tuple[str, str, int]] = set()
    shown: list[str] = []
    for ref in refs:
        number = ref.get("number") if isinstance(ref, dict) else None
        if not isinstance(number, int) or isinstance(number, bool):
            continue
        repository = ref.get("repository") or {}
        owner = (repository.get("owner") or {}).get("login")
        name = repository.get("name")
        if owner and name:
            key = (owner.lower(), name.lower())
        elif own:
            key = own
        else:
            continue
        if (*key, number) in seen:
            continue
        seen.add((*key, number))
        shown.append(
            f"#{number}" if key == own else _encodable(f"{owner}/{name}#{number}")
        )
    if not shown:
        return None
    text = "、".join(shown[:CLOSING_ISSUES_MAX])
    if len(shown) > CLOSING_ISSUES_MAX:
        text += f"…等 {len(shown)} 項"
    return text


@dataclass(frozen=True)
class SelfNotes:
    """The author's own why/what for a PR, from a local run summary or plan Goal.

    `rel` is the source path relative to `.maigo/` (e.g. `pr/40/summary-2.md`)."""

    rel: str
    kind: Literal["summary", "plan"]
    why: str | None
    what: str | None


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _pick_latest(directory: Path, stem: str) -> Path | None:
    """The newest `<stem>.md` / `<stem>-<n>.md` in `directory`: highest number wins
    (the unnumbered file counts as 1 and wins a tie), so `-10` beats `-2`."""
    pattern = re.compile(rf"^{re.escape(stem)}(?:-([1-9]\d*))?\.md$")
    best: tuple[tuple[int, bool], Path] | None = None
    try:
        for path in directory.iterdir():
            match = pattern.match(path.name)
            if not match or not is_listable_name(path.name) or not path.is_file():
                continue
            key = (int(match[1] or 1), match[1] is None)
            if best is None or key > best[0]:
                best = (key, path)
    except OSError:
        return None
    return best[1] if best else None


def find_self_notes(
    maigo_dir: Path, ident: str | None, head_ref: str | None
) -> SelfNotes | None:
    """Local why/what for a PR: `pr/<ident>/` first, then `topic/<slug>/` (slug from the
    head branch via `artifact_path.slugify`). A summary (`## 為什麼做`／`## 做了什麼`)
    anywhere beats any plan (`## Goal`, why only). Read-only; unreadable files count as
    absent."""
    directories: list[Path] = []
    if ident:
        directories.append(maigo_dir / "pr" / ident)
    slug = artifact_path.slugify(head_ref) if head_ref else None
    if slug:
        directories.append(maigo_dir / "topic" / slug)
    directories = [d for d in directories if is_listable_name(d.name)]
    kinds: tuple[Literal["summary", "plan"], ...] = ("summary", "plan")
    for kind in kinds:
        for directory in directories:
            path = _pick_latest(directory, kind)
            text = _read_text(path) if path else None
            if path is None or text is None:
                continue
            lines = _clean_body_lines(text)
            if kind == "summary":
                why = _clip(_section_text(lines, frozenset({"為什麼做"})))
                what = _clip(_section_text(lines, frozenset({"做了什麼"})))
            else:
                why = _clip(_section_text(lines, frozenset({"goal"})))
                what = None
            if why or what:
                return SelfNotes(
                    path.relative_to(maigo_dir).as_posix(), kind, why, what
                )
    return None


def render_detail_facts(
    *,
    type: str,  # noqa: A002
    status: str,
    title: str,
    url: str,
    additions: int | None,
    deletions: int | None,
    author: str | None,
    next_action: str | None,
    number: int | None,
    last_reviewed_at: str | None,
    review_time_source: str | None,
    acknowledged_at: str | None,
    load_command: str | None = None,
    result: str | None = None,
    related_files: Sequence[str] = (),
    review_threads: list[dict] | None = None,
    pr_body: str | None = None,
    closing_issues: Sequence[dict] | None = None,
    self_notes: SelfNotes | None = None,
) -> str:
    """The fact section (everything before `## 判斷`), work-board references/format-spec.md §1a; ends with a blank line.

    Only for `🔀` (own PR), between `- 連結：` and `- 規模：`: `pr_body` becomes the
    `- 對外（PR description）：` group (Why/What), `self_notes` the `- 自用（…）：` group,
    `closing_issues` the `- 關聯 issue：` line; each is left out when empty.

    `related_files` are paths relative to `.maigo/` in the order to print (see
    `sort_related_files`); each becomes a backticked, detail-file-relative sub-item of
    `- 相關檔案：`, and the field is left out when there are none.
    """
    lines = [f"# {type} {status} — {' '.join(title.split())}", "", f"- 連結：<{url}>"]
    if type == "🔀":
        why, what, summary = extract_why_what(pr_body)
        if why or what or summary:
            lines.append("- 對外（PR description）：")
            if summary:
                lines.append(f"  - 說明：{summary}")
            if why:
                lines.append(f"  - 為什麼：{why}")
            if what:
                lines.append(f"  - 做了什麼：{what}")
        if self_notes and (self_notes.why or self_notes.what):
            suffix = " 的 Goal" if self_notes.kind == "plan" else ""
            lines.append(f"- 自用（`../{self_notes.rel}`{suffix}）：")
            if self_notes.why:
                lines.append(f"  - 為什麼：{self_notes.why}")
            if self_notes.what:
                lines.append(f"  - 做了什麼：{self_notes.what}")
        closing = format_closing_issues(closing_issues, url)
        if closing:
            lines.append(f"- 關聯 issue：{closing}")
    is_pr = type != "🐛"
    if is_pr and additions is not None and deletions is not None:
        size = f"- 規模：Δ+{additions}/-{deletions}"
        lines.append(f"{size} ｜ 作者：{author}" if author else size)
    elif author:
        lines.append(f"- 作者：{author}")
    if is_pr and review_threads is not None:
        unresolved = sum(not t["isResolved"] for t in review_threads)
        resolved = len(review_threads) - unresolved
        lines.append(f"- Review 討論：未解決 {unresolved} ｜ 已解決 {resolved}")
    if next_action:
        action = next_action.replace("<n>", str(number)) if number else next_action
        lines.append(f"- 下一步：`{action}`")
    if load_command:
        lines.append(f"- 載入：`{load_command}`")
    if type == "👀":
        if result:
            lines.append(f"- 本地 review 結果：{result}")
        if last_reviewed_at:
            suffix = "（舊檔時間推估）" if review_time_source == "mtime" else ""
            lines.append(f"- 最後 review：{last_reviewed_at}{suffix}")
        else:
            lines.append("- 最後 review：尚未 review")
    if acknowledged_at:
        lines.append(f"- 已看完：{acknowledged_at}")
    if related_files:
        lines.append("- 相關檔案：")
        lines.extend(f"  - `../{rel}`" for rel in related_files)
    return "\n".join(lines) + "\n\n"


# --- related artifact files ---------------------------------------------------------

RELATED_GROUPS = ("review", "pr", "issue")  # scan and print order; never `topic/`
_KNOWN_STEMS = artifact_path.known_stems()


def sort_related_files(rels: Sequence[str]) -> list[str]:
    """Order `<group>/<ident>/<file>` paths: group, then known kinds (by `_KNOWN_KINDS`
    order, the unnumbered file before `-1`, then attempts ascending), then every other
    file by path."""

    def key(rel: str) -> tuple:
        group, _, rest = rel.split("/", 2)
        for index, stem in enumerate(_KNOWN_STEMS):
            match = re.fullmatch(re.escape(stem) + r"(?:-(\d+))?\.md", rest)
            if match:
                attempt = int(match[1] or 1)
                return (
                    RELATED_GROUPS.index(group),
                    0,
                    index,
                    attempt,
                    match[1] is not None,
                    rel,
                )
        return (RELATED_GROUPS.index(group), 1, 0, 0, False, rel)

    return sorted(rels, key=key)


def is_listable_name(name: str) -> bool:
    """Whether a file or directory name can appear in the related-files list: not hidden,
    not an in-flight temp file (`*.tmp`, `*~`), no backtick or
    line break (cannot sit in a one-line code span), and valid UTF-8 (a surrogate-escaped
    name from a non-UTF-8 filesystem cannot be written out)."""
    if name.startswith(".") or name.endswith((".tmp", "~")):
        return False
    if any(c in name for c in "`\r\n"):
        return False
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def scan_related_files(maigo_dir: Path, ident: str) -> list[str]:
    """Regular files under `<group>/<ident>/` for each of `RELATED_GROUPS`, as
    `<group>/<ident>/<path>`, sorted. A missing directory is just no files; names that
    `is_listable_name` rejects are left out, and an entry that cannot be inspected
    (OSError) is skipped without affecting the others."""
    found: list[str] = []
    for group in RELATED_GROUPS:
        top = maigo_dir / group / ident
        for dirpath, dirnames, filenames in os.walk(top):
            dirnames[:] = [d for d in dirnames if is_listable_name(d)]
            for name in filenames:
                if not is_listable_name(name):
                    continue
                full = os.path.join(dirpath, name)
                try:
                    if not os.path.isfile(full):
                        continue
                    rel = Path(full).relative_to(maigo_dir)
                except (OSError, ValueError):
                    continue
                found.append(rel.as_posix())
    return sort_related_files(found)


def format_local(now: datetime) -> str:
    return now.astimezone().strftime("%Y-%m-%d %H:%M")


def sanitize_error(message: str) -> str:
    """Last line, full-width parens → ASCII, one line, at most NOTE_MAX chars."""
    lines = [ln for ln in message.strip().splitlines() if ln.strip()]
    last = lines[-1] if lines else "unknown error"
    last = last.replace("（", "(").replace("）", ")")
    return " ".join(last.split())[:NOTE_MAX]


# --- fetch ---------------------------------------------------------------------


# GitHub's review-thread resolution lives in GraphQL, outside `gh pr view`.
_THREAD_QUERY = """query($owner:String!,$repo:String!,$number:Int!,$endCursor:String) {
  repository(owner:$owner,name:$repo) { pullRequest(number:$number) {
    reviewThreads(first:100,after:$endCursor) {
      pageInfo { hasNextPage endCursor }
      nodes { id isResolved comments(first:100) {
        commentPage: pageInfo { hasNextPage endCursor }
        nodes { author { login } createdAt pullRequestReview { id } }
      } }
    }
  } }
}"""
_THREAD_COMMENTS_QUERY = """query($id:ID!,$endCursor:String) {
  node(id:$id) { ... on PullRequestReviewThread {
    comments(first:100,after:$endCursor) {
      pageInfo { hasNextPage endCursor }
      nodes { author { login } createdAt pullRequestReview { id } }
    }
  } }
}"""


def fetch_review_threads(owner: str, repo: str, number: str) -> list[dict]:
    """Fetch every thread and comment; never classify a partial response as resolved."""
    pages = json.loads(
        sync.run(
            [
                "gh",
                "api",
                "graphql",
                "--paginate",
                "--slurp",
                "-f",
                f"query={_THREAD_QUERY}",
                "-f",
                f"owner={owner}",
                "-f",
                f"repo={repo}",
                "-F",
                f"number={number}",
            ]
        )
    )
    if not isinstance(pages, list) or not pages:
        raise ValueError("review threads: missing response pages")
    threads = []
    for page in pages:
        if page.get("errors"):
            raise ValueError(f"review threads: {page['errors']}")
        connection = page["data"]["repository"]["pullRequest"]["reviewThreads"]
        for thread in connection["nodes"]:
            if not isinstance(thread["isResolved"], bool):
                raise ValueError("review threads: missing resolution state")
            comments = thread["comments"]
            nodes = list(comments["nodes"])
            if comments["commentPage"]["hasNextPage"]:
                extra = json.loads(
                    sync.run(
                        [
                            "gh",
                            "api",
                            "graphql",
                            "--paginate",
                            "--slurp",
                            "-f",
                            f"query={_THREAD_COMMENTS_QUERY}",
                            "-f",
                            f"id={thread['id']}",
                            "-f",
                            f"endCursor={comments['commentPage']['endCursor']}",
                        ]
                    )
                )
                if not isinstance(extra, list) or not extra:
                    raise ValueError("review comments: missing response pages")
                for comment_page in extra:
                    if comment_page.get("errors"):
                        raise ValueError(f"review comments: {comment_page['errors']}")
                    nodes.extend(comment_page["data"]["node"]["comments"]["nodes"])
            threads.append({**thread, "comments": nodes})
    return threads


def fetch_item(
    url: str,
    type_hint: str | None,
    *,
    you: str = "",
    keep_type: bool = False,
    kind_known: bool = True,
) -> dict:
    """gh metadata for one URL: `{"type","gh_meta","url"}` or `{"error"}`. All via `sync.run`."""
    match = _URL_RE.match(url.strip())
    if not match:
        return {"error": f"not a GitHub issue/PR URL: {url}"}
    owner, repo, number = match["owner"], match["repo"], match["number"]
    base = f"https://github.com/{owner}/{repo}"
    try:
        if keep_type:
            is_pr = type_hint != "🐛"
        elif match["kind"] == "pull":
            is_pr = True
        elif not kind_known:
            probe = sync.run(
                [
                    "gh",
                    "api",
                    f"repos/{owner}/{repo}/issues/{number}",
                    "--jq",
                    ".pull_request != null",
                ]  # fmt: skip
            )
            is_pr = probe.strip() == "true"
        else:
            is_pr = False
        if is_pr:
            canonical = f"{base}/pull/{number}"
            meta = json.loads(
                sync.run(["gh", "pr", "view", canonical, "--json", PR_FIELDS])
            )
            meta["reviewThreads"] = fetch_review_threads(owner, repo, number)
            login = ((meta.get("author") or {}).get("login") or "").lower()
            if keep_type:
                item_type = type_hint or "👀"
            else:
                item_type = "🔀" if you and login == you.lower() else "👀"
        else:
            canonical = f"{base}/issues/{number}"
            meta = json.loads(
                sync.run(["gh", "issue", "view", canonical, "--json", ISSUE_FIELDS])
            )
            item_type = type_hint if keep_type and type_hint else "🐛"
    except (RuntimeError, OSError) as error:
        return {"error": sanitize_error(str(error))}
    except (ValueError, KeyError, TypeError) as error:
        return {"error": sanitize_error(f"gh 輸出不完整或不是合法 JSON：{error}")}
    return {"type": item_type, "gh_meta": meta, "url": canonical}


# --- data ----------------------------------------------------------------------


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class Entry:
    origin: str  # "line" | "addition" | "manual"
    url: str
    line: dict | None = None
    plan_line: dict | None = None
    addition: dict | None = None
    excluded: bool = False
    fetch: dict = field(default_factory=dict)

    @property
    def key(self) -> tuple | None:
        return sync.ref_key(self.url)


@dataclass
class Gathered:
    root: Path
    repo: str
    you: str
    now: datetime
    stale_days: int
    board_path: Path
    board_hash: str
    board_text: str
    plan: dict
    entries: list[Entry]
    details: dict[str, bytes | None]
    exclusions: dict
    manual_urls: list[str]


@dataclass
class Built:
    board_text: str
    rows_by_section: dict[str, list[dict]]
    detail_writes: list[dict]
    detail_deletes: list[dict]
    ledger_events: list[dict]
    manual_revive_urls: list[str]
    ack_results: list[dict]
    warnings: list[str]
    pending_reviews: list[dict]
    learn_pending: int
    aged: list[dict]
    closed_drops: list[dict]
    snapshot_overrides: dict[str, bool | None] = field(default_factory=dict)
    capped: list[dict] = field(
        default_factory=list
    )  # subset of `aged`: cut by DONE_CAP
    learn_expiring: list[dict] = field(default_factory=list)


# --- gather (reads and gh only) -------------------------------------------------


def normalize_targets(targets: list[str], repo: str) -> list[str]:
    urls: list[str] = []
    for target in targets:
        text = target.strip()
        if sync.ref_key(text):
            urls.append(text.rstrip("/"))
        elif text.isdigit():
            urls.append(f"https://github.com/{repo}/issues/{text}")
        elif _SHORT_REF_RE.match(text):
            m = _SHORT_REF_RE.match(text)
            assert m is not None
            urls.append(
                f"https://github.com/{m['owner']}/{m['repo']}/issues/{m['number']}"
            )
        else:
            raise RefreshError(1, f"--add：無法解析的 target：{target}")
    seen: set = set()
    unique = []
    for url in urls:
        key = sync.ref_key(url)
        if key not in seen:
            seen.add(key)
            unique.append(url)
    return unique


def gather(
    root: Path,
    repo: str,
    you: str,
    *,
    now: datetime,
    add: list[str],
    max_new: int,
    discovery: bool,
    stale_days: int,
    jobs: int,
) -> Gathered:
    maigo_dir = root / ".maigo"
    board_path = maigo_dir / "board.md"
    try:
        raw = board_path.read_bytes()
    except FileNotFoundError:
        hint = (
            "只找到舊的 review-board.md；舊格式遷移請在 Claude 裡跑 `/maigo:board`"
            if (maigo_dir / "review-board.md").exists()
            else "找不到 board.md；不自動建立，請在 Claude 裡跑 `/maigo:board` 建立，或指定 --maigo-root"
        )
        raise RefreshError(1, hint) from None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise RefreshError(1, f"board.md 不是合法 UTF-8：{error}") from error
    parsed = sync.parse_board(text, allow_missing_author=True)
    if parsed["legacy"]:
        raise RefreshError(
            1, "board.md 是舊版格式；refresh 不遷移，請在 Claude 裡跑 `/maigo:board`"
        )
    detail_root = (maigo_dir / "i").resolve()
    for line in parsed["lines"]:
        if not (maigo_dir / line["detail"]).resolve().is_relative_to(detail_root):
            raise RefreshError(
                1,
                f"board.md:{line['line_no']}: 細節檔路徑跑出 .maigo/i/：{line['detail']}",
            )
    errors = list(parsed["errors"]) + sync._resolve_lines(parsed, maigo_dir, repo)
    if errors:
        raise RefreshError(
            1,
            "board.md 有無法處理的行，未寫任何檔；請修正或在 Claude 裡跑 `/maigo:board`：\n"
            + "\n".join(errors),
        )

    details: dict[str, bytes | None] = {}
    for line in parsed["lines"]:
        path = maigo_dir / line["detail"]
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            data = None
        details[line["detail"]] = data
    manual_urls = normalize_targets(add, repo)
    exclusions, _ = sync.load_exclusions(sync._state_dir(root) / sync.LEDGER_NAME)

    plan = sync.plan_refresh(
        root,
        repo,
        you,
        now=now,
        max_new=max_new,
        discovery=discovery,
        dry_run=True,
        board_text=text,
        allow_missing_author=True,
    )
    plan_lines = {p["line_no"]: p for p in plan["lines"]}

    entries: list[Entry] = []
    for line in parsed["lines"]:
        plan_line = plan_lines[line["line_no"]]
        entries.append(
            Entry(
                "line",
                line["url"],
                line=line,
                plan_line=plan_line,
                excluded=bool(plan_line["excluded"]),
            )  # fmt: skip
        )
    for entry in entries:  # an excluded row keeps its detail file untouched
        if entry.line is None:
            continue
        data = details.get(entry.line["detail"])
        if entry.excluded or data is None:
            continue
        try:
            split_detail(data.decode("utf-8"))
        except ValueError as error:
            raise RefreshError(1, f"{entry.line['detail']}：{error}") from error

    board_keys = {e.key for e in entries}
    for url in manual_urls:
        if sync.ref_key(url) in board_keys:
            continue  # already on the board: the normal refresh covers it
        entries.append(Entry("manual", url, addition={"source": "manual"}))
        board_keys.add(sync.ref_key(url))
    manual_keys = {sync.ref_key(u) for u in manual_urls}
    for addition in plan["additions"]:
        if sync.ref_key(addition["url"]) in manual_keys:
            continue
        entries.append(Entry("addition", addition["url"], addition=addition))

    def fetch_one(entry: Entry) -> dict:
        if entry.excluded:
            return {}
        if entry.origin == "line":
            assert entry.line is not None
            return fetch_item(entry.url, entry.line["type"], you=you, keep_type=True)
        assert entry.addition is not None
        uncertain = entry.origin == "manual" or (
            entry.addition.get("source") == "artifact"
            and entry.addition.get("artifact_source") == "derived"
        )
        return fetch_item(
            entry.url,
            None if uncertain else entry.addition.get("type_hint"),
            you=you,
            kind_known=not uncertain,
        )

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        for entry, result in zip(entries, pool.map(fetch_one, entries)):
            entry.fetch = result
            if "url" in result and entry.origin != "line":
                entry.url = result["url"]
    for entry in entries:  # new rows may land on a stray detail file: read it too
        if entry.origin == "line":
            continue
        rel = board_state.detail_path(entry.url, repo)
        if rel and rel not in details:
            try:
                details[rel] = (maigo_dir / rel).read_bytes()
            except FileNotFoundError:
                details[rel] = None
            stray = details[rel]
            if stray is not None:
                try:
                    split_detail(stray.decode("utf-8"))
                except ValueError as error:
                    raise RefreshError(1, f"{rel}：{error}") from error
    return Gathered(
        root, repo, you, now, stale_days, board_path, _sha(raw), text, plan,
        entries, details, exclusions, manual_urls,
    )  # fmt: skip


# --- classify and render (no writes) --------------------------------------------


def apply_takeover(g: Gathered, takeover: dict[tuple, str]) -> list[str]:
    """Rewrite PR types in memory from the take-over list; returns warnings.

    Listed 👀 -> 🔀; a 🔀 whose author is not you and that left the list -> 👀.
    """
    warnings: list[str] = []
    live: set = set()
    excluded: set = set()
    unreachable: set = set()
    you = (g.you or "").lower()
    for entry in g.entries:
        key = entry.key
        listed = key is not None and key in takeover
        if entry.excluded:
            if key is not None and listed:
                excluded.add(key)
            continue
        if "gh_meta" not in entry.fetch:
            if key is not None and listed:
                unreachable.add(key)
            continue
        holder = entry.line if entry.line is not None else entry.fetch
        current = holder.get("type")
        if key is not None and listed:
            live.add(key)
            if current == "🐛":
                warnings.append(f"接棒清單的 {takeover[key]} 是 issue，略過")
            elif current == "👀":
                holder["type"] = "🔀"
        elif current == "🔀":
            author = (entry.fetch["gh_meta"].get("author") or {}).get("login") or ""
            if author and you and author.lower() != you:
                holder["type"] = "👀"
    for key, display in takeover.items():
        if key in live:
            continue
        if key in excluded:
            warnings.append(f"接棒清單的 {display} 已被 drop，清單不會讓它回來")
        elif key in unreachable:
            warnings.append(f"接棒清單的 {display} 這輪抓不到 gh 資料，本輪略過")
        else:
            warnings.append(
                f"接棒清單的 {display} 不在板上"
                f"（用 `/maigo:board {display}` 加入；已結案可從清單移除）"
            )
    return warnings


def run_acks(g: Gathered, *, dry_run: bool) -> list[dict]:
    items = []
    for entry in g.entries:
        line, plan_line = entry.line, entry.plan_line
        if (
            line is None
            or plan_line is None
            or entry.excluded
            or line["type"] != "👀"
            or plan_line["checkbox_change"] is None
            or "gh_meta" not in entry.fetch
        ):
            continue
        items.append(
            {
                "url": entry.url,
                "head": entry.fetch["gh_meta"].get("headRefOid") or "",
                "change": plan_line["checkbox_change"],
                "inferred": plan_line["inferred"],
                "reviewed_at": plan_line.get("reviewed_at"),
            }
        )
    if not items:
        return []
    return sync.ack_items(g.root, g.repo, g.you, items, dry_run=dry_run, now=g.now)


def _status_rank(status: str) -> int:
    try:
        return int(board_state._STATUS_META[board_state.BoardStatus(status)].rank)
    except ValueError:
        return int(board_state.Rank.P9)


def _section_of(item_type: str, rank: int) -> str:
    """Section glyph for a (type, rank) pair; same rule as `board_state.section_for`."""
    return board_state.section_for(
        board_state.Rank(rank), board_state.ItemType(item_type)
    ).value


def _row_from_line(entry: Entry, g: Gathered) -> dict:
    line = entry.line
    assert line is not None
    last_drop = (g.exclusions.get(entry.key) or {}).get("last_drop_at")
    return {
        "origin": entry.origin, "url": entry.url, "key": entry.key,
        "type": line["type"], "status": line["status"], "note": line["note"],
        "author": line["author"], "badges": list(line["badges"]),
        "action": line["action"], "result": line["result"], "size": line["size"],
        "ended": line["ended"] or _ended_label({"updatedAt": last_drop}),
        "detail": line["detail"], "title": line["title"], "checked": line["checked"],
        "section": _section_of(line["type"], _status_rank(line["status"])),
        "rank": _status_rank(line["status"]),
        "updated_at": last_drop, "mode": "keep", "gh_meta": None,
    }  # fmt: skip


def _is_error_note(note: str | None) -> bool:
    return bool(note and note.startswith(ERROR_NOTE_PREFIX))


def _prior_status(entry: Entry, g: Gathered) -> str | None:
    """Last good status. A row stuck at 抓不到 gets it back from the detail file's H1
    (a failed fetch never rewrites that file); unparseable -> None."""
    line = entry.line
    if line is None:
        return None
    if line["status"] != UNREACHABLE:
        return line["status"]
    data = g.details.get(line["detail"])
    if data is None:
        return None
    match = _DETAIL_H1_RE.match(data.decode("utf-8").split("\n", 1)[0])
    status = match["status"] if match else None
    if status in (None, UNREACHABLE):
        return None
    try:
        board_state.BoardStatus(status)
    except ValueError:
        return None
    return status


def _unreachable_row(entry: Entry, g: Gathered) -> dict:
    note = f"{ERROR_NOTE_PREFIX}{entry.fetch['error']}）"
    if entry.line is not None:
        row = _row_from_line(entry, g)
        if row["note"] and not _is_error_note(row["note"]):
            note = row["note"]  # keep the hand-written / command-written note
        row.update(
            error=entry.fetch["error"], status=UNREACHABLE, note=note, action=None,
            result=None,
            section=_section_of(row["type"], 0), rank=0,
            updated_at=None, mode="keep",
        )  # fmt: skip
        return row
    detail = board_state.detail_path(entry.url, g.repo) or ""
    hint = (entry.addition or {}).get("type_hint")
    kind_issue = "/issues/" in entry.url
    item_type = hint or ("🐛" if kind_issue else "👀")
    return {
        "origin": entry.origin, "url": entry.url, "key": entry.key,
        "type": item_type, "status": UNREACHABLE,
        "note": note, "author": "", "badges": [], "detail": detail,
        "action": None, "result": None, "size": None, "ended": None,
        "title": sync._short_ref(entry.url), "checked": False,
        "section": _section_of(item_type, 0),
        "rank": 0, "updated_at": None, "mode": "new-unreachable", "gh_meta": None,
        "error": entry.fetch["error"],
    }  # fmt: skip


def _ended_label(meta: dict) -> str | None:
    """`MM-DD` (local time) of when a closed item ended; None when unknown."""
    ended = meta.get("mergedAt") or meta.get("closedAt") or meta.get("updatedAt")
    if not ended:
        return None
    try:
        return board_state._parse_ts(ended).astimezone().strftime("%m-%d")
    except ValueError:
        return None


def _ended_at(row: dict) -> str | None:
    meta = row.get("gh_meta")
    if meta is None:
        return row.get("updated_at")  # excluded: ledger last_drop_at
    return meta.get("mergedAt") or meta.get("closedAt") or meta.get("updatedAt")


def build(
    g: Gathered,
    ack_results: list[dict],
    rules: list[WeightRule] | None = None,
    load_templates: dict[str, str] | None = None,
) -> Built:
    overrides = {
        r["url"]: r["simulated_review"] for r in ack_results if "simulated_review" in r
    }
    classify_entries = [e for e in g.entries if not e.excluded and "gh_meta" in e.fetch]
    items = []
    for entry in classify_entries:
        line = entry.line
        items.append(
            {
                "type": line["type"] if line else entry.fetch["type"],
                "gh_meta": entry.fetch["gh_meta"],
                "prior_status": _prior_status(entry, g) if line else None,
                "url": entry.url,
                "checked": line["checked"] if line else False,
                "checkbox_change": entry.plan_line["checkbox_change"]
                if entry.plan_line
                else None,
                "prior_badges": list(line["badges"]) if line else [],
                "title": line["title"] if line else "",
                "author": line["author"] if line else "",
                "prior_checked": entry.plan_line["snapshot_checked"]
                if entry.plan_line
                else False,
                "prior_others_activity_at": entry.plan_line["others_activity_at"]
                if entry.plan_line
                else None,
                "snapshot_written_at": g.plan.get("snapshot_written_at"),
            }
        )
    try:
        evaluated = board_state.evaluate_items(
            items,
            you=g.you,
            repo=g.repo,
            maigo_root=str(g.root),
            now=g.now,
            stale_days=g.stale_days,
            review_overrides=overrides,
        )
    except (ValueError, OSError) as error:
        raise RefreshError(1, f"分類失敗：{error}") from error
    by_entry = {id(e): r for e, r in zip(classify_entries, evaluated)}
    item_type_of = {id(e): i["type"] for e, i in zip(classify_entries, items)}

    # A checkbox change whose ack failed (locked/error) keeps the user's `[x]` so the
    # next round sees the change again instead of auto-unchecking it.
    unprocessed = {r["url"] for r in ack_results if r["result"] in ("locked", "error")}
    rows: list[dict] = []
    closed_drops: list[dict] = []
    for entry in g.entries:
        if entry.excluded:
            rows.append(_row_from_line(entry, g))
            continue
        if "error" in entry.fetch:
            rows.append(_unreachable_row(entry, g))
            continue
        r = by_entry[id(entry)]
        line = entry.line
        if (
            entry.origin == "addition"
            and (entry.addition or {}).get("source") == "artifact"
            and r["status"] in ("merged", "closed")
        ):
            closed_drops.append({"url": entry.url, "event": "drop", "reason": "closed"})
            continue
        prior = set(line["badges"]) if line else set()
        badges = {b for b in "🧠🔖" if b in prior}
        if r.get("learn_pending") or (r.get("reset_checkbox") and "🧠" not in prior):
            badges.add("🔖")
        if "💤" in r["badges"]:
            badges.add("💤")
        note = line["note"] if line else None
        if line and _is_error_note(note):
            note = None
        result = r["result"] if r["shows_result"] else None
        report_verdict = (result or "").removeprefix(board_state.RESULT_LAST_PREFIX)
        if r["shows_result"] and report_verdict in board_state.RESULT_VERDICTS:
            note = strip_duplicate_verdict_note(note, report_verdict)
        rows.append(
            {
                "origin": entry.origin, "url": entry.url, "key": entry.key,
                "type": item_type_of[id(entry)],
                "status": r["status"], "note": note, "author": r["author"],
                "badges": sorted(badges), "detail": line["detail"] if line else r["detail_path"],
                "title": r["title"],
                "action": None if r["shows_result"] else r["short_action"],
                "result": result, "size": r["size"],
                "ended": _ended_label(entry.fetch["gh_meta"]),
                "checked": line["checked"]
                if line and entry.url in unprocessed
                else bool(r["checked"]),
                "section": r["section"], "rank": r["rank"],
                "updated_at": entry.fetch["gh_meta"].get("updatedAt"),
                "others_activity_at": r.get("others_activity_at"),
                "mode": "write", "gh_meta": entry.fetch["gh_meta"], "r": r,
            }
        )  # fmt: skip

    aged: list[dict] = []
    capped: list[dict] = []
    learn_expiring: list[dict] = []
    candidates: list[tuple[datetime, dict]] = []  # ✅ rows subject to the cap
    kept: list[dict] = []
    for row in rows:
        if row["section"] == "✅" and row["origin"] != "manual":
            ended = _ended_at(row)
            if ended:
                ended_at = board_state._parse_ts(ended)
                age = g.now - ended_at
                learn_pending = (row["checked"] or "🔖" in row["badges"]) and (
                    "🧠" not in row["badges"]
                )
                if learn_pending and age <= LEARN_PENDING_LIMIT:
                    left = LEARN_PENDING_LIMIT - age
                    if left <= LEARN_PENDING_WARN:
                        learn_expiring.append(
                            {"url": row["url"], "title": row["title"],
                             "days_left": left.days}
                        )  # fmt: skip
                    kept.append(row)  # exempt from both the age limit and the cap
                    continue
                limit = AGE_LIMIT_REVIEW if row["type"] == "👀" else AGE_LIMIT_OWN
                if age > limit:
                    aged.append(row)
                    continue
                candidates.append((ended_at, row))
                continue
        kept.append(row)
    candidates.sort(key=lambda c: (-c[0].timestamp(), c[1].get("key") or ("", "", 0)))
    kept.extend(row for _, row in candidates[:DONE_CAP])
    for _, row in candidates[DONE_CAP:]:
        aged.append(row)
        capped.append(row)

    rows_by_section = {
        s: sort_rows(s, [r for r in kept if r["section"] == s], rules) for s in SECTIONS
    }
    all_rows = [r for s in SECTIONS for r in rows_by_section[s]]
    text = render_board(
        repo=g.repo,
        refreshed_at_local=format_local(g.now),
        rows_by_section=rows_by_section,
        learn_pending_count=count_learn_pending(all_rows),
    )

    load_warnings: list[str] = []
    detail_writes: list[dict] = []
    maigo_dir = g.root / ".maigo"
    for row in all_rows:
        if row["mode"] == "keep":
            continue
        rel = row["detail"]
        old = g.details.get(rel)
        ident = board_state.github_ref(row["url"], g.repo)
        related = scan_related_files(maigo_dir, ident) if ident else []
        if row["mode"] == "new-unreachable":
            facts = render_detail_facts(
                type=row["type"], status=UNREACHABLE, title=row["title"],
                url=row["url"], additions=None, deletions=None, author=None,
                next_action=None, number=None, last_reviewed_at=None,
                review_time_source=None, acknowledged_at=None,
                related_files=related,
            )  # fmt: skip
        else:
            r, meta = row["r"], row["gh_meta"]
            match = _URL_RE.match(row["url"])
            facts = render_detail_facts(
                type=row["type"], status=row["status"], title=row["title"],
                url=row["url"], additions=meta.get("additions"),
                deletions=meta.get("deletions"), author=row["author"],
                next_action=r["next_action"],
                number=int(match["number"]) if match else None,
                last_reviewed_at=r["last_reviewed_at"],
                review_time_source=r["review_time_source"],
                acknowledged_at=r["acknowledged_at"],
                load_command=load_command_for(
                    row, load_templates or {}, load_warnings
                ),
                review_threads=meta.get("reviewThreads"),
                result=row.get("result") if row["type"] == "👀" else None,
                related_files=related,
                pr_body=meta.get("body"),
                closing_issues=meta.get("closingIssuesReferences"),
                self_notes=(
                    find_self_notes(maigo_dir, ident, meta.get("headRefName"))
                    if row["type"] == "🔀"
                    else None
                ),
            )  # fmt: skip
        if old is None:
            preserved = NEW_PRESERVED
        else:
            try:
                _, preserved = split_detail(old.decode("utf-8"))
                preserved = collapse_blank_runs(preserved)
            except ValueError as error:
                raise RefreshError(1, f"{rel}：{error}") from error
        new_text = facts + preserved
        if old is not None and new_text.encode("utf-8") == old:
            continue
        detail_writes.append(
            {
                "path": rel, "create": old is None, "text": new_text,
                "old_hash": _sha(old) if old is not None else None,
            }
        )  # fmt: skip

    detail_deletes = []
    for row in aged:
        old = g.details.get(row["detail"])
        if old is not None:
            detail_deletes.append({"path": row["detail"], "hash": _sha(old)})

    at = g.now.isoformat()
    events: list[dict] = []
    for entry in g.plan["removed"]:
        events.append(
            {"url": entry["url"], "event": "drop", "reason": "dd", "at": entry["at"]}
        )
    for entry in g.plan["revived"]:
        events.append(
            {
                "url": entry["url"],
                "event": "revive",
                "reason": "re-requested",
                "at": entry["at"],
            }
        )
    just_dropped = {sync.ref_key(e["url"]) for e in g.plan["removed"]}
    manual_revive = [
        u
        for u in g.manual_urls
        if (g.exclusions.get(sync.ref_key(u)) or {}).get("excluded")
        or sync.ref_key(u) in just_dropped
    ]
    for row in aged:
        events.append({"url": row["url"], "event": "drop", "reason": "aged", "at": at})
    for drop in closed_drops:
        events.append({**drop, "at": at})

    warnings: list[str] = list(load_warnings)
    final_by_url = {r["url"]: r for r in all_rows}
    for result in ack_results:
        final = final_by_url.get(result["url"])
        if (
            result["result"] in ("no_report", "head_changed")
            and final
            and final.get("r", {}).get("needs_review")
        ):
            n = _URL_RE.match(final["url"])
            num = n["number"] if n else "?"
            warnings.append(
                f"#{num} 沒有本版 report／head 已變，未標記已看完；請先 /maigo:review {num}"
            )
        elif result["result"] == "report_changed":
            warnings.append(
                f"ack {result['url']}：報告已換版或尚未登記顯示版本，未標記已看完；請讀取本版後重新勾選"
            )
        elif result["result"] in ("locked", "error"):
            warnings.append(
                f"ack {result['url']}：{result['result']}（{result.get('message', '')}）"
            )
    # A checkbox change we could not process (fetch failed, ack locked/error) must
    # stay "changed" for the next round: snapshot the old state, not the new one.
    snapshot_overrides: dict[str, bool | None] = {}
    for entry in g.entries:
        plan_line = entry.plan_line
        if entry.line is None or plan_line is None or entry.excluded:
            continue
        change = plan_line["checkbox_change"]
        failed = "error" in entry.fetch
        if change is None or not (failed or entry.url in unprocessed):
            continue
        snapshot_overrides[entry.url] = (
            None if plan_line["inferred"] else change == "unchecked"
        )
        if failed:
            n = _URL_RE.match(entry.url)
            warnings.append(
                f"#{n['number'] if n else '?'} 的勾選變更還沒處理（抓不到），下次刷新會再處理"
            )
    for row in all_rows:
        if (row.get("r") or {}).get("reset_checkbox"):
            n = _URL_RE.match(row["url"])
            warnings.append(
                f"#{n['number'] if n else '?'} 有新 comment，已取消舊的勾選"
                + ("" if "🧠" in row["badges"] else "（補 🔖 待盤點）")
            )
    for row in all_rows:
        if row["status"] == UNREACHABLE and row["mode"] != "write":
            n = _URL_RE.match(row["url"])
            warnings.append(
                f"#{n['number'] if n else '?'} 抓不到：{row['error']}"
                if row.get("error")
                else f"#{n['number'] if n else '?'} 抓不到"
            )
    for row in all_rows:
        if not row.get("author"):
            n = _URL_RE.match(row["url"])
            warnings.append(f"#{n['number'] if n else '?'} {sync.AUTHOR_PENDING}")
    pending = []
    for row in all_rows:
        verdict = row.get("r")
        if verdict and verdict["needs_review"]:
            pending.append(
                {
                    "url": row["url"], "title": row["title"], "author": row["author"],
                    "status": row["status"], "last_reviewed_at": verdict["last_reviewed_at"],
                }
            )  # fmt: skip
    return Built(
        text, rows_by_section, detail_writes, detail_deletes, events, manual_revive,
        ack_results, warnings, pending, count_learn_pending(all_rows),
        [{"url": r["url"], "detail": r["detail"]} for r in aged], closed_drops,
        snapshot_overrides,
        [{"url": r["url"], "detail": r["detail"]} for r in capped], learn_expiring,
    )  # fmt: skip


# --- apply (writes) -------------------------------------------------------------


def _read_hash(path: Path) -> str | None:
    try:
        return _sha(path.read_bytes())
    except FileNotFoundError:
        return None


def _replace_from(src: Path, dst: Path) -> None:
    """Restore bytes with our own tmp+replace (must work even if atomic_write is broken)."""
    tmp = dst.with_name(f".{dst.name}.restore-{os.getpid()}")
    shutil.copyfile(src, tmp)
    os.replace(tmp, dst)


def _prune_backups(backup_root: Path, current: Path) -> None:
    """Keep the newest BACKUP_KEEP directories (by mtime); never remove *current*."""
    dirs = sorted(
        (p for p in backup_root.iterdir() if p.is_dir()),
        key=lambda p: (p.stat().st_mtime, p.name),
    )
    for old in dirs[:-BACKUP_KEEP]:
        if old != current:
            shutil.rmtree(old, ignore_errors=True)


LOCK_OWNER_NAME = "owner"


@contextlib.contextmanager
def refresh_lock(root: Path) -> Iterator[None]:
    """Keep the hash checks and every refresh side effect in one exclusive section."""
    lock = sync._state_dir(root) / ".refresh-write-lock"
    try:
        lock.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise RefreshError(3, f"無法建立刷新鎖目錄，尚未寫入：{error}") from error
    try:
        lock.mkdir()
    except FileExistsError as error:
        raise RefreshError(
            2, f"另一輪 board refresh 正在寫入{_lock_holder(lock)}；檢查 {lock} 後重跑",
            reason="refresh_locked",
        ) from error  # fmt: skip
    except OSError as error:
        raise RefreshError(3, f"無法取得刷新鎖，尚未寫入：{error}") from error
    owner = lock / LOCK_OWNER_NAME
    try:
        owner.write_text(f"{os.getpid()} {datetime.now(timezone.utc).isoformat()}\n")
    except OSError:
        pass  # owner info is advisory; the lock itself is already held
    try:
        yield
    finally:
        try:
            owner.unlink(missing_ok=True)
            lock.rmdir()
        except OSError as error:
            # Never mask the real result (or the original exception).
            print(
                f"warning: 無法移除刷新鎖 {lock}，請確認後手動刪除：{error}",
                file=sys.stderr,
            )


def _lock_holder(lock: Path) -> str:
    """` (pid N, 自 <ts>)` from the lock's owner file; empty when unreadable."""
    try:
        pid, stamp = (lock / LOCK_OWNER_NAME).read_text().split()
    except (OSError, ValueError):
        return ""
    return f"（pid {pid}，自 {stamp}）"


def apply_refresh(g: Gathered, built: Built) -> dict:
    """Apply a prepared refresh under the same lock as the CLI write path."""
    with refresh_lock(g.root):
        return _apply_refresh(g, built)


def _apply_refresh(g: Gathered, built: Built) -> dict:
    """Steps 8-14 of the side-effect order. Returns a summary; raises RefreshError."""
    root, maigo_dir = g.root, g.root / ".maigo"
    new_board = built.board_text
    board_changed = new_board != g.board_text

    # 8. CAS #2
    if _read_hash(g.board_path) != g.board_hash:
        raise RefreshError(2, CAS2_MESSAGE.format(what="board.md"))
    for write in built.detail_writes:
        current = _read_hash(maigo_dir / write["path"])
        if current != write["old_hash"]:
            raise RefreshError(2, CAS2_MESSAGE.format(what=write["path"]))
    for delete in built.detail_deletes:
        if _read_hash(maigo_dir / delete["path"]) != delete["hash"]:
            raise RefreshError(2, CAS2_MESSAGE.format(what=delete["path"]))

    # 9. backup
    backup_dir: Path | None = None
    to_backup = [w["path"] for w in built.detail_writes if not w["create"]]
    to_backup += [d["path"] for d in built.detail_deletes]
    if board_changed or to_backup:
        backup_root = sync._state_dir(root) / "backup"
        stamp = g.now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        try:
            backup_dir = backup_root / stamp
            suffix = 1
            while backup_dir.exists():
                suffix += 1
                backup_dir = backup_root / f"{stamp}-{suffix}"
            backup_dir.mkdir(parents=True)
            if board_changed:
                shutil.copy2(g.board_path, backup_dir / "board.md")
            for rel in to_backup:
                target = backup_dir / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(maigo_dir / rel, target)
        except OSError as error:
            raise RefreshError(3, f"備份失敗，尚未動到正式檔：{error}") from error

    # 10-11. write details (new first), then the board
    created: list[Path] = []
    attempted: list[str] = []
    board_attempted = False
    ordered = [w for w in built.detail_writes if w["create"]] + [
        w for w in built.detail_writes if not w["create"]
    ]
    try:
        for write in ordered:
            path = maigo_dir / write["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            if write["create"]:
                created.append(path)
            else:
                attempted.append(write["path"])
            review_report.atomic_write(path, write["text"])
        if board_changed:
            board_attempted = True
            review_report.atomic_write(g.board_path, new_board)
    except Exception as error:  # noqa: BLE001 - any failure must roll back
        failures: list[str] = []
        for path in reversed(created):
            try:
                path.unlink(missing_ok=True)
            except OSError as inner:
                failures.append(f"{path}（{inner}）")
        assert backup_dir is not None or not (attempted or board_attempted)
        for rel in reversed(attempted):
            try:
                assert backup_dir is not None
                _replace_from(backup_dir / rel, maigo_dir / rel)
            except Exception as inner:  # noqa: BLE001
                failures.append(f"{maigo_dir / rel}（{inner}）")
        if board_attempted and backup_dir is not None:
            try:
                _replace_from(backup_dir / "board.md", g.board_path)
            except Exception as inner:  # noqa: BLE001
                failures.append(f"{g.board_path}（{inner}）")
        message = f"寫入失敗，已從備份還原：{error}"
        if failures:
            message = (
                f"寫入失敗，且部分檔案未能還原：{error}\n備份在 {backup_dir}；未還原："
                + "、".join(failures)
            )
        raise RefreshError(
            3, message, backup=str(backup_dir) if backup_dir else None
        ) from error

    if backup_dir is not None:
        with contextlib.suppress(OSError):
            _prune_backups(backup_dir.parent, backup_dir)

    # 12. delete aged detail files (warning only)
    warnings: list[str] = []
    for delete in built.detail_deletes:
        try:
            (maigo_dir / delete["path"]).unlink(missing_ok=True)
        except OSError as error:
            warnings.append(f"刪除 {delete['path']} 失敗：{error}")

    # 13. ledger
    ledger = sync._state_dir(root) / sync.LEDGER_NAME
    pending_events = list(built.ledger_events)
    revive_manual = [
        {"url": u, "event": "revive", "reason": "manual", "at": g.now.isoformat()}
        for u in built.manual_revive_urls
    ]
    # dd / re-requested first, then manual revive, then aged / closed.
    ordered_events = (
        [e for e in pending_events if e["reason"] in ("dd", "re-requested")]
        + revive_manual
        + [e for e in pending_events if e["reason"] in ("aged", "closed")]
    )
    written = 0
    try:
        for event in ordered_events:
            sync.append_event(
                ledger, event["url"], event["event"], event["reason"], event["at"]
            )
            written += 1
    except OSError as error:
        left = ordered_events[written:]
        raise RefreshError(
            3,
            f"board 已是新版，但 ledger 有 {len(left)} 筆事件沒寫進去：{error}\n"
            + json.dumps(left, ensure_ascii=False),
            reason="post_write_failed",
            backup=str(backup_dir) if backup_dir else None,
        ) from error

    # 14. snapshot (re-reads the final board)
    previous_reviewed_at = {
        line["url"]: line.get("reviewed_at") for line in g.plan["lines"]
    }
    reviewed_at_overrides = {}
    for rows in built.rows_by_section.values():
        for row in rows:
            if row["type"] != "👀":
                continue
            record = row.get("r", {})
            # A pending check still belongs to the previously displayed report,
            # even when a failed ack is followed by classifying a newer report.
            if row["mode"] == "keep" or row["url"] in built.snapshot_overrides:
                reviewed_at_overrides[row["url"]] = previous_reviewed_at.get(row["url"])
            else:
                reviewed_at_overrides[row["url"]] = (
                    record.get("last_reviewed_at")
                    if record.get("review_time_source") == "report"
                    else None
                )
    others_activity_overrides = {
        row["url"]: row["others_activity_at"]
        for rows in built.rows_by_section.values()
        for row in rows
        if row["type"] == "🔀"
        and row["mode"] == "write"
        and "others_activity_at" in row
    }
    try:
        sync.write_snapshot(
            root, g.repo, g.now, checked_overrides=built.snapshot_overrides,
            reviewed_at_overrides=reviewed_at_overrides,
            others_activity_overrides=others_activity_overrides,
        )  # fmt: skip
    except (OSError, ValueError) as error:
        raise RefreshError(
            3, f"board 已是新版，但 snapshot 沒寫成：{error}",
            reason="post_write_failed",
            backup=str(backup_dir) if backup_dir else None,
        ) from error  # fmt: skip
    return {
        "backup": str(backup_dir) if backup_dir else None,
        "warnings": warnings,
        "ledger_events": ordered_events,
    }


# --- driver ---------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def run_refresh(
    root: Path,
    repo: str,
    you: str,
    *,
    apply: bool,
    add: list[str],
    max_new: int = sync.MAX_NEW_DEFAULT,
    discovery: bool = True,
    stale_days: int = board_state.STALE_DAYS_DEFAULT,
    jobs: int = 8,
    weights_file: Path | None = None,
    now: datetime | None = None,
) -> dict:
    now = now or _now()
    rules = load_weights(root, weights_file)  # bad lines reject before any gh call
    load_templates = load_load_templates(root)
    takeover = load_takeover(root, repo)  # bad lines reject before any gh call
    g = gather(
        root, repo, you, now=now, add=add, max_new=max_new, discovery=discovery,
        stale_days=stale_days, jobs=jobs,
    )  # fmt: skip
    takeover_warnings = apply_takeover(g, takeover)  # before run_acks: no ack for 🔀
    with refresh_lock(root) if apply else contextlib.nullcontext():
        if (
            apply and _read_hash(g.board_path) != g.board_hash
        ):  # CAS #1: before any side effect
            raise RefreshError(2, CAS_MESSAGE.format(what="board.md"))
        ack_results = run_acks(g, dry_run=not apply)
        built = build(g, ack_results, rules, load_templates)
        summary = summarize(g, built)
        summary["warnings"] += takeover_warnings
        summary["applied"] = apply
        if not apply:
            diff = difflib.unified_diff(
                g.board_text.splitlines(keepends=True),
                built.board_text.splitlines(keepends=True),
                "board.md (current)",
                "board.md (refreshed)",
            )
            summary["diff"] = "".join(diff)
            return summary
        outcome = _apply_refresh(g, built)
        summary["backup"] = outcome["backup"]
        summary["warnings"] += outcome["warnings"]
        return summary


def summarize(g: Gathered, built: Built) -> dict:
    sections = built.rows_by_section
    top = {
        section: [
            render_row(row, i, section)
            for i, row in enumerate(sections[section][:5], start=1)
        ]
        for section in ACTION_SECTIONS
    }
    return {
        "exit_reason": "ok",
        "board_path": str(g.board_path),
        "counts": {s: len(sections[s]) for s in SECTIONS},
        "learn_pending": built.learn_pending,
        "pending_reviews": built.pending_reviews,
        "top": top["🎯"],
        "top_review": top["👀"],
        "warnings": built.warnings,
        "ack_results": [
            {k: v for k, v in r.items() if k != "simulated_review"}
            for r in built.ack_results
        ],
        "errors": g.plan["errors"],
        "removed": g.plan["removed"],
        "revived": g.plan["revived"],
        "overflow": g.plan["overflow"],
        "unattributed": g.plan["unattributed"],
        "pending_orphans": g.plan["pending_orphans"],
        "excluded_detail_files": g.plan["excluded_detail_files"],
        "detail_writes": [
            {"path": w["path"], "create": w["create"]} for w in built.detail_writes
        ],
        "detail_deletes": [d["path"] for d in built.detail_deletes],
        "ledger_events": built.ledger_events
        + [
            {"url": u, "event": "revive", "reason": "manual"}
            for u in built.manual_revive_urls
        ],
        "aged": built.aged,
        "capped": built.capped,
        "learn_expiring": built.learn_expiring,
        "closed_drops": [d["url"] for d in built.closed_drops],
        "backup": None,
    }


def format_summary(summary: dict) -> str:
    out: list[str] = []
    if summary["applied"]:
        out.append(f"已寫回 {summary['board_path']}")
    else:
        out.append("預覽（未寫任何檔；加 --apply 才會寫回）")
    pending = summary["pending_reviews"]
    if pending:
        out.append(f"\n👀 現在要看的 PR（{len(pending)}）")
        for p in pending:
            who = f" @{p['author']}" if p["author"] else ""
            when = p["last_reviewed_at"] or "尚未 review"
            out.append(f"- {p['title']}{who} ｜ {p['status']} ｜ 最後 review：{when}")
    else:
        out.append("\n目前沒有待看的 PR。")
    out.append("\n🎯 我的下一件（前 5 行）")
    out.extend(summary["top"] or ["（空）"])
    out.append("\n👀 待我 review（前 5 行）")
    out.extend(summary["top_review"] or ["（空）"])
    c = summary["counts"]
    out.append(
        f"\n🎯 {c['🎯']} ｜ 👀 {c['👀']} ｜ ⏳ {c['⏳']} ｜ ✅ {c['✅']}"
        f" ｜ {summary['board_path']}"
    )
    if summary["overflow"]:
        out.append(f"\noverflow（{len(summary['overflow'])}，下次刷新接著補）")
        for o in summary["overflow"]:
            out.append(
                f"- {o.get('title', o['url'])} {author_token(o.get('author'))} {o['url']}"
            )
    if summary["unattributed"]:
        out.append(f"\nunattributed（{len(summary['unattributed'])}）")
        for u in summary["unattributed"]:
            out.append(f"- [{u['category']}] {u['path']}")
    for warning in summary["warnings"]:
        out.append(f"⚠️ {warning}")
    for error in summary["errors"]:
        out.append(f"⚠️ {error}")
    if summary["pending_orphans"]:
        out.append(
            f"\npending_orphans（寬限期內，本輪未判）：{len(summary['pending_orphans'])}"
        )
    if summary["removed"]:
        out.append(
            f"\nremoved（判為 dd）：{', '.join(r['url'] for r in summary['removed'])}"
        )
    if summary["excluded_detail_files"]:
        out.append("\nexcluded_detail_files（等你確認是否刪除）")
        for f in summary["excluded_detail_files"]:
            out.append(f"- {f['path']}")
    if summary["detail_writes"] or summary["detail_deletes"]:
        out.append(
            f"\n細節檔：新增/更新 {len(summary['detail_writes'])}、刪除 {len(summary['detail_deletes'])}"
        )
    if not summary["applied"]:
        out.append(f"\n預定 ledger 事件：{len(summary['ledger_events'])} 筆")
        out.append("\n" + (summary.get("diff") or "（board.md 無變動）"))
    elif summary.get("backup"):
        out.append(f"\n備份：{summary['backup']}")
    if summary["capped"]:
        out.append(
            f"\n✅ 超過 {DONE_CAP} 行上限，本輪清掉 {len(summary['capped'])} 行（最舊的先走）"
        )
    if summary["learn_expiring"]:
        out.append(f"\n🧠 學習盤點將到期（{len(summary['learn_expiring'])}）")
        for e in summary["learn_expiring"]:
            n = _URL_RE.match(e["url"])
            ref = f"#{n['number']}" if n else e["url"]
            out.append(
                f"- {ref} {e['title']} ｜ 剩 {e['days_left']} 天（過期後照一般老化清掉）"
            )
    if summary["learn_pending"]:
        out.append(
            f"\n🧠 有 {summary['learn_pending']} 項你勾了還沒盤點 → /maigo:board --learn"
        )
    return "\n".join(out)


# --- CLI defaults ---------------------------------------------------------------


def state_board_dir(path: Path) -> Path | None:
    """`<state>/<owner>/<repo>` containing a board.md when *path* is that dir or below it."""
    state = Path(os.path.realpath(maigo_state.get_state_root()))
    resolved = Path(os.path.realpath(path))
    if not resolved.is_relative_to(state):
        return None
    parts = resolved.relative_to(state).parts
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    if owner == maigo_state.BACKUP_DIRNAME:
        return None
    if not (
        maigo_state._is_valid_segment(owner) and maigo_state._is_valid_segment(repo)
    ):
        return None
    candidate = state / owner / repo
    return candidate if (candidate / "board.md").is_file() else None


@contextlib.contextmanager
def _synthetic_root(board_dir: Path) -> Iterator[Path]:
    """A temp root whose `.maigo` points at *board_dir*; only the symlink is removed."""
    tmp = Path(tempfile.mkdtemp(prefix="maigo-board-root-"))
    try:
        (tmp / ".maigo").symlink_to(board_dir, target_is_directory=True)
        yield tmp
    finally:
        try:
            link = tmp / ".maigo"
            if link.is_symlink():
                link.unlink()
            tmp.rmdir()
        except OSError as error:
            print(f"warning: 無法移除暫存目錄 {tmp}：{error}", file=sys.stderr)


def _unalias(obj, alias: str, real: str):
    if isinstance(obj, str):
        return obj.replace(alias, real)
    if isinstance(obj, dict):
        return {key: _unalias(value, alias, real) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_unalias(value, alias, real) for value in obj]
    return obj


def find_maigo_root(cwd: Path) -> Path:
    try:
        out = sync.run(["git", "-C", str(cwd), "worktree", "list", "--porcelain"])
    except (RuntimeError, OSError) as error:
        raise RefreshError(
            1, f"不在 git repo 裡，請指定 --maigo-root（{error}）"
        ) from error
    found = []
    seen_boards = set()
    for line in out.splitlines():
        if line.startswith("worktree "):
            path = Path(line[len("worktree ") :])
            board = path / ".maigo" / "board.md"
            if board.exists() and os.path.realpath(board) not in seen_boards:
                seen_boards.add(os.path.realpath(board))
                found.append(path)
    if not found:
        raise RefreshError(
            1,
            "找不到 board.md；不自動建立，請在 Claude 裡跑 `/maigo:board` 建立，或指定 --maigo-root",
        )
    if len(found) > 1:
        raise RefreshError(
            1,
            "找到多份 board.md，請用 --maigo-root 指定：\n"
            + "\n".join(f"- {p}" for p in found),
        )
    return found[0]


def resolve_repo(
    root: Path, explicit: str | None, *, allow_gh_fallback: bool = True
) -> str:
    header_repo = None
    with contextlib.suppress(OSError, UnicodeDecodeError):
        header_repo = sync.parse_header(
            (root / ".maigo" / "board.md").read_text(encoding="utf-8")
        )["repo"]
    if explicit:
        if header_repo and header_repo != explicit:
            raise RefreshError(
                1, f"--repo {explicit} 與 board header 的 {header_repo} 不一致"
            )
        return explicit
    if header_repo:
        return header_repo
    if not allow_gh_fallback:
        raise RefreshError(1, "從狀態目錄刷新時 board header 沒有 repo，請指定 --repo")
    previous = Path.cwd()
    try:
        os.chdir(root)
        return sync.run(
            ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"]
        )
    except (RuntimeError, OSError) as error:
        raise RefreshError(1, f"無法判斷 repo，請指定 --repo（{error}）") from error
    finally:
        os.chdir(previous)


def resolve_you(explicit: str | None) -> str:
    if explicit:
        return explicit
    try:
        login = sync.run(["gh", "api", "user", "--jq", ".login"])
    except (RuntimeError, OSError) as error:
        raise RefreshError(1, f"無法取得 gh 使用者，請指定 --you（{error}）") from error
    if not login:
        raise RefreshError(1, "gh api user 沒有回傳 login，請指定 --you")
    return login


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--apply", action="store_true", help="寫回（預設只預覽）")
    parser.add_argument(
        "--add", action="extend", nargs="+", default=[], metavar="TARGET"
    )
    parser.add_argument("--maigo-root", type=Path)
    parser.add_argument("--repo")
    parser.add_argument("--you")
    parser.add_argument("--max-new", type=int, default=sync.MAX_NEW_DEFAULT)
    parser.add_argument("--no-discovery", action="store_true")
    parser.add_argument(
        "--stale-days", type=int, default=board_state.STALE_DAYS_DEFAULT
    )
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument(
        "--weights",
        type=Path,
        help="同 rank 內加權檔（覆寫 repo 層與使用者層，只讀此檔）",
    )
    parser.add_argument("--json", action="store_true")


def cli(args: argparse.Namespace, *, now: datetime | None = None) -> int:
    board_dir = None
    if not (args.maigo_root and (args.maigo_root / ".maigo" / "board.md").exists()):
        board_dir = state_board_dir(args.maigo_root or Path.cwd())
    alias = real = ""
    with contextlib.ExitStack() as stack:
        try:
            if board_dir is not None:
                root = stack.enter_context(_synthetic_root(board_dir)).resolve()
                alias, real = str(root / ".maigo"), str(board_dir)
            else:
                root = (args.maigo_root or find_maigo_root(Path.cwd())).resolve()
            if args.apply:
                try:
                    maigo_state.check_maigo_link_trusted(root / ".maigo")
                except ValueError as error:
                    raise RefreshError(1, str(error)) from error
            repo = resolve_repo(root, args.repo, allow_gh_fallback=board_dir is None)
            you = resolve_you(args.you)
            summary = run_refresh(
                root, repo, you, apply=args.apply, add=args.add, max_new=args.max_new,
                discovery=not args.no_discovery, stale_days=args.stale_days,
                jobs=args.jobs, weights_file=args.weights, now=now,
            )  # fmt: skip
        except RefreshError as error:
            reason = (
                error.reason
                or {1: "rejected", 2: "cas_conflict", 3: "write_failed"}[error.code]
            )
            message = error.message
            extra = error.extra
            if board_dir is not None:
                message = _unalias(message, alias, real)
                extra = _unalias(extra, alias, real)
            print(f"board_refresh: {message}", file=sys.stderr)
            if args.json:
                payload = {"exit_reason": reason, "message": message, **extra}
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            return error.code
        if board_dir is not None:
            summary = _unalias(summary, alias, real)
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(format_summary(summary))
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_arguments(parser)
    return cli(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
