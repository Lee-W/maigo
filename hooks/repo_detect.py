#!/usr/bin/env python3
"""Maigo SessionStart hook：偵測目前 repo，自動 dispatch 對應的 project-aware 知識。

命中 → emit systemMessage 要求 agent 載入對應 skill。
未命中 → silent approve（空 systemMessage）。
任何 exception → fail-open approve + stderr 一行。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

REPO_RULES: list[dict] = [
    {
        "name": "apache-airflow",
        "skill": "airflow-aware",
        "detectors": [
            {"type": "git_remote", "pattern": "apache/airflow"},
            {
                "type": "file_structure",
                "all_of": ["airflow/__init__.py"],
                "any_of": ["airflow/models/dag.py", "airflow/dag.py"],
            },
        ],
        # "match" 欄位目前被忽略；match_rule 固定跑「任一 detector 命中即觸發」邏輯
    },
    # 之後加 commitizen-aware、其他 project 只在這裡加條目
]

# ---------------------------------------------------------------------------
# emit
# ---------------------------------------------------------------------------

GIT_TIMEOUT_SEC = 3


def emit(decision: str, system_message: str) -> None:
    payload = {
        "decision": decision,
        "reason": system_message,
        "systemMessage": system_message,
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.exit(0)


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------


def check_git_remote(cwd: str, pattern: str) -> bool:
    """Return True if git remote.origin.url contains *pattern*."""
    result = subprocess.run(
        ["git", "-C", cwd, "config", "--get", "remote.origin.url"],
        capture_output=True,
        timeout=GIT_TIMEOUT_SEC,
        check=False,
    )
    url = result.stdout.decode("utf-8", errors="replace").strip()
    return pattern in url


def check_file_structure(cwd: str, all_of: list[str], any_of: list[str]) -> bool:
    """Return True if all files in *all_of* exist AND at least one in *any_of* exists."""
    root = Path(cwd)
    if not all((root / f).is_file() for f in all_of):
        return False
    if any_of and not any((root / f).is_file() for f in any_of):
        return False
    return True


def run_detector(cwd: str, detector: dict) -> tuple[bool, str]:
    """Run one detector; return (matched, description_for_message)."""
    dtype = detector.get("type")
    if dtype == "git_remote":
        pattern = detector["pattern"]
        matched = check_git_remote(cwd, pattern)
        return matched, f"git remote 含 {pattern!r}"
    if dtype == "file_structure":
        all_of = detector.get("all_of", [])
        any_of = detector.get("any_of", [])
        matched = check_file_structure(cwd, all_of, any_of)
        return matched, f"file structure ({', '.join(all_of + any_of)})"
    return False, f"未知 detector type: {dtype!r}"


# ---------------------------------------------------------------------------
# Rule matching
# ---------------------------------------------------------------------------


def match_rule(cwd: str, rule: dict) -> tuple[bool, str]:
    """Return (matched, matched_detector_description).

    任一 detector 命中即回傳 True（目前唯一支援的策略）。
    """
    for detector in rule.get("detectors", []):
        try:
            matched, desc = run_detector(cwd, detector)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            # fail-open: skip this detector
            continue
        if matched:
            return True, desc

    return False, ""


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> None:
    try:
        raw = sys.stdin.read()
        try:
            data = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            data = {}

        cwd = (data.get("cwd") or os.getcwd()).strip()

        for rule in REPO_RULES:
            try:
                matched, detector_desc = match_rule(cwd, rule)
            except Exception:
                continue
            if matched:
                name = rule["name"]
                skill = rule["skill"]
                msg = (
                    f"偵測到 {name} repo（依據：{detector_desc}）。"
                    f"請讀取 skills/{skill}/SKILL.md，"
                    f"本 session 內執行任何 skill 時套用其中的慣例。"
                )
                emit("approve", msg)

        # No rule matched — silent approve
        emit("approve", "")

    except Exception as exc:  # noqa: BLE001
        print(f"repo_detect: unexpected error: {exc}", file=sys.stderr)
        emit("approve", "")


if __name__ == "__main__":
    main()
