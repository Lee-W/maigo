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

## 流程

### 1. 樂奈 (Raana) — 抓變更 + 周邊 context

- **取 diff**：
  - GitHub PR → `gh pr view <num/url> --json title,body,additions,deletions`、`gh pr diff <num/url>`
  - 本地 branch → `git diff <base>...<branch>`、`git log <base>...<branch>`
  - commit range → `git diff <range>`
- **看周邊**：diff 涉及檔案的呼叫關係（被誰用、用了誰）、同檔案 / 同 module 既有的寫法慣例
- 回報：變更摘要 + 周邊 context + 既有慣例

### 2. 燈 (Tomori) — 寫 review rubric 到 `/tmp/maigo/<repo>/review-rubric.md`

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

### 3. 爽世 (Soyo) — 拿 rubric 對 diff 做嚴格 review

依 `skills/strict-review/SKILL.md` 操作（預設 BLOCKED、9 項 checklist、要 evidence、不接受 TODO 規避）。

**這條 command 加碼：**
- 每條 must-fix 要對應 rubric 的哪一條（acceptance / edge case / trade-off）
- 內部 / 外部 PR 改法粒度的差異，見 SKILL.md 的 "Adapting per context" 表格

### 4. 立希 (Taki) — 跑驗證

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

- **不能跳過燈**——沒有 rubric 的 review 就是憑感覺
- **不能跳過樂奈**——脫離 context 的 review 會把「不熟悉」誤判成「有問題」
- 爽世的 verdict 不因為「author 是大佬」放水
- 立希拒絕「CI 已綠就不跑」，本地至少要重跑 lint/type
- 你（orchestrator）不要自己 review，每個 agent 都用 Task tool 啟動
