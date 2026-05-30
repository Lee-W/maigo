"""Shared test helpers and fixtures."""

from __future__ import annotations

import io
import json
import types
from pathlib import Path
from typing import Any

import pytest


def run_hook_main(
    module: types.ModuleType,
    payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> dict[str, Any]:
    """Run a hook's main() with a fake stdin payload.

    Patches sys.stdin so the hook reads the given payload JSON,
    then captures the stdout JSON written by emit() before sys.exit(0).
    Returns the parsed JSON dict.
    """
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    with pytest.raises(SystemExit):
        module.main()
    out = capsys.readouterr().out
    return json.loads(out.strip())


@pytest.fixture
def plugin_tree(tmp_path: Path) -> Path:
    """Build a minimal valid plugin tree under tmp_path."""
    # plugin.json
    (tmp_path / "plugin.json").write_text(
        json.dumps(
            {
                "name": "test-plugin",
                "version": "0.1.0",
                "description": "test",
                "license": "MIT",
            }
        ),
        encoding="utf-8",
    )

    # agents/foo.md with full required frontmatter
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "foo.md").write_text(
        "---\nname: foo\ndescription: test agent\nmodel: sonnet\ntools: [Read]\n---\n\n# foo\n",
        encoding="utf-8",
    )

    # commands/bar.md (must contain mkdocs-include-start marker)
    cmds_dir = tmp_path / "commands"
    cmds_dir.mkdir()
    (cmds_dir / "bar.md").write_text(
        "---\ndescription: test command\n---\n\n<!-- mkdocs-include-start -->\n\n# bar\n",
        encoding="utf-8",
    )

    # docs/commands/bar.md — include shim (required by check_commands_docs_alignment)
    docs_cmds_dir = tmp_path / "docs" / "commands"
    docs_cmds_dir.mkdir(parents=True)
    (docs_cmds_dir / "bar.md").write_text(
        '{% include-markdown "../../commands/bar.md" start="<!-- mkdocs-include-start -->" %}\n',
        encoding="utf-8",
    )

    # skills/baz/SKILL.md
    skill_dir = tmp_path / "skills" / "baz"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: baz\ndescription: test skill\n---\n\n# baz\n",
        encoding="utf-8",
    )

    # hooks/hooks.json pointing at a real hook script
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    (hooks_dir / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "Stop": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/check.py",
                                }
                            ]
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    (hooks_dir / "check.py").write_text("# minimal hook\n", encoding="utf-8")

    return tmp_path
