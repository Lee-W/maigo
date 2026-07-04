#!/usr/bin/env python3
"""Comprehensive structural check for the Maigo plugin.

Runs the full check list (see `CHECKS` at the bottom of this file for the
canonical, always-current set). Covers plugin.json / hooks.json / agent /
command / skill frontmatter, hook script existence + syntax, pre-commit
config sanity, skill cross-references, plugin↔pyproject version sync, and
commands/skills ↔ docs alignment.

跑：`python3 scripts/validate_plugin.py`
Exit 0 = 全綠；Exit 1 = 至少一項失敗。輸出最末一行印「全部 N checks 通過」
或「N/M checks 失敗」——以 N 為準，不必同步任何文件。

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
    r = CheckResult(".claude-plugin/plugin.json")
    path = ROOT / ".claude-plugin" / "plugin.json"
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
    # Type check for object-shaped fields — Claude Code v2.1.154+ rejects the
    # plugin install when `author` is a bare string instead of `{name, email?}`.
    author = data.get("author")
    if author is not None:
        if not isinstance(author, dict):
            r.fail(
                f'欄位 `author` 必須是 object（如 `{{"name": "..."}}`），'
                f"目前是 {type(author).__name__}"
            )
        elif not author.get("name"):
            r.fail("欄位 `author.name` 缺值（object 形式下 name 是必填）")
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


def check_hooks_schema() -> CheckResult:
    """Validate the hook config contract beyond JSON syntax."""
    r = CheckResult("hooks/hooks.json schema")
    path = ROOT / "hooks" / "hooks.json"
    if not path.is_file():
        r.note("hooks/hooks.json 不存在，跳過")
        return r
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        r.fail("hooks.json JSON 壞掉，跳過 schema 檢查")
        return r

    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        r.fail("缺少 object 型別的 `hooks` 頂層欄位")
        return r

    allowed_events = {"SessionStart", "TeammateIdle", "Stop"}
    for event, configs in hooks.items():
        if event not in allowed_events:
            r.fail(f"未知 hook event `{event}`")
        if not isinstance(configs, list):
            r.fail(f"{event}: event config 必須是 list")
            continue
        for cfg_index, cfg in enumerate(configs):
            if not isinstance(cfg, dict):
                r.fail(f"{event}[{cfg_index}]: config 必須是 object")
                continue
            handlers = cfg.get("hooks")
            if not isinstance(handlers, list) or not handlers:
                r.fail(f"{event}[{cfg_index}]: 缺少非空 `hooks` list")
                continue
            for hook_index, hook in enumerate(handlers):
                prefix = f"{event}[{cfg_index}].hooks[{hook_index}]"
                if not isinstance(hook, dict):
                    r.fail(f"{prefix}: hook 必須是 object")
                    continue
                if hook.get("type") != "command":
                    r.fail(f"{prefix}: type 必須是 `command`")
                command = hook.get("command")
                if not isinstance(command, str) or not command.strip():
                    r.fail(f"{prefix}: command 必須是非空字串")
                elif "${CLAUDE_PLUGIN_ROOT}/" not in command:
                    r.fail(f"{prefix}: command 必須使用 `${{CLAUDE_PLUGIN_ROOT}}/`")
                timeout = hook.get("timeout")
                if timeout is not None and (
                    not isinstance(timeout, int)
                    or isinstance(timeout, bool)
                    or timeout <= 0
                ):
                    r.fail(f"{prefix}: timeout 必須是正整數")
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


_PERSONA_MARKER_RE = re.compile(
    r"🐱|🩵|🎀|🟡|🟣|🌙|🌑|樂奈|Raana|Tomori|愛音|Anon|爽世|Soyo|立希|Taki|Doloris|Mortis|燈"
)
_BLOCKQUOTE_EPIGRAPH_RE = re.compile(r"^> 「[^「」]+」", re.MULTILINE)
# 用整份文件掃出「真的有收尾」的引號 span（[^「」]+ 允許跨行，如 crystallize.md:30-31 的
# 跨行台詞），而不是逐行看「有沒有 `「` 這個字」——後者會誤放行「只有開口沒收尾」的殘缺引號。
_QUOTE_SPAN_RE = re.compile(r"「[^「」]+」")


def _quote_is_persona_attributed(text: str, lines: list[str], match: re.Match) -> bool:
    """這段（已確認收尾的）引號是否掛名——同行引號開口前，或緊鄰的前一個非空白 / 非 fence 分隔行。"""
    offset = match.start()
    line_index = text.count("\n", 0, offset)
    line_start = text.rfind("\n", 0, offset) + 1
    col = offset - line_start
    line = lines[line_index]
    if _PERSONA_MARKER_RE.search(line[:col]):
        return True
    j = line_index - 1
    while j >= 0 and lines[j].strip() in ("", "```"):
        j -= 1
    return j >= 0 and bool(_PERSONA_MARKER_RE.search(lines[j]))


def check_command_persona_quotes() -> CheckResult:
    """每個 commands/*.md 至少一段「掛名」且「有收尾」的「」角色台詞（MyGO!!!!! 濃度慣例）。

    「有收尾」＝ 用整份文件的字元 offset 比對 `「[^「」]+」`（非空、可跨行），只有開口
    `「` 沒有對應 `」` 的殘缺引號不算數。

    「掛名」＝ 同一行「」引號開口前，或緊鄰的前一個非空白 / 非 code-fence 分隔行，看得到
    角色 emoji 或名字；或整段是 `> 「...」` 形式的 blockquote 標題引言（epigraph，如
    `doctor.md` / `go.md`）。

    這只是「引號附近找得到角色線索」的機械判斷，不是完整語意驗證真的是角色開口說的話——
    純 UI/error 訊息引號、旁邊完全沒有角色 emoji / 名字的（如 `memory.md` 印的友善提示
    文案）不算數，會被擋下。

    已知殘餘缺口（非本次擋下範圍，先記著）：`address-comments.md` / `crystallize.md` /
    `triage-issue.md` 目前是靠引號附近**巧合**提到角色名通過（例如順帶提到「Soyo」但那段
    引號其實是技術名詞，不是角色開口說的話），不是真的有掛名台詞——之後動這幾個檔時留意
    別刪掉那個巧合來源，最好找機會補一句真台詞。
    """
    r = CheckResult("commands/*.md 至少一段掛名角色「」台詞")
    cmds_dir = ROOT / "commands"
    if not cmds_dir.is_dir():
        r.note("commands/ 目錄不存在，跳過")
        return r
    for path in sorted(cmds_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if _BLOCKQUOTE_EPIGRAPH_RE.search(text):
            continue
        lines = text.split("\n")
        if any(
            _quote_is_persona_attributed(text, lines, m)
            for m in _QUOTE_SPAN_RE.finditer(text)
        ):
            continue
        r.fail(
            f"{path.relative_to(ROOT)}: 缺掛名角色台詞——「」引號旁邊看不到角色 emoji / "
            "名字（也沒有 blockquote epigraph），或引號沒有收尾。MyGO!!!!! 濃度慣例要求"
            "台詞要掛名且完整，不能只是 UI/error 訊息引號"
        )
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


def check_commands_reference_coverage() -> CheckResult:
    """docs/reference/commands.md 散文總表必須涵蓋每個 commands/*.md slug。

    比對方式：字面檢查 '## /maigo:<slug>' 是否出現在總表文字中。
    """
    r = CheckResult("commands/*.md → docs/reference/commands.md coverage")
    cmds_dir = ROOT / "commands"
    ref_path = ROOT / "docs" / "reference" / "commands.md"
    if not cmds_dir.is_dir():
        r.note("commands/ 目錄不存在，跳過")
        return r
    if not ref_path.is_file():
        r.note("docs/reference/commands.md 不存在，跳過")
        return r
    ref_text = ref_path.read_text(encoding="utf-8")
    for path in sorted(cmds_dir.glob("*.md")):
        slug = path.stem
        if f"## `/maigo:{slug}`" not in ref_text:
            r.fail(f"docs/reference/commands.md 未涵蓋命令：## `/maigo:{slug}`")
    return r


def check_command_overview_coverage() -> CheckResult:
    """README and docs home must not drift from the command catalog."""
    r = CheckResult("README / docs/index command overview coverage")
    cmds_dir = ROOT / "commands"
    if not cmds_dir.is_dir():
        r.note("commands/ 目錄不存在，跳過")
        return r

    slugs = sorted(path.stem for path in cmds_dir.glob("*.md"))
    expected_count_texts = {
        "README.md": f"完整 {len(slugs)} 個命令",
        "docs/index.md": f"完整 {len(slugs)} 個命令",
    }
    for rel, expected_count in expected_count_texts.items():
        path = ROOT / rel
        if not path.is_file():
            r.fail(f"{rel} 不存在")
            continue
        text = path.read_text(encoding="utf-8")
        if expected_count not in text:
            r.fail(f"{rel}: 缺 `{expected_count}`")
        for slug in slugs:
            needle = f"`/maigo:{slug}`"
            if needle not in text:
                r.fail(f"{rel}: command overview 未提及 {needle}")
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


def check_agents_docs_alignment() -> CheckResult:
    """Each agents/<Name>.md must align with the docs publishing path.

    1. agents/<Name>.md contains `<!-- mkdocs-include-start -->`
    2. docs/agents/<name_lower>.md shim exists
    3. mkdocs.yml nav references agents/<name_lower>.md
    4. docs/reference/agents.md catalog mentions the agent name
    """
    r = CheckResult("agents/*.md ↔ docs/agents/ + mkdocs + catalog alignment")
    agents_dir = ROOT / "agents"
    docs_agents_dir = ROOT / "docs" / "agents"
    if not agents_dir.is_dir():
        r.note("agents/ 目錄不存在，跳過")
        return r
    mkdocs_text = ""
    mkdocs_path = ROOT / "mkdocs.yml"
    if mkdocs_path.is_file():
        mkdocs_text = mkdocs_path.read_text(encoding="utf-8")
    catalog_text = ""
    catalog_path = ROOT / "docs" / "reference" / "agents.md"
    if catalog_path.is_file():
        catalog_text = catalog_path.read_text(encoding="utf-8")

    for path in sorted(agents_dir.glob("*.md")):
        name = path.stem  # e.g. "Anon"
        name_lower = name.lower()  # e.g. "anon"
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT)
        if "<!-- mkdocs-include-start -->" not in text:
            r.fail(f"{rel}: 缺 `<!-- mkdocs-include-start -->`")
        shim = docs_agents_dir / f"{name_lower}.md"
        if not shim.is_file():
            r.fail(f"agents/{name}.md: 缺對應 docs/agents/{name_lower}.md shim")
        if mkdocs_text and f"agents/{name_lower}.md" not in mkdocs_text:
            r.fail(f"agents/{name}.md: mkdocs.yml nav 未列入 `agents/{name_lower}.md`")
        if catalog_text and name not in catalog_text:
            r.fail(
                f"agents/{name}.md: docs/reference/agents.md catalog 未提及 `{name}`"
            )
    return r


def check_version_sync() -> CheckResult:
    """plugin.json version must equal pyproject.toml [project].version.

    Commitizen bumps both via `version_files`, but a manual edit to one
    without the other silently desyncs. This catches that.
    """
    r = CheckResult(".claude-plugin/plugin.json ↔ pyproject.toml version sync")
    plugin_path = ROOT / ".claude-plugin" / "plugin.json"
    pyproject_path = ROOT / "pyproject.toml"
    if not plugin_path.is_file() or not pyproject_path.is_file():
        r.note(".claude-plugin/plugin.json 或 pyproject.toml 不存在，跳過")
        return r
    try:
        plugin_ver = json.loads(plugin_path.read_text(encoding="utf-8")).get("version")
    except json.JSONDecodeError as exc:
        r.fail(f".claude-plugin/plugin.json 解析失敗：{exc}")
        return r
    try:
        with pyproject_path.open("rb") as f:
            pyproject_data = tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError) as exc:
        r.fail(f"pyproject.toml 解析失敗：{exc}")
        return r
    pyproject_ver = pyproject_data.get("project", {}).get("version")
    if plugin_ver is None:
        r.fail(".claude-plugin/plugin.json 沒有 `version` 欄位")
        return r
    if pyproject_ver is None:
        r.fail("pyproject.toml [project] 找不到 `version`")
        return r
    if plugin_ver != pyproject_ver:
        r.fail(
            f"版本不一致：.claude-plugin/plugin.json=`{plugin_ver}` vs "
            f"pyproject.toml=`{pyproject_ver}`。執行 `cz bump` 或手動同步。"
        )
    return r


def check_doc_link_convention() -> CheckResult:
    """Cross-source links in agents/commands/skills sources must be absolute GitHub URLs."""
    r = CheckResult("agents / commands / skills cross-source 連結需用絕對 GitHub URL")
    link_re = re.compile(r"\]\(([^)]+)\)")
    source_prefix_re = re.compile(r"^(agents|commands|skills)/")

    source_files: list[tuple[Path, str]] = []
    agents_dir = ROOT / "agents"
    if agents_dir.is_dir():
        for p in sorted(agents_dir.glob("*.md")):
            source_files.append((p, p.read_text(encoding="utf-8")))
    commands_dir = ROOT / "commands"
    if commands_dir.is_dir():
        for p in sorted(commands_dir.glob("*.md")):
            source_files.append((p, p.read_text(encoding="utf-8")))
    skills_dir = ROOT / "skills"
    if skills_dir.is_dir():
        for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
            sf = skill_dir / "SKILL.md"
            if sf.is_file():
                source_files.append((sf, sf.read_text(encoding="utf-8")))

    for path, text in source_files:
        rel = path.relative_to(ROOT)
        for m in link_re.finditer(text):
            target = m.group(1)
            if target.startswith(
                ("http://", "https://", "#", "../docs/reference/", "../docs/guides/")
            ):
                continue
            if source_prefix_re.match(target):
                r.fail(f"{rel}: 相對跨 source 連結 `]({target})` 需改為絕對 GitHub URL")
    return r


_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def _strip_code_spans(text: str) -> str:
    """把 fenced code block 與 inline code span 替換成空白，避免把範例連結誤判。

    fenced code block（``` ... ```）：保留換行符，其餘換空格。
    inline code span（`...`）：整段換成等長空格（不含換行）。
    """

    def blank_fenced(m: re.Match) -> str:  # type: ignore[type-arg]
        return "\n" * m.group(0).count("\n")

    def blank_inline(m: re.Match) -> str:  # type: ignore[type-arg]
        return " " * len(m.group(0))

    text = _FENCED_CODE_RE.sub(blank_fenced, text)
    text = _INLINE_CODE_RE.sub(blank_inline, text)
    return text


def check_relative_links() -> CheckResult:
    """Markdown 相對連結的目標檔必須存在。

    掃描 agents/*.md、commands/*.md、skills/**/*.md、docs/**/*.md 及 repo root *.md。
    只驗非 http / 非 # 錨點 / 非絕對路徑的相對連結；placeholder 與 glob 樣式跳過。
    fenced code block 內的連結（範例 / ❌ 反例）一律跳過。
    """
    r = CheckResult("markdown 相對連結目標存在")
    # 不處理 title-attribute 語法 [text](url "title") 與 reference-style links [text][ref]
    link_re = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

    md_files: set[Path] = set()
    for pattern in (
        "agents/*.md",
        "commands/*.md",
        "skills/**/*.md",
        "docs/**/*.md",
    ):
        md_files.update(ROOT.glob(pattern))
    for p in ROOT.glob("*.md"):
        md_files.add(p)

    for path in sorted(md_files):
        raw = path.read_text(encoding="utf-8")
        # 移除 fenced code block 與 inline code span，避免把範例連結誤判為失效連結
        text = _strip_code_spans(raw)
        for m in link_re.finditer(text):
            target = m.group(1).strip()
            # 跳過 http/https、純錨點、mailto、絕對路徑
            if "://" in target:
                continue
            if target.startswith("#"):
                continue
            if target.startswith("mailto:"):
                continue
            if target.startswith("/"):
                continue
            # 剝掉 #anchor，只留檔案部分
            file_part = target.split("#", 1)[0].strip()
            # 跳過 placeholder / glob / 範例（含 <> * 反引號 空白 ... 省略號）
            if not file_part or re.search(r"[<>*`\s]|\.\.\.", file_part):
                continue
            resolved = (path.parent / file_part).resolve()
            if not resolved.exists():
                r.fail(f"{path.relative_to(ROOT)} 的連結 '{target}' 指向不存在的路徑")
    return r


def check_skills_graph() -> CheckResult:
    """docs/reference/skills.md 的 mermaid 相依圖必須涵蓋每一個 skill。

    圖是手繪維護的；這個 check 抓「新增 skill 但忘了加進相依圖」的 drift。
    只驗節點存在（skill 名出現在 mermaid 區塊內），不驗邊的正確性。
    """
    r = CheckResult("docs/reference/skills.md mermaid 相依圖涵蓋所有 skill")
    skills_dir = ROOT / "skills"
    page = ROOT / "docs" / "reference" / "skills.md"
    if not skills_dir.is_dir() or not page.is_file():
        r.note("skills/ 或 docs/reference/skills.md 不存在，跳過")
        return r
    text = page.read_text(encoding="utf-8")
    m = re.search(r"```mermaid\n(.*?)```", text, re.DOTALL)
    if not m:
        r.fail("docs/reference/skills.md 找不到 ```mermaid 相依圖區塊")
        return r
    graph = m.group(1)
    for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        if skill_dir.name not in graph:
            r.fail(f"mermaid 相依圖缺 skill 節點：{skill_dir.name}")
    return r


CHECKS: list[Callable[[], CheckResult]] = [
    check_plugin_json,
    check_hooks_json,
    check_hooks_schema,
    check_agent_frontmatter,
    check_command_frontmatter,
    check_command_persona_quotes,
    check_skill_frontmatter,
    check_hook_scripts,
    check_pre_commit_config,
    check_skill_crossrefs,
    check_version_sync,
    check_commands_docs_alignment,
    check_commands_reference_coverage,
    check_command_overview_coverage,
    check_skills_docs_alignment,
    check_agents_docs_alignment,
    check_skills_graph,
    check_doc_link_convention,
    check_relative_links,
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
