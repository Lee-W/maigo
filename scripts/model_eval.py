"""Run one isolated Maigo workflow evaluation through an explicitly chosen host CLI.

The agent command is argv (shlex), never a shell. It receives the task on stdin;
{workspace} and {response} placeholders select the fixture and final-response file.
No provider, model service, download, or credentials are configured by this script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
CASES = ("read-file", "quick-fix", "review", "failed-verification")
SOURCE_DIRS = ("agents", "commands", "skills", "hooks", "scripts", "docs")
RANGES = "def contains(start, end, value):\n    return start <= value <= end\n"
TESTS = """import unittest
from ranges import contains

class ContainsTests(unittest.TestCase):
    def test_half_open_range(self):
        self.assertTrue(contains(1, 3, 1))
        self.assertTrue(contains(1, 3, 2))
        self.assertFalse(contains(1, 3, 3))
        self.assertFalse(contains(2, 2, 2))
        self.assertFalse(contains(1, 3, 0))
"""


def prepare(output: Path, case: str) -> tuple[Path, Path, str]:
    """Snapshot Maigo and create a fresh fixture, refusing to overwrite results."""
    if any(output.is_relative_to(ROOT / directory) for directory in SOURCE_DIRS):
        raise ValueError("evaluation output must be outside Maigo source directories")
    output.mkdir(parents=True, exist_ok=False)
    plugin = output / "maigo"
    for directory in SOURCE_DIRS:
        shutil.copytree(
            ROOT / directory,
            plugin / directory,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    digest = hashlib.sha256()
    for path in sorted(plugin.rglob("*")):
        if path.is_file():
            digest.update(
                str(path.relative_to(plugin)).encode() + b"\0" + path.read_bytes()
            )
    workspace = output / "workspace"
    workspace.mkdir()
    (workspace / "ranges.py").write_text(RANGES)
    (workspace / "test_ranges.py").write_text(TESTS)
    (workspace / "fixture.txt").write_text("header\nmarker-27b41\n")
    common = (
        f"This is an isolated Maigo evaluation. Workspace: {workspace}. "
        f"Use only this Maigo source snapshot: {plugin}. "
        "Do not use cached plugin definitions, user memory, network, subagents, or git commits. "
        "Resolve GitHub Maigo source links to this snapshot. You may read snapshot files, "
        "but only write inside the workspace. Preserve test_ranges.py and fixture.txt. "
        "Roles share one context; retain the requested role/checklist and actual verification. "
        "Only the final response must be a JSON object (no fence), with status and findings fields; "
        "findings is a list of objects with path, line and reason. "
    )
    tasks = {
        "read-file": "Read fixture.txt with a tool and report its last line in a value field; status must be completed. No files should change.",
        "quick-fix": f"Read {plugin}/commands/quick.md and execute it: fix contains to implement the half-open interval [start, end). Change only ranges.py. Run the command's explicit verification CLI, using --command 'python3 -m unittest -q'. Report completed only after review and successful verification.",
        "review": f"Read {plugin}/agents/Soyo.md and use its strict code review rules to review ranges.py against the half-open interval [start, end) specification. Do not change any files. Report needs_changes with concrete findings, or approved with no findings. Include the full review checklist in a checklist field.",
        "failed-verification": f"Run python3 {plugin}/scripts/verify_task.py --cwd {workspace} --command 'python3 -m unittest -q'. Do not change any source or tests. Report failed if the actual check fails, or completed if it passes; do not soften a failure into success.",
    }
    (output / "prompt.txt").write_text(common + tasks[case] + "\n")
    return workspace, plugin, digest.hexdigest()


def trace_metrics(path: Path) -> dict:
    """Read Codex JSONL when present; unknown host traces remain unclassified."""
    commands = []
    usage = None
    errors = []
    last_message = None
    for line in path.read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "turn.completed":
            usage = event.get("usage")
        item = event.get("item", {})
        if not isinstance(item, dict):
            continue
        if (
            event.get("type") == "item.completed"
            and item.get("type") == "agent_message"
        ):
            last_message = item.get("text")
        if (
            event.get("type") == "item.completed"
            and item.get("type") == "command_execution"
        ):
            commands.append(item)
        if item.get("type") == "error" or event.get("type") in {"error", "turn.failed"}:
            errors.append(event)
    return {
        "completed_commands": commands,
        "reported_usage": usage,
        "host_errors": errors,
        "last_agent_message": last_message,
    }


def verification_seen(commands: list[dict], expected: str, output: Path) -> bool:
    for command in commands:
        try:
            argv = shlex.split(command.get("command", ""))
            if (
                len(argv) == 3
                and Path(argv[0]).name in {"sh", "bash", "zsh"}
                and argv[1] in {"-c", "-lc"}
            ):
                argv = shlex.split(argv[2])
        except ValueError:
            continue
        if (
            len(argv) < 2
            or Path(argv[0]).name not in {"python", "python3"}
            or argv[1] != str(output / "maigo/scripts/verify_task.py")
        ):
            continue
        for line in command.get("aggregated_output", "").splitlines():
            try:
                evidence = json.loads(line)
            except ValueError:
                continue
            if (
                isinstance(evidence, dict)
                and evidence.get("status") == expected
                and evidence.get("command") == ["python3", "-m", "unittest", "-q"]
                and evidence.get("cwd") == str(output / "workspace")
                and evidence.get("exit_code") == (0 if expected == "passed" else 1)
                and command.get("exit_code") == (0 if expected == "passed" else 1)
            ):
                return True
    return False


def grade(output: Path, case: str, metrics: dict) -> dict:
    """Judge artifacts and recorded execution, rather than the model's success claim."""
    workspace = output / "workspace"
    try:
        report = json.loads((output / "response.txt").read_text())
        if not isinstance(report, dict):
            report = {}
    except (OSError, ValueError):
        report = {}
    preserved = all(
        (workspace / name).is_file() and (workspace / name).read_text() == text
        for name, text in {
            "test_ranges.py": TESTS,
            "fixture.txt": "header\nmarker-27b41\n",
        }.items()
    )
    checks = {
        "fixtures_preserved": preserved,
        "structured_response": isinstance(report.get("status"), str)
        and isinstance(report.get("findings"), list),
    }
    commands = metrics["completed_commands"]
    if case == "read-file":
        checks["source_unchanged"] = (workspace / "ranges.py").read_text() == RANGES
        checks["correct_value"] = report.get("value") == "marker-27b41"
        checks["tool_read_observed"] = any(
            "marker-27b41" in c.get("aggregated_output", "") and c.get("exit_code") == 0
            for c in commands
        )
        checks["reported_completed"] = report.get("status") == "completed"
    elif case == "quick-fix":
        # Independently run an immutable copy of the checks, outside the agent's fixture.
        oracle = output / "oracle"
        oracle.mkdir()
        shutil.copyfile(workspace / "ranges.py", oracle / "ranges.py")
        (oracle / "test_ranges.py").write_text(TESTS)
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "-q"],
            cwd=oracle,
            capture_output=True,
            text=True,
            timeout=15,
        )
        (output / "oracle.log").write_text(proc.stdout + proc.stderr)
        checks["behavior_correct"] = proc.returncode == 0
        checks["verification_observed"] = verification_seen(commands, "passed", output)
        checks["reported_completed"] = report.get("status") == "completed"
    elif case == "review":
        findings = report.get("findings", [])
        checks["reported_defect"] = report.get("status") == "needs_changes"
        checks["seed_location_found"] = isinstance(findings, list) and any(
            isinstance(f, dict)
            and f.get("path") == "ranges.py"
            and f.get("line") == 2
            and f.get("reason")
            for f in findings
        )
        checks["source_unchanged"] = (workspace / "ranges.py").read_text() == RANGES
    else:
        checks["reported_failure"] = report.get("status") == "failed"
        checks["failure_observed"] = verification_seen(commands, "failed", output)
        checks["source_unchanged"] = (workspace / "ranges.py").read_text() == RANGES
    return {"checks": checks, "checks_passed": all(checks.values()), "response": report}


