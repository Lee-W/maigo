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

Case studies (recurring across providers):

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
- apache/airflow PR #72049, `providers/openai/docs/operators/openai.rst`: a
  guide enumerated `service_tier`'s legal values (`'auto'`/`'default'`/
  `'flex'`/`'scale'`/`'priority'`) with no link to OpenAI's own API reference.
  The docstring on `operators/openai.py` already linked the Responses API
  reference — but the guide (`.rst`) and the docstring are two separate entry
  points, and a reader who lands on the guide never sees the docstring's
  link. Fix: added the authoritative link at the start of the section, before
  the enumerated values, so the list reads as "full list is here, here are a
  few worth knowing" rather than a closed set.

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
(3) link the upstream's full list, placed at the **start** of the section
before the enumerated values (not buried at the end), and added to **every**
entry point (guide and docstring) rather than assuming one covers the other.
If the set is actually fixed by construction (e.g. hardcoded subclasses of a
single vendor's hook), keep it exhaustive and don't add a disclaimer — a
disclaimer there would misrepresent it as open when it isn't.

---

## Connection docs stay actionable-only — cut implementation-mechanism detail

Connection docs (`provider.yaml` descriptions, hook docstrings,
`docs/connections/*.rst`) should only carry what a user can act on: what to
do, why, the concrete consequence, and a diagnostic clue (e.g. "check the
task log for the XX warning"). Cut:

- exception mechanism detail ("raises a TypeError that the hook catches")
- log strings copied verbatim
- version-verification provenance ("verified against pinned `<lib>` X.Y.Z")

Why: this content belongs in a commit message or PR description — evidence
for a reviewer, not guidance for a user. It reads like an internal debugging
note, and a version-verification note goes stale the moment a follow-up PR
lands, with nobody thinking to clean up a stray version string in a docs
file afterward.

Case study: `providers/common/ai/docs/connections/pydantic_ai_vertex.rst`'s
`vertexai` field warning box was rewritten from an internal-mechanism
description to pure consequence + diagnostic clue.

How to apply: before shipping a connection-doc edit, re-read it and cut any
sentence whose audience is actually "the reviewer of this PR" rather than
"the user configuring this connection" — move that content to the PR
description instead.

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

---

## AI/agent example prompts ask naturally; procedural knowledge goes in `system_prompt`

An AI/agent framework example's `prompt=` should read like a natural user
question, not an instruction that spells out API paths or steps. Endpoint/
procedural knowledge belongs in `system_prompt` instead.

Case study: apache/airflow PR #69867, `common.ai` provider. A reviewer pushed
back on an agent example's `prompt="Call /api/tags and summarize which models
are available."` with "should we just ask — 'Which models are available' —
instead of telling how." Resolved to `prompt="Which models are available?"`,
with the endpoint knowledge moved into `system_prompt` (e.g. "...the server's
model list is served at `GET /api/tags`."). Verified deterministic
tool-calling across repeated runs after the change.

Why: an example teaches the user's perspective — the prompt is what a person
would say, so it should read like human speech; "how to do it" is the agent's
own configuration layer (`system_prompt` / tool descriptions), not something
the user should have to say out loud. Grounding the endpoint in
`system_prompt` also avoids the model guessing at a path (which then hard-fails
on a 4xx from an HTTP-based tool).

How to apply: when writing or reviewing an example for `common.ai` (or any
agent framework), keep `prompt=` free of API paths or step-by-step
instructions. If the model needs grounding, put it in `system_prompt`, and
verify determinism by actually running the example more than once.

---

## `:any:` roles fan out to every domain — use a precise role instead

A `` :any: `` cross-reference asks every Sphinx domain to resolve the target.
A domain that doesn't implement `resolve_any_xref` falls back to Sphinx
calling `resolve_xref` once per role in that domain — normally a silent miss,
but not every domain stays silent on a miss.

Case study: apache/airflow PR #69445, upgrading `sphinx-argparse` 0.5.2 →
0.6.0. The new version's `commands` domain (absent in 0.5.2) logs
`WARNING: Error, no command xref target from <docname>:<target>` on every
`resolve_xref` miss instead of returning `None`. Docs builds treat Sphinx
warnings as errors, so any `` :any: `` target elsewhere in the docs — even one
with no relation to CLI commands, like `` :any:`os.environ` `` — now fails the
build. This is an upstream sphinx-argparse bug (an any-fallback probe
shouldn't itself warn), but the fix is local: stop using `` :any: ``.

Why: `` :any: `` is a "guess which domain this belongs to" role. It's
convenient to write, but every domain in the build gets probed for it, and a
badly-behaved domain (or a newly added one, as here) can turn an unrelated doc
elsewhere into a broken build. There's rarely an upside — the writer
typically already knows what kind of symbol they're linking.

How to apply: replace `` :any: `` with the precise role. To find which role a
target actually resolves under (Python stdlib symbols in particular), query
the target inventory directly instead of guessing:

```bash
python -m sphinx.ext.intersphinx https://docs.python.org/3/objects.inv | grep <target>
```

`os.environ` resolves under `py:data`, so `` :data:`os.environ` `` — not
`` :meth:`os.environ` ``, which is for callables like
`unittest.mock.patch.dict`. If a docs build newly starts failing after
bumping a Sphinx extension that adds a domain, grep the whole docs tree for
`` :any: `` first — it's likely the only affected role, and the fix doesn't
need touching every doc, just the handful using `` :any: ``.

---

## Provider docs' source links are version-pinned — a pre-release 404 is expected

Provider docs link back to GitHub source using
`blob/providers-<name>/|version|/...`, where `|version|` is a Sphinx
substitution that resolves to the package's current version. This is the
standard convention across the monorepo (core docs and every provider follow
it), because it points the reader at the exact source that shipped in the
version they're reading about — not whatever happens to be on `main` today.

Why it matters: if the version being documented hasn't been tagged yet (only
released as an rc, or not released at all), the rendered blob URL 404s until
the real tag lands. That's expected, not a defect to fix by pointing the link
at `main` instead — `main` drifts out from under a pinned doc the moment the
next PR merges, silently making the link describe different code than what
the version actually shipped.

How to apply: if a version-pinned blob link 404s during review, check whether
the corresponding tag exists yet (`git tag -l 'providers-<name>/<version>'` or
the GitHub tags page) before "fixing" it. Only escalate if the tag exists and
the link is still wrong (wrong path, wrong provider slug).

---

## New sub-pages nest into their parent page's own toctree, not the top-level index

When a topic already has its own page hierarchy (`operators/index.rst`,
`hooks/index.rst`, etc.), a new sub-page under that topic must be added to
*that page's* toctree, not appended as a new sibling entry in the top-level
`index.rst`'s Guides toctree.

The repo's convention: a parent page with a directory of children uses
`` .. toctree:: :glob: * `` to sweep every file in its own directory in one
shot, and the top-level `index.rst` lists that parent exactly once (e.g.
`Operators <operators/index>`). Adding a page directly as a new top-level
Guides entry duplicates it across two places in the nav and misrepresents it
as a peer of `operators/` or `hooks/` rather than a member of one of them.

Why: Sphinx warns "document not in toctree" for any `.rst` that isn't
reachable from a toctree somewhere, so a new page has to land in *some*
toctree to clear that warning — the glob-based parent toctree is the one
meant to catch it. Bypassing it and hand-adding to the top-level index
produces a flat, undifferentiated nav instead of the intended hierarchy.

How to apply: before wiring in a new sub-page, check whether its topic
already has a parent `index.rst` with `.. toctree:: :glob:`. If so, the new
file just needs to exist in that directory — the glob picks it up
automatically, and the top-level `index.rst` doesn't need touching. Only add
a brand-new top-level Guides entry when the page is genuinely a new top-level
topic with no existing parent.

---

## Prose external links use anonymous `` `text <url>`__ ``, not named `` `text <url>`_ ``

A single-trailing-underscore RST hyperlink (`` `text <url>`_ ``) registers
`text` as a named target for the whole document. If the same link text
points at two different URLs anywhere in that document, Sphinx raises
"Duplicate explicit target name" — and Airflow's docs build treats warnings
as errors, so this fails the build outright. The double-underscore form
(`` `text <url>`__ ``) is anonymous and never collides.

Airflow provider docs default to the anonymous form for prose external
links — a scan of `common.ai`'s `index.rst` found 38 anonymous links against
7 named ones, and the named ones cluster in generated tables, not
hand-written prose. The canonical case where the collision actually bites:
two links in the same file, both labeled `asc`, pointing at different
download URLs (e.g. two different release artifacts' signature files).

Why: it's easy to default to the single-underscore form out of habit (it's
the more commonly seen RST hyperlink syntax), and it works fine right up
until the same link text is reused for a different URL somewhere else in the
document — common in release/download docs where multiple artifacts each get
an `asc` / `sha512` link.

How to apply: when writing prose external links in provider `.rst` docs,
default to `` `text <url>`__ `` (double underscore). Only reach for the named
form (`_`) when the link genuinely needs to be referenceable elsewhere in the
document — and even then, check the rest of the file for repeated link text
first.

---

## Provider docs never cite source line numbers — point at durable symbols instead

Don't write `file.py:123`-style references into provider docs prose
(`providers/<x>/docs/**.rst`). A repo-wide scan
(`grep -rnE "\.py:[0-9]+" providers/common/ai/docs/`) turns up zero
precedent for it — line numbers drift with every commit, so a citation like
this in an ASF-published doc goes stale almost immediately, and it will get
flagged in review.

To point at "where a limitation comes from" instead, use a durable symbol: a
parameter name (`` allowed_tables ``, `` allow_writes ``), a class reference
(`` :class:`~airflow.providers.common.ai.toolsets.hook.HookToolset` ``), or a
quoted docstring sentence. File:line references still belong in review
material, plans, or scratchpad notes for a reviewer to check against — they
just don't belong in the shipped `.rst`.

This is one of the few places where a plan's acceptance criteria and the
doc's actual writing convention pull in different directions: a plan step
that says "cite `file:line` for every limitation" is describing what a
*reviewer* needs to verify against, not what the `.rst` prose should contain.
If that conflict comes up, follow this convention for the doc itself and say
so explicitly in the report — don't silently drop the plan's line-number
requirement without flagging it.

---

## `exampleinclude` requires START/END markers already present in the target file

Some providers use `exampleinclude` instead of the standard Sphinx
`literalinclude` directive to pull in example code. `exampleinclude` requires
the target file to already have matching `[START x]` / `[END x]` markers —
copying a working `exampleinclude` from a sibling page without checking the
new target file for markers will fail `breeze build-docs` (a system-test
example file with no markers is a common miss). Confirm the markers exist in
the target file before wiring up the include, rather than assuming every
example file follows the pattern of the one you copied from.

---

## Passthrough-kwargs docs must name the kwargs that break the wrapper, not gloss them as "any"

When an operator/hook design forwards a dict argument straight through to an
underlying SDK call (a common Airflow pattern: `response_kwargs`,
`hook_params`, any `*_kwargs`), the docs must not describe it as "any keyword
argument the underlying API accepts can be set there."

Why: the underlying SDK frequently has kwargs that **change the return
type** of the call, and the operator's own code right after the call assumes
one specific shape. Setting that kwarg makes the operator crash on the very
next line. Case in point: the OpenAI Responses API's `stream=True` makes
`responses.create` return a `Stream[ResponseStreamEvent]`, which has neither
`.status` nor `.output_text` — and `OpenAIResponseOperator.execute` reads
both immediately after the call, so the operator raises `AttributeError`
(apache/airflow PR #72049).

How to apply:

- Narrow the claim to "most keyword arguments … with the exceptions noted
  below," and make that sentence point at an actual exceptions list below it.
- Give each kwarg that breaks the wrapper its own entry describing **how it
  fails** — don't just list it among the available options with no warning.
- Offer an alternative path where one exists (e.g. "need streaming? call the
  hook directly from a `@task`").
- To find the exceptions: read the underlying SDK's `create`/`call` method
  overloads to see how many return types are possible, then read the
  operator's `execute` to see which attributes of the return value it reads.
  Any kwarg whose return shape falls outside what `execute` reads is one of
  the exceptions.

---

## A path a doc tells the reader to take must actually be reachable from that task

Before writing "take X and feed it into Y," go back and check the
implementation: does X actually leave the task it's produced in?

Judgment: a value that only appears in `self.log.*` calls is not reachable
downstream — it isn't in the return value, isn't pushed to XCom, and the
reader's only way to retrieve it is manually reading logs. A doc that tells
the reader to build on that value is describing a path that doesn't exist.

Case study: `OpenAIResponseOperator`'s docs originally said "use
`background=True` only when you plan to poll for completion or cancel the
response through `OpenAIHook` directly" — but `execute` only `return`s
`response.output_text`, and `response.id` (the value needed for
polling/cancelling) appears exclusively in `self.log.warning`/`self.log.info`
calls. Without the id, `get_response`/`cancel_response` can't be called at
all. Fix: rewrote it plainly as "don't set `background=True` on this
operator; for a background response, call `OpenAIHook.create_response`
directly from a `@task`" (apache/airflow PR #72049).

How to apply: for every "use A to feed B" sentence in a doc, grep the
implementation for where A actually goes. Only a `return` value or an XCom
push counts as reachable — a log call doesn't, no matter how prominent.

---

## Check `template_fields` before demoing XCom chaining into an operator argument

Before writing a doc example or example Dag that feeds an upstream XCom into
a downstream operator's argument, confirm that argument is actually listed
in that operator's `template_fields`. If it isn't, `` "{{ ti.xcom_pull(...) }}" ``
never gets rendered — it's sent to the external API as a literal Jinja
string. The example looks fine on the page and only reveals itself as
broken when someone actually runs it.

`XComArg` / `task.output` don't route around this — their resolution is also
gated on template rendering, so a non-template field breaks the same way
regardless of which XCom-reference syntax the example uses.

Case study: `OpenAIResponseOperator`'s `template_fields` was only
`("input_text",)`; a reviewer-requested `previous_response_id` chaining
example couldn't be made to work until `response_kwargs` was added to
`template_fields` (apache/airflow PR #72151).

Safety note: Airflow's templater only runs Jinja on **`str` leaf nodes**
(`task-sdk/src/airflow/sdk/definitions/_internal/templater.py:218-281`), so
adding a kwargs dict to `template_fields` doesn't accidentally template
list/dict/object values inside it — `PythonOperator.op_kwargs` is existing
precedent for this pattern.

How to apply: `grep -n "template_fields" <operator file>` before demoing any
XCom-into-argument example. If the target field needs to be added to
`template_fields` to make the example true, also add a test that calls
`operator.render_template_fields({...})` (no `dag_maker`/DB needed — see the
pattern in `providers/amazon/tests/unit/amazon/aws/operators/test_glue.py:1348`),
and run a mutation canary: remove the field from `template_fields` and
confirm the new test actually goes red.
