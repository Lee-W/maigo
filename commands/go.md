---
description: MyGO!!!!! 跑一遍——樂奈先看、燈寫計畫、愛音動手、爽世擋、立希驗。
---

<!-- mkdocs-include-start -->

# /maigo:go

> 「It's MyGO!!!!!」——輪到我了。

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
7. **Orchestrator** — Taki 全綠後，若還有未 commit 的本次變更，依 [`skills/commit-message`](https://github.com/Lee-W/maigo/blob/main/skills/commit-message/SKILL.md) 從 diff 草擬一段 commit message 附在 final summary。**不自動跑 git commit**——只給文字，使用者自決定要 `git commit -F -` / amend / 改寫。

## 失敗處理

### 爽世擋下（NEEDS_CHANGES / BLOCKED）

1. **完整把爽世的輸出傳給愛音**——must-fix 清單 + evidence 待補 + 具體改法
2. 愛音修完後，**必須附上每條 must-fix 的對應 diff 與 evidence**（不接受「都改好了」這種模糊回報）
3. 重新請爽世 review。爽世會逐條對照——任何一條沒清就維持 BLOCKED

### 立希驗證紅

1. 把 failure 完整貼給愛音（command + exit code + output）
2. 愛音修完後立希重跑——**不接受愛音口頭說「修好了」**
3. 修到全綠才算過

### 無限迴圈防護

- 爽世連續擋 3 次同一條 must-fix → 停下，請使用者介入（可能是計畫本身有問題）
- 立希連續紅 3 次同一個 test → 停下，請使用者介入（可能 test 本身需要更新）

### 絕對不能做的事

- **不能跳過爽世**直接給立希
- **不能用「test 過了就 = 通過 review」**——爽世擋下時，test 過了也不能 APPROVE
- **不能因為「來第三輪了」放水**——標準從第一輪到第三輪都一樣

## Memory propose confirm flow

當 Soyo 或 Anon 的輸出末尾含 `## Memory propose` 段時，orchestrator 在該 agent 完成後、繼續下一步前，立刻執行 confirm flow：

1. 檢查 propose 段的 6 個必填欄位（name / slug / description / body / type / rationale）是否齊全。
   缺任一欄位 → 不 confirm，印一行提示「偵測到 propose 段但格式不完整，已跳過」，繼續正常流程。
2. 顯示目前兩個 memory 來源的 index：
   - `~/.config/maigo/memory/MEMORY.md`（cross-project）
   - `~/.claude/projects/<current-project>/memory/MEMORY.md`（per-project，若存在）
3. 印出 propose 摘要（type / name / description / rationale）。
4. **AskUserQuestion**，選項：`存` / `修改` / `跳過`。
5. 選「存」或「修改」→ reuse `/maigo:remember` 步驟 5+6
   （以 propose 的欄位為預填值；「修改」時步驟 5 讓使用者改各欄位）。
6. 選「跳過」→ 繼續正常流程，不寫任何檔。

Confirm flow 完成後繼續主線流程——不改變 go 的步驟結構。

## Orchestrator 守則

- **你（orchestrator）不要自己實作**。每個 agent 都用 Task tool 啟動
- 每個 agent 完成後給使用者一行 summary（不是貼全文）
- 不要跳關。即使任務看起來很小，每一步都要走
- 完成後給使用者一份最終 summary：改了哪些檔案、test 結果、有沒有未解問題
- 偵測 `## Memory propose` 標頭時，只掃描 code fence 外的行；
  code block 內（triple-backtick fence 之間）的同名標頭不觸發 confirm flow。
  追蹤法：從輸出文字開頭往下追蹤 triple-backtick 計數（奇數 → in-fence），遇到 `^## Memory propose` 且 in-fence 為 true 時跳過。
