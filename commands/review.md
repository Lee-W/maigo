---
description: 對 PR / branch / commit range 做嚴格 review——樂奈看 context、燈寫對照基準、爽世挑問題、立希跑 verify。愛音不上場。
---

<!-- mkdocs-include-start -->

# /maigo:review

對**既有的**變更做嚴格 review。跟 `/maigo:go` 不同，這裡沒有實作環節——
變更已經寫好了，要做的是**判斷它對不對**。

## 使用

```
/maigo:review <github-pr-url>          # GitHub PR（需要 gh CLI）
/maigo:review <pr-1> <pr-2> ...         # 多 PR 批次（空白或逗號分隔）
/maigo:review <branch-name>             # 本地 branch（跟 main / 預設 base 比）
/maigo:review <commit-range>            # 例：HEAD~3..HEAD 或 main..feature
```

不給參數 → 預設 `HEAD` 對 `main`（review 你目前 branch 的所有變更）。

**模式（optional）：**

```
/maigo:review --mode=design-preview <target>     # 只看設計層，不查 evidence
/maigo:review --mode=compliance-only <target>    # 只查 convention/safety/magic/TODO/bloat
/maigo:review --bilingual <target>                # 雙語輸出（zh-TW 快結 + English detail）
/maigo:review <target>                            # 預設 full mode（9 項全跑）
```

| Mode | Soyo checklist | Taki 跑驗證？ | 適用場景 |
|------|----------------|---------------|----------|
| `full`（預設） | 9 項全跑 | ✅ | 一般 PR review |
| `design-preview` | 只跑 1 + 4 | ❌ skip | 早期設計討論、介面預審 |
| `compliance-only` | 只跑 4 / 5 / 6 / 7 / 8 | ✅ | 安全 audit、規範對焦 |

`--bilingual` 是**輸出格式 flag**，跟上面三個 mode 正交——可以跟 `--mode=*` 同時用。
偵測到 `apache/airflow` checkout（`hooks/repo_detect.py` 已 load airflow-aware）時 orchestrator 預設啟用 `--bilingual`，不必手動加旗標。

## Mode 旗標處理

Orchestrator 在啟動 Soyo / Taki 前先解析 `--mode` 與 `--bilingual`：
- 把 mode 名稱寫進 review-rubric.md 開頭 `<!-- mode: <mode-name> -->` 註解，讓 Soyo / Taki 啟動時讀得到
- Soyo 收到 prompt 時被明確告知 checklist subset（mirror `skills/strict-review/SKILL.md` 「Adapting per context」表的寫法——standard 9 項保持，只是把不在 subset 的項在輸出表標 `[—]` 而非 `[x]` / `[ ]`，附 reason「skipped by mode=<name>」）
- mode = `design-preview` → 不啟動 Taki stage；最終報告 Verification 段註記「Skipped (mode=design-preview)」
- mode = `compliance-only` → 正常啟動 Taki stage（與 full mode 相同）
- `--bilingual` 旗標**或** repo-detect 回報 `apache/airflow` → orchestrator 在最終 report 前面加一段 Taiwanese Mandarin 快結（見「## 雙語輸出」）；不影響 Soyo / Taki 行為

## 多 PR 批次與狀態前置處理

`/maigo:review` 接受**多個** PR 用空白或逗號分隔。orchestrator 自動排序後一次一個 review；每完成一個 PR 等使用者 go-ahead 才推進。

### 樂奈先抓 metadata 排隊

第一輪 🐱 樂奈以 parallel 方式抓**每個 PR** 的 lightweight metadata（不抓 diff）：

```bash
gh pr view <N> --repo <repo> --json number,title,additions,deletions,state,isDraft,mergedAt,reviewDecision
```

排序規則：

1. **Bucket A — `APPROVED`** 先（通常只欠最後一眼）
2. **Bucket B — neutral**（`reviewDecision` 為 `null` / `COMMENTED` / `REVIEW_REQUIRED`）
3. **Bucket C — `CHANGES_REQUESTED`** 最後（author 還欠 follow-up，reviewer 時間花在別處更值）
4. 每個 bucket 內按 `additions + deletions` **升序**——quick win 先

排好後印一張 queue 表給使用者：

```markdown
## 排序後 review queue（共 N 個）

| 順序 | PR | Title | Lines | State |
|---|---|---|---|---|
| 1 | #X | … | +A/-B | ✅ APPROVED |
| 2 | #Y | … | +A/-B | REVIEW_REQUIRED |
| 3 | #Z | … | +A/-B | ⚠️ CHANGES_REQUESTED |
| — | #W | … | — | ⏭️ skipped (merged) |

從 **#X** 開始。
```

第一個 PR **不必**等 go-ahead——使用者送多 PR 進來就已經授權 batch 啟動。「等 go-ahead」規則只套在 PR 與 PR 之間。

### 狀態前置處理（每 PR 進 §1 前）

