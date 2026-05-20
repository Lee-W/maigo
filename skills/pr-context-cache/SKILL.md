---
name: pr-context-cache
description: This skill should be used during /maigo:review when fetching or reusing PR context (title / body / diff / CI status / linked issues), caching the first fetch into review-rubric.md so subsequent re-review rounds skip re-fetching.
---

<!-- mkdocs-include-start -->

# PR Context Cache

**Owner Agent**: Raana
**Consumers**: [`/maigo:review`](https://github.com/Lee-W/maigo/blob/main/commands/review.md) step 1

## Why this skill exists

`/maigo:review` 的第一步是 Raana 抓 PR context（title / body / diff / CI status / linked issues）。
當使用者做「re-review」（同一個 PR 改完再跑一次）時，這些資料幾乎沒變——重抓只是浪費時間。

這個 skill 在第一次 fetch 後把 context cache 到 `review-rubric.md` 開頭的機讀區段。
後續 re-review 偵測到相同 source 且 diff sha 未變 → 直接還原 cache，跳過全部 `gh` / `git` 命令。

## Inputs

- **Source**：review 參數（GitHub PR URL / branch name / commit range）
- **review-rubric.md 路徑**：`/tmp/maigo/<repo>/review-rubric.md`（`<repo>` = `basename "$PWD"`）
- **目前 diff**（cache miss 時抓）

## Outputs

給 caller 一個 dict-like summary：

```
cache_hit: true | false
source: <github-pr-url | branch-name | commit-range>
title: <PR title 或 "n/a">
body: <PR body，截斷版>
linked_issues: <list 或 "n/a">
ci_status: <gh pr checks 摘要 或 "n/a">
diff_stat: <diff --stat output>
diff_full: <diff 內容，截斷版>
```

## Cache schema

寫入 `review-rubric.md` 開頭的獨立區段（HTML comment 包住作為機讀標記）：

```markdown
<!-- pr-context-cache:start v1 -->
## PR Context (cached)

- **Source**: <github-pr-url | branch-name | commit-range>
- **Fetched at**: <ISO timestamp>
- **PR number**: <num or "n/a">
- **Title**: <title>
- **Body**: <body, truncated to 500 lines, suffix "...[truncated]" if cut>
- **Linked issues**: <list of #N from body / commits, or "n/a">
- **CI status**: <gh pr checks output 摘要，或 "n/a"（非 GitHub PR）>
- **Diff stat**: <git diff --stat 或 gh pr diff --stat output>
- **Diff sha**: <sha256 of full diff，用來偵測 diff 改變>

<details>
<summary>Full diff (cached, first 2000 lines)</summary>

```diff
<diff，過大時取前 2000 行 + 末尾標 "[diff truncated at 2000 lines]">
```

</details>
<!-- pr-context-cache:end -->
```

## 操作流程

### 1. Detect cache

讀 `/tmp/maigo/<repo>/review-rubric.md`（若存在），grep `<!-- pr-context-cache:start v1 -->`。
若找到 → 進入步驟 2（Validate）；若無 → 直接跳步驟 3（Fetch）。

### 2. Validate cache（若存在）

- 比對「Source」欄位是否等於本次 review 參數
- 比對「Diff sha」欄位是否等於現在重抓 diff 的 sha256

兩者皆同 → **cache hit**：
- 輸出 `cache_hit=true`
- 從 cache 區段還原所有 fields，回傳給 caller
- **結束，跳過步驟 3-5**

任一不同 → **cache miss**：繼續步驟 3。

### 3. Fetch（cache miss / 無 cache）

依 source 類型抓資料：

**GitHub PR：**
- `gh pr view <id> --json title,body,number` → title / body / PR number
- `gh pr diff <id>` → diff 內容
- `gh pr checks <id>` → CI status 摘要
- body 裡的 `#N` / `Closes #N` / `Refs #N` → linked issues

**本地 branch：**
- `git log <base>...<branch>` → commits（找 linked issues）
- `git diff <base>...<branch>` → diff 內容
- PR number = `n/a`、CI status = `n/a`

**Commit range：**
- `git log <range>` → commits（找 linked issues）
- `git diff <range>` → diff 內容
- PR number = `n/a`、CI status = `n/a`

計算 `diff_sha`：`sha256(full diff content)`。

### 4. Truncation

- **Diff**：取前 2000 行，末尾加 `[diff truncated at 2000 lines]`（與 `/maigo:review` 既有慣例一致）
- **Body**：取前 500 行，末尾加 `...[truncated]`

### 5. Write cache

把 cache schema 寫到 `review-rubric.md` 開頭：
- 檔案不存在 → 建立，cache 區段為全部內容
- 存在但無 cache 區段 → prepend（cache 區段 + 換行 + 既有內容）
- 存在且有舊 cache 區段 → 整段取代（`<!-- pr-context-cache:start v1 -->` 到 `<!-- pr-context-cache:end -->` 含端點）

### 6. Output

回傳 dict-like summary 給 caller（見 Outputs 段）。

## What this skill does NOT cover

- 讀 `review-rubric.md` 其餘內容（rubric 本身由 Tomori 撰寫）
- 評估 diff 是否有問題（那是 Soyo 的工作）
- 決定要 review 哪個 target（caller 傳進來）
- 非 review 流程的 PR context 抓取（如 `/maigo:describe-pr` 不走這個 skill）
