# Memory Reference

## What it is

Maigo 的跨專案記憶層——平面檔案、人類可讀、可手改。

與 Claude Code 內建的 per-project memory（`CLAUDE.md`）不同：
那個是**per-project**（你在 project A 記下的東西，project B 看不到）；
這個是**cross-project**（使用者偏好、跨專案慣例，一份記憶、所有專案共用）。

v0 不做語意搜尋、不建 embedding；只是一個 reader agent 在啟動時讀的 markdown 目錄。

## Storage layout

```
~/.config/maigo/memory/
├── MEMORY.md          ← index（自動維護）
├── integration-test-preference.md
├── commit-message-style.md
└── ...
```

### `MEMORY.md`（index）

每一行代表一個 entry：

```
- [Integration test 偏好](integration-test-preference.md) — 偏好用 integration test 而非 mock
- [Commit message 風格](commit-message-style.md) — 使用 Conventional Commits 格式
```

Reader agent 啟動時先讀這個 index，依 description 判斷跟當前 task 的相關性，再決定要不要讀全文。

### Entry 檔案（`<slug>.md`）

Slug 規則：lowercase + hyphen + ASCII only。
例：`Integration test 偏好` → `integration-test-preference`

## Entry frontmatter schema

每個 entry 是一份 markdown 檔案，帶 YAML frontmatter：

```yaml
---
name: <人類可讀標題，不必跟檔名相同>
description: <一句話，給 reader agent 判斷相關性用>
type: user | feedback | project | reference
triggers: [<skill-name>, ...]   # optional；只有 type: project 適用
---
```

| 欄位 | 說明 |
|------|------|
| `name` | 人類可讀標題，可以有中文、空格 |
| `description` | 一句話摘要；reader 用這句話決定要不要讀全文 |
| `type` | 見下方 Types 說明 |
| `triggers` | optional；skill name list；只 `type: project` 適用 |

> **Frontmatter 必須是扁平結構**：不支援巢狀鍵（如 `metadata.type`）。所有欄位直接放在 `---` 最上層；巢狀結構會被 parser 讀不到，`validate_memory.py` 回報 "missing field"。

**`triggers` 載入行為**：Soyo 啟動時，對每個 `type: project` entry 的 `triggers` list，
逐一嘗試讀 `skills/<name>/SKILL.md`——存在就附加為 base 9 項 checklist 之後的 item 10+；
不存在 → log「triggered skill `<name>` 找不到，忽略」，不 crash，繼續後續 entry。
其他 type（`user` / `feedback` / `reference`）的 `triggers` 欄位無聲忽略。

## Types 解釋 + 範例

> **Note**: v0 的 spec 原本有 `convention` type；實際使用中發現 `project` 更能表達語意
> （跨專案共用的 per-project 慣例），故從 v0.1 起 enum 改為 `project`。
> 舊 entry 若仍使用 `type: convention`，validator 會發出 schema warn。

### `project` — 跨專案共用慣例

可被 reviewer（Soyo）用來判斷對錯。

```markdown
---
name: Integration test 偏好
description: 偏好用 integration test 驗行為，而非大量 unit mock
type: project
---

寫測試時，優先用 integration test 驗端到端行為。
只有在外部 dependency（網路、DB）無法控制時才用 mock。

不要為了 coverage 數字用假的 mock 把 business logic 測掉。
```

project entry 也可以透過 `triggers` 欄位觸發額外 domain skill 載入（v1.1 新增）：

```markdown
---
name: Airflow Dag 慣例
description: 這個專案的 Airflow Dag 寫法與版本控制規範
type: project
triggers: [airflow-aware]
---

Dag 檔案放 `dags/` 目錄，每個 Dag 一個檔案。
使用 `@dag` decorator 而非直接建立 Dag 物件。
task dependency 用 `>>` operator，不用 `set_upstream/set_downstream`。
```

Soyo 載入這個 entry 時，會額外讀 `skills/airflow-aware/SKILL.md`，
把其中的 checklist 附加為 item 10+ 一起跑。
triggered skill 不存在（typo、未安裝等）→ log「triggered skill `<name>` 找不到，忽略」，不 crash。

### `user` — 使用者個人偏好

