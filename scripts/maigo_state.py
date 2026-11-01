#!/usr/bin/env python3
"""把 `.maigo/` 的實體集中到本機一個 root，每個 worktree 的 `.maigo` 只是指向它的 symlink。

為什麼：hook 把 `.maigo/` 寫在 git toplevel，linked worktree 各有一份，board 與 review
報告散在不同 worktree。集中之後同一個 repo identity 的所有 worktree 共用一份；路徑仍是
`.maigo/...`，`artifact_path.py` 等讀寫端不必改。本檔只做儲存層，不碰任何傳輸。

集中 root：`$MAIGO_STATE_HOME`，未設則 `~/.local/share/maigo/state`；
repo 的目錄是 `<root>/<owner>/<repo>/`。

repo identity：先 `upstream` 再 `origin` 的 URL，去掉 `.git` 與結尾斜線，取最後兩段
`owner/repo`；host 與使用者名稱、port 都忽略，所以 ssh 與 https 形式得到同一個結果。
沒有可用 remote 時退回 `_local/<主 worktree 目錄名>`。這個 identity 只是目錄名，
**不代表任何同步許可**：本檔沒有內建 allowlist，也不預設放行任何 repo。

跑（CLI）：

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/maigo_state.py" identity [--cwd DIR]
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/maigo_state.py" link [--cwd DIR]
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/maigo_state.py" migrate [--cwd DIR] [--apply]
```

`migrate` 預設 dry-run：把同一個 repo 所有 worktree 的真目錄 `.maigo/` 併進集中 root，
同名但內容不同的檔只列出、不覆寫（有任何衝突時連 `--apply` 也不動手）；`--apply` 先把每份
原目錄備份到 `<root>/_migration-backup/<UTC ts>/`，逐項核對種類與內容都與集中 root 一致，才換成 symlink。
巢狀的 `.maigo/.maigo/` 殘留會被列出，內容原樣搬進去（不刪，之後由 `/maigo:tidy` 處理）。
"""

from __future__ import annotations

import argparse
import filecmp
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

GIT_TIMEOUT_SEC = 5
MAIGO_DIRNAME = ".maigo"
STATE_HOME_ENV = "MAIGO_STATE_HOME"
DEFAULT_STATE_HOME = "~/.local/share/maigo/state"
BACKUP_DIRNAME = "_migration-backup"
LOCAL_OWNER = "_local"
REMOTE_PRIORITY = ("upstream", "origin")
SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")

STATUS_LINKED = "linked"
STATUS_ALREADY_LINKED = "already-linked"
STATUS_NEEDS_MIGRATION = "needs-migration"
STATUS_WRONG_TARGET = "wrong-target"
STATUS_BLOCKED = "blocked"
STATUS_NOT_A_REPO = "not-a-repo"


def get_state_root() -> Path:
    override = os.environ.get(STATE_HOME_ENV, "").strip()
    return Path(override or DEFAULT_STATE_HOME).expanduser()


state_root = get_state_root


def _run_git(cwd: str | Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            timeout=GIT_TIMEOUT_SEC,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="replace").strip()


def _is_valid_segment(segment: str) -> bool:
    return segment not in {".", ".."} and bool(SEGMENT_RE.match(segment))


def parse_remote_identity(url: str) -> str | None:
    """`git@host:o/r.git`、`ssh://u@host:22/o/r`、`https://host/o/r.git/` 都得到 `o/r`；本機路徑回 None。"""
    url = url.strip()
    if not url:
        return None
    if "://" in url:
        path = urlparse(url).path
    elif ":" in url and not url.startswith(("/", ".")):
        path = url.split(":", 1)[1]
    else:
        return None
    path = path.rstrip("/")
    path = path.removesuffix(".git").rstrip("/")
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        return None
    owner, repo = parts[-2], parts[-1]
    if not (_is_valid_segment(owner) and _is_valid_segment(repo)):
        return None
    return f"{owner}/{repo}"


