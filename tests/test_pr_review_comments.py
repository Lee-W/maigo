"""Tests for scripts.pr_review_comments — read-only extraction of reviewer comments."""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from scripts import pr_review_comments as prc

URL = "https://github.com/octo/repo/pull/7"


def _user(login: str) -> dict[str, str]:
    return {"login": login}


def _raw(
    *,
    review_comments: list[dict[str, Any]] | None = None,
    reviews: list[dict[str, Any]] | None = None,
    issue_comments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "url": URL,
        "pull": {"user": _user("octocat")},
        "review_comments": review_comments or [],
        "reviews": reviews or [],
        "issue_comments": issue_comments or [],
    }


def _inline(login: str, **extra: Any) -> dict[str, Any]:
    return {
        "user": _user(login),
        "html_url": f"{URL}#discussion_r1",
        "path": "src/a.py",
        "line": 12,
        "body": "please add a test",
        **extra,
    }


class TestFilterReviewComments:
    def test_author_comment_is_excluded(self):
        raw = _raw(review_comments=[_inline("octocat"), _inline("reviewer-a")])
        result = prc.filter_pr(raw)
        assert [c["user"] for c in result["review_comments"]] == ["reviewer-a"]

    def test_author_match_ignores_case(self):
        raw = _raw(review_comments=[_inline("OctoCat")])
        assert prc.filter_pr(raw)["review_comments"] == []

    def test_bot_comment_is_excluded(self):
        raw = _raw(
            review_comments=[_inline("github-actions[bot]"), _inline("reviewer-a")]
        )
        result = prc.filter_pr(raw)
        assert [c["user"] for c in result["review_comments"]] == ["reviewer-a"]

    def test_reply_is_excluded(self):
        raw = _raw(review_comments=[_inline("reviewer-a", in_reply_to_id=99)])
        assert prc.filter_pr(raw)["review_comments"] == []

    def test_root_comment_keeps_url_and_location(self):
        raw = _raw(review_comments=[_inline("reviewer-a")])
        (comment,) = prc.filter_pr(raw)["review_comments"]
        assert comment["url"] == f"{URL}#discussion_r1"
        assert (comment["path"], comment["line"]) == ("src/a.py", 12)

    def test_line_falls_back_to_original_line(self):
        raw = _raw(review_comments=[_inline("reviewer-a", line=None, original_line=30)])
        (comment,) = prc.filter_pr(raw)["review_comments"]
        assert comment["line"] == 30


class TestFilterReviewsAndIssueComments:
    def test_empty_review_body_is_excluded(self):
        raw = _raw(
            reviews=[
                {
                    "user": _user("reviewer-a"),
                    "state": "APPROVED",
                    "body": "  ",
                    "html_url": "u1",
                },
                {
                    "user": _user("reviewer-a"),
                    "state": "COMMENTED",
                    "body": "nit",
                    "html_url": "u2",
                },
            ]
        )
        assert [r["url"] for r in prc.filter_pr(raw)["reviews"]] == ["u2"]

    def test_author_and_bot_reviews_are_excluded(self):
        raw = _raw(
            reviews=[
                {"user": _user("octocat"), "body": "self", "html_url": "u1"},
                {"user": _user("ci[bot]"), "body": "bot", "html_url": "u2"},
            ]
        )
        assert prc.filter_pr(raw)["reviews"] == []

    def test_issue_comment_excludes_author_and_bot(self):
        raw = _raw(
            issue_comments=[
                {"user": _user("octocat"), "body": "mine", "html_url": "u1"},
                {"user": _user("ci[bot]"), "body": "bot", "html_url": "u2"},
                {"user": _user("reviewer-a"), "body": "hi", "html_url": "u3"},
            ]
        )
        assert [c["url"] for c in prc.filter_pr(raw)["issue_comments"]] == ["u3"]

    def test_output_carries_pr_author_and_url(self):
        result = prc.filter_pr(_raw())
        assert (result["url"], result["author"]) == (URL, "octocat")


class TestParseAndPages:
    def test_parse_pr_url(self):
        assert prc.parse_pr_url(URL) == ("octo", "repo", 7)

    @pytest.mark.parametrize(
        "bad", ["https://github.com/octo/repo/issues/7", "nope", ""]
    )
    def test_parse_rejects_non_pr_url(self, bad):
        with pytest.raises(prc.PrCommentsError):
            prc.parse_pr_url(bad)

    def test_decode_concatenated_pages(self):
        assert prc._decode_pages('[{"a": 1}]\n[{"a": 2}, {"a": 3}]') == [
            {"a": 1},
            {"a": 2},
            {"a": 3},
        ]


def _fake_runner(calls: list[list[str]]):
    pull = {"user": _user("octocat")}

    def run(args: list[str]) -> str:
        calls.append(args)
        path = args[1]
        if path.endswith("/pulls/7"):
            return json.dumps(pull)
        return "[]"

    return run


class TestReadOnly:
    def test_fetch_issues_only_get_api_calls(self):
        calls: list[list[str]] = []
        prc.fetch_pr(URL, _fake_runner(calls))
        assert len(calls) == 4
        for args in calls:
            assert args[0] == "api"
            assert args[2] == "--paginate"
            assert len(args) == 3  # no -X / --method / -f / -F / --input
        paths = [args[1] for args in calls]
        assert paths[0] == "repos/octo/repo/pulls/7"

    def test_default_runner_calls_gh_api_only(self, monkeypatch):
        seen: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            seen.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")

        monkeypatch.setattr(prc.subprocess, "run", fake_run)
        prc.run_gh(["api", "repos/octo/repo/pulls/7", "--paginate"])
        assert seen == [["gh", "api", "repos/octo/repo/pulls/7", "--paginate"]]

    def test_gh_failure_raises(self, monkeypatch):
        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                cmd, 1, stdout="", stderr="boom\nHTTP 404"
            )

        monkeypatch.setattr(prc.subprocess, "run", fake_run)
        with pytest.raises(prc.PrCommentsError, match="HTTP 404"):
            prc.run_gh(["api", "x", "--paginate"])


class TestMain:
    def test_main_prints_json(self, monkeypatch, capsys):
        monkeypatch.setattr(prc, "fetch_pr", lambda url: _raw())
        assert prc.main([URL]) == 0
        out = json.loads(capsys.readouterr().out)
        assert out[0]["author"] == "octocat"

    def test_main_bad_url_exits_1(self, capsys):
        assert prc.main(["nope"]) == 1
        assert "不是 PR URL" in capsys.readouterr().err
