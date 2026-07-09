# Maigo（迷子）

> 「迷子になっても」——即使成為迷子也沒關係。
>
> ——『BanG Dream! It's MyGO!!!!!』

Maigo 是一套以 **MyGO!!!!!** 五位團員為人設的多 agent 通用開發工作流（Claude Code plugin）。

工程師日常都是迷子——debug 卡關、refactor 找不到入口、PR 不知道該怎麼拆。
Maigo 把五位團員的性格特質映射到開發角色，讓你即使迷失也能被帶回正軌。

## 角色映射

| 團員 | 性格 | 開發角色 | 主要負責 |
|------|------|---------|---------|
| **要 樂奈** Raana | 神祕、看似放空但觀察力極強 | Explorer | 探索 codebase、找線索 |
| **高松 燈** Tomori | 詩人、把混亂結構化成 narrative | Planner | 設計策略、寫實作計畫 |
| **千早 愛音** Anon | 活潑推動者、不放棄 | Implementer | 寫 code、實作 feature |
| **長崎 爽世** Soyo | 完美主義、執念細節 | Reviewer | Code review、稽核 |
| **椎名 立希** Taki | 毒舌、直接、行動派 | Verifier | 跑 test、驗證結果 |

串起這五人、在開場與收場框住整場的 orchestrator，由兩位**旁白**擔任 —— 🌙 **Doloris** 與 🌑 **Mortis**。他們是 MyGO!!!!! 續作《Ave Mujica》的角色，以旁白身份站在故事外講述這場演出，本身不下場做事。

## 快速安裝

```bash
cd /path/to/your/project
claude --plugin-dir /path/to/maigo
```

進 Claude Code 後輸入 `/` 應該能看到 `/maigo:go`、`/maigo:team`、`/maigo:review`、`/maigo:board`。

### 持久化載入

快速試完想長期用，可透過 marketplace 持久化載入：

在 Claude Code 內：

```
/plugin marketplace add Lee-W/maigo
/plugin install maigo@maigo
```

之後啟動 `claude` 就會自動載入，不必再帶 `--plugin-dir`。

更新、停用、移除：

```
/plugin marketplace update maigo
/plugin disable maigo@maigo
/plugin uninstall maigo@maigo
```

## 命令快覽

日常 90% 用這三個：

```bash
/maigo:go <task>          # 5 人順序：探索 → 計畫 → 實作 → review → 驗證
/maigo:team <task>        # 同上，但 Soyo + Taki 並行（省 ~30% 牆鐘）
/maigo:review <pr|branch> # Anon 不上場；review 既有變更
/maigo:board              # 跨 session 看現在球在誰手上
```

完整 15 個命令（含 `/maigo:quick`、`/maigo:board`、`/maigo:remember`、`/maigo:memory`、`/maigo:retro`、`/maigo:crystallize`、`/maigo:describe-pr`、`/maigo:address-comments`、`/maigo:triage-issue`、`/maigo:take-issue`、`/maigo:doctor`、`/maigo:repo-audit`）詳見 [Commands reference](reference/commands.md)。

## 文件導覽

- [Getting Started](guides/getting-started.md) — 第一次裝 Maigo 的 5 分鐘入門
- [Commands reference](reference/commands.md) — 每個命令的完整流程、合流邏輯、場景對照
- [Hooks reference](reference/hooks.md) — SessionStart / TeammateIdle / Stop hook 行為與設定
- [Skills reference](reference/skills.md) — skill 機制與目前 catalog
- [Agents reference](reference/agents.md) — 五位 agent 的 model tier 選擇邏輯
- [Contributing](guides/contributing.md) — 修 Maigo 本身的設定與原則
