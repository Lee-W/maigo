# Strict Review — Design Integrity Checks

Loaded on demand by `skills/strict-review/SKILL.md` — **design-level review tasks**.
Read this file when reviewing a PR that introduces or modifies a public framework/base API,
or when a rebase + fold-fixup workflow is involved.

---

## Part A — Base-layer completeness: no deferred gaps

### Rule

When evaluating whether a base / framework layer API is complete, the criterion is
**not** "do the currently-named cases (e.g. Kafka/SQS) work?" but
"can every known downstream implementation be built *without coming back to change the base*?"

If even one plausible downstream (e.g. Azure Service Bus dead-letter, Pub/Sub nack) would
be forced to wait for a base change, that gap must be closed now — not deferred — because:

- Pre-release: closing it is additive and cheap.
- Post-release: closing it is a breaking change or a compatibility shim.
- A reviewer asking to remove a capability is **not** a reason to omit it from the base
  if other downstreams genuinely need it.

### Three-bucket triage for "deferred" items

| Bucket | Disposition |
|--------|-------------|
| True base gap — a known downstream cannot implement without changing the base | Close this round |
| Provider/adapter layer concern — not the base's responsibility | Out of scope for base |
| Physically impossible (e.g., exactly-once delivery guarantee) | Not a defer; explain why it is out of scope |

Only Bucket 1 items are must-fix.

### Precondition

This rule applies when the API is **not yet released** and the change is additive.
For already-released APIs, use a compatibility path — do not silently break callers.

### Concrete reference

PR #67523 (Airflow shared-stream ack channel): a reviewer requested removal of the
public `reject` signal. Kafka and SQS do not need it, but Service Bus dead-letter and
Pub/Sub nack require distinguishing "deliberate reject" from "involuntary failure."
The maintainer's directive was "all functionality must be present at the base layer this
round, no defers." Resolution: a token-free reject signal counted in `AdvanceOutcome.rejected`
was added so the base is complete for all four broker families.

---

## Part B — No "experimental" hedge on a design question

### Rule

When a reviewer raises a lock-in / hard-to-remove concern about a new public interface,
the correct response is one of two things:

1. **Technical argument** that the design is sound (it is optional, has a safe default,
   it is the right abstraction, it generalizes cleanly).
2. **Fix the design** if the argument cannot be made.

Do **not** propose labelling the interface as `experimental` to defer the question.

### Why "experimental" is not an answer

The `experimental` label transfers uncertainty to users without resolving the underlying
design question. It avoids committing to "this is right" or "this needs changing."
The maintainer expects a genuine design decision — commit to it or fix it.

### How to apply during review

When you see a proposed `experimental` label (in code, docstring, or PR description) as
a response to a lock-in concern:

1. Ask: is the design actually sound?
   - Is this interface optional with a safe default?
   - Is it the right abstraction for the problem?
   - Does it generalize to other known cases?
2. If **yes**: write the technical argument; remove or reject the `experimental` hedge.
3. If **no**: flag the design as must-fix and propose a concrete alternative.

No forward-looking "we might change this later" phrasing without a tracking issue
(see `strict-review`'s "No TODO evasion" item).

### Concrete reference

PR #67523: reviewer expressed concern that `get_advance_lane` would be hard to remove
once public. A draft proposed labelling it `experimental`. The maintainer rejected this
directly: "don't doc it as experimental." The fix was a pure technical argument:
partition-as-key does not fit the Kafka consumer-group model; `lane` is the correct
abstraction; the parameter is optional with a single-lane default.

---

## Part C — Don't trust green after a fold-fixup rebase

### Problem

An interactive rebase that folds `fixup!` commits into their parent, combined with manual
conflict resolution in test files, can silently **revert test files to a deleted API**
while leaving production code byte-identical. The result: review passes, CI is green,
but a later run surfaces `AttributeError: '<X>' object has no attribute '<dropped>'`.

### Why this happens

The conflict resolver picks the "wrong side" for a test file — usually the older pre-fixup
version — which references symbols that were intentionally removed. Production code is
unaffected because it was edited cleanly; only the test side had a three-way conflict.

### Diagnostic recipe (production code is the source of truth)

1. Grep deleted symbols in the test file:
   ```bash
   git grep '<deleted_symbol_name>' -- '**/test_*.py'
   ```
   Non-zero count = regression confirmed.

2. Confirm production is intact:
   ```bash
   git diff <pre-rebase-tip> HEAD -- <production_paths> --stat
   ```
   If production shows no unexpected changes, the regression is isolated to test files.

3. Enumerate test functions on both sides to find:
   - Tests present in both that were reverted to old API.
   - Tests present only in HEAD that may be revived duplicates of existing coverage.

### Repair procedure (restore whole file, don't hand-patch)

When production matches the known-good tip, that tip's test file is the correct baseline.

```bash
git checkout <pre-rebase-tip> -- <test_file>
# then re-apply any review-requested additions (new parametrize cases, renames)
```

Restoring the whole file is **deterministic and verifiable** (diff production to confirm).
Hand-patching four or more reverted tests introduces secondary errors and cannot guarantee
completeness.

Before discarding HEAD-only tests, confirm they are equivalently covered by the restored
baseline (grep assertion strings, check parametrize IDs).

### Review-time signal

On any branch that went through fold-fixup + conflict resolution:

- Do **not** accept "tests are green" as sufficient evidence.
- Run: `git grep '<known-deleted-symbol>' -- '**/test_*.py'`
  Any hit = must-fix. Point at this file for the repair procedure.

---

## Part D — Prefer polymorphism over type-switching in the caller

### Rule

When a caller does `isinstance(x, A)` or branches on a boolean type-flag
(`is_rollup`, `is_temporal`) to decide behavior, that's a signal to push the
behavior onto the objects instead — a method on the base class (sensible
default + per-subclass override/delegation) rather than a caller-side type
test.

Do **not** invent a new marker/flag (e.g. `is_fan_out`) to extend an existing
type-switch — that's doubling down on the anti-pattern, not fixing it.

### How to apply during review

When you see `isinstance` chains or type-flag branching added or extended in
a caller:

1. Ask: could this be a method on the base class instead, with each subclass
   providing (or delegating to) its own implementation?
2. If a reviewer's fix proposal adds a new flag to an existing type-switch
   rather than replacing the switch, flag it as still the anti-pattern — the
   fix should collapse the branching, not extend it.
3. Prefer designs where adding a new subclass requires **zero** caller
   changes.

### Concrete reference

An apache/airflow `partition_date` PR repeatedly had `isinstance`/`is_temporal`/
`is_fan_out` branching in the scheduler pushed back on during review ("fan out
is not doing something too special, why do we need special handling here
instead of a generalized solution?"). This drove the design to a single
`to_partition_date` method on `PartitionMapper` that composite mappers
(`Rollup` → its `upstream_mapper`, `FanOut` → its `downstream_mapper`, `Chain`
→ its last mapper) each delegate to — new mapper types then need zero caller
changes.
