"""Tests for scripts.board_refresh — zero-token `board_sync.py refresh` (T1-T18 of the plan)."""

from __future__ import annotations

import hashlib
import json
import re
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

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


SKILL_MD = Path(__file__).resolve().parent.parent / "skills" / "work-board" / "SKILL.md"


def test_skill_grammar_examples_parse():
    """The example board in SKILL.md §1 parses cleanly and re-renders byte-identically."""
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
    notes = "多行\n\n<!-- 保留 -->\r\n- 一\n- 二\n"
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
    write_board(tmp_path, board_text(focus=[row(1, "x")]))
    put_detail(tmp_path, 1)
    gh.prs[1] = pr_meta(1)
    return report.publish(
        tmp_path, url(1), REPO, "PR 1", "## A\nx\n", HEAD, "APPROVE", owner="others"
    )


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
    assert not (tmp_path / ".maigo" / "_internal").exists()
    assert "未寫任何檔" in capsys.readouterr().err


def test_t6_detail_changed_before_apply_exits_2_and_writes_nothing(
    tmp_path, gh, monkeypatch
):
    write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1)
    gh.prs[1] = pr_meta(1)
    original = refresh.apply_refresh
    detail = tmp_path / ".maigo" / "i" / "1.md"

    def hooked(g, built):
        detail.write_text(detail.read_text().replace("<!-- 手寫區 -->", "新筆記"))
        return original(g, built)

    monkeypatch.setattr(refresh, "apply_refresh", hooked)
    board_before = (tmp_path / ".maigo/board.md").read_bytes()
    assert run_cli(tmp_path, "--apply", "--no-discovery") == 2
    assert (tmp_path / ".maigo/board.md").read_bytes() == board_before
    assert "新筆記" in detail.read_text() and "PR 1" not in detail.read_text()
    assert not (tmp_path / ".maigo" / "_internal").exists()


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
    assert set(refresh.parse_load_templates(example, "SKILL.md")) == {"pr", "branch"}


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
    assert not (tmp_path / ".maigo" / "_internal").exists()
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
    original = refresh.apply_refresh

    def hooked(g, built):
        action()
        return original(g, built)

    monkeypatch.setattr(refresh, "apply_refresh", hooked)


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
    assert not (tmp_path / ".maigo" / "_internal").exists()


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
