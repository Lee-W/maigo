# Git Workflow — Shared Worktree State Volatility

Loaded on demand by `skills/git-workflow/SKILL.md` — **verification discipline for
state that can change out from under a shared worktree or a status claim you're
about to make**. Complements
[`references/outward-ops-authority.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/references/outward-ops-authority.md)'s
"re-verify git state at the start of every turn" and
[`references/worktree-hygiene.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/references/worktree-hygiene.md)'s
per-write-action reverification — this file adds the dimensions those two don't
cover: bidirectional external change, base-ref staleness, destructive-reset
safety, delegated-worktree placement, and proxy signals (CI status, changelog
lines) that look like state but aren't. Read this before restating a git/PR/CI
status claim to the user, before a destructive reset on a diverged worktree, or
before trusting a cached base ref.

---

## External change goes both directions, not just revert

A shared worktree's branch or working tree can be altered by something other
than the current session in **either direction** — not only regression (a
tracked change reverted to HEAD, a branch rebased, a whole worktree deleted)
but also forward progress (another process commits work you were mid-review
of, sweeping your own already-verified changes into a state that now looks
"already done"). Don't assume the last snapshot you looked at still describes
reality in either direction.

When a worktree/branch ref vanishes entirely (not just modified underneath
you): confirm the commit content survived in the shared object store by SHA
(`git cat-file -e <sha>`), check whether `origin/<branch>` already contains it
(subjects may match with different SHAs if it was rebased), then rebuild from
the remote rather than recreating the branch from a stale local SHA:

```bash
git worktree add <path> -b <branch> origin/<branch>
```

After rebuilding, gitignored per-worktree state (local settings, installed
dependencies) needs redoing — it isn't part of the object store. If a stale
directory is left at the target path, `git worktree add` fails on a non-empty
directory; move it aside first.

## Recompute base refs live — don't reuse a cached SHA

Any validation that depends on a base ref (`--from-ref`, an `A..B` diff, a
merge-base recorded earlier in the session) must recompute that base
immediately before running it, not reuse a value from earlier in the
conversation. An external rebase moves the merge-base without changing
anything visible in the working tree — `git reflog` showing an unrequested
`rebase (start): checkout main` confirms it happened. Recompute right before
the validation call: `git merge-base HEAD upstream/main`. A stale base silently
validates the wrong commit range while still reporting green.

## Verify before restating a state claim, not just before writing

Per-write-action reverification (see `references/worktree-hygiene.md`) isn't
enough on its own — the same discipline applies to **reporting**. Before
telling the user "not pushed", "no PR yet", "still local", or "still ahead 1",
run the check fresh rather than reusing what was true the last time it was
checked:

- `git status -sb` — ahead/behind, and a tracking ref that wasn't there before
  is itself evidence of an external push.
- `git reflog show HEAD` and `git reflog show <remote-ref>` — push/rebase
  events leave a trail (`update by push`, `rebase (start/pick/finish)`).
- `gh pr list --head <branch> --state all` — the PR may have been opened by
  someone else already.

"I haven't run push this session" is not the same claim as "nobody has
pushed." State claims are timestamped facts — restate them fresh each time
before repeating them, and when a fresh check contradicts an earlier
statement, say so plainly rather than quietly correcting course.

## Prove equivalence before a destructive reset

Before `reset --hard` (or otherwise discarding local commits) on a worktree
that diverged from a remote that was rebased, don't reason commit-by-commit —
SHAs differ after a rebase, so comparing `git log` proves nothing. Diff the
**cumulative** change on each side against its own base and compare the
diffs directly:

```bash
git diff <local-base>..HEAD             > /tmp/local.diff
git diff <remote-base>..origin/<branch> > /tmp/remote.diff
diff /tmp/local.diff /tmp/remote.diff && echo "IDENTICAL — safe to reset"
```

Confirm the working tree is clean (`git status --porcelain` empty — never
`stash` to clear it; the stash is a shared global stack across sibling
worktrees, see `references/worktree-hygiene.md`), and print the SHA being left
behind (`git rev-parse HEAD`) so it stays recoverable from the output as well
as the reflog. Re-verify after handing back — the same branch can be rebased
externally again, taking the commits you just landed off the branch tip
(still reachable via reflog and the object store).

## Verify a delegated agent's worktree-isolation placement independently

When an agent tool call uses worktree isolation (e.g. `isolation: "worktree"`)
while the prompt itself also gives an explicit, already-existing absolute path
to work in, the agent follows the prompt's explicit path via its own tool
calls — the tool's own auto-created isolation worktree is simply left unused.
Don't take the agent's own completion report as proof of where the commit
landed: independently run `git log` / `git status` in **both** the path you
gave it and the tool's auto-created isolation path to confirm the work landed
where intended before treating the task as done.

## A green/skipped CI check and a changelog line are proxies, not proof

Two distinct traps in reading state through a proxy instead of the primary
source:

- **Skipped is not passing.** On a branch CI hasn't fully exercised, a
  `skipped` check is not a check that passes — a hard hook-abort or an
  upstream job failure cascades every downstream job to `skipped`, and fixing
  one blocking layer just reveals the next one underneath it. Don't report
  "this is the only red" or "two things remain" after fixing a single layer;
  say "the next failure is X" instead of quoting a remaining count, and check
  whether the run actually evaluated everything (count `skipped` conclusions,
  look for a hook-abort rather than a clean pass list) before quoting any
  count at all.
- **A changelog/release-note line is not evidence of ownership.** A line
  crediting a PR to a distribution's release notes doesn't prove that
  distribution's code actually gained the feature — release notes on release
  branches are generated from the branch's commit range, so a sync/backport
  commit sweeps in entries belonging to *other* distributions. Before citing
  such a line as "this distribution has/claims X," resolve the referenced PR
  number and check what it actually touched
  (`gh pr view <n> --json files -q '.files[].path'`); if no touched path
  belongs to the distribution whose notes you're reading, the line is noise.
