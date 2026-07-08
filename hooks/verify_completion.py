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

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_io import emit  # noqa: E402
from _retry_log import record_and_count  # noqa: E402

TEST_TIMEOUT_SEC = 90
GIT_TIMEOUT_SEC = 5
OUTPUT_TAIL_CHARS = 500  # chars to include in block message
RETRY_LIMIT = 2
_RETRY_LOG_BASE = Path(".maigo")
# Match `Foo:` with a colon to reduce false positives from incidental mentions
FATAL_MARKER_RE = re.compile(r"\b(ImportError|ModuleNotFoundError|SyntaxError):")
# Host-environment build failures (toolchain / native deps / system libs)
# bubble up through `uv run pytest`, `cargo test`, `go test`, `npm test`, etc.
# when a transitive dep tries to compile at import / build time. These look
# like test failures because the command exits non-zero, but the project's
# own code never ran. Treat as "skip with reason" so the operator can fix
# the host env (or pin `.claude/test-command` /
# `.claude/skip-test-verification`) without the loop.
BUILD_ENV_ERROR_RE = re.compile(
    # Python / CMake / native wheels
    r"CMake configuration failed"
    r"|Failed building wheel for \S+"
    r"|Failed to build [`'\"]?\S+"
    # Rust / Cargo native toolchain
    r"|error: linker `[^`]+` not found"
    r"|error: linker \S+ failed"
    r"|error: failed to run custom build command for"
    # Node-gyp native build (catches both bare and prefixed forms)
    r"|gyp ERR! (?:stack|build error)"
    r"|node-gyp.+failed"
    # Go cgo / C compiler
    r"|cgo: C compiler \S+ not found"
    r"|# runtime/cgo"
    # Java / JDK absent
    r"|JAVA_HOME is not set"
    r"|FindJava"
    # Generic compiler missing
    r"|(?:gcc|cc|clang|cl): command not found"
    r"|No such file or directory: ['\"]?(?:gcc|cc|clang|make|cmake)['\"]?",
)
# pytest collection / usage / config errors and "no tests ran" mean the suite
# never executed — the project's own code didn't fail, the *invocation* did.
# The classic case is a uv-workspace monorepo whose root needs `--project`:
# bare `uv run pytest` then errors out in a sub-package conftest
# (`pytest-plugins-in-non-top-level-conftest-files`). These emit no FAILED
# lines, so without this guard they fall through to the blind block below and
# loop forever (no test name to act on). Import/syntax errors in the user's
# own changed code are caught earlier by FATAL_MARKER_RE and still block; this
# pattern is for setup/invocation problems the operator fixes via
# `.claude/test-command`, not for masking real test breakage.
COLLECTION_ERROR_RE = re.compile(
    r"non-top-level[ -]conftest"  # pytest-plugins-in-non-top-level-conftest(-files)
    r"|errors during collection"
    r"|ERROR collecting "
    r"|no tests ran in"
    r"|ERROR: file or directory not found"
    r"|ERROR: not found:"
    r"|unrecognized arguments"
    # pytest summary reporting *errors* (collection) rather than failures, e.g.
    # "1 error in 0.30s" / "2 errors in 1.1s". Only consulted when no FAILED
    # line was parseable (see call site), so it cannot mask real failures that
    # happen to share a summary line with errors.
    r"|\b\d+ errors? in [\d.]+s",
)


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
    """Return the test command for the first matching project type, or None if tool unavailable.

    fail-fast flags (`-x` for pytest, `-failfast` for go) bail on the first
    failure so the 90s hook timeout has headroom for parsing the result.
    cargo and npm are left default — cargo aborts on compilation errors
    natively, and npm's `test` script is user-defined so the hook should
    not second-guess it.
    """
    if (cwd / "uv.lock").is_file():
        if shutil.which("uv"):
            return ["uv", "run", "pytest", "-x"]
    if (cwd / "pyproject.toml").is_file() or (cwd / "setup.py").is_file():
        if (cwd / "tests").is_dir() or (cwd / "test").is_dir():
            if shutil.which("pytest"):
                return ["pytest", "-x"]
    pkg = cwd / "package.json"
    if pkg.is_file():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            if "test" in (data.get("scripts") or {}):
                if shutil.which("npm"):
                    return ["npm", "test", "--silent"]
        except json.JSONDecodeError:
            pass
    if (cwd / "Cargo.toml").is_file():
        if shutil.which("cargo"):
            return ["cargo", "test", "--quiet"]
    if (cwd / "go.mod").is_file():
        if shutil.which("go"):
            return ["go", "test", "-failfast", "./..."]
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
    return record_and_count(log_path, failures, "failures")


