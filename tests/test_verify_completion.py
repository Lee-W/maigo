"""Tests for hooks.verify_completion."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import hooks.verify_completion as verify_completion
from tests.conftest import run_hook_main


# ---------------------------------------------------------------------------
# extract_failures
# ---------------------------------------------------------------------------


class TestExtractFailures:
    def test_pytest_failed_prefix(self):
        out = "FAILED tests/x.py::test_y"
        assert "tests/x.py::test_y" in verify_completion.extract_failures(out)

    def test_pytest_summary_suffix(self):
        out = "tests/x.py::test_y FAILED"
        assert "tests/x.py::test_y" in verify_completion.extract_failures(out)

    def test_jest_fail(self):
        out = "FAIL src/x.test.js"
        assert "src/x.test.js" in verify_completion.extract_failures(out)

    def test_cargo_failed(self):
        out = "test foo ... FAILED"
        assert "foo" in verify_completion.extract_failures(out)

    def test_go_fail(self):
        out = "--- FAIL: TestFoo"
        assert "TestFoo" in verify_completion.extract_failures(out)

    def test_empty_input(self):
        assert verify_completion.extract_failures("") == set()

    def test_mixed_multiple(self):
        out = "FAILED tests/a.py::test_1\nFAILED tests/b.py::test_2\n--- FAIL: TestBar"
        failures = verify_completion.extract_failures(out)
        assert "tests/a.py::test_1" in failures
        assert "tests/b.py::test_2" in failures
        assert "TestBar" in failures


# ---------------------------------------------------------------------------
# read_known_failures
# ---------------------------------------------------------------------------


class TestReadKnownFailures:
    def test_file_not_exists(self, tmp_path: Path):
        result = verify_completion.read_known_failures(tmp_path / "nonexistent")
        assert result == set()

    def test_normal_multiline(self, tmp_path: Path):
        p = tmp_path / "known"
        p.write_text("tests/a.py::test_x\ntests/b.py::test_y\n", encoding="utf-8")
        result = verify_completion.read_known_failures(p)
        assert result == {"tests/a.py::test_x", "tests/b.py::test_y"}

    def test_comments_and_blank_lines_filtered(self, tmp_path: Path):
        p = tmp_path / "known"
        p.write_text(
            "# this is a comment\n\ntests/a.py::test_x\n  \n# another comment\n",
            encoding="utf-8",
        )
        result = verify_completion.read_known_failures(p)
        assert result == {"tests/a.py::test_x"}


# ---------------------------------------------------------------------------
# read_config_line
# ---------------------------------------------------------------------------


class TestReadConfigLine:
    def test_file_not_exists(self, tmp_path: Path):
        assert verify_completion.read_config_line(tmp_path / "none") is None

    def test_first_line_returned(self, tmp_path: Path):
        p = tmp_path / "config"
        p.write_text("uv run pytest\n", encoding="utf-8")
        assert verify_completion.read_config_line(p) == "uv run pytest"

    def test_skips_comments_and_blank_lines(self, tmp_path: Path):
        p = tmp_path / "config"
        p.write_text("# skip me\n\nactual-line\n", encoding="utf-8")
        assert verify_completion.read_config_line(p) == "actual-line"


# ---------------------------------------------------------------------------
# detect_test_command
# ---------------------------------------------------------------------------


class TestDetectTestCommand:
    def test_uv_lock(self, tmp_path: Path):
        (tmp_path / "uv.lock").touch()
        assert verify_completion.detect_test_command(tmp_path) == [
            "uv",
            "run",
            "pytest",
        ]

    def test_pyproject_with_tests_dir(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").touch()
        (tmp_path / "tests").mkdir()
        assert verify_completion.detect_test_command(tmp_path) == ["pytest"]

    def test_pyproject_without_tests_dir_falls_through(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").touch()
        # no tests/ dir, no other markers
        assert verify_completion.detect_test_command(tmp_path) is None

    def test_package_json_with_test_script(self, tmp_path: Path):
        pkg = {"scripts": {"test": "jest"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
        assert verify_completion.detect_test_command(tmp_path) == [
            "npm",
            "test",
            "--silent",
        ]

    def test_package_json_without_test_script_falls_through(self, tmp_path: Path):
        pkg = {"scripts": {"build": "tsc"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
        assert verify_completion.detect_test_command(tmp_path) is None

    def test_cargo_toml(self, tmp_path: Path):
        (tmp_path / "Cargo.toml").touch()
        assert verify_completion.detect_test_command(tmp_path) == [
            "cargo",
            "test",
            "--quiet",
        ]

    def test_go_mod(self, tmp_path: Path):
        (tmp_path / "go.mod").touch()
        assert verify_completion.detect_test_command(tmp_path) == [
            "go",
            "test",
            "./...",
        ]

    def test_empty_dir_returns_none(self, tmp_path: Path):
        assert verify_completion.detect_test_command(tmp_path) is None


# ---------------------------------------------------------------------------
# main() integration
# ---------------------------------------------------------------------------


class TestMain:
    def test_skip_test_verification(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "skip-test-verification").write_text(
            "testing in progress", encoding="utf-8"
        )
        payload = {"cwd": str(tmp_path)}
        result = run_hook_main(verify_completion, payload, monkeypatch, capsys)
        assert result["decision"] == "approve"
        assert "跳過" in result["reason"]

    def test_no_test_command_detected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        # empty tmp_path — detect_test_command returns None
        payload = {"cwd": str(tmp_path)}
        result = run_hook_main(verify_completion, payload, monkeypatch, capsys)
        assert result["decision"] == "approve"
        assert "偵測不到" in result["reason"]

    def test_run_command_succeeds(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        (tmp_path / "uv.lock").touch()
        monkeypatch.setattr(verify_completion, "run_command", lambda cmd, cwd: (0, ""))
        payload = {"cwd": str(tmp_path)}
        result = run_hook_main(verify_completion, payload, monkeypatch, capsys)
        assert result["decision"] == "approve"
