#!/usr/bin/env python3
"""Single source of truth for computing a nested worktree's path + branch name.

背景：`skills/git-workflow/references/worktree-hygiene.md` 定義好佈局慣例——
worktree 收在**主 worktree（main checkout）根目錄底下的 `.worktrees/<topic>`**，
branch 名就是 `<topic>` 本身（不加前綴、不加 issue number）。
這支腳本只是把那條散文規則變成可重複執行的計算，**不發明新的路徑規則**。

純函式運算（跟 `artifact_path.py` 的命名層同一種「純計算」定位）：不跑任何 git
子行程、不建立任何檔案或 worktree——真的開 worktree 是呼叫端的事
（`git worktree add`），這支腳本只算路徑跟 branch 名。

`--cwd` 必須是**主 worktree 的根目錄**，不是任意 cwd；取得方式見
`worktree-hygiene.md`：`git worktree list --porcelain | head -1 | sed 's/^worktree //'`
（porcelain 第一筆必為 main worktree）。若傳進來的是某個 linked worktree 或子目錄，
會算出巢狀再巢狀的路徑——這支腳本不偵測，責任在呼叫端。

複用既有的 `slugify()`（`scripts/artifact_path.py`），不重寫一份正則；
`slugify()` 回傳 `None`（空字串／純 CJK）時退回 `"unnamed"`，跟
`resolve_identifier()` 第四級 fallback 邏輯一致，不另創規則。

跑（CLI）：

```
python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/worktree_path.py" \
    --topic "<自由文字>" [--cwd DIR]
```

stdout 兩行：`path: <cwd>/.worktrees/<slug>`、`branch: <slug>`。
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


def compute_worktree_location(topic: str, cwd: str | Path = ".") -> WorktreeLocation:
    """算出 nested worktree 的路徑與 branch 名。純函式，不做任何 I/O。"""
    slug = slugify(topic) or "unnamed"
    root = Path(cwd).resolve()
    path = root / ".worktrees" / slug
    return WorktreeLocation(path=str(path), branch=slug)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--topic", required=True, help="自由文字，會被 slugify 成 branch 名"
    )
    parser.add_argument(
        "--cwd",
        default=".",
        help="主 worktree 根目錄；worktree 開在它底下的 `.worktrees/<slug>`",
    )
    args = parser.parse_args(argv)

    location = compute_worktree_location(args.topic, cwd=args.cwd)

    print(f"path: {location.path}")
    print(f"branch: {location.branch}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
