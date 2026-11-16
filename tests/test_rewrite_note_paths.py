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
        "尚無草稿：先起草 `../review/1/draft.md`（`/maigo:review` §4.5 裁決 gate）"
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


# --- report files (review/<id>/, pr/<id>/): internal paths only -----------------


def report_plan(
    repo: Path, rel: str, body: str, *, newline: str = "\n"
) -> rnp.FilePlan:
    path = repo / ".maigo" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body.replace("\n", newline).encode("utf-8"))
    return rnp.plan_file(path, maigo_dir=repo / ".maigo", repo_root=repo, kind="report")


def report_line(repo: Path, line: str, rel: str = "review/1/review.md") -> str:
    return report_plan(repo, rel, line + "\n").new_text.removesuffix("\n")


@pytest.mark.parametrize(
    ("rel", "before", "after"),
    [
        (
            "review/1/review.md",
            "- Rubric: .maigo/review/1/rubric.md",
            "- Rubric: rubric.md",
        ),
        (
            "review/1/review.md",
            "詳見：.maigo/review/1/rubric.md",
            "詳見：`rubric.md`",
        ),
        ("review/1/review.md", "- Plan: .maigo/i/9.md", "- Plan: ../../i/9.md"),
        ("pr/2/review.md", "- Rubric: .maigo/pr/2/rubric.md", "- Rubric: rubric.md"),
        (
            "review/1/review.md",
            "- Other: .maigo/review/1261/review.md",
            "- Other: ../1261/review.md",
        ),
        (
            "review/1/review.md",
            "- Unprefixed: review/1/rubric.md",
            "- Unprefixed: rubric.md",
        ),
    ],
)
def test_report_internal_paths_become_file_relative(repo, rel, before, after):
    (repo / ".maigo/i/9.md").write_text("x\n")
    (repo / ".maigo/pr/2").mkdir(parents=True, exist_ok=True)
    (repo / ".maigo/pr/2/rubric.md").write_text("x\n")
    assert report_line(repo, before, rel) == after


def test_detail_note_gets_file_relative_for_every_internal_kind(repo):
    (repo / ".maigo/i/12.md").write_text("x\n")
    (repo / ".maigo/topic/t").mkdir(parents=True)
    (repo / ".maigo/topic/t/plan.md").write_text("x\n")
    assert (
        rewritten(repo, "- .maigo/review/1261/review.md")
        == "- ../review/1261/review.md"
    )
    assert rewritten(repo, "- .maigo/i/12.md") == "- 12.md"
    assert rewritten(repo, "- .maigo/topic/t/plan.md") == "- ../topic/t/plan.md"


@pytest.mark.parametrize(
    "line",
    [
        "詳見 `commitizen/commands/bump.py:347`",
        "原始碼：src/x.py:3",
        "- 原始碼：src/x.py:3（見）",
        "- src/not/there.py:9 之類",
        "- Rubric: src/x.py",
    ],
)
def test_report_source_paths_are_untouched_and_leave_no_record(repo, line):
    result = report_plan(repo, "review/1/review.md", line + "\n")
    assert result.new_text == line + "\n"
    assert result.changes == [] and result.skips == []
    # the same line in a detail note keeps the older delimiting behaviour
    if line == "原始碼：src/x.py:3":
        assert rewritten(repo, line) == "原始碼：`src/x.py:3`"


def test_report_ambiguous_unprefixed_path_is_skipped_with_reason(repo):
    (repo / "review/1").mkdir(parents=True)
    (repo / "review/1/rubric.md").write_text("repo-root twin\n")
    result = report_plan(repo, "review/1/review.md", "- Rubric: review/1/rubric.md\n")
    assert result.changes == []
    assert [s["reason"] for s in result.skips] == [rnp.AMBIGUOUS_REASON]


def test_report_missing_prefixed_target_is_listed_but_unprefixed_missing_is_not(repo):
    result = report_plan(
        repo,
        "review/1/review.md",
        "- Rubric: .maigo/review/9/rubric.md\n- Other: review/9/rubric.md\n",
    )
    assert result.changes == []
    assert [(s["line"], s["reason"]) for s in result.skips] == [(1, rnp.MISSING_REASON)]


