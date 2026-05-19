---
description: Session 結束時，把對話裡浮現的偏好 / 約定 / 學到的事，逐筆 AskUserQuestion 確認後寫進跨專案記憶層。寫檔流程 reuse /maigo:remember。
---

<!-- mkdocs-include-start -->

# /maigo:retro

Session 快結束時，那些「使用者剛指出的偏好」、「約好的慣例」、「學到的教訓」
常常就這樣消失在下一個 prompt 裡。retro 命令把這些抓回來，逐筆問使用者要不要存。

**Orchestrator 親自跑，不開新 agent。**

## 使用

```
/maigo:retro
```

（無參數）

## 流程

### 路徑 A — 同 session（orchestrator 有 conversation context）

1. orchestrator 從 session 對話 context 撈出 **N 個候選 retro 點**（建議 ≤ 5；多於 5 取最有信號的前 5）。

   候選來源：
   - 使用者顯式講的偏好 / 反饋（例：「以後 review 別寫這麼長」）
   - session 中浮現的約定（例：commit message 風格、test naming）
   - 學到的事 / 踩過的雷（例：「這個 lib 在 macOS 行為跟 linux 不同」）

2. **逐筆** propose（一次一筆，不要一口氣全列）：

   - 印一段「候選 #i / N」摘要：原始 context 引用 + orchestrator 推斷的 type / name / description。
   - **AskUserQuestion** 問使用者：「要存這筆嗎？」選項：
     - `存`（接受 → 進入步驟 3）
     - `修改`（使用者調整 type / name / body 後存）
     - `跳過`（不存，進下一筆）
     - `結束 retro`（停止，已存的保留）

3. 使用者選「存」或「修改」→ **reuse `/maigo:remember` 流程步驟 5（AskUserQuestion 確認三題）
   與步驟 6（寫檔 + 更新 MEMORY.md + rollback）**。
   觸發點：把 retro 候選當作 `/maigo:remember` 的 input 自然語言，
   從步驟 2（推斷 type）開始走，一路走完步驟 6。

4. 該筆寫完 → 回到步驟 2 的下一筆候選。

5. 所有候選跑完，或使用者「結束 retro」→ 印 summary：「本次 retro 存了 K 筆：
   `<name1>`（`<type1>`）、`<name2>`（`<type2>`）...」。

### 路徑 B — 跨 session fallback（orchestrator **無** conversation context）

1. orchestrator 判斷：session 對話 context 為空 / 不存在 / 無有意義 turn → 進入 fallback。

2. **AskUserQuestion** 問使用者：「上次的 session 沒在這條對話裡。剛剛做了什麼任務？
   有沒有想記下來的偏好 / 約定 / 學到的事？」

3. 使用者回覆 → orchestrator 把回覆當「N 個候選 retro 點」的 input，
   從**路徑 A 的步驟 2** 開始跑。

4. 使用者回覆「沒有 / 算了」→ 印「了解，retro 結束，未寫入任何記憶」。

## 中斷處理

- 使用者隨時打斷（送新 prompt、Ctrl+C 之類）→ **已存的保留，未答完的不存**。
- 寫檔失敗（同 `/maigo:remember` 的 atomic-ish rollback）→ 已寫成功的保留，當前這筆按 remember 的 rollback 規則處理。
- 同 slug 已存在 → 沿用 `/maigo:remember` 的三選一處理（覆蓋 / 重命名 / 取消）。

## Orchestrator 守則

- **一次只 propose 一筆**——不要一次列五筆讓使用者勾選；逐筆問，使用者答完才下一筆。
  （理由：勾選 UI 鼓勵草率回答；逐筆強迫使用者真的看過。）
- **不延伸推斷**——只用使用者實際講過 / context 浮現的東西，不要「補充使用者可能也想存的」。
- **不複製 `/maigo:remember` 的寫檔 spec**——指向它就好。寫檔 / index / rollback / 同 slug 處理都遵照 remember 的步驟 6 + 「失敗 / 中斷處理」段。
- **不 delegate 給 Tomori 或 Anon**——orchestrator 自己跑。

→ 寫檔細節：[/maigo:remember](https://github.com/Lee-W/maigo/blob/main/commands/remember.md)

→ 完整 storage spec：[Memory reference](../docs/reference/memory.md)
