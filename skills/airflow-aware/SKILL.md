---
name: airflow-aware
description: This skill should be used when working in the apache/airflow repository as a contributor (not as a Dag author). It surfaces the conventions Airflow's own AGENTS.md enforces — naming, Breeze/uv environment, Ruff/Mypy style, coding rules, pytest patterns, PR hygiene — so any task (review, quick-fix, refactor) in airflow follows them.
---

<!-- mkdocs-include-start -->

# Airflow-Aware

**Loaded by**: `repo-detect` hook (SessionStart) when `apache/airflow` is detected in git remote or file structure.
**Applies to**: Any skill execution within an Apache Airflow contributor checkout — review, quick-fix, refactoring, or otherwise.

## When to apply

A **knowledge layer**, not a review checklist, loaded by the
[`repo_detect` hook](https://github.com/Lee-W/maigo/blob/main/hooks/repo_detect.py) when an Apache Airflow repo is detected (or via a memory entry with
`triggers: [airflow-aware]`, see [Memory-triggered skill loading](https://github.com/Lee-W/maigo/blob/main/docs/reference/skills.md#memory-triggered-skill-載入)).
Once loaded, treat every convention as background — do not re-read each task.

**Layering**: this skill sits on the Python language layer — **read
[`python-aware`](https://github.com/Lee-W/maigo/blob/main/skills/python-aware/SKILL.md) first**; this skill lists only what is Airflow-specific.
Precedence: the repo's `AGENTS.md` / `CLAUDE.md` > this skill > `python-aware`. A rule that changes a `python-aware` default is marked **Airflow override**.

## Contributor conventions

### 1. Read AGENTS.md first — it wins

A condensed onramp, not a competing authority. Read [`AGENTS.md`](https://github.com/apache/airflow/blob/main/AGENTS.md) (or `CLAUDE.md`, identical) first; on conflict the repo file wins.
For review tasks also read [`.github/instructions/code-review.instructions.md`](https://github.com/apache/airflow/blob/main/.github/instructions/code-review.instructions.md).

### 2. Naming — Dag (prose) vs `DAG` (code)

In **prose**, write `Dag` (title case) — never all-caps `DAG` unless referring to the Python class, and never expand "Directed Acyclic Graph".
**Code tokens stay as-is**: class `DAG`, `dag_id`, `airflow dags list`, `dag_processing/`, `DAG_FOLDER`. See the "Naming" section of `AGENTS.md`.
The naming hook is a pure string match and false-positives on legitimate literals — classify each hit before "fixing" it (`references/naming.md`).
**Never rewrite past entries** in historical archival files (`migrations-ref.rst`, `RELEASE_NOTES.rst` / `CHANGELOG.rst`, provider `changelog.rst`); only new entries follow the rule.

### 3. Environment — Breeze + uv + prek

**Airflow override**: do not run `pytest`, `mypy`, or `pre-commit` on the host — use Breeze or `uv run --project <sub-project>` (the monorepo isolates dependencies per sub-project).

```bash
uv run --project airflow-core pytest tests/unit/foo/test_bar.py
uv run --project airflow-core ruff format src/
prek run --all-files   # prek, not pre-commit: the runner upstream specifies
```

- Never use `--project` at the **worktree root** (full-workspace resolve → `jpype1` needs Java); a sub-project *name* is fine.
- Reproduce a prek/CI hook failure from the **repo root** (only exception: `providers/`, to dodge an unrelated lychee failure — `references/verification-tooling.md` §1). Scratch scripts go in `dev/`.
- Before trusting a `prek` / `pytest` "Passed", local false reds, `verify_completion` / `jpype1` handling, `uv.lock` rebase handling: `references/verification-tooling.md`.
- A `uv.lock` diff you did not cause is usually drift on `main` — keep the re-lock out of a feature PR (`references/review-checks.md`, "uv.lock drift diagnostic").
- The commit hook runs the whole prek set and can outrun the Bash tool's timeout: run `ruff` / `ruff-format` / `mypy-<project>` by name on your changes first, then `--no-verify`; on a backport branch run both linters; a `uv.lock` diff that *downgrades* a package is a transitive-cap side effect — `references/verification-tooling.md`.

### 4. Code style — Ruff + Mypy

**Airflow override**: **line length 110** (not Ruff's 88 — agents most often miss this). New files need the **Apache License header** — copy it verbatim from an existing `.py`. Mypy runs via `prek`, not directly on the host.

### 5. Coding rules agents most often miss

- **Do not add new `raise AirflowException`** — use a more specific exception class.
- **`session` must be keyword-only**, and the callee must not call `session.commit()`; transaction management is the caller's job.
- Airflow-specific style (optional-extra import guard, naming, provider hooks, Dag authoring): `references/code-style.md`; general Python style (imports, validation, mypy, docstrings): `python-aware`'s `code-style.md`. attrs eq/hash, serialize/decode, scoped-session gotchas: `references/runtime-gotchas.md`. General Python rules (no `assert`, `time.monotonic()`, import placement): `python-aware`.
- A brand-new `provider.yaml` module-section *type* trips a validator check — read the "New provider.yaml module section" recipe in `references/registry-conventions.md` first.

### 6. Delivery completeness

A user-facing feature (new public class / SDK symbol / scheduling behaviour) ships **all three** in one PR: (1) **implementation + tests**; (2) an **example Dag** folded into an
**existing** example file, reusing its block style and objects — no new example file or bare new `with DAG(...)` block; (3) a **docs update** to the relevant `.rst`
(prose uses "Dag"; known limits are constraints, not `# TODO`). Adding or removing a public symbol also updates `task-sdk/docs/api.rst` and the `airflow-core/docs/` autoapi entries
together with `__init__.py` / `__all__` / the lazy-import table — both the removal and the addition. QA-plan and status-doc conventions: `references/delivery.md`.

### 7. Testing

- **Airflow override**: **do not use `caplog`** — see the "Testing" section of `AGENTS.md` for the prescribed pattern (typically a mock log handler asserted directly).
- **DB-touching tests must be marked `@pytest.mark.db_test`**.
- **Test paths mirror source paths**: `airflow-core/src/airflow/foo/bar.py` ↔ `airflow-core/tests/unit/foo/test_bar.py`.
- pytest-only, `spec=`/`autospec=True`, time-travel library, mock-assertion style: `python-aware`.

### 8. PR / commit / newsfragment

- Write commit messages and PR titles from the **user-impact perspective**, not which files were touched. Imminent fixes (obvious bugs, small refactors) can go straight to a PR.
- **Before any commit message or PR text, load the repo's `airflow-pr-draft-summary` skill** — it takes precedence over `maigo:commit-message` (body states the why, subject ≤70 chars, not Conventional Commits, no `Co-Authored-By`).
- Agent-opened PRs include a `Generated-by:` footer (see the "Pull requests" section of `AGENTS.md`).
- **Newsfragments are only required** for changes to `airflow-core/`, `chart/`, or `dev/mypy/`.
- A docs-page PR attaches a before/after screenshot at PR-open time; **never prefix a doc-only commit subject with `Docs:`** (it trips the conventional-commit hook) — `references/delivery.md`.

### 9. Architecture boundaries *(optional, for architectural review)*

**Scheduler** does not execute user code. **Worker** does not write to the metadata DB directly. **Providers** do not import from `airflow` core internals. **Task SDK** is isolated
from scheduler/worker internals. Cross-boundary changes need extra scrutiny — read `code-review.instructions.md` (its §1) first.
**Core ↔ SDK paired classes** (same name in `airflow-core/` and `task-sdk/`): drift on a same-named attribute is a **bug**, not a nit — fix it in the current PR
(compare constructor signature, post-`__init__` type, normalization, eager-raise; `references/design-integrity.md`).

### 10. Review-time-only checks *(loaded as strict-review item 10+)*

During a **review task** (🟡 Soyo running `strict-review` on an Airflow diff), read `references/review-checks.md` and append its sub-checks as items 10+, with the severity each states.
Its "Contents" list enumerates 10.1–10.37 plus the unnumbered release-tag check and DB portability and concurrency sections. The file also holds the Airflow case studies backing `strict-review`'s recurring must-fix patterns. Outside a review, skip the file.

### 11. CLI / REST / docs / backport conventions

- **CLI and REST**: grep sibling commands before designing a new semantic, filter or default; name a REST endpoint after the CLI's verb. Partitioned / scheduling-range APIs take `datetime` bounds, not `date` (`references/design-integrity.md`).
- **zh-TW locale content**: say "Taiwanese Mandarin", never "Traditional Chinese" (commit messages, PR text, docs, comments); translation details in `references/ui-conventions.md`.
- Docs prose, status claims, user-facing snippets: `references/docs-conventions.md`. A list already owned by another section defers to it — [`recurring-patterns.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/recurring-patterns.md). UI and backport judgment: `references/ui-conventions.md`, `references/delivery.md`.

## References index

| Reference | Read when |
|---|---|
| `references/code-style.md` | Airflow-specific style: optional-extra import guard, naming (action verbs, AIP-21, private modules), provider hooks, maintainer preferences, core-symbol version-floor checks, Dag authoring |
| `references/runtime-gotchas.md` | attrs eq/hash, (de)serialization field reads, scoped-session lifecycle |
| `references/verification-tooling.md` | Before trusting a prek / pytest "Passed"; local false reds; attribution; relock pin-back to the documented version; docs screenshot procedure |
| `references/review-checks.md` | Review tasks: items 10+ (Contents at the top); uv.lock drift diagnostic; release-tag check before "released"/"breaking" claims |
| `references/registry-conventions.md` | A diff touches `dev/registry/` or `registry/`, or adds a `provider.yaml` section |
| `references/design-integrity.md` | Hot-loop extension surfaces, Core ↔ SDK symmetry, CLI/REST consistency, range-API granularity |
| `references/docs-conventions.md` | Writing or reviewing docs prose, provider docs, docs examples |
| `references/test-cases.md` | Writing or reviewing Airflow tests: Airflow instances and Airflow-specific facts behind the python-aware test-conventions rules (read alongside the rule) |
| `references/ui-conventions.md` | `airflow-core/src/airflow/ui` changes; zh-TW translation rules |
| `references/naming.md` | The naming hook fires, or editing a historical archival file |
| `references/delivery.md` | Finishing a feature, QA / status docs, docs-page PRs, doc-only commit subjects, backports |
| [`python-aware`](https://github.com/Lee-W/maigo/blob/main/skills/python-aware/SKILL.md) | Always — the Python language layer this skill builds on |
| [`hook-runner-verification.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/references/hook-runner-verification.md) | Generic hook-runner false greens (stash, `git add -N`, `rebase --continue`, `files:` regex) |
| [`strict-review/references/design-integrity.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/design-integrity.md) | Generic framework / base-API design rules (type-pairing guards, symmetric naming, sum-types) |

## Composing with other skills

Builds on [`python-aware`](https://github.com/Lee-W/maigo/blob/main/skills/python-aware/SKILL.md) (Layering above); pairs with [`strict-review`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md).

**Review scenario** — run `strict-review`'s 9-item base checklist, then apply these as Airflow supplements: convention 2 (naming) → base item 4; 4 and 5 (style, correctness) → items 5–6;
6 (delivery completeness) → item 1; 7 (testing) → items 2–3. **§10 sub-checks (10.1–10.37) become items 10+**, with Block / Request-changes severity inherited from each sub-section.

**Quick-fix / refactor scenario** — use conventions 3–7 as background. Flag violations you notice, but do not run the full `strict-review` checklist unless the task calls for it; §10 is review-only.
