#!/usr/bin/env python3
"""
Single source of truth for Work Board state (`.maigo/board.md`) classification.

Defines the detail-state enum (with rank / section / default next_action),
the pure `classify()` transition function, `ALLOWED_TRANSITIONS` — the
declarative transition graph a property test checks `classify()` against —
以及 `detail_path()`：把 issue/PR URL 算成 `.maigo/i/<slug>.md` 細節檔路徑的正典。
`next_action` / badges 這些欄位不再直接進 board 索引行，是細節檔（`.maigo/i/<slug>.md`）
的資料來源；索引行格式見 `skills/work-board/SKILL.md`。

跑（薄 CLI）：

```
echo '[{"type": "🐛", "gh_meta": {"state": "OPEN"}, "prior_status": null, "url": null}]' \
    | python3 scripts/board_state.py --you octocat --repo owner/repo
```

stdin：JSON 陣列 `[{type, gh_meta, prior_status, url, local_verdict_at}]`
（`type` 是 🐛/🔀/👀；`prior_status` 是上次寫進 board.md 的狀態詞或 `null`；
未知/過期的狀態詞視為 `null`，向下相容自動正規化；`url` 是 optional 的 GitHub
issue/PR URL，用來算 `detail_path`；`local_verdict_at` 是 optional 的 ISO 8601
時間戳，只對 👀 型別有意義——本地產出這次 review verdict 的時間。顯式給了就
直接用；省略且帶了 `--maigo-root` 時，`main()` 自動用 `github_ref()` 算出的
`<id>` 找 `.maigo/review/<id>/review.md`。新版優先取 metadata `reviewed_at`；
舊檔沒有 metadata 才取 UTC mtime（明確標為推估）。report 的 `head_sha` 用來偵測新 push，
`acknowledged_at` / `acknowledged_by` 記使用者本地已看完，不表示 GitHub 已送出。
檔案不存在時退回 GitHub reviews 與 prior_status。
optional `checked`（bool，現檔勾選）、`checkbox_change`（`checked`/`unchecked`/null，
來自 `board_sync.py plan`）、`prior_badges`（list）：（任一出現才輸出）多三個欄位——`checked`（最終勾選，
沒帶 `checked` 時為 `null`＝不要動 checkbox）、`learn_pending`（👀 剛被勾、且沒有 🧠）、
`acked_current`（report 已由你在目前 head 之後 ack）。規則見 `checkbox_after_refresh()`。
stdout：JSON 陣列；含 section/rank/status/next_action/badges/detail_path、title/author、
last_reviewed_at/review_time_source/acknowledged_at、needs_review 與 index_entry。
`--reviews` 僅輸出待看 PR 並依 rank 排序；不可拿過濾後的結果覆寫整份 board。
（`rank` 是整數，數字越小優先序越高，呼叫端直接用它排序；`detail_path` 無 `url`
或無法解析時為 `null`）。

`--you <login>` 提供目前使用者的 GitHub login，用來比較「你 vs 別人最後活動」；
省略時視為空字串（時間戳比較一律不觸發，退回各狀態機的預設分支）。
`--stale-days`（預設 14）控制 `💤` badge 的門檻。
`--repo <owner/name>` 提供 board 綁定的 cwd repo，用來判斷 `detail_path` 是否算
「同 repo」；省略時視為空字串（一律當跨 repo 處理）。
`--maigo-root <dir>` 提供 `.maigo/` 所在的 repo root，用來自動算
`local_verdict_at`（見上）；省略時不自動算，行為與這個選項加入前完全一致。

stdlib-only；`classify()` 與 `compute_badges()` 皆為純函式——`classify()`
完全不碰時間；`compute_badges()` 需要 wall-clock 比較，因此把 `now` 當成
明確參數傳入，不在函式內部呼叫 `datetime.now()`。`detail_path()` 同樣是純函式，
只做字串解析，不打任何網路請求。

`待送出`（`UNPOSTED_VERDICT`）的 `next_action` 模板含佔位字
`_REVIEW_DRAFT_PLACEHOLDER`；`main()` 在 `url` 可解析出識別碼時，用
function-level import 把它換成 `artifact_path("review-draft", ref)` 算出的
真實路徑（見 `main()` 內註解說明為何不能在模組頂層 import `artifact_path`）；
`url` 缺失或無法解析時保留佔位字，不假造路徑。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum, IntEnum
from pathlib import Path

STALE_DAYS_DEFAULT = 14


class Rank(IntEnum):
    """優先序階梯，10 級，數字越小越優先。永遠由 detail state 推導，不獨立儲存。"""

    P0 = 0
    P1 = 1
    P2 = 2
    P3 = 3
    P4 = 4
    P5 = 5
    P6 = 6
    P7 = 7
    P8 = 8
    P9 = 9


class Section(str, Enum):
    """board.md 的三個區塊。永遠由 rank 推導，不獨立儲存。"""

    NEXT = "🎯"
    WAITING = "⏳"
    DONE = "✅"


class ItemType(str, Enum):
    """對應 board.md 行文法的型別 emoji。"""

    ISSUE = "🐛"
    OWN_PR = "🔀"
    REVIEW_PR = "👀"


class BoardStatus(str, Enum):
    """Detail state——board.md 的 `**<狀態詞>**`。這是狀態機的唯一真相來源。"""

    # 跨型別終端狀態
    CLOSED = "closed"
    MERGED = "merged"
    DUP = "DUP"
    CLOSE = "CLOSE"
    ARCHIVED = "已放棄"

    # P0：orchestrator 指派，classify() 永遠不產出
    UNREACHABLE = "抓不到"

    # 🐛 issue
    PENDING_TRIAGE = "待 triage"
    READY = "READY"
    IN_PROGRESS = "IN_PROGRESS"
    NEW_REPLY = "有新回覆"
    NEEDS_INFO = "NEEDS_INFO"

    # 🔀 你的 PR
    WIP = "WIP"
    CONFLICT = "有衝突"
    CI_RED = "CI 紅"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    NEW_COMMENT = "有新 comment"
    MERGEABLE = "可合併"
    CI_PENDING = "CI 等待"
    AWAITING_REVIEW = "等 review"

    # 👀 在審的 PR
    OTHERS_DRAFT = "他人草稿"
    PENDING_REVIEW = "待 review"
    BALL_BACK = "↩︎ 回你的球"
    BLOCKED = "BLOCKED"
    NEEDS_CHANGES = "NEEDS_CHANGES"
    APPROVE_WITH_NITS = "APPROVE_WITH_NITS"
    APPROVE = "APPROVE"
    UNPOSTED_VERDICT = "待送出"
    REVIEWED = "已看完"


@dataclass(frozen=True)
class StatusMeta:
    rank: Rank
    next_action: str | None


# 待送出的 next_action 模板佔位字：`main()` 在 url 可解析時，用
# function-level import 的 `artifact_path("review-draft", ref)` 換掉這段
# （見 `main()` 內的 circular-import 註解）；url 缺失時保留佔位字，不假造路徑。
_REVIEW_DRAFT_PLACEHOLDER = "<review-draft>"

_STATUS_META: dict[BoardStatus, StatusMeta] = {
    # P0：抓不到
    BoardStatus.UNREACHABLE: StatusMeta(Rank.P0, None),
    # P1：卡住的
    BoardStatus.CONFLICT: StatusMeta(Rank.P1, "/maigo:address-comments"),
    BoardStatus.CI_RED: StatusMeta(Rank.P1, "gh pr checks <n>"),
    BoardStatus.CHANGES_REQUESTED: StatusMeta(Rank.P1, "/maigo:address-comments"),
    # P2：球被打回
    BoardStatus.BALL_BACK: StatusMeta(Rank.P2, "/maigo:review <n>"),
    BoardStatus.NEW_REPLY: StatusMeta(Rank.P2, "/maigo:triage-issue <n>"),
    BoardStatus.NEW_COMMENT: StatusMeta(Rank.P2, "/maigo:address-comments"),
    # P3：一步就結束
    BoardStatus.MERGEABLE: StatusMeta(Rank.P3, "gh pr merge <n>"),
    BoardStatus.UNPOSTED_VERDICT: StatusMeta(
        Rank.P3, f"gh pr review <n> --comment --body-file {_REVIEW_DRAFT_PLACEHOLDER}"
    ),
    # P4：等你審
    BoardStatus.PENDING_REVIEW: StatusMeta(Rank.P4, "/maigo:review <n>"),
    # P5：手上正在做
    BoardStatus.IN_PROGRESS: StatusMeta(Rank.P5, None),
    BoardStatus.WIP: StatusMeta(Rank.P5, None),
    # P6：沒判過
    BoardStatus.PENDING_TRIAGE: StatusMeta(Rank.P6, "/maigo:triage-issue <n>"),
    # P7：可以開工
    BoardStatus.READY: StatusMeta(Rank.P7, "/maigo:take-issue <n>"),
    # P8：等別人
    BoardStatus.AWAITING_REVIEW: StatusMeta(Rank.P8, None),
    BoardStatus.CI_PENDING: StatusMeta(Rank.P8, None),
    BoardStatus.NEEDS_INFO: StatusMeta(Rank.P8, None),
    BoardStatus.OTHERS_DRAFT: StatusMeta(Rank.P8, None),
    BoardStatus.BLOCKED: StatusMeta(Rank.P8, None),
    BoardStatus.NEEDS_CHANGES: StatusMeta(Rank.P8, None),
    BoardStatus.APPROVE_WITH_NITS: StatusMeta(Rank.P8, None),
    BoardStatus.APPROVE: StatusMeta(Rank.P8, None),
    BoardStatus.REVIEWED: StatusMeta(Rank.P8, None),
    # P9：結案
    BoardStatus.CLOSED: StatusMeta(Rank.P9, None),
    BoardStatus.MERGED: StatusMeta(Rank.P9, None),
    BoardStatus.DUP: StatusMeta(Rank.P9, None),
    BoardStatus.CLOSE: StatusMeta(Rank.P9, None),
    BoardStatus.ARCHIVED: StatusMeta(Rank.P9, None),
}

assert set(_STATUS_META) == set(BoardStatus), "每個 BoardStatus 都必須有 rank"


def _section_for_rank(rank: Rank) -> Section:
    """Rank → section：P0–P7 進 🎯、P8 進 ⏳、P9 進 ✅。"""
    if rank <= Rank.P7:
        return Section.NEXT
    if rank == Rank.P8:
        return Section.WAITING
    return Section.DONE


_REVIEW_VERDICTS = frozenset(
    {
        BoardStatus.BLOCKED,
        BoardStatus.NEEDS_CHANGES,
        BoardStatus.APPROVE_WITH_NITS,
        BoardStatus.APPROVE,
    }
)
_REVIEW_ACTIVE_VERDICTS = _REVIEW_VERDICTS | {
    BoardStatus.BALL_BACK,
    BoardStatus.UNPOSTED_VERDICT,
    BoardStatus.REVIEWED,
}
# Fresh report/submission evidence may arrive independently of the prior board row.
_REVIEW_STATES = _REVIEW_ACTIVE_VERDICTS | {
    BoardStatus.PENDING_REVIEW,
    BoardStatus.OTHERS_DRAFT,
}
_REVIEW_TRANSITIONS = frozenset(
    _REVIEW_STATES | {BoardStatus.MERGED, BoardStatus.CLOSED}
)

_OWN_PR_STATES = frozenset(
    {
        BoardStatus.WIP,
        BoardStatus.CONFLICT,
        BoardStatus.CI_RED,
        BoardStatus.CHANGES_REQUESTED,
        BoardStatus.NEW_COMMENT,
        BoardStatus.MERGEABLE,
        BoardStatus.CI_PENDING,
        BoardStatus.AWAITING_REVIEW,
    }
)
# 🔀 你的 PR 判定表完全不看 prior_status，每次刷新純由 gh_meta 重算——
# 所以這幾個狀態彼此互通，唯一的出邊限制是「一定含 MERGED/CLOSED」。
_OWN_PR_ALL_TRANSITIONS = frozenset(
    _OWN_PR_STATES | {BoardStatus.MERGED, BoardStatus.CLOSED}
)

ALLOWED_TRANSITIONS: dict[BoardStatus | None, frozenset[BoardStatus]] = {
    None: frozenset(
        {
            BoardStatus.CLOSED,
            BoardStatus.PENDING_TRIAGE,
            BoardStatus.MERGED,
            BoardStatus.OTHERS_DRAFT,
            BoardStatus.PENDING_REVIEW,
        }
        | _OWN_PR_STATES
    ),
    # 🐛 issue
    BoardStatus.PENDING_TRIAGE: frozenset(
        {BoardStatus.CLOSED, BoardStatus.PENDING_TRIAGE}
    ),
    BoardStatus.READY: frozenset({BoardStatus.CLOSED, BoardStatus.READY}),
    BoardStatus.IN_PROGRESS: frozenset({BoardStatus.CLOSED, BoardStatus.IN_PROGRESS}),
    BoardStatus.NEEDS_INFO: frozenset(
        {BoardStatus.CLOSED, BoardStatus.NEEDS_INFO, BoardStatus.NEW_REPLY}
    ),
    BoardStatus.NEW_REPLY: frozenset(
        {BoardStatus.CLOSED, BoardStatus.NEW_REPLY, BoardStatus.NEEDS_INFO}
    ),
    BoardStatus.DUP: frozenset({BoardStatus.DUP, BoardStatus.CLOSED}),
    BoardStatus.CLOSE: frozenset({BoardStatus.CLOSE, BoardStatus.CLOSED}),
    # 🔀 你的 PR —— 每個非終端狀態都能互通（見上方註解）
    BoardStatus.WIP: _OWN_PR_ALL_TRANSITIONS,
    BoardStatus.CONFLICT: _OWN_PR_ALL_TRANSITIONS,
    BoardStatus.CI_RED: _OWN_PR_ALL_TRANSITIONS,
    BoardStatus.CHANGES_REQUESTED: _OWN_PR_ALL_TRANSITIONS,
    BoardStatus.NEW_COMMENT: _OWN_PR_ALL_TRANSITIONS,
    BoardStatus.MERGEABLE: _OWN_PR_ALL_TRANSITIONS,
    BoardStatus.CI_PENDING: _OWN_PR_ALL_TRANSITIONS,
    BoardStatus.AWAITING_REVIEW: _OWN_PR_ALL_TRANSITIONS,
    # Review transitions are determined by current local/GitHub evidence.
    **{status: _REVIEW_TRANSITIONS for status in _REVIEW_STATES},
    # 終端狀態：無出邊（只能被 purge），自迴圈代表「刷新時原樣保留」
    BoardStatus.CLOSED: frozenset({BoardStatus.CLOSED}),
    BoardStatus.MERGED: frozenset({BoardStatus.MERGED}),
    BoardStatus.ARCHIVED: frozenset({BoardStatus.ARCHIVED}),
    # P0：orchestrator 指派；下次抓得到就正常重判，出邊涵蓋所有狀態
    BoardStatus.UNREACHABLE: frozenset(BoardStatus),
}

ALLOWED_TRANSITIONS[None] |= _REVIEW_TRANSITIONS

assert set(ALLOWED_TRANSITIONS) == set(BoardStatus) | {None}, (
    "ALLOWED_TRANSITIONS 必須涵蓋每個 BoardStatus 加上 None（剛加入、無 prior）"
)


@dataclass(frozen=True)
class ClassifyResult:
    section: Section
    rank: Rank
    status: BoardStatus
    next_action: str | None


def next_action_for_status(status: str) -> str | None:
    """給 UI 用：已知狀態詞回其 `next_action`；未知狀態詞或無預設下一步一律回 `None`。"""
    try:
        return _STATUS_META[BoardStatus(status)].next_action
    except ValueError:
        return None


_GITHUB_ISSUE_OR_PR_URL_RE = re.compile(
    r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?:pull|issues)/(?P<number>\d+)/?$"
)


def github_ref(url: str, home_repo: str = "") -> str | None:
    """
    把 issue/PR URL 算成識別碼片段（不含路徑前綴／副檔名）。

    `home_repo`（cwd repo，`owner/name`）與 URL 所屬 repo 相同時回 `<n>`；
    跨 repo（含 `home_repo` 為空字串——省略時一律當跨 repo）回 `<repo>-<n>`。
    只認 `https://github.com/<owner>/<repo>/(pull|issues)/<n>` 形式，其餘（非
    GitHub 網域、非 issue/PR 路徑、格式壞掉）一律回 `None`。

    已知限制（刻意取捨，不要自作主張加 owner 前綴）：`<repo>` 只取 repo 名、
    不含 owner，不同 owner 的同名 repo 在跨 repo 情境會撞號——路徑短優先。

    供 `scripts/artifact_path.py` 的第 1 級識別碼來源重用，不重複實作。
    """
    if not url:
        return None
    match = _GITHUB_ISSUE_OR_PR_URL_RE.match(url.strip())
    if not match:
        return None
    owner = match.group("owner")
    repo = match.group("repo")
    number = match.group("number")
    if home_repo and f"{owner}/{repo}" == home_repo:
        return number
    return f"{repo}-{number}"


def detail_path(url: str, home_repo: str = "") -> str | None:
    """
    把 issue/PR URL 算成 board 索引行用的細節檔相對路徑（相對 `.maigo/`）。

    薄封裝：實際的 URL 解析在 `github_ref()`，這裡只加 `i/` 前綴與 `.md` 副檔名。
    """
    ref = github_ref(url, home_repo)
    if ref is None:
        return None
    return f"i/{ref}.md"


def _parse_ts(ts: str) -> datetime:
    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _activity_events(gh_meta: dict) -> list[tuple[str, str]]:
    """收集 (author_login, timestamp) 事件：開 issue/PR ＋ comments ＋ reviews。"""
    events: list[tuple[str, str]] = []
    author = (gh_meta.get("author") or {}).get("login")
    created_at = gh_meta.get("createdAt")
    if author and created_at:
        events.append((author, created_at))
    for comment in gh_meta.get("comments") or []:
        login = (comment.get("author") or {}).get("login")
        ts = comment.get("createdAt")
        if login and ts:
            events.append((login, ts))
    for review in gh_meta.get("reviews") or []:
        login = (review.get("author") or {}).get("login")
        ts = review.get("submittedAt") or review.get("createdAt")
        if login and ts:
            events.append((login, ts))
    return events


def _last_timestamp_by(events: list[tuple[str, str]], login: str) -> datetime | None:
    if not login:
        return None
    timestamps = [_parse_ts(ts) for author, ts in events if author == login]
    return max(timestamps) if timestamps else None


def _has_activity_after(
    events: list[tuple[str, str]], login: str | None, since: datetime
) -> bool:
    if not login:
        return False
    return any(author == login and _parse_ts(ts) > since for author, ts in events)


def _posted_by_you_since(reviews: list[dict], you: str, since: datetime | None) -> bool:
    """
    `you` 有沒有貼過 review——`since` 給定時只算 `submittedAt`/`createdAt` ≥
    `since` 的那些（本地新產出的 verdict 之後才貼的才算數，同 session 裡的舊
    review 不算「已送出這次的判斷」）；`since` 為 `None`（`local_verdict_at`
    欄位缺席）時退回舊行為，任一貼過就算。
    """
    for review in reviews:
        if review.get("state") in {"PENDING", "DISMISSED"}:
            continue
        if (review.get("author") or {}).get("login") != you:
            continue
        if since is None:
            return True
        ts = review.get("submittedAt") or review.get("createdAt")
        if ts and _parse_ts(ts) >= since:
            return True
    return False


def _has_others_activity_after(
    events: list[tuple[str, str]], you: str, since: datetime
) -> bool:
    return any(author != you and _parse_ts(ts) > since for author, ts in events)


def _ci_status(rollup: list[dict]) -> str:
    """回 `"red"` / `"pending"` / `"green"`；沒有 check 一律視為綠燈（不卡人）。"""
    if not rollup:
        return "green"
    has_pending = False
    for check in rollup:
        conclusion = check.get("conclusion")
        status = check.get("status") or check.get("state")
        if conclusion in {"FAILURE", "TIMED_OUT", "ERROR"} or status in {
            "FAILURE",
            "ERROR",
        }:
            return "red"
        if conclusion is None or status in {
            "IN_PROGRESS",
            "QUEUED",
            "PENDING",
            "WAITING",
        }:
            has_pending = True
    return "pending" if has_pending else "green"


def _is_conflicting(gh_meta: dict) -> bool:
    # `mergeable` 也可能是 `MERGEABLE` 或 `UNKNOWN`（GitHub 尚在計算）——
    # 只有明確 `CONFLICTING` 才判定衝突，`UNKNOWN` fallthrough 到其他規則。
    return gh_meta.get("mergeable") == "CONFLICTING"


def _classify_issue(
    gh_meta: dict, prior_status: BoardStatus | None, you: str
) -> BoardStatus:
    if gh_meta.get("state") == "CLOSED":
        return BoardStatus.CLOSED
    if prior_status in (BoardStatus.DUP, BoardStatus.CLOSE):
        return prior_status
    if prior_status in (None, BoardStatus.PENDING_TRIAGE):
        return BoardStatus.PENDING_TRIAGE
    assignees = {
        a.get("login") for a in gh_meta.get("assignees") or [] if a.get("login")
    }
    if prior_status is BoardStatus.READY and (not assignees or you in assignees):
        return BoardStatus.READY
    if prior_status is BoardStatus.IN_PROGRESS:
        return BoardStatus.IN_PROGRESS
    events = _activity_events(gh_meta)
    your_last = _last_timestamp_by(events, you)
    if your_last is not None and _has_others_activity_after(events, you, your_last):
        return BoardStatus.NEW_REPLY
    if prior_status is BoardStatus.NEEDS_INFO or your_last is not None:
        return BoardStatus.NEEDS_INFO
    return prior_status or BoardStatus.PENDING_TRIAGE


def _classify_own_pr(gh_meta: dict, you: str) -> BoardStatus:
    if gh_meta.get("state") == "MERGED" or gh_meta.get("mergedAt"):
        return BoardStatus.MERGED
    if gh_meta.get("state") == "CLOSED":
        return BoardStatus.CLOSED
    if gh_meta.get("isDraft"):
        return BoardStatus.WIP
    if _is_conflicting(gh_meta):
        return BoardStatus.CONFLICT
    ci = _ci_status(gh_meta.get("statusCheckRollup") or [])
    if ci == "red":
        return BoardStatus.CI_RED
    if gh_meta.get("reviewDecision") == "CHANGES_REQUESTED":
        return BoardStatus.CHANGES_REQUESTED
    events = _activity_events(gh_meta)
    your_last = _last_timestamp_by(events, you)
    if your_last is not None and _has_others_activity_after(events, you, your_last):
        return BoardStatus.NEW_COMMENT
    if gh_meta.get("reviewDecision") == "APPROVED" and ci == "green":
        return BoardStatus.MERGEABLE
    if ci == "pending":
        return BoardStatus.CI_PENDING
    return BoardStatus.AWAITING_REVIEW


def _classify_review_pr(
    gh_meta: dict,
    prior_status: BoardStatus | None,
    you: str,
    local_verdict_at: str | None = None,
    review: dict | None = None,
) -> BoardStatus:
    if gh_meta.get("state") == "MERGED" or gh_meta.get("mergedAt"):
        return BoardStatus.MERGED
    if gh_meta.get("state") == "CLOSED":
        return BoardStatus.CLOSED
    if gh_meta.get("isDraft"):
        return BoardStatus.OTHERS_DRAFT
    review = review or {}
    local_verdict_at = local_verdict_at or review.get("reviewed_at")
    reviews = gh_meta.get("reviews") or []
    since = _parse_ts(local_verdict_at) if local_verdict_at else None
    posted_by_you = _posted_by_you_since(reviews, you, since)
    acknowledged = (
        review.get("acknowledged_at")
        if review.get("acknowledged_by") == you and you
        else None
    )
    events = _activity_events(gh_meta)
    posted_times = [
        _parse_ts(r.get("submittedAt") or r["createdAt"])
        for r in reviews
        if (r.get("author") or {}).get("login") == you
        and r.get("state") not in {"PENDING", "DISMISSED"}
        and (r.get("submittedAt") or r.get("createdAt"))
    ]
    seen_times = [
        t for t in (since, _parse_ts(acknowledged) if acknowledged else None) if t
    ]
    seen_times.extend(posted_times)
    seen_at = max(seen_times) if seen_times else None
    old_head = review.get("head_sha")
    new_head = gh_meta.get("headRefOid")
    if old_head and new_head and old_head != new_head:
        return BoardStatus.BALL_BACK
    if seen_at:
        author = (gh_meta.get("author") or {}).get("login")
        commits = gh_meta.get("commits") or []
        if _has_activity_after(events, author, seen_at) or any(
            c.get("committedDate") and _parse_ts(c["committedDate"]) > seen_at
            for c in commits
        ):
            return BoardStatus.BALL_BACK
    if acknowledged and (since is None or _parse_ts(acknowledged) >= since):
        return BoardStatus.REVIEWED
    has_local = bool(local_verdict_at) or prior_status in _REVIEW_ACTIVE_VERDICTS
    if has_local and not posted_by_you:
        return BoardStatus.UNPOSTED_VERDICT
    if posted_by_you:
        verdict = _parse_prior_status(review.get("verdict"))
        if verdict in _REVIEW_VERDICTS:
            return verdict
        if prior_status in _REVIEW_VERDICTS:
            return prior_status
        return BoardStatus.REVIEWED
    return BoardStatus.PENDING_REVIEW


def classify(
    item_type: ItemType,
    gh_meta: dict,
    prior_status: BoardStatus | None,
    you: str = "",
    local_verdict_at: str | None = None,
    review: dict | None = None,
) -> ClassifyResult:
    """
    純函式：`(item_type, gh_meta, prior_status, you, local_verdict_at, review) ->
    section/status/rank/next_action`。

    不做任何 I/O；從 report 的明確時間/head 與 `gh_meta` 的 comments/reviews/commits
    比較新活動，不呼叫 `datetime.now()`（那是 `compute_badges()` 的事）。
    `local_verdict_at` 只有 `item_type is ItemType.REVIEW_PR` 時有效，其餘型別忽略。
    """
    if item_type is ItemType.ISSUE:
        status = _classify_issue(gh_meta, prior_status, you)
    elif item_type is ItemType.OWN_PR:
        status = _classify_own_pr(gh_meta, you)
    elif item_type is ItemType.REVIEW_PR:
        status = _classify_review_pr(
            gh_meta, prior_status, you, local_verdict_at, review
        )
    else:  # pragma: no cover - ItemType 是總函式，理論上不會落到這裡
        raise ValueError(f"unknown item_type: {item_type!r}")
    meta = _STATUS_META[status]
    return ClassifyResult(
        section=_section_for_rank(meta.rank),
        rank=meta.rank,
        status=status,
        next_action=meta.next_action,
    )


def compute_badges(
    gh_meta: dict, now: datetime, stale_days: int = STALE_DAYS_DEFAULT
) -> list[str]:
    """純函式，但需要 wall-clock——`now` 一律由呼叫端明確傳入。"""
    badges: list[str] = []
    updated_at = gh_meta.get("updatedAt")
    if updated_at:
        try:
            updated = _parse_ts(updated_at)
        except ValueError:
            updated = None
        if updated is not None and (now - updated) > timedelta(days=stale_days):
            badges.append("💤")
    return badges


def _parse_prior_status(raw: object) -> BoardStatus | None:
    """未知/過期狀態詞視為 `None`（向下相容：新 vocab 是舊的超集，自動正規化）。"""
    if not raw:
        return None
    try:
        return BoardStatus(raw)
    except ValueError:
        return None


def _import_artifact_path():
    """
    Function-level import: `artifact_path.py` imports `github_ref` from this
    module at module scope, so this module importing `artifact_path` back at
    module scope would fail (circular import, `artifact_path` not yet
    defined). Deferring to call time breaks the cycle; `classify()` stays a
    pure function untouched. Shared by both call sites in `main()` that need
    `artifact_path()`.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from artifact_path import artifact_path

    return artifact_path


