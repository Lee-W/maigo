# Strict Review — Output format 骨架

Loaded on demand by [`skills/strict-review/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md) — 寫最終審查輸出（Verdict／前置驗證／Checklist／Must-fix／Nit／Evidence pending）之前讀。
本檔內文原樣自 SKILL.md 搬出。

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

`/maigo:review` 的持久報告另依
[`review-templates`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/review-templates.md)
產生共用檔頭、最後 review 時間與 reviewed commit；只保留同 source 最新完整報告。
本地「已看完」與 GitHub 已送出分開記錄，不改變審查 verdict。
