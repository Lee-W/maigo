# Strict Review — 反覆出現的 must-fix 與判斷原則索引

Loaded on demand by [`skills/strict-review/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md) — 審查時要判斷某個 finding 屬於哪類慣見模式、或該不該 flag 時讀。三組索引各自指向更完整的 reference。
本檔內文原樣自 SKILL.md 搬出。

## Recurring must-fix patterns（索引）

Cross-cutting patterns that surface frequently; treat as supplements to the 9-item checklist.
Full rationale and recipes in `references/recurring-patterns.md` — read it when a pattern applies.

- **Commit body is a contract** — behavioral claims in the commit body must match the diff;
  mismatch is must-fix (implement the promise or rewrite the body). Details: `references/recurring-patterns.md`.
- **PR title/description is a contract** — behavioural/scope claims in the PR title or
  description must match the actual diff; mismatch is must-fix or nit depending on whether it
  would mislead reviewer judgment. Details: `references/recurring-patterns.md`.
- **Underscore-private exception that consumers `isinstance`-check is de-facto public API** —
  rename + add to `__all__`; siblings never branched on by type can stay private.
  Details + Airflow case studies: `references/recurring-patterns.md` and
  `skills/airflow-aware/references/review-checks.md`.
- **New public symbol must export at the same surface as its siblings** — a new
  Enum/class/type consumed by a user-facing kwarg must be reachable from the same
  top-level import as the sibling class that uses it; missing `__all__` / lazy-import
  entries is must-fix, not nit. Details: `references/recurring-patterns.md`.
- **不要框框式區段分隔註解** — `# ----` / `# --- 區段名 ---` 全刪含 label，靠函式邊界與空行分段。
- **Concurrent PR 根本修法優先** — 有 SDK 層根本修法時肯定當前解但明確指向根本修法，說明 supersede 關係。
  Details: `references/recurring-patterns.md`.
- **Naming: by what it is, not its first caller's use case** — a name coupled to one caller's context misleads and blocks reuse; generalize it.
- **Naming: private helper name carries the domain noun** — behavioral qualifiers ("once", "dedup") go in the docstring, not the name.
- **Naming: guard-then-hook pairs use two distinct verbs, not an underscore** — check for an existing same-file pairing convention before naming; collapsing to `x`/`_x` when the file's other pairs use two verbs reads as confusing, not idiomatic. Details: `references/recurring-patterns.md`.
- **State the rule, don't enumerate a code-derived set** — a comment/docstring listing "all the other X" goes stale as the set grows; require the rule itself. Hitting the same incomplete-enumeration defect a second round is a signal to change approach, not add the N+1th member.
  Details: `references/recurring-patterns.md`.
- **A PR that adds, removes or reorders calls inside a function: run the existing tests that assert on that function's mocks** — not only the tests the PR touched. Details: `references/recurring-patterns.md`.

## Design integrity checks（索引）

Cross-cutting patterns that surface on framework/base API work and rebase workflows;
details and recipes in `references/design-integrity.md`:

- **Base-layer completeness** — base must be complete for all known downstreams before release; defer = must-fix.
- **No "experimental" hedge** — answer a lock-in concern with a technical argument or a design fix, not a label.
- **Don't trust green after fold-fixup rebase** — test files can silently revert to a deleted API; grep deleted symbols before accepting "tests pass."
- **Prefer polymorphism over type-switching in the caller** — an `isinstance` chain or type-flag branch in the caller is a signal to push behavior onto a base-class method instead; don't extend the switch with a new flag.
- **Fix at the owning layer** — a defect in behavior owned by an upstream module/library gets an upstream option or callback, not a downstream workaround; details in `references/design-integrity.md` Part L.
- **External tools are optional and runtime-detected** — detect the binary, don't add a hard dependency; fallback must not leave the user with neither path; extension of Part E.
- **Type-pairing guards compare declared attributes** — never use "is this method overridden" as a proxy; one `is not` comparison on a declared attribute of both sides (Part M).
- **Name a counterpart symmetrically** — `upstream_x` / `downstream_x`, not `upstream_x` / `fine_x`; sibling classes share the vocabulary (Part N).
- **Close a framework-internal sum-type structurally, not visibly** — an encoder-level allowlist, not `ABC` / "do not subclass" text (Part O).
- **Version-skew tolerance at the client/transport boundary** — not by relaxing generated models or raising the dependency floor (Part P).
- **Normalize partial helper data at its source** — a variant of the owning-layer rule in Part L.

## Review judgment: when NOT to flag（索引）

Thirty-one principles for calibrating whether a finding is a real must-fix
and how much change a comment warrants; details in
`references/review-judgment.md`:

- **Verify repo config first** — grep linter config + sibling files before flagging a PEP / textbook rule.
- **Don't escalate coverage gap to correctness bug** — verify reachability + not-by-design (and blast radius — a removed guard isn't automatically must-fix) before calling it a bug.
- **Don't adopt regression framing uncritically** — verify the claim against HEAD; reply-only may be correct.
- **Proportionality** — COMMENTED nit does not justify a cross-hierarchy refactor; do the minimum proportionate change.
- **Don't flag squash-before-merge history** — pre-merge commit count / fixups vanish on merge; flag content violations, not history shape.
- **Prove a security/authz guard is load-bearing by removing it** — delete the guard, run the security test, confirm the flip, then restore.
- **Ground scope claims in the actual checker** — run the linter/hook and quote its output; never extrapolate a count from a raw grep.
- **A "minimize changes" instruction never licenses keeping a disproven fact** — fix the wrong token, keep the rest minimal.
- **Prefer conforming new code to an existing checker over extending the checker** — a local annotation fix beats a cross-cutting change to checker logic.
- **Verify installed-package evidence against the commit actually under test** — confirm the `.venv` matches the commit's lockfile and Python-version marker before citing package source.
- **Judge only the current/latest diff state** — commit history and prior review rounds are irrelevant to the verdict.
- **Don't silently overwrite a prior round's verdict** — a stricter new verdict needs discriminating evidence; surface conflicts to the user instead.
- **Verify a cited convention belongs to the same architectural layer** — a same-codebase precedent from a different layer is a category error, not support.
- **Calibrate naming-nit persistence by visibility** — one round then drop for private names; public API naming drift is worth pushing on. Exception: when the nit enforces a repo-documented naming convention (e.g. Airflow AGENTS.md's action-verb-prefix rule), private names don't get the one-round-then-drop treatment — the convention's own counter-examples are often private.
- **Verify a hard-limit claim before asserting "impossible" or "breaking"** — check release status and actual tool capability before foreclosing an option.
- **A reviewer's "strict / validate / enforce" wording may not match the schema** — check the underlying data model and sibling commands before implementing literally.
- **Don't demand a thin wrapper validate the wrapped library's own semantics** — and don't flag an eager-to-lazy init refactor as breaking without a concrete consumer signal.
- **Rank designs by the actual cadence of their cost path** — verify trigger frequency in code, not by feel; verify assumed costs too.
- **Verify a mechanism claim empirically** — write a small isolated repro before publishing a "why this works/breaks" explanation.
- **Trace the introducing commit before reverting a shared signature** — a type error at a changed signature's use site is usually an incomplete rollout, not a wrong change.
- **Trace the reconciliation/self-heal loop fully before characterizing a bug's severity** — a mismatch that self-corrects within one cleanup cycle is not the same severity as one that repeats forever; find the actual consumer/cleanup loop before writing the severity language.
- **Don't trust review-thread `isResolved` in either direction** — a resolved thread can be an empty self-resolve, an open thread can already be fixed; read the thread then verify against code before drawing either conclusion.
- **Re-review a rewritten claim by checking the carried-over clause, not the one you rewrote** — the clause reused verbatim from the flagged sentence gets no fresh scrutiny and is just as likely to still be wrong.
- **A reviewer's diagnosis being right doesn't make their proposed wording right** — verify the defect and the reviewer's replacement separately; rebuild the replacement from source before adopting it.
- **A reviewer's stated success criterion outranks nit severity** — a finding pointing at an unmet criterion the reviewer explicitly stated ("byte-identical", "no behaviour change") is must-fix even if the practical impact looks small.
- **When a must-fix asks for a test, derive the expected value from the contract, not the current output** — read the docstring/docs/changelog for what the behavior *should* be; if the contract and the implementation disagree, flag the disagreement itself as a finding instead of pinning current output as the test's expected value.
- **Check fallback paths before an absolute claim in a comment** — "never / can ever reach" gets refuted by a `TypeError` or env-var fallback on the call chain; trace it before writing or approving the claim. Details: `references/recurring-patterns.md`.
- **No repo-external note names in code comments** — a docstring or comment cites only facts verifiable in the repo and what breaks; a reference to an assistant memory entry reads as invented. Details: `references/recurring-patterns.md`.
