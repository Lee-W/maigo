# Changelog

All notable changes to Maigo are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

## v0.17.0 (2026-06-06)

### Feat

- add /maigo:triage-issue for maintainer-side batch issue triage
- enforce doc-link convention + skills-docs validator
- **hooks**: broaden language coverage and dedup shared helpers

### Fix

- **plugin**: align manifest location with Claude Code spec + valid source

### Refactor

- **agents**: align Tomori / Soyo / Taki persona with canon
- **agents**: sharpen Raana and Anon persona framing

## v0.16.2 (2026-05-31)

### Refactor

- slim down skill files and move rationale to docs

## v0.16.1 (2026-05-31)

### Refactor

- persist artefacts in .maigo/ and extract teammate-flow
- extract memory skills and align project spec + tone

## v0.16.0 (2026-05-29)

### Feat

- **describe-pr**: emit a copy-paste-ready PR description block

## v0.15.3 (2026-05-29)

### Fix

- **plugin**: use explicit directory source type in marketplace.json

## v0.15.2 (2026-05-29)

### Fix

- **plugin**: revert marketplace plugin source to "." (local directory)

## v0.15.1 (2026-05-29)

### Fix

- **plugin**: switch marketplace source from github to url type

## v0.15.0 (2026-05-28)

### Feat

- **memory**: rename convention type to project; add allowed-tools and Mortis settlement

## v0.14.1 (2026-05-28)

### Fix

- **plugin**: use github source type in marketplace.json

## v0.14.0 (2026-05-28)

### Feat

- **agents**: add character voice rules to all five agent personas

## v0.13.0 (2026-05-27)

### Feat

- **review**: batch multi-PR, bilingual output, Airflow review-time checks

## v0.12.0 (2026-05-27)

### Feat

- **hooks**: add persistent must-fix retry counting for Soyo
- **failure-handling**: extract skill and add persistent retry counting

## v0.11.0 (2026-05-27)

### Feat

- **commands**: rename /maigo:fix to /maigo:quick

## v0.10.1 (2026-05-27)

### Fix

- **plugin**: use ./ prefix for relative source path in marketplace.json

## v0.10.0 (2026-05-25)

### Feat

- **core**: implement /maigo:doctor and enhance memory/prompt logic

## v0.9.0 (2026-05-23)

### Feat

- **narration**: require emoji prefix on every agent / narrator mention

## v0.8.1 (2026-05-22)

### Refactor

- **describe-pr**: switch PR body to Why/What/Test Plan

## v0.8.0 (2026-05-22)

### Feat

- **narration**: give the orchestrator a Doloris / Mortis narrator face
- **commands**: add /maigo:address-comments
- **commands**: draft commit message at finale, slim mermaid out

### Refactor

- **describe-pr**: run the command through the Tomori agent

## v0.7.0 (2026-05-21)

### Feat

- **agents**: emoji prefix for agent output identification

## v0.6.1 (2026-05-21)

### Fix

- remove unverified 「らーなだよ」 self-reference from Raana persona

## v0.6.0 (2026-05-21)

### Feat

- **memory**: v1 agent propose — Soyo/Anon propose, orchestrator confirms
- add commitizen-aware contributor skill
- **retro**: add destination judgment (personal memory vs maigo doc gap)
- **memory**: add validate_memory.py + reader agent inline schema warn

### Fix

- memory propose doc — link, fence guard tracking, retro path-B constraint
- memory propose confirm flow gaps (fix.md, retro dedup, dual memory index)
- stale What v0 doesn't do + team.md code fence guard
- stale comment + verify skill doc link

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
