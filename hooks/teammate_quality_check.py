#!/usr/bin/env python3
"""Maigo TeammateIdle hook：各 agent 輸出規格檢查。

失敗時 block（要 agent 補完輸出）；輸入異常 / 角色未定義時 fail-open。
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_io import emit  # noqa: E402
from _retry_log import record_and_count  # noqa: E402


SOYO_RETRY_LIMIT = 2
_RETRY_LOG_BASE = Path(".maigo")
_MUST_FIX_FILE_RE = re.compile(r"`([\w./-]+\.\w+)(?::\d+)?`")
_MUST_FIX_LINE_RE = re.compile(
    r"^\s*(?:[-*]|\d+\.)\s+(.+)$",
    re.MULTILINE,
)


_MUST_FIX_HEADING_RE = re.compile(
    r"##\s+(?:must[-\s]?fix|必須修)",
    re.IGNORECASE,
)
_NEXT_HEADING_RE = re.compile(r"^##\s+", re.MULTILINE)


def _extract_soyo_must_fix_keys(out: str) -> set[str]:
    """Extract must-fix keys from Soyo output.

    Strategy:
    1. If a '## Must-fix' section exists, extract bullet items from that section only.
    2. Otherwise, fall back to lines containing the 'must-fix' keyword.
    For each item: backtick file path (with :line stripped) is the key;
    if none, use normalized text (lowercase, whitespace collapsed, max 80 chars).
    """
    # Find ## Must-fix section
    heading_match = _MUST_FIX_HEADING_RE.search(out)
    if heading_match:
        section_start = heading_match.end()
        # Find the next ## heading after section_start
        next_heading = _NEXT_HEADING_RE.search(out, section_start)
        section_text = (
            out[section_start : next_heading.start()]
            if next_heading
            else out[section_start:]
        )
        items = _MUST_FIX_LINE_RE.findall(section_text)
    else:
        # Fallback: lines that mention 'must-fix' keyword
        items = [
            line.strip()
            for line in out.splitlines()
            if re.search(r"must[-\s]?fix", line, re.IGNORECASE)
        ]

    keys: set[str] = set()
    for item in items:
        file_match = _MUST_FIX_FILE_RE.search(item)
        if file_match:
            keys.add(file_match.group(1))
        else:
            normalized = re.sub(r"\s+", " ", item).strip().lower()[:80]
            if normalized:
                keys.add(normalized)
    return keys


def _soyo_log_path(cwd: Path) -> Path:
    log_dir = cwd / _RETRY_LOG_BASE
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "soyo-must-fix.jsonl"


def _soyo_record_and_count(log_path: Path, keys: set[str]) -> dict[str, int]:
    return record_and_count(log_path, keys, "must_fix_keys")


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

    # plan 模式（預設）：把計畫寫進 .maigo/ 的檔案
    if not re.search(r"\.maigo/(plan|review-rubric)\.md", out):
        emit(
            "block",
            "燈 (Tomori) 的輸出沒提到 .maigo/plan.md 或 .maigo/review-rubric.md。把計畫寫進那個檔案再回報。",
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

        cwd = Path(os.getcwd()).resolve()
        keys = _extract_soyo_must_fix_keys(out)
        if keys:
            counts = _soyo_record_and_count(_soyo_log_path(cwd), keys)
            over_limit = {
                k: c for k, c in counts.items() if k in keys and c >= SOYO_RETRY_LIMIT
            }
            if over_limit:
                lines = "\n".join(
                    f"  - {k} ({c} 次)" for k, c in sorted(over_limit.items())
                )
                emit(
                    "block",
                    f"⚠️ RETRY LIMIT REACHED (Soyo): 以下 must-fix 已連續被指出 "
                    f"≥ {SOYO_RETRY_LIMIT} 次（本次含），考慮停下找使用者介入：\n"
                    f"{lines}\n依 skills/failure-handling 的「無限迴圈防護」"
                    f"——同 must-fix key 連續 {SOYO_RETRY_LIMIT} 次即達 limit。",
                )

    emit("approve", f"爽世 (Soyo) 輸出符合規格 (verdict={verdict})")


_URL_RE = re.compile(r"https?://\S+")
# Common source / config / docs extensions across the language ecosystems Maigo
# advertises support for. Word boundary at end so trailing punctuation (`,`, `.`,
# `:`, closing backtick) does not break the match.
_FILE_PATH_EXTS = (
    # Python
    "py",
    "pyi",
    # JS / TS / web frontends
    "js",
    "jsx",
    "mjs",
    "cjs",
    "ts",
    "tsx",
    "vue",
    "svelte",
    "astro",
    # JVM
    "java",
    "kt",
    "kts",
    "scala",
    "groovy",
    # Systems
    "rs",
    "go",
    "c",
    "cc",
    "cpp",
    "cxx",
    "h",
    "hh",
    "hpp",
    "hxx",
    # Other languages
    "rb",
    "php",
    "swift",
    "m",
    "mm",
    "cs",
    "fs",
    "fsx",
    "ex",
    "exs",
    "erl",
    "hs",
    "lua",
    "pl",
    "r",
    "jl",
    "dart",
    "clj",
    "cljs",
    "zig",
    "nim",
    # Web markup / style
    "html",
    "htm",
    "css",
    "scss",
    "sass",
    "less",
    # Docs
    "md",
    "mdx",
    "rst",
    "txt",
    "adoc",
    # Data / config
    "json",
    "yml",
    "yaml",
    "toml",
    "ini",
    "conf",
    "cfg",
    "env",
    "xml",
    "csv",
    "tsv",
    "lock",
    "properties",
    # Shell / scripts
    "sh",
    "bash",
    "zsh",
    "fish",
    "ps1",
    "bat",
    "cmd",
    # Build / infra
    "mk",
    "bzl",
    "bazel",
    "gradle",
    "sbt",
    "cmake",
    "tf",
    "tfvars",
    "dockerfile",
    # Other useful
    "sql",
    "proto",
    "graphql",
    "gql",
    "ipynb",
)
FILE_PATH_RE = re.compile(
    r"[\w./-]+\.(?:" + "|".join(_FILE_PATH_EXTS) + r")\b",
    re.IGNORECASE,
)


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
