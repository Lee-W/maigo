"""Tests for scripts.maigo_dir_catalog — `.maigo/` 頂層檔案分類（唯讀掃描）。"""

from __future__ import annotations

from pathlib import Path

from scripts import maigo_dir_catalog as mdc


class TestCategorize:
    def test_identifier_named_known_kind(self):
        catalog = mdc.categorize(["plan-fix-dag-run-stall.md"])
        assert catalog.identifier_named == ["plan-fix-dag-run-stall.md"]
        assert catalog.legacy_fixed_name == []
        assert catalog.registered_non_artifact == []
        assert catalog.unregistered == []

    def test_new_review_kind_identifier_named(self):
        """證明新 kind（review）不用改這支測試就能被正確分類。"""
        catalog = mdc.categorize(["review-x.md"])
        assert catalog.identifier_named == ["review-x.md"]
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
        assert catalog.identifier_named == ["review-42.md", "review-rubric-42.md"]
        assert catalog.legacy_fixed_name == ["review-rubric.md", "review.md"]
        assert catalog.unregistered == []

    def test_registered_non_artifact_board(self):
        catalog = mdc.categorize(["board.md"])
        assert catalog.registered_non_artifact == ["board.md"]
        assert catalog.identifier_named == []
        assert catalog.legacy_fixed_name == []
        assert catalog.unregistered == []

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

    def test_all_four_categories_together(self):
        catalog = mdc.categorize(
            [
                "plan-42.md",
                "plan.md",
                "board.md",
                "board-design.md",
            ]
        )
        assert catalog.identifier_named == ["plan-42.md"]
        assert catalog.legacy_fixed_name == ["plan.md"]
        assert catalog.registered_non_artifact == ["board.md"]
        assert catalog.unregistered == ["board-design.md"]


class TestScan:
    def test_scans_only_top_level_md_files(self, tmp_path: Path):
        """非 markdown 機器狀態檔（如 session-head.json）與 `i/` 子目錄都不在這支
        腳本的掃描範圍內——見 `docs/reference/artifacts.md`，它們一行帶過、非
        agent 面向格式，不用四類分類法。"""
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

    def test_missing_dir_returns_empty_catalog(self, tmp_path: Path):
        catalog = mdc.scan(tmp_path / "does-not-exist")
        assert catalog.identifier_named == []
        assert catalog.legacy_fixed_name == []
        assert catalog.registered_non_artifact == []
        assert catalog.unregistered == []


class TestCli:
    def test_prints_all_four_section_headers(self, tmp_path: Path, capsys):
        maigo_dir = tmp_path / ".maigo"
        maigo_dir.mkdir()
        (maigo_dir / "plan-42.md").write_text("# Plan: x\n", encoding="utf-8")

        exit_code = mdc.main(["--dir", str(maigo_dir)])

        captured = capsys.readouterr()
        assert exit_code == 0
        assert "identifier_named:" in captured.out
        assert "  plan-42.md" in captured.out
        assert "legacy_fixed_name:" in captured.out
        assert "registered_non_artifact:" in captured.out
        assert "unregistered:" in captured.out