| PR 狀態 | 處理 |
|---|---|
| `state == "MERGED"` 或 `mergedAt` 已設 | 不進流程，queue 上標 `⏭️ skipped (merged)`，**自動推進**到下一個 |
| `state == "CLOSED"` 未 merge | 同上，標 `⏭️ skipped (closed)` |
| `isDraft == true` | orchestrator 先問使用者「PR #N 是 draft，還是要看嗎？」`yes` → 走，`skip` → 跳下一個 |
| 其他 | 正常進入 §1 樂奈 stage |

merged / closed 的 PR **不需要** review report——只在 queue 表標 skipped 一行帶過。

### 一次一個 PR 規則

每個 PR 走完 §1-§4 出完一份 review report 後，orchestrator 在 report 結尾加一行：

```
Queue 還剩 **#Y**, **#Z** — 說 next（「好」/繼續/ok 都行）我再看下一個。
```

然後**停下來等使用者明確 go-ahead**。任何短肯定（`好` / `ok` / `next` / `下一個` / `繼續` / `go` / `yep`）都算。

- 使用者若給 substantive feedback（追問、要 re-read、pivot），先處理那個再推進
- 使用者說「全部一起看」/ `batch them` / `do them all` → 放掉這個 gate 直到 batch 結束
- 最後一個 PR 跑完 → queue 行改成最終 roll-up（見「## 輸出」雙語版範本）

## 雙語輸出

`--bilingual` 旗標或 repo-detect 自動觸發時，最終 report 在前面加一段 **Taiwanese Mandarin 快結**（1-3 句），後面接英文 detail：

```markdown
## 台灣漢語快速結論

**PR #<N> — <short title>** <APPROVE / REQUEST_CHANGES / BLOCKED>
<1-3 句：做什麼、能不能上、最大一個 concern；點到具體 file / function 名。>

---

## English — Detailed Review

[（既有的 # Review / Context / Rubric / Verdict / Verification / Bottom line 段落）]

---

**PR link:** <url>

<Queue / next-step line — 見「## 多 PR 批次」>
```

zh-TW 行文規範（通用，跨專案）：

- **「Taiwanese Mandarin」**，不寫「Traditional Chinese」
- 三個以上 item 不要 inline `(1)…(2)…(3)…`，拆 bullets
- 中英文之間留一個半形空格；不雙空格
- 技術名詞英文穿插無妨（PR / merge / refactor / cache / token / scheduler）

Repo-specific 命名規範（例如 Airflow 的 `Dag` title case + code token 例外）由各 repo 的 domain skill 負責（如 `airflow-aware` §2），這裡不重述——`--bilingual` 自動觸發那條路徑下 domain skill 已經被 repo-detect 載入。

## 流程

### 1. 樂奈 (Raana) — 抓變更 + 周邊 context。「看完了。相關的在這三個檔案。」