REPORT_PROTECTED = [
    "```\n- Rubric: .maigo/review/1/rubric.md\n```\n",
    "~~~\n詳見：.maigo/review/1/rubric.md\n~~~\n",
    "    詳見：.maigo/review/1/rubric.md\n",
    "<!-- maigo-review\nrubric: .maigo/review/1/rubric.md\n-->\n",
    "<!-- 詳見：.maigo/review/1/rubric.md -->\n",
    "<!-- pr-context-cache:start v1 -->\n詳見：.maigo/review/1/rubric.md\n"
    "```\n<!-- pr-context-cache:end -->\n",
    "- `gh pr review 1 --body-file .maigo/review/1/draft.md`\n",
    "gh pr review 1 --body-file .maigo/review/1/draft.md\n",
    "- see <https://github.com/o/r/blob/main/.maigo/review/1/rubric.md>\n",
    "- https://example.com/.maigo/review/1/rubric.md 之類\n",
    "| 項目 | .maigo/review/1/rubric.md |\n",
    "- [rubric](.maigo/review/1/rubric.md)\n",
]


@pytest.mark.parametrize("body", REPORT_PROTECTED)
def test_report_excluded_regions_keep_their_bytes(repo, body):
    result = report_plan(repo, "review/1/review.md", body)
    assert result.new_text == body and result.changes == []


def test_report_fence_inside_cache_region_does_not_mask_what_follows(repo):
    body = (
        "<!-- pr-context-cache:start v1 -->\n```\n<!-- pr-context-cache:end -->\n"
        "- Rubric: .maigo/review/1/rubric.md\n"
    )
    result = report_plan(repo, "review/1/review.md", body)
    assert result.new_text.endswith("- Rubric: rubric.md\n")


def test_report_files_are_idempotent_and_keep_crlf_and_missing_final_newline(repo):
    body = "- Rubric: .maigo/review/1/rubric.md\n- 結論：.maigo/review/1/rubric.md（x）"
    first = report_plan(repo, "review/1/review.md", body, newline="\r\n")
    assert first.new_text == "- Rubric: rubric.md\r\n- 結論：`rubric.md`（x）"
    path = repo / ".maigo/review/1/review.md"
    rnp.apply_plan(first)
    again = rnp.plan_file(
        path, maigo_dir=repo / ".maigo", repo_root=repo, kind="report"
    )
    assert again.changes == [] and path.read_bytes().endswith("（x）".encode())


def test_report_non_utf8_is_skipped(repo):
    path = repo / ".maigo/review/1/review.md"
    path.write_bytes(b"\xff\xfe .maigo/review/1/rubric.md")
    result = rnp.plan_file(
        path, maigo_dir=repo / ".maigo", repo_root=repo, kind="report"
    )
    assert result.skipped_reason == "非 UTF-8"


def _write(repo: Path, rel: str, text: str) -> Path:
    path = repo / ".maigo" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_run_repo_scans_whitelist_and_counts_post_files_as_unscanned(repo):
    pasted = "貼文：.maigo/pr/1/reply-draft.md\n"
    names = ("draft.md", "inline-comments.md", "reply-draft.md", "follow-up-issue.md")
    for name in names:
        _write(repo, f"pr/1/{name}", pasted)
    review = _write(repo, "pr/1/review.md", "- Rubric: .maigo/pr/1/rubric.md\n")
    _write(repo, "pr/1/rubric.md", "x\n")
    for name in ("draft.md",):
        (repo / ".maigo/review/1" / name).write_text(pasted)
    lines: list[str] = []
    stats = rnp.run_repo(repo, apply=True, out=lines.append)
    assert review.read_text() == "- Rubric: rubric.md\n"
    for name in names:
        assert (repo / ".maigo/pr/1" / name).read_text() == pasted
    # 4 under pr/1, plus review/1/draft.md and the two existing `pr/2`/`pr/76801` files
    assert stats["unscanned"] == 4 + 1 + 1 + 1
    assert any(line.startswith("未掃描：7 ") for line in lines)


