"""Tests for scripts.board_sync — reconcile, discovery, dd ledger and `[x]` semantics."""

from __future__ import annotations

import hashlib
import io
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts import board_sync as sync
from scripts import review_report as report

REPO = "o/r"
YOU = "me"
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
HEAD = "a" * 40


def url(n: int, kind: str = "pull", repo: str = REPO) -> str:
    return f"https://github.com/{repo}/{kind}/{n}"


def board_text(*items: str) -> str:
    body = "\n".join(items)
    return f"# Work Board — {REPO}\n> 最後刷新：x\n\n## 🎯 下一件（1）\n\n{body}\n"


def put_detail(root: Path, n: int, link: str | None = None, minutes_old: int = 60):
    path = root / ".maigo" / "i" / f"{n}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# 👀 待 review — T\n\n- 連結：{link or url(n)}\n")
    stamp = (NOW - timedelta(minutes=minutes_old)).timestamp()
    os.utime(path, (stamp, stamp))
    return path


def make_board(root: Path, *items: str, details: tuple[int, ...] = ()):
    maigo = root / ".maigo"
    maigo.mkdir(parents=True, exist_ok=True)
    (maigo / "board.md").write_text(board_text(*items))
    for n in details:
        put_detail(root, n)


def row(n: int, mark: str = " ", status: str = "待 review", extra: str = "") -> str:
    return f"{n}. [{mark}] 👀 {status} @carol{extra} i/{n}.md — Title {n}"


def state_dir(root: Path) -> Path:
    return root / ".maigo" / "_internal" / "board"


def ledger_events(root: Path) -> list[dict]:
    path = state_dir(root) / "dropped.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def pr(n: int, *, author="carol", is_bot=False, updated="2026-09-30T00:00:00Z"):
    return {
        "url": url(n),
        "title": f"PR {n}",
        "author": {"login": author, "is_bot": is_bot},
        "repository": {"nameWithOwner": REPO},
        "updatedAt": updated,
        "isDraft": False,
    }


class FakeGh:
    def __init__(self, requested=(), reviewed=(), timeline=None, fail=()):
        self.requested = list(requested)
        self.reviewed = list(reviewed)
        self.timeline = timeline or {}
        self.fail = set(fail)
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str]) -> str:
        self.calls.append(cmd)
        assert cmd[0] == "gh"
        if cmd[1] == "search":
            kind = "requested" if "user-review-requested:@me" in cmd else "reviewed"
            if kind in self.fail:
                raise RuntimeError("rate limited")
            assert cmd[cmd.index("--repo") + 1] == REPO
            assert "--state" in cmd and "open" in cmd
            return json.dumps(getattr(self, kind))
        number = int(cmd[2].split("/")[-2])
        if number in self.fail:
            raise RuntimeError("boom")
        return json.dumps(self.timeline.get(number, []))


@pytest.fixture
def gh(monkeypatch):
    fake = FakeGh()
    monkeypatch.setattr(sync, "run", fake)
    return fake


def plan(root: Path, **kwargs):
    kwargs.setdefault("now", NOW)
    return sync.plan_refresh(root, REPO, YOU, **kwargs)


