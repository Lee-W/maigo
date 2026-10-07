"""Tests for scripts.board_state — the Work Board state machine's single source of truth."""

from __future__ import annotations

import io
import itertools
import json
import os
import time
from datetime import datetime, timezone

import pytest

from scripts import board_state as bs

YOU = "octocat"


def _classify(item_type, gh_meta, prior_status):
    return bs.classify(item_type, gh_meta, prior_status, you=YOU)


# ---------------------------------------------------------------------------
# 🐛 issue — table rows from skills/work-board/SKILL.md §2
# ---------------------------------------------------------------------------


class TestClassifyIssue:
    def test_closed_state_wins_regardless_of_prior(self):
        result = _classify(bs.ItemType.ISSUE, {"state": "CLOSED"}, bs.BoardStatus.READY)
        assert result.status is bs.BoardStatus.CLOSED
        assert result.section is bs.Section.DONE
        assert result.rank is bs.Rank.P9

    @pytest.mark.parametrize("verdict", [bs.BoardStatus.DUP, bs.BoardStatus.CLOSE])
    def test_dup_and_close_verdicts_are_sticky_terminal(self, verdict):
        result = _classify(bs.ItemType.ISSUE, {"state": "OPEN"}, verdict)
        assert result.status is verdict
        assert result.section is bs.Section.DONE
        assert result.rank is bs.Rank.P9

    def test_no_prior_verdict_falls_to_pending_triage(self):
        result = _classify(bs.ItemType.ISSUE, {"state": "OPEN"}, None)
        assert result.status is bs.BoardStatus.PENDING_TRIAGE
        assert result.section is bs.Section.NEXT
        assert result.rank is bs.Rank.P6
        assert result.next_action == "/maigo:triage-issue <n>"

    def test_ready_with_no_assignee_stays_ready(self):
        gh_meta = {"state": "OPEN", "assignees": []}
        result = _classify(bs.ItemType.ISSUE, gh_meta, bs.BoardStatus.READY)
        assert result.status is bs.BoardStatus.READY
        assert result.section is bs.Section.NEXT
        assert result.rank is bs.Rank.P7
        assert result.next_action == "/maigo:take-issue <n>"

    def test_ready_with_you_assigned_stays_ready(self):
        gh_meta = {"state": "OPEN", "assignees": [{"login": YOU}]}
        result = _classify(bs.ItemType.ISSUE, gh_meta, bs.BoardStatus.READY)
        assert result.status is bs.BoardStatus.READY

    def test_in_progress_is_sticky_and_p5_rank(self):
        gh_meta = {"state": "OPEN"}
        result = _classify(bs.ItemType.ISSUE, gh_meta, bs.BoardStatus.IN_PROGRESS)
        assert result.status is bs.BoardStatus.IN_PROGRESS
        assert result.section is bs.Section.NEXT
        assert result.rank is bs.Rank.P5

    def test_new_activity_after_your_last_comment_is_new_reply(self):
        gh_meta = {
            "state": "OPEN",
            "assignees": [],
            "author": {"login": "carol"},
            "createdAt": "2026-01-01T00:00:00Z",
            "comments": [
                {"author": {"login": YOU}, "createdAt": "2026-01-02T00:00:00Z"},
                {"author": {"login": "carol"}, "createdAt": "2026-01-03T00:00:00Z"},
            ],
        }
        result = _classify(bs.ItemType.ISSUE, gh_meta, bs.BoardStatus.NEEDS_INFO)
        assert result.status is bs.BoardStatus.NEW_REPLY
        assert result.section is bs.Section.NEXT
        assert result.rank is bs.Rank.P2
        assert result.next_action == "/maigo:triage-issue <n>"

    def test_needs_info_when_your_comment_has_no_reply(self):
        gh_meta = {
            "state": "OPEN",
            "assignees": [],
            "author": {"login": "carol"},
            "createdAt": "2026-01-01T00:00:00Z",
            "comments": [
                {"author": {"login": YOU}, "createdAt": "2026-01-02T00:00:00Z"},
            ],
        }
        result = _classify(bs.ItemType.ISSUE, gh_meta, bs.BoardStatus.NEW_REPLY)
        assert result.status is bs.BoardStatus.NEEDS_INFO
        assert result.section is bs.Section.WAITING
        assert result.rank is bs.Rank.P8


# ---------------------------------------------------------------------------
# 🔀 你的 PR — recomputed purely from gh_meta each refresh, prior_status ignored
# ---------------------------------------------------------------------------


