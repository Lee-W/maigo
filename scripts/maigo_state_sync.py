#!/usr/bin/env python3
"""把集中 root（`maigo_state.get_state_root()`）當成一個 git work tree，手動同步到使用者自己的私有 remote。

為什麼：`.maigo/` 的實體已集中在本機一個 root（見 `maigo_state.py`）。要讓另一台機器看到同一份
board、plan 與 review 報告，最小的做法是把這個 root 變成 git repo、remote 叫 `origin`。
本檔只包 git，不呼叫 `gh`、不自動解衝突、不常駐；`pull` 與 `push` 都由使用者手動觸發。

預設拒絕（default-deny）：

- `allowlist`（root 底下的明文檔，每行一個 `owner/repo`，`#` 開頭為註解）是唯一的放行來源。
  程式沒有內建任何預設項；`allow` 只是把一行加進去並重新產生排除規則。
- 排除規則由 allowlist 產生、寫進 `.git/info/exclude`（不追蹤，所以兩台機器各自 allow 不同 repo 也不會衝突；
  `allowlist` 用 `merge=union` 合併），逐層寫成 `/*`、`!/owner/`、`/owner/*`、`!/owner/repo/` …
  （git 在父目錄被 exclude 後無法用 `!` 重新納入子項，所以每一層都要列）。沒在 allowlist 的
  `<owner>/<repo>/`、`_local/`、`_migration-backup/`，以及每個 allowlisted repo 底下的 `_internal/`
  都不會被追蹤；唯一例外是 `_internal/board/dropped.jsonl`（只增不改的排除紀錄，用 `merge=union` 合併）。
- `push` 在 `.gitignore` 之外再做一道檢查：`git add -f` 可以繞過 ignore，所以 index 與尚未推送的
  commit 裡每個路徑都必須落在 allowlist 內（或是兩個中繼檔 `allowlist`／`.gitattributes`），
  否則拒絕、exit 1。含 `/Users/`、`/home/` 絕對路徑的檔案與 ≥ 1 MB 的檔案只警告，不擋。

跑（CLI）：

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/maigo_state_sync.py" init [--url URL]
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/maigo_state_sync.py" allow OWNER/REPO
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/maigo_state_sync.py" status [--fetch]
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/maigo_state_sync.py" pull
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/maigo_state_sync.py" push
```

`pull` 衝突時停下：印出衝突檔與 `git status --short`、exit 1，不 abort、不選邊，工作區維持 git
留下的衝突標記，讓使用者自己解完再 `git add` + `git commit`。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from maigo_state import SEGMENT_RE, get_state_root  # noqa: E402

LOCAL_GIT_TIMEOUT_SEC = 30
NETWORK_GIT_TIMEOUT_SEC = 120
REMOTE_NAME = "origin"
DEFAULT_BRANCH = "main"
ALLOWLIST_NAME = "allowlist"
EXCLUDE_REL = ".git/info/exclude"
STATUS_FETCH_TIMEOUT_SEC = 10
GITATTRIBUTES_NAME = ".gitattributes"
META_FILES = frozenset({ALLOWLIST_NAME, GITATTRIBUTES_NAME})
INTERNAL_DIRNAME = "_internal"
LEDGER_REL = f"{INTERNAL_DIRNAME}/board/dropped.jsonl"
LARGE_FILE_BYTES = 1024 * 1024
ABSOLUTE_PATH_RE = re.compile(rb"(?<![\w:/.-])/(?:Users|home)/")
ALLOWLIST_HEADER = (
    "# One owner/repo per line. Only these repos are synced; add lines with\n"
    "# `maigo_state_sync.py allow OWNER/REPO`.\n"
)
GITATTRIBUTES_TEXT = f"**/{LEDGER_REL} merge=union\n{ALLOWLIST_NAME} merge=union\n"


def run_git(
    root: Path, *args: str, network: bool = False, timeout: int | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout
        or (NETWORK_GIT_TIMEOUT_SEC if network else LOCAL_GIT_TIMEOUT_SEC),
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        check=False,
    )


def print_git_failure(proc: subprocess.CompletedProcess[str]) -> None:
    text = (proc.stderr or proc.stdout).strip()
    print(f"error: git failed (exit {proc.returncode}): {text}", file=sys.stderr)


def is_git_root(root: Path) -> bool:
    return (root / ".git").exists()


def validate_allow_entry(entry: str) -> str:
    parts = entry.strip().split("/")
    if len(parts) != 2 or not all(
        SEGMENT_RE.match(p) and p not in {".", "..", ".git"} for p in parts
    ):
        raise ValueError(f"not an owner/repo entry: {entry!r}")
    if parts[0].startswith((".", "_")):
        raise ValueError(f"reserved owner name (never synced): {entry!r}")
    return "/".join(parts)


def parse_allowlist(text: str) -> list[str]:
    entries = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        entries.append(validate_allow_entry(line))
    return sorted(set(entries))


def load_allowlist(root: Path) -> list[str]:
    path = root / ALLOWLIST_NAME
    if not path.is_file():
        return []
    return parse_allowlist(path.read_text(encoding="utf-8"))


def render_exclude_rules(entries: list[str]) -> str:
    lines = [
        "# generated from allowlist by maigo_state_sync.py; do not edit",
        "/*",
        f"!/{ALLOWLIST_NAME}",
        f"!/{GITATTRIBUTES_NAME}",
    ]
    owners: dict[str, list[str]] = {}
    for entry in entries:
        owner, repo = entry.split("/")
        owners.setdefault(owner, []).append(repo)
    for owner, repos in owners.items():
        lines += [f"!/{owner}/", f"/{owner}/*"]
        for repo in repos:
            base = f"{owner}/{repo}"
            lines += [
                f"!/{base}/",
                f"/{base}/{INTERNAL_DIRNAME}/*",
                f"!/{base}/{INTERNAL_DIRNAME}/board/",
                f"/{base}/{INTERNAL_DIRNAME}/board/*",
                f"!/{base}/{LEDGER_REL}",
            ]
    lines += ["*.zip", ".DS_Store"]
    return "\n".join(lines) + "\n"


def write_exclude(root: Path, entries: list[str]) -> bool:
    if not is_git_root(root):
        return False
    path = root / EXCLUDE_REL
    text = render_exclude_rules(entries)
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def has_merge_in_progress(root: Path) -> bool:
    if (root / ".git" / "MERGE_HEAD").exists():
        return True
    return bool(run_git(root, "ls-files", "-u").stdout.strip())


def find_disallowed_paths(paths: set[str], entries: list[str]) -> list[str]:
    allowed = set(entries)
    bad = []
    for path in sorted(paths):
        parts = path.split("/")
        if path in META_FILES:
            continue
        in_allowlisted_repo = len(parts) >= 3 and "/".join(parts[:2]) in allowed
        in_internal = in_allowlisted_repo and parts[2] == INTERNAL_DIRNAME
        if not in_allowlisted_repo or path.endswith(".zip"):
            bad.append(path)
        elif in_internal and "/".join(parts[2:]) != LEDGER_REL:
            bad.append(path)
    return bad


def split_nul(text: str) -> set[str]:
    return {p for p in text.split("\0") if p}


def get_branch(root: Path) -> str | None:
    proc = run_git(root, "symbolic-ref", "--short", "HEAD")
    return proc.stdout.strip() if proc.returncode == 0 else None


def has_commits(root: Path) -> bool:
    return run_git(root, "rev-parse", "--verify", "-q", "HEAD").returncode == 0


def has_remote_branch(root: Path, branch: str) -> bool:
    ref = f"refs/remotes/{REMOTE_NAME}/{branch}"
    return run_git(root, "rev-parse", "--verify", "-q", ref).returncode == 0


def has_remote(root: Path) -> bool:
    return run_git(root, "remote", "get-url", REMOTE_NAME).returncode == 0


def get_tracked_paths(root: Path) -> set[str]:
    return split_nul(run_git(root, "ls-files", "-z").stdout)


def get_outgoing_paths(root: Path, branch: str) -> set[str]:
    if not has_commits(root):
        return set()
    span = (
        f"{REMOTE_NAME}/{branch}..HEAD" if has_remote_branch(root, branch) else "HEAD"
    )
    proc = run_git(root, "log", "--name-only", "--format=", "-z", span)
    return split_nul(proc.stdout)


def commit_all(root: Path, message: str) -> subprocess.CompletedProcess[str] | None:
    """`git add -A`（受排除規則約束）後有東西才 commit；回傳失敗的 proc，成功或無事回 None。"""
    proc = run_git(root, "add", "-A")
    if proc.returncode != 0:
        return proc
    if run_git(root, "diff", "--cached", "--quiet").returncode == 0:
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    proc = run_git(root, "commit", "-q", "-m", f"{message} {stamp}")
    return proc if proc.returncode != 0 else None


def scan_outgoing_warnings(root: Path, paths: set[str]) -> list[str]:
    warnings = []
    for rel in sorted(paths):
        path = root / rel
        if not path.is_file():
            continue
        size = path.stat().st_size
        if size >= LARGE_FILE_BYTES:
            warnings.append(f"{rel}: {size} bytes (>= 1 MB)")
        if ABSOLUTE_PATH_RE.search(path.read_bytes()):
            warnings.append(f"{rel}: contains an absolute /Users/ or /home/ path")
    return warnings


def get_repo_context(root: Path) -> tuple[list[str], str] | None:
    """驗證同步前置條件；失敗時印出原因並回 None。"""
    if not is_git_root(root):
        print(
            f"error: {root} is not a git repository; run `init` first", file=sys.stderr
        )
        return None
    if not has_remote(root):
        print(f"error: remote '{REMOTE_NAME}' is not configured", file=sys.stderr)
        return None
    try:
        entries = load_allowlist(root)
    except ValueError as exc:
        print(f"error: invalid {ALLOWLIST_NAME}: {exc}", file=sys.stderr)
        return None
    branch = get_branch(root)
    if branch is None:
        print("error: HEAD is detached; check out a branch first", file=sys.stderr)
        return None
    return entries, branch


def run_init(url: str | None) -> int:
    root = get_state_root()
    root.mkdir(parents=True, exist_ok=True)
    if not is_git_root(root):
        proc = run_git(root, "init", "-q", "-b", DEFAULT_BRANCH)
        if proc.returncode != 0:
            print_git_failure(proc)
            return 1
    if url:
        current = run_git(root, "remote", "get-url", REMOTE_NAME)
        if current.returncode != 0:
            proc = run_git(root, "remote", "add", REMOTE_NAME, url)
            if proc.returncode != 0:
                print_git_failure(proc)
                return 1
        elif current.stdout.strip() != url:
            print(
                f"error: remote '{REMOTE_NAME}' already points to {current.stdout.strip()}",
                file=sys.stderr,
            )
            return 1
    allowlist = root / ALLOWLIST_NAME
    if not allowlist.exists():
        allowlist.write_text(ALLOWLIST_HEADER, encoding="utf-8")
    attributes = root / GITATTRIBUTES_NAME
    if not attributes.exists():
        attributes.write_text(GITATTRIBUTES_TEXT, encoding="utf-8")
    try:
        write_exclude(root, load_allowlist(root))
    except ValueError as exc:
        print(f"error: invalid {ALLOWLIST_NAME}: {exc}", file=sys.stderr)
        return 1
    print(f"initialized: {root}")
    print("next: `allow OWNER/REPO` for each repo to sync, then `push`")
    return 0


def run_allow(entry: str) -> int:
    root = get_state_root()
    try:
        normalized = validate_allow_entry(entry)
        entries = load_allowlist(root)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    root.mkdir(parents=True, exist_ok=True)
    if normalized in entries:
        print(f"already allowed: {normalized}")
    else:
        entries = sorted({*entries, normalized})
        (root / ALLOWLIST_NAME).write_text(
            ALLOWLIST_HEADER + "".join(f"{e}\n" for e in entries), encoding="utf-8"
        )
        print(f"allowed: {normalized}")
    write_exclude(root, entries)
    return 0


def get_ahead_behind(root: Path, branch: str) -> tuple[int, int] | None:
    if not has_remote_branch(root, branch):
        return (0, 0) if not has_commits(root) else None
    if not has_commits(root):
        count = run_git(root, "rev-list", "--count", f"{REMOTE_NAME}/{branch}")
        return 0, int(count.stdout.strip())
    proc = run_git(
        root, "rev-list", "--left-right", "--count", f"HEAD...{REMOTE_NAME}/{branch}"
    )
    ahead, behind = proc.stdout.split()
    return int(ahead), int(behind)


def run_status(fetch: bool) -> int:
    root = get_state_root()
    if not is_git_root(root):
        print(f"state root {root} is not a git repository; sync is not set up")
        return 0
    print(f"root: {root}")
    try:
        entries: list[str] | None = load_allowlist(root)
        write_exclude(root, entries or [])
    except ValueError as exc:
        entries = None
        print(f"warning: invalid {ALLOWLIST_NAME}: {exc}")
    branch = get_branch(root) or "(detached)"
    print(f"branch: {branch}")
    if not has_remote(root):
        print(f"remote: none ('{REMOTE_NAME}' is not configured)")
    else:
        if fetch:
            try:
                proc = run_git(
                    root,
                    "fetch",
                    "-q",
                    REMOTE_NAME,
                    network=True,
                    timeout=STATUS_FETCH_TIMEOUT_SEC,
                )
                text = (proc.stderr or proc.stdout).strip()
                failed = proc.returncode != 0
            except subprocess.TimeoutExpired:
                text, failed = f"timed out after {STATUS_FETCH_TIMEOUT_SEC}s", True
            if failed:
                print(f"warning: fetch failed, counts may be stale: {text}")
        counts = get_ahead_behind(root, branch)
        if counts is None:
            print(
                f"remote: {REMOTE_NAME}/{branch} not found (never pushed or not fetched)"
            )
        else:
            print(f"ahead: {counts[0]}")
            print(f"behind: {counts[1]}")
            if not has_commits(root) and counts[1]:
                print(
                    "note: no local commit yet; the remote already has history"
                    " (clone it instead of `init`, see the docs)"
                )
    changed = [
        line
        for line in run_git(root, "status", "--porcelain").stdout.splitlines()
        if line
    ]
    print(f"uncommitted: {len(changed)}")
    for entry in entries or []:
        tracked = run_git(root, "ls-files", "-z", "--", f"{entry}/").stdout
        if (root / entry).is_dir() and not tracked:
            print(f"untracked-allowlist: {entry}")
    return 0


def list_conflicts(root: Path) -> list[str]:
    proc = run_git(root, "diff", "--name-only", "--diff-filter=U")
    return [line for line in proc.stdout.splitlines() if line]


def print_conflict_report(root: Path) -> None:
    print("conflicts:", file=sys.stderr)
    for path in list_conflicts(root):
        print(f"  {path}", file=sys.stderr)
    status = run_git(root, "status", "--short").stdout.rstrip()
    print(f"git status --short:\n{status}", file=sys.stderr)
    print(
        f"resolve the markers by hand in {root}, then `git add` + `git commit`;"
        " to give up: `git merge --abort`",
        file=sys.stderr,
    )


def run_pull() -> int:
    root = get_state_root()
    context = get_repo_context(root)
    if context is None:
        return 1
    entries, branch = context
    if has_merge_in_progress(root):
        print("error: a merge is already in progress", file=sys.stderr)
        print_conflict_report(root)
        return 1
    write_exclude(root, entries)
    failed = commit_all(root, "maigo-state: local snapshot before pull")
    if failed is not None:
        print_git_failure(failed)
        return 1
    proc = run_git(root, "fetch", "-q", REMOTE_NAME, network=True)
    if proc.returncode != 0:
        print_git_failure(proc)
        return 1
    if not has_remote_branch(root, branch):
        print(f"{REMOTE_NAME}/{branch} does not exist yet; nothing to pull")
        refs = run_git(
            root,
            "for-each-ref",
            "--format=%(refname:short)",
            f"refs/remotes/{REMOTE_NAME}",
        ).stdout.split()
        others = [r for r in refs if r != f"{REMOTE_NAME}/HEAD"]
        if others:
            print(
                f"warning: the remote has other branches ({', '.join(others)});"
                f" current branch is {branch}",
                file=sys.stderr,
            )
        return 0
    proc = run_git(root, "merge", "--no-edit", f"{REMOTE_NAME}/{branch}")
    if proc.returncode == 0:
        print(proc.stdout.strip() or "already up to date")
        write_exclude(root, load_allowlist(root))
        return 0
    if list_conflicts(root):
        print_conflict_report(root)
    else:
        print_git_failure(proc)
    return 1


def run_push() -> int:
    root = get_state_root()
    context = get_repo_context(root)
    if context is None:
        return 1
    entries, branch = context
    if has_merge_in_progress(root):
        print("error: a merge is in progress; resolve it first", file=sys.stderr)
        print_conflict_report(root)
        return 1
    write_exclude(root, entries)
    proc = run_git(root, "add", "-A")
    if proc.returncode != 0:
        print_git_failure(proc)
        return 1
    bad = find_disallowed_paths(
        get_tracked_paths(root) | get_outgoing_paths(root, branch), entries
    )
    if bad:
        print("error: refusing to push; paths outside the allowlist:", file=sys.stderr)
        for path in bad:
            print(f"  {path}", file=sys.stderr)
        print(
            "`git rm --cached` them (history too if already committed), or `allow` the repo",
            file=sys.stderr,
        )
        return 1
    failed = commit_all(root, "maigo-state: sync")
    if failed is not None:
        print_git_failure(failed)
        return 1
    if not has_commits(root):
        print("nothing to push")
        return 0
    for warning in scan_outgoing_warnings(root, get_outgoing_paths(root, branch)):
        print(f"warning: {warning}", file=sys.stderr)
    proc = run_git(root, "push", "-u", REMOTE_NAME, branch, network=True)
    if proc.returncode != 0:
        print_git_failure(proc)
        print("if the remote is ahead, run `pull` first", file=sys.stderr)
        return 1
    print((proc.stdout + proc.stderr).strip() or f"pushed {branch}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser(
        "init", help="把集中 root 變成 git repo，建立中繼檔與排除規則"
    )
    init.add_argument("--url", help="remote origin 的 URL")
    allow = sub.add_parser("allow", help="把 OWNER/REPO 加進 allowlist 並重產排除規則")
    allow.add_argument("entry", metavar="OWNER/REPO")
    status = sub.add_parser(
        "status", help="印出 ahead／behind 與尚未追蹤的 allowlist 目錄"
    )
    status.add_argument("--fetch", action="store_true", help="先 fetch origin 再比較")
    sub.add_parser(
        "pull", help="先 commit 本機變更，再 fetch 並 merge origin；衝突時停下"
    )
    sub.add_parser("push", help="檢查 allowlist 後 commit 並推到 origin")
    args = parser.parse_args(argv)

    try:
        if args.command == "init":
            return run_init(args.url)
        if args.command == "allow":
            return run_allow(args.entry)
        if args.command == "status":
            return run_status(args.fetch)
        if args.command == "pull":
            return run_pull()
        return run_push()
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
