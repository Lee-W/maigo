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

### Extension: external tools are optional and runtime-detected

Part E covers structure *inside* the codebase. The other half is dependencies
on *external* tools (a CLI or binary the project can use but doesn't own).

**Rule**: integrate an external tool as an optional capability, detected at
runtime — `shutil.which("tool")`; present → use it, absent → fall back
gracefully. Do not add it to hard dependencies, do not bind it to the same
virtual environment, do not pin its version.

**Why**: a tool distributed as its own standalone uv tool lives in its own
venv, so `import`ing it from the host project's venv can't work anyway;
detecting the binary and passing through over a subprocess needs zero Python
dependency and works with existing installs. It also keeps the two products
decoupled (independently upgradable) and degrades cleanly on a platform where
the tool doesn't exist, instead of crashing.

**How to apply during review / design**:

- Flag an `import` of an external tool, or a new entry in dependencies for
  it, when detection plus subprocess would do.
- **The fallback must not leave the user with neither path.** If the config
  selects backend X but X isn't installed, fall back to a backend that still
  delivers the outcome (e.g. a notification still appears) — not a state
  where the preferred path is missing and the fallback is silent. This comes
  from the abstraction layer's availability check plus fallback, not from
  detection magic.
- **The switch stays explicit**: one clear config value drives the behavior.
  "Binary detected, so behavior silently changes" is implicit coupling; reject
  it.

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

## Part H — Relaxing required fields breaks Union discrimination

### Rule

Using "make a required field Optional / give it a default" as a
version-compatibility tolerance measure breaks discrimination for any
`BaseModel` appearing as a Union member. Pydantic's smart union picks a
member by whether the payload *fits* it; a model with every field optional
fits everything, so it silently swallows a wrong-shaped payload and returns
an empty node instead of raising.

### How to apply during review

1. Before accepting "relax required → Optional" as a version-skew fix, check
   whether the model appears as a member of any Union with **≥2 non-`None`
   members**. Only single-member Optionals (`X | None`) are safe to relax.
2. Ask for the actual distribution first — quantify how many fields/models
   are Union members before deciding scope; a small count can justify a
   blanket exemption rather than a targeted one.
3. Reject "recursion" or "cycle guard" as the root cause without a minimal
   repro that actually removes recursion and still reproduces the bug — the
   real cause is usually the relaxed Union member itself, not the traversal
   that reaches it.
4. The fix trades "loud failure on a missing field" for "no silently wrong
   data" — that's the right trade, but it must be written down as an
   explicit consequence, not silently accepted.

### Concrete reference

apache/airflow airflowctl's backward-compat layer for an older API server:
recursively relaxing generated datamodels' required fields to
`X | None = None`. Minimal repro
`PartialAssetExpressionAsset.model_validate({"any": [{"asset": {"name": "n"}}]})`
returns `asset=None` with no error raised — no recursion involved.
`DAGDetailsResponse.asset_expression` is a 5-member Union; one missing
nested field collapses the whole `any` subtree into an empty `Asset` node.
Fix: skip rewriting any annotation that is a Union with ≥2 non-`None`
members (170 models total, only 9 fields qualified). The more durable fix
is adding a `Discriminator` to the Union so pydantic doesn't have to guess.

## Part I — A shared prefix on a searchable field has blast radius

### Rule

Adding a field into search matching requires checking whether its values
share a common prefix/suffix across all items. Indexing the full string
lets any substring of that shared prefix match everything — even a query
that used to be discriminating. The fix is to index the string with the
shared portion stripped, and compensate on the **query side** by stripping
the same prefix from user input.

### How to apply during review

1. When a PR adds a field to a search index/comparison, ask: "do all (or
   most) values of this field share a prefix or suffix?" If yes, demand a
   full-corpus before/after comparison, not a diff-fragment spot check.
2. The comparison must count **lost** (previously findable, now not),
   **gained**, and the change in **zero-result query count** across every
   real value in the corpus — and **lost must be 0**.
3. Check every entry point that builds the index, not just the one the
   reviewer pointed at (e.g. a DOM-side filter and a separate build-time
   search-index generator are two different sites that both need the fix).
