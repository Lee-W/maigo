# Commands Reference

Maigo 提供十五個命令，所有命令的 source-of-truth 是 `commands/*.md`。
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

檢查外部依賴（gh, python, git）、記憶層目錄、當前專案的 Taki (Verifier) 是否能正確跑起測試，
以及 retry / failure log 統計（`.maigo/soyo-must-fix.jsonl` / `.maigo/test-failures.jsonl`
各 key 觸發次數 + 最近 3 筆，read-only）。

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

Anon 不上場，Raana → Tomori → Soyo → Taki；report 後可從既有真人 review 學習慣例：

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
| 4.5 | Orchestrator | 裁決 gate——有 findings 才觸發，逐條表態；只有「不適用+理由」才寫記憶 |
| 5 | Orchestrator | 學習收尾——GitHub PR 有既有 review 才觸發，萃取慣例候選、使用者勾選後寫記憶 |

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

### 裁決校準（§4.5）與 input-not-waiver

report 後裁決 gate 讓使用者逐條表態：採納 / 駁回（一般）/ 標記本 repo 不適用 + 理由。
**只有「不適用+理由」才寫 type:project 記憶**（路徑：Soyo propose → confirm）——
純駁回不寫、採納不寫。

寫入的 entry 是 **review item 4 的 input，不是 waiver**：
不降 must-fix 門檻、不取代 9 項 checklist 任何一項。
依 `skills/strict-review` 的「Memory is input, not waiver」——「使用者標過不適用」不等於下次自動放行。

### 學習收尾（§5）與 `/maigo:address-comments` 的差異

| 項目 | `/maigo:review` §5 | `/maigo:address-comments` §7 |
|------|---------------------|-------------------------------|
| 意見來源 | PR 上既有真人 review | 此次處理的 comments |
| 有無實作 | 沒有（只讀 GitHub） | 有——逐項走 quick / go / team |
| 抓取時機 | review 完後 | address-comments 全流程後 |
| 路徑 | reuse remember 5+6 | reuse remember 5+6 |

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

## `/maigo:board` — 跨 session Work Board

把 issue、自己的 PR、正在 review 的 PR 放進同一份 `.maigo/board.md`，依球權分成
🎯 你的球 / ⏳ 等別人 / ✅ Merged-closed，並重生 `.maigo/board.html` 給瀏覽器閱讀。

```
/maigo:board <targets...>   # 混貼 issue/PR 編號或 URL；入板後刷新
/maigo:board                # 刷新全板、只印 🎯 + 計數
/maigo:board --all          # 印整板
/maigo:board --learn        # 盤點已勾但未 🧠 的項目
/maigo:board --drop <n...>  # 不追了，移除行
```

board 只決定「下一步誰該動」；實際 review、triage、take issue、address comments
仍交給各自命令。行文法、球權判定、回寫合約與舊 `.maigo/review-board.md` 遷移規則見
[work-board skill](../skills/work-board.md)。

## `/maigo:crystallize` — 把成熟的記憶條目畢業成 skill

記憶層是扁平、relevance-ranked、capped 10 筆的事實儲存；有些條目其實是「反覆出現的慣例 / workflow」，塞在 memory 裡只被當事實載入、相關條目一多還會被擠出前 10 筆。`/maigo:crystallize` 把這類條目**畢業**成常駐 skill——trigger 命中就一定在 context、結構化、可被 command / agent 引用。

```
/maigo:crystallize    # 無參數，掃整個記憶層找畢業候選
```

| 步驟 | 誰 | 做什麼 |
|------|-----|--------|
| 1 | Orchestrator | 全讀記憶層（不做 relevance 排序），掃畢業候選 |
| 2 | Orchestrator | 套 criteria 挑候選：convention 形狀 + 有明確 consumer + 反覆性 signal |
| 3 | Orchestrator | 世界觀隔離 gate——maigo 記憶不畢業進 mujica skill |
| 4 | Orchestrator | **逐筆** propose，AskUserQuestion（新建 / 併進 / 修改 / 跳過 / 結束），確認的記進批次清單 |
| 5 | 🎀 愛音 + 🟡 爽世 | manifest 一次委派：愛音照 Add New Skill Checklist 批次寫 skill + 跑 validator + mkdocs strict，爽世輕量 review（quick 模式） |
| 6 | Orchestrator | skill side 綠後退役來源記憶（刪 entry / 降級指針）|

