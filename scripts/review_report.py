#!/usr/bin/env python3
"""Publish the latest review with a TOC, timestamp and explicit local acknowledgement.

Standalone stdlib CLI; never posts to GitHub or rewrites the shared work board.
Only superseded reports with the same source identity are removed after publishing.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import tempfile

_METADATA = re.compile(r"^<!-- maigo-review: (.+) -->$", re.MULTILINE)
VERDICTS = ("APPROVE", "APPROVE_WITH_NITS", "NEEDS_CHANGES", "BLOCKED")


def metadata(text: str) -> dict:
    """Read explicit review state; a malformed managed record is an error."""
    match = _METADATA.search(text)
    if not match:
        return {}
    value = json.loads(match[1])
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("Unsupported review metadata")
    if not all(
        isinstance(value.get(key), str) and value[key]
        for key in ("source", "head_sha", "reviewed_at")
    ):
        raise ValueError("Review metadata requires source, head_sha and reviewed_at")
    if value.get("verdict") not in VERDICTS:
        raise ValueError("Unknown review verdict")
    if "author" in value and not (
        isinstance(value["author"], str) and value["author"].strip()
    ):
        raise ValueError("Review author must be a non-empty string")
    for key in ("reviewed_at", "acknowledged_at"):
        if key in value:
            timestamp = value[key]
            if (
                not isinstance(timestamp, str)
                or datetime.fromisoformat(timestamp.replace("Z", "+00:00")).tzinfo
                is None
            ):
                raise ValueError(f"{key} must include a timezone")
    return value


def same_source(text: str, source: str) -> bool:
    """Accept managed identity or the exact PR field of a legacy report."""
    record = metadata(text)
    if record:
        return record.get("source") == source
    return bool(
        source.startswith("https://github.com/")
        and re.search(r"^# Review:", text, re.MULTILINE)
        and re.search(
            r"^\*\*PR:\*\*\s*" + re.escape(source) + r"/?(?:\s|$)",
            text,
            re.MULTILINE,
        )
    )


def report_path(root: Path, source: str, home_repo: str) -> Path:
    # artifact_path imports board_state; defer this import to avoid a cycle.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from artifact_path import artifact_path, slugify
    from board_state import github_ref

    identifier = (
        github_ref(source, home_repo)
        if source.startswith("https://")
        else slugify(source)
    )
    if not identifier:
        raise ValueError("Review source must have a stable identifier")
    path = root / artifact_path("review", identifier)
    if any(
        part.is_symlink()
        for part in (root / ".maigo", path.parent.parent, path.parent, path)
    ) or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Review path escapes the repository")
    return path


@contextmanager
def report_lock(path: Path):
    """Serialize publication and acknowledgement for this PR only."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.parent / ".review-write-lock"
    try:
        lock.mkdir()
    except FileExistsError as error:
        raise ValueError(
            f"Review is being updated; retry after checking {lock}"
        ) from error
    try:
        yield
    finally:
        lock.rmdir()


