#!/usr/bin/env python3
"""
Maigo PreToolUse hook：擋下帶 `Co-Authored-By:` trailer 的 `git commit`。

背景：`skills/commit-message/SKILL.md` 的「不加 Co-Authored-By trailer」只寫在
prompt 層，已被違反多次。依 CLAUDE.md 的 Hooks vs Skills boundary（失敗應該擋下整個
turn → hook），這支 hook 把它降成機器擋。

只匹配 `Bash` 工具。判準刻意保守——寧可少擋、不可誤擋，因為誤擋會讓載入此 plugin
的所有 session 都無法 commit：

- 把指令切成 segment（`;` `&&` `||` `|` `&` 換行；引號內不切），只看
  `git [全域選項] commit ...` 的 segment（含 `git -C <dir> commit`、`--amend`）。
- 訊息來源只取指令字面上看得到的：`-m` / `--message` / `--trailer` 的值，以及掛在
  該 segment 上的 heredoc 內文（含 `-m "$(cat <<'EOF' ... EOF)"` 這種寫在引號內的形狀）。
- `-F <file>` 這類訊息不在指令字面上的情況不讀檔，放行。
- trailer 判準是「某一行以 `Co-Authored-By:` 開頭」（不分大小寫）：真正的 trailer 一定
  獨佔一行；散文裡提到這個字樣（例如討論這條規則的 commit）不算。
- `git log --grep Co-Authored-By`、`grep`、`echo` 等非 `git commit` 指令一律放行。
- 解析失敗（引號不平衡、輸入畸形）→ fail-open，靜默放行。

逃生口：`.claude/skip-commit-trailer-check`（在 hook payload 的 `cwd` 下），第一行
非空非註解視為原因；存在就整個跳過，形狀與 `.claude/skip-test-verification` 相同。

放行不輸出 decision payload，理由同 `hooks/legacy_artifact_path_check.py`：PreToolUse 的
`approve` 等於跳過權限系統，這個 hook 沒有資格代替使用者做那個決定。
"""

from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path
from typing import NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_io import emit

SKIP_FILE = "skip-commit-trailer-check"

_TRAILER_RE = re.compile(r"^[ \t]*co-authored-by[ \t]*:", re.IGNORECASE | re.MULTILINE)
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_]\w*=")
_HEREDOC_RE = re.compile(r"""<<-?[ \t]*(?:'([^'\n]+)'|"([^"\n]+)"|([^\s;&|<>()'"]+))""")

# git 全域選項裡「值在下一個 token」的那幾個。
_GIT_OPTS_WITH_VALUE = {
    "-C",
    "-c",
    "--git-dir",
    "--work-tree",
    "--namespace",
    "--exec-path",
}
# git commit 短選項裡會吃值的字母（`m` 另外處理）。
_COMMIT_SHORT_WITH_VALUE = set("FCctS")


class _Segment:
    def __init__(self) -> None:
        self.text: list[str] = []
        self.heredocs: list[str] = []


def _split_segments(command: str) -> list[_Segment]:
    """Split on top-level `; & | newline`, pulling heredoc bodies onto their segment."""
    segments = [_Segment()]
    pending: list[tuple[_Segment, str]] = []
    quote: str | None = None
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        cur = segments[-1]
        if quote == "'":
            cur.text.append(ch)
            if ch == "'":
                quote = None
        elif quote == '"':
            cur.text.append(ch)
            if ch == "\\" and i + 1 < n:
                i += 1
                cur.text.append(command[i])
            elif ch == '"':
                quote = None
        elif ch in "'\"":
            quote = ch
            cur.text.append(ch)
        elif ch == "\\" and i + 1 < n:
            cur.text.append(ch)
            i += 1
            cur.text.append(command[i])
        elif command.startswith("<<", i) and not command.startswith("<<<", i):
            m = _HEREDOC_RE.match(command, i)
            if m is None:
                cur.text.append(ch)
            else:
                pending.append((cur, m.group(1) or m.group(2) or m.group(3)))
                i = m.end() - 1
        elif ch == "\n":
            segments.append(_Segment())
            for owner, delim in pending:
                body: list[str] = []
                i += 1
                while i < n:
                    end = command.find("\n", i)
                    line = command[i:] if end == -1 else command[i:end]
                    i = n if end == -1 else end
                    if line.strip() == delim:
                        break
                    body.append(line)
                    i += 1
                owner.heredocs.append("\n".join(body))
            pending = []
        elif ch in ";&|":
            segments.append(_Segment())
        else:
            cur.text.append(ch)
        i += 1
    return segments


