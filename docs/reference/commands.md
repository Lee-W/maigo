# Commands Reference

Maigo 提供六個命令，所有命令的 source-of-truth 是 `commands/*.md`。
本頁是 quick reference。

## `/maigo:go` — 開發新功能 / 修 bug

順序版工作流，5 個 stage 全跑：

```
/maigo:go <任務描述>
```

| Stage | Agent | 做什麼 |
|-------|-------|--------|
| 1 | Raana | 探索 codebase 找相關位置、慣例 |
| 2 | Tomori | 寫 `/tmp/maigo/<repo>/plan.md` |
| 3 | (user) | 確認 plan、回 open questions |
| 4 | Anon | 按 plan 實作 |
| 5 | Soyo | review（依 `strict-review` skill） |
| 6 | Taki | 跑 test / lint / type check |

**失敗處理：** 任何 stage 卡關 → 回 Anon 修正。同條 must-fix / failure 連續 3 次卡關才停下。

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

## `/maigo:review` — Review 既有變更

Anon 不上場，只有 Raana → Tomori → Soyo → Taki：

```
/maigo:review https://github.com/org/repo/pull/123    # GitHub PR（需要 gh CLI）
/maigo:review feature/email-validation                 # 本地 branch（vs main）
/maigo:review HEAD~3..HEAD                             # commit range
/maigo:review                                          # 預設目前 branch vs main
```

| Stage | Agent | 做什麼 |
|-------|-------|--------|
| 1 | Raana | 抓 diff + 周邊 context（用 `gh pr view`、`gh pr diff` 或 `git diff`） |
| 2 | Tomori | **寫 `/tmp/maigo/<repo>/review-rubric.md`**（不是實作計畫，是 reviewer 對照基準） |
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
/maigo:memory convention  # 只列 convention type
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

## 場景對照

| 想做什麼 | 用哪個 |
|---------|--------|
| 加新 feature / 修 bug | `/maigo:go` |
| 同上但想省牆鐘時間 | `/maigo:team` |
| Review 同事的 PR | `/maigo:review <pr-url>` |
| 上線前最後一道把關自己的 branch | `/maigo:review` |
| 摸新專案 / onboarding | 直接呼叫 `Raana` |
| 重構評估（不實作） | `/maigo:go` 跑到燈寫完 plan 後喊停 |
| Security audit | `/maigo:review`，告訴 Soyo 重點看 unsafe pattern |
| 看現在記了什麼跨專案偏好 | `/maigo:memory` |
| Session 結束想沉澱學到的事 | `/maigo:retro` |
