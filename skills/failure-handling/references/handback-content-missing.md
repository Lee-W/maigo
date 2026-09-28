# Handback content going missing

Loaded on demand by
[`skills/failure-handling/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/failure-handling/SKILL.md) —
the detailed recovery procedure for the "handback delivered but content
missing" failure shape summarized there.

## Symptom

`<task-notification>` arrives normally with `status: completed`, and
`<result>` reads roughly "this agent's report was delivered to you as a
message from `<id>`; read it there, it is not repeated here" — but that
message never actually appears in the conversation. The report content is
lost; this is not a task failure.

## Wrong responses (wastes a full round, can pollute a shared worktree)

- Re-spawning a new agent to redo the same review / verification.
- Doing the check yourself instead (if it was a mutation-canary
  verification, this re-enters the mutation window).
- Assuming the missing conclusion was PASS / APPROVE and proceeding anyway.

## Correct recovery, three steps

1. **Independently inspect the state yourself first** (`git status --short`
   / `git diff`). Don't depend on the missing report for this — it also
   gives you something to cross-check once the report resurfaces.
2. **`SendMessage` the same agent** (by its id): "your report didn't arrive,
   don't rerun any checks, just re-paste the conclusion you already
   reached." It restates existing evidence instead of redoing the work —
   cheap.
3. Accept the re-pasted content as-is. If it volunteers extra work that's
   its choice, but asking explicitly for "just re-paste" usually prevents
   that.

Case: apache/airflow #71477 round 2 — the same reviewer's re-review
conclusion went missing twice in one session; both times handled with the
three steps above, and the second time an extra question ("which parts did
you not independently verify") was folded into the same re-paste request.

## Corollary: handback is not a lifecycle signal

**Receiving a handback message is not a signal that the agent has stopped.**
A handback is only that round's output — the agent may still be running,
still mutating a shared worktree. Always query lifecycle with `ListAgents`;
never substitute "did a report arrive" for that check.
