---
description: 對 PR / branch / commit range 做嚴格 review——樂奈看 context、燈寫對照基準、爽世挑問題、立希跑 verify。愛音不上場。
---

<!-- mkdocs-include-start -->

# /maigo:review

對**既有的**變更做嚴格 review。跟 `/maigo:go` 不同，這裡沒有實作環節——
變更已經寫好了，要做的是**判斷它對不對**。

## 使用

```
/maigo:review <github-pr-url>     # GitHub PR（需要 gh CLI）
/maigo:review <branch-name>        # 本地 branch（跟 main / 預設 base 比）
/maigo:review <commit-range>       # 例：HEAD~3..HEAD 或 main..feature
```

不給參數 → 預設 `HEAD` 對 `main`（review 你目前 branch 的所有變更）。

**模式（optional）：**

```
/maigo:review --mode=design-preview <target>     # 只看設計層，不查 evidence
/maigo:review --mode=compliance-only <target>    # 只查 convention/safety/magic/TODO/bloat
/maigo:review <target>                            # 預設 full mode（9 項全跑）
```

| Mode | Soyo checklist | Taki 跑驗證？ | 適用場景 |
|------|----------------|---------------|----------|
| `full`（預設） | 9 項全跑 | ✅ | 一般 PR review |
| `design-preview` | 只跑 1 + 4 | ❌ skip | 早期設計討論、介面預審 |
| `compliance-only` | 只跑 4 / 5 / 6 / 7 / 8 | ✅ | 安全 audit、規範對焦 |

## Mode 旗標處理

Orchestrator 在啟動 Soyo / Taki 前先解析 `--mode`：
- 把 mode 名稱寫進 review-rubric.md 開頭 `<!-- mode: <mode-name> -->` 註解，讓 Soyo / Taki 啟動時讀得到
- Soyo 收到 prompt 時被明確告知 checklist subset（mirror `skills/strict-review/SKILL.md` 「Adapting per context」表的寫法——standard 9 項保持，只是把不在 subset 的項在輸出表標 `[—]` 而非 `[x]` / `[ ]`，附 reason「skipped by mode=<name>」）
- mode = `design-preview` → 不啟動 Taki stage；最終報告 Verification 段註記「Skipped (mode=design-preview)」
- mode = `compliance-only` → 正常啟動 Taki stage（與 full mode 相同）

## 流程

### 1. 樂奈 (Raana) — 抓變更 + 周邊 context。「看完了。相關的在這三個檔案。」

**先套 [`skills/pr-context-cache`](https://github.com/Lee-W/maigo/blob/main/skills/pr-context-cache/SKILL.md)**：第一次 fetch 後 cache 到 `/tmp/maigo/<repo>/review-rubric.md` 開頭的 `<!-- pr-context-cache:start v1 -->` 段。後續 re-review 偵測同一段且 diff sha 未變 → 跳過 `gh pr view / gh pr diff / gh pr checks` 重抓。

- **取 diff**：
  - GitHub PR → `gh pr view <num/url> --json title,body,additions,deletions`、`gh pr diff <num/url>`
  - 本地 branch → `git diff <base>...<branch>`、`git log <base>...<branch>`
  - commit range → `git diff <range>`
- **看周邊**：diff 涉及檔案的呼叫關係（被誰用、用了誰）、同檔案 / 同 module 既有的寫法慣例
- 回報：變更摘要 + 周邊 context + 既有慣例

### 2. 燈 (Tomori) — 寫 review rubric 到 `/tmp/maigo/<repo>/review-rubric.md`。「……讓我先理清楚它想做什麼。」

（`<repo>` = `basename "$PWD"`；目錄不存在請先 `mkdir -p`）

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

最終一份 review report 給使用者：

```markdown
# Review: <PR title / branch / range>

## Context（樂奈）
<變更摘要 + 周邊 context 一段>

## Rubric（燈）
<rubric 摘要——詳見 /tmp/maigo/<repo>/review-rubric.md>

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
