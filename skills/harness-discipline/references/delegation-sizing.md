# Harness Discipline — Delegation Sizing for New Commands

Loaded on demand by [`skills/harness-discipline/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/harness-discipline/SKILL.md) —
設計新 `/maigo:*` 命令、或評估「這個任務要不要派團員」時的份量準則。Read this file when
你在**命令設計階段**決定要套哪一種流程形狀；已經在執行命令時，流程照
[`teammate-flow`](https://github.com/Lee-W/maigo/blob/main/skills/teammate-flow/SKILL.md) 走。

---

## 預設精實，不預設全團員

**規則**：設計新命令時，預設走精實委派，不要預設套完整五人 teammate-flow。

**理由**：使用者對 token 成本敏感。小 payload 的任務（例如一次寫一個 skill 檔＋幾處登記＋
跑 validator）冷啟動成本遠大於收益；尤其純掃描型的棒次，讀的常常是 orchestrator 在互動
階段本來就已經讀過的資料，等於同份資料讀兩次。

**怎麼套用**：

- payload 小 → 走 `/maigo:quick` 的形狀：orchestrator 主持互動，委派一個 🎀 Anon 實作，
  加輕量的 🟡 Soyo 審查，不 spawn 全隊。
- 多筆同類工作 → **批次一次 spawn**，不要 per-entry 各起一隻，攤平冷啟動。
- 砍掉與 orchestrator 重複讀資料的棒次。
- 提案派團員前，先估「payload 大小 vs 冷啟動成本」，並把這個取捨講給使用者，不要默默套
  最重的版本。

## 與 teammate-flow「不要跳關」的關係

兩者不衝突，管的是不同階段：

- **命令設計階段**（決定這個命令要用哪種流程形狀）：本檔的份量準則適用，可以選精實形狀。
- **執行階段**（命令已定案為 teammate-flow 形狀）：teammate-flow 的「不要跳關」適用，
  選定的流程每一步都要走。

「精實」是在設計時選對形狀，不是執行時把已選定的步驟臨時跳過。

## 派驗證 agent 跑大型 pytest：分開跑、導檔、加 timeout

派驗證 agent（Taki）跑 Airflow 路由這類大型 pytest 時，**不要把多個長跑 pytest 串在同一個任務**。
曾因串多個長跑測試、600 秒無進度被系統中止（agent 狀態 failed）；改成分開跑後穩定完成（約
130 秒內全綠）。被中止的 pytest 也可能是獨立 DB 被弄壞的原因之一，但這是推測，未證實。

**怎麼套用**：交辦文寫明——每個 pytest 分開跑、一次一條；輸出導到 scratchpad 檔
（`> log 2>&1; echo EXIT=$?`）；用 `timeout 480` 包住；只 tail 結果；逐條回報逾時的是哪一步，
不要空等。

## harness 可能擋 subagent 寫報告檔：被擋就改回傳文字

subagent 用 Write 寫報告正文檔時，harness 可能回「Subagents should return findings as text,
not write report files」。這是 harness 層的限制，**不要授權 subagent 改用 Bash heredoc 繞過**；
同一個 session 裡同類任務有的能寫、有的被擋，不能預設可寫。

**怎麼套用**：

- 預設仍照 [`SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/harness-discipline/SKILL.md) 回報合約「長產物寫到檔案，回傳路徑」；**被擋過一次、或同類任務已知被擋時才切換**成「不要寫檔，以文字回傳」（需要機器可讀的標題時，第一行單獨寫 `TITLE: ...`，不放 code fence）。
- 由 orchestrator 自己 Write 成 scratchpad 檔，再接後續發佈步驟，最後 grep 讀回確認。
- 存檔前逐句核對組裝者加的內容：它可能自行補進交辦材料裡沒有的未驗證句子，要刪掉。
