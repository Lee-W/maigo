#!/usr/bin/env python3
"""
Single source of truth for `.maigo/` markdown artifact 型錄分類。

背景：`.maigo/` 頂層散著沒有主人的舊檔（`board-design.md` / `index.md` /
`plan.md` 這類），沒有任何一份文件或程式碼描述「`.maigo/` 底下有哪些檔、
各自的正典是誰」；後續又加入按 PR/issue 分資料夾的巢狀佈局
（`.maigo/review/<id>/*.md`、`.maigo/pr/<id>/*.md`、`.maigo/issue/<id>/*.md`），型錄要能同時認出
新舊兩種形狀。這支腳本是唯讀掃描器，把每個 `.maigo/` 底下的相關檔分成六類。

**不重複列一份 kind 清單字面值**——已知種類直接 `from scripts.artifact_path
import _KNOWN_KINDS`，這是唯一正典來源；平行維護第二份清單正是要避免的漂移。

六類：

(a) 巢狀佈局：`<group>/<id>/<stem>[-<attempt>].md`，`(group, stem)` 對得上
    `artifact_path.nested_locations()` 的某個 kind（例：`review/58543/rubric.md`、
    `pr/58543/reply-draft.md`、`issue/12/rubric-2.md`）→ `nested`。
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

全樹模式 `scan_tree(maigo_dir)`（CLI `--tree`）另外看得到 `scan()` 刻意不看的
東西：非 `.md` 檔、`evals/` 這類未知頂層目錄（整個目錄只算一筆）、`_archive/`、
`topic/`、`_internal/`（只計數）、`.maigo/.maigo/`（hook 在子目錄 cwd 下長出的
巢狀殘留）、頂層的舊機器 log。分類與 `scan()` 的六類互不影響——`scan()` 的語意
和既有測試不變。

純函式：`categorize(names)`、`split_flat_name(name)` 不做任何 I/O。
`scan(maigo_dir)` 做唯讀 I/O（列出目錄內容，含 `review/*/*.md`、`pr/*/*.md` 與
`issue/*/*.md` 兩層遞迴，不進 `i/` 或更深），不建立、不覆寫、不刪除任何檔案。

跑（CLI）：

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/maigo_dir_catalog.py" [--dir .maigo] [--tree]
```
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_path import (
    _FLAT_NAME_LOOKALIKES,
    _KNOWN_KINDS,
    _NESTED_LAYOUT,
    nested_locations,
)

_REGISTERED_NON_ARTIFACT_FILES = ("board.md", "review-board.md")

# 內部機器狀態目錄，型錄永遠不列。
INTERNAL_DIR = "_internal"

# 比對時先試最長的 kind，避免短 kind（如 "review"）搶先吃掉長 kind 的檔名
# （如 "review-rubric-42.md"）。
_KINDS_BY_LENGTH_DESC = tuple(sorted(_KNOWN_KINDS, key=len, reverse=True))

_ALL_NESTED_LOCATIONS = {
    location for kind in _NESTED_LAYOUT for location in nested_locations(kind)
}
_NESTED_GROUP_STEMS = set(_ALL_NESTED_LOCATIONS)
_NESTED_GROUP_NAMES = sorted({group for group, _stem in _ALL_NESTED_LOCATIONS})
_ATTEMPT_SUFFIX_RE = re.compile(r"-\d+$")

# 全樹模式用：含 plan 的所有 `(group, stem)`（`topic/` 只有 plan 用）。
_TREE_LOCATIONS = {
    location for kind in _KNOWN_KINDS for location in nested_locations(kind)
}
_TREE_GROUP_NAMES = frozenset(group for group, _stem in _TREE_LOCATIONS)

ARCHIVE_DIR = "_archive"
NESTED_DOT_MAIGO_DIR = ".maigo"
BOARD_DETAIL_DIR = "i"
# 升級前 hook 直接寫在 `.maigo/` 頂層的機器 log；新位置是 `_internal/log/`。
LEGACY_INTERNAL_LOG_NAMES = frozenset(
    {
        "session-head.json",
        "token-usage.jsonl",
        "test-failures.jsonl",
        "soyo-must-fix.jsonl",
    }
)
TREE_CATEGORIES = (
    "nested",
    "legacy_fixed_name",
    "flat_identifier",
    "identifier_named",
    "legacy_internal_log",
    "archive",
    "board",
    "internal",
    "nested_dot_maigo",
    "unregistered",
)


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
    `review/*/*.md`、`pr/*/*.md` 與 `issue/*/*.md`（不進 `i/`，其他深度一律不收）。

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


def _mtime_iso(path: Path) -> str:
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return "unknown"
    return datetime.fromtimestamp(stamp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _count_files(directory: Path) -> int:
    return sum(1 for p in directory.rglob("*") if p.is_file())


def _real_dir(path: Path) -> bool:
    return path.is_dir() and not path.is_symlink()


def _tree_group_dir(root: Path, group: str, tree: dict[str, list[str]]) -> None:
    """`<group>/<id>/<file>`：登記過的 `(group, stem)` 進 nested，其餘逐檔進 unregistered。"""
    group_dir = root / group
    for id_dir in sorted(group_dir.iterdir()):
        rel = f"{group}/{id_dir.name}"
        if not _real_dir(id_dir):
            tree["unregistered"].append(rel)
            continue
        for candidate in sorted(id_dir.iterdir()):
            entry = f"{rel}/{candidate.name}"
            if not _real_dir(candidate) and candidate.name.endswith(".md"):
                stem = _ATTEMPT_SUFFIX_RE.sub("", candidate.name[: -len(".md")])
                if (group, stem) in _TREE_LOCATIONS:
                    tree["nested"].append(entry)
                    continue
            tree["unregistered"].append(f"{entry}/" if _real_dir(candidate) else entry)


def _tree_archive(root: Path, tree: dict[str, list[str]]) -> None:
    """`_archive/` 鏡射原相對路徑：往下兩層，每筆記錄 mtime（供保留期判斷）。"""
    archive_dir = root / ARCHIVE_DIR
    for group_entry in sorted(archive_dir.iterdir()):
        group_rel = f"{ARCHIVE_DIR}/{group_entry.name}"
        if _real_dir(group_entry):
            children = sorted(group_entry.iterdir())
            if not children:
                tree["archive"].append(
                    f"{group_rel}/ (mtime {_mtime_iso(group_entry)})"
                )
            for child in children:
                tree["archive"].append(
                    f"{group_rel}/{child.name} (mtime {_mtime_iso(child)})"
                )
        else:
            tree["archive"].append(f"{group_rel} (mtime {_mtime_iso(group_entry)})")


def _tree_top_level_file(path: Path, tree: dict[str, list[str]]) -> None:
    name = path.name
    if name in LEGACY_INTERNAL_LOG_NAMES:
        tree["legacy_internal_log"].append(name)
        return
    if not name.endswith(".md"):
        tree["unregistered"].append(name)
        return
    catalog = categorize([name])
    if catalog.registered_non_artifact:
        tree["board"].append(name)
    elif catalog.legacy_fixed_name:
        tree["legacy_fixed_name"].append(name)
    elif catalog.flat_identifier:
        tree["flat_identifier"].append(name)
    elif catalog.identifier_named:
        tree["identifier_named"].append(name)
    else:
        tree["unregistered"].append(name)


def scan_tree(maigo_dir: str | Path) -> dict[str, list[str]]:
    """
    全樹唯讀掃描：回傳 `TREE_CATEGORIES` 每個 key 的清單（沒有項目也有 key），
    路徑相對 `maigo_dir`。

    與 `scan()` 的差別：看得到非 `.md` 檔；未知頂層目錄整個算一筆（`evals/`
    只出現一次，不逐檔列）；`_archive/`（記錄 mtime）、`topic/`、`_internal/`
    （只計數）、`.maigo/.maigo/` 與頂層舊機器 log 各有自己的類別。
    `_archive/` 以外的項目不記 mtime。不跟隨 symlink，不建立、不覆寫任何檔案。
    目錄不存在時回傳全空的 dict。
    """
    tree: dict[str, list[str]] = {category: [] for category in TREE_CATEGORIES}
    root = Path(maigo_dir)
    if not root.is_dir():
        return tree
    for entry in sorted(root.iterdir()):
        name = entry.name
        if not _real_dir(entry):
            _tree_top_level_file(entry, tree)
        elif name == INTERNAL_DIR:
            tree["internal"].append(f"{INTERNAL_DIR}/ ({_count_files(entry)} files)")
        elif name == ARCHIVE_DIR:
            _tree_archive(root, tree)
        elif name == NESTED_DOT_MAIGO_DIR:
            tree["nested_dot_maigo"].append(f"{NESTED_DOT_MAIGO_DIR}/")
        elif name == BOARD_DETAIL_DIR:
            for detail in sorted(entry.iterdir()):
                tree["board"].append(f"{BOARD_DETAIL_DIR}/{detail.name}")
        elif name in _TREE_GROUP_NAMES:
            _tree_group_dir(root, name, tree)
        else:
            tree["unregistered"].append(f"{name}/")
    return tree


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dir", default=".maigo", help="要掃描的 .maigo/ 目錄（預設 .maigo）"
    )
    parser.add_argument(
        "--tree",
        action="store_true",
        help="全樹模式：連非 .md 檔、未知目錄、_archive/、topic/、舊機器 log 都列出",
    )
    args = parser.parse_args(argv)

    if args.tree:
        tree = scan_tree(args.dir)
        for category in TREE_CATEGORIES:
            print(f"{category}:")
            for entry in tree[category]:
                print(f"  {entry}")
        return 0

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
