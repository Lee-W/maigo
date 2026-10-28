"""Tests for scripts.pr_owner — PR author vs current user (mine / others)."""

from __future__ import annotations

import subprocess

import pytest

from scripts import pr_owner

URL = "https://github.com/o/r/pull/7"


def _completed(stdout: str = "", returncode: int = 0, stderr: str = ""):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


def _stub_gh(monkeypatch, *, user="Lee-W", author="Lee-W", user_rc=0, author_rc=0):
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[1] == "api":
            return _completed(user, user_rc, "boom: user" if user_rc else "")
        return _completed(author, author_rc, "boom: view" if author_rc else "")

    monkeypatch.setattr(pr_owner.subprocess, "run", fake_run)
    return calls


class TestResolveOwner:
    def test_same_login_is_mine(self, monkeypatch):
        _stub_gh(monkeypatch)
        assert pr_owner.resolve_owner(URL) == "mine"

    def test_case_insensitive_is_mine(self, monkeypatch):
        _stub_gh(monkeypatch, user="lee-w", author="Lee-W")
        assert pr_owner.resolve_owner(URL) == "mine"

    def test_different_login_is_others(self, monkeypatch):
        _stub_gh(monkeypatch, author="someone")
        assert pr_owner.resolve_owner(URL) == "others"

    def test_user_lookup_failure_raises(self, monkeypatch):
        _stub_gh(monkeypatch, user_rc=1)
        with pytest.raises(pr_owner.OwnerUnknownError, match="boom: user"):
            pr_owner.resolve_owner(URL)

    def test_pr_view_failure_raises(self, monkeypatch):
        _stub_gh(monkeypatch, author_rc=1)
        with pytest.raises(pr_owner.OwnerUnknownError, match="boom: view"):
            pr_owner.resolve_owner(URL)

    def test_empty_output_raises(self, monkeypatch):
        _stub_gh(monkeypatch, author="")
        with pytest.raises(pr_owner.OwnerUnknownError):
            pr_owner.resolve_owner(URL)

    def test_null_login_raises(self, monkeypatch):
        _stub_gh(monkeypatch, author="null")
        with pytest.raises(pr_owner.OwnerUnknownError):
            pr_owner.resolve_owner(URL)

    def test_explicit_you_skips_user_lookup(self, monkeypatch):
        calls = _stub_gh(monkeypatch, author="Lee-W")
        assert pr_owner.resolve_owner(URL, you="lee-w") == "mine"
        assert all(cmd[1] != "api" for cmd in calls)

    def test_oserror_raises(self, monkeypatch):
        def boom(cmd, **kwargs):
            raise FileNotFoundError("gh")

        monkeypatch.setattr(pr_owner.subprocess, "run", boom)
        with pytest.raises(pr_owner.OwnerUnknownError):
            pr_owner.resolve_owner(URL)


class TestCli:
    def test_success_prints_three_lines(self, monkeypatch, capsys):
        _stub_gh(monkeypatch, author="other")
        assert pr_owner.main(["--url", URL]) == 0
        assert capsys.readouterr().out.splitlines() == [
            "owner: others",
            "author: other",
            "you: Lee-W",
        ]

    def test_failure_exits_1_and_points_to_owner_flag(self, monkeypatch, capsys):
        _stub_gh(monkeypatch, author_rc=1)
        assert pr_owner.main(["--url", URL]) == 1
        assert "--owner" in capsys.readouterr().err
