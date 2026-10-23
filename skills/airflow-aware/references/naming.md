# Airflow naming conventions — hook false positives and historical archival files

Loaded on demand by `skills/airflow-aware/SKILL.md` §2 — the supporting detail behind the
`Dag` (prose) vs `DAG` (code) rule. Read this file when the airflow-workspace naming hook fires,
or when editing a migration reference, release-notes or changelog file.

---

## Naming hook false positives

The airflow-workspace naming hook (fires on Edit/Write, reports "RULE VIOLATION",
commands "Fix all occurrences now") is a **pure string match** — it fires on any
all-caps `DAG` spelling anywhere in the file, with no awareness of the naming rule's
own exceptions (Python code tokens, CLI commands, paths/config keys, URLs, anti-pattern
quotes that intentionally show the wrong form — all of these must stay literal).

When it fires:

1. `grep -n` list every hit in the file.
2. Classify each hit as prose-violation vs literal-exception against the exception list in the paragraph above (code tokens, CLI commands, paths/config keys, URLs, anti-pattern quotes).
3. Only fix the prose violations. If every hit is a literal exception, say so explicitly
   in the reply (with the classification) and don't touch the file.

Note: a file that *discusses* this naming rule itself (like this reference file) will always
trip the hook — that's expected, not a bug to fix.

## Historical archival files are exempt — never rewrite past entries

`airflow-core/docs/migrations-ref.rst` and `RELEASE_NOTES.rst` /
`CHANGELOG.rst` (including provider `changelog.rst` files) reproduce
historical record verbatim — a migration revision's original message, or a
past PR's shipped title. Existing all-caps/lowercase spellings in those
**past entries** are not to be rewritten to `Dag`, even when a naming-rule
hook fires on them. Rewriting them silently changes the historical record and
breaks the `git log` ↔ release-note correspondence for past PRs. When scoped
to fixing something else in one of these files (e.g. a spell-check nit),
touch only the offending line; ignore the naming hook for pre-existing
all-caps occurrences elsewhere in the same file — don't pre-emptively "fix"
them. **New** entries appended to these files still follow the normal Dag
naming rule; only existing historical rows are exempt.