語言、稱呼、風格偏好等，影響 agent 怎麼跟使用者互動。

```markdown
---
name: 語言偏好
description: 偏好漢語回覆，技術詞彙可保留英文
type: user
---

與我溝通時請用漢語，程式語言關鍵字、函式名、路徑等技術詞彙保留英文。
不要硬翻「callback」、「dependency injection」之類的詞。
```

### `feedback` — 過去任務的使用者反饋

**Informational only**——只是情報，不能降低標準。

```markdown
---
name: Review 嚴格度反饋（2025-Q1）
description: 使用者曾反映 review 輸出太冗長
type: feedback
---

2025 年初 code review 流程反饋：
- 每條 must-fix 的說明文字太長，希望更精簡
- 「為什麼」的說明可以短一點，抓重點即可
```

> 注意：`feedback` 不能改變 Soyo 的判斷標準。
> 見 [Memory is input, not waiver](../skills/strict-review.md#memory-is-input-not-waiver)。

### `reference` — 靜態參考資料

URL、文件節錄、style guide 摘要等。

```markdown
---
name: Conventional Commits spec
description: commit message 格式參考
type: reference
---

Commit message 格式：<type>(<scope>): <description>

type: feat | fix | docs | style | refactor | test | chore
body 和 footer 可選，breaking change 用 BREAKING CHANGE: 標注。

spec: https://www.conventionalcommits.org/
```

## 誰讀誰寫

### Readers（啟動時自動載入相關 entry）

| Agent | 為什麼讀 |
|-------|---------|
| **Raana** | 探索時帶入使用者慣例，找更對的東西 |
| **Tomori** | 寫計畫時把相關 `project` / `user` entry 內嵌進 plan |
| **Soyo** | review 時把 `project` entry 當作 checklist item 4 的判斷依據 |

### Non-readers（有意設計）

| Agent | 理由 |
|-------|------|
| **Anon** | 透過讀 Tomori 的 plan（`## Honoured memory` 段）間接拿到記憶；不用自己讀 |
| **Taki** | 驗證是看 evidence，不看記憶；記憶不影響 test 是否過 |

### Writers

| 方式 | 說明 |
|------|------|
| `/maigo:remember` | orchestrator 互動式命令，推斷 type / name、確認後寫檔 |
| 手改 | 直接編輯 `~/.config/maigo/memory/` 內的 markdown 檔案 |
| `## Memory propose`（Soyo / Anon） | agent 在 turn 末 propose；orchestrator 確認後才寫 |

**Agent 不自動寫 memory**——只能 propose；寫入仍由 orchestrator + user confirm 觸發（v1）。

### v1 propose（Soyo / Anon 即時 propose）

Soyo 或 Anon 在 turn 輸出末尾加 `## Memory propose` 段，格式如下：

```markdown
## Memory propose

- **type**: feedback | project | user | reference
- **name**: <人類可讀標題，短，例：「Review 說明精簡偏好」>
- **slug**: <lowercase-hyphen-ascii，例：review-explanation-concise>
- **description**: <一句話，給 MEMORY.md index 用>
- **body**: <entry 正文；可多行>
- **rationale**: <為什麼現在 propose——觸發這筆 propose 的 context 一句話>
```

**欄位規則：**

| 欄位 | 必填 | 規則 |
|------|------|------|
| `type` | 是 | 四選一；agent 依啟發式判斷，不確定時選最可能的並在 rationale 說明 |
| `name` | 是 | 中文或英文皆可；短但可讀 |
| `slug` | 是 | lowercase + hyphen + ASCII only |
| `description` | 是 | 一句話；給 reader 決定要不要讀全文用 |
| `body` | 是 | entry 正文；可多行 |
| `rationale` | 是 | 讓 orchestrator / 使用者判斷「這筆 propose 合不合理」的 context |

**每 turn 最多 propose 1 筆**——不允許一次出現兩個 `## Memory propose` 段。

**propose ≠ 寫入**：propose 段出現後，orchestrator 跑 confirm flow，使用者確認後才寫。agent 輸出 propose 段不等於記憶已存。

**格式範例**（`type: feedback` 典型情境）：

```markdown
## Memory propose

- **type**: feedback
- **name**: Review 說明精簡偏好
- **slug**: review-explanation-concise
- **description**: 使用者偏好 must-fix 說明精簡、抓重點，不要長篇大論
- **body**: Review 輸出的 must-fix 說明文字要精簡。「為什麼」抓重點即可，不要寫一大段。
- **rationale**: 使用者在這個 review 回合說「說明可以短一點」，是可複用的偏好信號
```

## 載入語意

Reader agent 啟動時依序讀**兩層** index：

1. `cat ~/.config/maigo/memory/MEMORY.md`（cross-project）
2. `cat ~/.claude/projects/<current-project>/memory/MEMORY.md`（per-project，若存在）
3. 讀兩層 index 的每一行 `- [Title](file.md) — description`，合併後判斷哪些 entry 的 description 跟當前 task keyword / 主題 overlap
4. 讀相關 entry 的全文（**兩層合計上限 10 筆**），當作 task context 一部分
5. 在輸出開頭印 `## Loaded memory entries`，列出用了哪些（沒用就寫「（無相關 entry）」）

**Fallback：兩層各自獨立，任一層不影響另一層：**

- 某一層目錄不存在、`MEMORY.md` 不存在或是空的、或 index 無相關 entry → 該層當「沒記憶」，另一層照常
- **兩層皆無相關記憶**才整體當「沒記憶」處理，繼續做事，不報錯、不要求使用者建立

## Validation

Memory entry 的 schema 採「warn-not-block」策略——schema 錯誤只 warn，不阻止 agent 工作。
有兩層 validation 機制：

### 1. `validate_memory.py`（手動跑）

[`python3 scripts/validate_memory.py`](https://github.com/Lee-W/maigo/blob/main/scripts/validate_memory.py)
掃描 cross-project（`~/.config/maigo/memory/`）與 project-specific（`~/.claude/projects/*/memory/`）
兩個來源，逐一檢查 entry frontmatter：

- 缺 `name` / `description` / `type` → warning
- `type` 不在 `{user, feedback, project, reference}` → warning
- unknown key（如 `originSessionId`）→ 完全忽略，不 warn

輸出範例：

```
## Cross-project memory: /Users/you/.config/maigo/memory
  ! some-entry.md: missing field: `type`
  ! old-entry.md: type=`convention` not in {feedback, project, reference, user}

## Project memory (-Users-you-my-project): /Users/you/.claude/projects/-Users-you-my-project/memory
  ✓ 3 entries passed schema check
```

加 `--strict` flag 時，有任何 warning 則 exit 1（給 CI / power user 用）。

### 2. Reader agent inline warn

Raana、Tomori、Soyo 在載入每個 entry 後做最小 schema 自檢。遇到問題不 abort，
繼續使用該 entry，但在 `## Loaded memory entries` 輸出段該行末尾加 `[schema warn: ...]`：

```
## Loaded memory entries
- [Integration test 偏好](integration-test-preference.md) — 已載入
- [Some entry](some-entry.md) — 已載入 [schema warn: 缺 type]
```

這讓使用者在 agent 工作輸出裡馬上看到問題，自己決定要不要修。

## What v0 doesn't do

- **Lazy validator only**——[`scripts/validate_memory.py`](https://github.com/Lee-W/maigo/blob/main/scripts/validate_memory.py)
  只 warn 不 block；reader agent 載入 entry 時遇到 schema 不符也只在輸出標 `[schema warn: ...]`。
  沒有 strict mode 預設啟用、沒有 pre-commit hook。
- **Agent 不自動寫 memory**——只能 propose；寫入仍由 orchestrator + user confirm 觸發。（`/maigo:remember` 是另一條互動式寫入路徑）
- **不做語意搜尋、不做 embedding**——純粹靠 description keyword / 主題 overlap
- **不跨機器同步**——使用者自行用 dotfiles / git 管理 `~/.config/maigo/memory/`
- **Memory 不會讓 Soyo 放水**——記憶是 input，不是 waiver；
  `feedback` type 不降低標準，`project` type 才算 convention claim。
  見 [Memory is input, not waiver](../skills/strict-review.md#memory-is-input-not-waiver)
