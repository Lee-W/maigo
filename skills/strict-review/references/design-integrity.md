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

---

## Part E — Prefer pluggable registry abstractions over hardcoded type lists

### Rule

When a design has a fixed `if x in {"a", "b", "c"}` branch over a "kind"
axis (backend, provider, notifier, source), treat that as a signal the axis
should be a **pluggable registry** instead — a `register_<kind>()` call plus
a protocol/interface, so adding a new kind requires zero changes to the core
dispatch logic.

### How to apply during review / design

1. Flag a hardcoded enumeration of kinds (`if backend in {"x", "y"}`, a dict
   literal keyed by kind name baked into core logic) as a signal to propose
   a registry abstraction (protocol + `register_*()` + built-in
   registrations for the currently-known kinds).
2. **Generalizing must not change existing behavior.** Keep the existing
   per-kind test coverage; after the refactor, behavior for every
   already-supported kind must be provably unchanged (add a fake/unknown
   kind to a test to pin "the dispatch only looks at the registered kind,
   not a hardcoded name").
3. **The abstraction layer can exist before every concrete implementation
   does.** Even if a given platform/backend's concrete implementation isn't
   being written this round, the protocol/registry should still be put in
   place now — "no concrete impl yet, but the plug point exists" — so a
   future addition is pure registration, zero core changes.

### Concrete reference

A repeated design pattern across several review threads on the same
personal project: a liveness check that hardcoded a fixed set of process
names got rewritten as a `register_provider_procs()` registry so new
process kinds register themselves instead of the core file gaining another
literal; similarly, a notification path (OS-specific, macOS-only) was
generalized into a `Notifier` protocol + registry with several
platform-specific backends as built-in registrations — done specifically
so a future platform could register a new notifier with zero changes to
the calling code, even though no second platform was being implemented
that round.

This complements Part D above (polymorphism over caller-side type-switching)
— Part D is about *pushing behavior onto existing types*; Part E is about
*making the set of types itself open for extension* via registration rather
than a hardcoded enumeration.

---

## Part F — `None` on an optional parameter always means "use the default"

### Rule

Within one constructor/function signature, `None` on every optional parameter
must mean the same thing: "use the default." Don't let one parameter's `None`
secretly mean "disable this behavior" while its siblings' `None` means "use
the default" — that asymmetry isn't visible from reading the signature or the
parameter list, only from reading the implementation.

To offer a way to disable a behavior, add a **separate, explicit boolean
flag**. When the flag and the disabled-via-`None` parameter are both supplied
and contradict each other, `raise` at construction time (matching the
constructor's existing eager-validation style) — don't let one silently win.

This escalates from "style" to "must-fix" whenever the parameter in question
gates masking, encryption, or signature verification — a silent wrong-default
in that class of parameter has a security consequence, not just a surprising
API.

### Concrete reference

apache/airflow PR #70830 (`common.ai` provider's `LLMRetryPolicy`):
`redactor=None` originally meant "turn off secrets masking," while the same
`__init__`'s `model_id` / `instructions` / `fallback_rules` all treated `None`
as "use the default." Building kwargs programmatically (`redactor=cfg.get("redactor")`)
would silently send unmasked exception text to an external LLM provider whenever
that config key was absent — no exception, no log, the data already sent. Fix:
`None` went back to meaning "use the default"; disabling moved to a dedicated
keyword-only `redact_exception: bool = True`, and supplying `redact_exception=False`
together with an explicit `redactor` raises `ValueError` at construction.

### How to apply during review

1. When a new optional parameter is added (or reviewed), check what `None`
   means for its siblings in the same signature — match that meaning.
2. If the intent is "allow turning this off," that's a separate boolean flag,
   not an overloaded `None`.
3. When the flag and the parameter can be specified together and disagree,
   require a construction-time `raise`, not a silent precedence rule.
4. Treat this as must-fix, not nit, whenever the parameter gates masking,
   encryption, or signature verification.

---

## Part G — Error messages must name the flag the user actually typed

### Rule

When one validation path can be reached by multiple distinct user-facing
inputs (e.g. several CLI flags that all normalize into the same internal
field), the error message must name the input the user actually typed — not
the internal field name those inputs get normalized into. Hardcoding the
normalized field's name into the message is a defect once more than one
surface input can trigger the same check.

### How to apply during review

1. Watch for the shape "multiple flags normalize into one internal field,
   then a shared validation function hardcodes that field's name into its
   error message."
2. Ask: "does this error message stay honest about the user's actual input
   across every path that can trigger it?"
3. The fix is to thread through which surface input triggered the check (e.g.
   a boolean recorded at the point where the expansion happens) and branch the
   message accordingly — not to pick one alias's name and apply it everywhere.

### Concrete reference

apache/airflow PR #69454, `airflow-core/src/airflow/cli/commands/partition_command.py`'s
`clear()`: `--date a~b` expands into `args.start_date`/`args.end_date`
internally, and the inverted-window guard unconditionally reported
"`--start-date` must be on or before `--end-date`." — naming a flag the user
calling `--date` never typed. Fix: record a `from_date_flag` boolean at the
point of expansion, and branch the guard's message on it (the `--date` path
quotes the original input fragment; the direct `--start-date`/`--end-date`
path keeps the original message).
