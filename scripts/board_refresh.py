#!/usr/bin/env python3
"""
`board_sync.py refresh`：零 token 的 Work Board 完整刷新（取代 `/maigo:board` 手動流程的
抓料、分類、渲染與寫回）。stdlib-only，由 `board_sync.main()` 以 function-level import 轉交。

- 不帶 `--apply` ＝預覽：整套流程照算（含 gh 抓料），但一個檔都不寫、不建 `_internal/`、
  不 append ledger、不寫 snapshot、**不 ack**（ack 只模擬）。輸出 board.md 的 unified diff。
- `--apply`：依序 CAS 預檢 #1 → ack → 渲染 → CAS 預檢 #2 → 備份 → 寫細節檔 → 寫 board.md →
  刪老化細節檔 → append ledger → 寫 snapshot。CAS 不一致（別人動過檔）→ exit 2，除了 ack 已寫的
  review.md 標記外不寫任何檔；寫細節檔／board 失敗 → 從備份還原、exit 3（`write_failed`）；
  board 已寫成功後 ledger／snapshot 失敗 → exit 3 但不還原（`post_write_failed`，重跑安全）。步驟與失敗語義見 `skills/work-board/SKILL.md` §3(b)。

渲染器（`render_line` / `render_board` / `render_detail_facts` / `split_detail`）是
`skills/work-board/SKILL.md` §1 / §1a 文法的程式鏡像，由 `tests/test_board_refresh.py`
的 round-trip 守著。外部指令一律走 `board_sync.run`（以 module attribute 存取，
測試只要 monkeypatch 那一個 seam）。

exit code：0 成功（含無變動）／預覽；1 前置條件拒絕；2 CAS 衝突；3 寫入階段失敗。
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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__:
    from . import board_state, review_report
    from . import board_sync as sync
else:  # run as a script: scripts/ is on sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import board_state  # type: ignore[no-redef]  # noqa: E402
    import board_sync as sync  # type: ignore[no-redef]  # noqa: E402
    import review_report  # type: ignore[no-redef]  # noqa: E402

SECTIONS = ("🎯", "⏳", "✅")
SECTION_TITLES = {"🎯": "## 🎯 下一件", "⏳": "## ⏳ 等別人", "✅": "## ✅ 最近結案"}
BADGE_ORDER = "🧠🔖💤"
AGE_LIMIT = timedelta(days=7)
BACKUP_KEEP = 10
NOTE_MAX = 80
JUDGMENT_HEADING = "## 判斷"
NEW_PRESERVED = "## 判斷\n\n\n## 筆記\n\n<!-- 手寫區 -->\n"
UNREACHABLE = "抓不到"
ERROR_NOTE_PREFIX = "（gh 失敗："
_DETAIL_H1_RE = re.compile(r"^# \S+ (?P<status>.+?) — ")
PR_FIELDS = (
    "title,state,isDraft,mergedAt,closedAt,mergeable,reviewDecision,createdAt,"
    "updatedAt,headRefOid,commits,reviews,comments,author,statusCheckRollup,"
    "additions,deletions"
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


# --- pure rendering (no I/O) ---------------------------------------------------


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
) -> str:
    """One board line per SKILL.md §1「行文法」."""
    prefix = f"{number}. " if number is not None else "- "
    line = f"{prefix}[{'x' if checked else ' '}] {type} {status}{note or ''}"
    if author:
        line += f" @{author}"
    shown = "".join(b for b in BADGE_ORDER if b in badges)
    if shown:
        line += f" {shown}"
    line += f" {detail} — {' '.join(title.split())}"
    return line.rstrip()


def count_learn_pending(rows: list[dict]) -> int:
    """Rows that are (`[x]` or `🔖`) and have no `🧠` (SKILL.md §1, §5)."""
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
    """Whole board.md per SKILL.md §1「Sections」; 🎯 is numbered from 1."""
    counts = {s: len(rows_by_section.get(s, [])) for s in SECTIONS}
    header = (
        f"> 最後刷新：{refreshed_at_local} ｜ 🎯 {counts['🎯']} ｜ "
        f"⏳ {counts['⏳']} ｜ ✅ {counts['✅']}"
    )
    if learn_pending_count > 0:
        header += f" ｜ 🧠 待學習盤點 {learn_pending_count}"
    out = [f"# Work Board — {repo}", header, ""]
    blocks: list[list[str]] = []
    for section in SECTIONS:
        rows = rows_by_section.get(section, [])
        block = [f"{SECTION_TITLES[section]}（{len(rows)}）"]
        if rows:
            block.append("")
            for index, row in enumerate(rows, start=1):
                block.append(
                    render_line(
                        number=index if section == "🎯" else None,
                        checked=row["checked"],
                        type=row["type"],
                        status=row["status"],
                        note=row.get("note"),
                        author=row.get("author"),
                        badges=row["badges"],
                        detail=row["detail"],
                        title=row["title"],
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


def sort_rows(section: str, rows: list[dict]) -> list[dict]:
    """🎯: rank asc, then updated_at asc. ⏳/✅: updated_at desc. Missing time = oldest."""

    def tiebreak(row: dict) -> tuple:
        return row.get("key") or ("", "", 0)

    if section == "🎯":
        return sorted(
            rows, key=lambda r: (r["rank"], _epoch(r.get("updated_at")), tiebreak(r))
        )
    return sorted(rows, key=lambda r: (-_epoch(r.get("updated_at")), tiebreak(r)))


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
) -> str:
    """The fact section (everything before `## 判斷`), SKILL.md §1a; ends with a blank line."""
    lines = [f"# {type} {status} — {' '.join(title.split())}", "", f"- 連結：{url}"]
    is_pr = type != "🐛"
    if is_pr and additions is not None and deletions is not None:
        size = f"- 規模：Δ+{additions}/-{deletions}"
        lines.append(f"{size} ｜ 作者：{author}" if author else size)
    elif author:
        lines.append(f"- 作者：{author}")
    if next_action:
        action = next_action.replace("<n>", str(number)) if number else next_action
        lines.append(f"- 下一步：`{action}`")
    if type == "👀":
        if last_reviewed_at:
            suffix = "（舊檔時間推估）" if review_time_source == "mtime" else ""
            lines.append(f"- 最後 review：{last_reviewed_at}{suffix}")
        else:
            lines.append("- 最後 review：尚未 review")
    if acknowledged_at:
        lines.append(f"- 已看完：{acknowledged_at}")
    return "\n".join(lines) + "\n\n"


def format_local(now: datetime) -> str:
    return now.astimezone().strftime("%Y-%m-%d %H:%M")


def sanitize_error(message: str) -> str:
    """Last line, full-width parens → ASCII, one line, at most NOTE_MAX chars."""
    lines = [ln for ln in message.strip().splitlines() if ln.strip()]
    last = lines[-1] if lines else "unknown error"
    last = last.replace("（", "(").replace("）", ")")
    return " ".join(last.split())[:NOTE_MAX]


# --- fetch ---------------------------------------------------------------------


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
    except ValueError as error:
        return {"error": sanitize_error(f"gh 輸出不是合法 JSON：{error}")}
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
    parsed = sync.parse_board(text)
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


def _row_from_line(entry: Entry, g: Gathered) -> dict:
    line = entry.line
    assert line is not None
    last_drop = (g.exclusions.get(entry.key) or {}).get("last_drop_at")
    return {
        "origin": entry.origin, "url": entry.url, "key": entry.key,
        "type": line["type"], "status": line["status"], "note": line["note"],
        "author": line["author"], "badges": list(line["badges"]),
        "detail": line["detail"], "title": line["title"], "checked": line["checked"],
        "section": line["section"], "rank": _status_rank(line["status"]),
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
            error=entry.fetch["error"], status=UNREACHABLE, note=note, section="🎯", rank=0,
            updated_at=None, mode="keep",
        )  # fmt: skip
        return row
    detail = board_state.detail_path(entry.url, g.repo) or ""
    hint = (entry.addition or {}).get("type_hint")
    kind_issue = "/issues/" in entry.url
    return {
        "origin": entry.origin, "url": entry.url, "key": entry.key,
        "type": hint or ("🐛" if kind_issue else "👀"), "status": UNREACHABLE,
        "note": note, "author": "", "badges": [], "detail": detail,
        "title": sync._short_ref(entry.url), "checked": False, "section": "🎯",
        "rank": 0, "updated_at": None, "mode": "new-unreachable", "gh_meta": None,
        "error": entry.fetch["error"],
    }  # fmt: skip


def _ended_at(row: dict) -> str | None:
    meta = row.get("gh_meta")
    if meta is None:
        return row.get("updated_at")  # excluded: ledger last_drop_at
    return meta.get("mergedAt") or meta.get("closedAt") or meta.get("updatedAt")


def build(g: Gathered, ack_results: list[dict]) -> Built:
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
        if r.get("learn_pending"):
            badges.add("🔖")
        if "💤" in r["badges"]:
            badges.add("💤")
        note = line["note"] if line else None
        if line and _is_error_note(note):
            note = None
        rows.append(
            {
                "origin": entry.origin, "url": entry.url, "key": entry.key,
                "type": item_type_of[id(entry)],
                "status": r["status"], "note": note, "author": r["author"],
                "badges": sorted(badges), "detail": line["detail"] if line else r["detail_path"],
                "title": r["title"],
                "checked": line["checked"]
                if line and entry.url in unprocessed
                else bool(r["checked"]),
                "section": r["section"], "rank": r["rank"],
                "updated_at": entry.fetch["gh_meta"].get("updatedAt"),
                "mode": "write", "gh_meta": entry.fetch["gh_meta"], "r": r,
            }
        )  # fmt: skip

    aged: list[dict] = []
    kept: list[dict] = []
    for row in rows:
        if row["section"] == "✅" and row["origin"] != "manual":
            ended = _ended_at(row)
            learn_pending = (row["checked"] or "🔖" in row["badges"]) and (
                "🧠" not in row["badges"]
            )
            if (
                ended
                and not learn_pending
                and g.now - board_state._parse_ts(ended) > AGE_LIMIT
            ):
                aged.append(row)
                continue
        kept.append(row)

    rows_by_section = {
        s: sort_rows(s, [r for r in kept if r["section"] == s]) for s in SECTIONS
    }
    all_rows = [r for s in SECTIONS for r in rows_by_section[s]]
    text = render_board(
        repo=g.repo,
        refreshed_at_local=format_local(g.now),
        rows_by_section=rows_by_section,
        learn_pending_count=count_learn_pending(all_rows),
    )

    detail_writes: list[dict] = []
    for row in all_rows:
        if row["mode"] == "keep":
            continue
        rel = row["detail"]
        old = g.details.get(rel)
        if row["mode"] == "new-unreachable":
            facts = render_detail_facts(
                type=row["type"], status=UNREACHABLE, title=row["title"],
                url=row["url"], additions=None, deletions=None, author=None,
                next_action=None, number=None, last_reviewed_at=None,
                review_time_source=None, acknowledged_at=None,
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
            )  # fmt: skip
        if old is None:
            preserved = NEW_PRESERVED
        else:
            try:
                _, preserved = split_detail(old.decode("utf-8"))
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

    warnings: list[str] = []
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
        if row["status"] == UNREACHABLE and row["mode"] != "write":
            n = _URL_RE.match(row["url"])
            warnings.append(
                f"#{n['number'] if n else '?'} 抓不到：{row['error']}"
                if row.get("error")
                else f"#{n['number'] if n else '?'} 抓不到"
            )
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


def apply_refresh(g: Gathered, built: Built) -> dict:
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
    try:
        sync.write_snapshot(
            root, g.repo, g.now, checked_overrides=built.snapshot_overrides
        )
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
    now: datetime | None = None,
) -> dict:
    now = now or _now()
    g = gather(
        root, repo, you, now=now, add=add, max_new=max_new, discovery=discovery,
        stale_days=stale_days, jobs=jobs,
    )  # fmt: skip
    if (
        apply and _read_hash(g.board_path) != g.board_hash
    ):  # CAS #1: before any side effect
        raise RefreshError(2, CAS_MESSAGE.format(what="board.md"))
    ack_results = run_acks(g, dry_run=not apply)
    built = build(g, ack_results)
    summary = summarize(g, built)
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
    outcome = apply_refresh(g, built)
    summary["backup"] = outcome["backup"]
    summary["warnings"] += outcome["warnings"]
    return summary


def summarize(g: Gathered, built: Built) -> dict:
    sections = built.rows_by_section
    top = [
        render_line(
            number=i,
            checked=r["checked"],
            type=r["type"],
            status=r["status"],
            note=r.get("note"),
            author=r.get("author"),
            badges=r["badges"],
            detail=r["detail"],
            title=r["title"],
        )  # fmt: skip
        for i, r in enumerate(sections["🎯"][:5], start=1)
    ]
    return {
        "exit_reason": "ok",
        "board_path": str(g.board_path),
        "counts": {s: len(sections[s]) for s in SECTIONS},
        "learn_pending": built.learn_pending,
        "pending_reviews": built.pending_reviews,
        "top": top,
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
    out.append("\n🎯 下一件（前 5 行）")
    out.extend(summary["top"] or ["（空）"])
    c = summary["counts"]
    out.append(
        f"\n🎯 {c['🎯']} ｜ ⏳ {c['⏳']} ｜ ✅ {c['✅']} ｜ {summary['board_path']}"
    )
    if summary["overflow"]:
        out.append(f"\noverflow（{len(summary['overflow'])}，下次刷新接著補）")
        for o in summary["overflow"]:
            out.append(
                f"- {o.get('title', o['url'])} @{o.get('author', '')} {o['url']}"
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
    if summary["learn_pending"]:
        out.append(
            f"\n🧠 有 {summary['learn_pending']} 項你勾了還沒盤點 → /maigo:board --learn"
        )
    return "\n".join(out)


# --- CLI defaults ---------------------------------------------------------------


def find_maigo_root(cwd: Path) -> Path:
    try:
        out = sync.run(["git", "-C", str(cwd), "worktree", "list", "--porcelain"])
    except (RuntimeError, OSError) as error:
        raise RefreshError(
            1, f"不在 git repo 裡，請指定 --maigo-root（{error}）"
        ) from error
    found = []
    for line in out.splitlines():
        if line.startswith("worktree "):
            path = Path(line[len("worktree ") :])
            if (path / ".maigo" / "board.md").exists():
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


def resolve_repo(root: Path, explicit: str | None) -> str:
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
    parser.add_argument("--json", action="store_true")


def cli(args: argparse.Namespace, *, now: datetime | None = None) -> int:
    try:
        root = (args.maigo_root or find_maigo_root(Path.cwd())).resolve()
        repo = resolve_repo(root, args.repo)
        you = resolve_you(args.you)
        summary = run_refresh(
            root, repo, you, apply=args.apply, add=args.add, max_new=args.max_new,
            discovery=not args.no_discovery, stale_days=args.stale_days,
            jobs=args.jobs, now=now,
        )  # fmt: skip
    except RefreshError as error:
        reason = (
            error.reason
            or {1: "rejected", 2: "cas_conflict", 3: "write_failed"}[error.code]
        )
        print(f"board_refresh: {error.message}", file=sys.stderr)
        if args.json:
            payload = {"exit_reason": reason, "message": error.message, **error.extra}
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return error.code
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
