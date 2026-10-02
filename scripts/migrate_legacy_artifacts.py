#!/usr/bin/env python3
"""
跨 repo 一次搬完 `.maigo/` 底下的舊產物：舊固定檔名（`plan.md`、
`review-rubric.md`……）與巢狀佈局採用前的分目錄前扁平檔
（`review-rubric-42.md`、`review-draft-airflow-73559.md`……）。

背景：13 個實際安裝 maigo 的 repo 一查，命名規範（`<kind>-<id>.md`）的採用率
是 0%——這支腳本原本只搬舊固定檔名；`scripts/artifact_path.py` 改成按
PR/issue 分資料夾後，同一批舊檔又多了一種要搬的形狀，這支腳本擴充成兩階段都
處理，並順手把 `.maigo/i/*.md` 的 `## 筆記` 段裡指到舊檔名的連結改成新相對
路徑。跟 `hooks/legacy_artifact_path_check.py`（擋新的寫入）是同一問題的兩端。

**只在 `tmp_path` 假 repo 上跑過 `--apply` 測試——不對任何真實 repo 執行
`--apply`**，那是跨出本 repo 範圍的不可逆操作，需要使用者逐一確認範圍與
執行者才動手。

唯讀輸入：接受一或多個 repo 根目錄（positional args），或 `--repo-list <file>`
讀一份純文字檔（每行一個絕對路徑，空行與 `#` 開頭的行忽略），預設
`--repo-list ~/.config/maigo/repos.txt`（與 `scripts/board_index.py` 共用
同一份清單）。

對每個 repo：`from maigo_dir_catalog import scan` 拿型錄（不重寫分類邏輯）。

**階段一（舊固定檔名，`catalog.legacy_fixed_name`）**：讀該檔 H1 →
`slugify(H1 文字)` 算新識別碼；H1 缺失或 slugify 回 `None` → 退回
`slugify(檔名去副檔名) or "unnamed"`。**去疊字**：這些舊檔的 H1 常常以 kind
名開頭（`# Plan: ...`、`# Review rubric — ...`），slugify 後再接上 `<kind>-`
前綴組檔名就會疊成 `plan-plan-...`；算出識別碼後若它等於該檔自己的 kind、或
以 `<kind>-` 開頭，去掉那段前綴，去掉後變空字串就退回下一級 fallback。只比對
「這份檔案自己的 kind」，不比對 `_KNOWN_KINDS` 全部種類——比對全部種類會把
恰好以另一個 kind 名開頭的不相干內容也錯誤地砍掉。**截斷邊界**：`slugify()`
的 40 字元硬截斷可能切在字中間；只有本模組（不動 `scripts/artifact_path.py`
共用的 `slugify()`——那邊的逐字截斷行為被
`test_artifact_path.py::TestSlugify::test_truncates_to_40_chars` 鎖定）在偵測
到識別碼命中 40 字元上限時，退到最後一個完整的 `-` 分段邊界。**刻意不用
branch 名**：遷移當下的 git branch 未必是當初寫檔時的 branch，
`resolve_identifier()` 的四級鏈第 2 級（當前 branch）在「事後遷移一份不知道
何時寫的舊檔」這個情境下不成立——這是刻意的取捨，不是漏做了。

**階段二（分目錄前扁平檔，`catalog.flat_identifier`）**：`split_flat_name()`
拆成 `(kind, raw_id)`。(a) id 正規化：`home_repo_name` 非空且 `raw_id` 形如
`<home_repo_name>-<數字>` → 收成 `<數字>`，記 `normalized_from`（例：airflow
的 `review-airflow-58543.md` 與 `review-rubric-58543.md` 收進同一個
`review/58543/`）。(b) conflict 後綴：正規化後的 id 形如 `<base>-<k>`
（k 為 2–99）**且**同 kind 的 `<kind>-<base>.md` 也在本批 → attempt=k、
id=base；否則整串當 id（例：孤立的 `review-rubric-99-2.md` 無 base 同伴 →
`review/99-2/rubric.md`，不誤拆）。`home_repo_name` 由 CLI 以
`git -C <repo> remote get-url origin` 的最後一段（去 `.git`）求得，失敗為空
字串；`--home-repo-name` 可覆寫。

兩階段共用同一份 reserved set：目標路徑已存在（撞到本次一起遷移的另一份舊
檔、還是撞到該 repo 已有的新命名檔案，都是同一種「目標路徑已存在」判斷，涵蓋
`.maigo/` 底下**所有既存檔案**，遞迴）→ 自動加 `-2`/`-3` attempt 尾碼直到不
衝突，在報告中標記這筆是自動消歧的，不靜默覆蓋任何既有檔案。

**連結改寫**：只看 `.maigo/i/*.md` 的 `## 筆記` 段（從該標題到下一個 `^## `
或 EOF）；`## 判斷` 與事實區一律不碰（事實區的 `- 下一步：` 這類欄位是
`/maigo:board` 刷新時重算的，不是這支腳本的責任）。token 以
`(?<![\\w./-])<舊檔名>(?![\\w./-])` 界定，帶目錄前綴的引用
（如 `airflow-registry-surface/.maigo/pr-comments-airflow-71477.md`）天然不
匹配（印成 `link-unchanged (path-qualified)` 供人看，不誤改）。對應表**只**
取自遷移紀錄（本次規劃的 old→new，或下述 manifest），不從磁碟反推：上一輪
若發生過自動消歧，「某個巢狀位置存在」分不出是這個舊檔名搬去的、還是撞名
對手搬去的。紀錄裡沒有、形狀又像待遷移舊檔名的 token 原封不動，印成
`link-unchanged (no migration record)`。

預設 dry-run：只印計畫與連結改寫預覽，不動任何檔案（也不寫 manifest）。
`--apply` 在第一個 rename 之前，先把完整的 old→new 對應表（含自動消歧結果）
原子寫入 `.maigo/migrate-legacy-artifacts.manifest.json`，接著搬檔
（`Path.rename()`，純檔案系統操作，`.maigo/` 不受版控，不用 `git mv`）、
改連結，全部完成才刪 manifest。目標路徑存在就拋 `FileExistsError`，不靜默
覆蓋，已搬的部分與 manifest 都保留。

**中斷後重跑**：manifest 存在就照它續跑、不重新規劃——已搬走的檔案不在
批次裡了，重新規劃會改變 sibling 與撞名判斷，把剩下的檔案搬到跟第一次不同
的位置。來源不在、目標已在的那筆視為上一輪已搬完，跳過（dry-run 標
`[already moved]`）；來源與目標都不在就報錯停下。連結改寫對已改過的 token
天然不再命中，重做是冪等的。manifest 讀不懂就報錯，不退回重新規劃。

Idempotent：對已無 `legacy_fixed_name`／`flat_identifier` 可搬、也沒有殘留
manifest 的 repo，印 `(nothing to migrate)`，重跑不出錯、不重複改名。

跑（CLI）：

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/migrate_legacy_artifacts.py" \
    [--repo-list ~/.config/maigo/repos.txt] [--home-repo-name NAME] [--apply] \
    [<repo>...]
```

核心邏輯 `plan_migration()` / `plan_link_rewrites()` / `read_manifest()` 皆為
唯讀 I/O（讀 H1、列既存檔名、讀 `i/*.md`，不寫任何檔案）；`write_manifest()` /
`apply_migration()` / `apply_link_rewrites()` 才是會寫入檔案系統的入口。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_path import (
    _FLAT_NAME_LOOKALIKES,
    _KNOWN_KINDS,
    _SLUG_MAX_LEN,
    artifact_path,
    read_topic,
    slugify,
)
from maigo_dir_catalog import Catalog, categorize, scan, split_flat_name

_DEFAULT_REPO_LIST = Path("~/.config/maigo/repos.txt").expanduser()

# `--apply` 在第一個 rename 之前寫下的完整 old→new 對應表，全部搬完、連結
# 改完才刪。`.json` 不進 `maigo_dir_catalog.scan()`（只收 `*.md`），也不命中
# `hooks/legacy_artifact_path_check.py`（regex 錨定 `\.md$`）。
_MANIFEST_NAME = "migrate-legacy-artifacts.manifest.json"
_MANIFEST_VERSION = 1

_KINDS_BY_LENGTH_DESC = sorted(_KNOWN_KINDS, key=len, reverse=True)

# 找 `.maigo/i/*.md` 的 `## 筆記` 段裡「看起來像舊產物名」的 token：
# 舊固定檔名（`review.md`）或分目錄前扁平檔（`review-rubric-42.md`）皆可，
# 兩側都要求非 word/路徑字元邊界，避免吃到帶目錄前綴的引用或半個檔名。
_OLD_ARTIFACT_TOKEN_RE = re.compile(
    r"(?<![\w./-])(?:"
    + "|".join(re.escape(k) for k in _KINDS_BY_LENGTH_DESC)
    + r")(?:-[A-Za-z0-9][\w.-]*)?\.md(?![\w./-])"
)
# 同一個 token 形狀，但前面緊接著路徑字元（`/`）——只用來印
# `link-unchanged (path-qualified)` 提示，不產生 rewrite。
_PATH_QUALIFIED_OLD_ARTIFACT_TOKEN_RE = re.compile(
    r"[\w./-][\w./-]*/(?:"
    + "|".join(re.escape(k) for k in _KINDS_BY_LENGTH_DESC)
    + r")(?:-[A-Za-z0-9][\w.-]*)?\.md"
)

_NOTES_HEADING_RE = re.compile(r"^## 筆記[ \t]*\n", re.MULTILINE)
_NEXT_HEADING_RE = re.compile(r"^##[ \t]+\S", re.MULTILINE)

# 正規化後的 id 若形如 `<base>-<k>`，只有 k 落在 2–99 才當 conflict 尾碼——
# 大於 99 幾乎必是 issue/PR 編號的一部分（如 `airflow-58543` 誤判過的形狀），
# 不是 attempt 計數。
_CONFLICT_SUFFIX_RE = re.compile(r"^(?P<base>.+)-(?P<k>\d{1,2})$")


@dataclass(frozen=True)
class MigrationAction:
    repo: str
    old_path: str  # repo-relative，例：".maigo/plan.md" 或 ".maigo/review-42.md"
    new_path: str  # repo-relative，例：".maigo/plan-fix-dag-run.md" 或 ".maigo/review/42/review.md"
    disambiguated: bool  # True＝目標撞名，自動加了 attempt 尾碼
    h1: str | None = None
    normalized_from: str | None = None  # 正規化前的 raw id（僅階段二、有正規化時填）


@dataclass(frozen=True)
class LinkRewrite:
    detail_path: str  # repo-relative，例：".maigo/i/58543.md"
    line_no: int
    old_token: str
    new_token: str  # 相對 .maigo/ 的新 relpath，例："review/58543/review.md"


def _existing_repo_relpaths(maigo_dir: Path) -> set[str]:
    """
    `.maigo/` 下所有既存檔案的 repo-relative 路徑集合（遞迴，唯讀），
    當 rename 目標的 reserved set——含巢狀路徑，不只頂層（`artifact_path()`
    一改成巢狀，只看頂層會漏掉既有的 `review/<id>/*.md` 目標）。
    """
    if not maigo_dir.is_dir():
        return set()
    return {
        f".maigo/{p.relative_to(maigo_dir).as_posix()}"
        for p in maigo_dir.rglob("*")
        if p.is_file()
    }


def _strip_kind_stutter(kind: str, identifier: str) -> str:
    """
    去掉識別碼開頭與 kind 重複的部分，避免組出 `<kind>-<kind>-...` 的疊字檔名。

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
    """
    `slugify()` 的 40 字元硬截斷可能切在字中間；退到最後一個完整的 `-`
    分段邊界，捨去被攔腰截斷的尾段。沒有 `-` 可退（單一長字）就原樣回傳。
    """
    if "-" not in text:
        return text
    trimmed, _, _tail = text.rpartition("-")
    return trimmed or text


