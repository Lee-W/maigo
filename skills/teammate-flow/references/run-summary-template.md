# Run summary 範本

`/maigo:go` 與 `/maigo:team` 收尾時，orchestrator 依這份範本寫 `summary.md`。路徑用
`scripts/artifact_path.py summary-for-plan <本次 plan 路徑>` 取得，與本次實際寫出的 plan 同目錄、
同編號（`plan.md` → `summary.md`、`plan-2.md` → `summary-2.md`）。什麼時候寫、為什麼由
orchestrator 自己寫，見
[`teammate-flow`](https://github.com/Lee-W/maigo/blob/main/skills/teammate-flow/SKILL.md) 的「Run summary」一節；版面規則見
[`vim-friendly-artifacts`](https://github.com/Lee-W/maigo/blob/main/skills/vim-friendly-artifacts/SKILL.md)，這份範本不重抄。

## 寫作規則

- 只寫實際發生的事。數字（輪數、測試數、exit code）一律來自本次實跑的輸出，不憑印象補。
- 失敗、跳過、沒驗證的事如實寫，放進「驗證」或「沒處理的」，不要略過。
- 不以人名或 login 指稱任何人；角色寫「使用者」。
- 內文（code fence 外）提到 agent 時帶 emoji 前綴：🐱 樂奈、🩵 燈、🎀 愛音、🟡 爽世、🟣 立希。圖裡（code fence 內）不放 emoji，用英文角色名。
- 不用 markdown 表格；對照關係用圖或條列。
- 三張圖都放在 `text` fenced code block 內，畫法見 vim-friendly-artifacts 的「純文字圖」一節：結構線只用 ASCII，單行不超過 80 個顯示寬度，不依賴中文字右邊的對齊，fence 內不留行尾空白。
- 標題與清單前後各留一個空行（檔頭四個欄位是一份連續的清單，欄位之間不留空行）；這是 formatter 的 fixed point，存檔不會被改寫才算合格。

## 骨架

四個反引號的外層 fence 只是為了在這裡展示內層的三反引號 fence，實際檔案不要帶外層。

````markdown
# <任務標題>

- **日期**：<絕對日期，例如 2026-11-17>
- **結果**：<完成／部分完成／中止>
- **計畫**：`<本次實際的 plan 檔名>`
- **commit**：`<短 hash>` <subject>

## 為什麼做

<2 至 4 句：誰遇到什麼問題、根因是什麼。>

```text
<因果鏈圖：症狀往上追到根因，或根因往下推到症狀，一路用 | 與 v 連接>
```

## 做了什麼

- <使用者可感知的行為變化，一條一句，不列檔名清單>

```text
<之前／之後對照圖：同一個輸入，兩條路徑並排或上下排>
```

## 怎麼做

```text
<流程圖：實際上場的角色、順序、審查與重試的輪數>
```

- 第 1 輪審查：<抓到什麼、怎麼處理>

## 驗證

- `<指令>`：exit <碼>，<摘要行>
- 未驗：<項目>，原因：<原因>

## 沒處理的

- <留下的缺口、被跳過的建議、待使用者決定的事；沒有就寫「無」>
````

欄位說明（放在 code fence 外，不要抄進產物）：

- **計畫**：填本次實際的 plan 檔名（`plan.md` 或 `plan-<n>.md`），同目錄、路徑相對於檔案自己，用反引號包住。plan 是 `plan-2.md` 時，這份 summary 是 `summary-2.md`，欄位填 `plan-2.md`。沒有 plan 路徑可用（退路）就寫「無」。
- **commit**：沒有 commit 就寫「未 commit」。拆成多顆時一顆一行。
- **結果**：完成／部分完成／中止的定義只有一份，在 `teammate-flow`「Run summary」的「何時寫」（以本次 run 有沒有 commit 落地為分界）；結果不是「完成」時，「沒處理的」逐條寫出「完成」的四項裡哪幾項沒達成，以及使用者為什麼決定結束。
- **怎麼做**的每一輪審查都要有對應條目；沒有重試就只有一條。
- **怎麼做**的流程圖在 `/maigo:team` 審查與驗證並行時，把兩者畫在同一列（例如 `Soyo || Taki`）。

## 填好的範例

下面是一個虛構的小任務，只示範版面與粒度；實際內容與數字都以本次執行為準。範例的 plan 是 `plan.md`，所以 summary 是同目錄的 `summary.md`；plan 是 `plan-2.md` 時，summary 是 `summary-2.md`，「計畫」欄填 `plan-2.md`。

````markdown
# 匯出指令在空資料時補上表頭

- **日期**：2026-11-17
- **結果**：完成
- **計畫**：`plan.md`
- **commit**：`a1b2c3d` fix(export): write the header row even when there are no records

## 為什麼做

使用者對一張還沒有資料的表執行匯出，得到一個 0 位元組的檔案，下游的匯入工具因此拒收。根因是表頭取自第一筆資料，沒有資料就沒有表頭。

```text
user exports an empty table
        |
        v
exporter takes the header from rows[0]
        |
        v
rows is empty  -->  header step is skipped
        |
        v
output file is 0 bytes
        |
        v
importer rejects the file
```

## 做了什麼

- 空表匯出時輸出只含表頭的檔案，不再是 0 位元組。
- 有資料的匯出結果與之前逐位元組相同。
- 欄位順序改由表結構決定，不再依賴第一筆資料的鍵順序。

```text
BEFORE                            AFTER
------                            -----
rows = []                         rows = []
  |                                 |
  v                                 v
header from rows[0]               header from schema
  |                                 |
  v                                 v
(skipped)                         header written
  |                                 |
  v                                 v
0-byte file                       header-only file
```

## 怎麼做

```text
user request
     |
     v
Raana (explore) --> Tomori (plan) --> user confirms plan
                                             |
                                             v
                                       Anon (implement)
                                             |
                                             v
                                       Soyo round 1: NEEDS_CHANGES (2 must-fix)
                                             |
                                             v
                                       Anon (fix #1, #2)
                                             |
                                             v
                                       Soyo round 2: APPROVED
                                             |
                                             v
                                       Taki (verify): PASS
                                             |
                                             v
                                       commit a1b2c3d
```

- 第 1 輪審查：🟡 爽世抓到兩個 must-fix。#1 表結構為空時沒有處理，會丟例外；#2 新測試沒有覆蓋有資料的情況。🎀 愛音補上空結構的分支與兩支測試。
- 第 2 輪審查：🟡 爽世確認兩項都已修正，結論 APPROVED，另留一個 Nit（變數命名）。
- 🟣 立希實跑測試與 lint，全部通過後才 commit。

## 驗證

- `uv run pytest`：exit 0，12 passed in 0.4s
- `uv run pre-commit run --files exporter.py test_exporter.py`：exit 0，所有 hook Passed
- 未驗：與真實匯入工具的整合，原因：測試環境沒有該工具

## 沒處理的

- 🟡 爽世的 Nit：`rows` 這個變數名稱可以更具體，沒有改，留給使用者決定。
- 其他輸出格式（JSON）的空表行為沒有檢查。
````
