# Airflow delivery conventions — docs sync, QA/status docs, PR hygiene, backports

Loaded on demand by `skills/airflow-aware/SKILL.md` §6, §8 and §11 — the supporting detail behind
the delivery-completeness, PR/commit and backport rules. Read this file when finishing a
user-facing feature, drafting a QA plan or status doc, opening a docs PR, writing a doc-only
commit subject, or judging a backport drift-check failure.

---

## Public-symbol sync (docs side)

Whenever a public symbol is added or removed,
`task-sdk/docs/api.rst` and the corresponding `airflow-core/docs/` `.. autoapiclass::` entries
must be updated together with `__init__.py` / `__all__` / lazy-import table.
Dropping a removed symbol and adding a new one are both required — a missing deletion causes
`breeze build-docs` to crash at Sphinx import time; a missing addition causes a silent gap
in the API reference. After editing, `grep` the old symbol name across `docs/` to confirm
no stale references remain.

Why: apache/airflow PR #64571 (`Window` / `RollupMapper`) and the partition-mapper
refactor both shipped with example + docs in the same PR; missing either was flagged in
round-1 review.

## QA / status-doc conventions

When drafting or reviewing a manual QA plan, feature-coverage matrix, or
status doc for a feature that ships:

- **Don't add a "serialization round-trip" manual QA item.** The scheduler
  only ever reads serialized Dags, so every functional test in the plan
  already exercises the deserialized form implicitly — a broken round-trip
  would make those functional checks fail first. Field-level lossless
  round-trip belongs in a pytest unit test, not a manual QA row. The one
  legitimate manual touch is a first-time smoke glance at the
  `serialized_dag` JSON when a brand-new param ships — that's dev smoke, not
  a recurring QA item.
- **Don't leave "not done yet" signals in a status/QA doc meant to record
  completed work** — drop header decorations like `✅ merged` / `🚧` / `❌ not
  native`, and avoid absence-wording for deliberately-scoped behavior
  (`not implemented`, `scoped out`, `ad-hoc`/`throwaway` for a fixture).
  Describe an intentionally-scoped feature positively as the current design,
  not as a gap measured against something that was never built. An **empty**
  results column (template waiting to be filled) is fine — that's not a
  not-done signal. Once a results column is actually **filled**, a per-row
  `✅ Pass (...)` marking the verification method is good practice — the
  no-decoration rule governs headers/progress marks and "not done" phrasing,
  not a factual pass/fail record.
- **A defect found in the example Dag / test fixture while QA-ing a feature
  is in scope to fix**, not just to log. If the bug is in the shipped example
  producer/consumer rather than the feature under test, fix it and fold the
  fix into the same PR (ask before editing the shared artifact) — a broken
  example is a broken user-facing artifact, and fixing it is part of
  finishing the QA.
- **Scope an unreleased-version doc/QA plan to the release branch's actual
  HEAD, not just a beta/rc tag.** When only a beta/rc tag exists (e.g.
  `3.3.0b1`), the release branch (e.g. `v3-3-test`) keeps accumulating
  commits after the tag — the tag is not the source of truth. After scoping
  against a tag, run `git log --oneline <tag>..HEAD -- <relevant paths>` and
  fold in the behavior-changing commits found there before calling the doc
  current. A beta tag isn't a real release for this purpose either — it
  doesn't freeze scope or API, the same instinct as treating a pre-release
  tag as authoritative for API stability.

## A docs page PR needs a before/after screenshot at PR-open time

If this PR adds or changes a docs page, attach a before/after screenshot at PR-open time —
a new reader-facing docs page counts as user-facing for the PR template's screenshot
requirement, even though "it's just docs." Don't wait for a reviewer to ask. See the
screenshot procedure in `verification-tooling.md` §6.

## Don't prefix a doc-only commit's subject with `Docs:`

The subject of a doc-only commit must not start with `Docs:`. `docs` is
itself a Conventional Commits type name, so
`scripts/ci/prek/check_no_conventional_commit_message.py` matches
`Docs:`/`Docs/` against its fixed `CONVENTIONAL_TYPES` list and fails the
hook — even though `AGENTS.md` explicitly allows area-tag prefixes like
`UI:`/`API:`/`Helm:` (those aren't in `CONVENTIONAL_TYPES`, so they pass).
Write plain prose describing user impact instead (e.g. "Sync
`LLMRetryPolicy` docs with the `redact_exception` default" rather than
"Docs: Sync..."). If `check-no-conventional-commit-message` fails, drop
the leading type-like prefix and retry — don't reach for `--no-verify`.

## Backport judgment

When a backport branch's drift-check fails because it references something
(a file, a test site) that doesn't exist on that branch, check whether the
**underlying capability** is already present on the branch before deciding
the check should just be narrowed in scope. If the capability shipped but
the newer test coverage for it didn't get backported, the right move is
usually to backport the source PR that added the missing coverage — not to
shrink the check to stop noticing the gap.
