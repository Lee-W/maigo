#!/usr/bin/env python3
"""Maigo PreToolUse hook：擋下寫入 `.maigo/` 底下舊固定檔名的產物。

背景：`scripts/artifact_path.py` 的 `<kind>-<id>.md` 命名規範存在近兩個月，跨
13 個實際安裝 maigo 的 repo 一查，採用率是 0%——不是規範不好，是散文說「一律
呼叫 `artifact_path.py`」，但沒有任何東西擋著一個趕時間的 agent 直接
`Write(".maigo/plan.md", ...)`。這支 hook 就是那個「東西」。

只匹配 `Write` / `Edit` 兩種工具。反向判準：`kind` 清單動態組自
`from artifact_path import _KNOWN_KINDS`（不重複列一份 kind 清單字面值），
regex 錨定在 `.maigo/` 目錄下，且必須是這幾個 kind 的**舊固定檔名**
（`<kind>.md`）——`plan-main.md` 這類已含識別碼的新命名不命中，因為 regex
要求 `<kind>.md` 前面沒有 `-<id>` 尾巴（stem 必須整個等於某個 kind）。

`board.md`（不在 `_KNOWN_KINDS` 裡）、`local-model-dispatch-plan.md`（stem 不
等於任何 kind）、`.maigo/i/9201.md`（不在 `.maigo/` 頂層）都天然不命中——白名單式
反向判準，不必為它們特別寫排除規則（呼應
`deny-by-default-when-tool-generates-paths` 記憶）。

命中時 block，訊息附上正確呼叫指令範例與
`skills/harness-discipline/references/artifact-ownership.md` 規則 4 的提醒；
不命中或輸入異常一律 fail-open，靜默放行——比照
`hooks/delegation_criteria_check.py` 的風格：PreToolUse 的 `approve` 等於跳過
權限系統，這個 hook 沒有資格代替使用者做那個決定，放行不輸出任何 decision
payload。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_io import emit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
try:
    from artifact_path import _KNOWN_KINDS
except Exception:
    # fail-open: `scripts/artifact_path.py` is still evolving (kinds get added,
    # syntax can momentarily break). An empty tuple makes `_KIND_ALTERNATION`
    # below an empty string, so `_LEGACY_ARTIFACT_RE` never matches anything —
    # no extra branch needed, this hook just silently stops blocking until the
    # import is fixed, instead of taking down every Write/Edit in every repo.
    _KNOWN_KINDS = ()

# 比對時先試最長的 kind，理由同 `scripts/maigo_dir_catalog.py`：避免短 kind
# （如 "review"）搶先吃掉長 kind 的檔名（如 "review-rubric.md"）。regex 本身
# 靠 `\.md$` 錨定與整體回溯就不會誤判，這裡沿用同一慣例只是為了可讀性一致。
_KINDS_BY_LENGTH_DESC = sorted(_KNOWN_KINDS, key=len, reverse=True)
_KIND_ALTERNATION = "|".join(re.escape(kind) for kind in _KINDS_BY_LENGTH_DESC)
_LEGACY_ARTIFACT_RE = re.compile(rf"(^|/)\.maigo/({_KIND_ALTERNATION})\.md$")


def is_legacy_artifact_path(file_path: str) -> str | None:
    """命中舊固定檔名回傳該 kind，否則回 `None`。純函式，不做任何 I/O。"""
    match = _LEGACY_ARTIFACT_RE.search(file_path)
    if match is None:
        return None
    return match.group(2)


def _block_reason(kind: str, file_path: str) -> str:
    return (
        f"`{file_path}` 是 `.maigo/` 底下舊固定檔名的 `{kind}` 產物，"
        "只可讀、不可當寫入目標（跨 13 個裝了 maigo 的 repo 實測，這套舊寫法的"
        "採用率仍是多數——散文擋不住，所以這裡改用程式碼擋）。\n"
        "改用：\n"
        f'  python3 scripts/artifact_path.py {kind} --topic "<H1 主題>"\n'
        "取得帶識別碼的新路徑（`path:` 那行），寫到那裡。\n"
        "見 skills/harness-discipline/references/artifact-ownership.md 規則 4："
        "舊固定檔名（`legacy_exists:` 那行指的檔案）只可讀、不可當寫入目標。"
    )


def _pass_through() -> NoReturn:
    """Silent fail-open: no decision payload, so the permission flow is untouched."""
    sys.exit(0)


def main() -> None:
    try:
        raw = sys.stdin.read()
        try:
            data = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            _pass_through()

        if data.get("tool_name") not in ("Write", "Edit"):
            _pass_through()

        tool_input = data.get("tool_input")
        if not isinstance(tool_input, dict):
            _pass_through()

        file_path = tool_input.get("file_path")
        if not isinstance(file_path, str) or not file_path.strip():
            _pass_through()

        kind = is_legacy_artifact_path(file_path)
        if kind:
            emit("block", _block_reason(kind, file_path))
        _pass_through()
    except SystemExit:
        raise
    except Exception:
        # Belt-and-suspenders fail-open, same spirit as `hooks/repo_detect.py`'s
        # top-level `try/except Exception` — any unforeseen error in this hook
        # must never take down the caller's Write/Edit. `_pass_through()` is
        # this hook's own established fail-open action (silent, no payload),
        # so reuse it here rather than `repo_detect.py`'s explicit
        # `emit("approve", "")` — the two hooks intentionally differ in
        # verbosity, not in the fail-open outcome.
        _pass_through()


if __name__ == "__main__":
    main()