def _retry_warning(counts: dict[str, int], keys: set[str], label: str) -> str:
    over_limit = {
        key: counts.get(key, 0) for key in keys if counts.get(key, 0) >= RETRY_LIMIT
    }
    if not over_limit:
        return ""
    lines = "\n".join(
        f"  - {key} ({count} 次)" for key, count in sorted(over_limit.items())
    )
    return (
        f"⚠️ RETRY LIMIT REACHED: {label} 已連續紅 ≥ {RETRY_LIMIT} 次"
        f"（本次含），考慮停下找使用者介入：\n{lines}\n"
        f"依 skills/failure-handling 的「無限迴圈防護」。\n\n"
    )


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

    if not custom_cmd and (cwd / "uv.lock").is_file() and shutil.which("uv") is None:
        emit(
            "approve",
            "立希 (Taki)：偵測到 uv.lock 但 uv 不在 PATH，已跳過 test 驗證——裝 uv 或在 .claude/test-command 指定可跑的指令。",
        )
        return

    if cmd is None:
        emit("approve", "立希 (Taki)：偵測不到 test 設定，跳過（no-op）")
        return

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
        fatal_key = f"__fatal__:{fatal_match.group(1)}:{' '.join(cmd)}"
        counts = _record_and_count(_retry_log_path(cwd), {fatal_key})
        warning = _retry_warning(counts, {fatal_key}, "import / collection 錯")
        emit(
            "block",
            f"{warning}立希 (Taki)：`{' '.join(cmd)}` 出現 {fatal_match.group(1)}（import / collection 錯，不是 test 失敗）。先修這個。",
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

    # No parseable failures at this point. If the output looks like a
    # collection / usage / config error (the suite never ran — e.g. a
    # uv-workspace monorepo root that needs `--project`), block with guidance.
    # A Stop hook must not approve completion when the configured suite did not
    # actually run. Checked here (not before extract_failures) so a summary that
    # mixes errors *and* real failures still blocks on the failures above.
    # Import/syntax errors in the user's own code are caught earlier by
    # FATAL_MARKER_RE and still block.
    collection_match = COLLECTION_ERROR_RE.search(output)
    if collection_match:
        collection_key = f"__collection__:{collection_match.group(0)}:{' '.join(cmd)}"
        counts = _record_and_count(_retry_log_path(cwd), {collection_key})
        warning = _retry_warning(counts, {collection_key}, "test collection / 設定錯")
        emit(
            "block",
            f"{warning}立希 (Taki)：`{' '.join(cmd)}` 失敗於 test collection / 設定（{collection_match.group(0)!r}），suite 根本沒跑。常見於 uv-workspace monorepo 根目錄要用 `--project`。在 `.claude/test-command` 改成可跑的指令（例如 `uv run --project <pkg> pytest <path>`），或 `.claude/skip-test-verification` 寫一行 reason 明確關閉本 worktree 的檢查。",
        )

    # Non-zero exit we couldn't attribute to any test name (and not a
    # recognized build-env / collection / config error). Block so the operator
    # sees it. Route through the retry log only to make repeated attempts
    # obvious; do not approve, because a non-zero test command is not verified.
    # The key is stable per command so distinct commands count independently.
    tail = output[-OUTPUT_TAIL_CHARS:] if len(output) > OUTPUT_TAIL_CHARS else output
    unparsed_key = f"__unparsed_nonzero__:{' '.join(cmd)}"
    counts = _record_and_count(_retry_log_path(cwd), {unparsed_key})
    if counts.get(unparsed_key, 0) >= RETRY_LIMIT:
        emit(
            "block",
            f"⚠️ RETRY LIMIT REACHED: 立希 (Taki)：`{' '.join(cmd)}` exit {exit_code} 已連續 ≥ {RETRY_LIMIT} 次無法 parse failure（本次含）。停止重試以免無限迴圈，請人工介入確認。依 skills/failure-handling 的「無限迴圈防護」。若這是 collection / 設定問題，在 `.claude/test-command` 改成可跑的指令，或 `.claude/skip-test-verification` 寫一行 reason 明確關閉本 worktree 的檢查。Raw tail:\n{tail}",
        )
    emit(
        "block",
        f"立希 (Taki)：`{' '.join(cmd)}` exit {exit_code}，無法 parse failure 名稱。Raw tail:\n{tail}",
    )


if __name__ == "__main__":
    main()
