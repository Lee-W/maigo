# Contributing to Maigo

要修 Maigo 本身的 agent / command / hook / skill。

## Setup

```bash
git clone <your-fork> maigo
cd maigo
pre-commit install      # 一次性，之後 commit 自動跑檢查
```

## 開發流程

| 動作 | 對應檔案 |
|------|--------|
| 改某位團員的人設 / 工具 | `agents/<Name>.md` |
| 改某個 command 的流程 | `commands/<name>.md` |
| 改評審標準（checklist 等） | `skills/strict-review/SKILL.md` |
| 改 hook 行為 | `hooks/<name>.py` |
| 加 hook | 寫 script + 在 `hooks/hooks.json` 註冊 |
| 加 skill | 見 [skills.md](../reference/skills.md) 的「加新 skill checklist」 |
| 為某個 project 加自動載入知識（project-aware） | 兩步：在 `hooks/repo_detect.py` 的 `REPO_RULES` 加 entry + 建對應 `skills/<name>/SKILL.md`。詳見 [hooks.md 加新 project entry](../reference/hooks.md#add-new-project-entry) |

## 提交前

### pre-commit 會自動擋下

- 基本檔案衛生：trailing whitespace、EOF newline、大檔、merge conflict marker、shebang 與 executable bit 一致性
- 壞掉的 JSON / YAML（`plugin.json` / `hooks/hooks.json` 壞了 plugin 整個載不到）
- Ruff lint / format 失敗
- Agent / command frontmatter 缺欄位（`name` / `description` / `model` / `tools`）或 agent name 跟檔名對不上

### 升版本或大動結構前，跑完整檢查

```bash
python3 scripts/validate_plugin.py
```

8 項檢查涵蓋：
1. `plugin.json` valid JSON + 必要欄位
2. `hooks/hooks.json` valid JSON
3. `agents/*.md` frontmatter（name / description / model / tools；name 必須對應檔名）
4. `commands/*.md` frontmatter（description）
5. `skills/*/SKILL.md` frontmatter（name / description；name 必須對應目錄名）
6. `hooks/hooks.json` 指向的 script 真的存在 + Python 語法 OK / Shell 有 executable bit
7. `.pre-commit-config.yaml` 結構合理 + local hook entry 指向的檔案存在
8. `agents/` 與 `commands/` 引用的 `skills/<name>` 真的有對應 skill

### Validator 速查

| Validator | 何時跑 | 涵蓋 |
|-----------|-------|------|
| `validate_frontmatter.py` | pre-commit（自動） | 只看 agent / command frontmatter；快 |
| `validate_plugin.py` | 手動 / CI / 升版本前 | 全面 8 項 |

## 設計原則

寫新東西前先讀這幾條：

1. **Reviewer 嚴謹度是核心特點**。任何 review 相關修改都不能放鬆 Soyo 的標準。
2. **Skill 優先於 agent prompt**。如果你想加給 reviewer 的「規則」，先想能不能進 `strict-review` skill，而不是直接塞 Soyo.md。
3. **Hook 防禦深度**。重要規格在多層擋（agent prompt + skill + hook validator + Stop hook），讓 orchestrator 偷雞跳關時還有最後一道。
4. **Artefact 寫到 `/tmp/maigo/<repo>/`**，不要污染使用者 repo。
5. **agent 個性與 process 解耦**——人設、語氣 → agent 檔；做事方法 → skill 或 command。

## 專案結構

```
maigo/
├── agents/                          # 5 位團員（人設 + 角色）
│   ├── Raana.md / Tomori.md / Anon.md / Soyo.md / Taki.md
├── commands/
│   ├── go.md                        # /maigo:go     順序版
│   ├── team.md                      # /maigo:team   並行版
│   └── review.md                    # /maigo:review
├── skills/                          # 跨 agent/command 共用的 process
│   └── strict-review/SKILL.md
├── hooks/
│   ├── hooks.json                   # 註冊 TeammateIdle + Stop
│   ├── teammate_quality_check.py    # agent 輸出規格檢查
│   └── verify_completion.py         # 任務宣告完成前強制跑 test
├── scripts/
│   ├── validate_frontmatter.py
│   └── validate_plugin.py
├── docs/                            # ← 你在這裡
│   ├── reference/                   # commands / hooks / skills
│   └── guides/                      # contributing 等
├── .pre-commit-config.yaml
├── plugin.json
├── CHANGELOG.md
└── README.md
```

## 注意事項

### HTML comment marker 與 agent loader

Agent / command / skill source 檔內含 `<!-- mkdocs-include-start -->` HTML comment marker，用於 mkdocs include-markdown frontmatter 處理。markdown comment 不會被 render，但會出現在 Claude Code agent loader 餵給 LLM 的 system prompt 內。HTML comment 通常不影響 LLM 行為，但若日後 agent 表現異常，此處可作為調查方向之一。

## 報 bug / 提 idea

issue 模板還沒寫；先寫一個簡短的 repro / 期待行為即可。

## License

MIT.
