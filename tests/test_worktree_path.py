"""Tests for scripts.worktree_path — sibling worktree path + branch name computation."""

from __future__ import annotations

from pathlib import Path

from scripts import worktree_path as wp


class TestSlugReuse:
    """跟 tests/test_artifact_path.py 的 TestSlugify 同幾個案例，確認同一份正則邏輯。"""

    def test_lowercases_and_replaces_invalid_chars(self, tmp_path: Path):
        location = wp.compute_worktree_location(
            "maigo", "Fix/DAG Run_Stall!!", cwd=tmp_path
        )
        assert location.branch == "fix-dag-run_stall"

    def test_cjk_only_topic_falls_back_to_unnamed(self, tmp_path: Path):
        location = wp.compute_worktree_location("maigo", "繁體中文字", cwd=tmp_path)
        assert location.branch == "unnamed"

    def test_empty_topic_falls_back_to_unnamed(self, tmp_path: Path):
        location = wp.compute_worktree_location("maigo", "", cwd=tmp_path)
        assert location.branch == "unnamed"


class TestPathComposition:
    def test_path_is_sibling_of_cwd_named_repo_hyphen_slug(self, tmp_path: Path):
        checkout = tmp_path / "workspaces" / "maigo"
        checkout.mkdir(parents=True)

        location = wp.compute_worktree_location(
            "maigo", "Fix DAG run stall", cwd=checkout
        )

        assert location.path == str(tmp_path / "workspaces" / "maigo-fix-dag-run-stall")
        assert location.branch == "fix-dag-run-stall"

    def test_path_does_not_hardcode_any_fixed_root(self, tmp_path: Path):
        checkout_a = tmp_path / "somewhere" / "maigo"
        checkout_a.mkdir(parents=True)
        checkout_b = tmp_path / "elsewhere" / "deep" / "maigo"
        checkout_b.mkdir(parents=True)

        location_a = wp.compute_worktree_location("maigo", "x", cwd=checkout_a)
        location_b = wp.compute_worktree_location("maigo", "x", cwd=checkout_b)

        assert location_a.path == str(tmp_path / "somewhere" / "maigo-x")
        assert location_b.path == str(tmp_path / "elsewhere" / "deep" / "maigo-x")
        assert location_a.path != location_b.path
        assert "worktrees" not in location_a.path
        assert "worktrees" not in location_b.path


class TestCli:
    def test_prints_path_and_branch(self, tmp_path: Path, capsys):
        checkout = tmp_path / "maigo"
        checkout.mkdir()

        exit_code = wp.main(
            ["--repo", "maigo", "--topic", "Fix DAG run stall", "--cwd", str(checkout)]
        )

        captured = capsys.readouterr()
        assert exit_code == 0
        assert (
            captured.out.splitlines()[0]
            == f"path: {tmp_path / 'maigo-fix-dag-run-stall'}"
        )
        assert captured.out.splitlines()[1] == "branch: fix-dag-run-stall"
