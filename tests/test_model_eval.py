"""Test evaluation bookkeeping and grading; stub hosts are not model benchmarks."""

from __future__ import annotations

import json
import shlex
import sys

import pytest

from scripts import model_eval as evaluation


def host_command(code):
    return shlex.join([sys.executable, "-c", code, "{workspace}", "{response}"])


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
