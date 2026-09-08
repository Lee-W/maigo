"""Tests for scripts.migrate_legacy_artifacts.

全程只對 `tmp_path` 底下的假 repo 操作，測試不得觸碰任何真實的其他 12 個
repo——這條規則寫在這裡是提醒之後有人為了「更真實」而把測試指向使用者本機
真實 repo 路徑：**不要**。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from scripts import migrate_legacy_artifacts as mla
from scripts.maigo_dir_catalog import scan


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_repo(tmp_path: Path, name: str = "fake-repo") -> Path:
    repo = tmp_path / name
    (repo / ".maigo").mkdir(parents=True)
    return repo


class TestPlanMigration:
    def test_legacy_file_with_h1_uses_slugified_h1_as_identifier(self, tmp_path: Path):
        repo = _make_repo(tmp_path)
        (repo / ".maigo" / "plan.md").write_text(
            "# Fix DAG run stall\n\nbody\n", encoding="utf-8"
        )

        catalog = scan(repo / ".maigo")
        actions = mla.plan_migration(repo, catalog)

        assert len(actions) == 1
        assert actions[0].old_path == ".maigo/plan.md"
        assert actions[0].new_path == ".maigo/plan-fix-dag-run-stall.md"
        assert actions[0].disambiguated is False

    def test_legacy_file_missing_h1_falls_back_to_filename_stem(self, tmp_path: Path):
        repo = _make_repo(tmp_path)
        (repo / ".maigo" / "review-rubric.md").write_text(
            "no heading here, just body text\n", encoding="utf-8"
        )

        catalog = scan(repo / ".maigo")
        actions = mla.plan_migration(repo, catalog)

        assert len(actions) == 1
        assert actions[0].old_path == ".maigo/review-rubric.md"
        # 檔名 stem 剛好等於 kind 本身（"review-rubric"），去疊字後變空字串，
        # 退到 "unnamed"——不是 "review-rubric-review-rubric.md"（那是本次修
        # 掉的疊字 bug；見 TestKindStutterRegressions）。
        assert actions[0].new_path == ".maigo/review-rubric-unnamed.md"

    def test_new_style_named_file_is_not_migrated(self, tmp_path: Path):
        repo = _make_repo(tmp_path)
        (repo / ".maigo" / "plan-x.md").write_text("# Plan: X\n", encoding="utf-8")

        catalog = scan(repo / ".maigo")
        actions = mla.plan_migration(repo, catalog)

        assert actions == []

    def test_ad_hoc_named_file_is_not_migrated(self, tmp_path: Path):
        repo = _make_repo(tmp_path)
        (repo / ".maigo" / "local-model-dispatch-plan.md").write_text(
            "# Local model dispatch\n", encoding="utf-8"
        )

        catalog = scan(repo / ".maigo")
        actions = mla.plan_migration(repo, catalog)

        assert actions == []

    def test_target_conflict_with_existing_new_style_file_gets_suffix(
        self, tmp_path: Path
    ):
        repo = _make_repo(tmp_path)
        (repo / ".maigo" / "plan.md").write_text(
            "# Fix DAG run stall\n", encoding="utf-8"
        )
        # 該 repo 已有一份新命名檔案，恰好撞到遷移後會算出的目標檔名。
        (repo / ".maigo" / "plan-fix-dag-run-stall.md").write_text(
            "# Fix DAG run stall (already migrated by someone else)\n",
            encoding="utf-8",
        )

        catalog = scan(repo / ".maigo")
        actions = mla.plan_migration(repo, catalog)

        assert len(actions) == 1
        assert actions[0].new_path == ".maigo/plan-fix-dag-run-stall-2.md"
        assert actions[0].disambiguated is True

    def test_two_legacy_files_colliding_on_same_h1_both_disambiguate(
        self, tmp_path: Path
    ):
        # 兩份不同 kind 的舊檔理論上不會撞名（kind 前綴不同），但同 kind 不會發生
        # （每個 kind 只有一份舊固定檔名）；這裡改用「已存在的第三方檔案」模擬
        # 連續撞名，驗證尾碼會遞增而不是卡在 -2。
        repo = _make_repo(tmp_path)
        (repo / ".maigo" / "plan.md").write_text("# X\n", encoding="utf-8")
        (repo / ".maigo" / "plan-x.md").write_text("taken\n", encoding="utf-8")
        (repo / ".maigo" / "plan-x-2.md").write_text("also taken\n", encoding="utf-8")

        catalog = scan(repo / ".maigo")
        actions = mla.plan_migration(repo, catalog)

        assert actions[0].new_path == ".maigo/plan-x-3.md"
        assert actions[0].disambiguated is True

    def test_no_legacy_files_returns_empty_list(self, tmp_path: Path):
        repo = _make_repo(tmp_path)
        (repo / ".maigo" / "board.md").write_text("# Work Board\n", encoding="utf-8")

        catalog = scan(repo / ".maigo")
        assert mla.plan_migration(repo, catalog) == []


class TestKindStutterRegressions:
    """回歸樣本：13 個真實 repo 跑 dry-run 時，11 筆遷移裡有 8 筆撞到
    `<kind>-<kind>-...` 疊字檔名。真實 H1 內容無法取得（不讀真實 repo），
    這裡用會 slugify 出同樣疊字前綴＋同樣截斷邊界情境的合成 H1 重建每一筆，
    逐一驗證修好後不再疊字、且截斷（真的命中 40 字元上限時）會退到完整的
    `-` 分段邊界。
    """

    def _migrate_one(
        self, tmp_path: Path, legacy_name: str, h1: str, repo_name: str | None = None
    ) -> str:
        # 預設用 h1 的 hash 湊出唯一 repo 名，避免同一個 tmp_path 底下多次
        # 呼叫（例如批次跑全部 8 筆樣本的測試）撞到同名目錄。
        unique = repo_name or f"{legacy_name.replace('.', '-')}-{abs(hash(h1)) % 10000}"
        repo = _make_repo(tmp_path, unique)
        (repo / ".maigo" / legacy_name).write_text(h1 + "\n", encoding="utf-8")
        catalog = scan(repo / ".maigo")
        actions = mla.plan_migration(repo, catalog)
        assert len(actions) == 1
        return actions[0].new_path

    def test_main_blog_plan_no_stutter(self, tmp_path: Path):
        new_path = self._migrate_one(
            tmp_path, "plan.md", "# Plan: Stats — Pelican stat dual mode (EN)"
        )
        assert new_path == ".maigo/plan-stats-pelican-stat-dual-mode-en.md"

    def test_pelican_osm_plan_no_stutter(self, tmp_path: Path):
        new_path = self._migrate_one(
            tmp_path, "plan.md", "# Plan: Emoji icon pin for place markers"
        )
        assert new_path == ".maigo/plan-emoji-icon-pin-for-place-markers.md"

    def test_ring_plan_no_stutter(self, tmp_path: Path):
        new_path = self._migrate_one(tmp_path, "plan.md", "# Plan: Ring kitty focuser")
        assert new_path == ".maigo/plan-ring-kitty-focuser.md"

    def test_attila_review_rubric_no_stutter_and_truncation_lands_on_boundary(
        self, tmp_path: Path
    ):
        new_path = self._migrate_one(
            tmp_path,
            "review-rubric.md",
            "# Review rubric — feat: pagination and modernization",
        )
        assert new_path == ".maigo/review-rubric-feat-pagination-and.md"
        # 截斷邊界驗證：不能落在字中間（例如疊字修掉之前真實遷移出來的
        # "...-and-modern.md" 就是這樣被 40 字元上限硬切出來的）。
        stem = Path(new_path).stem
        assert not stem.endswith("-modern")

    def test_airflow_pr_comments_ack_channel_no_stutter_and_boundary(
        self, tmp_path: Path
    ):
        new_path = self._migrate_one(
            tmp_path,
            "pr-comments.md",
            "# PR comments — add producer-side ack channel",
        )
        assert new_path == ".maigo/pr-comments-add-producer-side-ack.md"
        assert not Path(new_path).stem.endswith("-channe")

    def test_airflow_review_rubric_no_stutter_and_boundary(self, tmp_path: Path):
        new_path = self._migrate_one(
            tmp_path,
            "review-rubric.md",
            "# Review rubric — fix N+1 queries in triggerer",
        )
        assert new_path == ".maigo/review-rubric-fix-n-1-queries-in.md"
        assert not Path(new_path).stem.endswith("-trigger")

    def test_pycontw_blog_plan_no_stutter(self, tmp_path: Path):
        new_path = self._migrate_one(
            tmp_path,
            "plan.md",
            "# Plan: create_post slug — PR #224 review c2",
        )
        assert new_path == ".maigo/plan-create_post-slug-pr-224-review-c2.md"

    def test_pycontw_blog_pr_comments_no_stutter_and_boundary(self, tmp_path: Path):
        new_path = self._migrate_one(
            tmp_path,
            "pr-comments.md",
            "# PR comments — fix create-post and dev tooling",
        )
        assert new_path == ".maigo/pr-comments-fix-create-post-and-dev.md"
        assert not Path(new_path).stem.endswith("-tool")

    def test_no_new_path_contains_kind_kind_stutter(self, tmp_path: Path):
        """所有 8 筆樣本共通斷言：新檔名不得含 `<kind>-<kind>-` 疊字。"""
        samples = [
            ("plan.md", "# Plan: Stats — Pelican stat dual mode (EN)"),
            ("plan.md", "# Plan: Emoji icon pin for place markers"),
            ("plan.md", "# Plan: Ring kitty focuser"),
            (
                "review-rubric.md",
                "# Review rubric — feat: pagination and modernization",
            ),
            ("pr-comments.md", "# PR comments — add producer-side ack channel"),
            ("review-rubric.md", "# Review rubric — fix N+1 queries in triggerer"),
            ("plan.md", "# Plan: create_post slug — PR #224 review c2"),
            ("pr-comments.md", "# PR comments — fix create-post and dev tooling"),
        ]
        for i, (legacy_name, h1) in enumerate(samples):
            new_path = self._migrate_one(tmp_path, legacy_name, h1)
            kind = legacy_name[: -len(".md")]
            assert f"{kind}-{kind}-" not in new_path, (i, legacy_name, h1, new_path)


class TestApplyMigration:
    def test_apply_renames_file_and_preserves_content(self, tmp_path: Path):
        repo = _make_repo(tmp_path)
        old = repo / ".maigo" / "plan.md"
        old.write_text("# Fix DAG run stall\n\nsome body content\n", encoding="utf-8")
        original_hash = _sha(old)

        catalog = scan(repo / ".maigo")
        actions = mla.plan_migration(repo, catalog)
        mla.apply_migration(repo, actions)

        new = repo / actions[0].new_path
        assert not old.exists()
        assert new.exists()
        assert _sha(new) == original_hash


class TestCli:
    def test_dry_run_does_not_touch_any_file(self, tmp_path: Path, capsys):
        repo = _make_repo(tmp_path)
        old = repo / ".maigo" / "plan.md"
        old.write_text("# Fix DAG run stall\n", encoding="utf-8")
        original_hash = _sha(old)

        exit_code = mla.main([str(repo)])

        captured = capsys.readouterr()
        assert exit_code == 0
        assert f"{repo} :: .maigo/plan.md -> .maigo/plan-fix-dag-run-stall.md" in (
            captured.out
        )
        assert old.exists()
        assert _sha(old) == original_hash
        assert not (repo / ".maigo" / "plan-fix-dag-run-stall.md").exists()

    def test_apply_flag_actually_renames(self, tmp_path: Path, capsys):
        repo = _make_repo(tmp_path)
        old = repo / ".maigo" / "plan.md"
        old.write_text("# Fix DAG run stall\n", encoding="utf-8")

        exit_code = mla.main([str(repo), "--apply"])

        assert exit_code == 0
        assert not old.exists()
        assert (repo / ".maigo" / "plan-fix-dag-run-stall.md").exists()

    def test_rerun_after_apply_is_idempotent_and_reports_nothing_to_migrate(
        self, tmp_path: Path, capsys
    ):
        repo = _make_repo(tmp_path)
        old = repo / ".maigo" / "plan.md"
        old.write_text("# Fix DAG run stall\n", encoding="utf-8")

        mla.main([str(repo), "--apply"])
        capsys.readouterr()  # drain first run's output

        exit_code = mla.main([str(repo), "--apply"])
        captured = capsys.readouterr()

        assert exit_code == 0
        assert f"{repo} :: (nothing to migrate)" in captured.out
        assert (repo / ".maigo" / "plan-fix-dag-run-stall.md").exists()

    def test_repo_list_file_is_read_when_no_positional_repos_given(
        self, tmp_path: Path, capsys
    ):
        repo_a = _make_repo(tmp_path, "repo-a")
        repo_b = _make_repo(tmp_path, "repo-b")
        (repo_a / ".maigo" / "plan.md").write_text("# Plan: A\n", encoding="utf-8")
        (repo_b / ".maigo" / "plan.md").write_text("# Plan: B\n", encoding="utf-8")

        repo_list = tmp_path / "repos.txt"
        repo_list.write_text(
            f"# comment line, ignored\n\n{repo_a}\n{repo_b}\n", encoding="utf-8"
        )

        exit_code = mla.main(["--repo-list", str(repo_list)])
        captured = capsys.readouterr()

        assert exit_code == 0
        assert str(repo_a) in captured.out
        assert str(repo_b) in captured.out
        # dry-run: repo-list 讀取本身唯讀，任何一邊都沒被真的搬動
        assert (repo_a / ".maigo" / "plan.md").exists()
        assert (repo_b / ".maigo" / "plan.md").exists()

    def test_repo_list_missing_file_is_not_a_silent_noop(self, tmp_path: Path, capsys):
        missing = tmp_path / "nope" / "repos.txt"

        exit_code = mla.main(["--repo-list", str(missing)])
        captured = capsys.readouterr()

        assert exit_code != 0
        assert captured.out == ""  # 不能印出跟「真的沒東西要遷移」一樣的輸出
        assert str(missing) in captured.err
        assert "not found" in captured.err or "unreadable" in captured.err

    def test_repo_list_empty_file_is_not_a_silent_noop(self, tmp_path: Path, capsys):
        repo_list = tmp_path / "repos.txt"
        repo_list.write_text("", encoding="utf-8")

        exit_code = mla.main(["--repo-list", str(repo_list)])
        captured = capsys.readouterr()

        assert exit_code != 0
        assert captured.out == ""
        assert str(repo_list) in captured.err

    def test_repo_list_all_comments_is_not_a_silent_noop(self, tmp_path: Path, capsys):
        repo_list = tmp_path / "repos.txt"
        repo_list.write_text("# just a comment\n\n# another\n", encoding="utf-8")

        exit_code = mla.main(["--repo-list", str(repo_list)])
        captured = capsys.readouterr()

        assert exit_code != 0
        assert captured.out == ""
        assert str(repo_list) in captured.err

    def test_repo_list_with_nonexistent_repo_path_is_skipped_with_reason(
        self, tmp_path: Path, capsys
    ):
        real_repo = _make_repo(tmp_path, "real-repo")
        (real_repo / ".maigo" / "plan.md").write_text(
            "# Plan: Real\n", encoding="utf-8"
        )
        fake_repo = tmp_path / "does-not-exist"

        repo_list = tmp_path / "repos.txt"
        repo_list.write_text(f"{fake_repo}\n{real_repo}\n", encoding="utf-8")

        exit_code = mla.main(["--repo-list", str(repo_list)])
        captured = capsys.readouterr()

        assert exit_code == 0
        assert f"{fake_repo} :: skipped" in captured.out
        assert str(real_repo) in captured.out
        # 真的存在的 repo 仍照常算出遷移計畫，不受前一筆缺路徑影響
        assert "plan-real.md" in captured.out