class TestClassifyOwnPr:
    def test_merged_at_wins(self):
        result = _classify(
            bs.ItemType.OWN_PR, {"mergedAt": "2026-01-01T00:00:00Z"}, None
        )
        assert result.status is bs.BoardStatus.MERGED
        assert result.section is bs.Section.DONE
        assert result.rank is bs.Rank.P9

    def test_merged_state_wins(self):
        result = _classify(bs.ItemType.OWN_PR, {"state": "MERGED"}, None)
        assert result.status is bs.BoardStatus.MERGED

    def test_closed_state(self):
        result = _classify(bs.ItemType.OWN_PR, {"state": "CLOSED"}, None)
        assert result.status is bs.BoardStatus.CLOSED

    def test_draft_is_wip(self):
        gh_meta = {"state": "OPEN", "isDraft": True}
        result = _classify(bs.ItemType.OWN_PR, gh_meta, None)
        assert result.status is bs.BoardStatus.WIP
        assert result.section is bs.Section.NEXT
        assert result.rank is bs.Rank.P5

    def test_conflicting_mergeable_is_blocked(self):
        gh_meta = {"state": "OPEN", "isDraft": False, "mergeable": "CONFLICTING"}
        result = _classify(bs.ItemType.OWN_PR, gh_meta, None)
        assert result.status is bs.BoardStatus.CONFLICT
        assert result.section is bs.Section.NEXT
        assert result.rank is bs.Rank.P1
        assert result.next_action == "/maigo:address-comments"

    def test_unknown_mergeable_does_not_false_positive_conflict(self):
        gh_meta = {
            "state": "OPEN",
            "isDraft": False,
            "mergeable": "UNKNOWN",
            "statusCheckRollup": [{"conclusion": "FAILURE"}],
        }
        result = _classify(bs.ItemType.OWN_PR, gh_meta, None)
        assert result.status is bs.BoardStatus.CI_RED
        assert result.rank is bs.Rank.P1

    def test_changes_requested_is_blocked(self):
        gh_meta = {
            "state": "OPEN",
            "isDraft": False,
            "mergeable": "MERGEABLE",
            "statusCheckRollup": [],
            "reviewDecision": "CHANGES_REQUESTED",
        }
        result = _classify(bs.ItemType.OWN_PR, gh_meta, None)
        assert result.status is bs.BoardStatus.CHANGES_REQUESTED
        assert result.rank is bs.Rank.P1
        assert result.next_action == "/maigo:address-comments"

    def test_new_comment_after_your_last_activity(self):
        gh_meta = {
            "state": "OPEN",
            "isDraft": False,
            "mergeable": "MERGEABLE",
            "statusCheckRollup": [],
            "author": {"login": YOU},
            "createdAt": "2026-01-01T00:00:00Z",
            "comments": [
                {"author": {"login": "carol"}, "createdAt": "2026-01-02T00:00:00Z"}
            ],
        }
        result = _classify(bs.ItemType.OWN_PR, gh_meta, None)
        assert result.status is bs.BoardStatus.NEW_COMMENT
        assert result.section is bs.Section.NEXT
        assert result.rank is bs.Rank.P2
        assert result.next_action == "/maigo:address-comments"

    def test_approved_and_ci_green_is_mergeable(self):
        gh_meta = {
            "state": "OPEN",
            "isDraft": False,
            "mergeable": "MERGEABLE",
            "statusCheckRollup": [{"conclusion": "SUCCESS"}],
            "reviewDecision": "APPROVED",
            "author": {"login": YOU},
            "createdAt": "2026-01-01T00:00:00Z",
        }
        result = _classify(bs.ItemType.OWN_PR, gh_meta, None)
        assert result.status is bs.BoardStatus.MERGEABLE
        assert result.section is bs.Section.NEXT
        assert result.rank is bs.Rank.P3

    def test_ci_pending(self):
        gh_meta = {
            "state": "OPEN",
            "isDraft": False,
            "mergeable": "MERGEABLE",
            "statusCheckRollup": [{"status": "IN_PROGRESS"}],
            "author": {"login": YOU},
            "createdAt": "2026-01-01T00:00:00Z",
        }
        result = _classify(bs.ItemType.OWN_PR, gh_meta, None)
        assert result.status is bs.BoardStatus.CI_PENDING
        assert result.section is bs.Section.WAITING
        assert result.rank is bs.Rank.P8

    def test_default_is_awaiting_review(self):
        gh_meta = {
            "state": "OPEN",
            "isDraft": False,
            "mergeable": "MERGEABLE",
            "statusCheckRollup": [],
            "author": {"login": YOU},
            "createdAt": "2026-01-01T00:00:00Z",
        }
        result = _classify(bs.ItemType.OWN_PR, gh_meta, None)
        assert result.status is bs.BoardStatus.AWAITING_REVIEW
        assert result.section is bs.Section.WAITING
        assert result.rank is bs.Rank.P8


# ---------------------------------------------------------------------------
# 👀 在審的 PR — rebuilt table
# ---------------------------------------------------------------------------


class TestClassifyReviewPr:
    def test_merged(self):
        result = _classify(
            bs.ItemType.REVIEW_PR, {"mergedAt": "2026-01-01T00:00:00Z"}, None
        )
        assert result.status is bs.BoardStatus.MERGED

    def test_closed(self):
        result = _classify(bs.ItemType.REVIEW_PR, {"state": "CLOSED"}, None)
        assert result.status is bs.BoardStatus.CLOSED

    def test_others_draft_is_waiting(self):
        gh_meta = {"state": "OPEN", "isDraft": True}
        result = _classify(bs.ItemType.REVIEW_PR, gh_meta, None)
        assert result.status is bs.BoardStatus.OTHERS_DRAFT
        assert result.section is bs.Section.WAITING
        assert result.rank is bs.Rank.P8

    def test_never_reviewed_is_pending_review(self):
        gh_meta = {
            "state": "OPEN",
            "isDraft": False,
            "author": {"login": "carol"},
            "createdAt": "2026-01-01T00:00:00Z",
            "reviews": [],
            "comments": [],
        }
        result = _classify(bs.ItemType.REVIEW_PR, gh_meta, None)
        assert result.status is bs.BoardStatus.PENDING_REVIEW
        assert result.section is bs.Section.NEXT
        assert result.rank is bs.Rank.P4
        assert result.next_action == "/maigo:review <n>"

    def test_author_activity_after_your_review_is_ball_back(self):
        gh_meta = {
            "state": "OPEN",
            "isDraft": False,
            "author": {"login": "carol"},
            "createdAt": "2026-01-01T00:00:00Z",
            "reviews": [
                {"author": {"login": YOU}, "submittedAt": "2026-01-02T00:00:00Z"}
            ],
            "comments": [
                {"author": {"login": "carol"}, "createdAt": "2026-01-03T00:00:00Z"}
            ],
        }
        result = _classify(bs.ItemType.REVIEW_PR, gh_meta, bs.BoardStatus.BLOCKED)
        assert result.status is bs.BoardStatus.BALL_BACK
        assert result.section is bs.Section.NEXT
        assert result.rank is bs.Rank.P2
        assert result.next_action == "/maigo:review <n>"

    @pytest.mark.parametrize(
        "verdict",
        [
            bs.BoardStatus.BLOCKED,
            bs.BoardStatus.NEEDS_CHANGES,
            bs.BoardStatus.APPROVE_WITH_NITS,
            bs.BoardStatus.APPROVE,
        ],
    )
    def test_verdict_retained_when_no_new_author_activity(self, verdict):
        gh_meta = {
            "state": "OPEN",
            "isDraft": False,
            "author": {"login": "carol"},
            "createdAt": "2026-01-01T00:00:00Z",
            "reviews": [
                {"author": {"login": YOU}, "submittedAt": "2026-01-02T00:00:00Z"}
            ],
            "comments": [],
        }
        result = _classify(bs.ItemType.REVIEW_PR, gh_meta, verdict)
        assert result.status is verdict
        assert result.section is bs.Section.WAITING
        assert result.rank is bs.Rank.P8

    def test_unposted_verdict_when_review_not_posted(self):
        """Prior 是 active verdict，但 `reviews` 裡沒有你貼出的項目 → 待送出（P3）。"""
        gh_meta = {
            "state": "OPEN",
            "isDraft": False,
            "author": {"login": "carol"},
            "createdAt": "2026-01-01T00:00:00Z",
            "reviews": [],
            "comments": [],
        }
        result = _classify(bs.ItemType.REVIEW_PR, gh_meta, bs.BoardStatus.APPROVE)
        assert result.status is bs.BoardStatus.UNPOSTED_VERDICT
        assert result.section is bs.Section.NEXT
        assert result.rank is bs.Rank.P3
        assert (
            result.next_action
            == "gh pr review <n> --comment --body-file <review-draft>"
        )

    def test_unposted_verdict_not_triggered_when_review_already_posted(self):
        """反向 case：`reviews` 裡已有你貼出的項目 → 不判 待送出，維持原 verdict。"""
        gh_meta = {
            "state": "OPEN",
            "isDraft": False,
            "author": {"login": "carol"},
            "createdAt": "2026-01-01T00:00:00Z",
            "reviews": [
                {"author": {"login": YOU}, "submittedAt": "2026-01-02T00:00:00Z"}
            ],
            "comments": [],
        }
        result = _classify(bs.ItemType.REVIEW_PR, gh_meta, bs.BoardStatus.APPROVE)
        assert result.status is bs.BoardStatus.APPROVE


