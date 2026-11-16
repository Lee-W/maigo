# Strict Review — Reviewer Comment Taxonomy

Loaded on demand by `/maigo:address-comments` (step 7), `/maigo:retro --pr` and
`/maigo:crystallize`. A fixed list of categories for classifying what an external
reviewer pointed out, so the same lesson can be counted across PRs instead of being
re-described each time. Each category has a short key, one definition, and the rule that
should already have caught it before the PR was opened.

Origin: a hand-classified sample of review comments on apache/airflow PRs. Counts in that
sample are approximate (about ±3 per category) and concentrated in a few large PRs, so the
keys are a way to count, not a measured ranking. A category with no existing rule is a gap
in maigo; a category with a rule that still showed up means the rule was not applied in the
first round only if the PR was opened through go or team after the rule landed; go reviews
are not recorded, so that needs the user's confirmation.

Use a key as the `category` value of a memory entry (see
[`docs/reference/memory.md`](https://github.com/Lee-W/maigo/blob/main/docs/reference/memory.md)),
and record each PR the same lesson appeared in under `seen_in`.

## Categories

| key | Definition | Rule that should have caught it |
|---|---|---|
| `doc-claim-drift` | A doc, docstring, changelog line or PR description says X while the code or a sibling doc says Y; a released changelog section rewritten. | [`pre-pr-sweeps.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/pre-pr-sweeps.md) sweep (a); strict-review item 1; [`claims-and-evidence-checks.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/claims-and-evidence-checks.md) section 6. |
| `edge-case` | A boundary the author's tests did not exercise (empty or duplicate input, nested or list forms, variant implementations, time zone or locale, retry or concurrency). | strict-review item 3, checked against the edge-case categories the plan lists per step. Facts that need the reviewer's domain knowledge belong to `domain-knowledge`, not here. |
| `test-cannot-fail` | A test that cannot fail, is too weak, is redundant, or is not collected by CI. | `pre-pr-sweeps.md` sweep (b); strict-review item 2 and the Mutation test section of [`SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md). |
| `design-duplication` | The same helper, constant or paragraph exists twice. | `pre-pr-sweeps.md` sweep (d). Direction choices (abstraction, public versus private, protocol versus duck typing) are reviewer taste: no rule. |
| `released-compat` | A change that affects users of an already-released version (removed alias, changed default, edited released changelog section, stability policy). | `pre-pr-sweeps.md` sweep (c); for apache/airflow, [`review-checks.md`](https://github.com/Lee-W/maigo/blob/main/skills/airflow-aware/references/review-checks.md) release-tag section. |
| `style` | Naming, docstring length, dead code, import placement, visibility. | strict-review item 4 (convention conformance) and the language layer, [`python-aware`](https://github.com/Lee-W/maigo/blob/main/skills/python-aware/SKILL.md). |
| `scope` | A test or change unrelated to the PR's subject, or a test that already passes on the base branch. | `pre-pr-sweeps.md` sweep (e). |
| `ci-compat` | A failure that only shows in CI or the compat matrix (import fails collection on an older version, type-check stub error). | Partly: sweep (b) checks that CI collects new test files. Running or reading the compat matrix before opening the PR has no rule. |
| `pr-conflict` | The change conflicts with the base branch or with another in-flight PR touching the same text. | No existing rule. |
| `translation` | Wording of a translated string. | No existing rule; needs a native reviewer. |
| `perf` | A measured performance regression. | No existing rule; the reviewer ran the measurement. |
| `domain-knowledge` | A fact true only for one repo, module or external system that the author could not have known without being told (a library's internal behaviour, a project policy, a platform constraint). | No general rule: it cannot be written as a repo-independent self-review rule. Belongs to the matching repo's aware skill (for apache/airflow, [`airflow-aware`](https://github.com/Lee-W/maigo/blob/main/skills/airflow-aware/SKILL.md)). |

`domain-knowledge` is kept apart from the other keys on purpose. Once a reviewer has said it, the
fact is no longer only the reviewer's, and the next change to the same code can check it first, so
it is worth recording. But it is not a missed rule: it does not count toward the "rule exists" or
"rule existed but missed" tallies, and it does not graduate into the general `strict-review` or
`python-aware` skills.

Do not write reviewer or author names or GitHub logins into a memory entry, a skill or a
reference; keep the PR number and the category only.