def get_toplevel(cwd: str | Path) -> Path | None:
    top = _run_git(cwd, "rev-parse", "--show-toplevel")
    return Path(top) if top else None


def _get_main_worktree_name(cwd: str | Path) -> str | None:
    common = _run_git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common:
        path = Path(common)
        name = path.parent.name if path.name == ".git" else path.name
        name = name.removesuffix(".git")
        if _is_valid_segment(name):
            return name
    top = get_toplevel(cwd)
    if top is not None and _is_valid_segment(top.name):
        return top.name
    return None


def resolve_identity(cwd: str | Path, *, toplevel: Path | None = None) -> str | None:
    """回傳 `owner/repo`；不是 git repo 回 None。已知 toplevel 時傳入可省一次 git 呼叫。"""
    if (toplevel or get_toplevel(cwd)) is None:
        return None
    for remote in REMOTE_PRIORITY:
        url = _run_git(cwd, "remote", "get-url", remote)
        if not url:
            continue
        identity = parse_remote_identity(url)
        if identity:
            return identity
    name = _get_main_worktree_name(cwd)
    return f"{LOCAL_OWNER}/{name}" if name else None


@dataclass(frozen=True)
class LinkResult:
    status: str
    link: Path | None = None
    target: Path | None = None


def _points_to(link: Path, target: Path) -> bool:
    return os.path.realpath(link) == os.path.realpath(target)


def ensure_link(cwd: str | Path) -> LinkResult:
    """讓 `<toplevel>/.maigo` 成為指向集中 root 的 symlink；真目錄與錯誤目標只回報，不動。"""
    top = get_toplevel(cwd)
    identity = resolve_identity(cwd, toplevel=top) if top is not None else None
    if top is None or identity is None:
        return LinkResult(STATUS_NOT_A_REPO)
    link = top / MAIGO_DIRNAME
    target = get_state_root() / identity

    if link.is_symlink():
        if not _points_to(link, target):
            return LinkResult(STATUS_WRONG_TARGET, link, target)
        target.mkdir(parents=True, exist_ok=True)
        return LinkResult(STATUS_ALREADY_LINKED, link, target)
    if link.is_dir():
        return LinkResult(STATUS_NEEDS_MIGRATION, link, target)
    if link.exists():
        return LinkResult(STATUS_BLOCKED, link, target)

    target.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target, target_is_directory=True)
    return LinkResult(STATUS_LINKED, link, target)


def check_maigo_link_trusted(maigo: str | Path) -> None:
    """`.maigo` 是 symlink 時，目標必須在集中 root 之內；真目錄與不存在都放行。

    repo 若 commit 了一個指向任意位置的 `.maigo` symlink，沒有這道檢查，寫入端會被導出 repo 外。
    """
    link = Path(maigo)
    if not link.is_symlink():
        return
    root = Path(os.path.realpath(get_state_root()))
    resolved = Path(os.path.realpath(link))
    if not resolved.is_relative_to(root):
        raise ValueError(
            f"{link} is a symlink to {resolved}, outside the maigo state root {root}: "
            "path escapes the repository"
        )


# --------------------------------------------------------------------------- migrate


@dataclass
class WorktreePlan:
    worktree: Path
    maigo: Path
    state: str
    dirs: list[str] = field(default_factory=list)
    to_copy: list[str] = field(default_factory=list)
    identical: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    nested: list[str] = field(default_factory=list)


@dataclass
class MigrationPlan:
    identity: str
    target: Path
    worktrees: list[WorktreePlan]

    @property
    def has_conflicts(self) -> bool:
        return any(w.conflicts for w in self.worktrees)


def list_worktrees(cwd: str | Path) -> list[Path]:
    output = _run_git(cwd, "worktree", "list", "--porcelain")
    if not output:
        return []
    paths: list[Path] = []
    for block in output.split("\n\n"):
        lines = block.splitlines()
        if not lines or not lines[0].startswith("worktree "):
            continue
        if any(line.startswith("prunable") for line in lines):
            continue
        path = Path(lines[0].removeprefix("worktree "))
        if path.is_dir():
            paths.append(path)
    return paths


