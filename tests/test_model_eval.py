"""Test evaluation bookkeeping and grading; stub hosts are not model benchmarks."""

from __future__ import annotations

import json
import shlex
import sys

import pytest

from scripts import model_eval as evaluation


def host_command(code):
    return shlex.join([sys.executable, "-c", code, "{workspace}", "{response}"])


def claude_call(call_id, name, arguments):
    return {
        "type": "assistant",
        "message": {
            "model": "test-model",
            "content": [
                {"type": "tool_use", "id": call_id, "name": name, "input": arguments}
            ],
        },
    }


def claude_result(call_id, output, is_error=False, native=None):
    return {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": call_id,
                    "content": output,
                    "is_error": is_error,
                }
            ]
        },
        "tool_use_result": native,
    }


def test_explicit_host_gets_fixture_and_prompt_and_result_is_recorded(tmp_path):
    command = host_command("""import json, sys
from pathlib import Path
assert Path.cwd() == Path(sys.argv[1])
assert 'isolated Maigo evaluation' in sys.stdin.read()
value = Path('fixture.txt').read_text().splitlines()[-1]
Path(sys.argv[2]).write_text(json.dumps({'status': 'completed', 'findings': [], 'value': value}))
print(json.dumps({'type': 'item.completed', 'item': {'type': 'command_execution', 'command': 'cat fixture.txt', 'aggregated_output': value, 'exit_code': 0}}))
print(json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 42, 'output_tokens': 8}}))
""")
    result = evaluation.run(tmp_path / "run", "read-file", command, 10)
    assert result["passed"]
    assert result["host_exit_code"] == 0
    assert result["reported_usage"]["input_tokens"] == 42
    assert len(result["maigo_sources_sha256"]) == 64
    assert json.loads((tmp_path / "run/result.json").read_text()) == result


def test_success_claim_without_tool_evidence_does_not_pass(tmp_path):
    command = host_command(
        'from pathlib import Path; import sys; Path(sys.argv[2]).write_text(\'{"status":"completed","findings":[],"value":"marker-27b41"}\')'
    )
    result = evaluation.run(tmp_path / "run", "read-file", command, 10)
    assert result["checks"]["correct_value"]
    assert not result["checks"]["tool_read_observed"]
    assert not result["passed"]


def test_failed_host_is_not_a_success_even_with_correct_response(tmp_path):
    command = host_command("""import json, sys
from pathlib import Path
value = Path('fixture.txt').read_text().splitlines()[-1]
Path(sys.argv[2]).write_text(json.dumps({'status': 'completed', 'findings': [], 'value': value}))
print(json.dumps({'type': 'item.completed', 'item': {'type': 'command_execution', 'command': 'cat fixture.txt', 'aggregated_output': value, 'exit_code': 0}}))
raise SystemExit(7)
""")
    result = evaluation.run(tmp_path / "run", "read-file", command, 10)
    assert result["checks_passed"]
    assert result["host_exit_code"] == 7
    assert not result["passed"]


def test_missing_host_is_recorded_as_unavailable(tmp_path):
    result = evaluation.run(
        tmp_path / "run", "read-file", "missing-maigo-evaluation-host", 10
    )
    assert result["host_outcome"] == "unavailable"
    assert result["host_exit_code"] is None
    assert not result["passed"]


def test_timeout_is_bounded_and_persists_result(tmp_path):
    command = host_command("""import json, time
print(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'partial response'}}), flush=True)
time.sleep(10)
""")
    result = evaluation.run(tmp_path / "run", "read-file", command, 1)
    assert result["host_outcome"] == "timeout"
    assert result["last_agent_message"] == "partial response"
    assert result["elapsed_seconds"] < 5
    assert not result["passed"]


