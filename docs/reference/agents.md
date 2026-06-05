# Agents Reference

Maigo 五位 agent 分屬兩種 model tier，對應任務性質：

| Agent | Model | 為什麼 |
|-------|-------|-------|
| **Raana** / **Tomori** | opus | 探索與計畫的品質直接決定後續所有 agent 的上限；這兩步若粗糙，Anon / Soyo / Taki 都會被拖下水。值得花 token。 |
| **Anon** / **Soyo** / **Taki** | sonnet | 結構化任務（按 plan 寫、按 checklist 審、按 exit code 驗），sonnet 已足夠；用 opus 等於浪費。 |

要改 model 對應，編輯各 agent 檔 frontmatter 的 `model:` 欄位。

## 兩位旁白：🌙 Doloris / 🌑 Mortis

這兩位**不在 `agents/`** 也沒對應 Task agent——他們是 **orchestrator 對使用者說話時戴上的臉**，不下場做事。
所以沒有 frontmatter、沒有 tool list、沒有 model tier，只在開場 / 收場 / 卡關節點出現。

行為規格與何時用哪一位：[`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md)。