def test_run_repo_dry_run_prints_before_after_and_unscanned(repo):
    review = _write(repo, "review/1/review.md", "- Rubric: .maigo/review/1/rubric.md\n")
    before = review.read_bytes()
    lines: list[str] = []
    rnp.run_repo(repo, apply=False, out=lines.append)
    assert review.read_bytes() == before
    joined = "\n".join(lines)
    assert "改前：- Rubric: .maigo/review/1/rubric.md" in joined
    assert "改後：- Rubric: rubric.md" in joined and "未掃描：" in joined


def test_report_second_dry_run_after_apply_has_zero_changes(repo):
    _write(
        repo,
        "review/1/review.md",
        "- Rubric: .maigo/review/1/rubric.md\n- 詳見：.maigo/i/9.md（x）\n"
        "- 原始碼：src/x.py:3\n",
    )
    (repo / ".maigo/i/9.md").write_text("x\n")
    rnp.run_repo(repo, apply=True, out=lambda _: None)
    stats = rnp.run_repo(repo, apply=False, out=lambda _: None)
    assert stats["changes"] == 0
    assert (
        (repo / ".maigo/review/1/review.md")
        .read_text()
        .endswith("原始碼：src/x.py:3\n")
    )


def test_rescan_is_by_content_not_by_earlier_line_numbers(repo):
    review = _write(
        repo, "review/1/review.md", "a\n- Rubric: .maigo/review/1/rubric.md\n"
    )
    first: list[str] = []
    rnp.run_repo(repo, apply=False, out=first.append)
    assert any(".maigo/review/1/review.md:2" in line for line in first)
    review.write_text(
        "\n".join(f"line {i}" for i in range(10)) + "\n" + review.read_text()
    )
    second: list[str] = []
    stats = rnp.run_repo(repo, apply=True, out=second.append)
    assert any(".maigo/review/1/review.md:12" in line for line in second)
    text = review.read_text()
    assert stats["changes"] == 1 and text.splitlines()[11] == "- Rubric: rubric.md"
    assert text.splitlines()[:10] == [f"line {i}" for i in range(10)]


def test_file_changed_between_write_and_replace_is_not_overwritten(repo, monkeypatch):
    review = _write(repo, "review/1/review.md", "- Rubric: .maigo/review/1/rubric.md\n")
    result = rnp.plan_file(
        review, maigo_dir=repo / ".maigo", repo_root=repo, kind="report"
    )
    real = rnp.shutil.copymode

    def meddle(src, dst):
        real(src, dst)
        Path(src).write_text("someone else wrote this\n")

    monkeypatch.setattr(rnp.shutil, "copymode", meddle)
    reason = rnp.apply_plan(result)
    assert reason and "被改動" in reason
    assert review.read_text() == "someone else wrote this\n"
    assert not list(review.parent.glob("*.tmp"))


def test_symlinked_maigo_dir_gives_the_same_result(repo, tmp_path_factory):
    real_state = tmp_path_factory.mktemp("state")
    for sub in ("review/1", "i"):
        (real_state / sub).mkdir(parents=True)
    (real_state / "review/1/rubric.md").write_text("x\n")
    (real_state / "review/1/review.md").write_text(
        "- Rubric: .maigo/review/1/rubric.md\n"
    )
    link_repo = tmp_path_factory.mktemp("linkrepo")
    (link_repo / ".maigo").symlink_to(real_state)
    rnp.run_repo(link_repo, apply=True, out=lambda _: None)
    assert (real_state / "review/1/review.md").read_text() == "- Rubric: rubric.md\n"
    assert (link_repo / ".maigo").is_symlink()


def test_file_relative_same_dir_style(repo, monkeypatch):
    maigo = repo / ".maigo"
    assert (
        rnp.file_relative(maigo, "review/1/rubric.md", maigo / "review/1")
        == "rubric.md"
    )
    assert rnp.file_relative(maigo, "i/9.md", maigo / "review/1") == "../../i/9.md"
    monkeypatch.setattr(rnp, "SAME_DIR_STYLE", "sibling")
    assert (
        rnp.file_relative(maigo, "review/1/rubric.md", maigo / "review/1")
        == "../1/rubric.md"
    )


# --- report-mode classification branches (`./`, `../`, nested bare paths) ----------


@pytest.fixture
def report_repo(repo: Path) -> Path:
    for rel in (
        ".maigo/review/2/x.md",
        ".maigo/topic/a/b/plan.md",
        ".maigo/issue/3/triage-rubric.md",
        "README.md",
    ):
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n")
    return repo