def _commit_args(tokens: list[str]) -> list[str] | None:
    """If tokens are `git [opts] commit ...`, return the args after `commit`."""
    i = 0
    while i < len(tokens) and (
        _ENV_ASSIGN_RE.match(tokens[i]) or tokens[i] in ("command", "env")
    ):
        i += 1
    if i >= len(tokens) or tokens[i].rsplit("/", 1)[-1] != "git":
        return None
    i += 1
    while i < len(tokens):
        tok = tokens[i]
        if tok in _GIT_OPTS_WITH_VALUE:
            i += 2
        elif tok.startswith("-"):
            i += 1
        else:
            return tokens[i + 1 :] if tok == "commit" else None
    return None


def _message_values(args: list[str]) -> list[str]:
    """Message-bearing values literally present in `git commit` args."""
    values: list[str] = []
    i = 0
    while i < len(args):
        tok = args[i]
        i += 1
        if tok in ("--message", "--trailer"):
            if i < len(args):
                values.append(args[i])
                i += 1
        elif tok.startswith(("--message=", "--trailer=")):
            values.append(tok.split("=", 1)[1])
        elif tok.startswith("--") or not tok.startswith("-") or tok == "-":
            continue
        else:
            for pos, letter in enumerate(tok[1:], start=1):
                if letter == "m" or letter in _COMMIT_SHORT_WITH_VALUE:
                    rest = tok[pos + 1 :]
                    if rest:
                        if letter == "m":
                            values.append(rest)
                    elif i < len(args):
                        if letter == "m":
                            values.append(args[i])
                        i += 1
                    break
    return values


def has_coauthor_trailer(command: str) -> bool:
    """True when a `git commit` in `command` carries a Co-Authored-By trailer."""
    for seg in _split_segments(command):
        try:
            tokens = shlex.split("".join(seg.text))
        except ValueError:
            continue  # unbalanced quotes etc. → fail-open for this segment
        args = _commit_args(tokens)
        if args is None:
            continue
        if any(_TRAILER_RE.search(v) for v in [*_message_values(args), *seg.heredocs]):
            return True
    return False


def _skip_reason(cwd: object) -> str | None:
    base = Path(cwd) if isinstance(cwd, str) and cwd else Path.cwd()
    path = base / ".claude" / SKIP_FILE
    try:
        if not path.is_file():
            return None
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line
    except OSError:
        return None
    return None


_BLOCK_REASON = (
    "此 plugin 的 commit 慣例不加 AI 共同作者 trailer（`Co-Authored-By:`）。"
    "請把該行從 commit 訊息移除後重下一次（見 skills/commit-message/SKILL.md 的 Trailers 段）。\n"
    f"若這個 repo 確實需要，在 `.claude/{SKIP_FILE}` 寫一行原因即可關閉本檢查。"
)


def _pass_through() -> NoReturn:
    """Silent fail-open: no decision payload, so the permission flow is untouched."""
    sys.exit(0)


def main() -> None:
    try:
        raw = sys.stdin.read()
        try:
            data = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            _pass_through()
        if not isinstance(data, dict) or data.get("tool_name") != "Bash":
            _pass_through()
        tool_input = data.get("tool_input")
        if not isinstance(tool_input, dict):
            _pass_through()
        command = tool_input.get("command")
        if not isinstance(command, str) or not command.strip():
            _pass_through()
        if not has_coauthor_trailer(command):
            _pass_through()
        if _skip_reason(data.get("cwd")) is not None:
            _pass_through()
        emit("block", _BLOCK_REASON)
    except SystemExit:
        raise
    except Exception:
        _pass_through()


if __name__ == "__main__":
    main()
