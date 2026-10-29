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

    def test_pr_group_nested_paths_are_nested(self):
        catalog = mdc.categorize(["pr/7/review.md", "pr/7/reply-draft.md"])
        assert sorted(catalog.nested) == ["pr/7/reply-draft.md", "pr/7/review.md"]
        assert catalog.unregistered == []

    def test_pr_group_unknown_stem_is_unregistered(self):
        catalog = mdc.categorize(["pr/7/unknown.md"])
        assert catalog.unregistered == ["pr/7/unknown.md"]
        assert catalog.nested == []

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

    def test_scan_collects_pr_group(self, tmp_path: Path):
        pr_dir = tmp_path / ".maigo" / "pr" / "7"
        pr_dir.mkdir(parents=True)
        (pr_dir / "reply-draft.md").write_text("# Reply drafts: x\n", encoding="utf-8")

        catalog = mdc.scan(tmp_path / ".maigo")

        assert catalog.nested == ["pr/7/reply-draft.md"]

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


class TestInternalDir:
    def test_scan_never_lists_internal_files(self, tmp_path: Path):
        internal = tmp_path / "_internal"
        (internal / "board").mkdir(parents=True)
        (internal / "board" / "snapshot.json").write_text("{}")
        (internal / "x.md").write_text("x")
        (internal / "board" / "y.md").write_text("y")
        catalog = mdc.scan(tmp_path)
        everything = [
            name
            for field in (
                catalog.identifier_named,
                catalog.flat_identifier,
                catalog.nested,
                catalog.legacy_fixed_name,
                catalog.registered_non_artifact,
                catalog.unregistered,
            )
            for name in field
        ]
        assert not [name for name in everything if "_internal" in name]

    def test_categorize_skips_internal_paths(self):
        catalog = mdc.categorize(["_internal/board/dropped.jsonl", "_internal/x.md"])
        assert catalog == mdc.Catalog()

    def test_other_non_markdown_files_stay_unregistered(self):
        assert mdc.categorize(["x.json"]).unregistered == ["x.json"]


