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


def make_plugin_json(tmp_path: Path) -> Path:
    """Write a minimal valid .claude-plugin/plugin.json under tmp_path.

    Minimal valid structure: name, version, description, license fields.
    Returns the path to the created file.
    """
    claude_plugin_dir = tmp_path / ".claude-plugin"
    claude_plugin_dir.mkdir(parents=True, exist_ok=True)
    p = claude_plugin_dir / "plugin.json"
    p.write_text(
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
    return p


def make_agent_file(tmp_path: Path, name: str = "foo") -> Path:
    """Write a minimal valid agent markdown file to tmp_path/agents/<name>.md.

    Minimal valid structure: frontmatter with name, description, model, tools fields,
    plus the `<!-- mkdocs-include-start -->` marker required by check_agents_docs_alignment.
    Returns the path to the created file.
    """
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(exist_ok=True)
    p = agents_dir / f"{name}.md"
    p.write_text(
        f"---\nname: {name}\ndescription: test agent\nmodel: sonnet\ntools: [Read]\n---\n\n"
        f"<!-- mkdocs-include-start -->\n\n# {name}\n",
        encoding="utf-8",
    )
    return p


def make_docs_agent_shim(tmp_path: Path, name: str = "foo") -> Path:
    """Write a minimal valid docs/agents shim to tmp_path/docs/agents/<name_lower>.md.

    Required by check_agents_docs_alignment.
    Returns the path to the created shim file.
    """
    docs_agents_dir = tmp_path / "docs" / "agents"
    docs_agents_dir.mkdir(parents=True, exist_ok=True)
    name_lower = name.lower()
    p = docs_agents_dir / f"{name_lower}.md"
    p.write_text(
        f'{{% include-markdown "../../agents/{name}.md" start="<!-- mkdocs-include-start -->" %}}\n',
        encoding="utf-8",
    )
    return p


def make_command_file(tmp_path: Path, name: str = "bar") -> Path:
    """Write a minimal valid command markdown file to tmp_path/commands/<name>.md.

    Minimal valid structure: frontmatter with description field, the
    mkdocs-include-start marker required by check_commands_docs_alignment,
    plus a 🎀-prefixed 「」 persona-quote line required by
    check_command_persona_quotes (the emoji must precede the quote on the
    same line — a bare 「」 quote with no adjacent persona marker fails).
    Returns the path to the created file.
    """
    cmds_dir = tmp_path / "commands"
    cmds_dir.mkdir(exist_ok=True)
    p = cmds_dir / f"{name}.md"
    p.write_text(
        f"---\ndescription: test command\n---\n\n<!-- mkdocs-include-start -->\n\n"
        f"# {name}\n\n🎀 愛音：「測試台詞。」\n",
        encoding="utf-8",
    )
    return p


def make_docs_command_shim(tmp_path: Path, name: str = "bar") -> Path:
    """Write a minimal valid docs/commands shim to tmp_path/docs/commands/<name>.md.

    Minimal valid structure: an include-markdown directive pointing at
    commands/<name>.md with the mkdocs-include-start marker, required by
    check_commands_docs_alignment.
    Returns the path to the created file.
    """
    docs_cmds_dir = tmp_path / "docs" / "commands"
    docs_cmds_dir.mkdir(parents=True, exist_ok=True)
    p = docs_cmds_dir / f"{name}.md"
    p.write_text(
        f'{{% include-markdown "../../commands/{name}.md" start="<!-- mkdocs-include-start -->" %}}\n',
        encoding="utf-8",
    )
    return p


def make_command_overviews(
    tmp_path: Path, command_names: list[str] | None = None
) -> None:
    """Write minimal README.md and docs/index.md command overview sections."""
    command_names = command_names or ["bar"]
    command_list = "、".join(f"`/maigo:{name}`" for name in command_names)
    content = f"完整 {len(command_names)} 個命令（含 {command_list}）。\n"
    (tmp_path / "README.md").write_text(content, encoding="utf-8")
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(exist_ok=True)
    (docs_dir / "index.md").write_text(content, encoding="utf-8")


def make_skill(tmp_path: Path, name: str = "baz") -> Path:
    """Write a minimal valid skill directory to tmp_path/skills/<name>/SKILL.md.

    Minimal valid structure: frontmatter with name and description fields,
    plus the `<!-- mkdocs-include-start -->` marker required by
    check_skills_docs_alignment.
    Returns the path to the created SKILL.md file.
    """
    skill_dir = tmp_path / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    p = skill_dir / "SKILL.md"
    p.write_text(
        f"---\nname: {name}\ndescription: test skill\n---\n\n"
        f"<!-- mkdocs-include-start -->\n\n# {name}\n",
        encoding="utf-8",
    )
    return p


def make_docs_skill_shim(tmp_path: Path, name: str = "baz") -> Path:
    """Write a minimal valid docs/skills shim to tmp_path/docs/skills/<name>.md.

    Required by check_skills_docs_alignment.
    Returns the path to the created shim file.
    """
    docs_skills_dir = tmp_path / "docs" / "skills"
    docs_skills_dir.mkdir(parents=True, exist_ok=True)
    p = docs_skills_dir / f"{name}.md"
    p.write_text(
        f'{{% include-markdown "../../skills/{name}/SKILL.md" '
        f'start="<!-- mkdocs-include-start -->" %}}\n',
        encoding="utf-8",
    )
    return p


def make_mkdocs_yml(
    tmp_path: Path,
    skill_names: list[str] | None = None,
    agent_names: list[str] | None = None,
) -> Path:
    """Write a minimal mkdocs.yml referencing the given skill and agent shims.

    Required by check_skills_docs_alignment — each skill must appear in the nav as
    `skills/<name>.md` — and by check_agents_docs_alignment — each agent must appear
    as `agents/<name_lower>.md`.
    """
    skill_names = skill_names or ["baz"]
    agent_names = agent_names or ["foo"]
    skill_lines = "\n".join(f"      - {n}: skills/{n}.md" for n in skill_names)
    agent_lines = "\n".join(f"      - {n}: agents/{n.lower()}.md" for n in agent_names)
    p = tmp_path / "mkdocs.yml"
    p.write_text(
        f"site_name: test\nnav:\n  - Skills (source):\n{skill_lines}\n"
        f"  - Agents (source):\n{agent_lines}\n",
        encoding="utf-8",
    )
    return p


def make_skills_catalog(tmp_path: Path, skill_names: list[str] | None = None) -> Path:
    """Write a minimal docs/reference/skills.md catalog referencing the skills.

    Required by check_skills_docs_alignment — each skill must appear in the
    catalog as a backticked name `<name>` — and by check_skills_graph — each
    skill must appear as a node in the mermaid dependency graph.
    """
    skill_names = skill_names or ["baz"]
    rows = "\n".join(f"| `{n}` | — | — |" for n in skill_names)
    nodes = "\n".join(f'    {n.replace("-", "_")}["{n}"]' for n in skill_names)
    docs_ref_dir = tmp_path / "docs" / "reference"
    docs_ref_dir.mkdir(parents=True, exist_ok=True)
    p = docs_ref_dir / "skills.md"
    p.write_text(
        f"# Skills\n\n| Skill | Owner | Consumers |\n|---|---|---|\n{rows}\n"
        f"\n```mermaid\ngraph LR\n{nodes}\n```\n",
        encoding="utf-8",
    )
    return p


def make_agents_model_catalog(
    tmp_path: Path, agent_models: dict[str, str] | None = None
) -> Path:
    """Write a minimal docs/reference/agents.md model-tier table.

    Required by check_agent_model_tier_alignment — each agent must appear as a
    table row `| **<Name>** | <model> | ... |`.
    Returns the path to the created catalog file.
    """
    agent_models = agent_models or {"foo": "sonnet"}
    rows = "\n".join(
        f"| **{name}** | {model} | — |" for name, model in agent_models.items()
    )
    docs_ref_dir = tmp_path / "docs" / "reference"
    docs_ref_dir.mkdir(parents=True, exist_ok=True)
    p = docs_ref_dir / "agents.md"
    p.write_text(
        f"# Agents Reference\n\n| Agent | Model | 為什麼 |\n|---|---|---|\n{rows}\n",
        encoding="utf-8",
    )
    return p


def make_hooks(tmp_path: Path) -> Path:
    """Write a minimal valid hooks/ directory to tmp_path/hooks/.

    Minimal valid structure: hooks.json with a Stop hook entry referencing a
    real hook script (check.py), plus the script itself.
    Returns the path to the hooks directory.
    """
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir(exist_ok=True)
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
    return hooks_dir


@pytest.fixture
def plugin_tree(tmp_path: Path) -> Path:
    """Build a minimal valid plugin tree under tmp_path.

    Composes all make_* helpers to produce a tree that passes validate_plugin.py
    with zero errors. Tests that only need plugin_tree can use this fixture directly;
    tests that need to vary individual components can call the helpers directly.
    """
    make_plugin_json(tmp_path)
    make_agent_file(tmp_path)
    make_docs_agent_shim(tmp_path)
    make_command_file(tmp_path)
    make_docs_command_shim(tmp_path)
    make_command_overviews(tmp_path)
    make_skill(tmp_path)
    make_docs_skill_shim(tmp_path)
    make_mkdocs_yml(tmp_path)
    make_skills_catalog(tmp_path)
    make_hooks(tmp_path)
    return tmp_path
