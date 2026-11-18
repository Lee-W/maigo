# 可見變更的截圖

`/maigo:go` 與 `/maigo:team` 收尾時，變更有使用者看得見的輸出，就在 commit 落地之後、PR 草稿或
`pr-sync-check` 之前，由 orchestrator 準備一份能直接貼進 PR 的畫面。何時做、結果去哪，見
[`teammate-flow`](https://github.com/Lee-W/maigo/blob/main/skills/teammate-flow/SKILL.md) 的「Commit message draft + 落地」一節；這份檔案只放做法。

## 何時做（單一規則）

本次 diff 改變了「使用者在瀏覽器或終端機實際看到的畫面」，才做。拿不準時問自己：使用者執行或打開之後，畫面或終端上的字是否和以前不同，且不同處是這次 diff 造成的。

做（正例）：

- 樣式、版面、元件或頁面結構的改動，網頁或 docs 站的呈現因此不同
- 使用者直接執行的 CLI 指令，其 stdout／stderr 的文字或格式改變
- 使用者在終端機會看到的錯誤訊息改變
- hook 的擋下或警告訊息改變（使用者看得到）

不做（反例）：

- 只改 docs 或 prompt（skill、command、agent 說明）的文字內容，版面與呈現方式沒變——maigo 自己改 skill 文字的日常 run 屬於這一類
- 內部函式的回傳值、log 等使用者不會直接看到的輸出
- 只動測試

CLI 類的界線：以「使用者在終端機實際看到」為準。使用者直接執行的指令輸出與錯誤訊息算；hook 的擋下或警告訊息算（`hooks/_hook_io.py` 把同一段文字同時放進 `reason` 與 `systemMessage`，使用者看得到）；被 skill 或 command 呼叫、只給 agent 讀的 script stdout 不算，但由 command 原樣轉貼給使用者的輸出（例如 `/maigo:tidy`）算。

不適用時整步靜默，不印任何東西；適用但做不到才印一行原因，再附待辦清單。

## 終端輸出：前後對照的文字

不產圖。實跑變更前後的同一條指令，把兩份輸出並排成文字 code block：

- 「後」在當前 HEAD 跑。
- 「前」在 merge-base 的暫時 worktree 上跑，不用 `git stash` 或 `git checkout` 動當前工作樹（其他 session 可能正在用）。開與清 worktree 前先讀 [`git-workflow`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/SKILL.md)。
  - base：用 [`draft-bundle`](https://github.com/Lee-W/maigo/blob/main/skills/github-title-description/references/draft-bundle.md)「收尾情境」步驟 2 決定的 remote-tracking ref（例：`upstream/main`），不另立定義；實際跑「前」的 commit 是 `git merge-base <base> HEAD`，不是 base 的最新 commit，否則 branch 落後 base 時，別人已合併的變更會混進前後差異。draft-bundle 找不到 base 時，視為「前」擷取失敗。
  - 路徑：repo 之外的暫存位置（例如 `mktemp -d` 產生的目錄），**不可**放在 `.worktrees/`，那是任務 worktree 的位置。用 `git worktree add --detach <路徑> <merge-base 的 commit>` 建立。
  - 清理：不論跑成功或失敗，都 `git worktree remove --force <路徑>`，之後 `git worktree list` 確認沒有殘留。
  - 不做 bootstrap：新 worktree 需要先安裝依賴或建置才跑得動，就視為「前」擷取失敗，不去安裝。
- hook 訊息的前後對照，用 [`docs/reference/hooks.md`](https://github.com/Lee-W/maigo/blob/main/docs/reference/hooks.md)「觀察 hook 行為」的 stdin 模擬指令（`python3 -c "import json; print(json.dumps({...}))" | python3 hooks/<hook>.py`），在 merge-base 的暫時 worktree 與當前 HEAD 各跑一次。
- 「前」擷取失敗時，只附「後」的實跑輸出，並在待辦清單寫「要跑的指令＋在哪個 ref 跑」。
- 輸出必須是實跑結果，逐字貼，不憑推測改寫；太長就截取相關段落並標明截取。
- 「後」也跑不起來（缺相依、要連外部服務）：不補寫輸出，整段改列待辦清單。

## 網頁畫面：由 orchestrator 擷取

瀏覽器類工具只在 orchestrator 手上，五位團員的 agent 定義都沒有，所以擷取不交辦。兩個前提都成立才擷取：

1. 宿主有瀏覽器類工具（沒有就視為不成立，不嘗試安裝）。
2. repo 有說明怎麼把 app 或 docs 站跑起來，來源是 repo-aware skill 或專案文件（README、CONTRIBUTING、docs 的 build 說明）。
   例子：[`airflow-aware` 的 `verification-tooling.md` §6](https://github.com/Lee-W/maigo/blob/main/skills/airflow-aware/references/verification-tooling.md)
   寫了怎麼 build 單一 docs 套件、用 `file://` 開頁面、以及擷取前要檢查的陷阱。通用步驟不假設任何特定專案。

做法：照該說明啟動，開到變更涉及的頁面截圖；「前」只在不必另開 worktree、不必重新安裝依賴或另 build 就能取得時才補（例如 base 版本的站已經在跑），否則只截「後」。擷取前確認頁面載入完成、樣式有套上，空白或沒套樣式的畫面不算數。

### 圖檔位置與命名

不新增 artifact kind。圖檔放在本次 plan 所在的目錄（plan 路徑的 dirname），檔名以 plan 的檔名主幹為前綴，與 plan、summary 排在一起：

```text
<plan 主幹>-screenshot-<n>-<slug>[-before|-after].png
```

- `<plan 主幹>`：plan 檔名去掉 `.md`，`plan.md` 是 `plan`、`plan-2.md` 是 `plan-2`。
- `<n>`：同一次 run 的流水號，從 1 起。
- `<slug>`：小寫 ASCII、連字號分隔，說明畫面是什麼（例如 `export-empty-table`）。
- 有前後對照時加 `-before`／`-after`；只有單張就不加。

例：`plan.md` 對應 `plan-screenshot-1-export-empty-table-after.png`；`plan-2.md` 對應 `plan-2-screenshot-1-export-empty-table.png`。

圖檔是否被該 repo 忽略，用 `git check-ignore <圖檔路徑>` 確認，不假設。commit 一律明列檔名 `git add`（見 `git-workflow`），所以圖檔不會被帶進 commit；沒被忽略時它是 untracked 檔，照實告訴使用者，不要 `git add`。使用者貼 PR 時自己從該路徑拖進去。

`/maigo:tidy` 與 `/maigo:doctor` 會把這些圖檔列為「未登記」檔，這是預期（不新增 artifact kind 的代價）。orchestrator 不可代使用者執行 `--confirm` 或 `--confirm-archive`，使用者要留就忽略該提示。

## 擷取不到時

沒有瀏覽器工具、repo 沒說明怎麼啟動、啟動或擷取失敗：不硬擷取、不停下來問使用者，改列清單由使用者手動截或手動跑。清單分兩種：

- 網頁：每個畫面一條，寫「要截的畫面」（頁面或元件是什麼、預期看到什麼）與「怎麼到達」（啟動指令與要開的路徑或操作步驟，只寫 repo 說明裡查得到的，查不到就寫「repo 沒有說明」）。
- 終端：每條指令一條，寫「要跑的指令」與「在哪個 ref 跑」（前：`git merge-base <base> HEAD` 的 commit；後：當前 HEAD）。

任何失敗只印一行原因，不中斷收尾，與 `pr-sync-check` 的失敗處理一致。

## 結果去哪（三處）

- run summary 的「驗證」段：圖檔路徑、或待截清單、或前後對照；欄位寫法見 [`run-summary-template.md`](https://github.com/Lee-W/maigo/blob/main/skills/teammate-flow/references/run-summary-template.md)。
- PR 草稿或 `pr-sync-check` 的更新草稿：在草稿裡放截圖的位置標出「此處貼 `<檔名>`」或待截清單；前後對照的文字直接放進草稿。
- final summary：一行，寫產出了什麼（幾張圖、前後對照、或待截清單）以及路徑。

沒做這一步（不適用）時，三處都不提。
