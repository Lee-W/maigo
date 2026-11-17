# Work Board — 在 nvim 裡怎麼用（§6）

Loaded on demand by [`skills/work-board/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md) §6 — nvim 操作手冊（搜尋、gf、gx、勾選、dd）與 rewrite_note_paths 用法。
本檔內文原樣自 SKILL.md 搬出，章節編號（§1a、§3a 等）沿用原編號，SKILL.md 內仍以這些編號互相引用。

## 6. 在 nvim 裡怎麼用

真相層永遠是純 markdown 的 `.maigo/board.md`——agent 跟人都直接改它，不為排版
混入 HTML wrapper。**maigo 不提供任何呈現層，也不會建議你裝 nvim plugin**：
`.maigo/board.md` 就是最終產物，`:e` 開檔即讀即改。**沒有入口契約**：從 repo root、`cd .maigo` 之後或任何 cwd 開都行——
`.maigo` 內部的連結（索引行、細節檔筆記）都是檔案相對，`gf` 不依賴 cwd。唯一的例外是原始碼路徑（`src/x.py:12`）：
它維持 repo-root 相對，在 `.maigo` 裡開不了，要先 `:cd` 到 repo root（沒有被解決，只是寫明）。

本節是 [`vim-friendly-artifacts`](https://github.com/Lee-W/maigo/blob/main/skills/vim-friendly-artifacts/SKILL.md) 在 board.md 與 i/ 細節檔上的具體應用；
nvim 行為的前提與實測依據（Neovim 核心預設；實測涵蓋 repo root、`.maigo`、state 目錄與其他 cwd）都在那份規範。

1. **用 `/` 與 `gO` 在四個區之間移動**：四個 `## ` section 標題是純文字，`/我的下一件`、`/待我 review`、`/等別人`
   直接命中；filetype plugin 開啟時（一般預設）`gO` 會列出標題大綱。Neovim 預設**沒有** fold
   （實測 markdown 的 `foldmethod=manual`），所以 board 不依賴收合；自己設了 treesitter fold
   的人，四個 `## ` 標題會是邊界，那是你的設定，不是 maigo 的承諾。
2. **`/狀態詞` 搜尋**：狀態詞是純文字（`待 triage`、`CHANGES_REQUESTED`……），
   `/待送出` 之類直接命中；細節檔路徑內含編號（`i/9201.md`，在行尾），`/9201` 一樣命中對應行，命中後按 `$` 就停在路徑上。
3. **只找現在要看的 PR**：`/maigo:board --reviews`，看完報告後直接在 board 勾 `[x]`
   （或 `/maigo:board --reviewed <n>`），下次刷新就從待看清單移除；`--check` 只翻 checkbox，
   效果等同手勾。🐛/🔀 行的 `[x]` 仍只作學習訊號。
4. **細節檔路徑用 `$` 再 `gf` 跳過去**：索引行行尾的 `i/<slug>.md` 相對 board.md 所在目錄；
   `j`／`k` 移到某行後游標在行首（會落在 `1.` 上，`gf` 得到 E447），所以先按 `$` 跳到行尾（`/` 搜尋命中後也一樣），
   游標停在路徑上再 `gf`（Neovim 核心內建，不需 plugin）直接開那份細節檔，不受 cwd 影響
   （格式見 §1a）；看完 `<C-o>` 跳回 board.md 原本的位置。索引行不加反引號是行文法的
   格式慣例（§1），不是 `gf` 的限制。
5. **細節檔內 `gx` 開 GitHub**：真 URL 搬進了細節檔的「連結」那一行，游標移到該行 `gx`
   直接開瀏覽器到該 issue/PR（連結寫成 `<URL>` autolink：裸 URL 緊貼 `連結：` 的全形冒號時 `gx` 會連冒號一起取，
   `<URL>` 在無設定的 nvim 下取到乾淨的 URL）；「筆記」段落裡檔案相對的路徑
   （例：`../review/9301/review.md`）不論 cwd 在哪都 `gf` 可跳——前提是游標停在路徑字元上，且路徑獨立成行
   或包反引號、不緊貼中文／全形標點（緊貼時 `gf` 會把標籤一起當檔名，見
   [`vim-friendly-artifacts`](https://github.com/Lee-W/maigo/blob/main/skills/vim-friendly-artifacts/SKILL.md) 路徑規則第 6 條）；
   `檔案:行號` 的原始碼路徑用 `gF`，游標停在路徑部分。舊寫法 `.maigo/review/9301/review.md`
   只在 cwd 為 repo root 時可跳（在 `.maigo` 裡面開就解析不到）、`review/9301/review.md`（相對 `.maigo/`）從 `i/` 底下的檔案 `gf` 會找不到檔；
   報告正文裡指向 rubric 的路徑也一樣要寫檔案相對（同目錄的 `rubric.md`），`gh … --body-file .maigo/…` 這類要貼到 repo root 執行的指令字串則維持原樣、不是 `gf` 的對象；
   命令不會改寫既有筆記，要整理用 `python3 <maigo-root>/scripts/rewrite_note_paths.py <repo root>`（預設乾跑，印出改前改後整行與「未掃描：N」；
   `--apply` 才寫；詳見 `--help`）。
   範圍：`i/*.md` 細節檔（`## 判斷` 起）與 `review/<id>/`、`pr/<id>/` 底下的報告類檔案（`review.md`、`rubric.md`、`pr-comments.md`，
   整檔扣除 code fence、HTML 註解與 `pr-context-cache` 區段）；報告檔**只改解析後落在 `.maigo` 內且存在的路徑**，原始碼路徑一個字都不動；
   `draft.md`、`inline-comments.md`、`reply-draft.md`、`follow-up-issue.md` 等會貼到 GitHub 的草稿與其他未登記檔名不掃。
   script 只改「筆記引用檔案」形狀的路徑（行首、緊貼／接在中文字與全形標點之後、或接在 `Review report:` 這類英文冒號標籤之後）；前一個詞是其他 ASCII 的（指令、旗標、重導向、英文散文）不改並列為略過，寧可少改；它是啟發式，套用前仍請看乾跑清單。
6. **勾 `[x]` 觸發 ack 與 `--learn`**：把 `- [ ]` 或 `1. [ ]` 改成 `[x]` 存檔即完成（見 §4a、§5），
   不需要額外命令；下次 `/maigo:board` 刷新會 ack 該 report，並列出「(`[x]` 或 `🔖`) 且沒有 `🧠`」的項目。
7. **一行一項**：`/` 搜尋與 `dd` 刪除都以行為單位，board.md 的每一行對應一個 item，
   nvim 原生操作即可管理，不需要任何格式轉換或外部工具。**`dd` 刪掉的行不會再冒回來**：下次刷新
   把它寫進排除紀錄（§3a），除非你又被重新指名審那顆 PR。
