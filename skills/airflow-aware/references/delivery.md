# Airflow delivery conventions — docs sync, QA/status docs, PR hygiene, backports

Loaded on demand by `skills/airflow-aware/SKILL.md` §6, §8 and §11 — the supporting detail behind
the delivery-completeness, PR/commit and backport rules. Read this file when finishing a
user-facing feature, drafting a QA plan or status doc, opening a docs PR, writing a doc-only
commit subject, or judging a backport drift-check failure.

---

## Public-symbol sync (docs side)

Whenever a public symbol is added or removed,
`task-sdk/docs/api.rst` and the corresponding `airflow-core/docs/` `.. autoapiclass::` entries
must be updated together with `__init__.py` / `__all__` / lazy-import table.
Dropping a removed symbol and adding a new one are both required — a missing deletion causes
`breeze build-docs` to crash at Sphinx import time; a missing addition causes a silent gap
in the API reference. After editing, `grep` the old symbol name across `docs/` to confirm
no stale references remain.

Why: apache/airflow PR #64571 (`Window` / `RollupMapper`) and the partition-mapper
refactor both shipped with example + docs in the same PR; missing either was flagged in
round-1 review.

## QA / status-doc conventions

When drafting or reviewing a manual QA plan, feature-coverage matrix, or
status doc for a feature that ships:

- **Don't add a "serialization round-trip" manual QA item.** The scheduler
  only ever reads serialized Dags, so every functional test in the plan
  already exercises the deserialized form implicitly — a broken round-trip
  would make those functional checks fail first. Field-level lossless
  round-trip belongs in a pytest unit test, not a manual QA row. The one
  legitimate manual touch is a first-time smoke glance at the
  `serialized_dag` JSON when a brand-new param ships — that's dev smoke, not
  a recurring QA item.
- **Don't leave "not done yet" signals in a status/QA doc meant to record
  completed work** — drop header decorations like `✅ merged` / `🚧` / `❌ not
  native`, and avoid absence-wording for deliberately-scoped behavior
  (`not implemented`, `scoped out`, `ad-hoc`/`throwaway` for a fixture).
  Describe an intentionally-scoped feature positively as the current design,
  not as a gap measured against something that was never built. An **empty**
  results column (template waiting to be filled) is fine — that's not a
  not-done signal. Once a results column is actually **filled**, a per-row
  `✅ Pass (...)` marking the verification method is good practice — the
  no-decoration rule governs headers/progress marks and "not done" phrasing,
  not a factual pass/fail record.
- **A defect found in the example Dag / test fixture while QA-ing a feature
  is in scope to fix**, not just to log. If the bug is in the shipped example
  producer/consumer rather than the feature under test, fix it and fold the
  fix into the same PR (ask before editing the shared artifact) — a broken
  example is a broken user-facing artifact, and fixing it is part of
  finishing the QA.
- **Scope an unreleased-version doc/QA plan to the release branch's actual
  HEAD, not just a beta/rc tag.** When only a beta/rc tag exists (e.g.
  `3.3.0b1`), the release branch (e.g. `v3-3-test`) keeps accumulating
  commits after the tag — the tag is not the source of truth. After scoping
  against a tag, run `git log --oneline <tag>..HEAD -- <relevant paths>` and
  fold in the behavior-changing commits found there before calling the doc
  current. A beta tag isn't a real release for this purpose either — it
  doesn't freeze scope or API, the same instinct as treating a pre-release
  tag as authoritative for API stability.

## A docs page PR needs a before/after screenshot at PR-open time

If this PR adds or changes a docs page, attach a before/after screenshot at PR-open time —
a new reader-facing docs page counts as user-facing for the PR template's screenshot
requirement, even though "it's just docs." Don't wait for a reviewer to ask. See the
screenshot procedure in `verification-tooling.md` §6.

## Don't prefix a doc-only commit's subject with `Docs:`

