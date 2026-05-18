# Maigo（迷子）

> 「迷子になっても」——即使成為迷子也沒關係。
>
> ——『BanG Dream! It's MyGO!!!!!』

Maigo 是一套以 **MyGO!!!!!** 五位團員為人設的多 agent 通用開發工作流（Claude Code plugin）。

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
- **Reviewer 真的會擋**：Maigo 的核心特點是 Soyo 預設 BLOCKED、要 evidence 才放行；多層防禦（agent prompt + skill + hook validator）避免被偷雞跳過

## Prerequisites

| 需要 | 版本 | 用途 |
|------|------|------|
| Claude Code CLI | latest | Plugin host |
| Python 3 | 3.9+ | hooks + 驗證 script |
| `git` | any | review 本地 branch |
| `gh` CLI | 任意 | 選用——review GitHub PR URL 時 |
| `pre-commit` | 任意 | 選用——只在貢獻 Maigo 本身時需要 |

## 安裝

```bash
cd /path/to/your/project
claude --plugin-dir /path/to/maigo
```

進 Claude Code 後輸入 `/` 應該能看到 `/maigo:go`、`/maigo:team`、`/maigo:review`。

## 命令快覽

```bash
/maigo:go <task>          # 5 人順序：探索 → 計畫 → 實作 → review → 驗證
/maigo:team <task>        # 同上，但 Soyo + Taki 並行（省 ~30% 牆鐘）
/maigo:review <pr|branch> # Anon 不上場；review 既有變更
```

→ 完整流程、合流邏輯、場景對照表：[docs/reference/commands.md](docs/reference/commands.md)

## Hook 自動行為

只要 plugin 載入就生效，使用者不用設定：

- **TeammateIdle** — agent 輸出不符規格（如 Soyo 沒下 verdict、Taki 沒貼 exit code）就 block
- **Stop** — 任務宣告完成前自動偵測專案類型跑 test，跳過 Taki 也擋下

→ 完整擋下條件、設定檔（`.claude/skip-test-verification` 等）：[docs/reference/hooks.md](docs/reference/hooks.md)

## 產出檔案

計畫與 rubric 寫在 `/tmp/maigo/<repo>/`（`<repo>` = `basename "$PWD"`）。
**刻意放在 `/tmp`**——不污染 repo、不需 gitignore、重開機自動清掉。想保留就自己另存它處。

## 文件

- [Commands reference](docs/reference/commands.md) — 三個命令的完整流程、合流邏輯、場景對照
- [Hooks reference](docs/reference/hooks.md) — TeammateIdle / Stop hook 完整行為與設定
- [Skills reference](docs/reference/skills.md) — skill 機制與目前 catalog（`strict-review`）
- [Contributing](docs/guides/contributing.md) — 修 Maigo 本身的設定、原則、validator
- [CHANGELOG](CHANGELOG.md) — 版本歷史

## Status

`v0.0.1` — 初始骨架。歡迎一起迷路。

## Acknowledgments

Maigo 的整體結構**大幅受到 [agent-flow](https://github.com/josix/agent-flow) 啟發**——
multi-agent 分工、Claude Code plugin packaging、TeammateIdle / Stop hook 模式、
agent / command / skill / hook 四層分離，這些概念都來自 agent-flow。

Maigo 在這個基礎上做了三件事：
- 把 agent 換成 MyGO!!!!! 五位團員的人設
- 把焦點窄化到「reviewer 真的會擋」的 `strict-review` 流程
- 簡化掉暫時用不到的元件（Graphify、personal-kb、`/analyze`、`/explain` 等）

如果你需要更完整的工程級 multi-agent orchestration（含並行 review、知識圖譜整合、跨專案記憶），
直接用 agent-flow 會更合適。

## License

MIT
