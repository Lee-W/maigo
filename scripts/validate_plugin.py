#!/usr/bin/env python3
"""Comprehensive structural check for the Maigo plugin.

Runs ~8 checks covering plugin.json / hooks.json / agent / command / skill
frontmatter, hook script existence + syntax, pre-commit config sanity,
and skill cross-references.

跑：`python3 scripts/validate_plugin.py`
Exit 0 = 全綠；Exit 1 = 至少一項失敗。

跟 `scripts/validate_frontmatter.py` 的差別：
- validate_frontmatter — 快、窄、給 pre-commit 用
- validate_plugin     — 全面、慢一點、給 first-time install / 升版本前用
"""

from __future__ import annotations

import ast
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _frontmatter import parse_frontmatter  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class CheckResult:
    def __init__(self, name: str) -> None:
        self.name = name
        self.errors: list[str] = []
        self.notes: list[str] = []

    def fail(self, msg: str) -> None:
        self.errors.append(msg)

    def note(self, msg: str) -> None:
        self.notes.append(msg)

    @property
    def passed(self) -> bool:
        return not self.errors


def check_plugin_json() -> CheckResult:
    r = CheckResult("plugin.json")
    path = ROOT / "plugin.json"
    if not path.is_file():
        r.fail("檔案不存在")
        return r
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        r.fail(f"JSON 解析失敗：{e}")
        return r
    for key in ("name", "version", "description", "license"):
        if not data.get(key):
            r.fail(f"缺欄位 `{key}`")
    return r


def check_hooks_json() -> CheckResult:
    r = CheckResult("hooks/hooks.json")
    path = ROOT / "hooks" / "hooks.json"
    if not path.is_file():
        r.note("hooks/hooks.json 不存在（plugin 沒掛任何 hook）")
        return r
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        r.fail(f"JSON 解析失敗：{e}")
    return r


def check_agent_frontmatter() -> CheckResult:
    r = CheckResult("agents/*.md frontmatter")
    agents_dir = ROOT / "agents"
    if not agents_dir.is_dir():
        r.fail("agents/ 目錄不存在")
        return r
    required = {"name", "description", "model", "tools"}
    count = 0
    for path in sorted(agents_dir.glob("*.md")):
        count += 1
        fm = parse_frontmatter(path.read_text(encoding="utf-8"))
        rel = path.relative_to(ROOT)
        if fm is None:
            r.fail(f"{rel}: frontmatter 缺或損壞")
            continue
        missing = required - fm.keys()
        if missing:
            r.fail(f"{rel}: 缺欄位 {sorted(missing)}")
        if "name" in fm and fm["name"] != path.stem:
            r.fail(f"{rel}: name `{fm['name']}` ≠ 檔名 `{path.stem}`")
    if count == 0:
        r.note("agents/ 是空的")
    return r


def check_command_frontmatter() -> CheckResult:
    r = CheckResult("commands/*.md frontmatter")
    cmds_dir = ROOT / "commands"
    if not cmds_dir.is_dir():
        r.note("commands/ 目錄不存在")
        return r
    for path in sorted(cmds_dir.glob("*.md")):
        fm = parse_frontmatter(path.read_text(encoding="utf-8"))
        rel = path.relative_to(ROOT)
        if fm is None:
            r.fail(f"{rel}: frontmatter 缺或損壞")
            continue
        if not fm.get("description"):
            r.fail(f"{rel}: 缺 description")
    return r


def check_skill_frontmatter() -> CheckResult:
    r = CheckResult("skills/*/SKILL.md frontmatter")
    skills_dir = ROOT / "skills"
    if not skills_dir.is_dir():
        r.note("skills/ 目錄不存在")
        return r
    for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        skill_file = skill_dir / "SKILL.md"
        rel_dir = skill_dir.relative_to(ROOT)
        if not skill_file.is_file():
            r.fail(f"{rel_dir}: SKILL.md 缺")
            continue
        fm = parse_frontmatter(skill_file.read_text(encoding="utf-8"))
        rel = skill_file.relative_to(ROOT)
        if fm is None:
            r.fail(f"{rel}: frontmatter 缺或損壞")
            continue
        if not fm.get("name"):
            r.fail(f"{rel}: 缺 name")
        elif fm["name"] != skill_dir.name:
            r.fail(f"{rel}: name `{fm['name']}` ≠ 目錄名 `{skill_dir.name}`")
        if not fm.get("description"):
            r.fail(f"{rel}: 缺 description")
    return r


