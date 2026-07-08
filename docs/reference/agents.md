# Agents Reference

Maigo 五位 agent 依任務性質各自配置 model tier：

| Agent | Model | 為什麼 |
|-------|-------|-------|
| **Tomori** | opus | 計畫的品質直接決定後續所有 agent 的上限；這步若粗糙，Raana 探索之後的 Anon / Soyo / Taki 都會被拖下水。值得花 token。 |
| **Raana** | sonnet | 探索是結構化任務（讀檔、抓慣例、回報影響面），sonnet 已足夠。 |
| **Anon** | sonnet | 按 plan 寫 code，結構化任務，sonnet 已足夠。 |
| **Soyo** | sonnet | 按 checklist 審查，結構化任務，sonnet 已足夠。 |
| **Taki** | haiku | 跑 test / lint / type check、讀 exit code 回報，機械任務，haiku 即可，省 token。 |

要改 model 對應，編輯各 agent 檔 frontmatter 的 `model:` 欄位——`scripts/validate_plugin.py`
會檢查 frontmatter 與這張表是否一致，改了記得同步更新表格，否則 validator 會擋下。

## 兩位旁白：🌙 Doloris / 🌑 Mortis

這兩位**不在 `agents/`** 也沒對應 Task agent——他們是 **orchestrator 對使用者說話時戴上的臉**，不下場做事。
所以沒有 frontmatter、沒有 tool list、沒有 model tier，只在開場 / 收場 / 卡關節點出現。

行為規格與何時用哪一位：[`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md)。
