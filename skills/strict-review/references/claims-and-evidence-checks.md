# Strict Review — Claims and Evidence Checks

Loaded on demand by `skills/strict-review/SKILL.md`. Generic checks for the question
"does the evidence actually support the claim being made?" — in concurrent code, in text
written for humans (error messages, warnings, logs, docs), and in docs after behaviour
changes. Repo-agnostic; repo-specific recipes live in the matching domain skill.

Each item: the rule, why, how to check.

---

## 1. Concurrency: an empty or short result is not proof of "drained"

**Rule.** Under concurrency (multiple workers/replicas, `SKIP LOCKED`, lease-based claims),
a fetch that returns empty or fewer rows than the cap does not prove the backlog is gone.
Other workers may hold the locks on every remaining row. Only an authoritative,
lock-free count (`count <= cap`, or `0` when truly drained) is evidence.

**Why.** Resetting an edge-trigger / per-episode flag on an empty or short fetch re-arms
the warning or audit write while the same backlog episode is still ongoing, so the
"at most once per episode" guarantee silently breaks. Fixing only the "short fetch" path
and missing the "empty fetch" path is the typical incomplete fix.

**How to check.**
- List every code path that clears the flag (empty fetch, short fetch, count check,
  success path) and ask of each: "if another worker holds all the rows, does this path
  clear it wrongly?"
- The count query should run only when the flag is currently set, so idle ticks do not
  pay an extra query.
- Tests must simulate "everything is locked by someone else" (the fetch returns nothing
  while rows exist), assert the flag stays set and no duplicate warning/audit is emitted,
  and be mutation-checked: restore the unconditional clear and the test must go red.

## 2. Error message advice must hold on every path that raises it

**Rule.** When an error message carries a remedy ("give them different X", "use Y
instead"), enumerate every type/caller that can reach that raise and confirm the advice is
actionable for each. If not, qualify the advice in the message text.

**Why.** Advice written from the first example often fails for siblings that do not
accept that parameter; following it produces a different error (e.g. a `TypeError`),
which is worse than no advice.

**How to check.** Grep the callers/subclasses that reach the raise; try the advice on the
least-capable one. Example wording fix: "give them different prefixes" becomes "give them
different prefixes where they take one".

## 3. Deprecation warnings give the migrated value when semantics change

**Rule.** When a deprecated parameter is renamed and the new parameter's semantics differ
(for instance it now adds a separator itself), the warning must compute and print the
concrete migrated value, not just "use the new name".

**Why.** A literal rename can pass validation yet silently change behaviour (a doubled
separator in generated names), breaking hard-coded references elsewhere.

**How to check.** Feed the old parameter its realistic shapes (with and without the
trailing separator, non-identifier strings) and confirm that copying the suggested value
reproduces the old behaviour; note shapes where it cannot. Typical trap: copying the old
value verbatim (or stripping its trailing separator) still changes the result, because the
new parameter normalizes the value differently. Add a test pinning the warning text.

## 4. Log / audit text must not claim an evaluation that has not run

**Rule.** Wording in a log or audit record must match what is true at the moment it is
written. Text emitted before an evaluation loop must not say "evaluated" or "eligible",
because counts at that point may include items the loop will later skip.

**Why.** Operators read these messages to decide what to do. A claim such as "the rest
will be processed on later ticks" is false in exactly the case that needs the warning
(the oldest N items are all blocked, so the same N are re-examined every tick).

**How to check.** Read the control flow after the log call (`continue`, early return) and
list what it can still exclude; reword to what is actually known ("the oldest N were
fetched; M pending in total"). Update any test constant that matches the old string.

## 5. Docs sample output must come from the example shown beside it

**Rule.** A log block, error result, or output snippet in docs must be what the example
directly above it produces. Do not paste output from a unit-test fake as if it came from
the documented example.

**Why.** Readers (and reviewers) compare names and strings literally; a mismatched tool
or function name exposes the snippet as fabricated.

**How to check.** Capture a real run when possible. Otherwise use names the example
really calls, verified in the source, take error text from real source strings, and label
the block "illustrative, not captured from a real run".

## 6. After a behaviour change, re-derive the docs from current code

**Rule.** When later commits in the same change alter behaviour (raise conditions, limits,
defaults), re-check every doc page and docstring that describes it against the current
code, not against the earlier text or the reviewer's wording.

**Why.** Prose written before the behaviour commit goes stale in the same PR and still
looks plausible.

**How to check.** Order doc work after behaviour work; list what each behaviour commit
changed and grep the docs for each; do not promise anything you cannot verify (if a
vendor default cannot be found, say "raised" rather than quoting a number).

## 7. A count in a PR description must equal what the diff actually changes

**Rule.** When reviewing someone else's PR, check every number in the description ("changed four
tests", "touches N files", "updates N fields") against the diff. A mismatch is a must-fix: ask
the author to correct the description to the real number — don't rewrite the whole description
for them.

**Why.** The description becomes the source for the commit message and changelog; a wrong count
makes later readers believe tests were exercised by this PR that were not. Case (apache/airflow
#73607): the description said four `ModuleContract` field tests were changed, the diff touched
only two — the other two (`accepts_legacy_*`) already went through
`ModuleContract.model_validate` in the base commit.

**How to check.** `git diff --stat`, or list the changed items file by file, then compare each
claimed count. Report only the discrepancy. This is the counterpart of the rewritten-claim check
in the harness-discipline skill: that one asks whether a *reworded* claim holds per shape; this
one asks whether the *numbers* equal the diff.

## 8. A "fix flaky test" PR needs repeated-run or timeout-margin evidence

**Rule.** When reviewing a PR that fixes a flaky or timeout test, expect the description to carry
one line of evidence: either "ran the test N times in CI and it did not reproduce", or the
reasoning behind the chosen deadline/timeout value. After confirming the fix gates on a real
happens-before boundary, still raise a request for that line when it is missing. Don't block on
it if the logic is correct, but don't approve silently either.

**Why.** A flaky fix is about stability under CI timing, so one green run does not show the race
is gone. Without repeated-run results or the margin calculation, the reviewer cannot tell "race
pinned" from "race made rarer"; correct synchronization logic is necessary but not sufficient.
Seen on a shared-stream overflow test fix (apache/airflow #68651).

**How to check.** Look in the description for a run count or a deadline derivation; if neither,
ask for it as an evidence-pending item.

## 9. A query-count test that mocks a collaborator proves only the layer under test

**Rule.** When reviewing an N+1 / "constant query count" test, read what it patches. If a
downstream collaborator is mocked, the measured count covers only the tested layer, not
end-to-end behaviour. Open the mocked function, count its per-item queries, and scope the PR's
claim to the layer the test really exercises; flag over-broad wording such as "keeps query usage
stable as N grows" and say whether the residual cost is a separate optimization.

**Why.** Case (apache/airflow #65367, "Fix N+1 queries in trigger asset event submission"): the
test mocked `AssetManager.register_asset_change`, so it proved the eager-load change removed the
watcher-to-asset N+1, but `register_asset_change` itself re-queries the asset once per item. The
description's "stable query usage" was therefore over-claimed.

**How to check.** For each patched name in the test, ask whether it runs per item in production
and issues queries; if so the "constant" claim is unproven for that path.
