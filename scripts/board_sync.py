#!/usr/bin/env python3
"""
`/maigo:board` 的對帳層：解析 board.md、對帳 `.maigo/` 產物、discovery review PR、
dd 排除紀錄、`[x]` 勾選轉換。stdlib-only CLI，用 `python3` 直接執行。

`plan` / `ack` / `drop` / `revive` / `snapshot` **不寫 `board.md` 與 `.maigo/i/*.md`**——只輸出 JSON
變更清單，由 orchestrator 用 `Edit` 寫回（併發規則見 `skills/work-board/SKILL.md` §3(a)）。
`refresh --apply`（實作在 `scripts/board_refresh.py`）會整檔寫 `board.md` 與 `i/*.md`，改以
compare-and-swap 守住同一件事：別人動過檔案就中止、不寫（見 §3(b)）。它只寫自己擁有的機器狀態檔，
都在 `.maigo/_internal/board/`（寫入前自行建立目錄；`plan --dry-run` 與 `refresh` 預覽不寫任何檔、
不建目錄）：

- `dropped.jsonl`：排除紀錄，每行一個事件 `{"url","event":"drop"|"revive","reason","at"}`，
  只 append；讀取時依序 fold，最後一筆事件決定狀態。
- `snapshot.json`：`{"version":1,"written_at","items":{<url>:{"checked","detail"}}}`，
  上次刷新結束時 board 上有哪些項目與勾選狀態；原子寫入。
- `backup/<UTC ts>/`：`refresh --apply` 寫回前複製的 `board.md` 與細節檔，只留最新 10 份。

另外 `ack` 子命令會透過 `review_report.acknowledge` 寫 review.md 的 ack 標記。

子命令（都要 `--maigo-root <repo root> --repo <owner/name> --you <login>`）：

```
python3 scripts/board_sync.py plan [--dry-run] [--max-new 50] [--no-discovery] ...
echo '[{"url","head","change","inferred"}]' | python3 scripts/board_sync.py ack ...
python3 scripts/board_sync.py drop --reason {drop,dd,aged,closed} <url...> ...
python3 scripts/board_sync.py revive --reason manual <url...> ...
python3 scripts/board_sync.py snapshot ...
```

零 token 完整刷新（`refresh`，不需要 `--maigo-root` / `--repo` / `--you`，預設自動判斷）：

```
python3 scripts/board_sync.py refresh [--apply] [--add <url|n>...] [--max-new 50]
        [--no-discovery] [--stale-days 14] [--jobs 8] [--json]
        [--maigo-root <path>] [--repo <owner/name>] [--you <login>]
```

不帶 `--apply` 是預覽（印 unified diff，不寫檔、不 ack）。exit code：0 成功（含無變動）／預覽；
1 前置條件拒絕；2 CAS 衝突（除了 review.md 的 ack 標記外未寫任何檔，重跑即可）；
3 寫入階段失敗——寫 board／細節檔時失敗已從備份還原（`exit_reason: write_failed`）；board 已寫成功、
之後 ledger／snapshot 失敗則 **不還原**，board 已是新版（`exit_reason: post_write_failed`，重跑安全）。

canonical key：`ref_key(url)` = `(owner.lower(), repo.lower(), number)`，`pull` 與 `issues`
視為同一項；比對一律用 key，儲存時保留原 URL。

`gh` 呼叫全走 module-level `run(cmd) -> str`（失敗丟 `RuntimeError`），測試用
monkeypatch 注入。
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import board_state  # noqa: E402
import maigo_dir_catalog  # noqa: E402
import review_report  # noqa: E402

INTERNAL_BOARD_DIR = Path("_internal") / "board"
LEDGER_NAME = "dropped.jsonl"
SNAPSHOT_NAME = "snapshot.json"
ORPHAN_GRACE = timedelta(minutes=10)
SEARCH_LIMIT = 200
MAX_NEW_DEFAULT = 50
SEARCH_FIELDS = "url,title,author,repository,updatedAt,isDraft"
TIMELINE_JQ = (
    '[.[] | select(.event=="review_requested") | '
    "{event, created_at, requested_reviewer: {login: .requested_reviewer.login}}]"
)
DROP_REASONS = ("drop", "dd", "aged", "closed")

_URL_RE = re.compile(
    r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?P<kind>pull|issues)/(?P<number>\d+)/?$"
)
_ITEM_RE = re.compile(r"^(?:(?P<number>\d+)\.|-) \[(?P<mark>[ xX])\] (?P<rest>.*)$")
_BODY_RE = re.compile(
    r"\s*(?P<note>（[^）]*）)?"
    r"\s*(?:@(?P<author>[A-Za-z0-9_-]+(?:\[bot\])?))?"
    r"\s*(?P<badges>(?:[🧠💤🔖]\s*)*)"
    r"(?P<detail>i/\S+?\.md)?"
    r"\s*—\s?(?P<title>.*)$"
)
_DETAIL_ANYWHERE_RE = re.compile(r"i/\S+?\.md")
_LINK_RE = re.compile(r"^- 連結：(\S+)", re.MULTILINE)
_LEGACY_PR_RE = re.compile(r"^\*\*PR:\*\*\s*(\S+)", re.MULTILINE)
_SECTIONS = {
    "## 🎯 下一件": "🎯",
    "## ⏳ 等別人": "⏳",
    "## ✅ 最近結案": "✅",
}
_TYPES = {item_type.value for item_type in board_state.ItemType}
_STATUSES = sorted((s.value for s in board_state.BoardStatus), key=len, reverse=True)


def run(cmd: list[str]) -> str:
    """Run *cmd* and return stripped stdout; failure raises `RuntimeError`."""
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"exit {result.returncode}")
    return result.stdout.strip()


class BoardLegacyError(Exception):
    """board.md still uses the pre-three-section layout."""


def ref_key(url: str) -> tuple[str, str, int] | None:
    match = _URL_RE.match((url or "").strip())
    if not match:
        return None
    return (
        match["owner"].lower(),
        match["repo"].lower(),
        int(match["number"]),
    )


def _short_ref(url: str) -> str:
    match = _URL_RE.match(url.strip())
    return f"{match['owner']}/{match['repo']}#{match['number']}" if match else url


def _utc(ts: str) -> datetime:
    return board_state._parse_ts(ts)


# --- board parsing ---------------------------------------------------------


def parse_board(text: str) -> dict:
    """Parse board.md lines per the work-board grammar; never skip bad lines silently."""
    lines: list[dict] = []
    unparsed: list[dict] = []
    errors: list[str] = []
    legacy = False
    section: str | None = None
    for line_no, raw in enumerate(text.splitlines(), start=1):
        if raw.startswith("##"):
            heading = next((s for h, s in _SECTIONS.items() if raw.startswith(h)), None)
            if heading is None:
                legacy = True
            section = heading
            continue
        match = _ITEM_RE.match(raw)
        if not match:
            found = _DETAIL_ANYWHERE_RE.search(raw)
            if found:  # a mangled item line must not look like a dd
                errors.append(
                    f"board.md:{line_no}: 格式壞掉（無法解析的項目行）：{raw}"
                )
                unparsed.append(
                    {"line_no": line_no, "raw": raw, "detail": found[0], "type": None}
                )
            continue
        rest = match["rest"]
        problem = None
        item_type = next((t for t in _TYPES if rest.startswith(t)), None)
        if section is None:
            problem = "項目不在任何 section 內"
        elif item_type is None:
            problem = "未知型別 emoji"
        status = body = None
        if problem is None:
            after_type = rest[len(item_type or "") :].lstrip()
            for word in _STATUSES:
                if after_type.startswith(word) and (
                    len(after_type) == len(word) or after_type[len(word)] in " （"
                ):
                    status, body = word, after_type[len(word) :]
                    break
            if status is None:
                problem = "未知狀態詞"
        parsed = _BODY_RE.match(body) if problem is None and body is not None else None
        if problem is None and parsed is None:
            problem = "缺 `— ` 分隔符或欄位格式壞掉"
        if problem is None and not parsed["detail"]:  # type: ignore[index]
            problem = "缺細節檔路徑"
        if problem is not None or parsed is None:
            errors.append(f"board.md:{line_no}: {problem}：{raw}")
            found = _DETAIL_ANYWHERE_RE.search(raw)
            unparsed.append(
                {
                    "line_no": line_no,
                    "raw": raw,
                    "detail": found[0] if found else None,
                    "type": item_type,
                }
            )
            continue
        lines.append(
            {
                "line_no": line_no,
                "section": section,
                "number": int(match["number"]) if match["number"] else None,
                "checked": match["mark"] in "xX",
                "type": item_type,
                "status": status,
                "note": parsed["note"],
                "author": parsed["author"],
                "badges": re.findall(r"[🧠💤🔖]", parsed["badges"]),
                "detail": parsed["detail"],
                "title": parsed["title"].strip(),
                "raw": raw,
            }
        )
    return {"lines": lines, "unparsed": unparsed, "errors": errors, "legacy": legacy}


def detail_url(
    maigo_dir: Path, detail: str, repo: str, item_type: str | None = None
) -> str | None:
    """URL from the detail file's `- 連結：` line; numeric same-repo paths fall back."""
    try:
        found = _LINK_RE.search((maigo_dir / detail).read_text())
    except OSError:
        found = None
    if found and ref_key(found[1]):
        return found[1].rstrip("/")
    numeric = re.fullmatch(r"i/(\d+)\.md", detail)
    if numeric and repo:
        kind = "issues" if item_type == "🐛" else "pull"
        return f"https://github.com/{repo}/{kind}/{numeric[1]}"
    return None


