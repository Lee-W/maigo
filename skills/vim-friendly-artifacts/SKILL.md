---
name: vim-friendly-artifacts
description: This skill should be used whenever writing, templating or generating any human-read artifact under `.maigo/` (plan, run summary, review report, rubric, draft, pr-comments, reply draft, board.md and i/ detail files). It is the single source for the layout that makes them read and edit well in plain Neovim.
---

<!-- mkdocs-include-start -->

# Vim-friendly Artifacts

**Owner Agent**: orchestrator（寫入或交辦寫入 `.maigo/` 人讀產物時）

**Consumers**:

- [`agents/Tomori`](https://github.com/Lee-W/maigo/blob/main/agents/Tomori.md)（plan、triage rubric）
- [`teammate-flow` 的 run summary 範本](https://github.com/Lee-W/maigo/blob/main/skills/teammate-flow/references/run-summary-template.md)（summary）
- [`/maigo:review`](https://github.com/Lee-W/maigo/blob/main/commands/review.md)（review 報告、review draft）
- [`strict-review` 輸出模板](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/review-templates.md)（review rubric、報告骨架）
- [`github-reply-draft` 模板](https://github.com/Lee-W/maigo/blob/main/skills/github-reply-draft/references/comment-fetch-and-triage.md)（pr-comments、reply-draft）
- [`skills/work-board`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md)（board.md、i/ 細節檔）

使用者用編輯器（以 nvim 為例）直接開 `.maigo/` 底下的檔案來讀、來改。maigo 不蓋閱讀層、不建議裝 plugin，也不要求使用者為 maigo 在編輯器設定裡寫例外，所以「好讀」只能靠檔案本身是標準 markdown：通用 formatter 存檔不會改它、`gx`／`gf` 不靠設定就能用。這份 skill 是那個形狀的單一來源：各模板與產生器只放一行連結指到這裡，不重抄規則本文。

交付物預設落成使用者能用編輯器打開的檔案（也就是這份 skill 排版的 `.maigo/` 產物），不要把報告整份印在聊天裡——聊天輸出用完即棄。要貼去別處的內容（PR 留言、回覆草稿）另外放進 fenced block，依
[`copyable-deliverable`](https://github.com/Lee-W/maigo/blob/main/skills/copyable-deliverable/SKILL.md)；兩條規則疊加：檔案是來源，fenced block 是貼上面。

## 適用範圍

人讀產物的權威清單是 `scripts/artifact_path.py` 的 `_KNOWN_KINDS`，加上 Work Board（不在 `_KNOWN_KINDS` 裡）。各自的格式定義處：

- `plan`：[`agents/Tomori.md`](https://github.com/Lee-W/maigo/blob/main/agents/Tomori.md) 的輸出格式段
- `triage-rubric`：同檔的 triage-issue 模式段
- `summary`：[`run-summary-template.md`](https://github.com/Lee-W/maigo/blob/main/skills/teammate-flow/references/run-summary-template.md)，`/maigo:go`、`/maigo:team` 收尾由 orchestrator 寫；含三張純文字圖，畫法見下方「純文字圖」
- `review-rubric`：[`review-templates.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/review-templates.md) 的 rubric 骨架，檔頭夾著 `scripts/pr_context_cache.py` 產生的 cache 區塊
- `review`：`scripts/review_report.py` 的 `render_report` 產生檔頭，正文骨架在 `review-templates.md`
- `review-draft`：[`commands/review.md`](https://github.com/Lee-W/maigo/blob/main/commands/review.md) §4.5，整份會被 `gh pr review --body-file` 送上 GitHub
- `pr-comments`、`reply-draft`：[`comment-fetch-and-triage.md`](https://github.com/Lee-W/maigo/blob/main/skills/github-reply-draft/references/comment-fetch-and-triage.md) 的兩個模板
- `board.md`、`i/<slug>.md`：[`skills/work-board/references/format-spec.md`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/references/format-spec.md) §1、§1a，nvim 操作見 [`nvim-usage.md`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/references/nvim-usage.md)（§6）

不在範圍：`.maigo/_internal/` 與所有 jsonl／json 機器狀態檔，它們只給程式讀。

本規範只約束**新寫入**的檔案。`.maigo/` 被 gitignore、多為一次性產物，既有檔案不回溯改寫；review 報告與 rubric 的 cache 區塊、細節檔事實區會在下次發佈或刷新時自然換成新格式。讀回端（`board_sync`、`review_report`、`pr_context_cache`、`migrate_legacy_artifacts`）同時接受裸 URL 與 `<URL>`；筆記裡舊的路徑寫法（相對 `.maigo/` 或 repo-root 相對）不會被 refresh 或其他命令改寫，新舊混用可接受；要整理時用 `scripts/rewrite_note_paths.py`（預設乾跑、印出改前改後整行，確認後才 `--apply`，見路徑規則第 6 條）。

**保證的界線**：下列由 script 寫出、有測試鎖住——`board.md`、`i/<slug>.md` 的事實區與新建骨架（刷新時保留區只被壓掉 code fence 外的連續空行與純空白行（後接縮排 code block 的空行不動），其餘逐字保留）、`review.md` 檔頭、`rubric.md` 的 cache 區塊結構（欄位行、fence、marker 前後的空行）。cache 區塊裡 title、body、CI 狀態與 review thread／review／comment 的內容是 GitHub 原文逐字帶入，版面不保證（多行 body 會讓 formatter 在清單前補空行）。其餘（plan、`summary.md`、rubric 骨架、`review.md` 正文、`draft.md`、`inline-comments.md`、`pr-comments.md`、`reply-draft.md`）只靠範本約束，沒有機器擋，模型落筆時可能漂移；`scripts/review_report.py` 的 `publish` 不對正文做正規化，維持逐字寫入。

## 「預設可用」的前提

下面每一條 nvim 行為宣稱，都是在 Neovim 核心預設下實測的（NVIM v0.12.6，`-u NONE` 為最嚴基線，`path` 為預設的 `.,,`），涵蓋的 cwd 包含 repo root、`.maigo`（symlink）、state 真目錄與家目錄，不只 repo root；同目錄與跨目錄檔案相對寫法的 4 種寫法 × 4 種 cwd 矩陣見路徑規則第 1 條。`gO` 另外需要 filetype plugin 開啟，這是一般使用者的預設，`-u NONE` 下不成立。

使用者自己的 nvim 設定（`path`、`autochdir`、treesitter、fold）可能讓結果不同；規範只承諾預設下可用，不替使用者改設定。沒有實測的行為一律標「未確認」，不寫成規則的依據，也不宣稱其他編輯器的行為。

**不再有入口契約**：可以從 repo root、`cd .maigo` 之後、或任何其他 cwd 開 `.maigo` 裡的檔案——`.maigo` 內部的互連（細節檔、報告、rubric、board 索引行）都是**相對於檔案自己的位置**，`gf` 不依賴 cwd。唯一的限制是**原始碼路徑**（`commitizen/commands/bump.py:347`）：它維持 repo-root 相對，在 `.maigo` 裡面開檔時 `gf`／`gF` 開不了，要先 `:cd` 到 repo root。這沒有被解決，只是誠實寫明。

**不是 `gf` 對象的路徑**（維持 repo-root 相對，不要改成檔案相對）：要貼到 repo root 執行的 shell 指令字串（`gh pr review … --body-file .maigo/review/N/draft.md`）、script 印出給程式讀的 stdout（`rubric:`／`path:`）、`/maigo:tidy` 與對話裡印給使用者看的 `.maigo/…` 清單。這些是終端機輸出或指令參數，不是在 nvim 裡游標跳轉的目標。

## 版面規則

1. **一段一行，不手動斷行。** 理由：nvim 的 `wrap` 預設開啟，長行會自動折行顯示；改一個字不必重排整段，diff 也乾淨。review-draft 與 reply-draft 還會被貼上 GitHub，GitHub 留言把單一換行渲染成斷行，hard-wrap 的草稿貼過去會碎。條列一項一行，fenced code block 內容原樣。review 報告的 PR 摘要用 ```mermaid fenced block 畫改動前後圖，屬於 fenced code block，不違反 HTML 規則；在 nvim 裡是純文字，節點文字要自己讀得懂。
2. **不用 markdown 表格，改成 `- **欄位**：值` 條列或拆小節。** 理由：寬表格在 wrap 下整列折爛，補一個欄位要重排整列。唯一例外是逐字引用的既有表格，照原樣保留。
3. **用 `## ` 標題切段，標題字要夠具體、可被搜尋。** 理由：導覽靠 `/` 搜尋標題文字，以及 `gO` 大綱（實測：filetype plugin 開啟時，`gO` 在 markdown buffer 會列出標題；`-u NONE` 下沒有）。
4. **不要把導覽建立在 fold 上。** 理由：實測顯示預設的 `foldmethod=manual`、`foldexpr=0`，`## ` 標題不是 fold 邊界，沒有任何預設 fold；要 fold 得使用者自己設定。模板與說明文字不要寫「收合」「fold 邊界」當成產物的功能。
5. **不放目錄（TOC）。** 理由：純文字目錄會讓 `/標題字` 先命中目錄而不是章節本身；連結式目錄的 `#anchor` 跳轉未確認 nvim 預設支援（本次未實測），規範不依賴它。
6. **標題與清單前後各留一個空行，不留連續空行，closing fence 與緊接的 marker 之間留一個空行。** 理由：這是通用 markdown formatter 的 fixed point；版面已經是這個形狀，存檔就不會被改寫、diff 也不會出現只有空行的雜訊。鍵值檔頭行仍以空行隔開。

規則 1、2 的本文在 [`copyable-deliverable`](https://github.com/Lee-W/maigo/blob/main/skills/copyable-deliverable/SKILL.md)，這裡只補 nvim 側的理由，見下方「與 copyable-deliverable 的關係」。

## 純文字圖

產物裡需要畫圖（流程、因果、前後對照）時，用純文字圖（review 報告的 mermaid 圖是既有例外，見版面規則 1）。理由：nvim 不渲染圖，圖必須在原始檔裡就讀得懂，而且存檔後不會被 formatter 動。

- **一律放在 fenced code block 內，語言標 `text`。** 理由：fence 內容是 formatter 的不動點（rumdl 0.2.16 實測：fence 內的連續空行、行尾空白、非 ASCII 字元都不被改寫），圖不會因存檔而變形。
- **結構線只用 ASCII：`+ - | > < v ^`。** 不用 box-drawing 字元與 emoji。理由：box-drawing 在 Unicode 屬 East Asian Ambiguous，寬度可能因終端與字型而異（本 repo 未實測），emoji 同樣寬度不一；ASCII 在任何等寬字型下都是一格。
- **中文可以當標籤，但不可依賴中文字右邊的對齊。** 理由：中文字在等寬字型佔兩格，同一行中文字後面的字元位置會與純 ASCII 的行對不齊。要對齊的圖，標籤用 ASCII；中文標籤放行尾，或獨立成一行。
- **單行寬度以 80 個顯示寬度為上限**（ASCII 算 1、中文字算 2）。理由：超過會在一般視窗被 wrap 折斷，圖就爛了；規則 1 的「不手動斷行」只管散文，不管 fence 內的圖。
- **fence 內不留行尾空白。**
- 圖只畫實際發生的事，不為了版面好看補節點；數字（輪數、測試數）要與正文一致。

不加機器檢查：圖畫得不好只是品質下降，由範本與審查約束。

## HTML 規則與 marker 白名單

人讀區段**不放 HTML 元素**：不用 `<a id>`、`<details>`、`<summary>`、`<br>` 這類標籤。理由：nvim 不渲染 HTML，標籤只是多出來的雜訊行；原本靠 `<details>` 收合的內容，在 nvim 裡本來就不會收合。

唯一允許的 HTML 註解是 parser 依賴的 marker，以及下列登記過的佔位，每個都**獨佔一行**，位於檔頭、區塊邊界或檔尾：

- review 檔頭 metadata：以 `maigo-review:` 開頭、後接一行 JSON。owner：`scripts/review_report.py` 的 `_METADATA` 解析、`render_report` 的 metadata 行寫入、`acknowledge` 在標記「已看完」時改寫。下游 `scripts/board_sync.py` 與 `scripts/board_state.py` 經 `review_report.metadata()` 讀它。
- rubric 的 cache 區塊起訖：`pr-context-cache:start v1` 與 `pr-context-cache:end` 兩個 marker。owner：`scripts/pr_context_cache.py` 的 `CACHE_START`、`CACHE_END`；區塊內只認這兩個 marker 與 `- **欄位**: 值` 行。
- i/ 細節檔的手寫區佔位：內容為「手寫區」的註解。owner：`scripts/board_refresh.py` 的 `NEW_PRESERVED`（新建細節檔時寫入）。目前沒有程式讀它，是佔位用的既有格式。

新增 marker 必須同時登記進這份白名單，並寫出它的 owner 程式碼位置。理由：沒有登記的註解沒有人會維護，也沒有 parser 保證它存在。

**模板裡的說明性註解不放在 code block 內。** 寫給作者看的提示（例如「這欄必填」）改成 code block 外的散文。理由：code block 內的註解會被照抄進產物，變成沒有人負責的 HTML 雜訊。

另外，鍵值檔頭行（`**Source:**`、`**已看完：**` 等）的字面形狀被 `review_report.py` 的 `acknowledge()` 與舊報告判讀依賴，格式不動（`**Source:**` 的 URL 值寫成 `<URL>`）；它們之間以空行隔開，在 nvim 裡就是乾淨的獨立段落。

## 路徑規則

1. **指向其他 `.maigo/` 產物的路徑，用相對於檔案自己位置的路徑；指向原始碼維持 repo-root 相對。** 例：細節檔指向報告寫 `../review/9301/review.md`，報告指向細節檔寫 `../../i/<slug>.md`，同目錄寫裸檔名 `rubric.md`（不加 `./`）。理由（實測，nvim 0.12.6，`.maigo` 為 symlink）：同目錄裸檔名 `rubric.md`、`./rubric.md`、`../<自己目錄>/rubric.md` 與跨目錄 `../../review/2/x.md` 四種寫法，在 cwd 為 repo root、`.maigo`（symlink 進入）、state 真目錄、放了同名干擾檔的家目錄四種下，`gf` 全 16 格都開到檔案相對的那一份（`-u NONE` 與 `--clean` 兩輪皆同；同名干擾檔不會搶先，因為 `path` 的 `.` 是目前檔案所在目錄），所以選最短的裸檔名；使用者自己的設定未載入驗證，標未確認。另：`../review/x/review.md` 在 cwd 為 repo root、別處、state 真目錄三種下 `gf` 都開得到；repo-root 寫法 `.maigo/review/x/review.md` 只有 cwd 為 repo root 才開得到，相對 `.maigo/` 的 `review/x/review.md` 只有 cwd 為 state 真目錄才開得到。檔案相對路徑在封存同批搬移 `i/` 與 `review/` 後仍有效，repo-root 寫法則立刻失效。
2. **board.md 索引行的 `i/<slug>.md` 維持相對檔案所在目錄，不改，並放在行尾最後一欄。** 理由：預設 `path` 的 `.` 就是目前檔案所在目錄，board.md 在 `.maigo/` 第一層，`i/<slug>.md` 解得到；補充實測在 cwd 為 repo root 與 cwd 在別處兩種下都成立。放行尾是因為 `j`／`k` 移動後游標在行首（落在 `1.` 上，`gf` 得到 E447）：先按 `$` 游標就停在路徑上；路徑與前一字之間是單一半形空格，標題以全形標點或 emoji 結尾也不會黏住。
3. **要指到某一行時寫 `路徑:行號`，用 `gF` 跳。** 理由：實測 `scripts/x.py:3` 用 `gF` 開檔並落在第 3 行，用 `gf` 也開得了檔但落在第 1 行。
4. **反引號包住的路徑允許，不禁用。** 理由：實測游標在路徑字元上或開頭反引號上 `gf` 成立；只有游標停在結尾反引號時失敗（E446）。plan 與 review 大量使用反引號路徑，禁用成本高、收益為零。board 索引行維持不加反引號，是既有行文法與 parser 的格式慣例，不是 `gf` 的限制（行尾路徑不加反引號，`$` 後 `gf` 即成立）。
5. **外部 URL 一律寫成 `<URL>` autolink**（例：`- 連結：<https://github.com/o/r/pull/1>`、`- **PR**: <https://github.com/o/r/pull/1>`），不寫裸 URL、不藏進 `[文字](URL)`；文件裡的占位符寫成 `<PR URL>` 這類帶空格的形狀，避免與尖括號寫法混淆。理由（實測，nvim 0.12.6，無設定）：裸 URL 緊貼全形字元時 `gx` 會連全形字元一起取（`連結：https://example.com/a/b` 取到 `連結：https://example.com/a/b`，URL 後接全形逗號也會把逗號取進去），`<URL>` 在同樣版面下取到乾淨的 URL；`[文字](URL)` 在沒有 treesitter 時游標停在文字上會把文字當檔名。formatter 會把裸 URL 包成 `<URL>`，連 inline code 內的也是，所以讀回端兩種都要接受。
6. **路徑要嘛獨立成行（或獨立成一個清單項），要嘛包在反引號裡；路徑前後不得緊貼中文字或全形標點。** 例：``- ../review/9301/review.md`` 或 ``- 報告：`../review/9301/review.md`（舊）``，不要寫 `- 報告：../review/9301/review.md（舊）`。理由（實測，nvim 0.12.6 `-u NONE`）：大於等於 256 的字元一律算檔名字元，`報告：../review/1/review.md` 的 `<cfile>` 會變成含標籤的整串，開不到檔；路徑前面有空格（半形或全形）、或 ASCII 冒號加空格則正常；反引號、`<>`、markdown 連結寫法也正常。要加標籤時，標籤放在路徑後面並以空格隔開，或把路徑包反引號——反引號同時處理前後兩側緊貼，不必判斷要補空格還是移動標點。游標必須停在路徑字元上（停在清單符號 `1.`、標籤或行首會得到 E447）；`檔案:行號` 的原始碼路徑用 `gF`，游標停在路徑部分而不是行號數字上。script 寫出的細節檔事實區路徑都在反引號裡，有測試鎖住；既有筆記與報告的舊寫法（裸 `review/<id>/…`、`.maigo/…` 開頭、緊貼中文冒號的路徑）用 `scripts/rewrite_note_paths.py` 整理，預設乾跑，`--apply` 才寫；它掃 `i/*.md` 的 `## 判斷` 起與 `review/<id>/`、`pr/<id>/` 的 `review.md`／`rubric.md`／`pr-comments.md`，報告檔只改落在 `.maigo` 內的路徑（原始碼路徑不動），會貼到 GitHub 的草稿類檔案不掃。不要求任何 nvim 設定。

## 與 copyable-deliverable 的關係

[`copyable-deliverable`](https://github.com/Lee-W/maigo/blob/main/skills/copyable-deliverable/SKILL.md) 的「一段一行」與「不用表格」兩條，在這裡延伸到 `.maigo/` 所有人讀產物，不限於要貼去別處的 deliverable。規則本文仍只存在於 copyable-deliverable，這份 skill 不重抄；兩邊要的是同一件事，只是理由不同（貼上之後不碎、在 nvim 裡讀改不費力）。另立一套會讓同一條規則有兩份本文、日後漂移。

## 與 work-board §6 的關係

[`work-board` §6](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md) 是本規範在 board.md 與 i/ 細節檔上的具體應用（操作步驟、`gf`／`gx`／`/` 搜尋怎麼用）。§6 的 nvim 行為宣稱依本規範的實測為準；兩邊矛盾時以這裡為準並回頭修 §6。

## 明確不做

- 不裝、不建議任何 nvim plugin，不加任何呈現層（瀏覽器頁面、TUI、mkdocs serve）
- 不規定使用者的 nvim 設定
- 不動機器讀的 jsonl／json 與 `_internal/` 內容
- 不回溯改寫 `.maigo/` 既有產物
- 不加 hook：版面不合只是品質下降、人可自決，不該擋下整個 turn；程式產出的部分由 `tests/test_artifact_layout.py`、`tests/test_board_refresh.py`、`tests/test_board_sync.py`、`tests/test_review_report.py`、`tests/test_pr_context_cache.py` 鎖住（界線見「適用範圍」的保證的界線）
