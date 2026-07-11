from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODEX_MANIFEST = ROOT / ".codex-plugin" / "plugin.json"
CODEX_MARKETPLACE = ROOT / ".agents" / "plugins" / "marketplace.json"
ROUTER = ROOT / "skills" / "command-router" / "SKILL.md"


def test_codex_manifest_is_valid_and_matches_project_version() -> None:
    manifest = json.loads(CODEX_MANIFEST.read_text(encoding="utf-8"))
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert manifest["name"] == "maigo"
    assert (
        manifest["version"].split("+", maxsplit=1)[0] == project["project"]["version"]
    )
    assert re.fullmatch(
        r"\d+\.\d+\.\d+(?:\+codex\.[0-9A-Za-z.-]+)?", manifest["version"]
    )
    assert manifest["skills"] == "./skills/"
    assert manifest["author"]["name"]

    interface = manifest["interface"]
    for key in (
        "displayName",
        "shortDescription",
        "longDescription",
        "developerName",
        "category",
    ):
        assert interface[key]
    assert 1 <= len(interface["defaultPrompt"]) <= 3
    assert all(len(prompt) <= 128 for prompt in interface["defaultPrompt"])


def test_codex_router_dispatches_every_command() -> None:
    router = ROUTER.read_text(encoding="utf-8")
    commands = sorted((ROOT / "commands").glob("*.md"))

    assert commands
    for command in commands:
        assert f"commands/{command.name}" in router


def test_codex_marketplace_points_to_plugin_root() -> None:
    marketplace = json.loads(CODEX_MARKETPLACE.read_text(encoding="utf-8"))

    assert marketplace["name"] == "maigo"
    assert marketplace["interface"]["displayName"] == "Maigo"
    assert len(marketplace["plugins"]) == 1

    plugin = marketplace["plugins"][0]
    assert plugin["name"] == "maigo"
    assert plugin["source"] == {"source": "local", "path": "."}
    assert plugin["policy"] == {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL",
    }
    assert plugin["category"] == "Developer Tools"


def test_codex_router_has_no_scaffold_placeholders() -> None:
    assert "TODO" not in ROUTER.read_text(encoding="utf-8")
