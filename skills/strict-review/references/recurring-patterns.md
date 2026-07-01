# Strict Review — Recurring Must-Fix Patterns (Extended)

Loaded on demand by `skills/strict-review/SKILL.md` — **expanded rationale and recipes
for cross-cutting patterns that surface frequently enough to be named**.
Read this file when a pattern listed in the "Recurring must-fix patterns" section of
SKILL.md applies and you need the full reasoning or a worked example.

---

## Commit body is a contract — verify it matches the diff

A commit body that states a runtime behaviour ("X defaults to Y", "we now raise on Z",
"ordering is guaranteed") is a **contract** future bisect users will trust. When body prose
says "X happens", the diff must show X happening.

How to apply during review:

1. For each behavioral claim in the commit body (defaults, fallbacks, raise conditions,
   ordering, validation rules) grep / read the relevant code path to verify.
2. If code does not match: **must-fix**. Either implement the promised behaviour (Option A)
   or rewrite the commit body to describe what the code actually does (Option B). Do not
   accept "this is just docs".
3. Pre-release status does **not** downgrade this. Wire-format mutations are acceptable
   pre-release, but the commit body's promise about behaviour must still align with the diff.

---

## Underscore-private exception that consumers must `isinstance`-check is de-facto public API

When a module defines private exception classes (`_FooError`, `_BarError`) and a consumer
must `isinstance`-check one of them to distinguish failure modes, that one exception is
**already public API** — the underscore is a lie.

Two-step signal to watch for:

1. Multiple exception types exist behind a common wrapper (e.g., `_PollFailure(exc)`).
2. A consumer must inspect `.exc` and branch on its concrete type.

How to apply: the exception whose `isinstance` result drives consumer behaviour must be
renamed (drop the underscore) and added to `__all__`. Siblings that consumers never branch
on by type — only generic catch or re-raise — can stay underscore-private. Selective
promotion is the discipline; do not broadcast the whole hierarchy.

> Concrete case studies for this pattern (Airflow incidents) live in
> `skills/airflow-aware/references/review-checks.md` — read them when reviewing an
> Airflow diff and a worked example helps.

---

## Concurrent PR 根本修法優先

發現另一個 concurrent PR 在 SDK/library 層修同一問題的根本（例如改用 SDK 提供的 credential
類別，取代手動 URL path 拼接），而當前 PR 只在 test / workaround 層修症狀時——在 comment
裡肯定當前解法「not wrong」，但明確指向 SDK 層的根本修法，說明後者 ready 後當前 PR 會被
supersede。傾向推薦架構層解法而非繞路補丁。

---

## Naming: name by what it is, not by its first caller's use case

Flag a name that encodes the calling context rather than the operation it
performs. Name a function/method/variable by what it **intrinsically does**,
not by the use case of its first/current caller.

Example: a helper named after a domain-specific use case (e.g. something
read as partition-specific) may in fact compute a generic operation (e.g.
"calendar day + timetable timezone → UTC instant") that only touched that
domain because its first caller happened to compare the result against a
domain value. An over-coupled name misleads the next reader, blocks reuse,
and pretends the abstraction is narrower than it actually is (it can also
provoke a wrong placement debate — "why does the base class have this
narrow concept?" — when the real issue is just the name).

How to apply: before accepting a name, ask "what does this compute,
independent of who calls it?" If the name only makes sense given one caller,
flag it for a rename to the general operation. Verb-first naming
(`resolve_`, `compute_`, `get_`, `build_`, `find_`, `extract_`) generally
reads better once decoupled from the specific caller.

## Naming: a private helper's name must carry the domain noun

Flag a private helper name built from an adjective/adverb pair with no
object — it forces the reader to guess the subject. A name like
`_warn_unreachable_once` drops *what* is unreachable; `_warn_unreachable_asset_partition`
carries the domain noun (asset partition) the helper actually acts on.

Push behavioral/implementation qualifiers like "once" / "deduplicated" into
the docstring rather than the name, and align the name with sibling methods
in the same class (e.g. match an established `_resolve_asset_partition_status`
phrasing pattern).

How to apply: when naming (or reviewing the name of) a private helper, ask
"what does it act *on*?" and put that noun in the name; check sibling
methods for the established noun phrasing and match it. Keep dedup /
idempotency / "once" notes for the docstring. This complements the "name by
what it is, not its use case" pattern above — that one warns against
coupling a name to its first caller; this one warns against dropping the
domain object and leaving only a behavioral qualifier.
