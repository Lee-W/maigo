"""Tests for the fail-open subagent transcript reader."""

from __future__ import annotations

import json
from pathlib import Path

from hooks import _transcript as tr


def assistant(msg_id, usage=None, content=None, model=None, requested=None) -> dict:
    message: dict = {"id": msg_id, "role": "assistant"}
    if usage is not None:
        message["usage"] = usage
    if content is not None:
        message["content"] = content
    if model is not None:
        message["model"] = model
    row: dict = {"type": "assistant", "message": message}
    if requested is not None:
        row["requestedModel"] = requested
    return row


def usage(i=1, o=2, cw=3, cr=4, **extra) -> dict:
    return {
        "input_tokens": i,
        "output_tokens": o,
        "cache_creation_input_tokens": cw,
        "cache_read_input_tokens": cr,
        **extra,
    }


def write(path: Path, rows: list) -> Path:
    path.write_text(
        "\n".join(r if isinstance(r, str) else json.dumps(r) for r in rows) + "\n",
        encoding="utf-8",
    )
    return path


def handback(text: str) -> dict:
    return {
        "type": "tool_use",
        "name": "SubagentHandback",
        "input": {"message": text},
    }


class TestSumUsage:
    def test_dedups_by_message_id(self, tmp_path):
        path = write(
            tmp_path / "t.jsonl",
            [
                assistant("a", usage(1, 1, 1, 1, service_tier="x")),
                assistant("a", usage(1, 1, 1, 1)),
                assistant("a", usage(1, 1, 1, 1)),
                assistant("b", usage(10, 20, 30, 40)),
                assistant("c", usage(100, 200, 300, 400), requested="sonnet"),
            ],
        )
        counts, model = tr.sum_usage(path)
        assert counts == {
            "input_tokens": 111,
            "output_tokens": 221,
            "cache_creation_input_tokens": 331,
            "cache_read_input_tokens": 441,
        }
        assert model == "sonnet"

    def test_model_falls_back_to_message_model(self, tmp_path):
        path = write(tmp_path / "t.jsonl", [assistant("a", usage(), model="claude-x")])
        assert tr.sum_usage(path)[1] == "claude-x"

    def test_no_model_is_none(self, tmp_path):
        path = write(tmp_path / "t.jsonl", [assistant("a", usage())])
        assert tr.sum_usage(path)[1] is None

    def test_missing_file(self, tmp_path):
        assert tr.sum_usage(tmp_path / "nope.jsonl") is None

    def test_skips_bad_and_non_assistant_lines(self, tmp_path):
        path = write(
            tmp_path / "t.jsonl",
            [
                "{not json",
                '"a string"',
                {"type": "attachment"},
                {"type": "user", "message": {"id": "u", "usage": usage()}},
                {"type": "api-request"},
                assistant("a", usage(5, 6, 7, 8)),
                {"type": "assistant", "message": {"usage": usage()}},
                assistant("noUsage"),
                {"type": "assistant", "message": "not a dict"},
                {"type": "assistant", "message": {"id": "z", "content": "str"}},
            ],
        )
        counts, _ = tr.sum_usage(path)
        assert counts["input_tokens"] == 5

    def test_all_bad_lines(self, tmp_path):
        path = write(tmp_path / "t.jsonl", ["{x", "[]", {"type": "user"}])
        assert tr.sum_usage(path) is None


class TestFinalReport:
    def test_handback_beats_earlier_text(self, tmp_path):
        path = write(
            tmp_path / "t.jsonl",
            [
                assistant("a", content=[{"type": "text", "text": "early"}]),
                assistant("b", content=[handback("the report")]),
            ],
        )
        assert tr.final_report(path) == "the report"

    def test_handback_beats_text_in_same_message(self, tmp_path):
        path = write(
            tmp_path / "t.jsonl",
            [
                assistant(
                    "a", content=[handback("report"), {"type": "text", "text": "t"}]
                )
            ],
        )
        assert tr.final_report(path) == "report"

    def test_last_handback_wins(self, tmp_path):
        path = write(
            tmp_path / "t.jsonl",
            [
                assistant("a", content=[handback("first")]),
                assistant("b", content=[handback("second")]),
            ],
        )
        assert tr.final_report(path) == "second"

    def test_text_only_takes_last_message_texts(self, tmp_path):
        path = write(
            tmp_path / "t.jsonl",
            [
                assistant("a", content=[{"type": "text", "text": "old"}]),
                assistant(
                    "b",
                    content=[
                        {"type": "text", "text": "x"},
                        {"type": "tool_use", "name": "Bash", "input": {}},
                        {"type": "text", "text": "y"},
                    ],
                ),
            ],
        )
        assert tr.final_report(path) == "x\ny"

    def test_text_blocks_split_across_rows_with_same_id(self, tmp_path):
        path = write(
            tmp_path / "t.jsonl",
            [
                assistant("old", content=[{"type": "text", "text": "old"}]),
                assistant("m", content=[{"type": "text", "text": "first"}]),
                assistant("m", content=[{"type": "text", "text": "second"}]),
            ],
        )
        assert tr.final_report(path) == "first\nsecond"

    def test_non_list_content_skipped(self, tmp_path):
        path = write(
            tmp_path / "t.jsonl",
            [{"type": "assistant", "message": {"id": "a", "content": "str"}}],
        )
        assert tr.final_report(path) is None

    def test_neither(self, tmp_path):
        path = write(
            tmp_path / "t.jsonl",
            [assistant("a", content=[{"type": "tool_use", "name": "Bash"}])],
        )
        assert tr.final_report(path) is None

    def test_empty_handback_ignored(self, tmp_path):
        path = write(
            tmp_path / "t.jsonl",
            [
                assistant("a", content=[{"type": "text", "text": "fallback"}]),
                assistant("b", content=[handback("")]),
            ],
        )
        assert tr.final_report(path) == "fallback"

    def test_missing_file(self, tmp_path):
        assert tr.final_report(tmp_path / "nope.jsonl") is None


class TestReadWithRetry:
    def test_retries_until_value(self, tmp_path):
        path = tmp_path / "t.jsonl"
        path.write_text("")
        results = iter([None, None, "ok"])
        sleeps: list[float] = []
        got = tr.read_with_retry(lambda p: next(results), path, sleep=sleeps.append)
        assert got == "ok"
        assert sleeps == [0.15, 0.15]

    def test_gives_up_after_three_attempts(self, tmp_path):
        path = tmp_path / "t.jsonl"
        path.write_text("")
        calls: list[int] = []
        sleeps: list[float] = []

        def fn(p):
            calls.append(1)

        assert tr.read_with_retry(fn, path, sleep=sleeps.append) is None
        assert len(calls) == 3

    def test_missing_path_no_retry(self, tmp_path):
        sleeps: list[float] = []
        assert (
            tr.read_with_retry(tr.final_report, tmp_path / "nope", sleep=sleeps.append)
            is None
        )
        assert sleeps == []
