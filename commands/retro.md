---
description: Session 結束時，把對話裡浮現的偏好 / 約定 / 學到的事，逐筆 AskUserQuestion 確認後寫進跨專案記憶層。寫檔流程 reuse /maigo:remember。
allowed-tools: Read, Write, Edit, Bash(mkdir:*), Bash(cat:*), Bash(ls:*), Bash(test:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/pr_review_comments.py:*), AskUserQuestion
---

<!-- mkdocs-include-start -->

# /maigo:retro

Session 快結束時，那些「使用者剛指出的偏好」、「約好的慣例」、「學到的教訓」
常常就這樣消失在下一個 prompt 裡。retro 命令把這些抓回來，逐筆問使用者要不要存。

**Orchestrator 親自跑，不開新 agent。**

## 使用

```
/maigo:retro
/maigo:retro --pr <url> [<url> ...]
```

（無參數＝路徑 A／B；帶 `--pr` ＝路徑 C）

## 流程

### 路徑 A — 同 session（orchestrator 有 conversation context）

1. orchestrator 從 session 對話 context 撈出 **N 個候選 retro 點**（建議 ≤ 5；多於 5 取最有信號的前 5）。

   候選來源：
   - 使用者顯式講的偏好 / 反饋（例：「以後 review 別寫這麼長」）
   - session 中浮現的約定（例：commit message 風格、test naming）
   - 學到的事 / 踩過的雷（例：「這個 lib 在 macOS 行為跟 linux 不同」）

