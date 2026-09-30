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
import re
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
    )
    tasks = {
        "read-file": "Read fixture.txt with a tool and report its last line in a value field; status must be completed. No files should change.",
        "quick-fix": f"Read {plugin}/commands/quick.md and execute it: fix contains to implement the half-open interval [start, end). Change only ranges.py. Run the command's explicit verification CLI, using --command 'python3 -m unittest -q'. Report completed only after review and successful verification.",
        "review": f"Read {plugin}/agents/Soyo.md and use its strict code review rules to review ranges.py against the half-open interval [start, end) specification. Do not change any files. Report needs_changes with concrete findings, or approved with no findings. Include the full review checklist in a checklist field.",
        "failed-verification": f"Run python3 {plugin}/scripts/verify_task.py --cwd {workspace} --command 'python3 -m unittest -q'. Do not change any source or tests. Report failed if the actual check fails, or completed if it passes; do not soften a failure into success.",
    }
    verification_contract = (
        (
            " Run verification as its own foreground tool call: invoke python3 and the "
            "absolute verify_task.py path directly, without cd, pipes, redirection, command chaining, "
            "or echoing its exit code. The grader pairs that call's exit code with its JSON output. "
        )
        if case in {"quick-fix", "failed-verification"}
        else ""
    )
    response_contract = (
        "The final response must be exactly one JSON object, no fence or surrounding prose, "
        "with status and findings fields; findings is a list of objects with path, line and reason. "
        "Put all required checklists, summaries and evidence inside additional JSON fields."
    )
    (output / "prompt.txt").write_text(
        common + tasks[case] + " " + verification_contract + response_contract + "\n"
    )
    return workspace, plugin, digest.hexdigest()


def claude_trace_metrics(path: Path) -> dict:
    """Pair Claude Code stream-json tool results with their originating calls."""
    calls = {}
    commands = []
    reads = []
    errors = []
    models: set[str] = set()
    usage = None
    last_message = None
    final_response = None
    for line in path.read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict) or event.get("parent_tool_use_id"):
            continue
        if event.get("type") == "result":
            usage = event.get("usage")
            models.update(event.get("modelUsage") or {})
            if event.get("is_error") is False and event.get("subtype") == "success":
                final_response = event.get("result")
            else:
                errors.append(event)
            continue
        message = event.get("message", {})
        if not isinstance(message, dict):
            continue
        content = message.get("content", [])
        if not isinstance(content, list):
            continue
        if event.get("type") == "assistant":
            if message.get("model"):
                models.add(message["model"])
            text = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    calls[block["id"]] = block
                elif block.get("type") == "text":
                    text.append(block["text"])
            if text:
                last_message = "\n".join(text)
        elif event.get("type") == "user":
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                call = calls.pop(block.get("tool_use_id"), None)
                if call is None:
                    continue
                output = block.get("content", "")
                if isinstance(output, list):
                    output = "\n".join(
                        part["text"]
                        for part in output
                        if isinstance(part, dict) and part.get("type") == "text"
                    )
                if not isinstance(output, str):
                    continue
                native = event.get("tool_use_result")
                if call["name"] == "Read":
                    reads.append(
                        {
                            "path": call["input"]["file_path"],
                            "output": output,
                            "succeeded": not block.get("is_error", False),
                        }
                    )
                elif call["name"] == "Bash":
                    exit_code = None
                    if isinstance(native, dict) and not native.get("interrupted"):
                        if block.get("is_error") is False:
                            exit_code = 0
                    # A failed call may contain a permission/transport error rather
                    # than a process exit. Only the host's exit marker proves one.
                    if block.get("is_error") is True and not (
                        isinstance(native, dict) and native.get("interrupted")
                    ):
                        match = re.match(r"Exit code (\d+)(?:\n|$)", output)
                        if match:
                            exit_code = int(match[1])
                    commands.append(
                        {
                            "command": call["input"]["command"],
                            "aggregated_output": output,
                            "exit_code": exit_code,
                            "tool_use_id": block["tool_use_id"],
                        }
                    )
    return {
        "completed_commands": commands,
        "completed_reads": reads,
        "reported_usage": usage,
        "reported_models": sorted(models),
        "host_errors": errors,
        "terminal_error": bool(errors),
        "last_agent_message": last_message,
        "final_response": final_response,
    }


def trace_metrics(path: Path, trace_format: str = "codex") -> dict:
    """Read the explicitly selected host format; preserve unknown records."""
    if trace_format == "claude":
        return claude_trace_metrics(path)
    if trace_format != "codex":
        raise ValueError(f"Unsupported trace format: {trace_format}")
    commands = []
    usage = None
    errors = []
    terminal_error = False
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
        if event.get("type") == "turn.failed":
            terminal_error = True
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
        "terminal_error": terminal_error,
        "last_agent_message": last_message,
    }


def verification_seen(commands: list[dict], expected: str, output: Path) -> bool:
    for command in commands:
        try:
            source = command.get("command", "")
            argv = shlex.split(source)
            if (
                len(argv) == 3
                and Path(argv[0]).name in {"sh", "bash", "zsh"}
                and argv[1] in {"-c", "-lc"}
            ):
                source = argv[2]
            lexer = shlex.shlex(source.strip(), posix=True, punctuation_chars=";&|<>\n")
            lexer.whitespace = " \t\r"
            lexer.whitespace_split = True
            argv = list(lexer)
        except ValueError:
            continue
        if any(token and set(token) <= set(";&|<>\n") for token in argv):
            continue
        if argv and Path(argv[0]).name == "env":
            argv = argv[1:]
        while argv and re.match(r"^[A-Za-z_][A-Za-z_0-9]*=", argv[0]):
            argv = argv[1:]
        if argv and Path(argv[0]).name in {"python", "python3"}:
            while len(argv) > 1 and argv[1] in {
                "-B",
                "-E",
                "-I",
                "-O",
                "-OO",
                "-P",
                "-q",
                "-s",
                "-S",
                "-u",
            }:
                argv.pop(1)
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
        ) or any(
            Path(read["path"]).resolve() == (workspace / "fixture.txt").resolve()
            and "marker-27b41" in read["output"]
            and read["succeeded"]
            for read in metrics.get("completed_reads", [])
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


def run(
    output: Path,
    case: str,
    agent_command: str,
    timeout: int,
    trace_format: str = "codex",
) -> dict:
    if trace_format not in {"codex", "claude"}:
        raise ValueError(f"Unsupported trace format: {trace_format}")
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
    metrics = trace_metrics(output / "events.jsonl", trace_format)
    if trace_format == "claude" and isinstance(metrics["final_response"], str):
        (output / "response.txt").write_text(metrics["final_response"])
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
        "trace_format": trace_format,
        "command": argv,
        "maigo_sources_sha256": source_hash,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "host_outcome": outcome,
        "host_exit_code": returncode,
        **metrics,
        **assessment,
    }
    result["passed"] = (
        outcome == "completed"
        and returncode == 0
        and not metrics["terminal_error"]
        and (trace_format != "claude" or isinstance(metrics["final_response"], str))
        and assessment["checks_passed"]
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
    parser.add_argument("--trace-format", choices=("codex", "claude"), default="codex")
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
            args.trace_format,
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
