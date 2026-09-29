"""Tests for scripts.maigo_dir_catalog — `.maigo/` 型錄分類（唯讀掃描）。"""

from __future__ import annotations

from pathlib import Path

from scripts import maigo_dir_catalog as mdc


class TestCategorize:
    def test_identifier_named_known_kind(self):
        catalog = mdc.categorize(["plan-fix-dag-run-stall.md"])
        assert catalog.identifier_named == ["plan-fix-dag-run-stall.md"]
        assert catalog.flat_identifier == []
        assert catalog.legacy_fixed_name == []
        assert catalog.registered_non_artifact == []
        assert catalog.unregistered == []

    def test_nested_kind_flat_name_is_flat_identifier(self):
        """
        巢狀 kind 的分目錄前扁平檔（`review-x.md`）進 `flat_identifier`，
        待遷移；不再算進 `identifier_named`（那只剩 plan）。
        """
        catalog = mdc.categorize(["review-x.md"])
        assert catalog.flat_identifier == ["review-x.md"]
        assert catalog.identifier_named == []
        assert catalog.unregistered == []

    def test_legacy_fixed_name_known_kind(self):
        catalog = mdc.categorize(["plan.md"])
        assert catalog.legacy_fixed_name == ["plan.md"]
        assert catalog.identifier_named == []

    def test_review_prefix_does_not_swallow_review_rubric(self):
        """`review` 是 `review-rubric` 的前綴——必須先試最長 kind 才不會誤判。"""
        catalog = mdc.categorize(
            ["review-rubric-42.md", "review-rubric.md", "review-42.md", "review.md"]
        )
        assert catalog.flat_identifier == ["review-42.md", "review-rubric-42.md"]
        assert catalog.legacy_fixed_name == ["review-rubric.md", "review.md"]
        assert catalog.identifier_named == []
        assert catalog.unregistered == []

    def test_review_draft_flat_name_not_swallowed_by_review(self):
        catalog = mdc.categorize(["review-draft-airflow-73559.md"])
        assert catalog.flat_identifier == ["review-draft-airflow-73559.md"]
        assert mdc.split_flat_name("review-draft-airflow-73559.md") == (
            "review-draft",
            "airflow-73559",
        )

    def test_registered_non_artifact_board(self):
        catalog = mdc.categorize(["board.md"])
        assert catalog.registered_non_artifact == ["board.md"]
        assert catalog.identifier_named == []
        assert catalog.legacy_fixed_name == []
        assert catalog.unregistered == []

    def test_review_board_is_registered_non_artifact_not_review_kind(self):
        catalog = mdc.categorize(["review-board.md"])
        assert catalog.registered_non_artifact == ["review-board.md"]
        assert catalog.flat_identifier == []
        assert catalog.unregistered == []

    def test_review_batch_state_is_unregistered_not_review_kind(self):
        catalog = mdc.categorize(["review-batch-state.md"])
        assert catalog.unregistered == ["review-batch-state.md"]
        assert catalog.flat_identifier == []
        assert catalog.registered_non_artifact == []

    def test_unregistered_catch_all(self):
        catalog = mdc.categorize(
            ["board-design.md", "index.md", "local-model-dispatch-plan.md"]
        )
        assert catalog.unregistered == [
            "board-design.md",
            "index.md",
            "local-model-dispatch-plan.md",
        ]
        assert catalog.identifier_named == []
        assert catalog.legacy_fixed_name == []
        assert catalog.registered_non_artifact == []

    def test_non_markdown_file_is_unregistered(self):
        catalog = mdc.categorize(["session-head.json"])
        assert catalog.unregistered == ["session-head.json"]

    def test_all_categories_together(self):
        catalog = mdc.categorize(
            [
                "plan-42.md",
                "plan.md",
                "board.md",
                "board-design.md",
                "review-x.md",
                "review/58543/rubric-2.md",
            ]
        )
        assert catalog.identifier_named == ["plan-42.md"]
        assert catalog.flat_identifier == ["review-x.md"]
        assert catalog.nested == ["review/58543/rubric-2.md"]
        assert catalog.legacy_fixed_name == ["plan.md"]
        assert catalog.registered_non_artifact == ["board.md"]
        assert catalog.unregistered == ["board-design.md"]

    def test_nested_review_rubric_and_issue_rubric(self):
        catalog = mdc.categorize(["review/58543/rubric-2.md", "issue/12/rubric.md"])
        assert sorted(catalog.nested) == [
            "issue/12/rubric.md",
            "review/58543/rubric-2.md",
        ]
        assert catalog.unregistered == []

    def test_nested_unknown_stem_is_unregistered(self):
        catalog = mdc.categorize(["review/58543/notes.md"])
        assert catalog.unregistered == ["review/58543/notes.md"]
        assert catalog.nested == []


