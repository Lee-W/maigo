"""Tests for hooks.teammate_quality_check."""

from __future__ import annotations

import io
import json

import pytest

import hooks.teammate_quality_check as tqc
from tests.conftest import run_hook_main


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
        assert result["decision"] == "approve"

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
        assert result["decision"] == "approve"

    def test_chinese_headings_approves(self, capsys: pytest.CaptureFixture):
        with pytest.raises(SystemExit):
            tqc.check_tomori(
                "## Loaded memory entries\n（無相關 entry）\n"
                ".maigo/plan.md\n## 目標\n## 步驟\n"
            )
        result = json.loads(capsys.readouterr().out.strip())
        assert result["decision"] == "approve"

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
        assert result["decision"] == "approve"
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
            "## Loaded memory entries\n（無相關 entry）\n"
            "APPROVED\n[x] all good\n[x] verified\n",
            capsys,
        )
        assert result["decision"] == "approve"

    def test_blocked_with_checklist_and_must_fix_approves(self, capsys):
        result = self._run(
            "## Loaded memory entries\n（無相關 entry）\n"
            "BLOCKED\n[x] done\n[ ] pending\nmust-fix: broken import\n",
            capsys,
        )
        assert result["decision"] == "approve"

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
        "BLOCKED\n[x] done\n[ ] pending\n"
        "## Must-fix\n- `hooks/foo.py:10` — broken import\n"
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
        assert result["decision"] == "approve"
        # log file should exist with 1 line
        log_file = tmp_path / "soyo-must-fix.jsonl"
        assert log_file.is_file()
        lines = [line for line in log_file.read_text().splitlines() if line.strip()]
        assert len(lines) == 1

    def test_blocked_second_round_emits_retry_warning(
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
        assert result["decision"] == "block"
        assert "⚠️ RETRY LIMIT REACHED (Soyo):" in result["reason"]
        assert "hooks/foo.py" in result["reason"]
        assert "次" in result["reason"]

    def test_approved_does_not_write_log(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
        tmp_path,
    ):
        monkeypatch.setattr(tqc, "_RETRY_LOG_BASE", tmp_path)
        monkeypatch.chdir(tmp_path)
        approved_output = (
            "## Loaded memory entries\n（無相關 entry）\n"
            "APPROVED\n[x] all good\n[x] verified\n"
        )
        with pytest.raises(SystemExit):
            tqc.check_soyo(approved_output)
        result = json.loads(capsys.readouterr().out.strip())
        assert result["decision"] == "approve"
        # No log file should be written
        log_file = tmp_path / "soyo-must-fix.jsonl"
        assert not log_file.exists()

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
        # 1 from good existing line + 1 from current call = 2
        assert counts["foo.py"] == 2


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
        assert result["decision"] == "approve"

    def test_with_md_path_approves(self, capsys):
        result = self._run("更新了 docs/reference/hooks.md\n", capsys)
        assert result["decision"] == "approve"

    def test_hedge_language_does_not_block(self, capsys):
        result = self._run(
            "可能要先確認 X 是否需要再動。我改了 commands/retro.md\n", capsys
        )
        assert result["decision"] == "approve"

    def test_no_memory_header_does_not_block(self, capsys):
        result = self._run("我改了 hooks/check.py\n", capsys)
        assert result["decision"] == "approve"

    def test_url_with_md_does_not_approve(self, capsys):
        result = self._run(
            "詳見 https://example.com/doc.md，未改任何本地檔案\n", capsys
        )
        assert result["decision"] == "block"


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
            "teammate_output": (
                "## Loaded memory entries\n（無相關 entry）\n"
                ".maigo/plan.md\n## Goal\n## Steps\n"
            ),
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
            "teammate_output": (
                "## Loaded memory entries\n（無相關 entry）\n"
                ".maigo/plan.md\n## Goal\n## Steps\n"
            ),
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

    def test_anon_role_dispatches(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        payload = {
            "teammate_role": "Anon",
            "teammate_output": "我改了 hooks/teammate_quality_check.py",
        }
        result = run_hook_main(tqc, payload, monkeypatch, capsys)
        assert result["decision"] == "approve"