def _infer_identifier(maigo_dir: Path, kind: str, legacy_name: str) -> str:
    """
    讀 legacy 檔的 H1 slugify 當識別碼；缺 H1 或 slugify 失敗則退回檔名本身。

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


def _plan_legacy_fixed_name_actions(
    repo_root: Path,
    catalog: Catalog,
    maigo_dir: Path,
    reserved: set[str],
) -> list[MigrationAction]:
    actions: list[MigrationAction] = []
    for legacy_name in catalog.legacy_fixed_name:
        kind = legacy_name[: -len(".md")]
        old_rel = f".maigo/{legacy_name}"

        base_identifier = _infer_identifier(maigo_dir, kind, legacy_name)
        attempt = 1
        candidate_path = artifact_path(kind, base_identifier, attempt)

        disambiguated = False
        while candidate_path in reserved:
            attempt += 1
            candidate_path = artifact_path(kind, base_identifier, attempt)
            disambiguated = True

        reserved.add(candidate_path)
        actions.append(
            MigrationAction(
                repo=str(repo_root),
                old_path=old_rel,
                new_path=candidate_path,
                disambiguated=disambiguated,
                h1=read_topic(maigo_dir / legacy_name),
            )
        )

    return actions


def _normalize_flat_identifier(
    raw_id: str, home_repo_name: str
) -> tuple[str, str | None]:
    """
    (a) id 正規化：`raw_id` 形如 `<home_repo_name>-<數字>` → 收成 `<數字>`，
    回傳 `(正規化後的 id, 正規化前的 raw_id 或 None)`。`home_repo_name` 空字串
    時一律不正規化（跨 repo 判斷退化，見 `github_ref()` 既有取捨）。
    """
    if home_repo_name:
        match = re.match(rf"^{re.escape(home_repo_name)}-(\d+)$", raw_id)
        if match:
            return match.group(1), raw_id
    return raw_id, None


def _split_conflict_suffix(identifier: str) -> tuple[str, int] | None:
    """(b) `<base>-<k>`（k 為 2–99）→ `(base, k)`；不是這個形狀回 `None`。"""
    match = _CONFLICT_SUFFIX_RE.match(identifier)
    if match is None:
        return None
    k = int(match.group("k"))
    if not (2 <= k <= 99):
        return None
    return match.group("base"), k


def _canonical_flat_targets(
    flat_set: set[str], home_repo_name: str
) -> set[tuple[str, str]]:
    """
    整批 `flat_identifier` 檔名的 `(kind, canonical_id)` 集合——每個檔名都用
    「自己的 bare 形」正規化（不管它結構上像不像 conflict 後綴），當 sibling
    判斷的唯一權威來源。

    **為什麼不能比對字面前綴形**：同一顆 PR 的兩份產物，一份可能是裸形寫下的
    （`review-rubric-58543.md`），另一份可能是前綴形（`review-rubric-airflow-
    58543-2.md`，因為漏傳 `--repo` 那次剛好是 re-review）——字面比對
    `f"{kind}-{candidate_base}.md" in flat_set` 只認其中一種形狀，另一種形狀
    的 sibling 存在也找不到（見 Soyo re-review must-fix #2）。用 canonical id
    當集合的 key，兩種形狀正規化後是同一個值，才能互認。
    """
    targets: set[tuple[str, str]] = set()
    for name in flat_set:
        split = split_flat_name(name)
        if split is None:  # pragma: no cover - catalog membership guarantees shape
            continue
        kind, raw_id = split
        canonical_id, _normalized_from = _normalize_flat_identifier(
            raw_id, home_repo_name
        )
        targets.add((kind, canonical_id))
    return targets


def _resolve_flat_identifier(
    kind: str,
    raw_id: str,
    home_repo_name: str,
    canonical_targets: set[tuple[str, str]],
) -> tuple[str, int, str | None]:
    """
    合併 (a) id 正規化與 (b) conflict 後綴解析，回傳 `(base_id, attempt,
    normalized_from)`。conflict 後綴候選的 canonical id 只要對得上批次裡
    **任一**檔案的 canonical id（不論那份 sibling 原本寫成裸形還是前綴形）
    就採用。

    **順序是關鍵**：先在**未正規化**的 `raw_id` 上找 conflict 後綴，
    sibling 判定通過才對拆出來的 `candidate_base`（不是整個 `raw_id`）
    正規化。反過來做（先對整串 `raw_id` 正規化）會在前綴與後綴同時出現時
    失效——`_normalize_flat_identifier()` 的 regex 要求整串到結尾都是數字，
    `"airflow-58543-2"` 因為多了 `-2` 尾巴匹配不到、直接跳過正規化，
    `_split_conflict_suffix()` 接著在未正規化的字串上拆出
    `base="airflow-58543"`（不是 `"58543"`），把同一顆 PR 的 rubric 與
    rubric-2 拆進兩個不同資料夾且沒有任何錯誤訊息（見 Soyo review 的
    must-fix，Batch 1–5 review）。
    """
    suffix = _split_conflict_suffix(raw_id)
    if suffix is not None:
        candidate_base_raw, k = suffix
        canonical_base, normalized_from = _normalize_flat_identifier(
            candidate_base_raw, home_repo_name
        )
        if (kind, canonical_base) in canonical_targets:
            return canonical_base, k, normalized_from

    base_id, normalized_from = _normalize_flat_identifier(raw_id, home_repo_name)
    return base_id, 1, normalized_from


def _plan_flat_identifier_actions(
    repo_root: Path,
    catalog: Catalog,
    maigo_dir: Path,
    reserved: set[str],
    home_repo_name: str,
) -> list[MigrationAction]:
    flat_set = set(catalog.flat_identifier)
    canonical_targets = _canonical_flat_targets(flat_set, home_repo_name)

    def _sort_key(name: str) -> tuple[int, str]:
        # (c) 先處理無後綴者：避免 attempt 消歧順序受掃描順序影響。
        split = split_flat_name(name)
        if split is None:  # pragma: no cover - catalog membership guarantees shape
            return (0, name)
        kind, raw_id = split
        _base_id, attempt, _normalized_from = _resolve_flat_identifier(
            kind, raw_id, home_repo_name, canonical_targets
        )
        return (1 if attempt > 1 else 0, name)

    actions: list[MigrationAction] = []
    for name in sorted(flat_set, key=_sort_key):
        split = split_flat_name(name)
        if split is None:  # pragma: no cover - catalog membership guarantees shape
            continue
        kind, raw_id = split
        base_id, attempt, normalized_from = _resolve_flat_identifier(
            kind, raw_id, home_repo_name, canonical_targets
        )

        candidate_path = artifact_path(kind, base_id, attempt)
        disambiguated = False
        while candidate_path in reserved:
            attempt += 1
            candidate_path = artifact_path(kind, base_id, attempt)
            disambiguated = True

        reserved.add(candidate_path)
        actions.append(
            MigrationAction(
                repo=str(repo_root),
                old_path=f".maigo/{name}",
                new_path=candidate_path,
                disambiguated=disambiguated,
                h1=read_topic(maigo_dir / name),
                normalized_from=normalized_from,
            )
        )

    return actions


def plan_migration(
    repo_root: str | Path, catalog: Catalog, *, home_repo_name: str = ""
) -> list[MigrationAction]:
    """
    算出這個 repo 該搬哪些檔、搬去哪——純函式，只做唯讀 I/O（讀 H1、列既存檔名）。

    `catalog` 由呼叫端先 `scan()` 好傳進來，這支函式不自己重掃。兩階段共用
    同一份 reserved set（見模組 docstring）：先搬舊固定檔名，再搬分目錄前
    扁平檔——順序本身不影響正確性，只是讓 CLI 輸出裡舊資料形狀靠前。
    """
    repo_root = Path(repo_root)
    maigo_dir = repo_root / ".maigo"
    reserved = _existing_repo_relpaths(maigo_dir)

    actions = _plan_legacy_fixed_name_actions(repo_root, catalog, maigo_dir, reserved)
    actions.extend(
        _plan_flat_identifier_actions(
            repo_root, catalog, maigo_dir, reserved, home_repo_name
        )
    )
    return actions


def apply_migration(repo_root: str | Path, actions: list[MigrationAction]) -> None:
    """
    唯一會真的動檔案的入口之一：`Path.rename()`（純檔案系統操作，
    `.maigo/` 不受版控，不用 `git mv`）。

    每筆先建父目錄（巢狀目標的 `review/<id>/` 可能還不存在），rename 前重查
    目標是否存在——POSIX `rename()` 會靜默覆蓋既有目標，規劃時的 reserved set
    只是「當時」的快照，兩次呼叫之間可能有新檔案出現，此處是最後一道防線。
    存在就拋 `FileExistsError`（訊息含兩個路徑），不動來源也不動目標；已搬
    的那些筆保留（重跑可接續）。

    從 manifest 續跑時，來源已不在、目標已在的那筆就是上一輪搬完的，跳過；
    來源與目標都不在代表有人在兩輪之間動過檔案，拋 `FileNotFoundError`，
    不猜它去了哪。
    """
    for action in actions:
        old = Path(repo_root) / action.old_path
        new = Path(repo_root) / action.new_path
        if not old.exists():
            if new.exists():
                continue
            raise FileNotFoundError(
                f"migration source and target are both missing: {old} -> {new}"
            )
        new.parent.mkdir(parents=True, exist_ok=True)
        if new.exists():
            raise FileExistsError(
                f"migration target already exists, refusing to overwrite: {old} -> {new}"
            )
        old.rename(new)


def manifest_path(repo_root: str | Path) -> Path:
    return Path(repo_root) / ".maigo" / _MANIFEST_NAME


def write_manifest(repo_root: str | Path, actions: list[MigrationAction]) -> None:
    """
    在任何 rename 之前把完整 old→new（含 disambiguation 結果）落地。先寫同
    目錄暫存檔再 `os.replace()`：中斷時 manifest 只會是「完整的一份」或
    「不存在」，不會是半份。
    """
    path = manifest_path(repo_root)
    payload = {
        "version": _MANIFEST_VERSION,
        "actions": [
            {key: value for key, value in asdict(action).items() if key != "repo"}
            for action in actions
        ],
    }
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(tmp, path)


def read_manifest(repo_root: str | Path) -> list[MigrationAction] | None:
    """
    上一輪 `--apply` 沒跑完留下的 manifest；不存在回 `None`。格式不對拋
    `ValueError`——壞掉的 manifest 不能退回重新規劃，那正是它要取代的猜測。
    """
    path = manifest_path(repo_root)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload["version"] != _MANIFEST_VERSION:
            raise ValueError(f"unsupported manifest version: {payload['version']!r}")
        return [
            MigrationAction(repo=str(repo_root), **entry)
            for entry in payload["actions"]
        ]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise ValueError(f"unreadable migration manifest {path}: {error}") from error


def _notes_section_span(text: str) -> tuple[int, int] | None:
    """
    `## 筆記` 段的 `(start, end)` 位元組區間（不含標題行本身）；沒有這個
    標題回 `None`。
    """
    heading = _NOTES_HEADING_RE.search(text)
    if heading is None:
        return None
    start = heading.end()
    next_heading = _NEXT_HEADING_RE.search(text, start)
    end = next_heading.start() if next_heading else len(text)
    return start, end


def _iter_notes_lines(repo_root: Path):
    """
    逐行產出 `.maigo/i/*.md` 的 `## 筆記` 段內容：`(detail_path, line_no, line)`，
    `detail_path` 為 repo-relative、`line_no` 從 1 起算。唯讀。
    """
    i_dir = repo_root / ".maigo" / "i"
    if not i_dir.is_dir():
        return
    for detail_file in sorted(i_dir.glob("*.md")):
        text = detail_file.read_text(encoding="utf-8")
        span = _notes_section_span(text)
        if span is None:
            continue
        section_start, section_end = span
        offset = 0
        for line_no, line in enumerate(text.splitlines(keepends=True), start=1):
            line_start = offset
            offset += len(line)
            if offset <= section_start or line_start >= section_end:
                continue
            yield f".maigo/i/{detail_file.name}", line_no, line


def _link_mapping(actions: list[MigrationAction]) -> dict[str, str]:
    """舊檔名 → 相對 `.maigo/` 的新 relpath，只取自遷移紀錄（本次規劃或 manifest）。"""
    return {
        Path(action.old_path).name: action.new_path.removeprefix(".maigo/")
        for action in actions
    }


def plan_link_rewrites(
    repo_root: str | Path, actions: list[MigrationAction]
) -> list[LinkRewrite]:
    """
    算出 `.maigo/i/*.md` 的 `## 筆記` 段裡該改的舊產物連結——純函式，只做
    唯讀 I/O。只看 `## 筆記`，`## 判斷` 與事實區一律不碰。

    對應表**只**取自 *actions*（本次規劃，或從 manifest 續跑時的完整對應表），
    不從磁碟反推：上一輪若發生過 disambiguation，「某個巢狀位置存在」分不出
    那是這個舊檔名搬去的、還是撞名對手搬去的（Soyo re-review 2 must-fix #3）。
    對應表裡沒有的舊檔名交給 `find_unmapped_mentions()` 回報，不改。
    """
    mapping = _link_mapping(actions)
    rewrites: list[LinkRewrite] = []
    for detail_path, line_no, line in _iter_notes_lines(Path(repo_root)):
        for match in _OLD_ARTIFACT_TOKEN_RE.finditer(line):
            name = match.group(0)
            new_token = mapping.get(name)
            if new_token is None or new_token == name:
                continue
            rewrites.append(
                LinkRewrite(
                    detail_path=detail_path,
                    line_no=line_no,
                    old_token=name,
                    new_token=new_token,
                )
            )
    return rewrites


def find_unmapped_mentions(
    repo_root: str | Path, actions: list[MigrationAction]
) -> list[tuple[str, int, str]]:
    """
    `## 筆記` 段裡形狀是待遷移舊檔名（`legacy_fixed_name` / `flat_identifier`，
    判準沿用 `maigo_dir_catalog.categorize()`）、但遷移紀錄裡沒有的 token——
    例如該舊檔早已不在、或上一輪的 manifest 被手動刪掉。只供 CLI 印
    `link-unchanged (no migration record)`，不產生 rewrite。回傳
    `(detail_path, line_no, token)`。
    """
    mapping = _link_mapping(actions)
    mentions: list[tuple[str, int, str]] = []
    for detail_path, line_no, line in _iter_notes_lines(Path(repo_root)):
        for match in _OLD_ARTIFACT_TOKEN_RE.finditer(line):
            name = match.group(0)
            if name in mapping:
                continue
            catalog = categorize([name])
            if catalog.legacy_fixed_name or catalog.flat_identifier:
                mentions.append((detail_path, line_no, name))
    return mentions


def find_path_qualified_mentions(repo_root: str | Path) -> list[tuple[str, int, str]]:
    """
    `## 筆記` 段裡帶目錄前綴、因此天然不被 `plan_link_rewrites()` 改寫的
    舊產物引用——只供 CLI 印 `link-unchanged (path-qualified)` 讓人看見，
    不產生任何 rewrite、不做任何寫入。回傳 `(detail_path, line_no, token)`。
    """
    return [
        (detail_path, line_no, match.group(0))
        for detail_path, line_no, line in _iter_notes_lines(Path(repo_root))
        for match in _PATH_QUALIFIED_OLD_ARTIFACT_TOKEN_RE.finditer(line)
    ]


def apply_link_rewrites(repo_root: str | Path, rewrites: list[LinkRewrite]) -> None:
    """
    唯一會真的動檔案的入口之一。只替換該 token，其餘位元組不動——按檔案
    分組，各檔只讀寫一次；替換範圍限定在該 rewrite 規劃時記錄的那一行
    （`line_no`），不是整份檔案 `sub()`——同一個 token 可能同時出現在
    `## 判斷` 與 `## 筆記`（只有後者該改），整份檔案替換會誤中前者的第一個
    命中；逐行替換才能精準命中規劃當時看到的那個位置。
    """
    repo_root = Path(repo_root)
    by_file: dict[str, list[LinkRewrite]] = {}
    for rewrite in rewrites:
        by_file.setdefault(rewrite.detail_path, []).append(rewrite)

    for detail_path, file_rewrites in by_file.items():
        path = repo_root / detail_path
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        for rewrite in file_rewrites:
            index = rewrite.line_no - 1
            pattern = re.compile(
                rf"(?<![\w./-]){re.escape(rewrite.old_token)}(?![\w./-])"
            )
            lines[index] = pattern.sub(rewrite.new_token, lines[index], count=1)
        path.write_text("".join(lines), encoding="utf-8")


def _infer_home_repo_name(repo_root: str | Path) -> str:
    """
    `git -C <repo> remote get-url origin` 的最後一段（去 `.git`）；抓不到
    （非 git repo、無 origin remote、逾時）一律回空字串——id 正規化退化成
    不正規化，不是報錯。
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    url = result.stdout.strip()
    if not url:
        return ""
    last_segment = url.rstrip("/").rsplit("/", 1)[-1]
    return last_segment.removesuffix(".git")


