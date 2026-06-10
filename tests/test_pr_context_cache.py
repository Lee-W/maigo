"""Tests for scripts.pr_context_cache."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import scripts.pr_context_cache as pcc


class TestClassifySource:
    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            pytest.param("https://github.com/o/r/pull/42", "pr", id="url"),
            pytest.param("42", "pr", id="bare-number"),
            pytest.param("#42", "pr", id="hash-number"),
            pytest.param("main..feature", "range", id="two-dot-range"),
            pytest.param("HEAD~3..HEAD", "range", id="head-range"),
            pytest.param("feature-branch", "branch", id="branch"),
        ],
    )
    def test_classify(self, source: str, expected: str):
        assert pcc.classify_source(source) == expected


class TestTruncateLines:
    def test_under_limit_unchanged(self):
        text = "a\nb\nc"
        assert pcc.truncate_lines(text, 5, "[cut]") == text

    def test_over_limit_cut_with_suffix(self):
        text = "\n".join(str(i) for i in range(10))
        result = pcc.truncate_lines(text, 3, "[cut]")
        assert result == "0\n1\n2\n[cut]"


class TestExtractLinkedIssues:
    def test_dedup_and_order(self):
        issues = pcc.extract_linked_issues("Closes #1, refs #2", "see #1 and #3")
        assert issues == ["#1", "#2", "#3"]

    def test_empty(self):
        assert pcc.extract_linked_issues("no refs here") == []


def _fields(diff: str = "diff content", source: str = "my-branch") -> dict[str, str]:
    return {
        "source": source,
        "fetched_at": "2026-06-10T00:00:00+00:00",
        "pr_number": "n/a",
        "title": "n/a",
        "body": "n/a",
        "linked_issues": "n/a",
        "ci_status": "n/a",
        "diff_stat": "1 file changed",
        "diff_sha": hashlib.sha256(diff.encode()).hexdigest(),
        "diff": diff,
    }


class TestRenderAndParse:
    def test_roundtrip_fields(self):
        section = pcc.render_cache(_fields())
        assert section.startswith(pcc.CACHE_START)
        assert section.endswith(pcc.CACHE_END)
        assert pcc.parse_cached_field(section, "Source") == "my-branch"
        assert (
            pcc.parse_cached_field(section, "Diff sha")
            == hashlib.sha256(b"diff content").hexdigest()
        )

    def test_parse_missing_field_returns_empty(self):
        section = pcc.render_cache(_fields())
        assert pcc.parse_cached_field(section, "Nonexistent") == ""

    def test_find_cache_section_absent(self):
        assert pcc.find_cache_section("# rubric without cache\n") is None


class TestWriteCache:
    def test_create_when_file_missing(self, tmp_path: Path):
        rubric = tmp_path / ".maigo" / "review-rubric.md"
        section = pcc.render_cache(_fields())
        pcc.write_cache(rubric, section)
        assert rubric.read_text(encoding="utf-8") == section + "\n"

    def test_prepend_when_no_cache_section(self, tmp_path: Path):
        rubric = tmp_path / "review-rubric.md"
        rubric.write_text("# Existing rubric\n", encoding="utf-8")
        section = pcc.render_cache(_fields())
        pcc.write_cache(rubric, section)
        text = rubric.read_text(encoding="utf-8")
        assert text.startswith(pcc.CACHE_START)
        assert text.endswith("# Existing rubric\n")

    def test_replace_existing_cache_section(self, tmp_path: Path):
        rubric = tmp_path / "review-rubric.md"
        old = pcc.render_cache(_fields(diff="old diff"))
        rubric.write_text(old + "\n\n# Rubric body\n", encoding="utf-8")
        new = pcc.render_cache(_fields(diff="new diff"))
        pcc.write_cache(rubric, new)
        text = rubric.read_text(encoding="utf-8")
        assert text.count(pcc.CACHE_START) == 1
        assert "new diff" in text
        assert "old diff" not in text
        assert text.endswith("# Rubric body\n")


class TestMainCacheFlow:
    def test_cache_hit_skips_fetch(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        rubric = tmp_path / "rubric.md"
        diff = "the diff"
        rubric.write_text(pcc.render_cache(_fields(diff=diff)) + "\n", encoding="utf-8")
        monkeypatch.setattr(
            pcc,
            "current_diff_sha",
            lambda *a: hashlib.sha256(diff.encode()).hexdigest(),
        )
        monkeypatch.setattr(
            pcc,
            "fetch_context",
            lambda *a: pytest.fail("fetch_context called on cache hit"),
        )
        assert pcc.main(["my-branch", "--rubric", str(rubric)]) == 0
        out = capsys.readouterr().out
        assert out.startswith("cache_hit: true")

    def test_sha_mismatch_refetches(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        rubric = tmp_path / "rubric.md"
        rubric.write_text(
            pcc.render_cache(_fields(diff="old diff")) + "\n", encoding="utf-8"
        )
        monkeypatch.setattr(pcc, "current_diff_sha", lambda *a: "different-sha")
        monkeypatch.setattr(pcc, "fetch_context", lambda *a: _fields(diff="new diff"))
        assert pcc.main(["my-branch", "--rubric", str(rubric)]) == 0
        out = capsys.readouterr().out
        assert out.startswith("cache_hit: false")
        assert "new diff" in rubric.read_text(encoding="utf-8")

    def test_source_mismatch_refetches_without_sha_check(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        rubric = tmp_path / "rubric.md"
        rubric.write_text(
            pcc.render_cache(_fields(source="other-branch")) + "\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            pcc,
            "current_diff_sha",
            lambda *a: pytest.fail("sha check should be skipped on source mismatch"),
        )
        monkeypatch.setattr(pcc, "fetch_context", lambda *a: _fields())
        assert pcc.main(["my-branch", "--rubric", str(rubric)]) == 0
        assert capsys.readouterr().out.startswith("cache_hit: false")

    def test_no_rubric_fetches_and_creates(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        rubric = tmp_path / ".maigo" / "rubric.md"
        monkeypatch.setattr(pcc, "fetch_context", lambda *a: _fields())
        assert pcc.main(["my-branch", "--rubric", str(rubric)]) == 0
        assert capsys.readouterr().out.startswith("cache_hit: false")
        assert rubric.is_file()


class TestRunFailure:
    def test_failed_command_exits_1(self, capsys: pytest.CaptureFixture):
        with pytest.raises(SystemExit) as exc:
            pcc.run(["git", "diff", "--definitely-not-a-flag"])
        assert exc.value.code == 1
        assert "failed" in capsys.readouterr().err
