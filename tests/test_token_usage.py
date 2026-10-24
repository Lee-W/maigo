"""Tests for metadata-only token usage tracking."""

from __future__ import annotations

import json
import datetime
from pathlib import Path

from hooks import _token_usage as usage


def agent_event(cwd: Path, **overrides: object) -> dict:
    event = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Agent",
        "session_id": "session-1",
        "cwd": str(cwd),
        "tool_input": {"subagent_type": "maigo:Soyo"},
        "tool_response": {
            "status": "completed",
            "agentId": "agent-1",
            "resolvedModel": "claude-sonnet",
            "usage": {
                "input_tokens": 8_320,
                "output_tokens": 1_230,
                "cache_creation_input_tokens": 400,
                "cache_read_input_tokens": 2_500,
            },
        },
    }
    event.update(overrides)
    return event


def test_records_completed_agent_usage(tmp_path: Path):
    assert usage.record_agent_usage(agent_event(tmp_path))

    entries, malformed = usage.read_entries(tmp_path / usage.LOG_PATH)
    assert malformed == 0
    assert entries[0] == {
        "ts": entries[0]["ts"],
        "session_id": "session-1",
        "agent_id": "agent-1",
        "agent_type": "maigo:Soyo",
        "model": "claude-sonnet",
        "input_tokens": 8_320,
        "output_tokens": 1_230,
        "cache_creation_input_tokens": 400,
        "cache_read_input_tokens": 2_500,
    }


def test_deduplicates_session_and_agent(tmp_path: Path):
    event = agent_event(tmp_path)

    assert usage.record_agent_usage(event)
    assert not usage.record_agent_usage(event)
    assert len(usage.read_entries(tmp_path / usage.LOG_PATH)[0]) == 1


def test_background_or_missing_usage_is_ignored(tmp_path: Path):
    background = agent_event(
        tmp_path,
        tool_response={"status": "async_launched", "agentId": "agent-1"},
    )
    missing = agent_event(
        tmp_path,
        tool_response={"status": "completed", "agentId": "agent-2"},
    )

    assert not usage.record_agent_usage(background)
    assert not usage.record_agent_usage(missing)
    assert not (tmp_path / usage.LOG_PATH).exists()


def test_summary_filters_session_and_reports_malformed_lines(tmp_path: Path):
    log = tmp_path / usage.LOG_PATH
    log.parent.mkdir()
    rows = [
        {
            "session_id": "session-1",
            "input_tokens": 1_000,
            "output_tokens": 200,
            "cache_creation_input_tokens": 30,
            "cache_read_input_tokens": 400,
        },
        {
            "session_id": "session-2",
            "input_tokens": 9_000,
            "output_tokens": 800,
        },
    ]
    log.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\nnot-json\n",
        encoding="utf-8",
    )

    summary = usage.summarize(log, session_id="session-1")

    assert summary.tracked_agents == 1
    assert summary.input_tokens == 1_000
    assert summary.output_tokens == 200
    assert summary.cache_creation_input_tokens == 30
    assert summary.cache_read_input_tokens == 400
    assert summary.malformed_lines == 1
    assert usage.format_one_line(summary) == (
        "Token usage：input 1.0k｜output 200｜cache write 30｜"
        "cache read 400｜已追蹤 1 agents"
    )


def test_empty_summary_states_metadata_is_unavailable(tmp_path: Path):
    summary = usage.summarize(tmp_path / "missing.jsonl", session_id="missing")

    assert "無可用 metadata" in usage.format_one_line(summary)


