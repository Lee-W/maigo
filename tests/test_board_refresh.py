"""Tests for scripts.board_refresh — zero-token `board_sync.py refresh` (T1-T18 of the plan)."""

from __future__ import annotations

import hashlib
import json
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
> 最後刷新：2026-08-18 14:30 ｜ 🎯 3 ｜ ⏳ 2 ｜ ✅ 1 ｜ 🧠 待學習盤點 1

## 🎯 下一件（3）

1. [ ] 🔀 CHANGES_REQUESTED @Lee-W i/9201.md — Redesign Work Board reading view
2. [x] 👀 ↩︎ 回你的球 @contributor i/9301.md — Avoid duplicate GitHub requests
3. [ ] 🐛 待 triage @reporter 💤 i/9101.md — CLI 在空設定檔時會 crash

## ⏳ 等別人（2）

- [ ] 🔀 等 review @Lee-W i/9202.md — Document plugin installation flow
- [ ] 🐛 NEEDS_INFO（已請補作業系統與完整 log） @reporter i/9103.md — Hook occasionally exits without output

## ✅ 最近結案（1）

- [x] 👀 APPROVE（merged 07-12） @contributor 🧠 i/9303.md — Add structured review verdicts
"""

EXTRA_LINES = [
    "1. [ ] 🔀 CI 紅 i/airflow-70724.md — Run CI on release-branch pull requests",
    "2. [ ] 👀 抓不到（GraphQL: Could not resolve） i/foo-3.md — owner/foo#3",
    "3. [x] 👀 已看完 @dev 🧠🔖💤 i/55.md — All three badges",
]


def _as_board(line: str) -> str:
    heading = "## 🎯 下一件（1）" if line[0].isdigit() else "## ⏳ 等別人（1）"
    return f"# Work Board — {REPO}\n\n{heading}\n\n{line}\n"


def _render(parsed_line: dict) -> str:
    return refresh.render_line(
        number=parsed_line["number"], checked=parsed_line["checked"],
        type=parsed_line["type"], status=parsed_line["status"],
        note=parsed_line["note"], author=parsed_line["author"],
        badges=parsed_line["badges"], detail=parsed_line["detail"],
        title=parsed_line["title"],
    )  # fmt: skip


def test_t1_every_line_shape_round_trips():
    lines = [
        ln
        for ln in SKILL_BOARD.splitlines()
        if ln.startswith(("1. ", "2. ", "3. ", "- ["))
    ] + EXTRA_LINES
    assert len(lines) == 9
    for line in lines:
        parsed = sync.parse_board(_as_board(line))
        assert parsed["errors"] == [], line
        assert _render(parsed["lines"][0]) == line


def test_t2_whole_file_round_trip_is_byte_identical():
    parsed = sync.parse_board(SKILL_BOARD)
    rows = {s: [ln for ln in parsed["lines"] if ln["section"] == s] for s in "🎯⏳✅"}
    rows = {"🎯": rows["🎯"], "⏳": rows["⏳"], "✅": rows["✅"]}
    flat = [r for section in rows.values() for r in section]
    rendered = refresh.render_board(
        repo="Lee-W/maigo",
        refreshed_at_local="2026-08-18 14:30",
        rows_by_section=rows,
        learn_pending_count=refresh.count_learn_pending(flat),
    )
    assert rendered == SKILL_BOARD


def test_t3_real_board_shape_survives_parse_render_parse():
    # Shape of a real board: no blank after the section title, date-only header,
    # no 🧠 section, no @author. Content is invented.
    text = (
        "# Work Board — o/r\n"
        "> 最後刷新：2026-08-19 ｜ 🎯 2 ｜ ⏳ 1 ｜ ✅ 0\n\n"
        "## 🎯 下一件（2）\n"
        "1. [ ] 🔀 CI 紅 i/other-11.md — First invented title\n"
        "2. [ ] 👀 待 review 💤 i/12.md — Second invented title\n\n"
        "## ⏳ 等別人（1）\n"
        "- [ ] 🔀 等 review i/13.md — Third invented title\n\n"
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
    assert second["errors"] == []
    assert [{k: ln[k] for k in keys} for ln in second["lines"]] == [
        {k: ln[k] for k in keys} for ln in first["lines"]
    ]


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
    assert facts.startswith("# 👀 待 review — PR 1\n\n- 連結：" + url(1))
    assert "- 規模：Δ+10/-2 ｜ 作者：carol" in facts


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
    return report.publish(tmp_path, url(1), REPO, "PR 1", "## A\nx\n", HEAD, "APPROVE")


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
    assert lines[1] == "> 最後刷新：2026-10-01 12:00 ｜ 🎯 4 ｜ ⏳ 2 ｜ ✅ 0"
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
    assert "## 🎯 下一件（4）" in lines and "## ✅ 最近結案（0）" in lines


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


def test_t9_closed_artifact_is_not_added_but_logged(tmp_path, gh):
    write_board(tmp_path, board_text(focus=[row(1)]))
    put_detail(tmp_path, 1)
    gh.prs[1] = pr_meta(1)
    gh.prs[5] = pr_meta(5, state="MERGED", mergedAt=RECENT)
    report.publish(tmp_path, url(5), REPO, "PR 5", "## A\nx\n", HEAD, "APPROVE")
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
        tmp_path, url(1), REPO, "PR 1", "## A\nx\n", HEAD, "APPROVE"
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
        tmp_path, url(1), REPO, "PR 1", "## A\nx\n", HEAD, "APPROVE"
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
