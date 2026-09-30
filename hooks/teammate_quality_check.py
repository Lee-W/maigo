#!/usr/bin/env python3
"""
Maigo SubagentStop hook：各 agent 輸出規格檢查。

失敗時 block（要 agent 補完輸出）；輸入異常 / 角色未定義時 fail-open。
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _grep_criteria import block_reason, find_literal_grep_criteria
from _hook_io import emit_stop as emit
from _retry_log import RetryScope, record_and_count

SOYO_RETRY_LIMIT = 2
REVIEW_MODE_ITEMS = json.loads(
    Path(__file__).with_name("review_modes.json").read_text(encoding="utf-8")
)
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
    """
    Extract must-fix keys from Soyo output.

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
    return log_dir / "soyo-must-fix.jsonl"


def _soyo_record_and_count(
    log_path: Path, keys: set[str], scope: RetryScope | None = None
) -> dict[str, int]:
    return record_and_count(log_path, keys, "must_fix_keys", scope=scope)


MEMORY_HEADER_RE = re.compile(r"##\s+Loaded memory entries", re.IGNORECASE)


def require_memory_header(out: str, role_zh: str) -> None:
    """
    Memory-reader agent 必須在輸出含 `## Loaded memory entries` 段。

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

# `.maigo/` artifact naming migrated from fixed filenames (`plan.md` /
# `review-rubric.md` / `triage-rubric.md`) through identifier-suffixed flat
# ones (`plan-<id>.md` / ...) to the current nested-by-PR/issue layout
# (`review/<id>/rubric.md`, `issue/<id>/rubric.md`) — see
# `scripts/artifact_path.py`. `artifact_path_regex()` is the single source of
# truth for matching all three shapes at once; dynamic import (not a literal
# regex here) keeps this hook from drifting out of sync with that module.
_TOMORI_ARTIFACT_KINDS = ("plan", "review-rubric", "triage-rubric")
_TOMORI_ARTIFACT_RE: re.Pattern[str] | None
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from artifact_path import artifact_path_regex

    _TOMORI_ARTIFACT_RE = re.compile(artifact_path_regex(_TOMORI_ARTIFACT_KINDS))
except Exception:
    # fail-open, same shape as hooks/legacy_artifact_path_check.py's import
    # guard: scripts/artifact_path.py is still evolving (kinds get added,
    # syntax can momentarily break). `None` disables the two path-mention
    # checks below (`:127`-ish `_plan_criteria_hits()` and `check_tomori()`)
    # instead of taking down every Tomori SubagentStop check.
    _TOMORI_ARTIFACT_RE = None


def _plan_criteria_hits(out: str) -> list[str]:
    """
    Scan the plan artifact 燈 (Tomori) just wrote for literal-grep criteria.

    Fail-open: 讀不到檔案（還沒寫入、路徑在別的 repo、權限問題）就回空 list，
    hook 不會因為讀檔失敗擋下計畫；`_TOMORI_ARTIFACT_RE` 匯入失敗（`None`）
    同樣回空 list，不擋。
    """
    if _TOMORI_ARTIFACT_RE is None:
        return []
    match = _TOMORI_ARTIFACT_RE.search(out)
    if not match:
        return []
    path = Path(os.getcwd()).resolve() / match.group(0)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return find_literal_grep_criteria(text)


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

    # plan 模式（預設）/ review 模式 / triage 模式：把產出寫進 .maigo/ 的檔案
    # （巢狀路徑 `review/<id>/rubric.md` / `issue/<id>/rubric.md`、分目錄前扁平
    # `<kind>-<id>.md`、舊固定檔名 `plan.md` 皆可，見 _TOMORI_ARTIFACT_RE；
    # 匯入失敗時 `None`，fail-open 跳過此檢查，不擋）。
    if _TOMORI_ARTIFACT_RE is not None and not _TOMORI_ARTIFACT_RE.search(out):
        emit(
            "block",
            "燈 (Tomori) 的輸出沒提到 .maigo/plan-<id>.md / .maigo/review/<id>/rubric.md / "
            ".maigo/issue/<id>/rubric.md。呼叫 scripts/artifact_path.py 取得路徑，"
            "把計畫 / rubric 寫進那個檔案再回報。",
        )
    if not re.search(
        r"##\s+(Goal|Steps|Rubric|Acceptance|Category|目標|步驟|期待|對照|分類)",
        out,
    ):
        emit(
            "block",
            "燈 (Tomori) 的輸出缺少結構（## Goal / ## Steps / ## Rubric / ## Acceptance / ## Category / 目標 / 步驟 / 分類）。",
        )
    hits = _plan_criteria_hits(out)
    if hits:
        emit("block", block_reason("燈 (Tomori) 計畫的驗收條件", hits))
    emit("approve", "燈 (Tomori) 輸出結構齊全")


def _report_section(out: str, heading: str) -> str | None:
    match = re.search(
        rf"^##\s+{re.escape(heading)}\b[^\n]*\n(.*?)(?=^##\s|\Z)",
        out,
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    return match.group(1) if match else None


def _report_verdict(out: str, choices: str) -> str | None:
    """Read the verdict section; accept one standalone legacy verdict otherwise."""
    section = _report_section(out, "Verdict")
    matches = re.findall(
        rf"^\s*(?:\*\*)?({choices})(?:\*\*)?\s*$",
        section if section is not None else out,
        re.MULTILINE,
    )
    return matches[0] if len(matches) == 1 else None


def check_soyo(out: str, *, retry_scope: RetryScope | None = None) -> None:
    require_memory_header(out, "爽世 (Soyo)")
    verdict = _report_verdict(
        out, "APPROVED|NEEDS_CHANGES|BLOCKED|READY|NEEDS_INFO|DUP|CLOSE"
    )
    if verdict is None:
        emit(
            "block",
            "爽世 (Soyo) 的輸出沒看到 review verdict（APPROVED / NEEDS_CHANGES / BLOCKED）或 triage verdict（READY / NEEDS_INFO / DUP / CLOSE）。",
        )
        return

    checklist = re.search(
        r"^##\s+Checklist\b[^\n]*\n(.*?)(?=^##\s|\Z)",
        out,
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    if checklist is None:
        emit("block", "爽世 (Soyo) 的輸出缺少 ## Checklist 段。")
        return
    rows = re.findall(r"^.*\[([xX —-])\](.*)$", checklist.group(1), re.MULTILINE)
    if len(rows) < 9:
        emit(
            "block",
            "爽世 (Soyo) 的 ## Checklist 必須依序列出至少 9 項（[x] / [ ] / [—]）；quick 的略過項也要列出原因。",
        )

    triage = verdict in {"READY", "NEEDS_INFO", "DUP", "CLOSE"}
    modes = set(re.findall(r"\bmode=([\w-]+)", checklist.group(0)))
    mode = next(iter(modes)) if len(modes) == 1 else ("triage" if triage else "full")
    if len(modes) > 1 or mode not in REVIEW_MODE_ITEMS or (mode == "triage") != triage:
        emit(
            "block",
            "爽世 (Soyo) 的 checklist mode 不明、互相矛盾，或與 verdict 類型不符。",
        )
    skipped = {index for index, (mark, _) in enumerate(rows, 1) if mark in {"—", "-"}}
    allowed_skips = set(range(1, 10)) - set(REVIEW_MODE_ITEMS[mode])
    if not skipped <= allowed_skips or any(
        not triage and f"skipped by mode={mode}" not in rows[index - 1][1]
        for index in skipped
    ):
        emit(
            "block",
            f"爽世 (Soyo) 的 checklist 略過了 mode={mode} 的必要項目，或略過項缺少 skipped by mode={mode} 原因。",
        )
    if verdict in {"APPROVED", "READY"} and any(mark == " " for mark, _ in rows):
        emit("block", f"爽世 (Soyo) 的 checklist 仍有 [ ]，不能給 {verdict}。")

    if not triage and verdict != "APPROVED":
        if not re.search(r"(must[-\s]?fix|改法|evidence|待補)", out, re.IGNORECASE):
            emit(
                "block",
                f"爽世 (Soyo) 給出 {verdict} 卻沒列 must-fix 或 evidence 待補。要擋就要說擋什麼、怎麼改。",
            )

        cwd = Path(os.getcwd()).resolve()
        keys = _extract_soyo_must_fix_keys(out)
        counts = _soyo_record_and_count(_soyo_log_path(cwd), keys, retry_scope)
        if keys:
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

    if not triage and verdict == "APPROVED":
        _soyo_record_and_count(_soyo_log_path(Path.cwd()), set(), retry_scope)
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
    exit_codes = re.findall(r"exit\s+(-?[0-9]+)", out)
    if not exit_codes:
        emit(
            "block",
            "立希 (Taki) 沒看到 exit code。要拿真的 command 跑過，不是憑感覺說 PASS / FAIL。",
        )

    verdict = _report_verdict(out, "PASS|FAIL")
    if verdict is None:
        emit("block", "立希 (Taki) 沒給最終 verdict（PASS / FAIL）。")
        return
    if verdict == "PASS":
        commands = _report_section(out, "Commands")
        results: dict[str, int] = {}
        if commands is None:
            # A single legacy result is unambiguous; multiple anonymous results
            # cannot establish which failed check was rerun.
            if len(exit_codes) != 1:
                emit(
                    "block",
                    "立希 (Taki) 請在 ## Commands 逐項列出 `command` — exit <code>，不能用匿名 exit code 抵銷失敗。",
                )
            results["legacy command"] = int(exit_codes[0])
        else:
            for line in commands.splitlines():
                if not line.strip():
                    continue
                match = re.fullmatch(
                    r"\s*[-*]\s+`([^`]+)`\s*[—-]\s*exit\s+(-?[0-9]+)\b.*", line
                )
                if match is None or not match.group(1).strip():
                    emit(
                        "block",
                        "立希 (Taki) 的 ## Commands 每列必須是 `command` — exit <code>；略過或缺少結果不能 PASS。",
                    )
                    return
                results[match.group(1).strip()] = int(match.group(2))
        if not results or any(code != 0 for code in results.values()):
            emit(
                "block",
                "立希 (Taki) 宣告 PASS，但仍有 command 最新 exit code 非 0，或沒有檢查結果。請重跑失敗的檢查；其他 command 成功不能抵銷失敗。",
            )

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

    if not isinstance(data, dict):
        emit("approve", "輸入不是 JSON object，Maigo subagent check 跳過")
        return
    role = data.get("agent_type")
    if not isinstance(role, str) or not role.strip():
        emit("approve", "輸入缺少 agent_type，無法辨識 Maigo subagent，跳過")
        return
    role = role.strip().removeprefix("maigo:")

    handler = ROLE_HANDLERS.get(role)
    if handler is None:
        emit("approve", f"{role}：未設規格，預設通過")
        return

    output = data.get("last_assistant_message")
    if not isinstance(output, str) or not output.strip():
        emit(
            "block",
            f"{role} 的 SubagentStop 缺少 last_assistant_message，請補完角色輸出。",
        )
        return
    cwd = data.get("cwd") or os.getcwd()
    if not isinstance(cwd, str) or not Path(cwd).is_dir():
        emit("block", "SubagentStop 的 cwd 不是有效目錄，無法檢查角色產物。")
        return
    previous_cwd = os.getcwd()
    try:
        os.chdir(cwd)
        if handler is check_soyo:
            session_id, agent_id = data.get("session_id"), data.get("agent_id")
            scope = (
                RetryScope(session_id, agent_id)
                if isinstance(session_id, str)
                and session_id.strip()
                and isinstance(agent_id, str)
                and agent_id.strip()
                else None
            )
            check_soyo(output, retry_scope=scope)
        else:
            handler(output)
    finally:
        os.chdir(previous_cwd)


if __name__ == "__main__":
    main()
