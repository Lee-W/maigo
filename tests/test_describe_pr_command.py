"""Tests for /maigo:describe-pr command and github-title-description skill."""

from __future__ import annotations

import re
import sys
from pathlib import Path


# Allow importing scripts package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from _frontmatter import parse_frontmatter  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
COMMAND_FILE = ROOT / "commands" / "describe-pr.md"
SKILL_FILE = ROOT / "skills" / "github-title-description" / "SKILL.md"
DOCS_COMMAND_SHIM = ROOT / "docs" / "commands" / "describe-pr.md"
DOCS_SKILL_SHIM = ROOT / "docs" / "skills" / "github-title-description.md"
MKDOCS_YML = ROOT / "mkdocs.yml"


# ---------------------------------------------------------------------------
# 1. command file exists
# ---------------------------------------------------------------------------


def test_command_file_exists():
    assert COMMAND_FILE.exists(), f"{COMMAND_FILE} が存在しない"


# ---------------------------------------------------------------------------
# 2. command frontmatter description is non-empty
# ---------------------------------------------------------------------------


def test_command_frontmatter():
    text = COMMAND_FILE.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    assert fm is not None, "commands/describe-pr.md frontmatter が解析できない"
    assert fm.get("description"), "commands/describe-pr.md の description が空"


# ---------------------------------------------------------------------------
# 3. command has <!-- mkdocs-include-start -->
# ---------------------------------------------------------------------------


def test_command_has_include_marker():
    text = COMMAND_FILE.read_text(encoding="utf-8")
    assert (
        "<!-- mkdocs-include-start -->" in text
    ), "commands/describe-pr.md に <!-- mkdocs-include-start --> がない"


# ---------------------------------------------------------------------------
# 4. command references skill by literal path
# ---------------------------------------------------------------------------


def test_command_references_skill():
    text = COMMAND_FILE.read_text(encoding="utf-8")
    assert (
        "skills/github-title-description" in text
    ), "commands/describe-pr.md に skills/github-title-description への参照がない"


# ---------------------------------------------------------------------------
# 5. skill file exists
# ---------------------------------------------------------------------------


def test_skill_file_exists():
    assert SKILL_FILE.exists(), f"{SKILL_FILE} が存在しない"


# ---------------------------------------------------------------------------
# 6. skill frontmatter: name == "github-title-description" + description prefix
# ---------------------------------------------------------------------------


def test_skill_frontmatter():
    text = SKILL_FILE.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    assert fm is not None, "SKILL.md frontmatter が解析できない"
    assert (
        fm.get("name") == "github-title-description"
    ), f"skill name が期待と異なる: {fm.get('name')!r}"
    desc = fm.get("description", "")
    assert desc.startswith(
        "This skill should be used when"
    ), f"skill description が 'This skill should be used when' で始まっていない: {desc!r}"


# ---------------------------------------------------------------------------
# 7. skill has <!-- mkdocs-include-start -->
# ---------------------------------------------------------------------------


def test_skill_has_include_marker():
    text = SKILL_FILE.read_text(encoding="utf-8")
    assert (
        "<!-- mkdocs-include-start -->" in text
    ), "SKILL.md に <!-- mkdocs-include-start --> がない"


# ---------------------------------------------------------------------------
# 8. docs files exist and include the source exactly once via include-markdown
#    (a mermaid diagram before the include is allowed, like other command docs)
# ---------------------------------------------------------------------------


def test_docs_shims_exist():
    for shim_path in (DOCS_COMMAND_SHIM, DOCS_SKILL_SHIM):
        assert shim_path.exists(), f"{shim_path} が存在しない"
        text = shim_path.read_text(encoding="utf-8")
        include_lines = [
            line for line in text.splitlines() if "include-markdown" in line
        ]
        assert (
            len(include_lines) == 1
        ), f"{shim_path} の include-markdown 行が 1 行でない: {len(include_lines)}"


# ---------------------------------------------------------------------------
# 9. mkdocs.yml nav contains both entries
# ---------------------------------------------------------------------------


def test_mkdocs_nav_has_entries():
    text = MKDOCS_YML.read_text(encoding="utf-8")
    assert (
        "commands/describe-pr.md" in text
    ), "mkdocs.yml の nav に commands/describe-pr.md がない"
    assert (
        "skills/github-title-description.md" in text
    ), "mkdocs.yml の nav に skills/github-title-description.md がない"


# ---------------------------------------------------------------------------
# 10. no conventional-commits prefix in skill "Good" examples
# ---------------------------------------------------------------------------


def test_no_conventional_prefix_in_skill_good_examples():
    text = SKILL_FILE.read_text(encoding="utf-8")
    # Extract content of "Good" column cells from the Bad → Good table.
    # Pattern: table row with | Bad | Good | — grab the Good cell.
    # We look at all lines that look like table rows and extract the last cell.
    conventional_cell_pattern = re.compile(
        r"^`?(feat|fix|chore|docs|style|refactor|test)\s*[!:]",
        re.IGNORECASE,
    )
    # Only scan lines that are in the "Good" column (second cell in table).
    # Build a simple check: find all table row lines, split by |, check second cell.

    # sanity-check: pattern must catch a conventional prefix
    assert conventional_cell_pattern.search(
        "`feat: Reject something`"
    ), "pattern should catch conventional prefix but didn't"

    bad_matches = []
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        # The "Good" cell is the second cell (index 1).
        good_cell = cells[1] if len(cells) >= 2 else ""
        if conventional_cell_pattern.search(good_cell):
            bad_matches.append(line)
    assert not bad_matches, (
        "skill の Good 例に conventional commits prefix が含まれている:\n"
        + "\n".join(bad_matches)
    )


# ---------------------------------------------------------------------------
# 11. cross-source links to agents/commands/skills use absolute GitHub URLs
# ---------------------------------------------------------------------------


def test_cross_source_links_are_absolute():
    """Any markdown link pointing into agents/, commands/, or skills/ source
    directories must use an absolute https://github.com/Lee-W/maigo/... URL.
    Relative links like ](../commands/foo.md) or ](../../skills/bar/SKILL.md)
    are forbidden in source files (mkdocs strict-mode would abort).
    """
    # Relative link pattern: ](../something) or ](../../something) pointing into
    # agents/, commands/, or skills/
    relative_source_link = re.compile(r"\]\(\.\.+/(?:agents|commands|skills)/")
    violations = []
    for source_file in (COMMAND_FILE, SKILL_FILE):
        text = source_file.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            if relative_source_link.search(line):
                violations.append(f"{source_file.name}:{lineno}: {line.strip()}")
    assert not violations, (
        "source ファイル内に agents/commands/skills への相対 link がある（絶対 GitHub URL を使うこと）:\n"
        + "\n".join(violations)
    )
