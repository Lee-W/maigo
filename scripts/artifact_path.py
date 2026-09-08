#!/usr/bin/env python3
"""
Single source of truth for `.maigo/` markdown artifact paths (naming + ownership).

背景見 `.maigo/plan-maigo-artifact-collision.md`：`.maigo/` 底下固定檔名的
產物（`plan.md` / `review-rubric.md` / `review.md` / `triage-rubric.md` /
`pr-comments.md`）被兩個並行 session 覆寫過一次，因為它們共用同一個檔名，
語意上卻該有各自一份。

這個模組有**雙職責**，都是為了讓「拿到路徑就整份覆寫」在 API 層面做不到：

1. **命名**：`<kind>-<id>.md`，`<id>` 走四級來源鏈（`resolve_identifier()`），
   每一級都必須是事後可重新推導的——不是只要唯一就好。
2. **(c) 歸屬檢查**：`resolve_for_write()` 是唯一對外入口，`topic`
   （呼叫端打算寫進檔案第一行的 H1）是必填參數；同一次呼叫就完成「這個檔名
   目前屬於誰」的比對。沒有申報主題就拿不到路徑；主題不符時它不交出可寫入
   的路徑（`status="conflict"`, `path=None`），呼叫端必須先問使用者再決定
   要不要用 `suggested_path`。

沒有 hook 兜底（決策 5：不加任何 hook）——這個模組本身就是代償措施，程式碼
強制，不靠 agent 記性。散文只需要說「一律呼叫這支 script」。

命名層（純函式，不做任何 I/O）：`slugify(text)`、`github_ref(url, home_repo)`
（重用 `scripts/board_state.py` 既有實作，不重複解析 URL）、
`artifact_path(kind, identifier)`、`legacy_path(kind)`。

`resolve_identifier()` 與 `resolve_for_write()` 會做 I/O（本地 `git` 子行程、
讀檔案），不是純函式；`resolve_for_write()` 的 I/O 全部是唯讀，不建立、不
覆寫任何檔案——實際寫入是呼叫端的事，這個模組只算路徑、只讀既有檔案的 H1。

跑（CLI，給 markdown 寫手用）：

```
python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/artifact_path.py" plan \
    --topic "<H1 主題>" [--url URL] [--repo owner/name] [--cwd DIR]
```

stdout 第 1 行 `status: new|same_topic|conflict`；
非 conflict 時第 2 行 `path: .maigo/<kind>-<id>.md`；
conflict 時第 2 行 `conflict_owner: <既有 H1>`、第 3 行
`suggest: .maigo/<kind>-<id>-2.md`（候選檔名，須經使用者同意才可以用），
**exit 3**（非 0，讓 `&&` 串接的呼叫端直接停住），且不印任何可寫入的
`path:` 行。舊固定檔名存在時（不論 status）多印一行
`legacy_exists: .maigo/<kind>.md`（只供讀取退路，不當寫入目標）。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from board_state import github_ref

_KNOWN_KINDS = ("plan", "review-rubric", "review", "triage-rubric", "pr-comments")

_SLUG_INVALID_RE = re.compile(r"[^a-z0-9._-]+")
_SLUG_COLLAPSE_RE = re.compile(r"-{2,}")
_SLUG_MAX_LEN = 40

_H1_PREFIX = "# "


def slugify(text: str) -> str | None:
    """
    轉小寫 → 非 `[a-z0-9._-]` 換成 `-` → 連續 `-` 收成一個 → 去頭尾 `-`/`.`
    → 截斷 `_SLUG_MAX_LEN` 字元 → 空字串則回 `None` 讓呼叫端往下一級。

    純函式，不做任何 I/O。
    """
    lowered = text.lower()
    replaced = _SLUG_INVALID_RE.sub("-", lowered)
    collapsed = _SLUG_COLLAPSE_RE.sub("-", replaced)
    stripped = collapsed.strip("-.")
    truncated = stripped[:_SLUG_MAX_LEN]
    return truncated or None


def artifact_path(kind: str, identifier: str) -> str:
    """
    `(a)` 類命名：`.maigo/<kind>-<identifier>.md`。純函式。

    驗證 `kind` 屬於 `_KNOWN_KINDS`——CLI 有 `argparse choices` 擋著，但
    `resolve_for_write()` 這個函式庫入口（例如 `scripts/pr_context_cache.py`
    直接 import 呼叫）繞過 CLI，此處是兩個入口共同必經點。不驗證的話，帶
    `../` 的 `kind` 會讓算出來的路徑跳出 `.maigo/`（路徑穿越）。
    """
    if kind not in _KNOWN_KINDS:
        raise ValueError(f"unknown kind: {kind!r}; must be one of {_KNOWN_KINDS}")
    return f".maigo/{kind}-{identifier}.md"


def legacy_path(kind: str) -> str:
    """本計畫要修掉的舊固定檔名：`.maigo/<kind>.md`。只供讀取退路，不當寫入目標。"""
    return f".maigo/{kind}.md"


def _run_git(args: list[str], cwd: str | Path) -> str | None:
    """在 `cwd` 跑 `git <args>`；失敗（非 git repo、指令不存在、逾時）一律回 `None`。"""
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _rebase_original_branch_slug(cwd: str | Path) -> str | None:
    """
    進行中的 rebase 時，讀 rebase 記錄的原分支名，取代會在 `--continue`/
    `--amend` 之間移動的短 SHA。

    兩種 rebase backend 都要查（已在本機實測確認，非憑印象）：merge backend
    （預設）用 `<git-dir>/rebase-merge/head-name`；`--apply`（patch-based）
    backend 用 `<git-dir>/rebase-apply/head-name`。兩者格式相同，內容都是
    `refs/heads/<branch>\\n`。

    `<git-dir>` 一律用 `git rev-parse --git-dir` 取得，不自己組 `.git/`
    路徑——linked worktree 底下 `.git` 是檔案不是目錄，且每個 worktree 的
    rebase 狀態存在各自的 `.git/worktrees/<name>/` 下，只有 `--git-dir`
    的輸出會正確指過去。

    沒有進行中的 rebase、或檔案讀不到/格式不對 → `None`，呼叫端退回短 SHA。
    """
    git_dir = _run_git(["rev-parse", "--git-dir"], cwd)
    if not git_dir:
        return None
    git_dir_path = Path(cwd) / git_dir
    for rebase_dir in ("rebase-merge", "rebase-apply"):
        head_name_file = git_dir_path / rebase_dir / "head-name"
        try:
            content = head_name_file.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        branch = content.removeprefix("refs/heads/")
        slug = slugify(branch)
        if slug:
            return slug
    return None


def resolve_identifier(
    cwd: str | Path, url: str | None = None, home_repo: str = ""
) -> str:
    """
    四級識別碼鏈，由上往下第一個取得到的就用；永不退回固定檔名。

    1. `url` 給的 GitHub issue/PR → `github_ref()`（逐字沿用 `detail_path()` 規則）。
    2. 當前 branch（`git branch --show-current`）→ `slugify()`。
    3. detached HEAD：進行中的 rebase 用記錄的原分支名（見
       `_rebase_original_branch_slug()`，穩定、不隨 `--continue`/`--amend`
       移動）；純粹靜止的 detached HEAD 才用 `git rev-parse --short HEAD`
       （那種情況下 SHA 本身是穩定的）。
    4. 非 git repo：cwd 目錄名 → `slugify()`，空字串用 `unnamed`。

    會跑本地 `git` 子行程，不是純函式；不打任何網路請求。
    """
    if url:
        ref = github_ref(url, home_repo)
        if ref:
            return ref

    branch = _run_git(["branch", "--show-current"], cwd)
    if branch:
        slug = slugify(branch)
        if slug:
            return slug

    rebase_slug = _rebase_original_branch_slug(cwd)
    if rebase_slug:
        return rebase_slug

    short_sha = _run_git(["rev-parse", "--short", "HEAD"], cwd)
    if short_sha:
        return short_sha

    dir_slug = slugify(Path(cwd).resolve().name)
    return dir_slug or "unnamed"


def read_topic(path: Path) -> str | None:
    """
    讀檔案第一個 `^# ` 開頭的行，正規化空白後回傳；沒有這種行或檔案不存在 → `None`。

    只有 `FileNotFoundError`（真的不存在）才回 `None`——其餘讀取失敗（權限拒絕、
    二進位檔的 `UnicodeDecodeError`……）一律往上拋。「讀不到」不能被偷渡成
    「可以覆寫」：`resolve_for_write()` 靠 `existing_topic is None` 判斷
    `status="new"`，若把任何讀取失敗都吞成 `None`，權限被拒或內容看不懂的既有
    檔案就會被誤判成可安全覆寫的新檔。
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    for line in text.splitlines():
        if line.startswith(_H1_PREFIX):
            return _normalize_topic(line[len(_H1_PREFIX) :])
    return None


