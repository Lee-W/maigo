# Airflow UI conventions (rendering, labels, column visibility, route params)

Loaded on demand by `skills/airflow-aware/SKILL.md` — Airflow-specific UI
conventions covering how to render long value lists, when two similarly-named
labels are intentionally distinct, how to implement data-driven column
visibility, and where a free-form key goes in a UI route. Read this file when
building or reviewing an `airflow-core/src/airflow/ui` change that touches
any of these.

---

## Long value lists render by line, not comma-joined

When a UI surface lists values that are themselves long (a partition key, an
ISO timestamp), render them one-per-line — don't keep the default
comma-joined single line.

Case study: a backfill partition preview's `getInlineMessage` used
`LimitedItemsList`'s default `separator = ", "`, packing partition keys like
`2026-01-01T00:00:00+00:00` into one unreadable line.

Why: `LimitedItemsList`'s default horizontal layout is designed for **short**
tokens (tags, owners). The same component's default flips from compact to
unreadable once the value length grows — the judgment criterion is the
**length of the value**, not the length of the list.

How to apply: when a new surface lists long values, pass
`orientation="vertical"` (`LimitedItemsList` already has this prop; the
default is still horizontal). When modifying the shared component itself,
go through a reusable prop rather than a consumer-side one-off list (see "No
ref+remount hack for column visibility" below), and don't leave an ungated
attribute on the shared path.

---

## "Partition Key" vs "Mapped Partition Key": intentional label split, don't unify

The two partition-key labels used across the AIP-76 UI are semantically
distinct by design — do not unify them in either direction.

- **"Mapped Partition Key"** (used only in the schedule-preview modal): the
  shown key is the *downstream* key a partition mapper produced by
  transforming *upstream* asset partition key(s). "Mapped" signals "this is
  a derived/transformed key — don't expect it to match the upstream key."
  The modal lists these pending mapped keys before they materialize into
  runs.
- **"Partition Key"** (used for created runs, e.g. header/asset-event
  displays): the concrete key the run actually runs for. Not "Mapped"
  because at run level the upstream→downstream transformation story is no
  longer the point, and a manual single-run trigger lets a human type an
  arbitrary key that isn't mapped from anything.

The real axis is **transformed-from-upstream (schedule-preview) vs.
this-run's-concrete-key (created runs)** — not trigger mechanism, and not
"mapper involved or not." A discarded framing worth not resurrecting: "manual
trigger = user-typed vs. scheduled = mapper-derived" is wrong, because a
backfill is manually triggered yet its keys still come from the timetable,
same as the scheduler.

Why: stripping "Mapped" (unifying to "Partition Key" everywhere) loses the
"transformed, won't match upstream" signal; exporting "Mapped" everywhere
(e.g. via an identity-mapper argument) is false for hand-typed keys.

How to apply: flag any PR that unifies the two labels in either direction —
or renames one side to match the other — without addressing the
transformation-vs-concrete-key distinction above.

---

## No ref+`DataTable`-key remount hack for data-driven column visibility

Do not implement data-driven column visibility by fetching the deciding
data, latching it in a `useRef`, and forcing a `<DataTable>` remount via a
changing `key` prop so the mount-time column-visibility default re-reads.

Airflow UI convention (PR #69702 review): the rejected shape fetched
Dag-detail data, latched an `isPartitionedRef`, and set
`columnVisibility: { partition_key: isPartitioned }` combined with
`<DataTable key={`${dagId}-${...}`}>`.

Why: column-visibility defaults are read once at mount; hacking a remount to
re-derive them fights the framework — the whole table re-mounts once the
async answer arrives, which is fragile and visibly janky. The reviewer
wanted a **robust, reusable** mechanism instead — one general enough to also
cover related cases (e.g. hiding `map_index` for non-mapped tasks).

How to apply: when a PR toggles table columns based on fetched data, flag
any `key`-based remount / ref-latch workaround; steer toward (or wait for) a
reusable column-visibility utility that doesn't require remounting the
table.

---

## Free-form keys that may contain `/` go in a query param, not a path segment

In `airflow-core/src/airflow/api_fastapi/core_api/routes/ui/`, a free-form
key that can contain `/` (e.g. `partition_key`) belongs in a query
parameter. Path segments are reserved for controlled identifiers like
`dag_id`/`run_id`.

Why: a slash inside a path segment gets parsed as a route separator, so a
slash-containing key 404s when placed in a path segment. Precedent: the
pending-partition-run detail endpoint (`partitioned_dag_runs.py`) moved
`partition_key` to a query param after hitting exactly this — the first
query-param precedent in that directory, since every other UI route uses
path params for its (controlled) identifiers. Behavior notes: a missing
required query param returns 422; an empty string reaches the DB lookup and
returns 404.

How to apply: when adding a UI endpoint keyed by a user-authored string,
follow the pending-partition-run detail endpoint's shape and use a query
param — don't copy the path-param shape of sibling routes whose params are
controlled IDs.

## A "cannot submit" guard keys on the control being rendered, not on a data flag

A guard that blocks submit (for example an empty selection) must be conditioned on "this control is on screen", not on
a data flag that merely correlates with it, such as the HITL detail's `multiple`. In the HITL response form a guard
opening with `multiple &&` let an empty `chosen_options` through when `multiple` was false but the options were too
many for buttons and the Respond control was shown instead. Whenever that control appears, the field exists and an
empty value is never valid.

Scope the guard to that render path too. The shared `handleSubmit` also runs from the option-button path, which has no
such field, so an unscoped guard blocks every option button.

How to apply: before editing the guard, list every condition under which the control renders and make the guard's
trigger match that list; then check the shared submit handler on each other path (button mode, approval, preloaded
values). Tests need both kinds: the case that must be blocked, and the cases that must not be (the latter also pass
before the fix, so they are guards against over-blocking, not regression detectors).

## react-hook-form: `reset` rebases `dirtyFields`, so don't use it to detect a user edit

In an Airflow UI form, "apply an external value (an API suggestion) only if the user hasn't touched the field" must
not be gated on `formState.dirtyFields`. `reset(...)` makes the reset values the new `defaultValues`, so what the
user just typed stops counting as dirty, `dirtyFields.<field>` flips back to false, and the external value overwrites
the input. Any `reset` in the form triggers this, e.g. applying a recent config or editing the JSON conf and blurring.

Pattern: keep a `useRef` of the last external value applied; the effect calls `setValue` (and updates the ref) only when
the field is empty or equals that remembered value, with dependencies like `[open, externalValue, getValues,
setValue]`. A modal that unmounts on exit drops the ref with the form, so nothing stale survives.

Case: the first fix used `dirtyFields` and passed a test that only re-rendered with a new suggestion, which never
reached a `reset` path; reading the code, not the green run, found the bug. Tests must go through the real reset
paths (choose a recent config; edit the JSON editor and blur), and a mutation proves them: temporarily revert the
implementation to depend on `dirtyFields` and both tests must turn red.

## zh-TW locale content

**zh-TW locale content**: call it "Taiwanese Mandarin", never "Traditional
Chinese" — this applies to commit messages, PR text, docs, and comments
produced for this repo. When translating a UI string, check the repo's
existing zh-TW translations for established terminology before coining a
new term. A newly added plural `*_one` key says the literal `1`, not
`{{count}}` (that branch only renders when the count is 1); existing `_one`
keys that still interpolate are left alone, so don't retro-fix them in a
"fill missing translations" change. When delegating an i18n fill-in to a
subagent, paste these rules into the prompt one by one (it cannot read this
skill, and "follow the existing pattern" can point at the wrong convention
in the same file) and add a matching acceptance check, e.g. new `_one` keys
say the literal `1`. See
[`delegation-sizing`](https://github.com/Lee-W/maigo/blob/main/skills/harness-discipline/references/delegation-sizing.md).
