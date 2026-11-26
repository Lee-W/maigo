"""Tests for scripts.board_refresh — zero-token `board_sync.py refresh` (T1-T18 of the plan)."""

from __future__ import annotations

import hashlib
import json
import re
import os
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event

import pytest

from scripts import board_refresh as refresh
from scripts import board_sync as sync
from scripts import review_report as report

REPO = "o/r"
YOU = "me"
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
HEAD = "a" * 40
RECENT = "2026-09-30T00:00:00Z"


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    """Header times are local time: pin TZ, and pin `now` for the CLI."""
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    monkeypatch.setattr(refresh, "_now", lambda: NOW)
    yield
    monkeypatch.undo()
    time.tzset()


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch, tmp_path_factory):
    """The user-layer weights file lives under ~/.config: never read the real one."""
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    return home


def url(n: int, kind: str = "pull", repo: str = REPO) -> str:
    return f"https://github.com/{repo}/{kind}/{n}"


def tree_hash(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def pr_meta(n: int, *, author="carol", state="OPEN", updated=RECENT, head=HEAD, **kw):
    meta = {
        "title": f"PR {n}", "state": state, "isDraft": False, "mergedAt": None,
        "closedAt": None, "mergeable": "MERGEABLE", "reviewDecision": "",
        "createdAt": "2026-09-01T00:00:00Z", "updatedAt": updated, "headRefOid": head,
        "commits": [], "reviews": [], "comments": [], "author": {"login": author},
        "statusCheckRollup": [], "additions": 10, "deletions": 2,
    }  # fmt: skip
    meta.update(kw)
    return meta


def issue_meta(n: int, *, state="OPEN", updated=RECENT):
    return {
        "title": f"Issue {n}", "state": state, "stateReason": None, "closedAt": None,
        "assignees": [], "author": {"login": "rep"}, "comments": [],
        "createdAt": "2026-09-01T00:00:00Z", "updatedAt": updated, "labels": [],
        "closedByPullRequestsReferences": [],
    }  # fmt: skip


class FakeRunner:
    """Every external command goes through here; anything unexpected is an error."""

    def __init__(self, root: Path | None = None):
        self.prs: dict[int, dict] = {}
        self.issues: dict[int, dict] = {}
        self.fail: set[int] = set()
        self.calls: list[list[str]] = []
        self.worktrees: list[Path] = [root] if root else []
        self.on_pr_view = None  # called once, before the first `gh pr view` answers

    def __call__(self, cmd: list[str]) -> str:
        self.calls.append(cmd)
        if cmd[:3] == ["gh", "pr", "view"]:
            if self.on_pr_view:
                hook, self.on_pr_view = self.on_pr_view, None
                hook()
            number = int(cmd[3].rsplit("/", 1)[1])
            if number in self.fail:
                raise RuntimeError("HTTP 404\nGraphQL: Could not resolve（x）")
            return json.dumps(self.prs[number])
        if cmd[:3] == ["gh", "issue", "view"]:
            number = int(cmd[3].rsplit("/", 1)[1])
            if number in self.fail:
                raise RuntimeError("boom")
            return json.dumps(self.issues[number])
        if cmd[:3] == ["gh", "api", "graphql"]:
            number = int(
                next(arg.split("=", 1)[1] for arg in cmd if arg.startswith("number="))
            )
            threads = self.prs[number].get("reviewThreads", [])
            nodes = [
                {
                    **t,
                    "comments": {
                        "nodes": t["comments"],
                        "commentPage": {"hasNextPage": False, "endCursor": None},
                    },
                }
                for t in threads
            ]
            return json.dumps(
                [
                    {
                        "data": {
                            "repository": {
                                "pullRequest": {"reviewThreads": {"nodes": nodes}}
                            }
                        }
                    }
                ]
            )
        if cmd[:3] == ["gh", "api", "user"]:
            return YOU
        if cmd[:2] == ["gh", "api"] and cmd[2].endswith("/timeline"):
            return "[]"
        if cmd[:2] == ["gh", "api"] and "/issues/" in cmd[2]:
            return "true" if int(cmd[2].rsplit("/", 1)[1]) in self.prs else "false"
        if cmd[:2] == ["gh", "search"]:
            return "[]"
        if cmd[0] == "git" and "worktree" in cmd:
            return "\n\n".join(f"worktree {p}\nHEAD abc" for p in self.worktrees)
        raise AssertionError(f"unexpected command: {cmd}")


@pytest.fixture
def gh(tmp_path, monkeypatch):
    fake = FakeRunner(tmp_path)
    monkeypatch.setattr(sync, "run", fake)
    return fake


def board_text(*, focus=(), wait=(), done=(), header_repo=REPO) -> str:
    def block(title: str, rows: tuple) -> str:
        return f"## {title}（{len(rows)}）\n\n" + "".join(f"{r}\n" for r in rows)

    return (
        f"# Work Board — {header_repo}\n"
        f"> 最後刷新：2026-01-01 00:00 ｜ 🎯 {len(focus)} ｜ ⏳ {len(wait)} ｜ ✅ {len(done)}\n\n"
        + block("🎯 下一件", focus)
        + "\n"
        + block("⏳ 等別人", wait)
        + "\n"
        + block("✅ 最近結案", done)
    )


def detail_text(n, *, kind="pull", icon="👀", status="待 review", title="Old title",
                judgment="", notes="<!-- 手寫區 -->"):  # fmt: skip
    return (
        f"# {icon} {status} — {title}\n\n- 連結：{url(n, kind)}\n- 規模：Δ+1/-1\n\n"
        f"## 判斷\n\n{judgment}\n\n## 筆記\n\n{notes}\n"
    )


def put_detail(root: Path, n: int, text: str | None = None, *, minutes_old=60, **kw):
    path = root / ".maigo" / "i" / f"{n}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text is not None else detail_text(n, **kw))
    stamp = (NOW - timedelta(minutes=minutes_old)).timestamp()
    os.utime(path, (stamp, stamp))
    return path


def write_board(root: Path, text: str) -> Path:
    path = root / ".maigo" / "board.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def row(n, mark=" ", icon="👀", status="待 review", extra="", author="carol",
        numbered=True):  # fmt: skip
    lead = f"{n}. " if numbered else "- "
    who = f" @{author}" if author else ""
    return f"{lead}[{mark}] {icon} {status}{extra}{who} i/{n}.md — Title {n}"


def run_cli(root: Path, *args: str, repo=REPO, you=YOU) -> int:
    argv = ["refresh", "--maigo-root", str(root)]
    if repo:
        argv += ["--repo", repo]
    if you:
        argv += ["--you", you]
    return sync.main(argv + list(args))


def ledger(root: Path) -> list[dict]:
    path = root / ".maigo" / "_internal" / "board" / "dropped.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def board_lines(root: Path) -> list[str]:
    return (root / ".maigo" / "board.md").read_text().splitlines()


# --- T1 / T2 / T3: renderer round-trips ---------------------------------------

SKILL_BOARD = """\
# Work Board — Lee-W/maigo

> 最後刷新：2026-08-18 14:30 ｜ 🎯 2 ｜ 👀 1 ｜ ⏳ 2 ｜ ✅ 1 ｜ 🧠 待學習盤點 1

## 🎯 我的下一件（2）

1. [ ] 🔀 CHANGES_REQUESTED @Lee-W →修改 +286/-74 — Redesign Work Board reading view i/9201.md
2. [ ] 🐛 待 triage @reporter 💤 →triage — CLI 在空設定檔時會 crash i/9101.md

## 👀 待我 review（1）

1. [x] 👀 ↩︎ 回你的球 @contributor →重審 +1.2k/-340 — Avoid duplicate GitHub requests i/9301.md

## ⏳ 等別人（2）

- [ ] 🔀 等 review @Lee-W — Document plugin installation flow i/9202.md
- [ ] 🐛 NEEDS_INFO（已請補作業系統與完整 log） @reporter — Hook occasionally exits without output i/9103.md

## ✅ 最近結案（1）

- [x] 👀 APPROVE（merged 07-12） @contributor 🧠 07-12 — Add structured review verdicts i/9303.md
"""

EXTRA_LINES = [
    "1. [ ] 🔀 CI 紅 @octocat — Run CI on release-branch pull requests i/airflow-70724.md",
    "2. [ ] 👀 抓不到（GraphQL: Could not resolve） @octocat — owner/foo#3 i/foo-3.md",
    "3. [x] 👀 已看完 @dev 🧠🔖💤 — All three badges i/55.md",
    "4. [ ] 🔀 CI 紅 @octocat 💤 →修CI +1.2k/-340 — Action, size and badge i/56.md",
    "5. [ ] 👀 待 review（手寫旁註） @octocat +86/-12 — Size without action i/57.md",
    "- [x] 🔀 merged @octocat 🧠 11-14 — Closing date i/58.md",
]


def _as_board(line: str) -> str:
    heading = "## 🎯 我的下一件（1）" if line[0].isdigit() else "## ⏳ 等別人（1）"
    return f"# Work Board — {REPO}\n\n{heading}\n\n{line}\n"


def _render(parsed_line: dict) -> str:
    return refresh.render_line(
        number=parsed_line["number"], checked=parsed_line["checked"],
        type=parsed_line["type"], status=parsed_line["status"],
        note=parsed_line["note"], author=parsed_line["author"],
        badges=parsed_line["badges"], detail=parsed_line["detail"],
        title=parsed_line["title"], action=parsed_line["action"],
        size=parsed_line["size"], ended=parsed_line["ended"],
        result=parsed_line["result"],
    )  # fmt: skip


def test_t1_every_line_shape_round_trips():
    lines = [
        ln
        for ln in SKILL_BOARD.splitlines()
        if ln.startswith(("1. ", "2. ", "3. ", "- ["))
    ] + EXTRA_LINES
    assert len(lines) == 12
    for line in lines:
        parsed = sync.parse_board(_as_board(line))
        assert parsed["errors"] == [], line
        assert _render(parsed["lines"][0]) == line


def test_t1_author_pending_line_round_trips():
    lines = [
        "1. [ ] 🔀 CI 紅（作者待補） — No note, no author i/airflow-70724.md",
        "2. [ ] 👀 抓不到（GraphQL: x；作者待補） — owner/foo#3 i/foo-3.md",
        "- [ ] 🔀 等 review（作者待補） 💤 — Pending with badge i/13.md",
    ]
    for line in lines:
        parsed = sync.parse_board(_as_board(line))
        assert parsed["errors"] == [] and len(parsed["warnings"]) == 1, line
        assert parsed["lines"][0]["author"] is None
        assert _render(parsed["lines"][0]) == line


def test_t2_whole_file_round_trip_is_byte_identical():
    parsed = sync.parse_board(SKILL_BOARD)
    rows = {s: [ln for ln in parsed["lines"] if ln["section"] == s] for s in "🎯👀⏳✅"}
    flat = [r for section in rows.values() for r in section]
    rendered = refresh.render_board(
        repo="Lee-W/maigo",
        refreshed_at_local="2026-08-18 14:30",
        rows_by_section=rows,
        learn_pending_count=refresh.count_learn_pending(flat),
    )
    assert rendered == SKILL_BOARD


SKILL_MD = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "work-board"
    / "references"
    / "format-spec.md"
)


def test_skill_grammar_examples_parse():
    """The example board in work-board references/format-spec.md §1 parses cleanly and re-renders byte-identically."""
    text = SKILL_MD.read_text(encoding="utf-8")
    start = text.index("### Sections")
    fence = text.index("```markdown\n", start) + len("```markdown\n")
    example = text[fence : text.index("\n```", fence)] + "\n"
    parsed = sync.parse_board(example)
    assert parsed["errors"] == [] and parsed["legacy"] is False
    fields = [(ln["action"], ln["size"], ln["ended"]) for ln in parsed["lines"]]
    assert any(action and size for action, size, _ in fields)
    assert any(ended for _, _, ended in fields)
    rows = {s: [ln for ln in parsed["lines"] if ln["section"] == s] for s in "🎯👀⏳✅"}
    header = example.splitlines()[2]
    rendered = refresh.render_board(
        repo="Lee-W/maigo",
        refreshed_at_local=header.split("：")[1].split(" ｜")[0],
        rows_by_section=rows,
        learn_pending_count=refresh.count_learn_pending(
            [r for section in rows.values() for r in section]
        ),
    )
    assert rendered == example


def test_t3_real_board_shape_survives_parse_render_parse():
    # Shape of a real board: no blank after the section title, date-only header,
    # no 🧠 section. Content is invented.
    text = (
        "# Work Board — o/r\n"
        "> 最後刷新：2026-08-19 ｜ 🎯 2 ｜ ⏳ 1 ｜ ✅ 0\n\n"
        "## 🎯 下一件（2）\n"
        "1. [ ] 🔀 CI 紅 @octocat — First invented title i/other-11.md\n"
        "2. [ ] 👀 待 review @octocat 💤 — Second invented title i/12.md\n\n"
        "## ⏳ 等別人（1）\n"
        "- [ ] 🔀 等 review @octocat — Third invented title i/13.md\n\n"
        "## ✅ 最近結案（0）\n"
    )
    first = sync.parse_board(text)
    rows = {s: [ln for ln in first["lines"] if ln["section"] == s] for s in "🎯⏳✅"}
    rendered = refresh.render_board(
        repo="o/r", refreshed_at_local="2026-08-19 00:00",
        rows_by_section=rows, learn_pending_count=0,
    )  # fmt: skip
    second = sync.parse_board(rendered)
    keys = ("section", "checked", "type", "status", "note", "author", "badges",
            "detail", "title")  # fmt: skip
    assert first["errors"] == [] and second["errors"] == []
    assert len(first["lines"]) == 3
    assert [{k: ln[k] for k in keys} for ln in second["lines"]] == [
        {k: ln[k] for k in keys} for ln in first["lines"]
    ]


def _line_args(**over):
    base = dict(number=None, checked=False, type="👀", status="待 review", note=None,
                author=None, badges=[], detail="i/1.md", title="t")  # fmt: skip
    base.update(over)
    return base


def test_render_line_writes_author_pending_note_when_no_note():
    line = refresh.render_line(**_line_args())
    assert line == "- [ ] 👀 待 review（作者待補） — t i/1.md"


def test_render_line_merges_author_pending_into_existing_note():
    line = refresh.render_line(**_line_args(note="（手寫旁註）"))
    assert line == "- [ ] 👀 待 review（手寫旁註；作者待補） — t i/1.md"
    assert line.count("（") == 1


def test_render_line_treats_author_pending_lookalike_as_plain_note():
    line = refresh.render_line(**_line_args(note="（作者待補中）"))
    assert line == "- [ ] 👀 待 review（作者待補中；作者待補） — t i/1.md"


def test_render_line_drops_pending_marker_once_author_is_known():
    only = refresh.render_line(**_line_args(note="（作者待補）", author="octocat"))
    assert only == "- [ ] 👀 待 review @octocat — t i/1.md"
    merged = refresh.render_line(
        **_line_args(note="（手寫旁註；作者待補）", author="octocat")
    )
    assert merged == "- [ ] 👀 待 review（手寫旁註） @octocat — t i/1.md"


def test_overflow_never_prints_bare_at():
    assert refresh.author_token("") == "（作者待補）"
    assert refresh.author_token(None) == "（作者待補）"
    assert refresh.author_token("octocat") == "@octocat"
    summary = {
        "applied": False, "board_path": "b", "pending_reviews": [], "top": [],
        "top_review": [],
        "capped": [], "learn_expiring": [],
        "counts": {"🎯": 0, "👀": 0, "⏳": 0, "✅": 0}, "warnings": [], "errors": [],
        "pending_orphans": [], "removed": [], "revived": [], "unattributed": [],
        "excluded_detail_files": [], "detail_writes": [], "detail_deletes": [],
        "ledger_events": [], "learn_pending": 0,
        "overflow": [{"url": "u", "title": "T", "author": ""}],
    }  # fmt: skip
    out = refresh.format_summary(summary)
    assert "- T （作者待補） u" in out and " @ " not in out


# --- small pure pieces ----------------------------------------------------------


def test_split_detail_keeps_everything_from_the_judgment_line_verbatim():
    text = "# head\n\n- 連結：x\n\n## 判斷\r\nline\r\n\n## 筆記\n\n<!-- 手寫區 -->\n"
    facts, preserved = refresh.split_detail(text)
    assert facts + preserved == text and preserved.startswith("## 判斷\r\n")
    with pytest.raises(ValueError):
        refresh.split_detail("# head\n\n## 筆記\n")


OLD_TEMPLATE = "## 判斷\n\n\n## 筆記\n\n\n<!-- 手寫區 -->\n"


def test_collapse_blank_runs_squeezes_old_double_blank_lines():
    assert refresh.collapse_blank_runs(OLD_TEMPLATE) == refresh.NEW_PRESERVED


def test_collapse_blank_runs_keeps_fenced_blank_lines_and_handwriting():
    text = "## 判斷\n\n- 一\n  \n\n[連結](x)\n\n```\na\n\n\nb\n```\n\n~~~\nc\n\n\n~~~\n"
    want = "## 判斷\n\n- 一\n\n[連結](x)\n\n```\na\n\n\nb\n```\n\n~~~\nc\n\n\n~~~\n"
    assert refresh.collapse_blank_runs(text) == want


def test_collapse_blank_runs_is_identity_on_normal_content():
    for text in (
        refresh.NEW_PRESERVED,
        "## 判斷\r\nx\r\n\n## 筆記\n\n- a\n",
        "no newline",
    ):
        assert refresh.collapse_blank_runs(text) == text


def test_collapse_blank_runs_drops_a_trailing_blank_run():
    assert refresh.collapse_blank_runs("a\n\n\n") == "a\n"


WHITESPACE_CASES = [
    ("a\n  \n", "a\n"),
    ("a\n\t\n", "a\n"),
    ("a\n  \n\n\nb\n", "a\n\nb\n"),
    ("a\n   \n\t\n  \nb\n", "a\n\nb\n"),
    ("a\r\n  \r\n", "a\r\n"),
    ("a\r\n\t\r\n", "a\r\n"),
    ("a\r\n  \r\n\r\n\r\nb\r\n", "a\r\n\r\nb\r\n"),
    ("a\r\n   \r\n\t\r\n  \r\nb\r\n", "a\r\n\r\nb\r\n"),
    (
        "- a\n\n    ```\n    x\n\n\n    y\n    ```\n",
        "- a\n\n    ```\n    x\n\n\n    y\n    ```\n",
    ),
    ("```\nx\n```py\n\n\ny\n```\n", "```\nx\n```py\n\n\ny\n```\n"),
    ("~~~\nx\n~~~ notclose\n\n\ny\n~~~\n", "~~~\nx\n~~~ notclose\n\n\ny\n~~~\n"),
    ("````\nx\n```\n\n\ny\n````\n\n\nz\n", "````\nx\n```\n\n\ny\n````\n\nz\n"),
    ("```\nx\n```  \n\n\ny\n", "```\nx\n```  \n\ny\n"),
    ("p\n\n    x\n\n\n    y\n", "p\n\n    x\n\n\n    y\n"),
    ("p\n\n\tx\n\n\n\ty\n", "p\n\n\tx\n\n\n\ty\n"),
    ("p\n\n\n    x\n", "p\n\n\n    x\n"),
    (
        "## 判斷\n\n    x\n\n\n    y\n\n## 筆記\n",
        "## 判斷\n\n    x\n\n\n    y\n\n## 筆記\n",
    ),
]


@pytest.mark.parametrize(("text", "want"), WHITESPACE_CASES)
def test_collapse_blank_runs_whitespace_fences_and_crlf(text, want):
    got = refresh.collapse_blank_runs(text)
    assert got == want
    assert refresh.collapse_blank_runs(got) == got


def test_refresh_rewrites_old_double_blank_preserved_area(tmp_path, gh):
    write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1, judgment="keep\n\n\nme", notes="note")
    gh.prs[1] = pr_meta(1)
    path = tmp_path / ".maigo/i/1.md"
    path.write_text(path.read_text().replace("## 筆記", "\n## 筆記", 1))
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    after = path.read_text()
    assert "\n\n\n" not in after and "keep\n\nme" in after
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert path.read_text() == after


