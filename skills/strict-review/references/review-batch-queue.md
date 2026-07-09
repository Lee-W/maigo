# Strict Review — `/maigo:review` Multi-PR Batch & Queue Reference

Loaded on demand by [`commands/review.md`](https://github.com/Lee-W/maigo/blob/main/commands/review.md) —
full mechanics for the multi-PR batch path: how Raana sorts and prints the queue, the
per-PR status pre-processing table (merged / closed / draft), and the one-PR-at-a-time
gate between reviews. Read this file when `/maigo:review` receives more than one target.

---

`/maigo:review` 接受**多個** PR 用空白或逗號分隔。orchestrator 自動排序後一次一個 review；每完成一個 PR 等使用者 go-ahead 才推進。

## 樂奈先抓 metadata 排隊

第一輪 🐱 樂奈以 parallel 方式抓**每個 PR** 的 lightweight metadata（不抓 diff）：

```bash
gh pr view <N> --repo <repo> --json number,title,additions,deletions,state,isDraft,mergedAt,reviewDecision
```

排序規則：

按 `additions + deletions` **升序**——最少改動先看，一路由小到大。`reviewDecision` 不影響順序。

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

## 狀態前置處理（每 PR 進 §1 前）

| PR 狀態 | 處理 |
|---|---|
| `state == "MERGED"` 或 `mergedAt` 已設 | 不進流程，queue 上標 `⏭️ skipped (merged)`，**自動推進**到下一個 |
| `state == "CLOSED"` 未 merge | 同上，標 `⏭️ skipped (closed)` |
| `isDraft == true` | orchestrator 先問使用者「PR #N 是 draft，還是要看嗎？」`yes` → 走，`skip` → 跳下一個 |
| 其他 | 正常進入 §1 樂奈 stage |

merged / closed 的 PR **不需要** review report——只在 queue 表標 skipped 一行帶過。

## 一次一個 PR 規則

每個 PR 走完 §1-§4 出完一份 review report 後，orchestrator 在 report 結尾加一行：

```
Queue 還剩 **#Y**, **#Z** — 說 next（「好」/繼續/ok 都行）我再看下一個。
```

然後**停下來等使用者明確 go-ahead**。任何短肯定（`好` / `ok` / `next` / `下一個` / `繼續` / `go` / `yep`）都算。

- 使用者若給 substantive feedback（追問、要 re-read、pivot），先處理那個再推進
- 使用者說「全部一起看」/ `batch them` / `do them all` → 放掉這個 gate 直到 batch 結束
- 最後一個 PR 跑完 → queue 行改成最終 roll-up（見 `skills/strict-review/references/review-templates.md` 的「多 PR batch 最終 roll-up」）

## 持久 Work Board（跨 session 追蹤）

上面的 queue 是 **per-run、跑完即棄**。跨 session 追蹤已併入單一
[`skills/work-board`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md)：
`.maigo/board.md` 同時收 issue、你的 PR、在審的 PR，依 🎯 你的球 / ⏳ 等別人 /
✅ Merged-closed 分區。

review 特有 verdict 詞彙仍沿用本 skill：`BLOCKED` / `NEEDS_CHANGES` /
`APPROVE_WITH_NITS` / `APPROVE`，首次未審標 `待 review`。在 Work Board 裡，review
PR 的 Active / `↩︎ 回你的球` 對應 🎯，Off-board 對應 ⏳，merged / closed 對應 ✅。

舊 `.maigo/review-board.md` 的遷移規則、行文法、upsert 合約與 `--learn` checkbox
學習閘門全部見 `work-board` skill。刷新 / 查看 board 一律用 `/maigo:board`；
`/maigo:review` 不提供 board-only alias。
