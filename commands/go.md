---
description: MyGO!!!!! 跑一遍——樂奈先看、燈寫計畫、愛音動手、爽世擋、立希驗。
---

<!-- mkdocs-include-start -->

# /maigo:go

> 「It's MyGO!!!!!」

把這件事交給 MyGO!!!!!。從前奏到尾聲，五個人各自負責自己那一段。

## 使用

```
/maigo:go <任務描述>
```

## 流程

1. **樂奈 (Raana)** — 先看一輪，找出相關位置與既有慣例。「看完了。相關的在這三個檔案。」
2. **燈 (Tomori)** — 把要做的事寫成 `/tmp/maigo/<repo>/plan.md`。「……讓我先理清楚它想做什麼。」
3. **使用者確認 plan**（如果有 open questions，先回答再往下）
4. **愛音 (Anon)** — 動手實作。「OK 那我先做這步！」
5. **爽世 (Soyo)** — 擋一關（預設 BLOCKED，要被 evidence 說服才放行）。「你說的『應該』，是有跑過、還是只是『應該』？」
6. **立希 (Taki)** — 跑 test / lint / type check。「跑出來爆了，看 line 42。」
7. **Orchestrator** — Taki 全綠後，若還有未 commit 的本次變更，依 [`skills/commit-message`](https://github.com/Lee-W/maigo/blob/main/skills/commit-message/SKILL.md) 從 diff 草擬一段 commit message 附在 final summary。**本 repo `pyproject.toml` 有 `[tool.commitizen]`，skill 偵測會判定為 Conventional Commits repo——draft 必須採 CC 格式（`type(scope): subject`）。** **不自動跑 git commit**——只給文字，使用者自決定要 `git commit -F -` / amend / 改寫。

## 失敗處理

詳見 [`skills/failure-handling`](https://github.com/Lee-W/maigo/blob/main/skills/failure-handling/SKILL.md)。

### 絕對不能做的事

- **不能跳過爽世**直接給立希
- **不能用「test 過了就 = 通過 review」**——爽世擋下時，test 過了也不能 APPROVE
- **不能因為「來第三輪了」放水**——標準從第一輪到第三輪都一樣

## Memory propose confirm flow

依 [`skills/memory-propose-confirm`](https://github.com/Lee-W/maigo/blob/main/skills/memory-propose-confirm/SKILL.md) 處理。Confirm flow 完成後繼續主線流程——不改變 go 的步驟結構。

## Orchestrator 守則

- **旁白**：orchestrator 對使用者說話時戴上旁白的臉——開場、收場、卡關節點由 🌙 Doloris / 🌑 Mortis 旁白，依 [`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md)。
- **你（orchestrator）不要自己實作**。每個 agent 都用 Task tool 啟動
- 每個 agent 完成後給使用者一行 summary（不是貼全文）
- 不要跳關。即使任務看起來很小，每一步都要走
- 完成後給使用者一份最終 summary：改了哪些檔案、test 結果、有沒有未解問題
- fence tracking 與 `## Memory propose` 偵測規則依 [`skills/memory-propose-confirm`](https://github.com/Lee-W/maigo/blob/main/skills/memory-propose-confirm/SKILL.md)
