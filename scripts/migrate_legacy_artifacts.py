#!/usr/bin/env python3
"""跨 repo 一次搬完 `.maigo/` 底下的舊固定檔名（`plan.md`、`review-rubric.md`……）。

背景：13 個實際安裝 maigo 的 repo 一查，命名規範（`<kind>-<id>.md`）的採用率
是 0%——這支腳本是把散落各處的舊檔一次遷移到新命名的收尾動作，跟
`hooks/legacy_artifact_path_check.py`（擋新的寫入）是同一問題的兩端。

**只在 `tmp_path` 假 repo 上跑過 `--apply` 測試——不對任何真實 repo 執行
`--apply`**，那是跨出本 repo 範圍的不可逆操作，需要使用者逐一確認範圍與
執行者才動手（見 `.maigo/plan-main.md` 的 Open question 1）。

唯讀輸入：接受一或多個 repo 根目錄（positional args），或 `--repo-list <file>`
讀一份純文字檔（每行一個絕對路徑，空行與 `#` 開頭的行忽略），預設
`--repo-list ~/.config/maigo/repos.txt`（與 `scripts/board_index.py` 共用
同一份清單）。

對每個 repo：`from maigo_dir_catalog import scan` 拿 `legacy_fixed_name` 清單
（不重寫分類邏輯）。對每個命中檔案：讀該檔 H1 → `slugify(H1 文字)` 算新識別
碼；H1 缺失或 slugify 回 `None` → 退回 `slugify(檔名去副檔名) or "unnamed"`。

**去疊字**：這些舊檔的 H1 常常以 kind 名開頭（`# Plan: ...`、
`# Review rubric — ...`），slugify 後再接上 `<kind>-` 前綴組檔名就會疊成
`plan-plan-...`。算出識別碼後若它等於該檔自己的 kind、或以 `<kind>-`
開頭，去掉那段前綴；去掉後變空字串就退回下一級 fallback（H1 slug 去疊字
空了退到檔名 stem，stem 去疊字也空了退到 `"unnamed"`）。只比對「這份檔案
自己的 kind」，不比對 `_KNOWN_KINDS` 全部種類——比對全部種類會把恰好以
另一個 kind 名開頭的不相干內容也錯誤地砍掉。

**截斷邊界**：`slugify()` 的 40 字元硬截斷可能切在字中間；只有本模組（不
動 `scripts/artifact_path.py` 共用的 `slugify()`——那邊的逐字截斷行為被
`test_artifact_path.py::TestSlugify::test_truncates_to_40_chars` 鎖定，且被
branch 名等其他呼叫端共用）在偵測到識別碼命中 40 字元上限時，退到最後一個
完整的 `-` 分段邊界，避免產生像 `...review-c2` 這種攔腰截斷的尾巴。

**刻意不用 branch 名**：遷移當下的 git branch 未必是當初寫檔時的 branch，
`resolve_identifier()` 的四級鏈第 2 級（當前 branch）在「事後遷移一份不知道
何時寫的舊檔」這個情境下不成立——這是刻意的取捨，不是漏做了。

目標路徑已存在（不論是撞到本次一起遷移的另一份舊檔、還是撞到該 repo已有的
新命名檔案，都是同一種「目標路徑已存在」判斷，衝突偵測涵蓋 `.maigo/` 底下
**所有既存檔案**）→ 自動加 `-2`/`-3` 尾碼直到不衝突，在報告中標記這筆是自動
消歧的，不靜默覆蓋任何既有檔案。

預設 dry-run：只印 `<repo> :: <old> -> <new>` 表格，不動任何檔案。`--apply`
才真的 `Path.rename()`（純檔案系統操作，不是 `git mv`——`.maigo/` 不受版控）。

Idempotent：對已無 `legacy_fixed_name` 的 repo，印 `(nothing to migrate)`，
重跑不出錯、不重複改名。

跑（CLI）：

```
python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/migrate_legacy_artifacts.py" \
    [--repo-list ~/.config/maigo/repos.txt] [--apply] [<repo>...]
```

核心邏輯 `plan_migration()` 是純函式（讀 H1 屬唯讀 I/O，不寫任何檔案）；
`apply_migration()` 才是唯一會寫入檔案系統的入口。
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_path import _SLUG_MAX_LEN, artifact_path, read_topic, slugify
from maigo_dir_catalog import Catalog, scan

_DEFAULT_REPO_LIST = Path("~/.config/maigo/repos.txt").expanduser()


@dataclass(frozen=True)
class MigrationAction:
    repo: str
    old_path: str  # repo-relative，例：".maigo/plan.md"
    new_path: str  # repo-relative，例：".maigo/plan-fix-dag-run.md"
    disambiguated: bool  # True＝目標撞名，自動加了 -2/-3 尾碼


def _existing_top_level_names(maigo_dir: Path) -> set[str]:
    """`.maigo/` 頂層目前有的所有檔名（唯讀，不遞迴進 `i/`）。"""
    if not maigo_dir.is_dir():
        return set()
    return {p.name for p in maigo_dir.iterdir() if p.is_file()}


def _strip_kind_stutter(kind: str, identifier: str) -> str:
    """去掉識別碼開頭與 kind 重複的部分，避免組出 `<kind>-<kind>-...` 的疊字檔名。

    只比對這份檔案自己的 `kind`（呼叫端已知，不是搜尋 `_KNOWN_KINDS` 全部
    種類）——比對全部種類會有誤殺風險：若某份 `pr-comments.md` 的 H1 恰好
    誤用了別的模板、寫成「Plan: ...」開頭，比對全部種類會把這段不相干的
    「plan-」前綴也砍掉，那不是這支函式要修的疊字問題。
    """
    if identifier == kind:
        return ""
    prefix = f"{kind}-"
    if identifier.startswith(prefix):
        return identifier[len(prefix) :]
    return identifier


def _trim_to_word_boundary(text: str) -> str:
    """`slugify()` 的 40 字元硬截斷可能切在字中間；退到最後一個完整的 `-`
    分段邊界，捨去被攔腰截斷的尾段。沒有 `-` 可退（單一長字）就原樣回傳。
    """
    if "-" not in text:
        return text
    trimmed, _, _tail = text.rpartition("-")
    return trimmed or text


def _infer_identifier(maigo_dir: Path, kind: str, legacy_name: str) -> str:
    """讀 legacy 檔的 H1 slugify 當識別碼；缺 H1 或 slugify 失敗則退回檔名本身。

    去疊字與截斷邊界處理見模組 docstring；`kind` 由呼叫端算好傳入
    （`legacy_name` 去掉 `.md`），不在這裡重算。
    """
    h1 = read_topic(maigo_dir / legacy_name)
    if h1:
        slug = slugify(h1)
        if slug:
            if len(slug) >= _SLUG_MAX_LEN:
                slug = _trim_to_word_boundary(slug)
            deduped = _strip_kind_stutter(kind, slug)
            if deduped:
                return deduped
    stem = legacy_name[: -len(".md")] if legacy_name.endswith(".md") else legacy_name
    stem_slug = slugify(stem) or "unnamed"
    return _strip_kind_stutter(kind, stem_slug) or "unnamed"


def plan_migration(repo_root: str | Path, catalog: Catalog) -> list[MigrationAction]:
    """算出這個 repo 該搬哪些檔、搬去哪——純函式，只做唯讀 I/O（讀 H1、列既存檔名）。

    `catalog` 由呼叫端先 `scan()` 好傳進來，這支函式不自己重掃。
    """
    maigo_dir = Path(repo_root) / ".maigo"
    reserved = _existing_top_level_names(maigo_dir)
    actions: list[MigrationAction] = []

    for legacy_name in catalog.legacy_fixed_name:
        kind = legacy_name[: -len(".md")]
        old_rel = f".maigo/{legacy_name}"

        base_identifier = _infer_identifier(maigo_dir, kind, legacy_name)
        identifier = base_identifier
        candidate_name = Path(artifact_path(kind, identifier)).name

        disambiguated = False
        suffix = 2
        while candidate_name in reserved:
            identifier = f"{base_identifier}-{suffix}"
            candidate_name = Path(artifact_path(kind, identifier)).name
            disambiguated = True
            suffix += 1

        reserved.add(candidate_name)
        actions.append(
            MigrationAction(
                repo=str(repo_root),
                old_path=old_rel,
                new_path=f".maigo/{candidate_name}",
                disambiguated=disambiguated,
            )
        )

    return actions


def apply_migration(repo_root: str | Path, actions: list[MigrationAction]) -> None:
    """唯一會真的動檔案的入口：`Path.rename()`（純檔案系統操作，`.maigo/` 不受版控，
    不用 `git mv`）。"""
    for action in actions:
        old = Path(repo_root) / action.old_path
        new = Path(repo_root) / action.new_path
        old.rename(new)


def _read_repo_list(path: Path) -> list[str] | None:
    """讀清單檔；檔案不存在或讀不到（權限拒絕等）一律回 `None` 讓呼叫端印
    明確錯誤並回非 0 exit code——不能讓「路徑打錯」跟「清單裡真的沒東西」
    看起來一樣（都是印 `(nothing to migrate)`）。
    """
    try:
        if not path.is_file():
            return None
        raw_text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    repos = []
    for raw in raw_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        repos.append(line)
    return repos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "repos", nargs="*", help="repo 根目錄（未給時改讀 --repo-list）"
    )
    parser.add_argument(
        "--repo-list",
        default=str(_DEFAULT_REPO_LIST),
        help="一行一個絕對路徑的純文字檔，預設 ~/.config/maigo/repos.txt",
    )
    parser.add_argument(
        "--apply", action="store_true", help="真的執行 rename；預設只 dry-run 印清單"
    )
    args = parser.parse_args(argv)

    if args.repos:
        repos = args.repos
    else:
        repo_list_path = Path(args.repo_list).expanduser()
        repos = _read_repo_list(repo_list_path)
        if repos is None:
            print(
                f"error: --repo-list file not found or unreadable: {repo_list_path}",
                file=sys.stderr,
            )
            return 1
        if not repos:
            print(
                "error: --repo-list file has no repo paths "
                f"(all blank/comment lines?): {repo_list_path}",
                file=sys.stderr,
            )
            return 1

    for repo in repos:
        repo_path = Path(repo)
        if not repo_path.is_dir():
            print(f"{repo} :: skipped (repo path does not exist)")
            continue

        catalog = scan(repo_path / ".maigo")
        actions = plan_migration(repo, catalog)

        if not actions:
            print(f"{repo} :: (nothing to migrate)")
            continue

        for action in actions:
            marker = " [auto-disambiguated]" if action.disambiguated else ""
            print(f"{repo} :: {action.old_path} -> {action.new_path}{marker}")

        if args.apply:
            apply_migration(repo, actions)

    return 0


if __name__ == "__main__":
    sys.exit(main())