def test_refresh_normalises_whitespace_only_lines_and_trailing_blank_lines(
    tmp_path, gh
):
    write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1, judgment="keep", notes="note")
    gh.prs[1] = pr_meta(1)
    path = tmp_path / ".maigo/i/1.md"
    path.write_text(
        path.read_text().replace("keep", "keep\n  \n\t\n\nnext", 1).rstrip("\n")
        + "\n  \n\n"
    )
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    after = path.read_text()
    _, preserved = refresh.split_detail(after)
    assert "keep\n\nnext" in preserved
    assert preserved.endswith("note\n")
    assert "  \n" not in preserved and "\t\n" not in preserved
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert path.read_text() == after


def test_detail_facts_degradation_rules():
    base = dict(
        title="T", url=url(5), additions=3, deletions=1, author="carol",
        next_action="gh pr checks <n>", number=5, last_reviewed_at=None,
        review_time_source=None, acknowledged_at=None,
    )  # fmt: skip
    pr = refresh.render_detail_facts(type="🔀", status="CI 紅", **base)
    assert "- 規模：Δ+3/-1 ｜ 作者：carol\n" in pr and "`gh pr checks 5`" in pr
    assert "最後 review" not in pr
    issue = refresh.render_detail_facts(
        type="🐛",
        status="待 triage",
        **{**base, "additions": None, "next_action": None},
    )
    assert "- 作者：carol\n" in issue and "規模" not in issue and "下一步" not in issue
    review = refresh.render_detail_facts(type="👀", status="待 review", **base)
    assert "- 最後 review：尚未 review\n" in review
    old = refresh.render_detail_facts(
        type="👀", status="已看完", **{**base, "last_reviewed_at": "2026-01-01T00:00:00+00:00",
        "review_time_source": "mtime", "acknowledged_at": "2026-01-02T00:00:00+00:00"},
    )  # fmt: skip
    assert "（舊檔時間推估）" in old and "- 已看完：2026-01-02" in old
    assert old.endswith("\n\n")


def test_sort_related_files_orders_groups_then_known_kinds_then_attempts_then_the_rest():
    shuffled = [
        "issue/5/notes.txt", "pr/5/review.md", "review/5/rubric-2.md", "review/5/zz.md",
        "review/5/sub/a.md", "review/5/review.md", "review/5/draft.md", "pr/5/plan.md",
        "review/5/rubric-10.md", "review/5/rubric.md", "review/5/inline-comments.md",
        "review/5/pr-comments-2.md", "review/5/pr-comments.md", "pr/5/a.txt",
        "review/5/reply-draft.md", "review/5/aaa.md",
    ]  # fmt: skip
    assert refresh.sort_related_files(shuffled) == [
        "review/5/rubric.md", "review/5/rubric-2.md", "review/5/rubric-10.md",
        "review/5/review.md", "review/5/draft.md", "review/5/pr-comments.md",
        "review/5/pr-comments-2.md", "review/5/reply-draft.md",
        "review/5/inline-comments.md", "review/5/aaa.md", "review/5/sub/a.md",
        "review/5/zz.md", "pr/5/plan.md", "pr/5/review.md", "pr/5/a.txt",
        "issue/5/notes.txt",
    ]  # fmt: skip


def test_sort_related_files_lists_summary_after_plan_and_before_rubric():
    shuffled = [
        "pr/9/notes.md", "pr/9/review.md", "pr/9/summary-2.md", "pr/9/rubric.md",
        "pr/9/summary.md", "pr/9/plan-2.md", "pr/9/plan.md",
    ]  # fmt: skip
    assert refresh.sort_related_files(shuffled) == [
        "pr/9/plan.md", "pr/9/plan-2.md", "pr/9/summary.md", "pr/9/summary-2.md",
        "pr/9/rubric.md", "pr/9/review.md", "pr/9/notes.md",
    ]  # fmt: skip


def test_sort_related_files_puts_the_unnumbered_file_before_its_first_attempt():
    shuffled = [
        "review/5/rubric-10.md", "review/5/rubric-2.md", "review/5/rubric-1.md",
        "review/5/rubric.md",
    ]  # fmt: skip
    assert refresh.sort_related_files(shuffled) == [
        "review/5/rubric.md", "review/5/rubric-1.md", "review/5/rubric-2.md",
        "review/5/rubric-10.md",
    ]  # fmt: skip


def test_detail_facts_list_related_files_as_backticked_file_relative_sub_items():
    base = dict(
        title="T", url=url(5), additions=3, deletions=1, author="carol",
        next_action=None, number=5, last_reviewed_at=None,
        review_time_source=None, acknowledged_at=None,
    )  # fmt: skip
    facts = refresh.render_detail_facts(
        type="👀", status="待 review",
        related_files=["review/5/review.md", "pr/5/a.txt"], **base,
    )  # fmt: skip
    assert facts.endswith(
        "- 最後 review：尚未 review\n"
        "- 相關檔案：\n"
        "  - `../review/5/review.md`\n"
        "  - `../pr/5/a.txt`\n\n"
    )
    plain = refresh.render_detail_facts(type="👀", status="待 review", **base)
    assert "相關檔案" not in plain


def test_scan_related_files_reads_three_groups_recursively_and_nothing_else(tmp_path):
    maigo = tmp_path / ".maigo"
    for rel in (
        "review/5/review.md", "review/5/notes/deep.txt", "review/5/.DS_Store",
        "pr/5/plan.md", "issue/5/rubric.md", "topic/5/plan.md",
        "_archive/review/5/review.md", "review/50/review.md", "review/other-5/review.md",
    ):  # fmt: skip
        (maigo / rel).parent.mkdir(parents=True, exist_ok=True)
        (maigo / rel).write_text("x\n")
    assert refresh.scan_related_files(maigo, "5") == [
        "review/5/review.md",
        "review/5/notes/deep.txt",
        "pr/5/plan.md",
        "issue/5/rubric.md",
    ]
    assert refresh.scan_related_files(maigo, "other-5") == ["review/other-5/review.md"]
    assert refresh.scan_related_files(maigo, "404") == []
    assert refresh.scan_related_files(tmp_path / "missing", "5") == []


def _touch_all(maigo: Path, rels: list[str]) -> None:
    for rel in rels:
        (maigo / rel).parent.mkdir(parents=True, exist_ok=True)
        (maigo / rel).write_text("x\n")


def test_scan_related_files_skips_names_a_one_line_code_span_cannot_carry(tmp_path):
    maigo = tmp_path / ".maigo"
    _touch_all(
        maigo,
        ["review/5/a`b.md", "review/5/a\nb.md", "review/5/a\rb.md", "review/5/ok.md"],
    )
    assert refresh.scan_related_files(maigo, "5") == ["review/5/ok.md"]


def test_scan_related_files_skips_in_flight_temp_files(tmp_path):
    maigo = tmp_path / ".maigo"
    _touch_all(
        maigo,
        [
            "review/5/x.md.tmp", "review/5/notes.md~",
            "review/5/.tmp-abcdefgh", "review/5/tmp.md", "review/5/ok.md",
        ],
    )  # fmt: skip
    assert refresh.scan_related_files(maigo, "5") == [
        "review/5/ok.md",
        "review/5/tmp.md",
    ]


def test_scan_related_files_lists_hand_placed_files_that_only_look_like_temp_names(
    tmp_path,
):
    maigo = tmp_path / ".maigo"
    _touch_all(maigo, ["review/5/tmpnotes123", "review/5/tmpab12cd34"])
    assert refresh.scan_related_files(maigo, "5") == [
        "review/5/tmpab12cd34",
        "review/5/tmpnotes123",
    ]


def test_scan_related_files_skips_the_whole_subtree_of_an_unlistable_directory(
    tmp_path,
):
    maigo = tmp_path / ".maigo"
    _touch_all(
        maigo,
        [
            "review/5/dir~/a.md", "review/5/dir.tmp/a.md", "review/5/.hid/a.md",
            "review/5/d`r/a.md", "review/5/ok/a.md",
        ],
    )  # fmt: skip
    assert refresh.scan_related_files(maigo, "5") == ["review/5/ok/a.md"]


def test_scan_related_files_does_not_descend_into_directory_symlinks(tmp_path):
    maigo = tmp_path / ".maigo"
    _touch_all(maigo, ["review/5/real.md"])
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "o.md").write_text("x\n")
    (maigo / "review/5/linkdir").symlink_to(target, target_is_directory=True)
    assert refresh.scan_related_files(maigo, "5") == ["review/5/real.md"]


def test_atomic_write_stages_through_a_dot_prefixed_temp_file_next_to_the_target(
    tmp_path, monkeypatch
):
    seen = []
    real_replace = Path.replace

    def spy(self, target):
        seen.append((self.parent, self.name))
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", spy)
    report.atomic_write(tmp_path / "out.md", "hi\n")
    assert [parent for parent, _ in seen] == [tmp_path]
    assert seen[0][1].startswith(".tmp-")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["out.md"]


def test_scan_related_files_lists_names_with_spaces_and_parentheses(tmp_path):
    maigo = tmp_path / ".maigo"
    _touch_all(maigo, ["review/5/my file (1).md", "review/5/中文 檔.md"])
    assert refresh.scan_related_files(maigo, "5") == [
        "review/5/my file (1).md",
        "review/5/中文 檔.md",
    ]


def test_scan_related_files_lists_file_symlinks_and_skips_dangling_ones(tmp_path):
    maigo = tmp_path / ".maigo"
    _touch_all(maigo, ["review/5/real.md"])
    outside = tmp_path / "outside.md"
    outside.write_text("x\n")
    (maigo / "review/5/link.md").symlink_to(outside)
    (maigo / "review/5/dangling.md").symlink_to(tmp_path / "gone.md")
    assert refresh.scan_related_files(maigo, "5") == [
        "review/5/link.md",
        "review/5/real.md",
    ]


def test_is_listable_name_rejects_a_surrogate_escaped_non_utf8_name():
    assert refresh.is_listable_name("ok.md")
    assert not refresh.is_listable_name("bad\udcff.md")


def test_scan_related_files_skips_non_utf8_names_so_facts_still_write(
    tmp_path, monkeypatch
):
    maigo = tmp_path / ".maigo"
    top = maigo / "review" / "5"
    top.mkdir(parents=True)
    (top / "ok.md").write_text("x\n")
    walked = [
        (str(top), ["bad\udcffdir"], ["bad\udcff.md", "ok.md"]),
        (str(top / "bad\udcffdir"), [], ["inside.md"]),
    ]
    real_walk = os.walk
    monkeypatch.setattr(
        os, "walk", lambda path: iter(walked) if path == top else real_walk(path)
    )
    found = refresh.scan_related_files(maigo, "5")
    assert found == ["review/5/ok.md"]
    facts = refresh.render_detail_facts(
        type="👀", status="待 review", title="T", url=url(5), additions=1,
        deletions=1, author="carol", next_action=None, number=5,
        last_reviewed_at=None, review_time_source=None, acknowledged_at=None,
        related_files=found,
    )  # fmt: skip
    report.atomic_write(tmp_path / "detail.md", facts)
    assert (tmp_path / "detail.md").read_text(encoding="utf-8") == facts


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores file modes"
)
def test_scan_related_files_survives_an_unreadable_subdirectory(tmp_path):
    maigo = tmp_path / ".maigo"
    _touch_all(maigo, ["review/5/ok.md", "review/5/locked/x.md"])
    locked = maigo / "review/5/locked"
    locked.chmod(0o444)
    try:
        assert refresh.scan_related_files(maigo, "5") == ["review/5/ok.md"]
    finally:
        locked.chmod(0o755)


def _related_lines(path: Path) -> list[str]:
    facts, _ = refresh.split_detail(path.read_text())
    return [ln for ln in facts.splitlines() if ln.startswith("  - ")]


def _put_artifact(root: Path, rel: str) -> None:
    path = root / ".maigo" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x\n")


def test_refresh_lists_related_files_and_keeps_judgment_and_notes_byte_for_byte(
    tmp_path, gh
):
    write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1, judgment="修還是換路？", notes="- `../review/1/draft.md`")
    for rel in ("review/1/rubric.md", "review/1/review.md", "pr/1/plan.md"):
        _put_artifact(tmp_path, rel)
    gh.prs[1] = pr_meta(1)
    detail = tmp_path / ".maigo/i/1.md"
    _, preserved_before = refresh.split_detail(detail.read_text())
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert _related_lines(detail) == [
        "  - `../review/1/rubric.md`",
        "  - `../review/1/review.md`",
        "  - `../pr/1/plan.md`",
    ]
    facts, preserved = refresh.split_detail(detail.read_text())
    assert "\n- 相關檔案：\n  - `../review/1/rubric.md`\n" in facts
    assert preserved.encode() == preserved_before.encode()


def test_refresh_without_artifacts_writes_no_related_field(tmp_path, gh):
    write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1)
    gh.prs[1] = pr_meta(1)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert "相關檔案" not in (tmp_path / ".maigo/i/1.md").read_text()


def test_refresh_updates_the_list_when_artifacts_change_and_is_stable_otherwise(
    tmp_path, gh
):
    write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1)
    _put_artifact(tmp_path, "review/1/review.md")
    gh.prs[1] = pr_meta(1)
    detail = tmp_path / ".maigo/i/1.md"
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    first = detail.read_bytes()
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert detail.read_bytes() == first
    _put_artifact(tmp_path, "review/1/inline-comments.md")
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert _related_lines(detail) == [
        "  - `../review/1/review.md`",
        "  - `../review/1/inline-comments.md`",
    ]
    (tmp_path / ".maigo/review/1/inline-comments.md").unlink()
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert detail.read_bytes() == first


def test_refresh_cross_repo_item_lists_only_its_own_repo_prefixed_directories(
    tmp_path, gh
):
    cross = "https://github.com/o/other/pull/9"
    put_detail(tmp_path, 9, text=detail_text(9).replace(url(9), cross))
    (tmp_path / ".maigo/i/9.md").rename(tmp_path / ".maigo/i/other-9.md")
    write_board(
        tmp_path,
        board_text(focus=[row(9).replace("i/9.md", "i/other-9.md")]),
    )
    for rel in ("review/other-9/review.md", "review/9/review.md", "pr/other-9/plan.md"):
        _put_artifact(tmp_path, rel)
    gh.prs[9] = pr_meta(9)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert _related_lines(tmp_path / ".maigo/i/other-9.md") == [
        "  - `../review/other-9/review.md`",
        "  - `../pr/other-9/plan.md`",
    ]


def test_fetch_item_type_comes_from_the_author_unless_kept(gh):
    gh.prs[1] = pr_meta(1, author="ME")
    gh.prs[2] = pr_meta(2, author="carol")
    assert refresh.fetch_item(url(1), "👀", you=YOU)["type"] == "🔀"
    assert refresh.fetch_item(url(2), "🔀", you=YOU)["type"] == "👀"
    assert refresh.fetch_item(url(1), "👀", you=YOU, keep_type=True)["type"] == "👀"
    gh.fail = {3}
    failed = refresh.fetch_item(url(3), None, you=YOU)
    assert failed == {"error": "GraphQL: Could not resolve(x)"}


# --- T4: detail files -----------------------------------------------------------


def test_t4_judgment_and_notes_survive_byte_for_byte(tmp_path, gh):
    write_board(tmp_path, board_text(focus=[row(1)]))
    notes = "多行\n\n<!-- 保留 -->\r\n- 一\n- 二"
    put_detail(tmp_path, 1, judgment="修還是換路？\n第二行", notes=notes)
    gh.prs[1] = pr_meta(1)
    before = (tmp_path / ".maigo/i/1.md").read_bytes()
    _, preserved_before = refresh.split_detail(before.decode())
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    after = (tmp_path / ".maigo/i/1.md").read_bytes().decode()
    facts, preserved = refresh.split_detail(after)
    assert preserved == preserved_before
    assert facts.startswith("# 👀 待 review — PR 1\n\n- 連結：<" + url(1) + ">")
    assert "- 規模：Δ+10/-2 ｜ 作者：carol" in facts


def test_detail_facts_write_autolink_and_refresh_converts_bare_url_keeping_hand_written(
    tmp_path, gh
):
    write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1, judgment="keep", notes="note")
    gh.prs[1] = pr_meta(1)
    assert "- 連結：" + url(1) + "\n" in (tmp_path / ".maigo/i/1.md").read_text()
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    after = (tmp_path / ".maigo/i/1.md").read_text()
    assert f"- 連結：<{url(1)}>\n" in after
    assert "- 連結：" + url(1) + "\n" not in after
    assert after.endswith("## 判斷\n\nkeep\n\n## 筆記\n\nnote\n")


def test_new_detail_file_has_single_blank_lines_and_autolink(tmp_path, gh):
    write_board(tmp_path, board_text(focus=[row(1)]))
    gh.prs[1] = pr_meta(1)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    text = (tmp_path / ".maigo/i/1.md").read_text()
    assert f"- 連結：<{url(1)}>\n" in text
    assert text.endswith("## 判斷\n\n## 筆記\n\n<!-- 手寫區 -->\n")
    assert "\n\n\n" not in text


def test_board_header_is_separated_from_h1_by_a_blank_line(tmp_path, gh):
    write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1)
    gh.prs[1] = pr_meta(1)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    lines = board_lines(tmp_path)
    assert lines[0] == f"# Work Board — {REPO}" and lines[1] == ""
    assert lines[2].startswith("> 最後刷新：")


def test_t4_missing_judgment_line_rejects_without_writing(tmp_path, gh, capsys):
    write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1, "# 👀 待 review — T\n\n- 連結：" + url(1) + "\n\n## 筆記\n")
    gh.prs[1] = pr_meta(1)
    before = tree_hash(tmp_path)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 1
    assert tree_hash(tmp_path) == before
    assert "1.md" in capsys.readouterr().err


# --- T5 / T6: compare-and-swap --------------------------------------------------


def _checked_review_setup(tmp_path, gh):
    board = write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1)
    gh.prs[1] = pr_meta(1)
    published = report.publish(
        tmp_path, url(1), REPO, "PR 1", "## A\nx\n", HEAD, "APPROVE", owner="others"
    )
    sync.write_snapshot(tmp_path, REPO, NOW)
    board.write_text(board.read_text().replace("1. [ ]", "1. [x]"))
    return published


def test_t5_board_changed_while_fetching_exits_2_and_writes_nothing(
    tmp_path, gh, capsys
):
    published = _checked_review_setup(tmp_path, gh)
    board = tmp_path / ".maigo" / "board.md"
    gh.on_pr_view = lambda: board.write_text(board.read_text() + "<!-- nvim -->\n")
    before = tree_hash(tmp_path)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 2
    after = tree_hash(tmp_path)
    changed = {k for k in after if after[k] != before.get(k)}
    assert changed == {".maigo/board.md"}  # only the simulated nvim save
    assert set(after) == set(before)
    assert "acknowledged_at" not in report.metadata(Path(published["path"]).read_text())
    assert not (tmp_path / ".maigo/_internal/board/.refresh-write-lock").exists()
    assert "未寫任何檔" in capsys.readouterr().err


def test_t6_detail_changed_before_apply_exits_2_and_writes_nothing(
    tmp_path, gh, monkeypatch
):
    write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1)
    gh.prs[1] = pr_meta(1)
    original = refresh._apply_refresh
    detail = tmp_path / ".maigo" / "i" / "1.md"

    def hooked(g, built):
        detail.write_text(detail.read_text().replace("<!-- 手寫區 -->", "新筆記"))
        return original(g, built)

    monkeypatch.setattr(refresh, "_apply_refresh", hooked)
    board_before = (tmp_path / ".maigo/board.md").read_bytes()
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 2
    assert (tmp_path / ".maigo/board.md").read_bytes() == board_before
    assert "新筆記" in detail.read_text() and "PR 1" not in detail.read_text()
    assert not any(p.is_file() for p in (tmp_path / ".maigo/_internal").rglob("*"))


