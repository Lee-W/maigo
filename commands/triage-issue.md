---
description: 從 maintainer 視角批次 triage 進來的 GitHub issue——樂奈抓料、燈分類、爽世下 4 verdict（READY / NEEDS_INFO / DUP / CLOSE）、輸出 gh 指令草稿但不主動寫 GitHub。立希不上場。
---

<!-- mkdocs-include-start -->

# /maigo:triage-issue

> Maintainer 視角的 issue triage——大批 inbound issue 一輪掃完，告訴你哪些 ready / 哪些缺資訊 / 哪些是 dup / 哪些該 close。
> 跟 [`/maigo:review`](https://github.com/Lee-W/maigo/blob/main/commands/review.md) 的結構平行——只是對象從 PR diff 換成 issue body + comments，所以**立希不上場**（issue 沒 diff 可跑、沒 test 可驗）。

## 使用

```
/maigo:triage-issue <issue-1> <issue-2> ...   # 多 issue 批次（空白或逗號分隔）
/maigo:triage-issue <github-issue-url> ...    # 接受 URL 形式
```

不給參數 → 印錯誤訊息「`/maigo:triage-issue` 需要至少一條 issue 參數」並結束。
v1 不支援 `--label needs-triage` 之類自動拉清單的旗標——使用者顯式給 issue list。

## 流程

### 1. 樂奈 (Raana) — 抓 metadata + 排隊

第一輪 🐱 樂奈以 parallel 方式抓**每條 issue** 的 lightweight metadata：

```bash
gh issue view <N> --repo <repo> --json number,title,author,createdAt,state,labels,comments,body
```

排序規則（v1 簡單版）：

1. **Bucket A — closed / merged** → 自動 skip，標 `⏭️ already closed`
2. **Bucket B — open** → 按 `number` 升序（舊的先處理）

未來若有需要再加 `--quick-win-first` 旗標把疑似 dup / 缺 template 的擺前面。

排好後印 queue 表給使用者：

```markdown
## 排序後 triage queue（共 N 條）

| 順序 | Issue | Title | Author | Age | Labels |
|---|---|---|---|---|---|
| 1 | #X | … | @… | 3d | (none) |
| 2 | #Y | … | @… | 7d | bug |
| — | #W | … | — | — | ⏭️ skipped (closed) |

從 **#X** 開始。
```

第一條 issue **不必**等 go-ahead——使用者送多 issue 進來就授權批次啟動。「等 go-ahead」規則只在 issue 與 issue 之間。

### 2. 每條 issue — 樂奈 fetch full + 找 dup

🐱 樂奈進場第二輪，這條 issue 抓完整內容：

```bash
gh issue view <N> --comments                                           # body + comments
gh api repos/<owner>/<repo>/issues/<N>/timeline --paginate              # linked PRs / cross-references
```

並 grep repo 找潛在 dup：

- 從 issue title / body 抽 2-3 個關鍵字
- `gh search issues --repo <owner>/<repo> "<keyword>" --state all` 找近似 issue
- 限定回前 5 條最近的，避免噪音

回報：full body 摘要 + comments 摘要 + linked refs + 疑似 dup `#<N>` 清單（沒有則「(none found)」）。

### 3. 燈 (Tomori) — 寫 triage rubric 到 `.maigo/triage-rubric.md`

（目錄不存在請先 `mkdir -p .maigo`；同一批多條 issue 共用此檔，**每條覆寫**——爽世讀完即可，不需要長期保留。）

燈在 triage-issue 模式下的輸出結構見 [`agents/Tomori.md`](https://github.com/Lee-W/maigo/blob/main/agents/Tomori.md) 的「triage-issue 模式」段。重點：

- **Category 必填**，從 body 推導，**就算 issue 已經有 label 也照分**——這樣爽世才能 cross-check label 對不對
- **Why this category 必填**，引用 body 的具體片段（line / 段落），避免「感覺像 bug」這種無依據判斷
- Potential duplicates 抄樂奈第二步的結果

### 4. 爽世 (Soyo) — 套 strict-triage 給 verdict

依 [`skills/strict-triage`](https://github.com/Lee-W/maigo/blob/main/skills/strict-triage/SKILL.md) 操作：

- 預設 NEEDS_INFO，9 項 checklist 逐項標
- Verdict 4 值：READY / NEEDS_INFO / DUP / CLOSE
- Classification 段必印——複述燈的分類 + 跟 existing labels 對照（一致 / 不一致）
- 產草擬回覆 + gh 指令草稿（不執行）

skill 文件是 source of truth，本 command 不複述細節。

### 5. 印 per-issue report + 等使用者 next

把爽世輸出（verdict + classification + checklist + suggested labels + draft response + gh commands）原樣呈現給使用者。最末加一行：

```
Queue 還剩 **#Y**, **#Z** — 說 next（「好」/繼續/ok 都行）我再看下一條。
```

然後**停下來等使用者明確 go-ahead**。任何短肯定（`好` / `ok` / `next` / `下一條` / `繼續` / `go` / `yep`）都算。

- 使用者若給 substantive feedback（追問、要 re-read、改 verdict 的理由）→ 先處理那條再推進
- 使用者說「全部一起看」/ `batch them` / `do them all` → 放掉 gate 直到 batch 結束
- 最後一條跑完 → queue 行改成最終 roll-up（見下）

### 6. 整批結束 → roll-up

```markdown
## Triage batch summary（共 N 條）

- READY: **#A**, **#B**（建議 label：…）
- NEEDS_INFO: **#C**（缺：repro）、**#D**（缺：env）
- DUP: **#E** → #X
- CLOSE: **#F**（out of scope）
- Skipped: **#G**（already closed）

⚠️ 等使用者親自看：<列出 Soyo 連續 NEEDS_INFO 但 author 已多次回覆仍補不齊的條目；或分類強烈跟既有 label 衝突需要人類定奪的條目>
```

## 失敗處理

依 [`skills/failure-handling`](https://github.com/Lee-W/maigo/blob/main/skills/failure-handling/SKILL.md)——一樣 **2** 次 retry-limit 停下找使用者，但 triage 場景下：

- 「同條 must-fix」改判為「同條缺資訊」（爽世連 2 輪都標同一項 `[ ]` 缺）→ 停下，可能是 author 真的不知道怎麼補，需要 maintainer 親自介入

## Memory propose confirm flow

依 [`skills/memory-propose-confirm`](https://github.com/Lee-W/maigo/blob/main/skills/memory-propose-confirm/SKILL.md) 處理。Confirm flow 完成後繼續主線。triage 場景下，爽世可能因 maintainer 在 review 過程中明示「以後這種 issue 直接 close 不用問」這類偏好觸發 propose。

## Orchestrator 守則

- **旁白**：orchestrator 對使用者說話時戴上旁白的臉——開場、收場、卡關節點由 🌙 Doloris / 🌑 Mortis 旁白，依 [`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md)。
- **不能跳過燈**——沒有 rubric / 沒有 classification 的 triage 就是憑感覺
- **不能跳過樂奈**——沒抓完整 body + comments 就 triage 等於猜
- 爽世的 verdict 不因為「reporter 是長期貢獻者」放水
- **立希不啟動**——triage 沒驗證對象
- 你（orchestrator）不要自己 triage，每個 agent 都用 Task tool 啟動
- **不寫 GitHub**——不下 label、不 close、不 reply、不 assign；只產草稿。reply 草稿以「issue 連結 + 純內文 fenced code block」呈現（不用 `gh issue comment`）；label / close 仍用 `gh` 指令草稿（無純文字等價物）。
- draft response 與 gh 指令草稿呈現給使用者時，遵守 [`skills/copyable-deliverable`](https://github.com/Lee-W/maigo/blob/main/skills/copyable-deliverable/SKILL.md)——放單一 fenced code block 供複製。
- **不主動拉 issue 清單**——v1 只吃顯式 list
- 爽世的 triage 輸出若含 `## Memory propose`，把 per-issue report 完整呈現給使用者後再觸發 confirm flow

## 與其他命令的差異

| 項目 | `/maigo:review` | `/maigo:triage-issue` | `/maigo:address-comments` |
|------|-----------------|-----------------------|---------------------------|
| 輸入 | PR / branch / range | GitHub issue list | 當前 branch 的 PR 上的 review comments |
| 對象 | 程式碼變更 | issue body + comments | review 意見 |
| Soyo skill | `strict-review`（9 項 code） | `strict-triage`（9 項 issue） | 不上場 |
| 立希 | 跑 verify | 不上場 | 不上場（步驟 5 委派的 inner route 才跑） |
| 終態 | review 報告 | triage 報告 + gh 草稿 | 改動落地 + 回覆草稿 |
| 寫 GitHub | ❌ | ❌ | ❌（但會 commit code） |

→ 場景對照、其他命令：[Commands reference](https://github.com/Lee-W/maigo/blob/main/docs/reference/commands.md)