class TestClassifyReviewPrLocalVerdictAt:
    """
    `local_verdict_at`（本地 review 報告產生時間）用來區分「這次本地審完還沒貼」
    與「幾個月前貼過舊 review、現在該重審」——2026-09-29 board 誤判實例：舊
    review 蓋掉了「待送出」訊號。
    """

    def test_stale_review_before_local_verdict_is_unposted(self):
        """(a) 你送過的唯一一筆 review 早於這次本地 verdict 產生時間 → 待送出。"""
        gh_meta = {
            "state": "OPEN",
            "isDraft": False,
            "author": {"login": "carol"},
            "createdAt": "2026-01-01T00:00:00Z",
            "reviews": [
                {"author": {"login": YOU}, "submittedAt": "2026-01-02T00:00:00Z"}
            ],
            "comments": [],
        }
        result = bs.classify(
            bs.ItemType.REVIEW_PR,
            gh_meta,
            bs.BoardStatus.APPROVE,
            you=YOU,
            local_verdict_at="2026-09-29T00:00:00Z",
        )
        assert result.status is bs.BoardStatus.UNPOSTED_VERDICT
        assert result.section is bs.Section.NEXT
        assert result.rank is bs.Rank.P3

    def test_review_after_local_verdict_with_no_author_activity_keeps_verdict(self):
        """(b) review 晚於本地 verdict 產生時間，作者之後無活動 → 保留原 verdict。"""
        gh_meta = {
            "state": "OPEN",
            "isDraft": False,
            "author": {"login": "carol"},
            "createdAt": "2026-01-01T00:00:00Z",
            "reviews": [
                {"author": {"login": YOU}, "submittedAt": "2026-09-29T12:00:00Z"}
            ],
            "comments": [],
        }
        result = bs.classify(
            bs.ItemType.REVIEW_PR,
            gh_meta,
            bs.BoardStatus.APPROVE,
            you=YOU,
            local_verdict_at="2026-09-29T00:00:00Z",
        )
        assert result.status is bs.BoardStatus.APPROVE
        assert result.section is bs.Section.WAITING
        assert result.rank is bs.Rank.P8

    def test_review_after_local_verdict_with_author_activity_is_ball_back(self):
        """(c) review 晚於本地 verdict 產生時間，且之後作者有新活動 → 回你的球。"""
        gh_meta = {
            "state": "OPEN",
            "isDraft": False,
            "author": {"login": "carol"},
            "createdAt": "2026-01-01T00:00:00Z",
            "reviews": [
                {"author": {"login": YOU}, "submittedAt": "2026-09-29T12:00:00Z"}
            ],
            "comments": [
                {"author": {"login": "carol"}, "createdAt": "2026-09-29T13:00:00Z"}
            ],
        }
        result = bs.classify(
            bs.ItemType.REVIEW_PR,
            gh_meta,
            bs.BoardStatus.APPROVE,
            you=YOU,
            local_verdict_at="2026-09-29T00:00:00Z",
        )
        assert result.status is bs.BoardStatus.BALL_BACK
        assert result.section is bs.Section.NEXT
        assert result.rank is bs.Rank.P2

    def test_missing_local_verdict_at_keeps_legacy_behavior(self):
        """(d) 欄位缺席（`None`）→ 行為與現行一致：任一貼過的 review 都算已送出。"""
        gh_meta = {
            "state": "OPEN",
            "isDraft": False,
            "author": {"login": "carol"},
            "createdAt": "2026-01-01T00:00:00Z",
            "reviews": [
                {"author": {"login": YOU}, "submittedAt": "2026-01-02T00:00:00Z"}
            ],
            "comments": [],
        }
        result = bs.classify(
            bs.ItemType.REVIEW_PR,
            gh_meta,
            bs.BoardStatus.APPROVE,
            you=YOU,
            local_verdict_at=None,
        )
        assert result.status is bs.BoardStatus.APPROVE


# ---------------------------------------------------------------------------
# Transition property test: classify() 輸出必須 ∈ ALLOWED_TRANSITIONS[prior]
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "change,expected",
    [
        ({}, bs.BoardStatus.REVIEWED),
        ({"headRefOid": "new-head"}, bs.BoardStatus.BALL_BACK),
        (
            {
                "comments": [
                    {"author": {"login": "carol"}, "createdAt": "2026-01-04T00:00:00Z"}
                ]
            },
            bs.BoardStatus.BALL_BACK,
        ),
        (
            {"commits": [{"committedDate": "2026-01-04T00:00:00Z"}]},
            bs.BoardStatus.BALL_BACK,
        ),
        (
            {
                "comments": [
                    {"author": {"login": YOU}, "createdAt": "2026-01-04T00:00:00Z"}
                ]
            },
            bs.BoardStatus.REVIEWED,
        ),
        ({"isDraft": True}, bs.BoardStatus.OTHERS_DRAFT),
        ({"state": "CLOSED"}, bs.BoardStatus.CLOSED),
        ({"state": "MERGED"}, bs.BoardStatus.MERGED),
    ],
)
def test_local_read_marker_waits_until_new_author_activity(change, expected):
    gh_meta = {
        "state": "OPEN",
        "headRefOid": "same-head",
        "author": {"login": "carol"},
        **change,
    }
    review = {
        "reviewed_at": "2026-01-02T00:00:00Z",
        "head_sha": "same-head",
        "acknowledged_at": "2026-01-03T00:00:00Z",
        "acknowledged_by": YOU,
    }
    result = bs.classify(
        bs.ItemType.REVIEW_PR, gh_meta, bs.BoardStatus.REVIEWED, YOU, review=review
    )
    assert result.status is expected


def test_someone_elses_acknowledgement_does_not_complete_your_review():
    review = {
        "reviewed_at": "2026-01-02T00:00:00Z",
        "acknowledged_at": "2026-01-03T00:00:00Z",
        "acknowledged_by": "someone-else",
    }
    result = bs.classify(
        bs.ItemType.REVIEW_PR, {"state": "OPEN"}, None, YOU, review=review
    )
    assert result.status is bs.BoardStatus.UNPOSTED_VERDICT


