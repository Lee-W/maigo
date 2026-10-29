---
description: 整理 `.maigo/`——預設 dry-run，逐項列出判定依據與預定動作；`--apply` 只執行規則型動作（舊檔遷移、機器日誌歸位、已結案項目封存、log 輪替），刪除與未登記檔永遠由你逐項勾選。orchestrator 直跑，不 delegate 五人。
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/maigo_tidy.py:*), Bash(gh pr view:*), Bash(gh issue view:*), Read, AskUserQuestion
---

<!-- mkdocs-include-start -->

# /maigo:tidy

> 🌙 Doloris：「亂的地方不用急著收，先一件一件點名，再決定誰留下來。」

> 本檔的 `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/…` 刻意不加引號：為了讓 `allowed-tools` 的前綴放行與替換後的命令字串字面一致；plugin 安裝路徑含空白時不支援。

`.maigo/` 是 gitignore 的工作目錄，產物不會自己結案。這個命令是唯一的清理入口：先列清單、再動手，
每一項都附判定依據。命令由 orchestrator 直跑，不動員五人；清單邏輯在
[`scripts/maigo_tidy.py`](https://github.com/Lee-W/maigo/blob/main/scripts/maigo_tidy.py)，
各類產物的 owner 與結案條件見
[`.maigo/` Artifacts Reference](https://github.com/Lee-W/maigo/blob/main/docs/reference/artifacts.md)。

## 使用

```
/maigo:tidy                          # dry-run：只列清單，不動任何檔案
/maigo:tidy --no-gh                  # dry-run，跳過結案判定（不打 gh），只列本地可判的動作
/maigo:tidy --apply                  # 執行規則型動作（先列清單、徵得同意）
/maigo:tidy --apply --confirm <path> # 另外執行你點名的那一筆需要勾選的動作（可重複）
/maigo:tidy --apply --confirm-archive <path> # unregistered／.maigo/.maigo 改成封存而不是刪除（可重複）
```

## 兩種動作

**規則型動作**（`--apply` 會執行）：

- 舊扁平檔遷移成巢狀佈局（`scripts/migrate_legacy_artifacts.py` 的規劃）。
- 頂層機器日誌（`session-head.json`、三個 jsonl）搬進 `.maigo/_internal/log/`；新舊都在時 jsonl 把舊檔接在新檔前面（舊在前、新在後），`session-head.json` 以新檔為準。
- 狀態是 merged／closed 的 `pr/`、`review/`、`issue/` 目錄與 `i/<id>.md`，鏡射封存到 `.maigo/_archive/<原相對路徑>`。只處理 id 是純數字的項目；跨 repo 的 `<repo>-<n>`、slug 不逐筆列，統計段彙總成一行，`i/` 的那批由 `/maigo:board` 處理。
- `_internal/log/*.jsonl` 超過 2,000 行就輪替成 `<name>.1.jsonl`，只留一代。

**一律要你逐項勾選**（不隨 `--apply` 自動做）：

- `topic/<slug>/` 封存——沒有外部訊號可判結案。
- `_archive/` 裡封存後超過 90 天的項目（tidy 封存時會把 mtime 重設成封存當下）（delete-candidate）。
- catalog 判為 unregistered 的項目（`evals/`、`__titles.json` 這類）。
- `.maigo/.maigo/`（hook 在子目錄 cwd 下長出的殘留）。
- GitHub 狀態查不到的項目——查不到就不動。

unregistered 項目與 `.maigo/.maigo/` 有三條路，每一項都要明講選哪一條：

- **刪**：`--confirm <path>`，備份後刪除。
- **封存**：`--confirm-archive <path>`，備份後鏡射搬到 `.maigo/_archive/<原相對路徑>`，不覆蓋既有封存。
- **不勾就留**：兩個旗標都不點名，原封不動。

`delete-candidate`（`_archive/` 超過保留期）只有刪除一條路；`topic/` 勾選後是封存。`--confirm`、`--confirm-archive` 都只接受 dry-run 清單出現過的路徑。

## 流程

### 1. 先 dry-run

先跑 `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/maigo_tidy.py`（想省 gh 呼叫就加 `--no-gh`），第一個動作永遠是 dry-run。
輸出一段一行、不用表格，路徑都是 repo root 相對的 `.maigo/…`，依
[`vim-friendly-artifacts`](https://github.com/Lee-W/maigo/blob/main/skills/vim-friendly-artifacts/SKILL.md)。
把「規則型動作」「需要你逐項勾選」「未登記」三段原樣給使用者看，不要自己改寫或合併清單。

### 2. 規則型動作：徵得一次同意

使用者看過清單、同意規則型動作之後，才跑 `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/maigo_tidy.py --apply`。
動手前腳本會把每個要動的路徑備份到 `.maigo/_internal/tidy/backup/<UTC ts>/`（相對 `.maigo/` 的原路徑），
備份完才開始搬；改寫用 tmp ＋ rename。回報備份目錄與每一筆結果。

### 3. 需要勾選的項目：逐項問

用 AskUserQuestion 逐項問，每一項都附上 dry-run 印出的判定依據。使用者對一整批說「應該都可以刪」不算逐項確認。
刪除類（delete-candidate、unregistered、`.maigo/.maigo/`）刪之前，再列出檔數與前幾個檔名讓使用者最後確認一次。

### 4. 只傳被勾的項目

只把使用者勾選的項目以 `--confirm <path>`（刪除、`topic/` 封存）或 `--confirm-archive <path>`（封存）傳入（路徑照 dry-run 印的 `.maigo/…` 原樣寫）：

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/maigo_tidy.py --apply --confirm .maigo/topic/foo
```

### 5. 還原

動錯了：把 `.maigo/_internal/tidy/backup/<ts>/` 底下的路徑複製回 `.maigo/` 的原位置即可。

## 範圍與限制

- 結案判定走 `gh pr view` / `gh issue view`，只認純數字 id；跨 repo 的 `<repo>-<n>` 查不到，列為「狀態查不到」。`gh` 失敗或離線時該項不動。
- 不碰 `board.md`、`_internal/board/`；board 的對帳與封存仍由 `/maigo:board` 負責。
- 命令與 skill 的改動要開新 session 才看得到。

## 收場

🌑 Mortis 一句結算（動了幾筆、還有幾筆待勾選、備份在哪），旁白依
[`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md)。例如：

> 🌑 Mortis：「點過名的，該留的留下了；沒點到的，還在原地。」