# --- T7: ordering and sections --------------------------------------------------


def test_t7_sort_and_counts(tmp_path, gh):
    focus = [row(1), row(2), row(3), row(4, icon="🔀", status="CI 紅", author="me")]
    wait = [row(5, icon="🔀", status="等 review", author="me", numbered=False),
            row(6, icon="🔀", status="等 review", author="me", numbered=False)]  # fmt: skip
    write_board(tmp_path, board_text(focus=focus, wait=wait))
    for n in range(1, 7):
        put_detail(tmp_path, n)
    gh.prs[1] = pr_meta(1, updated="2026-09-03T00:00:00Z")
    gh.prs[2] = pr_meta(2, updated="2026-09-01T00:00:00Z")
    gh.prs[3] = pr_meta(3, updated="2026-09-02T00:00:00Z")
    gh.prs[4] = pr_meta(4, author="me", statusCheckRollup=[{"conclusion": "FAILURE"}])
    gh.prs[5] = pr_meta(5, author="me", updated="2026-09-10T00:00:00Z")
    gh.prs[6] = pr_meta(6, author="me", updated="2026-09-20T00:00:00Z")
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    lines = board_lines(tmp_path)
    assert lines[2] == "> 最後刷新：2026-10-01 12:00 ｜ 🎯 1 ｜ 👀 3 ｜ ⏳ 2 ｜ ✅ 0"
    order = [
        ln.split(" i/")[1].split(".md")[0]
        for ln in lines
        if ln[:2] in {"1.", "2.", "3.", "4."}
    ]
    assert order == ["4", "2", "3", "1"]  # CI 紅 first, then oldest-updated first
    waiting = [
        ln.split(" i/")[1].split(".md")[0] for ln in lines if ln.startswith("- [")
    ]
    assert waiting == ["6", "5"]  # newest first
    assert "## 🎯 我的下一件（1）" in lines and "## 👀 待我 review（3）" in lines
    assert "## ✅ 最近結案（0）" in lines


# --- line fields: short action, size, closing date; width budget ----------------


def _fields(**over):
    base = dict(
        number=1, checked=False, type="👀", status="待 review", note=None,
        author="octocat", badges=[], detail="i/1.md", title="t",
    )  # fmt: skip
    base.update(over)
    return base


def test_render_line_places_action_size_and_date_between_badges_and_detail():
    line = refresh.render_line(
        **_fields(badges=["🧠"], action="審", size="+1.2k/-340", ended="11-14")
    )
    assert line == "1. [ ] 👀 待 review @octocat 🧠 →審 +1.2k/-340 11-14 — t i/1.md"


def test_render_line_drops_action_when_prefix_over_budget():
    status = "CHANGES_REQUESTED"
    # exactly 80 columns without the action; the action (+8) pushes it past the budget
    author = "a" * 33
    line = refresh.render_line(
        **_fields(type="🔀", status=status, author=author, action="解衝突",
                  size="+10/-2", detail="i/12345.md")
    )  # fmt: skip
    assert "→" not in line and "+10/-2" in line
    fits = refresh.render_line(
        **_fields(type="🔀", status=status, author="a" * 5, action="解衝突",
                  size="+10/-2", detail="i/12345.md")
    )  # fmt: skip
    assert "→解衝突" in fits
    assert board_state_width(fits.split(" — ")[0]) <= refresh.LINE_BUDGET


def board_state_width(text: str) -> int:
    return refresh.board_state.display_width(text)


def test_render_line_keeps_size_and_title_when_over_budget():
    title = "A very long title " * 8
    line = refresh.render_line(
        **_fields(
            note="（手寫的很長很長很長很長很長很長很長很長很長很長很長很長的旁註）",
            action="審",
            size="+1/-1",
            title=title,
        )
    )
    head, _, tail = line.partition(" — ")
    assert "→" not in head and "+1/-1" in head
    assert tail == " ".join(title.split()) + " i/1.md"
    assert board_state_width(head + " i/1.md") > refresh.LINE_BUDGET  # best effort


def test_line_without_new_fields_still_parses():
    text = (
        "## 🎯 我的下一件（1）\n\n"
        "1. [ ] 🔀 CI 紅 @octocat 💤 i/9.md — Old shape\n\n"
        "## ✅ 最近結案（1）\n\n- [x] 🔀 merged @octocat i/8.md — Old closed\n"
    )
    parsed = sync.parse_board(text)
    assert parsed["errors"] == []
    assert [(ln["action"], ln["size"], ln["ended"]) for ln in parsed["lines"]] == [
        (None, None, None)
    ] * 2
    assert (
        _render(parsed["lines"][0]) == "1. [ ] 🔀 CI 紅 @octocat 💤 — Old shape i/9.md"
    )


def test_waiting_section_lines_have_no_action_or_size(tmp_path, gh):
    write_board(
        tmp_path,
        board_text(
            wait=[row(1, icon="🔀", status="等 review", author="me", numbered=False)]
        ),
    )
    put_detail(tmp_path, 1)
    gh.prs[1] = pr_meta(1, author="me")
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    waiting = section_rows(tmp_path)["⏳"]
    assert len(waiting) == 1
    assert "→" not in waiting[0] and "+10/-2" not in waiting[0]


def test_action_rows_show_action_and_size_and_done_rows_the_closing_date(tmp_path, gh):
    write_board(
        tmp_path,
        board_text(
            focus=[row(1), row(2, icon="🔀", status="CI 紅", author="me")],
            done=[row(3, icon="🔀", status="merged", author="me", numbered=False)],
        ),
    )
    for n in (1, 2, 3):
        put_detail(tmp_path, n)
    gh.prs[1] = pr_meta(1, additions=1210, deletions=340)
    gh.prs[2] = pr_meta(2, author="me", statusCheckRollup=[{"conclusion": "FAILURE"}])
    gh.prs[3] = pr_meta(3, author="me", state="MERGED", mergedAt="2026-09-28T08:00:00Z")
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    sections = section_rows(tmp_path)
    assert sections["🎯"][0].endswith("→修CI +10/-2 — PR 2 i/2.md")
    assert sections["👀"][0].endswith("待 review @carol +1.2k/-340 — PR 1 i/1.md")
    assert sections["✅"][0].endswith("merged @me 09-28 — PR 3 i/3.md")
    # the full facts stay in the detail file
    assert "- 規模：Δ+1210/-340" in (tmp_path / ".maigo/i/1.md").read_text()
    again = board_lines(tmp_path)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert board_lines(tmp_path) == again  # fixed point


# --- sections: own work and reviews are separate --------------------------------


def section_rows(root: Path) -> dict[str, list[str]]:
    """Item lines of the written board, grouped by `## ` heading glyph."""
    out: dict[str, list[str]] = {}
    current = ""
    for ln in board_lines(root):
        if ln.startswith("## "):
            current = ln[3]
            out[current] = []
        elif current and ln[:1] in {"-", "1", "2", "3", "4", "5", "6", "7", "8", "9"}:
            if "[" in ln[:8]:
                out[current].append(ln)
    return out


def test_airflow_scale_own_rows_head_the_file(tmp_path, gh):
    reviews = list(range(1, 56))
    focus = [row(n, numbered=True) for n in reviews]
    focus += [
        row(101, icon="🔀", status="CI 紅", author="me"),
        row(102, icon="🔀", status="有衝突", author="me"),
        row(103, icon="🐛", status="待 triage", author="rep"),
    ]
    write_board(tmp_path, board_text(focus=focus))
    for n in reviews + [101, 102]:
        put_detail(tmp_path, n)
    put_detail(tmp_path, 103, kind="issues", icon="🐛", status="待 triage")
    for n in reviews:
        gh.prs[n] = pr_meta(n, updated=f"2026-09-{1 + n % 28:02d}T00:00:00Z")
    gh.prs[101] = pr_meta(
        101, author="me", statusCheckRollup=[{"conclusion": "FAILURE"}]
    )
    gh.prs[102] = pr_meta(102, author="me", mergeable="CONFLICTING")
    gh.issues[103] = issue_meta(103)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    sections = section_rows(tmp_path)
    first_item = next(ln for ln in board_lines(tmp_path) if sync._ITEM_RE.match(ln))
    assert " 🔀 " in first_item or " 🐛 " in first_item
    assert len(sections["🎯"]) == 3
    assert all("👀" not in ln.split(" i/")[0] for ln in sections["🎯"])
    assert [ln.split(".")[0] for ln in sections["🎯"]] == ["1", "2", "3"]
    assert len(sections["👀"]) == 55
    assert [ln.split(".")[0] for ln in sections["👀"]] == [str(i) for i in range(1, 56)]
    assert all("👀" in ln.split(" i/")[0] for ln in sections["👀"])


def test_boost_reorders_within_review_section(tmp_path, gh):
    setup_weight_prs(tmp_path, gh, AUTHORS)
    (tmp_path / ".maigo" / "board-weights.txt").write_text("author:kaxil\n")
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    review = section_rows(tmp_path)["👀"]
    assert [int(ln.split(" i/")[1].split(".md")[0]) for ln in review] == [3, 1, 2, 4]


def test_waiting_and_done_list_own_rows_first(tmp_path, gh):
    old = "2026-09-29T00:00:00Z"
    wait = [
        row(1, icon="👀", status="已看完", numbered=False),
        row(2, icon="🔀", status="等 review", author="me", numbered=False),
    ]
    done = [
        row(3, icon="👀", status="merged", numbered=False),
        row(4, icon="🔀", status="merged", author="me", numbered=False),
    ]
    write_board(tmp_path, board_text(wait=wait, done=done))
    for n in (1, 2, 3, 4):
        put_detail(tmp_path, n)
    gh.prs[1] = pr_meta(
        1,
        updated="2026-09-30T10:00:00Z",
        reviews=[{"author": {"login": "me"}, "state": "COMMENTED", "submittedAt": old}],
    )
    gh.prs[2] = pr_meta(2, author="me", updated="2026-09-01T00:00:00Z")
    gh.prs[3] = pr_meta(
        3, state="MERGED", mergedAt=RECENT, updated="2026-09-30T10:00:00Z"
    )
    gh.prs[4] = pr_meta(
        4, author="me", state="MERGED", mergedAt=RECENT, updated="2026-09-01T00:00:00Z"
    )
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    sections = section_rows(tmp_path)
    for glyph, own, theirs in (("⏳", 2, 1), ("✅", 4, 3)):
        order = [int(ln.split(" i/")[1].split(".md")[0]) for ln in sections[glyph]]
        assert order == [own, theirs]  # own first even though it is older


def test_unreachable_review_row_goes_to_review_section(tmp_path, gh):
    write_board(
        tmp_path,
        board_text(focus=[row(1), row(2, icon="🔀", status="CI 紅", author="me")]),
    )
    put_detail(tmp_path, 1)
    put_detail(tmp_path, 2)
    gh.prs[2] = pr_meta(2, author="me")
    gh.fail = {1}
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    sections = section_rows(tmp_path)
    assert [ln for ln in sections["👀"] if "抓不到" in ln and "i/1.md" in ln]
    assert all("i/1.md" not in ln for ln in sections["🎯"])


def test_old_three_section_board_normalizes_to_four_sections(tmp_path, gh, capsys):
    focus = [row(n) for n in (1, 2)] + [row(3, icon="🔀", status="CI 紅", author="me")]
    write_board(tmp_path, board_text(focus=focus))
    for n in (1, 2, 3):
        put_detail(tmp_path, n)
    for n in (1, 2):
        gh.prs[n] = pr_meta(n)
    gh.prs[3] = pr_meta(3, author="me", statusCheckRollup=[{"conclusion": "FAILURE"}])
    before = tree_hash(tmp_path)
    assert run_cli(tmp_path, "--no-discovery", "--json") == 0
    summary = json.loads(capsys.readouterr().out)
    assert tree_hash(tmp_path) == before  # preview writes nothing
    diff = summary["diff"]
    assert "+## 👀 待我 review（2）" in diff and "+## 🎯 我的下一件（1）" in diff
    assert "-## 🎯 下一件（3）" in diff
    for n in (1, 2, 3):  # no row lost, only moved
        assert f"i/{n}.md" in diff
    assert summary["counts"] == {"🎯": 1, "👀": 2, "⏳": 0, "✅": 0}


# --- board-load.txt: the `載入` line in detail files ---------------------------


def _set_load(root, text, *, user=None, home=None):
    (root / ".maigo").mkdir(parents=True, exist_ok=True)
    if text is not None:
        (root / ".maigo" / "board-load.txt").write_text(text)
    if user is not None:
        folder = home / ".config" / "maigo"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "board-load.txt").write_text(user)


def _detail(root, n):
    return (root / ".maigo" / "i" / f"{n}.md").read_text()


def _load_line(root, n):
    return next(
        (ln for ln in _detail(root, n).splitlines() if ln.startswith("- 載入")), None
    )


def _load_board(tmp_path, gh):
    write_board(
        tmp_path,
        board_text(
            focus=[
                row(1),
                row(2, icon="🔀", status="CI 紅", author="me"),
                row(4, icon="🐛", status="待 triage", author="rep"),
            ],
            done=[row(3, icon="👀", status="merged", numbered=False)],
        ),
    )
    for n in (1, 2, 3):
        put_detail(tmp_path, n)
    put_detail(tmp_path, 4, kind="issues", icon="🐛", status="待 triage")
    gh.prs[1] = pr_meta(1, headRefName="theirs/topic")
    gh.prs[2] = pr_meta(
        2, author="me", headRefName="feat/mine",
        statusCheckRollup=[{"conclusion": "FAILURE"}],
    )  # fmt: skip
    gh.prs[3] = pr_meta(3, state="MERGED", mergedAt=RECENT)
    gh.issues[4] = issue_meta(4)


def test_pr_fields_include_head_ref_name():
    assert "headRefName" in refresh.PR_FIELDS.split(",")


def test_review_row_uses_pr_template(tmp_path, gh):
    _load_board(tmp_path, gh)
    _set_load(tmp_path, "pr:wt switch pr:{number}\nbranch:wt switch {branch}\n")
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert _load_line(tmp_path, 1) == "- 載入：`wt switch pr:1`"


def test_own_pr_prefers_branch_template_with_head_ref_name(tmp_path, gh):
    _load_board(tmp_path, gh)
    _set_load(tmp_path, "pr:wt switch pr:{number}\nbranch:wt switch {branch}\n")
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert _load_line(tmp_path, 2) == "- 載入：`wt switch feat/mine`"


def test_own_pr_falls_back_to_pr_template(tmp_path, gh):
    _load_board(tmp_path, gh)
    _set_load(tmp_path, "pr:wt switch pr:{number}\n")
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert _load_line(tmp_path, 2) == "- 載入：`wt switch pr:2`"


def test_load_line_omitted_without_config(tmp_path, gh):
    _load_board(tmp_path, gh)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert all(_load_line(tmp_path, n) is None for n in (1, 2, 3))
    assert "wt" not in refresh.LOAD_FILENAME and not refresh.load_load_templates(
        tmp_path
    )  # no built-in default


def test_load_line_omitted_for_issue_cross_repo_and_done_rows(tmp_path, gh):
    _load_board(tmp_path, gh)
    cross = "https://github.com/o/other/pull/9"
    put_detail(tmp_path, 9, text=detail_text(9).replace(url(9), cross))
    (tmp_path / ".maigo/i/9.md").rename(tmp_path / ".maigo/i/other-9.md")
    text = (
        (tmp_path / ".maigo/board.md")
        .read_text()
        .replace(
            "## ⏳ 等別人",
            "1. [ ] 👀 待 review @carol i/other-9.md — Cross\n\n## ⏳ 等別人",
            1,
        )
    )
    write_board(tmp_path, text)
    gh.prs[9] = pr_meta(9)
    _set_load(tmp_path, "pr:wt switch pr:{number}\n")
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert _load_line(tmp_path, 4) is None  # issue
    assert _load_line(tmp_path, 3) is None  # closed
    other = (tmp_path / ".maigo/i/other-9.md").read_text()
    assert "- 載入" not in other  # cross-repo
    assert _load_line(tmp_path, 1) is not None


def test_repo_layer_overrides_user_layer_per_key(tmp_path, isolated_home):
    _set_load(
        tmp_path, "pr:repo {number}\n",
        user="pr:user {number}\nbranch:user {branch}\n", home=isolated_home,
    )  # fmt: skip
    assert refresh.load_load_templates(tmp_path) == {
        "pr": "repo {number}",
        "branch": "user {branch}",
    }


@pytest.mark.parametrize(
    ("content", "lineno"),
    [
        ("# c\nlabel:foo\n", 2),
        ("pr:go {nubmer}\n", 1),
        ("branch:go {repo}\n", 1),
        ("pr:{branch}\n", 1),
        ("pr:   \n", 1),
    ],
)
def test_bad_load_template_fails_with_file_and_line(
    tmp_path, gh, capsys, content, lineno
):
    _load_board(tmp_path, gh)
    _set_load(tmp_path, content)
    before = tree_hash(tmp_path)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 1
    assert f"board-load.txt:{lineno}:" in capsys.readouterr().err
    assert tree_hash(tmp_path) == before
    assert not [c for c in gh.calls if c[:2] == ["gh", "pr"]]


@pytest.mark.parametrize(
    "branch", ["x; rm -rf ~", "$(id)", "a b", "-rf", "a/../b", "bad\n"]
)
def test_unsafe_branch_name_omits_load_line(tmp_path, gh, capsys, branch):
    _load_board(tmp_path, gh)
    gh.prs[2]["headRefName"] = branch
    _set_load(tmp_path, "pr:wt switch pr:{number}\nbranch:wt switch {branch}\n")
    assert run_cli(tmp_path, "--apply", "--no-discovery", "--json") == 0
    assert _load_line(tmp_path, 2) is None
    assert any("不安全" in w for w in json.loads(capsys.readouterr().out)["warnings"])


def test_unreachable_row_drops_the_stale_action_but_keeps_size(tmp_path, gh):
    write_board(
        tmp_path,
        board_text(focus=[]).replace(
            "## ⏳ 等別人",
            "## 👀 待我 review（1）\n\n"
            "1. [ ] 👀 待 review（x） @carol →審 +1/-1 i/1.md — Title 1\n\n## ⏳ 等別人",
            1,
        ),
    )
    put_detail(tmp_path, 1)
    gh.prs[1] = pr_meta(1)
    gh.fail = {1}
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    line = section_rows(tmp_path)["👀"][0]
    # a short hand-written note keeps the line inside the width budget, so a stale
    # action would otherwise show
    assert "抓不到（x）" in line and "→" not in line
    assert "+1/-1" in line


def test_skill_load_examples_parse():
    text = SKILL_MD.read_text(encoding="utf-8")
    start = text.index("# 載到本機的指令樣板（範例）")
    fence = text.rindex("```text\n", 0, start) + len("```text\n")
    example = text[fence : text.index("```", fence)]  # fence is indented in the list
    assert set(refresh.parse_load_templates(example, "format-spec.md")) == {
        "pr",
        "branch",
    }


def test_takeover_format_spec_example_parses():
    text = SKILL_MD.read_text(encoding="utf-8")
    start = text.index("# 接手的 PR\n")
    fence = text.rindex("```text\n", 0, start) + len("```text\n")
    example = text[fence : text.index("```", fence)]
    assert set(refresh.parse_takeover(example, "format-spec.md", REPO)) == {
        ("o", "r", 4821),
        ("o", "r", 4822),
        ("other-org", "other-repo", 17),
        ("example", "project", 9),
    }


# --- board-weights: same-rank boost ---------------------------------------------

EXAMPLE_WEIGHTS = """\
# boosted authors first, then topics
author:kaxil
author:FrankYang0529
title:common\\.ai|PydanticAI|LLMOperator|AgentOperator|DocumentLoader
"""


