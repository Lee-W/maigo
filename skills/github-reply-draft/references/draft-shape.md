# GitHub Reply Draft — Draft Shape Reference

Loaded on demand by [`SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/github-reply-draft/SKILL.md)
when drafting review comments or replies. The conventions in `SKILL.md` cover tone, length and the optional footer;
this file covers the **shape** of a draft: what form each comment takes and which threads it must
cover.

---

## Use a GitHub `suggestion` block when the fix is concrete

When drafting an inline review comment, if the recommendation can be expressed as a concrete
replacement for the anchored line (or a few lines), write it as a ```` ```suggestion ```` block
followed by one short sentence of reason (e.g. "I think we need this to fix the CI"). Reserve prose
for comments that are questions or need design discussion.

Why: in a batch of apache/airflow reviews (#73991, #73984, #73957) the maintainer rewrote every
spot that had a concrete fix — a `type: ignore`, version wording, a docstring, a rename, a comment
— into a suggestion block; the drafts had described them in prose.

How to apply: before writing an inline comment, decide whether there are lines that can be
replaced outright. If yes, the block must contain the complete new content of the anchored lines,
with the reason in one line, in the maintainer's habitual register ("I think", "IIUC").

---

## Mirror the reviewer's bullets one to one

When replying to a single reviewer comment that lists several points, the draft has the same
number of points, in the reviewer's order. Do not merge adjacent points to be concise. A first
draft that folded two test points into one (4 bullets for a reviewer's 5) drew "only 4 points
here?". Count the reviewer's points first, make the draft match, then tighten each point's wording. This is one of the "more than one sentence" cases in `SKILL.md`'s voice baseline: one short line per point, no extra explanation after them.

---

## List every thread; every thread with something to act on gets a pasteable reply

At the `/maigo:address-comments` Finale, the draft file lists **every numbered item still open** in
the triage list — including threads already replied to but unresolved, and threads the reviewer
pasted twice. A thread the reviewer has already resolved is not listed at all (step 6 re-fetches
thread state first); it is mentioned only in the one summary line. Listing is not pre-filtering:
the user still sees every open thread and decides.

**Every reviewer inline thread gets a pasteable reply** in a fenced `text` block, including a nit
that was simply done. A reviewer who gets no reply cannot tell whether the point was handled, so
the user should not have to write even the trivial ones.

**A done-as-asked point gets a very short reply**: usually one word to one short sentence
(`removed`, `dropped it`, `updated`, or one line saying what it became). No explanation, no
pleasantries. The other conventions are unchanged: describe the change rather than citing a commit
SHA, cite only symbols that are committed, no footer, no `@`.

**A point that needs substance** keeps the normal wording and length rules: the reviewer asked a
question; the change differs from what they suggested; the point was deliberately not changed; the
work is deferred (follow-up PR, later).

**No reply needed** is kept only for two cases: (a) a comment with nothing to act on and nothing to
answer (praise, plain agreement); (b) a thread the author has already replied to (do not draft a
duplicate reply; the entry notes "already replied to"). The entry keeps its heading, location and original-comment link, and its
reply line reads `不必回覆：無需處理` with no fenced block, so there is nothing to copy by mistake. If
the change was not actually run, every entry (including 不必回覆) still carries a `備註` line saying so.

Why: an earlier rule drafted long replies for every thread, including resolved ones (those are now
not listed); across one PR with 15 resolved threads the maintainer posted none of the 13 drafts, and
in general the posted replies were far shorter than the drafts or absent. The conclusion is that a
draft must be shorter, not that it can be skipped: a later rule skipped replies for done-as-asked
nits, and on a PR with 9 inline threads 8 had no draft, so the user wrote `removed`, `dropped it`
and `yes, missed this one. updated` by hand. Done-as-asked replies are therefore one word or one
short sentence.

How to apply: for case (b), an already-replied item that is still unresolved and needs nothing more,
write the `不必回覆` entry with a note of why ("already replied to"). For a
duplicated thread, give a short draft (e.g. pointing back to the main thread). In the
conversation's table, the 動作 column says `貼` or `不必回覆` per item.

---

## Design-discussion replies pitch differentiation, not self-critique

When drafting a reply in a PR design discussion, focus on what the proposal would provide once
built and how it differs from the existing option (e.g. a vendor provider's operator) — not on what
the current version lacks or which existing thing it is a subset of. Example: a draft on
apache/airflow #74026 said the current version "is a subset of `AgentOperator`"; the maintainer
had it rewritten as the proposal's difference from the existing approach.

How to apply: internal analysis may discuss the current version's problems; the outward reply uses
a positive positioning such as a three-way comparison — where the loop runs, what it can touch.

---

## When the user brings their own draft to confirm, fix correctness only

If the user pastes a draft they wrote and asks "is this right?" or "give me a copyable version", treat it as a **confirmation**, not a rewrite. Change only three things: factual errors, typos, and points the draft never answers from the other side's question. List what changed. Keep the wording, paragraph order, bullet layout and tone as they wrote them.

Why: a user twice objected to "don't change my format so much" after the draft was rewritten wholesale in the assistant's style.

How to apply: decide first whether the user wants confirmation or a rewrite; if they did not say rewrite, it is confirmation. If the draft has hard line breaks mid-paragraph, point out that GitHub joins them while Slack does not. Wrap the returned text per [`copyable-deliverable`](https://github.com/Lee-W/maigo/blob/main/skills/copyable-deliverable/SKILL.md).

---

## Technical assessments to colleagues or the community stay conservative

When drafting an outward technical assessment (a reply to a colleague or a community thread — Slack, GitHub, mailing list):

- **No effort-size labels** ("medium effort", "doable in a week"). Describe which layers the change touches and how many kinds of change it needs.
- **Do not mention processes or artifacts not yet decided** (an AIP, a design doc, a roadmap) unless the user asks.
- **Do not decide for the asker whether it is worth doing.** State facts, the blast radius and the existing alternatives; the judgment stays with them.
- If asked whether the effort is proportionate to the problem, answer with the facts about the problem's size (is there an alternative today, which scenarios it covers), not "worth it" or "not worth it".

Why: once a label or a process name is in an outward reply it reads as a commitment the user must then own; in one thread the user corrected the draft three times on exactly these points.

How to apply: before handing the draft over, scan for effort labels, process names and value judgments, and rewrite each as a statement of fact.
