"""Tests for scripts.validate_memory."""

from __future__ import annotations

from pathlib import Path

import pytest

import scripts.validate_memory as vm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_memory_dir(base: Path, entries: dict[str, str]) -> Path:
    """Create a memory dir with MEMORY.md index and entry files under base.

    entries: mapping of slug (e.g. "foo.md") → file content (or None to skip
    creating the file — simulates a declared-but-missing entry).
    """
    mem_dir = base / "memory"
    mem_dir.mkdir(parents=True, exist_ok=True)

    index_lines = []
    for slug, content in entries.items():
        title = slug.replace(".md", "").replace("-", " ").title()
        index_lines.append(f"- [{title}]({slug}) — description for {slug}")
        if content is not None:
            (mem_dir / slug).write_text(content, encoding="utf-8")

    (mem_dir / "MEMORY.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    return mem_dir


def good_entry(extra: str = "") -> str:
    base = (
        "---\n"
        "name: Test Entry\n"
        "description: A good test entry\n"
        "type: project\n"
    )
    if extra:
        base += extra + "\n"
    base += "---\n\nBody text.\n"
    return base


# ---------------------------------------------------------------------------
# T-1: Good entry with all required fields + extra unknown key → zero warnings
# ---------------------------------------------------------------------------


class TestGoodEntry:
    def test_valid_entry_no_warnings(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """A well-formed entry with name/description/type=project + originSessionId
        must produce zero warnings."""
        content = (
            "---\n"
            "name: Good Entry\n"
            "description: a good entry\n"
            "type: project\n"
            "originSessionId: abc123\n"
            "---\n\nBody.\n"
        )
        mem_dir = make_memory_dir(tmp_path, {"good-entry.md": content})
        result = vm.scan_directory(mem_dir, "Cross-project memory")
        assert not result.has_warnings
        assert result.entry_count == 1


# ---------------------------------------------------------------------------
# T-2: Missing name → warning contains "name"
# ---------------------------------------------------------------------------


class TestMissingName:
    def test_missing_name_warns(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        content = "---\ndescription: no name\ntype: project\n---\n"
        mem_dir = make_memory_dir(tmp_path, {"no-name.md": content})
        result = vm.scan_directory(mem_dir, "Cross-project memory")
        assert result.has_warnings
        assert any("name" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# T-3: Missing description → warning contains "description"
# ---------------------------------------------------------------------------


class TestMissingDescription:
    def test_missing_description_warns(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        content = "---\nname: No Desc\ntype: project\n---\n"
        mem_dir = make_memory_dir(tmp_path, {"no-desc.md": content})
        result = vm.scan_directory(mem_dir, "Cross-project memory")
        assert result.has_warnings
        assert any("description" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# T-4: Missing type → warning contains "type"
# ---------------------------------------------------------------------------


class TestMissingType:
    def test_missing_type_warns(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        content = "---\nname: No Type\ndescription: no type field\n---\n"
        mem_dir = make_memory_dir(tmp_path, {"no-type.md": content})
        result = vm.scan_directory(mem_dir, "Cross-project memory")
        assert result.has_warnings
        assert any("type" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# T-5: Invalid type (old "convention") → warning mentions enum
# ---------------------------------------------------------------------------


class TestInvalidType:
    def test_invalid_type_warns(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        content = (
            "---\nname: Old Entry\ndescription: uses old type\ntype: convention\n---\n"
        )
        mem_dir = make_memory_dir(tmp_path, {"old-type.md": content})
        result = vm.scan_directory(mem_dir, "Cross-project memory")
        assert result.has_warnings
        # should mention the invalid value or the enum set
        assert any("convention" in w or "not in" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# T-6: Empty frontmatter (---\n---\n) → treated as malformed by parser
#
# Note: parse_frontmatter uses text.find("\n---\n", 4) so "---\n---\n" has
# the closing fence at index 3, which is before the search start (index 4).
# This causes parse_frontmatter to return None, meaning empty frontmatter is
# treated as "missing or malformed" — not three separate field warnings.
# This is accepted v0 behaviour (lenient parser).
# ---------------------------------------------------------------------------


class TestEmptyFrontmatter:
    def test_empty_frontmatter_warns_malformed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        content = "---\n---\n\nSome body.\n"
        mem_dir = make_memory_dir(tmp_path, {"empty-fm.md": content})
        result = vm.scan_directory(mem_dir, "Cross-project memory")
        assert result.has_warnings
        assert any("missing or malformed" in w for w in result.warnings)

    def test_frontmatter_with_blank_values_warns_fields(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Frontmatter that parses but has empty values → field warnings."""
        content = "---\nname: \ndescription: \ntype: \n---\n\nBody.\n"
        mem_dir = make_memory_dir(tmp_path, {"blank-values.md": content})
        result = vm.scan_directory(mem_dir, "Cross-project memory")
        assert result.has_warnings
        warning_text = " ".join(result.warnings)
        assert "name" in warning_text
        assert "description" in warning_text
        assert "type" in warning_text


# ---------------------------------------------------------------------------
# T-7: No frontmatter (pure markdown body) → warning "missing or malformed"
# ---------------------------------------------------------------------------


class TestNoFrontmatter:
    def test_no_frontmatter_warns(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        content = "# Just a heading\n\nNo frontmatter here.\n"
        mem_dir = make_memory_dir(tmp_path, {"no-fm.md": content})
        result = vm.scan_directory(mem_dir, "Cross-project memory")
        assert result.has_warnings
        assert any("missing or malformed" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# T-8: MEMORY.md declares slug but file missing → missing-file warning
# ---------------------------------------------------------------------------


class TestMissingFile:
    def test_declared_but_missing_warns(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        # Pass None for content → file won't be created
        mem_dir = make_memory_dir(tmp_path, {"ghost-entry.md": None})
        result = vm.scan_directory(mem_dir, "Cross-project memory")
        assert result.has_warnings
        assert any("not found" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# T-9a: Cross-project dir completely absent → no raise, no warnings
# T-9b: Project-specific dir completely absent → no raise, no warnings
# ---------------------------------------------------------------------------


class TestMissingDirectory:
    def test_absent_cross_project_dir(self, tmp_path: Path):
        non_existent = tmp_path / "does-not-exist" / "memory"
        result = vm.scan_directory(non_existent, "Cross-project memory")
        assert not result.has_warnings
        assert result.entry_count == 0

    def test_absent_project_specific_dir(self, tmp_path: Path):
        non_existent = tmp_path / "projects" / "my-proj" / "memory"
        result = vm.scan_directory(non_existent, "Project memory (my-proj)")
        assert not result.has_warnings
        assert result.entry_count == 0


# ---------------------------------------------------------------------------
# T-10: Unknown keys (originSessionId, triggers) → no warnings
# ---------------------------------------------------------------------------


class TestUnknownKeys:
    def test_unknown_keys_not_warned(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        content = (
            "---\n"
            "name: Entry With Extras\n"
            "description: has extra keys\n"
            "type: user\n"
            "originSessionId: sess-xyz\n"
            "triggers: [some-skill]\n"
            "---\n\nBody.\n"
        )
        mem_dir = make_memory_dir(tmp_path, {"extras.md": content})
        result = vm.scan_directory(mem_dir, "Cross-project memory")
        assert not result.has_warnings


# ---------------------------------------------------------------------------
# T-11: --strict flag: warnings → exit 1; no warnings → exit 0
# ---------------------------------------------------------------------------


class TestStrictFlag:
    def test_strict_with_warnings_exits_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """--strict should return exit code 1 when there are warnings."""
        content = "---\ndescription: no name\ntype: project\n---\n"
        mem_dir = make_memory_dir(tmp_path, {"bad.md": content})

        # Patch discover_directories to return only our tmp dir
        monkeypatch.setattr(
            vm,
            "discover_directories",
            lambda: [(mem_dir, "Cross-project memory")],
        )
        exit_code = vm.main(["--strict"])
        assert exit_code == 1

    def test_strict_no_warnings_exits_0(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """--strict should return exit code 0 when there are no warnings."""
        content = good_entry()
        mem_dir = make_memory_dir(tmp_path, {"good.md": content})

        monkeypatch.setattr(
            vm,
            "discover_directories",
            lambda: [(mem_dir, "Cross-project memory")],
        )
        exit_code = vm.main(["--strict"])
        assert exit_code == 0

    def test_default_with_warnings_exits_0(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Default mode (no --strict) should always exit 0 even with warnings."""
        content = "---\ndescription: no name\ntype: project\n---\n"
        mem_dir = make_memory_dir(tmp_path, {"bad.md": content})

        monkeypatch.setattr(
            vm,
            "discover_directories",
            lambda: [(mem_dir, "Cross-project memory")],
        )
        exit_code = vm.main([])
        assert exit_code == 0


# ---------------------------------------------------------------------------
# T-12: All valid VALID_TYPES pass without type warning
# ---------------------------------------------------------------------------


class TestValidTypes:
    @pytest.mark.parametrize("type_val", ["user", "feedback", "project", "reference"])
    def test_all_valid_types_pass(self, tmp_path: Path, type_val: str):
        content = f"---\nname: Entry\ndescription: test\ntype: {type_val}\n---\n"
        mem_dir = make_memory_dir(tmp_path, {"entry.md": content})
        result = vm.scan_directory(mem_dir, "Cross-project memory")
        # Should not have any type-related warning
        type_warns = [w for w in result.warnings if "type" in w and "not in" in w]
        assert not type_warns


# ---------------------------------------------------------------------------
# T-13: discover_directories scans both cross-project and project-specific
# ---------------------------------------------------------------------------


class TestDiscoverDirectories:
    def test_discovers_cross_project_and_project_specific(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """discover_directories should include both sources."""
        # Set up fake home
        fake_home = tmp_path / "home"
        fake_home.mkdir()

        # cross-project memory
        cross_mem = fake_home / ".config" / "maigo" / "memory"
        cross_mem.mkdir(parents=True)
        (cross_mem / "MEMORY.md").write_text(
            "- [Entry](entry.md) — desc\n", encoding="utf-8"
        )
        (cross_mem / "entry.md").write_text(good_entry(), encoding="utf-8")

        # project-specific memory
        proj_mem = fake_home / ".claude" / "projects" / "-Users-foo-myrepo" / "memory"
        proj_mem.mkdir(parents=True)
        (proj_mem / "MEMORY.md").write_text(
            "- [Proj Entry](proj-entry.md) — desc\n", encoding="utf-8"
        )
        (proj_mem / "proj-entry.md").write_text(good_entry(), encoding="utf-8")

        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

        dirs = vm.discover_directories()
        paths = [str(p) for p, _ in dirs]

        assert str(cross_mem) in paths
        assert str(proj_mem) in paths