def focus_order(root: Path) -> list[int]:
    return [
        int(ln.split(" i/")[1].split(".md")[0])
        for ln in board_lines(root)
        if ln[:1].isdigit() and ". [" in ln[:6]
    ]


def setup_weight_prs(root, gh, authors, titles=None):
    write_board(root, board_text(focus=[row(n, author=a) for n, a in authors.items()]))
    for n, author in authors.items():
        put_detail(root, n)
        gh.prs[n] = pr_meta(n, author=author, updated=f"2026-09-0{n}T00:00:00Z")
        gh.prs[n]["title"] = (titles or {}).get(n, f"PR {n}")


AUTHORS = {1: "carol", 2: "dave", 3: "kaxil", 4: "erin"}


def test_w1_boosted_author_sorts_first_within_the_same_rank(tmp_path, gh):
    setup_weight_prs(tmp_path, gh, AUTHORS)
    (tmp_path / ".maigo" / "board-weights.txt").write_text("author:KAXIL\n")
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert focus_order(tmp_path) == [3, 1, 2, 4]  # boosted first, rest oldest-first


def test_w1_title_regex_is_case_insensitive_and_first_matching_rule_wins(tmp_path, gh):
    setup_weight_prs(
        tmp_path,
        gh,
        AUTHORS,
        titles={2: "Fix pydanticai agent", 4: "Docs for Common.AI"},
    )
    (tmp_path / ".maigo" / "board-weights.txt").write_text(EXAMPLE_WEIGHTS)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    # kaxil (rule 1) beats both title matches (rule 3); the two matches tie -> oldest first
    assert focus_order(tmp_path) == [3, 2, 4, 1]


def test_w2_boost_never_crosses_a_rank(tmp_path, gh):
    focus = [row(1, author="kaxil"), row(2, icon="🔀", status="CI 紅", author="me")]
    write_board(tmp_path, board_text(focus=focus))
    for n in (1, 2):
        put_detail(tmp_path, n)
    gh.prs[1] = pr_meta(1, author="kaxil")
    gh.prs[2] = pr_meta(2, author="me", statusCheckRollup=[{"conclusion": "FAILURE"}])
    (tmp_path / ".maigo" / "board-weights.txt").write_text("author:kaxil\n")
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert focus_order(tmp_path) == [2, 1]  # CI 紅 outranks the boosted 待 review


def test_w2_boost_does_not_reorder_the_waiting_section(gh):
    rows = [
        {"rank": 5, "author": a, "title": "t", "updated_at": ts, "key": ("o", "r", n)}
        for n, (a, ts) in enumerate(
            [("carol", "2026-09-02T00:00:00Z"), ("kaxil", "2026-09-01T00:00:00Z")]
        )
    ]
    rules = refresh.parse_weights("author:kaxil\n", "w.txt")
    assert [r["author"] for r in refresh.sort_rows("⏳", rows, rules)] == [
        "carol",
        "kaxil",
    ]  # newest first, untouched by the boost


def test_w3_no_config_keeps_the_original_order(tmp_path, gh):
    setup_weight_prs(tmp_path, gh, AUTHORS)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert focus_order(tmp_path) == [1, 2, 3, 4]  # oldest-updated first, as before


def test_w4_repo_layer_outranks_the_user_layer(tmp_path, gh, isolated_home):
    setup_weight_prs(tmp_path, gh, AUTHORS)
    (tmp_path / ".maigo" / "board-weights.txt").write_text("author:kaxil\n")
    user_dir = isolated_home / ".config" / "maigo"
    user_dir.mkdir(parents=True)
    (user_dir / "board-weights.txt").write_text("author:erin\nauthor:dave\n")
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert focus_order(tmp_path) == [3, 4, 2, 1]  # kaxil (repo), erin, dave (user)


def test_w5_weights_flag_replaces_both_layers(tmp_path, gh, isolated_home):
    setup_weight_prs(tmp_path, gh, AUTHORS)
    (tmp_path / ".maigo" / "board-weights.txt").write_text("author:kaxil\n")
    explicit = tmp_path / "elsewhere.txt"
    explicit.write_text("author:erin\n")
    assert (
        run_cli(tmp_path, "--apply", "--no-discovery", "--weights", str(explicit)) == 0
    )
    assert focus_order(tmp_path) == [4, 1, 2, 3]  # only erin is boosted
    assert (
        run_cli(tmp_path, "--no-discovery", "--weights", str(tmp_path / "no.txt")) == 1
    )


@pytest.mark.parametrize(
    ("content", "lineno", "needle"),
    [
        ("# c\nauthor:kaxil\nlabel:foo\n", 3, "label:foo"),
        ("author:kaxil\n\ntitle:(unclosed\n", 3, "regex"),
        ("author:\n", 1, "author:"),
        ("author:ka xil\n", 1, "author:ka xil"),
    ],
)
def test_w6_bad_line_exits_1_naming_file_and_line(
    tmp_path, gh, capsys, content, lineno, needle
):
    setup_weight_prs(tmp_path, gh, AUTHORS)
    path = tmp_path / ".maigo" / "board-weights.txt"
    path.write_text(content)
    before = tree_hash(tmp_path)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 1
    err = capsys.readouterr().err
    assert f"{path}:{lineno}:" in err and needle in err
    assert tree_hash(tmp_path) == before  # rejected before anything was written
    assert not [c for c in gh.calls if c[:2] == ["gh", "pr"]]  # and before any fetch


def test_w7_utf8_bom_at_file_start_is_ignored(tmp_path, gh):
    setup_weight_prs(tmp_path, gh, AUTHORS)
    (tmp_path / ".maigo" / "board-weights.txt").write_bytes(
        b"\xef\xbb\xbfauthor:kaxil\n"
    )
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert focus_order(tmp_path) == [3, 1, 2, 4]


# --- board-takeover: PRs taken over from someone else ---------------------------

TAKEOVER_SAMPLE = """\
# 接手的 PR
76991  # 還沒決定 push 到作者 branch 或另開 PR
#69849
o/x#5
https://github.com/Apache/Airflow/pull/7/
# 7
#note
76991
"""


def put_takeover(root: Path, text: str) -> Path:
    path = root / ".maigo" / "board-takeover.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def setup_takeover_pr(root, gh, *, icon="👀", status="待 review", mark=" ", **meta):
    write_board(root, board_text(focus=[row(1, mark, icon=icon, status=status)]))
    put_detail(root, 1)
    gh.prs[1] = pr_meta(1, author="carol", **meta)


def test_takeover_parse_grammar():
    found = refresh.parse_takeover(TAKEOVER_SAMPLE, "t.txt", "o/r")
    expected = {
        ("o", "r", 76991),
        ("o", "r", 69849),
        ("o", "x", 5),
        ("apache", "airflow", 7),
    }
    assert set(found) == expected
    assert ("o", "r", 7) not in found  # `# 7` is a comment
    assert found[("apache", "airflow", 7)] == "Apache/Airflow#7"


def test_takeover_parse_empty_and_comment_only_is_empty():
    assert refresh.parse_takeover("", "t.txt", "o/r") == {}
    assert refresh.parse_takeover("# a\n\n  # b\n", "t.txt", "o/r") == {}


@pytest.mark.parametrize(
    "bad",
    [
        "https://github.com/o/r/issues/5",
        "abc",
        "76991 extra",
        "²",
        "#²",
    ],
)
def test_takeover_parse_rejects_bad_lines(bad):
    with pytest.raises(refresh.RefreshError) as error:
        refresh.parse_takeover(f"# ok\n{bad}\n", "board-takeover.txt", "o/r")
    assert error.value.code == 1
    assert "board-takeover.txt:2" in str(error.value)


def test_takeover_moves_review_row_to_next(tmp_path, gh):
    setup_takeover_pr(tmp_path, gh)
    put_takeover(tmp_path, "1\n")
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    rows = section_rows(tmp_path)
    assert len(rows["🎯"]) == 1 and "🔀 接棒 @carol" in rows["🎯"][0]
    assert not rows.get("👀")


def test_takeover_waiting_after_push_stays_next(tmp_path, gh):
    setup_takeover_pr(
        tmp_path,
        gh,
        statusCheckRollup=[{"status": "IN_PROGRESS"}],
        comments=[
            {"author": {"login": YOU}, "createdAt": "2026-09-20T00:00:00Z"},
        ],
    )
    put_takeover(tmp_path, "1\n")
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    rows = section_rows(tmp_path)
    assert len(rows["🎯"]) == 1 and "🔀 接棒" in rows["🎯"][0]


def test_takeover_blocker_keeps_own_status(tmp_path, gh):
    setup_takeover_pr(tmp_path, gh, statusCheckRollup=[{"conclusion": "FAILURE"}])
    put_takeover(tmp_path, "1\n")
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    rows = section_rows(tmp_path)
    assert len(rows["🎯"]) == 1 and "🔀 CI 紅" in rows["🎯"][0]


def test_takeover_removed_from_list_reverts_to_review(tmp_path, gh):
    setup_takeover_pr(tmp_path, gh, icon="🔀", status="接棒")
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    rows = section_rows(tmp_path)
    assert len(rows["👀"]) == 1 and "👀" in rows["👀"][0]
    assert not rows.get("🎯")


def test_takeover_own_pr_never_reverted(tmp_path, gh):
    write_board(
        tmp_path, board_text(focus=[row(1, icon="🔀", status="CI 紅", author=YOU)])
    )
    put_detail(tmp_path, 1, icon="🔀", status="CI 紅")
    gh.prs[1] = pr_meta(1, author=YOU, statusCheckRollup=[{"conclusion": "FAILURE"}])
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    rows = section_rows(tmp_path)
    assert len(rows["🎯"]) == 1 and "🔀" in rows["🎯"][0]


def test_takeover_merged_keeps_own_retention(tmp_path, gh):
    five_days = (NOW - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    done = [
        row(1, " ", icon="👀", status="merged", numbered=False),
        row(2, " ", icon="👀", status="merged", numbered=False),
    ]  # unchecked: no learning-pending exemption from the 3-day review retention
    write_board(tmp_path, board_text(done=done))
    for n in (1, 2):
        put_detail(tmp_path, n, status="merged")
        gh.prs[n] = pr_meta(n, state="MERGED", mergedAt=five_days)
    put_takeover(tmp_path, "1\n")
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    text = (tmp_path / ".maigo/board.md").read_text()
    assert "i/1.md" in text  # listed: 7-day own retention
    assert "i/2.md" not in text  # unlisted 👀: 3-day retention, aged out
    assert "i/1.md" in "".join(section_rows(tmp_path)["✅"])


def test_takeover_checked_row_skips_ack(tmp_path, gh):
    published = _checked_review_setup(tmp_path, gh)
    put_takeover(tmp_path, "1\n")
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert "acknowledged_at" not in report.metadata(Path(published["path"]).read_text())
    rows = section_rows(tmp_path)
    assert rows["🎯"][0].startswith("1. [x]")


def test_takeover_not_on_board_warns(tmp_path, gh, capsys):
    setup_takeover_pr(tmp_path, gh)
    put_takeover(tmp_path, "9\n")
    before = board_lines(tmp_path)
    assert run_cli(tmp_path, "--no-discovery", "--json") == 0
    summary = json.loads(capsys.readouterr().out)
    assert any("o/r#9" in w and "不在板上" in w for w in summary["warnings"])
    assert board_lines(tmp_path) == before


def test_takeover_on_board_but_unreachable_warns_skip_not_missing(tmp_path, gh, capsys):
    setup_takeover_pr(tmp_path, gh)
    gh.fail = {1}
    put_takeover(tmp_path, "1\n")
    assert run_cli(tmp_path, "--no-discovery", "--json") == 0
    warnings = json.loads(capsys.readouterr().out)["warnings"]
    assert any("o/r#1" in w and "本輪略過" in w for w in warnings)
    assert not any("不在板上" in w for w in warnings)


def test_takeover_listed_issue_warns_and_stays_issue(tmp_path, gh, capsys):
    write_board(tmp_path, board_text(focus=[row(4, icon="🐛", status="待 triage")]))
    put_detail(tmp_path, 4, kind="issues", icon="🐛", status="待 triage")
    gh.issues[4] = issue_meta(4)
    put_takeover(tmp_path, "4\n")
    assert run_cli(tmp_path, "--no-discovery", "--json") == 0
    warnings = json.loads(capsys.readouterr().out)["warnings"]
    assert any("o/r#4" in w and "是 issue" in w for w in warnings)


def test_takeover_listed_dropped_item_warns(tmp_path, gh, capsys):
    write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1)
    gh.prs[1] = pr_meta(1)
    state = tmp_path / ".maigo" / "_internal" / "board"
    state.mkdir(parents=True)
    drop = {"url": url(1), "event": "drop", "reason": "drop", "at": _ago(days=1)}
    (state / "dropped.jsonl").write_text(json.dumps(drop) + "\n")
    put_takeover(tmp_path, "1\n")
    assert run_cli(tmp_path, "--no-discovery", "--json") == 0
    warnings = json.loads(capsys.readouterr().out)["warnings"]
    assert any("o/r#1" in w and "已被 drop" in w for w in warnings)


def test_takeover_row_without_author_not_reverted(tmp_path, gh):
    write_board(
        tmp_path, board_text(focus=[row(1, icon="🔀", status="接棒", author="")])
    )
    put_detail(tmp_path, 1, icon="🔀", status="接棒")
    meta = pr_meta(1, author="carol")
    meta["author"] = None
    gh.prs[1] = meta
    g = refresh.gather(
        tmp_path, REPO, YOU, now=NOW, add=[], max_new=50,
        discovery=False, stale_days=14, jobs=1,
    )  # fmt: skip
    assert refresh.apply_takeover(g, {}) == []
    entry = next(e for e in g.entries if e.line is not None)
    assert entry.line["type"] == "🔀"


def test_takeover_empty_you_never_reverts(tmp_path, gh):
    setup_takeover_pr(tmp_path, gh, icon="🔀", status="接棒")
    g = refresh.gather(
        tmp_path, REPO, "", now=NOW, add=[], max_new=50,
        discovery=False, stale_days=14, jobs=1,
    )  # fmt: skip
    assert refresh.apply_takeover(g, {}) == []
    entry = next(e for e in g.entries if e.line is not None)
    assert entry.line["type"] == "🔀"


def test_takeover_bad_line_rejects_before_gh(tmp_path, gh, capsys):
    setup_takeover_pr(tmp_path, gh)
    path = put_takeover(tmp_path, "1\nabc\n")
    before = tree_hash(tmp_path)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 1
    assert f"{path}:2:" in capsys.readouterr().err
    assert tree_hash(tmp_path) == before
    assert not [c for c in gh.calls if c[:2] == ["gh", "pr"]]


# --- T8 / T9: aging and closed artifacts ------------------------------------------