**先套 [`skills/pr-context-cache`](https://github.com/Lee-W/maigo/blob/main/skills/pr-context-cache/SKILL.md)**：跑 `python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/pr_context_cache.py" <source>`——第一次 fetch 後 cache 到 `.maigo/review-rubric.md` 開頭的 `<!-- pr-context-cache:start v1 -->` 段，後續 re-review 同 source 且 diff sha 未變 → 直接還原，跳過 `gh pr view / gh pr diff / gh pr checks` 重抓。script 跑不起來 → 依下面指令手動抓（不寫 cache）。

- **取 diff**：
  - GitHub PR → `gh pr view <num/url> --json title,body,additions,deletions`、`gh pr diff <num/url>`
  - 本地 branch → `git diff <base>...<branch>`、`git log <base>...<branch>`
  - commit range → `git diff <range>`
- **看周邊**：diff 涉及檔案的呼叫關係（被誰用、用了誰）、同檔案 / 同 module 既有的寫法慣例
- 回報：變更摘要 + 周邊 context + 既有慣例

### 2. 燈 (Tomori) — 寫 review rubric 到 `.maigo/review-rubric.md`。「……讓我先理清楚它想做什麼。」

（目錄不存在請先 `mkdir -p .maigo`）

從 PR description / commit message / linked issue / 變更本身，萃取出 reviewer 的**對照基準**：

```markdown
# Review rubric: <PR title>

## 這個 PR 應該做到什麼（acceptance）
1. <期待行為 1>
2. <期待行為 2>

## 應該涵蓋的 edge case
- <case 1>
- <case 2>

## 可接受 / 不可接受的 trade-off
- 可接受：<例：暫時 hardcode 設定值，下個 PR 抽出來>
- 不可接受：<例：略過 input validation>

## Description 沒講清楚的地方（需要 author 補答）
- <模糊點 1>
```

**為什麼這步很關鍵：** 沒有對照基準的 review = 憑感覺。
這也是 reviewer 不嚴謹最常見的根因。

### 3. 爽世 (Soyo) — 拿 rubric 對 diff 做嚴格 review。「你說的『應該』，是有跑過、還是只是『應該』？」

依 `skills/strict-review/SKILL.md` 操作（預設 BLOCKED、9 項 checklist、要 evidence、不接受 TODO 規避）。

**這條 command 加碼：**
- 每條 must-fix 要對應 rubric 的哪一條（acceptance / edge case / trade-off）
- 內部 / 外部 PR 改法粒度的差異，見 SKILL.md 的 "Adapting per context" 表格

**Mode-aware：** orchestrator 傳給 Soyo 的 prompt 必須明示 mode 與對應 checklist subset。Soyo 輸出 checklist 表時：mode subset 內的項照常 `[x]` / `[ ]`；不在 subset 內的項標 `[—]`，附 `skipped by mode=<name>`。

### 4. 立希 (Taki) — 跑驗證。「跑出來爆了，看 line 42。」

**若 mode=design-preview → 不啟動本 stage，最終報告 Verification 段標「Skipped (mode=design-preview)」。**

- **checkout 變更**：
  - PR → `gh pr checkout <num/url>`
  - branch → `git checkout <branch>`
- 跑 test / lint / type check，照 `agents/Taki.md` 的標準回報
- **不接受「CI 已經綠了」當理由略過**——至少重跑一次 lint/type 確認本地能複現

## 輸出

### 單一 PR / branch / range（預設）

```markdown
# Review: <PR title / branch / range>

## Context（樂奈）
<變更摘要 + 周邊 context 一段>

## Rubric（燈）
<rubric 摘要——詳見 .maigo/review-rubric.md>

## Verdict（爽世）
APPROVE | REQUEST_CHANGES | BLOCKED

### Must-fix
- ...（對應 rubric 哪一條）

### Nit / Evidence pending
- ...

## Verification（立希）
- `<cmd>` — exit <n> — <result>

## Bottom line
<一句話總結>
```

### 多 PR batch 最終 roll-up

batch 內最後一個 PR 跑完後，orchestrator 把「Queue 還剩...」那行改成 roll-up：

```markdown
**Summary of recommendations:**
- Approve: **#N**, **#N**
- Approve with nits: **#N** (one-line why)
- Request changes: **#N** (one-line why)
- Block: **#N** (one-line why)
- Skipped: **#N** (merged/closed/draft)
```

涵蓋整輪 batch，不只當下這個 PR。

### 雙語版（`--bilingual` 或 repo-detect 觸發）

最終 report 前加 Taiwanese Mandarin 快結 + horizontal rule，後面接既有英文 detail：

```markdown
## 台灣漢語快速結論

**PR #<N> — <short title>** <APPROVE / REQUEST_CHANGES / BLOCKED>
<1-3 句：做什麼、能不能上、最大一個 concern>

---

## English — Detailed Review

# Review: <PR title>
[（既有 Context / Rubric / Verdict / Verification / Bottom line 全段）]

---

**PR link:** <url>

<Queue / next-step line | batch 結束的 roll-up>
```

## 與 `/maigo:go` 的差異

| 項目 | `/maigo:go` | `/maigo:review` |
|------|---------|---------------|
| Anon 上場 | 是（核心） | 不上場 |
| 燈的產出 | 實作計畫 (`plan.md`) | review rubric (`review-rubric.md`) |
| 終態 | 變更落地 + 全綠 | review 報告 |
| 適用 | 開發新功能、修 bug | PR review、code audit |

## Orchestrator 守則

- **旁白**：orchestrator 對使用者說話時戴上旁白的臉——開場、收場、卡關節點由 🌙 Doloris / 🌑 Mortis 旁白，依 [`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md)。
- **不能跳過燈**——沒有 rubric 的 review 就是憑感覺
- **不能跳過樂奈**——脫離 context 的 review 會把「不熟悉」誤判成「有問題」
- 爽世的 verdict 不因為「author 是大佬」放水
- 立希拒絕「CI 已綠就不跑」，本地至少要重跑 lint/type
- 你（orchestrator）不要自己 review，每個 agent 都用 Task tool 啟動
- Soyo 的 review 輸出若含 `## Memory propose`，
  把 review report 完整呈現給使用者後再觸發 confirm flow；
  不要在使用者讀完 report 之前插入確認問題。
- **多 PR batch**：queue 排序、merged/closed 自動 skip、draft 先問、PR 與 PR 間等 go-ahead——細節見「## 多 PR 批次與狀態前置處理」；不要一次 fire 多個 review，不要自己決定 draft 要不要看。
- **雙語自動觸發**：repo-detect 回報 `apache/airflow` 時 orchestrator 自動加 `--bilingual`；偵測非 Airflow repo 但使用者顯式傳 `--bilingual` 也照樣執行——`--bilingual` 純粹是輸出層 flag，不會改變 agent 行為。
- orchestrator 草擬要貼到 PR 的回覆 / comment 時，遵守 [`skills/copyable-deliverable`](https://github.com/Lee-W/maigo/blob/main/skills/copyable-deliverable/SKILL.md)——放單一 fenced code block 供複製。
