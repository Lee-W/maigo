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
