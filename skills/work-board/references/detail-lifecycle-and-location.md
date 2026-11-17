# Work Board — 細節檔生命週期與 board 位置（§3 後半）

Loaded on demand by [`skills/work-board/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md) §3 — 細節檔建立／更新／回收／孤兒偵測，以及 board 與報告的位置細節（含尚未遷移的 repo）。
本檔內文原樣自 SKILL.md 搬出，章節編號（§1a、§3a 等）沿用原編號，SKILL.md 內仍以這些編號互相引用。

### 細節檔生命週期

- **建立**：項目首次進 board → 建細節檔（§1a）。
- **更新**：refresh 或任何寫回 → 重寫事實區，`## 判斷` / `## 筆記` 原樣保留（§1a 硬規則）。
- **回收**：項目離開 board（✅ 區老化或超過上限被清除、`--drop` 後也走同一組規則）→
  產物**封存而非刪除**，不留孤兒檔：orchestrator 在 `drop --reason closed|aged` 之後，對同一批
  URL 跑 `board_sync.py archive <url...>`，把 `.maigo/review/<id>/` 與 `.maigo/pr/<id>/`（整個目錄；
  依作者只會有其中一個或兩個都有）搬到 `.maigo/_archive/review/<id>/`、`.maigo/_archive/pr/<id>/`、
  `.maigo/i/<id>.md` 搬到 `.maigo/_archive/i/<id>.md`。它不查
  GitHub、不判斷 PR 狀態（哪些已結案由 orchestrator 決定，同 `drop`），目的地已存在就跳過不覆蓋，
  逐 URL 回報 moved／skipped／missing；同一路徑同時出現在 moved 與 skipped、且 skipped 的 reason
  以「警告」開頭，表示已封存但重設封存時間失敗，不是略過；`_internal/` 不碰。**順序不能顛倒**：只對已經 `drop` 掉、
  board 上已無索引行的項目跑 `archive`；索引行還在就先搬走 `i/<id>.md`，下次 `plan` 會讀不到細節檔，
  `review/<id>/review.md` 一消失，artifact 對帳也可能把項目當新項目補回——`archive` 本身沒有這層防呆。
  `refresh --apply` 目前仍直接刪老化的細節檔
  （刪前備份到 `_internal/board/backup/`），對它輸出的 `aged` URL 再跑 `archive`，`review/<id>/`
  照樣封存、`i/` 回 missing 屬正常。
  **為什麼**：已結案的 review 留在 `review/` 會混進「目前在審」的產物清單；直接刪又丟掉日後要翻的
  審查紀錄。封存後 `review/`、`pr/` 與 `i/` 只剩進行中的項目，`plan` 的孤兒偵測與 artifact 對帳也不再看到它們。
  案例：一次 40 顆 PR 的 batch 結束後手動封存了 25 個 review 目錄、10 個細節檔——使用者早已在自己的
  repo 用同一個 `_archive/` 佈局手動執行，規格卻從未寫過。
  🔀 自己的 PR 產物在 `.maigo/pr/<id>/`，不影響 👀 的 report 對帳（`board_state.py` 的 👀 項目固定讀
  `review/<id>/`；對帳掃到 `pr/<id>/` 的檔只列入未歸屬，不當成 👀 候選）。
- **孤兒偵測（dd 語意）**：`/maigo:board` 刷新時比對 `.maigo/i/*.md` 與 board 索引行；沒有任何
  索引行引用的細節檔，代表使用者用 `dd` 刪了那一行——`board_sync.py plan` 把它判成 dd 並寫進排除
  紀錄（§3a）。剛寫好的細節檔有 10 分鐘寬限（delegate 命令先寫細節檔、後 `Edit` 加行，plan 若
  落在兩者之間會誤判），期間列為 `pending_orphans`、本輪不判。排除項目殘留的細節檔
  （`excluded_detail_files`）列出來給使用者確認後才刪，不自動刪。


**尚未遷移的 repo（`.maigo` 還是真目錄，`/bin/ls -ld .maigo` 不是 symlink）才有舊行為：**
每個 worktree 各有一份 `.maigo/`，board 住在當初建立它的那個 worktree，記下來的舊路徑會過期
（2026-09-09 實例：一份記憶條目原記 `<repo>-main`，board 實際在一個 topic worktree 裡）。
這時先 `find <workspace 根> -maxdepth 3 -name board.md` 找到現存的那一份再 upsert，
不要假設它在主 worktree；找不到任何 `board.md` → 問使用者要建在哪。

**報告與 board 在同一份 `.maigo/` 底下（已遷移的 repo）。** `review/<id>/review.md` 與
`draft.md` 由 `artifact_path.py` 落在 `.maigo/` 下，不論哪個 worktree 執行，`board_state.py`
的 `--maigo-root` 讀到的都是同一份，細節檔 `## 筆記` 用檔案相對路徑
（`../review/<id>/review.md`，自己的 PR 為 `../pr/<id>/…`）就夠了，不必改寫成絕對路徑，也不必複製目錄；既有筆記裡的舊寫法不由命令改寫（要整理用 `scripts/rewrite_note_paths.py`）。
**尚未遷移的 repo** 才會發生報告落在執行命令的 worktree、board 在別處：`board_state.py`
找不到就退回 GitHub reviews 與 `prior_status`；回寫時把筆記改寫成絕對路徑，或把
`review/<id>/` 複製到 board 所在根的 `.maigo/review/`（2026-10-14 實例：6 顆 PR 在 topic
worktree 審完、board 在別的 worktree，筆記改用絕對路徑）。
