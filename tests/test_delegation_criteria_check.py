"""Tests for hooks.delegation_criteria_check and the shared grep-criteria detector."""

from __future__ import annotations

import io
import json

import pytest

import hooks.delegation_criteria_check as dcc
from hooks._grep_criteria import block_reason, find_literal_grep_criteria


def run_silent_hook(
    payload: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> str:
    """Run the hook's main() and return raw stdout (empty string = pass-through)."""
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    with pytest.raises(SystemExit) as exc:
        dcc.main()
    assert exc.value.code == 0
    return capsys.readouterr().out


class TestFindLiteralGrepCriteria:
    @pytest.mark.parametrize(
        "line",
        [
            "- [ ] `grep -c 'marker = ' uv.lock` 必須回 0",
            "- 全檔 grep 無「優化」「信息」，命中數為零",
            "1. `rg plugin-class` 只准剩一處，其餘為 0",
            "驗收條件：`grep -rn TODO src/` 應為 0",
        ],
    )
    def test_literal_grep_criteria_are_flagged(self, line: str):
        assert len(find_literal_grep_criteria(line)) == 1

    @pytest.mark.parametrize(
        "line",
        [
            "- `git diff | grep -c 'marker = '` 為 0",  # 限縮到本次改動＝正解
            "- 新增行不得有 grep 命中，數量為零",  # 同上
            "- 不要把 grep -c 為零 當驗收條件",  # 引用規則本身
            "- pytest exit 0、lint exit 0",  # 沒有 grep
            "- `grep -n foo bar.py` 找得到那一行",  # 沒有歸零斷言
            "背景說明：上次那個 grep 命中數為零，害我下了錯結論",
        ],
    )
    def test_legitimate_lines_are_not_flagged(self, line: str):
        assert find_literal_grep_criteria(line) == []

    def test_hit_drops_bullet_and_checkbox_markers(self):
        (hit,) = find_literal_grep_criteria("- [ ] `grep -c TODO src/` 必須回 0")
        assert hit.startswith("`grep -c TODO")

    def test_limit_caps_reported_hits(self):
        text = "\n".join(f"- `grep -c x{i} .` 為零" for i in range(10))
        assert len(find_literal_grep_criteria(text, limit=2)) == 2

    def test_block_reason_quotes_every_hit(self):
        reason = block_reason("交辦 prompt 的驗收條件", ["`grep -c a` 為零"])
        assert "`grep -c a` 為零" in reason
        assert "字面 grep 當判準" in reason
        assert "git diff" in reason


class TestDelegationCriteriaHook:
    def test_literal_grep_criterion_blocks(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ):
        payload = {
            "tool_name": "Agent",
            "tool_input": {
                "prompt": "目標：清掉舊欄位\n驗收條件：\n- `grep -c old_field .` 必須回 0\n"
            },
        }
        result = json.loads(run_silent_hook(payload, monkeypatch, capsys).strip())
        assert result["decision"] == "block"
        assert "grep -c old_field" in result["reason"]

    def test_clean_prompt_passes_silently(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ):
        payload = {
            "tool_name": "Agent",
            "tool_input": {"prompt": "驗收條件：\n- `uv run pytest` exit 0\n"},
        }
        assert run_silent_hook(payload, monkeypatch, capsys) == ""

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"tool_input": None},
            {"tool_input": {}},
            {"tool_input": {"prompt": "   "}},
            {"tool_input": {"prompt": 42}},
        ],
    )
    def test_malformed_input_fails_open(
        self,
        payload: dict,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        assert run_silent_hook(payload, monkeypatch, capsys) == ""

    def test_non_json_stdin_fails_open(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ):
        monkeypatch.setattr("sys.stdin", io.StringIO("not json at all"))
        with pytest.raises(SystemExit) as exc:
            dcc.main()
        assert exc.value.code == 0
        assert capsys.readouterr().out == ""
