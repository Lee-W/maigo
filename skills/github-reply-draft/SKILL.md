---
name: github-reply-draft
description: This skill should be used when drafting reply text for GitHub PR review threads or review comments — ensuring replies to a reviewer are terse, reference only committed symbols, are scoped per thread, and, for replies to a reviewer, carry no attribution footer unless the user asks for one.
---

<!-- mkdocs-include-start -->

# GitHub Reply Draft

**Owner**: — (orchestrator/agent drafting GitHub replies)
**Consumers**: `/maigo:address-comments` (per-thread replies at Finale), `/maigo:review` (reply drafts at criti gate; for its review body and inline comments only Conventions 2–5 apply)

**Scope of the voice baseline**: the "Voice baseline" section and Convention 1 below govern replies to a reviewer's comments (the `reply-draft.md` that `/maigo:address-comments` writes). The review body and inline comments `/maigo:review` drafts for someone else's PR (`draft.md`, `inline-comments.md`) keep the rules in `commands/review.md` and `skills/strict-review/references/review-templates.md`; Conventions 2–5 apply to both.

Delivery form: `/maigo:address-comments` writes the drafts to a `reply-draft.md` file with a
where-to-comment hint per reply — template in
[`references/comment-fetch-and-triage.md`](https://github.com/Lee-W/maigo/blob/main/skills/github-reply-draft/references/comment-fetch-and-triage.md)
("回覆草稿檔模板").

## Voice baseline

Replies should read like the maintainer typed them: short, concrete, no ceremony. In a comparison of agent drafts against what the maintainer actually posted, drafts were longer, opened with praise, carried verification disclaimers and a footer — and the maintainer cut all of them.

- **One sentence, about 20 English words.** No closing explanation, trade-off sentence or summary sentence. Write more only when the reviewer asked *why*, or the change differs from what they suggested — and then lay it out per the layout bullet.
- **Never open with praise or an apology.** Banned openers (and anything of the same kind): "Good catch", "You're right", "Great point", "Thanks for catching this", "Nice catch", "Good question". Start with the substance. "Yes", "Done" and "Agreed" are not banned.
- **No verification-scope statements in the reply text.** Do not write "I did not test…", "I only checked…", "I haven't run…". If something is unverified, say so in a **note outside the code block** in the draft file (for example "備註：這則的改動沒有實跑 X"), and mention it in the Finale table or closing summary. Every reply whose change was not actually run gets such a note — the drafter does not decide case by case. Whether to tell the reviewer is the user's call. This moves the information, it does not delete it — Convention 5 (no overclaiming) and the no-"I re-ran it" narration rule still hold.
- **Layout.** When more than one sentence is needed, put the conclusion alone on the first line, leave a blank line, then the detail. Do not write one block of text. (Each paragraph is still one unwrapped line — see the draft-file template.)
- **A very short reply is a legitimate reply.** When all there is to say is that it changed, "Done.", "Updated." or "Fixed." is enough; do not lengthen it to look complete. Use one only when the change is already in the diff being replied against and matches what the reviewer asked for; if it differs, or is only partly done, say so per the layout bullet. When the change was not run, prefer "Done." or "Updated." over "Fixed." — "Fixed." claims the problem is gone (Convention 5) — and add the note.
- **No footer** unless the user asks (Convention 6).

**Not like this → like this** (invented examples; every "like this" follows all the rules above):

1. Too long → one sentence.

   > **Not:** Changed `parse_range` to reject negative bounds. The old code silently clamped them to zero, which hid caller bugs, and the new `ValueError` makes them visible earlier in the pipeline.
   >
   > **Like:** `parse_range` now raises `ValueError` on negative bounds instead of clamping to zero.

2. Verification disclaimer → drop it from the reply, keep it as a note outside the block.

   > **Not:** Renamed the flag to `--dry-run`. I only checked the CLI help output, not the shell completions.
   >
   > **Like:** Renamed the flag to `--dry-run`.
   >
   > Plus, outside the code block in the draft file: 備註：shell completion 沒有實跑。

3. Praise opener → start with the substance.

   > **Not:** Good catch, thanks! `load_config` now falls back to the default path.
   >
   > **Like:** `load_config` now falls back to the default path.

4. One block of text → conclusion on its own line, blank line, detail. (Use two paragraphs only when the reviewer asked why, or the change differs from their suggestion; a plain change stays one sentence.)

   > **Not:** Moved the retry loop into `_send`. The public `send()` no longer retries, so callers that wrapped it in their own retry now double up and should drop theirs.
   >
   > **Like:**
   >
   > ```text
   > Moved the retry loop into `_send`.
   >
   > `send()` itself no longer retries, so callers with their own retry wrapper should drop it.
   > ```

5. Padding a trivial change → "Done."

   > **Not:** I have updated the docstring so that it now describes the new default, as you suggested.
   >
   > **Like:** Done.

## Overview

Drafting GitHub PR replies badly is a recurring source of reviewer friction.
Common failure modes: long preambles, referencing mid-iteration helpers that
were deleted before merge, merging all threads into one PR-level comment,
or overclaiming that a thread is "done ✅" when the reviewer has not yet
confirmed acceptance.

This skill captures the six conventions that prevent those failures.

## Convention 1 — Default terse

One sentence of about 20 words names what changed (see "Voice baseline" for
the length, layout and banned-opener rules). No trade-off, explanation or
summary sentence after it; a deliberate trade-off goes in the reply only when
the reviewer asked why or the change differs from their suggestion, otherwise
it goes in a note outside the code block for the user to decide on.
Cut: preamble, restating the reviewer's comment, hedging phrases
("hopefully this addresses...", "I believe this should..."), verification
narrative ("I re-ran the comparison and got the same result"), the process
of what was done, and anything the reviewer can already see from the diff.

The user will ask for more, not less — default short.

When the reply is about a reviewer's repro case you added as a test, name the parametrize case id (see `python-aware`'s `references/test-conventions.md`, "A reviewer's concrete repro case becomes a named parametrize case").

