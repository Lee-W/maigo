---
name: pr-context-cache
description: This skill should be used during /maigo:review when fetching or reusing PR context (title / body / diff / CI status / linked issues), caching the first fetch into review-rubric.md so subsequent re-review rounds skip re-fetching.
---

<!-- mkdocs-include-start -->

# PR Context Cache

**Owner Agent**: Raana
**Consumers**: [`/maigo:review`](https://github.com/Lee-W/maigo/blob/main/commands/review.md) step 1

## Why this skill exists

`/maigo:review` 的第一步是 Raana 抓 PR context。「re-review」（同一個 PR 改完再跑一次）
時這些資料幾乎沒變——重抓只是浪費時間。第一次 fetch 後 cache 到
`.maigo/review-rubric.md` 開頭的機讀區段，re-review 偵測同 source 且 diff sha 未變
→ 直接還原，跳過全部 `gh` / `git` 重抓。

## 怎麼跑

機械流程由 script 代勞（cache 偵測 / 驗證 / fetch / truncate / 寫檔一條龍）：

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/pr_context_cache.py" <source> \
    [--rubric .maigo/review-rubric.md] [--base main]
```

- `<source>`：GitHub PR URL / PR 編號（需要 gh CLI）、本地 branch 名、或 commit range
- 在 maigo repo 自身工作時，直接 `python3 scripts/pr_context_cache.py` 即可

stdout 第一行是 `cache_hit: true|false`，其後是 cache 區段全文——
含 Source / PR number / Title / Body（截 500 行）/ Linked issues / CI status /
Diff stat / **Review threads（inline review thread，含 resolve 狀態）/ Review
summaries（`gh pr view --json reviews`）/ Conversation comments（`gh pr view
--json comments`）** / Diff sha / Full diff（截 2000 行）。

Review threads / summaries / comments 只在 `<source>` 是 PR 時抓（branch / range
diff 沒有對應的 GitHub review thread 可抓）。**未解決（`[OPEN]`）的 thread 在輸出
裡會被特別標出**——下結論前先檢查這些 thread 對照目前 diff 是否已經處理，
避免漏看 reviewer 留下但尚未收斂的架構意見（真實事故：只抓 diff + PR body +
reviewDecision，漏看某 PR 上一位 reviewer 對 `isinstance`-based type-switch 設計
留下的 OPEN thread，直到使用者問「有沒有看 TP 說了什麼」才補回）。

## 行為摘要

- **cache hit**（Source 相同且 diff sha256 未變）→ 印出快取區段，不碰網路（除了重算 sha 的那次 diff）
- **cache miss** → 重抓全部欄位，寫回 rubric 開頭
  `<!-- pr-context-cache:start v1 -->` … `<!-- pr-context-cache:end -->` 區段
  （無檔案 → 建立；無區段 → prepend；有舊區段 → 整段取代）

## Fallback

script 跑不起來（找不到路徑、無 gh CLI、git 失敗 → exit 1 + stderr）→
Raana 回退手動抓：依 `/maigo:review` step 1 列的 `gh pr view / gh pr diff /
gh pr checks`（或 `git diff` / `git log`）指令直接 fetch，不寫 cache。

## What this skill does NOT cover

- 讀 `review-rubric.md` 其餘內容（rubric 本身由 Tomori 撰寫）
- 評估 diff 是否有問題（那是 Soyo 的工作）
- 決定要 review 哪個 target（caller 傳進來）
- 非 review 流程的 PR context 抓取（如 `/maigo:describe-pr` 不走這個 skill）