class TestSplitFlatName:
    def test_splits_kind_and_id(self):
        assert mdc.split_flat_name("review-rubric-42.md") == ("review-rubric", "42")

    def test_legacy_fixed_name_has_no_split(self):
        assert mdc.split_flat_name("plan.md") is None

    def test_non_markdown_has_no_split(self):
        assert mdc.split_flat_name("session-head.json") is None

    def test_unknown_kind_has_no_split(self):
        assert mdc.split_flat_name("not-a-kind-42.md") is None


class TestScan:
    def test_scans_only_top_level_md_files(self, tmp_path: Path):
        """
        非 markdown 機器狀態檔（如 session-head.json）與 `i/` 子目錄都不在這支
        腳本的掃描範圍內——見 `docs/reference/artifacts.md`，它們一行帶過、非
        agent 面向格式，不用型錄分類法。
        """
        maigo_dir = tmp_path / ".maigo"
        maigo_dir.mkdir()
        (maigo_dir / "plan-42.md").write_text("# Plan: x\n", encoding="utf-8")
        (maigo_dir / "board.md").write_text("# Board\n", encoding="utf-8")
        (maigo_dir / "session-head.json").write_text("{}", encoding="utf-8")
        nested = maigo_dir / "i"
        nested.mkdir()
        (nested / "orphan.md").write_text("# should not be scanned\n", encoding="utf-8")

        catalog = mdc.scan(maigo_dir)

        assert catalog.identifier_named == ["plan-42.md"]
        assert catalog.registered_non_artifact == ["board.md"]
        assert catalog.unregistered == []
        assert catalog.nested == []

    def test_recurses_into_review_and_issue_two_levels(self, tmp_path: Path):
        """Canary D 的紅燈斷言：`scan()` 拿掉遞迴必須紅在這裡。"""
        maigo_dir = tmp_path / ".maigo"
        review_dir = maigo_dir / "review" / "58543"
        review_dir.mkdir(parents=True)
        (review_dir / "rubric-2.md").write_text(
            "# Review rubric: x\n", encoding="utf-8"
        )
        (review_dir / "notes.md").write_text("# notes\n", encoding="utf-8")
        issue_dir = maigo_dir / "issue" / "12"
        issue_dir.mkdir(parents=True)
        (issue_dir / "rubric.md").write_text("# Triage rubric: y\n", encoding="utf-8")

        catalog = mdc.scan(maigo_dir)

        assert sorted(catalog.nested) == [
            "issue/12/rubric.md",
            "review/58543/rubric-2.md",
        ]
        assert catalog.unregistered == ["review/58543/notes.md"]

    def test_does_not_descend_past_two_levels(self, tmp_path: Path):
        maigo_dir = tmp_path / ".maigo"
        deep = maigo_dir / "review" / "58543" / "extra"
        deep.mkdir(parents=True)
        (deep / "too-deep.md").write_text("# too deep\n", encoding="utf-8")

        catalog = mdc.scan(maigo_dir)

        assert catalog.nested == []
        assert catalog.unregistered == []

    def test_missing_dir_returns_empty_catalog(self, tmp_path: Path):
        catalog = mdc.scan(tmp_path / "does-not-exist")
        assert catalog.identifier_named == []
        assert catalog.flat_identifier == []
        assert catalog.nested == []
        assert catalog.legacy_fixed_name == []
        assert catalog.registered_non_artifact == []
        assert catalog.unregistered == []


class TestCli:
    def test_prints_all_section_headers(self, tmp_path: Path, capsys):
        maigo_dir = tmp_path / ".maigo"
        maigo_dir.mkdir()
        (maigo_dir / "plan-42.md").write_text("# Plan: x\n", encoding="utf-8")

        exit_code = mdc.main(["--dir", str(maigo_dir)])

        captured = capsys.readouterr()
        assert exit_code == 0
        assert "identifier_named:" in captured.out
        assert "  plan-42.md" in captured.out
        assert "flat_identifier:" in captured.out
        assert "nested:" in captured.out
        assert "legacy_fixed_name:" in captured.out
        assert "registered_non_artifact:" in captured.out
        assert "unregistered:" in captured.out
