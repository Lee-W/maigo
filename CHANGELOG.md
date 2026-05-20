# Changelog

All notable changes to Maigo are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

## Unreleased

### Feat

- add /maigo:describe-pr command + github-title-description skill
- add repo-detect SessionStart hook + airflow-aware contributor skill
- add Anon hook check + /maigo:memory + /maigo:retro
- add domain skill composition mechanism

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

## v0.1.0 (2026-05-19)

### Feat

- add cross-project memory layer v0
- add /maigo:team, Stop hook, strict-review skill, validate_plugin
- scaffold Maigo — MyGO!!!!! five-member dev flow plugin

### Fix

- address audit findings (5 must-fix + 9 should-fix)
