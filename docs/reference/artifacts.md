# `.maigo/` Artifacts Reference

`.maigo/` 全貌型錄：這個目錄底下有哪些檔、各自的正典（code + skill）是誰、
生命週期多長。找不到某個 `.maigo/` 檔案該歸哪一類時，先查這頁；機器判斷
邏輯（哪個檔案屬於哪一類）由 `scripts/maigo_dir_catalog.py` 執行，不是散文
自己判斷——見 [`/maigo:doctor`](../commands/doctor.md) 的「`.maigo/` 頂層型錄」段。

## 帶識別碼命名的產物（`<kind>-<id>.md`）

| 種類 | 檔名規則 | 誰寫的 | 正典來源 | 生命週期 |
|------|----------|--------|----------|----------|
| `plan` | `.maigo/plan-<id>.md` | 🩵 Tomori | `scripts/artifact_path.py` + [artifact-ownership](https://github.com/Lee-W/maigo/blob/main/skills/harness-discipline/references/artifact-ownership.md) | 單次任務的實作計畫，任務結束後仍留存供追溯 |
| `review-rubric` | `.maigo/review-rubric-<id>.md` | 🩵 Tomori | 同上 | 對照基準，review 全程比對用；review 結束後留存 |
| `review` | `.maigo/review-<id>.md` | orchestrator（`/maigo:review`） | 同上 | 最終 review 五段報告的逐字檔案版；長期留存供 `grep` / board 細節檔連結 |
| `triage-rubric` | `.maigo/triage-rubric-<id>.md` | 🩵 Tomori | 同上 | issue triage 的對照基準 |
| `pr-comments` | `.maigo/pr-comments-<id>.md` | orchestrator（`/maigo:address-comments`） | 同上 | PR 既有 review comment 的抓取與分類結果 |

四種 kind 全部由 `scripts/artifact_path.py` 的 `_KNOWN_KINDS` 單一正典定義，
`resolve_for_write()` 是唯一對外寫入入口——同一檔名撞到不同主題時回
`status: conflict`，呼叫端必須先問使用者再決定要不要用建議的候選檔名，
不擅自覆寫。

## Work Board（`board.md` + `i/<slug>.md`）

| 種類 | 檔名規則 | 誰寫的 | 正典來源 | 生命週期 |
|------|----------|--------|----------|----------|
| Work Board 索引 | `.maigo/board.md` | orchestrator（`/maigo:board` / `/maigo:review`） | `scripts/board_state.py` + [work-board skill](../skills/work-board.md) | 跨 session 常駐，不隨單次任務結束而收檔 |
| Work Board 細節檔 | `.maigo/i/<slug>.md` | 同上 | 同上 | 跟著對應 issue/PR 的追蹤狀態走；孤兒偵測見 `/maigo:board` 既有邏輯 |

board 這條線是全 repo 最佳實踐——code 定正典（`board_state.py`）、skill 鏡射
人讀版本（`work-board`）、test 守一致（`tests/test_board_state.py`），三方鎖住，
本頁不重寫它的行文法，只在型錄裡佔一個位置。

## 非 markdown 機器狀態檔

一行帶過，內部用，非 agent 面向格式：`session-head.json`（session 開始時的
HEAD SHA）、`token-usage.jsonl`（token usage metadata）、
`test-failures.jsonl` / `soyo-must-fix.jsonl`（retry / failure log）、
`__titles.json`（內部快取）。

## 舊固定檔名與未登記檔案

升級前留下的舊固定檔名（`.maigo/plan.md` 這類）與不屬於上述任何種類的
未登記檔案，一律**只列不刪**——正典邏輯見 `scripts/maigo_dir_catalog.py`，
人讀報告見 [`/maigo:doctor`](../commands/doctor.md)。要不要清由使用者自己
決定，這份型錄與 doctor 報告都不建議刪除哪一個。
