# 在編輯器裡讀 Work Board 與 `.maigo` 產物

Maigo 把 plan、review 報告、草稿與 Work Board 都寫成 `.maigo/` 底下的 markdown 檔，
你用編輯器直接開來讀、來改。這份文件說明怎麼進去、怎麼在檔案之間跳轉、哪些地方可以手改，
以及哪些事做不到。讀完約 5 分鐘。

按鍵以 Vim／Neovim 為例，實測條件是 Neovim 0.12.6 的預設設定（`nvim --clean`）。
你自己改過 `path`、`autochdir` 之類的設定時，行為可能不同。其他編輯器沒有測過。

## 1. 進入

`.maigo` 預設是 repo root 裡的 symlink，指向本機集中的 state 目錄（SessionStart hook 會建，見 [集中儲存](../reference/state-storage.md)）。
入口是 `board.md`，它要先跑過 `/maigo:board` 才會存在（在 Claude Code 裡執行）。

```bash
nvim .maigo/board.md
```

從 repo root 開，或先 `cd .maigo` 再開，都可以。`.maigo` 內部的連結都是**相對於檔案自己的位置**，
`gf` 不依賴你當下的工作目錄。

## 2. board 長什麼樣

`board.md` 固定四個 `## ` 區，由上到下：

- `🎯 我的下一件`：你自己的 PR 與你在處理的 issue，編號清單，第 1 行就是下一件事
- `👀 待我 review`：輪到你審的別人的 PR，編號清單
- `⏳ 等別人`：球不在你手上，只是查閱
- `✅ 最近結案`：已 merged／closed／放棄的項目，行裡多一個結案日期 `MM-DD`，過一段時間會被清掉

一行就是一個項目：編號與 checkbox、類型 emoji（🐛 issue、🔀 你的 PR、👀 在審的 PR）、狀態詞、`@作者`、標記、
結果或動作、規模、` — `、標題，**行尾是細節檔的路徑**。標記的意思：`💤` 逾 14 天沒更新，`🔖` 待學習盤點，`🧠` 已學習盤點（見第 4 節的 checkbox）。例：

```markdown
1. [ ] 👀 待送出 @someone 💤 NEEDS_CHANGES +68/-1 — fix(parser): handle empty config i/4821.md
2. [x] 👀 ↩︎ 回你的球 @someone 上次 NEEDS_CHANGES +1.2k/-340 — feat(cache): reuse lookups across runs i/4822.md
```

以上是範例，帳號、標題與編號都是虛構的。

👀 區的行在 `@作者` 與標記之後、規模之前，顯示**本地 review 的結論**（`APPROVE`、`APPROVE_WITH_NITS`、`NEEDS_CHANGES`、`BLOCKED`），不是要你做的動作。
狀態是 `↩︎ 回你的球` 時會帶 `上次` 前綴——那是上一版 head 的結論，不是現況。沒有本地報告就什麼都不顯示。
完整行文法與狀態詞表見 [work-board skill](../skills/work-board.md)。

每個項目對應一份**細節檔** `.maigo/i/` 底下的檔案：最上面是事實區（標題與連結、規模、下一步，以及該項目在 `review/`、`pr/`、`issue/` 底下所有檔案的清單，由刷新重寫），
接著是 `## 判斷`（一句「你現在要決定什麼」），最後是 `## 筆記`（你自己的筆記）。

## 3. 跳轉

下面都是編輯器原生行為，不需要任何 Maigo 專用的設定或 plugin。

- **board → 細節檔**：移到該行，按 `$` 讓游標落在行尾的路徑上，再按 `gf`。看完用 `<C-o>` 回到 board 原本的位置。
- **細節檔 → 報告、草稿**：事實區的 `相關檔案` 清單列出該項目的所有產物，游標停在路徑上按 `gf`（檔名含空白或括號的檔會列出，但 `gf` 跳不過去，改用 `:e`）。路徑是相對於該細節檔自己的位置（例如 `../review/4822/review.md`）。
- **報告 → 同資料夾的 rubric 等**（rubric 是審查用的檢查清單）：同樣 `gf`，同目錄的檔案只寫檔名（例如 `rubric.md`）。
- **開 GitHub**：外部網址寫成 `<URL>`，游標在上面按 `gx`。細節檔的 `連結` 那一行就是這樣寫的。
- **在 board 裡找東西**：四個區標題與狀態詞都是純文字，`/待送出`、`/等別人`、`/4822` 直接命中；`gO` 在 filetype plugin 開啟時會列出標題大綱。

**游標必須停在路徑上。** `gf` 取的是游標所在的那一串「檔名字元」，所以路徑不能緊貼中文字或全形標點，否則會連它們一起取走而開不到檔。
`j`／`k` 會保留原本的欄位，游標常停在行首的 `1.` 上，這時 `gf` 只會得到 `E447`。
不管游標在那一行的哪裡，先按 `$` 就會落在行尾的路徑上，所以 board 上永遠是先 `$` 再 `gf`。

## 4. 編輯

- **細節檔的 `## 筆記`**：這是你的。`/maigo:board` 的刷新會保留細節檔從 `## 判斷` 起到檔尾的全部內容，
  但 `/maigo:address-comments` 這類命令會寫入或替換 `## 判斷` 那一節，所以要留的內容寫在 `## 筆記`。
  不要在 `## 判斷` 之前自己加 `## ` 標題，刷新會報錯。你在筆記裡加的路徑，要讓 `gf` 能用，就獨立成一行（或一個清單項），或用反引號包起來。
