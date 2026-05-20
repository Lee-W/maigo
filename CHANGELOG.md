# Changelog

All notable changes to Maigo are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

## v0.5.0 (2026-05-20)

### Feat

- **skills**: add commit-message skill for durable commit log style
- **airflow-aware**: add uv.lock drift and Core/SDK symmetry rules

## v0.4.0 (2026-05-20)

### Feat

- auto-skip test verification in apache/airflow checkouts

## v0.3.0 (2026-05-20)

### Feat

- add /maigo:fix command, pr-context-cache skill, review --mode flag

### Fix

- skip test verification when no uncommitted file modifications

## v0.2.0 (2026-05-20)

### Feat

- /maigo:describe-pr command + github-title-description skill
- repo-detect hook + airflow-aware contributor skill
- Anon hook check + /maigo:memory + /maigo:retro
- **memory**: add domain skill composition mechanism

## v0.1.0 (2026-05-19)

### Feat

- add cross-project memory layer v0
- add /maigo:team, Stop hook, strict-review skill, validate_plugin
- scaffold Maigo — MyGO!!!!! five-member dev flow plugin

### Fix

- address audit findings (5 must-fix + 9 should-fix)
