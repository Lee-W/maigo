# Strict Review — Review Judgment Principles (Extended)

Loaded on demand by `skills/strict-review/SKILL.md` — **five principles for when
NOT to flag, and how to calibrate response size to comment weight**.
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