@pytest.mark.parametrize(
    "prior", [bs.BoardStatus.UNPOSTED_VERDICT, bs.BoardStatus.BALL_BACK, None]
)
def test_submitted_review_no_longer_sticks_in_action_queue(prior):
    gh_meta = {
        "reviews": [
            {
                "author": {"login": YOU},
                "state": "APPROVED",
                "submittedAt": "2026-01-03T00:00:00Z",
            }
        ]
    }
    result = bs.classify(bs.ItemType.REVIEW_PR, gh_meta, prior, YOU)
    assert result.section is bs.Section.WAITING


@pytest.mark.parametrize("state", ["PENDING", "DISMISSED"])
def test_unsubmitted_or_dismissed_review_does_not_count_as_posted(state):
    gh_meta = {
        "reviews": [
            {
                "author": {"login": YOU},
                "state": state,
                "submittedAt": "2026-01-03T00:00:00Z",
            }
        ]
    }
    result = bs.classify(bs.ItemType.REVIEW_PR, gh_meta, bs.BoardStatus.APPROVE, YOU)
    assert result.status is bs.BoardStatus.UNPOSTED_VERDICT


def test_review_view_filters_and_orders_mixed_board_without_losing_metadata(
    monkeypatch, capsys
):
    items = [
        {
            "type": "👀",
            "gh_meta": {"title": "First review", "author": {"login": "alice"}},
        },
        {"type": "🔀", "gh_meta": {"title": "My PR", "isDraft": True}},
        {"type": "👀", "gh_meta": {"title": "Closed", "state": "CLOSED"}},
        {"type": "👀", "gh_meta": {"title": "Draft", "isDraft": True}},
        {
            "type": "👀",
            "gh_meta": {"title": "Report ready"},
            "review": {"reviewed_at": "2026-01-01T00:00:00Z"},
        },
        {
            "type": "👀",
            "gh_meta": {"title": "New push", "headRefOid": "new"},
            "review": {"head_sha": "old"},
        },
    ]
    payload = json.dumps(items)
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    assert bs.main(["--you", YOU, "--reviews"]) == 0
    filtered = json.loads(capsys.readouterr().out)
    assert [row["title"] for row in filtered] == [
        "New push",
        "Report ready",
        "First review",
    ]
    assert filtered[1]["last_reviewed_at"] == "2026-01-01T00:00:00Z"
    assert filtered[1]["review_time_source"] == "report"
    assert filtered[2]["author"] == "alice"
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    assert bs.main(["--you", YOU]) == 0
    assert len(json.loads(capsys.readouterr().out)) == len(items)


_ISSUE_GH_META_SCENARIOS = [
    {"state": "CLOSED"},
    {"state": "OPEN", "assignees": []},
    {"state": "OPEN", "assignees": [{"login": YOU}]},
    {"state": "OPEN", "assignees": [{"login": "dave"}]},
    {
        "state": "OPEN",
        "assignees": [],
        "author": {"login": "carol"},
        "createdAt": "2026-01-01T00:00:00Z",
        "comments": [
            {"author": {"login": YOU}, "createdAt": "2026-01-02T00:00:00Z"},
            {"author": {"login": "carol"}, "createdAt": "2026-01-03T00:00:00Z"},
        ],
    },
    {
        "state": "OPEN",
        "assignees": [],
        "author": {"login": "carol"},
        "createdAt": "2026-01-01T00:00:00Z",
        "comments": [
            {"author": {"login": YOU}, "createdAt": "2026-01-02T00:00:00Z"},
        ],
    },
]
_ISSUE_PRIOR_CANDIDATES = [
    None,
    bs.BoardStatus.PENDING_TRIAGE,
    bs.BoardStatus.READY,
    bs.BoardStatus.IN_PROGRESS,
    bs.BoardStatus.NEEDS_INFO,
    bs.BoardStatus.NEW_REPLY,
    bs.BoardStatus.DUP,
    bs.BoardStatus.CLOSE,
    bs.BoardStatus.UNREACHABLE,
]

_OWN_PR_GH_META_SCENARIOS = [
    {"mergedAt": "2026-01-01T00:00:00Z"},
    {"state": "CLOSED"},
    {"state": "OPEN", "isDraft": True},
    {"state": "OPEN", "isDraft": False, "mergeable": "CONFLICTING"},
    {
        "state": "OPEN",
        "isDraft": False,
        "mergeable": "MERGEABLE",
        "statusCheckRollup": [{"conclusion": "FAILURE"}],
    },
    {
        "state": "OPEN",
        "isDraft": False,
        "mergeable": "MERGEABLE",
        "statusCheckRollup": [],
        "reviewDecision": "CHANGES_REQUESTED",
    },
    {
        "state": "OPEN",
        "isDraft": False,
        "mergeable": "MERGEABLE",
        "statusCheckRollup": [],
        "author": {"login": YOU},
        "createdAt": "2026-01-01T00:00:00Z",
        "comments": [
            {"author": {"login": "carol"}, "createdAt": "2026-01-02T00:00:00Z"}
        ],
    },
    {
        "state": "OPEN",
        "isDraft": False,
        "mergeable": "MERGEABLE",
        "statusCheckRollup": [{"conclusion": "SUCCESS"}],
        "reviewDecision": "APPROVED",
        "author": {"login": YOU},
        "createdAt": "2026-01-01T00:00:00Z",
    },
    {
        "state": "OPEN",
        "isDraft": False,
        "mergeable": "MERGEABLE",
        "statusCheckRollup": [{"status": "PENDING"}],
        "author": {"login": YOU},
        "createdAt": "2026-01-01T00:00:00Z",
    },
    {
        "state": "OPEN",
        "isDraft": False,
        "mergeable": "MERGEABLE",
        "statusCheckRollup": [],
        "author": {"login": YOU},
        "createdAt": "2026-01-01T00:00:00Z",
    },
]
_OWN_PR_PRIOR_CANDIDATES = [
    None,
    bs.BoardStatus.WIP,
    bs.BoardStatus.CONFLICT,
    bs.BoardStatus.CI_RED,
    bs.BoardStatus.CHANGES_REQUESTED,
    bs.BoardStatus.NEW_COMMENT,
    bs.BoardStatus.MERGEABLE,
    bs.BoardStatus.CI_PENDING,
    bs.BoardStatus.AWAITING_REVIEW,
    bs.BoardStatus.UNREACHABLE,
]

