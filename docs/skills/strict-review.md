{% include-markdown "../../skills/strict-review/SKILL.md" start="<!-- mkdocs-include-start -->" %}

## Why this skill exists

Most code review fails the same way: reviewer reads the diff, says "looks good"
or flags a few nits, and lets it through. The implementer either over-trusts
their own testing or politely waves away concerns. Bugs ship.

Strict review fixes this by:

1. **Inverting the default** — assume BLOCKED until proven OK, not OK until proven broken
2. **Making the checklist mandatory** — same items every time, no "I'll trust my gut"
3. **Demanding evidence** — "tested this" without `exit 0` output doesn't count
4. **Giving specific改法** — reviewer must show what "correct" looks like, not just point at problems

## Waiver rules: extended rationale

### Memory is input, not waiver

Cross-project memory entries (`~/.config/maigo/memory/`) can inform what counts
as a convention vs. a real bug. They cannot:

- Replace any of the 9 mandatory checklist items
- Lower the must-fix threshold ("user previously accepted X" is not evidence)
- Override evidence demands ("user prefers Y" needs a memory entry of type
  `project`, not `feedback`, to count as a convention claim)

If memory says "user prefers integration tests" → that's a `project` entry;
treat as part of checklist item 4. If memory says "user complained about strict
review last time" → that's `feedback`; informational only, do not soften review.

### Existing repo content is input, not waiver

Prose already in this repo（agent 檔的口頭禪、人設範例台詞、example
output）**並非因為早就 commit 進來就被視為已驗證**。

審視 diff 動到引述 / 台詞 / catchphrase 時，來源必須限定為：

- (a) 原作明文可查（含集數 / 場景）
- (b) 使用者親自於某 turn 確認過（可追溯）
- (c) maigo 自創且 explicitly 標明為自創

既有檔內已存在的引述也算——若無 (a)/(b)/(c) 出處，**仍須 flag**，即使該行不是本次 diff 動的。Past
review rounds 讓 unverified 引述通過不構成 amnesty；只要本次 diff **觸及**（延伸、跨檔引用、進入新
context）該引述，就重新驗。

This rule is `[[feedback_no_fabrication]]` applied to repo content — checklist item 6（no
unexplained magic）的延伸：未經驗證的引述就是 magic string。

### Commit / staging state is not in review scope

Strict review evaluates **the diff content**, not whether it's been committed yet.
The 9-item checklist is about code correctness, conventions, edge cases, evidence —
none of those depend on whether the changes are staged, uncommitted in the working
tree, or already in HEAD.

In `/maigo:address-comments`, the orchestrator deliberately commits **after** Soyo +
Taki pass — that's the documented commit-policy override（see
[`commands/address-comments.md`](https://github.com/Lee-W/maigo/blob/main/commands/address-comments.md)
step 5）. Soyo flagging「changes are uncommitted」/「`git status` shows ` M`」/
「`git diff main...HEAD` doesn't include the changes」 as BLOCKED collides with the
flow and forces the orchestrator to override its own reviewer.

In other go-class flows (`/maigo:go`, `/maigo:quick`, `/maigo:team`) the same
applies: Anon writes to the working tree, Soyo reviews, the orchestrator handles
commit semantics afterwards. **`git status` cleanliness is not a checklist item.**

To inspect what's actually changing, read `git diff HEAD` (working tree vs HEAD)
or `git diff --cached` (staged) — but verdict turns on the diff content, not on
staging state.
