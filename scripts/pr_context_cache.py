#!/usr/bin/env python3
"""Fetch-or-restore PR context for /maigo:review (skills/pr-context-cache).

First run fetches PR context (title / body / diff / CI status / linked issues /
inline review threads with resolution state / review summaries / conversation
comments) and caches it into a machine-readable section at the top of
`.maigo/review-rubric.md`. Re-runs with the same source and an unchanged diff
restore the cache instead of re-fetching.

Review threads / review summaries / conversation comments are only fetched
for a `pr` source (branch / range diffs have no GitHub review thread to
attach to). Unresolved (`OPEN`) threads are marked distinctly in the
rendered output so a reviewer can spot outstanding maintainer feedback
before finalizing a verdict.

跑：`python3 scripts/pr_context_cache.py <source> [--rubric PATH] [--base BRANCH]`

source 可以是 GitHub PR URL / PR 編號（需要 gh CLI）、本地 branch 名、
或 commit range（如 `main..feature`）。

stdout 第一行印 `cache_hit: true|false`，其後是 cache 區段全文（含全部欄位）。
gh / git 失敗 → exit 1 + stderr 一行（caller 改走手動 fetch）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CACHE_START = "<!-- pr-context-cache:start v1 -->"
CACHE_END = "<!-- pr-context-cache:end -->"
DIFF_LINE_LIMIT = 2000
BODY_LINE_LIMIT = 500


def classify_source(source: str) -> str:
    """Return one of "pr" / "range" / "branch" for *source*."""
    if source.startswith(("http://", "https://")):
        return "pr"
    if re.fullmatch(r"#?\d+", source):
        return "pr"
    if ".." in source:
        return "range"
    return "branch"


def run(cmd: list[str], check: bool = True) -> str:
    """Run *cmd*, return stripped stdout. exit 1 with stderr note on failure."""
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        err = result.stderr.strip() or f"exit {result.returncode}"
        sys.stderr.write(f"pr_context_cache: `{' '.join(cmd)}` failed: {err}\n")
        sys.exit(1)
    return result.stdout.strip()


def truncate_lines(text: str, limit: int, suffix: str) -> str:
    """Return *text* capped at *limit* lines, appending *suffix* if cut."""
    lines = text.splitlines()
    if len(lines) <= limit:
        return text
    return "\n".join(lines[:limit]) + f"\n{suffix}"


def extract_linked_issues(*texts: str) -> list[str]:
    """Collect unique `#N` references from the given texts, in first-seen order."""
    seen: list[str] = []
    for text in texts:
        for ref in re.findall(r"#\d+", text):
            if ref not in seen:
                seen.append(ref)
    return seen


def repo_slug() -> str:
    """Return `owner/repo` for the current git remote, via gh. "" on failure."""
    return run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        check=False,
    )


def fetch_review_threads(owner: str, name: str, number: str) -> str:
    """Fetch inline review threads (resolution state + comments) via GraphQL."""
    if not owner or not name:
        return "n/a"
    query = (
        "query($owner:String!,$name:String!,$number:Int!){"
        "repository(owner:$owner,name:$name){pullRequest(number:$number){"
        "reviewThreads(first:100){nodes{isResolved path line "
        "comments(first:20){nodes{author{login} body}}}}}}}"
    )
    raw = run(
        [
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={query}",
            "-F",
            f"owner={owner}",
            "-F",
            f"name={name}",
            "-F",
            f"number={number}",
        ],
        check=False,
    )
    if not raw:
        return "n/a"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return "n/a"
    nodes = (
        data.get("data", {})
        .get("repository", {})
        .get("pullRequest", {})
        .get("reviewThreads", {})
        .get("nodes", [])
    )
    return render_review_threads(nodes)


def render_review_threads(nodes: list[dict]) -> str:
    """Render review-thread nodes, marking unresolved threads as `[OPEN]`."""
    if not nodes:
        return "n/a"
    lines: list[str] = []
    for node in nodes:
        status = "[OPEN]" if not node.get("isResolved") else "[RESOLVED]"
        location = f"{node.get('path', 'n/a')}:{node.get('line', 'n/a')}"
        lines.append(f"- **{status}** `{location}`")
        for comment in node.get("comments", {}).get("nodes", []):
            author = (comment.get("author") or {}).get("login", "n/a")
            body = (comment.get("body") or "").strip().splitlines()
            first_line = body[0] if body else ""
            lines.append(f"  - {author}: {first_line}")
    return "\n".join(lines) or "n/a"


def render_reviews(raw: str) -> str:
    """Render `gh pr view --json reviews` output as one line per review."""
    if not raw:
        return "n/a"
    try:
        reviews = json.loads(raw).get("reviews", [])
    except json.JSONDecodeError:
        return "n/a"
    if not reviews:
        return "n/a"
    lines = []
    for review in reviews:
        author = (review.get("author") or {}).get("login", "n/a")
        state = review.get("state", "n/a")
        body = (review.get("body") or "").strip().splitlines()
        first_line = body[0] if body else ""
        lines.append(f"- {author} **{state}**: {first_line}")
    return "\n".join(lines) or "n/a"


def render_comments(raw: str) -> str:
    """Render `gh pr view --json comments` output as one line per comment."""
    if not raw:
        return "n/a"
    try:
        comments = json.loads(raw).get("comments", [])
    except json.JSONDecodeError:
        return "n/a"
    if not comments:
        return "n/a"
    lines = []
    for comment in comments:
        author = (comment.get("author") or {}).get("login", "n/a")
        body = (comment.get("body") or "").strip().splitlines()
        first_line = body[0] if body else ""
        lines.append(f"- {author}: {first_line}")
    return "\n".join(lines) or "n/a"


def fetch_context(source: str, kind: str, base: str) -> dict[str, str]:
    """Fetch full context for *source*. Returns the field dict for render_cache."""
    pr_id = source.lstrip("#")
    if kind == "pr":
        meta = json.loads(
            run(["gh", "pr", "view", pr_id, "--json", "title,body,number"])
        )
        diff = run(["gh", "pr", "diff", pr_id])
        # gh pr checks exits nonzero while checks are pending / failing —
        # the output is still the summary we want.
        ci = run(["gh", "pr", "checks", pr_id], check=False) or "n/a"
        title = meta.get("title") or "n/a"
        body = meta.get("body") or ""
        number = str(meta.get("number") or "n/a")
        log = ""
        diff_stat = run(["gh", "pr", "diff", pr_id, "--stat"], check=False)
        owner, _, name = repo_slug().partition("/")
        review_threads = fetch_review_threads(owner, name, number)
        reviews = render_reviews(
            run(["gh", "pr", "view", pr_id, "--json", "reviews"], check=False)
        )
        comments = render_comments(
            run(["gh", "pr", "view", pr_id, "--json", "comments"], check=False)
        )
    else:
        spec = source if kind == "range" else f"{base}...{source}"
        diff = run(["git", "diff", spec])
        log = run(["git", "log", "--oneline", spec], check=False)
        diff_stat = run(["git", "diff", "--stat", spec])
        title = "n/a"
        body = ""
        number = ci = "n/a"
        review_threads = reviews = comments = "n/a"

    issues = extract_linked_issues(body, log)
    return {
        "source": source,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pr_number": number,
        "title": title,
        "body": truncate_lines(body, BODY_LINE_LIMIT, "...[truncated]") or "n/a",
        "linked_issues": ", ".join(issues) or "n/a",
        "ci_status": ci,
        "diff_stat": diff_stat or "n/a",
        "review_threads": review_threads,
        "reviews": reviews,
        "comments": comments,
        "diff_sha": hashlib.sha256(diff.encode("utf-8")).hexdigest(),
        "diff": truncate_lines(
            diff, DIFF_LINE_LIMIT, f"[diff truncated at {DIFF_LINE_LIMIT} lines]"
        ),
    }


def current_diff_sha(source: str, kind: str, base: str) -> str:
    """Compute sha256 of the current full diff for cache validation."""
    if kind == "pr":
        diff = run(["gh", "pr", "diff", source.lstrip("#")])
    elif kind == "range":
        diff = run(["git", "diff", source])
    else:
        diff = run(["git", "diff", f"{base}...{source}"])
    return hashlib.sha256(diff.encode("utf-8")).hexdigest()


def render_cache(f: dict[str, str]) -> str:
    """Render the machine-readable cache section from the field dict."""
    return (
        f"{CACHE_START}\n"
        "## PR Context (cached)\n"
        "\n"
        f"- **Source**: {f['source']}\n"
        f"- **Fetched at**: {f['fetched_at']}\n"
        f"- **PR number**: {f['pr_number']}\n"
        f"- **Title**: {f['title']}\n"
        f"- **Body**: {f['body']}\n"
        f"- **Linked issues**: {f['linked_issues']}\n"
        f"- **CI status**: {f['ci_status']}\n"
        f"- **Diff stat**: {f['diff_stat']}\n"
        f"- **Diff sha**: {f['diff_sha']}\n"
        "\n"
        "### Review threads (unresolved marked `[OPEN]`)\n"
        "\n"
        f"{f['review_threads']}\n"
        "\n"
        "### Review summaries\n"
        "\n"
        f"{f['reviews']}\n"
        "\n"
        "### Conversation comments\n"
        "\n"
        f"{f['comments']}\n"
        "\n"
        "<details>\n"
        f"<summary>Full diff (cached, first {DIFF_LINE_LIMIT} lines)</summary>\n"
        "\n"
        "```diff\n"
        f"{f['diff']}\n"
        "```\n"
        "\n"
        "</details>\n"
        f"{CACHE_END}"
    )


def find_cache_section(rubric_text: str) -> str | None:
    """Return the existing cache section (markers included), or None."""
    start = rubric_text.find(CACHE_START)
    end = rubric_text.find(CACHE_END)
    if start == -1 or end == -1 or end < start:
        return None
    return rubric_text[start : end + len(CACHE_END)]


def parse_cached_field(section: str, field: str) -> str:
    """Extract a one-line `- **<field>**: value` from the cached section."""
    m = re.search(rf"^- \*\*{re.escape(field)}\*\*: (.*)$", section, re.MULTILINE)
    return m.group(1).strip() if m else ""


def write_cache(rubric_path: Path, section: str) -> None:
    """Create / prepend / replace the cache section in the rubric file."""
    if not rubric_path.exists():
        rubric_path.parent.mkdir(parents=True, exist_ok=True)
        rubric_path.write_text(section + "\n", encoding="utf-8")
        return
    text = rubric_path.read_text(encoding="utf-8")
    old = find_cache_section(text)
    if old is None:
        new_text = section + "\n\n" + text
    else:
        new_text = text.replace(old, section, 1)
    rubric_path.write_text(new_text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="GitHub PR URL/number, branch, or commit range")
    parser.add_argument("--rubric", default=".maigo/review-rubric.md")
    parser.add_argument("--base", default="main", help="base branch for branch diffs")
    args = parser.parse_args(argv)

    kind = classify_source(args.source)
    rubric_path = Path(args.rubric)

    cached = None
    if rubric_path.exists():
        cached = find_cache_section(rubric_path.read_text(encoding="utf-8"))

    if cached and parse_cached_field(cached, "Source") == args.source:
        sha_now = current_diff_sha(args.source, kind, args.base)
        if parse_cached_field(cached, "Diff sha") == sha_now:
            print("cache_hit: true")
            print(cached)
            return 0

    fields = fetch_context(args.source, kind, args.base)
    section = render_cache(fields)
    write_cache(rubric_path, section)
    print("cache_hit: false")
    print(section)
    return 0


if __name__ == "__main__":
    sys.exit(main())
