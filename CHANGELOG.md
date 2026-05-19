# Changelog

All notable changes to Maigo are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `LICENSE` — MIT license，著作權人 Wei Lee
- `docs/reference/agents.md` — 五位 agent 的 model tier 選擇邏輯
- `.gitignore` 補 Python tooling 路徑（`__pycache__/`、`*.pyc`、`.venv/`、`.pytest_cache/`、`.ruff_cache/`、`/site/`）
- `pyproject.toml` + `uv.lock` — uv 專案設定，`requires-python = ">=3.13"`、pytest 9 native `[tool.pytest]` 語法
- `tests/` — pytest unit test suite（62 tests，涵蓋 `hooks/teammate_quality_check.py`、`hooks/verify_completion.py`、`scripts/validate_plugin.py`）
- `.github/workflows/ci.yml` — uv-based CI（pre-commit + `validate_plugin.py` + pytest，單 3.13）
- `.github/workflows/docs.yml` — Material for MkDocs build + `actions/deploy-pages` 部署
- `mkdocs.yml`、`docs/index.md`、`docs/changelog.md` — 文件站基底（站點：<https://lee-w.github.io/maigo/>）
- `docs/agents/*.md`、`docs/commands/*.md`、`docs/skills/strict-review.md` — include-markdown shim，把 plugin source 帶進文件站
- 9 個 source 檔（5 agents + 3 commands + strict-review skill）加 `<!-- mkdocs-include-start -->` marker

### Fixed

- `hooks/teammate_quality_check.py`：Soyo block message 「八項」→「9 項」
- `commands/review.md`：三處過時 `` `/maigo` `` 引用改為 `` `/maigo:go` ``
- `docs/reference/skills.md`：移除寫死行數的脆弱行數註解，改為文字說明
- `scripts/validate_plugin.py`：`plugin.json` 必填欄位檢查加入 `license`
- `README.md` Acknowledgments：移除「並行 review」這項與 agent-flow 的差異描述，
  與 `/maigo:team`（並行 Soyo + Taki）的存在矛盾

### Changed

- `hooks/verify_completion.py`：`500` magic number 改成具名常數 `OUTPUT_TAIL_CHARS`
- `docs/reference/hooks.md`：Stop hook 補 `### Fail-open 情況` 段
- `docs/reference/hooks.md`：TeammateIdle 補 `### Timeout` 段（30 秒上限說明）
- `docs/guides/contributing.md`：移除廢棄的「不主動提 Dag 概念」條目
- `hooks/verify_completion.py`：`systemMessage` prefix 統一為「立希 (Taki)」，
  與 `teammate_quality_check.py` 的人設化訊息一致
- `README.md`：加 CI badge、Docs URL；Python prerequisites 從 `3.9+` 改為 `3.13+`（對齊 `pyproject.toml requires-python`）

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
