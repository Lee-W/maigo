#!/usr/bin/env python3
"""
讀一或多個 PR 上「別人」留的 review comment，輸出 JSON，給 `/maigo:retro --pr` 歸類用。

唯讀：只經 `gh api <path> --paginate` 做 GET，不帶 `-X`／`--method`／`-f`／`-F`／`--input`，
不呼叫 `gh pr comment`／`review`／`edit`。不寫任何檔、不改 `.maigo/`。

過濾定義（每個 PR）：
- 排除 PR 作者本人的 comment（login 大小寫不分）與 login 以 `[bot]` 結尾的帳號
- inline comment 只留 root（`in_reply_to_id` 為空），reply 不收
- review body 只留非空的；issue comment 照樣排除作者與 bot

抓資料（`fetch_pr`）與過濾（`filter_pr`）分開：過濾吃 dict、不打網路；`gh` 執行器
（`run_gh`）可注入，測試用 fake 取代。module import 時無副作用。

跑（CLI）：

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pr_review_comments.py" <PR url> [<PR url> ...]
```

成功時 stdout 是 JSON list（每個 PR 一筆），exit 0；URL 格式不對或 `gh` 失敗時
stderr 印原因、exit 1。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable
from typing import Any

GhRunner = Callable[[list[str]], str]

_GH_TIMEOUT_SECONDS = 60
_PR_URL_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/pull/(\d+)/?$")
_BOT_SUFFIX = "[bot]"


class PrCommentsError(RuntimeError):
    """URL 格式不對，或 `gh` 讀取失敗。"""


def parse_pr_url(url: str) -> tuple[str, str, int]:
    match = _PR_URL_RE.match(url.strip())
    if not match:
        raise PrCommentsError(
            f"不是 PR URL（https://github.com/<owner>/<repo>/pull/<n>）: {url}"
        )
    return match.group(1), match.group(2), int(match.group(3))


def run_gh(args: list[str]) -> str:
    """真正執行 `gh`；只供 `fetch_pr` 以 `api <path> --paginate` 呼叫。"""
    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=_GH_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PrCommentsError(f"gh {' '.join(args[:2])} 無法執行: {error}") from error
    if result.returncode != 0:
        stderr_lines = result.stderr.strip().splitlines()
        reason = stderr_lines[-1] if stderr_lines else f"exit {result.returncode}"
        raise PrCommentsError(f"gh {' '.join(args[:2])} 失敗: {reason}")
    return result.stdout


def _decode_pages(text: str) -> list[Any]:
    """`gh api --paginate` 把每頁的 JSON array 直接串接；逐段解碼後攤平。"""
    decoder = json.JSONDecoder()
    items: list[Any] = []
    index = 0
    while index < len(text):
        if text[index].isspace():
            index += 1
            continue
        value, index = decoder.raw_decode(text, index)
        if isinstance(value, list):
            items.extend(value)
        else:
            items.append(value)
    return items


def _get(path: str, runner: GhRunner) -> list[Any]:
    return _decode_pages(runner(["api", path, "--paginate"]))


def fetch_pr(url: str, runner: GhRunner = run_gh) -> dict[str, Any]:
    """抓一個 PR 的原始資料（全是 GET）；不做任何過濾。"""
    owner, repo, number = parse_pr_url(url)
    base = f"repos/{owner}/{repo}"
    pulls = _get(f"{base}/pulls/{number}", runner)
    if not pulls:
        raise PrCommentsError(f"gh 沒有回傳 PR 資料: {url}")
    return {
        "url": url,
        "pull": pulls[0],
        "review_comments": _get(f"{base}/pulls/{number}/comments?per_page=100", runner),
        "reviews": _get(f"{base}/pulls/{number}/reviews?per_page=100", runner),
        "issue_comments": _get(f"{base}/issues/{number}/comments?per_page=100", runner),
    }


def _login(item: dict[str, Any]) -> str:
    user = item.get("user") or {}
    return str(user.get("login") or "")


def _is_other_human(login: str, author: str) -> bool:
    if login.lower() == author.lower():
        return False
    if login.endswith(_BOT_SUFFIX):
        return False
    return True


def filter_pr(raw: dict[str, Any]) -> dict[str, Any]:
    """從原始資料留下「非作者、非 bot」的 comment；不打網路。"""
    author = _login(raw["pull"])

    review_comments = []
    for comment in raw["review_comments"]:
        if comment.get("in_reply_to_id") is not None:
            continue
        login = _login(comment)
        if not _is_other_human(login, author):
            continue
        line = comment.get("line") or comment.get("original_line")
        review_comments.append(
            {
                "user": login,
                "url": comment.get("html_url"),
                "path": comment.get("path"),
                "line": line,
                "body": comment.get("body", ""),
            }
        )

    reviews = []
    for review in raw["reviews"]:
        login = _login(review)
        if not _is_other_human(login, author):
            continue
        if not (review.get("body") or "").strip():
            continue
        reviews.append(
            {
                "user": login,
                "state": review.get("state"),
                "url": review.get("html_url"),
                "body": review["body"],
            }
        )

    issue_comments = []
    for comment in raw["issue_comments"]:
        login = _login(comment)
        if not _is_other_human(login, author):
            continue
        issue_comments.append(
            {
                "user": login,
                "url": comment.get("html_url"),
                "body": comment.get("body", ""),
            }
        )

    return {
        "url": raw["url"],
        "author": author,
        "review_comments": review_comments,
        "reviews": reviews,
        "issue_comments": issue_comments,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("urls", nargs="+", help="PR URL（可多個）")
    args = parser.parse_args(argv)

    try:
        results = [filter_pr(fetch_pr(url)) for url in args.urls]
    except PrCommentsError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
