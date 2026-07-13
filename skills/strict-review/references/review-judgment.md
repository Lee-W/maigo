# Strict Review — Review Judgment Principles (Extended)

Loaded on demand by `skills/strict-review/SKILL.md` — **twenty principles for when
NOT to flag, how to calibrate response size to comment weight, and how to verify
a claim before escalating or reverting it**.
Read this file when you are deciding whether a finding is a real must-fix or a
false positive, and when choosing how much change a comment warrants.

---

## 1. Verify repo config before flagging a textbook / PEP rule

Do not open a must-fix based on a PEP or textbook rule alone. First confirm both:

(a) the linter / type-checker config (`pyproject.toml [tool.mypy]` / `[tool.ruff]` /
`setup.cfg`) actually enforces the rule — many "PEP-required" behaviours are off by
default (e.g. mypy `implicit_reexport`);

(b) grep the file and its siblings — if unchanged code already violates the rule without
anyone flagging it, the rule is not enforced in this repo.

Both conditions must hold before upgrading to must-fix.

Rules that are both listed in the ruff config (RUF / B series) and run in CI
can be flagged without per-PR manual grep — the tooling already enforces them
and the developer's editor will have caught them.

---

## 2. Do not escalate a coverage gap to a correctness bug

"This case has no test" must not be promoted to "this is a correctness bug"
until you have verified from the actual code that:

- the case is **reachable** in production, and
- it is **not by design** (no deliberate guard, no documented out-of-scope decision).

Read the caller / class hierarchy before stating the finding. If the case is
unreachable or by design, the observation is at most a docstring nit, not a bug.

Be prepared to **fully retract** the finding if the code proves you wrong — do not
repackage the same claim under a different framing to save face.

**Removing a defensive guard is not automatically must-fix.** Before escalating
"a guard was removed" to must-fix / BLOCKED, also weigh **blast radius**, not
just reachability. A guard often only ever protected an out-of-contract input;
if no in-tree caller and no in-contract default can reach the bad path, removing
it changes nothing observable. Blast radius matters too — a recoverable
log-view 500 for a contract-violating third-party plugin is not the same class
as data corruption or a security hole. Check the default return value,
enumerate in-tree callers/implementations, and read the type contract before
blocking; if only a contract-violating input reaches it and the failure is
recoverable, downgrade to nit/observation.

---

## 3. Do not adopt a reviewer's regression framing uncritically

When a reviewer says a change is a regression and proposes a revert, that is a
**claim**, not a specification. Before agreeing to revert:

1. Verify whether the change in question is an intentional fix (not a careless
   break).
2. Verify whether the reviewer's premise still holds against HEAD — the branch
   may have moved since the comment was written.

If the change is intentional and the premise is stale, the correct response is
usually **reply-only** (explain why it is correct), not a code change. Reverting
a valid fix to close a thread is worse than leaving the thread open.

---

## 4. Proportionality: match response size to comment weight

A `COMMENTED` (non-blocking) suggestion ("using X would be simpler") does not
justify a cross-file or cross-hierarchy refactor. Ask: "what is the minimum
proportionate response?"

Steps:

1. Is the comment blocking (REQUEST_CHANGES / BLOCKED) or advisory (COMMENTED /
   nit)?
2. What is the smallest change that genuinely addresses the concern?
3. Do that change — no more.

If the larger refactor is genuinely worth doing, cut it into a separate follow-up
PR or issue and reference it in the reply. Do not fold it into the current PR to
look thorough.

---

## 5. Do not flag squash-before-merge history issues

If the repository merges via squash-and-merge (as many open-source projects do),
the pre-merge commit history has no bearing on what lands. Do not flag:

- "messy history"
- "fixup commits"
- "squash before merging"
- commit count

These are pre-merge artefacts that vanish on merge.

**Still flag as must-fix**:

- Commit messages that contain content violations (e.g. a forbidden
  `Co-Authored-By: <agent>` line, or a body that misstates the scope of the
  change) — these are content problems, not history shape problems.

---

## 6. Prove a security/authz guard is load-bearing by removing it

When pushing back on a reviewer's "this code path isn't hit / this is dead
code" comment about a security or authorization guard, prove the guard is
load-bearing empirically — temporarily delete it, run the relevant security
test, confirm the result flips (e.g. `403` → `200`), then restore the guard.

