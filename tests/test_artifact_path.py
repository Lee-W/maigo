"""Tests for scripts.artifact_path — `.maigo/` artifact naming + ownership guard."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts import artifact_path as ap


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-q", "-m", "init"], cwd=path, check=True
    )


# ---------------------------------------------------------------------------
# slugify()
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_empty_string_returns_none(self):
        assert ap.slugify("") is None

    def test_cjk_only_returns_none(self):
        # 全部字元都在 [a-z0-9._-] 之外，替換後收成單一 "-"，去頭尾後變空字串。
        assert ap.slugify("繁體中文字") is None

    def test_lowercases_and_replaces_invalid_chars(self):
        assert ap.slugify("Fix/DAG Run_Stall!!") == "fix-dag-run_stall"

    def test_truncates_to_40_chars(self):
        result = ap.slugify("a" * 50)
        assert result == "a" * 40
        assert len(result) == 40


# ---------------------------------------------------------------------------
# artifact_path() / legacy_path() — pure naming
# ---------------------------------------------------------------------------


class TestNaming:
    def test_artifact_path_format(self):
        assert (
            ap.artifact_path("plan", "fix-dag-run-stall")
            == ".maigo/plan-fix-dag-run-stall.md"
        )

    def test_legacy_path_format(self):
        assert ap.legacy_path("plan") == ".maigo/plan.md"

    def test_review_artifact_path_format(self):
        assert ap.artifact_path("review", "x") == ".maigo/review-x.md"

    def test_review_legacy_path_format(self):
        assert ap.legacy_path("review") == ".maigo/review.md"

    @pytest.mark.parametrize(
        "kind",
        [
            "not-a-kind",
            "../../../../tmp/pwned",
            "plan/../../../etc",
        ],
    )
    def test_unknown_kind_raises_value_error(self, kind):
        with pytest.raises(ValueError):
            ap.artifact_path(kind, "42")


# ---------------------------------------------------------------------------
# resolve_identifier() — 四級來源鏈
# ---------------------------------------------------------------------------


class TestResolveIdentifierChain:
    def test_level1_same_repo_url_uses_bare_number(self, tmp_path: Path):
        identifier = ap.resolve_identifier(
            tmp_path,
            url="https://github.com/Lee-W/maigo/issues/42",
            home_repo="Lee-W/maigo",
        )
        assert identifier == "42"

    def test_level1_cross_repo_url_prefixes_repo_name(self, tmp_path: Path):
        identifier = ap.resolve_identifier(
            tmp_path,
            url="https://github.com/other-owner/other-repo/pull/7",
            home_repo="Lee-W/maigo",
        )
        assert identifier == "other-repo-7"

    def test_level1_unparseable_url_falls_through_to_next_level(self, tmp_path: Path):
        target_dir = tmp_path / "my-scratch-dir"
        target_dir.mkdir()
        identifier = ap.resolve_identifier(target_dir, url="not a github url")
        assert identifier == "my-scratch-dir"

    def test_level2_uses_current_branch_slug(self, tmp_path: Path):
        _init_git_repo(tmp_path)
        subprocess.run(
            ["git", "checkout", "-q", "-b", "Fix/dag-run-stall"],
            cwd=tmp_path,
            check=True,
        )
        assert ap.resolve_identifier(tmp_path) == "fix-dag-run-stall"

    def test_level3_detached_head_uses_short_sha(self, tmp_path: Path):
        _init_git_repo(tmp_path)
        expected_sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        subprocess.run(
            ["git", "checkout", "-q", "--detach", "HEAD"], cwd=tmp_path, check=True
        )
        assert ap.resolve_identifier(tmp_path) == expected_sha

    def test_level4_non_git_repo_uses_cwd_dir_slug(self, tmp_path: Path):
        target_dir = tmp_path / "My Scratch Dir"
        target_dir.mkdir()
        assert ap.resolve_identifier(target_dir) == "my-scratch-dir"

    def test_level4_cjk_dir_name_falls_back_to_unnamed(self, tmp_path: Path):
        target_dir = tmp_path / "中文資料夾"
        target_dir.mkdir()
        assert ap.resolve_identifier(target_dir) == "unnamed"

    def test_level3_rebase_merge_uses_recorded_branch_name(self, tmp_path: Path):
        # merge backend（`git rebase` 預設）：`.git/rebase-merge/head-name`。
        _init_git_repo(tmp_path)
        subprocess.run(
            ["git", "checkout", "-q", "--detach", "HEAD"], cwd=tmp_path, check=True
        )
        rebase_merge_dir = tmp_path / ".git" / "rebase-merge"
        rebase_merge_dir.mkdir()
        (rebase_merge_dir / "head-name").write_text(
            "refs/heads/my-feature\n", encoding="utf-8"
        )
        assert ap.resolve_identifier(tmp_path) == "my-feature"

    def test_level3_rebase_apply_uses_recorded_branch_name(self, tmp_path: Path):
        # apply backend（`git rebase --apply`，patch-based）：
        # `.git/rebase-apply/head-name`。
        _init_git_repo(tmp_path)
        subprocess.run(
            ["git", "checkout", "-q", "--detach", "HEAD"], cwd=tmp_path, check=True
        )
        rebase_apply_dir = tmp_path / ".git" / "rebase-apply"
        rebase_apply_dir.mkdir()
        (rebase_apply_dir / "head-name").write_text(
            "refs/heads/my-feature\n", encoding="utf-8"
        )
        assert ap.resolve_identifier(tmp_path) == "my-feature"


# ---------------------------------------------------------------------------
# read_topic()
# ---------------------------------------------------------------------------


class TestReadTopic:
    def test_missing_file_returns_none(self, tmp_path: Path):
        assert ap.read_topic(tmp_path / "nope.md") is None

    def test_file_without_h1_returns_none(self, tmp_path: Path):
        p = tmp_path / "f.md"
        p.write_text("no heading here\n", encoding="utf-8")
        assert ap.read_topic(p) is None

    def test_normalizes_internal_whitespace(self, tmp_path: Path):
        p = tmp_path / "f.md"
        p.write_text("#   Plan:   fix   dag run stall  \n\nbody\n", encoding="utf-8")
        assert ap.read_topic(p) == "Plan: fix dag run stall"

    def test_permission_denied_raises_not_treated_as_new(self, tmp_path: Path):
        p = tmp_path / "f.md"
        p.write_text("# Plan: fix dag run stall\n", encoding="utf-8")
        p.chmod(0o000)
        try:
            with pytest.raises(PermissionError):
                ap.read_topic(p)
        finally:
            p.chmod(0o644)

    def test_binary_file_raises_not_treated_as_new(self, tmp_path: Path):
        p = tmp_path / "f.md"
        p.write_bytes(b"\xff\xfe\x00\x01binary-garbage-not-utf8")
        with pytest.raises(UnicodeDecodeError):
            ap.read_topic(p)


# ---------------------------------------------------------------------------
# resolve_for_write() — (c) 歸屬檢查，三態
# ---------------------------------------------------------------------------

_URL = "https://github.com/Lee-W/maigo/issues/42"
_HOME_REPO = "Lee-W/maigo"


class TestResolveForWrite:
    def test_new_when_target_path_absent(self, tmp_path: Path):
        result = ap.resolve_for_write(
            "plan",
            "Plan: fix dag run stall",
            url=_URL,
            home_repo=_HOME_REPO,
            cwd=tmp_path,
        )
        assert result.status == "new"
        assert result.path == ".maigo/plan-42.md"
        assert result.existing_topic is None
        assert result.suggested_path is None
        assert result.legacy_path is None

    def test_new_for_review_kind_when_target_path_absent(self, tmp_path: Path):
        result = ap.resolve_for_write(
            "review",
            "Review: fix dag run stall",
            url=_URL,
            home_repo=_HOME_REPO,
            cwd=tmp_path,
        )
        assert result.status == "new"
        assert result.path == ".maigo/review-42.md"
        assert result.existing_topic is None
        assert result.suggested_path is None
        assert result.legacy_path is None

    def test_new_when_existing_file_has_no_h1(self, tmp_path: Path):
        target = tmp_path / ".maigo" / "plan-42.md"
        target.parent.mkdir(parents=True)
        target.write_text("no h1 here\njust text\n", encoding="utf-8")
        result = ap.resolve_for_write(
            "plan",
            "Plan: fix dag run stall",
            url=_URL,
            home_repo=_HOME_REPO,
            cwd=tmp_path,
        )
        assert result.status == "new"
        assert result.path == ".maigo/plan-42.md"

    def test_same_topic_when_h1_matches(self, tmp_path: Path):
        target = tmp_path / ".maigo" / "plan-42.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Plan: fix dag run stall\n\nbody\n", encoding="utf-8")
        result = ap.resolve_for_write(
            "plan",
            "Plan: fix dag run stall",
            url=_URL,
            home_repo=_HOME_REPO,
            cwd=tmp_path,
        )
        assert result.status == "same_topic"
        assert result.path == ".maigo/plan-42.md"
        assert result.existing_topic == "Plan: fix dag run stall"
        assert result.suggested_path is None

    def test_conflict_when_h1_differs(self, tmp_path: Path):
        target = tmp_path / ".maigo" / "plan-42.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Plan: something else\n", encoding="utf-8")
        result = ap.resolve_for_write(
            "plan",
            "Plan: fix dag run stall",
            url=_URL,
            home_repo=_HOME_REPO,
            cwd=tmp_path,
        )
        assert result.status == "conflict"
        assert result.path is None
        assert result.existing_topic == "Plan: something else"
        assert result.suggested_path == ".maigo/plan-42-2.md"

    def test_legacy_exists_flag_when_old_fixed_name_present(self, tmp_path: Path):
        maigo_dir = tmp_path / ".maigo"
        maigo_dir.mkdir()
        (maigo_dir / "plan.md").write_text("# old plan\n", encoding="utf-8")
        result = ap.resolve_for_write(
            "plan",
            "Plan: fix dag run stall",
            url=_URL,
            home_repo=_HOME_REPO,
            cwd=tmp_path,
        )
        assert result.legacy_path == ".maigo/plan.md"

    def test_legacy_path_none_when_absent(self, tmp_path: Path):
        result = ap.resolve_for_write(
            "plan",
            "Plan: fix dag run stall",
            url=_URL,
            home_repo=_HOME_REPO,
            cwd=tmp_path,
        )
        assert result.legacy_path is None

    def test_permission_denied_target_raises_not_new(self, tmp_path: Path):
        # must-fix #1 repro：真實內容 → chmod 000 → 呼叫，必須拋錯，不能變成
        # 可覆寫的 "new"。
        target = tmp_path / ".maigo" / "plan-42.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Plan: something else\n", encoding="utf-8")
        target.chmod(0o000)
        try:
            with pytest.raises(PermissionError):
                ap.resolve_for_write(
                    "plan",
                    "Plan: fix dag run stall",
                    url=_URL,
                    home_repo=_HOME_REPO,
                    cwd=tmp_path,
                )
        finally:
            target.chmod(0o644)

    def test_path_traversal_kind_raises_value_error(self, tmp_path: Path):
        # must-fix #2 repro：帶 `../` 的 kind 必須拋錯，不能算出跳出 .maigo/
        # 的穿越路徑。
        with pytest.raises(ValueError):
            ap.resolve_for_write(
                "../../../../tmp/pwned",
                "whatever",
                url=_URL,
                home_repo=_HOME_REPO,
                cwd=tmp_path,
            )


# ---------------------------------------------------------------------------
# CLI (main()) — status/path 契約 ＋ exit 3
# ---------------------------------------------------------------------------


class TestCli:
    def test_new_prints_status_and_path_exit_0(self, tmp_path: Path, capsys):
        exit_code = ap.main(
            [
                "plan",
                "--topic",
                "Plan: fix dag run stall",
                "--url",
                _URL,
                "--repo",
                _HOME_REPO,
                "--cwd",
                str(tmp_path),
            ]
        )
        out = capsys.readouterr().out.splitlines()
        assert exit_code == 0
        assert out == ["status: new", "path: .maigo/plan-42.md"]

    def test_conflict_exits_3_and_omits_path(self, tmp_path: Path, capsys):
        target = tmp_path / ".maigo" / "plan-42.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Plan: something else\n", encoding="utf-8")
        exit_code = ap.main(
            [
                "plan",
                "--topic",
                "Plan: fix dag run stall",
                "--url",
                _URL,
                "--repo",
                _HOME_REPO,
                "--cwd",
                str(tmp_path),
            ]
        )
        out = capsys.readouterr().out.splitlines()
        assert exit_code == 3
        assert out == [
            "status: conflict",
            "conflict_owner: Plan: something else",
            "suggest: .maigo/plan-42-2.md",
        ]
        assert not any(line.startswith("path:") for line in out)

    def test_legacy_exists_line_appended(self, tmp_path: Path, capsys):
        maigo_dir = tmp_path / ".maigo"
        maigo_dir.mkdir()
        (maigo_dir / "plan.md").write_text("# old plan\n", encoding="utf-8")
        exit_code = ap.main(
            [
                "plan",
                "--topic",
                "Plan: fix dag run stall",
                "--url",
                _URL,
                "--repo",
                _HOME_REPO,
                "--cwd",
                str(tmp_path),
            ]
        )
        out = capsys.readouterr().out.splitlines()
        assert exit_code == 0
        assert out == [
            "status: new",
            "path: .maigo/plan-42.md",
            "legacy_exists: .maigo/plan.md",
        ]
