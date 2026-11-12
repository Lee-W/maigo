# Airflow design-integrity conventions (framework / base API design)

Loaded on demand by `skills/airflow-aware/SKILL.md` — **Airflow-specific** design-level conventions
for hot-loop extension surfaces (scheduler / triggerer / API request handler / Dag parser),
`Window` semantics, common.ai adapters, and the Airflow cases behind the generic rules. The generic
framework-design rules (type-pairing guards, symmetric naming, structural closing of sum-types,
version-skew tolerance, normalizing partial data) live in
[`skills/strict-review/references/design-integrity.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/design-integrity.md).
Read this file when designing or reviewing a new base/framework API on an Airflow hot loop.

Also here: Core ↔ SDK paired-class symmetry, CLI/REST design consistency, and partitioned / scheduling-range
API granularity (moved out of `SKILL.md`; the hard rule for each stays there).

---

## New extension surface on a scheduler/triggerer/API hot loop: two independent cost axes

Adding a user-extension surface to a framework hot loop (scheduler tick,
triggerer poll, API request handler, Dag parser callback) has **two
independent** scheduler-load dimensions — both must be answered, closing one
does not close the other:

1. **Per-call cost cap**: any user-overridable method on the extension point
   must be O(1) pure computation. A DB query, network call, unbounded loop,
   or file I/O on that path stalls the hot loop — including the framework's
   own builtin implementations, which must obey the same cap.
2. **Arbitrary user-logic risk**: even when every builtin implementation is
   O(1), an open (public, non-closed) extension surface lets a user subclass
   put arbitrary logic into it. The only reliable way to close this is a
   structural reject — an encoder/serializer `BUILTIN_*` allowlist plus a
   `<Foo>NotSupported`-style exception — not a loud disclaimer (Part O in the generic file).

How to apply: when evaluating a new callback / hook / policy object / event
filter / timetable extension on a hot path, answer both axes explicitly — (a)
is every builtin implementation genuinely O(1) (if not, don't expose it to
the hot loop, or cache/pre-compute); (b) does the subclass surface need
closing, and is the closing mechanism structural (Part O in the generic file) rather
than a comment. Don't assume closing one axis buys safety on the other — a
closed subclass surface doesn't stop a builtin method from being slow, and a
fast builtin method doesn't stop a user subclass from adding an N+1 query.

### A change on a per-call scheduler hot path ships with timing in the PR

When a PR changes code the scheduler calls on every evaluation (for example `CronMixin._get_next` / `_get_prev`, or a timetable's next-dagrun computation), the PR attaches before/after microseconds measured on the same machine with the same method (`timeit`), and says whether the new branch is reached on an ordinary day. A branch that looks rare can be the common case: in #75847 a maintainer measured `_get_next` at 2.6x slower because an hourly cron (delta exactly 1h) took the slow path all year; the fix had to bring it back to main's order of magnitude (about 40 µs).

---

## New `Window` subclass or direction: default to uniform semantics, not calendar special-casing

When designing AIP-76 partition fan-out `Window` direction semantics, prefer
a single uniform rule applied across every window type over special-casing
for calendar alignment — even when the uniform rule produces a
non-calendar-aligned result. The accepted rule is the *trailing period ending
at* the anchor — the half-open `(anchor - period, anchor]` — mirrored by the
*period starting at* the anchor `[anchor, anchor + period)`, with the anchor
as the last/first member respectively. This is deliberately accepted even
when it makes `WeekWindow(2024-03-04)` fan out `02-27…03-04` (Tue→Mon, not a
calendar week) rather than special-casing to align to the calendar week.

Direction-label update (a later review, addressing a reviewer's comment): the
enum labels were swapped to follow the time axis. This was deliberately not
aligned to the linked issue's literal wording; the author chose the
temporally-intuitive reading instead.

How to apply: when a new `Window` subclass or direction raises a "should this
align to a calendar boundary?" question, default to the rule that stays
consistent with the other windows (mirror / fixed-stride / anchor-as-boundary),
and only break uniformity when explicitly asked for calendar alignment.

---

## common.ai wraps vendor agent SDKs as adapters, not operators

When common.ai integrates a vendor agent SDK that brings its own loop, the shape is the adapter
family (`tools/strands.py`, `adk.py`, the anthropic adapter in #73962, `claude_agent_sdk`): the
loop stays with the Dag author; common.ai owns only the tool layer and its guarantees — secret
masker, correctable errors → `is_error`, any other failure → task failure, the
`common_ai.tool_calls` metric. Do not build an Airflow-maintained cross-vendor runtime abstraction
or an operator: that is what pydantic-ai already provides to `AgentOperator`.

Why: in apache/airflow #74026 a `HarnessOperator` / `HarnessBackend` design was challenged by a
maintainer and reshaped into an `AirflowTools` adapter.

How to apply: for a new vendor SDK, compare against the existing adapters' shape and guarantee
list; before proposing an operator, answer "what does it give that `AgentOperator` cannot?"

## common.ai toolset strings and released parameters

- **Hints use the toolset's own tool names.** Any string a model or user sees from a common.ai
  toolset — retry hints, `allowed_tables` rejection messages, conflict hints — must be built from
  that toolset's own (prefixed) tool names, never hard-coded bare names such as `list_tables`.
- **A released major is frozen: restore, don't remove.** Once a common.ai major is on PyPI, a
  minor release must not remove parameters. Restore the removed name as a deprecated alias
  (`warnings.warn(..., AirflowProviderDeprecationWarning, stacklevel=2)`) kept until the next
  major, and make the changelog name every class (hooks included) whose default changed.

## Provider public-surface compatibility: six checks for trigger / hook / operator changes

Scope: a diff that changes a provider's public trigger, hook or operator surface — signatures,
capability detection, new parameters, serialized payloads. Once a provider is at 1.0 its public
signatures are frozen, and already-serialized state (triggers queued on a triggerer, Dag hashes,
serde payloads written by the previous version) must keep working across a rolling upgrade. Check
each of the following; every rule has at least one reviewer-flagged instance in apache/airflow.

1. **A new parameter on a public trigger / hook signature has a default, preferably keyword-only,
   and an unused new feature leaves the call shape unchanged.** A required new parameter breaks
   triggers already deferred before the upgrade (`TypeError` on `cls(**kwargs)` against the old
   serialized kwargs; #65618). When the new parameter is not used, the call made into a
   third-party subclass and the serialized kwargs must be identical to the old version's — pass
   the argument only when it is not `None`, otherwise a subclassed `DbApiHook.get_records` that
   does not accept it raises `TypeError` (#76270). If the same change alters a contract such as a
   `TriggerEvent` status, treat it as breaking too and add a changelog entry. Check: (a) does every
   new parameter have a default; (b) can an old serialized kwargs dict still rebuild the trigger;
   (c) with the feature unused, is what reaches third-party subclasses byte-for-byte the old call.
2. **Detect capability with an explicit class attribute, not method or object identity.** Declare
   it as `supports_async_execution = False` and let the subclass flip it to `True`, following the
   existing `supports_autocommit` / `supports_executemany` pattern on `DbApiHook`. An identity
   test such as `type(self).aget_conn is not DbApiHook.aget_conn` misfires under mixins,
   decorators and intermediate abstract bases (#65618), and `self.selector is not _first_cell`
   breaks for a user who passes `itemgetter(0)` or a deep-copied sensor (#76270). On seeing
   `is not <default function/object>`, ask "can the subclass just declare the capability?"; when
   the identity check stays, add tests for an explicit argument equal to the default, a
   `copy.deepcopy`, and the constructed result after `expand`.
3. **New parameter and method names reuse the repo's vocabulary; no magic values; reject bad
   combinations at construction.** Grep for an existing synonym first (`MinimumCount` /
   `WaitForAll` for partition rollups; the `aget_*` prefix for async variants, so `arun` rather
   than `run_async`; #65618, #70225). A special value standing for a meaning (`-1` for "all")
   cannot express "at least n"; use an explicit flag or enum instead (#70225). List the parameter
   combinations that conflict (`limit < expected_count`) and `raise` in `__init__` so the trap
   never ships, and make the parameter name match the type it accepts (#70225).
4. **A change to serialized content is a compatibility change.** This covers a serde
   `__version__` or semantics change, `repr` used as the serialized value, and any label or
   string that enters the serialized Dag hash. Check: (a) a payload written by the old version
   still reads back (a naive-datetime `timestamp` whose meaning changed without a `__version__`
   bump cannot be told apart during a rolling upgrade; #73748); (b) when the version number moves,
   comparison logic such as the Dag version diff normalizes old and new, since a migration that
   stored version 2 against a new serializer emitting 3 produces a false deadline diff, so keep
   the literal or normalize before comparing, and test that v2 and v3 compare equal (#73748);
   (c) there is a "serialize twice, compare equal" test and a "read the old-format payload" test
   — an object without `__repr__` inside `partial_kwargs` or expand values serializes to a string
   containing the object id and writes a new Dag version on every parse (#70225); (d) a comment
   next to the string says that changing it changes the Dag hash (#70225).
5. **A helper used only inside its own module is underscore-private.** After 1.0 a public name is
   a frozen signature; a test that imports it directly is not an external caller, so rename the
   helper and update the test together (#74695).
6. **Type a callback / factory parameter with a Protocol whose `__call__` is keyword-only, not
   `Callable[..., X]`.** The `...` hides the keyword arguments the factory is called with. Define
   `class XFactory(Protocol)` with `def __call__(self, *, model_name: str, ...) -> X: ...` and
   annotate both parameter and return with it; follow the in-provider precedent (the `AgentFactory`
   Protocol in `durable/strands.py`) and do not add `@runtime_checkable`, which the precedent also
   omits. A class whose constructor argument names are compatible (extra keyword-only parameters
   with defaults are fine) can be passed directly as the factory (#75369).

---

## Airflow cases behind the generic design-integrity rules

Airflow-specific instances of rules that now live in the generic file; read them alongside it.

- **Part M (type-pairing guards, "two definitions must stay in sync")**: Airflow already has a
  prek-hook precedent for this risk: `scripts/ci/prek/check_partition_mapper_defaults_in_sync.py`
  (see `.pre-commit-config.yaml:344-350`), which diffs the field-name sets core and SDK each
  maintain. A second instance surfaced on PR #69761 — `shared/plugins_manager`'s TypedDict vs. the
  Pydantic response model in `airflow.api_fastapi.core_api.datamodels.plugins` — when review flagged
  the lack of an automated sync check between the two. When a review raises this class of nit,
  point at the existing hook as the concrete pattern to replicate.
- **Part P (version-skew tolerance, dependency floor)**: the Airflow instance is
  (2026-09-17) `common.ai` `external-services`: `snowflake` landed in pydantic-ai 2.27.0 and
  `crusoe` in 2.28.0, while the provider supports `pydantic-ai-slim` from 2.23.0 upward and CI
  exercises that floor. When the new upstream item is a vendor, the declaration itself touches three
  places (`provider.yaml`, the generated `get_provider_info.py`, and the test's `LABELS`) — see
  [`registry-conventions.md`](https://github.com/Lee-W/maigo/blob/main/skills/airflow-aware/references/registry-conventions.md)
  ("New hooks module in a provider …").
- **Part L variant (normalize partial data at its source)**: apache/airflow #72786 —
  `_resolve_agent_ref()` returned `{}` on failure; four callers handled it — three with
  `.get(k, default)`, one with a bare `.get(k)`. That one printed the failover warning
  `Managed agent None on None failed; failing over to None` — exactly the line the docs tell
  operators to read to find the broken member. The fix normalized in the helper on **both** success
  and failure paths, and the four callers now index directly.

## Core ↔ SDK paired-class symmetry

Several public APIs exist as paired classes — one in `airflow-core/` and one in
`task-sdk/` with the same conceptual role and the same name (e.g., the temporal
partition mappers `_BaseTemporalMapper` in `airflow.partition_mappers.temporal`
vs `airflow.sdk.definitions.partition_mappers.temporal`). When the two
implementations drift on a **same-named attribute**, the divergence is a
**bug**, not a nit — even if both sides happen to work in practice because
downstream code (encoders, serializers, consumers) tolerates both shapes.

Things to compare side-by-side when reviewing or self-reviewing such a class:

- Constructor signature (kwargs, positional-vs-keyword, defaults).
- Attribute *type* after `__init__` (e.g., is `_timezone` always
  `Timezone | FixedTimezone` on both sides, or is one side keeping a raw
  `str`?).
- Validation / normalization step in `__init__` (e.g., one side runs
  `parse_timezone()`, the other stores verbatim).
- Eager-raise behaviour for invalid input.

Do **not** accept "this can be a separate PR" framing just because the gap
is "merely" a type or validation asymmetry. Fix it in the current PR. The
related question — whether the overall patch is a **bugfix** or **feature
completion**, which determines newsfragment + backport label — is a
separate axis covered by the SDK/Core release-state framing memory
(check release tags via `git tag --contains <sha>` **and** `git show
<tag>:<file>` to confirm).

## CLI and REST design consistency

Before designing a new CLI command's semantic, filter, or default, **grep
sibling commands first** — cross-command consistency outranks a per-command
UX win. If a proposed behavior diverges from how sibling commands treat the
same semantic field (e.g. a date-range filter, an end-date clamp), be able to
explain *why* this command deviates; if you can't, align with the siblings
instead. Do this before implementation, not after review blocks it.

When adding a REST endpoint that parallels an existing CLI command, name it
after the **CLI's verb** and the existing REST verb vocabulary, not a more
literally-accurate coined word — e.g. `clearPartitions` (mirroring CLI
`airflow partitions clear` and REST `clearDagRuns`) beats a technically-more-
precise `resetPartitionFields`. Consistency across the user-facing surface
beats per-endpoint pedantic accuracy.

## Partitioned / scheduling-range API granularity

Don't type a partitioned/scheduling-range API parameter at `date` granularity
(`datetime.date`) — take `datetime` bounds and walk the timetable's own
cadence instead. A `date`-typed parameter makes a sub-day window structurally
inexpressible, and day-bound expansion logic then silently widens any window
to the whole local day even for an hourly-cadence timetable. When adding or
reviewing timetable/backfill range behavior: pass datetimes and honor bounds
as both-ends-inclusive instants; always add a sub-day cron case
(`"0 * * * *"`) to the tests — day-grained tests alone give a false green on
day-bound bugs.