_REVIEW_PR_GH_META_SCENARIOS = [
    {"mergedAt": "2026-01-01T00:00:00Z"},
    {"state": "CLOSED"},
    {"state": "OPEN", "isDraft": True},
    {
        "state": "OPEN",
        "isDraft": False,
        "author": {"login": "carol"},
        "createdAt": "2026-01-01T00:00:00Z",
        "reviews": [],
        "comments": [],
    },
    {
        "state": "OPEN",
        "isDraft": False,
        "author": {"login": "carol"},
        "createdAt": "2026-01-01T00:00:00Z",
        "reviews": [{"author": {"login": YOU}, "submittedAt": "2026-01-02T00:00:00Z"}],
        "comments": [
            {"author": {"login": "carol"}, "createdAt": "2026-01-03T00:00:00Z"}
        ],
    },
    {
        "state": "OPEN",
        "isDraft": False,
        "author": {"login": "carol"},
        "createdAt": "2026-01-01T00:00:00Z",
        "reviews": [{"author": {"login": YOU}, "submittedAt": "2026-01-02T00:00:00Z"}],
        "comments": [],
    },
]
_REVIEW_PR_PRIOR_CANDIDATES = [
    None,
    bs.BoardStatus.PENDING_REVIEW,
    bs.BoardStatus.BALL_BACK,
    bs.BoardStatus.BLOCKED,
    bs.BoardStatus.NEEDS_CHANGES,
    bs.BoardStatus.APPROVE_WITH_NITS,
    bs.BoardStatus.APPROVE,
    bs.BoardStatus.UNREACHABLE,
    bs.BoardStatus.UNPOSTED_VERDICT,
    bs.BoardStatus.REVIEWED,
]

_TYPE_FIXTURES = [
    (bs.ItemType.ISSUE, _ISSUE_PRIOR_CANDIDATES, _ISSUE_GH_META_SCENARIOS),
    (bs.ItemType.OWN_PR, _OWN_PR_PRIOR_CANDIDATES, _OWN_PR_GH_META_SCENARIOS),
    (bs.ItemType.REVIEW_PR, _REVIEW_PR_PRIOR_CANDIDATES, _REVIEW_PR_GH_META_SCENARIOS),
]


class TestAllowedTransitionsProperty:
    @pytest.mark.parametrize(
        "item_type,prior,gh_meta",
        [
            (item_type, prior, gh_meta)
            for item_type, priors, scenarios in _TYPE_FIXTURES
            for prior, gh_meta in itertools.product(priors, scenarios)
        ],
    )
    def test_classify_output_is_within_allowed_transitions(
        self, item_type, prior, gh_meta
    ):
        """
        `classify()` 的輸出必須 ∈ `ALLOWED_TRANSITIONS[prior]`。

        本測試曾抓到 `ALLOWED_TRANSITIONS` 的兩個真實缺口——`NEW_REPLY` 缺
        `NEEDS_INFO` 出邊、review 的 active verdict priors 缺 `OTHERS_DRAFT`
        出邊（author 把已審過的 PR 改回 draft）——已在 `scripts/board_state.py`
        補上宣告，不是靠放寬這裡的斷言過關。
        """
        result = _classify(item_type, gh_meta, prior)
        allowed = bs.ALLOWED_TRANSITIONS[prior]
        assert result.status in allowed, (
            f"{item_type!r} prior={prior!r} gh_meta={gh_meta!r} "
            f"produced {result.status!r}, not in {allowed!r}"
        )


# ---------------------------------------------------------------------------
# rank / section totality
# ---------------------------------------------------------------------------


class TestRankTotality:
    def test_every_board_status_has_a_rank(self):
        for status in bs.BoardStatus:
            assert status in bs._STATUS_META
            assert isinstance(bs._STATUS_META[status].rank, bs.Rank)

    def test_section_for_rank_is_total(self):
        for rank in bs.Rank:
            assert bs._section_for_rank(rank) in set(bs.Section)


class TestNextActionForStatus:
    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            # P9：結案，全部無 next_action
            pytest.param("closed", None, id="closed"),
            pytest.param("merged", None, id="merged"),
            pytest.param("DUP", None, id="dup"),
            pytest.param("CLOSE", None, id="close"),
            pytest.param("已放棄", None, id="archived"),
            # P0：抓不到
            pytest.param("抓不到", None, id="unreachable"),
            # P6：沒判過
            pytest.param("待 triage", "/maigo:triage-issue <n>", id="pending-triage"),
            # P7：可以開工
            pytest.param("READY", "/maigo:take-issue <n>", id="ready"),
            # P5：手上正在做
            pytest.param("IN_PROGRESS", None, id="in-progress"),
            pytest.param("WIP", None, id="wip"),
            # P2：球被打回
            pytest.param("有新回覆", "/maigo:triage-issue <n>", id="new-reply"),
            pytest.param("有新 comment", "/maigo:address-comments", id="new-comment"),
            pytest.param("↩︎ 回你的球", "/maigo:review <n>", id="ball-back"),
            # P8：等別人
            pytest.param("NEEDS_INFO", None, id="needs-info"),
            pytest.param("CI 等待", None, id="ci-pending"),
            pytest.param("等 review", None, id="awaiting-review"),
            pytest.param("他人草稿", None, id="others-draft"),
            pytest.param("BLOCKED", None, id="blocked"),
            pytest.param("NEEDS_CHANGES", None, id="needs-changes"),
            pytest.param("APPROVE_WITH_NITS", None, id="approve-with-nits"),
            pytest.param("APPROVE", None, id="approve"),
            # P1：卡住的
            pytest.param("有衝突", "/maigo:address-comments", id="conflict"),
            pytest.param("CI 紅", "gh pr checks <n>", id="ci-red"),
            pytest.param(
                "CHANGES_REQUESTED",
                "/maigo:address-comments",
                id="changes-requested",
            ),
            # P3：一步就結束
            pytest.param("可合併", "gh pr merge <n>", id="mergeable"),
            pytest.param(
                "待送出",
                "gh pr review <n> --comment --body-file <review-draft>",
                id="unposted-verdict",
            ),
            # P4：等你審
            pytest.param("待 review", "/maigo:review <n>", id="pending-review"),
            # 未知狀態詞
            pytest.param("這不是一個合法狀態詞", None, id="unknown"),
        ],
    )
    def test_returns_action_for_status(self, status, expected):
        assert bs.next_action_for_status(status) == expected

    def test_allowed_transitions_covers_every_status_and_none(self):
        assert set(bs.ALLOWED_TRANSITIONS) == set(bs.BoardStatus) | {None}

    def test_terminal_states_have_no_outbound_edges_besides_self(self):
        for status in (
            bs.BoardStatus.CLOSED,
            bs.BoardStatus.MERGED,
            bs.BoardStatus.ARCHIVED,
        ):
            assert bs.ALLOWED_TRANSITIONS[status] == frozenset({status})


# ---------------------------------------------------------------------------
# detail_path()
# ---------------------------------------------------------------------------


