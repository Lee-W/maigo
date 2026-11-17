---
name: failure-handling
description: This skill should be used when handling failures in go-class command flows — Soyo NEEDS_CHANGES / BLOCKED, Taki test failures, subagent overload (529) or mid-task limit interruption — and infinite-loop protection on repeated same must-fix or test ID. Used by go, quick, team, address-comments.
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
2. 🎀 愛音修完後，若程式碼、測試或其他受審內容有變，先送回 🟡 爽世複審，再讓 🟣 立希重跑；team 可依原本規則並行兩者。**不接受口頭說「修好了」，也不沿用修改前的 APPROVED。**
3. 只有修復環境且受審內容完全沒變，才能沿用 review、只重跑驗證。
4. 🟡 爽世 APPROVED 與 🟣 立希 PASS 必須對應同一份變更快照才算過。交辦與回報保留 HEAD、tracked diff 與 untracked 檔內容的識別／雜湊；僅 HEAD 相同不足以證明內容未變。修復改了內容，舊 review 與驗證結果都失效。

### 環境造成的假紅 / Stop hook 假陽性迴圈

- 環境假紅（乾淨環境會綠、成因指向 Node／OS／工具版本）：優先改環境設定讓它真的綠；**不要把「加進 known-test-failures」當預設收尾**，寫之前先問使用者並說明代價（全檔粒度遮蔽會連未來真回歸一起遮掉）。
- Stop hook 因環境／collection 層問題逐輪重觸發：先確認成因一次；結構性壞掉且已用真實 runner 確認綠 → 寫 `.claude/skip-test-verification`（附原因）；使用者明說「忽略這個 hook」時**輸出零字元**；受限權限模式下寫 `.claude/` 被擋就停手交給使用者，**不繞、不換工具重試**。
[`references/test-signal-noise.md`](https://github.com/Lee-W/maigo/blob/main/skills/failure-handling/references/test-signal-noise.md)（優先順序、理由與可貼上的一行指令）

### Subagent 過載、被切斷與假 failed

- 529／過載：有限重試 2-3 次，仍失敗把選項攤給使用者（等、orchestrator 主線代打、暫停）；**不能因 529 跳過 review 或驗證 stage**；代打須明示違反分工、嚴格度不打折，infra 恢復後補跑真 agent 複核。
- `stalled`／睡眠／usage limit 被切斷：**不要開新 agent 從頭重做**，先看落檔與 `git status`，用 `SendMessage` 續跑同一 agent 並要求先盤點再續作；交辦文一律附落檔與防停滯條款；續跑後再次 `stalled` 才改開新 agent 接手。
- task-notification `status: failed` 不代表工作沒做完：先查實際 git 狀態對照驗收條件，工作已完整就直接進下一階段，不重派。
[`references/subagent-interruptions.md`](https://github.com/Lee-W/maigo/blob/main/skills/failure-handling/references/subagent-interruptions.md)（完整步驟、防停滯條款文字與案例）

### Handback 送達但內容遺失

`<task-notification>` 正常到達且 `status: completed`，`<result>` 寫著報告已用訊息送達，
但那則訊息從未出現——這是內容遺失，不是任務失敗。**不要**重派新 agent 重做同一輪工作、
不要自己代跑它該做的檢查、不要假設遺失的結論是 PASS。三步處置（先自己看現場 →
`SendMessage` 同一 agent 要求只重貼不重跑 → 採用重貼內容）與案例，見
[`references/handback-content-missing.md`](https://github.com/Lee-W/maigo/blob/main/skills/failure-handling/references/handback-content-missing.md)。

**附帶**：這也代表**不能用「收到 handback」當 agent 已停止的訊號**——handback 只是那一輪
的輸出，agent 可能仍在跑、仍在改共用 worktree；生命週期一律用 `ListAgents` 查。

### 背景 agent 等待、relay 被拒與定位層級

- 自己開的背景 agent 完成時會自動發 task-notification：**不要排 ScheduleWakeup 輪詢，也不要 spawn placeholder agent 來等**，直接結束當前 turn。
- Subagent 拒絕 relay 而卡死：一行可完整指定的修正由 orchestrator inline 套用；真要委派就開**全新** Agent，不要再對卡死的 agent `SendMessage`。
- 某工具在特定 repo 異常時，先查 repo-aware skill、`repo_detect` 的 seed、既有 opt-in 設定檔，三層都缺才考慮動工具原始碼。
[`references/orchestrator-coordination.md`](https://github.com/Lee-W/maigo/blob/main/skills/failure-handling/references/orchestrator-coordination.md)（完整判準與案例）

### 無限迴圈防護

計數只屬於同一個邏輯任務／執行批次，不帶入其他 work item 或舊 session 的歷史總數。
`verify_task.py` 首次回傳 run/task ID，重試須沿用；SubagentStop 只能辨識同一 agent 的續跑，
Stop 沒有可靠的 task ID。換 agent、沒有 hook 或缺識別碼時，由 orchestrator 保存本任務預算，
不能因 runtime 無法聚合就無限重試。doctor 的歷史次數不是這個連續計數。

- 爽世連續擋 **2 次**同一條 must-fix → 停下，請使用者介入（可能是計畫本身有問題）
- 立希連續紅 **2 次**同一個 test → 停下，請使用者介入（可能 test 本身需要更新）
  這條的機器計次只在 `scripts/verify_task.py` 沿用同一組 `--run-id`／`--task-id` 時成立；Stop hook 不累計跨呼叫次數（失敗仍照常 block），預算由 orchestrator 自己記。

「同一條 must-fix」判準：Soyo 輸出的 must-fix 條目**指向同一個檔案 + 同一個函式 / 區段 + 同一類問題描述**（不要求 wording 完全相同，但語意相同算同條）。Anon 改 wording、換實作方式但問題本質沒解掉 → 仍算同條。

「同一個 test」判準：test runner 報出的**同一個 test ID**（pytest 的 `path::TestClass::test_method[param]`、其他 framework 的等價 identifier）。**錯誤訊息字串變化不算「不同 test」**——ID 相同就是同一條。一次 run 裡多個 test ID 同時紅 → 各自獨立計次，不互相抵消。
