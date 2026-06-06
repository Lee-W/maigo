"""Tests for scripts.validate_plugin."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.validate_plugin as validate_plugin
from tests.conftest import (
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
# main() happy-path integration (M-1)
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_all_checks_pass(
        self, plugin_tree: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(validate_plugin, "ROOT", plugin_tree)
        exit_code = validate_plugin.main()
        assert exit_code == 0