def _skip_reason(name: str, category: str) -> str:
    if category == "identifier_named":
        return "already using canonical naming"
    if category == "registered_non_artifact":
        return "registered non-artifact file, not migrated"
    if name in _FLAT_NAME_LOOKALIKES:
        return "flat-name lookalike, not a review kind artifact"
    if not name.endswith(".md"):
        return "not markdown"
    return "unregistered / unrecognized"


def _iter_skip_lines(repo: str, catalog: Catalog):
    for name in catalog.identifier_named:
        yield f"{repo} :: skipped {name} ({_skip_reason(name, 'identifier_named')})"
    for name in catalog.registered_non_artifact:
        yield (
            f"{repo} :: skipped {name} ({_skip_reason(name, 'registered_non_artifact')})"
        )
    for name in catalog.unregistered:
        yield f"{repo} :: skipped {name} ({_skip_reason(name, 'unregistered')})"


def _format_action_line(action: MigrationAction, *, already_moved: bool = False) -> str:
    markers = ""
    if already_moved:
        markers += " [already moved]"
    if action.disambiguated:
        markers += " [auto-disambiguated]"
    if action.normalized_from:
        markers += f" [normalized from {action.normalized_from}]"
    h1_display = action.h1 if action.h1 else "(none)"
    return f"{action.repo} :: {action.old_path} -> {action.new_path}{markers}  H1: {h1_display}"