def test_t8_aging_removes_deletes_backs_up_and_logs(tmp_path, gh):
    old = (NOW - timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
    done = [
        row(1, icon="👀", status="merged", numbered=False),
        row(2, "x", icon="👀", status="merged", numbered=False),
        row(3, icon="👀", status="已放棄", numbered=False),
    ]
    write_board(tmp_path, board_text(done=done))
    for n in (1, 2, 3):
        put_detail(tmp_path, n, status="merged")
    gh.prs[1] = pr_meta(1, state="MERGED", mergedAt=old, updated=RECENT)
    gh.prs[2] = pr_meta(2, state="MERGED", mergedAt=old, updated=RECENT)
    gh.prs[3] = pr_meta(3)
    ledger_dir = tmp_path / ".maigo" / "_internal" / "board"
    ledger_dir.mkdir(parents=True)
    drop = {"url": url(3), "event": "drop", "reason": "drop", "at": old}
    (ledger_dir / "dropped.jsonl").write_text(json.dumps(drop) + "\n")
    detail_one = (tmp_path / ".maigo/i/1.md").read_bytes()
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    text = (tmp_path / ".maigo/board.md").read_text()
    assert "i/1.md" not in text and "i/3.md" not in text
    assert "i/2.md" in text  # [x] without 🧠 is awaiting its learning pass
    assert not (tmp_path / ".maigo/i/1.md").exists()
    assert not (tmp_path / ".maigo/i/3.md").exists()
    assert (tmp_path / ".maigo/i/2.md").exists()
    backups = list((ledger_dir / "backup").glob("*/i/1.md"))
    assert backups and backups[0].read_bytes() == detail_one
    aged = [e for e in ledger(tmp_path) if e["reason"] == "aged"]
    assert {e["url"] for e in aged} == {url(1), url(3)}


def _ago(**delta) -> str:
    return (NOW - timedelta(**delta)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _done_board(root, gh, specs):
    """`specs`: (n, icon, mark, ended-ago kwargs) rows, all already merged."""
    done = [
        row(n, mark, icon=icon, status="merged", numbered=False, author=author)
        for n, icon, mark, author, _ in specs
    ]
    write_board(root, board_text(done=done))
    for n, icon, _, author, ago in specs:
        put_detail(root, n, status="merged")
        gh.prs[n] = pr_meta(
            n, author=author, state="MERGED", mergedAt=_ago(**ago), updated=RECENT
        )


def _aged_urls(root) -> set[str]:
    return {e["url"] for e in ledger(root) if e["reason"] == "aged"}


def test_done_section_capped_at_ten_newest(tmp_path, gh):
    specs = [(n, "🔀", " ", "me", {"hours": n}) for n in range(1, 13)]
    _done_board(tmp_path, gh, specs)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    kept = section_rows(tmp_path)["✅"]
    assert len(kept) == refresh.DONE_CAP
    assert [int(ln.split(" i/")[1].split(".md")[0]) for ln in kept] == list(
        range(1, 11)
    )
    assert _aged_urls(tmp_path) == {url(11), url(12)}  # the two oldest
    assert not (tmp_path / ".maigo/i/12.md").exists()
    assert (tmp_path / ".maigo/i/10.md").exists()
    assert "## ✅ 最近結案（10）" in board_lines(tmp_path)


def test_review_rows_age_after_three_days_own_after_seven(tmp_path, gh):
    specs = [
        (1, "👀", " ", "carol", {"days": 4}),
        (2, "👀", " ", "carol", {"days": 2}),
        (3, "🔀", " ", "me", {"days": 4}),
        (4, "🔀", " ", "me", {"days": 8}),
    ]
    _done_board(tmp_path, gh, specs)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    text = (tmp_path / ".maigo/board.md").read_text()
    assert "i/1.md" not in text and "i/4.md" not in text
    assert "i/2.md" in text and "i/3.md" in text
    assert _aged_urls(tmp_path) == {url(1), url(4)}


def test_learn_pending_exemption_expires_after_thirty_days(tmp_path, gh, capsys):
    specs = [
        (1, "👀", "x", "carol", {"days": 20}),
        (2, "👀", "x", "carol", {"days": 31}),
        (3, "👀", "x", "carol", {"days": 26}),
    ]
    _done_board(tmp_path, gh, specs)
    assert run_cli(tmp_path, "--no-discovery", "--json") == 0
    summary = json.loads(capsys.readouterr().out)
    assert [(e["url"], e["days_left"]) for e in summary["learn_expiring"]] == [
        (url(3), 4)
    ]  # only rows within a week of expiry are listed
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    text = (tmp_path / ".maigo/board.md").read_text()
    assert "i/1.md" in text and "i/3.md" in text
    assert "i/2.md" not in text  # exemption lapsed: ages like any other row
    assert _aged_urls(tmp_path) == {url(2)}


def test_learn_pending_rows_do_not_count_against_cap_before_expiry(tmp_path, gh):
    specs = [(n, "🔀", " ", "me", {"hours": n}) for n in range(1, 11)]
    specs += [(n, "👀", "x", "carol", {"days": n - 4}) for n in (11, 12, 13)]
    _done_board(tmp_path, gh, specs)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    kept = section_rows(tmp_path)["✅"]
    assert len(kept) == 13  # ten capped rows plus three learning-pending ones
    assert _aged_urls(tmp_path) == set()


def test_t9_closed_artifact_is_not_added_but_logged(tmp_path, gh):
    write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1)
    gh.prs[1] = pr_meta(1)
    gh.prs[5] = pr_meta(5, state="MERGED", mergedAt=RECENT)
    report.publish(
        tmp_path, url(5), REPO, "PR 5", "## A\nx\n", HEAD, "APPROVE", owner="others"
    )
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert "i/5.md" not in (tmp_path / ".maigo/board.md").read_text()
    assert not (tmp_path / ".maigo/i/5.md").exists()
    closed = [e for e in ledger(tmp_path) if e["reason"] == "closed"]
    assert [e["url"] for e in closed] == [url(5)]


# --- T10 / T11: unreachable and notes --------------------------------------------


def test_t10_unreachable_row_goes_first_with_error_note_then_recovers(tmp_path, gh):
    write_board(tmp_path, board_text(focus=[row(1), row(2)]))
    put_detail(tmp_path, 1)
    put_detail(tmp_path, 2, judgment="別動我")
    gh.prs[1] = pr_meta(1)
    gh.prs[2] = pr_meta(2)
    gh.fail = {2}
    detail_two = (tmp_path / ".maigo/i/2.md").read_bytes()
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    first = [ln for ln in board_lines(tmp_path) if ln.startswith("1. ")][0]
    assert (
        "抓不到（gh 失敗：GraphQL: Could not resolve(x)）" in first
        and "i/2.md" in first
    )
    assert (tmp_path / ".maigo/i/2.md").read_bytes() == detail_two
    gh.fail = set()
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    line = [ln for ln in board_lines(tmp_path) if "i/2.md" in ln][0]
    assert "抓不到" not in line and "（" not in line


def test_t11_manual_note_is_kept(tmp_path, gh):
    write_board(
        tmp_path,
        board_text(
            focus=[
                row(
                    3,
                    icon="🐛",
                    status="IN_PROGRESS",
                    extra="（分支 fix/x）",
                    author="rep",
                )
            ]
        ),
    )
    put_detail(tmp_path, 3, kind="issues", icon="🐛", status="IN_PROGRESS")
    gh.issues[3] = issue_meta(3)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    line = [ln for ln in board_lines(tmp_path) if "i/3.md" in ln][0]
    assert "IN_PROGRESS（分支 fix/x）" in line


# --- T12: rejections --------------------------------------------------------------


def _legacy(root):
    write_board(root, "# Work Board — o/r\n\n## Active\n\n- [ ] x\n")


def _unknown_status(root):
    write_board(root, board_text(focus=[row(1, status="WEIRD")]))
    put_detail(root, 1)


def _no_board(root):
    (root / ".maigo").mkdir(parents=True)
    (root / ".maigo" / "review-board.md").write_text("# old\n")


@pytest.mark.parametrize("setup", [_legacy, _unknown_status, _no_board])
def test_t12_rejected_boards_exit_1_untouched(tmp_path, gh, setup):
    setup(tmp_path)
    before = tree_hash(tmp_path)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 1
    assert tree_hash(tmp_path) == before


def test_t12_zero_or_many_boards_exit_1(tmp_path, gh, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    gh.worktrees = [empty]
    assert sync.main(["refresh", "--repo", REPO, "--you", YOU]) == 1
    assert "找不到 board.md" in capsys.readouterr().err
    a, b = tmp_path / "a", tmp_path / "b"
    for root in (a, b):
        write_board(root, board_text())
    gh.worktrees = [a, b]
    assert sync.main(["refresh", "--repo", REPO, "--you", YOU]) == 1
    err = capsys.readouterr().err
    assert str(a) in err and str(b) in err


# --- T13: rollback ------------------------------------------------------------------


def test_t13_write_failure_restores_everything(tmp_path, gh, monkeypatch, capsys):
    write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1)
    gh.prs[1] = pr_meta(1)
    gh.prs[9] = pr_meta(9)
    board_before = (tmp_path / ".maigo/board.md").read_bytes()
    detail_before = (tmp_path / ".maigo/i/1.md").read_bytes()
    real = report.atomic_write

    def flaky(path, text):
        if Path(path).name == "board.md":
            raise OSError("disk full")
        real(path, text)

    monkeypatch.setattr(report, "atomic_write", flaky)
    assert run_cli(tmp_path, "--apply", "--no-discovery", "--add", "9") == 3
    assert (tmp_path / ".maigo/board.md").read_bytes() == board_before
    assert (tmp_path / ".maigo/i/1.md").read_bytes() == detail_before
    assert not (tmp_path / ".maigo/i/9.md").exists()
    assert ledger(tmp_path) == []
    assert not (tmp_path / ".maigo/_internal/board/snapshot.json").exists()
    assert not (tmp_path / ".maigo/_internal/board/.refresh-write-lock").exists()
    assert "已從備份還原" in capsys.readouterr().err


# --- T14: idempotence -----------------------------------------------------------------


def test_t14_second_apply_changes_nothing(tmp_path, gh):
    old = (NOW - timedelta(days=9)).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_board(
        tmp_path,
        board_text(
            focus=[row(1)],
            done=[row(2, icon="👀", status="merged", numbered=False)],
        ),
    )
    put_detail(tmp_path, 1)
    put_detail(tmp_path, 2, status="merged")
    put_detail(tmp_path, 7)  # orphan: nobody references it -> dd on the first run
    gh.prs[1] = pr_meta(1)
    gh.prs[2] = pr_meta(2, state="MERGED", mergedAt=old)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert [e["reason"] for e in ledger(tmp_path)].count("dd") == 1

    def snapshot_of_state() -> dict:
        tree = tree_hash(tmp_path)
        return {k: v for k, v in tree.items() if "/backup/" not in k}

    first = snapshot_of_state()
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert snapshot_of_state() == first


# --- T15: everything goes through run() --------------------------------------------------


def test_t15_no_direct_subprocess(tmp_path, gh, monkeypatch):
    write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1)
    gh.prs[1] = pr_meta(1)

    def boom(*args, **kwargs):
        raise AssertionError("subprocess.run called directly")

    monkeypatch.setattr(subprocess, "run", boom)
    assert run_cli(tmp_path, "--apply") == 0
    assert any(call[:2] == ["gh", "search"] for call in gh.calls)


# --- T16: preview ---------------------------------------------------------------------------


def test_t16_preview_writes_nothing_and_prints_a_diff(tmp_path, gh, capsys):
    published = _checked_review_setup(tmp_path, gh)
    before = tree_hash(tmp_path)
    assert run_cli(tmp_path, "--no-discovery", "--json") == 0
    assert tree_hash(tmp_path) == before
    assert "acknowledged_at" not in report.metadata(Path(published["path"]).read_text())
    out = json.loads(capsys.readouterr().out)
    assert out["applied"] is False
    assert (
        "--- board.md (current)" in out["diff"]
        and "+++ board.md (refreshed)" in out["diff"]
    )
    assert [r["result"] for r in out["ack_results"]] == ["acked"]
    assert run_cli(tmp_path, "--no-discovery") == 0
    assert "board.md (refreshed)" in capsys.readouterr().out


# --- T17: defaults ------------------------------------------------------------------------------


def test_t17_defaults_come_from_header_gh_user_and_worktrees(tmp_path, gh):
    write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1)
    gh.prs[1] = pr_meta(1)
    assert sync.main(["refresh", "--no-discovery"]) == 0
    assert ["gh", "api", "user", "--jq", ".login"] in gh.calls
    assert not any(call[:3] == ["gh", "repo", "view"] for call in gh.calls)
    assert any(call[0] == "git" and "worktree" in call for call in gh.calls)


def test_t17_explicit_repo_must_match_the_header(tmp_path, gh, capsys):
    write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1)
    before = tree_hash(tmp_path)
    assert run_cli(tmp_path, "--apply", repo="x/y") == 1
    assert tree_hash(tmp_path) == before
    assert "不一致" in capsys.readouterr().err


# --- T18: --add ----------------------------------------------------------------------------------


def test_t18_add_revives_an_excluded_url_after_the_write(tmp_path, gh):
    write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1)
    gh.prs[1] = pr_meta(1)
    gh.prs[8] = pr_meta(8)
    state = tmp_path / ".maigo" / "_internal" / "board"
    state.mkdir(parents=True)
    drop = {
        "url": url(8),
        "event": "drop",
        "reason": "dd",
        "at": "2026-09-01T00:00:00+00:00",
    }
    (state / "dropped.jsonl").write_text(json.dumps(drop) + "\n")
    assert run_cli(tmp_path, "--apply", "--no-discovery", "--add", "8") == 0
    events = ledger(tmp_path)
    assert events[-1]["event"] == "revive" and events[-1]["reason"] == "manual"
    assert sync.ref_key(events[-1]["url"]) == sync.ref_key(url(8))
    assert any("i/8.md" in ln for ln in board_lines(tmp_path))
    assert (tmp_path / ".maigo/i/8.md").exists()


def test_t18_add_on_cas_conflict_writes_no_revive(tmp_path, gh):
    write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1)
    gh.prs[1] = pr_meta(1)
    gh.prs[8] = pr_meta(8)
    state = tmp_path / ".maigo" / "_internal" / "board"
    state.mkdir(parents=True)
    drop = {
        "url": url(8),
        "event": "drop",
        "reason": "dd",
        "at": "2026-09-01T00:00:00+00:00",
    }
    (state / "dropped.jsonl").write_text(json.dumps(drop) + "\n")
    board = tmp_path / ".maigo" / "board.md"
    gh.on_pr_view = lambda: board.write_text(board.read_text() + "\n")
    assert run_cli(tmp_path, "--apply", "--no-discovery", "--add", "8") == 2
    assert [e["event"] for e in ledger(tmp_path)] == ["drop"]


def test_summary_lists_pending_reviews_with_their_own_fields(tmp_path, gh, capsys):
    write_board(tmp_path, board_text(focus=[row(1), row(2)]))
    put_detail(tmp_path, 1)
    put_detail(tmp_path, 2)
    gh.prs[1] = pr_meta(1)
    gh.prs[2] = pr_meta(2, author="dave")
    assert run_cli(tmp_path, "--no-discovery", "--json") == 0
    out = json.loads(capsys.readouterr().out)
    assert {(p["title"], p["author"]) for p in out["pending_reviews"]} == {
        ("PR 1", "carol"),
        ("PR 2", "dave"),
    }


def test_refresh_backfills_author_from_gh_and_drops_pending_note(tmp_path, gh):
    legacy = row(1, author=None, extra="（手寫旁註）")  # no @ at all: legacy shape
    marked = row(2, author=None, extra="（作者待補）")
    write_board(tmp_path, board_text(focus=[legacy, marked]))
    put_detail(tmp_path, 1)
    put_detail(tmp_path, 2)
    gh.prs[1] = pr_meta(1, author="octocat")
    gh.prs[2] = pr_meta(2, author="hubot")
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    lines = board_lines(tmp_path)
    first = [ln for ln in lines if "i/1.md" in ln][0]
    second = [ln for ln in lines if "i/2.md" in ln][0]
    assert "@octocat" in first and "作者待補" not in first
    assert "@hubot" in second and "作者待補" not in second and "（" not in second
    assert sync.parse_board((tmp_path / ".maigo/board.md").read_text())["errors"] == []


def test_refresh_keeps_previous_author_when_gh_has_none(tmp_path, gh):
    write_board(tmp_path, board_text(focus=[row(1, author="octocat")]))
    put_detail(tmp_path, 1)
    gh.prs[1] = pr_meta(1, author="")
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    line = [ln for ln in board_lines(tmp_path) if "i/1.md" in ln][0]
    assert "@octocat" in line and "作者待補" not in line


def test_summary_lists_author_pending_as_problem(tmp_path, gh, capsys):
    write_board(tmp_path, board_text(focus=[row(1, author=None)]))
    put_detail(tmp_path, 1)
    gh.prs[1] = pr_meta(1, author="")
    assert run_cli(tmp_path, "--apply", "--no-discovery", "--json") == 0
    out = json.loads(capsys.readouterr().out)
    assert any("作者待補" in w for w in out["warnings"])
    line = [ln for ln in board_lines(tmp_path) if "i/1.md" in ln][0]
    assert "（作者待補）" in line and "@ " not in line and not line.endswith("@")
    assert " @ " not in line


# --- Soyo review #1 regressions ---------------------------------------------------------


def _detail_with_notes_first(n: int, extra_heading: str = "## 筆記") -> str:
    return (
        f"# 👀 待 review — Old\n\n- 連結：{url(n)}\n\n"
        f"{extra_heading}\n\n我的手寫筆記\n\n## 判斷\n\nx\n"
    )


@pytest.mark.parametrize("heading", ["## 筆記", "## 其他"])
def test_s1_heading_above_judgment_rejects_instead_of_overwriting(
    tmp_path, gh, heading
):
    write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1, _detail_with_notes_first(1, heading))
    gh.prs[1] = pr_meta(1)
    before = tree_hash(tmp_path)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 1
    assert tree_hash(tmp_path) == before


def _fail_then_recover(tmp_path, gh, n: int, **setup):
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0  # normalise first
    before = [ln for ln in board_lines(tmp_path) if f"i/{n}.md" in ln]
    gh.fail = {n}
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    gh.fail = set()
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    return before, [ln for ln in board_lines(tmp_path) if f"i/{n}.md" in ln]


def test_s2_issue_in_progress_with_note_survives_a_transient_failure(tmp_path, gh):
    extra = "（分支 fix/x）"
    write_board(
        tmp_path,
        board_text(
            focus=[row(3, icon="🐛", status="IN_PROGRESS", extra=extra, author="rep")]
        ),
    )
    put_detail(tmp_path, 3, kind="issues", icon="🐛", status="IN_PROGRESS")
    gh.issues[3] = issue_meta(3)
    before, after = _fail_then_recover(tmp_path, gh, 3)
    assert "IN_PROGRESS（分支 fix/x）" in before[0] and after == before


def test_s2_issue_triage_status_survives_a_transient_failure(tmp_path, gh):
    write_board(
        tmp_path, board_text(focus=[row(3, icon="🐛", status="READY", author="rep")])
    )
    put_detail(tmp_path, 3, kind="issues", icon="🐛", status="READY")
    gh.issues[3] = issue_meta(3)
    before, after = _fail_then_recover(tmp_path, gh, 3)
    assert "READY" in before[0] and after == before


def test_s2_own_pr_note_survives_a_transient_failure(tmp_path, gh):
    write_board(
        tmp_path,
        board_text(
            focus=[
                row(4, icon="🔀", status="CI 紅", extra="（分支 feat/y）", author="me")
            ]
        ),
    )
    put_detail(tmp_path, 4)
    gh.prs[4] = pr_meta(4, author="me", statusCheckRollup=[{"conclusion": "FAILURE"}])
    before, after = _fail_then_recover(tmp_path, gh, 4)
    assert "（分支 feat/y）" in before[0] and after == before


def test_s3_a_check_made_during_a_failed_fetch_is_acked_on_recovery(tmp_path, gh):
    write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1)
    gh.prs[1] = pr_meta(1)
    published = report.publish(
        tmp_path, url(1), REPO, "PR 1", "## A\nx\n", HEAD, "APPROVE", owner="others"
    )
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    board = tmp_path / ".maigo" / "board.md"
    board.write_text(board.read_text().replace("1. [ ]", "1. [x]"))
    gh.fail = {1}
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    gh.fail = set()
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    meta = report.metadata(Path(published["path"]).read_text())
    assert meta.get("acknowledged_by") == YOU
    assert "🔖" in [ln for ln in board_lines(tmp_path) if "i/1.md" in ln][0]


def _hook_apply(monkeypatch, action):
    original = refresh._apply_refresh

    def hooked(g, built):
        action()
        return original(g, built)

    monkeypatch.setattr(refresh, "_apply_refresh", hooked)


@pytest.mark.parametrize("entrypoint", ["apply_refresh", "run_refresh"])
def test_concurrent_refresh_rejects_before_ack_or_writes(
    tmp_path, gh, monkeypatch, entrypoint
):
    board = write_board(tmp_path, board_text())
    gh.prs.update({n: pr_meta(n) for n in (1, 2)})
    gathered = refresh.gather(
        tmp_path, REPO, YOU, now=NOW, add=["1"], max_new=50,
        discovery=False, stale_days=14, jobs=1,
    )  # fmt: skip
    built = refresh.build(gathered, [])
    competing = refresh.gather(
        tmp_path, REPO, YOU, now=NOW + timedelta(seconds=1), add=["2"],
        max_new=50, discovery=False, stale_days=14, jobs=1,
    )  # fmt: skip
    competing_built = refresh.build(competing, [])
    writing, resume = Event(), Event()
    atomic_write = report.atomic_write
    run_acks = refresh.run_acks
    ack_calls = []

    def pause_first_board_write(path, text):
        if path == board and not writing.is_set():
            writing.set()
            assert resume.wait(timeout=5), "first refresh was never released"
        atomic_write(path, text)

    def record_ack_call(*args, **kwargs):
        ack_calls.append(True)
        return run_acks(*args, **kwargs)

    monkeypatch.setattr(report, "atomic_write", pause_first_board_write)
    monkeypatch.setattr(refresh, "run_acks", record_ack_call)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(refresh.apply_refresh, gathered, built)
        try:
            assert writing.wait(timeout=5), "first refresh never reached its write"
            with pytest.raises(refresh.RefreshError) as caught:
                if entrypoint == "apply_refresh":
                    refresh.apply_refresh(competing, competing_built)
                else:
                    refresh.run_refresh(
                        tmp_path, REPO, YOU, apply=True, add=["2"],
                        discovery=False, now=NOW,
                    )  # fmt: skip
            assert caught.value.code == 2
            assert ack_calls == []
        finally:
            resume.set()
        first.result(timeout=5)

    assert "i/1.md" in board.read_text()
    assert not (tmp_path / ".maigo/i/2.md").exists()
    assert not (tmp_path / ".maigo/_internal/board/.refresh-write-lock").exists()
    refresh.run_refresh(
        tmp_path, REPO, YOU, apply=True, add=["2"], discovery=False, now=NOW
    )
    assert all(f"i/{n}.md" in board.read_text() for n in (1, 2))


def test_lock_conflict_message_names_the_holder(tmp_path):
    with refresh.refresh_lock(tmp_path):
        with pytest.raises(refresh.RefreshError) as caught:
            with refresh.refresh_lock(tmp_path):
                pass
    assert caught.value.code == 2
    assert f"pid {os.getpid()}" in str(caught.value)


def test_lock_conflict_without_owner_file_keeps_the_plain_message(tmp_path):
    lock = tmp_path / ".maigo/_internal/board/.refresh-write-lock"
    lock.mkdir(parents=True)
    with pytest.raises(refresh.RefreshError) as caught:
        with refresh.refresh_lock(tmp_path):
            pass
    assert caught.value.code == 2 and "pid" not in str(caught.value)
    assert lock.is_dir()


def test_lock_directory_is_gone_after_normal_exit(tmp_path):
    lock = tmp_path / ".maigo/_internal/board/.refresh-write-lock"
    with refresh.refresh_lock(tmp_path):
        assert (lock / refresh.LOCK_OWNER_NAME).is_file()
    assert not lock.exists()


def test_lock_release_failure_warns_and_does_not_mask_the_result(
    tmp_path, monkeypatch, capsys
):
    def broken_rmdir(self):
        raise OSError("busy")

    monkeypatch.setattr(Path, "rmdir", broken_rmdir)
    with refresh.refresh_lock(tmp_path):
        result = "ok"
    assert result == "ok"
    assert "busy" in capsys.readouterr().err
    with pytest.raises(KeyError):
        with refresh.refresh_lock(tmp_path / "other"):
            raise KeyError("original")


def test_s4_cas2_message_admits_the_ack_was_written(tmp_path, gh, monkeypatch, capsys):
    published = _checked_review_setup(tmp_path, gh)
    board = tmp_path / ".maigo" / "board.md"
    _hook_apply(
        monkeypatch, lambda: board.write_text(board.read_text() + "<!-- x -->\n")
    )
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 2
    assert "acknowledged_at" in report.metadata(Path(published["path"]).read_text())
    err = capsys.readouterr().err
    assert "ack" in err and "board.md" in err
    assert not (tmp_path / ".maigo/_internal/board/.refresh-write-lock").exists()


