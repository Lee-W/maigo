"""Review publication and local completion must preserve source identity and recency."""

import io
import json
import os
from pathlib import Path

import pytest

from scripts import board_state as board
from scripts import review_report as report

URL = "https://github.com/owner/project/pull/42"
HEAD = "a" * 40
BODY = "## Context\nA fix.\n\n## Verdict\nAPPROVE\n\n### Evidence\nTests passed.\n"


def publish(root, **kwargs):
    return report.publish(
        root,
        URL,
        "owner/project",
        kwargs.pop("title", "Fix ranges"),
        kwargs.pop("body", BODY),
        kwargs.pop("head_sha", HEAD),
        "APPROVE",
        **kwargs,
    )


def test_publish_adds_timestamp_and_working_toc_ignoring_code_headings(tmp_path):
    result = publish(
        tmp_path, body=BODY + "\n```md\n## Example only\n```\n\n## Context\nRepeated.\n"
    )
    text = Path(result["path"]).read_text()
    assert text.startswith("# Review: Fix ranges\n")
    assert "**最後 review：** " + result["reviewed_at"] in text
    assert text.count("](#review-section-") == 4
    for index in range(1, 5):
        assert f'<a id="review-section-{index}"></a>' in text
        assert f"](#review-section-{index})" in text
    assert "[Example only]" not in text
    assert report.metadata(text)["head_sha"] == HEAD


def test_publish_replaces_same_pr_even_after_title_change_and_clears_ack(tmp_path):
    first = publish(tmp_path)
    report.acknowledge(tmp_path, URL, "owner/project", HEAD, "reviewer")
    second = publish(tmp_path, title="Renamed PR")
    assert second["path"] == first["path"]
    assert "acknowledged_at" not in report.metadata(Path(second["path"]).read_text())
    assert "Renamed PR" in Path(second["path"]).read_text()


def test_only_superseded_owned_reports_are_deleted_after_publish(tmp_path):
    initial = publish(tmp_path)
    current = Path(initial["path"])
    old_text = current.read_text()
    same = current.with_name("review-2.md")
    same.write_text(old_text)
    flat = tmp_path / ".maigo/review-42.md"
    flat.write_text(f"# Review: Previous title\n\n**PR:** {URL}\nold\n")
    foreign = current.with_name("review-3.md")
    foreign.write_text(old_text.replace(URL, URL + "0"))
    unknown = current.with_name("review-notes.md")
    unknown.write_text("handwritten notes")
    draft = current.with_name("draft.md")
    draft.write_text("unsent draft")
    result = publish(tmp_path)
    assert set(result["removed"]) == {str(same), str(flat)}
    assert foreign.exists() and unknown.exists() and draft.exists() and current.exists()
    assert not same.exists() and not flat.exists()


def test_publish_conflict_preserves_both_current_and_history(tmp_path):
    path = Path(publish(tmp_path)["path"])
    other = path.read_text().replace(URL, URL + "0")
    path.write_text(other)
    old = path.with_name("review-2.md")
    old.write_text(other)
    with pytest.raises(ValueError, match="ownership conflict"):
        publish(tmp_path)
    assert path.read_text() == old.read_text() == other


def test_newer_current_report_cannot_be_overwritten(tmp_path):
    path = Path(publish(tmp_path)["path"])
    record = report.metadata(path.read_text())
    record["reviewed_at"] = "2099-01-01T00:00:00+00:00"
    original = report.render_report("Newer report", BODY, record)
    path.write_text(original)
    with pytest.raises(ValueError, match="newer review"):
        publish(tmp_path)
    assert path.read_text() == original


def test_cross_repo_collision_is_not_mistaken_for_same_review(tmp_path):
    first = report.publish(
        tmp_path, URL, "home/repo", "First PR", BODY, HEAD, "APPROVE"
    )
    assert Path(first["path"]).parent.name == "project-42"
    with pytest.raises(ValueError, match="ownership conflict"):
        report.publish(
            tmp_path,
            URL.replace("owner/", "another/"),
            "home/repo",
            "Other PR",
            BODY,
            HEAD,
            "APPROVE",
        )
    assert report.metadata(Path(first["path"]).read_text())["source"] == URL


@pytest.mark.parametrize("source", ["feature/review-flow", "main..feature"])
def test_local_source_keeps_one_report_per_branch_or_range(tmp_path, source):
    first = report.publish(tmp_path, source, "", "Local review", BODY, HEAD, "APPROVE")
    second = report.publish(tmp_path, source, "", "Local review", BODY, HEAD, "APPROVE")
    assert first["path"] == second["path"]
    assert report.metadata(Path(second["path"]).read_text())["source"] == source


@pytest.mark.parametrize(
    "body", ["No headings", "# Wrong H1\n" + BODY, "## Context\n```\nunfinished"]
)
def test_invalid_report_cannot_replace_previous_report(tmp_path, body):
    path = Path(publish(tmp_path)["path"])
    previous = path.read_text()
    with pytest.raises(ValueError):
        publish(tmp_path, body=body)
    assert path.read_text() == previous


