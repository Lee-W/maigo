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
