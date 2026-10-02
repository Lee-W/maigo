"""Guard: runtime commands must locate plugin scripts via ${CLAUDE_PLUGIN_ROOT}.

Commands/skills run in the user's *target* repo, where a bare ``scripts/x.py``
or a ``${CLAUDE_PLUGIN_ROOT:-.}`` fallback (the variable is substituted in
Markdown only, so the fallback silently resolves to ``.``) does not exist.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ("commands", "skills", "agents")

# Any default-value expansion (`:-` or `-`) or a brace-less `$CLAUDE_PLUGIN_ROOT`
# (never substituted, and unset in the Bash tool's environment).
FALLBACK_FORM = re.compile(r"CLAUDE_PLUGIN_ROOT:?-")
BRACELESS_FORM = re.compile(r"\$CLAUDE_PLUGIN_ROOT(?!\w)")
BARE_RELATIVE = re.compile(r"""python3\s+(?:-\S+\s+)?["']?\.?/?scripts/""")

# (relative path, substring identifying the line) -> reason it is allowed.
BARE_RELATIVE_EXEMPT = {
    (
        "skills/pr-context-cache/SKILL.md",
        "在 maigo repo 自身工作時",
    ): "contributor hint: explicitly scoped to running inside the maigo repo",
}


def _lines(globs):
    for name, pattern in globs:
        for path in sorted((ROOT / name).rglob(pattern)):
            rel = path.relative_to(ROOT).as_posix()
            text = path.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), start=1):
                yield rel, lineno, line


def _md_lines():
    return _lines((name, "*.md") for name in SCAN_DIRS)


def _all_lines():
    # .py usage docstrings in scripts/ and hooks/ get copied into prompts too.
    return _lines(
        [(n, "*.md") for n in SCAN_DIRS] + [("scripts", "*.py"), ("hooks", "*.py")]
    )


def test_no_plugin_root_fallback_to_cwd() -> None:
    hits = [
        f"{rel}:{lineno}"
        for rel, lineno, line in _all_lines()
        if FALLBACK_FORM.search(line) or BRACELESS_FORM.search(line)
    ]
    assert not hits, (
        f"use plain ${{CLAUDE_PLUGIN_ROOT}}, no fallback/brace-less: {hits}"
    )


def test_detection_patterns_catch_known_bad_spellings() -> None:
    bad_relative = [
        "python3 scripts/x.py",
        "python3  scripts/x.py",
        "python3 ./scripts/x.py",
        'python3 "scripts/x.py"',
        "python3 -u scripts/x.py",
        "Bash(python3 scripts/x.py:*)",
    ]
    for sample in bad_relative:
        assert BARE_RELATIVE.search(sample), sample
    assert FALLBACK_FORM.search("${CLAUDE_PLUGIN_ROOT:-.}/x")
    assert FALLBACK_FORM.search("${CLAUDE_PLUGIN_ROOT-.}/x")
    assert BRACELESS_FORM.search("$CLAUDE_PLUGIN_ROOT/scripts/x.py")
    good = [
        'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/x.py"',
        "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/x.py",
        'python3 "<maigo-root>/scripts/x.py"',
        'python3 "$MAIGO_HOME/scripts/x.py"',
        "uv run python scripts/validate_plugin.py",
    ]
    for sample in good:
        assert not BARE_RELATIVE.search(sample), sample
        assert not FALLBACK_FORM.search(sample), sample
        assert not BRACELESS_FORM.search(sample), sample


def test_no_bare_relative_script_invocations() -> None:
    hits = []
    for rel, lineno, line in _md_lines():
        if not BARE_RELATIVE.search(line):
            continue
        if any(
            rel == exempt_rel and marker in line
            for exempt_rel, marker in BARE_RELATIVE_EXEMPT
        ):
            continue
        hits.append(f"{rel}:{lineno}")
    assert not hits, (
        f"use python3 ${{CLAUDE_PLUGIN_ROOT}}/scripts/... instead of bare path: {hits}"
    )
