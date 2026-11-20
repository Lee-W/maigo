# Work Board — 型別偵測與球權判定（§2）

Loaded on demand by [`skills/work-board/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md) §2 — 型別偵測、刷新抓的欄位、三張球權判定表。
本檔內文原樣自 SKILL.md 搬出，章節編號（§1a、§3a 等）沿用原編號，SKILL.md 內仍以這些編號互相引用。

### 型別偵測（加 item 時跑一次）

1. URL → 直接解析 owner/repo + 型別 + 編號
2. 裸編號 → `gh api repos/<owner>/<repo>/issues/<n>`，有 `pull_request` key ＝ PR
3. PR 再看 `author.login` 是否等於 `gh api user --jq .login` → 🔀 vs 👀
4. `gh` 抓不到 → 狀態詞 `抓不到`（P0，orchestrator 指派），併進 🎯（🐛／🔀）或 👀（別人的 PR）最上面，附錯誤末行

### 刷新時抓的欄位

```bash
# issue
gh issue view <n> --repo <r> --json title,state,stateReason,assignees,author,comments,createdAt,updatedAt,labels,closedByPullRequestsReferences
# PR（自己的與在審的同一組）
gh pr view <n> --repo <r> --json title,state,isDraft,mergedAt,mergeable,reviewDecision,createdAt,updatedAt,headRefOid,headRefName,commits,reviews,comments,author,statusCheckRollup,additions,deletions
```

「你」＝ `gh api user --jq .login`（沿用 review board 既有做法）。
「你最後活動 vs 他人最後活動」的比對邏輯：把 comments + reviews 的 author + 時間戳整理成
`gh_meta`，交給 [`scripts/board_state.py`](https://github.com/Lee-W/maigo/blob/main/scripts/board_state.py)
的 `classify()` 純函式比較——這是這次重構後的**判定邏輯正典**，本節三張表只是它的人類可讀
鏡像，兩者不一致以程式為準（`tests/test_board_state.py` 逐條守）。

呼叫方式（薄 CLI，stdin 餵 JSON 陣列 `[{type, gh_meta, prior_status}]`）：

```bash
echo '[{"type": "🐛", "gh_meta": {"state": "OPEN"}, "prior_status": null}]' \
  | python3 "${CLAUDE_PLUGIN_ROOT}/scripts/board_state.py" --you <login>
```

`mergeable` 欄位可能回 `CONFLICTING` / `MERGEABLE` / `UNKNOWN`（GitHub 尚在計算）；
`classify()` 只在明確 `CONFLICTING` 時判定衝突，`UNKNOWN` fallthrough 到其他規則，不誤判。

### 球權判定表（merged / closed 一律優先 → ✅；由上往下第一個命中）

**🐛 issue**：

| 條件 | 狀態 | section | rank |
|---|---|---|---|
| `state == CLOSED` | `closed`（stateReason / linked PR 併入旁註） | ✅ | P9 |
| prior 為 `DUP` / `CLOSE` | 保留該 verdict | ✅ | P9 |
| board 無 verdict（剛加入、從未 triage） | `待 triage` → `/maigo:triage-issue <n>` | 🎯 | P6 |
| prior `READY` 且無 assignee（或 assignee 是你） | `READY` → `/maigo:take-issue <n>` | 🎯 | P7 |
| 已 take（prior `IN_PROGRESS`） | `IN_PROGRESS`（旁註 branch 名） | 🎯 | P5 |
| 你最後活動後有別人新 comment | `有新回覆` → `/maigo:triage-issue <n>`（重判） | 🎯 | P2 |
| prior `NEEDS_INFO` 或你留言後無新活動 | `NEEDS_INFO` | ⏳ | P8 |

**🔀 你的 PR**（每次刷新純由 gh metadata 重算，不看 prior_status）：

| 條件 | 狀態 | section | rank |
|---|---|---|---|
| merged / closed | `merged` / `closed` | ✅ | P9 |
| `isDraft == true` | `WIP`（自己 draft＝還在寫） | 🎯 | P5 |
| `mergeable == CONFLICTING` | `有衝突` → `/maigo:address-comments` | 🎯 | P1 |
| `statusCheckRollup` 有 FAILURE | `CI 紅` → `gh pr checks <n>` | 🎯 | P1 |
| `reviewDecision == CHANGES_REQUESTED` | `CHANGES_REQUESTED` → `/maigo:address-comments` | 🎯 | P1 |
| 你最後 push/comment 後有別人 review/comment | `有新 comment` → `/maigo:address-comments` | 🎯 | P2 |
| `reviewDecision == APPROVED` 且 CI 綠 | `可合併` → `gh pr merge <n>` | 🎯 | P3 |
| `statusCheckRollup` 有 PENDING（其餘正常） | `CI 等待` | ⏳ | P8 |
| 其他（最後活動是你） | `等 review` | ⏳ | P8 |

**👀 在審的 PR**：

| 條件 | 狀態 | section | rank |
|---|---|---|---|
| merged / closed | `merged` / `closed` | ✅ | P9 |
| `isDraft == true` | `他人草稿` | ⏳ | P8 |
| report 的 head 與目前 head 不同，或最後 review／已看完／送出後有新 commit、作者留言 | `↩︎ 回你的球` → `/maigo:review <n>` | 👀 | P2 |
| 使用者明確 `--reviewed` 本版 report，之後無新活動 | `已看完`；本地確認，不代表送出 GitHub | ⏳ | P8 |
| 有本地 report / verdict，尚未確認且沒有這輪送出的 GitHub review | `待送出`；先看 report，再決定送出或 `--reviewed` | 👀 | P1 |
| GitHub 已送出這輪 review，且無新活動 | 本地 verdict（若有）；否則 `已看完` | ⏳ | P8 |
| 沒有本地 report 或已送出 review | `待 review` → `/maigo:review <n>` | 👀 | P4 |

`board_state.py --maigo-root <repo-root>` 讀 report 的明確時間與 head；舊報告才退回 mtime。
`待送出` 的下一步：`.maigo/review/<id>/draft.md` 存在才給 `gh pr review --body-file` 指令，不存在時
改為「尚無草稿：先起草 …（§4.5 裁決 gate）」——否則使用者照 board 跑指令會因檔案不存在而失敗
（2026-10 batch 有 5 顆 `待送出` 指向沒起草的 draft.md）。沒給 `--maigo-root` 時無從判斷，維持給指令。
「這輪已送出」以你的 GitHub review 的 `commit_id` 等於 report 的 `head_sha`、或 `submitted_at` 晚於 report 的 `reviewed_at` 為準；
只看「這顆 PR 上有沒有你的 review」會把前一輪的 review 誤判成本地草稿已送——手動盤點（例如批次整理草稿前挑出未送清單）同樣適用
（2026-11-12 實例：#73748、#76221、#75499 的已送 review 都是 11-02 舊 commit 的前一輪，本地 follow-up 草稿其實未送，卻被當成已送而跳過）。
`PENDING` / `DISMISSED` 的 GitHub review 不算已送出。`--reviews` 檢視只列 `needs_review`
為 true 的項目：待 review、回你的球、待送出，依 rank 排序；**這個過濾結果不得拿去重寫
完整 board**。索引顯示標題與貢獻者；最後 review／已看完時間在細節與對話待看清單中顯示。

review verdict 詞彙沿用 [`strict-review`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md)；
per-PR queue 排序 / 前置處理（merged / closed / draft 自動 skip 或問使用者）另見
[`review-batch-queue.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/review-batch-queue.md)，
那份文件管的是 **per-run 排隊**，跟本表管的**跨 session 落點**是兩件事。


### Review thread 解決狀態

完整刷新（含 `--all`）另外用 GitHub GraphQL 分頁抓完 `reviewThreads` 與 comments，以 `isResolved` 判定是否已解決；不把 outdated 當成 resolved。細節檔事實區顯示「Review 討論：未解決 N ｜ 已解決 M」。未解決 thread 的留言納入球權判定，已解決的留言不再觸發待處理；空白內文的 `COMMENTED` review 若對應的 threads 全部已解決，也不再觸發「有新 comment」。有內文的 review、正式 `CHANGES_REQUESTED`、一般 PR 留言與新 commit 仍依原規則判定。抓取失敗或不完整不當成零筆，保留舊資料並回報錯誤；不修改本地 review 報告、判斷或筆記。
