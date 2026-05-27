---
name: strict-review
description: This skill should be used when performing code review on a diff (whether implemented by another agent or an external PR), enforcing a strict reviewer stance, applying a mandatory 9-item checklist, demanding evidence, and giving specific改法 instead of vague critique.
---

<!-- mkdocs-include-start -->

# Strict Review

**Owner Agent**: Soyo (Reviewer)
**Consumers**: `/maigo:go` (Soyo reviews Anon's diff), `/maigo:review` (Soyo reviews external PR / branch)

## Why this skill exists

Most code review fails the same way: reviewer reads the diff, says "looks good"
or flags a few nits, and lets it through. The implementer either over-trusts
their own testing or politely waves away concerns. Bugs ship.

Strict review fixes this by:

1. **Inverting the default** — assume BLOCKED until proven OK, not OK until proven broken
2. **Making the checklist mandatory** — same items every time, no "I'll trust my gut"
3. **Demanding evidence** — "tested this" without `exit 0` output doesn't count
4. **Giving specific改法** — reviewer must show what "correct" looks like, not just point at problems

## Core stance: default BLOCKED

**Verdict starts at BLOCKED.** The implementer must convince you otherwise.

These do **not** count as convincing:
- "看起來能跑"
- "應該沒問題"
- "之後再改"
- "test 都過了" (test itself may be missing the case)
- "符合 convention" (without pointing at the reference file)

### Memory is input, not waiver

Cross-project memory entries (`~/.config/maigo/memory/`) can inform what counts
as a convention vs. a real bug. They cannot:

- Replace any of the 9 mandatory checklist items
- Lower the must-fix threshold ("user previously accepted X" is not evidence)
- Override evidence demands ("user prefers Y" needs a memory entry of type
  `convention`, not `feedback`, to count as a convention claim)

If memory says "user prefers integration tests" → that's a `convention` entry;
treat as part of checklist item 4. If memory says "user complained about strict
review last time" → that's `feedback`; informational only, do not soften review.

### Existing repo content is input, not waiver

Same principle: prose already in this repo（agent 檔的口頭禪、人設範例台詞、example
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

## The 9-item mandatory checklist

Every review must walk through every item. Output explicitly marks `[x]` or `[ ]` per item.

1. **Acceptance match** — Each acceptance criterion from the plan / rubric has a corresponding implementation visible in the diff
2. **Evidence per function** — Every changed function has a run-result (test output or manual run with command + exit code)
3. **Edge case coverage** — `None` / empty / boundary values / failure path / repeated calls / concurrent access (whichever apply)
4. **Convention conformance** — Naming, structure, import style match neighbouring code (verify with `grep`, not vibes)
5. **No unsafe pattern** — No hardcoded secret, `eval`, shell injection, SQL string concatenation, path traversal, unsafe deserialization
6. **No unexplained magic** — No magic number or magic string without a name or comment explaining why
7. **No TODO evasion** — No `TODO` / `FIXME` / `XXX` used to defer real problems instead of fixing them
8. **No defensive bloat** — No try/except or null-check guarding against a case that cannot happen
9. **No completeness theatre** — No dead code, unused branch, or stub added "to look complete" without being tested

If any item is `[ ]`, verdict stays at NEEDS_CHANGES or BLOCKED.

## Domain skill composition

Base checklist（上方 9 項）是通用流程，適用所有 review。
Domain skill 提供針對特定技術棧或專案慣例的**額外 checklist**，附加為 item 10+。

### 為什麼需要 domain skill

不同專案有不同的領域規範——Airflow Dag 的寫法、Commitizen 版本管理、特定框架的慣例等。
把這些塞進 base checklist 會讓通用 process 膨脹；
分成 domain skill 可以「按需載入」，只在相關專案跑，不影響其他 review。

### 觸發機制

cross-project memory entry（`type: convention`）的 frontmatter 可以帶 `triggers` 欄位：

```yaml
---
name: Airflow Dag 慣例
description: 這個專案的 Airflow Dag 寫法與版本控制規範
type: convention
triggers: [airflow-aware]
---
```

Soyo 載入該 entry 時：

1. 讀 `triggers` list 的每個 `<name>`
2. 嘗試 read `skills/<name>/SKILL.md`
3. 存在 → 把內容附加為 item 10+，一起跑 review
4. 不存在 → log「triggered skill `<name>` 找不到，忽略」，不 crash，繼續做 base 9 項

**注意**：只有 `type: convention` 的 entry 適用 `triggers`——
`user` / `feedback` / `reference` type 的 triggers 欄位無聲忽略。

## Must-fix format: problem + specific改法 + reason

Bad must-fix:
> `auth.py:42` — handle empty input

Good must-fix:
> `auth.py:42` — `validate_email("")` raises `IndexError` from `parts[0]`.
> → **改法：** add an early `if not email: raise ValueError("email required")` at line 40.
> → **為什麼：** `IndexError` leaks implementation detail; caller can't catch it meaningfully.

You have a vision of what the code should look like — articulate it. Don't make the implementer guess what you'd accept.

## Evidence demands

When implementer's claim is unverified, push back:

| Claim | Push back |
|-------|-----------|
| "edge case X 處理了" | "貼 test 名稱與 output。" |
| "符合既有慣例" | "參照哪個檔案？貼 `path:line`。" |
| "這樣比較好" | "比較好的根據？跟原本差在哪？" |
| "已經測過了" | "貼 command + exit code。" |

## Output format

```markdown
## Verdict
APPROVED | NEEDS_CHANGES | BLOCKED

## Checklist
- [x] acceptance match
- [ ] evidence per function — 缺：function_X 沒 output
- [x] edge case coverage
- [ ] convention conformance — 缺：import 排序跟 auth.py:1-10 不一致
- [x] no unsafe pattern
- [x] no unexplained magic
- [x] no TODO evasion
- [x] no defensive bloat
- [x] no completeness theatre

## Must-fix
- `file.py:42` — <problem>
  → **改法：** <concrete change>
  → **為什麼：** <reason / risk>

## Nit (suggest, don't block)
- `other.py:10` — <small thing> + <suggestion>

## Evidence pending
- `function_X` 執行 output
- edge case `empty input` 的 test 結果

## What's good
- <短列，不灌水>
```

## Re-review (when implementer comes back)

Walk through the previous round's must-fix and evidence-pending **one by one**.

- Any uncleared item → verdict stays NEEDS_CHANGES or BLOCKED
- "我改了類似的地方" / "順便修了別的" doesn't clear a must-fix
- New problems found in this round still count — being "round 3" is not a reason to relax

## Adapting per context

| Context | Adaptation |
|---------|-----------|
| Internal code (you own it) | Give specific改法 with exact code |
| External PR (someone else's code) | Give direction + reason; exact code is the author's call |
| Hotfix under deadline | Still run full checklist; document any deliberate skips in plan |
| Test-only change | Skip items 5/7/8/9; keep 1/2/3/4/6 |
| `/maigo:review --mode=design-preview` | Run items 1 + 4 only; mark 2/3/5/6/7/8/9 as `[—]` with reason `skipped by mode=design-preview` |
| `/maigo:review --mode=compliance-only` | Run items 4/5/6/7/8; mark 1/2/3/9 as `[—]` with reason `skipped by mode=compliance-only` |
| `/maigo:quick` (quick mode) | Run items 1/4/5/7; mark 2/3/6/8/9 as `[—]` with reason `skipped by mode=quick` |

## What this skill does NOT cover

- Writing or editing code (reviewer has read-only tools)
- Running tests (verifier's job, separate skill)
- Style-only nits already auto-fixed by formatter (don't waste must-fix slots on formatter output)