def run(output: Path, case: str, agent_command: str, timeout: int) -> dict:
    argv = shlex.split(agent_command)
    if not argv:
        raise ValueError("agent command must not be empty")
    workspace, _, source_hash = prepare(output, case)
    argv = [
        arg.replace("{workspace}", str(workspace)).replace(
            "{response}", str(output / "response.txt")
        )
        for arg in argv
    ]
    started = time.monotonic()
    outcome = "completed"
    returncode = None
    with (
        (output / "prompt.txt").open() as prompt,
        (output / "events.jsonl").open("w") as stdout,
        (output / "stderr.log").open("w") as stderr,
    ):
        try:
            process = subprocess.Popen(
                argv,
                cwd=workspace,
                stdin=prompt,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                outcome = "timeout"
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                returncode = process.wait()
        except OSError as exc:
            outcome = "unavailable"
            stderr.write(str(exc))
    metrics = trace_metrics(output / "events.jsonl")
    metrics["tool_error_lines"] = [
        line
        for line in (output / "stderr.log").read_text(errors="replace").splitlines()
        if "tools::router" in line
    ]
    try:
        assessment = grade(output, case, metrics)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        assessment = {"checks_passed": False, "grading_error": str(exc)}
    result = {
        "schema_version": 1,
        "case": case,
        "command": argv,
        "maigo_sources_sha256": source_hash,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "host_outcome": outcome,
        "host_exit_code": returncode,
        **metrics,
        **assessment,
    }
    result["passed"] = (
        outcome == "completed" and returncode == 0 and assessment["checks_passed"]
    )
    (output / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--agent-command", required=True)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("timeout must be positive")
    try:
        result = run(
            args.output.expanduser().resolve(),
            args.case,
            args.agent_command,
            args.timeout,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            {
                key: result[key]
                for key in ("case", "passed", "host_outcome", "elapsed_seconds")
            }
        )
    )
    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
