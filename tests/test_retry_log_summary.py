"""Tests for scripts.retry_log_summary."""

from __future__ import annotations

import json
from pathlib import Path

import scripts.retry_log_summary as rls


def test_missing_log_is_empty(tmp_path: Path):
    summary = rls.summarize_log("taki", tmp_path / "missing.jsonl", "failures")

    assert summary.total_entries == 0
    assert summary.counts == {}
    assert summary.malformed_lines == 0
    assert "無紀錄" in rls.format_summary(summary)


def test_counts_keys_and_keeps_recent_three(tmp_path: Path):
    log = tmp_path / "test-failures.jsonl"
    entries = [
        {"ts": "2026-01-01T00:00:00Z", "failures": ["a"]},
        {"ts": "2026-01-01T00:01:00Z", "failures": ["a", "b"]},
        {"ts": "2026-01-01T00:02:00Z", "failures": ["b"]},
        {"ts": "2026-01-01T00:03:00Z", "failures": ["c"]},
    ]
    log.write_text(
        "\n".join(json.dumps(entry) for entry in entries) + "\n",
        encoding="utf-8",
    )

    summary = rls.summarize_log("taki", log, "failures")

    assert summary.total_entries == 4
    assert summary.counts == {"a": 2, "b": 2, "c": 1}
    assert [entry["ts"] for entry in summary.recent] == [
        "2026-01-01T00:01:00Z",
        "2026-01-01T00:02:00Z",
        "2026-01-01T00:03:00Z",
    ]


def test_malformed_lines_are_reported_but_skipped(tmp_path: Path):
    log = tmp_path / "soyo-must-fix.jsonl"
    log.write_text(
        '{"ts": "2026-01-01T00:00:00Z", "must_fix_keys": ["hooks/foo.py"]}\n'
        "not-json\n"
        "[1, 2, 3]\n",
        encoding="utf-8",
    )

    summary = rls.summarize_log("soyo", log, "must_fix_keys")
    formatted = rls.format_summary(summary)

    assert summary.total_entries == 1
    assert summary.counts == {"hooks/foo.py": 1}
    assert summary.malformed_lines == 2
    assert "略過損壞 JSON：2 行" in formatted


def test_summarize_repo_uses_maigo_sources(tmp_path: Path):
    maigo = tmp_path / ".maigo"
    maigo.mkdir()
    (maigo / "test-failures.jsonl").write_text(
        '{"ts": "2026-01-01T00:00:00Z", "failures": ["tests/x.py::test_y"]}\n',
        encoding="utf-8",
    )

    summaries = rls.summarize_repo(tmp_path)

    assert [summary.label for summary in summaries] == ["soyo", "taki"]
    assert summaries[0].total_entries == 0
    assert summaries[1].counts == {"tests/x.py::test_y": 1}
