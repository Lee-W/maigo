# `.maigo/` Artifacts Reference

`.maigo/` 全貌型錄：這個目錄底下有哪些檔、各自的正典（code + skill）是誰、
生命週期多長。找不到某個 `.maigo/` 檔案該歸哪一類時，先查這頁；機器判斷
邏輯（哪個檔案屬於哪一類）由 `scripts/maigo_dir_catalog.py` 執行，不是散文
自己判斷——見 [`/maigo:doctor`](../commands/doctor.md) 的「`.maigo/` 型錄」段。

## 帶識別碼命名的產物

所有 kind 全部由 `scripts/artifact_path.py` 的 `_KNOWN_KINDS` 單一正典定義，
`resolve_for_write()` 負責一般產物的歸屬檢查（最終 review 報告用下述 publisher）——同一路徑撞到不同主題時回
`status: conflict`，呼叫端必須先問使用者再決定要不要用建議的候選路徑，
不擅自覆寫。分兩種形狀：

### `plan`（扁平，`<kind>-<id>.md`）

| 種類 | 檔名規則 | 誰寫的 | 正典來源 | 生命週期 |
|------|----------|--------|----------|----------|
| `plan` | `.maigo/plan-<id>.md` | 🩵 Tomori | `scripts/artifact_path.py` + [artifact-ownership](https://github.com/Lee-W/maigo/blob/main/skills/harness-discipline/references/artifact-ownership.md) | 單次任務的實作計畫，任務結束後仍留存供追溯 |

### `review` / `issue`（巢狀，`<group>/<id>/<stem>.md`）——按 PR/issue 分資料夾

同一顆 PR 的 `review` / `review-rubric` / `review-draft` / `pr-comments` 收進同一個
`.maigo/review/<id>/` 目錄；同一條 issue 的 `triage-rubric` 收進
`.maigo/issue/<id>/`；conflict 後綴（第 2 個 attempt 起）落在檔名層
（`rubric-2.md`），不落在目錄層。

| 種類 | 檔名規則 | 誰寫的 | 正典來源 | 生命週期 |
|------|----------|--------|----------|----------|
| `review-rubric` | `.maigo/review/<id>/rubric.md` | 🩵 Tomori | `scripts/artifact_path.py` + [artifact-ownership](https://github.com/Lee-W/maigo/blob/main/skills/harness-discipline/references/artifact-ownership.md) | 對照基準，review 全程比對用；review 結束後留存 |
| `review` | `.maigo/review/<id>/review.md` | orchestrator（`/maigo:review`） | `scripts/review_report.py`（重用 artifact_path 命名） | 同 source 只留最新完整 report；內含 TOC、原作者（`--author`）、最後 review 時間、reviewed commit 與本地已看完標記 |
| `review-draft` | `.maigo/review/<id>/draft.md` | orchestrator（`/maigo:review` §4.5） | 同上 | 待貼上 GitHub 的 review body 草稿；`board_state.py` 的 `待送出` next_action 在這個檔存在時給 `gh pr review --body-file` 指令，不存在時改提示先起草 |
| `pr-comments` | `.maigo/review/<id>/pr-comments.md` | orchestrator（`/maigo:address-comments`） | 同上 | PR 既有 review comment 的抓取與分類結果 |
| `triage-rubric` | `.maigo/issue/<id>/rubric.md` | 🩵 Tomori | 同上 | issue triage 的對照基準 |

`review_report.py publish` 先原子寫入最新 `review.md`，才清理同目錄 `review-N.md` 與
`.maigo/review-<id>.md` 中可確認同 source 的舊報告；未知歸屬、較新的 timestamp、
草稿、rubric、手寫檔與其他 PR 保留。歸屬看 metadata 的 source 或舊 report 明確 PR URL，
不因為檔名相似就刪。清理結果回傳給 caller，同步修正 board 細節檔的報告連結。

`review_report.py acknowledge` 記「使用者已看完這版」，不送 GitHub、不改最後 review
時間；使用者在 board 把 👀 行勾成 `[x]`，下次 `/maigo:board` 刷新就會呼叫它（`--reviewed` 等同勾上）。
新 head／作者留言讓 board 重新排入待看（👀 行自動取消勾）；新 report 清除上一輪確認。

### 分目錄前的扁平檔（`flat_exists:`，只可讀）

巢狀佈局採用前寫下的 `<kind>-<id>.md`（例：`review-rubric-42.md`）——`resolve_for_write()`
發現這種檔案存在時，`Resolution.flat_path` 會填值（CLI 印 `flat_exists:` 那行），
只供讀取退路，永遠不當寫入目標；`Write` / `Edit` 寫進這個形狀會被
[`hooks/legacy_artifact_path_check.py`](https://github.com/Lee-W/maigo/blob/main/hooks/legacy_artifact_path_check.py)
擋下。既有的這類檔案可用
[`scripts/migrate_legacy_artifacts.py`](https://github.com/Lee-W/maigo/blob/main/scripts/migrate_legacy_artifacts.py)
（先 dry-run 看清單，使用者同意後 `--apply`）搬進巢狀佈局，順手把 `.maigo/i/*.md`
的 `## 筆記` 段裡指到舊檔名的連結改成新相對路徑。`--apply` 中途中斷時，重跑同一
條指令即可：它照第一次寫下的搬移對應表續跑，不重新規劃。

## Work Board（`board.md` + `i/<slug>.md`）

| 種類 | 檔名規則 | 誰寫的 | 正典來源 | 生命週期 |
|------|----------|--------|----------|----------|
| Work Board 索引 | `.maigo/board.md` | orchestrator（`/maigo:board` / `/maigo:review`） | `scripts/board_state.py` + [work-board skill](../skills/work-board.md) | 跨 session 常駐，不隨單次任務結束而收檔 |
| Work Board 細節檔 | `.maigo/i/<slug>.md` | 同上 | 同上 | 跟著對應 issue/PR 的追蹤狀態走；沒有索引行引用的孤兒細節檔視為 `dd`（使用者刪了那一行），見 [work-board skill](../skills/work-board.md) §3a |
| 已結案封存 | `.maigo/_archive/review/<id>/`、`.maigo/_archive/i/<id>.md` | orchestrator（`board_sync.py archive`） | `scripts/board_sync.py` + [work-board skill](../skills/work-board.md) §3「細節檔生命週期」 | merged／closed／老化項目的 review 目錄與細節檔從 `review/`、`i/` 搬來這裡留存；不覆蓋既有封存，不被 board 對帳讀取 |

board 這條線是全 repo 最佳實踐——code 定正典（`board_state.py`）、skill 鏡射
人讀版本（`work-board`）、test 守一致（`tests/test_board_state.py`），三方鎖住，
本頁不重寫它的行文法，只在型錄裡佔一個位置。board 的內部狀態（排除紀錄、快照）放在
`.maigo/_internal/board/`，對帳、discovery 與排除規則見 [work-board skill](../skills/work-board.md) §3a。

### `_internal/`：只給機器讀

`.maigo/_internal/` 底下的所有內容都只給機器讀，使用者在 `.maigo/` 根目錄只會看到給人讀的檔案。
型錄（`maigo_dir_catalog`）與 `/maigo:doctor` 永遠不列這個目錄。目前只有 board 使用，
由 [`scripts/board_sync.py`](https://github.com/Lee-W/maigo/blob/main/scripts/board_sync.py) 自行建立與寫入：

| 檔案 | 用途 |
|------|------|
| `_internal/board/dropped.jsonl` | 排除紀錄：每行一個 `drop` / `revive` 事件，只 append；`dd` 掉的項目之後不會被 discovery 補回，除非重新被指名 |
| `_internal/board/snapshot.json` | 上次刷新結束時 board 上的項目與勾選狀態，用來偵測 `dd` 與 `[x]` 變化 |
| `_internal/board/backup/<UTC ts>/` | `refresh --apply` 寫回前複製的 `board.md` 與細節檔，只留最新 10 份；寫入失敗時用來還原 |

## 非 markdown 機器狀態檔

一行帶過，內部用，非 agent 面向格式：`session-head.json`（session 開始時的
HEAD SHA）、`token-usage.jsonl`（token usage metadata）、
`test-failures.jsonl` / `soyo-must-fix.jsonl`（retry / failure log）、
`__titles.json`（內部快取）、`migrate-legacy-artifacts.manifest.json`
（`scripts/migrate_legacy_artifacts.py --apply` 的搬移對應表，只在一次 apply
沒跑完時留存，重跑時照它續跑，跑完即刪）。這些檔日後可能搬進 `_internal/`。

## 舊固定檔名與未登記檔案

升級前留下的舊固定檔名（`.maigo/plan.md` 這類，`legacy_fixed_name`）、分目錄前的
扁平檔（`flat_identifier`，見上一節）與不屬於上述任何種類的未登記檔案
（`unregistered`），一律**只列不刪**——正典邏輯見 `scripts/maigo_dir_catalog.py`
（六類：`nested` / `identifier_named` / `flat_identifier` / `legacy_fixed_name` /
`registered_non_artifact` / `unregistered`），人讀報告見
[`/maigo:doctor`](../commands/doctor.md)。要不要清由使用者自己決定，這份型錄與
doctor 報告都不建議刪除哪一個。

兩個字面上像 review kind 產物、但不是的檔名——`categorize()` 特別排除，
不會被搬移或擋下：`review-batch-state.md`（本 repo 找不到 producer，型錄列為
`unregistered`）、`review-board.md`（舊版 Work Board 檔名，
[`commands/board.md`](../commands/board.md) 仍會偵測並遷移它，型錄列為
`registered_non_artifact`）。
