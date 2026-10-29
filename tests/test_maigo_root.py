"""Tests for hooks._maigo_root."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hooks import _maigo_root


def git_init(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, capture_output=True, check=True)


def test_subdir_cwd_resolves_to_repo_root(tmp_path: Path):
    git_init(tmp_path)
    sub = tmp_path / "scripts" / "deep"
    sub.mkdir(parents=True)

    assert _maigo_root.maigo_root(sub) == tmp_path
    assert _maigo_root.maigo_dir(sub) == tmp_path / ".maigo"
    assert (
        _maigo_root.internal_log_dir(sub) == tmp_path / ".maigo" / "_internal" / "log"
    )


def test_cwd_inside_dot_maigo_resolves_to_repo_root(tmp_path: Path):
    git_init(tmp_path)
    inside = tmp_path / ".maigo" / "pr" / "1"
    inside.mkdir(parents=True)

    assert _maigo_root.maigo_root(inside) == tmp_path
    assert _maigo_root.maigo_root(tmp_path / ".maigo") == tmp_path


def test_worktree_cwd_resolves_to_worktree_root(tmp_path: Path):
    main = tmp_path / "main"
    main.mkdir()
    git_init(main)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "--allow-empty",
            "-m",
            "init",
        ],
        cwd=main,
        capture_output=True,
        check=True,
    )
    wt = tmp_path / "wt"
    subprocess.run(
        ["git", "worktree", "add", "-b", "topic", str(wt)],
        cwd=main,
        capture_output=True,
        check=True,
    )
    sub = wt / "pkg"
    sub.mkdir()

    assert _maigo_root.maigo_root(sub) == wt.resolve()
    assert _maigo_root.maigo_dir(sub) == wt.resolve() / ".maigo"


def test_non_git_dir_falls_back_to_cwd_and_strips_dot_maigo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(_maigo_root, "_git_toplevel", lambda cwd: None)
    plain = tmp_path / "plain"
    nested = plain / ".maigo" / ".maigo"
    nested.mkdir(parents=True)

    assert _maigo_root.maigo_root(plain) == plain
    assert _maigo_root.maigo_root(plain / ".maigo") == plain
    assert _maigo_root.maigo_root(nested) == plain


def test_git_missing_falls_back_to_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def no_git(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(_maigo_root.subprocess, "run", no_git)

    assert _maigo_root.maigo_root(tmp_path) == tmp_path


def test_unresolvable_cwd_with_nul_byte_fails_open():
    bad = "/tmp/repo\x00/sub"

    assert _maigo_root.maigo_root(bad) == Path(bad)
    assert _maigo_root.maigo_dir(bad) == Path(bad) / ".maigo"


def test_readable_log_path_prefers_new_then_legacy(tmp_path: Path):
    legacy = tmp_path / ".maigo" / "a.jsonl"
    legacy.parent.mkdir()
    legacy.write_text("legacy\n", encoding="utf-8")
    assert _maigo_root.readable_log_path(tmp_path, "a.jsonl") == legacy

    new = tmp_path / ".maigo" / "_internal" / "log" / "a.jsonl"
    new.parent.mkdir(parents=True)
    new.write_text("new\n", encoding="utf-8")
    assert _maigo_root.readable_log_path(tmp_path, "a.jsonl") == new

    assert (
        _maigo_root.readable_log_path(tmp_path, "none.jsonl")
        == tmp_path / ".maigo" / "_internal" / "log" / "none.jsonl"
    )