def test_summary_lookback_and_breakdown(tmp_path: Path):
    log = tmp_path / usage.LOG_PATH
    log.parent.mkdir()
    now = datetime.datetime.now(datetime.UTC)
    rows = [
        {
            "ts": (now - datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "agent_type": "maigo:Soyo",
            "model": "sonnet",
            "input_tokens": 1_000,
            "output_tokens": 200,
        },
        {
            "ts": (now - datetime.timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "agent_type": "maigo:Raana",
            "model": "haiku",
            "input_tokens": 9_000,
            "output_tokens": 1_000,
        },
    ]
    log.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    since = now - datetime.timedelta(days=7)

    summary = usage.summarize(log, since=since)
    agents, models = usage.breakdown(log, since=since)

    assert summary.tracked_agents == 1
    assert agents == {"maigo:Soyo": 1_200}
    assert models == {"sonnet": 1_200}
    assert usage.format_breakdown("依角色", agents) == "依角色：maigo:Soyo 1.2k"


# --- SubagentStop transcript path -------------------------------------------


def _row(msg_id: str, i: int, o: int, cw: int, cr: int, **extra: object) -> dict:
    return {
        "type": "assistant",
        "message": {
            "id": msg_id,
            "usage": {
                "input_tokens": i,
                "output_tokens": o,
                "cache_creation_input_tokens": cw,
                "cache_read_input_tokens": cr,
            },
        },
        **extra,
    }


def _transcript(tmp_path: Path, rows: list[dict] | None = None) -> Path:
    if rows is None:
        rows = [
            _row("a", 1, 2, 3, 4),
            _row("a", 1, 2, 3, 4),
            _row("a", 1, 2, 3, 4),
            _row("b", 10, 20, 30, 40),
            _row("c", 100, 200, 300, 400, requestedModel="sonnet"),
        ]
    path = tmp_path / "agent.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def stop_event(cwd: Path, transcript: Path | None, **overrides: object) -> dict:
    event: dict = {
        "hook_event_name": "SubagentStop",
        "session_id": "session-1",
        "agent_id": "agent-1",
        "agent_type": "general-purpose",
        "cwd": str(cwd),
    }
    if transcript is not None:
        event["agent_transcript_path"] = str(transcript)
    event.update(overrides)
    return event


def test_subagent_stop_records_deduplicated_usage(tmp_path: Path):
    assert usage.record_subagent_usage(stop_event(tmp_path, _transcript(tmp_path)))

    entries, _ = usage.read_entries(tmp_path / usage.LOG_PATH)
    assert len(entries) == 1
    assert entries[0] == {
        "ts": entries[0]["ts"],
        "session_id": "session-1",
        "agent_id": "agent-1",
        "agent_type": "general-purpose",
        "model": "sonnet",
        "input_tokens": 111,
        "output_tokens": 222,
        "cache_creation_input_tokens": 333,
        "cache_read_input_tokens": 444,
    }


def test_subagent_stop_missing_inputs_do_not_write(tmp_path: Path):
    assert not usage.record_subagent_usage(stop_event(tmp_path, None))
    assert not usage.record_subagent_usage(
        stop_event(tmp_path, tmp_path / "missing.jsonl")
    )
    zero = _transcript(tmp_path, [_row("a", 0, 0, 0, 0)])
    assert not usage.record_subagent_usage(stop_event(tmp_path, zero))
    assert not (tmp_path / usage.LOG_PATH).exists()


def test_subagent_stop_ignores_other_events(tmp_path: Path):
    event = stop_event(tmp_path, _transcript(tmp_path), hook_event_name="Stop")
    assert not usage.record_subagent_usage(event)


def test_dedup_across_paths_post_tool_use_first(tmp_path: Path):
    assert usage.record_agent_usage(agent_event(tmp_path))
    assert not usage.record_subagent_usage(
        stop_event(tmp_path, _transcript(tmp_path), agent_id="agent-1")
    )
    assert len(usage.read_entries(tmp_path / usage.LOG_PATH)[0]) == 1


def test_dedup_across_paths_subagent_stop_first(tmp_path: Path):
    assert usage.record_subagent_usage(stop_event(tmp_path, _transcript(tmp_path)))
    assert not usage.record_agent_usage(agent_event(tmp_path))
    assert len(usage.read_entries(tmp_path / usage.LOG_PATH)[0]) == 1


def test_main_dispatches_subagent_stop(tmp_path: Path, monkeypatch, capsys):
    import io

    from hooks import token_usage

    event = stop_event(tmp_path, _transcript(tmp_path))
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    assert token_usage.main() == 0
    assert capsys.readouterr().out == ""
    assert len(usage.read_entries(tmp_path / usage.LOG_PATH)[0]) == 1


def test_hooks_json_registers_unmatched_token_usage_group():
    root = Path(__file__).resolve().parents[1]
    groups = json.loads((root / "hooks/hooks.json").read_text())["hooks"][
        "SubagentStop"
    ]
    assert len(groups) == 2
    quality, tokens = groups
    assert quality["matcher"] == "^(maigo:)?(Raana|Tomori|Anon|Soyo|Taki)$"
    assert quality["hooks"][0]["command"].endswith('teammate_quality_check.py"')
    assert "matcher" not in tokens
    assert tokens["hooks"][0]["command"].endswith('token_usage.py"')
