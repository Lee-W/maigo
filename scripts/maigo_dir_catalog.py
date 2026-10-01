#!/usr/bin/env python3
"""
Single source of truth for `.maigo/` markdown artifact 型錄分類。

背景：`.maigo/` 頂層散著沒有主人的舊檔（`board-design.md` / `index.md` /
`plan.md` 這類），沒有任何一份文件或程式碼描述「`.maigo/` 底下有哪些檔、
各自的正典是誰」；後續又加入按 PR/issue 分資料夾的巢狀佈局
（`.maigo/review/<id>/*.md`、`.maigo/issue/<id>/*.md`），型錄要能同時認出
新舊兩種形狀。這支腳本是唯讀掃描器，把每個 `.maigo/` 底下的相關檔分成六類。

**不重複列一份 kind 清單字面值**——已知種類直接 `from scripts.artifact_path
import _KNOWN_KINDS`，這是唯一正典來源；平行維護第二份清單正是要避免的漂移。

六類：

(a) 巢狀佈局：`<group>/<id>/<stem>[-<attempt>].md`，`(group, stem)` 對得上
    `artifact_path._NESTED_LAYOUT` 的某個 kind（例：`review/58543/rubric.md`、
    `issue/12/rubric-2.md`）→ `nested`。
(b) 巢狀 kind 的分目錄前扁平檔：`<kind>-<id>.md`，`kind` 屬於巢狀 kind
    （例：`review-42.md`、`review-rubric-42.md`）→ `flat_identifier`，待遷移。
(c) 非巢狀 kind（目前只有 `plan`）的識別碼命名：`<kind>-<id>.md`
    （例：`plan-fix-dag-run-stall.md`）→ `identifier_named`。
(d) 已知種類的舊固定檔名：`<kind>.md`（例：`plan.md`、`review-rubric.md`）
    → `legacy_fixed_name`。
(e) 已登記的非 artifact 檔——`board.md` 與舊版 board 檔名 `review-board.md`
    （`commands/board.md` 仍會偵測並遷移它，不是 review kind 的產物）
    → `registered_non_artifact`。
(f) 其餘全部（含找不到 producer 的 `review-batch-state.md`）
    → `unregistered`。用「不在白名單內」的反向判準，不列一份已知垃圾檔名的
    黑名單——黑名單會漏掉下一個手動殘留檔。

`_KNOWN_KINDS` 裡有些 kind 名互為前綴（`review` / `review-rubric`），比對時
一律先試最長的 kind，避免 `review-rubric-42.md` 被 `review` 錯誤搶先吃掉
（吃成 kind="review", id="rubric-42"）。

`_internal/` 不屬於六類中的任何一類：那是只給機器讀的狀態目錄（例：
`_internal/board/dropped.jsonl`），型錄永遠不列。

純函式：`categorize(names)`、`split_flat_name(name)` 不做任何 I/O。
`scan(maigo_dir)` 做唯讀 I/O（列出目錄內容，含 `review/*/*.md` 與
`issue/*/*.md` 兩層遞迴，不進 `i/` 或更深），不建立、不覆寫、不刪除任何檔案。

跑（CLI）：

```
python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/maigo_dir_catalog.py" [--dir .maigo]
```
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_path import _FLAT_NAME_LOOKALIKES, _KNOWN_KINDS, _NESTED_LAYOUT

_REGISTERED_NON_ARTIFACT_FILES = ("board.md", "review-board.md")

# 內部機器狀態目錄，型錄永遠不列。
INTERNAL_DIR = "_internal"

# 比對時先試最長的 kind，避免短 kind（如 "review"）搶先吃掉長 kind 的檔名
# （如 "review-rubric-42.md"）。
_KINDS_BY_LENGTH_DESC = tuple(sorted(_KNOWN_KINDS, key=len, reverse=True))

_NESTED_GROUP_STEMS = set(_NESTED_LAYOUT.values())
_NESTED_GROUP_NAMES = sorted({group for group, _stem in _NESTED_LAYOUT.values()})
_ATTEMPT_SUFFIX_RE = re.compile(r"-\d+$")


@dataclass
class Catalog:
    identifier_named: list[str] = field(default_factory=list)
    flat_identifier: list[str] = field(default_factory=list)
    nested: list[str] = field(default_factory=list)
    legacy_fixed_name: list[str] = field(default_factory=list)
    registered_non_artifact: list[str] = field(default_factory=list)
    unregistered: list[str] = field(default_factory=list)


def split_flat_name(name: str) -> tuple[str, str] | None:
    """
    把扁平 `<kind>-<id>.md` 檔名拆成 `(kind, id)`。

    沿用 `categorize()` 的最長 kind 優先比對，遷移腳本共用同一份邏輯，不要
    各寫一份。不是這個形狀（非 `.md`、`<kind>.md` 固定檔名、kind 不在
    `_KNOWN_KINDS`）一律回 `None`。純函式，不做任何 I/O。
    """
    if not name.endswith(".md"):
        return None
    stem = name[: -len(".md")]
    for kind in _KINDS_BY_LENGTH_DESC:
        prefix = f"{kind}-"
        if stem.startswith(prefix) and len(stem) > len(prefix):
            return kind, stem[len(prefix) :]
    return None


def _categorize_nested_relpath(relpath: str, catalog: Catalog) -> None:
    """`<group>/<id>/<stem>[-<attempt>].md` 兩層相對路徑分類。"""
    parts = relpath.split("/")
    if len(parts) == 3 and parts[2].endswith(".md"):
        group, _identifier, filename = parts
        stem = filename[: -len(".md")]
        stem_no_attempt = _ATTEMPT_SUFFIX_RE.sub("", stem)
        if (group, stem_no_attempt) in _NESTED_GROUP_STEMS:
            catalog.nested.append(relpath)
            return
    catalog.unregistered.append(relpath)


def categorize(names: list[str]) -> Catalog:
    """
    把一批 `.maigo/` 相關檔名（頂層檔名或 `<group>/<id>/<file>` 兩層相對
    路徑）分成六類。純函式，不做任何 I/O。
    """
    catalog = Catalog()
    for name in sorted(names):
        if name.startswith(f"{INTERNAL_DIR}/"):
            continue
        if "/" in name:
            _categorize_nested_relpath(name, catalog)
            continue

        if not name.endswith(".md"):
            catalog.unregistered.append(name)
            continue

        if name in _REGISTERED_NON_ARTIFACT_FILES:
            catalog.registered_non_artifact.append(name)
            continue
        if name in _FLAT_NAME_LOOKALIKES:
            catalog.unregistered.append(name)
            continue

        stem = name[: -len(".md")]
        if stem in _KNOWN_KINDS:
            catalog.legacy_fixed_name.append(name)
            continue

        split = split_flat_name(name)
        if split is None:
            catalog.unregistered.append(name)
        elif split[0] in _NESTED_LAYOUT:
            catalog.flat_identifier.append(name)
        else:
            catalog.identifier_named.append(name)

    return catalog


def scan(maigo_dir: str | Path) -> Catalog:
    """
    對給定的 `.maigo/` 目錄做唯讀掃描：頂層 `*.md` 檔，加上兩層遞迴
    `review/*/*.md` 與 `issue/*/*.md`（不進 `i/`，其他深度一律不收）。

    目錄不存在時回傳全空的 `Catalog`（不建立目錄，不當錯誤）。
    """
    root = Path(maigo_dir)
    if not root.is_dir():
        return Catalog()
    names = [p.name for p in root.iterdir() if p.is_file() and p.suffix == ".md"]
    for group in _NESTED_GROUP_NAMES:
        group_dir = root / group
        if not group_dir.is_dir():
            continue
        for id_dir in group_dir.iterdir():
            if not id_dir.is_dir():
                continue
            for candidate in id_dir.iterdir():
                if candidate.is_file() and candidate.suffix == ".md":
                    names.append(f"{group}/{id_dir.name}/{candidate.name}")
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
    print("flat_identifier:")
    for name in catalog.flat_identifier:
        print(f"  {name}")
    print("nested:")
    for name in catalog.nested:
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
