"""Tests for scripts.rewrite_note_paths — gf-clean paths in board detail-file notes."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts import board_refresh as refresh
from scripts import rewrite_note_paths as rnp

HEAD = "# 👀 待送出 — t\n\n- 連結：<https://github.com/o/r/pull/1>\n\n## 判斷\n\nx\n\n## 筆記\n\n"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for rel in (
        ".maigo/review/1261/review.md",
        ".maigo/review/1/review.md",
        ".maigo/review/1/rubric.md",
        ".maigo/pr/76801/reply-draft.md",
        ".maigo/pr/2/draft.md",
        ".maigo/review/1/draft.md",
        "src/x.py",
    ):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n")
    (tmp_path / ".maigo/i").mkdir(parents=True, exist_ok=True)
    return tmp_path


def note(repo: Path, body: str, *, head: str = HEAD, newline: str = "\n") -> Path:
    path = repo / ".maigo/i/1.md"
    path.write_bytes((head + body).replace("\n", newline).encode("utf-8"))
    return path


def plan(repo: Path, path: Path) -> rnp.FilePlan:
    return rnp.plan_file(path, maigo_dir=repo / ".maigo", repo_root=repo)


def rewritten(repo: Path, line: str) -> str:
    result = plan(repo, note(repo, line + "\n")).new_text
    return result.removeprefix(HEAD).removesuffix("\n")


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("- review/1261/review.md", "- ../review/1261/review.md"),
        (
            "- 回覆草稿：.maigo/pr/76801/reply-draft.md",
            "- 回覆草稿：`../pr/76801/reply-draft.md`",
        ),
        (
            "- 報告：../review/1/review.md（NEEDS_CHANGES）",
            "- 報告：`../review/1/review.md`（NEEDS_CHANGES）",
        ),
        (
            "- 細節：../review/1/rubric.md，草稿見上",
            "- 細節：`../review/1/rubric.md`，草稿見上",
        ),
        ("- 自己的 PR：../pr/2/draft.md", "- 自己的 PR：`../pr/2/draft.md`"),
        ("- 自己的 PR：../pr/2/draft.md。", "- 自己的 PR：`../pr/2/draft.md`。"),
        ("- 原始碼：src/x.py:3", "- 原始碼：`src/x.py:3`"),
        ("- 原始碼：src/x.py:3（見）", "- 原始碼：`src/x.py:3`（見）"),
    ],
)
def test_rewrites_old_forms_and_delimits_adjacent_paths(repo, before, after):
    assert rewritten(repo, before) == after


@pytest.mark.parametrize(
    "line",
    [
        "- ../review/1/review.md",
        "- 報告：`../review/1/review.md`（舊）",
        "- [報告](../review/1/review.md)",
        "- 報告： ../review/1/review.md",
        "- 報告：<../review/1/review.md>",
        "- 下一步：`gh pr review 1 --body-file .maigo/review/1/draft.md`",
        "- 連結：<https://github.com/o/r/pull/1/files/a/b.md>",
        "- 連結 https://example.com/a/b.md 後面",
        "- 沒有路徑的一般文字：好",
    ],
)
def test_leaves_protected_shapes_byte_for_byte(repo, line):
    path = note(repo, line + "\n")
    result = plan(repo, path)
    assert result.new_text.encode("utf-8") == path.read_bytes()
    assert result.changes == []


def test_fenced_blocks_are_untouched(repo):
    body = "```text\n報告：../review/1/review.md（x）\n- review/1261/review.md\n```\n~~~\n報告：../review/1/review.md（x）\n~~~\n"
    path = note(repo, body)
    result = plan(repo, path)
    assert result.new_text.encode("utf-8") == path.read_bytes()
    assert result.changes == [] and result.skips == []


def test_facts_before_judgment_are_never_touched(repo):
    head = "# t\n\n- 報告：../review/1/review.md（x）\n- review/1261/review.md\n\n## 判斷\n\n"
    path = note(repo, "- review/1261/review.md\n", head=head)
    result = plan(repo, path)
    assert result.new_text == head + "- ../review/1261/review.md\n"
    assert [c["line"] for c in result.changes] == [8]


def test_file_without_judgment_heading_is_skipped(repo):
    path = repo / ".maigo/i/1.md"
    path.write_text("# t\n\n- review/1261/review.md\n")
    result = plan(repo, path)
    assert result.skipped_reason and result.changes == []


@pytest.mark.parametrize(
    "line", ["- review/9/review.md", "- 報告：.maigo/review/9/review.md（x）"]
)
def test_missing_legacy_targets_are_skipped_and_line_unchanged(repo, line):
    path = note(repo, line + "\n")
    result = plan(repo, path)
    assert result.new_text.encode("utf-8") == path.read_bytes()
    assert result.changes == [] and len(result.skips) == 1


def test_plain_text_that_looks_like_a_path_is_not_reported(repo):
    path = note(repo, "- 報告：src/nope.py（x）\n- 比例 1/2.5 之類\n")
    result = plan(repo, path)
    assert result.new_text.encode("utf-8") == path.read_bytes()
    assert result.changes == [] and result.skips == []


@pytest.mark.parametrize(
    "body",
    [
        "手動送出 gh pr review 1 --body-file .maigo/review/1/draft.md 即可\n",
        "段落\n\n    cat .maigo/review/1/draft.md\n",
        "- 先 cat .maigo/review/1/draft.md 再看\n",
        "- 說明 ``code `.maigo/review/1/draft.md` 中文`` 後面\n",
    ],
    ids=["prose-command", "indented-code", "command-word", "double-backtick"],
)
def test_command_strings_and_code_are_left_alone_and_reported(repo, body):
    path = note(repo, body)
    result = plan(repo, path)
    assert result.new_text.encode("utf-8") == path.read_bytes()
    assert result.changes == []
    assert result.skips and result.skips[0]["reason"] == rnp.CODE_REASON


def test_indented_fence_in_list_is_untouched(repo):
    body = "- 清單：\n\n    ```bash\n    gh pr review 1 --body-file .maigo/review/1/draft.md\n    ```\n"
    path = note(repo, body)
    result = plan(repo, path)
    assert result.new_text.encode("utf-8") == path.read_bytes()
    assert result.changes == []


def test_span_that_is_exactly_one_legacy_path_is_still_rewritten(repo):
    assert (
        rewritten(repo, "- `review/1261/review.md`") == "- `../review/1261/review.md`"
    )


def test_symlinked_detail_file_stays_a_symlink(repo, tmp_path_factory):
    real = tmp_path_factory.mktemp("real") / "1.md"
    real.write_text(HEAD + "- review/1261/review.md\n")
    link = repo / ".maigo/i/1.md"
    link.symlink_to(real)
    rnp.run_repo(repo, apply=True, out=lambda _: None)
    assert link.is_symlink()
    assert real.read_text().endswith("- ../review/1261/review.md\n")


BODY = (
    "- review/1261/review.md\n"
    "- 回覆草稿：.maigo/pr/76801/reply-draft.md\n"
    "- 報告：../review/1/review.md（舊）\n"
    "- 手寫，含非 ASCII：這是一段話。\n"
)


def test_dry_run_writes_nothing_and_prints_before_and_after(repo):
    path = note(repo, BODY)
    before = path.read_bytes()
    stamp = (1_700_000_000, 1_700_000_000)
    os.utime(path, stamp)
    lines: list[str] = []
    stats = rnp.run_repo(repo, apply=False, out=lines.append)
    assert path.read_bytes() == before and os.stat(path).st_mtime == stamp[0]
    joined = "\n".join(lines)
    assert "改前：- 回覆草稿：.maigo/pr/76801/reply-draft.md" in joined
    assert "改後：- 回覆草稿：`../pr/76801/reply-draft.md`" in joined
    assert stats["changes"] == 3


def test_apply_changes_only_planned_lines_and_is_idempotent(repo):
    path = note(repo, BODY)
    rnp.run_repo(repo, apply=True, out=lambda _: None)
    after = path.read_text()
    assert after == HEAD + (
        "- ../review/1261/review.md\n"
        "- 回覆草稿：`../pr/76801/reply-draft.md`\n"
        "- 報告：`../review/1/review.md`（舊）\n"
        "- 手寫，含非 ASCII：這是一段話。\n"
    )
    stats = rnp.run_repo(repo, apply=True, out=lambda _: None)
    assert stats["changes"] == 0 and path.read_text() == after


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("trailing", [True, False])
def test_bytes_outside_paths_are_preserved(repo, newline, trailing):
    body = BODY if trailing else BODY.rstrip("\n")
    path = note(repo, body, newline=newline)
    original = path.read_bytes()
    rnp.run_repo(repo, apply=True, out=lambda _: None)
    changed = path.read_bytes()
    assert (changed.endswith(newline.encode())) == (original.endswith(newline.encode()))
    assert changed.count(b"\r\n") == original.count(b"\r\n")
    undone = (
        changed.decode()
        .replace("../review/1261/review.md", "review/1261/review.md")
        .replace("`../pr/76801/reply-draft.md`", ".maigo/pr/76801/reply-draft.md")
        .replace("`../review/1/review.md`", "../review/1/review.md")
    )
    assert undone.encode() == original


def test_non_utf8_file_is_skipped_untouched(repo):
    path = repo / ".maigo/i/1.md"
    path.write_bytes(b"## \xff\xfe\n")
    result = plan(repo, path)
    assert result.skipped_reason == "非 UTF-8"
    assert path.read_bytes() == b"## \xff\xfe\n"


def test_content_changed_between_plan_and_apply_is_not_overwritten(repo):
    path = note(repo, BODY)
    result = plan(repo, path)
    path.write_text(path.read_text() + "- 使用者剛存的一行\n")
    saved = path.read_bytes()
    assert rnp.apply_plan(result) is not None
    assert path.read_bytes() == saved
    assert not list(path.parent.glob(".*.tmp"))


def test_main_requires_apply_flag_to_write(repo, capsys):
    path = note(repo, BODY)
    before = path.read_bytes()
    assert rnp.main([str(repo)]) == 0
    assert path.read_bytes() == before
    assert "乾跑" in capsys.readouterr().out
    assert rnp.main([str(repo), "--apply"]) == 0
    assert path.read_bytes() != before


def test_main_reads_repo_list(repo, tmp_path_factory, capsys):
    listing = tmp_path_factory.mktemp("lists") / "repos.txt"
    listing.write_text(f"# c\n\n{repo}\n/nonexistent/repo\n")
    assert rnp.main(["--repo-list", str(listing)]) == 0
    assert "does not exist" in capsys.readouterr().out


# --- find_adjacent_paths --------------------------------------------------------


def test_find_adjacent_paths_catches_glued_paths_and_ignores_safe_shapes():
    glued = "- 報告：../review/1/review.md（舊）\n"
    assert rnp.find_adjacent_paths(glued) == [(1, "../review/1/review.md")]
    safe = (
        "- 報告：`../review/1/review.md`（舊）\n- ../review/1/review.md\n"
        "- 報告： ../review/1/review.md\n```\n報告：../a/b.md（x）\n```\n"
    )
    assert rnp.find_adjacent_paths(safe) == []


# --- lock: script-written fact lines never glue a path to Chinese text ------------


def _facts(**over) -> str:
    base = dict(
        type="👀", status="待送出", title="t", url="https://github.com/o/r/pull/1",
        additions=1, deletions=1, author="a",
        next_action="gh pr review <n> --comment --body-file .maigo/review/1/draft.md",
        number=1, last_reviewed_at="2026-01-01T00:00:00+00:00",
        review_time_source="report", acknowledged_at=None,
    )  # fmt: skip
    base.update(over)
    return refresh.render_detail_facts(**base)


def test_script_written_fact_lines_have_no_glued_paths():
    missing = (
        "尚無草稿：先起草 `.maigo/review/1/draft.md`（`/maigo:review` §4.5 裁決 gate）"
    )
    variants = [
        _facts(),
        _facts(next_action=missing),
        _facts(load_command="gh pr checkout 1"),
        _facts(
            status="↩︎ 回你的球",
            next_action="/maigo:review <n>",
            result="上次 NEEDS_CHANGES",
        ),
    ]
    for text in variants:
        assert rnp.find_adjacent_paths(text) == [], text


# --- positive shape test: only note-style references are rewritten ----------------


@pytest.mark.parametrize(
    "line",
    [
        "- echo hi >> .maigo/review/1/draft.md",
        "- wc -l < .maigo/review/1/draft.md",
        "- rg foo .maigo/review/1/review.md",
        "- bat .maigo/review/1/review.md",
        "- $EDITOR .maigo/review/1/draft.md",
        "see .maigo/review/1/review.md for details",
        "- frobnicate .maigo/review/1/review.md",
        "- 執行 frobnicate .maigo/review/1/review.md",
    ],
)
def test_ascii_preceded_paths_are_left_alone_and_reported(repo, line):
    path = note(repo, line + "\n")
    result = plan(repo, path)
    assert result.new_text.encode("utf-8") == path.read_bytes()
    assert result.changes == []
    assert [s["reason"] for s in result.skips] in (
        [rnp.ASCII_REASON],
        [rnp.CODE_REASON],
    )


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("- review/1/review.md", "- ../review/1/review.md"),
        (
            "- 報告：.maigo/review/1/review.md（舊）",
            "- 報告：`../review/1/review.md`（舊）",
        ),
        ("見 .maigo/review/1/review.md", "見 ../review/1/review.md"),
        ("報告： .maigo/review/1/review.md", "報告： ../review/1/review.md"),
        ("報告：../review/1/review.md", "報告：`../review/1/review.md`"),
        ("- 報告：`review/1/review.md`", "- 報告：`../review/1/review.md`"),
    ],
)
def test_note_shaped_references_are_still_rewritten(repo, before, after):
    assert rewritten(repo, before) == after


# --- English `Label: path` references ---------------------------------------------


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (
            "- Review report: .maigo/review/1/review.md",
            "- Review report: ../review/1/review.md",
        ),
        (
            "- Draft (not sent): .maigo/review/1/draft.md; inline comments: .maigo/review/1/review.md",
            "- Draft (not sent): ../review/1/draft.md; inline comments: ../review/1/review.md",
        ),
    ],
)
def test_english_label_references_are_rewritten(repo, before, after):
    assert rewritten(repo, before) == after


@pytest.mark.parametrize(
    "line",
    [
        "echo x: .maigo/review/1/review.md",
        "- gh pr view 1 --json title: .maigo/review/1/review.md",
        "- --flag: .maigo/review/1/review.md",
    ],
)
def test_colon_after_command_or_flag_is_not_a_label(repo, line):
    path = note(repo, line + "\n")
    result = plan(repo, path)
    assert result.new_text.encode("utf-8") == path.read_bytes()
    assert result.changes == [] and len(result.skips) == 1
