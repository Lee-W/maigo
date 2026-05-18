#!/usr/bin/env python3
"""Maigo Stop hook：任務宣告完成前強制跑 test。

偵測專案類型 → 跑對應 test 指令 → 失敗就 block。即使 orchestrator
跳過立希也擋下；defense in depth。

支援的設定檔（放在 user 專案的 `.claude/` 下）：
- `skip-test-verification` — 第一行非空非註解視為原因，整個檢查跳過
- `test-command` — 覆寫 test 指令（第一行非空非註解）
- `known-test-failures` — 已知失敗名單（一行一個），不擋這些
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

TEST_TIMEOUT_SEC = 90
OUTPUT_TAIL_CHARS = 500  # chars to include in block message
# Match `Foo:` with a colon to reduce false positives from incidental mentions
FATAL_MARKER_RE = re.compile(r"\b(ImportError|ModuleNotFoundError|SyntaxError):")


def emit(decision: str, reason: str) -> None:
    payload = {"decision": decision, "reason": reason, "systemMessage": reason}
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.exit(0)


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


def main() -> None:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        data = {}

    cwd = Path(data.get("cwd") or os.getcwd()).resolve()
    claude_dir = cwd / ".claude"

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

    fatal_match = FATAL_MARKER_RE.search(output)
    if fatal_match:
        emit(
            "block",
            f"立希 (Taki)：`{' '.join(cmd)}` 出現 {fatal_match.group(1)}（import / collection 錯，不是 test 失敗）。先修這個。",
        )

    actual = extract_failures(output)
    new_failures = actual - known

    if new_failures:
        details = "\n".join(f"  - {f}" for f in sorted(new_failures))
        emit(
            "block",
            f"立希 (Taki)：`{' '.join(cmd)}` exit {exit_code}，{len(new_failures)} 個新失敗：\n{details}\n\n（已知失敗已忽略；要忽略新失敗，加到 .claude/known-test-failures）",
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
