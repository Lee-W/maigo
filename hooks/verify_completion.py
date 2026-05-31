#!/usr/bin/env python3
"""Maigo Stop hook：任務宣告完成前強制跑 test。

偵測專案類型 → 跑對應 test 指令 → 失敗就 block。即使 orchestrator
跳過立希也擋下；defense in depth。Host build-env 失敗（CMake、native
wheel build 等）一律 emit skip——那不是 test 失敗，是 host 環境問題。

支援的設定檔（放在 user 專案的 `.claude/` 下）：
- `skip-test-verification` — 第一行非空非註解視為原因，整個檢查跳過
- `test-command` — 覆寫 test 指令（第一行非空非註解）
- `known-test-failures` — 已知失敗名單（一行一個），不擋這些
"""

from __future__ import annotations

import datetime
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

TEST_TIMEOUT_SEC = 90
GIT_TIMEOUT_SEC = 5
OUTPUT_TAIL_CHARS = 500  # chars to include in block message
RETRY_LIMIT = 2
_RETRY_LOG_BASE = Path(".maigo")
# Match `Foo:` with a colon to reduce false positives from incidental mentions
FATAL_MARKER_RE = re.compile(r"\b(ImportError|ModuleNotFoundError|SyntaxError):")
# Host-environment build failures (CMake/Java/native wheel) bubble up through
# `uv run pytest` / `pip install` when a transitive dependency tries to compile
# at import time. These look like test failures because the command exits
# non-zero, but they are not — the project's own code never ran. Treat as
# "skip with reason" so the operator can fix the host env (or pin
# `.claude/test-command` / `.claude/skip-test-verification`) without the loop.
BUILD_ENV_ERROR_RE = re.compile(
    r"CMake configuration failed"
    r"|Failed building wheel for \S+"
    r"|Failed to build [`'\"]?\S+",
)


def emit(decision: str, reason: str) -> None:
    payload = {"decision": decision, "reason": reason, "systemMessage": reason}
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.exit(0)


