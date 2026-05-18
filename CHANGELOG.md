# Changelog

All notable changes to Maigo are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `LICENSE` — MIT license，著作權人 Wei Lee
- `docs/reference/agents.md` — 五位 agent 的 model tier 選擇邏輯
- `.gitignore` 補 Python tooling 路徑（`__pycache__/`、`*.pyc`、`.venv/`、`.pytest_cache/`、`.ruff_cache/`）
- `CHANGELOG.md` 補 `### Planned (v0.1)` 子段（CI + tests 計畫）

### Fixed

- `hooks/teammate_quality_check.py`：Soyo block message 「八項」→「9 項」
- `commands/review.md`：三處過時 `` `/maigo` `` 引用改為 `` `/maigo:go` ``
- `docs/reference/skills.md`：移除寫死行數的脆弱行數註解，改為文字說明
- `scripts/validate_plugin.py`：`plugin.json` 必填欄位檢查加入 `license`

### Changed

- `hooks/verify_completion.py`：`500` magic number 改成具名常數 `OUTPUT_TAIL_CHARS`
- `docs/reference/hooks.md`：Stop hook 補 `### Fail-open 情況` 段
- `docs/reference/hooks.md`：TeammateIdle 補 `### Timeout` 段（30 秒上限說明）
- `docs/guides/contributing.md`：移除廢棄的「不主動提 Dag 概念」條目

### Planned (v0.1)

- GitHub Actions CI（跑 `validate_plugin.py` + `pre-commit run --all-files` + `pytest`）
- `tests/` for hook scripts (`teammate_quality_check.py`, `verify_completion.py`) 與 validators

## [0.0.1] — 2026-05-18

Initial scaffold. Plugin maps **MyGO!!!!!** members to dev roles, with focus on
a genuinely strict reviewer (Soyo).

### Added

**Agents** (`agents/`)
- `Raana` — explorer (codebase context, read-only)
- `Tomori` — planner (writes plan / review rubric)
- `Anon` — implementer (follows plan, no scope creep)
- `Soyo` — reviewer (default BLOCKED, applies `strict-review` skill)
- `Taki` — verifier (real exit codes, no hedge language)

**Commands** (`commands/`)
- `/maigo:go` — sequential dev flow (5 stages)
- `/maigo:team` — parallel review + verify after implement (~30% wall-clock saving)
- `/maigo:review` — review existing PR / branch / commit range (Anon sits out)

**Skills** (`skills/`)
- `strict-review` — 9-item checklist + evidence-driven reviewer process,
  extracted from Soyo so multiple consumers can reference it

**Hooks** (`hooks/`)
- `teammate_quality_check.py` (TeammateIdle) — validates Tomori / Soyo / Taki
  output structure; blocks until correctly formatted
- `verify_completion.py` (Stop) — auto-detects project type
  (Python / Node / Rust / Go), runs tests before completion; supports
  `.claude/skip-test-verification`, `.claude/test-command`,
  `.claude/known-test-failures`

**Scripts** (`scripts/`)
- `validate_frontmatter.py` — fast frontmatter check for pre-commit
- `validate_plugin.py` — 8-item comprehensive structural check
  (JSON validity, agent/command/skill frontmatter, hook scripts exist
  and parse, pre-commit config, skill cross-refs)

**Tooling**
- `.pre-commit-config.yaml` — file hygiene + ruff + custom frontmatter validator
- `.gitignore`, `plugin.json`, `README.md`

### Design choices

- **Reviewer is the priority.** Soyo defaults to BLOCKED, requires evidence,
  walks a 9-item checklist every time. Multiple layers (skill prompt + hook
  output validation) protect against orchestrator skipping or accepting weak
  output.
- **Artefacts live in `/tmp/maigo/<repo>/`**, not in the user's repo, so
  plan / rubric files don't pollute the working directory or need gitignoring.
- **Heavily inspired by [agent-flow](https://github.com/josix/agent-flow)** —
  multi-agent structure, hook patterns, skill / agent / command / hook
  layering all originate there. Maigo swaps the cast for MyGO!!!!! and
  narrows scope to strict-review workflows.
