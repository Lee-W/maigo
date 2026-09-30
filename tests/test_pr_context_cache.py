"""Tests for scripts.pr_context_cache."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

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
        "review_threads": "n/a",
        "reviews": "n/a",
        "comments": "n/a",
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
    @pytest.mark.parametrize(
        "source",
        [
            pytest.param("https://github.com/o/r/pull/42", id="url"),
            pytest.param("42", id="number"),
            pytest.param("#42", id="hash-number"),
        ],
    )
    @pytest.mark.parametrize("legacy", [False, True], ids=["current", "flat-fallback"])
    def test_pr_refreshes_metadata_with_unchanged_diff(
        self, source, legacy, tmp_path, monkeypatch, capsys
    ):
        rubric = tmp_path / "review" / "42" / "rubric.md"
        old_path = tmp_path / "review-rubric-42.md" if legacy else rubric
        old_path.parent.mkdir(parents=True, exist_ok=True)
        old = (
            pcc.render_cache(_fields(source=source)) + "\n\n# Review rubric: original\n"
        )
        old_path.write_text(old)
        fresh = {
            **_fields(source=source),
            "ci_status": "tests failed",
            "body": "Closes #73",
            "linked_issues": "#73",
            "review_threads": "[RESOLVED] a.py:2",
            "reviews": "CHANGES_REQUESTED: missing boundary",
            "comments": "new maintainer feedback",
        }
        fetch = mock.Mock(return_value=fresh)
        monkeypatch.setattr(pcc, "fetch_context", fetch)
        monkeypatch.setattr(pcc, "current_diff_sha", lambda *a: fresh["diff_sha"])
        monkeypatch.setattr(
            pcc,
            "_resolve_rubric_path",
            lambda *a: (rubric, old_path if legacy else None),
        )

        assert pcc.main([source]) == 0
        expected_section = pcc.render_cache(fresh)
        assert pcc.find_cache_section(rubric.read_text()) == expected_section
        assert (
            capsys.readouterr().out
            == f"cache_hit: false\nrubric: {rubric}\n{expected_section}\n"
        )
        assert fetch.mock_calls == [mock.call(source, "pr", "main")]
        if legacy:
            assert old_path.read_text() == old
        else:
            assert rubric.read_text().endswith("# Review rubric: original\n")

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

    def test_no_rubric_conflict_exits_3_without_writing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        monkeypatch.setattr(
            pcc, "_resolve_rubric_path", lambda source, kind: (None, None)
        )
        monkeypatch.setattr(
            pcc,
            "fetch_context",
            lambda *a: pytest.fail("fetch_context called despite conflict"),
        )
        assert pcc.main(["my-branch"]) == 3

    def test_flat_fallback_cache_hit_writes_new_path_and_leaves_flat_untouched(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        """(a) 只有扁平檔、Source+sha 吻合 → cache_hit: true、新路徑寫入、扁平檔不變。"""
        flat = tmp_path / "flat-rubric.md"
        diff = "the diff"
        flat.write_text(pcc.render_cache(_fields(diff=diff)) + "\n", encoding="utf-8")
        flat_sha_before = hashlib.sha256(flat.read_bytes()).hexdigest()

        new_path = tmp_path / "review" / "42" / "rubric.md"
        monkeypatch.setattr(
            pcc, "_resolve_rubric_path", lambda source, kind: (new_path, flat)
        )
        monkeypatch.setattr(
            pcc,
            "current_diff_sha",
            lambda *a: hashlib.sha256(diff.encode()).hexdigest(),
        )
        monkeypatch.setattr(
            pcc,
            "fetch_context",
            lambda *a: pytest.fail("fetch_context called on flat cache hit"),
        )
        assert pcc.main(["my-branch"]) == 0
        out = capsys.readouterr().out
        assert out.startswith("cache_hit: true")
        assert new_path.is_file()
        assert pcc.find_cache_section(new_path.read_text(encoding="utf-8")) is not None
        assert hashlib.sha256(flat.read_bytes()).hexdigest() == flat_sha_before

    def test_flat_fallback_sha_mismatch_refetches_leaves_flat_untouched(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        """(b) 只有扁平檔、sha 不同 → cache_hit: false、扁平檔不變、新路徑被寫入。"""
        flat = tmp_path / "flat-rubric.md"
        flat.write_text(
            pcc.render_cache(_fields(diff="old diff")) + "\n", encoding="utf-8"
        )
        flat_sha_before = hashlib.sha256(flat.read_bytes()).hexdigest()

        new_path = tmp_path / "review" / "42" / "rubric.md"
        monkeypatch.setattr(
            pcc, "_resolve_rubric_path", lambda source, kind: (new_path, flat)
        )
        monkeypatch.setattr(pcc, "current_diff_sha", lambda *a: "different-sha")
        monkeypatch.setattr(pcc, "fetch_context", lambda *a: _fields(diff="new diff"))
        assert pcc.main(["my-branch"]) == 0
        out = capsys.readouterr().out
        assert out.startswith("cache_hit: false")
        assert "new diff" in new_path.read_text(encoding="utf-8")
        assert hashlib.sha256(flat.read_bytes()).hexdigest() == flat_sha_before


def _stub_resolution(**overrides) -> SimpleNamespace:
    fields = {
        "status": "new",
        "path": ".maigo/review/42/rubric.md",
        "existing_topic": None,
        "incoming_topic": "Review rubric: stub",
        "suggested_path": None,
        "legacy_path": None,
        "flat_path": None,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


class TestResolveRubricPath:
    """
    `_resolve_rubric_path()` calls `artifact_path.resolve_for_write()` per
    kind (pr/branch/range) and translates its Resolution into either a
    `(rubric_path, flat_fallback)` tuple or the conflict stdout + `(None, None)`.
    `resolve_for_write()` itself is tested in `tests/test_artifact_path.py` —
    these tests only check the plumbing.
    """

    def test_pr_kind_builds_url_and_title_topic(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(pcc, "repo_slug", lambda: "o/r")
        monkeypatch.setattr(pcc, "run", lambda *a, **kw: "Fix the thing")
        captured: dict = {}

        def fake_resolve_for_write(kind, topic, *, url=None, home_repo=""):
            captured.update(kind=kind, topic=topic, url=url, home_repo=home_repo)
            return _stub_resolution(path=".maigo/review/42/rubric.md")

        monkeypatch.setattr(pcc, "resolve_for_write", fake_resolve_for_write)
        result = pcc._resolve_rubric_path("42", "pr")
        assert result == (Path(".maigo/review/42/rubric.md"), None)
        assert captured == {
            "kind": "review-rubric",
            "topic": "Review rubric: Fix the thing",
            "url": "https://github.com/o/r/pull/42",
            "home_repo": "o/r",
        }

    def test_branch_kind_has_no_url(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(pcc, "repo_slug", lambda: "o/r")
        captured: dict = {}

        def fake_resolve_for_write(kind, topic, *, url=None, home_repo=""):
            captured.update(kind=kind, topic=topic, url=url)
            return _stub_resolution(path=".maigo/review/my-branch/rubric.md")

        monkeypatch.setattr(pcc, "resolve_for_write", fake_resolve_for_write)
        result = pcc._resolve_rubric_path("my-branch", "branch")
        assert result == (Path(".maigo/review/my-branch/rubric.md"), None)
        assert captured == {
            "kind": "review-rubric",
            "topic": "Review rubric: my-branch",
            "url": None,
        }

    def test_range_kind_has_no_url(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(pcc, "repo_slug", lambda: "o/r")
        captured: dict = {}

        def fake_resolve_for_write(kind, topic, *, url=None, home_repo=""):
            captured.update(kind=kind, topic=topic, url=url)
            return _stub_resolution(path=".maigo/review/main-feature/rubric.md")

        monkeypatch.setattr(pcc, "resolve_for_write", fake_resolve_for_write)
        result = pcc._resolve_rubric_path("main..feature", "range")
        assert result == (Path(".maigo/review/main-feature/rubric.md"), None)
        assert captured == {
            "kind": "review-rubric",
            "topic": "Review rubric: main..feature",
            "url": None,
        }

    def test_returns_flat_fallback_when_present(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(pcc, "repo_slug", lambda: "o/r")
        monkeypatch.setattr(pcc, "run", lambda *a, **kw: "Fix the thing")
        monkeypatch.setattr(
            pcc,
            "resolve_for_write",
            lambda *a, **kw: _stub_resolution(
                path=".maigo/review/42/rubric.md",
                flat_path=".maigo/review-rubric-42.md",
            ),
        )
        result = pcc._resolve_rubric_path("42", "pr")
        assert result == (
            Path(".maigo/review/42/rubric.md"),
            Path(".maigo/review-rubric-42.md"),
        )

    def test_conflict_prints_owner_and_suggestion_and_returns_none(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ):
        monkeypatch.setattr(pcc, "repo_slug", lambda: "o/r")
        monkeypatch.setattr(
            pcc,
            "resolve_for_write",
            lambda *a, **kw: _stub_resolution(
                status="conflict",
                path=None,
                existing_topic="Review rubric: Some other PR",
                suggested_path=".maigo/review/42/rubric-2.md",
            ),
        )
        result = pcc._resolve_rubric_path("42", "pr")
        assert result == (None, None)
        out = capsys.readouterr().out
        assert "status: conflict" in out
        assert "conflict_owner: Review rubric: Some other PR" in out
        assert "suggest: .maigo/review/42/rubric-2.md" in out


class TestRenderReviewThreads:
    def test_marks_unresolved_open(self):
        nodes = [
            {
                "isResolved": False,
                "path": "src/foo.py",
                "line": 10,
                "comments": {
                    "nodes": [
                        {"author": {"login": "tp"}, "body": "why isinstance here?"}
                    ]
                },
            },
            {
                "isResolved": True,
                "path": "src/bar.py",
                "line": 20,
                "comments": {"nodes": [{"author": {"login": "wei"}, "body": "fixed"}]},
            },
        ]
        rendered = pcc.render_review_threads(nodes)
        assert "[OPEN]" in rendered
        assert "[RESOLVED]" in rendered
        assert "src/foo.py:10" in rendered
        assert "tp: why isinstance here?" in rendered

    def test_empty_returns_na(self):
        assert pcc.render_review_threads([]) == "n/a"


class TestRenderReviews:
    def test_renders_author_state_body(self):
        raw = json.dumps(
            {
                "reviews": [
                    {
                        "author": {"login": "tp"},
                        "state": "CHANGES_REQUESTED",
                        "body": "please fix",
                    }
                ]
            }
        )
        rendered = pcc.render_reviews(raw)
        assert "tp **CHANGES_REQUESTED**: please fix" in rendered

    def test_empty_returns_na(self):
        assert pcc.render_reviews(json.dumps({"reviews": []})) == "n/a"

    def test_blank_input_returns_na(self):
        assert pcc.render_reviews("") == "n/a"


class TestRenderComments:
    def test_renders_author_body(self):
        raw = json.dumps(
            {
                "comments": [
                    {"author": {"login": "wei"}, "body": "did you check TP's thread?"}
                ]
            }
        )
        rendered = pcc.render_comments(raw)
        assert "wei: did you check TP's thread?" in rendered

    def test_empty_returns_na(self):
        assert pcc.render_comments(json.dumps({"comments": []})) == "n/a"


class TestFetchReviewThreads:
    def test_missing_owner_or_name_returns_na(self):
        assert pcc.fetch_review_threads("", "repo", "1") == "n/a"
        assert pcc.fetch_review_threads("owner", "", "1") == "n/a"

    @pytest.mark.parametrize("hostname", ["github.com", "github.example"])
    def test_parses_graphql_response(self, hostname, monkeypatch: pytest.MonkeyPatch):
        graphql_response = json.dumps(
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "nodes": [
                                    {
                                        "isResolved": False,
                                        "path": "a.py",
                                        "line": 5,
                                        "comments": {
                                            "nodes": [
                                                {
                                                    "author": {"login": "tp"},
                                                    "body": "concern here",
                                                }
                                            ]
                                        },
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        )
        run = mock.Mock(return_value=graphql_response)
        monkeypatch.setattr(pcc, "run", run)
        rendered = pcc.fetch_review_threads("owner", "repo", "42", hostname=hostname)
        assert "[OPEN]" in rendered
        assert "a.py:5" in rendered
        command = run.call_args.args[0]
        assert command[:2] == ["gh", "api"]
        assert command[command.index("--hostname") + 1] == hostname
        assert "owner=owner" in command
        assert "name=repo" in command
        assert "number=42" in command


@pytest.mark.parametrize(
    ("source", "url"),
    [
        pytest.param(
            "https://github.com/remote/project/pull/42",
            "https://github.com/remote/project/pull/42",
            id="cross-repo",
        ),
        pytest.param(
            "42", "https://github.com/local/workspace/pull/42", id="local-number"
        ),
        pytest.param(
            "#42", "https://github.com/local/workspace/pull/42", id="local-hash-number"
        ),
        pytest.param(
            "https://github.example/remote/project/pull/42",
            "https://github.example/remote/project/pull/42",
            id="enterprise-host",
        ),
    ],
)
def test_pr_context_uses_canonical_target_and_supported_stats(source, url, monkeypatch):
    metadata = {
        "url": url,
        "title": "Fix ranges",
        "body": "Closes #73",
        "number": 42,
        "changedFiles": 3,
        "additions": 8,
        "deletions": 2,
        "reviews": [
            {
                "author": {"login": "reviewer"},
                "state": "CHANGES_REQUESTED",
                "body": "fix boundary",
            }
        ],
        "comments": [{"author": {"login": "author"}, "body": "working on it"}],
    }

    def command_output(command, check=True):
        if command[:3] == ["gh", "repo", "view"]:
            return "local/workspace"
        if command[:3] == ["gh", "pr", "view"]:
            return json.dumps(metadata)
        if command[:3] == ["gh", "pr", "checks"]:
            return "tests pending"
        if command[:3] == ["gh", "pr", "diff"]:
            return "" if "--stat" in command else "full diff"
        raise AssertionError(command)

    run = mock.Mock(side_effect=command_output)
    threads = mock.Mock(return_value="[OPEN] ranges.py:2")
    monkeypatch.setattr(pcc, "run", run)
    monkeypatch.setattr(pcc, "fetch_review_threads", threads)
    fields = pcc.fetch_context(source, "pr", "main")
    host, owner, name = url.split("/")[2:5]
    assert threads.mock_calls == [mock.call(owner, name, "42", hostname=host)]
    assert fields["diff_stat"] == "3 files changed, 8 insertions(+), 2 deletions(-)"
    assert fields["reviews"] == "- reviewer **CHANGES_REQUESTED**: fix boundary"
    assert fields["comments"] == "- author: working on it"
    assert run.mock_calls == [
        mock.call(
            [
                "gh",
                "pr",
                "view",
                source.lstrip("#"),
                "--json",
                "url,title,body,number,additions,deletions,changedFiles,reviews,comments",
            ]
        ),
        mock.call(["gh", "pr", "diff", url]),
        mock.call(["gh", "pr", "checks", url], check=False),
    ]


class TestRunFailure:
    def test_failed_command_exits_1(self, capsys: pytest.CaptureFixture):
        with pytest.raises(SystemExit) as exc:
            pcc.run(["git", "diff", "--definitely-not-a-flag"])
        assert exc.value.code == 1
        assert "failed" in capsys.readouterr().err
