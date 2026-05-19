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
type: user | feedback | convention | reference
triggers: [<skill-name>, ...]   # optional；只有 type: convention 適用
---
```

| 欄位 | 說明 |
|------|------|
| `name` | 人類可讀標題，可以有中文、空格 |
| `description` | 一句話摘要；reader 用這句話決定要不要讀全文 |
| `type` | 見下方 Types 說明 |
| `triggers` | optional；skill name list；只 `type: convention` 適用 |

**`triggers` 載入行為**：Soyo 啟動時，對每個 `type: convention` entry 的 `triggers` list，
逐一嘗試讀 `skills/<name>/SKILL.md`——存在就附加為 base 9 項 checklist 之後的 item 10+；
不存在 → log「triggered skill `<name>` 找不到，忽略」，不 crash，繼續後續 entry。
其他 type（`user` / `feedback` / `reference`）的 `triggers` 欄位無聲忽略。

## Types 解釋 + 範例

### `convention` — 跨專案共用慣例

可被 reviewer（Soyo）用來判斷對錯。

```markdown
---
name: Integration test 偏好
description: 偏好用 integration test 驗行為，而非大量 unit mock
type: convention
---

寫測試時，優先用 integration test 驗端到端行為。
只有在外部 dependency（網路、DB）無法控制時才用 mock。

不要為了 coverage 數字用假的 mock 把 business logic 測掉。
```

convention entry 也可以透過 `triggers` 欄位觸發額外 domain skill 載入（v1.1 新增）：

```markdown
---
name: Airflow DAG 慣例
description: 這個專案的 Airflow DAG 寫法與版本控制規範
type: convention
triggers: [review-airflow]
---

DAG 檔案放 `dags/` 目錄，每個 DAG 一個檔案。
使用 `@dag` decorator 而非直接建立 `DAG` 物件。
task dependency 用 `>>` operator，不用 `set_upstream/set_downstream`。
```

Soyo 載入這個 entry 時，會額外讀 `skills/review-airflow/SKILL.md`，
把其中的 checklist 附加為 item 10+ 一起跑。
skill 不存在 → log「triggered skill `review-airflow` 找不到，忽略」，不 crash。

### `user` — 使用者個人偏好

語言、稱呼、風格偏好等，影響 agent 怎麼跟使用者互動。

```markdown
---
name: 語言偏好
description: 偏好中文回覆，技術詞彙可保留英文
type: user
---

與我溝通時請用中文，程式語言關鍵字、函式名、路徑等技術詞彙保留英文。
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
| **Tomori** | 寫計畫時把相關 `convention` / `user` entry 內嵌進 plan |
| **Soyo** | review 時把 `convention` entry 當作 checklist item 4 的判斷依據 |

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

**Agent 不自動寫 memory**（v0 設計決策）。

## 載入語意

Reader agent 啟動時：

1. `cat ~/.config/maigo/memory/MEMORY.md`
2. 讀 index 的每一行 `- [Title](file.md) — description`
3. 判斷哪些 entry 的 description 跟當前 task keyword / 主題 overlap
4. 讀相關 entry 的全文，當作 task context 一部分
5. 在輸出開頭印 `## Loaded memory entries`，列出用了哪些（沒用就寫「（無相關 entry）」）

**以下情況都當「沒記憶」處理，繼續做事，不報錯、不要求使用者建立：**

- `~/.config/maigo/memory/` 不存在
- `MEMORY.md` 不存在或是空的
- index 裡沒有任何跟當前 task 相關的 entry

## What v0 doesn't do

- **沒有 validator**——schema 鬆，使用者手改也沒問題
- **Agent 不自動寫 memory**——只有 `/maigo:remember` 和手改
- **不做語意搜尋、不做 embedding**——純粹靠 description keyword / 主題 overlap
- **不跨機器同步**——使用者自行用 dotfiles / git 管理 `~/.config/maigo/memory/`
- **Memory 不會讓 Soyo 放水**——記憶是 input，不是 waiver；
  `feedback` type 不降低標準，`convention` type 才算 convention claim。
  見 [Memory is input, not waiver](../skills/strict-review.md#memory-is-input-not-waiver)
