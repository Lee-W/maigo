"""
Tests for scripts.migrate_legacy_artifacts.

全程只對 `tmp_path` 底下的假 repo 操作，測試不得觸碰任何真實的其他 12 個
repo——這條規則寫在這裡是提醒之後有人為了「更真實」而把測試指向使用者本機
真實 repo 路徑：**不要**。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from scripts.maigo_dir_catalog import scan

from scripts import migrate_legacy_artifacts as mla


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot(maigo_dir: Path) -> set[tuple[str, str]]:
    """`(relpath, sha256)` 集合，逐檔算，不用 `uniq`/`sort -u` 摘要。"""
    return {
        (str(p.relative_to(maigo_dir)), _sha(p))
        for p in maigo_dir.rglob("*")
        if p.is_file()
    }


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
        assert actions[0].h1 == "Fix DAG run stall"

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
        # 掉的疊字 bug；見 TestKindStutterRegressions）。kind 是巢狀 kind，
        # 新路徑落在巢狀資料夾底下，不是扁平檔名。
        assert actions[0].new_path == ".maigo/review/unnamed/rubric.md"

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
    """
    回歸樣本：13 個真實 repo 跑 dry-run 時，11 筆遷移裡有 8 筆撞到
    `<kind>-<kind>-...` 疊字檔名。真實 H1 內容無法取得（不讀真實 repo），
    這裡用會 slugify 出同樣疊字前綴＋同樣截斷邊界情境的合成 H1 重建每一筆，
    逐一驗證修好後不再疊字、且截斷（真的命中 40 字元上限時）會退到完整的
    `-` 分段邊界。巢狀 kind（review-rubric / pr-comments）的識別碼落在
    `Path(new_path).parent.name`（目錄名），不是檔名 stem。
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
        assert new_path == ".maigo/review/feat-pagination-and/rubric.md"
        # 截斷邊界驗證：識別碼（目錄名）不能落在字中間（例如疊字修掉之前真實
        # 遷移出來的 "...-and-modern" 就是這樣被 40 字元上限硬切出來的）。
        identifier = Path(new_path).parent.name
        assert not identifier.endswith("-modern")

    def test_airflow_pr_comments_ack_channel_no_stutter_and_boundary(
        self, tmp_path: Path
    ):
        new_path = self._migrate_one(
            tmp_path,
            "pr-comments.md",
            "# PR comments — add producer-side ack channel",
        )
        assert new_path == ".maigo/review/add-producer-side-ack/pr-comments.md"
        assert not Path(new_path).parent.name.endswith("-channe")

    def test_airflow_review_rubric_no_stutter_and_boundary(self, tmp_path: Path):
        new_path = self._migrate_one(
            tmp_path,
            "review-rubric.md",
            "# Review rubric — fix N+1 queries in triggerer",
        )
        assert new_path == ".maigo/review/fix-n-1-queries-in/rubric.md"
        assert not Path(new_path).parent.name.endswith("-trigger")

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
        assert new_path == ".maigo/review/fix-create-post-and-dev/pr-comments.md"
        assert not Path(new_path).parent.name.endswith("-tool")

    def test_no_new_path_contains_kind_kind_stutter(self, tmp_path: Path):
        """所有 8 筆樣本共通斷言：新路徑不得含 `<kind>-<kind>-` 疊字。"""
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


