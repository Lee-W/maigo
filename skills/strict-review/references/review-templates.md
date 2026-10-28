# Strict Review — `/maigo:review` Output Templates Reference

Loaded on demand by [`commands/review.md`](https://github.com/Lee-W/maigo/blob/main/commands/review.md) —
the markdown skeletons for the review rubric (🩵 Tomori's step 2 output) and the
three report shapes (single PR/branch/range, multi-PR batch roll-up, bilingual). Read this
file when writing the rubric or assembling the final report.

---

## Review rubric 骨架（`.maigo/review/<id>/rubric.md`，自己的 PR 是 `.maigo/pr/<id>/rubric.md`，路徑見 [`pr-context-cache`](https://github.com/Lee-W/maigo/blob/main/skills/pr-context-cache/SKILL.md) 或 `scripts/artifact_path.py`）

版面規範見 [`vim-friendly-artifacts`](https://github.com/Lee-W/maigo/blob/main/skills/vim-friendly-artifacts/SKILL.md)（版面、HTML 與路徑規則）。

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
產生最新 `.maigo/review/<id>/review.md`（自己的 PR 是 `.maigo/pr/<id>/review.md`）。所有版型共用檔頭；不是讓每個模型自行
猜 review 時間。報告正文不放 HTML、不手寫目錄或 anchor，版面規範見
[`vim-friendly-artifacts`](https://github.com/Lee-W/maigo/blob/main/skills/vim-friendly-artifacts/SKILL.md)。orchestrator 讀回最終檔案呈現，檔案與對話使用同一份內容。

共用檔頭由 publisher 產生，鍵值行之間各隔一個空行；`Author` 只在有 `--author` 時出現，`已看完` 一開始是「尚未確認」：

```markdown
# Review: <title>

<!-- maigo-review: {...} -->

**Source:** <canonical PR URL / branch / range>

**Author:** <@login / git author>

**最後 review：** <ISO 8601，含時區>

**Reviewed commit:** `<full SHA>`

**Verdict:** <verdict>

**已看完：** 尚未確認
```

第二行的 `maigo-review` 註解是 parser 依賴的 marker（白名單見 `vim-friendly-artifacts`），後面接一行 JSON，不要手改。檔頭之後直接是正文的第一個 H2，沒有目錄。

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

### Head moved after this review

發佈前一律再查一次 `gh pr view <n> --json headRefOid`。值與審查時不同，就在正文最末
附這個 H2，並以 publisher 的 `--head <審查的那個完整 commit hash>` 發佈（publisher 要求完整 hash，
短 SHA 會被拒）——不是現在的 head：

```markdown
## Head moved after this review

This report covers head `<reviewed short SHA>` only. At publish time the head is
`<current short SHA>` (<force-push / new commit `<sha>` "<subject>">, touching <files or scope>).
The new head has not been reviewed — re-check before submitting.
```

**為什麼**：用新 head 發佈，board 會把未審的 commit 當成已審；用審查的 SHA 發佈，board 才會
判為 `↩︎ 回你的球`，提醒重審。

> 案例（2026-10 batch）：7 顆 PR 在審查後、發佈前被推新 head（force-push 或追加 commit），
> 都以此 H2 ＋舊 SHA 發佈，交由 board 判為 `↩︎ 回你的球`。

### Refreshing a draft against the PR's current thread state

When trimming a review draft (body items or per-thread replies) against what the PR
already has, an item stays in the draft until **the user** has responded on that thread.
An author reply only proves the other side moved; it doesn't mean the user's concern was
handled, so it is not a reason to drop the item. Drop an item only when the thread is
resolved or its last comment is the user's own.

How to apply: fetch threads via GraphQL `reviewThreads` (REST has no `isResolved`) and read,
per thread, whether it is resolved and who wrote the last comment. Also list what the
user's pending (unsubmitted) review already contains, so inline comments aren't queued
twice. The Work Board's possession rules (a submitted review, approve included, with no
new activity afterwards parks the PR in ⏳; new author activity flips it back to 🎯) are in
[`work-board`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md) §2 and
already cover the board side — this note covers only what a *draft* should keep.

### Someone else's PR with only should-fix or nit findings: draft APPROVE and keep the nits out

When a review of another contributor's PR ends as "approve with nits" and nothing is must-fix (docs gaps, wording, a missing one-clause mention), default the review draft to APPROVE with a short body and no inline comments. Tell the user the nits in the terminal and offer a follow-up branch or worktree for them instead. Only must-fix findings go into the sent review.

**Why**: a round of nit fixes costs the author a cycle for no gain, and a maintainer can fold the gaps in with a follow-up of their own. The typical case is a gap the PR merely exposed rather than introduced.

How to apply: if the user explicitly asks for the nits to be in the review, do that. Opening the follow-up worktree and pushing it is the user's action; stack it on the PR head only when the edit depends on the PR's change.

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

正文最前面加 Taiwanese Mandarin 快結（位於共用檔頭之後） + horizontal rule，後面接既有英文 detail：

```markdown
## 台灣漢語快速結論

**PR:** <url>

**PR #<N> — <short title>** <APPROVE / REQUEST_CHANGES / BLOCKED>
<1-3 句：做什麼、能不能上、最大一個 concern>

---

## English — Detailed Review

[既有 Context / Rubric / Verdict / Verification / Bottom line，章節仍用 H2/H3；不新增 H1]

---

<Queue / next-step line | batch 結束的 roll-up>
```

`**PR:**` 這行放原 PR 的完整 URL，與共用檔頭的 `Source` 同值（快結段落獨立可讀，所以再寫一次）。這類給作者看的提示一律寫在 code block 外，不要放進骨架裡的 HTML 註解，否則會被照抄進產物。