def test_existing_results_are_never_overwritten(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("original")
    with pytest.raises(FileExistsError):
        evaluation.prepare(output, "read-file")
    assert marker.read_text() == "original"


def test_output_under_source_directory_is_rejected():
    with pytest.raises(ValueError, match="outside Maigo source"):
        evaluation.prepare(evaluation.ROOT / "scripts" / "recursive-eval", "read-file")


@pytest.mark.parametrize("correct", [False, True])
def test_fix_is_checked_by_immutable_external_tests(tmp_path, correct):
    evaluation.prepare(tmp_path / "run", "quick-fix")
    workspace = tmp_path / "run/workspace"
    if correct:
        (workspace / "ranges.py").write_text(
            evaluation.RANGES.replace("value <= end", "value < end")
        )
    # An agent can falsify its local tests; these must not fool the oracle.
    (workspace / "test_ranges.py").write_text("")
    (tmp_path / "run/response.txt").write_text('{"status":"completed","findings":[]}')
    result = evaluation.grade(tmp_path / "run", "quick-fix", {"completed_commands": []})
    assert result["checks"]["behavior_correct"] is correct
    assert not result["checks"]["fixtures_preserved"]
    assert not result["checks_passed"]


def test_review_seed_location_and_unchanged_source(tmp_path):
    evaluation.prepare(tmp_path / "run", "review")
    response = {
        "status": "needs_changes",
        "findings": [
            {"path": "ranges.py", "line": 2, "reason": "Upper bound is included."}
        ],
    }
    (tmp_path / "run/response.txt").write_text(json.dumps(response))
    result = evaluation.grade(tmp_path / "run", "review", {"completed_commands": []})
    assert result["checks_passed"]
    response["findings"][0]["line"] = 1
    (tmp_path / "run/response.txt").write_text(json.dumps(response))
    assert not evaluation.grade(tmp_path / "run", "review", {"completed_commands": []})[
        "checks_passed"
    ]


def test_echoed_verification_claim_is_not_execution_evidence(tmp_path):
    evidence = json.dumps(
        {
            "status": "passed",
            "command": ["python3", "-m", "unittest", "-q"],
            "exit_code": 0,
            "cwd": str(tmp_path / "workspace"),
        }
    )
    command = {
        "command": "echo verify_task.py",
        "exit_code": 0,
        "aggregated_output": evidence,
    }
    assert not evaluation.verification_seen([command], "passed", tmp_path)
    command["command"] = shlex.join(
        [
            "/bin/zsh",
            "-lc",
            shlex.join(
                [
                    "python3",
                    str(tmp_path / "maigo/scripts/verify_task.py"),
                    "--cwd",
                    str(tmp_path / "workspace"),
                ]
            ),
        ]
    )
    assert evaluation.verification_seen([command], "passed", tmp_path)
    command["exit_code"] = 1
    assert not evaluation.verification_seen([command], "passed", tmp_path)


def test_failed_verification_requires_both_failure_report_and_actual_check(tmp_path):
    output = tmp_path / "run"
    evaluation.prepare(output, "failed-verification")
    (output / "response.txt").write_text('{"status":"failed","findings":[]}')
    evidence = {
        "status": "failed",
        "command": ["python3", "-m", "unittest", "-q"],
        "exit_code": 1,
        "cwd": str(output / "workspace"),
    }
    command = {
        "command": shlex.join(
            ["python3", str(output / "maigo/scripts/verify_task.py")]
        ),
        "exit_code": 1,
        "aggregated_output": json.dumps(evidence),
    }
    assert evaluation.grade(
        output, "failed-verification", {"completed_commands": [command]}
    )["checks_passed"]
    (output / "response.txt").write_text('{"status":"completed","findings":[]}')
    assert not evaluation.grade(
        output, "failed-verification", {"completed_commands": [command]}
    )["checks_passed"]


def test_claude_trace_pairs_interleaved_calls_and_records_failed_verification(tmp_path):
    output = tmp_path / "run"
    evaluation.prepare(output, "failed-verification")
    verification = shlex.join(["python3", str(output / "maigo/scripts/verify_task.py")])
    evidence = json.dumps(
        {
            "status": "failed",
            "command": ["python3", "-m", "unittest", "-q"],
            "exit_code": 1,
            "cwd": str(output / "workspace"),
        }
    )
    events = [
        claude_call("check", "Bash", {"command": verification}),
        claude_call("unrelated", "Bash", {"command": "echo unrelated"}),
        claude_result("unrelated", "unrelated", native={"interrupted": False}),
        claude_result("check", "Exit code 1\n" + evidence, True, "Error: Exit code 1"),
    ]
    trace = output / "events.jsonl"
    trace.write_text("\n".join(json.dumps(event) for event in events))
    metrics = evaluation.trace_metrics(trace, "claude")
    assert [(c["command"], c["exit_code"]) for c in metrics["completed_commands"]] == [
        ("echo unrelated", 0),
        (verification, 1),
    ]
    assert evaluation.verification_seen(metrics["completed_commands"], "failed", output)
    assert not evaluation.verification_seen(
        metrics["completed_commands"], "passed", output
    )
    assert metrics["reported_models"] == ["test-model"]


@pytest.mark.parametrize(
    ("prefix", "suffix", "expected"),
    [
        pytest.param("PYTHONDONTWRITEBYTECODE=1 ", "", True, id="assignment"),
        pytest.param("env PYTHONDONTWRITEBYTECODE=1 ", "", True, id="env"),
        pytest.param("", "; echo success", False, id="chained-echo"),
        pytest.param("", "\necho success", False, id="newline-chain"),
        pytest.param("", " | cat", False, id="pipe-masks-exit"),
        pytest.param("", " || true", False, id="ignored-failure"),
    ],
)
def test_verification_command_allows_environment_but_not_masked_exits(
    tmp_path, prefix, suffix, expected
):
    source = (
        prefix
        + shlex.join(["python3", str(tmp_path / "maigo/scripts/verify_task.py")])
        + suffix
    )
    command = {
        "command": shlex.join(["/bin/zsh", "-lc", source]),
        "exit_code": 0,
        "aggregated_output": json.dumps(
            {
                "status": "passed",
                "command": ["python3", "-m", "unittest", "-q"],
                "cwd": str(tmp_path / "workspace"),
                "exit_code": 0,
            }
        ),
    }
    assert evaluation.verification_seen([command], "passed", tmp_path) is expected


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        pytest.param("-B", True, id="no-bytecode"),
        pytest.param("-I -u", True, id="isolated-unbuffered"),
        pytest.param("-c", False, id="code-string-not-script"),
        pytest.param("-m", False, id="module-not-script"),
    ],
)
def test_verification_accepts_python_script_flags(tmp_path, flags, expected):
    command = {
        "command": f"python3 {flags} "
        + shlex.quote(str(tmp_path / "maigo/scripts/verify_task.py")),
        "exit_code": 0,
        "aggregated_output": json.dumps(
            {
                "status": "passed",
                "command": ["python3", "-m", "unittest", "-q"],
                "cwd": str(tmp_path / "workspace"),
                "exit_code": 0,
            }
        ),
    }
    assert evaluation.verification_seen([command], "passed", tmp_path) is expected


