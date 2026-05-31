# Commands Reference

Maigo 提供十個命令，所有命令的 source-of-truth 是 `commands/*.md`。
本頁是 quick reference。

## `/maigo:go` — 開發新功能 / 修 bug

順序版工作流，5 個 stage 全跑：

```
/maigo:go <任務描述>
```

| Stage | Agent | 做什麼 |
|-------|-------|--------|
| 1 | Raana | 探索 codebase 找相關位置、慣例 |
| 2 | Tomori | 寫 `.maigo/plan.md` |
| 3 | (user) | 確認 plan、回 open questions |
| 4 | Anon | 按 plan 實作 |
| 5 | Soyo | review（依 `strict-review` skill） |
| 6 | Taki | 跑 test / lint / type check |

**失敗處理：** 任何 stage 卡關 → 回 Anon 修正。同條 must-fix / failure 連續 **2** 次卡關才停下——詳見 [`skills/failure-handling`](../skills/failure-handling.md)。

## `/maigo:team` — 並行版的 /maigo:go

跟 `/maigo:go` 同流程，但 step 5 和 step 6（Soyo + Taki）並行跑：

```
/maigo:team <任務描述>
/maigo:team --force-sequential <任務描述>
```

### Trade-off

| 模式 | Wall clock | 白做工風險 |
|------|-----------|-----------|
| `/maigo:go` | 100% | 0（Soyo 擋下就不跑 test） |
| `/maigo:team` | ~60-70% | 中（Soyo 擋下時 Taki 可能已跑完） |

多數情況淨值正。高風險變更（重構、scope 大）建議用 `/maigo:go` 順序版。

### 合流邏輯

| Soyo | Taki | 處理 |
|------|------|------|
| APPROVED | PASS | 完成 |
| APPROVED | FAIL | 回 Anon 修 test failure（review 不重跑） |
| NEEDS_CHANGES / BLOCKED | PASS | 回 Anon 修 must-fix，修完**重跑 Soyo + Taki** |
| NEEDS_CHANGES / BLOCKED | FAIL | 兩邊一起修，重跑 |

## `/maigo:doctor` — 環境與配置診斷

檢查外部依賴（gh, python, git）、記憶層目錄、以及當前專案的 Taki (Verifier) 是否能正確跑起測試。

```
/maigo:doctor
```

## `/maigo:quick` — 輕量任務入口

跳過 Raana / Tomori，orchestrator 直接呼叫 Anon。Anon 做完跑 Soyo 輕量 review（9 項 → 4 項），test 由 stop hook 兜底。

```
/maigo:quick <小任務描述>
```

### Soyo 輕量 checklist（9 項砍到 4 項）

跑：1（acceptance match）+ 4（convention）+ 5（safety）+ 7（no TODO evasion）

略：2（evidence，由 stop hook 兜底）/ 3（edge case）/ 6（magic）/ 8（bloat）/ 9（completeness theatre）

### 邊界

使用者說是 quick-fix 就是 quick-fix——不自動 gate。orchestrator 看到大改動描述會**一次**提醒「要改用 `/maigo:go` 嗎」，使用者拒絕後不再追問。

### 與其他命令的差異

| 項目 | `/maigo:quick` | `/maigo:go` | `/maigo:team` |
|------|-------------|-------------|---------------|
| Raana / Tomori | skip | run | run |
| Soyo | 輕量 4 項 | 完整 9 項 | 完整 9 項 |
| Taki | stop hook 兜底 | 顯式 | 顯式（並行） |

## `/maigo:review` — Review 既有變更

Anon 不上場，只有 Raana → Tomori → Soyo → Taki：

```
/maigo:review https://github.com/org/repo/pull/123    # GitHub PR（需要 gh CLI）
/maigo:review feature/email-validation                 # 本地 branch（vs main）
/maigo:review HEAD~3..HEAD                             # commit range
/maigo:review                                          # 預設目前 branch vs main
```

**Mode（optional）：**

| Mode | Soyo checklist | Taki | 場景 |
|------|----------------|------|------|
| `full`（預設） | 9 項全跑 | ✅ | 一般 PR review |
| `--mode=design-preview` | 1 + 4 | skip | 早期設計討論、介面預審 |
| `--mode=compliance-only` | 4/5/6/7/8 | ✅ | 安全 audit、規範對焦 |

| Stage | Agent | 做什麼 |
|-------|-------|--------|
| 1 | Raana | 抓 diff + 周邊 context（用 `gh pr view`、`gh pr diff` 或 `git diff`） |
| 2 | Tomori | **寫 `.maigo/review-rubric.md`**（不是實作計畫，是 reviewer 對照基準） |
| 3 | Soyo | 拿 rubric 對 diff 嚴格 review |
| 4 | Taki | checkout 變更，跑 test / lint / type check |

### 為什麼需要 rubric

沒有對照基準的 review = 憑感覺。
有 rubric 後 Soyo 可以逐條對照「期待行為 / 應涵蓋 edge case / 可接受 trade-off」，
避免「自己當下覺得不錯就 approve」這種偷懶 review。

### 內部 vs 外部 PR 改法粒度

| Context | Soyo 給的 must-fix |
|---------|-------------------|
| 內部 PR（你 own 的 code） | 具體改法 + 為什麼 |
| 外部 PR（別人的 code） | 方向 + 為什麼；exact code 是 author 的事 |

詳見 `skills/strict-review/SKILL.md` 的 "Adapting per context" 表。

