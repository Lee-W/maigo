---
name: failure-handling
description: This skill should be used when handling failures in go-class command flows — Soyo blocking with NEEDS_CHANGES / BLOCKED, Taki test failures, subagent infrastructure overload / unavailability (e.g. 529), mid-task usage/session-limit interruption of a running subagent, and infinite-loop protection for repeated same must-fix or same test ID. Applies to /maigo:go, /maigo:quick, /maigo:team, and /maigo:address-comments step 5.
---

<!-- mkdocs-include-start -->

# Failure Handling

**Consumers**: [`/maigo:go`](https://github.com/Lee-W/maigo/blob/main/commands/go.md) 失敗處理段、[`/maigo:quick`](https://github.com/Lee-W/maigo/blob/main/commands/quick.md) 同段、[`/maigo:team`](https://github.com/Lee-W/maigo/blob/main/commands/team.md) 同段、[`/maigo:address-comments`](https://github.com/Lee-W/maigo/blob/main/commands/address-comments.md) step 5 都引用本 skill。

### 爽世擋下（NEEDS_CHANGES / BLOCKED）

1. **完整把爽世 (Soyo) 的輸出傳給愛音 (Anon)**——must-fix 清單 + evidence 待補 + 具體改法
2. 愛音修完後，**必須附上每條 must-fix 的對應 diff 與 evidence**（不接受「都改好了」這種模糊回報）
3. 重新請爽世 review。爽世會逐條對照——任何一條沒清就維持 BLOCKED

### 修正輪閉環

套用任何 review 修正後，一律**送回同一位 reviewer** 複驗——同一個 context 才抓得到這輪
修正本身引入的新矛盾；換一個沒看過前情的 reviewer，等於失去對照歷史的能力。

1. **修到 PASS 為止**——每一輪修正都可能引入新缺陷，改完就收工等於沒驗；verdict 未達
   對應 command 的通過門檻前，流程不算完成。
2. **reviewer 無法續用**（原 agent session 已結束、必須開新 agent）時，**視同重新審查**：
   附上完整前情——原始 diff、前幾輪 must-fix 清單、目前已套用的修正——不能只給「這是修正
   後的版本」讓新 reviewer 從零判斷。

### 立希驗證紅

1. 把 failure 完整貼給愛音 (Anon)（command + exit code + output）
2. 愛音修完後立希 (Taki) 重跑——**不接受愛音口頭說「修好了」**
3. 修到全綠才算過

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

### Subagent 中途撞 usage / session limit

與 529 不同：529 是啟動失敗，這是**跑到一半被切斷**——subagent 可能已完成部分工作（working tree 留有半成品），回傳卻只有一句 limit 訊息（含重置時間）。

1. **不要開新 agent 從頭重做**——半成品會跟新一輪工作糾纏，已完成的部分也白費。
2. Limit 重置後，**用 SendMessage 續跑同一個 agent**——transcript context 還在，任務背景不用重講。
3. 續跑指令必須要求**先盤點再續作**：`git status` + 檢視目標檔案，逐項判斷任務做到哪，只補缺的。盤點常發現工作其實已全部完成（切斷發生在回報前）——此時直接進驗證，避免重工。
4. 盤點與續作完成後照常走原流程——review / 驗證不因中斷打折。

### 無限迴圈防護

- 爽世連續擋 **2 次**同一條 must-fix → 停下，請使用者介入（可能是計畫本身有問題）
- 立希連續紅 **2 次**同一個 test → 停下，請使用者介入（可能 test 本身需要更新）

「同一條 must-fix」判準：Soyo 輸出的 must-fix 條目**指向同一個檔案 + 同一個函式 / 區段 + 同一類問題描述**（不要求 wording 完全相同，但語意相同算同條）。Anon 改 wording、換實作方式但問題本質沒解掉 → 仍算同條。

「同一個 test」判準：test runner 報出的**同一個 test ID**（pytest 的 `path::TestClass::test_method[param]`、其他 framework 的等價 identifier）。**錯誤訊息字串變化不算「不同 test」**——ID 相同就是同一條。一次 run 裡多個 test ID 同時紅 → 各自獨立計次，不互相抵消。
