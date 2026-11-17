---
name: work-board
description: This skill should be used when reading, writing, or migrating `.maigo/board.md` — the cross-session Work Board of issues to triage, your own PRs and PRs you review, ranked into 🎯 我的下一件 / 👀 待我 review / ⏳ 等別人 / ✅ 最近結案. Covers line grammar, upsert contract, migration and the `--learn` gate.
---

<!-- mkdocs-include-start -->

# Work Board

**Owner Agent**: orchestrator（直跑，不 delegate 五人）
**Consumers**: [`/maigo:board`](https://github.com/Lee-W/maigo/blob/main/commands/board.md)（讀寫全套）、
[`/maigo:review`](https://github.com/Lee-W/maigo/blob/main/commands/review.md)、
[`/maigo:triage-issue`](https://github.com/Lee-W/maigo/blob/main/commands/triage-issue.md)、
[`/maigo:take-issue`](https://github.com/Lee-W/maigo/blob/main/commands/take-issue.md)、
[`/maigo:address-comments`](https://github.com/Lee-W/maigo/blob/main/commands/address-comments.md)、
[`/maigo:describe-pr`](https://github.com/Lee-W/maigo/blob/main/commands/describe-pr.md)（各自的收尾回寫段）

`.maigo/` 全貌型錄（board 在其中的定位、其餘產物種類）見
[`docs/reference/artifacts.md`](https://github.com/Lee-W/maigo/blob/main/docs/reference/artifacts.md)。

**`~/.config/maigo/board-index.md` 是什麼**：跨 repo 唯讀索引，由
`scripts/board_index.py`（`/maigo:board --cross-repo` 觸發）產生——回答「這台
機器裝了 maigo 的所有 repo，現在該我動哪些」這句話，**不是另一份 `board.md`
正典**。每次重新產生、沒有手寫區、沒有 upsert 語意；只逐字複製各 repo
`board.md` 的 `## 🎯 我的下一件`（舊版標題 `## 🎯 下一件` 也收）與 `## 👀 待我 review` 兩段，不重新解析或合併排序。跟本節下面講的
`board.md` 單一 repo 內的行文法、upsert 合約是完全不同的東西。

## Why this skill exists

`/maigo:review` 的 `.maigo/review-board.md` 只涵蓋「reviewer 視角」。實際工作面是三種混在一起的球：
**要 triage / 接的 issue**、**自己開的 PR**、**在審別人的 PR**。Work Board 把它們併成一份，
核心機制沿用 review board 最有價值的部分：board 的存在意義不是收藏分類，
而是回答「**現在該我動哪些**」。

## 1. `.maigo/board.md` 格式規格

四個 `## ` section 固定順序：`## 🎯 我的下一件`、`## 👀 待我 review`、`## ⏳ 等別人`、`## ✅ 最近結案`。
索引行一行一項、絕不換行；行尾最後一欄是裸相對路徑的細節檔（`i/<n>.md`）；`—` 分隔符強制，parser 不猜。
完整範例、行文法、細節檔格式（§1a）、狀態詞 vocabulary 與 rank、排序、加權與載入樣板：
- [`references/format-spec.md`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/references/format-spec.md)：**寫、改、解析任何一行 board 或細節檔之前讀**（行文法的程式鏡像在 `scripts/board_refresh.py` 的 `render_line` / `render_board`，改文法時兩邊一起改）。

**硬規則：refresh 或任何寫回只重寫 `## 判斷` 之前的事實區（標題行 ＋ metadata），
`## 判斷` 與 `## 筆記` 兩段一律原樣保留，絕不覆蓋。**
唯一例外：`board_refresh.py` 刷新時把這兩段裡 code fence 外的連續空行壓成一行、只含空白的行改成空行（空行後接縮排 4 格以上或 tab 的行時整段不動，免得改到縮排 code block），讓檔案維持 formatter 不動點；其餘位元組不動。
細節檔不存在時才整份新建
（判斷句寫進 `## 判斷`、`## 筆記` 留空）。這條硬規則適用於**所有**寫回路徑——`/maigo:board`
的 refresh 以及五個 delegate 命令（review / triage-issue / take-issue / describe-pr /
address-comments）各自的 upsert，沒有例外可以整份覆蓋掉細節檔清掉使用者手寫的 `## 筆記`。
改 `## 筆記` 裡的路徑時，同一路徑也會出現在事實區的 `相關檔案` 清單：Edit 的 `old_string` 要包含 `## 筆記` 標題或相鄰的筆記行等上下文，使它在檔內只命中一次；動手前先確認命中數為一，不可用 `replace_all`；事實區清單由下次刷新重寫，不要手改。
寫進 `## 筆記` 的每一行都要帶實際值：路徑放反引號（`.maigo` 內的產物用相對於該檔自己的路徑，原始碼用 repo-root 相對路徑，repo 外與 worktree 用絕對路徑）；記 worktree 就寫該 worktree 的絕對路徑。不寫「見某某檔」這種只指向別處的指標行；沒有實際值可寫就不要寫那一行。

### 舊格式與整檔重寫（硬規則）

**不在 enum 內的狀態詞**（手改壞、或舊工具寫入的殘留字）——寫回命令刷新該行時大聲失敗，
不靜默正規化成任何看似合理的狀態，比照 `—` 分隔符解析失敗的處理方式。

**向下相容**：新 vocab 是舊 vocab 的超集，沒有任何舊狀態詞被移除或改名（包含 `抓不到`／`待送出`／`已看完`）。第一次 `/maigo:board` 刷新時，`board_state.py` 的 `classify()`
會用 `prior_status` 重算每一行，未知或已停用的狀態詞視為 `None`（等同剛加入），自動
正規化成新表的對應狀態——不需要手動遷移步驟，沿用既有「刷新即正規化」的遷移慣例。
讀到舊版任何 section 標題（球權三分區時代的四個舊標題）時同樣吃得進來：取 checkbox /
`🧠` / 狀態詞後，整檔以新骨架（四個 section）重寫，不做逐行 in-place 遷移。

**`## 🎯 下一件`（三區時代的標題）是讀取別名，不是舊格式**：parser 把它當 🎯 區，所以三區的 board
不會被判成舊格式、`refresh` 照常處理；寫出時一律改成 `## 🎯 我的下一件`，並把 👀 行重新分到
`## 👀 待我 review`——script 就能完成這次遷移（有 CAS），不必走下面的整檔正規化。

**但整檔重寫與 §3(a) 的「禁止整份 `Write`」會直接對撞——併發安全優先。** 舊格式遷移必然是
整檔重寫，而 board 是跨 session 共用、不帶任務識別碼、且 `.maigo/` 被 gitignore（輾掉沒有
版本可救）。所以誰能做整檔寫入是分工，不是隨手做的事：

- **整檔重寫只有 `board_sync.py refresh --apply` 會做**，由 CAS（讀檔雜湊、寫前重讀比對、不一致就
  中止，見 §3(b)）取代 `ListAgents` 確認：別人動過檔案，這次寫入就以 exit 2 中止、不寫任何檔。
  refresh 遇到舊格式（舊 section 標題）或 `review-board.md` 會直接拒絕（exit 1），不遷移。
- **舊格式正規化**仍由 Claude 的 `/maigo:board` 完整刷新做——它本來就要重算每一行，是唯一有理由
  持有整檔的 Claude 寫入者；因為 script 看不到 `🔍 本批佇列` 的重判，也看不到其他 session。
- **五個 delegate 命令的收尾 upsert**（review / triage-issue / take-issue / describe-pr /
  address-comments）遇到真正的舊格式（球權三分區時代的舊標題）時，**只 `Edit` 自己那一行，並沿用該檔
  當下的舊行文法**，把正規化留給下一次 `/maigo:board`。**不要把一行新格式混進舊格式檔**——那會讓檔案
  同時有兩種文法，比整檔仍是舊格式更難解析。寫完在回覆裡告訴使用者「board 仍是舊格式，正規化留給
  `/maigo:board`」，不要靜默略過。
- **新標題缺席時**（board 是三區、`## 🎯 下一件` 開頭，檔內沒有 `## 👀 待我 review`；這不是舊格式，
  `refresh` 讀得進去）：👀 行照舊 append 到 `## 🎯` 開頭的那一區，不自己插入新標題、不整檔重寫；回覆裡
  告訴使用者「board 還是三區，下次刷新會自動分區」。新骨架（檔內已有 `## 👀 待我 review`）下，👀 的
  P0–P7 行 append 到 👀 區，🔀／🐛 的 P0–P7 行 append 到 🎯 區。
- Claude 做舊格式整檔重寫前先確認沒有其他 session 正在寫（`ListAgents`；同一台機器多個 worktree
  各跑一個 session 時，它們共用這一份 board）。不確定就當作有。`refresh --apply` 不需要這一步，
  CAS 會在衝突時自己中止。

實例（2026-09-19）：一次 `address-comments` 收尾對舊格式 board 只 `Edit` 了自己那一行；同一份
board 在那之後又被別的 session 加了一項、改了另一項、計數從 🎯 7 變 8——若當時照「整檔重寫」
辦，那兩筆會被安靜輾掉。

## 2. 型別偵測與球權判定

加 item 時先偵測型別（URL／裸編號／作者比對），`gh` 抓不到就標 `抓不到`（P0）；球權判定由 `scripts/board_state.py` 的 `classify()` 為正典，文件三張表只是鏡像。
- [`references/classification.md`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/references/classification.md)：**判定狀態、解讀 rank／section 落點、或寫入 `gh` 抓料欄位之前讀**。

## 3. 各命令回寫合約

**upsert 規則**：以 `#<n>`（含 repo 全稱時用全稱）為 key；行存在→整行替換
（**保留原 checkbox 與 🧠 狀態**；publish 新報告時重置該 PR 的 checkbox），不存在→append 到對應 section；board 檔不存在就先建骨架。
**整行替換時，對應細節檔（`.maigo/i/<slug>.md`）必須跟著整份重寫，不可只改索引行漏改
細節檔**——索引行與細節檔是同一次寫回的兩個產物，不允許其中一個落後。
**例外：board 還是舊格式時這條無從執行**——舊行文法把 URL / 規模 / 產物路徑都內嵌在索引行裡，
`.maigo/i/` 整個目錄不存在。此時只更新索引行，不要為單一項目憑空生一份細節檔（那會讓同一份
board 一半有細節檔一半沒有）；細節檔由 `/maigo:board` 在整檔正規化時一次建齊，見 §1 向下相容段。
**例外：`board.md` 不存在、但同目錄有 `board.md.migrated`（或 `review-board.md.migrated`）時，
不建骨架、也不靜默略過**——只有搬遷殘檔、沒有現役 board，可能是使用者已停用 board，也可能是搬遷後
還沒重建，收尾 upsert 分不出是哪一種；憑空建骨架會讓一份只有單一項目的 board 冒出來。改在收尾
summary 說明「board 不存在（只有 `.migrated` 殘檔），本次未回寫」，並建議跑 `/maigo:board` 重建。
（2026-11-13 apache/airflow #71072：address-comments 步驟 8 撞到此情境。）

**併發寫回（board 是跨 session 共用的單一檔，不帶任務識別碼，所以要靠寫法自保）**。
共同目的：別人動過就吵，不安靜覆蓋。寫入者有兩種：

**(a) Claude（五個 delegate 命令的收尾 upsert，以及 `/maigo:board` 的 fallback 手動流程）**：

1. **既有 board 一律用 `Edit`，禁止整份 `Write`。** `Edit` 的 `old_string` 就是天然的樂觀鎖：
   別的 session 動過那一行時 `Edit` 會失敗——**會吵**；`Write` 則會安靜輾過對方的寫入。
   `Write` 只保留給「board 檔不存在、要建骨架」那一次。
2. **寫入前立即重讀。** 不可拿幾輪之前讀到的內容當現況——中間可能已經有別的 session 寫過。
3. **`Edit` 失敗 → 重讀、重算那一行、再試；不要改用 `Write` 硬寫。** 失敗是訊號不是障礙。

**(b) `board_sync.py refresh --apply`（script，整檔寫回）**：先取得同一 state 目錄共用的
`.maigo/_internal/board/.refresh-write-lock`，持有到 ack、備份、寫回與 snapshot 全部完成；
有別的刷新持鎖時以 **exit 2** 中止、直接重跑，不覆蓋也不移除對方的鎖。程序遭強制終止留下鎖時，先確認原程序已結束才手動移除。
鎖內以 compare-and-swap 檢查抓料期間的改動——
讀 board.md 時記下內容雜湊，寫入前（ack 之前與實際寫檔之前各一次）重讀比對，不一致就以 **exit 2** 中止
（每個要改／刪的細節檔同樣比對，要新建的細節檔必須仍不存在）。第一次比對在 ack 之前、什麼都沒寫；
第二次比對在 ack 之後，所以 exit 2 時**除了 review.md 的 ack 標記外**不會寫任何檔。通過後先備份到
`.maigo/_internal/board/backup/<UTC ts>/`（§3a），再用同目錄 tmp＋rename 原子寫入；寫 board／細節檔失敗
從備份還原並 exit 3；board 已寫成功後 ledger／snapshot 才失敗也是 exit 3，但此時**不還原**、board 已是
新版（重跑安全，漏寫的事件會列在輸出裡）。

已知限制：某列抓料失敗時狀態詞會變 `抓不到`，恢復時 `refresh` 從該列細節檔的 H1 取回舊狀態詞；
若同一輪你手改了索引行的狀態詞、又剛好抓料失敗，恢復後會回到細節檔 H1 的舊狀態，手改的狀態詞不會保留。exit 2 的處理方式是**直接重跑**，不要改用 `Write`。

`.maigo/i/<slug>.md` 的「整份重寫事實區、保留手寫 `## 判斷` / `## 筆記`」同樣要求
**重寫前立即重讀**（script 則是上面的 CAS），理由相同。


細節檔生命週期（建立／更新／回收封存／孤兒偵測）與 board 位置細節（已遷移 vs 尚未遷移的 repo、報告與 board 的相對位置）：
- [`references/detail-lifecycle-and-location.md`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/references/detail-lifecycle-and-location.md)：**回收（封存）項目、處理孤兒細節檔、或在尚未遷移的 repo 找 board 時讀**。

| 命令 | 回寫時機 | 行為 |
|---|---|---|
| `/maigo:review` | 每顆 PR publish 後 | 依 report metadata + GitHub 重新 classify；待看／待送出 → 👀，已看完／已送且無新活動 → ⏳；同步 title、貢獻者與審查時間 |
| `/maigo:triage-issue` | 每個 verdict 出爐 | `READY`→🎯（next: take）；`NEEDS_INFO`→⏳；`DUP`/`CLOSE`→✅，duplicate / close 理由放狀態旁註。board 是本地檔，不違反 triage「不主動寫 GitHub」原則 |
| `/maigo:take-issue` | 開工時＋收尾 | 開工：issue 行標 `IN_PROGRESS` ＋ branch 名；收尾若開了 PR：新增 🔀 行、issue 行旁註 linked PR |
| `/maigo:describe-pr` | PR 開出後（若使用者說已開） | 新增/更新對應 🔀 行 → ⏳ `等 review` |
| `/maigo:address-comments` | 步驟 8（全部 work item 走完） | commit 未 push（**預設**——該命令不 push、不替使用者回覆）→ 🎯 留著，細節檔 `## 判斷` 區寫「push 了嗎——還沒就先 push」；使用者已自行 push 且回覆已送出 → ⏳ `等 review`（`## 判斷` 區留空） |

maigo 命令自己處理的項目**不勾 checkbox**——checkbox 專屬「使用者親自處理」的訊號（見 §5）。
`--reviewed` 是使用者的明確操作，可以勾（等同使用者在 nvim 手勾）。

**Work Board 每個 repo identity 只有一份，位置就是目前 worktree 的 `.maigo/board.md`。**
`.maigo` 預設是指向本機集中 root 的 symlink（`$MAIGO_STATE_HOME`，預設
`~/.local/share/maigo/state/<owner>/<repo>/`；SessionStart hook `repo_detect.py` 會建，
identity 與遷移細節見 [`.maigo/` 集中儲存](https://github.com/Lee-W/maigo/blob/main/docs/reference/state-storage.md)），同一個 repo 的
所有 worktree 讀寫同一份，board 不會因為某個 worktree 被 `git worktree remove` 而搬家，
也不必再找「哪個 worktree 有 board」。跑 board 回寫類命令（`/maigo:board`、
`address-comments` 步驟 8 等）時直接讀寫 `.maigo/board.md`；`board.md` 不存在 → 這個 repo
還沒有 board，問使用者要不要建，不要自己建。

**Upsert 紀律**（單項 upsert 的日期更新、容易被漏掉的獨立檢查、verdict 未必已送出 GitHub）
三條實務守則見
[`references/upsert-discipline.md`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/references/upsert-discipline.md)。

## 3a. 對帳、discovery 與排除紀錄

正典是 [`scripts/board_sync.py`](https://github.com/Lee-W/maigo/blob/main/scripts/board_sync.py)
（stdlib-only CLI：`plan` / `ack` / `drop` / `revive` / `snapshot` / `refresh`）。`plan` / `ack` / `drop` /
`revive` / `snapshot` 不寫 `board.md` 與 `i/*.md`，只輸出 JSON 變更清單，由 orchestrator 用 `Edit` 寫回
（§3(a) 規則不變）；`refresh --apply` 會整檔寫 `board.md` 與 `i/*.md`，規則見 §3(b)（CAS ＋ 備份 ＋ 原子寫入）。
`refresh` 不帶 `--apply` 是預覽：只印 unified diff，不寫任何檔、不 ack。從 shell 跑它即是零 token 刷新，
用法見 [`commands/board.md`](https://github.com/Lee-W/maigo/blob/main/commands/board.md)。

- [`references/reconcile-ledger.md`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/references/reconcile-ledger.md)：**跑 `plan` / `ack` / `drop` / `revive` / `snapshot`、判讀排除紀錄、discovery 或綁報告版本的 `[x]` ack 規則之前讀**。

## 4. 併入遷移與 4a 看完標記

遇到 `.maigo/review-board.md` 且 `board.md` 不存在時依遷移步驟搬行（舊檔改名 `.migrated` 留底）；`[x]` 看完 review 的 ack 流程亦在同檔。
- [`references/migration-and-ack.md`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/references/migration-and-ack.md)：**遷移舊 review-board.md，或處理 `--reviewed`／`[x]` ack 時讀**。

## 5. 學習閘門（checkbox → `--learn` → 記憶層）

勾選是學習閘門唯一訊號；刷新只列出待盤點項目，不自動進學習（學習有 AskUserQuestion 確認）；記憶寫入走 [`memory-propose-confirm`](https://github.com/Lee-W/maigo/blob/main/skills/memory-propose-confirm/SKILL.md)。
- [`references/learning-gate.md`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/references/learning-gate.md)：**執行 `--learn` 前讀**。

## 6. 在 nvim 裡怎麼用

真相層永遠是純 markdown 的 `.maigo/board.md`，maigo 不提供呈現層；`.maigo` 內連結都是檔案相對。
- [`references/nvim-usage.md`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/references/nvim-usage.md)：**回答使用者怎麼在 nvim 操作 board、或要整理舊筆記路徑（`rewrite_note_paths.py`）時讀**。

## 7. 跨 session 接續

`ListAgents` 查不到對應 session 時，先查 `.maigo/board.md` 的 `IN_PROGRESS` 行與 plan 檔接續，不必重走探索與規劃。
- [`references/session-resume.md`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/references/session-resume.md)：**接續一個找不到 session 的任務時讀**。

## What this skill does NOT cover

- `/maigo:board` 的命令面（無參數刷新 / `<targets...>` / `--all` / `--learn` /
  `--check` / `--uncheck` / `--reviewed` / `--unreviewed` / `--reviews` / `--drop`）——
  見 [`commands/board.md`](https://github.com/Lee-W/maigo/blob/main/commands/board.md)
- Review verdict 本身的判斷標準——那是
  [`strict-review`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md) /
  [`strict-triage`](https://github.com/Lee-W/maigo/blob/main/skills/strict-triage/SKILL.md) 的事，本 skill 只管球權落點與行文法
