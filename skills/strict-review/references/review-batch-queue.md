# Strict Review — `/maigo:review` Multi-PR Batch & Queue Reference

Loaded on demand by [`commands/review.md`](https://github.com/Lee-W/maigo/blob/main/commands/review.md) —
full mechanics for the multi-PR batch path: how Raana sorts and prints the queue, the
per-PR status pre-processing table (merged / closed / draft), the default
run-them-all-in-parallel flow, and the opt-in one-at-a-time gate. Read this file when `/maigo:review` receives more than one target.

---

`/maigo:review` 接受**多個** PR 用空白或逗號分隔。orchestrator 自動排序後**預設一次平行審完全部**，不在 PR 與 PR 之間等 go-ahead；使用者明講要逐顆才改成一次一個、每顆等 go-ahead（見「逐顆模式」）。

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

共 N 顆，平行開跑（排序只決定 roll-up 與 board 的呈現順序）。
```

使用者送多 PR 進來就已經授權整批啟動——**不需要**任何 go-ahead，PR 與 PR 之間也不停。

## 狀態前置處理（每 PR 進 §1 前）

| PR 狀態 | 處理 |
|---|---|
| `state == "MERGED"` 或 `mergedAt` 已設 | 不進流程，queue 上標 `⏭️ skipped (merged)`，**自動推進**到下一個 |
| `state == "CLOSED"` 未 merge | 同上，標 `⏭️ skipped (closed)` |
| `isDraft == true` | orchestrator 先問使用者「PR #N 是 draft，還是要看嗎？」`yes` → 走，`skip` → 跳下一個 |
| 其他 | 正常進入 §1 樂奈 stage |

merged / closed 的 PR **不需要** review report——只在 queue 表標 skipped 一行帶過。

## 預設：平行審完全部、統一 publish、board 放最前

多 PR 參數的預設流程（不必使用者另外交代）：

1. **先排隊、再一次 fetch**：樂奈 metadata 排好 queue、前置處理表過完後，orchestrator
   **一次**把所有要審的 PR head fetch 成具名本機 ref（`+pull/<N>/head:refs/review/pr-<N>-latest`，
   不用 `FETCH_HEAD`，fetch 後對 `headRefOid`——細節見下方「大批平行 spawn」一節的 fetch 規則）。
   各 agent 不各自 fetch，避免搶 fetch 與讀到別顆的 head。
2. **平行審**：🟡 爽世唯讀，並行度不受下面這條上限；🟣 立希每顆各自一個**獨立 worktree**（Airflow
   另要各自 fresh `AIRFLOW_HOME`，見下方一節），但**同時存在的 worktree 最多 2–3 個**（與
   [`teammate-flow` 的「Worktree safety in parallel batch review」](https://github.com/Lee-W/maigo/blob/main/skills/teammate-flow/SKILL.md)
   同一個數字——曾經約 10 個並行 worktree 耗盡硬碟、整個 verify 階段掛掉兩次），開之前先查剩餘磁碟
   （每個約 2GB 以上），超過上限的 PR 排隊等前面的立希收工、worktree 移除後再開。並行度另照下方
   「節流」縮波次，每波一完成就落地。
3. **全部跑完才統一收尾**：每顆審完只產出並發佈 report（本地 report；貼上 GitHub 仍是使用者的動作，
   「交付時效」那節不變：裁決集中問一次，但每份 report 一產出本地就可讀、可先貼，使用者不必等整批
   問完；見「交付時效」）；must-fix 放不放、nit 怎麼送，**全部審完後集中問一次**（收尾用
   AskUserQuestion，每次最多 4 題、分輪問完；每題推薦項放第一個，選項寫清楚 must-fix 與 nit 各自
   怎麼處理）；草稿與 board 回寫等裁決之後一次做。例外：某顆有「使用者必須先決定才不會白做」的
   前提（例如範圍需要改審）才提前問。draft PR 仍照前置處理表先問。
4. **board 單一寫手**：Work Board 由**單一** agent 以 `Edit` 回寫（不要每顆各寫一次、也不整份
   覆寫；規則見 `skills/work-board`），這批 PR 的行放 🎯 最前面。
5. 最後走 roll-up（見 `skills/strict-review/references/review-templates.md` 的「多 PR batch 最終 roll-up」）。

Why：一次五顆 PR 照舊預設審完第一顆就停下等 go-ahead，使用者的回應是「一次看完，都寫 board，
放到最前面」——逐顆停頓只是把等待成本丟給使用者，而且 report 版型一樣、沒有節省判斷。

## 逐顆模式（使用者明講才用）

只有使用者明確要求逐顆（「一顆一顆來」、`one at a time`、「先看第一顆」之類）才走這個模式；
同一 session 內以使用者**最新**的指示為準。

每個 PR 走完 §1-§4 出完一份 review report 後，orchestrator 在 report 結尾加一行：

```
Queue 還剩 **#Y**, **#Z** — 說 next（「好」/繼續/ok 都行）我再看下一個。
```

然後**停下來等使用者明確 go-ahead**。任何短肯定（`好` / `ok` / `next` / `下一個` / `繼續` / `go` / `yep`）都算。

- 使用者若給 substantive feedback（追問、要 re-read、pivot），先處理那個再推進
- 使用者中途說「全部一起看」/ `batch them` / `do them all` → 回到上面的預設流程，放掉這個 gate
  直到 batch 結束（裁決同樣集中到最後問一次）
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
- 平行派出的 agent 若會跑目標 repo 的測試套件，每隻要各自隔離可寫的共享狀態，不要共用
  同一份——Airflow 是每隻各自一個 fresh `AIRFLOW_HOME`，且要寫進交辦 prompt，不能只交給
  agent 自行判斷；**在同一個 Bash 呼叫裡**把測試指令整段接在
  `env AIRFLOW_HOME=<fresh-dir> uv run ...` 後面，不要拆成 `export` 一行 ＋ 跑測試另一行
  （Bash tool 不跨呼叫保留 shell state，`export` 會在下一次呼叫消失，退回共用的
  `~/airflow`）；根因與其他症狀見
  [`airflow-aware` 的「Every worktree shares one sqlite test DB」一節](https://github.com/Lee-W/maigo/blob/main/skills/airflow-aware/references/verification-tooling.md)。

- 平行派出的 agent 若對同一個 repo 跑 `git fetch`，**一律 fetch 到具名 ref**（例如
  `git fetch <remote> +pull/<N>/head:refs/review/pr-<N>-latest`），或直接用裸 SHA，交辦 prompt 裡要寫明
  「不要用 `FETCH_HEAD`」。**refspec 開頭要有 `+`**：重審時早先 session 留下的同名 ref 已存在，
  沒有 `+` 會被 `! [rejected] (non-fast-forward)` 拒絕、ref 靜默留在舊 head，後面的 worktree 與
  所有派工就對著舊 head 審（實例：重審時 `review-pr-<N>` 仍指著舊 head，PR 實際 head 早已前進）。fetch 後一律拿 `git rev-parse <ref>` 與
  `gh pr view <N> --json headRefOid` 比對，不一致就停下重抓。`FETCH_HEAD` 是整個 repo 共用的單一檔案，後跑的 fetch 會覆寫先跑的，
  讀到的可能是別隻 agent 的 PR。實例（2026-10-01）：一隻探索 agent 拿 `git diff main FETCH_HEAD`
  看到另一顆 PR 的 snowflake 改動，就誤判成「main 在 session 中途被 fast-forward」；查 `git reflog`
  才確認 main 根本沒動。

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

Work Board 的 `--reviews` 檢視只列當下待看 PR；使用者讀完最新 report 後可用
`/maigo:board --reviewed <n>` 或在 board 勾 `[x]` 標記本地已看完，不等同送出 GitHub。
每顆 report 都由共同 publisher 產生檔頭與最後 review 時間；batch roll-up 不覆蓋單顆報告。