# --- ledger and snapshot ---------------------------------------------------


def append_event(ledger: Path, url: str, event: str, reason: str, at: str) -> None:
    """Append one JSON line; the ledger is append-only."""
    ledger.parent.mkdir(parents=True, exist_ok=True)
    record = {"url": url, "event": event, "reason": reason, "at": at}
    with open(ledger, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_exclusions(ledger: Path) -> tuple[dict, list[str]]:
    """Fold events in order. Returns ({key: {url, excluded, last_drop_at, reason}}, errors)."""
    state: dict = {}
    errors: list[str] = []
    try:
        text = ledger.read_text(encoding="utf-8")
    except OSError:
        return state, errors
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            event = record["event"]
            url = record["url"]
            key = ref_key(url)
            if event not in ("drop", "revive") or key is None:
                raise ValueError("unknown event or URL")
            at = record["at"]
            _utc(at)
        except (ValueError, KeyError, TypeError) as error:
            errors.append(f"{LEDGER_NAME}:{number}: 壞掉的紀錄（{error}）")
            continue
        entry = state.setdefault(key, {"url": url})
        entry["url"] = url
        if event == "drop":
            entry.update(
                excluded=True, last_drop_at=at, reason=record.get("reason", "")
            )
        else:
            entry["excluded"] = False
    return state, errors


def _load_snapshot(path: Path) -> tuple[dict | None, str | None, list[str]]:
    """Returns (items or None, written_at, errors)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, None, []
    except (OSError, ValueError) as error:
        return None, None, [f"{SNAPSHOT_NAME}: 讀不到（{error}），視為第一次刷新"]
    if not isinstance(data, dict) or data.get("version") != 1:
        return None, None, [f"{SNAPSHOT_NAME}: 版本不符，視為第一次刷新"]
    items = data.get("items")
    written = data.get("written_at")
    return (
        items if isinstance(items, dict) else {},
        written if isinstance(written, str) else None,
        [],
    )


def checkbox_changes(
    entries: list[tuple[tuple | None, bool]], snapshot: dict | None
) -> dict:
    """key -> {change: checked|unchecked|None, inferred: bool}."""
    previous = {}
    for url, info in (snapshot or {}).items():
        key = ref_key(url)
        if key is not None and isinstance(info, dict):
            previous[key] = bool(info.get("checked"))
    result: dict = {}
    for key, checked in entries:
        if key in previous:
            if checked != previous[key]:
                result[key] = {
                    "change": "checked" if checked else "unchecked",
                    "inferred": False,
                }
            else:
                result[key] = {"change": None, "inferred": False}
        else:
            result[key] = {
                "change": "checked" if checked else None,
                "inferred": checked,
            }
    return result


# --- dd detection ----------------------------------------------------------


def scan_orphans(
    maigo_dir: Path, board_details: set[str], repo: str, now: datetime
) -> tuple[dict, list[dict], list[str]]:
    """i/ files no board line references. Returns (settled {key: info}, pending, errors)."""
    settled: dict = {}
    pending: list[dict] = []
    errors: list[str] = []
    detail_dir = maigo_dir / "i"
    if not detail_dir.is_dir():
        return settled, pending, errors
    for path in sorted(detail_dir.glob("*.md")):
        detail = f"i/{path.name}"
        if detail in board_details:
            continue
        try:
            age = now.timestamp() - path.stat().st_mtime
        except OSError:
            continue
        if age < ORPHAN_GRACE.total_seconds():
            pending.append({"path": detail})
            continue
        url = detail_url(maigo_dir, detail, repo)
        key = ref_key(url) if url else None
        if url is None or key is None:
            errors.append(f"{detail}: 孤兒細節檔沒有可解析的 `連結`，無法判定 dd")
            continue
        settled[key] = {"url": url, "path": detail}
    return settled, pending, errors


def detect_removed(
    snapshot: dict,
    orphans: dict,
    board_keys: set,
    excluded: set,
    board_details: set[str] | frozenset[str] = frozenset(),
) -> list[dict]:
    """(snapshot ∪ orphans) − board − excluded; returns [{url, key, source}]."""
    removed: dict = {}
    for url, info in snapshot.items():
        key = ref_key(url)
        detail = info.get("detail") if isinstance(info, dict) else None
        if key is None or detail in board_details:
            continue
        removed[key] = {"url": url, "key": key, "source": "snapshot"}
    for key, info in orphans.items():
        removed.setdefault(key, {"url": info["url"], "key": key, "source": "orphan"})
    return [
        entry
        for key, entry in removed.items()
        if key not in board_keys and key not in excluded
    ]


# --- discovery -------------------------------------------------------------


def _json_stream(text: str) -> list:
    """Concatenate JSON arrays printed one per page by `gh api --paginate --jq`."""
    decoder = json.JSONDecoder()
    items: list = []
    index = 0
    while index < len(text):
        if text[index].isspace():
            index += 1
            continue
        value, index = decoder.raw_decode(text, index)
        items.extend(value if isinstance(value, list) else [value])
    return items


def discover(repo: str, you: str) -> tuple[dict, list[str]]:
    """Two `gh search prs` runs merged by key. Returns ({key: candidate}, errors)."""
    candidates: dict = {}
    errors: list[str] = []
    queries: tuple[tuple[str, list[str], str], ...] = (
        ("requested", [], "user-review-requested:@me"),
        ("reviewed", ["--reviewed-by", "@me"], "-author:@me"),
    )
    for flag, extra, query in queries:
        cmd = [
            "gh", "search", "prs", "--repo", repo, "--state", "open",
            "--limit", str(SEARCH_LIMIT), "--json", SEARCH_FIELDS,
            *extra, "--", query,
        ]  # fmt: skip
        try:
            results = json.loads(run(cmd) or "[]")
        except (RuntimeError, ValueError) as error:
            errors.append(f"gh search ({flag}) 失敗：{error}")
            continue
        if len(results) >= SEARCH_LIMIT:
            errors.append(
                f"gh search ({flag}) 結果數等於 limit {SEARCH_LIMIT}，可能截斷"
            )
        for result in results:
            url = result.get("url", "")
            key = ref_key(url)
            if key is None:
                continue
            author = result.get("author") or {}
            login = author.get("login") or ""
            entry = candidates.setdefault(
                key,
                {
                    "url": url,
                    "title": result.get("title", ""),
                    "author": login,
                    "is_bot": bool(author.get("is_bot")),
                    "updatedAt": result.get("updatedAt", ""),
                    "isDraft": bool(result.get("isDraft")),
                    "requested": False,
                    "reviewed": False,
                    "type_hint": "🔀" if login.lower() == you.lower() else "👀",
                },
            )
            entry[flag] = True
    return candidates, errors


def is_rerequested(events: list[dict], you: str, since: str | None) -> bool:
    """A review_requested event naming *you* strictly after *since*."""
    cutoff = _utc(since) if since else None
    for event in events:
        reviewer = ((event or {}).get("requested_reviewer") or {}).get("login") or ""
        if (
            event.get("event") == "review_requested"
            and reviewer.lower() == you.lower()
            and event.get("created_at")
            and (cutoff is None or _utc(event["created_at"]) > cutoff)
        ):
            return True
    return False


def _timeline_events(url: str) -> list[dict]:
    match = _URL_RE.match(url)
    if not match:
        raise RuntimeError(f"not a GitHub issue/PR URL: {url}")
    path = f"repos/{match['owner']}/{match['repo']}/issues/{match['number']}/timeline"
    return _json_stream(run(["gh", "api", path, "--paginate", "--jq", TIMELINE_JQ]))


# --- artifact reconciliation -----------------------------------------------


def reconcile_artifacts(
    maigo_dir: Path, repo: str
) -> tuple[list[dict], list[dict], list[str]]:
    """Map `.maigo/` artifacts to PR/issue URLs. Returns (candidates, unattributed, errors)."""
    catalog = maigo_dir_catalog.scan(maigo_dir)
    candidates: dict = {}
    unattributed: list[dict] = []
    errors: list[str] = []

    def add(url: str, source: str, hint: str) -> None:
        key = ref_key(url)
        if key is not None:
            candidates.setdefault(
                key, {"url": url, "artifact_source": source, "type_hint": hint}
            )

    def skip(name: str, category: str, reason: str) -> None:
        unattributed.append({"path": name, "category": category, "reason": reason})

    def internal(name: str) -> bool:
        return name.startswith(maigo_dir_catalog.INTERNAL_DIR + "/")

    nested_dirs: dict[tuple[str, str], list[str]] = {}
    for name in catalog.nested:
        if not internal(name):
            group, identifier, _file = name.split("/")
            nested_dirs.setdefault((group, identifier), []).append(name)
    for (group, identifier), names in sorted(nested_dirs.items()):
        review = f"{group}/{identifier}/review.md"
        if review in names:
            try:
                source = review_report.metadata((maigo_dir / review).read_text()).get(
                    "source", ""
                )
            except (OSError, ValueError) as error:
                errors.append(f"{review}: metadata 讀取失敗（{error}）")
                source = ""
            if ref_key(source):
                add(source, "metadata", "👀")
            else:
                skip(review, "nested", "metadata source 不是 GitHub URL")
        elif identifier.isdigit() and repo:
            kind = "pull" if group == "review" else "issues"
            add(
                f"https://github.com/{repo}/{kind}/{identifier}",
                "derived",
                "👀" if group == "review" else "🐛",
            )
        else:
            for name in names:
                skip(name, "nested", "id 不是純數字，沒有 owner 無法推導")
    for name in catalog.flat_identifier:
        if internal(name):
            continue
        split = maigo_dir_catalog.split_flat_name(name)
        found = None
        if split and split[0] == "review":
            try:
                text = (maigo_dir / name).read_text()
            except OSError:
                text = ""
            match = _LEGACY_PR_RE.search(text)
            if match and ref_key(match[1]):
                try:
                    if review_report.same_source(text, match[1].rstrip("/")):
                        found = match[1].rstrip("/")
                except ValueError:
                    found = None
        if found:
            add(found, "legacy-pr", "👀")
        else:
            skip(name, "flat_identifier", "沒有可靠的 PR URL")
    for category in ("identifier_named", "legacy_fixed_name", "unregistered"):
        for name in getattr(catalog, category):
            if not internal(name) and name.endswith(".md"):
                skip(name, category, "沒有可靠的 PR/issue 對應")
    return list(candidates.values()), unattributed, errors


# --- plan ------------------------------------------------------------------


def _state_dir(maigo_root: Path) -> Path:
    return maigo_root / ".maigo" / INTERNAL_BOARD_DIR


_HEADER_RE = re.compile(r"^# Work Board — (\S+)$")


def parse_header(text: str) -> dict:
    """First line of board.md: `{"repo": owner/name or None, "raw": <first line>}`."""
    raw = text.splitlines()[0] if text.strip() else ""
    match = _HEADER_RE.match(raw)
    return {"repo": match[1] if match else None, "raw": raw}


def _read_board(maigo_root: Path, text: str | None = None) -> dict:
    if text is None:
        board = maigo_root / ".maigo" / "board.md"
        try:
            text = board.read_text(encoding="utf-8")
        except FileNotFoundError:
            text = ""
    parsed = parse_board(text)
    if parsed["legacy"]:
        raise BoardLegacyError("board.md 是舊版格式；請先跑整檔正規化再執行 plan")
    return parsed


def _resolve_lines(parsed: dict, maigo_dir: Path, repo: str) -> list[str]:
    errors: list[str] = []
    for line in parsed["lines"]:
        line["url"] = detail_url(maigo_dir, line["detail"], repo, line["type"])
        if line["url"] is None:
            errors.append(
                f"board.md:{line['line_no']}: {line['detail']} 沒有可解析的 `連結`"
            )
    return errors


def plan_refresh(
    maigo_root: Path,
    repo: str,
    you: str,
    *,
    now: datetime | None = None,
    max_new: int = MAX_NEW_DEFAULT,
    discovery: bool = True,
    dry_run: bool = False,
    board_text: str | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    at = now.isoformat()
    maigo_dir = maigo_root / ".maigo"
    state_dir = _state_dir(maigo_root)
    ledger = state_dir / LEDGER_NAME
    parsed = _read_board(maigo_root, board_text)
    errors = list(parsed["errors"]) + _resolve_lines(parsed, maigo_dir, repo)
    lines = parsed["lines"]

    board_keys = {ref_key(line["url"]) for line in lines if line["url"]}
    board_details = {line["detail"] for line in lines}
    for bad in parsed["unparsed"]:  # a broken line must not look like a dd
        if bad["detail"]:
            board_details.add(bad["detail"])
            url = detail_url(maigo_dir, bad["detail"], repo, bad["type"])
            if url:
                board_keys.add(ref_key(url))
    board_keys.discard(None)

    snapshot, snapshot_at, snapshot_errors = _load_snapshot(state_dir / SNAPSHOT_NAME)
    errors += snapshot_errors
    exclusions, ledger_errors = load_exclusions(ledger)
    errors += ledger_errors

    orphans, pending, orphan_errors = scan_orphans(maigo_dir, board_details, repo, now)
    errors += orphan_errors

    def excluded_keys() -> set:
        return {k for k, v in exclusions.items() if v.get("excluded")}

    removed = detect_removed(
        snapshot or {}, orphans, board_keys, excluded_keys(), board_details
    )
    if snapshot and not lines and not parsed["unparsed"]:
        removed = []  # fail closed: a missing/empty board is not mass deletion
        errors.append(
            "board.md 不存在或沒有任何項目行，但 snapshot 有項目：略過 dd 判定"
        )
    for entry in removed:
        # The deletion happened between the last snapshot and now.
        drop_at = snapshot_at if entry["source"] == "snapshot" and snapshot_at else at
        entry["at"] = drop_at
        if not dry_run:
            append_event(ledger, entry["url"], "drop", "dd", drop_at)
        exclusions[entry["key"]] = {
            "url": entry["url"], "excluded": True, "last_drop_at": drop_at, "reason": "dd",
        }  # fmt: skip

    pool: list[dict] = []
    revived: list[dict] = []
    if discovery:
        found, search_errors = discover(repo, you)
        errors += search_errors
        for key, candidate in found.items():
            state = exclusions.get(key)
            if state and state.get("excluded"):
                if not candidate["requested"]:
                    continue
                try:
                    again = is_rerequested(
                        _timeline_events(candidate["url"]),
                        you,
                        state.get("last_drop_at"),
                    )
                except (RuntimeError, ValueError) as error:
                    errors.append(
                        f"{_short_ref(candidate['url'])}: timeline 抓取失敗，維持排除（{error}）"
                    )
                    continue
                if not again:
                    continue
                if not dry_run:
                    append_event(ledger, candidate["url"], "revive", "re-requested", at)
                state["excluded"] = False
                revived.append({"url": candidate["url"], "at": at})
            if key not in board_keys:
                pool.append(
                    {
                        **candidate,
                        "source": "requested" if candidate["requested"] else "reviewed",
                    }
                )

    artifacts, unattributed, artifact_errors = reconcile_artifacts(maigo_dir, repo)
    errors += artifact_errors
    pooled = {ref_key(item["url"]) for item in pool}
    for artifact in artifacts:
        key = ref_key(artifact["url"])
        if key in board_keys or key in pooled or key in excluded_keys():
            continue
        pool.append({**artifact, "source": "artifact", "updatedAt": ""})
        pooled.add(key)

    order = {"requested": 0, "reviewed": 1, "artifact": 2}
    pool.sort(key=lambda item: (order[item["source"]], item.get("updatedAt", "")))
    additions, overflow = pool[:max_new], pool[max_new:]

    excluded_now = excluded_keys()
    changes = checkbox_changes(
        [(ref_key(item["url"]), item["checked"]) for item in lines if item["url"]],
        snapshot,
    )
    out_lines = []
    for line in lines:
        key = ref_key(line["url"]) if line["url"] else None
        change = changes.get(key, {"change": None, "inferred": False})
        out_lines.append(
            {
                "line_no": line["line_no"],
                "url": line["url"],
                "type": line["type"],
                "status": line["status"],
                "detail": line["detail"],
                "badges": line["badges"],
                "author": line["author"],
                "title": line["title"],
                "checked": line["checked"],
                "checkbox_change": change["change"],
                "inferred": change["inferred"],
                "excluded": key in excluded_now,
            }
        )
    return {
        "dry_run": dry_run,
        "first_run": snapshot is None,
        "lines": out_lines,
        "removed": [
            {
                "url": e["url"],
                "source": e["source"],
                "reason": "dd",
                "at": e["at"],
            }
            for e in removed
        ],
        "revived": revived,
        "additions": additions,
        "overflow": overflow,
        "unattributed": unattributed,
        "pending_orphans": pending,
        "excluded_detail_files": [
            {"path": info["path"], "url": info["url"]}
            for key, info in sorted(orphans.items())
            if key in excluded_now
        ],
        "errors": errors,
    }


# --- ack / drop / snapshot -------------------------------------------------


def ack_items(
    maigo_root: Path,
    repo: str,
    you: str,
    items: list[dict],
    *,
    dry_run: bool = False,
    now: datetime | None = None,
) -> list[dict]:
    """Ack each item; `dry_run` takes the same branches but writes nothing and
    returns `simulated_review` (the record as it would look afterwards)."""
    at = (now or datetime.now(timezone.utc)).isoformat()
    results = []
    for item in items:
        url = (item.get("url") or "").rstrip("/")
        head = item.get("head") or ""
        change = item.get("change")
        result = {"url": url, "result": "skipped"}
        try:
            if change not in ("checked", "unchecked") or ref_key(url) is None:
                results.append(result)
                continue
            path = review_report.report_path(maigo_root, url, repo)
            try:
                record = review_report.metadata(path.read_text())
            except FileNotFoundError:
                record = {}
            if not record:
                result["result"] = "no_report"
            else:
                source = (
                    record["source"]
                    if ref_key(record["source"]) == ref_key(url)
                    else url
                )
                if change == "unchecked":
                    if dry_run:
                        result["simulated_review"] = {
                            k: v
                            for k, v in record.items()
                            if k not in ("acknowledged_at", "acknowledged_by")
                        }
                    else:
                        review_report.acknowledge(
                            maigo_root, source, repo, head, you, True
                        )
                    result["result"] = "unacked"
                elif record["head_sha"] != head:
                    result["result"] = "head_changed"
                elif item.get("inferred") and board_state.acked_current(
                    record, you, head
                ):
                    result["result"] = "already_acked"
                else:
                    if dry_run:
                        result["simulated_review"] = {
                            **record,
                            "acknowledged_at": at,
                            "acknowledged_by": you,
                        }
                    else:
                        review_report.acknowledge(maigo_root, source, repo, head, you)
                    result["result"] = "acked"
        except (OSError, ValueError, KeyError) as error:
            locked = "being updated" in str(error)
            result.update(result="locked" if locked else "error", message=str(error))
        results.append(result)
    return results


def drop_urls(
    maigo_root: Path, urls: list[str], reason: str, now: datetime | None = None
) -> list[dict]:
    at = (now or datetime.now(timezone.utc)).isoformat()
    ledger = _state_dir(maigo_root) / LEDGER_NAME
    results = []
    for url in urls:
        url = url.strip()
        if ref_key(url) is None:
            results.append(
                {"url": url, "result": "error", "message": "不是 issue/PR URL"}
            )
            continue
        append_event(ledger, url, "drop", reason, at)
        results.append({"url": url, "result": "dropped", "reason": reason})
    return results


def revive_urls(
    maigo_root: Path, urls: list[str], reason: str, now: datetime | None = None
) -> list[dict]:
    """Explicit re-add: write a revive event only for keys currently excluded."""
    at = (now or datetime.now(timezone.utc)).isoformat()
    ledger = _state_dir(maigo_root) / LEDGER_NAME
    state, _ = load_exclusions(ledger)
    results = []
    for url in urls:
        url = url.strip()
        key = ref_key(url)
        if key is None:
            results.append(
                {"url": url, "result": "error", "message": "不是 issue/PR URL"}
            )
        elif state.get(key, {}).get("excluded"):
            append_event(ledger, url, "revive", reason, at)
            state[key]["excluded"] = False
            results.append({"url": url, "result": "revived"})
        else:
            results.append({"url": url, "result": "not_excluded"})
    return results


def write_snapshot(
    maigo_root: Path,
    repo: str,
    now: datetime | None = None,
    checked_overrides: dict[str, bool | None] | None = None,
) -> dict:
    """Re-read the current board.md (not the plan-time copy) and persist it.

    `checked_overrides[url]` records a different `checked` (or `None` = leave the
    URL out) so a checkbox change refresh could not process is seen again next round."""
    maigo_dir = maigo_root / ".maigo"
    parsed = _read_board(maigo_root)
    errors = list(parsed["errors"]) + _resolve_lines(parsed, maigo_dir, repo)
    items = {
        line["url"]: {"checked": line["checked"], "detail": line["detail"]}
        for line in parsed["lines"]
        if line["url"]
    }
    for override_url, value in (checked_overrides or {}).items():
        if override_url not in items:
            continue
        if value is None:
            del items[override_url]
        else:
            items[override_url]["checked"] = value
    state_dir = _state_dir(maigo_root)
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "written_at": (now or datetime.now(timezone.utc)).isoformat(),
        "items": items,
    }
    path = state_dir / SNAPSHOT_NAME
    review_report.atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2))
    return {"path": str(path), "count": len(items), "errors": errors}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    refresh_parser = sub.add_parser(
        "refresh", help="零 token 完整刷新（預設預覽；--apply 才寫回）"
    )
    # function-level import: board_refresh imports this module back. A broken
    # refresh module must not take plan/ack/... (used by the delegate commands) down.
    try:
        board_refresh = importlib.import_module(
            f"{__package__}.board_refresh" if __package__ else "board_refresh"
        )
        board_refresh.add_arguments(refresh_parser)
    except ImportError as error:
        board_refresh = None
        refresh_parser.set_defaults(import_error=str(error))
    for name in ("plan", "ack", "drop", "revive", "snapshot"):
        p = sub.add_parser(name)
        p.add_argument("--maigo-root", type=Path, required=True)
        p.add_argument("--repo", required=True)
        p.add_argument("--you", required=True)
        if name == "plan":
            p.add_argument("--dry-run", action="store_true")
            p.add_argument("--max-new", type=int, default=MAX_NEW_DEFAULT)
            p.add_argument("--no-discovery", action="store_true")
        if name == "drop":
            p.add_argument("--reason", choices=DROP_REASONS, required=True)
            p.add_argument("urls", nargs="+")
        if name == "revive":
            p.add_argument("--reason", choices=("manual",), required=True)
            p.add_argument("urls", nargs="+")
    args = parser.parse_args(argv)
    if args.command == "refresh":
        if board_refresh is None:
            print(f"board_sync: refresh 無法載入：{args.import_error}", file=sys.stderr)
            return 1
        return board_refresh.cli(args)
    root = args.maigo_root.resolve()
    try:
        if args.command == "plan":
            result: object = plan_refresh(
                root,
                args.repo,
                args.you,
                max_new=args.max_new,
                discovery=not args.no_discovery,
                dry_run=args.dry_run,
            )
        elif args.command == "ack":
            items = json.loads(sys.stdin.read() or "[]")
            result = ack_items(root, args.repo, args.you, items)
        elif args.command == "drop":
            result = drop_urls(root, args.urls, args.reason)
        elif args.command == "revive":
            result = revive_urls(root, args.urls, args.reason)
        else:
            result = write_snapshot(root, args.repo)
    except (BoardLegacyError, OSError, ValueError) as error:
        print(f"board_sync: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
