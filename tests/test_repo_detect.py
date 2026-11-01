"""Tests for hooks.repo_detect."""

from __future__ import annotations

import io
import json
import os
import subprocess
from pathlib import Path

import pytest

import hooks.repo_detect as rd
from hooks import _session_head
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
            line
            for line in content.splitlines()
            if line.strip() and not line.startswith("#")
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


# ---------------------------------------------------------------------------
# ensure_maigo_ignored
# ---------------------------------------------------------------------------


GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
}


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=path,
        capture_output=True,
        env=GIT_ENV,
        check=True,
    )


class TestRecordsSessionHead:
    def test_records_head_for_plain_repo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        _init_repo(tmp_path)

        run_hook_main(
            rd, {"cwd": str(tmp_path), "session_id": "sess-1"}, monkeypatch, capsys
        )

        records = _session_head.read_records(tmp_path / _session_head.LOG_PATH)
        assert records == {"sess-1": _session_head.current_head(tmp_path)}

    def test_recorded_file_is_git_ignored(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        """The record must not make the working tree look dirty."""
        _init_repo(tmp_path)

        run_hook_main(
            rd, {"cwd": str(tmp_path), "session_id": "sess-1"}, monkeypatch, capsys
        )

        assert (tmp_path / _session_head.LOG_PATH).is_file()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        assert status.stdout.decode().strip() == ""


def _git_status(repo: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True,
        check=True,
    )
    return result.stdout.decode().strip()


class TestEnsureMaigoLinked:
    @staticmethod
    def _init_repo(path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        empty = path.parent / "gitconfig.empty"
        empty.write_text("", encoding="utf-8")
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
        monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(empty))
        path.mkdir()
        subprocess.run(["git", "init", "-q", str(path)], check=True)
        subprocess.run(
            ["git", "-C", str(path), "commit", "-q", "--allow-empty", "-m", "init"],
            env=GIT_ENV,
            check=True,
        )

    def test_hook_links_maigo_into_state_home_and_keeps_status_clean(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
    ) -> None:
        repo = tmp_path / "repo"
        self._init_repo(repo, monkeypatch)

        run_hook_main(rd, {"cwd": str(repo), "session_id": "s"}, monkeypatch, capsys)

        state_home = Path(os.environ["MAIGO_STATE_HOME"])
        assert (repo / ".maigo").is_symlink()
        assert (repo / ".maigo").resolve().is_relative_to(state_home.resolve())
        assert (repo / ".maigo/_internal/log/session-head.json").is_file()
        assert _git_status(repo) == ""

    def test_linked_worktree_shares_the_same_state_and_stays_clean(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
    ) -> None:
        repo = tmp_path / "repo"
        self._init_repo(repo, monkeypatch)
        linked = tmp_path / "linked"
        subprocess.run(
            ["git", "-C", str(repo), "worktree", "add", "-q", "-b", "wt", str(linked)],
            check=True,
        )

        run_hook_main(rd, {"cwd": str(repo), "session_id": "a"}, monkeypatch, capsys)
        run_hook_main(rd, {"cwd": str(linked), "session_id": "b"}, monkeypatch, capsys)

        assert (repo / ".maigo").resolve() == (linked / ".maigo").resolve()
        assert _git_status(repo) == ""
        assert _git_status(linked) == ""

    def test_real_maigo_directory_is_left_alone(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        repo = tmp_path / "repo"
        self._init_repo(repo, monkeypatch)
        (repo / ".maigo").mkdir()
        (repo / ".maigo" / "board.md").write_text("keep", encoding="utf-8")

        rd.ensure_maigo_linked(str(repo))

        assert not (repo / ".maigo").is_symlink()
        assert (repo / ".maigo" / "board.md").read_text(encoding="utf-8") == "keep"

    def test_fails_open_when_linking_raises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        def boom(cwd: str):
            raise PermissionError("read-only home")

        monkeypatch.setattr(rd, "ensure_link", boom)

        rd.ensure_maigo_linked(str(tmp_path))

    def test_noop_when_maigo_state_import_failed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        repo = tmp_path / "repo"
        self._init_repo(repo, monkeypatch)
        monkeypatch.setattr(rd, "ensure_link", None)

        rd.ensure_maigo_linked(str(repo))

        assert not (repo / ".maigo").exists()

    def test_noop_outside_git_repo(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        plain = tmp_path / "plain"
        plain.mkdir()

        rd.ensure_maigo_linked(str(plain))

        assert not (plain / ".maigo").exists()


class TestEnsureMaigoIgnored:
    """Exercises the real-git side effect, isolated from the machine's global config."""

    @staticmethod
    def _init_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Neutralise the machine's global/system git config (incl. any global
        # core.excludesFile) so check-ignore reflects only this repo.
        empty = tmp_path / "gitconfig.empty"
        empty.write_text("", encoding="utf-8")
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
        monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(empty))
        monkeypatch.setenv("HOME", str(tmp_path))
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)

    def test_writes_exclude_and_git_ignores_it(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        self._init_repo(tmp_path, monkeypatch)

        rd.ensure_maigo_ignored(str(tmp_path))

        exclude = tmp_path / ".git" / "info" / "exclude"
        assert ".maigo" in exclude.read_text(encoding="utf-8").split()
        # The whole point: git now actually ignores the dir.
        check = subprocess.run(
            ["git", "-C", str(tmp_path), "check-ignore", "-q", ".maigo"], check=False
        )
        assert check.returncode == 0

    def test_idempotent(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        self._init_repo(tmp_path, monkeypatch)

        rd.ensure_maigo_ignored(str(tmp_path))
        rd.ensure_maigo_ignored(str(tmp_path))

        exclude = tmp_path / ".git" / "info" / "exclude"
        assert exclude.read_text(encoding="utf-8").split().count(".maigo") == 1

    def test_noop_when_already_ignored_by_tracked_gitignore(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        self._init_repo(tmp_path, monkeypatch)
        (tmp_path / ".gitignore").write_text(".maigo/\n", encoding="utf-8")

        rd.ensure_maigo_ignored(str(tmp_path))

        exclude = tmp_path / ".git" / "info" / "exclude"
        text = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
        assert ".maigo" not in text.split()

    def test_symlinked_maigo_is_ignored_and_status_is_clean(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        repo = tmp_path / "repo"
        TestEnsureMaigoLinked._init_repo(repo, monkeypatch)
        central = tmp_path / "central"
        central.mkdir()
        (repo / ".maigo").symlink_to(central, target_is_directory=True)

        rd.ensure_maigo_ignored(str(repo))

        assert _git_status(repo) == ""

    def test_slash_rule_does_not_cover_a_symlink(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        repo = tmp_path / "repo"
        TestEnsureMaigoLinked._init_repo(repo, monkeypatch)
        central = tmp_path / "central"
        central.mkdir()
        (repo / ".maigo").symlink_to(central, target_is_directory=True)
        exclude = repo / ".git" / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        exclude.write_text(".maigo/\n", encoding="utf-8")
        assert _git_status(repo) == "?? .maigo"

        rd.ensure_maigo_ignored(str(repo))

        assert ".maigo" in exclude.read_text(encoding="utf-8").split()
        assert _git_status(repo) == ""

    def test_existing_slash_rule_still_covers_a_real_directory(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        self._init_repo(tmp_path, monkeypatch)
        exclude = tmp_path / ".git" / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        exclude.write_text(".maigo/\n", encoding="utf-8")
        (tmp_path / ".maigo").mkdir()

        rd.ensure_maigo_ignored(str(tmp_path))

        assert exclude.read_text(encoding="utf-8").split().count(".maigo") == 0

    def test_noop_outside_git_repo(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        empty = tmp_path / "gitconfig.empty"
        empty.write_text("", encoding="utf-8")
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
        monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(empty))
        monkeypatch.setenv("HOME", str(tmp_path))

        # tmp_path is not a git repo — must not raise and must not create one.
        rd.ensure_maigo_ignored(str(tmp_path))

        assert not (tmp_path / ".git").exists()
