# Failure Handling — 背景 agent 等待、relay 被拒與定位層級

Loaded on demand by [`skills/failure-handling/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/failure-handling/SKILL.md) — 等待自己開的背景 agent、SendMessage relay 被 subagent 拒絕、或某工具在特定 repo 異常想動工具原始碼前讀。
本檔內文原樣自 SKILL.md 搬出。

### 等待自己開的背景 agent

用 Agent tool 開的背景 agent 完成時會自動發 task-notification 把 orchestrator 叫回來，**不需要
排 ScheduleWakeup 去輪詢**。ScheduleWakeup 是 `/loop` dynamic mode 專用工具，不是等待自己 spawn
的背景任務的機制——同一條教訓在不同 `/maigo:address-comments` 場次重複違反過，根因是
orchestrator 自己跑 `/maigo:*` 流程前沒有主動查一次 memory（見
[`skills/memory-loading`](https://github.com/Lee-W/maigo/blob/main/skills/memory-loading/SKILL.md)
consumer 清單已補上 orchestrator）。

背景 subagent 若寫了一個等待「從未被建立過的哨兵檔案」的假迴圈（例如輪詢一個不存在的 flag
檔案直到自己的 Bash timeout 打斷它），**不要重新 spawn 這個 agent**——用 SendMessage 直接告訴它
(1) 那個假旗標檔案不會被任何東西建立，停掉那個迴圈；(2) 明確給出它自己啟動的背景任務的真實
output 檔案路徑或 task id，叫它直接讀那個檔案或用 TaskOutput 查真實狀態。

同理，也**不要為了「等待」而 spawn 一隻 placeholder / fork agent**——harness 會在背景 agent
結束時自動發 task-notification，不需要任何 tool call 觸發。想等待時直接結束當前 turn（回一句
短訊息告訴使用者正在等什麼）即可。實例：一次為了等 review 完成而 spawn 的「placeholder to
force wait」agent 燒掉約 28 萬 subagent token 卻什麼都沒做。

### Subagent 拒絕 relay 而卡死

Orchestrator 用 `SendMessage` 把 Soyo 的 must-fix 轉給一個正在跑的 Anon 時，Anon 可能把這個
relay 當成「沒有使用者直接授權的 coordinator 訊息」而拒絕執行，即使 orchestrator 事後確認授權
也持續卡住。

**How to apply**：對於一個一行、完整指定的簡單修正（import 移動、rename、單行邏輯），
orchestrator 直接 inline 套用，不要再 relay 一次。真的需要委派時，開一個**全新**的 Agent()
（乾淨 context、無 relay 框架），不要對已卡死的 agent 再 SendMessage——同類任務由全新 agent
執行通常不會被拒絕。

### 先定位層級再修，不要直接 patch 工具原始碼

當某個 maigo / hook / 共用工具在**特定 repo** 表現異常時，先追高層再考慮改工具本身：

1. 這個 repo 是否已有對應的 `repo-aware` skill（如 `airflow-aware`、`commitizen-aware`）在處理這類摩擦？有 → 修法大概率在該 skill 或它引用的 seed。
2. maigo 的 `SessionStart` `repo_detect` hook 是否已經替這個 repo seed 了對應的 `.claude/<config>`？檢查 `hooks/repo_detect.py` 的 `REPO_RULES` → `claude_config_seeds`；若有，可能只是這個 worktree 建立在該功能之前，手動補寫一次 seed 檔即可。
3. 這個工具是否已支援 opt-in / opt-out 設定檔（如 `skip-test-verification`、`test-command`、`known-test-failures`）？有就用它。

三層都確認缺席後才考慮動工具原始碼——patch 共用工具的 blast radius 是跨 repo 的，一個為
某 repo 環境限制調校的「修法」會改變所有沒有那個限制的其他 repo 的行為。
