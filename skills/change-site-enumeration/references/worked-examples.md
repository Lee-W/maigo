# Worked examples: change-site enumeration

Four real instances backing `skills/change-site-enumeration/SKILL.md`. All four
are from apache/airflow's `dev/registry` (provider registry site + its build
pipeline). Reviewer GitHub handles are generalized to "reviewer" — the point
is the enumeration failure, not who caught it.

## 1. Two independent search mechanisms (PR #70498)

Triaging "search on the registry site can't find X" started with a symptom
grep: `currentSearch|searchInput|type="search"`. That found exactly one
implementation — the `/providers/` page's inline filter box
(`#provider-search` → `provider-filters.js`, reads a DOM data attribute) — and
the fix was declared scoped to it.

The site actually has a **second, fully independent** search mechanism: the
site-wide search modal (header magnifier, `Cmd+K`, homepage hero) —
`#search-input` → `search.js` → Pagefind, whose index is built by
`registry/scripts/build-pagefind-index.mjs` via `addCustomRecord`. That script
does not read page HTML at all, so the DOM-attribute fix had zero effect on
it. The user reported "still can't find it" — the second mechanism was never
even opened.

**False signal encountered**: searching `pydantic` during triage did return a
result, which looked like "partial fix already working." It wasn't — that
provider's description happened to contain the substring `pydantic-ai`,
unrelated to the fix.

Enumeration method that would have caught it: reverse from user entry points,
not from symbol names. The site has ≥2 search entry points (inline filter,
site-wide modal) with different data sources (DOM vs. build-time index) —
entry count > 1 means each one needs independent verification.

## 2. Same gap, two entry points, reviewer named only one (PR #70498)

Follow-up to example 1: a reviewer flagged, at `registry/src/providers.njk:72`,
that the `/providers/` search box doesn't mirror the id-matching logic used at
build time. That's real, but it's only half the gap — "provider search" has
**two** entry points sharing the same missing piece:

1. `src/js/provider-filters.js` — the DOM-side filtering logic
2. `scripts/build-pagefind-index.mjs` — the Pagefind index `content` field
   (it doesn't read page HTML, so fixing the template alone is a no-op for it)

The reviewer's comment pointed at entry point 1 only. Fixing just the named
site leaves the other half of the bug in place — a fix that satisfies "the
reviewer's comment is addressed" while the underlying user-facing bug (search
box doesn't find integration names) is still half-broken.

This is the general pattern behind the SKILL.md rule "don't accept 'the site
the reviewer named is fixed' as evidence of exhaustion" — a reviewer comment
is a *lower bound* on the site count, not the full enumeration.

## 3. Parallel dict-shaped sections, same drift caught twice (PR #70190)

`provider.yaml`'s `plugins` and `dialects` sections are handled by two
byte-for-byte identical loops in `dev/registry/extract_parameters.py`,
differing only in three literals: the yaml key, the type id, and the field
name used to pull the integration name (`name` vs. `dialect-type`).

- **First review round**: a reviewer caught that `extract_versions.py` kept
  its own hardcoded list drifting from the two loops. The fix added
  `DICT_SHAPED_CLASS_LEVEL_SECTIONS` — but only collected the **class-path**
  field name. The PR reply told the reviewer "won't drift again."
- **Second review round**: a different reviewer pointed out the table could
  have a third component (`name` / `dialect-type`), and then
  `discover_classes_from_provider` would only need one loop instead of two.
  The same drift got caught a second time, and the "won't drift again" claim
  from round one turned out to be wrong.

Enumeration method that would have caught it in one pass: diff the two loops
line-by-line, list *every* differing literal (yaml key, type id, field name,
category override), and ask "how many of these can go in the shared table?"
for each one — not just the one a reviewer happened to name. The semantic
acceptance criterion is "how many per-section branches does this logic still
need?" targeting 0, not "did we collect the field the reviewer mentioned?".

## 4. Constant arity change, plan said 3 sites, actual was 5 (PR #70190)

Follow-up to example 3: `DICT_SHAPED_CLASS_LEVEL_SECTIONS` changed from
`dict[str, tuple[str, str]]` to `dict[str, tuple[str, str, str]]`. The
pre-implementation plan enumerated 3 unpacking sites (one each in
`extract_versions.py`, `test_extract_versions.py`, `test_types.py`).

The implementer, instructed to grep the constant name itself rather than
trust the plan's list, found the plan was wrong: `test_extract_versions.py`
alone had two more sites the plan missed — an intermediate-variable unpack
(`mod_type, class_path_field = type_and_field`, stored one line before being
destructured) and a set comprehension (`{t for t, _ in ....values()}`).
Missing either would have raised `ValueError: too many values to unpack` at
runtime, not at type-check time.

This is the source example for the SKILL.md rule that Anon must re-enumerate
independently rather than reuse the plan's site list — the plan itself can be
the thing that's wrong, and only a fresh grep against the constant name (not
the type name, not the field name) surfaces the sites the plan missed.
