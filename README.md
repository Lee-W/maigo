# Maigo（迷子）

> 「迷子になっても」——即使成為迷子也沒關係。
>
> ——『BanG Dream! It's MyGO!!!!!』

Maigo 是一套以 **MyGO!!!!!** 五位團員為人設的多 agent 通用開發工作流。

工程師日常都是迷子——debug 卡關、refactor 找不到入口、PR 不知道該怎麼拆。
Maigo 把五位團員的性格特質映射到開發角色，讓你即使迷路也能被帶回正軌。

## 角色映射

| 團員 | 性格 | 開發角色 | 主要負責 |
|------|------|---------|---------|
| **要 樂奈** Raana | 神祕、看似放空但觀察力極強 | Explorer | 探索 codebase、找線索 |
| **高松 燈** Tomori | 詩人、把混亂結構化成 narrative | Planner | 設計策略、寫實作計畫 |
| **千早 愛音** Anon | 活潑推動者、不放棄 | Implementer | 寫 code、實作 feature |
| **長崎 爽世** Soyo | 完美主義、執念細節 | Reviewer | Code review、稽核 |
| **椎名 立希** Taki | 毒舌、直接、行動派 | Verifier | 跑 test、驗證結果 |

## 設計哲學

- **實用 > 玩梗**：角色化是為了好用、好記、好溝通；不為了梗犧牲效果
- **通用化**：不綁特定技術領域、不綁特定語言
- **角色邊界清楚**：每個團員只做自己擅長的事，不越界，避免一人份的 agent 假裝五人份

## 使用方式

### 開發新功能 / 改 bug

```
/maigo:go <任務描述>
```

五個人接力：樂奈先看、燈寫計畫、愛音動手、爽世擋一關、立希跑驗證。

### Review 既有變更

```
/maigo:review <github-pr-url>     # GitHub PR
/maigo:review <branch-name>        # 本地 branch
/maigo:review                      # 預設 review 你目前 branch vs main
```

四個人接力（愛音不上場）：樂奈抓 context、燈寫對照基準、爽世嚴格挑、立希跑驗證。
適合 PR review、code audit、上線前最後一道把關。

## Status

`v0.0.1` — 初始骨架。歡迎一起迷路。

## License

MIT
