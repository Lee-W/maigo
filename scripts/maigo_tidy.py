#!/usr/bin/env python3
"""
`/maigo:tidy` 的後端：把 `.maigo/` 收斂到目標佈局的唯一清理入口。

預設 dry-run：只印「逐項 ＋ 判定依據 ＋ 預定動作」清單，不動任何檔案。
`--apply` 只執行**規則型動作**（`needs_confirm=False`）：

- 舊扁平檔遷移成巢狀佈局（委派給 `migrate_legacy_artifacts.plan_migration`）；
- 頂層機器日誌（`session-head.json` 與三個 jsonl）搬進 `.maigo/_internal/log/`；
- 已結案（merged／closed）的 `pr/`、`review/`、`issue/` 目錄與 `i/<id>.md` 鏡射
  封存到 `.maigo/_archive/<原相對路徑>`（重用 `board_sync.archive_relpaths`）；
- `_internal/log/*.jsonl` 超過 `LOG_ROTATE_MAX_LINES` 行就輪替成 `<name>.1.jsonl`，
  只留一代。

下列項目一律 `needs_confirm=True`，只有 `--apply --confirm <path>` 點名的那一筆才動
（沒有「全部同意」的開關）：`topic/<slug>/` 封存（沒有外部訊號可判結案）、`_archive/`
中封存（mtime，tidy 封存時會重設成封存當下）超過 `ARCHIVE_RETENTION` 的項目（delete-candidate）、`scan_tree` 判為
unregistered 的項目（`--confirm`＝備份後刪除，`--confirm-archive`＝備份後封存）、`.maigo/.maigo/`（同左）、
以及 GitHub 狀態查不到的 `pr/`／`review/`／`issue/` 項目（確認＝封存）。

結案判定要打 gh（`item_state(group, id)` 注入，回 `"open"`／`"merged"`／`"closed"`／
`None`）；`--no-gh` 整段跳過，只列本地可判的動作。狀態查不到（`None`）的項目不動。

動手前把每個要動的路徑先備份到 `.maigo/_internal/tidy/backup/<UTC ts>/<相對 .maigo/ 的原路徑>`，
改寫類的寫入用 tmp ＋ rename；備份完成之前不搬任何東西。還原：把備份裡的路徑複製回 `.maigo/`。

`build_actions()`／`apply()` 沒有 import 副作用，`maigo_dir` 與 gh 查詢都可注入。
`maigo_dir` 的目錄名必須是 `.maigo`（遷移與封存的 helper 以 `maigo_dir.parent/.maigo` 為準；不是就拒絕）。

跑（CLI）：

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/maigo_tidy.py" [--dir .maigo] [--no-gh] \\
    [--apply [--confirm .maigo/<path> ...] [--confirm-archive .maigo/<path> ...]]
```
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parent))
import board_sync  # noqa: E402
import maigo_dir_catalog  # noqa: E402
import migrate_legacy_artifacts as migrate  # noqa: E402

Kind = Literal[
    "migrate",
    "move-internal-log",
    "archive",
    "rotate-log",
    "delete-candidate",
    "unregistered",
    "remove-nested-dot-maigo",
]
KINDS: tuple[str, ...] = (
    "migrate",
    "move-internal-log",
    "archive",
    "rotate-log",
    "delete-candidate",
    "unregistered",
    "remove-nested-dot-maigo",
)

# 門檻：兩個數字都可以調，docs/reference/artifacts.md 有標明。
LOG_ROTATE_MAX_LINES = 2000
ARCHIVE_RETENTION = timedelta(days=90)

STATE_GROUPS = ("pr", "review", "issue")
SETTLED_STATES = frozenset({"merged", "closed"})
MAIGO_PREFIX = ".maigo/"
INTERNAL_LOG_REL = "_internal/log"
BACKUP_REL = "_internal/tidy/backup"
GH_TIMEOUT_SEC = 20
_ARCHIVE_ENTRY_RE = re.compile(r"^(?P<path>.+?) \(mtime (?P<mtime>[^)]+)\)$")

CONFIRM_HOW = (
    "；確認方式：--confirm PATH＝備份後刪除，"
    "--confirm-archive PATH＝備份後封存到 _archive/，不點名就保留"
)
ARCHIVE_CONFIRM_KINDS = frozenset({"unregistered", "remove-nested-dot-maigo"})

ItemState = Callable[[str, str], "str | None"]


@dataclass(frozen=True)
class TidyAction:
    kind: Kind
    path: str  # repo-root 相對，`.maigo/...`
    target: str | None  # repo-root 相對，`.maigo/...`；刪除類為 None
    reason: str
    needs_confirm: bool


def _display(rel: str) -> str:
    return MAIGO_PREFIX + rel.strip("/")


def _rel(display: str) -> str:
    """`.maigo/pr/12` → `pr/12`。"""
    return _norm(display).removeprefix(MAIGO_PREFIX)


def _norm(path: str) -> str:
    return path.strip().removeprefix("./").rstrip("/")


def _is_real_dir(path: Path) -> bool:
    return path.is_dir() and not path.is_symlink()


# --------------------------------------------------------------------------- 規劃


def _migration_actions(
    maigo_dir: Path, home_repo_name: str | None
) -> list[migrate.MigrationAction]:
    """殘留 manifest 優先（照上一輪的對應表續跑），否則重新規劃。"""
    repo_root = maigo_dir.parent
    resumed = migrate.read_manifest(repo_root)
    if resumed is not None:
        return resumed
    if home_repo_name is None:
        home_repo_name = migrate.infer_home_repo_name(repo_root)
    return migrate.plan_migration(
        repo_root,
        maigo_dir_catalog.scan(maigo_dir),
        home_repo_name=home_repo_name,
    )


def _plan_migrate(maigo_dir: Path, home_repo_name: str | None) -> list[TidyAction]:
    actions = []
    for item in _migration_actions(maigo_dir, home_repo_name):
        reason = "舊佈局檔，遷移成巢狀佈局"
        if item.disambiguated:
            reason += "（目標撞名，自動加 attempt 尾碼）"
        actions.append(
            TidyAction("migrate", item.old_path, item.new_path, reason, False)
        )
    return actions


def _plan_internal_logs(
    maigo_dir: Path, tree: dict[str, list[str]]
) -> list[TidyAction]:
    actions = []
    for name in tree["legacy_internal_log"]:
        target_rel = f"{INTERNAL_LOG_REL}/{name}"
        reason = "頂層機器日誌，新位置是 _internal/log/"
        if (maigo_dir / target_rel).exists():
            reason += (
                "；目標已存在，舊檔內容接在新檔前面（舊在前、新在後）再刪舊檔"
                if name.endswith(".jsonl")
                else "；目標已存在，以新檔為準、刪舊檔"
            )
        actions.append(
            TidyAction(
                "move-internal-log", _display(name), _display(target_rel), reason, False
            )
        )
    return actions


def _line_count(path: Path) -> int:
    with path.open("rb") as handle:
        return sum(1 for _ in handle)


def _plan_rotations(maigo_dir: Path) -> list[TidyAction]:
    log_dir = maigo_dir / INTERNAL_LOG_REL
    if not _is_real_dir(log_dir):
        return []
    actions = []
    for entry in sorted(log_dir.glob("*.jsonl")):
        stem = entry.name.removesuffix(".jsonl")
        if stem.endswith(".1") or not entry.is_file():
            continue
        lines = _line_count(entry)
        if lines > LOG_ROTATE_MAX_LINES:
            actions.append(
                TidyAction(
                    "rotate-log",
                    _display(f"{INTERNAL_LOG_REL}/{entry.name}"),
                    _display(f"{INTERNAL_LOG_REL}/{stem}.1.jsonl"),
                    f"{lines} 行，超過 {LOG_ROTATE_MAX_LINES} 行門檻；只留一代",
                    False,
                )
            )
    return actions


def _settled_action(
    maigo_dir: Path, group: str, ident: str, rel: str, item_state: ItemState
) -> TidyAction | None:
    state = item_state(group, ident)
    target_rel = f"{board_sync.ARCHIVE_DIR}/{rel}"
    exists_note = (
        "；目的地已存在，apply 不會覆蓋" if (maigo_dir / target_rel).exists() else ""
    )
    if state is None:
        return TidyAction(
            "archive",
            _display(rel),
            _display(target_rel),
            "狀態查不到（gh 失敗、離線或 id 無法對應 GitHub），不自動封存",
            True,
        )
    if state in SETTLED_STATES:
        return TidyAction(
            "archive",
            _display(rel),
            _display(target_rel),
            f"GitHub 狀態 {state}{exists_note}",
            False,
        )
    return None


def _plan_settled(
    maigo_dir: Path, item_state: ItemState, notes: list[str]
) -> list[TidyAction]:
    """只替 id 是純數字的項目查狀態；其餘（跨 repo 的 `<repo>-<n>`、slug）彙總成一行備註。"""
    actions = []
    unresolvable_groups = 0
    for group in STATE_GROUPS:
        group_dir = maigo_dir / group
        if not _is_real_dir(group_dir):
            continue
        for entry in sorted(group_dir.iterdir()):
            if not _is_real_dir(entry):
                continue
            if not entry.name.isdigit():
                unresolvable_groups += 1
                continue
            actions.append(
                _settled_action(
                    maigo_dir, group, entry.name, f"{group}/{entry.name}", item_state
                )
            )
    unresolvable_details = 0
    detail_dir = maigo_dir / maigo_dir_catalog.BOARD_DETAIL_DIR
    if _is_real_dir(detail_dir):
        for entry in sorted(detail_dir.glob("*.md")):
            if not entry.is_file() or entry.is_symlink():
                continue
            if not entry.stem.isdigit():
                unresolvable_details += 1
                continue
            actions.append(
                _settled_action(
                    maigo_dir, "i", entry.stem, f"i/{entry.name}", item_state
                )
            )
    if unresolvable_groups:
        notes.append(
            f"pr/、review/、issue/ 有 {unresolvable_groups} 筆 id 不是純數字，"
            "狀態查不到，沒有列動作"
        )
    if unresolvable_details:
        notes.append(
            f"i/ 有 {unresolvable_details} 筆狀態查不到（id 不是純數字），由 /maigo:board 處理"
        )
    return [action for action in actions if action is not None]


def _plan_topics(maigo_dir: Path) -> list[TidyAction]:
    topic_dir = maigo_dir / "topic"
    if not _is_real_dir(topic_dir):
        return []
    return [
        TidyAction(
            "archive",
            _display(f"topic/{entry.name}"),
            _display(f"{board_sync.ARCHIVE_DIR}/topic/{entry.name}"),
            "topic 沒有外部結案訊號可查，是否已結案由你決定",
            True,
        )
        for entry in sorted(topic_dir.iterdir())
        if _is_real_dir(entry)
    ]


def _plan_expired_archive(
    tree: dict[str, list[str]], now: datetime
) -> list[TidyAction]:
    actions = []
    for entry in tree["archive"]:
        match = _ARCHIVE_ENTRY_RE.match(entry)
        if match is None:
            continue
        try:
            mtime = datetime.strptime(match["mtime"], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue
        age = now - mtime
        if age > ARCHIVE_RETENTION:
            actions.append(
                TidyAction(
                    "delete-candidate",
                    _display(match["path"]),
                    None,
                    f"封存時間 {match['mtime']}，已 {age.days} 天，超過保留期 "
                    f"{ARCHIVE_RETENTION.days} 天；確認＝備份後刪除",
                    True,
                )
            )
    return actions


def _describe_dir(path: Path) -> str:
    files = [p for p in path.rglob("*") if p.is_file()]
    total = sum(p.stat().st_size for p in files if not p.is_symlink())
    return f"{len(files)} 個檔、{total} bytes"


def _plan_nested_dot_maigo(
    maigo_dir: Path, tree: dict[str, list[str]]
) -> list[TidyAction]:
    if not tree["nested_dot_maigo"]:
        return []
    nested = maigo_dir / maigo_dir_catalog.NESTED_DOT_MAIGO_DIR
    names = sorted(str(p.relative_to(nested)) for p in nested.rglob("*") if p.is_file())
    shown = ", ".join(names[:5]) + (" …" if len(names) > 5 else "")
    return [
        TidyAction(
            "remove-nested-dot-maigo",
            _display(maigo_dir_catalog.NESTED_DOT_MAIGO_DIR),
            None,
            f"hook 在子目錄 cwd 下長出的殘留，{len(names)} 個檔（{shown or '空'}）；"
            "要合併回上層請手動處理" + CONFIRM_HOW,
            True,
        )
    ]


def _plan_unregistered(maigo_dir: Path, tree: dict[str, list[str]]) -> list[TidyAction]:
    actions: list[TidyAction] = []
    seen: set[str] = set()
    for entry in tree["unregistered"]:
        path = _display(entry)
        if path in seen:
            continue
        seen.add(path)
        reason = "catalog 判為 unregistered，不屬於任何已登記的產物種類"
        full = maigo_dir / _rel(path)
        if _is_real_dir(full):
            reason += f"；目錄，{_describe_dir(full)}"
        reason += CONFIRM_HOW
        actions.append(TidyAction("unregistered", path, None, reason, True))
    return actions


def build_actions(
    maigo_dir: str | Path,
    *,
    now: datetime,
    item_state: ItemState | None,
    home_repo_name: str | None = None,
) -> list[TidyAction]:
    """
    唯讀：算出整份清單。`item_state(group, id)` 回 `"open"`／`"merged"`／`"closed"`／
    `None`（查不到）；整個傳 `None` 代表不做結案判定（`--no-gh`），連「查不到」的項目
    也不列。`now` 要帶時區。
    """
    return build_plan(
        maigo_dir, now=now, item_state=item_state, home_repo_name=home_repo_name
    )[0]


def _check_dir_name(maigo_dir: Path) -> None:
    if maigo_dir.resolve().name != ".maigo":
        raise ValueError(
            f"{maigo_dir} 的目錄名不是 .maigo（遷移與封存以 <root>/.maigo 為準，"
            "列的和動的會不是同一個目錄）"
        )


def build_plan(
    maigo_dir: str | Path,
    *,
    now: datetime,
    item_state: ItemState | None,
    home_repo_name: str | None = None,
) -> tuple[list[TidyAction], list[str]]:
    """`build_actions` 加上統計段要印的備註（例如「i/ 有 N 筆狀態查不到」）。"""
    maigo_dir = Path(maigo_dir)
    _check_dir_name(maigo_dir)
    notes: list[str] = []
    if not maigo_dir.is_dir():
        return [], notes
    tree = maigo_dir_catalog.scan_tree(maigo_dir)
    actions = _plan_migrate(maigo_dir, home_repo_name)
    actions += _plan_internal_logs(maigo_dir, tree)
    actions += _plan_rotations(maigo_dir)
    if item_state is not None:
        actions += _plan_settled(maigo_dir, item_state, notes)
    actions += _plan_topics(maigo_dir)
    actions += _plan_expired_archive(tree, now)
    actions += _plan_nested_dot_maigo(maigo_dir, tree)
    actions += _plan_unregistered(maigo_dir, tree)
    return actions, notes


# --------------------------------------------------------------------------- 套用


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _move(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, destination)


def _backup(maigo_dir: Path, backup_root: Path, rel: str) -> bool:
    source = maigo_dir / rel
    destination = backup_root / rel
    if not (source.exists() or source.is_symlink()):
        return False
    if destination.exists():
        raise FileExistsError(
            f"backup target already exists, refusing to reuse: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    if _is_real_dir(source):
        shutil.copytree(source, destination, symlinks=True)
    else:
        shutil.copy2(source, destination, follow_symlinks=False)
    return True


def _remove(path: Path) -> None:
    if _is_real_dir(path):
        shutil.rmtree(path)
    else:
        path.unlink()


def _migration_items(
    todo: list[TidyAction], repo_root: Path
) -> list[migrate.MigrationAction]:
    return [
        migrate.MigrationAction(
            repo=str(repo_root),
            old_path=action.path,
            new_path=action.target or "",
            disambiguated=False,
        )
        for action in todo
        if action.kind == "migrate"
    ]


def _backup_rels(
    todo: list[TidyAction], maigo_dir: Path, link_rewrites: list[migrate.LinkRewrite]
) -> list[str]:
    rels: list[str] = []
    for action in todo:
        rels.append(_rel(action.path))
        if action.kind in ("move-internal-log", "rotate-log") and action.target:
            rels.append(_rel(action.target))
    rels.extend(_rel(rewrite.detail_path) for rewrite in link_rewrites)
    return list(dict.fromkeys(rels))


def _apply_migrate(
    migrations: list[migrate.MigrationAction],
    link_rewrites: list[migrate.LinkRewrite],
    repo_root: Path,
) -> list[str]:
    if migrate.read_manifest(repo_root) is None:
        migrate.write_manifest(repo_root, migrations)
    try:
        migrate.apply_migration(repo_root, migrations)
    except (FileExistsError, FileNotFoundError) as error:
        return [f"migrate 失敗，manifest 保留、重跑可續：{error}"]
    migrate.apply_link_rewrites(repo_root, link_rewrites)
    migrate.remove_manifest(repo_root)
    return [f"migrate：{m.old_path} → {m.new_path}" for m in migrations]


def _apply_move_internal_log(action: TidyAction, maigo_dir: Path) -> str:
    source = maigo_dir / _rel(action.path)
    destination = maigo_dir / _rel(action.target or "")
    if not destination.exists():
        _move(source, destination)
        return f"move-internal-log：{action.path} → {action.target}"
    if source.name.endswith(".jsonl"):
        # 舊的在前、新的在後：讀取端用 entries[-3:] 當「最近」。
        older = source.read_bytes()
        if older and not older.endswith(b"\n"):
            older += b"\n"
        _atomic_write(destination, older + destination.read_bytes())
        source.unlink()
        return f"move-internal-log：{action.path} 接在 {action.target} 前面（舊在前、新在後）"
    source.unlink()
    return f"move-internal-log：{action.target} 已存在，以新檔為準，刪 {action.path}"


def _stamp_warnings(skipped: list[dict], moved: list[str]) -> str:
    """archive_relpaths 搬完但無法重設封存時間的警告，附在成功訊息後。"""
    notes = [
        f"（{entry['reason']}：{entry['path']}）"
        for entry in skipped
        if entry["path"] in moved
    ]
    return "".join(notes)


def _apply_archive(action: TidyAction, maigo_dir: Path) -> str:
    moved, skipped, missing = board_sync.archive_relpaths(
        maigo_dir.parent, [_rel(action.path)]
    )
    if moved:
        return (
            f"archive：{action.path} → {action.target}{_stamp_warnings(skipped, moved)}"
        )
    if skipped:
        return f"archive 略過：{action.path}（目的地已存在，不覆蓋）"
    return f"archive 略過：{action.path}（來源已不存在）"


def _apply_archive_confirmed(action: TidyAction, maigo_dir: Path) -> str:
    moved, skipped, _missing = board_sync.archive_relpaths(
        maigo_dir.parent, [_rel(action.path)]
    )
    target = _display(f"{board_sync.ARCHIVE_DIR}/{_rel(action.path)}")
    if moved:
        return (
            f"{action.kind}：已封存 {action.path} → {target}"
            f"{_stamp_warnings(skipped, moved)}"
        )
    if skipped:
        return f"{action.kind} 略過：{action.path}（{target} 已存在，不覆蓋）"
    return f"{action.kind} 略過：{action.path}（來源已不存在）"


def apply(
    actions: Iterable[TidyAction],
    *,
    maigo_dir: str | Path,
    backup_root: str | Path,
    confirmed: set[str] | frozenset[str] = frozenset(),
    archive_confirmed: set[str] | frozenset[str] = frozenset(),
) -> list[str]:
    """
    只執行 `needs_confirm=False` 的動作，加上 `path` 被 `confirmed` 點名的動作。
    `archive_confirmed` 只對 unregistered 與 `.maigo/.maigo/` 有效：備份後鏡射封存到
    `_archive/`（不覆蓋），而不是刪除。
    全部要動的路徑先備份到 `backup_root/<相對 .maigo/ 的原路徑>`，備份完才開始搬
    （備份目的地已存在就拋 `FileExistsError`，不沿用上一輪的備份）。
    回傳每個動作一行的結果訊息；中途例外時先印已完成的結果行再 re-raise。
    """
    maigo_dir = Path(maigo_dir)
    backup_root = Path(backup_root)
    repo_root = maigo_dir.parent
    archive_approved = {_norm(path) for path in archive_confirmed}
    approved = {_norm(path) for path in confirmed} | archive_approved
    todo = [
        action
        for action in actions
        if not action.needs_confirm or _norm(action.path) in approved
    ]
    if not todo:
        return []

    migrations = _migration_items(todo, repo_root)
    link_rewrites = (
        migrate.plan_link_rewrites(repo_root, migrations) if migrations else []
    )
    for rel in _backup_rels(todo, maigo_dir, link_rewrites):
        _backup(maigo_dir, backup_root, rel)

    results: list[str] = []
    try:
        if migrations:
            results.extend(_apply_migrate(migrations, link_rewrites, repo_root))
        for action in todo:
            if action.kind == "migrate":
                continue
            if action.kind == "move-internal-log":
                results.append(_apply_move_internal_log(action, maigo_dir))
            elif action.kind == "rotate-log":
                _move(
                    maigo_dir / _rel(action.path), maigo_dir / _rel(action.target or "")
                )
                results.append(f"rotate-log：{action.path} → {action.target}")
            elif action.kind == "archive":
                results.append(_apply_archive(action, maigo_dir))
            elif (
                action.kind in ARCHIVE_CONFIRM_KINDS
                and _norm(action.path) in archive_approved
            ):
                results.append(_apply_archive_confirmed(action, maigo_dir))
            else:  # delete-candidate / unregistered / remove-nested-dot-maigo
                _remove(maigo_dir / _rel(action.path))
                results.append(
                    f"{action.kind}：已刪除 {action.path}（備份在 {backup_root.name}/）"
                )
    except BaseException:
        print("## 執行結果（中途中斷，以下是已完成的動作）")
        print("\n".join(f"- {line}" for line in results) if results else "- （無）")
        raise
    return results


# --------------------------------------------------------------------------- 輸出


def _line(action: TidyAction, *, checkbox: bool) -> str:
    head = "- [ ] " if checkbox else "- "
    arrow = f" → {action.target}" if action.target else ""
    return f"{head}{action.kind}：{action.path}{arrow} ｜ 依據：{action.reason}"


def render(
    actions: list[TidyAction],
    *,
    state_checked: bool = True,
    notes: Iterable[str] = (),
) -> str:
    """
    dry-run 輸出：一段一行、不用表格、路徑 `.maigo/` 開頭（skills/vim-friendly-artifacts）。
    每一行不是 `## ` 標題就是 `- ` 開頭。
    """
    rules = [a for a in actions if not a.needs_confirm]
    confirm = [a for a in actions if a.needs_confirm and a.kind != "unregistered"]
    unregistered = [a for a in actions if a.kind == "unregistered"]
    lines = ["## 規則型動作（--apply 會執行）"]
    lines += [_line(a, checkbox=False) for a in rules] or ["- （無）"]
    lines.append("## 需要你逐項勾選")
    lines += [_line(a, checkbox=True) for a in confirm] or ["- （無）"]
    lines.append("## 未登記（不隨 --apply 動，點名才處理）")
    lines += [_line(a, checkbox=False) for a in unregistered] or ["- （無）"]
    lines.append("## 統計")
    counts = [(kind, sum(1 for a in actions if a.kind == kind)) for kind in KINDS]
    lines += [f"- {kind}：{count}" for kind, count in counts if count] or ["- （無）"]
    lines += [f"- {note}" for note in notes]
    lines.append(
        "- 結案判定：已查 GitHub 狀態"
        if state_checked
        else "- 結案判定：略過（--no-gh），pr/、review/、issue/、i/ 的封存沒有列出"
    )
    return "\n".join(lines)


# --------------------------------------------------------------------------- gh


def _gh_state(args: list[str], cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            ["gh", *args, "--json", "state", "-q", ".state"],
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT_SEC,
            cwd=cwd,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return {"OPEN": "open", "MERGED": "merged", "CLOSED": "closed"}.get(
        result.stdout.strip().upper()
    )


def make_gh_item_state(repo_root: Path) -> ItemState:
    """`gh pr/issue view <n>` 查狀態；只認純數字 id（跨 repo 的 `<repo>-<n>` 查不到）。"""
    cache: dict[tuple[str, str], str | None] = {}

    def item_state(group: str, ident: str) -> str | None:
        key = (group, ident)
        if key not in cache:
            state = None
            if ident.isdigit():
                kinds = {"issue": ["issue"], "i": ["pr", "issue"]}.get(group, ["pr"])
                for kind in kinds:
                    state = _gh_state([kind, "view", ident], repo_root)
                    if state is not None:
                        break
            cache[key] = state
        return cache[key]

    return item_state


# --------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dir", default=".maigo", help="要整理的 .maigo/ 目錄（預設 .maigo）"
    )
    parser.add_argument(
        "--apply", action="store_true", help="執行規則型動作；預設只 dry-run"
    )
    parser.add_argument(
        "--confirm",
        action="append",
        default=[],
        metavar="PATH",
        help="搭配 --apply，執行這一筆需要勾選的動作（可重複；路徑照 dry-run 印出的 .maigo/… 寫）",
    )
    parser.add_argument(
        "--confirm-archive",
        action="append",
        default=[],
        metavar="PATH",
        help="搭配 --apply，把這一筆 unregistered／.maigo/.maigo 備份後封存到 _archive/（可重複）",
    )
    parser.add_argument("--no-gh", action="store_true", help="跳過結案判定，不打 gh")
    args = parser.parse_args(argv)

    maigo_dir = Path(args.dir)
    if not maigo_dir.is_dir():
        print(f"error: {maigo_dir} 不存在", file=sys.stderr)
        return 1
    try:
        _check_dir_name(maigo_dir)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    now = datetime.now(timezone.utc)
    item_state = None if args.no_gh else make_gh_item_state(maigo_dir.resolve().parent)
    try:
        actions, notes = build_plan(maigo_dir, now=now, item_state=item_state)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if not args.apply:
        if args.confirm or args.confirm_archive:
            print("error: --confirm／--confirm-archive 要搭配 --apply", file=sys.stderr)
            return 1
        print(render(actions, state_checked=not args.no_gh, notes=notes))
        return 0

    known = {_norm(a.path) for a in actions if a.needs_confirm}
    unknown = [path for path in args.confirm if _norm(path) not in known]
    if unknown:
        for path in unknown:
            print(f"error: --confirm {path} 不在需要勾選的清單裡", file=sys.stderr)
        return 1

    archivable = {_norm(a.path) for a in actions if a.kind in ARCHIVE_CONFIRM_KINDS}
    bad_archive = [p for p in args.confirm_archive if _norm(p) not in archivable]
    if bad_archive:
        for path in bad_archive:
            print(
                f"error: --confirm-archive {path} 不是 unregistered／.maigo/.maigo 清單裡的路徑",
                file=sys.stderr,
            )
        return 1
    both = {_norm(p) for p in args.confirm} & {_norm(p) for p in args.confirm_archive}
    if both:
        print(
            f"error: {sorted(both)} 同時出現在 --confirm 與 --confirm-archive",
            file=sys.stderr,
        )
        return 1

    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    backup_root = maigo_dir / BACKUP_REL / stamp
    results = apply(
        actions,
        maigo_dir=maigo_dir,
        backup_root=backup_root,
        confirmed=set(args.confirm),
        archive_confirmed=set(args.confirm_archive),
    )
    print("## 執行結果")
    print("\n".join(f"- {line}" for line in results) if results else "- （無）")
    if results:
        print(f"- 備份：{_display(f'{BACKUP_REL}/{stamp}')}/")
    approved = {_norm(path) for path in [*args.confirm, *args.confirm_archive]}
    pending = [a for a in actions if a.needs_confirm and _norm(a.path) not in approved]
    print(f"- 仍待勾選：{len(pending)} 項（重跑 dry-run 查看）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