@pytest.mark.parametrize(
    "line",
    [
        "詳見：../../../README.md（x）",  # exists, but outside the state dir
        "- Rubric: ../../../README.md",
        "詳見：../../../nope.md（x）",  # outside and missing
        "詳見：../nope.md（x）",  # inside and missing
    ],
)
def test_report_relative_paths_outside_state_or_missing_are_untouched_and_unrecorded(
    report_repo, line
):
    result = report_plan(report_repo, "review/1/review.md", line + "\n")
    assert result.new_text == line + "\n"
    assert result.changes == [] and result.skips == []


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("詳見：./rubric.md（x）", "詳見：`rubric.md`（x）"),  # rewritten + delimited
        ("- Rubric: ./rubric.md", "- Rubric: rubric.md"),
        (
            "詳見：../2/x.md（x）",
            "詳見：`../2/x.md`（x）",
        ),  # already relative: delimit only
        ("- Other: ../2/x.md", "- Other: ../2/x.md"),  # already right: untouched
    ],
)
def test_report_dot_relative_paths_inside_state_are_normalised_or_delimited(
    report_repo, before, after
):
    assert report_line(report_repo, before) == after


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("- Plan: topic/a/b/plan.md", "- Plan: ../../topic/a/b/plan.md"),
        (
            "- Rubric: issue/3/triage-rubric.md",
            "- Rubric: ../../issue/3/triage-rubric.md",
        ),
    ],
)
def test_report_nested_bare_paths_become_file_relative(report_repo, before, after):
    assert report_line(report_repo, before) == after


def test_report_nested_bare_path_also_in_repo_root_is_ambiguous(report_repo):
    twin = report_repo / "topic/a/b/plan.md"
    twin.parent.mkdir(parents=True)
    twin.write_text("root twin\n")
    result = report_plan(
        report_repo, "review/1/review.md", "- Plan: topic/a/b/plan.md\n"
    )
    assert result.changes == []
    assert [s["reason"] for s in result.skips] == [rnp.AMBIGUOUS_REASON]


# --- apply keeps the file's times; reader that depends on them ----------------------


def test_apply_keeps_the_mtime_of_the_rewritten_report_to_the_nanosecond(repo):
    # atime is not asserted: reading the file to plan the rewrite already bumps it
    review = _write(repo, "review/1/review.md", "- Rubric: .maigo/review/1/rubric.md\n")
    os.utime(review, ns=(1_600_000_000_123_456_789, 1_600_000_001_987_654_321))
    rnp.run_repo(repo, apply=True, out=lambda _: None)
    assert review.read_text() == "- Rubric: rubric.md\n"
    assert review.stat().st_mtime_ns == 1_600_000_001_987_654_321


def test_apply_keeps_mtime_of_detail_notes_too(repo):
    path = note(repo, "- review/1261/review.md\n")
    os.utime(path, ns=(1_600_000_000_000_000_000, 1_600_000_005_000_000_000))
    rnp.run_repo(repo, apply=True, out=lambda _: None)
    assert path.stat().st_mtime_ns == 1_600_000_005_000_000_000


def test_apply_does_not_change_the_review_time_board_state_reads_from_mtime(tmp_path):
    """Protects `board_state._auto_local_verdict_at`: a report without `reviewed_at`
    is dated by its mtime, so rewriting it must not move that time."""
    from scripts import board_state

    url = "https://github.com/owner/project/pull/42"
    review = tmp_path / ".maigo/review/42/review.md"
    review.parent.mkdir(parents=True)
    (review.parent / "rubric.md").write_text("x\n")
    review.write_text(
        f"# Review\n\n- Rubric: .maigo/review/42/rubric.md\n- Source: <{url}>\n"
    )
    os.utime(review, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
    before = board_state._auto_local_verdict_at(url, "owner/project", str(tmp_path))
    assert before is not None
    rnp.run_repo(tmp_path, apply=True, out=lambda _: None)
    assert "- Rubric: rubric.md" in review.read_text()
    assert (
        board_state._auto_local_verdict_at(url, "owner/project", str(tmp_path))
        == before
    )
