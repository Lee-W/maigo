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
# has_git_modifications
# ---------------------------------------------------------------------------


class TestHasGitModifications:
    def test_clean_repo_returns_false(self, tmp_path: Path):
        import subprocess

        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "init"],
            cwd=tmp_path,
            capture_output=True,
            env={
                **__import__("os").environ,
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@t",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@t",
            },
        )
        assert verify_completion.has_git_modifications(tmp_path) is False

    def test_untracked_file_returns_true(self, tmp_path: Path):
        import subprocess

        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        (tmp_path / "new.py").write_text("x = 1")
        assert verify_completion.has_git_modifications(tmp_path) is True

    def test_staged_file_returns_true(self, tmp_path: Path):
        import subprocess

        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        f = tmp_path / "f.py"
        f.write_text("x = 1")
        subprocess.run(["git", "add", "f.py"], cwd=tmp_path, capture_output=True)
        assert verify_completion.has_git_modifications(tmp_path) is True

    def test_non_git_dir_fails_open(self, tmp_path: Path):
        # tmp_path has no git repo → git status fails → fail-open (True)
        assert verify_completion.has_git_modifications(tmp_path) is True

    def test_git_not_found_fails_open(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        import subprocess

        original_run = subprocess.run

        def raise_not_found(*args, **kwargs):
            if args and args[0][0] == "git":
                raise FileNotFoundError
            return original_run(*args, **kwargs)

        monkeypatch.setattr(subprocess, "run", raise_not_found)
        assert verify_completion.has_git_modifications(tmp_path) is True


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


# ---------------------------------------------------------------------------
# _retry_log_path
# ---------------------------------------------------------------------------


class TestRetryLogPath:
    def test_path_structure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(verify_completion, "_RETRY_LOG_BASE", tmp_path / "maigo")
        cwd = tmp_path / "myrepo"
        cwd.mkdir()
        result = verify_completion._retry_log_path(cwd)
        assert result == tmp_path / "maigo" / "myrepo" / "test-failures.jsonl"

    def test_parent_created(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(verify_completion, "_RETRY_LOG_BASE", tmp_path / "maigo")
        cwd = tmp_path / "myrepo"
        cwd.mkdir()
        result = verify_completion._retry_log_path(cwd)
        assert result.parent.is_dir()


# ---------------------------------------------------------------------------
# _record_and_count
# ---------------------------------------------------------------------------


class TestRecordAndCount:
    def test_first_append_count_is_one(self, tmp_path: Path):
        log = tmp_path / "test-failures.jsonl"
        counts = verify_completion._record_and_count(log, {"tests/x.py::test_a"})
        assert counts["tests/x.py::test_a"] == 1

    def test_second_append_same_id_count_is_two(self, tmp_path: Path):
        log = tmp_path / "test-failures.jsonl"
        verify_completion._record_and_count(log, {"tests/x.py::test_a"})
        counts = verify_completion._record_and_count(log, {"tests/x.py::test_a"})
        assert counts["tests/x.py::test_a"] == 2

    def test_different_ids_counted_independently(self, tmp_path: Path):
        log = tmp_path / "test-failures.jsonl"
        verify_completion._record_and_count(log, {"tests/x.py::test_a"})
        counts = verify_completion._record_and_count(log, {"tests/x.py::test_b"})
        assert counts["tests/x.py::test_a"] == 1
        assert counts["tests/x.py::test_b"] == 1

    def test_corrupted_log_line_skipped(self, tmp_path: Path):
        log = tmp_path / "test-failures.jsonl"
        log.write_text(
            '{"ts": "2026-01-01T00:00:00Z", "failures": ["tests/x.py::test_a"]}\n'
            "not valid json at all\n",
            encoding="utf-8",
        )
        counts = verify_completion._record_and_count(log, {"tests/x.py::test_a"})
        # first line parsed correctly → count is 1 from history + 1 from this call = 2
        assert counts["tests/x.py::test_a"] == 2

    def test_io_error_returns_empty_dict(self, tmp_path: Path):
        # Make log path unwritable by placing a file where the parent dir should be
        parent_blocker = tmp_path / "blocked-dir"
        parent_blocker.write_text("i am a file, not a dir")
        log = parent_blocker / "test-failures.jsonl"
        # log.open("a") will raise OSError since parent is a file, not a dir
        counts = verify_completion._record_and_count(log, {"tests/x.py::test_a"})
        assert counts == {}


# ---------------------------------------------------------------------------
# main() retry warning integration
# ---------------------------------------------------------------------------


class TestMainRetryWarning:
    def test_first_failure_no_warning(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        (tmp_path / "uv.lock").touch()
        monkeypatch.setattr(
            verify_completion,
            "run_command",
            lambda cmd, cwd: (1, "FAILED tests/x.py::test_y"),
        )
        monkeypatch.setattr(
            verify_completion, "has_git_modifications", lambda cwd: True
        )
        monkeypatch.setattr(
            verify_completion, "_RETRY_LOG_BASE", tmp_path / "retry-log"
        )
        payload = {"cwd": str(tmp_path)}
        result = run_hook_main(verify_completion, payload, monkeypatch, capsys)
        assert result["decision"] == "block"
        assert "⚠️ RETRY LIMIT REACHED:" not in result["reason"]

    def test_second_failure_same_id_emits_warning(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        (tmp_path / "uv.lock").touch()
        monkeypatch.setattr(
            verify_completion,
            "run_command",
            lambda cmd, cwd: (1, "FAILED tests/x.py::test_y"),
        )
        monkeypatch.setattr(
            verify_completion, "has_git_modifications", lambda cwd: True
        )
        monkeypatch.setattr(
            verify_completion, "_RETRY_LOG_BASE", tmp_path / "retry-log"
        )
        payload = {"cwd": str(tmp_path)}

        # First run — no warning
        run_hook_main(verify_completion, payload, monkeypatch, capsys)
        # Second run — should have warning
        result = run_hook_main(verify_completion, payload, monkeypatch, capsys)
        assert result["decision"] == "block"
        assert "⚠️ RETRY LIMIT REACHED:" in result["reason"]
        assert "2 次" in result["reason"]
