#!/usr/bin/env python3
"""Single source of truth for computing a sibling worktree's path + branch name.

背景：`skills/git-workflow/references/worktree-hygiene.md`（第 10–16 行）已經定義
好佈局慣例——worktree 是**主 checkout 的 sibling**，跟主 clone 放在同一個父目錄下，
命名 `<repo>-<topic>`，branch 名就是 `<topic>` 本身（不加前綴、不加 issue number）。
這支腳本只是把那條散文規則變成可重複執行的計算，**不發明新的路徑規則**。

純函式運算（跟 `artifact_path.py` 的命名層同一種「純計算」定位）：不跑任何 git
子行程、不建立任何檔案或 worktree——真的開 worktree 是呼叫端的事
（`git worktree add`），這支腳本只算路徑跟 branch 名。

複用既有的 `slugify()`（`scripts/artifact_path.py`），不重寫一份正則；
`slugify()` 回傳 `None`（空字串／純 CJK）時退回 `"unnamed"`，跟
`resolve_identifier()` 第四級 fallback 邏輯一致，不另創規則。

跑（CLI）：

```
python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/worktree_path.py" \
    --repo <name> --topic "<自由文字>" [--cwd DIR]
```

stdout 兩行：`path: <cwd 的父目錄>/<repo>-<slug>`、`branch: <slug>`。
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_path import slugify


@dataclass(frozen=True)
class WorktreeLocation:
    path: str
    branch: str


def compute_worktree_location(
    repo: str, topic: str, cwd: str | Path = "."
) -> WorktreeLocation:
    """算出 sibling worktree 的路徑與 branch 名。純函式，不做任何 I/O。"""
    slug = slugify(topic) or "unnamed"
    parent = Path(cwd).resolve().parent
    path = parent / f"{repo}-{slug}"
    return WorktreeLocation(path=str(path), branch=slug)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="主 checkout 的 repo 名")
    parser.add_argument(
        "--topic", required=True, help="自由文字，會被 slugify 成 branch 名"
    )
    parser.add_argument(
        "--cwd", default=".", help="主 checkout 目錄；worktree 開在它的父目錄下"
    )
    args = parser.parse_args(argv)

    location = compute_worktree_location(args.repo, args.topic, cwd=args.cwd)

    print(f"path: {location.path}")
    print(f"branch: {location.branch}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
