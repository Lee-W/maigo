# Git Workflow — Outward Ops Authority

Loaded on demand by `skills/git-workflow/SKILL.md`'s "Pushing and opening a
PR" section — **case studies for why outward/irreversible git and GitHub
operations (commit, push, force-push, opening an issue/PR) stay the user's
to run**, not the orchestrator's default action.

---

## The user drives outward git ops; the orchestrator only drafts

A peer-level maintainer commonly commits, `--amend`s, `fixup!`s, and
`force-push`es **between** conversation turns, and opens PRs themselves —
branch tip and PR state can change several times across one session without
the orchestrator having run any of those commands.

**Why:** outward / irreversible git actions (commit, push, force-push,
opening a PR) are the kind of thing this user wants to keep in their own
hands, not delegate to the orchestrator.

**How to apply:**

1. At wrap-up, only **draft** the commit message and PR title+body (in a
   copyable fenced block) with the commands the user would run themselves.
   Don't auto-run `git commit` / `git push` / `gh pr create` /
   `--force-with-lease`.
2. **Re-verify current git state at the start of every turn**
   (`git rev-parse --abbrev-ref HEAD` + `git status --short` + `git log -1`)
   — don't trust a snapshot from an earlier turn. Branch/tip state can have
   moved (amend, branch switch, force-push) since it was last checked; if
   the state doesn't match expectations, investigate (`git reflog`) before
   acting, and report the discrepancy plainly.
3. **Creating a PR and editing an existing one's description are not the same
   authorization.** Once the user has explicitly authorized opening a new PR,
   running `gh pr create` on their behalf is fine. Editing the description of
   an **existing** PR is different — never run `gh pr edit` on their behalf,
   no matter what authorization was given for creation. Hand over a complete
   replacement body in a fenced code block (one block per PR, labeled with the
   PR number and base branch) and let them paste it themselves; preserve
   whatever `Generated-by:` wording that PR already carries rather than
   normalizing it to a different agent-name string.

## Don't casually open a GitHub issue or PR

Creating an issue or PR is visible to others and hard to walk back — treat
it with the same caution as any other irreversible, outward-facing action.

**Why:** an issue/PR opened as a side effect of a routine gate — e.g. one
"should we open a tracking issue?" option bundled into a batch of otherwise
routine must-fix/nit triage questions — doesn't give the user a real chance
to review the actual title/body before it goes out. It reads as a low-stakes
checkbox, not a publish decision.

**How to apply:**

- Default to *drafting* the issue/PR body and showing it to the user, then
  waiting for an explicit "yes, post this" — never fold the create/don't
  decision into a batch of otherwise-routine gate questions.
- This applies even when the user has already agreed in principle that "a
  tracking issue should exist eventually" — agreeing something should exist
  is not authorization to author and publish the exact wording right now.
- Content requirements for *when* a tracking issue is substantively required
  (as opposed to whether you may open one yourself) are a separate, adjacent
  rule — see the airflow-aware "forward-looking comment" check in
  [`skills/airflow-aware/references/review-checks.md`](https://github.com/Lee-W/maigo/blob/main/skills/airflow-aware/references/review-checks.md).

## Fixing an already-pushed branch: commit locally, don't push

When fixing an already-pushed PR branch (resolving a committed merge
conflict, squashing a `fixup!`, amending a message), do the local
commit/amend and **stop**. Do not list force-push as the recommended action
or run it — the user runs the push themselves.

**Why:** in one session the orchestrator put "squash + force-push" forward
as the *recommended* option; the user interrupted, chose "commit locally, no
push," and had the orchestrator amend and stop instead. History-rewrite +
outward push is theirs to control — distinct from the "don't casually open
an issue/PR" rule above, which covers *creating* new GitHub objects rather
than *pushing* an existing branch.

**How to apply:** after making the branch correct locally, report the commit
hash and that nothing was pushed; mention `--force-with-lease` is needed
when the user is ready, but don't run it or frame it as the recommended next
step.
