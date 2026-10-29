"""Tests for scripts.maigo_tidy — `/maigo:tidy` 的 dry-run 清單與規則型 apply。"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts import board_sync
from scripts import maigo_tidy as tidy

NOW = datetime(2026, 10, 29, tzinfo=timezone.utc)
OLD = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
STATES = {
    ("pr", "11"): "merged",
    ("pr", "12"): "open",
    ("review", "13"): "closed",
    ("issue", "5"): "closed",
    ("i", "11"): "merged",
}


def fake_state(group: str, ident: str) -> str | None:
    return STATES.get((group, ident))


def write(path: Path, text: str = "x\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def make_maigo(tmp_path: Path) -> Path:
    maigo = tmp_path / ".maigo"
    write(maigo / "plan.md", "# Plan: Fix thing\n")
    write(maigo / "token-usage.jsonl", '{"a": 1}\n')
    write(maigo / "pr" / "11" / "reply-draft.md")
    write(maigo / "pr" / "12" / "reply-draft.md")
    write(maigo / "review" / "13" / "review.md")
    write(maigo / "issue" / "5" / "rubric.md")
    write(maigo / "i" / "11.md")
    write(maigo / "topic" / "foo" / "plan.md")
    write(maigo / "evals" / "a.json")
    write(maigo / "evals" / "b.json")
    write(maigo / "evals" / "sub" / "c.json")
    old = write(maigo / "_archive" / "pr" / "1" / "x.md")
    os.utime(old.parent, (OLD, OLD))
    fresh = write(maigo / "_archive" / "pr" / "2" / "x.md")
    os.utime(old, (OLD, OLD))
    os.utime(fresh, (NOW.timestamp(), NOW.timestamp()))
    return maigo


def build(maigo: Path, state=fake_state):
    return tidy.build_actions(maigo, now=NOW, item_state=state, home_repo_name="")


def snapshot(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def by_path(actions, path: str) -> tidy.TidyAction:
    return next(a for a in actions if a.path == path)


def run_apply(maigo: Path, actions, confirmed=frozenset()):
    backup = maigo / "_internal" / "tidy" / "backup" / "T1"
    return tidy.apply(actions, maigo_dir=maigo, backup_root=backup, confirmed=confirmed)


def test_dry_run_touches_nothing(tmp_path, capsys):
    maigo = make_maigo(tmp_path)
    before = snapshot(tmp_path)
    dirs_before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    assert tidy.main(["--dir", str(maigo), "--no-gh"]) == 0
    build(maigo)
    assert snapshot(tmp_path) == before
    assert (
        sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")) == dirs_before
    )
    assert capsys.readouterr().out


def test_apply_skips_needs_confirm_without_confirm_flag(tmp_path):
    maigo = make_maigo(tmp_path)
    actions = build(maigo)
    needs = [a for a in actions if a.needs_confirm]
    assert {a.kind for a in needs} >= {"archive", "delete-candidate", "unregistered"}
    run_apply(maigo, actions)
    assert (maigo / "topic" / "foo" / "plan.md").is_file()
    assert (maigo / "evals" / "a.json").is_file()
    assert (maigo / "_archive" / "pr" / "1" / "x.md").is_file()
    backup = maigo / "_internal" / "tidy" / "backup" / "T1"
    assert not (backup / "evals").exists()


def test_apply_runs_confirmed_delete_only_for_listed_path(tmp_path):
    maigo = make_maigo(tmp_path)
    actions = build(maigo)
    delete = by_path(actions, ".maigo/_archive/pr/1")
    assert delete.kind == "delete-candidate" and delete.needs_confirm
    run_apply(maigo, actions, {delete.path})
    assert not (maigo / "_archive" / "pr" / "1").exists()
    assert (maigo / "_archive" / "pr" / "2" / "x.md").is_file()
    assert (maigo / "evals" / "a.json").is_file()
    backup = maigo / "_internal" / "tidy" / "backup" / "T1"
    assert (backup / "_archive" / "pr" / "1" / "x.md").is_file()


def test_merged_pr_dir_archives_to_mirrored_path(tmp_path):
    maigo = make_maigo(tmp_path)
    actions = build(maigo)
    for path, group in (
        (".maigo/pr/11", "pr"),
        (".maigo/review/13", "review"),
        (".maigo/issue/5", "issue"),
        (".maigo/i/11.md", "i"),
    ):
        action = by_path(actions, path)
        assert action.kind == "archive" and not action.needs_confirm
        assert action.target == path.replace(".maigo/", ".maigo/_archive/", 1)
    assert not any(a.path == ".maigo/pr/12" for a in actions)  # open：不動
    run_apply(maigo, actions)
    assert (maigo / "_archive" / "pr" / "11" / "reply-draft.md").is_file()
    assert (maigo / "_archive" / "issue" / "5" / "rubric.md").is_file()
    assert (maigo / "_archive" / "i" / "11.md").is_file()
    assert not (maigo / "pr" / "11").exists()
    assert (maigo / "pr" / "12" / "reply-draft.md").is_file()


def test_unknown_state_is_left_alone(tmp_path):
    maigo = make_maigo(tmp_path)
    actions = build(maigo, state=lambda group, ident: None)
    unknown = by_path(actions, ".maigo/pr/11")
    assert unknown.needs_confirm and "狀態查不到" in unknown.reason
    run_apply(maigo, actions)
    assert (maigo / "pr" / "11" / "reply-draft.md").is_file()
    assert (maigo / "issue" / "5" / "rubric.md").is_file()
    assert not (maigo / "_archive" / "pr" / "11").exists()


def test_no_state_lookup_lists_no_settlement_actions(tmp_path):
    maigo = make_maigo(tmp_path)
    actions = build(maigo, state=None)
    assert not any(a.path.startswith((".maigo/pr/", ".maigo/i/")) for a in actions)
    assert by_path(actions, ".maigo/plan.md").kind == "migrate"


def test_legacy_logs_merge_into_existing_internal_log(tmp_path):
    maigo = make_maigo(tmp_path)
    write(maigo / "_internal" / "log" / "token-usage.jsonl", '{"b": 2}\n')
    write(maigo / "session-head.json", '{"old": true}')
    write(maigo / "_internal" / "log" / "session-head.json", '{"new": true}')
    actions = build(maigo)
    assert by_path(actions, ".maigo/token-usage.jsonl").kind == "move-internal-log"
    run_apply(maigo, actions)
    merged = (maigo / "_internal" / "log" / "token-usage.jsonl").read_text()
    assert merged == '{"b": 2}\n{"a": 1}\n'
    assert not (maigo / "token-usage.jsonl").exists()
    assert (
        maigo / "_internal" / "log" / "session-head.json"
    ).read_text() == '{"new": true}'
    assert not (maigo / "session-head.json").exists()


def test_legacy_log_moves_when_internal_log_missing(tmp_path):
    maigo = make_maigo(tmp_path)
    run_apply(maigo, build(maigo))
    assert (
        maigo / "_internal" / "log" / "token-usage.jsonl"
    ).read_text() == '{"a": 1}\n'
    assert not (maigo / "token-usage.jsonl").exists()


def test_legacy_plan_migrates_to_topic(tmp_path):
    maigo = make_maigo(tmp_path)
    actions = build(maigo)
    action = by_path(actions, ".maigo/plan.md")
    assert (
        action.target == ".maigo/topic/fix-thing/plan.md" and not action.needs_confirm
    )
    run_apply(maigo, actions)
    assert (maigo / "topic" / "fix-thing" / "plan.md").is_file()
    assert not (maigo / "plan.md").exists()
    backup = maigo / "_internal" / "tidy" / "backup" / "T1"
    assert (backup / "plan.md").read_text() == "# Plan: Fix thing\n"


def test_log_over_threshold_rotates_to_one_generation(tmp_path):
    maigo = make_maigo(tmp_path)
    log = maigo / "_internal" / "log"
    write(log / "test-failures.jsonl", "row\n" * (tidy.LOG_ROTATE_MAX_LINES + 1))
    write(log / "test-failures.1.jsonl", "previous generation\n")
    write(log / "soyo-must-fix.jsonl", "row\n" * tidy.LOG_ROTATE_MAX_LINES)
    actions = build(maigo)
    rotate = [a for a in actions if a.kind == "rotate-log"]
    assert [a.path for a in rotate] == [".maigo/_internal/log/test-failures.jsonl"]
    run_apply(maigo, actions)
    assert not (log / "test-failures.jsonl").exists()
    assert (log / "test-failures.1.jsonl").read_text().count("row") == 2001
    assert (log / "soyo-must-fix.jsonl").is_file()
    backup = maigo / "_internal" / "tidy" / "backup" / "T1" / "_internal" / "log"
    assert (backup / "test-failures.1.jsonl").read_text() == "previous generation\n"


def test_topic_archive_requires_confirm(tmp_path):
    maigo = make_maigo(tmp_path)
    actions = build(maigo)
    topic = by_path(actions, ".maigo/topic/foo")
    assert topic.kind == "archive" and topic.needs_confirm
    run_apply(maigo, actions)
    assert (maigo / "topic" / "foo" / "plan.md").is_file()
    run_apply(maigo, build(maigo), {".maigo/topic/foo/"})
    assert (maigo / "_archive" / "topic" / "foo" / "plan.md").is_file()
    assert not (maigo / "topic" / "foo").exists()


def test_backup_written_before_any_move(tmp_path, monkeypatch):
    maigo = make_maigo(tmp_path)
    backup = maigo / "_internal" / "tidy" / "backup" / "T1"
    seen: list[bool] = []
    real_move = tidy._move
    real_archive = board_sync.archive_relpaths

    def spy_move(source, destination):
        seen.append((backup / "plan.md").is_file() and (backup / "pr" / "11").is_dir())
        real_move(source, destination)

    def spy_archive(root, rels):
        seen.append((backup / "plan.md").is_file() and (backup / "pr" / "11").is_dir())
        return real_archive(root, rels)

    monkeypatch.setattr(tidy, "_move", spy_move)
    monkeypatch.setattr(board_sync, "archive_relpaths", spy_archive)
    run_apply(maigo, build(maigo))
    assert seen and all(seen)


def test_unregistered_dir_listed_once(tmp_path):
    maigo = make_maigo(tmp_path)
    actions = build(maigo)
    evals = [a for a in actions if a.path.startswith(".maigo/evals")]
    assert [a.path for a in evals] == [".maigo/evals"]
    assert evals[0].kind == "unregistered" and evals[0].needs_confirm
    assert "3 個檔" in evals[0].reason
    run_apply(maigo, actions, {".maigo/evals"})
    assert not (maigo / "evals").exists()
    backup = maigo / "_internal" / "tidy" / "backup" / "T1"
    assert (backup / "evals" / "sub" / "c.json").is_file()


def test_nested_dot_maigo_is_listed_and_deleted_only_when_confirmed(tmp_path):
    maigo = make_maigo(tmp_path)
    write(maigo / ".maigo" / "session-head.json", "{}")
    actions = build(maigo)
    nested = by_path(actions, ".maigo/.maigo")
    assert nested.kind == "remove-nested-dot-maigo" and nested.needs_confirm
    run_apply(maigo, actions)
    assert (maigo / ".maigo" / "session-head.json").is_file()
    run_apply(maigo, build(maigo), {nested.path})
    assert not (maigo / ".maigo").exists()


def test_archive_entry_within_retention_is_not_a_candidate(tmp_path):
    maigo = make_maigo(tmp_path)
    paths = [a.path for a in build(maigo) if a.kind == "delete-candidate"]
    assert ".maigo/_archive/pr/1" in paths
    assert ".maigo/_archive/pr/2" not in paths


def test_existing_archive_destination_is_not_overwritten(tmp_path):
    maigo = make_maigo(tmp_path)
    write(maigo / "_archive" / "pr" / "11" / "keep.md", "kept\n")
    results = run_apply(maigo, build(maigo))
    assert any("目的地已存在" in line for line in results)
    assert (maigo / "pr" / "11" / "reply-draft.md").is_file()
    assert (maigo / "_archive" / "pr" / "11" / "keep.md").read_text() == "kept\n"


def test_dry_run_output_shape(tmp_path):
    maigo = make_maigo(tmp_path)
    text = tidy.render(build(maigo))
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    assert headings == [
        "## 規則型動作（--apply 會執行）",
        "## 需要你逐項勾選",
        "## 未登記（只列不動）",
        "## 統計",
    ]
    for line in text.splitlines():
        assert line.startswith(("## ", "- ")), line
        assert not line.startswith("|")
        if "：.maigo/" in line:
            body = line.split("：", 1)[1]
            path = body.split(" → ")[0].split(" ｜ ")[0]
            assert path.startswith(".maigo/"), line
            assert " ｜ 依據：" in line
            if " → " in body:
                assert body.split(" → ", 1)[1].startswith(".maigo/"), line
    assert any(line.startswith("- [ ] ") for line in text.splitlines())


def test_dry_run_output_empty_sections_say_none(tmp_path):
    maigo = tmp_path / ".maigo"
    maigo.mkdir()
    actions = tidy.build_actions(maigo, now=NOW, item_state=None, home_repo_name="")
    text = tidy.render(actions, state_checked=False)
    assert text.splitlines().count("- （無）") == 4
    assert "略過（--no-gh）" in text


def test_cli_apply_without_confirm_leaves_confirm_items_and_writes_backup(
    tmp_path, capsys
):
    maigo = make_maigo(tmp_path)
    assert tidy.main(["--dir", str(maigo), "--no-gh", "--apply"]) == 0
    out = capsys.readouterr().out
    assert "## 執行結果" in out and "備份：.maigo/_internal/tidy/backup/" in out
    backups = list((maigo / "_internal" / "tidy" / "backup").iterdir())
    assert len(backups) == 1 and (backups[0] / "plan.md").is_file()
    assert (maigo / "topic" / "foo" / "plan.md").is_file()
    assert (maigo / "evals" / "a.json").is_file()
    assert (maigo / "pr" / "11").is_dir()  # --no-gh：不做結案判定


def test_cli_rejects_confirm_for_unlisted_path(tmp_path, capsys):
    maigo = make_maigo(tmp_path)
    before = snapshot(tmp_path)
    assert (
        tidy.main(
            ["--dir", str(maigo), "--no-gh", "--apply", "--confirm", ".maigo/plan.md"]
        )
        == 1
    )
    assert snapshot(tmp_path) == before
    assert "不在需要勾選的清單裡" in capsys.readouterr().err


def test_cli_confirm_without_apply_is_rejected(tmp_path):
    maigo = make_maigo(tmp_path)
    assert tidy.main(["--dir", str(maigo), "--no-gh", "--confirm", ".maigo/evals"]) == 1


def test_gh_item_state_maps_states_and_non_numeric_ids(tmp_path, monkeypatch):
    calls: list[list[str]] = []
    outputs = {"pr": "MERGED", "issue": "CLOSED"}

    def fake_gh(args, cwd):
        calls.append(args)
        return {"MERGED": "merged", "CLOSED": "closed"}[outputs[args[0]]]

    monkeypatch.setattr(tidy, "_gh_state", fake_gh)
    state = tidy.make_gh_item_state(tmp_path)
    assert state("pr", "7") == "merged"
    assert state("issue", "7") == "closed"
    assert state("pr", "7") == "merged"
    assert len(calls) == 2  # 第二次 pr 查詢走快取
    assert state("pr", "repo-7") is None
    assert len(calls) == 2


def test_archive_relpaths_is_shared_with_board_sync(tmp_path):
    (tmp_path / ".maigo" / "issue" / "9").mkdir(parents=True)
    moved, skipped, missing = board_sync.archive_relpaths(
        tmp_path, ["issue/9", "topic/x"]
    )
    assert (moved, skipped, missing) == (["issue/9"], [], ["topic/x"])


@pytest.mark.parametrize("flag", ["--apply", "--no-gh"])
def test_missing_dir_is_an_error(tmp_path, flag):
    assert tidy.main(["--dir", str(tmp_path / "nope"), flag]) == 1
