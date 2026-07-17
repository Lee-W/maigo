"""Tests for scripts.board_state — the Work Board state machine's single source of truth."""

from __future__ import annotations

import io
import itertools
import json
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
        assert result.bucket is bs.Bucket.DONE
        assert result.tier is bs.Tier.DONE

    @pytest.mark.parametrize("verdict", [bs.BoardStatus.DUP, bs.BoardStatus.CLOSE])
    def test_dup_and_close_verdicts_are_sticky_terminal(self, verdict):
        result = _classify(bs.ItemType.ISSUE, {"state": "OPEN"}, verdict)
        assert result.status is verdict
        assert result.bucket is bs.Bucket.DONE
        assert result.tier is bs.Tier.DONE

    def test_no_prior_verdict_falls_to_pending_triage(self):
        result = _classify(bs.ItemType.ISSUE, {"state": "OPEN"}, None)
        assert result.status is bs.BoardStatus.PENDING_TRIAGE
        assert result.bucket is bs.Bucket.TARGET
        assert result.tier is bs.Tier.ACT
        assert result.next_action == "/maigo:triage-issue"

    def test_ready_with_no_assignee_stays_ready(self):
        gh_meta = {"state": "OPEN", "assignees": []}
        result = _classify(bs.ItemType.ISSUE, gh_meta, bs.BoardStatus.READY)
        assert result.status is bs.BoardStatus.READY
        assert result.bucket is bs.Bucket.TARGET
        assert result.tier is bs.Tier.ACT
        assert result.next_action == "/maigo:take-issue"

    def test_ready_with_you_assigned_stays_ready(self):
        gh_meta = {"state": "OPEN", "assignees": [{"login": YOU}]}
        result = _classify(bs.ItemType.ISSUE, gh_meta, bs.BoardStatus.READY)
        assert result.status is bs.BoardStatus.READY

    def test_in_progress_is_sticky_and_wip_tier(self):
        gh_meta = {"state": "OPEN"}
        result = _classify(bs.ItemType.ISSUE, gh_meta, bs.BoardStatus.IN_PROGRESS)
        assert result.status is bs.BoardStatus.IN_PROGRESS
        assert result.bucket is bs.Bucket.TARGET
        assert result.tier is bs.Tier.WIP

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
        assert result.bucket is bs.Bucket.TARGET
        assert result.tier is bs.Tier.ACT
        assert result.next_action == "/maigo:triage-issue"

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
        assert result.bucket is bs.Bucket.WAITING
        assert result.tier is bs.Tier.WAIT


# ---------------------------------------------------------------------------
# 🔀 你的 PR — recomputed purely from gh_meta each refresh, prior_status ignored
# ---------------------------------------------------------------------------


class TestClassifyOwnPr:
    def test_merged_at_wins(self):
        result = _classify(
            bs.ItemType.OWN_PR, {"mergedAt": "2026-01-01T00:00:00Z"}, None
        )
        assert result.status is bs.BoardStatus.MERGED
        assert result.bucket is bs.Bucket.DONE
        assert result.tier is bs.Tier.DONE

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
        assert result.bucket is bs.Bucket.TARGET
        assert result.tier is bs.Tier.WIP

    def test_conflicting_mergeable_is_blocked(self):
        gh_meta = {"state": "OPEN", "isDraft": False, "mergeable": "CONFLICTING"}
        result = _classify(bs.ItemType.OWN_PR, gh_meta, None)
        assert result.status is bs.BoardStatus.CONFLICT
        assert result.bucket is bs.Bucket.TARGET
        assert result.tier is bs.Tier.BLOCKED
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
        assert result.tier is bs.Tier.BLOCKED

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
        assert result.tier is bs.Tier.BLOCKED
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
        assert result.bucket is bs.Bucket.TARGET
        assert result.tier is bs.Tier.ACT
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
        assert result.bucket is bs.Bucket.TARGET
        assert result.tier is bs.Tier.ACT

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
        assert result.bucket is bs.Bucket.WAITING
        assert result.tier is bs.Tier.WAIT

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
        assert result.bucket is bs.Bucket.WAITING
        assert result.tier is bs.Tier.WAIT


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
        assert result.bucket is bs.Bucket.WAITING
        assert result.tier is bs.Tier.WAIT

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
        assert result.bucket is bs.Bucket.TARGET
        assert result.tier is bs.Tier.ACT
        assert result.next_action == "/maigo:review"

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
        assert result.bucket is bs.Bucket.TARGET
        assert result.tier is bs.Tier.ACT
        assert result.next_action == "/maigo:review"

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
        assert result.bucket is bs.Bucket.WAITING
        assert result.tier is bs.Tier.WAIT


# ---------------------------------------------------------------------------
# Transition property test: classify() 輸出必須 ∈ ALLOWED_TRANSITIONS[prior]
# ---------------------------------------------------------------------------

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
        """`classify()` 的輸出必須 ∈ `ALLOWED_TRANSITIONS[prior]`。

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
# tier / bucket totality
# ---------------------------------------------------------------------------


class TestTierTotality:
    def test_every_board_status_has_a_tier(self):
        for status in bs.BoardStatus:
            assert bs.tier_for_status(status.value) is not None

    def test_unknown_status_returns_none(self):
        assert bs.tier_for_status("這不是一個合法狀態詞") is None

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
                "bucket": "🎯",
                "status": "待 triage",
                "tier": "act",
                "next_action": "/maigo:triage-issue",
                "badges": [],
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
