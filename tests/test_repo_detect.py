"""Tests for hooks.repo_detect."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import pytest

import hooks.repo_detect as rd
from tests.conftest import run_hook_main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(payload: dict, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture):
    return run_hook_main(rd, payload, monkeypatch, capsys)


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


class TestRepoDetect:
    def test_airflow_git_remote_detected(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
        tmp_path: Path,
    ):
        """git remote 含 apache/airflow → systemMessage 含 airflow-aware。"""
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: _fake_git_result("https://github.com/apache/airflow.git"),
        )
        result = _run({"cwd": str(tmp_path)}, monkeypatch, capsys)
        assert result["decision"] == "approve"
        assert "airflow-aware" in result["systemMessage"]
        assert result["systemMessage"] != ""

    def test_non_airflow_repo_silent(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
        tmp_path: Path,
    ):
        """git remote 是別的 URL → silent approve（空 systemMessage）。"""
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: _fake_git_result("https://github.com/some/other-repo.git"),
        )
        result = _run({"cwd": str(tmp_path)}, monkeypatch, capsys)
        assert result["decision"] == "approve"
        assert result["systemMessage"] == ""

    def test_airflow_file_structure_detected(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
        tmp_path: Path,
    ):
        """git fail，但 file structure 完整 → 偵測到 airflow-aware。"""
        # Build airflow/__init__.py + airflow/models/dag.py
        (tmp_path / "airflow").mkdir()
        (tmp_path / "airflow" / "__init__.py").touch()
        (tmp_path / "airflow" / "models").mkdir()
        (tmp_path / "airflow" / "models" / "dag.py").touch()

        # git remote call fails (non-zero returncode, empty output)
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: _fake_git_result("", returncode=1),
        )
        result = _run({"cwd": str(tmp_path)}, monkeypatch, capsys)
        assert result["decision"] == "approve"
        assert "airflow-aware" in result["systemMessage"]

    def test_airflow_file_structure_dag_root_detected(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
        tmp_path: Path,
    ):
        """git fail，airflow/dag.py（any_of 第二路徑）存在 → 偵測到 airflow-aware。"""
        (tmp_path / "airflow").mkdir()
        (tmp_path / "airflow" / "__init__.py").touch()
        (tmp_path / "airflow" / "dag.py").touch()  # any_of 第二個路徑

        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: _fake_git_result("", returncode=1),
        )
        result = _run({"cwd": str(tmp_path)}, monkeypatch, capsys)
        assert result["decision"] == "approve"
        assert "airflow-aware" in result["systemMessage"]

    def test_file_structure_incomplete_not_triggered(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
        tmp_path: Path,
    ):
        """只有 airflow/__init__.py，沒有 dag.py → silent（file structure 不完整）。"""
        (tmp_path / "airflow").mkdir()
        (tmp_path / "airflow" / "__init__.py").touch()
        # dag.py missing

        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: _fake_git_result("", returncode=1),
        )
        result = _run({"cwd": str(tmp_path)}, monkeypatch, capsys)
        assert result["decision"] == "approve"
        assert result["systemMessage"] == ""

    def test_git_missing_fail_open(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
        tmp_path: Path,
    ):
        """subprocess.run 丟 FileNotFoundError（git 不在 PATH）→ fail-open approve。"""
        monkeypatch.setattr(
            "subprocess.run",
            _raise_file_not_found,
        )
        result = _run({"cwd": str(tmp_path)}, monkeypatch, capsys)
        assert result["decision"] == "approve"

    def test_malformed_stdin_fail_open(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        """stdin 非 JSON → fail-open approve（cwd fallback os.getcwd()）。"""
        monkeypatch.setattr("sys.stdin", io.StringIO("not valid json {{{"))
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: _fake_git_result("https://github.com/some/other.git"),
        )
        with pytest.raises(SystemExit):
            rd.main()
        result_raw = capsys.readouterr().out.strip()
        result = json.loads(result_raw)
        assert result["decision"] == "approve"

    def test_subprocess_timeout_fail_open(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
        tmp_path: Path,
    ):
        """subprocess 丟 TimeoutExpired → fail-open approve。"""
        monkeypatch.setattr(
            "subprocess.run",
            _raise_timeout_expired,
        )
        result = _run({"cwd": str(tmp_path)}, monkeypatch, capsys)
        assert result["decision"] == "approve"

    def test_airflow_seeds_skip_test_verification(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
        tmp_path: Path,
    ):
        """偵測到 airflow → 寫 .claude/skip-test-verification 並在 message 提及。"""
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: _fake_git_result("https://github.com/apache/airflow.git"),
        )
        result = _run({"cwd": str(tmp_path)}, monkeypatch, capsys)

        seeded = tmp_path / ".claude" / "skip-test-verification"
        assert seeded.is_file()
        content = seeded.read_text(encoding="utf-8")
        # First non-comment line is what verify_completion reads as the skip reason
        first_payload = next(
            line for line in content.splitlines() if line.strip() and not line.startswith("#")
        )
        assert "airflow" in first_payload.lower()
        assert ".claude/skip-test-verification" in result["systemMessage"]

    def test_airflow_seeds_do_not_overwrite_existing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
        tmp_path: Path,
    ):
        """已存在的 .claude/skip-test-verification 不會被覆寫，message 也不提它。"""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        existing = claude_dir / "skip-test-verification"
        existing.write_text("user-custom reason\n", encoding="utf-8")

        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: _fake_git_result("https://github.com/apache/airflow.git"),
        )
        result = _run({"cwd": str(tmp_path)}, monkeypatch, capsys)

        assert existing.read_text(encoding="utf-8") == "user-custom reason\n"
        assert "skip-test-verification" not in result["systemMessage"]
        assert "airflow-aware" in result["systemMessage"]

    def test_non_airflow_repo_does_not_seed(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
        tmp_path: Path,
    ):
        """非 airflow repo 不會建立 .claude/ 或寫入任何種子檔。"""
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: _fake_git_result("https://github.com/some/other-repo.git"),
        )
        _run({"cwd": str(tmp_path)}, monkeypatch, capsys)
        assert not (tmp_path / ".claude" / "skip-test-verification").exists()


# ---------------------------------------------------------------------------
# Fake subprocess helpers
# ---------------------------------------------------------------------------


class _FakeCompletedProcess:
    def __init__(self, stdout: bytes, returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = b""


def _fake_git_result(url: str, returncode: int = 0) -> _FakeCompletedProcess:
    return _FakeCompletedProcess(stdout=url.encode(), returncode=returncode)


def _raise_file_not_found(*args, **kwargs):
    raise FileNotFoundError("git not found")


def _raise_timeout_expired(*args, **kwargs):
    raise subprocess.TimeoutExpired(cmd="git", timeout=3)