def test_snapshot_records_the_report_displayed_before_a_concurrent_publication(
    tmp_path, gh, monkeypatch
):
    write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1)
    gh.prs[1] = pr_meta(1)
    old = report.publish(
        tmp_path, url(1), REPO, "PR 1", "## A\nOld report\n", HEAD,
        "APPROVE", owner="others",
    )  # fmt: skip

    def publish_new_report():
        report.publish(
            tmp_path, url(1), REPO, "PR 1", "## A\nNew report\n", HEAD,
            "NEEDS_CHANGES", owner="others",
        )  # fmt: skip

    _hook_apply(monkeypatch, publish_new_report)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    snapshot = json.loads(
        (tmp_path / ".maigo/_internal/board/snapshot.json").read_text()
    )
    assert snapshot["items"][url(1)]["reviewed_at"] == old["reviewed_at"]
    assert (
        report.metadata(Path(old["path"]).read_text())["reviewed_at"]
        != old["reviewed_at"]
    )


def test_refresh_rejects_an_old_check_then_accepts_a_new_explicit_check(tmp_path, gh):
    board = write_board(tmp_path, board_text(focus=[row(1, "x")]))
    put_detail(tmp_path, 1)
    gh.prs[1] = pr_meta(1)
    published = report.publish(
        tmp_path, url(1), REPO, "PR 1", "## A\nUnread report\n", HEAD,
        "APPROVE", owner="others",
    )  # fmt: skip
    result = refresh.run_refresh(
        tmp_path, REPO, YOU, apply=True, add=[], discovery=False, now=NOW
    )
    assert [r["result"] for r in result["ack_results"]] == ["report_changed"]
    assert any("重新勾選" in warning for warning in result["warnings"])
    assert "acknowledged_at" not in report.metadata(Path(published["path"]).read_text())
    result = refresh.run_refresh(
        tmp_path, REPO, YOU, apply=True, add=[], discovery=False, now=NOW
    )
    assert result["ack_results"] == []
    board.write_text(board.read_text().replace("1. [ ]", "1. [x]"))
    result = refresh.run_refresh(
        tmp_path, REPO, YOU, apply=True, add=[], discovery=False, now=NOW
    )
    assert [r["result"] for r in result["ack_results"]] == ["acked"]


def test_report_replaced_during_ack_is_not_confirmed_on_the_next_refresh(
    tmp_path, gh, monkeypatch
):
    published = _checked_review_setup(tmp_path, gh)
    acknowledge = sync.review_report.acknowledge

    def replace_report_before_ack(*args, **kwargs):
        report.publish(
            tmp_path, url(1), REPO, "PR 1", "## A\nNew unread report\n", HEAD,
            "NEEDS_CHANGES", owner="others",
        )  # fmt: skip
        return acknowledge(*args, **kwargs)

    monkeypatch.setattr(sync.review_report, "acknowledge", replace_report_before_ack)
    result = refresh.run_refresh(
        tmp_path, REPO, YOU, apply=True, add=[], discovery=False, now=NOW
    )
    assert [r["result"] for r in result["ack_results"]] == ["report_changed"]
    assert any("重新勾選" in warning for warning in result["warnings"])
    assert any("1. [ ]" in line and "i/1.md" in line for line in board_lines(tmp_path))
    assert "acknowledged_at" not in report.metadata(Path(published["path"]).read_text())

    monkeypatch.setattr(sync.review_report, "acknowledge", acknowledge)
    result = refresh.run_refresh(
        tmp_path, REPO, YOU, apply=True, add=[], discovery=False, now=NOW
    )
    assert result["ack_results"] == []
    assert "acknowledged_at" not in report.metadata(Path(published["path"]).read_text())


@pytest.mark.parametrize(
    ("message", "result"),
    [("review.md is being updated", "locked"), ("temporary write failure", "error")],
)
def test_failed_ack_keeps_the_old_report_version_for_its_pending_check(
    tmp_path, gh, monkeypatch, message, result
):
    published = _checked_review_setup(tmp_path, gh)
    acknowledge = sync.review_report.acknowledge

    def replace_report_and_fail_ack(*args, **kwargs):
        report.publish(
            tmp_path, url(1), REPO, "PR 1", "## A\nNew unread report\n", HEAD,
            "NEEDS_CHANGES", owner="others",
        )  # fmt: skip
        raise OSError(message)

    monkeypatch.setattr(sync.review_report, "acknowledge", replace_report_and_fail_ack)
    first = refresh.run_refresh(
        tmp_path, REPO, YOU, apply=True, add=[], discovery=False, now=NOW
    )
    assert [r["result"] for r in first["ack_results"]] == [result]
    assert any("1. [x]" in line and "i/1.md" in line for line in board_lines(tmp_path))
    snapshot = json.loads(
        (tmp_path / ".maigo/_internal/board/snapshot.json").read_text()
    )
    assert snapshot["items"][url(1)]["reviewed_at"] == published["reviewed_at"]
    assert "acknowledged_at" not in report.metadata(Path(published["path"]).read_text())

    monkeypatch.setattr(sync.review_report, "acknowledge", acknowledge)
    second = refresh.run_refresh(
        tmp_path, REPO, YOU, apply=True, add=[], discovery=False, now=NOW
    )
    assert [r["result"] for r in second["ack_results"]] == ["report_changed"]
    assert any("1. [ ]" in line and "i/1.md" in line for line in board_lines(tmp_path))
    assert "acknowledged_at" not in report.metadata(Path(published["path"]).read_text())


def test_s5_post_write_failure_has_its_own_exit_reason(
    tmp_path, gh, monkeypatch, capsys
):
    write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1)
    gh.prs[1] = pr_meta(1)

    def broken(*args, **kwargs):
        raise OSError("snapshot disk full")

    monkeypatch.setattr(sync, "write_snapshot", broken)
    assert run_cli(tmp_path, "--apply", "--no-discovery", "--json") == 3
    out = json.loads(capsys.readouterr().out)
    assert out["exit_reason"] == "post_write_failed"
    assert "PR 1" in (tmp_path / ".maigo/board.md").read_text()  # board is already new


def test_s6_stray_detail_without_judgment_rejects_before_ack(tmp_path, gh):
    published = _checked_review_setup(tmp_path, gh)
    gh.prs[9] = pr_meta(9)
    (tmp_path / ".maigo/i/9.md").write_text("# x\n\n- 連結：" + url(9) + "\n")
    before = tree_hash(tmp_path)
    assert run_cli(tmp_path, "--apply", "--no-discovery", "--add", "9") == 1
    assert tree_hash(tmp_path) == before
    assert "acknowledged_at" not in report.metadata(Path(published["path"]).read_text())


def test_s7_cas2_catches_a_board_change_at_apply_entry(tmp_path, gh, monkeypatch):
    write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1)
    gh.prs[1] = pr_meta(1)
    board = tmp_path / ".maigo" / "board.md"
    _hook_apply(
        monkeypatch, lambda: board.write_text(board.read_text() + "<!-- x -->\n")
    )
    detail_before = (tmp_path / ".maigo/i/1.md").read_bytes()
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 2
    assert board.read_text().endswith("<!-- x -->\n")
    assert (tmp_path / ".maigo/i/1.md").read_bytes() == detail_before


def test_s7_cas2_catches_a_detail_file_created_by_someone_else(
    tmp_path, gh, monkeypatch
):
    write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1)
    gh.prs[1] = pr_meta(1)
    gh.prs[9] = pr_meta(9)
    _hook_apply(monkeypatch, lambda: put_detail(tmp_path, 9, judgment="別人寫的"))
    assert run_cli(tmp_path, "--apply", "--no-discovery", "--add", "9") == 2
    assert "別人寫的" in (tmp_path / ".maigo/i/9.md").read_text()
    assert "i/9.md" not in (tmp_path / ".maigo/board.md").read_text()


def test_s7_cas2_catches_a_change_to_a_detail_file_about_to_be_deleted(
    tmp_path, gh, monkeypatch
):
    old = (NOW - timedelta(days=9)).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_board(
        tmp_path,
        board_text(
            focus=[row(1)], done=[row(2, icon="👀", status="merged", numbered=False)]
        ),
    )
    put_detail(tmp_path, 1)
    put_detail(tmp_path, 2, status="merged")
    gh.prs[1] = pr_meta(1)
    gh.prs[2] = pr_meta(2, state="MERGED", mergedAt=old)
    target = tmp_path / ".maigo/i/2.md"
    _hook_apply(monkeypatch, lambda: target.write_text(target.read_text() + "新筆記\n"))
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 2
    assert target.exists() and "新筆記" in target.read_text()


def test_s8_prune_never_removes_the_current_backup(tmp_path):
    root = tmp_path / "backup"
    names = ["20260101T000000Z"] + [f"20260101T000000Z-{i}" for i in range(2, 13)]
    for index, name in enumerate(names):
        (root / name).mkdir(parents=True)
        os.utime(root / name, (1000 + index, 1000 + index))
    current = root / names[0]  # the oldest by mtime, e.g. after a clock rollback
    refresh._prune_backups(root, current)
    remaining = {p.name for p in root.iterdir()}
    assert current.name in remaining
    assert len(remaining) == refresh.BACKUP_KEEP + 1 and names[1] not in remaining


def test_s9_missing_gh_binary_is_a_clean_rejection(tmp_path, gh, monkeypatch, capsys):
    write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1)

    def no_gh(cmd):
        raise FileNotFoundError("gh")

    monkeypatch.setattr(sync, "run", no_gh)
    assert run_cli(tmp_path, "--apply", you="") == 1
    assert "Traceback" not in capsys.readouterr().err


def test_s11_script_mode_import_works():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["python3", str(root / "scripts" / "board_sync.py"), "refresh", "--help"],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert result.returncode == 0 and "--apply" in result.stdout


def test_s13_detail_path_outside_i_dir_is_rejected(tmp_path, gh):
    write_board(
        tmp_path, board_text(focus=["1. [ ] 👀 待 review @carol i/../x.md — T"])
    )
    (tmp_path / ".maigo" / "i").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".maigo" / "x.md").write_text(
        "連結\n- 連結：" + url(1) + "\n\n## 判斷\n"
    )
    gh.prs[1] = pr_meta(1)
    before = tree_hash(tmp_path)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 1
    assert tree_hash(tmp_path) == before


def test_s14_locked_ack_keeps_the_check_and_warns_then_acks_on_retry(
    tmp_path, gh, monkeypatch
):
    write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1)
    gh.prs[1] = pr_meta(1)
    published = report.publish(
        tmp_path, url(1), REPO, "PR 1", "## A\nx\n", HEAD, "APPROVE", owner="others"
    )
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    board = tmp_path / ".maigo" / "board.md"
    board.write_text(board.read_text().replace("1. [ ]", "1. [x]"))
    original = sync.review_report.acknowledge

    def locked(*args, **kwargs):
        raise OSError("review.md is being updated")

    monkeypatch.setattr(sync.review_report, "acknowledge", locked)
    summary = refresh.run_refresh(
        tmp_path, REPO, YOU, apply=True, add=[], discovery=False, now=NOW
    )
    assert [r["result"] for r in summary["ack_results"]] == ["locked"]
    assert summary["warnings"]
    assert any("1. [x]" in ln and "i/1.md" in ln for ln in board_lines(tmp_path))
    monkeypatch.setattr(sync.review_report, "acknowledge", original)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    meta = report.metadata(Path(published["path"]).read_text())
    assert "acknowledged_at" in meta


def test_s6_stray_detail_without_judgment_rejects_even_when_its_fetch_fails(
    tmp_path, gh
):
    published = _checked_review_setup(tmp_path, gh)
    gh.prs[9] = pr_meta(9)
    gh.fail = {9}
    (tmp_path / ".maigo/i/9.md").write_text("# x\n\n- 連結：" + url(9) + "\n")
    before = tree_hash(tmp_path)
    assert run_cli(tmp_path, "--apply", "--no-discovery", "--add", url(9)) == 1
    assert tree_hash(tmp_path) == before
    assert "acknowledged_at" not in report.metadata(Path(published["path"]).read_text())


def _git(cwd: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, check=True, env=env
    )


def _repo_with_worktree(tmp_path: Path) -> tuple[Path, Path]:
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-q")
    _git(main, "commit", "-q", "--allow-empty", "-m", "init")
    linked = tmp_path / "linked"
    _git(main, "worktree", "add", "-q", "-b", "wt", str(linked))
    return main, linked


def test_find_maigo_root_counts_worktrees_sharing_one_board_once(tmp_path):
    main, linked = _repo_with_worktree(tmp_path)
    central = tmp_path / "central"
    central.mkdir()
    (central / "board.md").write_text("board", encoding="utf-8")
    for worktree in (main, linked):
        (worktree / ".maigo").symlink_to(central, target_is_directory=True)

    assert refresh.find_maigo_root(main) == main.resolve()


def test_find_maigo_root_still_rejects_distinct_boards(tmp_path):
    main, linked = _repo_with_worktree(tmp_path)
    for worktree in (main, linked):
        (worktree / ".maigo").mkdir()
        (worktree / ".maigo" / "board.md").write_text("board", encoding="utf-8")

    with pytest.raises(refresh.RefreshError, match="多份 board.md"):
        refresh.find_maigo_root(main)


def test_apply_refuses_maigo_symlink_outside_state_root(tmp_path, capsys):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "board.md").write_text("board", encoding="utf-8")
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".maigo").symlink_to(outside, target_is_directory=True)
    before = tree_hash(outside)

    assert run_cli(root, "--apply") == 1

    assert tree_hash(outside) == before
    assert "outside the maigo state root" in capsys.readouterr().err


# --- refreshing from the central state directory ------------------------------------


@pytest.fixture
def state_board(tmp_path, monkeypatch, gh):
    """A board that lives only in `<state>/o/r`; the checkout `ck` is not a worktree."""
    state = tmp_path / "state"
    repo_dir = state / "o" / "r"
    repo_dir.mkdir(parents=True)
    monkeypatch.setenv("MAIGO_STATE_HOME", str(state))
    scratch = tmp_path / "tmp"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    ck = tmp_path / "ck"
    ck.mkdir()
    (ck / ".maigo").symlink_to(repo_dir, target_is_directory=True)
    write_board(ck, board_text(focus=[row(1)]))
    put_detail(ck, 1)
    gh.prs[1] = pr_meta(1)
    return repo_dir


