"""Tests for scripts.validate_frontmatter."""

from __future__ import annotations

from pathlib import Path

import pytest

import scripts.validate_frontmatter as vf
from tests.conftest import make_agent_file, make_command_file, make_skill


class TestCheckFile:
    def test_valid_agent_passes(self, tmp_path: Path):
        path = make_agent_file(tmp_path, "foo")
        errors = vf.check_file(path, vf.AGENT_REQUIRED, expected_name="foo")
        assert errors == []

    def test_missing_frontmatter(self, tmp_path: Path):
        p = tmp_path / "bad.md"
        p.write_text("# no frontmatter\n", encoding="utf-8")
        errors = vf.check_file(p, vf.AGENT_REQUIRED)
        assert any("frontmatter" in e for e in errors)

    def test_missing_required_field(self, tmp_path: Path):
        p = tmp_path / "missing.md"
        p.write_text(
            "---\nname: missing\ndescription: d\nmodel: sonnet\n---\n", encoding="utf-8"
        )
        errors = vf.check_file(p, vf.AGENT_REQUIRED)
        assert any("tools" in e for e in errors)

    def test_empty_field(self, tmp_path: Path):
        p = tmp_path / "empty.md"
        p.write_text(
            "---\nname: empty\ndescription: \nmodel: sonnet\ntools: [Read]\n---\n",
            encoding="utf-8",
        )
        errors = vf.check_file(p, vf.AGENT_REQUIRED)
        assert any("description" in e for e in errors)

    def test_name_mismatch(self, tmp_path: Path):
        p = tmp_path / "real.md"
        p.write_text(
            "---\nname: wrong\ndescription: d\nmodel: sonnet\ntools: [Read]\n---\n",
            encoding="utf-8",
        )
        errors = vf.check_file(p, vf.AGENT_REQUIRED, expected_name="real")
        assert any("wrong" in e for e in errors)

    def test_valid_skill_passes(self, tmp_path: Path):
        skill_file = make_skill(tmp_path, "my-skill")
        errors = vf.check_file(skill_file, vf.SKILL_REQUIRED, expected_name="my-skill")
        assert errors == []


class TestMain:
    def test_clean_tree_returns_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        make_agent_file(tmp_path, "foo")
        make_command_file(tmp_path, "bar")
        make_skill(tmp_path, "baz")
        monkeypatch.setattr(vf, "ROOT", tmp_path)
        assert vf.main() == 0

    def test_broken_agent_returns_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        p = tmp_path / "agents"
        p.mkdir()
        (p / "bad.md").write_text("# no frontmatter\n", encoding="utf-8")
        monkeypatch.setattr(vf, "ROOT", tmp_path)
        assert vf.main() == 1

    def test_broken_skill_frontmatter_returns_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        skill_dir = tmp_path / "skills" / "broken"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: broken\n---\n", encoding="utf-8"
        )
        monkeypatch.setattr(vf, "ROOT", tmp_path)
        assert vf.main() == 1
