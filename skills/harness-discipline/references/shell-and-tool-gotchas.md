# Harness Discipline — Shell and Tool Gotchas

Loaded on demand by [`skills/harness-discipline/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/harness-discipline/SKILL.md) —
五組「工具的失敗不長得像失敗」的坑：指令根本沒跑卻像「查無結果」、驗到的根本不是實際在跑
的那一份、heredoc 餵錯指令而掛住、zsh 的 `path` 變數蓋掉 `PATH`、profile alias 讓檔案
操作與量測靜默失效。Read this file when 你要動態組指令參數、要拿 shell 輸出當「沒有」
的證據、要驗證一個依賴本地開發中套件的專案，或要在 shell 裡寫迴圈、heredoc、檔案替換。

---

## 1. 含 glob 字元的參數一律加引號（zsh 的 `nomatch`）

**規則**：傳給指令的參數只要含 `*` `?` `[` `]`，一律加引號。

**理由**：zsh 預設在 glob 匹配不到時**報錯並中止整條命令**（`nomatch`），不是像 bash
那樣原樣傳下去。錯誤訊息長這樣：

```text
(eval):1: no matches found: --include=*.ext
```

這行的意思**不是**「grep 沒找到東西」，而是「grep 根本沒被執行」。把它讀成「查無結果」
是最貴的失誤。

| 寫法 | 問題 | 改法 |
|------|------|------|
| `grep -r --include=*.ext pat dir` | `*.ext` 被 shell 先展開 | `--include='*.ext'` |
| `gh api repos/x/y/git/trees/HEAD?recursive=1` | `?` 是單字元 glob | 整個 URL 加引號 |
| `ls dir/prefix* 2>/dev/null` | 展開失敗發生在 shell 階段，`2>/dev/null` 擋不住 | `ls 'dir/prefix*'`，或改用 `find` |

**怎麼套用**：

1. 動態組出來的參數（副檔名 pattern、URL query string）預設就加引號。
2. 看到 `no matches found:` 先認出「這條命令沒跑」，不要當成「沒有結果」。
3. 用 `&&` 串接的命令鏈，前面一條這樣掛掉會讓後面全部不執行——別讓「後面沒跑」被誤讀成
   「後面沒事」。

### 同源：zsh 不對未加引號的變數做 word splitting

bash 會依 `IFS` 把未加引號的變數拆成多個字，**zsh 預設不會**。所以 bash 慣用的
`set -- $pair` 之類寫法在 zsh 會靜靜地壞掉：整個變數成為單一參數，下游收到黏成一串的值，
症狀看起來像下游服務出錯（例如 HTTP 400）。

**怎麼套用**：多欄位資料改用陣列，或直接改用 Python 處理，省下引號地獄；驗證 shell 腳本
時印出拆分後的每個欄位，確認真的被拆開。

## 2. 驗證的是不是實際在跑的那一份

**規則**：宣稱「修好了／驗過了」之前，先確認你驗的是使用者實際會執行的那一份——PATH 上的
executable、實際載入的套件位置、長駐程式的目前 process——而不是工作樹裡的那一份。

**怎麼套用**：

- 修改本機 CLI 後，核對 PATH 上實際執行的 executable 與安裝來源；若是長駐 TUI／daemon，
  重啟後再驗。只測工作樹，不能說「使用者目前跑的版本已生效」。
- 依賴本地 editable 套件的專案，開工第一件事確認載到哪一份：

  ```bash
  uv run --no-sync python -c "import pkg; print(pkg.__file__)"
  ```

  印出的路徑要是開發目錄（`<local-pkg-path>`），不是 `.venv/`。

### `uv run` 會無聲換掉 editable install

**現象**：uv 專案模式下，不帶 `--no-sync` 的 `uv run` 會先依 `uv.lock` re-sync 環境，把
editable install 換回 lock 裡的發布版，沒有任何警告。

**為什麼貴**：症狀不會指向真正的原因。乾淨的 HEAD 上 build 突然炸掉，錯誤訊息看起來像
schema／資料問題，實際上是本地套件被換成缺少新功能的發布版。最陰險的觸發點是 pre-commit
hook 的 `entry: uv run ...`——每 commit 一次就洗掉一次環境，`git diff` 卻什麼都看不出來。

**兩條防法**：

1. 所有指令一律加 `--no-sync`，包含 pre-commit 的 `entry:`。CI 若在跑 hook 前已 `uv sync`，
   略過 sync 沒有代價——先確認 CI 順序。
2. `uv pip install -e <local-pkg-path>` 裝完立刻 `git checkout -- pyproject.toml uv.lock`。
   它會把本機絕對路徑回寫進 `[tool.uv.sources]` 並改 lock；路徑進 repo 會讓 CI 拉不到；
   repo 若有 guard，通常也只在該檔被 stage 時才擋，忘了還原就等著被下次 `git add` 帶走。

## 3. heredoc 只餵給複合指令裡的最後一個指令

**規則**：要餵 stdin 的指令（`git commit -F -`、`psql -f -`、`kubectl apply -f -`）獨占
一次 Bash 呼叫，heredoc 緊接在**它自己**後面。

**理由**：複合指令（`a && b; c`）尾端的 `<<'EOF'` 只會餵給**最後一個**指令。寫成
`git add X && git commit -F - > log 2>&1; git status <<'EOF' ... EOF`，commit 讀不到
stdin，無聲掛住直到 timeout，被移進背景後還得手動停掉。掛住期間若沒留下半成品，那是運氣，
不是設計。

**怎麼套用**：

1. 讀 stdin 的指令一次一個呼叫，驗證輸出的指令另開一次。
2. 呼叫掛住時先停掉它，再用唯讀指令（`git log -1`、`git status`）確認有沒有留下半成品，
   不要直接重跑同一條。

## 4. zsh 的 `path` 變數綁定 `PATH`

**規則**：zsh 的迴圈變數與賦值別用 `path`（也避開 `cdpath`、`fpath`、`manpath`、
`module_path`），改用 `dir`、`file`、`wt` 之類的名稱。

**理由**：`path` 是與 `PATH` 綁定的特殊陣列。`while read -r path x; do ...` 或
`for path in ...` 會把 `PATH` 蓋成單一路徑，之後同一段腳本的 `wc`、`tr`、`git` 全部
`command not found`。危險處在於其他欄位會「看起來正常地」變成空值或預設字串（例如每個
branch 都顯示「沒有對應 PR」），把假結果當成事實回報。

**怎麼套用**：腳本輸出出現任何 `command not found` 或 `(eval):` 開頭的錯誤，整輪結果作廢
重跑，不得只挑能用的欄位。

## 5. profile alias 讓檔案操作與量測靜默失效

**規則**：Bash 工具的 shell 會載入使用者 profile，其中的 alias 會改變指令行為。任何
「會改檔」或「結果會當證據」的指令，用 `/bin/<cmd>` 呼叫，並在下一步前確認效果真的發生。

**理由**：每種 alias 的失敗方式都不同，沒有單一症狀可以盯：

- **`cp`／`mv` 被換成互動式**（`-i`）：`cp` 印出 `not overwritten` 卻 **exit 0**，什麼
  都沒複製；`mv` 在沒有 tty 時卡在確認提示，整個呼叫 timeout。`cp -f` 擋不住，alias 的
  `-i` 會贏。後果是還原式實驗（改壞 → 測試 → 還原）的「還原」其實沒發生，前後兩次量的是
  同一份檔案，得到一模一樣的假綠；或卡死時檔案停在被改壞的狀態。
- **`cd` 被換成別的導航工具**：目標不在它的資料庫時印出「沒有匹配」，但**不換目錄**。
  `cd X && cmd` 安全（`&&` 短路），單獨一行的 `cd X` 之後接的指令會在原本的目錄執行，輸出
  看起來完全正常——可能對錯的工作樹做 checkout，或量到錯的環境。
- **`df`／`cat` 被換成參數不相容的替代品**：`df -h /` 印出替代品的用法說明、`cat -v` 回
  「unexpected argument」。不是掛住也不是錯誤結論，只是沒回答問題，容易誤以為底層查詢本身
  壞了。

**怎麼套用**：

1. 覆寫／移動檔案用 `/bin/cp -f`、`/bin/mv -f`；看原始位元組用 `/bin/cat -v`；查磁碟用
   `/bin/df -h`。
2. 不要用 `cd` 指向工作樹：git 用 `git -C <absolute>`，其他指令用絕對路徑；結論取決於「在
   哪個樹跑」時，前後各印一次 `git rev-parse --short HEAD`。
3. 替換或還原檔案後，用 checksum、`git status --porcelain` 或 `git diff --stat` 確認效果
   真的發生，不採信「指令沒報錯」。
4. 呼叫掛住時先讀 harness 給的 interim output 看卡在哪，再判斷；不要重試同一條指令。

相關：與本檔第 1 節同族——指令回報成功、或回報了*某個東西*，卻沒有做到或沒有回答你問的事。

## 6. 大型 CI job 日誌：用 `gh api`，別用 `gh run view --log-failed`

**現象**：`gh run view <run> --job <id> --log-failed` 抓大型 job 日誌（上萬行）會先卡到被
harness 丟背景，最後曾觀察到回 `failed to get run log: stream error: CANCEL`（視情況而異）——exit 0、檔案只有那一行
錯誤，容易被誤當成日誌。

**做法**：

1. `gh pr checks <PR>` 取 job URL，尾段即 job id。
2. `gh api --allow-escape-sequences repos/<owner>/<repo>/actions/jobs/<job_id>/logs 2>&1 | sed 's/\x1b\[[0-9;]*m//g' > <scratchpad>/<id>.log`
   （不加旗標會因含終端跳脫字元被拒，exit 1、檔案為空）。
3. 先 `wc -l` 確認不是單行錯誤，再 grep 失敗行（如 `Z FAILED `、`Failed$|hook id`）並依測試名定位
   traceback。遇到 CANCEL 就換路，不要重試同一條指令。
