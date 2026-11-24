# Work Board — 格式規格（§1、§1a）

Loaded on demand by [`skills/work-board/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md) §1 — 四個 section 的範例、行文法、細節檔格式、狀態詞 vocabulary、排序、加權與載入樣板。
本檔內文原樣自 SKILL.md 搬出，章節編號（§1a、§3a 等）沿用原編號，SKILL.md 內仍以這些編號互相引用。

### Sections（固定順序，四個 `## ` section）

```markdown
# Work Board — Lee-W/maigo

> 最後刷新：2026-08-18 14:30 ｜ 🎯 2 ｜ 👀 1 ｜ ⏳ 2 ｜ ✅ 1 ｜ 🧠 待學習盤點 1

## 🎯 我的下一件（2）

1. [ ] 🔀 CHANGES_REQUESTED @Lee-W →修改 +286/-74 — Redesign Work Board reading view i/9201.md
2. [ ] 🐛 待 triage @reporter 💤 →triage — CLI 在空設定檔時會 crash i/9101.md

## 👀 待我 review（1）

1. [x] 👀 ↩︎ 回你的球 @contributor 上次 NEEDS_CHANGES +1.2k/-340 — Avoid duplicate GitHub requests i/9301.md

## ⏳ 等別人（2）

- [ ] 🔀 等 review @Lee-W — Document plugin installation flow i/9202.md
- [ ] 🐛 NEEDS_INFO（已請補作業系統與完整 log） @reporter — Hook occasionally exits without output i/9103.md

## ✅ 最近結案（1）

- [x] 👀 APPROVE（merged 07-12） @contributor 🧠 07-12 — Add structured review verdicts i/9303.md
```

索引行行尾的 `i/9201.md` 對應 `.maigo/i/9201.md` 這份細節檔（索引行的路徑相對 board.md 所在的 `.maigo/`）：

```markdown
# 🔀 CHANGES_REQUESTED — Redesign Work Board reading view

- 連結：<https://github.com/Lee-W/maigo/pull/9201>
- 規模：Δ+286/-74
- 下一步：`/maigo:address-comments`

## 判斷

補測試還是反駁 reviewer

## 筆記

<!-- 手寫區 -->
```

細節檔格式規格見 §1a；欄位省略規則（`作者`／`規模`／`下一步` 何時整行不寫）與 upsert
生命週期（建立/更新/回收/孤兒偵測）也在該節。

- **🎯 我的下一件**：Rank P0–P7 的 🔀／🐛（你自己開的 PR、你在處理的 issue），**編號清單**
  （`1. [ ]`），第 1 行就是下一件事。自己的工作永遠在檔案最上面，不會被一長串 review 淹沒。
- **👀 待我 review**：Rank P0–P7 的 👀（別人的 PR，輪到你審），同樣是**編號清單**、獨立從 1 編號。
  區落點只看 rank 與型別：`section_for(rank, 型別)`——P0–P7 時 👀 進這區、🔀／🐛 進 🎯。
- **⏳ 等別人**：Rank P8，checkbox 清單、無編號——球不在你手上，這區是查閱，不是待辦。
  區內自己的（🔀／🐛）排前面、再排 👀，各群內 `updatedAt` 降序。
- **✅ 最近結案**：Rank P9，checkbox 清單、無編號，有保留期與筆數上限（見〈排序〉：別人的 PR 3 天、自己的 7 天、最多 10 行；
  待盤點未完成的行最多再留到 30 天）。
  區內同樣自己的排前面、再排 👀。
- 舊版另外兩個獨立 section（收 `gh` 抓不到的項目、收軟刪項目的那兩區）**已取消**：
  `gh` 抓不到的項目改判 `抓不到`（P0），併進 🎯 或 👀 最上面（依型別）；`--drop` 改成把該行移進 ✅ 最近結案、狀態詞
  `已放棄`，跟其他結案行共用同一組老化規則（保留期與上限見〈排序〉），同時寫入排除紀錄（§3a），之後刷新不再補回。

### 行文法

**設計原則：索引直接回答「哪顆 PR、誰貢獻、現在要做什麼（或 review 的結果）、多大」。**
狀態詞後必填 `@貢獻者`（GitHub `author.login`），完整 title 不截斷，裸細節檔路徑放在**行尾最後一欄**供 `$` 後 `gf`。
行動區（🎯／👀）的行另帶一個短動作 `→<動作>`（👀 區與 🔀 `有新 comment` 改帶 review 結果）與改動規模 `+A/-D`；URL、完整下一步指令（`Δ+A/-D`
規模、`下一步`）與判斷句仍放細節檔（§1a）——索引行只帶短版，所以不必為了放指令擠掉 title 或貢獻者。
`board_state.py` 回傳 `index_entry`（含 `short_action`／`result` 與 `size`）是可重用的行內容；orchestrator 加原 checkbox、badges
與編號（badges 放在貢獻者之後、`→動作`／結果之前）；缺作者的行在刷新取得 GitHub author 後補上，拿不到就標 `作者待補`，不臆造作者。
完整刷新的行與整檔由 `scripts/board_refresh.py` 的 `render_line` / `render_board` 渲染——這兩個函式是
本節文法的程式鏡像，由 `tests/test_board_refresh.py` 的 round-trip 測試守著；改文法時兩邊一起改。

```text
🎯／👀 區：<n>. [ ] <型別emoji> <狀態詞>[（旁註）] @<contributor>[ <badges>][ →<動作> | <結果>][ +A/-D] — [<title> ]<細節檔路徑>
⏳ 區：- [ ] <型別emoji> <狀態詞>[（旁註）] @<contributor>[ <badges>] — [<title> ]<細節檔路徑>
✅ 區：- [ ] <型別emoji> <狀態詞>[（旁註）] @<contributor>[ <badges>][ MM-DD] — [<title> ]<細節檔路徑>
```

作者待補時省略 `@login`，改在旁註寫 `作者待補`（併進同一個旁註：`（<原旁註>；作者待補）`）。

- **一行一項、絕不換行**：`/` 搜尋與 `dd` 刪除都以行為單位；換行會讓兩者都失準。
- **型別 emoji**：🐛 issue ｜ 🔀 你的 PR ｜ 👀 在審的 PR
- **編號 ＋ checkbox 混排（僅 🎯、👀 兩區，各自從 1 編號）**：`1. [ ]`。使用者選定編號清單，checkbox 是學習閘門
  的唯一訊號（§5），兩者都要留；⏳/✅ 區是查閱不是待辦，維持無編號的 `- [ ]`。
- **`→<動作>` 與 `+A/-D`（只在 🎯／👀 區，optional）**：放在 badges 之後、` — ` 之前。
  動作是短字詞（無空白、≤6 顯示欄），由 `_STATUS_META` 的 `short_action` 決定：`有衝突`→`解衝突`、
  `CI 紅`→`修CI`、`CHANGES_REQUESTED`→`修改`、`待送出`→`送出`（草稿不存在時改 `起草`）、`↩︎ 回你的球`→`重審`、
  `有新回覆`→`重判`、`有新 comment`→`回覆`、`可合併`→`merge`、`待 review`→`審`、`待 triage`→`triage`、
  `READY`→`接手`；`抓不到`、`WIP`、`IN_PROGRESS` 不顯示。**👀 區的列不帶動作**（`待 review` 的 `→審` 也不帶——
  使用者看 board 要的是 review 的結果，動作資訊全在細節檔的「下一步」），改帶**結果**，佔動作的位置：
  本地報告 metadata 有 verdict 時顯示原詞（`APPROVE`／`APPROVE_WITH_NITS`／`NEEDS_CHANGES`／`BLOCKED`），
  狀態是 `↩︎ 回你的球` 時前綴 `上次 `（那是舊 head 的 verdict，不是現況）；沒有本地報告就什麼都不顯示。
  🔀 `有新 comment` 的 `→回覆` 也換成對方的 review 決定（`已核准`／`要求修改`；`REVIEW_REQUIRED` 與空值不顯示）——
  但 `CHANGES_REQUESTED` 本來就會先判成自己的狀態，所以實際只會看到 `已核准`。其他 🎯 列（`解衝突`、`修CI`、`修改`、
  `merge`）與 🐛 的動作不變。⏳ 的 `BLOCKED` 等本來就是狀態詞，不重複。規模是 `+A/-D`，任一數字 ≥1000 時縮成一位小數加 `k`
  （`+1.2k/-340`）；issue 沒有規模、不顯示。細節檔仍是完整的 `Δ+A/-D` 與完整下一步指令。
  這幾欄是**衍生值**：refresh 每次從狀態與 gh 資料重算，parser 讀回來只為了 round-trip（排除列沿用讀到的值；抓不到的列沿用讀到的規模，但**不顯示動作**——動作是建議你現在做什麼，抓不到時這個建議不可信，所以刷新時清掉）。
- **✅ 區的結案日期 `MM-DD`（optional）**：放在同一個位置（badges 之後、` — ` 之前），讓「還會留多久」看得見；
  日期取 `mergedAt` → `closedAt` → `updatedAt`（本機時區）。⏳ 區不帶這三個欄位。
- **行長預算**：`—` 之前的部分**加上空格與細節檔路徑**（量法等同路徑仍在 `—` 之前，臨界點不因路徑移到行尾而改變）以顯示寬度計（East Asian Wide/Fullwidth 與 emoji 算 2 欄、組合字元與變體選擇符算 0、
  其餘含 `→`／`Δ` 算 1），預算 80 欄；超出時**先拿掉 `→動作`**（狀態詞本身已大致說明下一步），規模保留；
  帶**結果**的列相反：結果優先於規模，超出時先拿掉 `+A/-D`，結果與 `上次 ` 前綴永不截（規模可以從 GitHub 看到；
  `上次` 一旦被縮掉，舊 head 的 verdict 會被讀成現況）；
  旁註、作者、細節檔、title 一律不截（title 不截斷是既有規則；旁註是手寫事實）。所以預算是盡力而為，不是硬上限——
  一行帶超長旁註時仍可能超過，這是刻意的。欄寬是近似值，不是 nvim 實際欄寬。
- **旁註**（沿用 review board 慣例，optional）：branch 名、closed 理由、linked PR、DRAFT、
  他人 review decision 這類「per-item 事實」寫在狀態詞後面的括弧裡
  （例：`IN_PROGRESS（分支 fix/xxx）`）——旁註記事實，判斷句記決定，兩者不是同一件事；
  判斷句本身已搬進細節檔（§1a）。`（gh 失敗：…）` 開頭的旁註是 `refresh` 專用的抓料錯誤標記，恢復時
  會被清掉；手寫旁註請勿用這個開頭。結果欄已經顯示本地 verdict，所以**不要手寫 `（本地 <verdict>）` 旁註**；
  refresh 寫入 👀 列時會把重複的那一段移除：旁註依 `；` 切段，只有「去掉前後空白後完整等於 `本地 <目前報告的 verdict>`」
  的段才算純重複，只移除那一段、其餘接回，全沒了就不寫旁註。含其他內容的段（`本地 NEEDS_CHANGES，must-fix 5`）、
  verdict 與目前報告不同的段、半形括號寫法一律原樣保留。
- **貢獻者（必填）**：從 GitHub `author.login` 取得，包含自己的 PR；放狀態詞／旁註後、badges 前。
  舊行缺作者視為待遷移，刷新時必補；補不到（gh 沒給、前一輪也沒有）就標 `作者待補`，不臆造 login、
  不留光禿的 `@`。其餘消費者（`plan`／`snapshot` 等）讀到缺 `@` 又沒標 `作者待補` 的行會報錯；只有 `refresh`
  讀現檔時放寬，好把作者補回去。作者補到後，下一輪刷新會拿掉 `作者待補`。
- **badges**（`🧠`/`💤`/`🔖`，optional）：緊接在貢獻者（缺值時為旁註）之後、`→動作`／結果／規模／結案日期與 ` — ` 之前，用一個空格分隔；
  §2 vocabulary 表下方有各自的觸發規則。
- **細節檔路徑（必填、行尾最後一欄、裸相對路徑、不加反引號）**：相對 board.md 所在的 `.maigo/`，由
  [`detail_path()`](https://github.com/Lee-W/maigo/blob/main/scripts/board_state.py)
  算出——同 repo 是 `i/<n>.md`，跨 repo 是 `i/<repo>-<n>.md`。**不加反引號**：這是行文法的
  格式慣例，`board_sync.py` 讀回端認的是行尾最後一個裸 `i/…md`，不含反引號；
  不是 `gf` 的限制（實測反引號不擋 `gf`，見 [`vim-friendly-artifacts`](https://github.com/Lee-W/maigo/blob/main/skills/vim-friendly-artifacts/SKILL.md)）。
  放在行尾是為了 `gf`：`j`／`k` 移到某一行時游標落在行首，而 `gf` 抓游標下的檔名；按 `$`
  跳到行尾就正好停在路徑上（`/` 搜尋命中後同理）。路徑與前一個字之間恆為**單一半形空格**
  （標題以全形標點或 emoji 結尾也不會黏住），路徑之後不留任何字元；之後再按 `gf` 直接開對應細節檔
  （格式見 §1a、操作見 §6）。
- **`—` 分隔符是強制的，parser 不會用啟發式猜**：`—` 之後是 `[<title> ]<細節檔路徑>`，
  行尾最後一個以空白分隔的 token 是路徑，其餘是 title（title 可為空，則 ` — i/1.md`；可含 ` — `；
  可全形標點或 emoji 結尾；title 自己以 `i/9.md` 結尾也行，因為只認**最後一個** token）。title
  **不加引號**。漏打分隔符、行尾沒有路徑、或路徑後面多了字，一律回報格式壞掉，寫回命令**大聲失敗**，
  不靜默留空——比照未知狀態詞。行尾的**尾隨空白**會被容忍（nvim 存檔可能留下），refresh 重寫時正規化掉。
- **舊形仍可讀**：舊行文法 `… <細節檔路徑> — <title>`（路徑在 `—` 之前）讀得進來，兩種形狀解出同一組欄位；
  refresh 一次就把每一行（含排除列、抓不到的列）以新形寫出。分辨方式是「第一個 `—` 之前的部分有沒有細節檔路徑」。
  已知接受的歧義：手改壞的舊行（`— fix i/9.md`，`—` 前沒路徑、title 恰好以路徑形狀結尾）會被當成新形，
  路徑是 `i/9.md`；若該細節檔不存在讀回會大聲失敗，但數字檔名（`i/9.md`）沿用同 repo 編號推導，**不會**被擋——
  手改行時請維持 `— <title> <路徑>` 的形狀。
- **checkbox**：👀 行的 `[x]` ＝「我看完目前這份報告了」——使用者在 nvim 勾上，下次刷新會 ack 該
  report；有新 commit／作者留言（回你的球）或待 review 時**自動取消勾**。🐛/🔀 行的 `[x]` ＝「這項我
  **親自**處理過了」，純學習閘門訊號（見 §5），不 ack、不自動取消勾；與所在 section 正交。
- **🧠 標記**：學習盤點已完成，不重複學。
- **🔖 標記**：待學習盤點——👀 行被勾（含 `--reviewed`）時加上，跨刷新保留，所以後來自動取消勾也
  不會吃掉學習訊號；`--learn` 完成後換成 `🧠`。
- **💤 標記**：`updatedAt` 逾期未更新（stale badge，見 §2 vocabulary 表下方說明），跟
  `🧠` 一樣是正交於狀態詞的 badge，不影響 rank / section。
- **跨 repo**：board 綁 cwd repo（header 記 `gh repo view --json nameWithOwner` 結果）；
  丟進來的 URL 若屬其他 repo，細節檔路徑改用 `i/<repo>-<n>.md` 形式（見上），真 URL
  完整記在該項的細節檔 `連結` 欄裡，不在索引行出現。
- **空白容錯**：旁註 `（…）` 與緊接著的 badges 之間有沒有留空格，parser 都吃得下
  （nvim 手改最容易漏這格空白）。

### 1a. 細節檔格式 `.maigo/i/<slug>.md`

索引行以外的細節（URL、規模 Δ+A/-D、完整作者資訊、完整下一步、審查時間、判斷句、舊 `📄 <產物路徑>`）全部
收進這份細節檔；索引行的行動區只帶短版的 `→動作`（👀 區為結果）與 `+A/-D`（§1），細節檔維持完整版：

```markdown
# <型別emoji> <狀態詞> — <title>

- 連結：<https://github.com/OWNER/REPO/pull/NUMBER>
- 對外（PR description）：（只有 🔀 且有內容時才寫）
  - 為什麼：<PR description 的 Why 段，單行>
  - 做了什麼：<PR description 的 What 段，單行>
- 自用（`../pr/<ident>/summary.md`）：（只有 🔀 且有內容時才寫）
  - 為什麼：<本地 run summary 的「為什麼做」，單行>
  - 做了什麼：<本地 run summary 的「做了什麼」，單行>
- 關聯 issue：#<n>、<owner>/<repo>#<n>（只有 🔀 且 PR 有 closing issue 時才寫）
- 規模：Δ+A/-D ｜ 作者：<author>
- 下一步：`<next_action>`
- 載入：`<依 board-load.txt 樣板代入的指令；沒設定樣板就整行省略>`
- 本地 review 結果：<與 board 行相同的結果字串>
- 最後 review：<ISO 8601 時間，含時區>
- 已看完：<ISO 8601 時間，含時區；尚未確認時省略>
- 相關檔案：
  - `../review/<ident>/review.md`
  - `../pr/<ident>/plan.md`

## 判斷

<判斷句——你現在要決定什麼，不寫發生了什麼>

## 筆記

<!-- 手寫區 -->
```


**撞號限制與後果**：`detail_path()` 的 `<repo>` 只取 repo 名、不含 owner（見
[`scripts/board_state.py`](https://github.com/Lee-W/maigo/blob/main/scripts/board_state.py)
docstring），所以不同 owner 的同名 repo（例如 `Lee-W/maigo` 與另一個 owner 的
`maigo`）在跨 repo 情境會共用同一個 `i/<repo>-<n>.md`——兩項的事實區與 `## 判斷` /
`## 筆記` 會互相覆蓋。這是刻意的取捨（路徑短優先），目前**不自動處理**；真的撞號時
手動把其中一份細節檔改名（並同步索引行的細節檔路徑）即可繞開。

欄位省略規則：

- **作者**：索引行必填 `@login`（拿不到時標 `作者待補`）；細節檔可重複完整 login，不寫含糊的「你」。
- **本地 review 結果**：只有 👀 且本地報告 metadata 有 verdict 時才寫（字串與 board 行的結果欄相同，含 `上次 ` 前綴）；
  沒有報告或不是 👀 就省略整行。H1 不放結果（refresh 靠 H1 的狀態詞復原 prior 狀態）。
- **最後 review / 已看完**：使用 report 的 `reviewed_at` / `acknowledged_at`，不能用
  board 刷新時間取代。沒有 report 時寫「尚未 review」；舊檔 mtime fallback 註明「舊檔時間推估」。
- **對外（PR description）／自用／關聯 issue**：只有 🔀（自己的 PR）才寫，順序固定為對外、自用、關聯 issue，接在 `- 連結：` 之後、`- 規模：` 之前；各組沒有內容就整組省略（含組標題），不寫佔位字。
  每一行都以 `- ` 或兩格縮排加 `- ` 開頭、來源文字一律單行化，所以事實區不會出現行首 `## `，仍是 formatter 不動點。
  - **對外**：來源是 GitHub 上的 PR body。取標題文字（不分大小寫、層級與尾端冒號）為 `Why`／`為什麼`／`動機`／`Motivation`／`背景` 的第一段當「為什麼」，為 `What`／`做了什麼`／`Changes`／`Summary`／`變更` 的第一段當「做了什麼」；段落到下一個同層或更高層標題為止。
    先清掉 fenced code、HTML 註解、表格行、圖片行、整行 HTML 與行內 HTML 標籤；段內清單項以 `；` 連接、其餘換行以空格連接；每欄上限 200 字元，超過取前 199 字加 `…`。
    body 沒有 Why 也沒有 What 段時，退成一行 `  - 說明：`（清掉標題後的第一個段落）；body 空白或清理後為空就整組省略。
  - **自用**：來源是本地 run summary 的 `## 為什麼做` 與 `## 做了什麼`；整個找不到 summary 時退回 plan 的 `## Goal`（只有「為什麼」）；兩者都沒有就整組省略。
    找檔順序是 `pr/<ident>/`、再 `topic/<slug>/`（`<slug>` 是 PR 的 `headRefName` 經 [`artifact_path.slugify`](https://github.com/Lee-W/maigo/blob/main/scripts/artifact_path.py)，`/` 變成 `-`）；兩個目錄裡任一個有可用的 summary 就不看 plan。
    同一目錄有多份時取編號最大者（`summary.md` 視為編號 1，編號相同取無後綴者）。組標題寫實際來源檔、相對於細節檔的路徑（例 `../topic/<slug>/summary.md`，plan 為 `../topic/<slug>/plan.md` 的 Goal），可用 `gf` 跳；`topic/` 底下的檔只讀來取文字，不列進 `相關檔案`。
  - **關聯 issue**：來源是 `closingIssuesReferences`；同 repo 寫 `#12`、跨 repo 寫 `owner/repo#7`，以 `、` 連接、去重，至多 5 筆，超過寫 `…等 N 項`；不附 URL。
  - **已知限制**：一個任務對多張 PR 時，同一份 summary 會出現在每張對得上的 PR；summary 的結果可能是部分完成或中止，不顯示；`topic/<slug>/` 被封存後自用組消失；在預設分支開工或用 `--slug` 指定的任務，`headRefName` 對不上 topic 目錄，只能靠 `pr/<ident>/`；整行以 `<` 開頭的 HTML 區塊會被丟掉；行內 `<tag>` 形式的文字（例如泛型 `Vec<T>`）也會被當 HTML 移除；PR body 裡無法以 UTF-8 編碼的字元（孤立 surrogate）換成 `?`；長度以字元計，截斷可能切在行內 markdown 中間；自用組只在刷新時更新。
- **規模**：issue 省略整行（沒有 additions/deletions 可言）。
- **載入**：只有設定了 `board-load.txt` 樣板（見〈排序〉之後的「載到本機的指令」）、且該項目是開著的同 repo PR 時才寫；
  🐛 issue、跨 repo 項目（`i/<repo>-<n>.md`）、✅ 結案項目、抓不到的列一律省略整行。delegate 命令寫細節檔時可省略這行，下一次刷新補上。
- **下一步**：`next_action` 為 `null` 時省略整行——狀態沒有對應下一步，見
  [`scripts/board_state.py`](https://github.com/Lee-W/maigo/blob/main/scripts/board_state.py)
  的 `_STATUS_META`（`WIP` / `IN_PROGRESS` / P8 / P9 / P0 這類狀態）。
- **相關檔案**：刷新時掃 state 目錄的 `review/<ident>/`、`pr/<ident>/`、`issue/<ident>/`（`<ident>` 與細節檔名同一個識別碼，同 repo 為 `<n>`、跨 repo 為 `<repo>-<n>`，由 `board_state.github_ref()` 算出），把底下所有一般檔列成事實區最後一個欄位的巢狀清單，每項是包反引號、相對於細節檔自己位置的路徑（`../review/<ident>/review.md`），所以在 nvim 裡游標停在路徑上按 `gf` 就能開，**但檔名含空白或括號的檔仍會列出、`gf` 無法直接跳**（用 `:e` 或自己選取路徑）。清單只在刷新時更新，檔案增減要等下一次刷新才反映；沒有被這次刷新重新產生的列（沿用舊內容的 `keep` 列，例如抓取失敗的項目）不會更新。順序：先依目錄（`review`、`pr`、`issue`），目錄內先依 [`scripts/artifact_path.py`](https://github.com/Lee-W/maigo/blob/main/scripts/artifact_path.py) 的 `_KNOWN_KINDS` 對應的檔名順序（`plan`、`rubric`、`review`、`draft`、`pr-comments`、`reply-draft`、`inline-comments`；同名的無後綴檔排在 `-<attempt>` 之前，`-<attempt>` 由小到大，例如 `rubric.md`、`rubric-1.md`、`rubric-2.md`、`rubric-10.md`），其餘檔（含子目錄內的檔）依路徑字典序。沒有任何產物時整個欄位省略；不列的有：`topic/`、`_archive/`、`_internal/`、隱藏檔與隱藏目錄（名稱以 `.` 開頭）、名稱含反引號或換行（CR／LF）的檔（無法放進單行 code span）、名稱不是合法 UTF-8 的檔、寫入中的暫存檔（`.tmp` 或 `~` 結尾），以及掃描時讀不到的檔或目錄；目錄的名稱同樣套用這些條件（隱藏、`.tmp`／`~` 結尾、含反引號或換行、非 UTF-8），符合的目錄整個子樹都不列。這個清單是機器維護的事實，不要手改；自己的筆記與手寫連結寫在 `## 筆記`。
- **舊 `📄 <產物路徑>`**（`review/<n>/review.md` / triage 筆記等本地產物）：改寫進 `## 筆記`
  區裡的一行路徑連結（檔案相對、獨立成清單項或包反引號，例：`- ../review/9301/review.md`，自己的 PR 為 `../pr/9301/review.md`；不要寫成緊貼中文冒號的 `報告：../review/…`；
  細節檔在 `.maigo/i/` 底下，理由見 [`vim-friendly-artifacts`](https://github.com/Lee-W/maigo/blob/main/skills/vim-friendly-artifacts/SKILL.md)）。這是手寫區的連結，refresh 不替它寫；產物的完整清單由事實區的 `相關檔案` 欄提供，筆記裡的連結只用來補充說明，重複列出可接受。
  既有筆記裡的舊寫法（`.maigo/review/…`、`review/…`、緊貼中文標點的路徑）refresh 與命令不會改寫，新舊混用可接受；要整理時跑 `scripts/rewrite_note_paths.py`（預設乾跑，見 §6）。
- **資料缺失時的降級**（與上面三條「刻意省略」不同）：某欄位該有值但當下拿不到
  （例：遷移進來的 👀 項目沒有 `Δ+A/-D`，因為舊格式本來就沒記），就**只寫拿得到的部分**
  ——`- 規模：` 整行只剩作者時退化成 `- 作者：<author>`，不要填 `?` 或 `N/A` 佔位。
  下次寫回拿到真值就補回完整形狀，省略規則不會擋住它被填回去。

`## 判斷`：只寫「你現在要決定什麼」，**不寫「發生了什麼」**。

- 狀態詞本身已經講清楚下一步、或根本沒有判斷要下（例：`可合併`、`等 review`、
  `IN_PROGRESS`）→ 該段留空
- 真有岔路要選（改還是不改、修還是換路、能不能重現）→ 一句話點出岔路，愈短愈好

### 狀態詞 vocabulary（依型別，含 rank）

rank 決定排序與所在 section，10 級由緊急到不急：P0 最急，P9 只留痕。
**正典在 [`scripts/board_state.py`](https://github.com/Lee-W/maigo/blob/main/scripts/board_state.py) 的 `BoardStatus` enum ＋ `Rank` ＋ `_STATUS_META`**，
本表只是人類可讀鏡像，兩者須一致（由 `tests/test_board_state.py` 守）。

| 型別 | 狀態詞 | rank |
|---|---|---|
| 跨型別 | `抓不到`（orchestrator 指派，`classify()` 不產出） | P0 |
| 🐛 issue | `待 triage` | P6 |
| 🐛 issue | `READY` | P7 |
| 🐛 issue | `IN_PROGRESS` | P5 |
| 🐛 issue | `有新回覆` | P2 |
| 🐛 issue | `NEEDS_INFO` | P8 |
| 🐛 issue | `DUP` / `CLOSE` | P9 |
| 🔀 你的 PR | `WIP` | P5 |
| 🔀 你的 PR | `有衝突` | P1 |
| 🔀 你的 PR | `CI 紅` | P1 |
| 🔀 你的 PR | `CHANGES_REQUESTED` | P1 |
| 👀 在審的 PR | `待送出`（本地報告待你看／決定是否送出；報告已寫好只差送出，與「卡住的」同為 P1） | P1 |
| 🔀 你的 PR | `有新 comment` | P2 |
| 🔀 你的 PR | `可合併` | P3 |
| 🔀 你的 PR | `CI 等待` | P8 |
| 🔀 你的 PR | `等 review` | P8 |
| 👀 在審的 PR | `他人草稿` | P8 |
| 👀 在審的 PR | `待 review` | P4 |
| 👀 在審的 PR | `↩︎ 回你的球` | P2 |
| 👀 在審的 PR | `已看完`（本地確認，或已送出但無本地 verdict） | P8 |
| 👀 在審的 PR | `BLOCKED` / `NEEDS_CHANGES` / `APPROVE_WITH_NITS` / `APPROVE` | P8 |
| 跨型別終端 | `closed` / `merged` | P9 |
| 跨型別 | `已放棄`（`--drop` 軟刪，進 ✅ 最近結案；寫入排除紀錄、刷新不重新分類） | P9 |

triage verdict 沿用 [`strict-triage`](https://github.com/Lee-W/maigo/blob/main/skills/strict-triage/SKILL.md)、
review verdict 沿用 [`strict-review`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md)，不另造詞。

**badge（正交於狀態詞，不佔 rank）**：`🧠` 已完成學習盤點；`🔖` 待學習盤點；`💤` stale——`updatedAt`
逾 14 天（`scripts/board_state.py --stale-days` 可調），提示這顆球可能被遺忘，不改變 rank / section。
都寫在旁註之後、` — ` 之前，例：`🎯 1. [ ] 🔀 WIP 🧠💤 — <title> i/12.md`。


### 排序

- 🎯／👀 區：**rank 升序 → 同 rank 內加權（boost）升序 → `updatedAt` 升序**——排名先分先後，
  同一級內先看使用者設定的加權，再看最久沒動的（沿用舊「責任感排序」的精神，但改成明確的
  `updatedAt`）。編號 `1. 2. 3.` 就是這個排序結果，排名本身不顯示在行內。
- **同 rank 內加權**（使用者可設定）：只在同一個 rank 內調整先後，**不改 rank、不改 section**，
  所以 P1 永遠排在 P4 的加權項目前面；加權在 👀 區照樣生效（👀 區就是它的主戰場）；⏳ / ✅ 區不套用；`--reviews` 檢視（`board_state.py`）只依
  rank 排序，**不套用加權**。加權規則放持久設定檔、由 `refresh` 每次重算，不把手動順序寫進
  `board.md`，所以刷新不會洗掉。設定檔（兩者都不存在＝無加權，行為與沒有這個功能時完全相同）：
  - repo 層：`<maigo-root>/.maigo/board-weights.txt`
  - 使用者層：`~/.config/maigo/board-weights.txt`（與 `repos.txt` 同目錄）
  - 兩者都存在時 repo 層規則排在前面（優先）；`refresh --weights <file>` 覆寫兩者，只讀該檔。

  格式是純文字，一行一條規則，空行與 `#` 開頭的行忽略：
  - `author:<login>`——大小寫不分，精確比對 gh author login
  - `title:<regex>`——大小寫不分的 `re.search`，比對該行的 title

  boost ＝第一條命中規則的序號（依檔案行序、兩檔合併時 repo 層在前連續編號；
  越前面越優先）；沒命中＝一個比任何規則都大的值。壞行（未知前綴、`author:` 值含空白、
  regex 編譯失敗）fail loudly：`refresh` 以前置條件拒絕（exit 1），訊息指出檔名與行號，不會靜默忽略。
  範例：

  ```text
  # 先排 kaxil、FrankYang0529 的項目，再排 common.ai 相關主題
  author:kaxil
  author:FrankYang0529
  title:common\.ai|PydanticAI|LLMOperator|AgentOperator|DocumentLoader
  ```
- **載到本機的指令（`board-load.txt`）**：細節檔的 `- 載入：` 那一行，游標在索引行的路徑上 `gf` 進去、
  `yi`＋反引號即可複製到終端機。樣板由使用者設定，**maigo 不內建任何預設、也不執行它**——board 只顯示。
  沒設定就整行省略。設定檔沿用 `board-weights.txt` 的兩層慣例：
  - repo 層：`<maigo-root>/.maigo/board-load.txt`
  - 使用者層：`~/.config/maigo/board-load.txt`
  - 同一個 key 兩層都有時 repo 層優先（逐 key 覆蓋）。

  格式一行一條，空行與 `#` 開頭忽略：
  - `pr:<樣板>`：給 PR 用，可用佔位字 `{number}`；
  - `branch:<樣板>`：給自己的 🔀 用，可用 `{branch}`（PR 的 `headRefName`）與 `{number}`。

  誰拿到哪條：👀 用 `pr`；🔀 優先用 `branch`，沒設 `branch`（或 gh 沒給 branch 名）時退回 `pr`；兩條都沒設就不顯示。
  未知 key、未知佔位字、空樣板會以 `檔名:行號` 大聲失敗（`refresh` exit 1，未寫任何檔）。`headRefName` 由 PR 作者決定，
  代入前會驗證只含 git branch 的安全字元，不合格就省略那一行並在刷新摘要警告。範例（使用者設定檔內容，
  工具與指令依你自己的環境調整，這裡只是示意）：

  ```text
  # 載到本機的指令樣板（範例）
  pr:wt switch pr:{number}
  branch:wt switch {branch}
  ```
- ⏳ / ✅ 區：自己的（🔀／🐛）在前、👀 在後，各群內 `updatedAt` 降序（這兩區是查閱，不是待辦）。
- ✅ 區在刷新時自動清掉過期與超量的行，清掉時同時寫入排除紀錄（`reason: aged`，§3a）。規則依序是：
  1. **保留期**：👀（別人的 PR）結案超過 **3 天**清掉，🔀／🐛（自己的）超過 **7 天**（`AGE_LIMIT_REVIEW`／`AGE_LIMIT_OWN`）。
  2. **學習例外**：待盤點未完成的行〔(`[x]` 或 `🔖`) 且沒有 `🧠`〕不受保留期與上限限制，學完才走；
     但例外有期限——結案超過 **30 天**（`LEARN_PENDING_LIMIT`）就回到一般規則被清掉。刷新摘要會事先列出
     7 天內將到期的行與剩餘天數。
  3. **筆數上限**：其餘行依結案時間新到舊最多留 **10 行**（`DONE_CAP`），超出的最舊行清掉；
     手動加進來的行（`--add` 那一輪）與學習例外中的行不計入。刷新摘要列出本輪因上限清掉的行數。
  老化基準時間（`refresh` 實作）依序取 `mergedAt` → `closedAt` →（排除項目）排除紀錄的 `last_drop_at`
  → `updatedAt`。
  `/maigo:board --drop` 的落點也是這裡（狀態詞改 `已放棄`），跟其他結案行共用同一條
  老化規則，不再有獨立的 tombstone 區。

完整刷新取得 PR review threads 時，細節檔事實區加 `- Review 討論：未解決 N ｜ 已解決 M`；零筆顯示 0／0，未取得資料則省略，不推測成零筆。