def atomic_write(path: Path, text: str) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(text)
            stream.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def render_report(title: str, body: str, record: dict) -> str:
    """Add explicit anchors for every H2/H3 outside fenced examples."""
    if _METADATA.search(body):
        raise ValueError("Supply the review body, not an already published report")
    lines = []
    toc: list[str] = []
    fence = None
    for line in body.strip().splitlines():
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            token = marker[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
        heading = (
            re.match(r"^(#{2,3})\s+(.+?)(?:\s+#+)?$", line) if fence is None else None
        )
        if heading:
            anchor = f"review-section-{len(toc) + 1}"
            label = heading[2].replace("[", r"\[").replace("]", r"\]")
            toc.append(f"{'  ' if len(heading[1]) == 3 else ''}- [{label}](#{anchor})")
            lines.append(f'<a id="{anchor}"></a>\n')
        if fence is None and line.startswith("# "):
            raise ValueError("Body must use H2/H3; the publisher supplies the H1")
        lines.append(line)
    if fence is not None or not toc:
        raise ValueError("Review body needs headings and closed code fences")
    author = record.get("author")
    if author and record["source"].startswith("https://github.com/"):
        author = f"@{author.lstrip('@')}"
    author_line = f"**Author:** {author}\n\n" if author else ""
    return (
        f"# Review: {' '.join(title.split())}\n\n"
        f"<!-- maigo-review: {json.dumps(record, ensure_ascii=False)} -->\n\n"
        f"**Source:** {record['source']}\n\n"
        f"{author_line}"
        f"**最後 review：** {record['reviewed_at']}\n\n"
        f"**Reviewed commit:** `{record['head_sha']}`\n\n"
        f"**Verdict:** {record['verdict']}\n\n"
        "**已看完：** 尚未確認\n\n"
        "## TOC\n\n" + "\n".join(toc) + "\n\n" + "\n".join(lines) + "\n"
    )


def publish(
    root: Path,
    source: str,
    home_repo: str,
    title: str,
    body: str,
    head_sha: str,
    verdict: str,
    author: str | None = None,
) -> dict:
    path = report_path(root, source, home_repo)
    record: dict = {
        "version": 1,
        "source": source,
        "head_sha": head_sha,
        "verdict": verdict,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    if author is not None:
        if not author.strip():
            raise ValueError("Review author must be a non-empty string")
        record["author"] = author.strip()
    text = render_report(title, body, record)
    removed = []
    retained = []
    with report_lock(path):
        if path.exists():
            previous = path.read_text()
            if not same_source(previous, source):
                raise ValueError(f"Review ownership conflict: {path}")
            previous_time = metadata(previous).get("reviewed_at")
            if previous_time and datetime.fromisoformat(
                previous_time.replace("Z", "+00:00")
            ) > datetime.fromisoformat(record["reviewed_at"]):
                raise ValueError(
                    "A newer review was already published; reread before replacing it"
                )
        atomic_write(path, text)
        # Only recognized report names, never drafts, rubrics, notes or other PRs.
        candidates = [
            *path.parent.glob("review-[0-9]*.md"),
            root / ".maigo" / f"review-{path.parent.name}.md",
        ]
        for old in candidates:
            if not old.exists():
                continue
            if old.is_symlink() or (
                not re.fullmatch(r"review-\d+\.md", old.name)
                and old.parent == path.parent
            ):
                retained.append(str(old))
                continue
            old_text = old.read_text()
            try:
                owned = same_source(old_text, source)
                old_record = metadata(old_text)
                old_time = old_record.get("reviewed_at")
                if old_time and datetime.fromisoformat(
                    old_time.replace("Z", "+00:00")
                ) > datetime.fromisoformat(record["reviewed_at"]):
                    owned = False
            except (ValueError, TypeError):
                owned = False
            if owned:
                old.unlink()
                removed.append(str(old))
            else:
                retained.append(str(old))
    return {"path": str(path), **record, "removed": removed, "retained": retained}


def acknowledge(
    root: Path,
    source: str,
    home_repo: str,
    head_sha: str,
    you: str,
    undo: bool = False,
) -> dict:
    path = report_path(root, source, home_repo)
    with report_lock(path):
        text = path.read_text()
        record = metadata(text)
        if not record or record.get("source") != source:
            raise ValueError(
                "Publish a timestamped review for this PR before marking it read"
            )
        if not undo and record.get("head_sha") != head_sha:
            raise ValueError(
                "PR head changed; review the current commit before marking it read"
            )
        if undo:
            record.pop("acknowledged_at", None)
            record.pop("acknowledged_by", None)
        else:
            record["acknowledged_at"] = datetime.now(timezone.utc).isoformat()
            record["acknowledged_by"] = you
        replacement = f"<!-- maigo-review: {json.dumps(record, ensure_ascii=False)} -->"
        text = _METADATA.sub(lambda _: replacement, text, count=1)
        read_status = (
            "尚未確認" if undo else f"{record['acknowledged_at']}（@{you}；本地標記）"
        )
        text = re.sub(
            r"^\*\*已看完：\*\* .*?$",
            lambda _: f"**已看完：** {read_status}",
            text,
            count=1,
            flags=re.MULTILINE,
        )
        atomic_write(path, text)
    return {"path": str(path), **record}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("publish", "acknowledge"))
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--repo", default="")
    parser.add_argument(
        "--source", required=True, help="Canonical PR URL or local branch/range"
    )
    parser.add_argument(
        "--head",
        required=True,
        help="Commit actually reviewed (current PR head when acknowledging)",
    )
    parser.add_argument("--title")
    parser.add_argument("--body-file", type=Path)
    parser.add_argument("--verdict", choices=VERDICTS)
    parser.add_argument("--author", help="Original author (publish only)")
    parser.add_argument("--you")
    parser.add_argument("--undo", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not re.fullmatch(r"[0-9a-fA-F]{40,64}", args.head):
            raise ValueError("--head must be a full commit hash")
        source = args.source.rstrip("/")
        if args.action == "publish":
            if not args.title or not args.body_file or not args.verdict or args.undo:
                raise ValueError("publish requires --title, --body-file and --verdict")
            result = publish(
                args.cwd.resolve(),
                source,
                args.repo,
                args.title,
                args.body_file.read_text(),
                args.head,
                args.verdict,
                args.author,
            )
        else:
            if args.author is not None:
                raise ValueError("--author is only valid with publish")
            if not args.you:
                raise ValueError("acknowledge requires --you")
            result = acknowledge(
                args.cwd.resolve(), source, args.repo, args.head, args.you, args.undo
            )
    except (OSError, ValueError) as error:
        print(f"review_report: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