def tree_hash(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def publish_report(root: Path, n: int, head: str = HEAD):
    return report.publish(root, url(n), REPO, f"PR {n}", "## A\nx\n", head, "APPROVE")


# --- parse_board -------------------------------------------------------------


class TestParseBoard:
    def test_parses_all_three_sections_and_fields(self):
        text = (
            "# Work Board\n\n## 🎯 下一件（1）\n\n"
            "1. [x] 👀 APPROVE_WITH_NITS（merged 07-12） @bot[bot] 🧠💤🔖 i/9.md — A — B\n\n"
            "## ⏳ 等別人（1）\n\n- [ ] 🔀 等 review @me i/2.md — T2\n\n"
            "## ✅ 最近結案（1）\n\n- [x] 🐛 已放棄 i/3.md — T3\n"
        )
        parsed = sync.parse_board(text)
        assert parsed["errors"] == [] and not parsed["legacy"]
        first, second, third = parsed["lines"]
        assert first["checked"] and first["number"] == 1 and first["section"] == "🎯"
        assert first["status"] == "APPROVE_WITH_NITS"
        assert first["note"] == "（merged 07-12）" and first["author"] == "bot[bot]"
        assert first["badges"] == ["🧠", "💤", "🔖"] and first["title"] == "A — B"
        assert second["section"] == "⏳" and second["number"] is None
        assert third["status"] == "已放棄" and third["detail"] == "i/3.md"

    def test_longest_status_wins_and_spaced_statuses_parse(self):
        text = (
            "## 🎯 下一件\n"
            "1. [ ] 👀 ↩︎ 回你的球 @a i/1.md — x\n"
            "2. [ ] 👀 APPROVE @a i/2.md — x\n"
            "3. [ ] 🐛 抓不到 i/3.md — x\n"
        )
        statuses = [line["status"] for line in sync.parse_board(text)["lines"]]
        assert statuses == ["↩︎ 回你的球", "APPROVE", "抓不到"]

    def test_missing_space_after_note_is_tolerated(self):
        text = "## 🎯 下一件\n1. [ ] 🔀 WIP（分支 x）@me🧠i/4.md — t\n"
        line = sync.parse_board(text)["lines"][0]
        assert line["note"] == "（分支 x）" and line["author"] == "me"
        assert line["badges"] == ["🧠"] and line["detail"] == "i/4.md"

    @pytest.mark.parametrize(
        "bad,needle",
        [
            ("1. [ ] 👀 待 review @a i/1.md Title", "—"),
            ("1. [ ] 👀 NOT_A_STATUS @a i/1.md — t", "未知狀態詞"),
            ("1. [ ] 🚀 待 review @a i/1.md — t", "未知型別"),
            ("1. [ ] 👀 待 review @a — t", "缺細節檔路徑"),
        ],
    )
    def test_bad_lines_are_reported_not_skipped(self, bad, needle):
        parsed = sync.parse_board("## 🎯 下一件\n" + bad + "\n")
        assert parsed["lines"] == []
        assert len(parsed["errors"]) == 1 and needle in parsed["errors"][0]
        assert parsed["unparsed"][0]["raw"] == bad

    def test_old_section_heading_is_legacy(self):
        assert sync.parse_board("## 🎯 你的球\n- [ ] x\n")["legacy"] is True
        assert sync.parse_board("## 🎯 下一件\n### 已 review\n")["legacy"] is True

    def test_plan_refuses_legacy_board(self, tmp_path, gh):
        (tmp_path / ".maigo").mkdir()
        (tmp_path / ".maigo" / "board.md").write_text("## 🎯 你的球\n")
        with pytest.raises(sync.BoardLegacyError):
            plan(tmp_path)
        assert (
            sync.main(
                ["plan", "--maigo-root", str(tmp_path), "--repo", REPO, "--you", YOU]
            )
            == 1
        )


class TestDetailUrl:
    def test_reads_link_line_and_falls_back_for_numeric_ids(self, tmp_path):
        maigo = tmp_path / ".maigo"
        (maigo / "i").mkdir(parents=True)
        (maigo / "i" / "5.md").write_text("- 連結：https://github.com/x/y/pull/5\n")
        assert sync.detail_url(maigo, "i/5.md", REPO) == "https://github.com/x/y/pull/5"
        assert sync.detail_url(maigo, "i/6.md", REPO) == url(6)
        assert sync.detail_url(maigo, "i/6.md", REPO, "🐛") == url(6, "issues")
        assert sync.detail_url(maigo, "i/repo-6.md", REPO) is None


def test_ref_key_treats_pull_and_issues_alike_and_ignores_case():
    assert sync.ref_key("https://github.com/O/R/pull/3/") == sync.ref_key(
        "https://github.com/o/r/issues/3"
    )
    assert sync.ref_key("https://example.com/o/r/pull/3") is None


# --- ledger ------------------------------------------------------------------


class TestLedger:
    def test_fold_follows_event_order(self, tmp_path):
        ledger = tmp_path / "dropped.jsonl"
        sync.append_event(ledger, url(1), "drop", "dd", "2026-01-01T00:00:00+00:00")
        sync.append_event(ledger, url(1), "revive", "x", "2026-01-02T00:00:00+00:00")
        state, errors = sync.load_exclusions(ledger)
        assert errors == [] and not state[sync.ref_key(url(1))]["excluded"]
        sync.append_event(
            ledger, url(1, "issues"), "drop", "dd", "2026-01-03T00:00:00+00:00"
        )
        state, _ = sync.load_exclusions(ledger)
        entry = state[sync.ref_key(url(1))]
        assert entry["excluded"] and entry["last_drop_at"].startswith("2026-01-03")

    def test_bad_line_is_reported_and_rest_still_loads(self, tmp_path):
        ledger = tmp_path / "dropped.jsonl"
        sync.append_event(ledger, url(2), "drop", "dd", "2026-01-01T00:00:00+00:00")
        with open(ledger, "a") as stream:
            stream.write("{not json\n")
        sync.append_event(ledger, url(3), "drop", "dd", "2026-01-01T00:00:00+00:00")
        state, errors = sync.load_exclusions(ledger)
        assert len(errors) == 1 and "dropped.jsonl:2" in errors[0]
        assert sync.ref_key(url(2)) in state and sync.ref_key(url(3)) in state

    def test_append_creates_missing_directory(self, tmp_path):
        ledger = tmp_path / "a" / "b" / "dropped.jsonl"
        sync.append_event(ledger, url(1), "drop", "dd", NOW.isoformat())
        assert ledger.exists()


# --- checkbox changes --------------------------------------------------------


class TestCheckboxChanges:
    K1, K2 = sync.ref_key(url(1)), sync.ref_key(url(2))

    def test_with_snapshot_both_directions(self):
        snap = {url(1): {"checked": False}, url(2): {"checked": True}}
        out = sync.checkbox_changes([(self.K1, True), (self.K2, False)], snap)
        assert out[self.K1] == {"change": "checked", "inferred": False}
        assert out[self.K2] == {"change": "unchecked", "inferred": False}

    def test_unchanged_is_none(self):
        snap = {url(1): {"checked": True}}
        assert sync.checkbox_changes([(self.K1, True)], snap)[self.K1]["change"] is None

    @pytest.mark.parametrize("snap", [None, {}, {url(9): {"checked": True}}])
    def test_without_snapshot_entry_falls_back_to_inference(self, snap):
        out = sync.checkbox_changes([(self.K1, True), (self.K2, False)], snap)
        assert out[self.K1] == {"change": "checked", "inferred": True}
        assert out[self.K2] == {"change": None, "inferred": False}


# --- discovery ---------------------------------------------------------------


class TestDiscover:
    def test_merges_overlapping_results_with_flags(self, gh):
        gh.requested = [pr(1), pr(2, author="bot", is_bot=True)]
        gh.reviewed = [pr(2, author="bot", is_bot=True), pr(3)]
        found, errors = sync.discover(REPO, YOU)
        assert errors == []
        assert (
            found[sync.ref_key(url(1))]["requested"]
            and not found[sync.ref_key(url(1))]["reviewed"]
        )
        both = found[sync.ref_key(url(2))]
        assert both["requested"] and both["reviewed"] and both["is_bot"]
        assert found[sync.ref_key(url(3))]["reviewed"]
        assert {c[-1] for c in gh.calls} == {"user-review-requested:@me", "-author:@me"}

    def test_own_pr_gets_review_pr_type_hint_flipped_to_own(self, gh):
        gh.requested = [pr(1, author="Me"), pr(2)]
        found, _ = sync.discover(REPO, YOU)
        assert found[sync.ref_key(url(1))]["type_hint"] == "🔀"
        assert found[sync.ref_key(url(2))]["type_hint"] == "👀"

    def test_result_count_equal_to_limit_warns_of_truncation(self, gh, monkeypatch):
        monkeypatch.setattr(sync, "SEARCH_LIMIT", 2)
        gh.requested = [pr(1), pr(2)]
        _, errors = sync.discover(REPO, YOU)
        assert any("可能截斷" in e for e in errors)

    def test_search_failure_is_an_error_not_a_crash(self, gh):
        gh.fail = {"requested"}
        gh.reviewed = [pr(3)]
        found, errors = sync.discover(REPO, YOU)
        assert any("requested" in e for e in errors) and sync.ref_key(url(3)) in found


# --- re-request detection ----------------------------------------------------


class TestIsRerequested:
    @staticmethod
    def event(reviewer, at, kind="review_requested"):
        return {
            "event": kind,
            "created_at": at,
            "requested_reviewer": {"login": reviewer},
        }

    def test_event_before_drop_does_not_count(self):
        assert not sync.is_rerequested(
            [self.event(YOU, "2026-01-01T00:00:00Z")], YOU, "2026-01-02T00:00:00+00:00"
        )

    def test_event_after_drop_counts(self):
        assert sync.is_rerequested(
            [self.event("ME", "2026-01-03T00:00:00Z")], YOU, "2026-01-02T00:00:00+00:00"
        )

    def test_request_for_someone_else_does_not_count(self):
        assert not sync.is_rerequested(
            [self.event("other", "2026-01-03T00:00:00Z")],
            YOU,
            "2026-01-02T00:00:00+00:00",
        )

    def test_other_event_kinds_do_not_count(self):
        assert not sync.is_rerequested(
            [self.event(YOU, "2026-01-03T00:00:00Z", "review_request_removed")],
            YOU,
            "2026-01-02T00:00:00+00:00",
        )


# --- artifacts ---------------------------------------------------------------


class TestReconcileArtifacts:
    def test_maps_reliable_artifacts_and_flags_the_rest(self, tmp_path):
        publish_report(tmp_path, 11)
        foreign = "https://github.com/x/y/pull/50"
        report.publish(tmp_path, foreign, REPO, "Foreign", "## A\nx\n", HEAD, "APPROVE")
        maigo = tmp_path / ".maigo"
        (maigo / "review-42.md").write_text(
            f"# Review: Old\n\n**PR:** {url(42)}\nold\n"
        )
        (maigo / "review-43.md").write_text("# Review: no pr line\n")
        (maigo / "review" / "77").mkdir(parents=True)
        (maigo / "review" / "77" / "rubric.md").write_text("# Review rubric: x\n")
        (maigo / "issue" / "88").mkdir(parents=True)
        (maigo / "issue" / "88" / "rubric.md").write_text("# Triage rubric: x\n")
        (maigo / "plan-x.md").write_text("# Plan: x\n")
        (maigo / "plan.md").write_text("# Plan: y\n")
        (maigo / "notes.md").write_text("# loose\n")
        local = tmp_path / "local"
        report.publish(local, "feature/x", "", "Local", "## A\nx\n", HEAD, "APPROVE")
        local_review = next((local / ".maigo").rglob("review.md"))
        dest = maigo / "review" / "feature-x"
        dest.mkdir(parents=True)
        (dest / "review.md").write_text(local_review.read_text())
        (maigo / "review" / "other-5").mkdir()
        (maigo / "review" / "other-5" / "rubric.md").write_text("# r\n")

        candidates, unattributed, errors = sync.reconcile_artifacts(maigo, REPO)
        assert errors == []
        by_url = {c["url"]: c for c in candidates}
        assert by_url[url(11)]["artifact_source"] == "metadata"
        assert by_url[foreign]["artifact_source"] == "metadata"
        assert by_url[url(42)]["artifact_source"] == "legacy-pr"
        assert by_url[url(77)]["artifact_source"] == "derived"
        assert by_url[url(88, "issues")]["artifact_source"] == "derived"
        assert len(by_url) == 5
        skipped = {u["path"] for u in unattributed}
        assert {
            "plan-x.md",
            "plan.md",
            "notes.md",
            "review-43.md",
            "review/feature-x/review.md",
            "review/other-5/rubric.md",
        } <= skipped

    def test_internal_files_never_show_up(self, tmp_path):
        maigo = tmp_path / ".maigo"
        (maigo / "_internal" / "board").mkdir(parents=True)
        (maigo / "_internal" / "x.md").write_text("x")
        (maigo / "_internal" / "board" / "snapshot.json").write_text("{}")
        candidates, unattributed, _ = sync.reconcile_artifacts(maigo, REPO)
        assert candidates == [] and unattributed == []


# --- dd detection ------------------------------------------------------------


class TestDetectRemoved:
    def test_snapshot_minus_board_minus_excluded(self):
        snapshot = {
            url(1): {"detail": "i/1.md"},
            url(2): {"detail": "i/2.md"},
            url(3): {},
        }
        removed = sync.detect_removed(
            snapshot, {}, {sync.ref_key(url(2))}, {sync.ref_key(url(3))}
        )
        assert [r["url"] for r in removed] == [url(1)]

    def test_snapshot_entry_whose_detail_is_still_on_board_is_kept(self):
        snapshot = {url(1): {"detail": "i/1.md"}}
        assert sync.detect_removed(snapshot, {}, set(), set(), {"i/1.md"}) == []

    def test_orphan_is_a_removal_signal(self):
        orphans = {sync.ref_key(url(4)): {"url": url(4), "path": "i/4.md"}}
        removed = sync.detect_removed({}, orphans, set(), set())
        assert removed[0]["source"] == "orphan"


class TestPlanDeletion:
    def test_snapshot_signal_writes_dd_to_ledger(self, tmp_path, gh):
        make_board(tmp_path, row(1), row(2), details=(1, 2))
        sync.write_snapshot(tmp_path, REPO, NOW)
        make_board(tmp_path, row(1))
        result = plan(tmp_path, discovery=False)
        assert [r["url"] for r in result["removed"]] == [url(2)]
        events = ledger_events(tmp_path)
        assert events[0]["event"] == "drop" and events[0]["reason"] == "dd"
        second = plan(tmp_path, discovery=False)
        assert second["removed"] == []

    def test_orphan_detail_file_is_dd_on_first_run(self, tmp_path, gh):
        make_board(tmp_path, row(1), details=(1,))
        put_detail(tmp_path, 9, minutes_old=60)
        result = plan(tmp_path, discovery=False)
        assert result["first_run"] is True
        assert [r["url"] for r in result["removed"]] == [url(9)]
        assert result["removed"][0]["source"] == "orphan"
        assert result["excluded_detail_files"] == [{"path": "i/9.md", "url": url(9)}]

    def test_ten_minute_grace_period_for_fresh_orphans(self, tmp_path, gh):
        make_board(tmp_path, row(1), details=(1,))
        put_detail(tmp_path, 9, minutes_old=9)
        result = plan(tmp_path, discovery=False)
        assert result["removed"] == []
        assert result["pending_orphans"] == [{"path": "i/9.md"}]
        assert ledger_events(tmp_path) == []
        put_detail(tmp_path, 8, minutes_old=11)
        assert [r["url"] for r in plan(tmp_path, discovery=False)["removed"]] == [
            url(8)
        ]

    def test_unparseable_line_is_not_mistaken_for_a_deletion(self, tmp_path, gh):
        make_board(tmp_path, row(1), row(2), details=(1, 2))
        sync.write_snapshot(tmp_path, REPO, NOW)
        make_board(tmp_path, row(1), "2. [ ] 👀 待 review @carol i/2.md no separator")
        result = plan(tmp_path, discovery=False)
        assert result["removed"] == [] and result["errors"]


# --- plan: discovery, exclusion, revival --------------------------------------


class TestPlanDiscovery:
    def test_additions_ordered_requested_reviewed_artifact_then_by_age(
        self, tmp_path, gh
    ):
        make_board(tmp_path, row(1), details=(1,))
        publish_report(tmp_path, 30)
        gh.requested = [
            pr(1),
            pr(10, updated="2026-09-02T00:00:00Z"),
            pr(11, updated="2026-09-01T00:00:00Z"),
        ]
        gh.reviewed = [pr(20)]
        result = plan(tmp_path)
        assert [a["url"] for a in result["additions"]] == [
            url(11),
            url(10),
            url(20),
            url(30),
        ]
        assert [a["source"] for a in result["additions"]] == [
            "requested", "requested", "reviewed", "artifact",
        ]  # fmt: skip

    def test_max_new_caps_and_overflow_keeps_priority_order(self, tmp_path, gh):
        make_board(tmp_path, row(1), details=(1,))
        gh.requested = [pr(10, updated="2026-09-01T00:00:00Z")]
        gh.reviewed = [pr(20), pr(21)]
        result = plan(tmp_path, max_new=2)
        assert [a["url"] for a in result["additions"]] == [url(10), url(20)]
        assert [a["url"] for a in result["overflow"]] == [url(21)]

    def test_no_discovery_skips_gh_but_still_reconciles_artifacts(self, tmp_path, gh):
        make_board(tmp_path, row(1), details=(1,))
        publish_report(tmp_path, 30)
        result = plan(tmp_path, discovery=False)
        assert gh.calls == []
        assert [a["url"] for a in result["additions"]] == [url(30)]

    def test_items_already_on_board_are_not_added(self, tmp_path, gh):
        make_board(tmp_path, row(1), details=(1,))
        gh.requested = [pr(1)]
        assert plan(tmp_path)["additions"] == []

    def test_excluded_item_without_new_request_stays_excluded(self, tmp_path, gh):
        make_board(tmp_path, row(1), details=(1,))
        sync.append_event(
            state_dir(tmp_path) / "dropped.jsonl", url(5), "drop", "drop",
            "2026-09-30T00:00:00+00:00",
        )  # fmt: skip
        gh.requested = [pr(5)]
        gh.timeline = {5: [TestIsRerequested.event(YOU, "2026-09-29T00:00:00Z")]}
        result = plan(tmp_path)
        assert result["additions"] == [] and result["revived"] == []
        assert len(ledger_events(tmp_path)) == 1

    def test_newer_request_revives_and_re_adds(self, tmp_path, gh):
        make_board(tmp_path, row(1), details=(1,))
        sync.append_event(
            state_dir(tmp_path) / "dropped.jsonl", url(5), "drop", "drop",
            "2026-09-30T00:00:00+00:00",
        )  # fmt: skip
        gh.requested = [pr(5)]
        gh.timeline = {5: [TestIsRerequested.event(YOU, "2026-10-01T01:00:00Z")]}
        result = plan(tmp_path)
        assert [r["url"] for r in result["revived"]] == [url(5)]
        assert [a["url"] for a in result["additions"]] == [url(5)]
        assert ledger_events(tmp_path)[-1]["event"] == "revive"

    def test_timeline_failure_fails_closed(self, tmp_path, gh):
        make_board(tmp_path, row(1), details=(1,))
        sync.append_event(
            state_dir(tmp_path) / "dropped.jsonl", url(5), "drop", "drop",
            "2026-09-30T00:00:00+00:00",
        )  # fmt: skip
        gh.requested = [pr(5)]
        gh.fail = {5}
        result = plan(tmp_path)
        assert result["additions"] == [] and result["revived"] == []
        assert any("timeline" in e for e in result["errors"])

    def test_just_dd_item_is_not_resurrected_by_old_request(self, tmp_path, gh):
        make_board(tmp_path, row(1), row(2), details=(1, 2))
        sync.write_snapshot(tmp_path, REPO, NOW)
        make_board(tmp_path, row(1))
        gh.requested = [pr(2)]
        gh.timeline = {2: [TestIsRerequested.event(YOU, "2026-09-01T00:00:00Z")]}
        result = plan(tmp_path)
        assert [r["url"] for r in result["removed"]] == [url(2)]
        assert result["additions"] == []

    def test_excluded_artifact_is_not_added_back(self, tmp_path, gh):
        make_board(tmp_path, row(1), details=(1,))
        publish_report(tmp_path, 30)
        sync.append_event(
            state_dir(tmp_path) / "dropped.jsonl",
            url(30),
            "drop",
            "closed",
            NOW.isoformat(),
        )
        assert plan(tmp_path, discovery=False)["additions"] == []

    def test_lines_on_board_carry_excluded_and_checkbox_change(self, tmp_path, gh):
        make_board(tmp_path, row(1), row(2, "x", "已放棄"), details=(1, 2))
        sync.append_event(
            state_dir(tmp_path) / "dropped.jsonl",
            url(2),
            "drop",
            "drop",
            NOW.isoformat(),
        )
        result = plan(tmp_path, discovery=False)
        first, second = result["lines"]
        assert first["excluded"] is False and second["excluded"] is True
        assert second["checkbox_change"] == "checked" and second["inferred"] is True


# --- plan side effects ---------------------------------------------------------


class TestPlanSideEffects:
    def test_dry_run_changes_nothing_and_creates_no_internal_dir(self, tmp_path, gh):
        make_board(tmp_path, row(1), details=(1,))
        put_detail(tmp_path, 9)
        publish_report(tmp_path, 30)
        gh.requested = [pr(10)]
        before = tree_hash(tmp_path)
        result = plan(tmp_path, dry_run=True)
        assert result["removed"] and result["additions"]
        assert tree_hash(tmp_path) == before
        assert not (tmp_path / ".maigo" / "_internal").exists()

    def test_state_dir_is_created_on_demand(self, tmp_path, gh):
        make_board(tmp_path, row(1), details=(1,))
        put_detail(tmp_path, 9)
        plan(tmp_path, discovery=False)
        assert (state_dir(tmp_path) / "dropped.jsonl").exists()
        fresh = tmp_path / "other"
        assert sync.drop_urls(fresh, [url(3)], "drop", NOW)[0]["result"] == "dropped"
        assert (state_dir(fresh) / "dropped.jsonl").exists()
        make_board(fresh, row(1), details=(1,))
        sync.write_snapshot(fresh, REPO, NOW)
        assert (state_dir(fresh) / "snapshot.json").exists()

    def test_plan_never_rewrites_board_or_detail_files(self, tmp_path, gh):
        make_board(tmp_path, row(1), details=(1,))
        put_detail(tmp_path, 9)
        gh.requested = [pr(10)]
        before = {
            k: v
            for k, v in tree_hash(tmp_path).items()
            if k == ".maigo/board.md" or k.startswith(".maigo/i/")
        }
        plan(tmp_path)
        after = {
            k: v
            for k, v in tree_hash(tmp_path).items()
            if k == ".maigo/board.md" or k.startswith(".maigo/i/")
        }
        assert before == after

    def test_internal_markdown_is_not_unattributed(self, tmp_path, gh):
        make_board(tmp_path, row(1), details=(1,))
        (tmp_path / ".maigo" / "_internal").mkdir()
        (tmp_path / ".maigo" / "_internal" / "x.md").write_text("x")
        assert plan(tmp_path, discovery=False)["unattributed"] == []

    def test_snapshot_rereads_the_current_board_not_the_plan_copy(self, tmp_path, gh):
        make_board(tmp_path, row(1), row(2), details=(1, 2))
        plan(tmp_path, discovery=False)
        make_board(tmp_path, row(1, "x"), details=(1,))
        info = sync.write_snapshot(tmp_path, REPO, NOW)
        saved = json.loads((state_dir(tmp_path) / "snapshot.json").read_text())
        assert info["count"] == 1 and list(saved["items"]) == [url(1)]
        assert saved["items"][url(1)]["checked"] is True and saved["version"] == 1


# --- ack -----------------------------------------------------------------------


class TestAck:
    def item(self, n=1, change="checked", inferred=False, head=HEAD):
        return {"url": url(n), "head": head, "change": change, "inferred": inferred}

    def ack(self, root, *items):
        return [r["result"] for r in sync.ack_items(root, REPO, YOU, list(items))]

    def test_checked_with_matching_report_acks(self, tmp_path):
        path = Path(publish_report(tmp_path, 1)["path"])
        assert self.ack(tmp_path, self.item()) == ["acked"]
        assert report.metadata(path.read_text())["acknowledged_by"] == YOU

    def test_inferred_with_head_already_acked_is_not_re_acked(self, tmp_path):
        path = Path(publish_report(tmp_path, 1)["path"])
        self.ack(tmp_path, self.item())
        before = path.read_text()
        assert self.ack(tmp_path, self.item(inferred=True)) == ["already_acked"]
        assert path.read_text() == before

    def test_explicit_check_re_acks_even_when_already_acked(self, tmp_path):
        path = Path(publish_report(tmp_path, 1)["path"])
        self.ack(tmp_path, self.item())
        first = report.metadata(path.read_text())["acknowledged_at"]
        assert self.ack(tmp_path, self.item(inferred=False)) == ["acked"]
        assert report.metadata(path.read_text())["acknowledged_at"] >= first

    def test_inferred_without_prior_ack_acks(self, tmp_path):
        publish_report(tmp_path, 1)
        assert self.ack(tmp_path, self.item(inferred=True)) == ["acked"]

    def test_no_report(self, tmp_path):
        assert self.ack(tmp_path, self.item()) == ["no_report"]

    def test_head_changed_does_not_ack(self, tmp_path):
        path = Path(publish_report(tmp_path, 1)["path"])
        assert self.ack(tmp_path, self.item(head="b" * 40)) == ["head_changed"]
        assert "acknowledged_at" not in report.metadata(path.read_text())

    def test_unchecked_undoes_the_ack(self, tmp_path):
        path = Path(publish_report(tmp_path, 1)["path"])
        self.ack(tmp_path, self.item())
        assert self.ack(tmp_path, self.item(change="unchecked")) == ["unacked"]
        assert "acknowledged_at" not in report.metadata(path.read_text())

    def test_busy_lock_is_reported_as_locked(self, tmp_path):
        path = Path(publish_report(tmp_path, 1)["path"])
        (path.parent / ".review-write-lock").mkdir()
        assert self.ack(tmp_path, self.item()) == ["locked"]

    def test_change_none_is_skipped(self, tmp_path):
        publish_report(tmp_path, 1)
        assert self.ack(tmp_path, self.item(change=None)) == ["skipped"]


# --- CLI -----------------------------------------------------------------------


class TestCli:
    common = ["--repo", REPO, "--you", YOU]

    def test_plan_dry_run_prints_json(self, tmp_path, gh, capsys):
        make_board(tmp_path, row(1), details=(1,))
        args = ["plan", "--dry-run", "--no-discovery", "--maigo-root", str(tmp_path)]
        assert sync.main([*args, *self.common]) == 0
        out = json.loads(capsys.readouterr().out)
        assert out["dry_run"] is True and out["lines"][0]["url"] == url(1)

    def test_drop_ack_and_snapshot_subcommands(self, tmp_path, monkeypatch, capsys):
        root = ["--maigo-root", str(tmp_path), *self.common]
        assert sync.main(["drop", "--reason", "aged", url(4), *root]) == 0
        assert json.loads(capsys.readouterr().out)[0]["result"] == "dropped"
        assert ledger_events(tmp_path)[0]["reason"] == "aged"
        publish_report(tmp_path, 1)
        payload = json.dumps(
            [{"url": url(1), "head": HEAD, "change": "checked", "inferred": False}]
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        assert sync.main(["ack", *root]) == 0
        assert json.loads(capsys.readouterr().out)[0]["result"] == "acked"
        make_board(tmp_path, row(1), details=(1,))
        assert sync.main(["snapshot", *root]) == 0
        assert json.loads(capsys.readouterr().out)["count"] == 1


class TestArchive:
    def put_review(self, root: Path, n: int) -> Path:
        path = root / ".maigo" / "review" / str(n)
        path.mkdir(parents=True, exist_ok=True)
        (path / "rubric.md").write_text("# Review rubric: x\n")
        return path

    def test_moves_review_dir_and_detail_file_under_archive(self, tmp_path):
        self.put_review(tmp_path, 7)
        put_detail(tmp_path, 7)
        result = sync.archive_urls(tmp_path, [url(7)], REPO)
        assert result == [
            {
                "url": url(7),
                "id": "7",
                "moved": ["review/7", "i/7.md"],
                "skipped": [],
                "missing": [],
            }
        ]
        archive = tmp_path / ".maigo" / "_archive"
        assert (
            archive / "review" / "7" / "rubric.md"
        ).read_text() == "# Review rubric: x\n"
        assert (archive / "i" / "7.md").is_file()
        assert not (tmp_path / ".maigo" / "review" / "7").exists()
        assert not (tmp_path / ".maigo" / "i" / "7.md").exists()

    def test_existing_destination_is_never_overwritten(self, tmp_path):
        self.put_review(tmp_path, 7)
        put_detail(tmp_path, 7)
        kept = tmp_path / ".maigo" / "_archive" / "i" / "7.md"
        kept.parent.mkdir(parents=True)
        kept.write_text("older archive\n")
        result = sync.archive_urls(tmp_path, [url(7)], REPO)[0]
        assert result["moved"] == ["review/7"]
        assert result["skipped"] == [{"path": "i/7.md", "reason": "destination exists"}]
        assert kept.read_text() == "older archive\n"
        assert (tmp_path / ".maigo" / "i" / "7.md").is_file()

    def test_missing_sources_and_bad_urls_are_reported(self, tmp_path):
        foreign = "https://github.com/x/y/pull/3"
        result = sync.archive_urls(tmp_path, [url(8), "not-a-url", foreign], REPO)
        assert result[0] == {
            "url": url(8),
            "id": "8",
            "moved": [],
            "skipped": [],
            "missing": ["review/8", "i/8.md"],
        }
        assert result[1] == {
            "url": "not-a-url",
            "result": "error",
            "message": "不是 issue/PR URL",
        }
        assert result[2]["id"] == "y-3"
        assert not (tmp_path / ".maigo" / "_archive").exists()

    def test_internal_dir_is_untouched(self, tmp_path):
        internal = tmp_path / ".maigo" / "_internal" / "board"
        internal.mkdir(parents=True)
        (internal / "snapshot.json").write_text("{}")
        put_detail(tmp_path, 7)
        before = {k: v for k, v in tree_hash(tmp_path).items() if "_internal" in k}
        sync.archive_urls(tmp_path, [url(7)], REPO)
        after = {k: v for k, v in tree_hash(tmp_path).items() if "_internal" in k}
        assert before == after

    def test_plan_ignores_archived_items(self, tmp_path, gh):
        make_board(tmp_path, row(1), details=(1,))
        self.put_review(tmp_path, 9)
        put_detail(tmp_path, 9)
        before = plan(tmp_path, discovery=False, dry_run=True)
        assert [r["url"] for r in before["removed"]] == [url(9)]
        sync.archive_urls(tmp_path, [url(9)], REPO)
        after = plan(tmp_path, discovery=False, dry_run=True)
        assert after["removed"] == [] and after["errors"] == []
        assert url(9) not in [a["url"] for a in after["additions"]]

    def test_cli(self, tmp_path, capsys):
        put_detail(tmp_path, 7)
        args = ["archive", "--maigo-root", str(tmp_path), *TestCli.common, url(7)]
        assert sync.main(args) == 0
        assert json.loads(capsys.readouterr().out)[0]["moved"] == ["i/7.md"]


class TestFailClosedDeletion:
    @pytest.mark.parametrize(
        "mangled",
        [
            "1. [] 👀 待 review @carol i/2.md — Title 2",
            "1. [ ] 👀 待 review @carol i/2.md — Title 2".replace("1. ", ""),
        ],
    )
    def test_mangled_line_with_detail_path_is_not_a_dd(self, tmp_path, gh, mangled):
        make_board(tmp_path, row(1), row(2), details=(1, 2))
        sync.write_snapshot(tmp_path, REPO, NOW)
        make_board(tmp_path, row(1), mangled)
        result = plan(tmp_path, discovery=False)
        assert result["removed"] == []
        assert result["errors"]
        assert ledger_events(tmp_path) == []

    @pytest.mark.parametrize("state", ["missing", "empty"])
    def test_missing_or_empty_board_does_not_mass_drop(self, tmp_path, gh, state):
        make_board(tmp_path, row(1), row(2), details=(1, 2))
        sync.write_snapshot(tmp_path, REPO, NOW)
        board = tmp_path / ".maigo" / "board.md"
        if state == "missing":
            board.unlink()
        else:
            board.write_text("")
        result = plan(tmp_path, discovery=False)
        assert result["removed"] == []
        assert any("略過 dd" in e for e in result["errors"])
        assert ledger_events(tmp_path) == []


class TestRevive:
    def test_drop_then_revive_clears_exclusion(self, tmp_path, gh):
        make_board(tmp_path, row(1), details=(1,))
        sync.drop_urls(tmp_path, [url(5)], "drop", NOW)
        assert plan(tmp_path, discovery=False)["lines"][0]["excluded"] is False
        out = sync.revive_urls(tmp_path, [url(5, "issues")], "manual", NOW)
        assert out[0]["result"] == "revived"
        state, _ = sync.load_exclusions(state_dir(tmp_path) / "dropped.jsonl")
        assert state[sync.ref_key(url(5))]["excluded"] is False
        make_board(tmp_path, row(5), details=(5,))
        assert plan(tmp_path, discovery=False)["lines"][0]["excluded"] is False

    def test_revive_of_non_excluded_writes_nothing(self, tmp_path):
        out = sync.revive_urls(tmp_path, [url(5)], "manual", NOW)
        assert out[0]["result"] == "not_excluded"
        assert ledger_events(tmp_path) == []

    def test_cli_revive(self, tmp_path, capsys):
        root = ["--maigo-root", str(tmp_path), "--repo", REPO, "--you", YOU]
        sync.drop_urls(tmp_path, [url(5)], "drop", NOW)
        assert sync.main(["revive", "--reason", "manual", url(5), *root]) == 0
        assert json.loads(capsys.readouterr().out)[0]["result"] == "revived"


def test_dd_is_dated_at_snapshot_so_a_request_before_refresh_revives(tmp_path, gh):
    make_board(tmp_path, row(1), row(2), details=(1, 2))
    sync.write_snapshot(tmp_path, REPO, NOW - timedelta(hours=2))
    make_board(tmp_path, row(1))
    gh.requested = [pr(2)]
    gh.timeline = {
        2: [TestIsRerequested.event(YOU, (NOW - timedelta(hours=1)).isoformat())]
    }
    result = plan(tmp_path)
    assert [r["url"] for r in result["removed"]] == [url(2)]
    assert [r["url"] for r in result["revived"]] == [url(2)]
    assert [a["url"] for a in result["additions"]] == [url(2)]


class TestBoardTextAndTimes:
    def test_board_text_takes_precedence_over_disk(self, tmp_path, gh):
        make_board(tmp_path, row(1), details=(1,))
        override = board_text(row(2))
        put_detail(tmp_path, 2)
        result = plan(tmp_path, discovery=False, board_text=override)
        assert [line["url"] for line in result["lines"]] == [url(2)]

    def test_parse_header_extracts_repo(self):
        assert sync.parse_header(board_text(row(1)))["repo"] == REPO
        assert sync.parse_header("# Work Board\n")["repo"] is None
        assert sync.parse_header("")["raw"] == ""

    def test_removed_carries_the_snapshot_time_and_revived_carries_now(
        self, tmp_path, gh
    ):
        make_board(tmp_path, row(1), row(2), details=(1, 2))
        written = NOW - timedelta(hours=2)
        sync.write_snapshot(tmp_path, REPO, written)
        make_board(tmp_path, row(1))
        gh.requested = [pr(2)]
        gh.timeline = {
            2: [TestIsRerequested.event(YOU, (NOW - timedelta(hours=1)).isoformat())]
        }
        result = plan(tmp_path)
        assert result["removed"][0]["at"] == written.isoformat()
        assert result["revived"][0]["at"] == NOW.isoformat()


class TestAckDryRun:
    def item(self, change="checked"):
        return {"url": url(1), "head": HEAD, "change": change, "inferred": False}

    def test_dry_run_leaves_report_bytes_and_simulates_the_ack(self, tmp_path):
        path = Path(publish_report(tmp_path, 1)["path"])
        before = path.read_bytes()
        [result] = sync.ack_items(
            tmp_path, REPO, YOU, [self.item()], dry_run=True, now=NOW
        )
        assert path.read_bytes() == before
        assert result["result"] == "acked"
        simulated = result["simulated_review"]
        assert simulated["acknowledged_by"] == YOU
        assert simulated["acknowledged_at"] == NOW.isoformat()

    def test_dry_run_unack_simulates_removal(self, tmp_path):
        path = Path(publish_report(tmp_path, 1)["path"])
        sync.ack_items(tmp_path, REPO, YOU, [self.item()])
        before = path.read_bytes()
        [result] = sync.ack_items(
            tmp_path, REPO, YOU, [self.item("unchecked")], dry_run=True
        )
        assert path.read_bytes() == before
        assert result["result"] == "unacked"
        assert "acknowledged_at" not in result["simulated_review"]
