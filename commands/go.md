---
description: MyGO 五人接力跑一輪——樂奈觀察、燈寫計畫、愛音動手、爽世擋、立希驗。
---

# /maigo:go

> 「It's MyGO」——輪到我了。

把這件事交給五人組。從第一眼觀察到最後驗證，每個人接她該接的那一棒。

## 使用

```
/maigo:go <任務描述>
```

## 流程

1. **樂奈 (Raana)** — 先看一輪，找出相關位置與既有慣例
2. **燈 (Tomori)** — 把要做的事寫成 `.maigo/plan.md`
3. **使用者確認 plan**（如果有 open questions，先回答再往下）
4. **愛音 (Anon)** — 動手實作
5. **爽世 (Soyo)** — 擋一關（預設 BLOCKED，要被 evidence 說服才放行）
6. **立希 (Taki)** — 跑 test / lint / type check

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

## Orchestrator 守則

- **你（orchestrator）不要自己實作**。每個 agent 都用 Task tool 啟動
- 每個 agent 完成後給使用者一行 summary（不是貼全文）
- 不要跳關。即使任務看起來很小，五個步驟都要走
- 完成後給使用者一份最終 summary：改了哪些檔案、test 結果、有沒有未解問題
