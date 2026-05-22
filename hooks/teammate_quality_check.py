#!/usr/bin/env python3
"""Maigo TeammateIdle hook：各 agent 輸出規格檢查。

失敗時 block（要 agent 補完輸出）；輸入異常 / 角色未定義時 fail-open。
"""

from __future__ import annotations

import json
import re
import sys


def emit(decision: str, reason: str) -> None:
    payload = {"decision": decision, "reason": reason, "systemMessage": reason}
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.exit(0)


MEMORY_HEADER_RE = re.compile(r"##\s+Loaded memory entries", re.IGNORECASE)


def require_memory_header(out: str, role_zh: str) -> None:
    """Memory-reader agent 必須在輸出含 `## Loaded memory entries` 段。

    沒有相關 entry 也要明說「（無相關 entry）」——避免 silent skip。
    """
    if not MEMORY_HEADER_RE.search(out):
        emit(
            "block",
            f"{role_zh} 的輸出缺少 `## Loaded memory entries` 段。即使沒相關 entry，也要顯式寫出「（無相關 entry）」，不能 silent skip 跨專案記憶層。",
        )


def check_raana(out: str) -> None:
    require_memory_header(out, "樂奈 (Raana)")
    emit("approve", "樂奈 (Raana) 輸出含 memory 載入回報")


PR_DRAFT_RE = re.compile(r"##\s+Suggested PR title", re.IGNORECASE)


def check_tomori(out: str) -> None:
    require_memory_header(out, "燈 (Tomori)")

    # describe-pr 模式：燈產 PR 草稿，不寫 plan.md，結構照 github-title-description skill
    if PR_DRAFT_RE.search(out):
        if not re.search(r"##\s+Suggested PR description", out, re.IGNORECASE):
            emit(
                "block",
                "燈 (Tomori) 的 PR 草稿缺少 `## Suggested PR description` 段。"
                "describe-pr 要同時給 `## Suggested PR title` 與 `## Suggested PR description` 兩塊。",
            )
        emit("approve", "燈 (Tomori) PR 草稿結構齊全")

    # plan 模式（預設）：把計畫寫進 /tmp/maigo/<repo>/ 的檔案
    if not re.search(r"/tmp/maigo/[^/\s]+/(plan|review-rubric)\.md", out):
        emit(
            "block",
            "燈 (Tomori) 的輸出沒提到 /tmp/maigo/<repo>/plan.md 或 /tmp/maigo/<repo>/review-rubric.md。把計畫寫進那個檔案再回報。",
        )
    if not re.search(r"##\s+(Goal|Steps|Rubric|Acceptance|目標|步驟|期待|對照)", out):
        emit(
            "block",
            "燈 (Tomori) 的輸出缺少計畫結構（## Goal / ## Steps / ## Rubric / ## Acceptance / 目標 / 步驟）。",
        )
    emit("approve", "燈 (Tomori) 計畫結構齊全")


def check_soyo(out: str) -> None:
    require_memory_header(out, "爽世 (Soyo)")
    verdict_match = re.search(r"\b(APPROVED|NEEDS_CHANGES|BLOCKED)\b", out)
    if not verdict_match:
        emit(
            "block",
            "爽世 (Soyo) 的輸出沒看到 verdict（APPROVED / NEEDS_CHANGES / BLOCKED）。預設 BLOCKED，所有 review 都要明確寫出 verdict。",
        )
    verdict = verdict_match.group(1)

    if not re.search(r"\[[xX ]\]", out):
        emit(
            "block",
            "爽世 (Soyo) 的輸出缺少 checklist（[x] / [ ] 項目）。9 項強制檢查必須逐項標示。",
        )

    if verdict != "APPROVED":
        if not re.search(r"(must[-\s]?fix|改法|evidence|待補)", out, re.IGNORECASE):
            emit(
                "block",
                f"爽世 (Soyo) 給出 {verdict} 卻沒列 must-fix 或 evidence 待補。要擋就要說擋什麼、怎麼改。",
            )

    emit("approve", f"爽世 (Soyo) 輸出符合規格 (verdict={verdict})")


_URL_RE = re.compile(r"https?://\S+")
FILE_PATH_RE = re.compile(r"[\w./-]+\.(py|md|yml|yaml|json|toml|txt|sh|cfg)\b")


def check_anon(out: str) -> None:
    stripped = _URL_RE.sub("", out)
    if not FILE_PATH_RE.search(stripped):
        emit(
            "block",
            "愛音 (Anon) 的輸出沒看到任何檔案路徑 reference。"
            "implementer 必須具體指出動過哪個檔，不能只回『改好了』。"
            "格式例：`hooks/teammate_quality_check.py`、`tests/test_*.py`。",
        )
    emit("approve", "愛音 (Anon) 輸出含 file path reference")


def check_taki(out: str) -> None:
    if not re.search(r"exit\s+[0-9]+", out):
        emit(
            "block",
            "立希 (Taki) 沒看到 exit code。要拿真的 command 跑過，不是憑感覺說 PASS / FAIL。",
        )

    verdict_match = re.search(r"\b(PASS|FAIL)\b", out)
    if not verdict_match:
        emit("block", "立希 (Taki) 沒給最終 verdict（PASS / FAIL）。")
    verdict = verdict_match.group(1)

    hedge_patterns = [
        r"should\s+work",
        r"looks?\s+good",
        r"probably\s+fine",
        r"應該可以",
        r"看起來沒問題",
        r"大概沒問題",
    ]
    for pattern in hedge_patterns:
        if re.search(pattern, out, re.IGNORECASE):
            emit(
                "block",
                "立希 (Taki) 出現模糊語氣（'應該可以' / 'looks good' 之類）。verifier 只能拿 exit code 講話。",
            )

    emit("approve", f"立希 (Taki) 驗證結果完整 (verdict={verdict})")


ROLE_HANDLERS = {
    "Raana": check_raana,
    "explorer": check_raana,
    "Explorer": check_raana,
    "Tomori": check_tomori,
    "planner": check_tomori,
    "Planner": check_tomori,
    "Soyo": check_soyo,
    "reviewer": check_soyo,
    "Reviewer": check_soyo,
    "Taki": check_taki,
    "verifier": check_taki,
    "Verifier": check_taki,
    "Anon": check_anon,
    "implementer": check_anon,
    "Implementer": check_anon,
}


def main() -> None:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        emit("approve", "輸入不是有效 JSON，Maigo teammate check 跳過")

    role = (data.get("teammate_role") or "").strip()
    output = data.get("teammate_output") or ""

    if not role or not output:
        emit("approve", "輸入缺少 teammate_role 或 teammate_output，跳過")

    handler = ROLE_HANDLERS.get(role)
    if handler is None:
        emit("approve", f"{role}：未設規格，預設通過")

    handler(output)


if __name__ == "__main__":
    main()
