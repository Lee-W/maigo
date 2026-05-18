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


def check_tomori(out: str) -> None:
    if not re.search(r"/tmp/maigo/[^/\s]+/(plan|review-rubric)\.md", out):
        emit("block", "燈 (Tomori) 的輸出沒提到 /tmp/maigo/<repo>/plan.md 或 /tmp/maigo/<repo>/review-rubric.md。把計畫寫進那個檔案再回報。")
    if not re.search(r"##\s+(Goal|Steps|Rubric|Acceptance|目標|步驟|期待|對照)", out):
        emit("block", "燈 (Tomori) 的輸出缺少計畫結構（## Goal / ## Steps / ## Rubric / ## Acceptance / 目標 / 步驟）。")
    emit("approve", "燈 (Tomori) 計畫結構齊全")


def check_soyo(out: str) -> None:
    verdict_match = re.search(r"\b(APPROVED|NEEDS_CHANGES|BLOCKED)\b", out)
    if not verdict_match:
        emit("block", "爽世 (Soyo) 的輸出沒看到 verdict（APPROVED / NEEDS_CHANGES / BLOCKED）。預設 BLOCKED，所有 review 都要明確寫出 verdict。")
    verdict = verdict_match.group(1)

    if not re.search(r"\[[xX ]\]", out):
        emit("block", "爽世 (Soyo) 的輸出缺少 checklist（[x] / [ ] 項目）。八項強制檢查必須逐項標示。")

    if verdict != "APPROVED":
        if not re.search(r"(must[-\s]?fix|改法|evidence|待補)", out, re.IGNORECASE):
            emit("block", f"爽世 (Soyo) 給出 {verdict} 卻沒列 must-fix 或 evidence 待補。要擋就要說擋什麼、怎麼改。")

    emit("approve", f"爽世 (Soyo) 輸出符合規格 (verdict={verdict})")


def check_taki(out: str) -> None:
    if not re.search(r"exit\s+[0-9]+", out):
        emit("block", "立希 (Taki) 沒看到 exit code。要拿真的 command 跑過，不是憑感覺說 PASS / FAIL。")

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
            emit("block", "立希 (Taki) 出現模糊語氣（'應該可以' / 'looks good' 之類）。verifier 只能拿 exit code 講話。")

    emit("approve", f"立希 (Taki) 驗證結果完整 (verdict={verdict})")


ROLE_HANDLERS = {
    "Tomori": check_tomori,
    "planner": check_tomori,
    "Planner": check_tomori,
    "Soyo": check_soyo,
    "reviewer": check_soyo,
    "Reviewer": check_soyo,
    "Taki": check_taki,
    "verifier": check_taki,
    "Verifier": check_taki,
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