def _normalize_topic(text: str) -> str:
    return " ".join(text.split())


@dataclass(frozen=True)
class Resolution:
    status: str  # "new" | "same_topic" | "conflict"
    path: str | None  # 只有 status != "conflict" 才是可寫入的路徑
    existing_topic: str | None
    incoming_topic: str
    suggested_path: (
        str | None
    )  # conflict 時的候選（`<kind>-<id>-2.md`），須經使用者同意才用
    legacy_path: str | None  # 舊固定檔名存在時填，僅供讀取退路


def resolve_for_write(
    kind: str,
    topic: str,
    *,
    url: str | None = None,
    home_repo: str = "",
    cwd: str | Path = ".",
) -> Resolution:
    """
    (c) 歸屬檢查的唯一對外入口。`topic` 必填——沒有申報主題就拿不到路徑。

    同一次呼叫就完成命名（四級鏈）＋ 歸屬比對：目標路徑不存在，或存在但沒有
    H1 → `"new"`；H1 與 `topic` 相同 → `"same_topic"`（續寫是安全的）；H1
    不同 → `"conflict"`，`path=None`，呼叫端必須先問使用者才能用
    `suggested_path`。全程唯讀，不建立、不覆寫任何檔案。
    """
    identifier = resolve_identifier(cwd, url=url, home_repo=home_repo)
    path_str = artifact_path(kind, identifier)
    existing_topic = read_topic(Path(cwd) / path_str)

    legacy_str = legacy_path(kind)
    legacy_exists = (Path(cwd) / legacy_str).exists()
    legacy_result = legacy_str if legacy_exists else None

    normalized_incoming = _normalize_topic(topic)

    if existing_topic is None:
        return Resolution(
            status="new",
            path=path_str,
            existing_topic=None,
            incoming_topic=normalized_incoming,
            suggested_path=None,
            legacy_path=legacy_result,
        )
    if existing_topic == normalized_incoming:
        return Resolution(
            status="same_topic",
            path=path_str,
            existing_topic=existing_topic,
            incoming_topic=normalized_incoming,
            suggested_path=None,
            legacy_path=legacy_result,
        )
    return Resolution(
        status="conflict",
        path=None,
        existing_topic=existing_topic,
        incoming_topic=normalized_incoming,
        suggested_path=artifact_path(kind, f"{identifier}-2"),
        legacy_path=legacy_result,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=_KNOWN_KINDS)
    parser.add_argument("--topic", required=True, help="打算寫進檔案第一行的 H1 主題")
    parser.add_argument(
        "--url", default=None, help="GitHub issue/PR URL（第 1 級識別碼來源）"
    )
    parser.add_argument(
        "--repo", default="", help="cwd 所屬 repo（owner/name），判斷同 repo/跨 repo"
    )
    parser.add_argument("--cwd", default=".", help="計算識別碼與檢查既有檔案的目錄")
    args = parser.parse_args(argv)

    resolution = resolve_for_write(
        args.kind, args.topic, url=args.url, home_repo=args.repo, cwd=args.cwd
    )

    print(f"status: {resolution.status}")
    if resolution.status == "conflict":
        print(f"conflict_owner: {resolution.existing_topic}")
        print(f"suggest: {resolution.suggested_path}")
        if resolution.legacy_path:
            print(f"legacy_exists: {resolution.legacy_path}")
        return 3

    print(f"path: {resolution.path}")
    if resolution.legacy_path:
        print(f"legacy_exists: {resolution.legacy_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