class TestDetailPath:
    def test_same_repo_pr_url_uses_bare_number(self):
        result = bs.detail_path(
            "https://github.com/Lee-W/maigo/pull/9201", home_repo="Lee-W/maigo"
        )
        assert result == "i/9201.md"

    def test_cross_repo_pr_url_prefixes_repo_name(self):
        result = bs.detail_path(
            "https://github.com/other-owner/other-repo/pull/42",
            home_repo="Lee-W/maigo",
        )
        assert result == "i/other-repo-42.md"

    def test_issues_url_is_recognized(self):
        result = bs.detail_path(
            "https://github.com/Lee-W/maigo/issues/9101", home_repo="Lee-W/maigo"
        )
        assert result == "i/9101.md"

    def test_no_home_repo_treats_everything_as_cross_repo(self):
        result = bs.detail_path("https://github.com/Lee-W/maigo/pull/9201")
        assert result == "i/maigo-9201.md"

    @pytest.mark.parametrize(
        "url",
        [
            "",
            "not a url",
            "https://example.com/Lee-W/maigo/pull/9201",
            "https://github.com/Lee-W/maigo",
            "https://github.com/Lee-W/maigo/commits/9201",
            "https://github.com/Lee-W/maigo/pull/not-a-number",
        ],
    )
    def test_unparseable_url_returns_none(self, url):
        assert bs.detail_path(url, home_repo="Lee-W/maigo") is None


# ---------------------------------------------------------------------------
# compute_badges()
# ---------------------------------------------------------------------------


class TestComputeBadges:
    def test_stale_badge_after_threshold(self):
        now = datetime(2026, 7, 17, tzinfo=timezone.utc)
        gh_meta = {"updatedAt": "2026-06-01T00:00:00Z"}
        assert bs.compute_badges(gh_meta, now) == ["💤"]

    def test_no_stale_badge_within_threshold(self):
        now = datetime(2026, 7, 17, tzinfo=timezone.utc)
        gh_meta = {"updatedAt": "2026-07-16T00:00:00Z"}
        assert bs.compute_badges(gh_meta, now) == []

    def test_custom_stale_days(self):
        now = datetime(2026, 7, 17, tzinfo=timezone.utc)
        gh_meta = {"updatedAt": "2026-07-10T00:00:00Z"}
        assert bs.compute_badges(gh_meta, now, stale_days=5) == ["💤"]
        assert bs.compute_badges(gh_meta, now, stale_days=14) == []

    def test_missing_updated_at_is_not_stale(self):
        now = datetime(2026, 7, 17, tzinfo=timezone.utc)
        assert bs.compute_badges({}, now) == []


# ---------------------------------------------------------------------------
# CLI (`main()`)
# ---------------------------------------------------------------------------


class TestMain:
    def test_round_trips_a_single_issue(self, monkeypatch, capsys):
        stdin_payload = json.dumps(
            [{"type": "🐛", "gh_meta": {"state": "OPEN"}, "prior_status": None}]
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_payload))

        exit_code = bs.main(["--you", YOU])

        assert exit_code == 0
        out = json.loads(capsys.readouterr().out)
        assert out == [
            {
                "section": "🎯",
                "rank": 6,
                "status": "待 triage",
                "next_action": "/maigo:triage-issue <n>",
                "badges": [],
                "detail_path": None,
                "title": "",
                "author": "",
                "last_reviewed_at": None,
                "review_time_source": None,
                "acknowledged_at": None,
                "needs_review": False,
                "index_entry": "🐛 待 triage —",
            }
        ]

    def test_unknown_prior_status_normalizes_to_none(self, monkeypatch, capsys):
        stdin_payload = json.dumps(
            [
                {
                    "type": "🐛",
                    "gh_meta": {"state": "OPEN"},
                    "prior_status": "某個舊工具寫的殘留字",
                }
            ]
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_payload))

        exit_code = bs.main(["--you", YOU])

        assert exit_code == 0
        out = json.loads(capsys.readouterr().out)
        assert out[0]["status"] == "待 triage"

    def test_invalid_json_exits_1(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.stdin", io.StringIO("not json"))

        assert bs.main([]) == 1
        assert "JSON" in capsys.readouterr().err

    def test_non_list_json_exits_1(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"a": 1})))

        assert bs.main([]) == 1
        assert "陣列" in capsys.readouterr().err

    def test_invalid_type_field_exits_1(self, monkeypatch, capsys):
        stdin_payload = json.dumps(
            [{"type": "❓", "gh_meta": {}, "prior_status": None}]
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_payload))

        assert bs.main([]) == 1
        assert "type" in capsys.readouterr().err

    def test_empty_stdin_returns_empty_array(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.stdin", io.StringIO(""))

        assert bs.main([]) == 0
        assert json.loads(capsys.readouterr().out) == []

    @staticmethod
    def _unposted_verdict_item(url):
        return {
            "type": "👀",
            "gh_meta": {
                "state": "OPEN",
                "isDraft": False,
                "author": {"login": "carol"},
                "createdAt": "2026-01-01T00:00:00Z",
                "reviews": [],
                "comments": [],
            },
            "prior_status": "APPROVE",
            "url": url,
        }

    def test_unposted_verdict_same_repo_fills_review_draft_path(
        self, monkeypatch, capsys
    ):
        # canary C 的紅燈斷言：`main()` 拿掉佔位字替換必須紅在這裡。
        stdin_payload = json.dumps(
            [
                self._unposted_verdict_item(
                    "https://github.com/apache/airflow/pull/58543"
                )
            ]
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_payload))

        exit_code = bs.main(["--you", YOU, "--repo", "apache/airflow"])

        assert exit_code == 0
        out = json.loads(capsys.readouterr().out)
        assert out[0]["status"] == "待送出"
        assert out[0]["next_action"] == (
            "gh pr review <n> --comment --body-file .maigo/review/58543/draft.md"
        )

    def test_unposted_verdict_cross_repo_prefixes_repo_name(self, monkeypatch, capsys):
        stdin_payload = json.dumps(
            [
                self._unposted_verdict_item(
                    "https://github.com/apache/airflow/pull/58543"
                )
            ]
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_payload))

        exit_code = bs.main(["--you", YOU])

        assert exit_code == 0
        out = json.loads(capsys.readouterr().out)
        assert out[0]["next_action"] == (
            "gh pr review <n> --comment --body-file .maigo/review/airflow-58543/draft.md"
        )

    def test_unposted_verdict_without_url_keeps_placeholder(self, monkeypatch, capsys):
        stdin_payload = json.dumps([self._unposted_verdict_item(None)])
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_payload))

        exit_code = bs.main(["--you", YOU])

        assert exit_code == 0
        out = json.loads(capsys.readouterr().out)
        assert out[0]["next_action"] == (
            "gh pr review <n> --comment --body-file <review-draft>"
        )

    def _run_with_root(self, monkeypatch, capsys, root):
        stdin_payload = json.dumps(
            [
                self._unposted_verdict_item(
                    "https://github.com/apache/airflow/pull/58543"
                )
            ]
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin_payload))
        args = ["--you", YOU, "--repo", "apache/airflow", "--maigo-root", str(root)]
        assert bs.main(args) == 0
        out = json.loads(capsys.readouterr().out)
        assert out[0]["status"] == "待送出"
        return out[0]["next_action"]

    def test_unposted_verdict_with_existing_draft_gives_gh_command(
        self, monkeypatch, capsys, tmp_path
    ):
        draft = tmp_path / ".maigo" / "review" / "58543" / "draft.md"
        draft.parent.mkdir(parents=True)
        draft.write_text("body\n")
        assert self._run_with_root(monkeypatch, capsys, tmp_path) == (
            "gh pr review <n> --comment --body-file .maigo/review/58543/draft.md"
        )

    def test_unposted_verdict_without_draft_asks_to_draft_first(
        self, monkeypatch, capsys, tmp_path
    ):
        assert self._run_with_root(monkeypatch, capsys, tmp_path) == (
            "尚無草稿：先起草 `.maigo/review/58543/draft.md`（`/maigo:review` §4.5 裁決 gate）"
        )