def _auto_local_verdict_at(url: str, home_repo: str, maigo_root: str) -> str | None:
    """
    自動算 `local_verdict_at`：`url` 解析不出 `<id>`，或
    `<maigo_root>/.maigo/review/<id>/review.md` 不存在（含 `maigo_root` 為空
    字串——`--maigo-root` 省略時），一律回 `None`，呼叫端據此退回舊行為。

    新報告優先使用不受 touch/複製/acknowledge 影響的 `reviewed_at`。
    舊報告 mtime 用 `tz=timezone.utc` 明確轉換——這是 POSIX 時間戳轉 aware datetime，
    天生不會有時區偏移，不需要（也不能）用 naive `fromtimestamp()` 再手動猜
    系統時區。
    """
    if not maigo_root:
        return None
    ref = github_ref(url, home_repo)
    if ref is None:
        return None
    artifact_path = _import_artifact_path()
    review_path = Path(maigo_root) / artifact_path("review", ref)
    record = _load_review(url, home_repo, maigo_root)
    if record.get("reviewed_at"):
        return record["reviewed_at"]
    try:
        mtime = review_path.stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()


def _load_review(url: str, home_repo: str, maigo_root: str) -> dict:
    if not maigo_root or not github_ref(url, home_repo):
        return {}
    artifact_path = _import_artifact_path()
    from review_report import metadata

    path = Path(maigo_root) / artifact_path("review", github_ref(url, home_repo))
    try:
        record = metadata(path.read_text())
    except FileNotFoundError:
        return {}
    if record and record.get("source") != url.rstrip("/"):
        raise ValueError(f"Review ownership conflict: {path}")
    return record