def has_git_modifications(cwd: Path) -> bool:
    """Return True if there are uncommitted changes (staged, unstaged, or untracked).

    Fail-open: returns True on any error so tests still run when uncertain.
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(cwd),
            capture_output=True,
            timeout=GIT_TIMEOUT_SEC,
            check=False,
        )
        if result.returncode != 0:
            return True  # not a git repo or other error — fail-open
        return bool(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return True


def read_config_line(path: Path) -> str | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return None


def detect_test_command(cwd: Path) -> list[str] | None:
    """Return the test command for the first matching project type."""
    if (cwd / "uv.lock").is_file():
        return ["uv", "run", "pytest"]
    if (cwd / "pyproject.toml").is_file() or (cwd / "setup.py").is_file():
        if (cwd / "tests").is_dir() or (cwd / "test").is_dir():
            return ["pytest"]
    pkg = cwd / "package.json"
    if pkg.is_file():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            if "test" in (data.get("scripts") or {}):
                return ["npm", "test", "--silent"]
        except json.JSONDecodeError:
            pass
    if (cwd / "Cargo.toml").is_file():
        return ["cargo", "test", "--quiet"]
    if (cwd / "go.mod").is_file():
        return ["go", "test", "./..."]
    return None


def run_command(cmd: list[str], cwd: Path) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            timeout=TEST_TIMEOUT_SEC,
            check=False,
        )
        out = (proc.stdout + proc.stderr).decode("utf-8", errors="replace")
        return proc.returncode, out
    except FileNotFoundError:
        return -1, f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -1, f"timeout after {TEST_TIMEOUT_SEC}s: {' '.join(cmd)}"


def extract_failures(output: str) -> set[str]:
    """Heuristic extraction of failed test names from common test runner output."""
    failures: set[str] = set()
    # pytest: "FAILED tests/x.py::test_y"
    failures.update(re.findall(r"FAILED (\S+)", output))
    # pytest summary: "tests/x.py::test_y FAILED"
    failures.update(re.findall(r"(\S+::\S+)\s+FAILED", output))
    # jest: "FAIL src/x.test.js"
    failures.update(re.findall(r"FAIL\s+(\S+\.(?:test|spec)\.[jt]sx?)", output))
    # cargo test: "test foo ... FAILED"
    failures.update(re.findall(r"test (\S+) \.\.\. FAILED", output))
    # go test: "--- FAIL: TestFoo"
    failures.update(re.findall(r"---\s+FAIL:\s+(\S+)", output))
    return failures


def read_known_failures(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def _retry_log_path(cwd: Path) -> Path:
    log_dir = cwd / _RETRY_LOG_BASE
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "test-failures.jsonl"


def _record_and_count(log_path: Path, failures: set[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    try:
        if log_path.is_file():
            for line in log_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    for tid in entry.get("failures", []):
                        counts[tid] = counts.get(tid, 0) + 1
                except json.JSONDecodeError:
                    pass  # corrupted line — skip, don't crash
        ts = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        new_entry = json.dumps(
            {"ts": ts, "failures": sorted(failures)}, ensure_ascii=False
        )
        with log_path.open("a", encoding="utf-8") as f:
            f.write(new_entry + "\n")
        for tid in failures:
            counts[tid] = counts.get(tid, 0) + 1
    except (OSError, PermissionError):
        return {}
    return counts


def main() -> None:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        data = {}

    cwd = Path(data.get("cwd") or os.getcwd()).resolve()
    claude_dir = cwd / ".claude"

    if not has_git_modifications(cwd):
        emit("approve", "立希 (Taki)：本次 session 無未提交的檔案修改，跳過 test 驗證")

    skip_reason = read_config_line(claude_dir / "skip-test-verification")
    if skip_reason is not None:
        emit("approve", f"verify_completion 跳過：{skip_reason}")

    custom_cmd = read_config_line(claude_dir / "test-command")
    cmd = shlex.split(custom_cmd) if custom_cmd else detect_test_command(cwd)

    if cmd is None:
        emit("approve", "立希 (Taki)：偵測不到 test 設定，跳過（no-op）")

    known = read_known_failures(claude_dir / "known-test-failures")
    exit_code, output = run_command(cmd, cwd)

    if exit_code == 0:
        emit("approve", f"立希 (Taki)：`{' '.join(cmd)}` 通過")

    build_env_match = BUILD_ENV_ERROR_RE.search(output)
    if build_env_match:
        emit(
            "approve",
            f"立希 (Taki)：`{' '.join(cmd)}` 失敗於 host build env（{build_env_match.group(0)!r}），不是 test 失敗。跳過——修 host build env，或在 `.claude/test-command` 改成可跑的指令，或 `.claude/skip-test-verification` 寫一行 reason 永久關閉本 worktree 的檢查。",
        )

    fatal_match = FATAL_MARKER_RE.search(output)
    if fatal_match:
        emit(
            "block",
            f"立希 (Taki)：`{' '.join(cmd)}` 出現 {fatal_match.group(1)}（import / collection 錯，不是 test 失敗）。先修這個。",
        )

    actual = extract_failures(output)
    new_failures = actual - known

    if new_failures:
        counts = _record_and_count(_retry_log_path(cwd), new_failures)
        over_limit = {
            tid: c
            for tid, c in counts.items()
            if tid in new_failures and c >= RETRY_LIMIT
        }
        warning = ""
        if over_limit:
            lines = "\n".join(
                f"  - {tid} ({c} 次)" for tid, c in sorted(over_limit.items())
            )
            warning = (
                f"⚠️ RETRY LIMIT REACHED: 以下 test 已連續紅 ≥ {RETRY_LIMIT} 次"
                f"（本次含），考慮停下找使用者介入：\n{lines}\n"
                f"依 skills/failure-handling 的「無限迴圈防護」"
                f"——同 test ID 連紅 {RETRY_LIMIT} 次即達 limit。\n\n"
            )
        details = "\n".join(f"  - {f}" for f in sorted(new_failures))
        emit(
            "block",
            f"{warning}立希 (Taki)：`{' '.join(cmd)}` exit {exit_code}，"
            f"{len(new_failures)} 個新失敗：\n{details}\n\n"
            f"（已知失敗已忽略；要忽略新失敗，加到 .claude/known-test-failures）",
        )

    if actual and not new_failures:
        emit(
            "approve",
            f"立希 (Taki)：{len(actual)} 個失敗全在 known-test-failures 名單，放行",
        )

    tail = output[-OUTPUT_TAIL_CHARS:] if len(output) > OUTPUT_TAIL_CHARS else output
    emit(
        "block",
        f"立希 (Taki)：`{' '.join(cmd)}` exit {exit_code}，無法 parse failure 名稱。Raw tail:\n{tail}",
    )


if __name__ == "__main__":
    main()
