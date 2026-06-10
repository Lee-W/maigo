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
- 壞掉的 JSON / YAML（`.claude-plugin/plugin.json` / `hooks/hooks.json` 壞了 plugin 整個載不到）
- Ruff lint / format 失敗
- Agent / command frontmatter 缺欄位（`name` / `description` / `model` / `tools`）或 agent name 跟檔名對不上

### 升版本或大動結構前，跑完整檢查

```bash
python3 scripts/validate_plugin.py
```

涵蓋的檢查面向（具體項數會隨 plugin 演進變動，**以 `CHECKS` list 與實際輸出為準**）：

- `.claude-plugin/plugin.json` valid JSON + 必要欄位
- `hooks/hooks.json` valid JSON
- `agents/*.md` frontmatter（name / description / model / tools；name 必須對應檔名）
- `commands/*.md` frontmatter（description）
- `skills/*/SKILL.md` frontmatter（name / description；name 必須對應目錄名）
- `hooks/hooks.json` 指向的 script 真的存在 + Python 語法 OK / Shell 有 executable bit
- `.pre-commit-config.yaml` 結構合理 + local hook entry 指向的檔案存在
- `agents/` 與 `commands/` 引用的 `skills/<name>` 真的有對應 skill
- `.claude-plugin/plugin.json` 與 `pyproject.toml` 的 version 同步
- `commands/*.md` ↔ `docs/commands/<name>.md` 對齊（mkdocs-include-start marker + shim）
- `skills/*/SKILL.md` ↔ `docs/skills/` + `mkdocs.yml` + `docs/reference/skills.md` catalog 四向對齊

### Validator 速查

| Validator | 何時跑 | 涵蓋 |
|-----------|-------|------|
| `validate_frontmatter.py` | pre-commit（自動） | 只看 agent / command frontmatter；快 |
| `validate_plugin.py` | 手動 / CI / 升版本前 | 全面，項數會 drift——看 `CHECKS` |

## 設計原則

寫新東西前先讀這幾條：

1. **Reviewer 嚴謹度是核心特點**。任何 review 相關修改都不能放鬆 Soyo 的標準。
2. **Skill 優先於 agent prompt**。如果你想加給 reviewer 的「規則」，先想能不能進 `strict-review` skill，而不是直接塞 Soyo.md。
3. **Hook 防禦深度**。重要規格在多層擋（agent prompt + skill + hook validator + Stop hook），讓 orchestrator 偷雞跳關時還有最後一道。
4. **Artefact 寫到 `.maigo/`**（repo root 下，gitignored），不要污染使用者 repo。
5. **agent 個性與 process 解耦**——人設、語氣 → agent 檔；做事方法 → skill 或 command。
6. **Skill 文件語言慣例**——Engineering-facing skills **MUST** be written in English;
   user-facing utility skills **SHOULD** be written in Taiwanese Mandarin unless
   portability is required.
   - 工程知識、架構設計、開發規範（如 `strict-review`、`airflow-aware`、`commit-message`）→ 英文：工程技能具可移植性
   - 個人工具、流程 utility（如 `teammate-flow`、`failure-handling`、`narration`）→ 台灣漢語：強依賴個人語境
   - 稱呼語言時全稱「台灣漢語」、語境清楚時簡稱「漢語」（英文 Taiwanese Mandarin）；不混用「華語 / 台灣華語」，避免「繁體中文 / Traditional Chinese」——繁體是字形，不是語言
7. **角色刻畫以動機為主**——Characterization is conveyed primarily through motivation,
   value hierarchy, and conflict handling; catchphrases, emoji, punctuation, and verbal
   tics are secondary signals only.
   - 爽世不是因為有「♪」才是爽世；Doloris 不是因為省略號才是 Doloris；Mortis 不是因為講話冷才是 Mortis
   - 真正的人格來自動機：爽世——維持關係與團隊秩序；Doloris——帶著傷痛繼續前進；Mortis——為了保護而拒絕前進
   - 口癖只是輔助訊號——寫人設或台詞時先對齊動機與衝突處理方式，再考慮口癖

## 專案結構

> 列舉只放代表性檔案——目錄底下的完整內容會 drift。看本機 `tree -L 2` 或 GitHub 介面比較準。

```
maigo/
├── agents/                          # 5 位團員（人設 + 角色）
│   └── Raana.md / Tomori.md / Anon.md / Soyo.md / Taki.md
├── commands/                        # /maigo:<name> 入口（go / team / quick / review / remember / memory / retro / describe-pr / address-comments / doctor）
├── skills/                          # 跨 agent/command 共用的 process
│   └── strict-review/ / teammate-flow/ / commit-message/ / failure-handling/ / memory-loading/ / memory-propose-confirm/ / narration/ / pr-context-cache/ / github-title-description/ / doc-link-convention/ / airflow-aware/ / commitizen-aware/
├── hooks/
│   ├── hooks.json                   # 註冊 SessionStart + TeammateIdle + Stop
│   ├── repo_detect.py               # SessionStart：偵測 repo 自動載 domain skill
│   ├── teammate_quality_check.py    # TeammateIdle：agent 輸出規格檢查
│   ├── verify_completion.py         # Stop：任務宣告完成前強制跑 test
│   ├── _hook_io.py                  # 共用 emit() payload
│   └── _retry_log.py                # 共用 JSONL retry-log（Soyo must-fix / Taki test 失敗）
├── scripts/
│   ├── validate_frontmatter.py
│   └── validate_plugin.py
├── docs/                            # ← 你在這裡
│   ├── reference/                   # agents / commands / hooks / skills / memory / character-colors
│   └── guides/                      # getting-started / contributing
├── .claude-plugin/
│   ├── plugin.json                  # plugin manifest（per Claude Code spec）
│   └── marketplace.json             # marketplace catalog（用於 /plugin install）
├── .pre-commit-config.yaml
├── CHANGELOG.md
└── README.md
```

## 注意事項

### HTML comment marker 與 agent loader

Agent / command / skill source 檔內含 `<!-- mkdocs-include-start -->` HTML comment marker，用於 mkdocs include-markdown frontmatter 處理。markdown comment 不會被 render，但會出現在 Claude Code agent loader 餵給 LLM 的 system prompt 內。HTML comment 通常不影響 LLM 行為，但若日後 agent 表現異常，此處可作為調查方向之一。

## 報 bug / 提 idea

issue 模板還沒寫；先寫一個簡短的 repro / 期待行為即可。

## Future considerations

### Zensical（MkDocs 替代方案）

目前不切換至 Zensical（Material for MkDocs 作者新作，尚未 GA）的原因：
Maigo 重度依賴 `include-markdown`、`pymdownx.superfences`、`admonition`、`pymdownx.details`，這些插件均不在 Zensical 目前支援清單。切換成本高（mkdocs.yml、pyproject.toml、CI workflow、`docs/{agents,commands,skills}/` 底下的 include-markdown shim 可能全部重寫），收益不明確——Material theme 已滿足現有文件需求。

**重新評估時機**：Zensical 進入 GA 且明確支援等價的 include-markdown 機制時；或 Maigo 文件需求發生重大變化、Material theme 不再夠用時。

## License

MIT.