The subject of a doc-only commit must not start with `Docs:`. `docs` is
itself a Conventional Commits type name, so
`scripts/ci/prek/check_no_conventional_commit_message.py` matches
`Docs:`/`Docs/` against its fixed `CONVENTIONAL_TYPES` list and fails the
hook — even though `AGENTS.md` explicitly allows area-tag prefixes like
`UI:`/`API:`/`Helm:` (those aren't in `CONVENTIONAL_TYPES`, so they pass).
Write plain prose describing user impact instead (e.g. "Sync
`LLMRetryPolicy` docs with the `redact_exception` default" rather than
"Docs: Sync..."). If `check-no-conventional-commit-message` fails, drop
the leading type-like prefix and retry — don't reach for `--no-verify`.

## Backport judgment

When a backport branch's drift-check fails because it references something
(a file, a test site) that doesn't exist on that branch, check whether the
**underlying capability** is already present on the branch before deciding
the check should just be narrowed in scope. If the capability shipped but
the newer test coverage for it didn't get backported, the right move is
usually to backport the source PR that added the missing coverage — not to
shrink the check to stop noticing the gap.

**Backporting to `airflow-ctl/v*-test`.** That branch ships only `airflow-ctl/`, and CI runs
`airflow-ctl-tests` only. Three adjustments follow:

- **Drop `airflow-core` hunks.** A cherry-pick from main that also touches `airflow-core` (for
  example a decorator plus its import that main added alongside the ctl change) must be dropped
  unless the symbol exists on the base. Run
  `git grep <symbol> upstream/airflow-ctl/v0-1-test -- airflow-core` before keeping it. Default:
  drop it and do not backport the helper. A reviewer will otherwise find an import pointing at a
  symbol the base does not have.
- **Tests follow the base's datamodel.** `airflow-ctl/src/airflowctl/api/datamodels/generated.py`
  is generated, and its field defaults can differ between main and the release branch (for
  example `ClearTaskInstancesBody.run_on_latest_version` is `None` on main, `False` on
  `airflow-ctl/v0-1-test`). A cherry-picked test that asserts a datamodel default must follow the
  base's `generated.py`: change the expected value, never edit `generated.py` or loosen the
  assertion.
- **Verify in a dedicated environment.** The main worktree's shared `.venv` carries editable
  provider installs that exist only on main (stale `.pth`), so on a release branch any
  `import airflow` dies with `ModuleNotFoundError: No module named 'airflow.providers.<x>'`. Use
  `env UV_PROJECT_ENVIRONMENT=<scratch dir> uv run --frozen --python 3.12 --project airflow-ctl pytest <paths>`
  and pin `--python`; a fresh env otherwise picks a Python without pydantic-core wheels.

## Bot-opened CI-upgrade backport PRs: find the main follow-up, and push only with explicit say-so

Applies to a bot-opened `[v3-x-test] Upgrade important CI environment` backport PR whose checks are widely red while the release branch itself is green. The bot regenerates such PRs on its own schedule.

**Diagnose: the root cause is usually a main-side follow-up that was never backported.** The dependency upgrade in the bot's `uv.lock` bump needed a companion fix on `main`, and that fix is missing on the release branch. Case (#76524): `uv.lock` moved Celery from 5.6.3 to 5.7.0; 5.7 no longer exports `retry` from `celery.backends.database`, so `celery_executor_utils.py` raised `ImportError` at import, and the DB, Non-DB, K8S, Special and PROD e2e jobs all went red together; the matching fix on `main` was #76591. Fixing job by job is wasted work when the failure surface is this wide.

1. Read the failure logs of several jobs from different categories and find the first error they share.
2. Look for the corresponding fix on `main`.
3. Cherry-pick it as-is on top of the bot's commit, and reconcile it with `git patch-id --stable` against the `main` commit.
4. Re-check the PR head (below), then push as a fast-forward to the bot branch.
5. The bot overwrites that commit when it regenerates the PR. For a fix that must last, open a separate backport PR.

**Pushing to the bot's branch on apache is a per-time exception to "push only to your fork", and it needs the user's explicit instruction every time.** Authorization from an earlier push does not carry over. This does not conflict with the push rule in [`git-workflow` outward-ops-authority](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/references/outward-ops-authority.md): pushing stays the user's action unless the user has explicitly instructed this one push for this PR. Only with that instruction may the orchestrator run the single fast-forward push; without it, hand over the command and stop. Before pushing, all three must hold, otherwise stop and report:

- The user said to push to upstream for this PR.
- `gh pr view <N> --repo apache/airflow --json headRefOid` equals the parent of your fix commit (the bot can regenerate the PR at any moment).
- The push is a fast-forward (`git push <apache remote> <local>:<bot branch>`), never forced. Confirm the apache remote's name with `git remote -v` first; `origin` may be a fork.

## Review fixes on an apache/airflow PR branch land as `--fixup` commits, and the user squashes and pushes mid-review

When handling review comments on a PR branch in `apache/airflow`, the orchestrator lands each work item's
fix as `git commit --fixup=<the PR's main commit>`, with no `Co-Authored-By` trailer, and does not push.
The mechanics (`--fixup` plus autosquash, "commit yes, push no") are in
[`git-workflow`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/references/commit-hygiene.md);
this section only adds the Airflow default and the timing.

- Autosquash, rebase onto the latest `main`, and push are the user's actions, and they may happen while the
  orchestrator is still reviewing. Before touching the branch, re-read `git log -1` and `git status` instead of
  assuming HEAD is where it was last seen; an unexpected rebase or commit means the user acted in a parallel
  terminal ([`worktree-hygiene.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/references/worktree-hygiene.md)).
- Example: across one three-round fixup sequence, the user squashed and pushed twice on their own.

## Review-time diff basis: `origin` may be a stale fork, and a stacked PR's base is not `main`

Scope gate: applies when reviewing or addressing comments on a local branch, or when a PR's base branch is not `main`.

- **`origin/main` can be wrong.** In an Airflow checkout `origin` can be the user's fork, whose `main` is out of
  date, while the PR itself lives in `apache/airflow` and the local branch has usually been rebased. A
  `git diff origin/main...HEAD` then lists dozens of files that are not the PR's (one review saw 44 files where the
  PR's real change was 2). Count the branch's commits with `git log --oneline` and diff `HEAD~N..HEAD`, or diff
  against upstream's `main`. When the pushed head's SHA differs from the local HEAD, use `git range-diff` to tell a
  rebase from a content change.
- **Stacked PRs.** Before reviewing, run `gh pr view <n> --json baseRefName,baseRefOid`. If the base is another PR's
  branch:
  - `gh pr diff` is the increment over that base and is the review target.
  - A local `git diff origin/main..<ref>` is **not** the PR diff: it folds in the parent PR and upstream drift
    (one case: GitHub showed 8 files, the local diff against `main` showed 21). For the increment use
    `git diff <parent head> <this head>` after `git merge-base --is-ancestor` confirms the parent is an ancestor.
  - Checks on such a PR may show every job as skipping. Don't read that as evidence either way; say "CI gives no
    evidence" in the report and ask the author to post results after retargeting to `main`. The *reason* they skip
    (a workflow filter on the base branch) is an inference: the workflow configuration was not read to confirm it.
  - Review the parent PR separately.
  - If the parent later squash-merges, the child needs `rebase --onto`; a local review normally doesn't simulate
    that, so list it as unverified.