A static argument ("removing this makes an empty-list check vacuously true,
so it's a bypass") is persuasive but not as convincing as demonstrating it.
The reply should carry "verified: removing it flips
`test_unauthorized_returns_403` to 200" instead of a chain of asserted
call-graph behavior.

How to apply: edit out the guard, run the authz/security test, observe the
flip, then restore the guard (e.g. `git checkout HEAD -- <file>`). This
extends the "verify empirically" instinct from DB/library WHY-claims to
authorization defenses specifically — and it's also how to avoid adopting a
reviewer's framing unchecked (see §3 above): demonstrate, don't just argue.

---

## 7. Ground scope claims ("N other similar issues exist") in the actual checker

Before claiming "there are N other similar issues" in a fix or PR summary,
run the actual checker (linter, type-checker, custom hook) and quote its
output. Never extrapolate a countable scope claim from a raw `grep` pattern.

A `grep` for a superficial pattern (e.g. a config key name) can massively
over- or under-count real violations if the actual checker has narrower
semantics (e.g. it only walks a specific AST node type, or only applies
under a specific decorator). The actual tool defines what counts as a
violation — a grep pattern is only a hint.

How to apply:

- If a checker exists for the issue → run it and quote its output verbatim.
- If no checker exists → state explicitly "based on grep, may include false
  positives" rather than presenting the count as authoritative.
- Applies to `/maigo:fix` summaries, `/maigo:review` findings, and PR
  descriptions — anywhere a countable scope claim is made.

---

## 8. A "minimize changes" instruction never licenses keeping a disproven fact

When something has been empirically verified (e.g. via checking release tags
that a symbol was introduced in a specific version, absent from every prior
release), a later "don't change existing content too much" instruction — or
even the user's own earlier assertion to the contrary — does not justify
preserving the wrong wording.

Minimal-diff discipline and deference to the user's framing are about *style
and scope*, not *truth*. Burying an established fact to shrink a diff, or to
match a stated preference, just forces a re-correction later and erodes
trust in the verification step.

How to apply: when a minimize-changes constraint collides with something
already verified to be wrong, change exactly the incorrect token and nothing
else, and add one line explaining why that single change is non-negotiable.
Don't silently conform to someone's framing when the evidence contradicts
it — surface the conflict instead of hiding it inside a "kept it minimal"
diff.

---

## 9. Prefer conforming new code to an existing checker over extending the checker

When new code makes an existing AST-based lint/sync checker blind to a
field/attribute it used to detect, the default fix is to change the **new
code** to match the checker's existing detection convention (e.g. add a type
annotation the checker's AST walk already looks for), not to extend the
checker's detection logic with a new fallback path.

Reasoning: changing checker logic has cross-cutting side effects (it affects
every other class going through the same rule), while conforming the new
code is a local, predictable change.

Case study: apache/airflow's `check_partition_mapper_defaults_in_sync.py`
walks class-body `AnnAssign` nodes to compare mapper fields between core and
SDK. When `FixedKeyMapper` was rewritten with a manual `__init__`, the
checker stopped detecting its `downstream_key` field. The fix was to add a
`downstream_key: str` class-body annotation to `FixedKeyMapper` (mirroring
how `PartitionMapper.max_downstream_keys: int | None = None` is already
declared) rather than teaching the checker's `extract_class_field_names` to
also parse `__init__` parameters as a fallback — the annotation-only fix let
a prek-hook workaround be fully reverted.

---

## 10. Verify installed-package evidence against the commit actually under test

Before citing "the source code of an installed package" as evidence for a
mechanism claim, confirm that installation matches the **lockfile and
runtime environment of the commit actually being verified** — not just
whatever's in the host's `.venv`.

Two traps:

1. The host `.venv` may have been synced against a different branch's
   lockfile entirely.
2. The same lockfile can resolve different package versions per Python
   version (marker-based resolution — e.g. apache/airflow's `uv.lock`
   resolves sphinx 8.1.3 for py3.10 but 9.1.0 for py3.12).

Checklist:

- (a) `git rev-parse HEAD` + `git status` to confirm the working tree is the
  commit under test.
- (b) Read dependency versions via `git show <commit>:<lockfile>` (a
  commit-object read, immune to what's currently checked out) rather than
  trusting the live filesystem.
- (c) Before citing external package source, confirm the actual resolved
  version for the runtime environment in play (including the Python-version
  marker) — if it doesn't match, go pull the correct version from PyPI/GitHub
  tags rather than reading the host `.venv`'s copy.

Case study: while investigating a PR #69445 docs-build warning, the first
pass cited Sphinx fallback code read from the host `.venv` (sphinx 9.1.0,
sphinx-argparse still at main's lockfile version 0.5.2), but the actual
reproduction ran under breeze `--python 3.10` against the PR's own lockfile
(sphinx 8.1.3) — the conclusion happened to still hold, but the evidence
chain had a hole that only got caught by someone asking "are you sure you're
on the right commit?".

---

## 11. Judge only the current/latest diff state — history is irrelevant to the verdict

Evaluate the current state of the diff on its own merits. Commit history, how
many rounds it took, "this commit addresses round-2 feedback", "prior
reviewers already covered X", and the back-and-forth in resolved threads are
all irrelevant to the verdict — the reviewer judges what will merge (the
final state), not how it got there.

Drop "prior review already addressed", commit-history nits ("messy commits,
suggest squashing"), and resolved-thread recaps from review output. Read the
current diff as if seeing it for the first time. When replying to a single
review comment, address the current code state, not the historical thread
discussion.

---

## 12. Don't silently overwrite a prior round's verdict on re-review — surface the conflict

When re-reviewing a PR that already has a review record from a prior round,
and this round's verdict **conflicts** with it (especially when this round is
*stricter*, e.g. prior round was NEEDS_CHANGES and this round wants to
escalate to BLOCKED), do not silently adopt the new verdict and overwrite the
old one.

A stricter new verdict must earn it with **evidence that can discriminate
between the two hypotheses** — if the new evidence is equally consistent with
the prior round's conclusion (e.g. a mutation test that can't distinguish
"code bug" from "test environment limitation"), it isn't strong enough to
overturn the prior finding. Surface the disagreement to the user: state both
rounds' verdicts and their respective evidence, and let the user pick which
stands. Record the dissenting round as an annotation, not as the final call.

---

## 13. Verify a cited convention belongs to the same architectural layer

Before justifying a design choice by appeal to "the codebase's convention",
confirm the convention comes from the **same architectural layer** as the
decision being made. A convention from one layer (e.g. task-execution-layer
retry/reschedule semantics) is not automatically a precedent for a different
layer's mechanism (e.g. a scheduler- or triggerer-side design question) — a
plausible-sounding convention cited from the wrong layer produces confident
but wrong design reasoning.

How to apply: before accepting "the codebase does X elsewhere, so this should
too", name the layer the decision actually lives in and check that the cited
precedent comes from that same layer (or the same module/component) — not
just anywhere in the codebase that happens to look similar.

---

## 14. Calibrate naming-nit persistence by symbol visibility

The bar for "must rename" scales with a symbol's visibility:

- **Private / narrowly-scoped names** (single-underscore prefix, narrow call
  sites within one class): high bar to insist on a rename. Offer one round of
  suggestion, then drop it if the author pushes back — repeating the same nit
  after pushback reads as noise, not diligence.
- **Public API** (exported symbols, user-facing kwargs, sibling-class parity):
  worth pushing on — naming drift there is a real, lasting cost to every
  caller.

When the author proposes an alternative naming/design, evaluate it on its
merits and switch to it plainly if it's better than the original suggestion
— don't restate the original just to defend having said it first.

---

## 15. Verify a hard-limit claim before asserting "impossible" or "breaking"

Don't state a hard limit ("X is impossible", "that would be a breaking
change") unless it has actually been verified. Inflating "not worth it /
shouldn't" into "can't / definitely breaking" misroutes the decision — it
forecloses an option that may genuinely be on the table.

How to apply before asserting infeasibility or breakage:

- *Breaking?* Check whether the symbol/signature is actually released (check
  release tags, not assumption). Unreleased → not breaking, free to change.
- *Impossible?* Check whether the tool/language genuinely can't do it, rather
  than assuming from a first attempt.

Frame advice as "feasible but not worth it" (with the trade-off stated)
rather than "impossible", unless the hard limit has actually been proven.

---

## 16. A reviewer's "strict / validate / enforce" wording may not match the underlying schema

When a reviewer asks for "strict" validation or rejection of some input,
verify the underlying data model / schema **before** implementing the literal
interpretation. Reviewers themselves often don't check the schema before
suggesting a fix, and a literal implementation can silently break a
legitimate use case the reviewer didn't have in mind.

How to apply: before implementing a reviewer's "strict / reject / validate /
enforce X" request, check (1) the underlying column type / data model, (2)
how sibling commands/endpoints handle the same input, (3) whether the
proposed strictness conflicts with any first-class use case. If it does, the
right fix is usually elsewhere (e.g. a different bug in how a boundary value
gets computed), not tightening validation on the wrong field.

---

## 17. Don't demand a wrapper validate semantics that belong to what it wraps

When reviewing code that thinly wraps a third-party client/library (e.g. a
provider hook wrapping an SDK), don't demand it re-validate constraints that
are the wrapped library's own responsibility (a required subdomain format, a
host-naming quirk, a valid-combination-of-options rule). The wrapper should
validate structural inputs it itself needs to not crash and any
platform-side contract it owns — not second-guess what the wrapped library
already validates.

Related: don't flag an eager-to-lazy initialization refactor (e.g. moving
connection setup from `__init__` into a `cached_property` / first-use path)
as a breaking change unless there's a concrete signal a real consumer depends
on eager validation (a test asserting `__init__` raises, a caller that
validates something before any method call). Instantiation is almost always
immediately followed by a method call, so the timing difference is normally
unobservable — treat it as a refactor, not a behavior break.

