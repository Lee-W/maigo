# Harness Discipline — Shell and Tool Gotchas

Loaded on demand by [`skills/harness-discipline/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/harness-discipline/SKILL.md) —
兩組「工具的失敗不長得像失敗」的坑：一個是指令根本沒跑卻像「查無結果」，一個是驗到的
根本不是實際在跑的那一份。Read this file when 你要動態組指令參數、要拿 shell 輸出當
「沒有」的證據，或要驗證一個依賴本地開發中套件的專案。

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
