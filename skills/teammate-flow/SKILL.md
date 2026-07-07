---
name: teammate-flow
description: This skill should be used when orchestrating the full MyGO!!!!! teammate flow — Raana explores, Tomori plans, Anon implements, Soyo reviews, Taki validates. Applies to /maigo:go and /maigo:team (both sequential and parallel variants).
---

<!-- mkdocs-include-start -->

# Teammate Flow

**Consumers**: [`/maigo:go`](https://github.com/Lee-W/maigo/blob/main/commands/go.md)、[`/maigo:team`](https://github.com/Lee-W/maigo/blob/main/commands/team.md)。

teammate-flow 定義了 MyGO!!!!! 五人協作的共通流程骨架——從探索到實作到審查到驗證，
每個角色各自負責自己那一段，Orchestrator 負責串起來。

## 共通流程（Sequential 段）

以下四步在 `/maigo:go` 和 `/maigo:team` 都必須照順序走：

1. **🐱 樂奈 (Raana)** — 探 codebase，找出相關位置與既有慣例。「看完了。相關的在這三個檔案。」
2. **🩵 燈 (Tomori)** — 把要做的事寫成 `.maigo/plan.md`。「……讓我先理清楚它想做什麼。」
3. **使用者確認 plan**（如果有 open questions，先回答再往下）
4. **🎀 愛音 (Anon)** — 按 plan 動手實作。「OK 那我先做這步！」

步驟 5 以後由各 command 決定——`/maigo:go` 是順序（先 🟡 爽世再 🟣 立希），
`/maigo:team` 是並行（🟡 爽世和 🟣 立希同時觸發）。

## 交棒契約

Maigo 的 MyGO!!!!! 感來自「每個人用自己的方式把下一個人推到正確位置」，不是靠台詞堆疊。
每次 hand-off 都必須留下下一位能直接接住的資訊：

| 交棒 | 必須留下什麼 | 不能怎樣 |
|------|-------------|----------|
| 🐱 樂奈 → 🩵 燈 | 相關位置、既有慣例、異狀、潛在影響面 | 不把探索報告寫成實作計畫 |
| 🩵 燈 → 🎀 愛音 | `.maigo/plan.md` 裡清楚標 `Goal`、`Steps`、acceptance、blocking decisions | 不把風險藏在語氣裡；不讓 🎀 愛音猜 |
| 🎀 愛音 → 🟡 爽世 | 每個 step 的完成狀態、改了哪些檔、sanity check / test output | 不用「應該」「大概」包裝未驗證狀態 |
| 🟡 爽世 → 🎀 愛音 | 編號 must-fix、具體改法、為什麼、還缺什麼 evidence | 不只說方向，讓 🎀 愛音猜怎麼修 |
| 🟣 立希 → 🎀 愛音 / orchestrator | command、exit code、重要 output、新舊失敗區分 | 不把紅燈柔化成「看起來」 |

Orchestrator 每次轉場 summary 只說一行，但要說清楚「上一位留下了什麼、下一位要接什麼」。
例如：「🐱 樂奈找到兩個慣例衝突點；🩵 燈會把它們寫進 plan 的 Risks。」

## Orchestrator 守則

### 旁白

Orchestrator 對使用者說話時戴上旁白的臉——開場、收場、卡關節點由 🌙 Doloris / 🌑 Mortis 旁白，
依 [`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md)。

### 執行規則

- **你（orchestrator）不要自己實作**。每個 agent 都用 Task tool 啟動
- 每個 agent 完成後給使用者一行 summary（不是貼全文）
- 不要跳關。即使任務看起來很小，每一步都要走
- 完成後給使用者一份最終 summary：改了哪些檔案、test 結果、有沒有未解問題

### Commit message draft

Taki 全綠（或 `/maigo:team` 合流 APPROVED + PASS）後，若還有未 commit 的本次變更，
依 [`skills/commit-message`](https://github.com/Lee-W/maigo/blob/main/skills/commit-message/SKILL.md) 從 diff 草擬一段 commit message 附在 final summary。

本 repo `pyproject.toml` 有 `[tool.commitizen]`，skill 偵測會判定為 Conventional Commits repo——
draft 必須採 CC 格式（`type(scope): subject`）。

**不自動跑 git commit**——只給文字，使用者自決定要 `git commit -F -` / amend / 改寫。

若使用者或後續步驟確實要跑 git 操作（stage / amend / 診斷 diff 大小），
依 [`skills/git-workflow`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/SKILL.md)
的 staging（不用 `git add -A`）、不 `cd`、unreleased commit 的 amend 慣例。

### `/maigo:go` vs `/maigo:team` — 選哪個

兩個命令的 review 嚴格度一模一樣（🟡 爽世完整 9 項 + 🟣 立希）；差別只在 §5 之後：
`/maigo:go` 是 🟡 爽世先、🟣 立希後（序列）；`/maigo:team` 是兩者並行（省約 30% 牆鐘）。

**預設選 `/maigo:team`** 的條件（全部符合）：
- scope 清楚（邊界已定、不需邊探邊改）
- 已有測試覆蓋（即使 correctness-sensitive 的重構也算低風險）
- 牽動面可以在 plan 階段就界定完

**偏 `/maigo:go`** 的情況：
- scope 未定、需要邊探邊實作才知道影響面
- 牽動面難以事先界定（跨多個子系統、依賴圖複雜）

不確定時不要因「謹慎」自動退回 go——team 的並行不犧牲嚴格度。

## Worktree safety in parallel batch review

適用範圍：用 `Workflow` tool 對**多個 PR** 做並行 fan-out（🐱 樂奈 → 🩵 燈 → 🟡 爽世）
的場景——跟 `/maigo:review` 既有的「一次一個 PR」序列 queue
（[`skills/strict-review/references/review-batch-queue.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/review-batch-queue.md)）
是不同的路徑。

**規則：並行 batch review 只能 read-only** —— agent 只用 `gh pr diff` /
`gh pr view` / `gh api graphql` 抓資料；不開 `git worktree`，任何 agent 都不能
`gh pr checkout`，即使是在隔離的 worktree 裡。

背景是兩次真實事故：

1. 為每個 PR 的 🟣 立希驗證階段各開一個 `isolation: 'worktree'` run——每個
   worktree 都 clone 完整 airflow checkout，約 10 個並行跑下去把硬碟耗盡
   （`No space left on device`），整個 verify 階段掛了兩次。
2. 即使明確交代「不要 git checkout」，還是有 agent 在**共用的 main
   worktree** 裡跑了 `gh pr checkout` 去做 mutation test——把使用者當下
   進行中的 branch 切換成該 PR 的 branch（commit 沒丟，但 branch pointer
   被劫走了）。

**How to apply**：batch / 並行 review = review-only，不開 worktree，把跑
runtime 驗證（🟣 立希）留到之後的獨立階段再做。那個獨立階段用單一隔離
worktree（或最多 2–3 個併發、有速率限制），先確認硬碟還有空間
（每個 worktree 抓~2GB+）。**任何 review / verify agent 都不能在使用者的
共用 / main worktree 裡跑 `git checkout` / `gh pr checkout`**——那裡只能讀。

## 失敗處理

詳見 [`skills/failure-handling`](https://github.com/Lee-W/maigo/blob/main/skills/failure-handling/SKILL.md)。

## Memory propose confirm flow

偵測（含 fence tracking）與 6 步 confirm flow 依
[`skills/memory-propose-confirm`](https://github.com/Lee-W/maigo/blob/main/skills/memory-propose-confirm/SKILL.md) 處理。
Confirm flow 完成後繼續主線流程——不改變各 command 的步驟結構。

## 絕對不能做的事

- **不能跳過 🟡 爽世**直接給 🟣 立希
- **不能用「test 過了就 = 通過 review」**——爽世擋下時，test 過了也不能 APPROVE
- **不能因為「來第三輪了」放水**——標準從第一輪到第三輪都一樣
