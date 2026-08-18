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

## 交付時效

review 報告寫得多完整都不算交付——**貼上 GitHub 才算**。apache/airflow 的 merge 速度
常快過一輪「深審 → 覆核 → 依新意見改草稿」的循環，窗口關掉的成本不是「晚一點貼」，是
**歸零**（帶著缺陷 merged 之後只剩開 issue 這條較弱的路，且要重新查證缺陷仍在 main 上）。

- **一顆審完就貼**，不要累積成批等「一起送」。
- **先貼粗版再補**：must-fix ＋ 一句證據就夠，nit 可後續補留言。完美措辭的邊際價值遠低於
  時效。
- **審之前先查 PR state**：`gh pr view <n> --json state,mergedAt,headRefOid`。避免審
  已 merged 的 PR，也避免審過期的 head。
- 若同一 PR 上已有其他人提出同樣的點，**改成接話而非重述**，否則就是 reviewer noise。

實證：一次 session 產出 28 份草稿、一份都沒送出，其間有 PR 帶著未送出的 must-fix
merged（例如 CLI 每次呼叫都分頁抓完整歷史、reject 路徑零測試），也有一份三輪修訂磨到
很完整，貼之前重查 head 才發現三個發現全部被別人先提且作者已修，整份作廢。**把案例精簡
成 2–3 個代表性 PR 講清楚後果就夠，不必逐條記過。**

送 review 是掛使用者帳號對外發言，agent 不代送——這條的可執行部分是 agent 側的：主動
催、先給可直接複製的版本、不主動累積庫存，而非替使用者按下送出。

## 大批平行 spawn：節流與進度落地

大批平行 spawn subagent 的任務（例如一次 batch review 幾十個 PR）會反覆撞 session
limit——單一 session 內可能撞多次不同重置點，每次都有整批在飛的 agent 被砍、需重跑。
平行度開太大時，額度在少數幾波內就燒完；被砍的 agent 若結果沒落地，重跑等於白做。

**How to apply**：

- 縮小每波並行度（撞過就再縮，5-6 個仍可能撞）。
- **每波一完成就把結果落地到持久檔**（如 `.maigo/board.md` 或 project memory），不要
  等整批跑完才寫——撞限額時已完成的部分不丟。
- spawn 前先想好「這波若中途死，重跑的入口在哪」，把待辦與已完成狀態都寫進持久檔。

## 持久 Work Board（跨 session 追蹤）

上面的 queue 是 **per-run、跑完即棄**。跨 session 追蹤已併入單一
[`skills/work-board`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md)：
`.maigo/board.md` 同時收 issue、你的 PR、在審的 PR，依單一優先序排名分進 🎯 下一件 /
⏳ 等別人 / ✅ 最近結案三個 section。

review 特有 verdict 詞彙仍沿用本 skill：`BLOCKED` / `NEEDS_CHANGES` /
`APPROVE_WITH_NITS` / `APPROVE`，首次未審標 `待 review`；本地 verdict 尚未送 GitHub 標
`待送出`。在 Work Board 裡（判定邏輯正典見
[`scripts/board_state.py`](https://github.com/Lee-W/maigo/blob/main/scripts/board_state.py)）：
`待 review`（從未 review）、`待送出`（verdict 未送出）與 `↩︎ 回你的球`（你 review 後
author 有新活動）對應 🎯 下一件；verdict 已下且無新 author 活動（`BLOCKED` /
`NEEDS_CHANGES` / `APPROVE_WITH_NITS` / `APPROVE` 原樣保留）與 `他人草稿` 對應 ⏳ 等別人；
merged / closed 對應 ✅ 最近結案。

舊 `.maigo/review-board.md` 的遷移規則、行文法、upsert 合約與 `--learn` checkbox
學習閘門全部見 `work-board` skill。刷新 / 查看 board 一律用 `/maigo:board`；
`/maigo:review` 不提供 board-only alias。
