---
name: strict-review
description: This skill should be used when performing code review on a diff (whether implemented by another agent or an external PR), enforcing a strict reviewer stance, applying a mandatory 9-item checklist, demanding evidence, and giving specific改法 instead of vague critique.
---

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

## What this skill does NOT cover

- Writing or editing code (reviewer has read-only tools)
- Running tests (verifier's job, separate skill)
- Style-only nits already auto-fixed by formatter (don't waste must-fix slots on formatter output)