def test_refresh_from_state_dir_without_flags(
    state_board, tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(state_board)
    assert sync.main(["refresh", "--no-discovery", "--you", YOU]) == 0
    assert "board.md (refreshed)" in capsys.readouterr().out
    assert list((tmp_path / "tmp").iterdir()) == []


def test_refresh_from_state_subdir_resolves_board_dir(state_board, monkeypatch):
    monkeypatch.chdir(state_board / "i")
    assert sync.main(["refresh", "--no-discovery", "--you", YOU]) == 0


def test_explicit_maigo_root_state_dir(state_board, tmp_path):
    assert run_cli(state_board, "--no-discovery") == 0
    assert list((tmp_path / "tmp").iterdir()) == []


def test_apply_from_state_dir_writes_state_and_cleans_temp(
    state_board, tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(state_board)
    before = (state_board / "board.md").read_text()
    code = sync.main(["refresh", "--apply", "--no-discovery", "--json", "--you", YOU])
    out = capsys.readouterr().out
    assert code == 0
    assert (state_board / "board.md").read_text() != before
    assert (state_board / "_internal" / "board" / "snapshot.json").exists()
    backup = json.loads(out)["backup"]
    assert backup is not None
    assert backup.startswith(os.path.realpath(state_board))
    assert Path(backup).exists()
    assert not (state_board / "_internal" / "board" / ".refresh-write-lock").exists()
    assert list((tmp_path / "tmp").iterdir()) == []
    state = tmp_path / "state"
    assert [p for p in state.rglob("*") if p.is_symlink()] == []


def test_apply_from_state_dir_respects_lock_held_by_checkout_entry(
    state_board, tmp_path, monkeypatch, capsys
):
    (state_board / "_internal" / "board" / ".refresh-write-lock").mkdir(parents=True)
    monkeypatch.chdir(state_board)
    before = tree_hash(state_board)
    assert sync.main(["refresh", "--apply", "--no-discovery", "--you", YOU]) == 2
    err = capsys.readouterr().err
    assert os.path.realpath(state_board) in err
    assert str(tmp_path / "tmp") not in err
    assert os.path.realpath(tmp_path / "tmp") not in err
    assert tree_hash(state_board) == before
    assert list((tmp_path / "tmp").iterdir()) == []


def test_state_dir_post_write_failure_reports_real_backup_path(
    state_board, tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(state_board)

    def broken(*args, **kwargs):
        raise OSError("snapshot disk full")

    monkeypatch.setattr(sync, "write_snapshot", broken)
    code = sync.main(["refresh", "--apply", "--no-discovery", "--json", "--you", YOU])
    out = json.loads(capsys.readouterr().out)
    assert code == 3
    assert out["exit_reason"] == "post_write_failed"
    assert out["backup"] is not None
    assert out["backup"].startswith(os.path.realpath(state_board))
    assert Path(out["backup"]).exists()
    assert list((tmp_path / "tmp").iterdir()) == []


def test_state_dir_failure_midway_cleans_temp(
    state_board, tmp_path, gh, monkeypatch, capsys
):
    monkeypatch.chdir(state_board)
    gh.prs[9] = pr_meta(9)
    gh.fail = {9}
    (state_board / "i" / "9.md").write_text("# x\n\n- 連結：" + url(9) + "\n")
    before = tree_hash(state_board)
    code = sync.main(
        ["refresh", "--apply", "--no-discovery", "--you", YOU, "--add", url(9)]
    )
    assert code == 1
    assert "## 判斷" in capsys.readouterr().err
    assert tree_hash(state_board) == before
    assert list((tmp_path / "tmp").iterdir()) == []

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(refresh, "run_refresh", boom)
    with pytest.raises(RuntimeError):
        sync.main(["refresh", "--no-discovery", "--you", YOU])
    assert list((tmp_path / "tmp").iterdir()) == []


def test_state_root_or_backup_dir_is_not_a_board_dir(state_board, tmp_path):
    state = tmp_path / "state"
    backup = state / "_migration-backup" / "x"
    backup.mkdir(parents=True)
    (backup / "board.md").write_text("board", encoding="utf-8")
    (state / "o" / "r2").mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "board.md").write_text("board", encoding="utf-8")
    for path in (state, state / "o", backup, outside, state / "o" / "r2"):
        assert refresh.state_board_dir(path) is None
    expected = Path(os.path.realpath(state_board))
    assert refresh.state_board_dir(state_board / "i") == expected
    assert refresh.state_board_dir(state_board) == expected


def test_state_dir_without_header_repo_requires_repo_flag(
    state_board, tmp_path, gh, monkeypatch, capsys
):
    (state_board / "board.md").write_text("# Work Board\n", encoding="utf-8")
    assert sync.parse_header((state_board / "board.md").read_text())["repo"] is None
    monkeypatch.chdir(state_board)
    assert sync.main(["refresh", "--no-discovery", "--you", YOU]) == 1
    assert "請指定 --repo" in capsys.readouterr().err
    assert not any(call[:3] == ["gh", "repo", "view"] for call in gh.calls)
    assert list((tmp_path / "tmp").iterdir()) == []


# --- review verdict replaces the action on 👀 rows ---------------------------------


def _after_report(tmp_path, hours: int) -> str:
    """A timestamp `hours` after the published report's `reviewed_at`."""
    text = (tmp_path / ".maigo/review/1/review.md").read_text()
    reviewed = datetime.fromisoformat(report.metadata(text)["reviewed_at"])
    return (reviewed + timedelta(hours=hours)).isoformat()


def _verdict_board(tmp_path, gh, line, *, verdict="NEEDS_CHANGES", **over):
    write_board(tmp_path, board_text(focus=[line]))
    put_detail(tmp_path, 1, status="待送出", judgment="手寫判斷", notes="手寫筆記")
    gh.prs[1] = pr_meta(1, additions=68, deletions=1, **over)
    if verdict:
        report.publish(
            tmp_path, url(1), REPO, "PR 1", "## A\nx\n", HEAD, verdict, owner="others"
        )


def _line_1(tmp_path):
    return [ln for ln in board_lines(tmp_path) if "i/1.md" in ln][0]


def test_unposted_row_shows_verdict_and_old_duplicate_note_retires(tmp_path, gh):
    legacy = (
        "1. [ ] 👀 待送出（本地 NEEDS_CHANGES） @carol →送出 +68/-1 i/1.md — Title 1"
    )
    _verdict_board(tmp_path, gh, legacy)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert _line_1(tmp_path) == (
        "1. [ ] 👀 待送出 @carol NEEDS_CHANGES +68/-1 — PR 1 i/1.md"
    )
    assert sync.parse_board((tmp_path / ".maigo/board.md").read_text())["errors"] == []
    detail = (tmp_path / ".maigo/i/1.md").read_text()
    facts, _, rest = detail.partition("## 判斷")
    assert "- 本地 review 結果：NEEDS_CHANGES\n- 最後 review：" in facts
    assert "手寫判斷" in rest and "手寫筆記" in rest
    again = board_lines(tmp_path)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert board_lines(tmp_path) == again  # fixed point


@pytest.mark.parametrize(
    ("note", "expected"),
    [
        ("（本地 NEEDS_CHANGES；等作者回覆）", "（等作者回覆）"),
        ("（本地 BLOCKED）", "（本地 BLOCKED）"),
        ("（本地 NEEDS_CHANGES，must-fix 5）", "（本地 NEEDS_CHANGES，must-fix 5）"),
        ("（本地 BLOCKED；本地 NEEDS_CHANGES）", "（本地 BLOCKED）"),
        ("（NEEDS_CHANGES）", "（NEEDS_CHANGES）"),
        ("（本地 NEEDS_CHANGES）", None),
        ("（本地 NEEDS_CHANGES；）", None),
        ("（；本地 NEEDS_CHANGES）", None),
    ],
)
def test_strip_duplicate_verdict_note(note, expected):
    assert refresh.strip_duplicate_verdict_note(note, "NEEDS_CHANGES") == expected


def test_hand_written_note_survives_verdict_row_refresh(tmp_path, gh):
    legacy = "1. [ ] 👀 待送出（手寫 x） @carol →送出 +68/-1 i/1.md — Title 1"
    _verdict_board(tmp_path, gh, legacy)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert "（手寫 x） @carol NEEDS_CHANGES +68/-1" in _line_1(tmp_path)


def test_ball_back_row_says_last_verdict(tmp_path, gh):
    legacy = "1. [ ] 👀 ↩︎ 回你的球 @carol →重審 +68/-1 i/1.md — Title 1"
    _verdict_board(tmp_path, gh, legacy)
    gh.prs[1]["reviews"] = [
        {"author": {"login": YOU}, "submittedAt": _after_report(tmp_path, 1)}
    ]
    gh.prs[1]["comments"] = [
        {"author": {"login": "carol"}, "createdAt": _after_report(tmp_path, 2)}
    ]
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    line = _line_1(tmp_path)
    assert "回你的球" in line and " 上次 NEEDS_CHANGES " in line and "→" not in line


def test_review_row_without_report_shows_neither_result_nor_action(tmp_path, gh):
    legacy = "1. [ ] 👀 待 review @carol →審 +68/-1 i/1.md — Title 1"
    _verdict_board(tmp_path, gh, legacy, verdict=None)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert _line_1(tmp_path) == "1. [ ] 👀 待 review @carol +68/-1 — PR 1 i/1.md"
    assert "本地 review 結果" not in (tmp_path / ".maigo/i/1.md").read_text()


def test_own_pr_new_comment_shows_approval_and_ci_red_keeps_action(tmp_path, gh):
    write_board(
        tmp_path,
        board_text(
            focus=[
                row(1, icon="🔀", status="有新 comment", author="me"),
                row(2, icon="🔀", status="CI 紅", author="me"),
            ]
        ),
    )
    for n in (1, 2):
        put_detail(tmp_path, n)
    gh.prs[1] = pr_meta(
        1, author="me", reviewDecision="APPROVED",
        comments=[{"author": {"login": "carol"}, "createdAt": "2026-09-30T05:00:00Z"}],
    )  # fmt: skip
    gh.prs[2] = pr_meta(2, author="me", statusCheckRollup=[{"conclusion": "FAILURE"}])
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    first = [ln for ln in board_lines(tmp_path) if "i/1.md" in ln][0]
    second = [ln for ln in board_lines(tmp_path) if "i/2.md" in ln][0]
    assert "已核准" in first and "→" not in first
    assert "→修CI" in second


def test_excluded_legacy_action_line_keeps_its_fields_but_moves_the_path_last():
    # was "kept byte for byte"; the path-last grammar rewrites the old shape once
    line = "1. [ ] 👀 待送出 @a →送出 +68/-1 i/2120.md — t"
    parsed = sync.parse_board(_as_board(line))["lines"][0]
    assert _render(parsed) == "1. [ ] 👀 待送出 @a →送出 +68/-1 — t i/2120.md"


# --- path-last grammar: `… — [<title> ]<detail>` -----------------------------


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        (
            dict(
                number=1,
                type="👀",
                status="待送出",
                author="marcusalstrom",
                badges=["💤"],
                result="NEEDS_CHANGES",
                size="+68/-1",
                detail="i/1261.md",
                title="fix(bump)!: only add version files",
            ),
            "1. [ ] 👀 待送出 @marcusalstrom 💤 NEEDS_CHANGES +68/-1 — fix(bump)!: only add version files i/1261.md",
        ),
        (
            dict(
                number=2,
                checked=True,
                type="👀",
                status="↩︎ 回你的球",
                author="contributor",
                result="上次 APPROVE_WITH_NITS",
                size="+1.2k/-340",
                detail="i/9301.md",
                title="Avoid duplicate GitHub requests",
            ),
            "2. [x] 👀 ↩︎ 回你的球 @contributor 上次 APPROVE_WITH_NITS +1.2k/-340 — Avoid duplicate GitHub requests i/9301.md",
        ),
        (
            dict(
                number=3,
                type="🔀",
                status="有新 comment",
                author="Lee-W",
                result="已核准",
                size="+12/-3",
                detail="i/9202.md",
                title="Document plugin installation flow",
            ),
            "3. [ ] 🔀 有新 comment @Lee-W 已核准 +12/-3 — Document plugin installation flow i/9202.md",
        ),
    ],
)
def test_render_line_puts_the_path_last_for_the_three_documented_examples(
    fields, expected
):
    assert refresh.render_line(**_fields(**fields)) == expected


@pytest.mark.parametrize(
    "title",
    [
        "",
        "標題。",
        "標題！？",
        "done 🎉",
        "bump i/9.md",
        "a — b",
        "多\n行\t標題  x",
        "　全形空白　",
    ],
)
@pytest.mark.parametrize(
    "extra",
    [
        dict(),
        dict(number=None, status="等 review", type="🔀"),
        dict(ended="11-14", number=None, checked=True, status="merged", type="🔀"),
        dict(action="審", size="+1/-1"),
        dict(result="NEEDS_CHANGES", size="+1/-1", badges=["🧠", "💤"]),
    ],
)
def test_render_line_invariants_path_is_last_token_after_one_ascii_space(title, extra):
    detail = "i/1261.md"
    line = refresh.render_line(**_fields(detail=detail, title=title, **extra))
    assert line.endswith(detail)
    assert line[-len(detail) - 1] == " " and line[-len(detail) - 2] != " "
    assert line == line.rstrip() and "\n" not in line
    parsed = sync.parse_board(_as_board(line))
    assert parsed["errors"] == [] and parsed["lines"][0]["detail"] == detail
    assert parsed["lines"][0]["title"] == " ".join(title.split())


def test_render_line_empty_title_leaves_just_the_path_after_the_dash():
    assert refresh.render_line(**_fields(title="")).endswith("@octocat — i/1.md")


def test_render_line_over_budget_row_still_ends_with_the_path():
    line = refresh.render_line(
        **_fields(
            note="（手寫的很長很長很長很長很長很長很長很長很長很長很長很長的旁註）",
            action="審",
            size="+1/-1",
        )
    )
    assert line.endswith(" — t i/1.md")


def test_old_shape_board_refreshes_to_new_shape_and_is_a_fixed_point(tmp_path, gh):
    write_board(
        tmp_path,
        board_text(
            focus=[
                row(1, extra="（手寫旁註）", author="carol"),
                row(2, status="↩︎ 回你的球", author="carol"),
            ],
            wait=[row(3, icon="🔀", status="等 review", author="me", numbered=False)],
        ),
    )
    for n in (1, 2, 3):
        put_detail(tmp_path, n)
    gh.prs[1] = pr_meta(1, author="carol")
    gh.prs[2] = pr_meta(2, author="carol")
    gh.prs[3] = pr_meta(3, author="me")
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    first = (tmp_path / ".maigo/board.md").read_text()
    item_lines = [ln for ln in first.splitlines() if "[ ]" in ln or "[x]" in ln]
    assert len(item_lines) == 3
    assert all(re.search(r" — PR \d i/\d\.md$", ln) for ln in item_lines)
    assert any("（手寫旁註）" in ln for ln in item_lines)
    assert sync.parse_board(first)["errors"] == []
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert (tmp_path / ".maigo/board.md").read_text() == first


def test_detail_next_action_line_carries_the_file_relative_draft_hint():
    hint = "尚無草稿：先起草 `../review/1/draft.md`（`/maigo:review` §4.5 裁決 gate）"
    facts = refresh.render_detail_facts(
        type="👀", status="待送出", title="t", url="https://github.com/o/r/pull/1",
        additions=1, deletions=1, author="a", next_action=hint, number=1,
        last_reviewed_at=None, review_time_source=None, acknowledged_at=None,
    )  # fmt: skip
    assert f"- 下一步：`{hint}`" in facts.splitlines()
    assert ".maigo/" not in facts


def test_render_line_puts_result_before_size_and_drops_size_first_when_over_budget():
    line = refresh.render_line(
        **_fields(status="待送出", author="a", result="NEEDS_CHANGES", size="+68/-1")
    )
    assert line == "1. [ ] 👀 待送出 @a NEEDS_CHANGES +68/-1 — t i/1.md"
    wide = _fields(
        status="待送出", author="a" * 22, badges=["💤"], result="上次 APPROVE_WITH_NITS",
        size="+1.2k/-340",
    )  # fmt: skip
    cut = refresh.render_line(**wide)
    assert "上次 APPROVE_WITH_NITS" in cut and "+1.2k/-340" not in cut
    assert board_state_width(cut.split(" — ")[0]) <= refresh.LINE_BUDGET + 12
    short = refresh.render_line(**{**wide, "author": "a"})
    assert "+1.2k/-340" in short


@pytest.mark.parametrize("resolved", [False, True])
def test_refresh_resolved_inline_review_stops_needing_a_reply(tmp_path, gh, resolved):
    write_board(
        tmp_path,
        board_text(focus=(row(1, icon="🔀", status="有新 comment", author=YOU),)),
    )
    detail = put_detail(
        tmp_path, 1, icon="🔀", judgment="Keep judgment", notes="Keep notes"
    )
    gh.prs[1] = pr_meta(
        1,
        author=YOU,
        reviews=[
            {
                "id": "R1",
                "state": "COMMENTED",
                "body": "",
                "author": {"login": "reviewer"},
                "submittedAt": "2026-09-20T00:00:00Z",
            }
        ],
        reviewThreads=[
            {
                "id": "T1",
                "isResolved": resolved,
                "comments": [
                    {
                        "author": {"login": "reviewer"},
                        "createdAt": "2026-09-20T00:00:00Z",
                        "pullRequestReview": {"id": "R1"},
                    }
                ],
            }
        ],
    )
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    text = detail.read_text()
    assert ("# 🔀 等 review" if resolved else "# 🔀 有新 comment") in text
    assert (
        f"- Review 討論：未解決 {int(not resolved)} ｜ 已解決 {int(resolved)}" in text
    )
    assert "Keep judgment" in text
    assert "Keep notes" in text


def test_review_thread_fetch_follows_both_connections(monkeypatch):
    calls = []
    comment = {"author": {"login": "reviewer"}, "createdAt": RECENT}
    thread = {
        "id": "T1",
        "isResolved": False,
        "comments": {
            "nodes": [comment],
            "commentPage": {"hasNextPage": True, "endCursor": "C1"},
        },
    }

    def run(cmd):
        calls.append(cmd)
        assert "--paginate" in cmd and "--slurp" in cmd
        if "id=T1" in cmd:
            assert "endCursor=C1" in cmd
            return json.dumps([{"data": {"node": {"comments": {"nodes": [comment]}}}}])
        return json.dumps(
            [
                {
                    "data": {
                        "repository": {
                            "pullRequest": {"reviewThreads": {"nodes": nodes}}
                        }
                    }
                }
                for nodes in (
                    [thread],
                    [
                        {
                            **thread,
                            "id": "T2",
                            "comments": {
                                "nodes": [],
                                "commentPage": {"hasNextPage": False},
                            },
                        }
                    ],
                )
            ]
        )

    monkeypatch.setattr(sync, "run", run)
    assert refresh.fetch_review_threads("o", "r", "1") == [
        {"id": "T1", "isResolved": False, "comments": [comment, comment]},
        {"id": "T2", "isResolved": False, "comments": []},
    ]
    assert len(calls) == 2


@pytest.mark.parametrize(
    "response",
    [
        pytest.param([], id="missing-pages"),
        pytest.param([{"errors": [{"message": "forbidden"}]}], id="graphql-error"),
        pytest.param([{"data": {"repository": None}}], id="missing-repository"),
    ],
)
def test_thread_fetch_failure_keeps_the_existing_detail(
    tmp_path, gh, monkeypatch, response
):
    write_board(tmp_path, board_text(focus=(row(1),)))
    detail = put_detail(
        tmp_path, 1, judgment="Preserve judgment", notes="Preserve notes"
    )
    before = detail.read_bytes()
    gh.prs[1] = pr_meta(1)

    def run(cmd):
        if cmd[:3] == ["gh", "api", "graphql"]:
            return json.dumps(response)
        return gh(cmd)

    monkeypatch.setattr(sync, "run", run)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert detail.read_bytes() == before


# --- own PR: why / what ------------------------------------------------------------

PR_URL = "https://github.com/o/r/pull/40"


def own_facts(type="🔀", **kw) -> str:
    """`render_detail_facts` with boilerplate filled; also proves the result splits."""
    args = dict(
        type=type, status="等 review", title="t", url=PR_URL, additions=3,
        deletions=1, author="me", next_action=None, number=40,
        last_reviewed_at=None, review_time_source=None, acknowledged_at=None,
    )  # fmt: skip
    args.update(kw)
    facts = refresh.render_detail_facts(**args)
    assert refresh.split_detail(facts + refresh.NEW_PRESERVED)[0] == facts
    assert not any(ln.startswith("## ") for ln in facts.splitlines())
    return facts


def write_note(root: Path, rel: str, text: str) -> Path:
    path = root / ".maigo" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


SUMMARY = (
    "# T\n\n## 為什麼做\n\n使用者想先知道來龍去脈。\n\n```text\n需求 → 缺口\n```\n\n"
    "## 做了什麼\n\n- 多出摘要\n- 帶出 issue\n\n```text\nA → B\n```\n\n## 怎麼做\n\n其他\n"
)


class TestOwnPrWhyAndWhat:
    def test_pr_fields_include_body_and_closing_issues(self):
        fields = refresh.PR_FIELDS.split(",")
        assert "body" in fields
        assert "closingIssuesReferences" in fields
        assert "headRefName" in fields

    def test_why_and_what_become_nested_single_lines(self):
        body = "## Why\n\nBoard 只顯示 title，\n看不出為什麼。\n\n## What\n\n- 新增欄位\n- 帶出 issue\n"
        facts = own_facts(pr_body=body)
        lines = facts.splitlines()
        i = lines.index("- 對外（PR description）：")
        assert lines[i + 1] == "  - 為什麼：Board 只顯示 title， 看不出為什麼。"
        assert lines[i + 2] == "  - 做了什麼：新增欄位；帶出 issue"
        assert "說明：" not in facts
        assert (
            lines.index(f"- 連結：<{PR_URL}>")
            < i
            < lines.index("- 規模：Δ+3/-1 ｜ 作者：me")
        )

    @pytest.mark.parametrize(
        "why", ["### Why", "## WHY", "## 為什麼", "## Why:", "## Motivation"]
    )
    def test_heading_variants_are_found(self, why):
        facts = own_facts(pr_body=f"{why}\n\nbecause\n")
        assert "  - 為什麼：because" in facts.splitlines()

    def test_only_what(self):
        facts = own_facts(pr_body="## What\n\ndone it\n")
        assert "  - 做了什麼：done it" in facts.splitlines()
        assert "為什麼" not in facts

    def test_no_headings_falls_back_to_first_paragraph(self):
        body = (
            "| a | b |\n|---|---|\n<div>x</div>\n![img](u)\n\n"
            "First para\nsecond line\n\nSecond para\n"
        )
        facts = own_facts(pr_body=body)
        lines = facts.splitlines()
        assert "  - 說明：First para second line" in lines
        assert "為什麼" not in facts and "做了什麼" not in facts
        assert "|" not in facts and "div" not in facts and "img" not in facts

    @pytest.mark.parametrize(
        "body", [None, "", "   \n\n", "<!-- only a comment\nspanning lines -->"]
    )
    def test_empty_body_omits_the_group(self, body):
        facts = own_facts(pr_body=body)
        assert "對外" not in facts

    def test_heading_like_lines_and_fenced_headings(self):
        body = (
            "## Why\n\nreason\n\n## 判斷\n\ntext\n\n```\n## What\nfenced\n```\n\n"
            "## 其他\n\nx\n"
        )
        facts = own_facts(pr_body=body)
        assert "  - 為什麼：reason" in facts.splitlines()
        assert "fenced" not in facts

    def test_one_line_handles_carriage_returns_and_inline_html(self):
        facts = own_facts(
            pr_body="## Why\r\n\r\nline <b>bold</b> a\r\nb <https://x.y/z>\r\n"
        )
        assert "  - 為什麼：line bold a b <https://x.y/z>" in facts.splitlines()

    def test_length_cap(self):
        facts = own_facts(
            pr_body="## Why\n\n" + "字" * 500 + "\n\n## What\n\n" + "x" * 200
        )
        why = next(ln for ln in facts.splitlines() if "為什麼：" in ln)
        value = why.split("：", 1)[1]
        assert len(value) == 200 and value.endswith("…")
        what = next(ln for ln in facts.splitlines() if "做了什麼：" in ln)
        assert what.split("：", 1)[1] == "x" * 200

    def test_inline_angle_brackets_are_removed_as_html_today(self):
        # Known limitation (format-spec §1a): generics like `Vec<T>` lose the tag.
        assert refresh.extract_why_what("Vec<T> fix") == (None, None, "Vec fix")

    def test_lone_surrogates_from_json_escapes_cannot_break_the_write(self, tmp_path):
        body = json.loads(
            '"## Why\\n\\nbad \\ud800 reason\\n\\n## What\\n\\n- x \\udfff"'
        )
        facts = own_facts(pr_body=body, closing_issues=[ref(7, "x\ud800", "y")])
        facts.encode("utf-8")
        assert "  - 為什麼：bad ? reason" in facts.splitlines()

    def test_summary_file_with_encoded_surrogate_counts_as_absent(self, tmp_path):
        # Local files are read as strict UTF-8, so a surrogate can only come from JSON.
        path = write_note(tmp_path, "pr/40/summary.md", "")
        path.write_bytes(
            "## 為什麼做\n\nbad \ud800 x\n".encode("utf-8", "surrogatepass")
        )
        assert refresh.find_self_notes(tmp_path / ".maigo", "40", None) is None

    def test_subheading_content_is_kept_in_section(self):
        facts = own_facts(pr_body="## What\n\n### Part\n\ninner\n\n## Next\n\nouter\n")
        assert "  - 做了什麼：inner" in facts.splitlines()

    def test_other_types_are_unchanged_by_the_new_arguments(self):
        notes = refresh.SelfNotes("pr/40/summary.md", "summary", "w", "x")
        extra = dict(
            pr_body="## Why\n\nz\n", self_notes=notes,
            closing_issues=[{"number": 1}],
        )  # fmt: skip
        for kind in ("👀", "🐛"):
            assert own_facts(type=kind, **extra) == own_facts(type=kind)

    def test_own_pr_without_new_arguments_has_no_new_fields(self):
        facts = own_facts()
        assert "對外" not in facts and "自用" not in facts and "關聯" not in facts

    def test_group_order(self):
        notes = refresh.SelfNotes("pr/40/summary.md", "summary", "w", None)
        facts = own_facts(
            pr_body="## Why\n\nz\n", self_notes=notes, closing_issues=[{"number": 1}]
        )
        lines = facts.splitlines()
        marks = [
            "- 對外（PR description）：",
            "- 自用（`../pr/40/summary.md`）：",
            "- 關聯 issue：#1",
        ]
        assert [lines.index(m) for m in marks] == sorted(lines.index(m) for m in marks)