class TestPlanMigrationFlatIdentifier:
    """階段二：分目錄前扁平檔（`catalog.flat_identifier`）的遷移計畫。"""

    def test_same_repo_flat_review_rubric_migrates_to_nested(self, tmp_path: Path):
        repo = _make_repo(tmp_path)
        (repo / ".maigo" / "review-rubric-58543.md").write_text(
            "# Review rubric: x\n", encoding="utf-8"
        )

        catalog = scan(repo / ".maigo")
        actions = mla.plan_migration(repo, catalog)

        assert len(actions) == 1
        assert actions[0].old_path == ".maigo/review-rubric-58543.md"
        assert actions[0].new_path == ".maigo/review/58543/rubric.md"
        assert actions[0].disambiguated is False
        assert actions[0].normalized_from is None

    def test_home_repo_name_normalizes_owner_prefixed_id(self, tmp_path: Path):
        repo = _make_repo(tmp_path)
        (repo / ".maigo" / "review-airflow-58543.md").write_text(
            "# Review: x\n", encoding="utf-8"
        )
        (repo / ".maigo" / "review-rubric-58543.md").write_text(
            "# Review rubric: x\n", encoding="utf-8"
        )

        catalog = scan(repo / ".maigo")
        actions = mla.plan_migration(repo, catalog, home_repo_name="airflow")

        by_old = {a.old_path: a for a in actions}
        review_action = by_old[".maigo/review-airflow-58543.md"]
        rubric_action = by_old[".maigo/review-rubric-58543.md"]

        assert review_action.new_path == ".maigo/review/58543/review.md"
        assert review_action.normalized_from == "airflow-58543"
        assert rubric_action.new_path == ".maigo/review/58543/rubric.md"
        assert (
            Path(review_action.new_path).parent == Path(rubric_action.new_path).parent
        )

    def test_without_home_repo_name_cross_repo_id_is_not_normalized(
        self, tmp_path: Path
    ):
        repo = _make_repo(tmp_path)
        (repo / ".maigo" / "review-airflow-58543.md").write_text(
            "# Review: x\n", encoding="utf-8"
        )

        catalog = scan(repo / ".maigo")
        actions = mla.plan_migration(repo, catalog, home_repo_name="")

        assert len(actions) == 1
        assert actions[0].new_path == ".maigo/review/airflow-58543/review.md"
        assert actions[0].normalized_from is None

    def test_conflict_suffix_with_sibling_base_in_batch_splits_attempt(
        self, tmp_path: Path
    ):
        repo = _make_repo(tmp_path)
        (repo / ".maigo" / "review-rubric-58543.md").write_text(
            "# Review rubric: x\n", encoding="utf-8"
        )
        (repo / ".maigo" / "review-rubric-58543-2.md").write_text(
            "# Review rubric: y\n", encoding="utf-8"
        )

        catalog = scan(repo / ".maigo")
        actions = mla.plan_migration(repo, catalog)

        by_old = {a.old_path: a for a in actions}
        assert (
            by_old[".maigo/review-rubric-58543.md"].new_path
            == ".maigo/review/58543/rubric.md"
        )
        assert (
            by_old[".maigo/review-rubric-58543-2.md"].new_path
            == ".maigo/review/58543/rubric-2.md"
        )

    def test_orphan_numeric_suffix_without_base_sibling_is_not_split(
        self, tmp_path: Path
    ):
        repo = _make_repo(tmp_path)
        (repo / ".maigo" / "review-rubric-99-2.md").write_text(
            "# Review rubric: solo\n", encoding="utf-8"
        )

        catalog = scan(repo / ".maigo")
        actions = mla.plan_migration(repo, catalog)

        assert len(actions) == 1
        assert actions[0].new_path == ".maigo/review/99-2/rubric.md"

    def test_home_repo_prefix_and_conflict_suffix_combine_into_same_folder(
        self, tmp_path: Path
    ):
        """
        Soyo must-fix #1 的紅燈斷言：`review-rubric-airflow-58543-2.md`
        （前綴＋後綴同時出現）必須跟 `review-rubric-airflow-58543.md` 落進同一個
        `.maigo/review/58543/` 資料夾（`rubric.md` / `rubric-2.md`），且第二筆的
        `normalized_from` 不是 `None`——修前它會落進 `.maigo/review/airflow-58543/`
        （被 `-2` 尾巴擋掉正規化，然後未正規化就當 conflict base 用），跟第一筆分裂。
        """
        repo = _make_repo(tmp_path)
        (repo / ".maigo" / "review-rubric-airflow-58543.md").write_text(
            "# Review rubric: A\n", encoding="utf-8"
        )
        (repo / ".maigo" / "review-rubric-airflow-58543-2.md").write_text(
            "# Review rubric: B\n", encoding="utf-8"
        )

        catalog = scan(repo / ".maigo")
        actions = mla.plan_migration(repo, catalog, home_repo_name="airflow")

        by_old = {a.old_path: a for a in actions}
        base_action = by_old[".maigo/review-rubric-airflow-58543.md"]
        suffixed_action = by_old[".maigo/review-rubric-airflow-58543-2.md"]

        assert base_action.new_path == ".maigo/review/58543/rubric.md"
        assert suffixed_action.new_path == ".maigo/review/58543/rubric-2.md"
        assert (
            Path(base_action.new_path).parent == Path(suffixed_action.new_path).parent
        )
        assert suffixed_action.normalized_from == "airflow-58543"

    def test_suffixed_flat_name_without_base_sibling_is_not_split_even_with_prefix(
        self, tmp_path: Path
    ):
        """
        前綴＋後綴、但沒有 base sibling 在同一批（`review-rubric-airflow-58543.md`
        不存在）——依既有 sibling 規則，不當 conflict 後綴拆，整串當 id；正規化 regex
        要求整串到結尾都是數字，`airflow-58543-2` 不符合，維持原樣、`normalized_from`
        為 `None`。
        """
        repo = _make_repo(tmp_path)
        (repo / ".maigo" / "review-rubric-airflow-58543-2.md").write_text(
            "# Review rubric: solo\n", encoding="utf-8"
        )

        catalog = scan(repo / ".maigo")
        actions = mla.plan_migration(repo, catalog, home_repo_name="airflow")

        assert len(actions) == 1
        assert actions[0].new_path == ".maigo/review/airflow-58543-2/rubric.md"
        assert actions[0].normalized_from is None

    @pytest.mark.parametrize(
        "base_name, suffix_name",
        [
            pytest.param(
                "review-rubric-58543.md",
                "review-rubric-airflow-58543-2.md",
                id="bare-base_prefixed-suffix",
            ),
            pytest.param(
                "review-rubric-airflow-58543.md",
                "review-rubric-58543-2.md",
                id="prefixed-base_bare-suffix",
            ),
            pytest.param(
                "review-rubric-58543.md",
                "review-rubric-58543-2.md",
                id="bare-base_bare-suffix",
            ),
            pytest.param(
                "review-rubric-airflow-58543.md",
                "review-rubric-airflow-58543-2.md",
                id="prefixed-base_prefixed-suffix",
            ),
        ],
    )
    def test_canonical_sibling_match_covers_all_bare_prefixed_combinations(
        self, tmp_path: Path, base_name: str, suffix_name: str
    ):
        """
        Soyo re-review must-fix #2 的紅燈斷言（`bare-base_prefixed-suffix` 那個
        id）：sibling 判斷曾經只認字面前綴形，base 已經是裸形、後綴檔仍是前綴形時
        （或反過來）就找不到彼此，後綴檔被錯誤地整串當 id 用（沒有正規化、attempt
        停在 1）。四種組合都要落進同一個 `.maigo/review/58543/` 資料夾，
        `rubric.md` / `rubric-2.md`，不能只補其中一種形狀。
        """
        repo = _make_repo(tmp_path)
        (repo / ".maigo" / base_name).write_text(
            "# Review rubric: A\n", encoding="utf-8"
        )
        (repo / ".maigo" / suffix_name).write_text(
            "# Review rubric: B\n", encoding="utf-8"
        )

        catalog = scan(repo / ".maigo")
        actions = mla.plan_migration(repo, catalog, home_repo_name="airflow")

        by_old = {a.old_path: a for a in actions}
        base_action = by_old[f".maigo/{base_name}"]
        suffix_action = by_old[f".maigo/{suffix_name}"]

        assert base_action.new_path == ".maigo/review/58543/rubric.md"
        assert suffix_action.new_path == ".maigo/review/58543/rubric-2.md"
        assert Path(base_action.new_path).parent == Path(suffix_action.new_path).parent

    def test_two_sources_normalizing_to_same_canonical_id_are_disambiguated(
        self, tmp_path: Path
    ):
        """
        同一個 canonical 目標有兩個來源檔（一份裸形、一份前綴形，皆無 conflict
        後綴）——不可覆寫也不可靜默丟一個，沿用既有 reserved-set 消歧規則分配
        attempt，並標 `disambiguated=True` 供 dry-run 呈現。
        """
        repo = _make_repo(tmp_path)
        (repo / ".maigo" / "review-rubric-58543.md").write_text(
            "# Review rubric: bare\n", encoding="utf-8"
        )
        (repo / ".maigo" / "review-rubric-airflow-58543.md").write_text(
            "# Review rubric: prefixed\n", encoding="utf-8"
        )

        catalog = scan(repo / ".maigo")
        actions = mla.plan_migration(repo, catalog, home_repo_name="airflow")

        new_paths = sorted(a.new_path for a in actions)
        assert new_paths == [
            ".maigo/review/58543/rubric-2.md",
            ".maigo/review/58543/rubric.md",
        ]
        by_new = {a.new_path: a for a in actions}
        assert by_new[".maigo/review/58543/rubric.md"].disambiguated is False
        assert by_new[".maigo/review/58543/rubric-2.md"].disambiguated is True

    def test_orphan_cross_repo_and_orphan_numeric_tail_are_not_misparsed(
        self, tmp_path: Path
    ):
        """
        真正跨 repo、無 sibling 的 id（`otherrepo-42`）與孤立的
        `fix-2`（看起來像 conflict 後綴，但沒有 `review-rubric-fix.md` sibling）
        都必須維持原樣，不能被 canonical sibling 判斷誤拆——回歸保護，
        不是 must-fix 本身要求的新行為。
        """
        repo = _make_repo(tmp_path)
        (repo / ".maigo" / "review-rubric-otherrepo-42.md").write_text(
            "# Review rubric: cross-repo\n", encoding="utf-8"
        )
        (repo / ".maigo" / "review-rubric-fix-2.md").write_text(
            "# Review rubric: orphan tail\n", encoding="utf-8"
        )

        catalog = scan(repo / ".maigo")
        actions = mla.plan_migration(repo, catalog, home_repo_name="airflow")

        by_old = {a.old_path: a for a in actions}
        assert (
            by_old[".maigo/review-rubric-otherrepo-42.md"].new_path
            == ".maigo/review/otherrepo-42/rubric.md"
        )
        assert (
            by_old[".maigo/review-rubric-fix-2.md"].new_path
            == ".maigo/review/fix-2/rubric.md"
        )

    def test_review_draft_flat_name_migrates_with_normalization(self, tmp_path: Path):
        repo = _make_repo(tmp_path)
        (repo / ".maigo" / "review-draft-airflow-73559.md").write_text(
            "# Review draft: x\n", encoding="utf-8"
        )

        catalog = scan(repo / ".maigo")
        actions = mla.plan_migration(repo, catalog, home_repo_name="airflow")

        assert len(actions) == 1
        assert actions[0].new_path == ".maigo/review/73559/draft.md"
        assert actions[0].normalized_from == "airflow-73559"

    def test_flat_name_lookalikes_are_never_planned(self, tmp_path: Path):
        repo = _make_repo(tmp_path)
        (repo / ".maigo" / "review-batch-state.md").write_text(
            "# whatever\n", encoding="utf-8"
        )
        (repo / ".maigo" / "review-board.md").write_text(
            "# Work Board\n", encoding="utf-8"
        )

        catalog = scan(repo / ".maigo")
        actions = mla.plan_migration(repo, catalog)

        assert actions == []

    def test_pre_existing_nested_target_causes_disambiguation_without_overwrite(
        self, tmp_path: Path
    ):
        repo = _make_repo(tmp_path)
        existing = repo / ".maigo" / "review" / "58543" / "rubric.md"
        existing.parent.mkdir(parents=True)
        existing.write_text("# Pre-existing\n", encoding="utf-8")
        existing_sha = _sha(existing)

        (repo / ".maigo" / "review-rubric-58543.md").write_text(
            "# Review rubric: new one\n", encoding="utf-8"
        )

        catalog = scan(repo / ".maigo")
        actions = mla.plan_migration(repo, catalog)

        assert len(actions) == 1
        assert actions[0].new_path == ".maigo/review/58543/rubric-2.md"
        assert actions[0].disambiguated is True
        assert _sha(existing) == existing_sha


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

    def test_apply_creates_nested_parent_directories(self, tmp_path: Path):
        repo = _make_repo(tmp_path)
        old = repo / ".maigo" / "review-rubric-58543.md"
        old.write_text("# Review rubric: x\n", encoding="utf-8")

        catalog = scan(repo / ".maigo")
        actions = mla.plan_migration(repo, catalog)
        mla.apply_migration(repo, actions)

        new = repo / ".maigo" / "review" / "58543" / "rubric.md"
        assert new.is_file()

    def test_apply_refuses_to_overwrite_target_created_after_planning(
        self, tmp_path: Path
    ):
        # canary B 的紅燈斷言：拿掉 rename 前的 exists() 檢查必須紅在這裡
        # （sha256 相等那條）——POSIX rename() 會靜默覆蓋既有目標。
        repo = _make_repo(tmp_path)
        old = repo / ".maigo" / "plan.md"
        old.write_text("# Fix DAG run stall\n", encoding="utf-8")

        catalog = scan(repo / ".maigo")
        actions = mla.plan_migration(repo, catalog)

        # 規劃之後才建立目標檔（模擬「規劃與套用之間，另一個寫入出現」）。
        target = repo / actions[0].new_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "# Someone else wrote this after planning\n", encoding="utf-8"
        )
        target_sha = _sha(target)

        with pytest.raises(FileExistsError):
            mla.apply_migration(repo, actions)

        assert _sha(target) == target_sha
        assert old.exists()

    def test_apply_skips_already_moved_and_refuses_when_both_paths_missing(
        self, tmp_path: Path
    ):
        repo = _make_repo(tmp_path)
        moved = repo / ".maigo" / "review" / "42" / "review.md"
        moved.parent.mkdir(parents=True)
        moved.write_text("# Review: moved last run\n", encoding="utf-8")
        already_moved = mla.MigrationAction(
            repo=str(repo),
            old_path=".maigo/review-42.md",
            new_path=".maigo/review/42/review.md",
            disambiguated=False,
        )
        vanished = mla.MigrationAction(
            repo=str(repo),
            old_path=".maigo/review-rubric-42.md",
            new_path=".maigo/review/42/rubric.md",
            disambiguated=False,
        )

        mla.apply_migration(repo, [already_moved])
        assert moved.read_text(encoding="utf-8") == "# Review: moved last run\n"

        with pytest.raises(FileNotFoundError):
            mla.apply_migration(repo, [already_moved, vanished])


