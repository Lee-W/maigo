#!/usr/bin/env python3
"""跨 repo 唯讀 Work Board 索引：一次回答「現在該我動哪些」，不用逐一 cd 進每個 repo。

背景：`.maigo/board.md` 綁 cwd repo 是刻意設計（見
[`skills/work-board/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md)），
但這代表「現在該我動哪些」這句話沒有單一答案——13 個裝了 maigo 的 repo 各自
一份 board，實測其中 maigo / commitizen / pycon-etl 三份互不相通且過期。這支
腳本不重寫 board 的行文法，只把每個 repo 的「🎯 下一件」原樣抄一份到單一檔案。

**全程唯讀**：只讀 `<repo>/.maigo/board.md`，不寫回任何被掃描 repo 的 `board.md`
內容本身，也不重新解析每一行的欄位或合併排序——只逐字複製 `## 🎯 下一件`
整段。唯一的寫入動作是整份重寫 `~/.config/maigo/board-index.md`（這份索引檔
本身沒有手寫區、沒有 upsert 語意，每次重新產生，用 `Write` 沒有樂觀鎖疑慮）。

**格式假設已用真實 board.md 驗證過、且證實不成立時要能安全失敗**：本 session
實際讀了 maigo 自己（新格式）、commitizen（05-30）、pycon-etl（07-25）三份
真實 board.md——後兩份是**舊版三分區行文法**（`## 🎯 你的球` 而非
`## 🎯 下一件`，另有 `### 已 review` 這類巢狀子標題、`📥 無法分類`／
`🗄️ 已放棄` 這類舊 section），header 行雖然仍能被 regex 抽出計數，但找不到
`## 🎯 下一件` 這個 heading——這正是本腳本要處理的「格式無法解析」情境，不是
理論假設。header 抽得到、`## 🎯 下一件` 找不到、或兩者皆失敗，一律視為整份
無法解析（**大聲失敗、不猜、不用只有半邊資料的結果誤導使用者**），且不因為
某一個 repo 解析失敗就中斷其餘 repo 的處理。

唯讀輸入：`--repo-list <file>`（預設 `~/.config/maigo/repos.txt`，與
`scripts/migrate_legacy_artifacts.py` 共用同一份清單）。

跑（CLI）：

```
python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/board_index.py" [--repo-list ~/.config/maigo/repos.txt]
```

核心邏輯 `parse_board_text()` / `build_index()` 是純函式，只吃字串、只吐字串，
跟「掃 repo 清單、讀檔」的 I/O 完全分離，可被測試用純字串輸入輸出驗證。
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_REPO_LIST = Path("~/.config/maigo/repos.txt").expanduser()
_DEFAULT_OUTPUT = Path("~/.config/maigo/board-index.md").expanduser()

# 例：`> 最後刷新：2026-08-18 14:30 ｜ 🎯 3 ｜ ⏳ 2 ｜ ✅ 1 ｜ 🧠 待學習盤點 1`
# 只抽日期與三個計數；`🧠` 欄位是 optional，不強制要求存在。
_HEADER_RE = re.compile(
    r"^>\s*最後刷新：\s*(?P<date>\S+(?:\s+\S+)?)\s*｜\s*🎯\s*(?P<todo>\d+)"
    r"\s*｜\s*⏳\s*(?P<waiting>\d+)\s*｜\s*✅\s*(?P<done>\d+)",
    re.MULTILINE,
)
_NEXT_SECTION_HEADING_RE = re.compile(r"^## 🎯 下一件.*$", re.MULTILINE)
_ANY_SECTION_HEADING_RE = re.compile(r"^## .*$", re.MULTILINE)


@dataclass(frozen=True)
class BoardHeader:
    date: str
    todo: int
    waiting: int
    done: int


@dataclass(frozen=True)
class BoardParseResult:
    ok: bool
    header: BoardHeader | None
    next_section_lines: list[str] | None  # `## 🎯 下一件` 原始內容，逐字保留


def parse_board_text(text: str) -> BoardParseResult:
    """解析 `board.md` 的 header 計數 ＋ `## 🎯 下一件` 整段原文。純函式。

    header 抽不到、或找不到 `## 🎯 下一件` 這個 heading（含舊版三分區行文法，
    heading 是 `## 🎯 你的球`）→ `ok=False`，兩個欄位都是 `None`——整份視為
    無法解析，不回傳只有一半資料的結果。
    """
    header_match = _HEADER_RE.search(text)
    heading_match = _NEXT_SECTION_HEADING_RE.search(text)
    if header_match is None or heading_match is None:
        return BoardParseResult(ok=False, header=None, next_section_lines=None)

    header = BoardHeader(
        date=header_match.group("date"),
        todo=int(header_match.group("todo")),
        waiting=int(header_match.group("waiting")),
        done=int(header_match.group("done")),
    )

    body_start = heading_match.end()
    next_heading = _ANY_SECTION_HEADING_RE.search(text, pos=body_start)
    body_end = next_heading.start() if next_heading else len(text)
    body = text[body_start:body_end]
    lines = body.strip("\n").splitlines()

    return BoardParseResult(ok=True, header=header, next_section_lines=lines)


@dataclass(frozen=True)
class RepoBoardEntry:
    name: str
    path: str
    status: str  # "ok" | "no_board" | "unparseable"
    result: BoardParseResult | None = None


def scan_repo_board(repo_path: str | Path) -> RepoBoardEntry:
    """讀 `<repo>/.maigo/board.md`，回傳這個 repo 的索引項目。唯讀 I/O。"""
    repo = Path(repo_path)
    board_path = repo / ".maigo" / "board.md"
    if not board_path.is_file():
        return RepoBoardEntry(name=repo.name, path=str(repo), status="no_board")

    text = board_path.read_text(encoding="utf-8")
    result = parse_board_text(text)
    if not result.ok:
        return RepoBoardEntry(
            name=repo.name, path=str(repo), status="unparseable", result=result
        )
    return RepoBoardEntry(name=repo.name, path=str(repo), status="ok", result=result)


def build_index(entries: list[RepoBoardEntry], generated_at: str) -> str:
    """把每個 repo 的索引項目彙整成整份 `board-index.md` 內容。純函式。"""
    total = len(entries)
    with_board = sum(1 for e in entries if e.status == "ok")

    lines = [
        "# maigo Cross-repo Board Index",
        f"> 產生於：{generated_at} ｜ {total} 個 repo（{with_board} 有 board）",
        "",
    ]

    for entry in entries:
        lines.append(f"## {entry.name}（{entry.path}）")
        if entry.status == "no_board":
            lines.append("")
            lines.append("(no board)")
            lines.append("")
            continue
        if entry.status == "unparseable":
            lines.append("")
            lines.append(f"⚠️ 格式無法解析，開 `{entry.path}/.maigo/board.md` 手動查")
            lines.append("")
            continue

        # status == "ok" 時 scan_repo_board() 保證 result 與其兩個欄位都非
        # None（見該函式與 parse_board_text() 的合約），這裡 assert 只是給
        # mypy 一個型別窄化的錨點，不是新的執行期防呆。
        assert entry.result is not None
        assert entry.result.header is not None
        assert entry.result.next_section_lines is not None
        header = entry.result.header
        lines.append(
            f"> 🎯 {header.todo} ｜ ⏳ {header.waiting} ｜ ✅ {header.done} "
            f"｜ 最後刷新：{header.date}"
        )
        lines.append("")
        lines.extend(entry.result.next_section_lines)
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def _read_repo_list(path: Path) -> list[str]:
    if not path.is_file():
        return []
    repos = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        repos.append(line)
    return repos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-list",
        default=str(_DEFAULT_REPO_LIST),
        help="一行一個絕對路徑的純文字檔，預設 ~/.config/maigo/repos.txt",
    )
    parser.add_argument(
        "--output",
        default=str(_DEFAULT_OUTPUT),
        help="輸出檔路徑，預設 ~/.config/maigo/board-index.md",
    )
    args = parser.parse_args(argv)

    repos = _read_repo_list(Path(args.repo_list).expanduser())
    entries = [scan_repo_board(repo) for repo in repos]

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    content = build_index(entries, generated_at)

    output_path = Path(args.output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")

    print(f"path: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
