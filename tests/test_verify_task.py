"""Exercise the explicit verification entry point with real child processes."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verify_task.py"


def verify(cwd: Path, command: str | None = None) -> tuple[int, dict]:
    argv = [sys.executable, str(SCRIPT), "--cwd", str(cwd)]
    if command is not None:
        argv.extend(["--command", command])
    proc = subprocess.run(argv, cwd=cwd.parent, capture_output=True, text=True)
    assert not proc.stderr, proc.stderr
    return proc.returncode, json.loads(proc.stdout)


@pytest.mark.parametrize("code", [0, 1, 7])
def test_records_actual_command_result(tmp_path, code):
    command = shlex.join(
        [sys.executable, "-c", f"print('evidence'); raise SystemExit({code})"]
    )
    rc, result = verify(tmp_path, command)
    assert rc == (0 if code == 0 else 1)
    assert result["status"] == ("passed" if code == 0 else "failed")
    assert result["exit_code"] == code
    assert result["output"] == "evidence\n"
    assert result["cwd"] == str(tmp_path.resolve())
    assert result["command"] == shlex.split(command)
    assert result["schema_version"] == 1
    assert result["finished_at"] >= result["started_at"]


def test_runs_in_clean_repository_without_session_hook(tmp_path):
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    rc, result = verify(tmp_path, shlex.join([sys.executable, "-c", "print('ran')"]))
    assert rc == 0
    assert result["output"] == "ran\n"


@pytest.mark.parametrize(
    "command", [None, "", "'unclosed", "missing-maigo-test-runner"]
)
def test_unavailable_is_not_success(tmp_path, command):
    rc, result = verify(tmp_path, command)
    assert rc == 2
    assert result["status"] == "unavailable"


def test_explicit_skip_is_distinct(tmp_path):
    config = tmp_path / ".claude"
    config.mkdir()
    (config / "skip-test-verification").write_text("manual hardware check required\n")
    rc, result = verify(tmp_path)
    assert rc == 3
    assert result["status"] == "skipped"
    assert result["exit_code"] is None
    assert "manual hardware" in result["reason"]


def test_missing_cwd_returns_structured_unavailable(tmp_path):
    rc, result = verify(tmp_path / "missing")
    assert rc == 2
    assert result["status"] == "unavailable"
    assert result["exit_code"] is None
    assert "not a directory" in result["reason"]


def test_known_failures_are_not_pass(tmp_path):
    config = tmp_path / ".claude"
    config.mkdir()
    (config / "known-test-failures").write_text("tests/example.py::test_old\n")
    rc, result = verify(
        tmp_path,
        shlex.join(
            [
                sys.executable,
                "-c",
                "print('FAILED tests/example.py::test_old'); raise SystemExit(1)",
            ]
        ),
    )
    assert rc == 4
    assert result["status"] == "known_failures"
    assert result["exit_code"] == 1


def test_build_environment_failure_is_unavailable(tmp_path):
    rc, result = verify(
        tmp_path,
        shlex.join(
            [
                sys.executable,
                "-c",
                "print('CMake configuration failed'); raise SystemExit(1)",
            ]
        ),
    )
    assert rc == 2
    assert result["status"] == "unavailable"


def test_legacy_config_command_still_runs(tmp_path):
    config = tmp_path / ".claude"
    config.mkdir()
    (config / "test-command").write_text(
        shlex.join([sys.executable, "-c", "print('configured')"])
    )
    rc, result = verify(tmp_path)
    assert rc == 0
    assert result["output"] == "configured\n"


def test_bug_fix_changes_verification_from_failed_to_passed(tmp_path):
    source = tmp_path / "example.py"
    source.write_text("def normalize(text):\n    return text\n")
    (tmp_path / "test_example.py").write_text(
        "import unittest\nfrom example import normalize\n"
        "class TestNormalize(unittest.TestCase):\n"
        "    def test_trims_whitespace(self):\n"
        "        self.assertEqual(normalize(' hello '), 'hello')\n"
    )
    command = shlex.join([sys.executable, "-B", "-m", "unittest", "-v"])
    rc, before = verify(tmp_path, command)
    assert rc == 1
    assert before["status"] == "failed"
    assert "AssertionError" in before["output"]

    source.write_text("def normalize(text):\n    return text.strip()\n")
    rc, after = verify(tmp_path, command)
    assert rc == 0
    assert after["status"] == "passed"
    assert "Ran 1 test" in after["output"]
