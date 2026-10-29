---
name: vim-friendly-artifacts
description: This skill should be used whenever writing, templating or generating any human-read artifact under `.maigo/` (plan, review report, review rubric, review draft, pr-comments, reply draft, triage rubric, board.md and its i/ detail files). It is the single source for the layout those files follow so they read and edit well in plain Neovim with no plugin - one paragraph per line, no tables, no HTML outside a marker whitelist, repo-root-relative paths, bare URLs.
---

<!-- mkdocs-include-start -->

# Vim-friendly Artifacts

**Owner Agent**: orchestrator（寫入或交辦寫入 `.maigo/` 人讀產物時）

**Consumers**:

- [`agents/Tomori`](https://github.com/Lee-W/maigo/blob/main/agents/Tomori.md)（plan、triage rubric）
- [`/maigo:review`](https://github.com/Lee-W/maigo/blob/main/commands/review.md)（review 報告、review draft）
- [`strict-review` 輸出模板](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/review-templates.md)（review rubric、報告骨架）
- [`github-reply-draft` 模板](https://github.com/Lee-W/maigo/blob/main/skills/github-reply-draft/references/comment-fetch-and-triage.md)（pr-comments、reply-draft）
- [`skills/work-board`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md)（board.md、i/ 細節檔）

使用者用 nvim 直接開 `.maigo/` 底下的檔案來讀、來改。maigo 不蓋閱讀層、不建議裝 plugin，所以「好讀」只能靠檔案本身的形狀。這份 skill 是那個形狀的單一來源：各模板與產生器只放一行連結指到這裡，不重抄規則本文。

交付物預設落成使用者能用編輯器打開的檔案（也就是這份 skill 排版的 `.maigo/` 產物），不要把報告整份印在聊天裡——聊天輸出用完即棄。要貼去別處的內容（PR 留言、回覆草稿）另外放進 fenced block，依
[`copyable-deliverable`](https://github.com/Lee-W/maigo/blob/main/skills/copyable-deliverable/SKILL.md)；兩條規則疊加：檔案是來源，fenced block 是貼上面。

## 適用範圍

人讀產物的權威清單是 `scripts/artifact_path.py` 的 `_KNOWN_KINDS`，加上 Work Board（不在 `_KNOWN_KINDS` 裡）。各自的格式定義處：

- `plan`：[`agents/Tomori.md`](https://github.com/Lee-W/maigo/blob/main/agents/Tomori.md) 的輸出格式段
- `triage-rubric`：同檔的 triage-issue 模式段
- `review-rubric`：[`review-templates.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/review-templates.md) 的 rubric 骨架，檔頭夾著 `scripts/pr_context_cache.py` 產生的 cache 區塊
- `review`：`scripts/review_report.py` 的 `render_report` 產生檔頭，正文骨架在 `review-templates.md`
- `review-draft`：[`commands/review.md`](https://github.com/Lee-W/maigo/blob/main/commands/review.md) §4.5，整份會被 `gh pr review --body-file` 送上 GitHub
- `pr-comments`、`reply-draft`：[`comment-fetch-and-triage.md`](https://github.com/Lee-W/maigo/blob/main/skills/github-reply-draft/references/comment-fetch-and-triage.md) 的兩個模板
- `board.md`、`i/<slug>.md`：[`skills/work-board`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md) §1、§1a，nvim 操作見 §6

不在範圍：`.maigo/_internal/` 與所有 jsonl／json 機器狀態檔，它們只給程式讀。

本規範只約束**新寫入**的檔案。`.maigo/` 被 gitignore、多為一次性產物，既有檔案不回溯改寫；review 報告與 rubric 的 cache 區塊會在下次發佈或刷新時自然換成新格式。

## 「預設可用」的前提

下面每一條 nvim 行為宣稱，都是在 Neovim 核心預設、cwd 為 repo root 下實測的（NVIM v0.12.6，`-u NONE` 為最嚴基線，`path` 為預設的 `.,,`）。`gO` 另外需要 filetype plugin 開啟，這是一般使用者的預設，`-u NONE` 下不成立。

使用者自己的 nvim 設定（`path`、`autochdir`、treesitter、fold）可能讓結果不同；規範只承諾預設下可用，不替使用者改設定。沒有實測的行為一律標「未確認」，不寫成規則的依據。

## 版面規則

1. **一段一行，不手動斷行。** 理由：nvim 的 `wrap` 預設開啟，長行會自動折行顯示；改一個字不必重排整段，diff 也乾淨。review-draft 與 reply-draft 還會被貼上 GitHub，GitHub 留言把單一換行渲染成斷行，hard-wrap 的草稿貼過去會碎。條列一項一行，fenced code block 內容原樣。
2. **不用 markdown 表格，改成 `- **欄位**：值` 條列或拆小節。** 理由：寬表格在 wrap 下整列折爛，補一個欄位要重排整列。唯一例外是逐字引用的既有表格，照原樣保留。
3. **用 `## ` 標題切段，標題字要夠具體、可被搜尋。** 理由：導覽靠 `/` 搜尋標題文字，以及 `gO` 大綱（實測：filetype plugin 開啟時，`gO` 在 markdown buffer 會列出標題；`-u NONE` 下沒有）。
4. **不要把導覽建立在 fold 上。** 理由：實測顯示預設的 `foldmethod=manual`、`foldexpr=0`，`## ` 標題不是 fold 邊界，沒有任何預設 fold；要 fold 得使用者自己設定。模板與說明文字不要寫「收合」「fold 邊界」當成產物的功能。
5. **不放目錄（TOC）。** 理由：純文字目錄會讓 `/標題字` 先命中目錄而不是章節本身；連結式目錄的 `#anchor` 跳轉未確認 nvim 預設支援（本次未實測），規範不依賴它。

規則 1、2 的本文在 [`copyable-deliverable`](https://github.com/Lee-W/maigo/blob/main/skills/copyable-deliverable/SKILL.md)，這裡只補 nvim 側的理由，見下方「與 copyable-deliverable 的關係」。

## HTML 規則與 marker 白名單

人讀區段**不放 HTML 元素**：不用 `<a id>`、`<details>`、`<summary>`、`<br>` 這類標籤。理由：nvim 不渲染 HTML，標籤只是多出來的雜訊行；原本靠 `<details>` 收合的內容，在 nvim 裡本來就不會收合。

唯一允許的 HTML 註解是 parser 依賴的 marker，以及下列登記過的佔位，每個都**獨佔一行**，位於檔頭、區塊邊界或檔尾：

- review 檔頭 metadata：以 `maigo-review:` 開頭、後接一行 JSON。owner：`scripts/review_report.py:23` 解析（`_METADATA`）、`:174` 寫入、`:295` 在標記「已看完」時改寫。下游 `scripts/board_sync.py` 與 `scripts/board_state.py` 經 `review_report.metadata()` 讀它。
- rubric 的 cache 區塊起訖：`pr-context-cache:start v1` 與 `pr-context-cache:end` 兩個 marker。owner：`scripts/pr_context_cache.py:58-59`（`CACHE_START`、`CACHE_END`）；區塊內只認這兩個 marker 與 `- **欄位**: 值` 行。
- i/ 細節檔的手寫區佔位：內容為「手寫區」的註解。owner：`scripts/board_refresh.py:55`（`NEW_PRESERVED`，新建細節檔時寫入）。目前沒有程式讀它，是佔位用的既有格式。

新增 marker 必須同時登記進這份白名單，並寫出它的 owner 程式碼位置。理由：沒有登記的註解沒有人會維護，也沒有 parser 保證它存在。

**模板裡的說明性註解不放在 code block 內。** 寫給作者看的提示（例如「這欄必填」）改成 code block 外的散文。理由：code block 內的註解會被照抄進產物，變成沒有人負責的 HTML 雜訊。

另外，鍵值檔頭行（`**Source:**`、`**已看完：**` 等）的字面形狀被 `review_report.py` 的 `acknowledge()` 與舊報告判讀依賴，格式不動；它們之間以空行隔開，在 nvim 裡就是乾淨的獨立段落。

## 路徑規則

1. **新寫的路徑一律用 repo root 相對，連指向其他 `.maigo/` 產物也一樣：寫 `.maigo/review/<id>/review.md`，不寫 `review/<id>/review.md`。** 理由：在 cwd 為 repo root、預設 `path` 下實測，從 `.maigo/i/` 底下的檔案游標停在相對 `.maigo/` 的 `review/9301/review.md` 上按 `gf` 得到 E447 找不到檔，改寫成 `.maigo/review/9301/review.md` 則成立。相對 `.maigo/` 的路徑只在檔案正好位於 `.maigo/` 第一層時才解得到（預設 `path` 的 `.` 是目前檔案所在目錄，由此推得）。
2. **board.md 索引行的 `i/<slug>.md` 維持相對檔案所在目錄，不改。** 理由：預設 `path` 的 `.` 就是目前檔案所在目錄，board.md 在 `.maigo/` 第一層，`i/<slug>.md` 解得到；補充實測在 cwd 為 repo root 與 cwd 在別處兩種下都成立。
3. **要指到某一行時寫 `路徑:行號`，用 `gF` 跳。** 理由：實測 `scripts/x.py:3` 用 `gF` 開檔並落在第 3 行，用 `gf` 也開得了檔但落在第 1 行。
4. **反引號包住的路徑允許，不禁用。** 理由：實測游標在路徑字元上或開頭反引號上 `gf` 成立；只有游標停在結尾反引號時失敗（E446）。plan 與 review 大量使用反引號路徑，禁用成本高、收益為零。board 索引行維持不加反引號，是既有行文法與 parser 的格式慣例，不是 `gf` 的限制。
5. **外部 URL 寫裸 URL，放在 `連結：<url>` 或 `- **PR**: <url>` 這類行內，不藏進 `[文字](url)`。** 理由：實測 `gx` 對裸 URL 在有無 treesitter 兩種情境都解到 URL；`[文字](url)` 在沒有 treesitter 時游標停在文字上會把文字當檔名。

## 與 copyable-deliverable 的關係

[`copyable-deliverable`](https://github.com/Lee-W/maigo/blob/main/skills/copyable-deliverable/SKILL.md) 的「一段一行」與「不用表格」兩條，在這裡延伸到 `.maigo/` 所有人讀產物，不限於要貼去別處的 deliverable。規則本文仍只存在於 copyable-deliverable，這份 skill 不重抄；兩邊要的是同一件事，只是理由不同（貼上之後不碎、在 nvim 裡讀改不費力）。另立一套會讓同一條規則有兩份本文、日後漂移。

## 與 work-board §6 的關係

[`work-board` §6](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md) 是本規範在 board.md 與 i/ 細節檔上的具體應用（操作步驟、`gf`／`gx`／`/` 搜尋怎麼用）。§6 的 nvim 行為宣稱依本規範的實測為準；兩邊矛盾時以這裡為準並回頭修 §6。

## 明確不做

- 不裝、不建議任何 nvim plugin，不加任何呈現層（瀏覽器頁面、TUI、mkdocs serve）
- 不規定使用者的 nvim 設定
- 不動機器讀的 jsonl／json 與 `_internal/` 內容
- 不回溯改寫 `.maigo/` 既有產物
- 不加 hook：版面不合只是品質下降、人可自決，不該擋下整個 turn；程式產出的部分（review 檔頭、cache 區塊）由 `tests/test_review_report.py` 與 `tests/test_pr_context_cache.py` 鎖住
