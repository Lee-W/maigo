"""Tests for hooks.delegation_criteria_check and the shared grep-criteria detector."""

from __future__ import annotations

import io
import json

import hooks.delegation_criteria_check as dcc
import pytest
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
            "- `git diff -U0 | grep '^+' | grep -c 'marker = '` 為 0",  # 明確限縮到加號行
            "- `git diff` 的新增行中 `grep -c 'marker = '` 為 0",  # 句內寫新增行＝正解
            "- 新增行不得有 grep 命中，數量為零",  # 同上
            "- 不要把 grep -c 為零 當驗收條件",  # 引用規則本身
            "- pytest exit 0、lint exit 0",  # 沒有 grep
            "- `grep -n foo bar.py` 找得到那一行",  # 沒有歸零斷言
            "背景說明：上次那個 grep 命中數為零，害我下了錯結論",
        ],
    )
    def test_legitimate_lines_are_not_flagged(self, line: str):
        assert find_literal_grep_criteria(line) == []

    def test_bare_git_diff_is_no_longer_scoped(self):
        # 2026-10-24 教訓：diff 的減號行與加號行混計，裸 git diff 不構成限縮。
        line = "- `git diff | grep -c 'marker = '` 為 0"
        assert len(find_literal_grep_criteria(line)) == 1

    def test_plus_prefixed_lines_are_scoped(self):
        assert find_literal_grep_criteria("- 加號開頭的行中 grep -c foo 為 0") == []
        assert find_literal_grep_criteria("- grep -c foo on the '^+' lines 為 0") == []
        assert (
            find_literal_grep_criteria("- grep -c foo on plus-prefixed lines 為 0")
            == []
        )

    @pytest.mark.parametrize(
        "line",
        [
            "驗收條件：grep -c foo x.py 等於 0",
            "驗收條件：grep -c foo x.py 必須等於 0",
            "驗收條件：grep -c foo x.py 等於零",
            "Acceptance: grep -c foo x.py must be 0",
            "Acceptance: grep -c foo x.py must equal 0",
            "Acceptance: grep -c foo x.py equals 0",
        ],
    )
    def test_equals_zero_phrasings_are_flagged(self, line: str):
        assert len(find_literal_grep_criteria(line)) == 1

    @pytest.mark.parametrize(
        "line",
        [
            "- `grep -c foo file` 的輸出不等於 0",
            "- `grep -c foo file` 的輸出不等於零",
            "- `rg foo` 命中數 must not equal 0",
            "- `rg foo` 命中數 must not be equal to 0",
            "- `rg foo` count does not equal 0",
            "- `rg foo` count doesn't equal 0",
        ],
    )
    def test_negated_equals_zero_is_positive_evidence_and_passes(self, line: str):
        assert find_literal_grep_criteria(line) == []

    def test_affirmative_equals_zero_still_flagged_next_to_negated_form(self):
        assert len(find_literal_grep_criteria("- `grep -c foo x` 等於 0")) == 1
        assert len(find_literal_grep_criteria("- `rg foo` count equals 0")) == 1

    def test_exit_code_zero_criterion_without_search_command_is_not_flagged(self):
        line = "驗收條件：測試結束碼必須等於 0；the exit code must equal 0"
        assert find_literal_grep_criteria(line) == []

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            pytest.param(
                "驗收條件：\n- grep -rn 'foo' src/ 回 0 筆", 1, id="s1_zh_baseline"
            ),
            pytest.param(
                "Acceptance:\n- rg 'foo' src/ returns zero matches",
                1,
                id="s2_en_zero_matches",
            ),
            pytest.param(
                "Acceptance criteria:\n- grep -rn 'foo' src/ returns no matches",
                1,
                id="s3_en_no_matches",
            ),
            pytest.param(
                "驗收條件：\n- git diff origin/main..HEAD | /usr/bin/grep -c 'checkout@v5' 為 0",
                1,
                id="s4_abs_path_bare_git_diff",
            ),
            pytest.param(
                "驗收條件：\n- $(grep -c 'foo' file.py) 必須等於 0",
                1,
                id="s5_command_substitution_equals_zero",
            ),
            pytest.param(
                "驗收條件：\n- `grep -c 'foo' file.py` 的輸出為 0",
                1,
                id="s6_backtick_output_is_zero",
            ),
            pytest.param(
                "驗收條件：\n- git diff -U0 origin/main..HEAD 的新增行中，grep 'foo' 回 0 筆",
                0,
                id="s7_scoped_to_added_lines",
            ),
            pytest.param(
                "注意：不要把驗收條件寫成「grep 某 pattern 回 0 筆」這種字面掃描。\n"
                "驗收條件：\n- 欄位名須來自共用常數",
                0,
                id="s8_quoting_the_rule",
            ),
        ],
    )
    def test_criteria_samples_block_or_pass(self, text: str, expected: int):
        assert len(find_literal_grep_criteria(text)) == expected

    def test_negation_written_form_is_not_flagged(self):
        # 2026-09-29 誤擋實例：語意型驗收條件用「不寫」明確否定字面 grep 版，
        # 曾被 _NEGATION_RE 漏收而誤擋。
        line = (
            "驗收條件（語意型，不寫「全檔 grep 為零」）："
            "`uvx ruff@0.16.8 check`／`format --check` 變更檔 exit 0；"
            "`uv run --project providers/common/ai mypy <變更 src 檔>` exit 0"
        )
        assert find_literal_grep_criteria(line) == []

    def test_still_flags_criteria_without_negation_wording(self):
        # 對照組：既有樣本沒有否定寫法，補完 _NEGATION_RE 後仍要照擋。
        line = "驗收條件：`grep -rn TODO src/` 應為 0"
        assert len(find_literal_grep_criteria(line)) == 1

    def test_hit_drops_bullet_and_checkbox_markers(self):
        (hit,) = find_literal_grep_criteria("- [ ] `grep -c TODO src/` 必須回 0")
        assert hit.startswith("`grep -c TODO")

    @pytest.mark.parametrize(
        "text",
        [
            # 兩個訊號同一行。
            "Forbidden: the literal string `foo_bar` must not appear anywhere.",
            # 軟換行版：句子跨行、續行沒有 bullet 標記（英文 plan 常見寫法）。
            "Forbidden: the literal strings `prompt_cache_retention` and\n"
            "`prompt_cache_options` must not appear anywhere in the page text",
        ],
    )
    def test_literal_string_ban_prose_is_flagged_without_grep_mention(self, text: str):
        assert len(find_literal_grep_criteria(text)) == 1

    @pytest.mark.parametrize(
        "text",
        [
            "no credentials must appear in the log",  # 講性質，沒有點名字面字串
            "the file must not contain tabs",  # 同上
            "- the literal string must not appear on added lines (新增行)",  # 限縮到新增行＝正解
            "- 不要把 the literal string must not appear 這種寫法當驗收條件",  # 引用規則本身
        ],
    )
    def test_literal_string_ban_prose_respects_scope_and_negation(self, text: str):
        assert find_literal_grep_criteria(text) == []

    def test_bare_git_diff_literal_string_ban_is_flagged(self):
        text = "- `git diff | grep -c` the literal string must not appear"
        assert len(find_literal_grep_criteria(text)) == 1

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