def _walk_entries(maigo: Path) -> tuple[list[str], list[str]]:
    dirs: list[str] = []
    files: list[str] = []
    for current, dirnames, filenames in os.walk(maigo, followlinks=False):
        base = Path(current)
        for name in list(dirnames):
            full = base / name
            rel = full.relative_to(maigo).as_posix()
            if full.is_symlink():
                dirnames.remove(name)
                files.append(rel)
            else:
                dirs.append(rel)
        files.extend((base / name).relative_to(maigo).as_posix() for name in filenames)
    return sorted(dirs), sorted(files)


def _same_entry(left: Path, right: Path) -> bool:
    if left.is_symlink() or right.is_symlink():
        return (
            left.is_symlink()
            and right.is_symlink()
            and os.readlink(left) == os.readlink(right)
        )
    if not (left.is_file() and right.is_file()):
        return False
    return filecmp.cmp(left, right, shallow=False)


def _is_real_dir(path: Path) -> bool:
    return path.is_dir() and not path.is_symlink()


def _find_holder(target: Path, claimed: dict[str, Path], rel: str) -> Path | None:
    """集中 root 已有、或前一個 worktree 已認領的同名項目（不分檔案或目錄）。"""
    existing = target / rel
    if os.path.lexists(existing):
        return existing
    return claimed.get(rel)


def build_migration_plan(cwd: str | Path) -> MigrationPlan | None:
    identity = resolve_identity(cwd)
    if identity is None:
        return None
    target = get_state_root() / identity
    claimed: dict[str, Path] = {}
    plans: list[WorktreePlan] = []

    for worktree in list_worktrees(cwd):
        maigo = worktree / MAIGO_DIRNAME
        if maigo.is_symlink():
            state = (
                STATUS_ALREADY_LINKED
                if _points_to(maigo, target)
                else STATUS_WRONG_TARGET
            )
            plans.append(WorktreePlan(worktree, maigo, state))
            continue
        if not maigo.exists():
            plans.append(WorktreePlan(worktree, maigo, "absent"))
            continue
        if not maigo.is_dir():
            plans.append(WorktreePlan(worktree, maigo, STATUS_BLOCKED))
            continue

        plan = WorktreePlan(worktree, maigo, STATUS_NEEDS_MIGRATION)
        dirs, files = _walk_entries(maigo)
        plan.dirs = dirs
        for rel in dirs:
            holder = _find_holder(target, claimed, rel)
            if holder is None:
                claimed[rel] = maigo / rel
            elif not _is_real_dir(holder):
                plan.conflicts.append(rel)
        for rel in files:
            source = maigo / rel
            holder = _find_holder(target, claimed, rel)
            if holder is None:
                claimed[rel] = source
                plan.to_copy.append(rel)
            elif _same_entry(source, holder):
                plan.identical.append(rel)
            else:
                plan.conflicts.append(rel)
        plan.nested = [rel for rel in dirs if rel == MAIGO_DIRNAME]
        plans.append(plan)
    return MigrationPlan(identity, target, plans)


