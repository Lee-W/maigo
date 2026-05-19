"""Tests for hooks.teammate_quality_check."""

from __future__ import annotations

import io
import json

import pytest

import hooks.teammate_quality_check as tqc
from tests.conftest import run_hook_main


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
            tqc.check_tomori("/tmp/maigo/myrepo/plan.md was written\n")
        result = json.loads(capsys.readouterr().out.strip())
        assert result["decision"] == "block"

    def test_path_and_heading_approves(self, capsys: pytest.CaptureFixture):
        with pytest.raises(SystemExit):
            tqc.check_tomori("/tmp/maigo/myrepo/plan.md\n## Goal\n## Steps\n")
        result = json.loads(capsys.readouterr().out.strip())
        assert result["decision"] == "approve"

    def test_chinese_headings_approves(self, capsys: pytest.CaptureFixture):
        with pytest.raises(SystemExit):
            tqc.check_tomori("/tmp/maigo/myrepo/plan.md\n## 目標\n## 步驟\n")
        result = json.loads(capsys.readouterr().out.strip())
        assert result["decision"] == "approve"


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
        result = self._run("APPROVED\n[x] all good\n[x] verified\n", capsys)
        assert result["decision"] == "approve"

    def test_blocked_with_checklist_and_must_fix_approves(self, capsys):
        result = self._run(
            "BLOCKED\n[x] done\n[ ] pending\nmust-fix: broken import\n", capsys
        )
        assert result["decision"] == "approve"

    def test_blocked_with_checklist_without_must_fix_blocks(self, capsys):
        result = self._run("BLOCKED\n[x] done\n[ ] pending\n", capsys)
        assert result["decision"] == "block"


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
        assert result["decision"] == "approve"


# ---------------------------------------------------------------------------
# main() dispatch
# ---------------------------------------------------------------------------


class TestMain:
    def test_tomori_role_dispatches(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        payload = {
            "teammate_role": "Tomori",
            "teammate_output": "/tmp/maigo/repo/plan.md\n## Goal\n## Steps\n",
        }
        result = run_hook_main(tqc, payload, monkeypatch, capsys)
        assert result["decision"] == "approve"

    def test_planner_alias_dispatches_to_tomori(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        payload = {
            "teammate_role": "planner",
            "teammate_output": "/tmp/maigo/repo/plan.md\n## Goal\n## Steps\n",
        }
        result = run_hook_main(tqc, payload, monkeypatch, capsys)
        assert result["decision"] == "approve"

    def test_unknown_role_fail_open_approves(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        payload = {
            "teammate_role": "SomeUnknownRole",
            "teammate_output": "whatever",
        }
        result = run_hook_main(tqc, payload, monkeypatch, capsys)
        assert result["decision"] == "approve"

    def test_invalid_json_fail_open_approves(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        monkeypatch.setattr("sys.stdin", io.StringIO("not json at all"))
        with pytest.raises(SystemExit):
            tqc.main()
        result = json.loads(capsys.readouterr().out.strip())
        assert result["decision"] == "approve"
