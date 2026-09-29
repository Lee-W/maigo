#!/usr/bin/env python3
"""
Maigo PreToolUse hook：擋下寫入 `.maigo/` 底下舊固定檔名／分目錄前扁平檔的產物。

背景：`scripts/artifact_path.py` 的命名規範存在近兩個月，跨 13 個實際安裝
maigo 的 repo 一查，採用率是 0%——不是規範不好，是散文說「一律呼叫
`artifact_path.py`」，但沒有任何東西擋著一個趕時間的 agent 直接
`Write(".maigo/plan.md", ...)`。這支 hook 就是那個「東西」。後續佈局改成
按 PR/issue 分資料夾（`review/<id>/*.md`、`issue/<id>/*.md`）後，同一問題多
了一種新形狀——分目錄前的扁平 `<kind>-<id>.md`（如 `review-rubric-42.md`）
手寫路徑正是散文漏網的實例——這支 hook 現在同時擋這兩種寫法。

只匹配 `Write` / `Edit` 兩種工具。反向判準：`kind` 清單動態組自
`from artifact_path import _KNOWN_KINDS`（不重複列一份 kind 清單字面值），
regex 錨定在 `.maigo/` 目錄下：

1. **舊固定檔名**（`<kind>.md`）——`plan-main.md` 這類已含識別碼的新命名不
   命中，因為 regex 要求 `<kind>.md` 前面沒有 `-<id>` 尾巴（stem 必須整個
   等於某個 kind）。
2. **巢狀 kind 的分目錄前扁平檔**（`<kind>-<id>.md`，`kind` 屬於
   `_NESTED_LAYOUT`）——`_FLAT_NAME_LOOKALIKES`（`review-batch-state.md` /
   `review-board.md`）字面上符合這個形狀但不是 review kind 的產物，先排除
   才不會誤擋。

`board.md`（不在 `_KNOWN_KINDS` 裡）、`local-model-dispatch-plan.md`（stem 不
等於任何 kind）、`.maigo/i/9201.md`（不在 `.maigo/` 頂層）、
`.maigo/review/42/rubric.md`（新巢狀路徑本身）都天然不命中——白名單式
反向判準，不必為它們特別寫排除規則（呼應
`deny-by-default-when-tool-generates-paths` 記憶）。

命中時 block，訊息附上正確呼叫指令範例、（分目錄前扁平檔另提
`scripts/migrate_legacy_artifacts.py` 可搬既有檔）與
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
    from artifact_path import _FLAT_NAME_LOOKALIKES, _KNOWN_KINDS, _NESTED_LAYOUT
except Exception:
    # fail-open: `scripts/artifact_path.py` is still evolving (kinds get added,
    # syntax can momentarily break). Empty containers make both alternations
    # below empty strings, so neither regex ever matches anything — no extra
    # branch needed, this hook just silently stops blocking until the import
    # is fixed, instead of taking down every Write/Edit in every repo.
    _KNOWN_KINDS = ()
    _NESTED_LAYOUT = {}
    _FLAT_NAME_LOOKALIKES = ()

# 比對時先試最長的 kind，理由同 `scripts/maigo_dir_catalog.py`：避免短 kind
# （如 "review"）搶先吃掉長 kind 的檔名（如 "review-rubric.md"）。regex 本身
# 靠 `\.md$` 錨定與整體回溯就不會誤判，這裡沿用同一慣例只是為了可讀性一致。
_KINDS_BY_LENGTH_DESC = sorted(_KNOWN_KINDS, key=len, reverse=True)
_KIND_ALTERNATION = "|".join(re.escape(kind) for kind in _KINDS_BY_LENGTH_DESC)
_LEGACY_ARTIFACT_RE = re.compile(rf"(^|/)\.maigo/({_KIND_ALTERNATION})\.md$")

# 巢狀 kind 的分目錄前扁平檔（`<kind>-<id>.md`，`kind` 屬於 `_NESTED_LAYOUT`）
# ——決策 3：這也要擋，`.maigo/` 命名規範曾經只靠散文、採用率 0%。
_NESTED_KINDS_BY_LENGTH_DESC = sorted(_NESTED_LAYOUT, key=len, reverse=True)
_NESTED_KIND_ALTERNATION = "|".join(
    re.escape(kind) for kind in _NESTED_KINDS_BY_LENGTH_DESC
)
_FLAT_PRE_NESTED_ARTIFACT_RE = re.compile(
    rf"(^|/)\.maigo/({_NESTED_KIND_ALTERNATION})-[A-Za-z0-9][\w.-]*\.md$"
)


def is_legacy_artifact_path(file_path: str) -> str | None:
    """命中舊固定檔名回傳該 kind，否則回 `None`。純函式，不做任何 I/O。"""
    match = _LEGACY_ARTIFACT_RE.search(file_path)
    if match is None:
        return None
    return match.group(2)


def is_flat_pre_nested_artifact_path(file_path: str) -> str | None:
    """
    命中巢狀 kind 的分目錄前扁平檔（`<kind>-<id>.md`）回傳該 kind，否則 `None`。

    `_FLAT_NAME_LOOKALIKES` 先排除——那兩個檔名字面上符合 `<review-kind>-<尾巴>.md`
    的形狀，但不是 review kind 的產物（見 `scripts/artifact_path.py` 模組內
    各自的理由註解），不能被這支誤擋。同理，`is_legacy_artifact_path()` 已經
    命中的舊固定檔名（例：`review-rubric.md` 的 stem 整個等於 kind
    `review-rubric`）也要排除——不然較短的 `review` 會在 regex 回溯時把它
    誤讀成 kind="review"、id="rubric" 的分目錄前扁平檔。純函式，不做任何 I/O。
    """
    basename = file_path.rsplit("/", 1)[-1]
    if basename in _FLAT_NAME_LOOKALIKES:
        return None
    if is_legacy_artifact_path(file_path) is not None:
        return None
    match = _FLAT_PRE_NESTED_ARTIFACT_RE.search(file_path)
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


def _flat_pre_nested_block_reason(kind: str, file_path: str) -> str:
    return (
        f"`{file_path}` 是巢狀佈局採用前的分目錄前扁平 `{kind}` 產物，"
        "只可讀、不可當寫入目標——新路徑收進 `.maigo/review/<id>/` 或 "
        "`.maigo/issue/<id>/` 底下的資料夾。\n"
        "改用：\n"
        f'  python3 scripts/artifact_path.py {kind} --topic "<H1 主題>" '
        "[--url <url> --repo <owner/name>]\n"
        "取得巢狀新路徑（`path:` 那行），寫到那裡；既有舊檔可用 "
        "`scripts/migrate_legacy_artifacts.py` 搬過去，不必手動搬。\n"
        "見 skills/harness-discipline/references/artifact-ownership.md 規則 4："
        "分目錄前的扁平檔（`flat_exists:` 那行指的檔案）只可讀、不可當寫入目標。"
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
        flat_kind = is_flat_pre_nested_artifact_path(file_path)
        if flat_kind:
            emit("block", _flat_pre_nested_block_reason(flat_kind, file_path))
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
