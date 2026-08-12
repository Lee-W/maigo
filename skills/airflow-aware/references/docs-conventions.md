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

---

## Name a default in its own module — don't tell users to import a symbol that moves

Docs must not tell a user to import a private or unstable symbol that belongs
to someone else's internals. The strongest reverse signal that a symbol will
move again: **if the repo already has a compatibility/fallback import chain
written for it**, that chain is evidence of past churn — don't point docs at
it.

Case study: apache/airflow PR #70830, `common.ai` provider. `LLMRetryPolicy`'s
default redactor was originally an inline lambda in the signature, and the
docs told Dag authors to write `from airflow.sdk.log import redact` to layer
their own on top. A reviewer pointed out `redact` isn't in Task SDK's public
interface (`task-sdk/docs/api.rst` only autodocs `mask_secret`), and it has
moved four times — `providers/common/compat/.../sdk.py` carries exactly four
fallback imports for it (`airflow.sdk.log` →
`airflow.sdk._shared.secrets_masker` →
`airflow.sdk.execution_time.secrets_masker` →
`airflow.utils.log.secrets_masker`). Fix: extracted to a module-level
`default_redactor`, added to `__all__`, and the docs now point at
`from airflow.providers.common.ai.policies.retry import default_redactor`
instead.

Why: an import path in docs is a compatibility promise to the user. Pointing
at a private symbol you don't control turns someone else's refactor into
silent user-facing breakage — their custom redactor `ImportError`s or quietly
stops working after an upgrade. A named default exported from your own module
is a stable surface regardless of how the internals move.

How to apply: before telling users to import a symbol, confirm it's in that
package's public API docs. If the repo already has a compat/fallback import
chain for a symbol, treat that as proof it will move again and keep it out of
docs. If the default value in question is that kind of symbol, wrap it in a
named function in your own module, export it via `__all__`, and point docs at
that layer instead. Check docstring `:func:` cross-references for the same
symbol while you're at it — don't fix only the `.rst`.

---

## Shared examples use the ecosystem-standard endpoint, not a single backend's private path

A doc that supports **multiple backends** must keep its shared (tool-neutral)
example on the ecosystem-standard API — hardcoding one backend's private
endpoint in the shared example secretly locks the reader into that backend,
contradicting the doc's own "any compatible backend works" premise. Per-tool
tabbed sections, explicitly labeled for one backend, are the place for that
backend's private paths — leave those as-is.

Case study: apache/airflow PR #69867, `common.ai` self-hosted-models guide.
The shared `example_agent_self_hosted` hardcoded Ollama's private
`/api/tags` model-list endpoint — flagged as "too Ollama-focused." Fix:
switched to `GET /v1/models`, the standard endpoint every OpenAI-compatible
server (Ollama/vLLM/LM Studio) exposes — which the guide's own "curl check"
section already recommended. The per-tool tabbed setup sections elsewhere in
the same guide stayed backend-specific, unchanged.

How to apply: when writing or reviewing a multi-backend provider doc, first
separate "shared example" from "per-tool section." Shared examples default to
the ecosystem standard (for OpenAI-compatible servers: `/v1/models`,
`/v1/chat/completions`, etc.); only a section explicitly labeled for one
backend's tab uses that backend's private path. A private single-backend
endpoint showing up in a shared example is the signal to neutralize it.

