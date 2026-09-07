"""Detect acceptance criteria that lean on a literal grep count as proof.

Registered harness lesson family「字面 grep 當判準」(2026-07-25 / 07-31 /
08-11)：把「掃某 pattern，命中數必須是 0」寫成驗收條件，只證明了那串**字面**
pattern 不存在，證不到它代表的抽象性質。兩個方向都會出錯：

- pattern 命中正當內容（註解、對照表、fixture、詞彙表），逼執行者刪掉不該刪的東西
- pattern 命中無關的共現字串，判準回非預期值，而「修好它」比原狀更糟

判準應該寫成語意版，或把掃描範圍限縮到 `git diff` 的新增行。
"""

from __future__ import annotations

import re

_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_CHECKBOX_RE = re.compile(r"^\[[ xX]\]\s*")
_GREP_RE = re.compile(r"\b(?:grep|rg|ripgrep)\b")
_COUNT_ZERO_RE = re.compile(
    r"為零|為 ?0(?![.\d])|回 ?0(?![.\d])|=\s*0(?![.\d])|應為 ?0(?![.\d])"
    r"|必須是 ?0(?![.\d])|零命中|沒有任何命中|不得有任何命中|只准剩"
    r"|no matches|count\s*(?:==|=|:)?\s*0(?![.\d])"
)
# 已經把範圍限縮到「本次改動」的判準不算違規——那是教訓本身給的正解。
_SCOPED_RE = re.compile(r"git diff|新增行|added lines|本次新增|本次修改|diff 的")
# 引用這條規則本身（反例、禁令）不該被自己擋下。
_NEGATION_RE = re.compile(r"不要|不得用|別用|禁止|避免|不可用|反例|wrong example")

MAX_HITS = 3
_HIT_MAX_LEN = 160


def _strip_bullet(line: str) -> str:
    """Drop the list marker and checkbox so the quoted hit reads cleanly."""
    stripped = _BULLET_RE.sub("", line, count=1)
    return _CHECKBOX_RE.sub("", stripped, count=1).strip() or line


def find_literal_grep_criteria(text: str, limit: int = MAX_HITS) -> list[str]:
    """Return acceptance-criteria lines that prove a property by grep count."""
    hits: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not _BULLET_RE.match(raw) and "驗收" not in line:
            continue
        if not _GREP_RE.search(line) or not _COUNT_ZERO_RE.search(line):
            continue
        if _SCOPED_RE.search(line) or _NEGATION_RE.search(line):
            continue
        hits.append(_strip_bullet(line)[:_HIT_MAX_LEN])
        if len(hits) >= limit:
            break
    return hits


def block_reason(where: str, hits: list[str]) -> str:
    """Build the block message shown when literal-grep criteria are found."""
    listed = "\n".join(f"  - {h}" for h in hits)
    return (
        f"{where}把「字面 grep 的命中數」當成抽象性質的證明：\n"
        f"{listed}\n"
        "這是登記在案的教訓家族「字面 grep 當判準」（2026-07-25／07-31／08-11）："
        "pattern 會命中正當內容（註解、對照表、fixture、詞彙表）或無關的共現字串，"
        "判準回非預期值時，錯的往往是判準而不是產物，而照字面「修好它」比原狀更糟。\n"
        "改法二選一：(1) 寫成語意版判準（要證明的性質是什麼就寫什麼，例如"
        "「兩個迴圈不得有本地 literal，欄位名須來自共用常數」）；"
        "(2) 真要掃就把範圍限縮到 `git diff` 的新增行或明列豁免區段，"
        "並先問「這個 pattern 除了我想抓的，還會命中什麼」。"
    )
