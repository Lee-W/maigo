# `.maigo/` Artifacts Reference

`.maigo/` 全貌型錄：這個目錄底下有哪些檔、各自的正典（code + skill）是誰、
生命週期多長。找不到某個 `.maigo/` 檔案該歸哪一類時，先查這頁；機器判斷
邏輯（哪個檔案屬於哪一類）由 `scripts/maigo_dir_catalog.py` 執行，不是散文
自己判斷——見 [`/maigo:doctor`](../commands/doctor.md) 的「`.maigo/` 型錄」段。

`.maigo/` 人讀產物（plan、review 報告、rubric、草稿、board 與 i/ 細節檔）的版面規範見 [`vim-friendly-artifacts`](../skills/vim-friendly-artifacts.md)。

## 佈局總覽

```text
.maigo/
├── board.md                    Work Board 索引（人讀）
├── i/<slug>.md                 Work Board 細節檔（人讀）
├── pr/<id>/                    自己的 PR：plan.md、rubric.md、review.md、reply-draft.md …
├── review/<id>/                別人的 PR：review.md、rubric.md、draft.md、pr-comments.md …
├── issue/<id>/                 issue：plan.md、rubric.md
├── topic/<slug>/               沒有 PR / issue 的任務：plan[-n].md
├── _archive/<原相對路徑>        已結案項目，鏡射上面的相對路徑（review/、pr/、i/ 由 /maigo:board 與 /maigo:tidy 封存；issue/、topic/ 由 /maigo:tidy 封存）
└── _internal/                  只給機器讀：board/、log/、tidy/backup/
```

- `plan` 的 group 依 URL 決定：PR URL → `pr/`、issue URL → `issue/`，其餘 → `topic/`。
  在預設分支（`main` / `master` / `develop` / `trunk`）上，識別碼不用分支名，用
  `--slug`（優先）或 `--topic` 的 H1 slug；兩者都推不出來就報錯，不退回短 SHA。
- 同一個 group 目錄收同一顆 PR / issue / topic 的所有產物；conflict 的第 2 個 attempt
  起落在檔名層（`plan-2.md`），不另開目錄。
- 頂層 `plan-<id>[-n].md` 是舊形狀，只可讀；`scripts/migrate_legacy_artifacts.py`
  會把它搬到 `topic/<id>/plan[-n].md`（不推測 PR / issue 歸屬）；`-n` 只在同批有
  `plan-<id>.md` 同伴時才當 attempt 後綴。

## 帶識別碼命名的產物

所有 kind 全部由 `scripts/artifact_path.py` 的 `_KNOWN_KINDS` 單一正典定義，
`resolve_for_write()` 負責一般產物的歸屬檢查（最終 review 報告用下述 publisher）——同一路徑撞到不同主題時回
`status: conflict`，呼叫端必須先問使用者再決定要不要用建議的候選路徑（從第 2 個 attempt 起第一個未被其他主題占用者；也可能指到 H1 相同的既有檔，status 仍是 conflict），
不擅自覆寫。兩種形狀都是巢狀：

### `plan`（巢狀，`<group>/<id>/plan.md`，group 依 URL 分 `pr` / `issue` / `topic`）

