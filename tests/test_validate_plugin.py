"""Tests for scripts.validate_plugin."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.validate_plugin as validate_plugin
from tests.conftest import (
    make_command_file,
    make_command_overviews,
    make_docs_skill_shim,
    make_mkdocs_yml,
    make_skill,
    make_skills_catalog,
)


def _plugin_json_path(tmp_path: Path) -> Path:
    """Return the canonical .claude-plugin/plugin.json path, ensuring its parent exists."""
    d = tmp_path / ".claude-plugin"
    d.mkdir(parents=True, exist_ok=True)
    return d / "plugin.json"


# ---------------------------------------------------------------------------
# parse_frontmatter
# ---------------------------------------------------------------------------


class TestParseFrontmatter:
    def test_no_opening_fence_returns_none(self):
        assert validate_plugin.parse_frontmatter("name: foo\n") is None

    def test_opening_fence_no_closing_returns_none(self):
        assert validate_plugin.parse_frontmatter("---\nname: foo\n") is None

    def test_normal_key_value_dict(self):
        text = "---\nname: foo\ndescription: bar baz\n---\n"
        result = validate_plugin.parse_frontmatter(text)
        assert result == {"name": "foo", "description": "bar baz"}

    def test_indent_lines_skipped(self):
        text = "---\nname: foo\n  indented: line\n---\n"
        result = validate_plugin.parse_frontmatter(text)
        assert "indented" not in result
        assert result["name"] == "foo"

    def test_no_colon_lines_skipped(self):
        text = "---\nname: foo\nno colon here\n---\n"
        result = validate_plugin.parse_frontmatter(text)
        assert result == {"name": "foo"}


# ---------------------------------------------------------------------------
# check_plugin_json
# ---------------------------------------------------------------------------


class TestCheckPluginJson:
    def test_file_not_exists(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_plugin_json()
        assert not result.passed
        assert any("不存在" in e for e in result.errors)

    def test_bad_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        _plugin_json_path(tmp_path).write_text("{not valid json", encoding="utf-8")
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_plugin_json()
        assert not result.passed
        assert any("JSON 解析失敗" in e for e in result.errors)

    def test_missing_version_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        data = {"name": "test", "description": "d", "license": "MIT"}
        _plugin_json_path(tmp_path).write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_plugin_json()
        assert not result.passed
        assert any("version" in e for e in result.errors)

    def test_all_fields_passes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        data = {"name": "test", "version": "1.0", "description": "d", "license": "MIT"}
        _plugin_json_path(tmp_path).write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_plugin_json()
        assert result.passed

    def test_author_as_string_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        data = {
            "name": "test",
            "version": "1.0",
            "description": "d",
            "license": "MIT",
            "author": "Wei Lee",  # invalid — must be object
        }
        _plugin_json_path(tmp_path).write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_plugin_json()
        assert not result.passed
        assert any("author" in e and "object" in e for e in result.errors)

    def test_author_object_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        data = {
            "name": "test",
            "version": "1.0",
            "description": "d",
            "license": "MIT",
            "author": {"name": "Wei Lee"},
        }
        _plugin_json_path(tmp_path).write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_plugin_json()
        assert result.passed

    def test_author_object_missing_name_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        data = {
            "name": "test",
            "version": "1.0",
            "description": "d",
            "license": "MIT",
            "author": {"email": "x@y.com"},  # missing required name
        }
        _plugin_json_path(tmp_path).write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_plugin_json()
        assert not result.passed
        assert any("author.name" in e for e in result.errors)


# ---------------------------------------------------------------------------
# check_agent_frontmatter
# ---------------------------------------------------------------------------


class TestCheckAgentFrontmatter:
    def test_agents_dir_not_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_agent_frontmatter()
        assert not result.passed
        assert any("不存在" in e for e in result.errors)

    def test_name_mismatch_fails(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        agents = tmp_path / "agents"
        agents.mkdir()
        (agents / "foo.md").write_text(
            "---\nname: bar\ndescription: d\nmodel: sonnet\ntools: [Read]\n---\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_agent_frontmatter()
        assert not result.passed
        assert any("bar" in e for e in result.errors)

    def test_missing_tools_fails(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        agents = tmp_path / "agents"
        agents.mkdir()
        (agents / "foo.md").write_text(
            "---\nname: foo\ndescription: d\nmodel: sonnet\n---\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_agent_frontmatter()
        assert not result.passed
        assert any("tools" in e for e in result.errors)

    def test_valid_agent_passes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        agents = tmp_path / "agents"
        agents.mkdir()
        (agents / "foo.md").write_text(
            "---\nname: foo\ndescription: d\nmodel: sonnet\ntools: [Read]\n---\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_agent_frontmatter()
        assert result.passed


# ---------------------------------------------------------------------------
# check_hook_scripts
# ---------------------------------------------------------------------------


class TestCheckHookScripts:
    def _make_hooks_json(self, tmp_path: Path, script_path: str) -> None:
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir(exist_ok=True)
        data = {
            "hooks": {
                "Stop": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": f"python3 ${{CLAUDE_PLUGIN_ROOT}}/{script_path}",
                            }
                        ]
                    }
                ]
            }
        }
        (hooks_dir / "hooks.json").write_text(json.dumps(data), encoding="utf-8")

    def test_script_not_exists_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        self._make_hooks_json(tmp_path, "hooks/missing.py")
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_hook_scripts()
        assert not result.passed
        assert any("不存在" in e for e in result.errors)

    def test_python_syntax_error_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir(exist_ok=True)
        broken_py = hooks_dir / "broken.py"
        broken_py.write_text("def foo(\n", encoding="utf-8")
        self._make_hooks_json(tmp_path, "hooks/broken.py")
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_hook_scripts()
        assert not result.passed
        assert any("語法錯" in e for e in result.errors)

    def test_valid_script_passes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir(exist_ok=True)
        good_py = hooks_dir / "good.py"
        good_py.write_text("print('hello')\n", encoding="utf-8")
        self._make_hooks_json(tmp_path, "hooks/good.py")
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_hook_scripts()
        assert result.passed


# ---------------------------------------------------------------------------
# check_hooks_schema
# ---------------------------------------------------------------------------


class TestCheckHooksSchema:
    def _write_hooks_json(self, tmp_path: Path, data: dict) -> None:
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir(exist_ok=True)
        (hooks_dir / "hooks.json").write_text(json.dumps(data), encoding="utf-8")

    def test_valid_schema_passes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        self._write_hooks_json(
            tmp_path,
            {
                "hooks": {
                    "Stop": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/check.py",
                                    "timeout": 30,
                                }
                            ]
                        }
                    ]
                }
            },
        )
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_hooks_schema()
        assert result.passed

    def test_unknown_event_fails(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        self._write_hooks_json(
            tmp_path,
            {
                "hooks": {
                    "TypoEvent": [
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
            },
        )
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_hooks_schema()
        assert not result.passed
        assert any("TypoEvent" in e for e in result.errors)

    def test_non_command_type_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        self._write_hooks_json(
            tmp_path,
            {
                "hooks": {
                    "Stop": [
                        {
                            "hooks": [
                                {
                                    "type": "prompt",
                                    "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/check.py",
                                }
                            ]
                        }
                    ]
                }
            },
        )
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_hooks_schema()
        assert not result.passed
        assert any("type" in e and "command" in e for e in result.errors)

    def test_missing_plugin_root_placeholder_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        self._write_hooks_json(
            tmp_path,
            {
                "hooks": {
                    "Stop": [
                        {
                            "hooks": [
                                {"type": "command", "command": "python3 hooks/check.py"}
                            ]
                        }
                    ]
                }
            },
        )
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_hooks_schema()
        assert not result.passed
        assert any("CLAUDE_PLUGIN_ROOT" in e for e in result.errors)


# ---------------------------------------------------------------------------
# check_skill_crossrefs
# ---------------------------------------------------------------------------


class TestCheckSkillCrossrefs:
    def test_missing_skill_reference_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "foo.md").write_text(
            "Use skills/missing-skill for this task.\n",
            encoding="utf-8",
        )
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        # "missing-skill" dir does NOT exist
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_skill_crossrefs()
        assert not result.passed
        assert any("missing-skill" in e for e in result.errors)

    def test_existing_skill_reference_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "foo.md").write_text(
            "Use skills/existing-skill for this task.\n",
            encoding="utf-8",
        )
        skills_dir = tmp_path / "skills"
        (skills_dir / "existing-skill").mkdir(parents=True)
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_skill_crossrefs()
        assert result.passed


# ---------------------------------------------------------------------------
# check_plugin_json — empty JSON reports all missing fields (S-1)
# ---------------------------------------------------------------------------


class TestCheckPluginJsonAllMissing:
    def test_empty_plugin_json_reports_all_missing_fields(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        _plugin_json_path(tmp_path).write_text("{}", encoding="utf-8")
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_plugin_json()
        assert not result.passed
        required = {"name", "version", "description", "license"}
        reported = {e.split("`")[1] for e in result.errors if "`" in e}
        assert required == reported


# ---------------------------------------------------------------------------
# check_version_sync — plugin.json ↔ pyproject.toml
# ---------------------------------------------------------------------------


class TestCheckVersionSync:
    def _write(
        self, tmp_path: Path, plugin_ver: str | None, pyproject_ver: str | None
    ) -> None:
        if plugin_ver is not None:
            _plugin_json_path(tmp_path).write_text(
                json.dumps({"version": plugin_ver}), encoding="utf-8"
            )
        if pyproject_ver is not None:
            (tmp_path / "pyproject.toml").write_text(
                f'[project]\nname = "x"\nversion = "{pyproject_ver}"\n',
                encoding="utf-8",
            )

    def test_versions_match_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        self._write(tmp_path, "1.2.3", "1.2.3")
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_version_sync()
        assert result.passed

    def test_versions_differ_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        self._write(tmp_path, "1.2.3", "1.2.4")
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_version_sync()
        assert not result.passed
        assert "1.2.3" in str(result.errors)
        assert "1.2.4" in str(result.errors)

    def test_missing_pyproject_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        self._write(tmp_path, "1.2.3", None)
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_version_sync()
        assert result.passed
        assert any("跳過" in n for n in result.notes)


# ---------------------------------------------------------------------------
# check_skills_docs_alignment — 4-way check (SKILL marker / shim / mkdocs / catalog)
# ---------------------------------------------------------------------------


class TestCheckSkillsDocsAlignment:
    def test_skills_dir_missing_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_skills_docs_alignment()
        assert result.passed
        assert any("不存在" in n for n in result.notes)

    def test_all_four_components_present_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        make_skill(tmp_path, "foo")
        make_docs_skill_shim(tmp_path, "foo")
        make_mkdocs_yml(tmp_path, ["foo"])
        make_skills_catalog(tmp_path, ["foo"])
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_skills_docs_alignment()
        assert result.passed

    def test_missing_mkdocs_marker_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        skill_dir = tmp_path / "skills" / "foo"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: foo\ndescription: d\n---\n\n# foo\n",  # no marker
            encoding="utf-8",
        )
        make_docs_skill_shim(tmp_path, "foo")
        make_mkdocs_yml(tmp_path, ["foo"])
        make_skills_catalog(tmp_path, ["foo"])
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_skills_docs_alignment()
        assert not result.passed
        assert any("mkdocs-include-start" in e for e in result.errors)

    def test_missing_docs_shim_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        make_skill(tmp_path, "foo")
        # no shim
        make_mkdocs_yml(tmp_path, ["foo"])
        make_skills_catalog(tmp_path, ["foo"])
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_skills_docs_alignment()
        assert not result.passed
        assert any("docs/skills/foo.md" in e for e in result.errors)

    def test_missing_mkdocs_nav_entry_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        make_skill(tmp_path, "foo")
        make_docs_skill_shim(tmp_path, "foo")
        make_mkdocs_yml(tmp_path, ["other-skill"])  # foo not in nav
        make_skills_catalog(tmp_path, ["foo"])
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_skills_docs_alignment()
        assert not result.passed
        assert any("mkdocs.yml" in e for e in result.errors)

    def test_missing_catalog_row_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        make_skill(tmp_path, "foo")
        make_docs_skill_shim(tmp_path, "foo")
        make_mkdocs_yml(tmp_path, ["foo"])
        make_skills_catalog(tmp_path, ["other-skill"])  # foo not in catalog
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_skills_docs_alignment()
        assert not result.passed
        assert any("catalog" in e for e in result.errors)


# ---------------------------------------------------------------------------
# check_command_overview_coverage
# ---------------------------------------------------------------------------


class TestCheckCommandOverviewCoverage:
    def test_all_commands_mentioned_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        make_command_file(tmp_path, "go")
        make_command_file(tmp_path, "review")
        make_command_overviews(tmp_path, ["go", "review"])
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_command_overview_coverage()
        assert result.passed

    def test_missing_command_slug_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        make_command_file(tmp_path, "go")
        make_command_file(tmp_path, "review")
        make_command_overviews(tmp_path, ["go"])
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_command_overview_coverage()
        assert not result.passed
        assert any("/maigo:review" in e for e in result.errors)


# ---------------------------------------------------------------------------
# check_skills_graph
# ---------------------------------------------------------------------------


class TestCheckSkillsGraph:
    def test_all_skills_in_graph_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        make_skill(tmp_path, "foo")
        make_skills_catalog(tmp_path, ["foo"])
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_skills_graph()
        assert result.passed

    def test_missing_skill_node_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        make_skill(tmp_path, "foo")
        make_skills_catalog(tmp_path, ["other-skill"])  # foo not in graph
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_skills_graph()
        assert not result.passed
        assert any("foo" in e for e in result.errors)

    def test_no_mermaid_block_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        make_skill(tmp_path, "foo")
        docs_ref_dir = tmp_path / "docs" / "reference"
        docs_ref_dir.mkdir(parents=True, exist_ok=True)
        (docs_ref_dir / "skills.md").write_text(
            "# Skills\n\n| Skill |\n|---|\n| `foo` |\n", encoding="utf-8"
        )
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_skills_graph()
        assert not result.passed
        assert any("mermaid" in e for e in result.errors)

    def test_missing_page_is_note_not_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        make_skill(tmp_path, "foo")  # no docs/reference/skills.md at all
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_skills_graph()
        assert result.passed
        assert result.notes


class TestCheckRelativeLinks:
    def _make_md(self, tmp_path: Path, subpath: str, content: str) -> Path:
        p = tmp_path / subpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def test_existing_relative_link_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        self._make_md(tmp_path, "docs/foo.md", "hello")
        self._make_md(tmp_path, "docs/index.md", "[Foo](foo.md)\n")
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_relative_links()
        assert result.passed

    def test_nonexistent_relative_link_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        self._make_md(tmp_path, "docs/index.md", "[Missing](missing.md)\n")
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_relative_links()
        assert not result.passed
        assert any("missing.md" in e for e in result.errors)

    @pytest.mark.parametrize(
        "link_content",
        [
            pytest.param("[Foo](<path/to/file.md>)\n", id="placeholder-angle-bracket"),
            pytest.param("[Foo](*.md)\n", id="placeholder-glob-star"),
            pytest.param("[Foo](...)\n", id="placeholder-ellipsis"),
            pytest.param("[Foo](https://example.com/foo.md)\n", id="http"),
            pytest.param("[Foo](#section)\n", id="anchor-only"),
            pytest.param("[Email](mailto:foo@example.com)\n", id="mailto"),
            pytest.param("[Foo](/docs/foo.md)\n", id="absolute-path"),
        ],
    )
    def test_skip_cases_pass(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, link_content: str
    ):
        self._make_md(tmp_path, "docs/index.md", link_content)
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_relative_links()
        assert result.passed

    def test_anchor_suffix_stripped_existing_file_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        self._make_md(tmp_path, "docs/foo.md", "# Section\nhello")
        self._make_md(tmp_path, "docs/index.md", "[Foo](foo.md#section)\n")
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_relative_links()
        assert result.passed

    def test_link_in_fenced_code_block_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        content = "```\n[Missing](missing.md)\n```\n"
        self._make_md(tmp_path, "docs/index.md", content)
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_relative_links()
        assert result.passed

    def test_link_in_inline_code_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        content = "See `[Title](missing.md)` for details.\n"
        self._make_md(tmp_path, "docs/index.md", content)
        monkeypatch.setattr(validate_plugin, "ROOT", tmp_path)
        result = validate_plugin.check_relative_links()
        assert result.passed


# ---------------------------------------------------------------------------
# main() happy-path integration (M-1)
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_all_checks_pass(
        self, plugin_tree: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(validate_plugin, "ROOT", plugin_tree)
        exit_code = validate_plugin.main()
        assert exit_code == 0
