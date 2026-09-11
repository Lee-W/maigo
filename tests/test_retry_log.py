"""Retry streaks are scoped to a run, task and check, not lifetime history."""

from dataclasses import asdict
import json

import pytest

from hooks._retry_log import RetryScope, record_and_count


@pytest.mark.parametrize("field", ["failures", "must_fix_keys"])
@pytest.mark.parametrize("between", [set(), {"b"}])
def test_absent_failure_restarts_streak(tmp_path, field, between):
    log = tmp_path / "nested" / "retry.jsonl"
    scope = RetryScope("run", "task")
    assert record_and_count(log, {"a"}, field, scope=scope) == {"a": 1}
    record_and_count(log, between, field, scope=scope)
    assert record_and_count(log, {"a"}, field, scope=scope) == {"a": 1}
    assert record_and_count(log, {"a", "b"}, field, scope=scope) == {"a": 2, "b": 1}


@pytest.mark.parametrize(
    "other",
    [
        RetryScope("other-run", "task", "cmd"),
        RetryScope("run", "other-task", "cmd"),
        RetryScope("run", "task", "other-cmd"),
    ],
)
def test_scopes_can_interleave_without_sharing_or_resetting_counts(tmp_path, other):
    log = tmp_path / "retry.jsonl"
    scope = RetryScope("run", "task", "cmd")
    record_and_count(log, {"a"}, "failures", scope=scope)
    assert record_and_count(log, {"a"}, "failures", scope=other) == {"a": 1}
    record_and_count(log, set(), "failures", scope=other)
    assert record_and_count(log, {"a"}, "failures", scope=scope) == {"a": 2}


def test_malformed_and_legacy_records_do_not_pollute_scope(tmp_path):
    log = tmp_path / "retry.jsonl"
    scope = RetryScope("run", "task")
    log.write_text(
        "\n".join(
            [
                "broken json",
                "null",
                "[]",
                json.dumps({"failures": ["a"]}),
                json.dumps({"scope": asdict(scope), "failures": "a"}),
                json.dumps({"scope": asdict(scope), "failures": [None]}),
                json.dumps({"scope": asdict(scope), "failures": ["a", "a"]}),
            ]
        )
        + "\n"
    )
    assert record_and_count(log, {"a"}, "failures", scope=scope) == {"a": 2}


def test_log_io_failure_remains_fail_open(tmp_path):
    blocker = tmp_path / "file"
    blocker.touch()
    assert (
        record_and_count(
            blocker / "retry.jsonl", {"a"}, "failures", scope=RetryScope("run", "task")
        )
        == {}
    )
