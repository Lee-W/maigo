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