def check_hook_scripts() -> CheckResult:
    r = CheckResult("hooks.json 指向的 script 存在 + 語法正確 + 可執行")
    hooks_json = ROOT / "hooks" / "hooks.json"
    if not hooks_json.is_file():
        r.note("hooks.json 不存在，跳過")
        return r
    try:
        data = json.loads(hooks_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        r.fail("hooks.json JSON 壞掉，跳過子檢查")
        return r

    placeholder_re = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/(\S+)")

    for event, configs in (data.get("hooks") or {}).items():
        for cfg in configs:
            for hook in cfg.get("hooks") or []:
                cmd_str = hook.get("command", "")
                m = placeholder_re.search(cmd_str)
                if not m:
                    continue
                rel = m.group(1)
                script = ROOT / rel
                if not script.is_file():
                    r.fail(f"{event}: 指向 `{rel}` 但檔案不存在")
                    continue
                if script.suffix == ".py":
                    try:
                        ast.parse(script.read_text(encoding="utf-8"))
                    except SyntaxError as e:
                        r.fail(f"{rel}: Python 語法錯 ({e.lineno}: {e.msg})")
                elif script.suffix == ".sh":
                    if not (script.stat().st_mode & 0o111):
                        r.fail(f"{rel}: 無 executable bit（chmod +x）")
    return r


def check_pre_commit_config() -> CheckResult:
    r = CheckResult(".pre-commit-config.yaml")
    path = ROOT / ".pre-commit-config.yaml"
    if not path.is_file():
        r.note("不存在，跳過")
        return r
    text = path.read_text(encoding="utf-8")
    if "repos:" not in text:
        r.fail("缺 `repos:` 頂層 key")

    entry_re = re.compile(r"entry:\s*(?:python3?|bash)\s+(\S+)")
    for m in entry_re.finditer(text):
        rel = m.group(1)
        if not (ROOT / rel).is_file():
            r.fail(f"local hook entry 指向 `{rel}` 但檔案不存在")
    return r


def check_skill_crossrefs() -> CheckResult:
    r = CheckResult("agents / commands 引用的 skill 真的存在")
    skills_dir = ROOT / "skills"
    if not skills_dir.is_dir():
        r.note("skills/ 不存在，跳過")
        return r
    available = {p.name for p in skills_dir.iterdir() if p.is_dir()}
    ref_re = re.compile(r"skills/([a-z0-9_-]+)(?:/|\b)")
    for d in ("agents", "commands"):
        target = ROOT / d
        if not target.is_dir():
            continue
        for path in target.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            for m in ref_re.finditer(text):
                skill = m.group(1)
                if skill not in available:
                    r.fail(
                        f"{path.relative_to(ROOT)} 引用了不存在的 skill: skills/{skill}"
                    )
    return r


def check_commands_docs_alignment() -> CheckResult:
    """每個 commands/*.md 必須含 mkdocs-include-start 且有對應 docs/commands/<basename>.md。"""
    r = CheckResult("commands/*.md ↔ docs/commands/ alignment")
    cmds_dir = ROOT / "commands"
    docs_cmds_dir = ROOT / "docs" / "commands"
    if not cmds_dir.is_dir():
        r.note("commands/ 目錄不存在，跳過")
        return r
    for path in sorted(cmds_dir.glob("*.md")):
        rel = path.relative_to(ROOT)
        text = path.read_text(encoding="utf-8")
        if "<!-- mkdocs-include-start -->" not in text:
            r.fail(f"{rel}: 缺 `<!-- mkdocs-include-start -->`")
        shim = docs_cmds_dir / path.name
        if not shim.is_file():
            r.fail(f"{rel}: 缺對應 docs/commands/{path.name}")
    return r


def check_skills_docs_alignment() -> CheckResult:
    """Each skills/<name>/SKILL.md must align with the 6-step publish path.

    Checks the four mechanically-verifiable steps from the new-skill checklist
    (the other two — frontmatter and validate_plugin run — already have their
    own checks above):

    1. SKILL.md contains `<!-- mkdocs-include-start -->`
    2. docs/skills/<name>.md shim exists
    3. mkdocs.yml nav references skills/<name>.md
    4. docs/reference/skills.md catalog has a row for `<name>`
    """
    r = CheckResult("skills/*/SKILL.md ↔ docs/skills/ + mkdocs + catalog alignment")
    skills_dir = ROOT / "skills"
    docs_skills_dir = ROOT / "docs" / "skills"
    if not skills_dir.is_dir():
        r.note("skills/ 目錄不存在，跳過")
        return r
    mkdocs_text = ""
    mkdocs_path = ROOT / "mkdocs.yml"
    if mkdocs_path.is_file():
        mkdocs_text = mkdocs_path.read_text(encoding="utf-8")
    catalog_text = ""
    catalog_path = ROOT / "docs" / "reference" / "skills.md"
    if catalog_path.is_file():
        catalog_text = catalog_path.read_text(encoding="utf-8")

    for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        name = skill_dir.name
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            continue  # check_skill_frontmatter already flags this
        text = skill_file.read_text(encoding="utf-8")
        if "<!-- mkdocs-include-start -->" not in text:
            r.fail(f"skills/{name}/SKILL.md: 缺 `<!-- mkdocs-include-start -->`")
        shim = docs_skills_dir / f"{name}.md"
        if not shim.is_file():
            r.fail(f"skills/{name}/: 缺對應 docs/skills/{name}.md shim")
        if mkdocs_text and f"skills/{name}.md" not in mkdocs_text:
            r.fail(f"skills/{name}/: mkdocs.yml nav 未列入 `skills/{name}.md`")
        if catalog_text and f"`{name}`" not in catalog_text:
            r.fail(f"skills/{name}/: docs/reference/skills.md catalog 未列入 `{name}`")
    return r


def check_version_sync() -> CheckResult:
    """plugin.json version must equal pyproject.toml [project].version.

    Commitizen bumps both via `version_files`, but a manual edit to one
    without the other silently desyncs. This catches that.
    """
    r = CheckResult("plugin.json ↔ pyproject.toml version sync")
    plugin_path = ROOT / "plugin.json"
    pyproject_path = ROOT / "pyproject.toml"
    if not plugin_path.is_file() or not pyproject_path.is_file():
        r.note("plugin.json 或 pyproject.toml 不存在，跳過")
        return r
    try:
        plugin_ver = json.loads(plugin_path.read_text(encoding="utf-8")).get("version")
    except json.JSONDecodeError as exc:
        r.fail(f"plugin.json 解析失敗：{exc}")
        return r
    try:
        with pyproject_path.open("rb") as f:
            pyproject_data = tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError) as exc:
        r.fail(f"pyproject.toml 解析失敗：{exc}")
        return r
    pyproject_ver = pyproject_data.get("project", {}).get("version")
    if plugin_ver is None:
        r.fail("plugin.json 沒有 `version` 欄位")
        return r
    if pyproject_ver is None:
        r.fail("pyproject.toml [project] 找不到 `version`")
        return r
    if plugin_ver != pyproject_ver:
        r.fail(
            f"版本不一致：plugin.json=`{plugin_ver}` vs "
            f"pyproject.toml=`{pyproject_ver}`。執行 `cz bump` 或手動同步。"
        )
    return r


CHECKS: list[Callable[[], CheckResult]] = [
    check_plugin_json,
    check_hooks_json,
    check_agent_frontmatter,
    check_command_frontmatter,
    check_skill_frontmatter,
    check_hook_scripts,
    check_pre_commit_config,
    check_skill_crossrefs,
    check_version_sync,
    check_commands_docs_alignment,
    check_skills_docs_alignment,
]


def main() -> int:
    failed = 0
    for check_fn in CHECKS:
        result = check_fn()
        if result.passed:
            print(f"✓ {result.name}")
        else:
            failed += 1
            print(f"✗ {result.name}")
            for err in result.errors:
                print(f"    ! {err}")
        for note in result.notes:
            print(f"    · {note}")
    print()
    total = len(CHECKS)
    if failed:
        print(f"✗ {failed}/{total} checks 失敗")
        return 1
    print(f"✓ 全部 {total} checks 通過")
    return 0


if __name__ == "__main__":
    sys.exit(main())
