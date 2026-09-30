# Strict Review — `/maigo:review` Output Templates Reference

Loaded on demand by [`commands/review.md`](https://github.com/Lee-W/maigo/blob/main/commands/review.md) —
the markdown skeletons for the review rubric (🩵 Tomori's step 2 output) and the
three report shapes (single PR/branch/range, multi-PR batch roll-up, bilingual). Read this
file when writing the rubric or assembling the final report.

---

## Review rubric 骨架（`.maigo/review/<id>/rubric.md`，路徑見 [`pr-context-cache`](https://github.com/Lee-W/maigo/blob/main/skills/pr-context-cache/SKILL.md) 或 `scripts/artifact_path.py`）

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

報告正文先寫到 scratchpad，再交
[`scripts/review_report.py publish`](https://github.com/Lee-W/maigo/blob/main/scripts/review_report.py)
產生最新 `.maigo/review/<id>/review.md`。所有版型共用檔頭與 TOC；不是讓每個模型自行
猜 anchor 或 review 時間。orchestrator 讀回最終檔案呈現，檔案與對話使用同一份內容。

共用檔頭由 publisher 產生：

```markdown
# Review: <title>

**Source:** <canonical PR URL / branch / range>
**最後 review：** <ISO 8601，含時區>
**Reviewed commit:** <full SHA>
**Verdict:** <verdict>

## TOC

- [Context（🐱 樂奈）](#review-section-1)
- [Rubric（🩵 燈）](#review-section-2)
- ...（依實際 H2/H3 自動產生）
```

同一 source 只保留最新完整 report。舊的同 source report 在新檔寫入成功後清除；
歸屬不明、其他 PR、草稿與手寫筆記不刪。最後 review 時間在重審才改，刷新 board、
標「已看完」不會改它。呼叫與清理範圍見
[`commands/review.md`](https://github.com/Lee-W/maigo/blob/main/commands/review.md)。

### 單一 PR / branch / range（預設）

```markdown
## Context（🐱 樂奈）
<變更摘要 + 周邊 context 一段>

## Rubric（🩵 燈）
<rubric 摘要——詳見本次 review rubric 檔（pr-context-cache 印出的 rubric: 路徑）>

## Verdict（🟡 爽世）
APPROVE | REQUEST_CHANGES | BLOCKED

### Must-fix
- ...（對應 rubric 哪一條）

### Nit / Evidence pending
- ...

## Verification（🟣 立希）
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

涵蓋整輪 batch，不只當下這個 PR。roll-up 留在對話；每顆 PR 的最新 report 各自保存，
不能把整輪總結寫進最後一顆的 review.md 取代它的審查。

### 雙語版（`--bilingual` 或 repo-detect 觸發）

正文最前面加 Taiwanese Mandarin 快結（位於共用檔頭與 TOC 之後） + horizontal rule，後面接既有英文 detail：

```markdown
## 台灣漢語快速結論

**PR:** <url>   <!-- 硬性：原 PR 完整 URL 另由共用檔頭 Source 提供 -->

**PR #<N> — <short title>** <APPROVE / REQUEST_CHANGES / BLOCKED>
<1-3 句：做什麼、能不能上、最大一個 concern>

---

## English — Detailed Review

[既有 Context / Rubric / Verdict / Verification / Bottom line，章節仍用 H2/H3；不新增 H1]

---

<Queue / next-step line | batch 結束的 roll-up>
```
