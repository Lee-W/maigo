#!/usr/bin/env python3
"""
改寫 board 細節檔（`.maigo/i/*.md`）筆記區裡讓 `gf` 失效的路徑寫法。

背景：Neovim 把大於等於 256 的字元一律算檔名字元，所以路徑緊貼中文或全形標點
（`報告：../review/1/review.md（舊）`）時，`<cfile>` 會把標籤與標點一起吃進去，`gf` 開不到檔；
舊寫法的裸路徑 `review/<id>/…`（相對 `.maigo/`）從 `i/` 底下的檔案解析不到。這支 script 只改這兩種：

1. **舊寫法**：`(.maigo/)?(review|pr)/<id>/<檔>.md` → `../review/<id>/<檔>.md`／`../pr/<id>/<檔>.md`
   （檔案相對）；目標檔必須真的存在，否則略過。
2. **分隔**：路徑緊鄰大於等於 256 的字元（前或後任一側）→ 用反引號把路徑本身（含 `:行號`）包起來；
   路徑必須解析得到實際存在的檔（依序試細節檔所在目錄、repo root），否則略過。

**只改「筆記裡引用檔案」形狀的路徑（正向判斷，不靠指令字清單）**：路徑是該行第一個東西（清單／引用標記之後）、
緊貼中文字或全形標點、或前一個以空白分隔的詞以中文字／全形標點結尾（`見 <路徑>`）、或以半形冒號結尾的英文標籤
（`Review report: <路徑>`，同行第二個 `; inline comments: <路徑>` 也算），或被單一對反引號包住且外側符合前述；
前一個詞是其他 ASCII（指令、旗標、`>>`、`|`、`$EDITOR`、英文散文）的一律不改、列為略過。第二層保護（行首指令字、
fence、縮排、反引號 span）優先，所以 `echo x: <路徑>` 不改。代價是英文散文裡的路徑（`see .maigo/review/1/review.md`）
也不會被改——寧可少改，這是啟發式不是保證；套用前請看乾跑清單與略過清單。

只處理每個細節檔「`## 判斷` 那一行起到檔尾」（事實區一律不碰；沒有 `## 判斷` 的檔略過）。
不碰：fenced code block（含 `~~~`）內、含空白的反引號片段（shell 指令字串，例如 `--body-file .maigo/…`）、
`<URL>` 與裸 URL。以位元組讀寫、只換路徑字串本身：保留 CRLF 與檔尾有無換行；寫前重讀確認內容與規劃時相同，
不同就略過；暫存檔加 `os.replace`；非 UTF-8 的檔案略過。

用法：

```
python3 scripts/rewrite_note_paths.py [--repo-list ~/.config/maigo/repos.txt] [--apply] [repo ...]
```

位置參數是 repo 根目錄（未給時讀 `--repo-list`，每行一個絕對路徑，空行與 `#` 開頭忽略）。
預設乾跑：每一處印出檔案、行號、改前整行、改後整行與處置種類；略過的另列原因與原行；結尾印統計。
`--apply` 才寫檔。

只 `tmp_path` 假 repo 上跑過 `--apply` 測試——套用到真實 state 前請先乾跑、備份、給使用者看輸出。

stdlib-only。純函式 `plan_line_rewrites()`、`find_adjacent_paths()` 供測試共用。
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

JUDGMENT_HEADING = "## 判斷"  # 與 board_refresh.JUDGMENT_HEADING 同一個切點
_DEFAULT_REPO_LIST = Path("~/.config/maigo/repos.txt").expanduser()

_FNAME = (
    r"-A-Za-z0-9_.+,#$%~="  # vim 預設 isfname 的 ASCII 檔名字元（不含 `/`，另外處理）
)
_PATH_RE = re.compile(
    rf"(?<![{_FNAME}/])"
    rf"(?P<path>(?:[{_FNAME}]+/)+[{_FNAME}]*\.[A-Za-z0-9]+)"
    r"(?P<lineno>:\d+)?"
)
_LEGACY_RE = re.compile(
    r"^(?:\.maigo/)?(?P<kind>review|pr)/(?P<id>[^/]+)/(?P<file>[^/]+\.md)$"
)
_URL_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s<>`)\]]+")
_SPAN_RE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")  # 清單內縮排的 fence 也算
_COMMAND_WORDS = frozenset(
    "gh git cat cp mv rm ls less more head tail vim nvim vi open cd diff grep sed "
    "python python3 uv sh bash zsh xargs tee code mkdir touch echo printf".split()
)
_LIST_MARKER_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")
CODE_REASON = "疑似指令字串／code"
ASCII_REASON = "前一個詞是 ASCII，疑似指令或參數"
_LEAD_RE = re.compile(r"^(?:\s*(?:>|[-*+](?=\s)|\d+[.)](?=\s)))*\s*")


@dataclass
class Edit:
    start: int
    end: int
    replacement: str
    kind: str  # 改寫 | 分隔 | 改寫+分隔


@dataclass
class Skip:
    reason: str
    path: str


@dataclass
class LinePlan:
    new_line: str
    edits: list[Edit] = field(default_factory=list)
    skips: list[Skip] = field(default_factory=list)


def _is_wide(char: str) -> bool:
    return ord(char) >= 256


def _candidates(line: str) -> list[dict]:
    """Path-looking strings in one line with their neighbours; URLs are not candidates."""
    url_spans = [m.span() for m in _URL_RE.finditer(line)]
    spans = [(m.start(), m.end(), m.group(2).strip()) for m in _SPAN_RE.finditer(line)]
    found = []
    for m in _PATH_RE.finditer(line):
        start = m.start()
        path = m["path"]
        trimmed = path.rstrip(".,")  # 句尾的 `.` `,` 屬於文句，不屬於路徑
        lineno = "" if trimmed != path else (m["lineno"] or "")
        path = trimmed
        end = start + len(path)
        if not path or "/" not in path or not re.search(r"\.[A-Za-z0-9]+$", path):
            continue
        if any(a <= start < b for a, b in url_spans):
            continue
        end_all = end + len(lineno)
        before = line[start - 1] if start else ""
        after = line[end_all] if end_all < len(line) else ""
        span = next((sp for sp in spans if sp[0] <= start < sp[1]), None)
        found.append(
            {
                "start": start,
                "end": end_all,
                "path": path,
                "lineno": lineno,
                "adjacent": bool(before and _is_wide(before))
                or bool(after and _is_wide(after)),
                # 在行內 code 裡：只有整個 span 就是這一條路徑時才算安全
                "in_code_span": span is not None and span[2] != path + lineno,
                "before_text": line[:start],
            }
        )
    return found


def _resolve(path: str, detail_dir: Path, repo_root: Path) -> Path | None:
    for base in (detail_dir, repo_root):
        candidate = base / path
        if candidate.is_file():
            return candidate
    return None


def _is_code_like(before_text: str, line: str, indented_code: bool) -> bool:
    """Command strings and code: a flag or command word right before the path, a line that
    starts with a command word, or a 4+ space indented non-list line (markdown code block)."""
    if indented_code:
        return True
    tokens = before_text.split()
    if tokens and len(tokens[-1]) > 1 and tokens[-1].startswith("-"):
        return True
    if tokens and tokens[-1] in _COMMAND_WORDS:
        return True
    words = _LIST_MARKER_RE.sub("", line + " ", count=1).split()
    return bool(words) and (words[0] in _COMMAND_WORDS or words[0].startswith("$"))


def _reads_like_a_note(before_text: str) -> bool:
    """Positive shape test: the path is the first thing on the line (甲), glued to a CJK
    character or full-width mark (乙), or follows a token that ends in one (丙). A single
    backticked path is judged by what precedes its backtick (丁). Anything else — a command,
    flag, redirect, `$EDITOR`, English prose — is not a note reference and stays untouched."""
    if before_text.endswith("`") and not before_text.endswith("``"):
        before_text = before_text[:-1]
    lead = _LEAD_RE.match(before_text)
    rest = before_text[lead.end() if lead else 0 :]
    if not rest.strip():
        return True
    if _is_wide(rest[-1]):
        return True
    if not rest[-1].isspace():
        return False
    token = rest.split()[-1]
    if _is_wide(token[-1]):
        return True
    # 英文標籤 `Review report: <路徑>`（含同行第二個 `; inline comments: <路徑>`）
    return (
        token.endswith(":")
        and not token.startswith("-")
        and token[:-1] not in _COMMAND_WORDS
    )


def is_indented_code(line: str) -> bool:
    return bool(re.match(r"^(?: {4,}|\t)", line)) and not _LIST_MARKER_RE.match(line)


def plan_line_rewrites(
    line: str, *, maigo_dir: Path, detail_dir: Path, repo_root: Path
) -> LinePlan:
    """Plan the rewrites of one line (outside fences). Pure apart from `is_file` lookups."""
    edits: list[Edit] = []
    skips: list[Skip] = []
    indented = is_indented_code(line)
    for cand in _candidates(line):
        path, lineno = cand["path"], cand["lineno"]
        if not (cand["adjacent"] or _LEGACY_RE.match(path)):
            continue  # 一般文字，不是這支 script 要處理的形狀
        if cand["in_code_span"] or _is_code_like(cand["before_text"], line, indented):
            skips.append(Skip(CODE_REASON, path))
            continue
        if not _reads_like_a_note(cand["before_text"]):
            skips.append(Skip(ASCII_REASON, path))
            continue
        rewritten = path
        kinds = []
        legacy = _LEGACY_RE.match(path)
        if legacy:
            target = maigo_dir / legacy["kind"] / legacy["id"] / legacy["file"]
            if not target.is_file():
                skips.append(Skip("指不到實際存在的檔", path))
                continue
            rewritten = f"../{legacy['kind']}/{legacy['id']}/{legacy['file']}"
            kinds.append("改寫")
        wrap = cand["adjacent"]
        if wrap:
            if _resolve(rewritten, detail_dir, repo_root) is None:
                if not kinds:
                    continue
                wrap = False
            else:
                kinds.append("分隔")
        if not kinds:
            continue
        text = rewritten + lineno
        edits.append(
            Edit(
                cand["start"],
                cand["end"],
                f"`{text}`" if wrap else text,
                "+".join(kinds),
            )
        )
    new_line = line
    for edit in sorted(edits, key=lambda e: e.start, reverse=True):
        new_line = new_line[: edit.start] + edit.replacement + new_line[edit.end :]
    return LinePlan(new_line, edits, skips)


def _fence_states(lines: list[str]) -> list[bool]:
    """True for each line that is a fence delimiter or inside a fenced code block."""
    states = []
    opener: str | None = None
    for raw in lines:
        line = raw.rstrip("\r")
        match = _FENCE_RE.match(line)
        if opener is None:
            if match:
                opener = match[1]
                states.append(True)
            else:
                states.append(False)
            continue
        states.append(True)
        if (
            match
            and match[1][0] == opener[0]
            and len(match[1]) >= len(opener)
            and line.strip() == match[1]
        ):
            opener = None
    return states


def find_adjacent_paths(text: str) -> list[tuple[int, str]]:
    """
    `(line_no, path)` for each path that sits right next to a character of 256 or above and
    so would break `gf`. Fenced code blocks and URLs are ignored; backticked, angle-bracketed
    and own-line paths are never adjacent by construction.
    """
    lines = text.split("\n")
    fenced = _fence_states(lines)
    return [
        (number, cand["path"] + cand["lineno"])
        for number, (line, in_fence) in enumerate(zip(lines, fenced), 1)
        if not in_fence
        for cand in _candidates(line)
        if cand["adjacent"]
    ]


def _judgment_start(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if line.rstrip("\r") == JUDGMENT_HEADING:
            return index
    return None


@dataclass
class FilePlan:
    path: Path
    original: bytes
    new_text: str
    changes: list[dict] = field(default_factory=list)
    skips: list[dict] = field(default_factory=list)
    skipped_reason: str | None = None


def plan_file(path: Path, *, maigo_dir: Path, repo_root: Path) -> FilePlan:
    original = path.read_bytes()
    try:
        text = original.decode("utf-8")
    except UnicodeDecodeError:
        return FilePlan(path, original, "", skipped_reason="非 UTF-8")
    lines = text.split("\n")
    start = _judgment_start(lines)
    if start is None:
        return FilePlan(path, original, text, skipped_reason="沒有 `## 判斷` 行")
    fenced = _fence_states(lines)
    plan = FilePlan(path, original, text)
    out = list(lines)
    for index in range(start, len(lines)):
        if fenced[index]:
            continue
        result = plan_line_rewrites(
            lines[index],
            maigo_dir=maigo_dir,
            detail_dir=path.parent,
            repo_root=repo_root,
        )
        for skip in result.skips:
            plan.skips.append(
                {
                    "line": index + 1,
                    "reason": skip.reason,
                    "path": skip.path,
                    "text": lines[index],
                }
            )
        if result.edits:
            out[index] = result.new_line
            plan.changes.append(
                {
                    "line": index + 1,
                    "before": lines[index],
                    "after": result.new_line,
                    "kind": "+".join(sorted({e.kind for e in result.edits})),
                }
            )
    plan.new_text = "\n".join(out)
    return plan


def apply_plan(plan: FilePlan) -> str | None:
    """Write one planned file; returns a skip reason or None when written."""
    if plan.path.read_bytes() != plan.original:
        return "檔案在規劃後被改動，未覆蓋"
    target = plan.path.resolve()  # 細節檔是 symlink 時寫到真檔，不把連結換成一般檔
    tmp = target.with_name(f".{target.name}.rewrite-{os.getpid()}.tmp")
    try:
        tmp.write_bytes(plan.new_text.encode("utf-8"))
        shutil.copymode(target, tmp)
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    return None


def _read_repo_list(path: Path) -> list[str] | None:
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return None
    return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]


def _show(line: str) -> str:
    return line.rstrip("\r")


def run_repo(repo: Path, *, apply: bool, out=print) -> dict:
    stats = {"files": 0, "changed_files": 0, "changes": 0, "skips": 0}
    maigo_dir = repo / ".maigo"
    for path in sorted((maigo_dir / "i").glob("*.md")):
        stats["files"] += 1
        rel = f"{repo}/.maigo/i/{path.name}"
        plan = plan_file(path, maigo_dir=maigo_dir, repo_root=repo)
        if plan.skipped_reason:
            out(f"略過 {rel} :: {plan.skipped_reason}")
            stats["skips"] += 1
            continue
        for change in plan.changes:
            out(f"[{change['kind']}] {rel}:{change['line']}")
            out(f"  改前：{_show(change['before'])}")
            out(f"  改後：{_show(change['after'])}")
        for skip in plan.skips:
            out(f"[略過] {rel}:{skip['line']} :: {skip['reason']}（{skip['path']}）")
            out(f"  原行：{_show(skip['text'])}")
        stats["changes"] += len(plan.changes)
        stats["skips"] += len(plan.skips)
        if plan.changes:
            stats["changed_files"] += 1
            if apply:
                reason = apply_plan(plan)
                if reason:
                    out(f"略過 {rel} :: {reason}")
                    stats["skips"] += 1
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "repos", nargs="*", help="repo 根目錄（未給時改讀 --repo-list）"
    )
    parser.add_argument(
        "--repo-list",
        default=str(_DEFAULT_REPO_LIST),
        help="一行一個絕對路徑的純文字檔，預設 ~/.config/maigo/repos.txt",
    )
    parser.add_argument(
        "--apply", action="store_true", help="真的寫檔；預設只乾跑印出清單"
    )
    args = parser.parse_args(argv)

    repos = args.repos
    if not repos:
        listed = _read_repo_list(Path(args.repo_list).expanduser())
        if listed is None:
            print(
                f"error: --repo-list file not found or unreadable: {args.repo_list}",
                file=sys.stderr,
            )
            return 1
        if not listed:
            print(
                f"error: --repo-list file has no repo paths: {args.repo_list}",
                file=sys.stderr,
            )
            return 1
        repos = listed

    total = {"files": 0, "changed_files": 0, "changes": 0, "skips": 0}
    for repo in repos:
        repo_path = Path(repo)
        if not repo_path.is_dir():
            print(f"{repo} :: skipped (repo path does not exist)")
            continue
        for key, value in run_repo(repo_path, apply=args.apply).items():
            total[key] += value
    mode = "已套用" if args.apply else "乾跑（未寫檔；加 --apply 才寫）"
    print(
        f"{mode}：掃描 {total['files']} 個細節檔，"
        f"{total['changes']} 行變更（{total['changed_files']} 個檔），略過 {total['skips']} 項"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
