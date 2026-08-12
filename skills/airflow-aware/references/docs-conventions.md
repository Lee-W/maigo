# Airflow docs-writing conventions (subset framing, symbol stability, shared examples)

Loaded on demand by `skills/airflow-aware/SKILL.md` — conventions for writing
or reviewing Airflow docs prose (`.rst` files, provider guides, docstrings)
that recur often enough to warrant a shared reference. Read this file when
writing or reviewing docs prose and one of the topics below applies.

---

## Label an upstream-driven subset as representative, and link the full list

When a list's membership is **not fixed by local code but decided by an
upstream package or by a caller-supplied identifier**, presenting it as a bare
heading/section reads as the complete set — a reader concludes anything not
listed is unsupported. Two things are required together: **label it as
representative/non-exhaustive**, and **link the upstream's full list**.

Case studies (two rounds of review on the same class of problem):

- apache/airflow PR #69552: two review rounds both circled extras
  discoverability — one reviewer asked for an extra-name-to-package mapping,
  another asked for a link to the upstream extras list. Fix: after listing
  four model extras, add "extra names mirror the same-named
  `pydantic-ai-slim` optional group; see upstream install docs (`#slim-install`
  anchor) for the full list."
- apache/airflow PR #70497: a registry's `external-services` field rendered as
  a bare `<th>External services</th>`. A reviewer noted the base hook just
  maps `conn.password` to `api_key` for whichever provider the model id
  names, and dozens of that library's provider classes take `api_key` — ten
  listed out of many more means a reader concludes the rest are unsupported,
  and the list needs an edit every time the upstream package adds a provider.
  Fix: the header became "External services (examples)", with the schema
  description and contributing docs using the same vocabulary
  (representative / non-exhaustive / examples / compatibility matrix) and
  stating **why** an exhaustive list is impossible. This round didn't add a
  link to the upstream full list — a later review flagged that as the
  remaining gap in this same recurring pattern.

Why: "N picked out of M" is itself a claim about support coverage, and a
reader has no way to know it was a sample. An open set also needs a local-list
edit every time upstream adds a member — not labeling it representative signs
a maintenance commitment nobody intends to keep. Labeling it representative
without an exit (a link to where to find the full list) leaves the reader
knowing the list is incomplete but not where to look — that only solves half
the problem.

How to apply: before writing or reviewing an enumerated field/list, ask "who
decides this set's membership?" — a caller's model id, an upstream optional
group, or a third-party package's provider classes all mean an open set. For
an open set: (1) use the **same vocabulary** everywhere a reader encounters
the field (rendered heading, schema description, contributor docs) — don't
let three documents each invent their own phrasing; (2) state the mechanism
that makes exhaustive listing impossible, not just "this list is incomplete";
(3) link the upstream's full list. If the set is actually fixed by
construction (e.g. hardcoded subclasses of a single vendor's hook), keep it
exhaustive and don't add a disclaimer — a disclaimer there would misrepresent
it as open when it isn't.