**Word-level conventions:**

- Prefer an em-dash over `, so` for casual flow (`reports should stay in sync from now
  on`, not `, so reports should stay in sync`).
- No comma after a sentence-starting `Also` before a verb (`Also updated the file`, not
  `Also, updated the file`).
- Avoid vague abstract nouns ("window", "a while", "soon", "some buffer") — swap each for
  the concrete, quantifiable mechanism behind it (a number of seconds, a count, an
  explicit configurable flag). A vague noun reads as hand-waving; a measurable mechanism
  is something a reviewer can actually evaluate and implement.
- Never close a reply with `Acceptance pending your review.` or any variant of
  "waiting for your confirmation" — whether to accept is the reviewer's call by
  definition; writing it out is zero-information filler. State what changed and stop.
- Never open with a praise or apology opener — the banned list is in "Voice
  baseline". Start directly with what changed.

**Good:**

> `validate_email` now raises `ValueError` on empty input instead of propagating `IndexError`.

**Bad:**

> Thank you for catching this. I've reviewed your comment about the empty-input
> case on `validate_email` and I believe I've addressed the concern by adding...

## Convention 2 — Describe the change, never cite a commit SHA

Reference the change by symbol or behavior description, not by commit hash.
Rebase and force-push rewrite all commit SHAs; a draft that cites a SHA will
contain an unresolvable orphan link on GitHub the moment the branch is rebased.

**Good:**

> `has_partition_selectors` is now a property on the shared mixin instead of a
> per-subclass attribute.

**Bad:**

> Fixed in `5ab9ca3`.

## Convention 3 — Only name symbols present in the final committed diff

Before presenting a draft, cross-check every code token against the net
committed diff. Remove any reference to helpers tried and deleted mid-iteration.

Reviewers look up symbols you name. A symbol that does not exist in the final
code makes the draft look inaccurate and erodes trust.

