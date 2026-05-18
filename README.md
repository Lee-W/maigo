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
- **角色邊界清楚**：每個團員只做自己擅長的事，不越界，避免一人份的 agent 假裝五人份
- **Reviewer 真的會擋**：Maigo 的核心特點是 Soyo 預設 BLOCKED、要 evidence 才放行

## Prerequisites

| 需要 | 版本 | 用途 |
|------|------|------|
| Claude Code CLI | latest | Plugin host |
| Python 3 | 3.9+ | TeammateIdle hook + frontmatter validator |
| `git` | any | Review 本地 branch / commit range |
| `gh` CLI | 任意 | 選用——`/maigo:review` 給 GitHub PR URL 時需要 |
| `pre-commit` | 任意 | 選用——只有要修 Maigo 本身才需要 |

## 安裝

在你想用 Maigo 的專案目錄下：

```bash
cd /path/to/your/project
claude --plugin-dir /path/to/maigo
```

進 Claude Code 後輸入 `/` 應該能看到 `/maigo:go` 與 `/maigo:review`，這樣就裝好了。

> 想做永久安裝（不用每次帶 `--plugin-dir`）？把路徑寫進 Claude Code 的 settings.json，或等專案 publish 到 plugin marketplace。

## 使用方式

### `/maigo:go` — 開發新功能 / 修 bug

```
/maigo:go <任務描述>
```

範例：

```
/maigo:go 幫 User model 加 email 驗證，需要支援 plus address (foo+bar@x.com)
```

接下來自動跑：

1. **樂奈** 探 codebase（找 User model 在哪、現有驗證怎麼寫、相關 test）
2. **燈** 寫 `.maigo/plan.md`——列出步驟與 acceptance；有 open questions 會問你
3. **你確認 plan**（先把 open questions 回完再往下）
4. **愛音** 按 plan 動手改 code
5. **爽世** review 變更——**預設 BLOCKED**，要被 evidence 說服才 APPROVE
6. **立希** 跑 test / lint / type check

任何一關卡住 → 回到愛音修正再重試。同一個 must-fix / failure 連續 3 次卡關才會停下找你。

### `/maigo:review` — Review 既有變更

```
/maigo:review https://github.com/org/repo/pull/123    # GitHub PR
/maigo:review feature/email-validation                 # 本地 branch（vs main）
/maigo:review HEAD~3..HEAD                             # commit range
/maigo:review                                          # 預設目前 branch vs main
```

愛音不上場——只有 樂奈 → 燈 → 爽世 → 立希。
跟 `/maigo:go` 最大差別：**燈這次寫的是 `review-rubric.md`**（reviewer 對照基準），爽世拿它逐條對 diff 比。
沒有基準的 review = 憑感覺，這是 reviewer 不嚴謹最常見的根因。

## 常見場景對照

| 想做什麼 | 用哪個 |
|---------|--------|
| 加新 feature / 修 bug | `/maigo:go <task>` |
| Review 同事的 GitHub PR | `/maigo:review <pr-url>` |
| 上線前最後一道把關自己的 branch | `/maigo:review` |
| 摸新專案 / onboarding | 讓 Claude 直接呼叫 `Raana` 探一輪 |
| 重構評估（不實作） | `/maigo:go` 跑到燈寫完 plan 後喊停 |
| Security audit | `/maigo:review`，告訴爽世重點看 unsafe pattern |

## Hook 行為（TeammateIdle）

只要 plugin 載入，`hooks/teammate_quality_check.py` 自動生效。下列情況會 **block** agent 並要求補完：

| Agent | 會被擋的情況 |
|-------|-------------|
| **Tomori** | 沒把計畫寫進 `.maigo/plan.md` 或 `.maigo/review-rubric.md`；缺結構段落（Goal / Steps / Rubric / Acceptance） |
| **Soyo** | 沒下 verdict（APPROVED / NEEDS_CHANGES / BLOCKED）；沒 checklist；非 APPROVED 卻沒列 must-fix |
| **Taki** | 沒貼 exit code；沒給 PASS / FAIL；出現「應該可以」「looks good」這類 hedge 語 |

Raana 與 Anon 目前未設規格，預設通過。Malformed 輸入或 jq 不存在會 fail-open。

## 產出檔案

| 路徑 | 由誰寫 | 用途 |
|------|--------|------|
| `.maigo/plan.md` | 燈（`/maigo:go`） | 實作計畫，給愛音照著做、給爽世對照 |
| `.maigo/review-rubric.md` | 燈（`/maigo:review`） | Review 對照基準，給爽世逐條比對 |

這兩個檔案預設 gitignored——它們是 session 期間的工件，不進 repo。

## 開發 Maigo 本身

如果你要修 Maigo 的 agent / command / hook：

```bash
cd /path/to/maigo
pre-commit install      # 一次性，之後 commit 自動跑檢查
```

pre-commit 會擋下：
- 基本檔案衛生問題（trailing whitespace、EOF、大檔、merge conflict marker）
- 壞掉的 JSON / YAML（`plugin.json` / `hooks/hooks.json` 壞了 plugin 整個載不到）
- Ruff lint / format 失敗
- Agent / command frontmatter 缺欄位（`name`/`description`/`model`/`tools`）或 agent name 跟檔名對不上

### 專案結構

```
maigo/
├── agents/                          # 五位團員
│   ├── Raana.md / Tomori.md / Anon.md / Soyo.md / Taki.md
├── commands/
│   ├── go.md                        # /maigo:go
│   └── review.md                    # /maigo:review
├── hooks/
│   ├── hooks.json                   # 註冊 TeammateIdle hook
│   └── teammate_quality_check.py    # 輸出規格檢查
├── scripts/
│   └── validate_frontmatter.py      # pre-commit 用
├── .pre-commit-config.yaml
├── plugin.json
└── README.md
```

## Status

`v0.0.1` — 初始骨架。歡迎一起迷路。

## License

MIT
