# Strict Review — `/maigo:review` Output Templates Reference

Loaded on demand by [`commands/review.md`](https://github.com/Lee-W/maigo/blob/main/commands/review.md) —
the verbatim markdown skeletons for the review rubric (Tomori's step 2 output) and the
three report shapes (single PR/branch/range, multi-PR batch roll-up, bilingual). Read this
file when writing the rubric or assembling the final report.

---

## Review rubric 骨架（`.maigo/review-rubric.md`）

```markdown
# Review rubric: <PR title>

## 這個 PR 應該做到什麼（acceptance）
1. <期待行為 1>
2. <期待行為 2>

## 應該涵蓋的 edge case
- <case 1>
- <case 2>

## 可接受 / 不可接受的 trade-off
- 可接受：<例：暫時 hardcode 設定值，下個 PR 抽出來>
- 不可接受：<例：略過 input validation>

## Description 沒講清楚的地方（需要 author 補答）
- <模糊點 1>
```

## 輸出

### 單一 PR / branch / range（預設）

```markdown
# Review: <PR title / branch / range>

**PR:** <url>   <!-- GitHub PR 一律附完整連結；branch/range 無 PR 則省略 -->

## Context（樂奈）
<變更摘要 + 周邊 context 一段>

## Rubric（燈）
<rubric 摘要——詳見 .maigo/review-rubric.md>

## Verdict（爽世）
APPROVE | REQUEST_CHANGES | BLOCKED

### Must-fix
- ...（對應 rubric 哪一條）

### Nit / Evidence pending
- ...

## Verification（立希）
- `<cmd>` — exit <n> — <result>

## Bottom line
<一句話總結>
```

### 多 PR batch 最終 roll-up

batch 內最後一個 PR 跑完後，orchestrator 把「Queue 還剩...」那行改成 roll-up：

```markdown
**Summary of recommendations:**
- Approve: **#N**, **#N**
- Approve with nits: **#N** (one-line why)
- Request changes: **#N** (one-line why)
- Block: **#N** (one-line why)
- Skipped: **#N** (merged/closed/draft)
```

涵蓋整輪 batch，不只當下這個 PR。

### 雙語版（`--bilingual` 或 repo-detect 觸發）

最終 report 前加 Taiwanese Mandarin 快結 + horizontal rule，後面接既有英文 detail：

```markdown
## 台灣漢語快速結論

**PR #<N> — <short title>** <APPROVE / REQUEST_CHANGES / BLOCKED>
<1-3 句：做什麼、能不能上、最大一個 concern>

---

## English — Detailed Review

# Review: <PR title>
[（既有 Context / Rubric / Verdict / Verification / Bottom line 全段）]

---

**PR link:** <url>

<Queue / next-step line | batch 結束的 roll-up>
```