def _copy_entry(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_symlink():
        os.symlink(os.readlink(source), destination)
    else:
        shutil.copy2(source, destination)


def _count_files(directory: Path) -> int:
    return sum(
        len(filenames) + sum((Path(cur) / d).is_symlink() for d in dirnames)
        for cur, dirnames, filenames in os.walk(directory, followlinks=False)
    )


def apply_migration(plan: MigrationPlan, now: datetime | None = None) -> list[str]:
    """回傳錯誤訊息清單；空表示成功。有衝突一律拒絕。"""
    if plan.has_conflicts:
        return ["有同名但內容不同的檔案，未做任何變更"]
    pending = [w for w in plan.worktrees if w.state == STATUS_NEEDS_MIGRATION]
    if not pending:
        return []

    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    backup_root = get_state_root() / BACKUP_DIRNAME / stamp
    errors: list[str] = []

    for index, wt in enumerate(pending):
        backup = backup_root / f"{index}-{wt.worktree.name}"
        shutil.copytree(wt.maigo, backup, symlinks=True)
        if _count_files(backup) != _count_files(wt.maigo):
            errors.append(f"{wt.maigo}: 備份檔數與原目錄不符，已中止")
            return errors

    plan.target.mkdir(parents=True, exist_ok=True)
    for wt in pending:
        for rel in wt.dirs:
            (plan.target / rel).mkdir(parents=True, exist_ok=True)
        for rel in wt.to_copy:
            destination = plan.target / rel
            if not os.path.lexists(destination):
                _copy_entry(wt.maigo / rel, destination)

    for wt in pending:
        mismatched = [
            rel
            for rel in (*wt.to_copy, *wt.identical)
            if not _same_entry(wt.maigo / rel, plan.target / rel)
        ] + [rel for rel in wt.dirs if not _is_real_dir(plan.target / rel)]
        if mismatched:
            errors.append(
                f"{wt.maigo}: 集中 root 有 {len(mismatched)} 個項目的種類或內容與原目錄不符，"
                f"未換成 symlink（例：{mismatched[0]}）"
            )
            continue
        if wt.maigo.is_symlink():
            continue
        shutil.rmtree(wt.maigo)
        wt.maigo.symlink_to(plan.target, target_is_directory=True)
    return errors


def _format_plan(plan: MigrationPlan, apply: bool) -> list[str]:
    lines = [
        f"identity: {plan.identity}",
        f"target: {plan.target}",
        f"mode: {'apply' if apply else 'dry-run'}",
    ]
    for wt in plan.worktrees:
        lines.append(
            f"worktree {wt.worktree}: {wt.state}"
            f" copy={len(wt.to_copy)} identical={len(wt.identical)}"
            f" conflicts={len(wt.conflicts)} nested={len(wt.nested)}"
        )
        lines.extend(f"  conflict: {rel}" for rel in wt.conflicts)
        lines.extend(
            f"  nested: {MAIGO_DIRNAME}/{rel} (保留，不刪)" for rel in wt.nested
        )
    return lines


def run_migrate(cwd: str, apply: bool) -> int:
    plan = build_migration_plan(cwd)
    if plan is None:
        print(f"error: {cwd} 不是 git repo", file=sys.stderr)
        return 1
    for line in _format_plan(plan, apply):
        print(line)
    if plan.has_conflicts:
        print("衝突：同名但內容不同，請人工決定後再跑；不會覆寫任何檔", file=sys.stderr)
        return 2
    if not apply:
        return 0
    errors = apply_migration(plan)
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("identity", "印出 repo identity 與集中 root 路徑"),
        ("link", "讓 <toplevel>/.maigo 成為指向集中 root 的 symlink"),
        ("migrate", "把各 worktree 的 .maigo/ 併進集中 root（預設 dry-run）"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--cwd", default=".", help="repo 內任一目錄（預設 .）")
        if name == "migrate":
            command.add_argument("--apply", action="store_true", help="真的寫入")
    args = parser.parse_args(argv)

    if args.command == "identity":
        identity = resolve_identity(args.cwd)
        if identity is None:
            print(f"error: {args.cwd} 不是 git repo", file=sys.stderr)
            return 1
        print(f"identity: {identity}")
        print(f"path: {get_state_root() / identity}")
        return 0
    if args.command == "link":
        result = ensure_link(args.cwd)
        print(f"status: {result.status}")
        if result.link is not None:
            print(f"link: {result.link}")
            print(f"target: {result.target}")
        ok = {STATUS_LINKED, STATUS_ALREADY_LINKED}
        return 0 if result.status in ok else 1
    return run_migrate(args.cwd, args.apply)


if __name__ == "__main__":
    sys.exit(main())
