"""Tests for scripts.maigo_state_sync — default-deny git channel for the central state root."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts import maigo_state_sync as sync
from scripts.maigo_state import STATE_HOME_ENV, get_state_root


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


def git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True
    )
    return proc.stdout


def write(root: Path, rel: str, text: str = "x\n") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def remote(tmp_path: Path) -> Path:
    path = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(path)], check=True)
    return path


@pytest.fixture
def root(remote: Path) -> Path:
    assert sync.main(["init", "--url", str(remote)]) == 0
    return get_state_root()


def clone_machine(
    remote: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    other = tmp_path / "machineB" / "Users" / "bob" / "state"
    other.parent.mkdir(parents=True)
    subprocess.run(["git", "clone", "-q", str(remote), str(other)], check=True)
    monkeypatch.setenv(STATE_HOME_ENV, str(other))
    return other


class TestAllowlist:
    def test_nothing_is_allowed_by_default(self, root: Path) -> None:
        assert sync.load_allowlist(root) == []
        text = (root / sync.EXCLUDE_REL).read_text(encoding="utf-8")
        assert "/*" in text.splitlines()
        assert "octo/pub" not in text

    @pytest.mark.parametrize(
        "entry",
        ["octo", "a/b/c", "_local/app", ".hidden/x", "a/..", "a/.git", "a b/c", ""],
    )
    def test_rejects_malformed_or_reserved_entries(self, entry: str) -> None:
        with pytest.raises(ValueError):
            sync.validate_allow_entry(entry)

    def test_allow_regenerates_gitignore(
        self, root: Path, capsys: pytest.CaptureFixture
    ) -> None:
        before = (root / sync.EXCLUDE_REL).read_text(encoding="utf-8")
        assert sync.main(["allow", "octo/pub"]) == 0
        after = (root / sync.EXCLUDE_REL).read_text(encoding="utf-8")
        assert after != before
        for rule in (
            "!/octo/",
            "/octo/*",
            "!/octo/pub/",
            "/octo/pub/_internal/*",
            "!/octo/pub/_internal/board/",
            "/octo/pub/_internal/board/*",
            "!/octo/pub/_internal/board/dropped.jsonl",
        ):
            assert rule in after.splitlines()
        assert sync.load_allowlist(root) == ["octo/pub"]
        assert sync.main(["allow", "octo/pub"]) == 0
        assert "already allowed" in capsys.readouterr().out

    def test_allow_rejects_reserved_owner(self, root: Path) -> None:
        assert sync.main(["allow", "_local/app"]) == 1
        assert sync.load_allowlist(root) == []


class TestDefaultDeny:
    def test_only_allowlisted_repo_is_added(self, root: Path) -> None:
        sync.main(["allow", "octo/pub"])
        write(root, "octo/pub/board.md")
        write(root, "octo/pub/_internal/board/dropped.jsonl")
        write(root, "octo/pub/_internal/board/snapshot.json")
        write(root, "octo/pub/_internal/log/a.log")
        write(root, "octo/pub/pr/1/bundle.zip")
        write(root, "octo/secret/pr/2/plan.md")
        write(root, "corp/private/board.md")
        write(root, "_migration-backup/20260101/x/f")
        write(root, "_local/app/board.md")
        git(root, "add", "-A")
        assert set(git(root, "ls-files").split()) == {
            ".gitattributes",
            "allowlist",
            "octo/pub/board.md",
            "octo/pub/_internal/board/dropped.jsonl",
        }

    def test_allowlist_outside_dir_is_not_listed_untracked(self, root: Path) -> None:
        write(root, "octo/pub/board.md")
        status = git(root, "status", "--porcelain", "--untracked-files=all")
        assert "octo" not in status


class TestPush:
    def test_pushes_allowlisted_content_only(self, root: Path, remote: Path) -> None:
        sync.main(["allow", "octo/pub"])
        write(root, "octo/pub/board.md")
        write(root, "octo/secret/plan.md")
        write(root, "octo/pub/_internal/log/a.log")
        assert sync.main(["push"]) == 0
        assert set(git(remote, "ls-tree", "-r", "--name-only", "main").split()) == {
            ".gitattributes",
            "allowlist",
            "octo/pub/board.md",
        }

    def test_forced_file_outside_allowlist_blocks_push(
        self, root: Path, remote: Path, capsys: pytest.CaptureFixture
    ) -> None:
        sync.main(["allow", "octo/pub"])
        write(root, "octo/pub/board.md")
        write(root, "octo/secret/plan.md")
        git(root, "add", "-f", "octo/secret/plan.md")
        assert sync.main(["push"]) == 1
        assert "octo/secret/plan.md" in capsys.readouterr().err
        assert git(remote, "branch", "--list").strip() == ""
        assert not sync.has_commits(root)

    def test_forced_internal_file_blocks_push(self, root: Path) -> None:
        sync.main(["allow", "octo/pub"])
        write(root, "octo/pub/_internal/log/a.log")
        git(root, "add", "-f", "octo/pub/_internal/log/a.log")
        assert sync.main(["push"]) == 1

    def test_forced_file_already_committed_blocks_push(
        self, root: Path, remote: Path
    ) -> None:
        sync.main(["allow", "octo/pub"])
        write(root, "octo/secret/plan.md")
        git(root, "add", "-f", ".")
        git(root, "commit", "-q", "-m", "oops")
        git(root, "rm", "-q", "--cached", "octo/secret/plan.md")
        assert sync.main(["push"]) == 1
        assert git(remote, "branch", "--list").strip() == ""

    def test_warns_on_absolute_paths_and_large_files_but_pushes(
        self, root: Path, remote: Path, capsys: pytest.CaptureFixture
    ) -> None:
        sync.main(["allow", "octo/pub"])
        write(root, "octo/pub/board.md", "see /Users/alice/repo/x\n")
        write(root, "octo/pub/review.md", "see https://example.com/home/page\n")
        write(root, "octo/pub/big.bin", "a" * sync.LARGE_FILE_BYTES)
        assert sync.main(["push"]) == 0
        captured = capsys.readouterr()
        out = captured.err
        assert "octo/pub/board.md: contains an absolute" in out
        assert "octo/pub/big.bin" in out and ">= 1 MB" in out
        assert "review.md" not in out
        assert "warning" not in captured.out
        assert "octo/pub/board.md" in git(
            remote, "ls-tree", "-r", "--name-only", "main"
        )

    def test_push_requires_init(self, capsys: pytest.CaptureFixture) -> None:
        assert sync.main(["push"]) == 1
        assert "init" in capsys.readouterr().err

    def test_nothing_to_commit_second_push_succeeds(self, root: Path) -> None:
        sync.main(["allow", "octo/pub"])
        write(root, "octo/pub/board.md")
        assert sync.main(["push"]) == 0
        assert sync.main(["push"]) == 0


class TestPull:
    def test_round_trip_between_two_machines(
        self,
        root: Path,
        remote: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sync.main(["allow", "octo/pub"])
        write(root, "octo/pub/board.md", "A\n")
        assert sync.main(["push"]) == 0
        other = clone_machine(remote, tmp_path, monkeypatch)
        write(other, "octo/pub/board.md", "A\nB\n")
        write(other, "corp/local/plan.md")
        assert sync.main(["push"]) == 0
        monkeypatch.setenv(STATE_HOME_ENV, str(root))
        assert sync.main(["pull"]) == 0
        assert (root / "octo/pub/board.md").read_text(encoding="utf-8") == "A\nB\n"
        assert not (root / "corp").exists()

    def test_conflict_stops_and_keeps_markers(
        self,
        root: Path,
        remote: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        sync.main(["allow", "octo/pub"])
        write(root, "octo/pub/board.md", "base\n")
        assert sync.main(["push"]) == 0
        other = clone_machine(remote, tmp_path, monkeypatch)
        write(other, "octo/pub/board.md", "from B\n")
        assert sync.main(["push"]) == 0
        monkeypatch.setenv(STATE_HOME_ENV, str(root))
        write(root, "octo/pub/board.md", "from A\n")
        capsys.readouterr()
        assert sync.main(["pull"]) == 1
        err = capsys.readouterr().err
        assert "octo/pub/board.md" in err and "UU octo/pub/board.md" in err
        text = (root / "octo/pub/board.md").read_text(encoding="utf-8")
        assert "<<<<<<<" in text and "from A" in text and "from B" in text
        assert (root / ".git" / "MERGE_HEAD").exists()
        assert sync.main(["pull"]) == 1

    def test_dropped_ledger_merges_without_conflict(
        self,
        root: Path,
        remote: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        ledger = "octo/pub/_internal/board/dropped.jsonl"
        sync.main(["allow", "octo/pub"])
        write(root, ledger, '{"url":"u0"}\n')
        assert sync.main(["push"]) == 0
        other = clone_machine(remote, tmp_path, monkeypatch)
        write(other, ledger, '{"url":"u0"}\n{"url":"uB"}\n')
        assert sync.main(["push"]) == 0
        monkeypatch.setenv(STATE_HOME_ENV, str(root))
        write(root, ledger, '{"url":"u0"}\n{"url":"uA"}\n')
        assert sync.main(["pull"]) == 0
        lines = (root / ledger).read_text(encoding="utf-8").splitlines()
        assert {'{"url":"uA"}', '{"url":"uB"}', '{"url":"u0"}'} == set(lines)

    def test_pull_from_empty_remote_is_not_an_error(
        self, root: Path, capsys: pytest.CaptureFixture
    ) -> None:
        assert sync.main(["pull"]) == 0
        assert "nothing to pull" in capsys.readouterr().out


class TestStatus:
    def test_not_a_git_repo_explains_and_exits_zero(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        assert sync.main(["status"]) == 0
        out = capsys.readouterr().out
        assert "not a git repository" in out
        assert "sync is not set up" in out

    def test_reports_ahead_behind_and_untracked_allowlist(
        self,
        root: Path,
        remote: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        sync.main(["allow", "octo/pub"])
        sync.main(["allow", "octo/later"])
        write(root, "octo/pub/board.md")
        assert sync.main(["push"]) == 0
        other = clone_machine(remote, tmp_path, monkeypatch)
        write(other, "octo/pub/board.md", "newer\n")
        assert sync.main(["push"]) == 0
        monkeypatch.setenv(STATE_HOME_ENV, str(root))
        write(root, "octo/later/board.md")
        capsys.readouterr()
        assert sync.main(["status", "--fetch"]) == 0
        out = capsys.readouterr().out
        assert "behind: 1" in out
        assert "ahead: 0" in out
        assert "untracked-allowlist: octo/later" in out
        assert "uncommitted: " in out

    def test_without_remote_says_so(self, capsys: pytest.CaptureFixture) -> None:
        assert sync.main(["init"]) == 0
        capsys.readouterr()
        assert sync.main(["status"]) == 0
        assert "remote: none" in capsys.readouterr().out


class TestInit:
    def test_creates_meta_files_without_allowing_anything(self, root: Path) -> None:
        for name in (sync.EXCLUDE_REL, ".gitattributes", "allowlist"):
            assert (root / name).is_file()
        assert not (root / ".gitignore").exists()
        assert "merge=union" in (root / ".gitattributes").read_text(encoding="utf-8")
        assert sync.load_allowlist(root) == []
        assert git(root, "remote", "get-url", "origin").strip()

    def test_is_idempotent_and_keeps_allowlist(self, root: Path, remote: Path) -> None:
        sync.main(["allow", "octo/pub"])
        assert sync.main(["init", "--url", str(remote)]) == 0
        assert sync.load_allowlist(root) == ["octo/pub"]

    def test_refuses_to_change_an_existing_remote(
        self, root: Path, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        assert sync.main(["init", "--url", str(tmp_path / "other.git")]) == 1
        assert "already points to" in capsys.readouterr().err


class TestFindDisallowedPaths:
    @pytest.mark.parametrize(
        ("path", "bad"),
        [
            ("allowlist", False),
            (".gitignore", True),
            (".gitattributes", False),
            ("octo/pub/board.md", False),
            ("octo/pub/_internal/board/dropped.jsonl", False),
            ("octo/pub/_internal/board/snapshot.json", True),
            ("octo/pub/_internal/log/a.log", True),
            ("octo/pub/x.zip", True),
            ("octo/other/board.md", True),
            ("octo/pub", True),
            ("_migration-backup/1/f", True),
            ("README.md", True),
        ],
    )
    def test_classifies_paths(self, path: str, bad: bool) -> None:
        assert bool(sync.find_disallowed_paths({path}, ["octo/pub"])) is bad


def conflict_between_two_machines(
    root: Path, remote: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    sync.main(["allow", "octo/pub"])
    write(root, "octo/pub/board.md", "base\n")
    assert sync.main(["push"]) == 0
    other = clone_machine(remote, tmp_path, monkeypatch)
    write(other, "octo/pub/board.md", "from B\n")
    assert sync.main(["push"]) == 0
    monkeypatch.setenv(STATE_HOME_ENV, str(root))
    write(root, "octo/pub/board.md", "from A\n")
    assert sync.main(["pull"]) == 1
    return other


class TestUnresolvedMerge:
    def test_push_is_refused_and_remote_is_unchanged(
        self,
        root: Path,
        remote: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        conflict_between_two_machines(root, remote, tmp_path, monkeypatch)
        before = git(remote, "rev-parse", "main")
        capsys.readouterr()
        assert sync.main(["push"]) == 1
        assert "merge is in progress" in capsys.readouterr().err
        assert git(remote, "rev-parse", "main") == before
        assert "<<<<<<<" not in git(remote, "show", "main:octo/pub/board.md")

    def test_push_is_refused_when_only_unmerged_index_entries_remain(
        self,
        root: Path,
        remote: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        conflict_between_two_machines(root, remote, tmp_path, monkeypatch)
        (root / ".git" / "MERGE_HEAD").unlink()
        assert sync.main(["push"]) == 1

    def test_pull_is_refused(
        self,
        root: Path,
        remote: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        conflict_between_two_machines(root, remote, tmp_path, monkeypatch)
        assert sync.main(["pull"]) == 1


class TestAllowlistMerge:
    def test_each_machine_allowing_a_different_repo_merges_cleanly(
        self,
        root: Path,
        remote: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sync.main(["allow", "octo/base"])
        assert sync.main(["push"]) == 0
        other = clone_machine(remote, tmp_path, monkeypatch)
        sync.main(["allow", "octo/from-b"])
        assert sync.main(["push"]) == 0
        monkeypatch.setenv(STATE_HOME_ENV, str(root))
        sync.main(["allow", "octo/from-a"])
        assert sync.main(["pull"]) == 0
        assert sync.load_allowlist(root) == ["octo/base", "octo/from-a", "octo/from-b"]
        assert "!/octo/from-b/" in (root / sync.EXCLUDE_REL).read_text(encoding="utf-8")
        assert other != root

    def test_first_status_after_clone_writes_the_exclude_rules(
        self,
        root: Path,
        remote: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sync.main(["allow", "octo/pub"])
        assert sync.main(["push"]) == 0
        other = clone_machine(remote, tmp_path, monkeypatch)
        assert "!/octo/pub/" not in (other / sync.EXCLUDE_REL).read_text(
            encoding="utf-8"
        )
        assert sync.main(["status"]) == 0
        assert "!/octo/pub/" in (other / sync.EXCLUDE_REL).read_text(encoding="utf-8")
        write(other, "corp/x/board.md")
        assert "corp" not in git(other, "status", "--porcelain")


class TestRound2Nits:
    def test_pull_warns_when_remote_has_only_other_branches(
        self, root: Path, remote: Path, capsys: pytest.CaptureFixture
    ) -> None:
        sync.main(["allow", "octo/pub"])
        write(root, "octo/pub/board.md")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "seed")
        git(root, "push", "-q", "origin", "HEAD:refs/heads/master")
        capsys.readouterr()
        assert sync.main(["pull"]) == 0
        captured = capsys.readouterr()
        assert "nothing to pull" in captured.out
        assert "origin/master" in captured.err

    def test_status_on_fresh_machine_with_remote_history_says_behind(
        self,
        root: Path,
        remote: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        sync.main(["allow", "octo/pub"])
        write(root, "octo/pub/board.md")
        assert sync.main(["push"]) == 0
        fresh = tmp_path / "fresh"
        monkeypatch.setenv(STATE_HOME_ENV, str(fresh))
        assert sync.main(["init", "--url", str(remote)]) == 0
        capsys.readouterr()
        assert sync.main(["status", "--fetch"]) == 0
        out = capsys.readouterr().out
        assert "behind: 1" in out
        assert "no local commit yet" in out

    def test_status_fetch_timeout_is_a_warning(
        self,
        root: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        def raise_timeout(*args: object, **kwargs: object) -> None:
            raise subprocess.TimeoutExpired(cmd="git", timeout=1)

        original = sync.run_git

        def run_git_with_slow_fetch(root: Path, *args: str, **kwargs: object):
            if args[0] == "fetch":
                raise_timeout()
            return original(root, *args, **kwargs)

        monkeypatch.setattr(sync, "run_git", run_git_with_slow_fetch)
        assert sync.main(["status", "--fetch"]) == 0
        assert "timed out" in capsys.readouterr().out