def _write(path: Path, text: str = "x\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class TestScanTree:
    def test_scan_tree_reports_unknown_top_level_dir_once(self, tmp_path: Path):
        maigo_dir = tmp_path / ".maigo"
        _write(maigo_dir / "evals" / "a" / "one.json")
        _write(maigo_dir / "evals" / "two.json")
        _write(maigo_dir / "evals" / "three.md")

        tree = mdc.scan_tree(maigo_dir)

        assert tree["unregistered"] == ["evals/"]

    def test_scan_tree_sees_non_markdown_top_level_files(self, tmp_path: Path):
        maigo_dir = tmp_path / ".maigo"
        _write(maigo_dir / "__titles.json", "{}")
        _write(maigo_dir / "notes.txt")
        _write(maigo_dir / "local-model-dispatch-plan.md")

        tree = mdc.scan_tree(maigo_dir)

        assert tree["unregistered"] == [
            "__titles.json",
            "local-model-dispatch-plan.md",
            "notes.txt",
        ]
        # `scan()` is blind to the non-markdown ones (its semantics stay unchanged)
        assert mdc.scan(maigo_dir).unregistered == ["local-model-dispatch-plan.md"]

    def test_scan_tree_recognises_topic_and_archive(self, tmp_path: Path):
        maigo_dir = tmp_path / ".maigo"
        _write(maigo_dir / "topic" / "my-topic" / "plan.md")
        _write(maigo_dir / "topic" / "my-topic" / "plan-2.md")
        _write(maigo_dir / "topic" / "my-topic" / "rubric.md")
        _write(maigo_dir / "pr" / "9" / "plan.md")
        _write(maigo_dir / "issue" / "3" / "plan.md")
        _write(maigo_dir / "review" / "5" / "rubric.md")
        _write(maigo_dir / "_archive" / "review" / "42" / "review.md")
        _write(maigo_dir / "_archive" / "i" / "42.md")

        tree = mdc.scan_tree(maigo_dir)

        assert tree["nested"] == [
            "issue/3/plan.md",
            "pr/9/plan.md",
            "review/5/rubric.md",
            "topic/my-topic/plan-2.md",
            "topic/my-topic/plan.md",
        ]
        # `rubric.md` is not a topic stem, so it is not a registered artifact there
        assert tree["unregistered"] == ["topic/my-topic/rubric.md"]
        assert len(tree["archive"]) == 2
        assert tree["archive"][0].startswith("_archive/i/42.md (mtime 20")
        assert tree["archive"][1].startswith("_archive/review/42 (mtime 20")

    def test_scan_tree_lists_non_group_archive_entry_as_one_unit(self, tmp_path: Path):
        maigo_dir = tmp_path / ".maigo"
        _write(maigo_dir / "_archive" / "x" / "old.md")
        _write(maigo_dir / "_archive" / "x" / "sub" / "deep.md")
        _write(maigo_dir / "_archive" / "topic" / "t" / "plan.md")
        _write(maigo_dir / "_archive" / "loose.md")

        paths = [
            entry.partition(" (mtime ")[0]
            for entry in mdc.scan_tree(maigo_dir)["archive"]
        ]

        assert paths == ["_archive/loose.md", "_archive/topic/t", "_archive/x"]

    def test_scan_tree_flags_nested_dot_maigo(self, tmp_path: Path):
        maigo_dir = tmp_path / ".maigo"
        _write(maigo_dir / ".maigo" / "_internal" / "log" / "session-head.json")
        _write(maigo_dir / "_internal" / "board" / "snapshot.json")
        _write(maigo_dir / "_internal" / "log" / "token-usage.jsonl")

        tree = mdc.scan_tree(maigo_dir)

        assert tree["nested_dot_maigo"] == [".maigo/"]
        assert tree["internal"] == ["_internal/ (2 files)"]
        assert tree["unregistered"] == []

    def test_scan_tree_classifies_legacy_internal_logs(self, tmp_path: Path):
        maigo_dir = tmp_path / ".maigo"
        for name in (
            "session-head.json",
            "token-usage.jsonl",
            "test-failures.jsonl",
            "soyo-must-fix.jsonl",
        ):
            _write(maigo_dir / name)

        tree = mdc.scan_tree(maigo_dir)

        assert tree["legacy_internal_log"] == [
            "session-head.json",
            "soyo-must-fix.jsonl",
            "test-failures.jsonl",
            "token-usage.jsonl",
        ]
        assert tree["unregistered"] == []

    def test_scan_tree_covers_every_category_and_missing_dir(self, tmp_path: Path):
        maigo_dir = tmp_path / ".maigo"
        _write(maigo_dir / "plan.md")
        _write(maigo_dir / "plan-fix.md")
        _write(maigo_dir / "review-rubric-42.md")
        _write(maigo_dir / "board.md")
        _write(maigo_dir / "i" / "42.md")

        tree = mdc.scan_tree(maigo_dir)

        assert set(tree) == set(mdc.TREE_CATEGORIES)
        assert tree["legacy_fixed_name"] == ["plan.md"]
        assert tree["identifier_named"] == ["plan-fix.md"]
        assert tree["flat_identifier"] == ["review-rubric-42.md"]
        assert tree["board"] == ["board.md", "i/42.md"]
        assert all(v == [] for v in mdc.scan_tree(tmp_path / "nope").values())

    def test_cli_tree_flag_prints_every_category(self, tmp_path: Path, capsys):
        maigo_dir = tmp_path / ".maigo"
        _write(maigo_dir / "evals" / "x.json")
        _write(maigo_dir / "topic" / "t" / "plan.md")
        _write(maigo_dir / "session-head.json")
        _write(maigo_dir / "_archive" / "pr" / "1" / "plan.md")
        _write(maigo_dir / "_internal" / "a.json")
        _write(maigo_dir / ".maigo" / "x")
        _write(maigo_dir / "board.md")
        _write(maigo_dir / "plan-a.md")
        _write(maigo_dir / "plan.md")
        _write(maigo_dir / "review-b-1.md")

        exit_code = mdc.main(["--dir", str(maigo_dir), "--tree"])
        out = capsys.readouterr().out

        assert exit_code == 0
        for category in mdc.TREE_CATEGORIES:
            header, _, rest = out.partition(f"{category}:\n")
            assert rest, category
            first_line = rest.splitlines()[0]
            assert first_line.startswith("  "), (category, first_line)