## `/maigo:remember` — 寫入跨專案記憶

把一句話的偏好 / 慣例 / 反饋存進記憶層（`~/.config/maigo/memory/`）。
Orchestrator 推斷 type / name，AskUserQuestion 確認後才寫檔。

```
/maigo:remember <自然語言描述>
```

例：

```
/maigo:remember 以後 review 要記得我偏好 integration test 而非 mock
/maigo:remember 我的 commit message 一律用 Conventional Commits
```

這是 Maigo 第一個需要 multi-turn 互動的命令：orchestrator 問、使用者答、確認後才寫。
命令只動 `~/.config/maigo/memory/`，不碰 repo。

→ 完整 storage spec、types 說明、entry 範例：[Memory reference](memory.md)

## `/maigo:memory` — 列當前跨專案記憶

列出記憶層目前儲存的跨專案偏好 / 慣例 / 反饋。**read-only，不寫任何檔。**

```
/maigo:memory             # 列全部
/maigo:memory project     # 只列 project type
/maigo:memory user        # 只列 user type
/maigo:memory feedback
/maigo:memory reference
```

若記憶層尚未建立，會印友善訊息並引導使用者用 `/maigo:remember` 建立第一筆。

→ [Memory reference](memory.md)

## `/maigo:retro` — Session 結束時把學到的事存進記憶

session 快結束時，`/maigo:retro` 從對話 context 撈出偏好 / 約定 / 教訓候選，**逐筆** AskUserQuestion 確認，使用者接受後寫入記憶層。

**寫檔機制 reuse `/maigo:remember`**——retro spec 本身不重複寫一份 storage / rollback / 同 slug 衝突處理，全部指向 remember 的步驟 5 + 6。

orchestrator 判斷兩條路徑：
- **同 session**：直接從對話 context 撈候選，逐筆 propose。
- **跨 session fallback**：context 不存在時先問使用者「剛剛做了什麼」，再從回覆撈候選跑同流程。

→ [/maigo:remember](../commands/remember.md)

→ [Memory reference](memory.md)

## `/maigo:describe-pr` — 產 GitHub PR title + description

從當前 branch 的 commits / diff 產出 PR 草稿（user-impact title + Why / What / Test Plan）。
Orchestrator 前置抓 git context，燈 (Tomori) 套 `github-title-description` skill 產草稿。**read-only，不寫檔、不開 PR。**

```
/maigo:describe-pr                    # base 預設 main
/maigo:describe-pr --base develop
```

PR title **不套** conventional commits 格式（user-impact 句子就好）；
即使 repo 用 commitizen，那只影響 commit message，不影響 PR title。

→ Skill: [github-title-description](../skills/github-title-description.md)

## `/maigo:address-comments` — 處理 PR 上的 review 意見

讀當前 branch 對應 PR 的 GitHub review 意見，列出讓使用者挑，擬路由計畫確認後逐項實作：

```
/maigo:address-comments    # 一律針對當前 branch 的 PR；讀不到就擋下
```

| 步驟 | 誰 | 做什麼 |
|------|-----|--------|
| 1 | Orchestrator | Pre-flight gate——不在 git repo / 沒 `gh` / 當前 branch 無 PR → 擋下、非 0 退出 |
| 2 | Orchestrator | 抓 inline review threads + review 摘要 + conversation comments |
| 3 | Orchestrator | 列出意見，使用者挑哪些要處理 |
| 4 | Orchestrator | 寫 `.maigo/pr-comments.md`，分組 work item + 提路由計畫，AskUserQuestion 確認 |
| 5 | (route) | 逐 work item 跑 `/maigo:quick` / `/maigo:go` / `/maigo:team` 的完整流程 |
| 6 | Orchestrator | finale——處理對照 + 回覆草稿（不送出）+ commit message 草稿 |

**路由原則：** 單檔機械性修正 → `quick`；跨檔 / 動行為 → `go`；大且低風險想省牆鐘 → `team`。**預設盡量走 `quick`**，不確定偏 `go`。

步驟 1–4 orchestrator 直跑（要跟使用者多輪互動）；步驟 5 才委派 agent 流程。**不碰 GitHub 寫入**——不回覆 comment、不 resolve thread、不 push，只產回覆草稿讓使用者自己貼。

## 場景對照

| 想做什麼 | 用哪個 |
|---------|--------|
| 小改動 / typo / 一行修正 | `/maigo:quick` |
| 加新 feature / 修 bug | `/maigo:go` |
| 同上但想省牆鐘時間 | `/maigo:team` |
| Review 同事的 PR | `/maigo:review <pr-url>` |
| 上線前最後一道把關自己的 branch | `/maigo:review` |
| Review 介面 / 設計層（不要求功能完成） | `/maigo:review --mode=design-preview <ref>` |
| Compliance audit（只看規範 / 安全） | `/maigo:review --mode=compliance-only <ref>` |
| 寫 PR title / description | `/maigo:describe-pr` |
| 處理 PR 上收到的 review 意見 | `/maigo:address-comments` |
| 環境壞了 / 第一次裝 | `/maigo:doctor` |
| 摸新專案 / onboarding | 直接呼叫 `Raana` |
| 重構評估（不實作） | `/maigo:go` 跑到燈寫完 plan 後喊停 |
| Security audit | `/maigo:review`，告訴 Soyo 重點看 unsafe pattern |
| 看現在記了什麼跨專案偏好 | `/maigo:memory` |
| Session 結束想沉澱學到的事 | `/maigo:retro` |