**分工**：互動的挑候選 / propose / confirm / 退役記憶留 orchestrator；「寫 SKILL.md + shim + mkdocs + catalog + 驗證」這段該被 review、被 verify 的 code change **委派 🎀 愛音**（走 `/maigo:quick` 輕量模式），**批次**委派、一次 spawn 不 per-entry——攤平冷啟動 token 成本。

**atomic：skill side 驗證綠才動記憶層**——skill 沒寫成就退役會讓知識消失。寫 skill 細節指向 repo 的 [Add New Skill Checklist](skills.md#add-new-skill-checklist)，退役記憶指向 `/maigo:remember` 步驟 6，本命令不重複 spec。

**跟 retro 的關係**：retro 把 session 學到的事**寫進** memory（餵養）；crystallize 把 memory 裡夠成熟的條目**升階成** skill（收割）。

→ [Add New Skill Checklist](skills.md#add-new-skill-checklist)

→ [/maigo:remember](../commands/remember.md)

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
| 7 | Orchestrator | 學習收尾——萃取 convention 形狀 comment → 確認 → 寫 type:project 記憶 |

**路由原則：** 單檔機械性修正 → `quick`；跨檔 / 動行為 → `go`；大且低風險想省牆鐘 → `team`。**預設盡量走 `quick`**，不確定偏 `go`。

步驟 1–4 orchestrator 直跑（要跟使用者多輪互動）；步驟 5 才委派 agent 流程；步驟 7 也是 orchestrator 直跑，會（經使用者確認後）寫 `~/.config/maigo/memory/`。**不碰 GitHub 寫入**——不回覆 comment、不 resolve thread、不 push，只產回覆草稿讓使用者自己貼。

## `/maigo:triage-issue` — 批次 triage GitHub issue

從 maintainer 視角批次掃 inbound issue：🐱 樂奈抓 metadata、🩵 燈寫 triage rubric、🟡 爽世下 verdict（READY / NEEDS_INFO / DUP / CLOSE），輸出 `gh` 指令草稿但不主動寫 GitHub。🟣 立希不上場（issue 沒 diff 可跑）。

```
/maigo:triage-issue <issue-1> <issue-2> ...   # 多 issue 批次（空白或逗號分隔）
/maigo:triage-issue <github-issue-url> ...    # 接受 URL 形式
```

| 步驟 | 誰 | 做什麼 |
|------|-----|--------|
| 1 | 🐱 樂奈 | 抓每條 issue 的 lightweight metadata，排 triage queue |
| 2 | 🐱 樂奈 | 每條 issue 抓完整 body + comments + 找潛在 dup |
| 3 | 🩵 燈 | 寫 `.maigo/triage-rubric.md`（category + why + potential dup） |
| 4 | 🟡 爽世 | 套 `strict-triage` skill，下 verdict + 產 `gh` 草稿 |
| 5 | Orchestrator | 呈現 per-issue 報告，等使用者 next |
| 6 | Orchestrator | 整批結束後輸出 roll-up summary |

**read-only，不寫 GitHub**——不下 label、不 close、不 reply、不 assign；只產草稿讓使用者自己執行。

→ Source: [`commands/triage-issue.md`](../commands/triage-issue.md)

## `/maigo:take-issue` — 把 READY issue 接進實作

接住 `/maigo:triage-issue` 判定 READY 之後斷掉的那一段：orchestrator 前置抓 issue
body/comments，萃取 acceptance criteria，交給標準 teammate-flow（🐱 樂奈探索 → 🩵 燈寫
plan，須引用 issue 編號與 acceptance criteria → 🎀 愛音實作 → 🟡 爽世 review → 🟣 立希驗證）。

```
/maigo:take-issue <issue 編號或 URL>
```

| 步驟 | 誰 | 做什麼 |
|------|-----|--------|
| 1 | Orchestrator | `gh issue view` 抓 body/comments，萃取需求敘述；不是 READY 形狀就建議先 triage |
| 2-6 | teammate-flow | 依 [`skills/teammate-flow`](../skills/teammate-flow.md) 標準五段 |
| 7 | Orchestrator | 草擬帶 issue 參照的 commit，不自動 push / 開 PR |

→ Source: [`commands/take-issue.md`](../commands/take-issue.md)

## `/maigo:repo-audit` — repo 自身內部健診

read-only 掃描 repo 積壓狀態：已合併可刪的 branch、未關 PR、程式碼 TODO/FIXME、
skill 健診（孤兒 / 重疊候選 / 指向失效）。
Orchestrator 直跑（不 delegate 五人），輸出可複製的處置 checklist，不執行任何寫入。
🌑 Mortis 一句結算。

```
/maigo:repo-audit
```

| 資料源 | 指令 | 行動 |
|--------|------|------|
| 已合併可刪的 branch | `git branch --merged main` | 列出，不刪除 |
| 未關 PR | `gh pr list --state open` | 列出，不關閉（`gh` 缺則跳過） |
| TODO / FIXME 積壓 | `grep -rn -E "TODO\|FIXME"` | 列出，不修改 |
| Skill 健診（孤兒 / 重疊 / 指向失效） | 讀 `skills/*/SKILL.md` + grep | 列出，不合併、不刪除 |

**與 doctor / triage-issue 的差異**：
`/maigo:doctor` 診斷的是**環境依賴**（gh, git, python 是否可用）；
`/maigo:triage-issue` 處理的是 **inbound GitHub issue**（maintainer 視角的 triage）；
`/maigo:repo-audit` 關注的是 **repo 自身的積壓**（branch / PR / TODO 清理）。

→ Source: [`commands/repo-audit.md`](../commands/repo-audit.md)

## 場景對照

| 想做什麼 | 用哪個 |
|---------|--------|
| 小改動 / typo / 一行修正 | `/maigo:quick` |
| 加新 feature / 修 bug | `/maigo:go` |
| 同上但想省牆鐘時間 | `/maigo:team` |
| Review 同事的 PR | `/maigo:review <pr-url>` |
| 看目前哪些 issue / PR 輪到自己處理 | `/maigo:board` |
| 上線前最後一道把關自己的 branch | `/maigo:review` |
| Review 介面 / 設計層（不要求功能完成） | `/maigo:review --mode=design-preview <ref>` |
| Compliance audit（只看規範 / 安全） | `/maigo:review --mode=compliance-only <ref>` |
| 寫 PR title / description | `/maigo:describe-pr` |
| 處理 PR 上收到的 review 意見 | `/maigo:address-comments` |
| 批次分類 / 標記 GitHub issue | `/maigo:triage-issue` |
| 把 triage 判定 READY 的 issue 接進實作 | `/maigo:take-issue` |
| 定期清 repo（已合併 branch / 未關 PR / TODO 積壓 / skill 健診） | `/maigo:repo-audit` |
| 環境壞了 / 第一次裝 | `/maigo:doctor` |
| 摸新專案 / onboarding | 直接呼叫 `Raana` |
| 重構評估（不實作） | `/maigo:go` 跑到燈寫完 plan 後喊停 |
| Security audit | `/maigo:review`，告訴 Soyo 重點看 unsafe pattern |
| 看現在記了什麼跨專案偏好 | `/maigo:memory` |
| Session 結束想沉澱學到的事 | `/maigo:retro` |
| 記憶裡某條慣例反覆出現，想升階成常駐 skill | `/maigo:crystallize` |
