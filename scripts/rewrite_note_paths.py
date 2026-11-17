#!/usr/bin/env python3
"""
改寫 `.maigo` 筆記與報告裡讓 `gf` 失效的路徑寫法。

背景：Neovim 把大於等於 256 的字元一律算檔名字元，所以路徑緊貼中文或全形標點
（`報告：../review/1/review.md（舊）`）時，`<cfile>` 會把標籤與標點一起吃進去，`gf` 開不到檔；
repo-root 寫法（`.maigo/review/1/rubric.md`）在 cwd 不是 repo root 時（例如 `cd .maigo`）解析不到；
舊寫法的裸路徑 `review/<id>/…`（相對 `.maigo/`）從 `i/` 底下的檔案解析不到。這支 script 的原則只有一條：
**`.maigo` 內的互連相對於檔案自己的位置**，`gf` 就不依賴 cwd。

**掃描範圍（白名單）**

- `i/*.md` 細節檔：只處理「`## 判斷` 那一行起到檔尾」（事實區一律不碰；沒有 `## 判斷` 的檔略過）。
- `review/<id>/` 與 `pr/<id>/` 底下的 `review.md`、`rubric.md`、`pr-comments.md`：整檔，扣除 fenced code、
  HTML 註解（含 `maigo-review` metadata）與 `pr-context-cache:start`～`:end` 之間整段（PR diff 與 GitHub 原文）。
- **貼文用檔不掃**：`draft.md`、`inline-comments.md`、`reply-draft.md`、`follow-up-issue.md`——它們會貼到 GitHub，
  裡面若有 `.maigo/…` 是內容問題不是 `gf` 問題，改成相對路徑反而會把它貼出去；其他未登記檔名（`plan*.md`、手寫筆記）
  同樣不掃。輸出會印「未掃描：N 個貼文用／未登記檔」讓範圍看得見。

**改什麼**

1. **改寫**：`.maigo/<路徑>` 與無前綴的 `(review|pr|issue|topic|i)/…`（目標檔必須真的存在於 `.maigo` 內）→ 相對於**該檔所在目錄**的寫法
   （同目錄裸檔名 `rubric.md`，見 `SAME_DIR_STYLE`；跨目錄 `../../i/1.md`、`../review/1/review.md`）。
   無前綴且 repo root 也有同名檔時無法判斷，略過並說明。
2. **分隔**：路徑緊鄰大於等於 256 的字元（前或後任一側）→ 用反引號把路徑本身（含 `:行號`）包起來。
   細節檔筆記區：路徑須解析得到實際存在的檔（依序試細節檔所在目錄、repo root）；
   報告檔：**只對落在 `.maigo` 內的目標**分隔。

**報告檔只處理 `.maigo` 內部路徑**：原始碼路徑（`src/pkg/mod.py:12`）在報告裡有數千處，一個字都不改、也不記錄、
不出現在略過清單；細節檔筆記區維持原本的行為（原始碼緊貼中文時仍加反引號）。

**只改「筆記裡引用檔案」形狀的路徑（正向判斷，不靠指令字清單）**：路徑是該行第一個東西（清單／引用標記之後）、
緊貼中文字或全形標點、或前一個以空白分隔的詞以中文字／全形標點結尾（`見 <路徑>`）、或以半形冒號結尾的英文標籤
（`Review report: <路徑>`，同行第二個 `; inline comments: <路徑>` 也算），或被單一對反引號包住且外側符合前述；
前一個詞是其他 ASCII（指令、旗標、`>>`、`|`、`$EDITOR`、英文散文）的一律不改、列為略過。第二層保護（行首指令字、
fence、縮排、反引號 span）優先，所以 `echo x: <路徑>` 不改。代價是英文散文裡的路徑（`see .maigo/review/1/review.md`）
也不會被改——寧可少改，這是啟發式不是保證；套用前請看乾跑清單與略過清單。

不碰：fenced code block（含 `~~~`）內、含空白的反引號片段（shell 指令字串，例如 `--body-file .maigo/…`）、
`<URL>` 與裸 URL。以位元組讀寫、只換路徑字串本身：保留 CRLF 與檔尾有無換行；暫存檔加 `os.replace`；
非 UTF-8 的檔案略過。寫入有兩道檢查：規劃後先比一次內容，暫存檔寫完、換上去之前再比一次 `sha256`／`mtime_ns`／大小，
任一次不同就略過並回報「檔案在規劃後被改動，未覆蓋」。乾跑與 `--apply` 各自**重新掃描**磁碟（以內容定位，
行號是當下的，不跨次沿用）；乾跑與套用之間檔案被更新時，請以套用當下輸出的行號為準。
寫入會保留原檔的 atime／mtime（舊報告沒有 `reviewed_at` 時，`board_state` 拿 mtime 當審查時間）。
**套用期間不要同時編輯這些檔**：保護是盡力而為，最後一次檢查與 `os.replace` 之間仍有極短的視窗。

用法：

```
python3 scripts/rewrite_note_paths.py [--repo-list ~/.config/maigo/repos.txt] [--apply] [repo ...]
```

位置參數是 repo 根目錄（未給時讀 `--repo-list`，每行一個絕對路徑，空行與 `#` 開頭忽略）。
預設乾跑：每一處印出檔案、行號、改前整行、改後整行與處置種類；略過的另列原因與原行；結尾印統計與「未掃描：N」。
`--apply` 才寫檔。

只在 `tmp_path` 假 repo 上跑過 `--apply` 測試——套用到真實 state 前請先乾跑、備份、給使用者看輸出。

stdlib-only。純函式 `plan_line_rewrites()`、`find_adjacent_paths()`、`file_relative()` 供測試共用。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_list import read_repo_list  # noqa: E402

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
_MAIGO_KINDS = ("review", "pr", "issue", "topic", "i")
_LEGACY_RE = re.compile(
    r"^(?P<prefix>\.maigo/)?(?P<rel>(?P<kind>review|pr|issue|topic|i)/(?:[^/]+/)*[^/]+\.md)$"
)
_OLD_KINDS = ("review", "pr")  # 舊版只認這兩種；找不到目標時列為略過
# 同目錄的寫法：`bare` ＝ 裸檔名（`rubric.md`）。2026-11 nvim 0.12.6 實測：裸檔名、`./`、
# `../<自己目錄>/<檔>` 與跨目錄 `../../…` 在 cwd 為 repo root、`.maigo`（symlink）、state 真目錄、
# 家目錄（各放同名干擾檔）下 `gf` 全部開到檔案相對的那一份。若哪天某環境裸檔名失效，改成 `sibling`
# 就退回 `../<自己目錄名>/<檔>`。
SAME_DIR_STYLE = "bare"
# 貼文用檔（會貼到 GitHub）與其他未登記檔名都不掃；掃描集是白名單，不是黑名單。
REPORT_FILES = ("review.md", "rubric.md", "pr-comments.md")
REPORT_DIRS = ("review", "pr")
_CACHE_START = "pr-context-cache:start"
_CACHE_END = "pr-context-cache:end"
AMBIGUOUS_REASON = "同名檔也存在於 repo root，無法判斷"
MISSING_REASON = "指不到實際存在的檔"
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


def file_relative(maigo_dir: Path, rel: str, file_dir: Path) -> str:
    """`maigo_dir/rel` written relative to `file_dir` (pure string math, no symlink resolve).

    Both ends sit under the same `.maigo` path, so the result is stable whether `.maigo` is
    a symlink or a real directory. A same-directory target follows `SAME_DIR_STYLE`.
    """
    result = os.path.relpath(maigo_dir / rel, file_dir).replace(os.sep, "/")
    if SAME_DIR_STYLE != "bare" and "/" not in result:
        return f"../{file_dir.name}/{result}"
    return result


def _classify_target(
    path: str,
    *,
    maigo_dir: Path,
    detail_dir: Path,
    repo_root: Path,
    internal_only: bool,
) -> tuple[str, str | None]:
    """How `path` relates to the `.maigo` directory.

    Returns `(state, rel)`; `rel` is the target relative to `maigo_dir` when it is one:
    `none` (not one of ours; a report-mode candidate in this state is dropped without a
    trace), `ok`, `missing` (has a `.maigo/` prefix or an old-style kind but no such file),
    `ambiguous` (unprefixed, exists under both `.maigo` and the repo root).
    """
    legacy = _LEGACY_RE.match(path)
    if path.startswith(".maigo/"):
        rel = path[len(".maigo/") :]
        if ".." in rel.split("/") or not (legacy or internal_only):
            return "none", None
        return ("ok" if (maigo_dir / rel).is_file() else "missing"), rel
    if legacy:
        rel = legacy["rel"]
        if (maigo_dir / rel).is_file():
            if (repo_root / rel).is_file():
                return "ambiguous", rel
            return "ok", rel
        if not internal_only and legacy["kind"] in _OLD_KINDS:
            return "missing", rel
        return "none", None
    if internal_only and path.startswith(("./", "../")):
        norm = os.path.normpath(detail_dir / path)
        root = os.path.normpath(maigo_dir)
        if norm != root and os.path.commonpath([norm, root]) == root:
            if os.path.isfile(norm):
                return "ok", os.path.relpath(norm, root).replace(os.sep, "/")
    return "none", None


def plan_line_rewrites(
    line: str,
    *,
    maigo_dir: Path,
    detail_dir: Path,
    repo_root: Path,
    internal_only: bool = False,
) -> LinePlan:
    """Plan the rewrites of one line (outside fences). Pure apart from `is_file` lookups.

    `internal_only` (report files) first asks whether a candidate is a `.maigo` internal
    path; if not (source code, anything else) it is dropped with no record at all, so a
    report full of `src/pkg/mod.py:12` neither changes nor produces skip noise. The default
    (detail-file notes) keeps the older behaviour, including delimiting source paths.
    """
    edits: list[Edit] = []
    skips: list[Skip] = []
    indented = is_indented_code(line)
    for cand in _candidates(line):
        path, lineno = cand["path"], cand["lineno"]
        state, rel = _classify_target(
            path,
            maigo_dir=maigo_dir,
            detail_dir=detail_dir,
            repo_root=repo_root,
            internal_only=internal_only,
        )
        if state == "none" and (internal_only or not cand["adjacent"]):
            continue  # 一般文字或原始碼，不是這支 script 要處理的形狀
        if cand["in_code_span"] or _is_code_like(cand["before_text"], line, indented):
            skips.append(Skip(CODE_REASON, path))
            continue
        if not _reads_like_a_note(cand["before_text"]):
            skips.append(Skip(ASCII_REASON, path))
            continue
        if state in ("missing", "ambiguous"):
            skips.append(
                Skip(MISSING_REASON if state == "missing" else AMBIGUOUS_REASON, path)
            )
            continue
        rewritten = path
        kinds = []
        wrap = cand["adjacent"]
        if rel is not None:
            rewritten = file_relative(maigo_dir, rel, detail_dir)
            if rewritten != path:
                kinds.append("改寫")
            if wrap:
                kinds.append("分隔")
        elif wrap:
            if _resolve(rewritten, detail_dir, repo_root) is None:
                continue
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


def _comment_states(lines: list[str]) -> list[bool]:
    """True for each line that is, or sits inside, an HTML comment (`<!-- … -->`).

    Whole lines are masked, never parts of them: a report's metadata (`maigo-review`) and
    markers live in comments and must never be edited.
    """
    states = []
    inside = False
    for raw in lines:
        if inside:
            states.append(True)
            inside = "-->" not in raw
        elif "<!--" in raw:
            states.append(True)
            inside = "-->" not in raw.split("<!--", 1)[1]
        else:
            states.append(False)
    return states


def _cache_states(lines: list[str]) -> list[bool]:
    """True for the lines from the `pr-context-cache:start` marker through the `:end` one
    (PR diffs and GitHub text pasted verbatim; an unclosed region runs to the end)."""
    states = []
    inside = False
    for raw in lines:
        if not inside and _CACHE_START in raw:
            inside = True
        states.append(inside)
        if inside and _CACHE_END in raw:
            inside = False
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
    fingerprint: tuple[str, int, int] | None = None


def _fingerprint(path: Path) -> tuple[str, int, int]:
    """`(sha256, mtime_ns, size)` of a file — the identity apply checks twice."""
    data = path.read_bytes()
    stat = path.stat()
    return hashlib.sha256(data).hexdigest(), stat.st_mtime_ns, stat.st_size


def plan_file(
    path: Path, *, maigo_dir: Path, repo_root: Path, kind: str = "note"
) -> FilePlan:
    """Plan one file. `kind="note"`: a detail file, from `## 判斷` to the end. `kind="report"`:
    a review/pr report, whole file minus fences, HTML comments and the pr-context-cache
    region, and only paths that resolve inside the `.maigo` directory are touched."""
    original = path.read_bytes()
    fingerprint = _fingerprint(path)
    try:
        text = original.decode("utf-8")
    except UnicodeDecodeError:
        return FilePlan(path, original, "", skipped_reason="非 UTF-8")
    lines = text.split("\n")
    report = kind == "report"
    if report:
        start = 0
        cache = _cache_states(lines)
        # fence 計算時把 cache 區段當空行，裡面不成對的 ``` 不會把後面整份蓋掉
        fenced = [
            a or b
            for a, b in zip(
                _fence_states(["" if c else ln for ln, c in zip(lines, cache)]),
                _comment_states(lines),
            )
        ]
        fenced = [a or c for a, c in zip(fenced, cache)]
    else:
        found = _judgment_start(lines)
        if found is None:
            return FilePlan(path, original, text, skipped_reason="沒有 `## 判斷` 行")
        start = found
        fenced = _fence_states(lines)
    plan = FilePlan(path, original, text, fingerprint=fingerprint)
    out = list(lines)
    for index in range(start, len(lines)):
        if fenced[index]:
            continue
        result = plan_line_rewrites(
            lines[index],
            maigo_dir=maigo_dir,
            detail_dir=path.parent,
            repo_root=repo_root,
            internal_only=report,
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
    changed = "檔案在規劃後被改動，未覆蓋"
    if plan.path.read_bytes() != plan.original:
        return changed
    target = plan.path.resolve()  # 細節檔是 symlink 時寫到真檔，不把連結換成一般檔
    tmp = target.with_name(f".{target.name}.rewrite-{os.getpid()}.tmp")
    try:
        tmp.write_bytes(plan.new_text.encode("utf-8"))
        shutil.copymode(target, tmp)
        # 保留原檔的 atime／mtime（奈秒）：沒有 `reviewed_at` 的舊 review.md 會被
        # `board_state._auto_local_verdict_at` 拿 mtime 當審查時間，換檔後 mtime 變成現在
        # 會讓「審查後作者有新 commit」的 PR 無聲地不再顯示成「回你的球」。
        stat = target.stat()
        os.utime(tmp, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        # 所有準備工作做完後，緊貼 `os.replace` 前再比一次：暫存檔寫入期間被改動的檔案不覆蓋。
        # 這個檢查與 replace 之間仍有極短的視窗（沒有鎖就關不掉）。
        if plan.fingerprint is not None and _fingerprint(target) != plan.fingerprint:
            return changed
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    return None


def _show(line: str) -> str:
    return line.rstrip("\r")


def _scan_targets(maigo_dir: Path) -> tuple[list[tuple[Path, str]], int]:
    """`(files to scan with their kind, number of files left unscanned)`.

    Scanned: `i/*.md` (notes) and the whitelisted report files under `review/<id>/` and
    `pr/<id>/`. Everything else in those directories (drafts that get pasted to GitHub,
    hand-written files) is counted, never read.
    """
    targets = [(p, "note") for p in sorted((maigo_dir / "i").glob("*.md"))]
    unscanned = 0
    for top in REPORT_DIRS:
        for item_dir in sorted((maigo_dir / top).glob("*")):
            if not item_dir.is_dir():
                continue
            for child in sorted(item_dir.iterdir()):
                if not child.is_file():
                    continue
                if child.name in REPORT_FILES:
                    targets.append((child, "report"))
                else:
                    unscanned += 1
    return targets, unscanned


def run_repo(repo: Path, *, apply: bool, out=print) -> dict:
    stats = {"files": 0, "changed_files": 0, "changes": 0, "skips": 0, "unscanned": 0}
    maigo_dir = repo / ".maigo"
    targets, unscanned = _scan_targets(maigo_dir)
    stats["unscanned"] = unscanned
    out(f"未掃描：{unscanned} 個貼文用／未登記檔（{repo}）")
    for path, kind in targets:
        stats["files"] += 1
        rel = f"{repo}/.maigo/{path.relative_to(maigo_dir).as_posix()}"
        plan = plan_file(path, maigo_dir=maigo_dir, repo_root=repo, kind=kind)
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
        listed = read_repo_list(Path(args.repo_list).expanduser())
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

    total = {"files": 0, "changed_files": 0, "changes": 0, "skips": 0, "unscanned": 0}
    for repo in repos:
        repo_path = Path(repo)
        if not repo_path.is_dir():
            print(f"{repo} :: skipped (repo path does not exist)")
            continue
        for key, value in run_repo(repo_path, apply=args.apply).items():
            total[key] += value
    mode = "已套用" if args.apply else "乾跑（未寫檔；加 --apply 才寫）"
    print(
        f"{mode}：掃描 {total['files']} 個檔，"
        f"{total['changes']} 行變更（{total['changed_files']} 個檔），略過 {total['skips']} 項，"
        f"未掃描：{total['unscanned']} 個貼文用／未登記檔"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