class TestLinkRewrites:
    def _write_detail_file(self, repo: Path, name: str, body: str) -> Path:
        i_dir = repo / ".maigo" / "i"
        i_dir.mkdir(parents=True, exist_ok=True)
        path = i_dir / name
        path.write_text(body, encoding="utf-8")
        return path

    def _sample_detail_body(self) -> str:
        return (
            "# 👀 待送出 — Some PR\n\n"
            "- 連結：https://github.com/apache/airflow/pull/58543\n"
            "- 規模：Δ+10/-2\n"
            "- 下一步：`gh pr review 58543 --comment --body-file "
            ".maigo/review-58543.md`\n\n"
            "## 判斷\n\n"
            "review-airflow-58543.md 提到過這裡，不應該被改。\n\n"
            "## 筆記\n\n"
            "review-airflow-58543.md 與 review-rubric-58543.md 都寫過摘要。\n"
            "帶路徑前綴的參考："
            "airflow-registry-surface/.maigo/pr-comments-airflow-71477.md\n"
        )

    def test_plans_rewrites_only_within_notes_section(self, tmp_path: Path):
        repo = _make_repo(tmp_path)
        detail = self._write_detail_file(repo, "58543.md", self._sample_detail_body())
        original_text = detail.read_text(encoding="utf-8")

        (repo / ".maigo" / "review-airflow-58543.md").write_text(
            "# Review: x\n", encoding="utf-8"
        )
        (repo / ".maigo" / "review-rubric-58543.md").write_text(
            "# Review rubric: x\n", encoding="utf-8"
        )

        catalog = scan(repo / ".maigo")
        actions = mla.plan_migration(repo, catalog, home_repo_name="airflow")
        rewrites = mla.plan_link_rewrites(repo, actions)

        tokens = {(r.old_token, r.new_token) for r in rewrites}
        assert ("review-airflow-58543.md", "review/58543/review.md") in tokens
        assert ("review-rubric-58543.md", "review/58543/rubric.md") in tokens
        assert len(rewrites) == 2
        for rewrite in rewrites:
            assert rewrite.line_no >= 10  # 只在 ## 筆記 段內（該段從第 10 行左右開始）
        # dry-run 唯讀：規劃階段完全不動檔案。
        assert detail.read_text(encoding="utf-8") == original_text

    def test_apply_only_changes_notes_section_tokens(self, tmp_path: Path):
        repo = _make_repo(tmp_path)
        detail = self._write_detail_file(repo, "58543.md", self._sample_detail_body())
        original_lines = detail.read_text(encoding="utf-8").splitlines()

        (repo / ".maigo" / "review-airflow-58543.md").write_text(
            "# Review: x\n", encoding="utf-8"
        )
        (repo / ".maigo" / "review-rubric-58543.md").write_text(
            "# Review rubric: x\n", encoding="utf-8"
        )

        catalog = scan(repo / ".maigo")
        actions = mla.plan_migration(repo, catalog, home_repo_name="airflow")
        mla.apply_migration(repo, actions)
        rewrites = mla.plan_link_rewrites(repo, actions)
        mla.apply_link_rewrites(repo, rewrites)

        new_lines = detail.read_text(encoding="utf-8").splitlines()
        assert len(new_lines) == len(original_lines)
        diffs = [
            (i, old, new)
            for i, (old, new) in enumerate(zip(original_lines, new_lines))
            if old != new
        ]
        assert len(diffs) == 1
        _, old_line, new_line = diffs[0]
        assert old_line == (
            "review-airflow-58543.md 與 review-rubric-58543.md 都寫過摘要。"
        )
        assert (
            new_line == "review/58543/review.md 與 review/58543/rubric.md 都寫過摘要。"
        )
        # 事實區與 ## 判斷 逐行不變
        assert "review-airflow-58543.md 提到過這裡，不應該被改。" in new_lines
        assert "review-58543.md" in "\n".join(new_lines)  # 事實區的 `- 下一步：` 不動

    def test_link_rewrite_for_prefix_and_suffix_combined_flat_name(
        self, tmp_path: Path
    ):
        """
        Soyo must-fix #1 的連結改寫版：`## 筆記` 同時提到
        `review-rubric-airflow-58543.md`（base）與 `review-rubric-airflow-58543-2.md`
        （前綴＋後綴）時，兩個 token 都要改到同一個 `review/58543/` 資料夾底下
        （`rubric.md` / `rubric-2.md`），不能有一個掉進 `review/airflow-58543/`。
        """
        repo = _make_repo(tmp_path)
        detail = self._write_detail_file(
            repo,
            "58543.md",
            "# 👀 待送出 — Some PR\n\n"
            "- 連結：https://github.com/apache/airflow/pull/58543\n\n"
            "## 判斷\n\n略。\n\n"
            "## 筆記\n\n"
            "review-rubric-airflow-58543.md 與 "
            "review-rubric-airflow-58543-2.md 都寫過摘要。\n",
        )
        (repo / ".maigo" / "review-rubric-airflow-58543.md").write_text(
            "# Review rubric: A\n", encoding="utf-8"
        )
        (repo / ".maigo" / "review-rubric-airflow-58543-2.md").write_text(
            "# Review rubric: B\n", encoding="utf-8"
        )

        catalog = scan(repo / ".maigo")
        actions = mla.plan_migration(repo, catalog, home_repo_name="airflow")
        mla.apply_migration(repo, actions)
        rewrites = mla.plan_link_rewrites(repo, actions)
        mla.apply_link_rewrites(repo, rewrites)

        tokens = {(r.old_token, r.new_token) for r in rewrites}
        assert (
            "review-rubric-airflow-58543.md",
            "review/58543/rubric.md",
        ) in tokens
        assert (
            "review-rubric-airflow-58543-2.md",
            "review/58543/rubric-2.md",
        ) in tokens

        text = detail.read_text(encoding="utf-8")
        assert "review/58543/rubric.md 與 review/58543/rubric-2.md 都寫過摘要。" in text

    def test_path_qualified_mentions_are_reported_not_rewritten(self, tmp_path: Path):
        repo = _make_repo(tmp_path)
        self._write_detail_file(repo, "58543.md", self._sample_detail_body())

        mentions = mla.find_path_qualified_mentions(repo)

        assert any(
            token.endswith("pr-comments-airflow-71477.md") for _, _, token in mentions
        )

    def test_old_names_without_migration_record_are_left_unchanged(
        self, tmp_path: Path
    ):
        """
        12. 沒有遷移紀錄（本次 `actions` 沒有、也沒有 manifest）時不猜目標：
        檔案已在巢狀位置、`## 筆記` 仍是舊連結 → 連結原封不動，只回報。

        從磁碟反推「這個舊檔名搬去了哪」分不出「我的位置」與「撞名對手佔走的
        位置」（Soyo re-review 2 must-fix #3）；這裡的巢狀檔案沒有任何紀錄能
        證明它們是由這兩個舊檔名搬過去的。
        """
        repo = _make_repo(tmp_path)
        detail = self._write_detail_file(repo, "58543.md", self._sample_detail_body())
        original_text = detail.read_text(encoding="utf-8")

        nested_review = repo / ".maigo" / "review" / "58543" / "review.md"
        nested_review.parent.mkdir(parents=True)
        nested_review.write_text("# Review: x\n", encoding="utf-8")
        nested_rubric = repo / ".maigo" / "review" / "58543" / "rubric.md"
        nested_rubric.write_text("# Review rubric: x\n", encoding="utf-8")

        catalog = scan(repo / ".maigo")
        actions = mla.plan_migration(repo, catalog, home_repo_name="airflow")
        assert actions == []

        assert mla.plan_link_rewrites(repo, actions) == []
        unmapped = {token for _, _, token in mla.find_unmapped_mentions(repo, actions)}
        assert unmapped == {"review-airflow-58543.md", "review-rubric-58543.md"}
        assert detail.read_text(encoding="utf-8") == original_text