---

## 18. Rank competing designs by the actual cadence of their cost path, not by feel

When comparing two designs and one has a "cheap-looking" one-time cost (e.g.
a migration, a low-frequency endpoint change) while the other has a cost
embedded in a hot/frequently-executed path (e.g. a per-poll query, a
per-request join), verify the actual **trigger frequency** of that path in
the code (loop interval, heartbeat cadence, reparse interval) before ranking
— don't rank from a general sense of which change "feels" bigger. A once-a-
second polling loop's added join cost is a permanent tax; a one-time schema
migration is not the same currency, even if its diff looks scarier.

Also verify assumed costs before ranking on them — e.g. "information would be
lost" may not hold once the actual source of truth is identified (it may live
somewhere the design already reads from).

---

## 19. Verify a mechanism claim empirically before publishing the explanation

When explaining *why* something works or breaks — especially transaction
semantics, constraint enforcement, or other library-internal behavior — write
a small isolated repro and verify empirically before stating the cause.
Don't reason from documentation/spec quotes alone, and don't restate a claim
under pushback without re-testing it. A broad mechanism claim ("X is a no-op
inside a transaction, so Y always defeats it") can be wrong for a subset of
cases (e.g. pure DDL vs DML) that only a real test distinguishes.

How to apply: before writing a "why this works/breaks" explanation that
hinges on transaction state, autocommit semantics, ORM internals, or similar
library-internal behavior, run a small script that toggles each variable
separately and compare the reported state against the actual observed side
effect — they can disagree.

---

## 20. Trace the introducing commit before reverting a shared signature

When a type/lint error points at a use site referencing a **recently-changed
shared signature**, do not assume the signature change itself was wrong and
revert it. Read the commit that changed the signature first (`git log -L` /
`git show`) — the error usually means an **incomplete rollout** of an
intentional change: some call sites/implementations were updated to the new
contract, others were missed.

How to apply: (1) trace the introducing commit to learn the intended
contract, (2) identify which siblings already conform and which lag, (3)
align the laggards rather than reverting the signature. Then re-check every
consumer, not just the one where the error first surfaced — changing a
shared signature back can simply relocate the error to a different file.

---

## See also: parallel batch review safety

Read-only discipline for fanning out multiple PRs to parallel reviewers on a
**shared worktree** (no checkout, no stash, no test runs — runtime
verification is serialized separately) is covered in
[`skills/teammate-flow`](https://github.com/Lee-W/maigo/blob/main/skills/teammate-flow/SKILL.md#worktree-safety-in-parallel-batch-review)
rather than duplicated here — that's an operational safety rule, not a
judgment-calibration principle.