2. **逐筆** propose（一次一筆，不要一口氣全列）：

   - 印一段「候選 #i / N」摘要：原始 context 引用 + orchestrator 推斷的 type / name / description。
   - **先判斷目的地**（印在摘要裡）：
     - `個人 memory`：使用者的偏好、workflow 習慣、跨 session 記憶的事實
     - `maigo 文件缺口`：描述的是「maigo 如何工作 / maigo 的某個慣例 / 實作規範」
       → 應進 maigo 的 source file（例：`docs/reference/memory.md`、`CONTRIBUTING.md`），而不是寫進個人 memory
     - `repo／語言慣例`：某個 repo 或某個語言的寫碼慣例（pytest／mock／import 規則、某 repo 的 PR 規則），**不是** maigo 自身怎麼運作
       → 仍存成個人 memory（`type: project`），`description` 開頭標 `畢業候選 → <python-aware|airflow-aware|…>`
       （換到另一個同語言 repo 仍成立 → 語言層，否則 → 該 repo 的 repo-aware skill；判斷依 [`skill-graduation.md`](https://github.com/Lee-W/maigo/blob/main/skills/maigo-self-check/references/skill-graduation.md) 落點表）；
       寫入 skill 一律交給 `/maigo:crystallize`，**retro 不直接 Edit `skills/`**
   - 依目的地調整問法：
     - **個人 memory** → **AskUserQuestion**「要存這筆嗎？」選項：`存` / `修改` / `跳過` / `結束 retro`
     - **repo／語言慣例** → **AskUserQuestion**「要存成畢業候選嗎？」選項同個人 memory（`存` / `修改` / `跳過` / `結束 retro`）；
       「存」走下方步驟 3 的 `/maigo:remember` 流程，不新增寫檔路徑
     - **maigo 文件缺口** → **AskUserQuestion**「要更新 maigo 文件嗎？」選項：
       `更新 maigo 文件`（orchestrator 直接 Edit 指定 source file）/ `改存 personal memory` / `跳過` / `結束 retro`

3. 使用者選「存」或「修改」→ **reuse `/maigo:remember` 流程步驟 5（AskUserQuestion 確認三題）
   與步驟 6（寫檔 + 更新 MEMORY.md + rollback）**。
   觸發點：把 retro 候選當作 `/maigo:remember` 的 input 自然語言，
   從步驟 2（推斷 type）開始走，一路走完步驟 6。

   使用者選「更新 maigo 文件」→ orchestrator 直接 Edit 目標 source file，完成後印「已更新 `<file>`」，不寫 memory。

4. 該筆寫完 → 回到步驟 2 的下一筆候選。

5. 所有候選跑完，或使用者「結束 retro」→ 印 summary：「本次 retro 存了 K 筆：
   `<name1>`（`<type1>`）、`<name2>`（`<type2>`）...」。
   若其中有標 `畢業候選` 的條目，補一句提示：「有 N 筆畢業候選，之後跑 `/maigo:crystallize` 收進對應 skill」。

6. **🌑 Mortis 結算（一句）**

   Summary 印完後，再加一行——把本次 retro 的核心壓縮成**一句**。

   **硬性字數限：1 句。**

   範例：
   ```
   🌑 Mortis：本次 retro 的核心是「Soyo review 要更精簡」。
   ```

   守則：
   - 溫柔包裹克制——短句；不刻意冷酷；結尾常是靜靜的收束
   - 不感嘆號、不鼓勵語
   - 候選為 0 筆 → 跳過結算（沒存任何東西的 retro 不需要結算）

### 路徑 B — 跨 session fallback（orchestrator **無** conversation context）

1. orchestrator 判斷：session 對話 context 為空 / 不存在 / 無有意義 turn → 進入 fallback。

2. **AskUserQuestion** 問使用者：「上次的 session 沒在這條對話裡。剛剛做了什麼任務？
   有沒有想記下來的偏好 / 約定 / 學到的事？」

3. 使用者回覆 → orchestrator 把回覆當「N 個候選 retro 點」的 input，
   從**路徑 A 的步驟 2** 開始跑。

4. 使用者回覆「沒有 / 算了」→ 印「了解，retro 結束，未寫入任何記憶」。

### 路徑 C — `--pr <url> [<url> ...]`：從 PR 上別人留的 review comment 學

reviewer 實際挑過什麼，不在對話裡。這條路徑讀 PR 上**別人**的 comment，歸類、計次，
判斷「現行規則該不該擋到它」。**只讀 GitHub：不留言、不送 review、不改 PR。**

1. 跑 [`scripts/pr_review_comments.py`](https://github.com/Lee-W/maigo/blob/main/scripts/pr_review_comments.py)
   （唯讀，只經 `gh api` 做 GET）：

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pr_review_comments.py" <url> [<url> ...]
   ```

   輸出 JSON：每個 PR 的作者，與非作者、非 bot 的 root inline comment（排除 reply）、
   review body、issue comment，各附 URL 與 `path:line`。腳本失敗（exit 非 0）→ 印 stderr
   原因並結束，不寫任何記憶。comment 為 0 → 印「這些 PR 沒有別人留的 comment」並結束。

2. **歸類**：orchestrator 依
   [`reviewer-comment-taxonomy`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/reviewer-comment-taxonomy.md)
   逐則把 comment 歸到一個 `category` key。純提問、純讚美、無法歸類的略過。

3. **逐則判定「現行規則該擋到它嗎」**，三選一：
   - **規則存在卻漏擋**：taxonomy 為該類列了對應規則，但 go 的第一輪沒做到 → 候選
   - **無對應規則**：該類在 taxonomy 標「無對應規則」→ 候選
   - **屬 reviewer 領域知識**：需要 reviewer 自己的專業或專案內部知識才知道，作者無從套用 → **不收**

4. 前兩種候選沿用路徑 A 的步驟 2–4：**一次一筆**、先判目的地、再走 `/maigo:remember`
   步驟 5+6 寫檔。寫入時帶 `category` 與 `seen_in`（`<owner/repo>#<n>`），並先套用
   [`/maigo:address-comments`](https://github.com/Lee-W/maigo/blob/main/commands/address-comments.md)
   步驟 7 的追加判定：已有同 `category` 且判定為同一教訓的條目，改為在其 `seen_in`
   追加本次 PR，不新建；使用者可改判。reviewer 與作者的人名不寫進記憶，只留 PR 號與類別。

5. 結尾 summary 在路徑 A 的 summary 之外多印兩項：
   - 一行「本次各類別次數」，例：`doc-claim-drift 3、test-cannot-fail 2、edge-case 1`
   - 「規則存在卻漏擋」清單：每筆一行，`<category>（<PR 號>）→ <該擋到它的規則>`。
     這份清單是 pre-PR sweeps 在第一輪是否生效的量測。

   候選為 0 筆時仍印次數行；沒有任何漏擋寫「無」。

## 中斷處理

- 使用者隨時打斷（送新 prompt、Ctrl+C 之類）→ **已存的保留，未答完的不存**。
- 寫檔失敗（同 `/maigo:remember` 的 atomic-ish rollback）→ 已寫成功的保留，當前這筆按 remember 的 rollback 規則處理。
- 同 slug 已存在 → 沿用 `/maigo:remember` 的三選一處理（覆蓋 / 重命名 / 取消）。

## Orchestrator 守則

- **旁白**：orchestrator 對使用者說話時戴上旁白的臉——開場、收場、卡關節點由 🌙 Doloris / 🌑 Mortis 旁白，依 [`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md)。
- **對話**：對話本體（旁白節點以外）的互動節奏與用詞，依 [`skills/orchestrator-voice`](https://github.com/Lee-W/maigo/blob/main/skills/orchestrator-voice/SKILL.md)。
- **一次只 propose 一筆**——不要一次列五筆讓使用者勾選；逐筆問，使用者答完才下一筆。
  （理由：勾選 UI 鼓勵草率回答；逐筆強迫使用者真的看過。）
- **目的地優先**——每筆 propose 前先判斷「個人 memory／maigo 文件缺口／repo／語言慣例」三類；把 maigo 本身的規則/慣例/實作規範存成個人 memory，是把 plugin 知識放錯地方；repo／語言慣例只存成畢業候選 memory、交給 `/maigo:crystallize`，retro 不直接寫 `skills/`。
- **不延伸推斷**——只用使用者實際講過 / context 浮現的東西，不要「補充使用者可能也想存的」。
- **不複製 `/maigo:remember` 的寫檔 spec**——指向它就好。寫檔 / index / rollback / 同 slug 處理都遵照 remember 的步驟 6 + 「失敗 / 中斷處理」段。
- **不 delegate 給 Tomori 或 Anon**——orchestrator 自己跑。
- **即時 propose vs retro 的關係**：Soyo / Anon 即時 propose 是前置網；
  retro 是 catch-all 後置網。即使這個 session 已用過即時 propose，retro 仍應照常跑——
  即時 propose 只抓當下明確信號，retro 還能補抓沒講清楚的。
  retro 跑到與即時 propose 重複的候選時，正常展示 MEMORY.md index，
  由使用者眼睛判斷是否重複；orchestrator 不做 keyword dedup。
  已在 confirm flow 存入的 entry（使用者選「存」或「修改」後完成寫檔的），retro 不重複 propose。
  此判斷僅限路徑 A；路徑 B 因無 session context，orchestrator 無法可靠辨別，照常 propose 並讓使用者從 MEMORY.md index 自行判斷是否重複。

→ 寫檔細節：[/maigo:remember](https://github.com/Lee-W/maigo/blob/main/commands/remember.md)

→ 完整 storage spec：[Memory reference](../docs/reference/memory.md)