| 種類 | 檔名規則 | 誰寫的 | 正典來源 | 生命週期 |
|------|----------|--------|----------|----------|
| `plan` | `.maigo/pr/<id>/plan.md`（PR URL）／`.maigo/issue/<id>/plan.md`（issue URL）／`.maigo/topic/<slug>/plan.md`（其餘；預設分支用 `--slug`） | 🩵 Tomori | `scripts/artifact_path.py` + [artifact-ownership](https://github.com/Lee-W/maigo/blob/main/skills/harness-discipline/references/artifact-ownership.md) | 單次任務的實作計畫，任務結束後仍留存供追溯 |

### `review` / `pr` / `issue`（巢狀，`<group>/<id>/<stem>.md`）——按 PR/issue 分資料夾

同一顆 PR 的 `review` / `review-rubric` / `review-draft` / `pr-comments` / `reply-draft`
收進同一個目錄，並依 PR 作者分流：**別人的 PR** 放 `.maigo/review/<id>/`，**自己的 PR**
（含本地 branch / commit range）放 `.maigo/pr/<id>/`，下表檔名規則裡的 `review/` 都適用這兩組。
作者由 [`scripts/pr_owner.py`](https://github.com/Lee-W/maigo/blob/main/scripts/pr_owner.py)
查，以 `--owner mine|others` 傳給 `scripts/artifact_path.py`；另一組已有同 id 同名檔時，
`artifact_path.py` 多印 `other_group_exists:` 供讀取。既有的 `review/<id>/` 可用
`scripts/migrate_legacy_artifacts.py --split-own-prs` 把自己的 PR 搬進 `pr/<id>/`。
同一條 issue 的 `triage-rubric` 收進
`.maigo/issue/<id>/`；conflict 後綴（第 2 個 attempt 起）落在檔名層
（`rubric-2.md`），不落在目錄層。

| 種類 | 檔名規則 | 誰寫的 | 正典來源 | 生命週期 |
|------|----------|--------|----------|----------|
| `review-rubric` | `.maigo/review/<id>/rubric.md` | 🩵 Tomori | `scripts/artifact_path.py` + [artifact-ownership](https://github.com/Lee-W/maigo/blob/main/skills/harness-discipline/references/artifact-ownership.md) | 對照基準，review 全程比對用；review 結束後留存 |
| `review` | `.maigo/review/<id>/review.md` | orchestrator（`/maigo:review`） | `scripts/review_report.py`（重用 artifact_path 命名） | 同 source 只留最新完整 report；內含原作者（`--author`）、最後 review 時間、reviewed commit 與本地已看完標記 |
| `review-draft` | `.maigo/review/<id>/draft.md` | orchestrator（`/maigo:review` §4.5） | 同上 | 待貼上 GitHub 的 review body 草稿；`board_state.py` 的 `待送出` next_action 在這個檔存在時給 `gh pr review --body-file` 指令，不存在時改提示先起草 |
| `pr-comments` | `.maigo/review/<id>/pr-comments.md` | orchestrator（`/maigo:address-comments`） | 同上 | PR 既有 review comment 的抓取與分類結果 |
| `reply-draft` | `.maigo/review/<id>/reply-draft.md`（自己的 PR 在 `.maigo/pr/<id>/`） | orchestrator（`/maigo:address-comments` §6） | 同上 | 每則回覆草稿的正本檔，每則標明在哪裡回（inline thread / PR conversation 底部）、連結與前置條件；對話只印路徑與對照表 |
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
| 已結案封存 | `.maigo/_archive/review/<id>/`、`.maigo/_archive/pr/<id>/`、`.maigo/_archive/i/<id>.md` | orchestrator（`board_sync.py archive`） | `scripts/board_sync.py` + [work-board skill](../skills/work-board.md) §3「細節檔生命週期」 | merged／closed／老化項目的 review／pr 目錄與細節檔從 `review/`、`pr/`、`i/` 搬來這裡留存；不覆蓋既有封存，不被 board 對帳讀取 |

board 這條線是全 repo 最佳實踐——code 定正典（`board_state.py`）、skill 鏡射
人讀版本（`work-board`）、test 守一致（`tests/test_board_state.py`），三方鎖住，
本頁不重寫它的行文法，只在型錄裡佔一個位置。索引行的 `@<login>`（GitHub `author.login`）是必填：缺作者的行，
`board_sync.py` 的嚴格解析會報錯，`refresh` 讀現檔時放寬並補回；補不到就在旁註標 `作者待補`（警告，不是錯誤）。board 的內部狀態（排除紀錄、快照）放在
`.maigo/_internal/board/`，對帳、discovery 與排除規則見 [work-board skill](../skills/work-board.md) §3a。

### `_internal/`：只給機器讀

`.maigo/_internal/` 底下的所有內容都只給機器讀，使用者在 `.maigo/` 根目錄只會看到給人讀的檔案。
型錄（`maigo_dir_catalog` 的 `scan()`）與 `/maigo:doctor` 不列這個目錄（`--tree` 只計檔數）。board 部分
由 [`scripts/board_sync.py`](https://github.com/Lee-W/maigo/blob/main/scripts/board_sync.py) 自行建立與寫入；其餘列在同一張表：

| 檔案 | 用途 |
|------|------|
| `_internal/board/dropped.jsonl` | 排除紀錄：每行一個 `drop` / `revive` 事件，只 append；`dd` 掉的項目之後不會被 discovery 補回，除非重新被指名 |
| `_internal/board/snapshot.json` | 上次刷新結束時 board 上的項目與勾選狀態，用來偵測 `dd` 與 `[x]` 變化 |
| `_internal/log/*` | hook 寫的機器 log（見下節「非 markdown 機器狀態檔」） |
| `_internal/migrate-legacy-artifacts.manifest.json` | `migrate_legacy_artifacts.py --apply` 中斷時留存的搬移對應表，跑完即刪 |
| `_internal/tidy/backup/<UTC ts>/` | `/maigo:tidy --apply` 動手前複製的備份，路徑是相對 `.maigo/` 的原路徑；還原＝複製回 `.maigo/`；不自動清，要刪由你自己決定 |
| `_internal/board/backup/<UTC ts>/` | `refresh --apply` 寫回前複製的 `board.md` 與細節檔，只留最新 10 份；寫入失敗時用來還原 |

## 生命週期與 `/maigo:tidy`

每一類產物有一個 owner、一個結案條件、一個去向。結案之後的搬移與清理都走
[`/maigo:tidy`](../commands/tidy.md)（預設 dry-run，`--apply` 只做規則型動作）；下面的門檻數字是
`scripts/maigo_tidy.py` 裡的常數，可以調整。

| 產物 | owner | 結案條件 | 去向 |
|------|-------|----------|------|
| `pr/<id>/`、`review/<id>/`、`issue/<id>/` | 該 PR／issue 的處理者（orchestrator 與 agent 寫入） | id 是純數字，且 GitHub 狀態是 merged 或 closed（`gh pr view`／`gh issue view`）；查不到就不動，非純數字的 id（`<repo>-<n>`、slug）不逐筆列、在統計段彙總一行 | 鏡射搬到 `_archive/<原相對路徑>`（規則型，`--apply` 會做） |
| `i/<id>.md` | `/maigo:board` | id 是純數字且對應 PR／issue merged 或 closed；`<repo>-<n>` 形的由 `/maigo:board` 處理，tidy 只在統計段彙總 | 同上 |
| `topic/<slug>/` | 寫 plan 的人 | 沒有外部訊號可查，只能由你勾選 | 勾選後封存到 `_archive/topic/<slug>/` |
| 頂層舊檔（`plan.md`、`plan-<id>.md`、`<kind>-<id>.md` …） | 升級前的 maigo | 一律視為待遷移 | 遷移成巢狀佈局（規則型） |
| 頂層機器日誌（`session-head.json`、三個 jsonl） | 升級前的 hook | 一律視為待搬 | 搬進 `_internal/log/`，jsonl 新舊都在時把舊檔接在新檔前面（舊在前、新在後；`session-head.json` 以新檔為準）（規則型） |
| `_internal/log/*.jsonl` | hook | 超過 2,000 行 | 舊的搬成 `<name>.1.jsonl`，只留一代（規則型，門檻 `LOG_ROTATE_MAX_LINES`）；`/maigo:doctor` 的統計只看現行檔，不含 `.1.jsonl` |
| `_archive/` 的項目 | `/maigo:board`、`/maigo:tidy` | mtime 超過 90 天（`ARCHIVE_RETENTION`） | 列為 delete-candidate，**一律要你逐項勾選**；確認＝備份後刪除 |
| 未登記檔（`evals/`、`__titles.json`、`local-model-dispatch-plan.md` 這類） | 不明 | catalog 判為 `unregistered` | 不隨 `--apply` 動；`--confirm <path>`＝備份後刪除，`--confirm-archive <path>`＝備份後封存到 `_archive/`，不點名就保留 |
| `.maigo/.maigo/` | hook 在子目錄 cwd 下的殘留 | 一律視為殘留 | 同上（刪除或封存）；要合併回上層請手動處理 |

規則型動作之外沒有「全部同意」的開關：刪除類與 `topic/` 封存只對 `--confirm` 點名的那一筆動手。
每個動作前都先備份到 `_internal/tidy/backup/<UTC ts>/`。

## 非 markdown 機器狀態檔

一行帶過，內部用，非 agent 面向格式。四個 hook 寫的機器 log 在
`.maigo/_internal/log/`：`session-head.json`（session 開始時的 HEAD SHA）、
`token-usage.jsonl`（token usage metadata）、
`test-failures.jsonl` / `soyo-must-fix.jsonl`（retry / failure log）。
hook 一律寫到 repo 根目錄的 `.maigo/`（`hooks/_maigo_root.py`：git toplevel，
git 不可用時退回 payload cwd），不管 session 的 cwd 在哪個子目錄，也不會再長出
`.maigo/.maigo/`。讀取端先讀 `_internal/log/` 的新檔，沒有才讀舊的頂層同名檔
（新舊都在時只讀新的、不合併）；舊檔不由 hook 搬，留給 `/maigo:tidy` 處理。
其餘：`__titles.json`（內部快取）、`_internal/migrate-legacy-artifacts.manifest.json`
（`scripts/migrate_legacy_artifacts.py --apply` 的搬移對應表，只在一次 apply
沒跑完時留存，重跑時照它續跑，跑完即刪；升級前放在 `.maigo/` 頂層的舊位置
讀取時也認、清理時一併刪）。

## 舊固定檔名與未登記檔案

升級前留下的舊固定檔名（`.maigo/plan.md` 這類，`legacy_fixed_name`）、分目錄前的
扁平檔（`flat_identifier`，見上一節）與不屬於上述任何種類的未登記檔案
（`unregistered`），預設**只列不刪**（要處理走 [`/maigo:tidy`](../commands/tidy.md)，刪除只對你勾選的那一筆動手）——正典邏輯見 `scripts/maigo_dir_catalog.py`
（六類：`nested` / `identifier_named` / `flat_identifier` / `legacy_fixed_name` /
`registered_non_artifact` / `unregistered`），人讀報告見
[`/maigo:doctor`](../commands/doctor.md)。要不要清由使用者自己決定，這份型錄與
doctor 報告都不建議刪除哪一個。

兩個字面上像 review kind 產物、但不是的檔名——`categorize()` 特別排除，
不會被搬移或擋下：`review-batch-state.md`（本 repo 找不到 producer，型錄列為
`unregistered`）、`review-board.md`（舊版 Work Board 檔名，
[`commands/board.md`](../commands/board.md) 仍會偵測並遷移它，型錄列為
`registered_non_artifact`）。