4. If the final implementation doesn't follow the reviewer's literal
   suggestion, the reply must give a concrete counterexample (which input,
   what it became, why the literal suggestion misfires) — not silently do
   something else.

### Concrete reference

apache/airflow registry (PR #70498): search didn't mirror the id half of
the build-time searchable-values collection, so ids like
`clickhousedb`/`cncf-kubernetes` weren't findable from themselves, and the
full distribution name printed under the card title wasn't findable at
all. The naive fix (index the printed distribution name) failed under
test: `apache` went from matching 18 cards to matching all 105, `airflow`
from 2 to 105. Fix: index `provider.id` as-is, add `normalizeSearch()` to
strip the `apache-airflow-providers-` prefix from the query. Both the DOM
filter and the build-time Pagefind index generator needed the fix — the
reviewer had only pointed at one.

## Part J — An additive prop's "default path unchanged" claim must cover DOM attributes

### Rule

When a shared component gains a new prop with a default value, and the PR
claims "the default path has zero behavior change," the verbatim comparison
must extend to DOM attributes, not just logic branches and layout. A newly
added `data-testid`, `aria-*`, or `role` that isn't gated on the new prop
means the default path *was* touched — even if no test currently asserts
on it and nothing looks different on screen.

### How to apply during review

1. When a diff claims "added a prop, default value keeps current behavior,
   other call sites unaffected," ask specifically: "does this diff add any
   attribute on the shared path, gated or not?"
2. An unconditional new `data-testid`/`aria-*` addition inside a shared
   branch is a defect regardless of whether any test currently observes it.
3. The fix is conditional rendering — e.g.
   `data-testid={isNewMode ? "…" : undefined}` — so the unset case renders
   with zero added attributes, restoring the pre-change DOM verbatim.
4. Decide and pin down the semantics of any new testid with a test (does
   the boundary item count as "in" or "out") rather than letting two
   different meanings share one testid.

### Concrete reference

apache/airflow backfill partition preview: `LimitedItemsList` gained an
`orientation` prop (default `"horizontal"`); the "+N more" expand logic
was extracted into a shared `expandAffordance`. The remaining-items === 1
branch got an unconditional `data-testid="limited-items-item"`. A
whitespace-normalized diff had verified the separator logic and layout
were verbatim identical — the attribute-level gap wasn't caught by that
comparison. Consequence: four untouched call sites gained an extra DOM
attribute when down to exactly one remaining item, and in vertical mode,
at exactly `maxItems + 1` items, the capped item and the overflow item
shared the same testid.

---

**Common shape across Parts H–J**: all three PRs claimed "the default path
is unchanged" while actually leaving a breach in a shared path — a Union
member that fits anything, an index entry that matches everything, a DOM
attribute that renders unconditionally. Reviewing a "default path
unchanged" claim means actively looking for where the shared path picked
up new reach, not just confirming the branch you expect wasn't hit.

---

## Part K — A broad catch-all is only for someone else's failure

### Rule

A catch-all exception written for resilience is judged by **whose failure
it is**, not by how important the surrounding code looks. Someone else's
failure can be swallowed — a failover member's label can't be parsed, but
that label isn't the precondition for calling another member, and the
member's own exception tree can't be enumerated anyway. A component's own
failure must not be swallowed — when its own identity or config is broken
there is no sibling to fall back to, and swallowing it just turns a
subclass's bug into a one-line warning plus an `"unknown"` tag, on a call
that had nobody left to serve it anyway. Let it raise.

Orthogonal to this: a control-flow exception must be re-raised regardless
of how broad the catch is. A control-flow signal (e.g. a retry signal) that
subclasses `Exception` will get silently swallowed by any `except
Exception`, while other parts of the same module assume it always
propagates — the two assumptions contradicting each other is the bug.

### How to apply during review

- On any catch-all used for observability/label/metrics purposes, ask
  "whose failure is this value's parse failure — who has a fallback for
  it?" No answer → it shouldn't be swallowed.
- Write the helper's docstring as "for reading someone **else's** X only,"
  so the next caller doesn't point it at its own state.
- Scan the same module for any control-flow exception that this broad catch
  could intercept.

---

## Part L — Fix a defect at the layer that owns the behavior, not downstream

### Rule

When a behavior is wrong, first locate **who owns it**, then fix it there. If
the gap is in a plugin / CLI / library the same maintainer owns, the right fix
is an option or callback upstream — not a parallel timer / watcher / wrapper
written in a downstream config file.

Cost of the downstream workaround: logic scattered in the wrong place; a
duplicate implementation once upstream adds official support; nothing other
consumers can reuse; and a downstream config that slowly grows into an
unmaintained mini-plugin.

### How to apply during review / planning

- In a diff, ask of any new helper in a config or glue file: "does this
  reimplement a behavior another module owns?" If yes, ask why the owning
  module wasn't changed.
- **Treat your own hesitation as the signal.** If the author (or you) has
  already said "this would be cleaner upstream", that's the cue to change
  course, not to finish the downstream version anyway.
- Dead code left behind by an approach that didn't work is removed on the
  spot, not left in the file for someone else to find.

### Variant: a helper that returns partial data — normalize at the source, not at each caller

When a helper returns a partial structure on a failure path (`{}`, `None`, a dict missing keys),
complete the shape **inside the helper** rather than letting every caller `.get(key, default)`.
Scattered defaults drift apart: the caller that forgets one is the bug, and because its neighbours
did supply defaults it looks deliberate rather than missed.

Case: a `_resolve_ref()` helper returned `{}` on failure; four callers handled it — three with
`.get(k, default)`, one with a bare `.get(k)`. That one printed a failover warning reading
`Agent None on None failed; failing over to None` — exactly the line the docs tell operators to read
to find the broken member. The fix normalized in the helper on **both** the success and failure
paths, and the four callers now index directly.

Two traps:

- **Fixing only the failure branch is not enough.** If just the `except` returns a sentinel and the
  success path is passed through unchanged, a "didn't raise but returned a dict missing keys" hole
  stays open — and deleting the callers' defaults then becomes a `KeyError`, worse than the
  original bug. Normalize both paths or keep the caller defaults; never half of each.
- **Normalizing is not swallowing.** In `ref = _normalize(obj.attr)` the argument is evaluated
  before the call, so a raise propagates unchanged. Surfacing what is deliberately broken while
  degrading what someone else broke can coexist.

---

## Part M — Type-pairing guards compare declared attributes, never "is method overridden" proxies

### Rule

When guarding a constraint between two paired objects (e.g. two mapper classes that must decode to
the same type), compare a **declared attribute** on both sides with a single equality check — do
not use "is this method overridden" as a proxy for the property you actually care about, and do not
write two directional/mirrored branches with duplicated messages.

Why: an override-based proxy encodes an assumption about *why* someone overrides a method — an
override can still return the same type, producing a false rejection. A declared attribute states
the contract directly, and a symmetric mismatch check is one comparison
(`if a.expected_type is not b.expected_type: raise`), not two mirrored branches.

### How to apply during review

When guarding a pairing constraint, add the declared-attribute contract to **both** sides of the
pair (if the pair spans two packages, both packages), and write a single `is not` comparison. If one
side already has the declared attribute and the other doesn't, add it to the missing side rather
than working around the gap with an override check.

If review raises the "two definitions need to stay in sync" concern (two hand-maintained field-name
sets, a TypedDict beside a response model), point at an existing automated sync check in the repo
as the concrete pattern to replicate, rather than suggesting "this should be automated somehow" in
the abstract.

---

## Part N — Name a parameter's obvious counterpart symmetrically, not descriptively

### Rule

When a class already has one half of an obvious pair as a parameter/field/method name, name its
counterpart symmetrically rather than reaching for a role-descriptive label — prefer
`upstream_mapper` / `downstream_mapper` over `upstream_mapper` / `fine_mapper`. Symmetric naming
makes the pairing explicit at the call site and in docstrings.

This also applies **across sibling classes**, not just within one. If one mapper class uses
`upstream_mapper` / `downstream_mapper`, a structural sibling class should use `upstream_mapper` for
the same role — not a vague near-synonym like `source_mapper`. Cross-class naming drift forces the
reader to learn two vocabularies for the same concept and obscures that the classes are sibling
compositions.

### How to apply during review

Reach for descriptive names only when pair members truly play different structural roles
(`upstream_mapper` + `window` is fine because they aren't the same kind of thing; `upstream_mapper`
+ `fine_mapper` is not, because both are mappers). Applies equally to method names and attribute
names, not just `__init__` kwargs — and a serialized (wire-format) shape follows the same renames.

---

## Part O — Close a framework-internal sum-type / policy object structurally, not visibly

### Rule

A framework-internal sum-type / policy object (a small closed set of builtin strategy classes
consumed by a hot loop) should be **"low-key closed"**, not hard-enforced with visible machinery.
Structural close — an encoder/serializer that rejects anything outside a `BUILTIN_*` allowlist — is
the actual enforcement. Visible signals like `abc.ABC` / `@abstractmethod` / `__init_subclass__`
raising / a `NotImplementedError` stub / an explicit "do not subclass" disclaimer are all **loud
"subclass me" signals** — they carry the same IDE-autocomplete/`help()`/docs-generator visual weight
as an invitation to extend, whether the words say "subclass me" or "don't subclass me". A clean
user-facing interface (a plain base class, no methods, a docstring describing only behavior) plus
structural rejection at the encoder layer is more durable than a text warning, especially for a
hot-loop extension point (scheduler tick, poll loop, request handler) where any DB query or network
call a user smuggles into an override degrades throughput.

### How to apply during review / design

- Keep the user-facing base a plain class with no methods; the docstring describes only observable
  behavior.
- If a type checker forces a method stub, keep the stub on the internal side the user never imports.
- Reject non-builtin instances structurally at the encoder, via a `BUILTIN_*` allowlist plus a
  dedicated `NotSupported`-style exception.
- Don't write "extend / subclass to / extension point / pluggable" in the docstring — and don't write
  "do not subclass" either; both are the same kind of loud signal.
- Don't add `__init_subclass__`-style runtime hard-enforcement — it's heavier than the encoder-level
  reject and still advertises the extension point.

---

## Part P — Version-skew tolerance belongs at the client/transport boundary, not in generated models

### Rule

When a versioned client (an SDK talking to a service API) hits a missing field because the server is
older than the client's generated models, the fix is **not** to relax the generated model's
`required` declaration to make the field optional.

Why: a generated model faithfully reflects the contract of the spec version it was generated from —
those fields really were required in that version; the codegen didn't mis-mark them. Relaxing them
to optional has two costs: (a) it also drops validation for a version-**matched** server, sacrificing
a correct check to accommodate a mismatched one; and (b) the model then misrepresents its own
version's contract from that point on. The actual problem is a version mismatch between client and
server, not an error in the model definition.

### How to apply during review

Put compatibility tolerance at the **call site / transport boundary** (e.g. the response-validation
step in the client's operations layer), never in the model definition or codegen template. Keep the
tolerance as narrow as possible — catch only the specific error shape a version skew produces (e.g. a
pydantic `ValidationError` where `error["type"] == "missing"`), re-raise everything else, and log the
synthesized field so the fabricated value leaves a trace. The same judgment applies to any
client/server pair with independently-versioned generated models on each side.

### Extension: the dependency floor

The same principle governs the **dependency floor**. When a drift tripwire — a test that derives what
the package can reach from what is actually installed — fails on a low-dependency CI job because the
declared feature set names things a newer upstream release introduced, raising the package's own lower
bound is the wrong fix: it forces every downstream user to upgrade so that a documentation page reads
complete. Absorb the skew in the layer that knows about it. Assert the direction that holds on every
supported version (anything installed must be declared) unconditionally, and gate the opposite
direction (anything declared must exist upstream) on the release that carries the whole declared set,
naming that release in a constant so the next reader sees which version the list was derived from.
Prove with a mutation canary that the unconditional direction is still red when something is
genuinely missing — a gate that silently disables both directions is not a tripwire. (Case: a vendor
listed in the declared set landed upstream in a release newer than the package's supported floor,
while CI exercises that floor.)
