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

## 持久 review board（跨 session 追蹤）

上面的 queue 是 **per-run、跑完即棄**。當使用者**長期**追一批 PR、跨多個 session 回來看時，
用一份**持久 board** 記住每顆 PR 的狀態，避免每次重排，也不會忘記哪些「你回過但作者又推了新東西」。

**board 檔**：預設 `.maigo/review-board.md`（跟 `review-rubric.md` 同目錄）。
repo 可透過 domain skill 或 memory（`type: project`）覆寫路徑——例如某 repo 慣例把產物放 `files/`。

### board section（固定順序）

| Section | 收錄條件 |
|---|---|
| `🔍 本批佇列` | 使用者這次帶進來要看的 PR。分「首次 review」「重看（指定 anchor）」兩子區。 |
| `Active` | 你在 GitHub 還沒回覆 / approve。verdict = 本地結論，尚未送出。 |
| `↩︎ 回你的球了` | 你回覆過，之後 PR 又有新活動（舊 verdict 過期，需重看）。標你回覆日 + 新活動日。 |
| `Off-board` | 你已回覆或 approve，且之後無新活動。 |
| `✅ Merged / closed` | 已 merged / closed，移出追蹤。標 merge 日。 |

行格式：`- #<PR> (<author>) [🔍] — **<verdict>** — <title>`，旁註放 DRAFT / 你自己的 PR / 指定 anchor（commit range、comment id）/ 他人 review decision。
verdict 詞彙沿用 SKILL.md：`BLOCKED` / `NEEDS_CHANGES` / `APPROVE_WITH_NITS` / `APPROVE`，首次未審標 `待 review`。

### 刷新 board（🐱 樂奈 stage 前置，或 `--refresh-board` 單獨跑）

對 board 上**每一顆** PR（不只本批）parallel 抓：

```bash
gh pr view <n> --repo <repo> --json state,isDraft,mergedAt,reviewDecision,updatedAt,reviews,comments
```

用 `gh api user`（`.login`）取「你」，自動 re-bucket：

| 條件 | 落點 |
|---|---|
| `mergedAt` 已設 / `state == CLOSED` | Merged / closed |
| 你（login）**沒有** review 或 comment | Active |
| 你回過，且**之後沒有**別人的 commit / comment / review | Off-board |
| 你回過，但**之後有**別人的活動 | ↩︎ 回你的球了 |

「回你的球了」是 board 的核心價值——ephemeral queue 給不了，因為它不記得你上次何時回的。
比對「你最後活動時間 vs 其他人最後活動時間」即可判定；merged / closed 一律優先。

### review 完回寫 board

`/maigo:review` 每跑完一顆 PR 出 report 後，orchestrator 更新 board 對應行：

- 記本地 verdict（尚未送 GitHub）→ 該顆進 / 留在 `Active`，標 verdict
- 若這次順手在 GitHub 回覆 / approve → 移到 `Off-board`
- merged / closed 的照上面的狀態前置處理移到底部

### `--refresh-board` 模式

`/maigo:review --refresh-board`（**不帶** PR 參數）→ 只刷新 board、重新分區、印出「該看的」（`Active` + `↩︎ 回你的球了`），**不**進 review 流程。
把印出來的 🔍 子集接著丟給 `/maigo:review <那些 PR>` 就能開審。分工：**board 決定「誰該看」→ review 負責「看」**。
