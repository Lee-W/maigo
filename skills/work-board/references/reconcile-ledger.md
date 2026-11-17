# Work Board — 對帳、discovery 與排除紀錄（§3a 後半）

Loaded on demand by [`skills/work-board/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md) §3a — 機器狀態檔、dd 排除、復活、discovery、ack 與學習訊號。
本檔內文原樣自 SKILL.md 搬出，章節編號（§1a、§3a 等）沿用原編號，SKILL.md 內仍以這些編號互相引用。

**機器狀態檔**——只有 script 寫，都在 `.maigo/_internal/board/`（script 自行建立目錄；
`plan --dry-run` 與 `refresh` 預覽不建目錄、不寫檔；型錄與 doctor 永遠不列 `_internal/`）：

| 檔案 | 格式 | 寫法 | 用途 |
|---|---|---|---|
| `dropped.jsonl` | 每行 `{"url","event":"drop"\|"revive","reason","at"}` | 單次 append 一行，只增不改 | 持久排除紀錄；以 canonical URL（`(owner, repo, number)` 小寫，`pull`/`issues` 同一項）為 key，依事件順序 fold，最後一筆決定狀態 |
| `snapshot.json` | `{"version":1,"written_at","items":{<url>:{"checked","detail"}}}` | tempfile ＋ replace 原子寫入 | 上次刷新結束時 board 上有哪些項目與勾選狀態，用來偵測 `dd` 與勾選變化 |
| `backup/<UTC ts>/` | 與 board.md 相同的目錄結構（`board.md`、`i/*.md`） | `refresh --apply` 寫回前複製要改／刪的檔，只留最新 10 份 | 寫入失敗時還原；也是誤刪細節檔後的救援來源 |

**`dd` → 排除**：`removed = (snapshot 的 URL ∪ 孤兒 i/ 檔的 URL) − board 現有行 − 已排除`，成立就
append `{"event":"drop","reason":"dd"}`。第一次跑（沒有 snapshot）時既有的孤兒 i/ 檔一律視為 `dd`，
並在輸出列出清單。排除項目：discovery 與 artifact 對帳都跳過；仍留在 board 上的排除項目（`已放棄`
的行）標 `excluded: true`，orchestrator 不重新分類。`--drop` / 老化 / 已結案的 artifact 補行也寫入
排除紀錄（`reason` 分別是 `drop` / `aged` / `closed`）。

**重新指名 → 復活**：要同時滿足 (1) URL 出現在本輪 `user-review-requested:@me` 結果；(2) timeline 有
`review_requested` 事件、`requested_reviewer.login` 是你，且 `created_at` 晚於最後一次 drop 的時間。
抓取 timeline 失敗時 fail-closed：維持排除並列進 `errors`。使用者明確把被排除的項目重新加進 board
（`/maigo:board <targets>`）時，先跑 `board_sync.py revive --reason manual <url...>`，只對目前被排除的
key 寫 `revive` 事件。`dd` 事件的時間記為 snapshot 的 `written_at`（沒有 snapshot 才用現在），所以
「刪行後、刷新前」被重新指名的 PR 仍會復活。

**fail-closed**：board.md 壞掉的行（含 `i/*.md` 路徑但解析失敗）不當成 `dd`，列進 `errors`；
snapshot 有項目但 board.md 不存在或沒有任何項目行時略過整個 `dd` 判定。

**已知限制**：ack 的 `acknowledged_at` 是刷新當下，不是勾選當下；第一次跑（沒有 snapshot）時，
已勾的 👀 行會以推斷模式補 ack。

**對帳 `.maigo/` 產物**（建在 `maigo_dir_catalog.scan()` 之上）：`review/<id>/review.md` 的 metadata
`source`（GitHub PR URL，可跨 repo）、舊扁平 `review-<id>.md` 的 `**PR:**` 行、以及純數字 id 的
`review/<n>/*` / `issue/<n>/*`（推導成 board repo 的 URL）是可靠對應，會補進 board；
頂層 `plan-*`、`topic/<slug>/plan.md`、舊固定檔名、`unregistered` 的 `.md`、metadata `source` 不是 URL 的本地 review、
`<repo>-<n>` 形式的 id 沒有可靠對應，只列入 `unattributed`。孤兒 i/ 檔是 `dd` 訊號，不是補行來源。

**Discovery**：在 board repo 跑兩次 `gh search prs --state open`（`user-review-requested:@me`、
`--reviewed-by @me` 加 `-author:@me`），依 key 合併；bot PR 照常收；作者是你本人的項目給 `🔀` 提示。
**筆數**：`--max-new`（預設 50）限制單次新增的項目數，排序「被指名 → 審過 → artifact」，同類內
`updatedAt` 由舊到新；超過的放進 `overflow`，在對話列出、下次刷新接著補。結果數等於 `gh search` 的
`--limit 200` 時在 `errors` 註明「可能截斷」。

**`[x]` 與 ack**：snapshot 的 `checked` 與現檔比對，`[ ]→[x]` 記 `checked`、`[x]→[ ]` 記 `unchecked`；
沒有 snapshot 或該 URL 不在 snapshot 裡時退回推斷（已勾即記 `checked`，`inferred: true`，不產生
`unchecked`）。`checked` 且 report 存在、head 相符 → ack；`inferred` 而且同一 head 已被你 ack →
不重打（避免把 seen_at 推過作者的新留言）；明確的 `[ ]→[x]` 一律重打；沒有 report → `no_report`；
head 已變 → `head_changed`；`unchecked` → `acknowledge --undo`。最終 👀 checkbox ＝
`(acked_current or checked_now) and not needs_review`（`board_state.checkbox_after_refresh`）。
👀 勾了卻沒有 report 或 head 已變：取消勾、加 `🔖`，並警告先 `/maigo:review <n>`。

**學習訊號 `🔖`**：👀 行的 `checkbox_change == checked` 且行上沒有 `🧠` 時加 `🔖`（`learn_pending`），
跨刷新保留；`--learn` 處理沒有 `🧠` 且為「(`[x]` 或 `🔖`)」或「✅ 區 `merged`」的行，完成後加 `🧠`、拿掉 `🔖`。