def ref(number, owner="o", name="r"):
    """A `closingIssuesReferences` item as `gh pr view --json` returns it."""
    return {
        "id": f"I_{number}",
        "number": number,
        "repository": {
            "id": f"R_{name}",
            "name": name,
            "owner": {"id": f"O_{owner}", "login": owner},
        },
        "url": f"https://github.com/{owner}/{name}/issues/{number}",
    }


class TestClosingIssues:
    def test_same_and_cross_repo_keep_order(self):
        refs = [ref(12), ref(7, "x", "y"), ref(3)]
        assert refresh.format_closing_issues(refs, PR_URL) == "#12、x/y#7、#3"

    def test_case_insensitive_same_repo(self):
        assert refresh.format_closing_issues([ref(1, "O", "R")], PR_URL) == "#1"

    def test_duplicates_collapse(self):
        refs = [ref(12), ref(12), ref(12, "x", "y"), ref(12, "X", "Y")]
        assert refresh.format_closing_issues(refs, PR_URL) == "#12、x/y#12"

    def test_more_than_five(self):
        out = refresh.format_closing_issues([ref(n) for n in range(1, 8)], PR_URL)
        assert out == "#1、#2、#3、#4、#5…等 7 項"

    def test_missing_repository_means_same_repo(self):
        assert refresh.format_closing_issues([{"number": 4}], PR_URL) == "#4"

    @pytest.mark.parametrize(
        "refs", [None, [], [{"repository": {}}], [{"number": None}], "x"]
    )
    def test_nothing_to_show(self, refs):
        assert refresh.format_closing_issues(refs, PR_URL) is None


class TestSelfNotes:
    def test_pr_dir_summary_is_found(self, tmp_path):
        write_note(tmp_path, "pr/40/summary.md", SUMMARY)
        notes = refresh.find_self_notes(tmp_path / ".maigo", "40", "feat/x")
        assert notes == refresh.SelfNotes(
            "pr/40/summary.md", "summary",
            "使用者想先知道來龍去脈。", "多出摘要；帶出 issue",
        )  # fmt: skip
        facts = own_facts(self_notes=notes)
        lines = facts.splitlines()
        i = lines.index("- 自用（`../pr/40/summary.md`）：")
        assert lines[i + 1] == "  - 為什麼：使用者想先知道來龍去脈。"
        assert lines[i + 2] == "  - 做了什麼：多出摘要；帶出 issue"
        assert "需求" not in facts and "A → B" not in facts

    def test_cross_repo_ident(self, tmp_path):
        write_note(tmp_path, "pr/r-40/summary.md", SUMMARY)
        notes = refresh.find_self_notes(tmp_path / ".maigo", "r-40", None)
        assert notes and notes.rel == "pr/r-40/summary.md"

    def test_topic_dir_via_slugified_branch(self, tmp_path):
        write_note(tmp_path, "topic/feat-my-board/summary.md", SUMMARY)
        notes = refresh.find_self_notes(tmp_path / ".maigo", "40", "feat/my-board")
        assert notes and notes.rel == "topic/feat-my-board/summary.md"
        assert "- 自用（`../topic/feat-my-board/summary.md`）：" in own_facts(
            self_notes=notes
        )

    def test_pr_dir_wins_over_topic(self, tmp_path):
        write_note(tmp_path, "pr/40/summary.md", SUMMARY)
        write_note(tmp_path, "topic/feat-x/summary.md", SUMMARY)
        notes = refresh.find_self_notes(tmp_path / ".maigo", "40", "feat/x")
        assert notes and notes.rel == "pr/40/summary.md"

    @pytest.mark.parametrize(
        ("ident", "head"), [("40", None), ("40", "中文"), (None, None), (None, "中文")]
    )
    def test_nothing_found(self, tmp_path, ident, head):
        write_note(tmp_path, "pr/41/summary.md", SUMMARY)
        assert refresh.find_self_notes(tmp_path / ".maigo", ident, head) is None
        assert "自用" not in own_facts(
            self_notes=refresh.find_self_notes(tmp_path / ".maigo", ident, head)
        )

    def test_plan_goal_only_has_why(self, tmp_path):
        write_note(
            tmp_path, "pr/40/plan.md", "# P\n\n## Goal\n\n做 X。\n\n## Steps\n\n1. a\n"
        )
        notes = refresh.find_self_notes(tmp_path / ".maigo", "40", None)
        assert notes == refresh.SelfNotes("pr/40/plan.md", "plan", "做 X。", None)
        lines = own_facts(self_notes=notes).splitlines()
        assert "- 自用（`../pr/40/plan.md` 的 Goal）：" in lines
        assert "  - 為什麼：做 X。" in lines
        assert not any("做了什麼" in ln for ln in lines)

    def test_summary_anywhere_beats_plan(self, tmp_path):
        write_note(tmp_path, "pr/40/plan.md", "## Goal\n\ng\n")
        write_note(tmp_path, "topic/feat-x/summary.md", SUMMARY)
        notes = refresh.find_self_notes(tmp_path / ".maigo", "40", "feat/x")
        assert notes and notes.kind == "summary"

    def test_empty_summary_falls_to_plan(self, tmp_path):
        write_note(tmp_path, "pr/40/summary.md", "# T\n\n## 怎麼做\n\nx\n")
        write_note(tmp_path, "pr/40/plan.md", "## Goal\n\ng\n")
        notes = refresh.find_self_notes(tmp_path / ".maigo", "40", None)
        assert notes and notes.kind == "plan" and notes.why == "g"

    def test_latest_numbered_summary_wins_numerically(self, tmp_path):
        for name in ("summary.md", "summary-2.md", "summary-10.md"):
            write_note(tmp_path, f"pr/40/{name}", f"## 為什麼做\n\n{name}\n")
        notes = refresh.find_self_notes(tmp_path / ".maigo", "40", None)
        assert notes and notes.rel == "pr/40/summary-10.md"

    def test_unnumbered_wins_a_tie_with_dash_one(self, tmp_path):
        write_note(tmp_path, "pr/40/summary-1.md", "## 為什麼做\n\nold\n")
        write_note(tmp_path, "pr/40/summary.md", "## 為什麼做\n\nnew\n")
        notes = refresh.find_self_notes(tmp_path / ".maigo", "40", None)
        assert notes and notes.rel == "pr/40/summary.md"

    def test_odd_content_stays_one_line_per_field(self, tmp_path):
        text = (
            "## 為什麼做\n\n| a | b |\n<div>x</div>\n## 判斷\nreal reason\n"
            "<!-- c -->\n\n## 做了什麼\n\n1. one\n2. two\n"
        )
        write_note(tmp_path, "pr/40/summary.md", text)
        notes = refresh.find_self_notes(tmp_path / ".maigo", "40", None)
        assert notes and notes.what == "one；two"
        own_facts(self_notes=notes)

    def test_unreadable_files_count_as_absent(self, tmp_path):
        path = write_note(tmp_path, "pr/40/summary.md", "x")
        path.write_bytes(b"\xff\xfe\x00bad")
        assert refresh.find_self_notes(tmp_path / ".maigo", "40", None) is None

    def test_missing_directory(self, tmp_path):
        assert refresh.find_self_notes(tmp_path / ".maigo", "40", "feat/x") is None


class TestOwnPrEndToEnd:
    def test_refresh_writes_both_groups_for_own_pr_only(self, tmp_path, gh):
        write_board(
            tmp_path,
            board_text(
                focus=[row(1, author="carol")],
                wait=[row(3, icon="🔀", status="等 review", author="me")],
            ),
        )
        for n in (1, 3):
            put_detail(tmp_path, n)
        write_note(tmp_path, "pr/3/summary.md", SUMMARY)
        body = "## Why\n\nreason\n\n## What\n\n- a\n- b\n"
        closing = [ref(12)]
        gh.prs[1] = pr_meta(
            1, author="carol", body=body, closingIssuesReferences=closing
        )
        gh.prs[3] = pr_meta(
            3, author="me", body=body, closingIssuesReferences=closing,
            headRefName="feat/x",
        )  # fmt: skip
        assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
        own = (tmp_path / ".maigo/i/3.md").read_text()
        assert "  - 為什麼：reason" in own
        assert "  - 做了什麼：a；b" in own
        assert "- 自用（`../pr/3/summary.md`）：" in own
        assert "- 關聯 issue：#12" in own
        review = (tmp_path / ".maigo/i/1.md").read_text()
        assert "對外" not in review and "自用" not in review and "關聯" not in review
        before = own
        assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
        assert (tmp_path / ".maigo/i/3.md").read_text() == before


# --- own-PR checkbox reset on a new comment -------------------------------------

SNAPSHOT_AT = datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc)
STORED_OTHERS_AT = "2026-09-25T00:00:00+00:00"


def _own_pr_line(mark: str, badges: str = "") -> str:
    return f"1. [{mark}] 🔀 有新 comment @me{badges} i/1.md — Title 1"


def _seed_own_pr(
    root: Path,
    *,
    snapshot_mark: str,
    board_mark: str = "x",
    badges: str = "",
    others_at: str | None = STORED_OTHERS_AT,
    legacy: bool = False,
) -> Path:
    """Board + snapshot as the previous refresh left them, then the board as edited now."""
    write_board(root, board_text(focus=[_own_pr_line(snapshot_mark, badges)]))
    put_detail(root, 1, icon="🔀", status="有新 comment")
    sync.write_snapshot(root, REPO, SNAPSHOT_AT)
    path = root / ".maigo/_internal/board/snapshot.json"
    data = json.loads(path.read_text())
    if legacy:
        for item in data["items"].values():
            item.pop("others_activity_at", None)
    elif others_at:
        data["items"][url(1)]["others_activity_at"] = others_at
    path.write_text(json.dumps(data))
    write_board(root, board_text(focus=[_own_pr_line(board_mark, badges)]))
    return path


def _commented_pr(commented_at: str) -> dict:
    return pr_meta(
        1, author="me",
        comments=[{"author": {"login": "carol"}, "createdAt": commented_at}],
    )  # fmt: skip


def _own_pr_line_on_board(root: Path) -> str:
    return next(ln for ln in board_lines(root) if "i/1.md" in ln and "[" in ln[:8])


def test_refresh_unchecks_own_pr_with_newer_comment_and_marks_it_for_learning(
    tmp_path, gh
):
    _seed_own_pr(tmp_path, snapshot_mark="x")
    gh.prs[1] = _commented_pr("2026-09-29T00:00:00Z")
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    line = _own_pr_line_on_board(tmp_path)
    assert "[ ]" in line and "🔖" in line and "🧠" not in line
    snapshot = json.loads(
        (tmp_path / ".maigo/_internal/board/snapshot.json").read_text()
    )["items"][url(1)]
    assert snapshot["checked"] is False
    assert snapshot["others_activity_at"].startswith("2026-09-29T00:00:00")


def test_refresh_unchecks_own_pr_without_adding_learn_mark_when_already_learned(
    tmp_path, gh
):
    _seed_own_pr(tmp_path, snapshot_mark="x", badges=" 🧠")
    gh.prs[1] = _commented_pr("2026-09-29T00:00:00Z")
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    line = _own_pr_line_on_board(tmp_path)
    assert "[ ]" in line and "🧠" in line and "🔖" not in line


def test_refresh_keeps_own_pr_check_when_no_comment_is_newer_than_the_last_one_seen(
    tmp_path, gh
):
    _seed_own_pr(tmp_path, snapshot_mark="x")
    gh.prs[1] = _commented_pr("2026-09-24T00:00:00Z")
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    line = _own_pr_line_on_board(tmp_path)
    assert "[x]" in line and "🔖" not in line


def test_refresh_keeps_a_check_first_seen_in_this_round_even_with_newer_comment(
    tmp_path, gh
):
    _seed_own_pr(tmp_path, snapshot_mark=" ", board_mark="x")
    gh.prs[1] = _commented_pr("2026-09-29T00:00:00Z")
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert "[x]" in _own_pr_line_on_board(tmp_path)


@pytest.mark.parametrize(
    "commented_at,reset",
    [("2026-09-29T00:00:00Z", True), ("2026-09-10T00:00:00Z", False)],
)
def test_refresh_reads_a_legacy_snapshot_and_falls_back_to_its_written_at(
    tmp_path, gh, commented_at, reset
):
    path = _seed_own_pr(tmp_path, snapshot_mark="x", legacy=True)
    assert "others_activity_at" not in path.read_text()
    gh.prs[1] = _commented_pr(commented_at)
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert ("[ ]" in _own_pr_line_on_board(tmp_path)) is reset
    snapshot = json.loads(path.read_text())
    assert snapshot["version"] == 1
    assert "others_activity_at" in snapshot["items"][url(1)]


def test_refresh_preview_reports_the_own_pr_checkbox_reset_and_writes_nothing(
    tmp_path, gh, capsys
):
    _seed_own_pr(tmp_path, snapshot_mark="x")
    gh.prs[1] = _commented_pr("2026-09-29T00:00:00Z")
    before = tree_hash(tmp_path)
    assert run_cli(tmp_path, "--no-discovery", "--json") == 0
    summary = json.loads(capsys.readouterr().out)
    assert tree_hash(tmp_path) == before
    assert any("#1" in w and "取消舊的勾選" in w for w in summary["warnings"])
    assert f"-{_own_pr_line('x')}\n" in summary["diff"]
    assert "\n+1. [ ] 🔀 有新 comment @me 🔖 " in summary["diff"]


def _snapshot_item(root: Path) -> dict:
    data = json.loads((root / ".maigo/_internal/board/snapshot.json").read_text())
    return data["items"][url(1)]


def test_refresh_keeps_own_pr_check_when_newest_activity_equals_the_baseline(
    tmp_path, gh
):
    _seed_own_pr(tmp_path, snapshot_mark="x")
    gh.prs[1] = _commented_pr("2026-09-25T00:00:00Z")
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert "[x]" in _own_pr_line_on_board(tmp_path)


@pytest.mark.parametrize("legacy", [False, True])
def test_refresh_does_not_advance_the_baseline_while_another_status_masks_the_comment(
    tmp_path, gh, legacy
):
    _seed_own_pr(tmp_path, snapshot_mark="x", legacy=legacy)
    commented = "2026-09-29T00:00:00Z"
    gh.prs[1] = _commented_pr(commented)
    gh.prs[1]["reviewDecision"] = "CHANGES_REQUESTED"
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    line = _own_pr_line_on_board(tmp_path)
    assert "[x]" in line and "🔖" not in line
    assert _snapshot_item(tmp_path)["others_activity_at"] < "2026-09-29"
    gh.prs[1] = _commented_pr(commented)  # same activity, now plain 有新 comment
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    line = _own_pr_line_on_board(tmp_path)
    assert "[ ]" in line and "🔖" in line
    assert _snapshot_item(tmp_path)["others_activity_at"].startswith("2026-09-29")


def test_refresh_advances_the_baseline_when_the_user_unticked_during_a_masked_round(
    tmp_path, gh
):
    _seed_own_pr(tmp_path, snapshot_mark="x", board_mark=" ")
    gh.prs[1] = _commented_pr("2026-09-29T00:00:00Z")
    gh.prs[1]["reviewDecision"] = "CHANGES_REQUESTED"
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert _snapshot_item(tmp_path)["others_activity_at"].startswith("2026-09-29")


def test_refresh_treats_an_unparsable_stored_others_activity_as_missing(tmp_path, gh):
    _seed_own_pr(tmp_path, snapshot_mark="x", others_at="garbage")
    gh.prs[1] = _commented_pr("2026-09-29T00:00:00Z")
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert "[ ]" in _own_pr_line_on_board(tmp_path)


def test_refresh_leaves_a_hand_unticked_own_pr_alone_despite_new_comment(
    tmp_path, gh, capsys
):
    _seed_own_pr(tmp_path, snapshot_mark="x", board_mark=" ")
    gh.prs[1] = _commented_pr("2026-09-29T00:00:00Z")
    assert run_cli(tmp_path, "--apply", "--no-discovery", "--json") == 0
    summary = json.loads(capsys.readouterr().out)
    line = _own_pr_line_on_board(tmp_path)
    assert "[ ]" in line and "🔖" not in line
    assert not any("取消舊的勾選" in w for w in summary["warnings"])


def test_refresh_keeps_the_stored_others_activity_of_an_unreachable_own_pr(
    tmp_path, gh
):
    _seed_own_pr(tmp_path, snapshot_mark="x")
    gh.fail = {1}
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    assert _snapshot_item(tmp_path)["others_activity_at"] == STORED_OTHERS_AT


def test_write_snapshot_carries_over_others_activity_for_the_snapshot_command(
    tmp_path,
):
    path = _seed_own_pr(tmp_path, snapshot_mark="x")
    argv = ["snapshot", "--maigo-root", str(tmp_path), "--repo", REPO, "--you", YOU]
    assert sync.main(argv) == 0
    assert json.loads(path.read_text())["items"][url(1)]["others_activity_at"] == (
        STORED_OTHERS_AT
    )
    sync.write_snapshot(tmp_path, REPO, NOW, others_activity_overrides={url(1): None})
    assert "others_activity_at" not in json.loads(path.read_text())["items"][url(1)]


def test_refresh_does_not_apply_the_own_pr_reset_to_review_or_issue_rows(tmp_path, gh):
    write_board(
        tmp_path,
        board_text(
            focus=[
                row(2, "x", status="已看完"),
                row(3, "x", icon="🐛", status="待 triage", author="rep"),
            ]
        ),
    )
    put_detail(tmp_path, 2)
    put_detail(tmp_path, 3, kind="issues", icon="🐛", status="待 triage")
    sync.write_snapshot(tmp_path, REPO, SNAPSHOT_AT)
    gh.prs[2] = pr_meta(
        2,
        reviews=[
            {"author": {"login": YOU}, "state": "APPROVED",
             "submittedAt": "2026-09-15T00:00:00Z", "body": "ok"},
        ],
        comments=[{"author": {"login": "dave"}, "createdAt": "2026-09-29T00:00:00Z"}],
    )  # fmt: skip
    gh.issues[3] = issue_meta(3)
    gh.issues[3]["comments"] = [
        {"author": {"login": "dave"}, "createdAt": "2026-09-29T00:00:00Z"}
    ]
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 0
    lines = [ln for ln in board_lines(tmp_path) if "i/2.md" in ln or "i/3.md" in ln]
    assert len(lines) == 2
    assert all("[x]" in ln and "🔖" not in ln for ln in lines)
