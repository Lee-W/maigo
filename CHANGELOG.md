# Changelog

All notable changes to Maigo are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

## v0.44.0 (2026-07-13)

### Feat

- **skills**: crystallize graduated memory conventions into skills
- **board**: make work tracking easier to scan and manage

## v0.43.0 (2026-07-12)

### Feat

- **skills**: add model-dispatch and harness-discipline skills

## v0.42.0 (2026-07-11)

### Feat

- **codex**: support Maigo workflows as a plugin
- **board**: serve the work board live instead of rendering static HTML

## v0.41.1 (2026-07-10)

### Fix

- **board**: reject doc paths escaping the board directory

## v0.41.0 (2026-07-09)

### Feat

- **board**: link and auto-render review docs from the work board

### Fix

- **review**: require the original PR link in review report templates

## v0.40.0 (2026-07-09)

### Feat

- add work board command

## v0.39.0 (2026-07-08)

### Feat

- **review**: add cross-session review board and reviewer pre-verification

## v0.38.1 (2026-07-08)

### Fix

- **verify**: log setup failures for doctor

## v0.38.0 (2026-07-08)

### Feat

- **doctor**: add retry log summary tool
- validate agent model tiers against docs

## v0.37.0 (2026-07-07)

### Feat

- **crystallize**: guard against unscoped checklist items and out-of-repo destinations

## v0.36.0 (2026-07-07)

### Feat

- **skills**: graduate crystallized conventions into existing skills

## v0.35.0 (2026-07-05)

### Feat

- **failure-handling**: handle mid-task usage-limit interruption of subagents
- **crystallize**: add privacy gate before skill graduation

## v0.34.0 (2026-07-05)

### Feat

- **agents**: retier Raana to sonnet and Taki to haiku

## v0.33.0 (2026-07-04)

### Feat

- **validation**: enforce attributed command dialogue
- **doctor**: report retry / failure statistics from .maigo hook logs
- **commands**: add /maigo:take-issue to bridge triage verdicts into implementation
- **repo-audit**: add skill health-check data source (orphans / overlaps / dead pointers)

### Refactor

- **commands**: slim review, address-comments, crystallize via references extraction

## v0.32.0 (2026-07-01)

### Feat

- **skills**: graduate 26 memory conventions into skills

## v0.31.0 (2026-06-30)

### Feat

- **skills**: graduate three recurring conventions into existing skills

## v0.30.0 (2026-06-30)

### Feat

- add github-reply-draft skill and review-judgment refinements

## v0.29.0 (2026-06-23)

### Feat

- **review**: learn conventions from existing reviews and waiver decisions

## v0.28.0 (2026-06-22)

### Feat

- **address-comments**: learn conventions from addressed PR comments

## v0.27.1 (2026-06-22)

### Fix

- tighten verification and plugin validation

## v0.27.0 (2026-06-22)

### Feat

- add subagent overload / unavailability handling to failure-handling
- add /maigo:repo-audit command for repo internal housekeeping
- add markdown relative-link existence check to validate_plugin
- add maigo-self-check skill for structure-change verification

### Refactor

- slim strict-review skill via references extraction

## v0.26.0 (2026-06-18)

### Feat

- **orchestrator-voice**: act autonomously after batch go-ahead
- **validate_plugin**: check docs/reference/commands.md covers every command

### Fix

- close memory-loading per-project gap and verify_completion silent-skip
- **docs**: quote mermaid node labels in address-comments flowchart

## v0.25.1 (2026-06-18)

### Fix

- **verify_completion**: skip non-test collection errors and cap retry loop
- **memory-propose-confirm**: treat unanswered propose as deferred, not skipped

## v0.25.0 (2026-06-16)

### Feat

- no hard-wrap for docs

## v0.24.1 (2026-06-16)

### Refactor

- **skills,commands**: trim duplicated and over-long recipe prose

## v0.24.0 (2026-06-15)

### Feat

- **skills**: split verbose recipes into skill reference files

## v0.23.0 (2026-06-15)

### Feat

- **crystallize**: 新增萃取 memory 的慣例
- **review**: crystallize review preferences into strict-review skill
- **validate**: flag orphan memory files missing from MEMORY.md index

## v0.22.0 (2026-06-15)

### Feat

- **agents**: add Tomori plan-rejected and Anon all-steps-done voice lines
- **crystallize**: gate private memory with a public-safety check before graduation

### Fix

- **validate**: recognize nested metadata.type in memory schema check

## v0.21.2 (2026-06-12)

### Fix

- import describe-pr command

## v0.21.1 (2026-06-10)

### Fix

- **validate**: add agents alignment check, doc-link enforcement, skills frontmatter pre-commit, and mypy

## v0.21.0 (2026-06-10)

### Feat

- use Taiwanese Mandarian instead of Traditional Chinese whenever possible
- **agents**: add Soyo external-PR voice + narrator stuck-point lines
- **skills**: slim skill bodies via progressive disclosure + script-ify pr-context-cache

## v0.20.0 (2026-06-08)

### Feat

- **commands**: add /maigo:crystallize to graduate memory into skills

## v0.19.0 (2026-06-08)

### Feat

- **commands**: reply 草稿改為 comment 連結 + 純內文可複製 block

## v0.18.0 (2026-06-07)

### Feat

- **skills**: add copyable-deliverable skill for one-click paste

## v0.17.2 (2026-06-06)

### Fix

- **hooks**: keep .maigo/ out of host repo via git exclude

## v0.17.1 (2026-06-06)

### Fix

- **plugin**: make plugin.json author an object per Claude Code schema

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
