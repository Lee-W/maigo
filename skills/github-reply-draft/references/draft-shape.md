# GitHub Reply Draft — Draft Shape Reference

Loaded on demand by [`SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/github-reply-draft/SKILL.md)
when drafting review comments or replies. The conventions in `SKILL.md` cover tone and attribution;
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
here?". Count the reviewer's points first, make the draft match, then tighten each point's wording.

---

## Draft every thread on the list

At the `/maigo:address-comments` Finale, the draft set covers **every numbered item** shown to the
user in the triage list — including threads already replied to and resolved, and threads the
reviewer pasted twice. Whether to post, and which, is the maintainer's call, not the orchestrator's
to pre-filter.

Why: on apache/airflow #72149 the list was C1–C6 but drafts were produced only for C4–C6 (C1–C3
had been answered and resolved days earlier); after pushing, the maintainer said all six needed
drafts.

How to apply: for an already-replied / resolved item, still write a draft and put one line above
it: "this thread is already replied to and resolved — whether to post again is up to you". For a
duplicated thread, give a short draft (e.g. pointing back to the main thread).

---

## Design-discussion replies pitch differentiation, not self-critique

When drafting a reply in a PR design discussion, focus on what the proposal would provide once
built and how it differs from the existing option (e.g. a vendor provider's operator) — not on what
the current version lacks or which existing thing it is a subset of. Example: a draft on
apache/airflow #74026 said the current version "is a subset of `AgentOperator`"; the maintainer
had it rewritten as the proposal's difference from the existing approach.

How to apply: internal analysis may discuss the current version's problems; the outward reply uses
a positive positioning such as a three-way comparison — where the loop runs, what it can touch.
