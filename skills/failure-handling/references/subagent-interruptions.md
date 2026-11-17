# Failure Handling — Subagent 過載、被切斷與假 failed

Loaded on demand by [`skills/failure-handling/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/failure-handling/SKILL.md) — subagent 啟動失敗（529）、`stalled`／睡眠中斷、撞 usage／session limit、或 task-notification 標 `status: failed` 時讀。
本檔內文原樣自 SKILL.md 搬出。

### Subagent 過載 / 不可用（如 529 Overloaded）

某個 agent 的 Task 因基礎設施問題（伺服器 529 Overloaded、逾時、暫時不可用）反覆啟動失敗，與該 agent 的工作品質無關時：

1. **有限次重試**——重試 **2-3 次**。每次重試成本不低（subagent 啟動到報錯可能耗數分鐘），不要無聲地一直重撞。
2. 仍失敗 → **把選項攤給使用者**，不自行決定：
   - 等久一點再試（短間隔重試只是重複燒時間；建議擱 20-30 分鐘讓尖峰過）
   - **orchestrator 主線代打**該 stage——繞過過載點立即解卡
   - 暫停，等基礎設施恢復後再接續
3. 使用者授權主線代打時：
   - **明示這違反該 command 的分工守則**（orchestrator 本不該自己 review / 實作），且**獨立性較弱**（等於審 / 改自己流程的產出）
   - **嚴格度不打折**——照對應 skill（如 `strict-review` 9 項）硬走，以 `git diff` / 實測為憑，不因「我自己跑」放水
   - review 類代打要實際構造場景驗證（不只讀 code 說 OK）；驗證類代打要貼真實 exit code
4. **infra 恢復後，讓真人 agent 補跑一次複核**——代打有真實盲點（代打者對該 repo 的慣例未必熟，且審/驗自己的產出獨立性弱）。基礎設施恢復可 spawn 時，對代打過的 stage 補跑真正的 agent 一輪；真人 agent 揪出代打漏掉的問題是常態，不是例外。

**不能做**：因 subagent 撞 529 就**跳過**該 stage（跳過 review / 跳過驗證）。過載是基礎設施問題，不是放行理由——要嘛代打、要嘛等，不能省。

### Subagent 中途被切斷（`stalled`／睡眠／連線中斷）

與 529 不同：529 是啟動失敗，這是**跑到一半沒了**，而且回傳往往只有一句 harness 訊息，看不出真因。

**`Agent stalled: no progress for 600s` 不等於基礎設施過載。** 同樣的訊息也會由
**本機電腦進入睡眠**產生（訊息可能到下一次才變成 `Your computer went to sleep
mid-response`）。差別很重要：過載該退避重試，睡眠退避無效——所以**不要**因為連續幾次
`stalled` 就把 prompt 拆得越來越小，那治不到真因，只是把同一份工作重跑好幾遍。
判準：`ListAgents` 顯示其他 agent 同時段也一起停、或多次中斷落在同一段掛機時間 → 懷疑睡眠。

**唯一可靠的緩解是把「落檔」寫進回報合約**，而不是縮小任務：

> 報告檔路徑：`<scratchpad>/<agent>-<task>.md`
> **每答完一條就立刻追加寫入，不要累積到最後才寫。** 若你中途被切斷，落檔的部分就是有效交付。

被切斷後的復原順序：

1. **先看落檔**（`ls` scratchpad、讀那個報告檔）——已答完的部分可能已經在裡面
2. **不要開新 agent 從頭重做**——用 `SendMessage` 續跑同一個 agent，transcript context 還在
3. 續跑指令要求**先盤點再續作**：讀既有報告檔 ＋ `git status` ＋ 檢視目標檔，逐項判斷做到哪，**只補缺的**
4. 明確告知「哪幾項已確認完成、不用重做」——orchestrator 自己先盤點過，能省掉一整輪

**第二個成因：單一前景指令長時間無輸出。** 睡眠之外，`stalled` 也常停在一個逼近 Bash
10 分鐘上限、期間不吐任何輸出的前景指令上（整包 pytest、`pnpm install`、mkdocs build）。
這是相關性觀察加合理機制（watchdog 只看得到「600 秒沒進度」），不是已證明的因果；但緩解
成本低，所以**交辦文一律附防停滯條款**——這也不是「拆小 prompt」，任務範圍不變：

> 任何可能超過 2 分鐘的指令一律背景執行、輸出導檔，用 `tail` 短指令輪詢；每條指令加
> `timeout`；每完成一步就把結論追加進 progress 檔。

續跑的上限與接手：

- 同一個 agent 經 `SendMessage` 續跑後**再次** `stalled` → 不要第三次續跑同一個
  transcript。改開新 agent，輸入＝progress 檔＋既有 scratchpad 產物＋完整失敗軌跡
  （原交辦文、兩次停在哪個指令）；要不要換模型依
  [`model-dispatch`](https://github.com/Lee-W/maigo/blob/main/skills/model-dispatch/SKILL.md)
  「模型選擇與重試」（只換已授權的替代模型，換了也計入兩輪重試預算）。這不違反上面
  第 2 點：新 agent 是接手續作，不是從頭重做。
- 被切斷的 agent 若正在做**變異驗證**，worktree 可能殘留被改壞的檔案——續跑或接手的
  第一件事是 `git status --short` 加 sha 對帳並還原，再做別的。

> 案例（2026-10）：兩個 sonnet review agent 各 `stalled` 兩次，每次都停在整包 pytest 的變異驗證或
> `pnpm install` 上，其中一個 worktree 殘留了 M5 變異，靠接手者先對帳才發現；之後約 14 個
> 交辦加上防停滯條款，含 35 分鐘、165 次工具呼叫的審查，零次 `stalled`。

### Subagent 中途撞 usage / session limit

與 529 不同：529 是啟動失敗，這是**跑到一半被切斷**——subagent 可能已完成部分工作（working tree 留有半成品），回傳卻只有一句 limit 訊息（含重置時間）。

1. **不要開新 agent 從頭重做**——半成品會跟新一輪工作糾纏，已完成的部分也白費。
2. Limit 重置後，**用 SendMessage 續跑同一個 agent**——transcript context 還在，任務背景不用重講。
3. 續跑指令必須要求**先盤點再續作**：`git status` + 檢視目標檔案，逐項判斷任務做到哪，只補缺的。盤點常發現工作其實已全部完成（切斷發生在回報前）——此時直接進驗證，避免重工。
4. 盤點與續作完成後照常走原流程——review / 驗證不因中斷打折。

### task-notification 標記 `status: failed`，不代表工作沒做完

跟 529（啟動失敗）、usage/session limit（有明確 limit 訊息）都不同：這是第三種訊號——subagent
在收尾寫最終報告時遭遇 API 連線中斷，task-notification 的 `status` 欄位字面上顯示
`failed`，`summary`/`result` 只留下被截斷的半句話（例："Exit 0, passed. Let's verify final
git state is clean..."）。**這個 `failed` 字面上看起來像整個任務失敗，但實際常常是：實質工作
（含 commit）早就做完，中斷只發生在自我確認 / 收尾報告階段。**

1. **先查實際狀態，不要照 `status: failed` 字面重派**——去該 agent 實際操作的目錄/repo 跑
   `git log --oneline` + `git status --porcelain` + `git diff --stat <base>...HEAD`，對照原始
   交辦的驗收條件逐項核對，而不是看到 `failed` 就假設一切從零開始。
2. 若 git 狀態顯示工作（含 commit）已完整——**不要重派 agent 從頭做**，直接把這個結果送進
   下一階段（review / 驗證），比照「Subagent 中途撞 usage / session limit」第 3-4 點的做法；
   被截斷的只是它自己的收尾敘述，不是它的產出。
3. 若 git 狀態顯示工作明顯未完成或矛盾——才視同「跑到一半被切斷」，比照上面 usage/session
   limit 小節處理（SendMessage 續跑同一 agent，要求先盤點再續作）。