class TestInterruptedApply:
    """
    `--apply` 在第 k 個 rename 之後中斷、再重跑：每個舊檔名的最終位置與
    `## 筆記` 連結都必須等於**第一次**規劃的 `new_path`（Soyo re-review 2
    must-fix #3）。這批輸入刻意同時含：

    - 規劃期 disambiguation：`review-rubric-58543.md` 與
      `review-rubric-airflow-58543.md` 正規化後撞同一個 canonical id，後者被
      推到 `rubric-2.md`，它的 `-2` 同伴再被推到 `rubric-3.md`；
    - 依賴批次 sibling 的後綴解讀：`review-58543-2.md` 只因為
      `review-58543.md` 同批才被解讀成 attempt=2——base 先被搬走後重新規劃，
      就會退化成孤立的 `58543-2` id。
    """

    _FILES = {
        "review-58543.md": "# Review: first\n",
        "review-58543-2.md": "# Review: second\n",
        "review-rubric-58543.md": "# Review rubric: bare\n",
        "review-rubric-airflow-58543.md": "# Review rubric: prefixed\n",
        "review-rubric-airflow-58543-2.md": "# Review rubric: prefixed re-review\n",
    }

    def _build_repo(self, tmp_path: Path) -> Path:
        repo = _make_repo(tmp_path)
        for name, body in self._FILES.items():
            (repo / ".maigo" / name).write_text(body, encoding="utf-8")
        i_dir = repo / ".maigo" / "i"
        i_dir.mkdir()
        (i_dir / "58543.md").write_text(
            "# 👀 待送出 — Some PR\n\n## 判斷\n\n略。\n\n## 筆記\n\n"
            + "".join(f"- {name}\n" for name in sorted(self._FILES)),
            encoding="utf-8",
        )
        return repo

    @pytest.mark.parametrize("interrupt_after", [2, len(_FILES)])
    def test_rerun_after_interruption_matches_original_plan(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        interrupt_after: int,
    ):
        repo = self._build_repo(tmp_path)
        maigo_dir = repo / ".maigo"
        planned = {
            Path(a.old_path).name: a.new_path
            for a in mla.plan_migration(repo, scan(maigo_dir), home_repo_name="airflow")
        }
        assert planned["review-rubric-airflow-58543.md"] == (
            ".maigo/review/58543/rubric-2.md"
        )
        assert planned["review-58543-2.md"] == ".maigo/review/58543/review-2.md"

        class _Interrupted(Exception):
            pass

        real_rename = Path.rename
        renames_done = 0

        def _rename_then_maybe_interrupt(self: Path, target):
            nonlocal renames_done
            result = real_rename(self, target)
            renames_done += 1
            if renames_done == interrupt_after:
                raise _Interrupted
            return result

        with monkeypatch.context() as patch:
            patch.setattr(Path, "rename", _rename_then_maybe_interrupt)
            with pytest.raises(_Interrupted):
                mla.main([str(repo), "--apply", "--home-repo-name", "airflow"])
        assert renames_done == interrupt_after
        assert mla.manifest_path(repo).is_file()

        # 續跑前的 dry-run：照 manifest 顯示，但不動任何檔案（含 manifest 本身）。
        before_dry_run = _snapshot(maigo_dir)
        capsys.readouterr()
        assert mla.main([str(repo), "--home-repo-name", "airflow"]) == 0
        dry_run_out = capsys.readouterr().out
        assert "resuming interrupted --apply" in dry_run_out
        assert dry_run_out.count("[already moved]") == interrupt_after
        assert _snapshot(maigo_dir) == before_dry_run

        assert mla.main([str(repo), "--apply", "--home-repo-name", "airflow"]) == 0
        assert not mla.manifest_path(repo).exists()

        for name, body in self._FILES.items():
            assert not (maigo_dir / name).exists()
            assert (repo / planned[name]).read_text(encoding="utf-8") == body
        notes = (maigo_dir / "i" / "58543.md").read_text(encoding="utf-8")
        for name in self._FILES:
            assert f"- {planned[name].removeprefix('.maigo/')}\n" in notes
            assert f"- {name}\n" not in notes


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
        assert not mla.manifest_path(repo).exists()

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
        before = _snapshot(repo / ".maigo")

        exit_code = mla.main([str(repo), "--apply"])
        captured = capsys.readouterr()

        assert exit_code == 0
        assert f"{repo} :: (nothing to migrate)" in captured.out
        assert (repo / ".maigo" / "plan-fix-dag-run-stall.md").exists()
        assert _snapshot(repo / ".maigo") == before

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

    def test_home_repo_name_flag_overrides_git_remote_detection(
        self, tmp_path: Path, capsys
    ):
        repo = _make_repo(tmp_path)
        (repo / ".maigo" / "review-airflow-58543.md").write_text(
            "# Review: x\n", encoding="utf-8"
        )

        exit_code = mla.main([str(repo), "--home-repo-name", "airflow"])
        captured = capsys.readouterr()

        assert exit_code == 0
        assert ".maigo/review/58543/review.md" in captured.out
        assert "[normalized from airflow-58543]" in captured.out

    def test_skipped_categories_are_reported_with_reasons(self, tmp_path: Path, capsys):
        repo = _make_repo(tmp_path)
        (repo / ".maigo" / "plan-already-canonical.md").write_text(
            "# Plan: already\n", encoding="utf-8"
        )
        (repo / ".maigo" / "board.md").write_text("# Work Board\n", encoding="utf-8")
        (repo / ".maigo" / "review-batch-state.md").write_text(
            "# whatever\n", encoding="utf-8"
        )

        exit_code = mla.main([str(repo)])
        captured = capsys.readouterr()

        assert exit_code == 0
        assert f"{repo} :: skipped plan-already-canonical.md" in captured.out
        assert f"{repo} :: skipped board.md" in captured.out
        assert f"{repo} :: skipped review-batch-state.md" in captured.out
        # `maigo_dir_catalog.scan()` only lists `*.md` files in the first
        # place — non-markdown machine-state files (`session-head.json`,
        # `soyo-must-fix.jsonl`) never even reach the catalog, so there is
        # nothing to print a skip line for; they are absent from the output
        # by construction, not via the skip-reporting path.
        assert "session-head.json" not in captured.out