@pytest.mark.parametrize(
    ("is_error", "native", "output", "expected"),
    [
        pytest.param(
            False, {"interrupted": False}, "Exit code 9", 0, id="stdout-not-exit"
        ),
        pytest.param(True, "permission denied", "Permission denied", None, id="denied"),
        pytest.param(False, {"interrupted": True}, "partial", None, id="interrupted"),
        pytest.param(
            True, {"interrupted": True}, "Exit code 1", None, id="interrupted-error"
        ),
        pytest.param(False, None, "output", None, id="missing-native-result"),
        pytest.param(True, "Error: Exit code 3", "Exit code 3", 3, id="nonzero"),
    ],
)
def test_claude_bash_does_not_guess_process_exit(
    tmp_path, is_error, native, output, expected
):
    trace = tmp_path / "events.jsonl"
    events = [
        claude_call("call", "Bash", {"command": "python3 check.py"}),
        claude_result("call", output, is_error, native),
        claude_result("unknown", "unpaired", native={"interrupted": False}),
    ]
    trace.write_text("\n".join(json.dumps(event) for event in events))
    commands = evaluation.trace_metrics(trace, "claude")["completed_commands"]
    assert len(commands) == 1
    assert commands[0]["exit_code"] == expected


@pytest.mark.parametrize("terminal", ["success", "error", "missing"])
def test_claude_final_response_requires_successful_terminal_result(tmp_path, terminal):
    report = '{"status":"completed","findings":[],"value":"marker-27b41"}'
    events = [
        claude_call(
            "read", "Read", {"file_path": str(tmp_path / "run/workspace/fixture.txt")}
        ),
        claude_result("read", [{"type": "text", "text": "header\nmarker-27b41"}]),
        {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": report}]},
        },
    ]
    if terminal != "missing":
        events.append(
            {
                "type": "result",
                "is_error": terminal == "error",
                "subtype": "success" if terminal == "success" else "error_max_turns",
                "result": report,
                "usage": {"input_tokens": 12, "output_tokens": 4},
                "modelUsage": {"test-model": {}},
            }
        )
    command = host_command(
        "import sys; from pathlib import Path; "
        f"Path(sys.argv[2]).write_text({report!r}); "
        f"print({chr(10).join(json.dumps(e) for e in events)!r})"
    )
    result = evaluation.run(tmp_path / "run", "read-file", command, 10, "claude")
    assert result["passed"] is (terminal == "success")
    assert result["checks"]["tool_read_observed"]
    assert result["last_agent_message"] == report
    assert (tmp_path / "run/response.txt").exists()


def test_claude_failed_read_is_not_evidence(tmp_path):
    output = tmp_path / "run"
    evaluation.prepare(output, "read-file")
    (output / "response.txt").write_text(
        '{"status":"completed","findings":[],"value":"marker-27b41"}'
    )
    events = [
        claude_call(
            "read", "Read", {"file_path": str(output / "workspace/fixture.txt")}
        ),
        claude_result("read", "marker-27b41", True),
    ]
    trace = output / "events.jsonl"
    trace.write_text("\n".join(json.dumps(event) for event in events))
    result = evaluation.grade(
        output, "read-file", evaluation.trace_metrics(trace, "claude")
    )
    assert not result["checks"]["tool_read_observed"]


@pytest.mark.parametrize("terminal", [False, True])
def test_only_terminal_host_error_blocks_otherwise_valid_result(tmp_path, terminal):
    error = (
        {"type": "turn.failed", "error": {"message": "session failed"}}
        if terminal
        else {
            "type": "item.completed",
            "item": {"type": "error", "message": "metadata warning"},
        }
    )
    code = """import json,sys
from pathlib import Path
Path(sys.argv[2]).write_text('{"status":"completed","findings":[],"value":"marker-27b41"}')
print(json.dumps({'type':'item.completed','item':{'type':'command_execution','command':'cat fixture.txt','aggregated_output':'marker-27b41','exit_code':0}}))
"""
    command = host_command(code + f"\nprint({json.dumps(error)!r})")
    result = evaluation.run(tmp_path / "run", "read-file", command, 10)
    assert result["checks_passed"]
    assert result["host_exit_code"] == 0
    assert result["passed"] is not terminal
