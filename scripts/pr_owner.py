#!/usr/bin/env python3
"""
判斷一顆 PR 是「自己的」還是「別人的」，給 `scripts/artifact_path.py` 的
`owner` 參數用。

`artifact_path.py` 承諾不打網路，所以「作者是誰」這件事在模組外面查好、再當
`owner`（`mine` / `others`）傳進去。這支就是專門打 `gh` 的那一端：

- `current_login(explicit)`：`explicit` 優先，否則 `gh api user --jq .login`。
- `pr_author(url)`：`gh pr view <url> --json author --jq .author.login`。
- `resolve_owner(url, you=None)`：兩邊轉小寫比對，同名回 `mine`，否則 `others`。

查不到（gh 失敗、逾時、空輸出）一律 raise `OwnerUnknownError`，不猜；呼叫端
要請使用者明確指定 `--owner mine|others`。

只用 stdlib；不 import `board_state` / `artifact_path` / `board_sync`，避免循環。

跑（CLI）：

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pr_owner.py" --url <PR url> [--you <login>]
```

成功時 stdout 三行 `owner: mine|others`、`author: <login>`、`you: <login>`，
exit 0；失敗時 exit 1，stderr 指向 `--owner`。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from typing import Literal

Owner = Literal["mine", "others"]

_GH_TIMEOUT_SECONDS = 30


class OwnerUnknownError(RuntimeError):
    """查不到 PR 作者或目前使用者，無法判斷 owner。"""


def _run_gh(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=_GH_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise OwnerUnknownError(f"gh {' '.join(args[:2])} 無法執行: {error}") from error
    if result.returncode != 0:
        stderr_lines = result.stderr.strip().splitlines()
        reason = stderr_lines[-1] if stderr_lines else f"exit {result.returncode}"
        raise OwnerUnknownError(f"gh {' '.join(args[:2])} 失敗: {reason}")
    output = result.stdout.strip()
    if not output or output == "null":
        raise OwnerUnknownError(f"gh {' '.join(args[:2])} 沒有回傳內容")
    return output


def current_login(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    return _run_gh(["api", "user", "--jq", ".login"])


def pr_author(url: str) -> str:
    return _run_gh(["pr", "view", url, "--json", "author", "--jq", ".author.login"])


def resolve_owner(url: str, *, you: str | None = None) -> Owner:
    login = current_login(you)
    author = pr_author(url)
    return "mine" if author.lower() == login.lower() else "others"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="PR URL")
    parser.add_argument("--you", default=None, help="目前使用者 login（省略則查 gh）")
    args = parser.parse_args(argv)

    try:
        login = current_login(args.you)
        author = pr_author(args.url)
    except OwnerUnknownError as error:
        print(
            f"無法判斷 PR 作者（{error}）；請改用 `--owner mine|others` 明確指定",
            file=sys.stderr,
        )
        return 1

    owner: Owner = "mine" if author.lower() == login.lower() else "others"
    print(f"owner: {owner}")
    print(f"author: {author}")
    print(f"you: {login}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
