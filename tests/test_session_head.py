"""Tests for hooks._session_head."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from hooks import _session_head

GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
}


def init_repo(path: Path) -> str:
    """Init a repo with one empty commit; return its HEAD sha."""
    subprocess.run(["git", "init"], cwd=path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=path,
        capture_output=True,
        env=GIT_ENV,
        check=True,
    )
    head = _session_head.current_head(path)
    assert head is not None
    return head


def commit_empty(path: Path, message: str) -> str:
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", message],
        cwd=path,
        capture_output=True,
        env=GIT_ENV,
        check=True,
    )
    head = _session_head.current_head(path)
    assert head is not None
    return head


# ---------------------------------------------------------------------------
# current_head
# ---------------------------------------------------------------------------


class TestCurrentHead:
    def test_returns_sha_in_repo(self, tmp_path: Path):
        head = init_repo(tmp_path)
        assert len(head) == 40

    def test_non_git_dir_returns_none(self, tmp_path: Path):
        assert _session_head.current_head(tmp_path) is None

    def test_repo_without_commits_returns_none(self, tmp_path: Path):
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        assert _session_head.current_head(tmp_path) is None

    def test_git_not_found_returns_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        def raise_not_found(*args, **kwargs):
            raise FileNotFoundError

        monkeypatch.setattr(subprocess, "run", raise_not_found)
        assert _session_head.current_head(tmp_path) is None


# ---------------------------------------------------------------------------
# record / read_records
# ---------------------------------------------------------------------------


class TestRecord:
    def test_writes_session_head(self, tmp_path: Path):
        head = init_repo(tmp_path)
        assert _session_head.record(tmp_path, "sess-1") is True
        stored = json.loads((tmp_path / _session_head.LOG_PATH).read_text())
        assert stored == {"sess-1": head}

    def test_second_session_appends(self, tmp_path: Path):
        head = init_repo(tmp_path)
        _session_head.record(tmp_path, "sess-1")
        _session_head.record(tmp_path, "sess-2")
        stored = _session_head.read_records(tmp_path / _session_head.LOG_PATH)
        assert stored == {"sess-1": head, "sess-2": head}

    def test_non_git_dir_records_nothing(self, tmp_path: Path):
        assert _session_head.record(tmp_path, "sess-1") is False
        assert not (tmp_path / _session_head.LOG_PATH).exists()

    def test_missing_session_id_records_nothing(self, tmp_path: Path):
        init_repo(tmp_path)
        assert _session_head.record(tmp_path, None) is False
        assert _session_head.record(tmp_path, "") is False
        assert not (tmp_path / _session_head.LOG_PATH).exists()

    def test_prunes_to_max_entries(self, tmp_path: Path):
        head = init_repo(tmp_path)
        path = tmp_path / _session_head.LOG_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        old = {f"old-{i}": head for i in range(_session_head.MAX_ENTRIES + 10)}
        path.write_text(json.dumps(old), encoding="utf-8")

        _session_head.record(tmp_path, "newest")
        stored = _session_head.read_records(path)
        assert len(stored) == _session_head.MAX_ENTRIES
        assert "newest" in stored
        assert "old-0" not in stored  # oldest dropped first

    def test_corrupted_file_is_replaced_not_raised(self, tmp_path: Path):
        head = init_repo(tmp_path)
        path = tmp_path / _session_head.LOG_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")

        assert _session_head.record(tmp_path, "sess-1") is True
        assert _session_head.read_records(path) == {"sess-1": head}

    def test_read_records_ignores_non_string_values(self, tmp_path: Path):
        path = tmp_path / "rec.json"
        path.write_text(json.dumps({"a": "sha", "b": 3, "c": None}), encoding="utf-8")
        assert _session_head.read_records(path) == {"a": "sha"}


# ---------------------------------------------------------------------------
# head_moved
# ---------------------------------------------------------------------------


class TestHeadMoved:
    def test_false_when_head_unchanged(self, tmp_path: Path):
        init_repo(tmp_path)
        _session_head.record(tmp_path, "sess-1")
        assert _session_head.head_moved(tmp_path, "sess-1") is False

    def test_true_after_a_commit(self, tmp_path: Path):
        init_repo(tmp_path)
        _session_head.record(tmp_path, "sess-1")
        commit_empty(tmp_path, "work done in this session")
        assert _session_head.head_moved(tmp_path, "sess-1") is True

    def test_false_without_a_record(self, tmp_path: Path):
        """No SessionStart record means "unknown" — must not force a test run."""
        init_repo(tmp_path)
        commit_empty(tmp_path, "committed by some earlier session")
        assert _session_head.head_moved(tmp_path, "sess-1") is False

    def test_false_for_a_different_session(self, tmp_path: Path):
        init_repo(tmp_path)
        _session_head.record(tmp_path, "sess-1")
        commit_empty(tmp_path, "work")
        assert _session_head.head_moved(tmp_path, "other-session") is False

    def test_false_without_session_id(self, tmp_path: Path):
        init_repo(tmp_path)
        _session_head.record(tmp_path, "sess-1")
        commit_empty(tmp_path, "work")
        assert _session_head.head_moved(tmp_path, None) is False

    def test_false_when_head_unreadable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        init_repo(tmp_path)
        _session_head.record(tmp_path, "sess-1")
        monkeypatch.setattr(_session_head, "current_head", lambda cwd: None)
        assert _session_head.head_moved(tmp_path, "sess-1") is False
