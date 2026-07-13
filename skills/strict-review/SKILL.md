---
name: strict-review
description: This skill should be used when performing code review on a diff (whether implemented by another agent or an external PR), enforcing a strict reviewer stance, applying a mandatory 9-item checklist, demanding evidence, and giving specific改法 instead of vague critique.
---

<!-- mkdocs-include-start -->

# Strict Review

**Owner Agent**: Soyo (Reviewer)
**Consumers**: `/maigo:go` (Soyo reviews Anon's diff), `/maigo:review` (Soyo reviews external PR / branch)

## Core stance: default BLOCKED

**Verdict starts at BLOCKED.** The implementer must convince you otherwise.

These do **not** count as convincing:

- "看起來能跑" / "應該沒問題" / "之後再改"
- "test 都過了" (test itself may be missing the case)
- "符合 convention" (without pointing at the reference file)

### Waiver rules

- **Memory** (`~/.config/maigo/memory/`) can inform conventions but cannot replace any checklist item, lower the must-fix threshold, or substitute for evidence
- **Existing repo content** (quotes, catchphrases, dialogue) that appears in this diff needs a source: (a) original work citation with episode/scene, (b) user confirmed in session, or (c) explicitly marked self-created — flag even if the line wasn't changed in this diff
- **Commit / staging state** is not in review scope; `git status` cleanliness is not a checklist item — read `git diff HEAD` or `git diff --cached` for the actual changes

> Extended rationale for all three waiver rules: [docs/skills/strict-review](https://github.com/Lee-W/maigo/blob/main/docs/skills/strict-review.md)

## 前置驗證：先自證，再信 rubric / description / 前人結論

Rubric（燈寫的）、PR description、既有 review、前一輪的判斷，都是**線索，不是事實**。
進 checklist 前先自己重核一手，證明結論不是照抄轉述：

- **取一手 diff** — `gh pr diff <n>`（或 `git diff <range>`）自己看範圍，不靠 description 轉述的 +/- 行數與檔案清單
- **拉 load-bearing 行的實際內容** — must-fix 或關鍵判斷所依賴的程式碼，直接讀原始檔（`gh api .../contents`、`git show <sha>:<path>` 或 checkout），核對 rubric 說的跟 code 真的一致，不憑描述推斷
- **查 linked issue / 作者承諾** — `gh api repos/{owner}/{repo}/issues/<n>/timeline` 確認「作者說要開的 tracking issue」「linked issue」是否真的存在，不憑轉述當成已完成
- 對照後在輸出的 `## 前置驗證` 段列「查了什麼、確認/推翻了什麼」——空口結論不算 evidence

**推翻 rubric 要明講。** 若自證後發現燈的某條 acceptance / trade-off 判斷是過時或錯的，不要默默照做，也不要默默略過——在輸出的 `## Facts corrected from rubric` 段明列推翻了哪一條、依據哪個 `path:line`。

## 共用 working tree 上的審查紀律

Review 常在跟其他 session 共用的 working tree 上進行；驗證動作本身不能污染這棵樹。

- **驗證方法唯讀優先**——歸因用「讀失敗訊息指向的檔案逐一比對」，不要用 `git stash` /
  `git checkout` 對照前後差異；唯讀比對做不到才考慮下一條。
- **不得不動 tree 時的安全流程**：動前先存 `git status --short` 快照 → 執行操作 →
  復原 → 收尾再取一次 `git status --short` / `diff` 快照，證明復原後與動前逐位元組一致；
  兩份快照都要附進 review 報告當證據，不能只寫「已復原」。
- **平行 session 的暫存一律不碰**——別人的 `git stash` 條目、尚未 commit 的檔案，不讀取、
  不清除、不覆寫。

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

碰 pyproject.toml / git hook / 升 tool 版本的 diff 時，對照 `references/tooling-conventions.md` 的 tooling 慣例把關。

## Domain skill composition

Base checklist（上方 9 項）通用於所有 review。Memory entry（`type: project`）的 `triggers` 欄位可附加領域 checklist：

```yaml
triggers: [airflow-aware]
```

Soyo: read `skills/<name>/SKILL.md` → append as item 10+. If not found, log and continue.
Only `type: project` entries support `triggers`; `user` / `feedback` / `reference` types are silently ignored.

## Must-fix format: problem + specific改法 + reason

Bad must-fix:
> `auth.py:42` — handle empty input

Good must-fix:
> `auth.py:42` — `validate_email("")` raises `IndexError` from `parts[0]`.
> → **改法：** add an early `if not email: raise ValueError("email required")` at line 40.
> → **為什麼：** `IndexError` leaks implementation detail; caller can't catch it meaningfully.

You have a vision of what the code should look like — articulate it. Don't make the implementer guess what you'd accept.

## Evidence demands

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

## 前置驗證
- `gh pr diff` — 範圍 +A/-B，N 檔（自己核，非轉述）
- 讀 `path:line` 原始碼 — 確認 <rubric 某判斷> 屬實 / 推翻
- timeline 查 linked issue — <有 / 無>

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

## Facts corrected from rubric（推翻燈的判斷時才寫，否則省略）
- <rubric 的哪條 Decision / acceptance> — 實查 `path:line` 後推翻，因為 <證據>
```

## Re-review (when implementer comes back)

Walk through the previous round's must-fix and evidence-pending **one by one**.

- Any uncleared item → verdict stays NEEDS_CHANGES or BLOCKED
- "我改了類似的地方" / "順便修了別的" doesn't clear a must-fix
- New problems found in this round still count — being "round 3" is not a reason to relax

**Mutation test 作為修法驗證證據**：光看「新增的斷言轉綠」不夠——測試可能本來就不會失敗，
或斷言弱到修法被拆掉也不會紅（安慰劑測試）。要求：暫時拆掉修法本體 → 對應測試必須轉紅
（證明測試真的在守這條修法）→ 復原修法 → 測試轉綠。復原動作依上方「共用 working tree 上的
審查紀律」的安全流程執行，並用備份檔／`git diff` byte-compare 證明復原乾淨、無殘留改動——
這份 mutation-test 證據是修正輪 evidence 的必要項，不是加分項。

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

## Recurring must-fix patterns

Cross-cutting patterns that surface frequently; treat as supplements to the 9-item checklist.
Full rationale and recipes in `references/recurring-patterns.md` — read it when a pattern applies.

- **Commit body is a contract** — behavioral claims in the commit body must match the diff;
  mismatch is must-fix (implement the promise or rewrite the body). Details: `references/recurring-patterns.md`.
- **Underscore-private exception that consumers `isinstance`-check is de-facto public API** —
  rename + add to `__all__`; siblings never branched on by type can stay private.
  Details + Airflow case studies: `references/recurring-patterns.md` and
  `skills/airflow-aware/references/review-checks.md`.
- **New public symbol must export at the same surface as its siblings** — a new
  Enum/class/type consumed by a user-facing kwarg must be reachable from the same
  top-level import as the sibling class that uses it; missing `__all__` / lazy-import
  entries is must-fix, not nit. Details: `references/recurring-patterns.md`.
- **測試要預設用 parametrize** — 疊 assert 或近重複 test method → must-fix，拆成
  `@pytest.mark.parametrize` + `pytest.param(..., id=...)` 標 case 名稱。
- **不要框框式區段分隔註解** — `# ----` / `# --- 區段名 ---` 全刪含 label，靠函式邊界與空行分段。
- **Concurrent PR 根本修法優先** — 有 SDK 層根本修法時肯定當前解但明確指向根本修法，說明 supersede 關係。
  Details: `references/recurring-patterns.md`.
- **Naming: by what it is, not its first caller's use case** — a name coupled to one caller's context misleads and blocks reuse; generalize it.
- **Naming: private helper name carries the domain noun** — behavioral qualifiers ("once", "dedup") go in the docstring, not the name.

## Test conventions (references)

Seven test-writing / test-review patterns for mock assertions, sequence
coverage, boundary pairing, and forced-churn discipline; details and worked
examples in `references/test-conventions.md`:

- **Mock assertions** — prefer `m.method.mock_calls == [mock.call(...)]` over `assert_called_once_with`.
- **Full-sequence assertions** — assert the whole iterable/list, not head+tail+length.
- **Cap-boundary pairs** — a numeric cap needs both an at-cap (allowed) and one-over-cap (trips) test.
- **No thin test helpers** — assert only the field the function under test decides; skip one-use wrapper helpers.
- **Minimize forced test churn** — keep an existing test's diff to the forced minimum; add a new test for new behavior.
- **Build the fixture, don't defer** — a missing example fixture is not "can't test"; build the smallest purpose-built one.
- **Log assertion when the log IS the observable** — Airflow's "no caplog" rule is about scraping vs. checking logic, not a ban on asserting an operator-visibility log call via a mocked logger.

## Design integrity checks (references)

Four cross-cutting patterns that surface on framework/base API work and rebase workflows;
details and recipes in `references/design-integrity.md`:

- **Base-layer completeness** — base must be complete for all known downstreams before release; defer = must-fix.
- **No "experimental" hedge** — answer a lock-in concern with a technical argument or a design fix, not a label.
- **Don't trust green after fold-fixup rebase** — test files can silently revert to a deleted API; grep deleted symbols before accepting "tests pass."
- **Prefer polymorphism over type-switching in the caller** — an `isinstance` chain or type-flag branch in the caller is a signal to push behavior onto a base-class method instead; don't extend the switch with a new flag.

## Review judgment: when NOT to flag (references)

Twenty principles for calibrating whether a finding is a real must-fix and how
much change a comment warrants; details in `references/review-judgment.md`:

- **Verify repo config first** — grep linter config + sibling files before flagging a PEP / textbook rule.
- **Don't escalate coverage gap to correctness bug** — verify reachability + not-by-design (and blast radius — a removed guard isn't automatically must-fix) before calling it a bug.
- **Don't adopt regression framing uncritically** — verify the claim against HEAD; reply-only may be correct.
- **Proportionality** — COMMENTED nit does not justify a cross-hierarchy refactor; do the minimum proportionate change.
- **Don't flag squash-before-merge history** — pre-merge commit count / fixups vanish on merge; flag content violations, not history shape.
- **Prove a security/authz guard is load-bearing by removing it** — delete the guard, run the security test, confirm the flip, then restore.
- **Ground scope claims in the actual checker** — run the linter/hook and quote its output; never extrapolate a count from a raw grep.
- **A "minimize changes" instruction never licenses keeping a disproven fact** — fix the wrong token, keep the rest minimal.
- **Prefer conforming new code to an existing checker over extending the checker** — a local annotation fix beats a cross-cutting change to checker logic.
- **Verify installed-package evidence against the commit actually under test** — confirm the `.venv` matches the commit's lockfile and Python-version marker before citing package source.
- **Judge only the current/latest diff state** — commit history and prior review rounds are irrelevant to the verdict.
- **Don't silently overwrite a prior round's verdict** — a stricter new verdict needs discriminating evidence; surface conflicts to the user instead.
- **Verify a cited convention belongs to the same architectural layer** — a same-codebase precedent from a different layer is a category error, not support.
- **Calibrate naming-nit persistence by visibility** — one round then drop for private names; public API naming drift is worth pushing on.
- **Verify a hard-limit claim before asserting "impossible" or "breaking"** — check release status and actual tool capability before foreclosing an option.
- **A reviewer's "strict / validate / enforce" wording may not match the schema** — check the underlying data model and sibling commands before implementing literally.
- **Don't demand a thin wrapper validate the wrapped library's own semantics** — and don't flag an eager-to-lazy init refactor as breaking without a concrete consumer signal.
- **Rank designs by the actual cadence of their cost path** — verify trigger frequency in code, not by feel; verify assumed costs too.
- **Verify a mechanism claim empirically** — write a small isolated repro before publishing a "why this works/breaks" explanation.
- **Trace the introducing commit before reverting a shared signature** — a type error at a changed signature's use site is usually an incomplete rollout, not a wrong change.

Read `references/review-judgment.md` when deciding whether to flag and how large to make the change.

## What this skill does NOT cover

- Writing or editing code (reviewer has read-only tools)
- Running tests (verifier's job, separate skill)
- Style-only nits already auto-fixed by formatter (don't waste must-fix slots on formatter output)
