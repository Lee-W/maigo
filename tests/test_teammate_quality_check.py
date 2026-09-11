"""Tests for hooks.teammate_quality_check."""

from __future__ import annotations

import io
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import hooks.teammate_quality_check as tqc
from tests.conftest import run_hook_main


CHECKLIST = (
    "## Checklist\n"
    + "\n".join(
        f"- [x] {item}"
        for item in (
            "acceptance match",
            "evidence per function",
            "edge case coverage",
            "convention conformance",
            "no unsafe pattern",
            "no unexplained magic",
            "no TODO evasion",
            "no defensive bloat",
            "no completeness theatre",
        )
    )
    + "\n"
)
MEMORY = "## Loaded memory entries\n（無相關 entry）\n"


@pytest.fixture(autouse=True)
def _redirect_soyo_log_base(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Redirect tqc._RETRY_LOG_BASE to tmp_path for every test in this module.

    Prevents the real .maigo/ from being polluted and makes tests
    deterministic regardless of prior runs.
    """
    monkeypatch.setattr(tqc, "_RETRY_LOG_BASE", tmp_path)


# ---------------------------------------------------------------------------
# check_raana
# ---------------------------------------------------------------------------


class TestCheckRaana:
    def test_with_memory_header_approves(self, capsys: pytest.CaptureFixture):
        with pytest.raises(SystemExit):
            tqc.check_raana("## Loaded memory entries\n（無相關 entry）\n")
        result = json.loads(capsys.readouterr().out.strip())
        assert result.get("decision") is None

    def test_missing_memory_header_blocks(self, capsys: pytest.CaptureFixture):
        with pytest.raises(SystemExit):
            tqc.check_raana("some exploration notes without header\n")
        result = json.loads(capsys.readouterr().out.strip())
        assert result["decision"] == "block"
        assert "Loaded memory entries" in result["reason"]


# ---------------------------------------------------------------------------
# check_tomori
# ---------------------------------------------------------------------------


class TestCheckTomori:
    def test_no_plan_path_blocks(self, capsys: pytest.CaptureFixture):
        with pytest.raises(SystemExit):
            tqc.check_tomori("no plan mentioned here\n## Goal\n## Steps\n")
        result = json.loads(capsys.readouterr().out.strip())
        assert result["decision"] == "block"

    def test_plan_path_but_no_heading_blocks(self, capsys: pytest.CaptureFixture):
        with pytest.raises(SystemExit):
            tqc.check_tomori(".maigo/plan.md was written\n")
        result = json.loads(capsys.readouterr().out.strip())
        assert result["decision"] == "block"

    def test_path_and_heading_approves(self, capsys: pytest.CaptureFixture):
        with pytest.raises(SystemExit):
            tqc.check_tomori(
                "## Loaded memory entries\n（無相關 entry）\n"
                ".maigo/plan.md\n## Goal\n## Steps\n"
            )
        result = json.loads(capsys.readouterr().out.strip())
        assert result.get("decision") is None

    def test_chinese_headings_approves(self, capsys: pytest.CaptureFixture):
        with pytest.raises(SystemExit):
            tqc.check_tomori(
                "## Loaded memory entries\n（無相關 entry）\n"
                ".maigo/plan.md\n## 目標\n## 步驟\n"
            )
        result = json.loads(capsys.readouterr().out.strip())
        assert result.get("decision") is None

    def test_missing_memory_header_blocks(self, capsys: pytest.CaptureFixture):
        with pytest.raises(SystemExit):
            tqc.check_tomori(".maigo/plan.md\n## Goal\n## Steps\n")
        result = json.loads(capsys.readouterr().out.strip())
        assert result["decision"] == "block"
        assert "Loaded memory entries" in result["reason"]

    def test_pr_draft_mode_approves(self, capsys: pytest.CaptureFixture):
        # describe-pr 模式：有 PR title + description 兩塊就過，不要求 plan.md
        with pytest.raises(SystemExit):
            tqc.check_tomori(
                "## Loaded memory entries\n（無相關 entry）\n"
                "## Suggested PR title\nReject empty emails at signup\n"
                "## Suggested PR description\n## Summary\n...\n"
            )
        result = json.loads(capsys.readouterr().out.strip())
        assert result.get("decision") is None
        assert "PR 草稿" in result["reason"]

    def test_pr_draft_missing_description_blocks(self, capsys: pytest.CaptureFixture):
        with pytest.raises(SystemExit):
            tqc.check_tomori(
                "## Loaded memory entries\n（無相關 entry）\n"
                "## Suggested PR title\nReject empty emails at signup\n"
            )
        result = json.loads(capsys.readouterr().out.strip())
        assert result["decision"] == "block"
        assert "Suggested PR description" in result["reason"]

    def test_pr_draft_missing_memory_header_blocks(self, capsys: pytest.CaptureFixture):
        with pytest.raises(SystemExit):
            tqc.check_tomori(
                "## Suggested PR title\nx\n## Suggested PR description\n## Summary\ny\n"
            )
        result = json.loads(capsys.readouterr().out.strip())
        assert result["decision"] == "block"
        assert "Loaded memory entries" in result["reason"]

    def test_triage_rubric_with_category_approves(self, capsys: pytest.CaptureFixture):
        with pytest.raises(SystemExit):
            tqc.check_tomori(
                "## Loaded memory entries\n（無相關 entry）\n"
                "## Triage rubric\n"
                ".maigo/triage-rubric.md\n"
                "## Category\nbug\n"
            )
        result = json.loads(capsys.readouterr().out.strip())
        assert result.get("decision") is None

    def test_triage_path_but_no_category_heading_blocks(
        self, capsys: pytest.CaptureFixture
    ):
        with pytest.raises(SystemExit):
            tqc.check_tomori(
                "## Loaded memory entries\n（無相關 entry）\n"
                ".maigo/triage-rubric.md\n"  # path mentioned, no structural heading
            )
        result = json.loads(capsys.readouterr().out.strip())
        assert result["decision"] == "block"
        assert "結構" in result["reason"]

    def test_review_rubric_with_rubric_heading_approves(
        self, capsys: pytest.CaptureFixture
    ):
        with pytest.raises(SystemExit):
            tqc.check_tomori(
                "## Loaded memory entries\n（無相關 entry）\n"
                ".maigo/review-rubric-71380.md\n## Rubric\n"
            )
        result = json.loads(capsys.readouterr().out.strip())
        assert result.get("decision") is None


# ---------------------------------------------------------------------------
# check_tomori — plan 驗收條件的字面 grep 判準（教訓家族「字面 grep 當判準」）
# ---------------------------------------------------------------------------


class TestTomoriPlanCriteria:
    OUT = "## Loaded memory entries\n（無相關 entry）\n.maigo/plan-x.md\n## Steps\n"

    @staticmethod
    def _write_plan(tmp_path, body: str) -> None:
        plan_dir = tmp_path / ".maigo"
        plan_dir.mkdir(exist_ok=True)
        (plan_dir / "plan-x.md").write_text(body, encoding="utf-8")

    def test_literal_grep_criterion_in_plan_blocks(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ):
        self._write_plan(
            tmp_path, "## Acceptance\n- [ ] `grep -c old_field .` 必須回 0\n"
        )
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            tqc.check_tomori(self.OUT)
        result = json.loads(capsys.readouterr().out.strip())
        assert result["decision"] == "block"
        assert "字面 grep 當判準" in result["reason"]

    def test_scoped_grep_criterion_in_plan_approves(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ):
        self._write_plan(
            tmp_path, "## Acceptance\n- [ ] `git diff | grep -c old_field` 為 0\n"
        )
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            tqc.check_tomori(self.OUT)
        result = json.loads(capsys.readouterr().out.strip())
        assert result.get("decision") is None

    def test_missing_plan_file_fails_open(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            tqc.check_tomori(self.OUT)
        result = json.loads(capsys.readouterr().out.strip())
        assert result.get("decision") is None


# ---------------------------------------------------------------------------
# _TOMORI_ARTIFACT_RE — accepts both the old fixed filenames and the new
# identifier-suffixed ones (`.maigo/plan-maigo-artifact-collision.md` Step 11)
# ---------------------------------------------------------------------------


class TestTomoriArtifactRegex:
    @pytest.mark.parametrize(
        "text",
        [
            pytest.param(".maigo/plan.md", id="old-plan"),
            pytest.param(".maigo/review-rubric.md", id="old-review-rubric"),
            pytest.param(".maigo/triage-rubric.md", id="old-triage-rubric"),
            pytest.param(".maigo/plan-fix-dag-run-stall.md", id="new-plan"),
            pytest.param(".maigo/review-rubric-71380.md", id="new-review-rubric"),
            pytest.param(
                ".maigo/triage-rubric-airflow-9201.md", id="new-triage-rubric"
            ),
        ],
    )
    def test_matches_old_and_new_forms(self, text: str):
        assert tqc._TOMORI_ARTIFACT_RE.search(text)

    @pytest.mark.parametrize(
        "text",
        [
            pytest.param(".maigo/plan-.md", id="empty-identifier"),
            pytest.param(".maigo/plan--x.md", id="hyphen-leading-identifier"),
        ],
    )
    def test_rejects_malformed_identifier(self, text: str):
        assert tqc._TOMORI_ARTIFACT_RE.search(text) is None


# ---------------------------------------------------------------------------
# check_soyo
# ---------------------------------------------------------------------------


class TestCheckSoyo:
    def _run(self, text: str, capsys: pytest.CaptureFixture):
        with pytest.raises(SystemExit):
            tqc.check_soyo(text)
        return json.loads(capsys.readouterr().out.strip())

    def test_no_verdict_blocks(self, capsys):
        result = self._run("Some review without verdict\n[x] item done\n", capsys)
        assert result["decision"] == "block"

    def test_verdict_but_no_checklist_blocks(self, capsys):
        result = self._run("APPROVED but no checklist items", capsys)
        assert result["decision"] == "block"

    def test_needs_changes_without_must_fix_blocks(self, capsys):
        result = self._run("NEEDS_CHANGES\n[x] checked\n[ ] not done\n", capsys)
        assert result["decision"] == "block"

    def test_approved_with_checklist_approves(self, capsys):
        result = self._run(
            "## Loaded memory entries\n（無相關 entry）\nAPPROVED\n" + CHECKLIST,
            capsys,
        )
        assert result.get("decision") is None

    def test_blocked_with_checklist_and_must_fix_approves(self, capsys):
        result = self._run(
            "## Loaded memory entries\n（無相關 entry）\n"
            "BLOCKED\n" + CHECKLIST + "must-fix: broken import\n",
            capsys,
        )
        assert result.get("decision") is None

    def test_missing_memory_header_blocks(self, capsys):
        result = self._run("APPROVED\n[x] all good\n[x] verified\n", capsys)
        assert result["decision"] == "block"
        assert "Loaded memory entries" in result["reason"]

    def test_blocked_with_checklist_without_must_fix_blocks(self, capsys):
        result = self._run("BLOCKED\n[x] done\n[ ] pending\n", capsys)
        assert result["decision"] == "block"


# ---------------------------------------------------------------------------
# Soyo retry count (must-fix persistence)
# ---------------------------------------------------------------------------


class TestSoyoRetryCount:
    """Tests for _extract_soyo_must_fix_keys, _soyo_log_path, _soyo_record_and_count,
    and the retry-count logic inside check_soyo."""

    _BLOCKED_OUTPUT = (
        "## Loaded memory entries\n（無相關 entry）\n"
        "BLOCKED\n" + CHECKLIST + "## Must-fix\n- `hooks/foo.py:10` — broken import\n"
    )

    def test_extract_must_fix_keys_with_file_ref(self):
        out = "## Must-fix\n- `hooks/foo.py` — something wrong\n"
        keys = tqc._extract_soyo_must_fix_keys(out)
        assert keys == {"hooks/foo.py"}

    def test_extract_must_fix_keys_strips_line_number(self):
        out = "## Must-fix\n- `foo.py:42` — broken import\n"
        keys = tqc._extract_soyo_must_fix_keys(out)
        assert keys == {"foo.py"}

    def test_extract_must_fix_keys_fallback_no_file(self):
        out = "## Must-fix\n- must-fix: rename var X to Y\n"
        keys = tqc._extract_soyo_must_fix_keys(out)
        assert len(keys) == 1
        key = next(iter(keys))
        assert key != ""

    def test_extract_must_fix_keys_empty_returns_empty_set(self):
        assert tqc._extract_soyo_must_fix_keys("") == set()
        assert tqc._extract_soyo_must_fix_keys("APPROVED\n[x] ok\n") == set()

    def test_blocked_first_round_no_warning(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
        tmp_path,
    ):
        monkeypatch.setattr(tqc, "_RETRY_LOG_BASE", tmp_path)
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            tqc.check_soyo(self._BLOCKED_OUTPUT)
        result = json.loads(capsys.readouterr().out.strip())
        assert result.get("decision") is None
        # log file should exist with 1 line
        log_file = tmp_path / "soyo-must-fix.jsonl"
        assert log_file.is_file()
        lines = [line for line in log_file.read_text().splitlines() if line.strip()]
        assert len(lines) == 1

    def test_legacy_history_does_not_trigger_retry_warning(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
        tmp_path,
    ):
        monkeypatch.setattr(tqc, "_RETRY_LOG_BASE", tmp_path)
        monkeypatch.chdir(tmp_path)
        # Pre-write one log entry with the same key
        log_dir = tmp_path
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "soyo-must-fix.jsonl"
        import json as _json

        log_file.write_text(
            _json.dumps(
                {"ts": "2026-01-01T00:00:00Z", "must_fix_keys": ["hooks/foo.py"]}
            )
            + "\n"
        )
        with pytest.raises(SystemExit):
            tqc.check_soyo(self._BLOCKED_OUTPUT)
        result = json.loads(capsys.readouterr().out.strip())
        assert result.get("decision") is None
        assert "RETRY LIMIT" not in result["reason"]

    def test_approved_records_empty_keys_to_reset_streak(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
        tmp_path,
    ):
        monkeypatch.setattr(tqc, "_RETRY_LOG_BASE", tmp_path)
        monkeypatch.chdir(tmp_path)
        approved_output = (
            "## Loaded memory entries\n（無相關 entry）\nAPPROVED\n" + CHECKLIST
        )
        with pytest.raises(SystemExit):
            tqc.check_soyo(approved_output)
        result = json.loads(capsys.readouterr().out.strip())
        assert result.get("decision") is None
        # An approved result ends the previous failure streak.
        log_file = tmp_path / "soyo-must-fix.jsonl"
        assert json.loads(log_file.read_text())["must_fix_keys"] == []

    def test_corrupted_log_line_does_not_crash(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ):
        monkeypatch.setattr(tqc, "_RETRY_LOG_BASE", tmp_path)
        import json as _json

        log_file = tmp_path / "soyo-must-fix.jsonl"
        # Write one corrupted line + one good line
        log_file.write_text(
            "{bad json\n"
            + _json.dumps({"ts": "2026-01-01T00:00:00Z", "must_fix_keys": ["foo.py"]})
            + "\n"
        )
        counts = tqc._soyo_record_and_count(log_file, {"foo.py"})
        # Historical entries have no task identity.
        assert counts["foo.py"] == 1


# ---------------------------------------------------------------------------
# check_taki
# ---------------------------------------------------------------------------


class TestCheckTaki:
    def _run(self, text: str, capsys: pytest.CaptureFixture):
        with pytest.raises(SystemExit):
            tqc.check_taki(text)
        return json.loads(capsys.readouterr().out.strip())

    def test_no_exit_code_blocks(self, capsys):
        result = self._run("PASS looks good", capsys)
        assert result["decision"] == "block"

    def test_exit_code_but_no_pass_fail_blocks(self, capsys):
        result = self._run("exit 0 but nothing else", capsys)
        assert result["decision"] == "block"

    def test_hedge_language_blocks(self, capsys):
        result = self._run("exit 0\nPASS\nshould work fine", capsys)
        assert result["decision"] == "block"

    def test_clean_pass_approves(self, capsys):
        result = self._run("exit 0\nPASS\nAll tests passed.", capsys)
        assert result.get("decision") is None

    @pytest.mark.parametrize("exit_code", [1, -1, 137])
    def test_pass_with_nonzero_exit_blocks(self, exit_code, capsys):
        result = self._run(f"PASS\nexit {exit_code}", capsys)
        assert result["decision"] == "block"


# ---------------------------------------------------------------------------
# check_anon
# ---------------------------------------------------------------------------


class TestCheckAnon:
    def _run(self, text: str, capsys: pytest.CaptureFixture):
        with pytest.raises(SystemExit):
            tqc.check_anon(text)
        return json.loads(capsys.readouterr().out.strip())

    def test_no_file_path_blocks(self, capsys):
        result = self._run("改好了\n", capsys)
        assert result["decision"] == "block"
        assert "file path" in result["reason"] or "檔案路徑" in result["reason"]

    def test_with_py_path_approves(self, capsys):
        result = self._run("我動了 hooks/foo.py\n", capsys)
        assert result.get("decision") is None

    def test_with_md_path_approves(self, capsys):
        result = self._run("更新了 docs/reference/hooks.md\n", capsys)
        assert result.get("decision") is None

    def test_hedge_language_does_not_block(self, capsys):
        result = self._run(
            "可能要先確認 X 是否需要再動。我改了 commands/retro.md\n", capsys
        )
        assert result.get("decision") is None

    def test_no_memory_header_does_not_block(self, capsys):
        result = self._run("我改了 hooks/check.py\n", capsys)
        assert result.get("decision") is None

    def test_url_with_md_does_not_approve(self, capsys):
        result = self._run(
            "詳見 https://example.com/doc.md，未改任何本地檔案\n", capsys
        )
        assert result["decision"] == "block"


# ---------------------------------------------------------------------------
# main() dispatch
# ---------------------------------------------------------------------------


class TestMain:
    @pytest.mark.parametrize(
        ("role", "output", "blocked"),
        [
            ("maigo:Soyo", MEMORY + "APPROVED\n" + CHECKLIST, False),
            ("maigo:Soyo", MEMORY + "APPROVED\n## Checklist\n- [x] done", True),
            (
                "maigo:Soyo",
                MEMORY + "APPROVED\n" + CHECKLIST.replace("[x]", "[ ]", 1),
                True,
            ),
            ("maigo:Soyo", MEMORY + "READY\n" + CHECKLIST, False),
            ("maigo:Taki", "PASS\nexit 1", True),
            ("maigo:Taki", "PASS\nexit 0", False),
            ("maigo:Anon", "Updated src/example.py", False),
            ("maigo:Anon", "", True),
            ("other-plugin:Soyo", "", False),
        ],
    )
    def test_documented_subagent_stop_contract(self, role, output, blocked, tmp_path):
        root = Path(__file__).resolve().parents[1]
        payload = {
            "hook_event_name": "SubagentStop",
            "session_id": "test-session",
            "agent_id": "test-agent",
            "agent_type": role,
            "cwd": str(tmp_path),
            "stop_hook_active": False,
            "transcript_path": str(tmp_path / "parent.jsonl"),
            "agent_transcript_path": str(tmp_path / "agent.jsonl"),
            "last_assistant_message": output,
        }
        proc = subprocess.run(
            [sys.executable, str(root / "hooks/teammate_quality_check.py")],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        assert proc.returncode == 0
        assert not proc.stderr
        result = json.loads(proc.stdout)
        assert result.get("decision") == ("block" if blocked else None)

    def test_registered_event_matches_maigo_only(self):
        root = Path(__file__).resolve().parents[1]
        hooks = json.loads((root / "hooks/hooks.json").read_text())["hooks"]
        assert "TeammateIdle" not in hooks
        matcher = hooks["SubagentStop"][0]["matcher"]
        for agent in (root / "agents").glob("*.md"):
            assert re.fullmatch(matcher, f"maigo:{agent.stem}")
        assert not re.fullmatch(matcher, "other-plugin:Soyo")

    def test_quick_skips_only_optional_items(self, monkeypatch, capsys):
        rows = CHECKLIST.splitlines()
        for index in (2, 3, 6, 8, 9):
            rows[index] = rows[index].replace("[x]", "[—]") + " — skipped by mode=quick"
        output = MEMORY + "APPROVED\n" + "\n".join(rows)
        result = run_hook_main(
            tqc,
            {"agent_type": "maigo:Soyo", "last_assistant_message": output},
            monkeypatch,
            capsys,
        )
        assert result.get("decision") is None
        output = output.replace("[x] acceptance match", "[—] acceptance match")
        result = run_hook_main(
            tqc,
            {"agent_type": "maigo:Soyo", "last_assistant_message": output},
            monkeypatch,
            capsys,
        )
        assert result["decision"] == "block"

    def test_tomori_role_dispatches(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        payload = {
            "agent_type": "Tomori",
            "last_assistant_message": (
                "## Loaded memory entries\n（無相關 entry）\n"
                ".maigo/plan.md\n## Goal\n## Steps\n"
            ),
        }
        result = run_hook_main(tqc, payload, monkeypatch, capsys)
        assert result.get("decision") is None

    def test_planner_alias_dispatches_to_tomori(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        payload = {
            "agent_type": "planner",
            "last_assistant_message": (
                "## Loaded memory entries\n（無相關 entry）\n"
                ".maigo/plan.md\n## Goal\n## Steps\n"
            ),
        }
        result = run_hook_main(tqc, payload, monkeypatch, capsys)
        assert result.get("decision") is None

    def test_unknown_role_fail_open_approves(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        payload = {
            "agent_type": "SomeUnknownRole",
            "last_assistant_message": "whatever",
        }
        result = run_hook_main(tqc, payload, monkeypatch, capsys)
        assert result.get("decision") is None

    def test_invalid_json_fail_open_approves(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        monkeypatch.setattr("sys.stdin", io.StringIO("not json at all"))
        with pytest.raises(SystemExit):
            tqc.main()
        result = json.loads(capsys.readouterr().out.strip())
        assert result.get("decision") is None

    def test_anon_role_dispatches(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        payload = {
            "agent_type": "Anon",
            "last_assistant_message": "我改了 hooks/teammate_quality_check.py",
        }
        result = run_hook_main(tqc, payload, monkeypatch, capsys)
        assert result.get("decision") is None


def test_real_subagent_events_scope_retry_and_approval_reset(tmp_path):
    script = Path(__file__).resolve().parents[1] / "hooks/teammate_quality_check.py"
    blocked = (
        MEMORY
        + "BLOCKED\n"
        + CHECKLIST
        + "## Must-fix\n- `src/app.py` — broken import\n"
    )
    approved = MEMORY + "APPROVED\n" + CHECKLIST

    def run(output=blocked, session="session", agent="review-task"):
        proc = subprocess.run(
            [sys.executable, str(script)],
            input=json.dumps(
                {
                    "hook_event_name": "SubagentStop",
                    "session_id": session,
                    "agent_id": agent,
                    "agent_type": "maigo:Soyo",
                    "cwd": str(tmp_path),
                    "last_assistant_message": output,
                }
            ),
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0 and not proc.stderr
        return json.loads(proc.stdout)

    assert "RETRY LIMIT" not in run()["reason"]
    assert "RETRY LIMIT" not in run(agent="another-task")["reason"]
    assert "RETRY LIMIT" not in run(session="another-session")["reason"]
    assert "RETRY LIMIT" in run()["reason"]
    assert run(approved).get("decision") is None
    assert "RETRY LIMIT" not in run()["reason"]
