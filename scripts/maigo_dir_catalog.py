#!/usr/bin/env python3
"""Single source of truth for `.maigo/` top-level markdown 型錄分類。

背景：`.maigo/` 頂層散著沒有主人的舊檔（`board-design.md` / `index.md` /
`plan.md` 這類），沒有任何一份文件或程式碼描述「`.maigo/` 底下有哪些檔、
各自的正典是誰」。這支腳本是唯讀掃描器，把每個頂層 `*.md` 檔分成四類。

**不重複列一份 kind 清單字面值**——已知種類直接 `from scripts.artifact_path
import _KNOWN_KINDS`，這是唯一正典來源；平行維護第二份清單正是要避免的漂移。

四類：

(a) 已知種類的識別碼命名：`<kind>-<id>.md`，`kind` 屬於 `_KNOWN_KINDS`
    （例：`plan-fix-dag-run-stall.md`、`review-42.md`）
(b) 已知種類的舊固定檔名：`<kind>.md`（例：`plan.md`、`review-rubric.md`）
(c) 已登記的非 artifact 檔——目前只有 `board.md`。`.maigo/i/` 整個子目錄
    不在這支腳本管，`commands/board.md` 已經有自己的孤兒偵測邏輯（比對
    `.maigo/i/*.md` 與 board 索引行），兩者不要疊床架屋。
(d) 其餘全部 → 未登記檔案。用「不在白名單內」的反向判準，不列一份已知
    垃圾檔名的黑名單——黑名單會漏掉下一個手動殘留檔。

`_KNOWN_KINDS` 裡有些 kind 名互為前綴（`review` / `review-rubric`），比對時
一律先試最長的 kind，避免 `review-rubric-42.md` 被 `review` 錯誤搶先吃掉
（吃成 kind="review", id="rubric-42"）。

純函式：`categorize(names)` 不做任何 I/O。`scan(maigo_dir)` 做唯讀 I/O
（列出目錄內容），不建立、不覆寫、不刪除任何檔案。

跑（CLI）：

```
python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/maigo_dir_catalog.py" [--dir .maigo]
```
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_path import _KNOWN_KINDS

_REGISTERED_NON_ARTIFACT_FILES = ("board.md",)

# 比對時先試最長的 kind，避免短 kind（如 "review"）搶先吃掉長 kind 的檔名
# （如 "review-rubric-42.md"）。
_KINDS_BY_LENGTH_DESC = tuple(sorted(_KNOWN_KINDS, key=len, reverse=True))


@dataclass
class Catalog:
    identifier_named: list[str] = field(default_factory=list)
    legacy_fixed_name: list[str] = field(default_factory=list)
    registered_non_artifact: list[str] = field(default_factory=list)
    unregistered: list[str] = field(default_factory=list)


def categorize(names: list[str]) -> Catalog:
    """把一批頂層 `.maigo/*.md` 檔名分成四類。純函式，不做任何 I/O。"""
    catalog = Catalog()
    for name in sorted(names):
        if not name.endswith(".md"):
            catalog.unregistered.append(name)
            continue
        stem = name[: -len(".md")]

        if name in _REGISTERED_NON_ARTIFACT_FILES:
            catalog.registered_non_artifact.append(name)
            continue

        matched_kind = None
        for kind in _KINDS_BY_LENGTH_DESC:
            if stem == kind:
                matched_kind = ("legacy", kind)
                break
            if stem.startswith(f"{kind}-") and len(stem) > len(kind) + 1:
                matched_kind = ("identifier", kind)
                break

        if matched_kind is None:
            catalog.unregistered.append(name)
        elif matched_kind[0] == "legacy":
            catalog.legacy_fixed_name.append(name)
        else:
            catalog.identifier_named.append(name)

    return catalog


def scan(maigo_dir: str | Path) -> Catalog:
    """對給定的 `.maigo/` 目錄做唯讀掃描，只看頂層 `*.md` 檔（不遞迴進 `i/`）。

    目錄不存在時回傳全空的 `Catalog`（不建立目錄，不當錯誤）。
    """
    root = Path(maigo_dir)
    if not root.is_dir():
        return Catalog()
    names = [p.name for p in root.iterdir() if p.is_file() and p.suffix == ".md"]
    return categorize(names)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dir", default=".maigo", help="要掃描的 .maigo/ 目錄（預設 .maigo）"
    )
    args = parser.parse_args(argv)

    catalog = scan(args.dir)

    print("identifier_named:")
    for name in catalog.identifier_named:
        print(f"  {name}")
    print("legacy_fixed_name:")
    for name in catalog.legacy_fixed_name:
        print(f"  {name}")
    print("registered_non_artifact:")
    for name in catalog.registered_non_artifact:
        print(f"  {name}")
    print("unregistered:")
    for name in catalog.unregistered:
        print(f"  {name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