# ---------------------------------------------------------------------------
# `--maigo-root` 自動算 local_verdict_at（end-to-end，走 main()/CLI）
# ---------------------------------------------------------------------------


class TestMainAutoLocalVerdictAt:
    @staticmethod
    def _stdin_item(url, submitted_at, prior_status="APPROVE", extra_comments=None):
        return {
            "type": "👀",
            "gh_meta": {
                "state": "OPEN",
                "isDraft": False,
                "author": {"login": "carol"},
                "createdAt": "2026-01-01T00:00:00Z",
                "reviews": [{"author": {"login": YOU}, "submittedAt": submitted_at}],
                "comments": extra_comments or [],
            },
            "prior_status": prior_status,
            "url": url,
        }

    def _write_review_with_mtime(self, root, ref, epoch_seconds):
        review_path = root / ".maigo" / "review" / ref / "review.md"
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.write_text("# review\n", encoding="utf-8")
        os.utime(review_path, (epoch_seconds, epoch_seconds))
        return review_path

    def test_same_repo_auto_detects_stale_review_as_unposted(
        self, tmp_path, monkeypatch, capsys
    ):
        """(i) 同 repo：review.md mtime 晚於你送出的唯一一筆 review → 待送出。"""
        mtime_epoch = datetime(2026, 9, 29, 0, 0, 0, tzinfo=timezone.utc).timestamp()
        self._write_review_with_mtime(tmp_path, "58543", mtime_epoch)

        item = self._stdin_item(
            "https://github.com/apache/airflow/pull/58543",
            submitted_at="2026-01-02T00:00:00Z",  # 遠早於 review.md mtime
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps([item])))

        exit_code = bs.main(
            [
                "--you",
                YOU,
                "--repo",
                "apache/airflow",
                "--maigo-root",
                str(tmp_path),
            ]
        )

        assert exit_code == 0
        out = json.loads(capsys.readouterr().out)
        assert out[0]["status"] == "待送出"

    def test_cross_repo_auto_detects_review_under_prefixed_dir(
        self, tmp_path, monkeypatch, capsys
    ):
        """(ii) 跨 repo：`<id>` 是 `<repo>-<n>`，review.md 要放在對應的前綴目錄。"""
        mtime_epoch = datetime(2026, 9, 29, 0, 0, 0, tzinfo=timezone.utc).timestamp()
        self._write_review_with_mtime(tmp_path, "airflow-58543", mtime_epoch)

        item = self._stdin_item(
            "https://github.com/apache/airflow/pull/58543",
            submitted_at="2026-01-02T00:00:00Z",
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps([item])))

        # 沒帶 --repo（或帶不同 repo）→ 跨 repo，<id> 應為 airflow-58543
        exit_code = bs.main(["--you", YOU, "--maigo-root", str(tmp_path)])

        assert exit_code == 0
        out = json.loads(capsys.readouterr().out)
        assert out[0]["status"] == "待送出"

    def test_explicit_local_verdict_at_overrides_auto_detection(
        self, tmp_path, monkeypatch, capsys
    ):
        """(iii) stdin 顯式 `local_verdict_at` 優先於自動算出的值。"""
        # review.md mtime 早於 review submittedAt → 自動算出的話會判定「已送出」。
        old_mtime_epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp()
        self._write_review_with_mtime(tmp_path, "58543", old_mtime_epoch)

        item = self._stdin_item(
            "https://github.com/apache/airflow/pull/58543",
            submitted_at="2026-01-02T00:00:00Z",
        )
        # 顯式欄位晚於 review submittedAt → 應蓋掉自動偵測，強制判「待送出」。
        item["local_verdict_at"] = "2026-09-29T00:00:00Z"
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps([item])))

        exit_code = bs.main(
            [
                "--you",
                YOU,
                "--repo",
                "apache/airflow",
                "--maigo-root",
                str(tmp_path),
            ]
        )

        assert exit_code == 0
        out = json.loads(capsys.readouterr().out)
        assert out[0]["status"] == "待送出"

    def test_auto_detected_mtime_has_no_timezone_offset(
        self, tmp_path, monkeypatch, capsys
    ):
        """
        (iv) 時區 canary：mtime 對應的真實 UTC 時刻與「若誤用系統本地時區重新解讀該
        wall-clock、再被當成 UTC」兩種結果相差 8 小時，剛好跨過 review submittedAt
        這個判斷點——如果實作退化成 naive `datetime.fromtimestamp(mtime)`（沒帶
        `tz=timezone.utc`），這條測試會因為系統本地時區被設成 Asia/Taipei 而翻盤
        （偽 UTC 時刻變成 12:00，比 08:00 的 review 還晚，判成「待送出」）；正確實作
        用 `tz=timezone.utc` 直接換算，不受系統本地時區影響，結果穩定為「已送出」。
        """
        original_tz = os.environ.get("TZ")
        os.environ["TZ"] = "Asia/Taipei"
        time.tzset()
        try:
            true_utc = datetime(2026, 9, 29, 4, 0, 0, tzinfo=timezone.utc)
            self._write_review_with_mtime(tmp_path, "58543", true_utc.timestamp())

            item = self._stdin_item(
                "https://github.com/apache/airflow/pull/58543",
                submitted_at="2026-09-29T08:00:00Z",
            )
            monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps([item])))

            exit_code = bs.main(
                [
                    "--you",
                    YOU,
                    "--repo",
                    "apache/airflow",
                    "--maigo-root",
                    str(tmp_path),
                ]
            )

            assert exit_code == 0
            out = json.loads(capsys.readouterr().out)
            # 正確：local_verdict_at == 2026-09-29T04:00:00+00:00，
            # submittedAt (08:00Z) >= local_verdict_at → 已送出 → 保留 prior verdict。
            assert out[0]["status"] == "APPROVE"
        finally:
            if original_tz is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = original_tz
            time.tzset()


