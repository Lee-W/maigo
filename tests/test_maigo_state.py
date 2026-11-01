"""Tests for scripts.maigo_state — central .maigo storage, identity, symlink, migrate."""

from __future__ import annotations

import hashlib
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts import maigo_state as ms


@pytest.fixture(autouse=True)
def isolated_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty = tmp_path / "gitconfig.empty"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(empty))
    monkeypatch.setenv("GIT_AUTHOR_NAME", "t")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@t")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "t")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@t")


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, check=True)


def make_repo(path: Path, **remotes: str) -> Path:
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "commit", "-q", "--allow-empty", "-m", "init")
    for name, url in remotes.items():
        git(path, "remote", "add", name, url)
    return path


def add_worktree(repo: Path, name: str) -> Path:
    path = repo.parent / name
    git(repo, "worktree", "add", "-q", "-b", name, str(path))
    return path


def snapshot(root: Path) -> str:
    """Hash of every path (incl. symlinks and empty dirs) and file content under *root*."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        digest.update(str(path.relative_to(root)).encode())
        if path.is_symlink():
            digest.update(os.readlink(path).encode())
        elif path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class TestStateRoot:
    def test_env_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("MAIGO_STATE_HOME", str(tmp_path / "custom"))
        assert ms.get_state_root() == tmp_path / "custom"

    def test_default_is_under_home(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("MAIGO_STATE_HOME")
        monkeypatch.setenv("HOME", str(tmp_path))
        assert ms.state_root() == tmp_path / ".local/share/maigo/state"


class TestParseRemoteIdentity:
    @pytest.mark.parametrize(
        "url",
        [
            "git@github.com:apache/airflow.git",
            "git@github.com:apache/airflow",
            "ssh://git@github.com/apache/airflow.git",
            "https://github.com/apache/airflow",
            "https://github.com/apache/airflow.git/",
            "https://user:token@gitlab.example.com/apache/airflow.git",
            "ssh://u@192.168.0.1:20022/apache/airflow.git",
        ],
    )
    def test_all_forms_give_same_identity(self, url: str):
        assert ms.parse_remote_identity(url) == "apache/airflow"

    def test_takes_last_two_segments(self):
        assert ms.parse_remote_identity("ssh://u@nas:22/volume1/git/mujica.git") == (
            "git/mujica"
        )

    @pytest.mark.parametrize(
        "url", ["", "nourl", "/abs/local/path", "../rel/path", "https://h/onlyone"]
    )
    def test_unusable_urls_give_none(self, url: str):
        assert ms.parse_remote_identity(url) is None

    def test_rejects_parent_traversal_segments(self):
        assert ms.parse_remote_identity("git@h:../repo.git") is None


class TestResolveIdentity:
    def test_ssh_and_https_clones_share_identity(self, tmp_path: Path):
        ssh = make_repo(tmp_path / "a", origin="git@github.com:Lee-W/maigo.git")
        https = make_repo(tmp_path / "b", origin="https://github.com/Lee-W/maigo")
        assert ms.resolve_identity(ssh) == ms.resolve_identity(https) == "Lee-W/maigo"

    def test_upstream_wins_over_origin(self, tmp_path: Path):
        repo = make_repo(
            tmp_path / "fork",
            origin="ssh://git@github.com/astronomer/airflow.git",
            upstream="git@github.com:apache/airflow.git",
        )
        assert ms.resolve_identity(repo) == "apache/airflow"

    def test_unparseable_upstream_falls_back_to_origin(self, tmp_path: Path):
        repo = make_repo(
            tmp_path / "r", upstream="/some/local/path", origin="git@h:me/x.git"
        )
        assert ms.resolve_identity(repo) == "me/x"

    def test_no_remote_uses_local_basename(self, tmp_path: Path):
        repo = make_repo(tmp_path / "standup")
        assert ms.resolve_identity(repo) == "_local/standup"

    def test_linked_worktree_shares_main_worktree_identity(self, tmp_path: Path):
        repo = make_repo(tmp_path / "standup")
        linked = add_worktree(repo, "feature")
        assert ms.resolve_identity(linked) == "_local/standup"

    def test_subdirectory_resolves_like_root(self, tmp_path: Path):
        repo = make_repo(tmp_path / "r", origin="git@h:me/x.git")
        (repo / "sub").mkdir()
        assert ms.resolve_identity(repo / "sub") == "me/x"

    def test_not_a_repo_gives_none(self, tmp_path: Path):
        plain = tmp_path / "plain"
        plain.mkdir()
        assert ms.resolve_identity(plain) is None


class TestEnsureLink:
    def test_creates_target_and_symlink(self, tmp_path: Path):
        repo = make_repo(tmp_path / "r", origin="git@h:me/x.git")

        result = ms.ensure_link(repo)

        target = ms.get_state_root() / "me" / "x"
        assert result.status == ms.STATUS_LINKED
        assert (repo / ".maigo").is_symlink()
        assert (repo / ".maigo").resolve() == target.resolve()
        assert target.is_dir()

    def test_idempotent(self, tmp_path: Path):
        repo = make_repo(tmp_path / "r", origin="git@h:me/x.git")
        ms.ensure_link(repo)

        assert ms.ensure_link(repo).status == ms.STATUS_ALREADY_LINKED

    def test_existing_real_directory_is_not_touched(self, tmp_path: Path):
        repo = make_repo(tmp_path / "r", origin="git@h:me/x.git")
        write(repo / ".maigo" / "board.md", "keep me")
        before = snapshot(repo / ".maigo")

        result = ms.ensure_link(repo)

        assert result.status == ms.STATUS_NEEDS_MIGRATION
        assert not (repo / ".maigo").is_symlink()
        assert snapshot(repo / ".maigo") == before
        assert not (ms.get_state_root() / "me").exists()

    def test_symlink_to_wrong_target_is_reported_not_replaced(self, tmp_path: Path):
        repo = make_repo(tmp_path / "r", origin="git@h:me/x.git")
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        (repo / ".maigo").symlink_to(elsewhere, target_is_directory=True)

        result = ms.ensure_link(repo)

        assert result.status == ms.STATUS_WRONG_TARGET
        assert (repo / ".maigo").resolve() == elsewhere.resolve()

    def test_regular_file_blocks(self, tmp_path: Path):
        repo = make_repo(tmp_path / "r", origin="git@h:me/x.git")
        write(repo / ".maigo", "oops")

        assert ms.ensure_link(repo).status == ms.STATUS_BLOCKED
        assert (repo / ".maigo").read_text(encoding="utf-8") == "oops"

    def test_worktrees_share_one_target(self, tmp_path: Path):
        repo = make_repo(tmp_path / "r", origin="git@h:me/x.git")
        linked = add_worktree(repo, "feature")

        ms.ensure_link(repo)
        ms.ensure_link(linked)
        write(repo / ".maigo" / "pr" / "1" / "plan.md", "# shared")

        assert (linked / ".maigo" / "pr" / "1" / "plan.md").read_text(
            encoding="utf-8"
        ) == "# shared"

    def test_not_a_repo(self, tmp_path: Path):
        plain = tmp_path / "plain"
        plain.mkdir()

        assert ms.ensure_link(plain).status == ms.STATUS_NOT_A_REPO
        assert not (plain / ".maigo").exists()


class TestMigrate:
    NOW = datetime(2026, 11, 2, 1, 2, 3, tzinfo=timezone.utc)

    def make_two_worktrees(self, tmp_path: Path) -> tuple[Path, Path]:
        repo = make_repo(tmp_path / "r", origin="git@h:me/x.git")
        linked = add_worktree(repo, "feature")
        return repo, linked

    def test_merges_distinct_files_and_replaces_with_symlinks(self, tmp_path: Path):
        repo, linked = self.make_two_worktrees(tmp_path)
        write(repo / ".maigo" / "board.md", "board")
        write(repo / ".maigo" / "pr" / "1" / "plan.md", "plan-1")
        write(linked / ".maigo" / "pr" / "2" / "plan.md", "plan-2")
        write(linked / ".maigo" / "pr" / "1" / "plan.md", "plan-1")

        plan = ms.build_migration_plan(repo)
        assert plan is not None
        assert ms.apply_migration(plan, now=self.NOW) == []

        target = ms.get_state_root() / "me" / "x"
        assert (target / "board.md").read_text(encoding="utf-8") == "board"
        assert (target / "pr/2/plan.md").read_text(encoding="utf-8") == "plan-2"
        assert (repo / ".maigo").is_symlink()
        assert (linked / ".maigo").is_symlink()
        backups = sorted((ms.get_state_root() / "_migration-backup").iterdir())
        assert [b.name for b in backups] == ["20261102T010203Z"]
        stored = sorted(p.name for p in backups[0].iterdir())
        assert stored == ["0-r", "1-feature"]
        assert (backups[0] / "1-feature/pr/2/plan.md").read_text(
            encoding="utf-8"
        ) == "plan-2"

    def test_conflicting_files_are_listed_and_nothing_changes(self, tmp_path: Path):
        repo, linked = self.make_two_worktrees(tmp_path)
        write(repo / ".maigo" / "board.md", "from main")
        write(linked / ".maigo" / "board.md", "from feature")
        before = (snapshot(repo / ".maigo"), snapshot(linked / ".maigo"))

        plan = ms.build_migration_plan(repo)
        assert plan is not None
        assert plan.has_conflicts
        assert [w.conflicts for w in plan.worktrees if w.conflicts] == [["board.md"]]
        assert ms.apply_migration(plan, now=self.NOW)
        assert (snapshot(repo / ".maigo"), snapshot(linked / ".maigo")) == before
        assert not ms.get_state_root().joinpath("me").exists()

    def test_conflict_with_existing_central_file(self, tmp_path: Path):
        repo = make_repo(tmp_path / "r", origin="git@h:me/x.git")
        write(repo / ".maigo" / "board.md", "local")
        write(ms.get_state_root() / "me" / "x" / "board.md", "central")

        plan = ms.build_migration_plan(repo)
        assert plan is not None
        assert plan.worktrees[0].conflicts == ["board.md"]

    def test_nested_maigo_is_reported_and_kept(self, tmp_path: Path):
        repo = make_repo(tmp_path / "r", origin="git@h:me/x.git")
        write(repo / ".maigo" / "board.md", "board")
        write(repo / ".maigo" / ".maigo" / "stray.md", "stray")

        plan = ms.build_migration_plan(repo)
        assert plan is not None
        assert plan.worktrees[0].nested == [".maigo"]
        assert ms.apply_migration(plan, now=self.NOW) == []

        target = ms.get_state_root() / "me" / "x"
        assert (target / ".maigo" / "stray.md").read_text(encoding="utf-8") == "stray"

    def test_dry_run_changes_nothing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ):
        repo, linked = self.make_two_worktrees(tmp_path)
        write(repo / ".maigo" / "board.md", "board")
        write(linked / ".maigo" / "pr" / "2" / "plan.md", "plan-2")
        (linked / ".maigo" / "empty").mkdir()
        before = (snapshot(tmp_path), snapshot(ms.get_state_root()))

        assert ms.main(["migrate", "--cwd", str(repo)]) == 0

        assert (snapshot(tmp_path), snapshot(ms.get_state_root())) == before
        assert "mode: dry-run" in capsys.readouterr().out

    def test_cli_apply_exits_2_on_conflict_without_writing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ):
        repo, linked = self.make_two_worktrees(tmp_path)
        write(repo / ".maigo" / "board.md", "a")
        write(linked / ".maigo" / "board.md", "b")
        before = snapshot(tmp_path)

        assert ms.main(["migrate", "--cwd", str(repo), "--apply"]) == 2

        assert snapshot(tmp_path) == before
        assert "conflict: board.md" in capsys.readouterr().out

    def test_cli_apply_is_idempotent(self, tmp_path: Path):
        repo = make_repo(tmp_path / "r", origin="git@h:me/x.git")
        write(repo / ".maigo" / "board.md", "board")

        assert ms.main(["migrate", "--cwd", str(repo), "--apply"]) == 0
        after_first = snapshot(ms.get_state_root() / "me")
        assert ms.main(["migrate", "--cwd", str(repo), "--apply"]) == 0

        assert snapshot(ms.get_state_root() / "me") == after_first
        assert (repo / ".maigo").is_symlink()

    def test_missing_maigo_in_a_worktree_is_left_alone(self, tmp_path: Path):
        repo, linked = self.make_two_worktrees(tmp_path)
        write(repo / ".maigo" / "board.md", "board")

        plan = ms.build_migration_plan(repo)
        assert plan is not None
        assert ms.apply_migration(plan, now=self.NOW) == []

        assert not (linked / ".maigo").exists()

    def test_not_a_repo_exits_1(self, tmp_path: Path):
        plain = tmp_path / "plain"
        plain.mkdir()

        assert ms.main(["migrate", "--cwd", str(plain)]) == 1


class TestMigrateKindConflicts:
    def make_two_worktrees(self, tmp_path: Path) -> tuple[Path, Path]:
        repo = make_repo(tmp_path / "r", origin="git@h:me/x.git")
        return repo, add_worktree(repo, "feature")

    def test_file_vs_directory_across_worktrees_is_a_conflict(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ):
        repo, linked = self.make_two_worktrees(tmp_path)
        write(repo / ".maigo" / "x" / "f", "a")
        write(linked / ".maigo" / "x", "b")
        before = snapshot(tmp_path)

        assert ms.main(["migrate", "--cwd", str(repo), "--apply"]) == 2

        assert snapshot(tmp_path) == before
        assert "conflict: x" in capsys.readouterr().out

    def test_file_vs_existing_central_directory_is_a_conflict(self, tmp_path: Path):
        repo = make_repo(tmp_path / "r", origin="git@h:me/x.git")
        write(repo / ".maigo" / "x", "b")
        write(ms.get_state_root() / "me" / "x" / "x" / "f", "a")

        plan = ms.build_migration_plan(repo)

        assert plan is not None
        assert plan.worktrees[0].conflicts == ["x"]

    def test_failed_verification_keeps_the_original_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        repo = make_repo(tmp_path / "r", origin="git@h:me/x.git")
        write(repo / ".maigo" / "board.md", "board")
        plan = ms.build_migration_plan(repo)
        assert plan is not None
        monkeypatch.setattr(ms, "_copy_entry", lambda source, destination: None)

        errors = ms.apply_migration(plan)

        assert errors and "board.md" in errors[0]
        assert not (repo / ".maigo").is_symlink()
        assert (repo / ".maigo" / "board.md").read_text(encoding="utf-8") == "board"

    def test_central_content_changed_before_swap_keeps_the_original(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        repo = make_repo(tmp_path / "r", origin="git@h:me/x.git")
        write(repo / ".maigo" / "board.md", "board")
        plan = ms.build_migration_plan(repo)
        assert plan is not None
        real_copy = ms._copy_entry

        def copy_then_corrupt(source: Path, destination: Path) -> None:
            real_copy(source, destination)
            destination.write_text("tampered", encoding="utf-8")

        monkeypatch.setattr(ms, "_copy_entry", copy_then_corrupt)

        assert ms.apply_migration(plan)
        assert (repo / ".maigo").is_dir() and not (repo / ".maigo").is_symlink()


class TestTrustedLink:
    def test_symlink_outside_state_root_is_rejected(self, tmp_path: Path):
        outside = tmp_path / "outside"
        outside.mkdir()
        (tmp_path / ".maigo").symlink_to(outside, target_is_directory=True)

        with pytest.raises(ValueError, match="outside the maigo state root"):
            ms.check_maigo_link_trusted(tmp_path / ".maigo")

    def test_symlink_inside_state_root_real_dir_and_missing_are_allowed(
        self, tmp_path: Path
    ):
        inside = ms.get_state_root() / "o" / "r"
        inside.mkdir(parents=True)
        (tmp_path / "a").symlink_to(inside, target_is_directory=True)
        (tmp_path / "b").mkdir()

        for name in ("a", "b", "missing"):
            ms.check_maigo_link_trusted(tmp_path / name)


class TestCli:
    def test_help_exits_zero(self, capsys: pytest.CaptureFixture):
        with pytest.raises(SystemExit) as exc:
            ms.main(["--help"])
        assert exc.value.code == 0

    def test_identity_prints_identity_and_path(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ):
        repo = make_repo(tmp_path / "r", origin="git@h:me/x.git")

        assert ms.main(["identity", "--cwd", str(repo)]) == 0

        out = capsys.readouterr().out
        assert "identity: me/x" in out
        assert str(ms.get_state_root() / "me" / "x") in out

    def test_link_exit_code_reflects_status(self, tmp_path: Path):
        repo = make_repo(tmp_path / "r", origin="git@h:me/x.git")
        assert ms.main(["link", "--cwd", str(repo)]) == 0
        real = make_repo(tmp_path / "real", origin="git@h:me/y.git")
        write(real / ".maigo" / "a", "a")
        assert ms.main(["link", "--cwd", str(real)]) == 1