def acked_current(review: dict, you: str, head: str | None) -> bool:
    """You acknowledged this report at the current head, after it was written."""
    acknowledged = review.get("acknowledged_at")
    reviewed = review.get("reviewed_at")
    return bool(
        you
        and acknowledged
        and review.get("acknowledged_by") == you
        and head
        and review.get("head_sha") == head
        and (not reviewed or _parse_ts(acknowledged) >= _parse_ts(reviewed))
    )


def checkbox_after_refresh(
    item_type: ItemType,
    checked_now: bool,
    acked_current: bool,
    needs_review: bool,
) -> bool:
    """
    刷新後的最終 checkbox。👀：`(acked_current or checked_now) and not needs_review`
    （回你的球／待 review 自動取消勾，`--reviewed` 之後一定是勾）；🐛/🔀 是純學習訊號，
    原樣保留。
    """
    if item_type is ItemType.REVIEW_PR:
        return (acked_current or checked_now) and not needs_review
    return checked_now


def index_entry(
    item_type: ItemType,
    status: BoardStatus,
    detail: str | None,
    title: str,
    author: str,
) -> str:
    """One-line display text; checkbox, badges and numbering belong to the caller."""
    contributor = f" @{author}" if author else ""
    return f"{item_type.value} {status.value}{contributor}{' ' + detail if detail else ''} — {' '.join(title.split())}".strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--you", default="", help="目前使用者的 GitHub login")
    parser.add_argument(
        "--stale-days", type=int, default=STALE_DAYS_DEFAULT, help="💤 badge 門檻天數"
    )
    parser.add_argument(
        "--repo",
        default="",
        help="board 綁定的 cwd repo（owner/name），判定 detail_path 同 repo/跨 repo",
    )
    parser.add_argument(
        "--maigo-root",
        default="",
        help="`.maigo/` 所在的 repo root；提供時自動算未顯式給值的 local_verdict_at",
    )
    parser.add_argument("--reviews", action="store_true", help="只列現在需要你看的 PR")
    args = parser.parse_args(argv)

    raw = sys.stdin.read()
    try:
        items = json.loads(raw) if raw.strip() else []
    except json.JSONDecodeError as error:
        sys.stderr.write(f"board_state: stdin 不是合法 JSON：{error}\n")
        return 1
    if not isinstance(items, list):
        sys.stderr.write("board_state: stdin JSON 必須是陣列\n")
        return 1

    now = datetime.now(timezone.utc)
    results: list[dict] = []
    for index, item in enumerate(items):
        try:
            item_type = ItemType(item["type"])
        except (KeyError, ValueError, TypeError) as error:
            sys.stderr.write(f"board_state: 第 {index} 項 `type` 無效：{error}\n")
            return 1
        gh_meta = item.get("gh_meta") or {}
        prior_status = _parse_prior_status(item.get("prior_status"))
        review = item.get("review") or {}
        try:
            if item_type is ItemType.REVIEW_PR and args.maigo_root:
                review = _load_review(item.get("url") or "", args.repo, args.maigo_root)
        except (OSError, ValueError) as error:
            sys.stderr.write(f"board_state: {error}\n")
            return 1
        local_verdict_at = item.get("local_verdict_at")
        review_time_source = "explicit" if local_verdict_at else None
        if local_verdict_at is None and review.get("reviewed_at"):
            local_verdict_at = review["reviewed_at"]
            review_time_source = "report"
        if (
            local_verdict_at is None
            and item_type is ItemType.REVIEW_PR
            and args.maigo_root
        ):
            local_verdict_at = _auto_local_verdict_at(
                item.get("url") or "", args.repo, args.maigo_root
            )
            if local_verdict_at:
                review_time_source = "report" if review.get("reviewed_at") else "mtime"
        result = classify(
            item_type, gh_meta, prior_status, args.you, local_verdict_at, review
        )
        badges = compute_badges(gh_meta, now, args.stale_days)

        next_action = result.next_action
        if result.status is BoardStatus.UNPOSTED_VERDICT and next_action is not None:
            ref = github_ref(item.get("url") or "", args.repo)
            if ref is not None:
                artifact_path = _import_artifact_path()
                next_action = next_action.replace(
                    _REVIEW_DRAFT_PLACEHOLDER, artifact_path("review-draft", ref)
                )

        needs_review = item_type is ItemType.REVIEW_PR and result.status in {
            BoardStatus.PENDING_REVIEW,
            BoardStatus.BALL_BACK,
            BoardStatus.UNPOSTED_VERDICT,
        }
        if args.reviews and not needs_review:
            continue
        current_ack = item_type is ItemType.REVIEW_PR and acked_current(
            review, args.you, gh_meta.get("headRefOid")
        )
        checked = (
            checkbox_after_refresh(
                item_type, bool(item["checked"]), current_ack, needs_review
            )
            if "checked" in item
            else None
        )
        learn_pending = (
            item_type is ItemType.REVIEW_PR
            and item.get("checkbox_change") == "checked"
            and "🧠" not in (item.get("prior_badges") or [])
        )
        title = gh_meta.get("title") or item.get("title") or ""
        author = (gh_meta.get("author") or {}).get("login") or item.get("author") or ""
        detail = detail_path(item.get("url") or "", args.repo)
        extra: dict = {}
        if {"checked", "checkbox_change", "prior_badges"} & item.keys():
            extra = {
                "checked": checked,
                "learn_pending": learn_pending,
                "acked_current": current_ack,
            }
        results.append(
            {
                **extra,
                "section": result.section.value,
                "rank": int(result.rank),
                "status": result.status.value,
                "next_action": next_action,
                "badges": badges,
                "detail_path": detail,
                "title": title,
                "author": author,
                "last_reviewed_at": local_verdict_at,
                "review_time_source": review_time_source,
                "acknowledged_at": review.get("acknowledged_at"),
                "needs_review": needs_review,
                "index_entry": index_entry(
                    item_type, result.status, detail, title, author
                ),
            }
        )

    if args.reviews:
        results.sort(key=lambda row: row["rank"])
    json.dump(results, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
