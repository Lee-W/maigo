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

### fence tracking 與 Memory propose 偵測

fence tracking 與 `## Memory propose` 偵測規則依
[`skills/memory-propose-confirm`](https://github.com/Lee-W/maigo/blob/main/skills/memory-propose-confirm/SKILL.md)。

## 失敗處理

詳見 [`skills/failure-handling`](https://github.com/Lee-W/maigo/blob/main/skills/failure-handling/SKILL.md)。

## Memory propose confirm flow

依 [`skills/memory-propose-confirm`](https://github.com/Lee-W/maigo/blob/main/skills/memory-propose-confirm/SKILL.md) 處理。
Confirm flow 完成後繼續主線流程——不改變各 command 的步驟結構。

## 絕對不能做的事

- **不能跳過 🟡 爽世**直接給 🟣 立希
- **不能用「test 過了就 = 通過 review」**——爽世擋下時，test 過了也不能 APPROVE
- **不能因為「來第三輪了」放水**——標準從第一輪到第三輪都一樣