class TestCheckboxAfterRefresh:
    @pytest.mark.parametrize(
        "item_type", [bs.ItemType.ISSUE, bs.ItemType.OWN_PR, bs.ItemType.REVIEW_PR]
    )
    @pytest.mark.parametrize(
        "checked_now,acked,needs_review",
        list(itertools.product([False, True], repeat=3)),
    )
    def test_truth_table(self, item_type, checked_now, acked, needs_review):
        expected = (
            (acked or checked_now) and not needs_review
            if item_type is bs.ItemType.REVIEW_PR
            else checked_now
        )
        assert (
            bs.checkbox_after_refresh(item_type, checked_now, acked, needs_review)
            is expected
        )

    def test_ball_back_unchecks_review_even_if_checked(self):
        assert not bs.checkbox_after_refresh(bs.ItemType.REVIEW_PR, True, False, True)

    def test_reviewed_is_always_checked(self):
        assert bs.checkbox_after_refresh(bs.ItemType.REVIEW_PR, False, True, False)


class TestMainCheckboxFields:
    URL = "https://github.com/o/r/pull/7"
    HEAD = "a" * 40

    def _write_report(self, root, **extra):
        record = {
            "version": 1,
            "source": self.URL,
            "head_sha": self.HEAD,
            "verdict": "APPROVE",
            "reviewed_at": "2026-01-02T00:00:00+00:00",
            **extra,
        }
        path = root / ".maigo" / "review" / "7" / "review.md"
        path.parent.mkdir(parents=True)
        path.write_text(f"<!-- maigo-review: {json.dumps(record)} -->\n")

    def _run(self, monkeypatch, capsys, root, head=None, **fields):
        item = {
            "type": "👀",
            "url": self.URL,
            "prior_status": None,
            "gh_meta": {
                "state": "OPEN",
                "author": {"login": "carol"},
                "createdAt": "2026-01-01T00:00:00Z",
                "headRefOid": head or self.HEAD,
            },
            **fields,
        }
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps([item])))
        args = ["--you", YOU, "--repo", "o/r", "--maigo-root", str(root)]
        assert bs.main(args) == 0
        return json.loads(capsys.readouterr().out)[0]

    def test_ball_back_auto_unchecks(self, tmp_path, monkeypatch, capsys):
        self._write_report(tmp_path)
        row = self._run(monkeypatch, capsys, tmp_path, head="b" * 40, checked=True)
        assert row["status"] == "↩︎ 回你的球"
        assert row["checked"] is False

    def test_acked_current_requires_matching_head(self, tmp_path, monkeypatch, capsys):
        self._write_report(
            tmp_path,
            acknowledged_by=YOU,
            acknowledged_at="2026-01-03T00:00:00+00:00",
        )
        same = self._run(monkeypatch, capsys, tmp_path, checked=False)
        assert same["acked_current"] is True and same["checked"] is True
        moved = self._run(monkeypatch, capsys, tmp_path, head="b" * 40, checked=False)
        assert moved["acked_current"] is False and moved["checked"] is False

    def test_learn_pending_skips_items_already_learned(
        self, tmp_path, monkeypatch, capsys
    ):
        self._write_report(tmp_path)
        fresh = self._run(
            monkeypatch,
            capsys,
            tmp_path,
            checked=True,
            checkbox_change="checked",
            prior_badges=[],
        )
        learned = self._run(
            monkeypatch,
            capsys,
            tmp_path,
            checked=True,
            checkbox_change="checked",
            prior_badges=["🧠"],
        )
        assert fresh["learn_pending"] is True
        assert learned["learn_pending"] is False

    def test_old_call_shape_has_no_new_fields(self, tmp_path, monkeypatch, capsys):
        self._write_report(tmp_path)
        row = self._run(monkeypatch, capsys, tmp_path)
        assert not {"checked", "learn_pending", "acked_current"} & row.keys()

    def test_checked_is_null_when_not_supplied_but_other_field_is(
        self, tmp_path, monkeypatch, capsys
    ):
        self._write_report(tmp_path)
        row = self._run(monkeypatch, capsys, tmp_path, prior_badges=[])
        assert row["checked"] is None


class TestEvaluateItemsReviewOverrides:
    URL = "https://github.com/o/r/pull/7"
    HEAD = "a" * 40

    def _item(self):
        return {
            "type": "👀",
            "url": self.URL,
            "prior_status": None,
            "checked": False,
            "gh_meta": {
                "state": "OPEN",
                "author": {"login": "carol"},
                "createdAt": "2026-01-01T00:00:00Z",
                "headRefOid": self.HEAD,
            },
        }

    def _record(self, **extra):
        return {
            "version": 1,
            "source": self.URL,
            "head_sha": self.HEAD,
            "verdict": "APPROVE",
            "reviewed_at": "2026-01-02T00:00:00+00:00",
            **extra,
        }

    def test_override_replaces_the_report_read_from_disk(self, tmp_path):
        now = datetime(2026, 2, 1, tzinfo=timezone.utc)
        kwargs = {"you": YOU, "repo": "o/r", "maigo_root": str(tmp_path), "now": now}
        # No report on disk: without an override the item is not acked.
        plain = bs.evaluate_items([self._item()], **kwargs)[0]
        assert plain["acked_current"] is False
        acked = self._record(
            acknowledged_by=YOU, acknowledged_at="2026-01-03T00:00:00+00:00"
        )
        item = {**self._item(), "prior_badges": []}
        result = bs.evaluate_items(
            [item], review_overrides={self.URL: acked}, **kwargs
        )[0]
        assert result["acked_current"] is True and result["checked"] is True
        unacked = bs.evaluate_items(
            [item], review_overrides={self.URL: self._record()}, **kwargs
        )[0]
        assert unacked["acked_current"] is False and unacked["checked"] is False

    def test_invalid_type_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="第 0 項"):
            bs.evaluate_items(
                [{"type": "?"}],
                you=YOU,
                repo="o/r",
                maigo_root="",
                now=datetime(2026, 2, 1, tzinfo=timezone.utc),
            )