def test_newer_or_malformed_reports_are_not_deleted(tmp_path):
    path = Path(publish(tmp_path)["path"])
    record = report.metadata(path.read_text())
    record["reviewed_at"] = "2099-01-01T00:00:00+00:00"
    newer = path.with_name("review-2.md")
    newer.write_text(report.render_report("Future", BODY, record))
    malformed = path.with_name("review-3.md")
    malformed.write_text("<!-- maigo-review: broken -->")
    result = publish(tmp_path)
    assert set(result["retained"]) == {str(newer), str(malformed)}
    assert not result["removed"]


def test_failed_atomic_publish_does_not_clean_history(tmp_path, monkeypatch):
    path = Path(publish(tmp_path)["path"])
    previous = path.read_text()
    old = path.with_name("review-2.md")
    old.write_text(previous)

    def fail_replace(self, target):
        raise OSError("disk failure")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="disk failure"):
        publish(tmp_path)
    assert path.read_text() == old.read_text() == previous
    assert sorted(p.name for p in path.parent.iterdir()) == ["review-2.md", "review.md"]


def test_symlink_and_busy_lock_do_not_allow_overwrite(tmp_path):
    path = Path(publish(tmp_path)["path"])
    previous = path.read_text()
    with report.report_lock(path), pytest.raises(ValueError, match="being updated"):
        publish(tmp_path)
    assert path.read_text() == previous
    path.unlink()
    target = tmp_path / "notes.md"
    target.write_text(previous)
    path.symlink_to(target)
    with pytest.raises(ValueError, match="escapes"):
        publish(tmp_path)
    assert target.read_text() == previous


def test_acknowledgement_preserves_review_time_rejects_stale_head_and_can_undo(
    tmp_path,
):
    first = publish(tmp_path)
    path = Path(first["path"])
    with pytest.raises(ValueError, match="head changed"):
        report.acknowledge(tmp_path, URL, "owner/project", "b" * 40, "reviewer")
    result = report.acknowledge(tmp_path, URL, "owner/project", HEAD, "reviewer")
    assert result["reviewed_at"] == first["reviewed_at"]
    assert result["acknowledged_by"] == "reviewer"
    assert "**已看完：** " + result["acknowledged_at"] in path.read_text()
    os.utime(path, (2000000000, 2000000000))
    assert (
        board._auto_local_verdict_at(URL, "owner/project", str(tmp_path))
        == first["reviewed_at"]
    )
    result = report.acknowledge(
        tmp_path, URL, "owner/project", HEAD, "reviewer", undo=True
    )
    assert "acknowledged_at" not in result
    assert "**已看完：** 尚未確認" in path.read_text()
    assert result["reviewed_at"] == first["reviewed_at"]


def test_cli_publish_acknowledge_and_board_review_filter(tmp_path, monkeypatch, capsys):
    body = tmp_path / "body.md"
    body.write_text(BODY)
    common = [
        "--cwd",
        str(tmp_path),
        "--source",
        URL,
        "--repo",
        "owner/project",
        "--head",
        HEAD,
    ]
    assert (
        report.main(
            [
                "publish",
                *common,
                "--title",
                "Fix ranges",
                "--body-file",
                str(body),
                "--verdict",
                "APPROVE",
            ]
        )
        == 0
    )
    capsys.readouterr()
    item = {
        "type": "👀",
        "url": URL,
        "gh_meta": {
            "state": "OPEN",
            "title": "Fix ranges",
            "author": {"login": "contributor"},
            "headRefOid": HEAD,
        },
    }
    args = [
        "--you",
        "reviewer",
        "--repo",
        "owner/project",
        "--maigo-root",
        str(tmp_path),
        "--reviews",
    ]
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps([item])))
    assert board.main(args) == 0
    row = json.loads(capsys.readouterr().out)[0]
    assert row["needs_review"] and row["status"] == "待送出"
    assert "@contributor" in row["index_entry"] and "Fix ranges" in row["index_entry"]
    assert row["last_reviewed_at"]
    assert report.main(["acknowledge", *common, "--you", "reviewer"]) == 0
    capsys.readouterr()
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps([item])))
    assert board.main(args) == 0
    assert json.loads(capsys.readouterr().out) == []
    item["gh_meta"]["headRefOid"] = "b" * 40
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps([item])))
    assert board.main(args) == 0
    assert json.loads(capsys.readouterr().out)[0]["status"] == "↩︎ 回你的球"


def test_cli_failure_is_actionable_and_does_not_write(tmp_path, capsys):
    assert (
        report.main(
            [
                "acknowledge",
                "--cwd",
                str(tmp_path),
                "--source",
                URL,
                "--head",
                "bad",
                "--you",
                "reviewer",
            ]
        )
        == 1
    )
    assert "full commit hash" in capsys.readouterr().err
    assert not (tmp_path / ".maigo").exists()