def _format_link_line(repo: str, rewrite: LinkRewrite) -> str:
    return f"{repo} :: link {rewrite.detail_path}:{rewrite.line_no} {rewrite.old_token} -> {rewrite.new_token}"


def _format_path_qualified_line(
    repo: str, detail_path: str, line_no: int, token: str
) -> str:
    return f"{repo} :: link-unchanged (path-qualified) {detail_path}:{line_no} {token}"


def _format_unmapped_line(repo: str, detail_path: str, line_no: int, token: str) -> str:
    return f"{repo} :: link-unchanged (no migration record) {detail_path}:{line_no} {token}"


def _read_repo_list(path: Path) -> list[str] | None:
    """
    讀清單檔；檔案不存在或讀不到（權限拒絕等）一律回 `None` 讓呼叫端印
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
        "--home-repo-name",
        default=None,
        help=(
            "覆寫每個 repo 的 origin repo 名（id 正規化用）；省略則對每個 "
            "repo 各自跑 `git remote get-url origin` 推導，失敗為空字串"
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真的執行搬檔與連結改寫；預設只 dry-run 印清單",
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
                f"error: --repo-list file has no repo paths (all blank/comment lines?): {repo_list_path}",
                file=sys.stderr,
            )
            return 1

    for repo in repos:
        repo_path = Path(repo)
        if not repo_path.is_dir():
            print(f"{repo} :: skipped (repo path does not exist)")
            continue

        home_repo_name = (
            args.home_repo_name
            if args.home_repo_name is not None
            else _infer_home_repo_name(repo_path)
        )

        catalog = scan(repo_path / ".maigo")
        try:
            resumed_actions = read_manifest(repo_path)
        except ValueError as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        # 上一輪 `--apply` 沒跑完：照它當初寫下的對應表續跑，不重新規劃——
        # 已搬走的檔案不在批次裡了，重新規劃會改變 sibling／撞名判斷。
        resuming = resumed_actions is not None
        actions = (
            resumed_actions
            if resumed_actions is not None
            else plan_migration(repo, catalog, home_repo_name=home_repo_name)
        )
        link_rewrites = plan_link_rewrites(repo, actions)
        unmapped = find_unmapped_mentions(repo, actions)
        path_qualified = find_path_qualified_mentions(repo)
        skip_lines = list(_iter_skip_lines(repo, catalog))

        if resuming:
            print(
                f"{repo} :: resuming interrupted --apply from .maigo/{_MANIFEST_NAME}"
            )
        if not actions and not link_rewrites:
            print(f"{repo} :: (nothing to migrate)")
        else:
            for action in actions:
                already_moved = (
                    resuming
                    and not (repo_path / action.old_path).exists()
                    and (repo_path / action.new_path).exists()
                )
                print(_format_action_line(action, already_moved=already_moved))
            for rewrite in link_rewrites:
                print(_format_link_line(repo, rewrite))

        for detail_path, line_no, token in unmapped:
            print(_format_unmapped_line(repo, detail_path, line_no, token))
        for detail_path, line_no, token in path_qualified:
            print(_format_path_qualified_line(repo, detail_path, line_no, token))
        for line in skip_lines:
            print(line)

        if args.apply and (actions or resuming):
            if not resuming:
                write_manifest(repo_path, actions)
            try:
                apply_migration(repo, actions)
            except (FileExistsError, FileNotFoundError) as error:
                print(f"error: {error}", file=sys.stderr)
                return 2
            apply_link_rewrites(repo, link_rewrites)
            manifest_path(repo_path).unlink()

    return 0


if __name__ == "__main__":
    sys.exit(main())