## Convention 4 — One reply per thread, never a combined PR-level summary

GitHub's "Resolve conversation" button is per-thread. Collapsing multiple threads
into one PR-level comment breaks that workflow.

Structure:

- List threads by comment ID / URL
- One acknowledgement per thread — name the function or location of the fix,
  not a raw line number (line numbers shift on rebase)
- A PR-level comment is acceptable *in addition to* per-thread replies only when
  there is cross-thread context (e.g. "rebased + force-pushed, please re-review"),
  and it must not replace the per-thread replies

## Convention 5 — Do not overclaim a comment as "done ✅"

Distinguish between:

- "we changed code to address this" — the implementer's claim
- "reviewer accepted" — only confirmed when the reviewer presses Resolve

A thread becoming `outdated` because of an edit is not the same as resolved;
the reviewer has not clicked Resolve yet. State what changed, then stop —
whether to accept is the reviewer's call, not something the draft narrates. A plain
"Done." is fine: it only reports that the code changed. What is wrong is the ✅ or
any wording that claims the reviewer is satisfied.

A draft carried over from an earlier session or round is a claim about the
diff *as it was then*. Before handing it over again, re-check every universal
statement in it ("every resolved anchor exists", "no other provider changed",
"all callers") against the commits landed since: a later commit that widens
the set turns a verified claim into an overclaim without changing a word of
the draft. Re-verify it for the new set, or narrow it to what was verified.

**Good:**

> `_serialize_keys` now returns a `frozenset` (was `list`).

**Bad:**

> Done ✅ — fixed as suggested.

## Convention 6 — No attribution footer by default

A reply draft carries no `Drafted-by` / attribution footer. In a comparison of agent
drafts against what the maintainer posted, every draft had one and the maintainer deleted
it every time.

Add a footer only when the user asks for one (for example when a repo expects AI assistance
to be disclosed). maigo has no per-repo setting for this and none is added: the user says so,
and the footer goes on its own paragraph after a blank line and a horizontal rule, inside
the code block, with this wording:

- Agent draft, posted without prior human review:

  ```
  ---
  Drafted-by: <Agent Name and Version> (no human review before posting)
  ```

- Agent draft reviewed and approved by a human before posting:

  ```
  ---
  Drafted-by: Claude Code; reviewed by @<github-handle> before posting
  ```

In either template above, a review-body footer writes `Claude Code` exactly, with no model name
or version, and the complete footer string goes in the delegation text instead of being left for
each subagent to fill in: in one batch review, drafts written by different subagents produced four
different footers and the checker twice asked the user to confirm. This replaces the
`<Agent Name and Version>` placeholder above for review bodies only; replies in a discussion
thread carry no footer.

This convention is about replies, except that the review-body footer wording above also applies to
the `draft.md` that `/maigo:review` writes; the rest of that draft's footer handling stays in
`commands/review.md`. PR descriptions follow
[`skills/github-title-description`](https://github.com/Lee-W/maigo/blob/main/skills/github-title-description/SKILL.md).

## Comment fetch & triage, and pre-apply verification (references)

The `gh`/GraphQL queries for pulling inline threads, review summaries, and
conversation comments, the triage-file template, and the routing table for
turning selected comments into `/maigo:quick` vs `/maigo:go` work items are
in `references/comment-fetch-and-triage.md`. The same file also covers two
pre-apply verification habits: running a full before/after check on a
reviewer's *suggested* fix (not just their cited example) before applying it
literally, and checking PR review threads before a "unify / clean up" sweep
touches a line you didn't write — it may be a reviewer-directed change
already landed via `fixup!`.

Draft-shape rules (GitHub `suggestion` blocks for concrete fixes, one bullet per reviewer point,
every thread listed but only those needing a reply drafted, design replies that pitch differentiation) live in
[`references/draft-shape.md`](https://github.com/Lee-W/maigo/blob/main/skills/github-reply-draft/references/draft-shape.md).
