#!/usr/bin/env python3
"""Single source of truth for Work Board state (`.maigo/board.md`) classification.

Defines the detail-state enum (with bucket / tier / default next_action),
the pure `classify()` transition function, and `ALLOWED_TRANSITIONS` — the
declarative transition graph a property test checks `classify()` against.

跑（薄 CLI）：

```
echo '[{"type": "🐛", "gh_meta": {"state": "OPEN"}, "prior_status": null}]' \
    | python3 scripts/board_state.py --you octocat
```

stdin：JSON 陣列 `[{type, gh_meta, prior_status}]`
（`type` 是 🐛/🔀/👀；`prior_status` 是上次寫進 board.md 的狀態詞或 `null`；
未知/過期的狀態詞視為 `null`，向下相容自動正規化）。
stdout：JSON 陣列 `[{bucket, status, tier, next_action, badges}]`。

`--you <login>` 提供目前使用者的 GitHub login，用來比較「你 vs 別人最後活動」；
省略時視為空字串（時間戳比較一律不觸發，退回各狀態機的預設分支）。
`--stale-days`（預設 14）控制 `💤` badge 的門檻。

stdlib-only；`classify()` 與 `compute_badges()` 皆為純函式——`classify()`
完全不碰時間；`compute_badges()` 需要 wall-clock 比較，因此把 `now` 當成
明確參數傳入，不在函式內部呼叫 `datetime.now()`。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

STALE_DAYS_DEFAULT = 14


class Tier(str, Enum):
    """顏色分級——決定 UI tier class，5 級由緊急到不急。"""

    BLOCKED = "blocked"
    ACT = "act"
    WIP = "wip"
    WAIT = "wait"
    DONE = "done"


class Bucket(str, Enum):
    """球權分區。永遠由 detail state 推導，不獨立儲存。"""

    TARGET = "🎯"
    WAITING = "⏳"
    DONE = "✅"
    UNSORTED = "📥"
    ARCHIVED = "🗄️"


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


@dataclass(frozen=True)
class StatusMeta:
    bucket: Bucket
    tier: Tier
    next_action: str | None


_STATUS_META: dict[BoardStatus, StatusMeta] = {
    BoardStatus.CLOSED: StatusMeta(Bucket.DONE, Tier.DONE, None),
    BoardStatus.MERGED: StatusMeta(Bucket.DONE, Tier.DONE, None),
    BoardStatus.DUP: StatusMeta(Bucket.DONE, Tier.DONE, None),
    BoardStatus.CLOSE: StatusMeta(Bucket.DONE, Tier.DONE, None),
    BoardStatus.ARCHIVED: StatusMeta(Bucket.ARCHIVED, Tier.DONE, None),
    BoardStatus.PENDING_TRIAGE: StatusMeta(
        Bucket.TARGET, Tier.ACT, "/maigo:triage-issue"
    ),
    BoardStatus.READY: StatusMeta(Bucket.TARGET, Tier.ACT, "/maigo:take-issue"),
    BoardStatus.IN_PROGRESS: StatusMeta(Bucket.TARGET, Tier.WIP, None),
    BoardStatus.NEW_REPLY: StatusMeta(Bucket.TARGET, Tier.ACT, "/maigo:triage-issue"),
    BoardStatus.NEEDS_INFO: StatusMeta(Bucket.WAITING, Tier.WAIT, None),
    BoardStatus.WIP: StatusMeta(Bucket.TARGET, Tier.WIP, None),
    BoardStatus.CONFLICT: StatusMeta(
        Bucket.TARGET, Tier.BLOCKED, "/maigo:address-comments"
    ),
    BoardStatus.CI_RED: StatusMeta(Bucket.TARGET, Tier.BLOCKED, None),
    BoardStatus.CHANGES_REQUESTED: StatusMeta(
        Bucket.TARGET, Tier.BLOCKED, "/maigo:address-comments"
    ),
    BoardStatus.NEW_COMMENT: StatusMeta(
        Bucket.TARGET, Tier.ACT, "/maigo:address-comments"
    ),
    BoardStatus.MERGEABLE: StatusMeta(Bucket.TARGET, Tier.ACT, None),
    BoardStatus.CI_PENDING: StatusMeta(Bucket.WAITING, Tier.WAIT, None),
    BoardStatus.AWAITING_REVIEW: StatusMeta(Bucket.WAITING, Tier.WAIT, None),
    BoardStatus.OTHERS_DRAFT: StatusMeta(Bucket.WAITING, Tier.WAIT, None),
    BoardStatus.PENDING_REVIEW: StatusMeta(Bucket.TARGET, Tier.ACT, "/maigo:review"),
    BoardStatus.BALL_BACK: StatusMeta(Bucket.TARGET, Tier.ACT, "/maigo:review"),
    BoardStatus.BLOCKED: StatusMeta(Bucket.WAITING, Tier.WAIT, None),
    BoardStatus.NEEDS_CHANGES: StatusMeta(Bucket.WAITING, Tier.WAIT, None),
    BoardStatus.APPROVE_WITH_NITS: StatusMeta(Bucket.WAITING, Tier.WAIT, None),
    BoardStatus.APPROVE: StatusMeta(Bucket.WAITING, Tier.WAIT, None),
}

assert set(_STATUS_META) == set(BoardStatus), "每個 BoardStatus 都必須有 tier/bucket"

_REVIEW_ACTIVE_VERDICTS = frozenset(
    {
        BoardStatus.BLOCKED,
        BoardStatus.NEEDS_CHANGES,
        BoardStatus.APPROVE_WITH_NITS,
        BoardStatus.APPROVE,
        BoardStatus.BALL_BACK,
    }
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
    # 👀 在審的 PR
    BoardStatus.OTHERS_DRAFT: frozenset(
        {
            BoardStatus.MERGED,
            BoardStatus.CLOSED,
            BoardStatus.OTHERS_DRAFT,
            BoardStatus.PENDING_REVIEW,
        }
    ),
    # PENDING_REVIEW / BALL_BACK / 四個 active verdict：author 隨時可能把 PR 改回
    # draft（GitHub 允許已審過的 PR 回到 draft），所以都要能轉去 OTHERS_DRAFT。
    BoardStatus.PENDING_REVIEW: frozenset(
        {
            BoardStatus.MERGED,
            BoardStatus.CLOSED,
            BoardStatus.PENDING_REVIEW,
            BoardStatus.OTHERS_DRAFT,
        }
    ),
    BoardStatus.BALL_BACK: frozenset(
        {
            BoardStatus.MERGED,
            BoardStatus.CLOSED,
            BoardStatus.BALL_BACK,
            BoardStatus.OTHERS_DRAFT,
        }
    ),
    BoardStatus.BLOCKED: frozenset(
        {
            BoardStatus.MERGED,
            BoardStatus.CLOSED,
            BoardStatus.BLOCKED,
            BoardStatus.BALL_BACK,
            BoardStatus.OTHERS_DRAFT,
        }
    ),
    BoardStatus.NEEDS_CHANGES: frozenset(
        {
            BoardStatus.MERGED,
            BoardStatus.CLOSED,
            BoardStatus.NEEDS_CHANGES,
            BoardStatus.BALL_BACK,
            BoardStatus.OTHERS_DRAFT,
        }
    ),
    BoardStatus.APPROVE_WITH_NITS: frozenset(
        {
            BoardStatus.MERGED,
            BoardStatus.CLOSED,
            BoardStatus.APPROVE_WITH_NITS,
            BoardStatus.BALL_BACK,
            BoardStatus.OTHERS_DRAFT,
        }
    ),
    BoardStatus.APPROVE: frozenset(
        {
            BoardStatus.MERGED,
            BoardStatus.CLOSED,
            BoardStatus.APPROVE,
            BoardStatus.BALL_BACK,
            BoardStatus.OTHERS_DRAFT,
        }
    ),
    # 終端狀態：無出邊（只能被 purge），自迴圈代表「刷新時原樣保留」
    BoardStatus.CLOSED: frozenset({BoardStatus.CLOSED}),
    BoardStatus.MERGED: frozenset({BoardStatus.MERGED}),
    BoardStatus.ARCHIVED: frozenset({BoardStatus.ARCHIVED}),
}

assert set(ALLOWED_TRANSITIONS) == set(BoardStatus) | {None}, (
    "ALLOWED_TRANSITIONS 必須涵蓋每個 BoardStatus 加上 None（剛加入、無 prior）"
)


@dataclass(frozen=True)
class ClassifyResult:
    bucket: Bucket
    status: BoardStatus
    tier: Tier
    next_action: str | None


def tier_for_status(status: str) -> Tier | None:
    """給 UI 用：已知狀態詞回其 tier，未知狀態詞回 `None`（呼叫端據此大聲失敗）。"""
    try:
        return _STATUS_META[BoardStatus(status)].tier
    except ValueError:
        return None


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
    gh_meta: dict, prior_status: BoardStatus | None, you: str
) -> BoardStatus:
    if gh_meta.get("state") == "MERGED" or gh_meta.get("mergedAt"):
        return BoardStatus.MERGED
    if gh_meta.get("state") == "CLOSED":
        return BoardStatus.CLOSED
    if gh_meta.get("isDraft"):
        return BoardStatus.OTHERS_DRAFT
    if prior_status not in _REVIEW_ACTIVE_VERDICTS:
        return BoardStatus.PENDING_REVIEW
    events = _activity_events(gh_meta)
    your_last = _last_timestamp_by(events, you)
    author_login = (gh_meta.get("author") or {}).get("login")
    if your_last is not None and _has_activity_after(events, author_login, your_last):
        return BoardStatus.BALL_BACK
    return prior_status


def classify(
    item_type: ItemType,
    gh_meta: dict,
    prior_status: BoardStatus | None,
    you: str = "",
) -> ClassifyResult:
    """純函式：`(item_type, gh_meta, prior_status, you) -> bucket/status/tier/next_action`。

    不做任何 I/O；「你 vs 別人最後活動」全部從 `gh_meta` 的 comments/reviews
    author+時間戳算出，不呼叫 `datetime.now()`（那是 `compute_badges()` 的事）。
    """
    if item_type is ItemType.ISSUE:
        status = _classify_issue(gh_meta, prior_status, you)
    elif item_type is ItemType.OWN_PR:
        status = _classify_own_pr(gh_meta, you)
    elif item_type is ItemType.REVIEW_PR:
        status = _classify_review_pr(gh_meta, prior_status, you)
    else:  # pragma: no cover - ItemType 是總函式，理論上不會落到這裡
        raise ValueError(f"unknown item_type: {item_type!r}")
    meta = _STATUS_META[status]
    return ClassifyResult(
        bucket=meta.bucket, status=status, tier=meta.tier, next_action=meta.next_action
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--you", default="", help="目前使用者的 GitHub login")
    parser.add_argument(
        "--stale-days", type=int, default=STALE_DAYS_DEFAULT, help="💤 badge 門檻天數"
    )
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
        result = classify(item_type, gh_meta, prior_status, args.you)
        badges = compute_badges(gh_meta, now, args.stale_days)
        results.append(
            {
                "bucket": result.bucket.value,
                "status": result.status.value,
                "tier": result.tier.value,
                "next_action": result.next_action,
                "badges": badges,
            }
        )

    json.dump(results, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
