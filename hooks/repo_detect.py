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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_io import emit  # noqa: E402

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
        #
        # claude_config_seeds：偵測命中時 write-once 進 .claude/。檔案若已存在
        # 不會覆寫，使用者隨時可手動編輯或刪除以改變行為。Airflow 預設跳過
        # verify_completion 的 test 驗證，因為 host 端無法跑（要 Breeze container
        # 或 `uv run --project <PROJECT> pytest <PATH>`），而 hook 90s timeout
        # 也不夠 Airflow 任何 subproject 的 test suite 跑完。
        "claude_config_seeds": {
            "skip-test-verification": (
                "# Auto-written by maigo repo_detect for apache/airflow.\n"
                "# Airflow tests run via Breeze or `uv run --project <PROJECT> pytest <PATH>`;\n"
                "# bare `uv run pytest` on the host pulls jpype1 → cmake FindJava and fails.\n"
                "# To re-enable verification, delete this file or replace with a targeted\n"
                "# command in .claude/test-command (e.g. `uv run --project airflow-core pytest tests/unit/...`).\n"
                "airflow checkout: run tests manually via Breeze or `uv run --project <PROJECT>`\n"
            ),
        },
    },
    {
        "name": "commitizen-tools-commitizen",
        "skill": "commitizen-aware",
        "detectors": [
            {"type": "git_remote", "pattern": "commitizen-tools/commitizen"},
            {
                "type": "file_structure",
                "all_of": ["commitizen/__init__.py"],
                "any_of": [
                    "commitizen/cli.py",
                    "commitizen/commands/__init__.py",
                    "commitizen/bump.py",
                ],
            },
        ],
    },
    # 新增 project：在此 append 一個 dict，參見 docs/reference/hooks.md 的 Add New Project Entry
]

# ---------------------------------------------------------------------------
# emit
# ---------------------------------------------------------------------------

GIT_TIMEOUT_SEC = 3


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


def seed_claude_config(cwd: str, seeds: dict[str, str]) -> list[str]:
    """Write seed files into .claude/ if absent. Return list of newly-written filenames.

    Never overwrites — once a file exists (user-edited or written by a prior session)
    it is treated as authoritative.
    """
    written: list[str] = []
    if not seeds:
        return written
    claude_dir = Path(cwd) / ".claude"
    try:
        claude_dir.mkdir(exist_ok=True)
    except OSError:
        return written
    for name, content in seeds.items():
        target = claude_dir / name
        if target.exists():
            continue
        try:
            target.write_text(content, encoding="utf-8")
            written.append(name)
        except OSError:
            continue
    return written


def ensure_maigo_ignored(cwd: str) -> None:
    """Make ``.maigo/`` git-ignored locally, without touching a tracked .gitignore.

    maigo writes working artefacts (``plan.md``, ``review-rubric.md``,
    ``pr-comments.md``, retry logs) into ``.maigo/`` at the repo root; those must
    never be committed. We append the rule to the repo's ``info/exclude`` —
    resolved via ``git rev-parse --git-path`` so it lands in the shared git dir
    even from a linked worktree — rather than the project's tracked ``.gitignore``,
    which the host repo (e.g. apache/airflow) commits and must not be mutated.

    Idempotent and fail-open: does nothing if ``.maigo/`` is already ignored (a
    global excludesfile, a tracked ``.gitignore``, or a prior run), if *cwd* is
    not a git repo, or on any git/OS error.
    """
    try:
        already = subprocess.run(
            ["git", "-C", cwd, "check-ignore", "-q", ".maigo/"],
            timeout=GIT_TIMEOUT_SEC,
            check=False,
        )
        if already.returncode == 0:
            return  # already ignored by some mechanism — nothing to do

        resolved = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--git-path", "info/exclude"],
            capture_output=True,
            timeout=GIT_TIMEOUT_SEC,
            check=False,
        )
        if resolved.returncode != 0:
            return  # not a git repo

        exclude = Path(resolved.stdout.decode("utf-8", errors="replace").strip())
        if not exclude.is_absolute():
            exclude = Path(cwd) / exclude

        existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
        if ".maigo/" in existing.split():
            return  # entry already present

        exclude.parent.mkdir(parents=True, exist_ok=True)
        prefix = "" if (not existing or existing.endswith("\n")) else "\n"
        with exclude.open("a", encoding="utf-8") as fh:
            fh.write(f"{prefix}# maigo working artefacts (auto-added)\n.maigo/\n")
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return


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

        # Keep maigo's own scratch dir out of the host repo regardless of which
        # project this is — every command (go/quick/team/review/address-comments)
        # writes into .maigo/.
        ensure_maigo_ignored(cwd)

        for rule in REPO_RULES:
            try:
                matched, detector_desc = match_rule(cwd, rule)
            except Exception:
                continue
            if matched:
                name = rule["name"]
                skill = rule["skill"]
                written = seed_claude_config(cwd, rule.get("claude_config_seeds", {}))
                msg = (
                    f"偵測到 {name} repo（依據：{detector_desc}）。"
                    f"請讀取 skills/{skill}/SKILL.md，"
                    f"本 session 內執行任何 skill 時套用其中的慣例。"
                )
                if written:
                    files = ", ".join(f".claude/{f}" for f in written)
                    msg += f" 已寫入 {files}（要覆寫請手動編輯）。"
                emit("approve", msg)

        # No rule matched — silent approve
        emit("approve", "")

    except Exception as exc:  # noqa: BLE001
        print(f"repo_detect: unexpected error: {exc}", file=sys.stderr)
        emit("approve", "")


if __name__ == "__main__":
    main()
