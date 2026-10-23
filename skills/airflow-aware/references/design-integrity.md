# Airflow design-integrity conventions (framework / base API design)

Loaded on demand by `skills/airflow-aware/SKILL.md` — **Airflow-specific** design-level conventions
for hot-loop extension surfaces (scheduler / triggerer / API request handler / Dag parser),
`Window` semantics, common.ai adapters, and the Airflow cases behind the generic rules. The generic
framework-design rules (type-pairing guards, symmetric naming, structural closing of sum-types,
version-skew tolerance, normalizing partial data) live in
[`skills/strict-review/references/design-integrity.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/design-integrity.md).
Read this file when designing or reviewing a new base/framework API on an Airflow hot loop.

Core ↔ SDK paired-class attribute symmetry is already covered in
`skills/airflow-aware/SKILL.md` §9 ("Core ↔ SDK paired-class symmetry") — not
repeated here.

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
- **Part N (symmetric naming)**: the mapper examples are Airflow's partition mappers
  (`upstream_mapper` / `downstream_mapper`, with `Window` as the structurally different pair member).