- **checkbox**：👀 行的 `[x]` 表示「這份報告我看完了」，下次刷新會標記已看，有新 commit 或新留言時會自動取消勾；勾上時會加 `🔖`（待學習盤點）。
  🐛／🔀 行的 `[x]` 表示「這項我親自處理過」。被勾的項目可以用 `/maigo:board --learn` 做學習盤點（從你處理過的項目萃取慣例，候選要經你確認才會寫進記憶），盤點完加上 `🧠`。
- **刪掉 board 的一列**：在 board 上用 `dd` 刪掉那一行，之後的刷新不會再補回來，除非你又被重新指名審那顆 PR。
- **路徑是行的最後一個字**：不要在行尾路徑後面追加文字，否則下次刷新會回報該行格式錯誤並停下。
- **存檔時自動格式化**：`board.md` 與細節檔的事實區由 script 產生，版面是常見 markdown formatter 的不動點，存檔時自動格式化不會改它們。
  報告正文與 agent 寫的其他檔只靠範本約束，沒有機器保證，formatter 可能會調整這些部分。
- **刷新會換掉檔案**：`/maigo:board` 以換檔方式寫入 `board.md`。在 Neovim 預設設定下，buffer 沒改過時，下次 Neovim 檢查檔案（例如 `:checktime`）會自動重新載入，沒有提示；你已經改了 buffer 還沒存時，會出現 W12 警告並保留你的修改，存檔時還會再警告一次。刷新期間不要存檔，等它跑完先 `:e` 重新載入再編輯。

## 5. 刷新與重審

- `/maigo:board`：重抓 GitHub 狀態、重算排序、更新細節檔的事實區；已結案的項目依保留期老化清除
  （別人的 PR 3 天、自己的 7 天、最多 10 行）。細節見 [`/maigo:board`](../commands/board.md)。
- `/maigo:review`：重審同一顆 PR 時，命令要求 agent 以既有的 `draft.md`、`inline-comments.md`、`rubric.md` 為底稿用 Edit 修改，
  仍成立的 finding 逐字保留，新的附加在後，要移除的先在對話列出。這是給 agent 的指示，不是程式強制的保證：
  你手改過的草稿，重審後請自己看一眼 diff。細節見 [`/maigo:review`](../commands/review.md)。

## 6. 做不到的事

- **原始碼路徑**：報告裡的 `src/pkg/mod.py:12` 是相對於 repo root 的，在 `.maigo` 裡 `gf` 開不了。
  要開就先把編輯器的工作目錄換到 repo root（Vim 是 `:cd`），用 `gF` 可以跳到行號，游標要停在路徑部分而不是行號數字上。
  審別人的 PR 時，那個行號對應的是審查當下的 PR head，不一定是你本機 checkout 的版本。
- **貼到 shell 的指令**：「下一步」裡的 `gh … --body-file .maigo/…` 是要貼到 repo root 執行的指令，不是跳轉的對象。
- **LSP 的跳到定義**（常被映射到 `gd`，實際行為取決於你的編輯器設定）：用 marksman 測過，裸路徑不會被解析成可跳轉的目標，
  寫成 markdown 連結才會；Maigo 的路徑是裸路徑。其他 LSP 沒測過。所以跳轉請用 `gf`，不要依賴 LSP 的跳到定義。
- **舊筆記裡的舊寫法路徑**：較早寫下的筆記與報告裡可能有 `review/<id>/…`、`.maigo/review/…`，或緊貼中文冒號的路徑，`gf` 會失效。
  [`scripts/rewrite_note_paths.py`](https://github.com/Lee-W/maigo/blob/main/scripts/rewrite_note_paths.py) 可以整理。
  這個 script 在 Maigo 的安裝目錄裡（用 `claude --plugin-dir` 啟動時，就是你傳給它的那個目錄；用 marketplace 安裝時的目錄位置文件沒寫，未確認，請看你的 plugin 管理設定），不在你的 repo：

  ```bash
  # 乾跑（預設）：印出每一處的改前改後整行與略過清單，不寫檔
  python3 <Maigo 安裝目錄>/scripts/rewrite_note_paths.py <你的 repo 根目錄>
  # 確認清單沒問題後才真的寫檔
  python3 <Maigo 安裝目錄>/scripts/rewrite_note_paths.py --apply <你的 repo 根目錄>
  ```

  不給 repo 路徑時，它改讀 `--repo-list` 指定的檔（預設 `~/.config/maigo/repos.txt`，一行一個絕對路徑）；
  這個檔不會自動建立，不存在或是空的就以 exit 1 結束，所以直接傳 repo 路徑最省事。
  它會掃細節檔 `## 判斷` 起的內容，以及 `review/<id>/`、`pr/<id>/` 底下的 `review.md`、`rubric.md`、`pr-comments.md`；
  只改目標檔確實存在的 `.maigo` 內部路徑，不碰會貼到 GitHub 的草稿檔。英文句子裡的路徑會保守略過，所以套用前先看乾跑清單。
  報告檔裡的原始碼路徑不動；細節檔筆記裡緊貼中文的原始碼路徑，在該檔於 repo root 底下實際存在時，只會被加上反引號，路徑本身不變。
  套用期間不要同時編輯這些檔。

## 7. 為什麼這樣設計

設計目標是不要求你為 Maigo 改編輯器設定：產物只用標準 markdown 與相對路徑，Maigo 不提供閱讀層，也不要你裝 plugin。
實測只在 Neovim 做過（0.12.6，`nvim --clean` 預設設定）。理論上，任何有「開啟游標下檔案」功能的編輯器都適用，但沒有實測。
版面規則（一段一行、不用表格、連結寫法）的單一來源是
[`vim-friendly-artifacts`](../skills/vim-friendly-artifacts.md)；產物的種類與落點見 [Artifacts reference](../reference/artifacts.md)。
