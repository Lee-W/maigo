---
name: work-board
description: This skill should be used when reading, writing, or migrating `.maigo/board.md` — the single cross-session Work Board that tracks issues to triage, your own PRs, and PRs you're reviewing, bucketed by whose turn it is to act (🎯 你的球 / ⏳ 等別人 / ✅ merged-closed). Covers the line grammar, possession-判定 tables per item type, the upsert contract each writing command follows, the review-board.md migration path, and the checkbox → `--learn` memory gate.
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

## Why this skill exists

`/maigo:review` 的 `.maigo/review-board.md` 只涵蓋「reviewer 視角」。實際工作面是三種混在一起的球：
**要 triage / 接的 issue**、**自己開的 PR**、**在審別人的 PR**。Work Board 把它們併成一份，
核心機制沿用 review board 最有價值的部分：board 的存在意義不是收藏分類，
而是回答「**現在該我動哪些**」。

## 1. `.maigo/board.md` 格式規格

### Sections（固定順序）

```markdown
# Work Board — Lee-W/maigo
> 最後刷新：2026-07-09 14:30 ｜ 🎯 3 ｜ ⏳ 2 ｜ ✅ 1 ｜ 🧠 待學習盤點 2

## 🎯 你的球（3）
- [ ] 🐛 #123 (alice) **READY** — triage 完可接 → `/maigo:take-issue 123` — "fix xxx"
- [ ] 🔀 #456 (你) **CHANGES_REQUESTED** Δ +120/-45 — reviewer 要改 → `/maigo:address-comments` — "feat yyy"
- [x] 👀 #789 (bob) **↩︎ 回你的球** Δ +88/-12 — 你回過後又推新 commit → `/maigo:review 789` — "…"

## ⏳ 等別人（2）
- [ ] 🔀 #460 (你) **等 review** Δ +42/-7 — 最後活動是你 07-08 — "…"
- [ ] 🐛 #130 (carol) **NEEDS_INFO** — 等回報者補資訊 — "…"

## 📥 無法分類（0）
<!-- 只放 gh 抓不到的（權限 / 打錯號碼 / 網路失敗），抓得到的一律直接分桶 -->

## ✅ Merged / closed（最近 7 天）
- [x] 👀 #700 (dave) **APPROVE** Δ +31/-9 🧠 — merged 07-07 — "…"

## 🗄️ 已放棄（1）
- [ ] 🐛 #99 (eve) **已放棄** — `--drop` 軟刪，7 天後可清 — "…"
```

### 行文法

```text
- [ ] <型別emoji> #<n 或 owner/repo#n> (<作者>) **<狀態詞>** Δ +<additions>/-<deletions> — <一句話理由> → `<下一步命令>` 📄 `<產物路徑>` — "<title>"
```

- **型別 emoji**：🐛 issue ｜ 🔀 你的 PR ｜ 👀 在審的 PR
- **作者**：issue / PR 的 author；自己的 PR 寫 `(你)`，served 表格會拆成獨立欄位
- **`Δ +A/-D`**（PR 必填、issue 省略）：GitHub `additions` / `deletions`；閱讀層另以
  `A + D` 作為「改動量」排序 key
- **`→ 下一步命令`**：只有 🎯 區的行有——看到就能複製執行，這是「最好讀寫」的核心
- **`📄 產物路徑`**（optional）：指向這項的本地產物（review-<n>.md / triage 筆記等），相對
  `.maigo/` 的路徑。沒產物就省略。真相層不塞 markdown link；served 表格
  會把它轉成可點的本地 report 連結（見 §6）
- **checkbox**：`[x]` ＝「這項我**親自**處理過了」（學習閘門訊號，見 §5）；與所在分區正交
- **🧠 標記**：學習盤點已完成，不重複學
- **💤 標記**：`updatedAt` 逾期未更新（stale badge，見 §2 vocabulary 表下方說明），跟
  `🧠` 一樣是正交於狀態詞的 badge，不影響 bucket / tier
- **跨 repo**：board 綁 cwd repo（header 記 `gh repo view --json nameWithOwner` 結果）；
  丟進來的 URL 若屬其他 repo，行內用 `owner/repo#n` 全稱
- 旁註沿用 review board 慣例：DRAFT / 指定 anchor / 他人 review decision 放狀態詞後面

### 狀態詞 vocabulary（依型別，含 tier）

tier 決定 UI 顏色，五級由緊急到不急：`blocked`(紅) / `act`(琥珀) / `wip`(藍) / `wait`(灰) / `done`(綠)。
**正典在 [`scripts/board_state.py`](https://github.com/Lee-W/maigo/blob/main/scripts/board_state.py) 的 `BoardStatus` enum ＋ `_STATUS_META`**，
本表只是人類可讀鏡像，兩者須一致（由 `tests/test_board_state.py` 守）。

| 型別 | 狀態詞 | tier |
|---|---|---|
| 🐛 issue | `待 triage` | act |
| 🐛 issue | `READY` | act |
| 🐛 issue | `IN_PROGRESS` | wip |
| 🐛 issue | `有新回覆` | act |
| 🐛 issue | `NEEDS_INFO` | wait |
| 🐛 issue | `DUP` / `CLOSE` | done |
| 🔀 你的 PR | `WIP` | wip |
| 🔀 你的 PR | `有衝突` | blocked |
| 🔀 你的 PR | `CI 紅` | blocked |
| 🔀 你的 PR | `CHANGES_REQUESTED` | blocked |
| 🔀 你的 PR | `有新 comment` | act |
| 🔀 你的 PR | `可合併` | act |
| 🔀 你的 PR | `CI 等待` | wait |
| 🔀 你的 PR | `等 review` | wait |
| 👀 在審的 PR | `他人草稿` | wait |
| 👀 在審的 PR | `待 review` | act |
| 👀 在審的 PR | `↩︎ 回你的球` | act |
| 👀 在審的 PR | `BLOCKED` / `NEEDS_CHANGES` / `APPROVE_WITH_NITS` / `APPROVE` | wait |
| 跨型別終端 | `closed` / `merged` | done |
| 跨型別 | `已放棄`（進 🗄️ 已放棄 section） | done |

triage verdict 沿用 [`strict-triage`](https://github.com/Lee-W/maigo/blob/main/skills/strict-triage/SKILL.md)、
review verdict 沿用 [`strict-review`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md)，不另造詞。

**badge（正交於狀態詞，不佔 bucket）**：`🧠` 已完成學習盤點；`💤` stale——`updatedAt`
逾 14 天（`scripts/board_state.py --stale-days` 可調），提示這顆球可能被遺忘，不改變 bucket / tier。
兩者都寫在 `Δ +A/-D` 之後、理由之前，例：`Δ +12/-3 🧠💤 — ...`。

**不在 enum 內的狀態詞**（手改壞、或舊工具寫入的殘留字）在 `--serve` 閱讀層會顯示紅框
「⚠ 未知狀態」，不會靜默落灰——見 §6。

**向下相容**：新 vocab 是舊 vocab 的超集，沒有任何舊狀態詞被移除或改名。第一次
`/maigo:board` 刷新時，`board_state.py` 的 `classify()` 會用 `prior_status` 重算每一行，
未知或已停用的狀態詞視為 `None`（等同剛加入），自動正規化成新表的對應狀態——不需要
手動遷移步驟，沿用既有「刷新即正規化」的遷移慣例。

### 排序

- 🎯 區：**球到你手上的時間升序**——最久沒回的最上面（責任感排序）
- ⏳ / ✅ 區：最後活動時間降序
- ✅ 區超過 7 天的行在刷新時自動清掉（唯一例外：`🧠` 待盤點未完成的行不清，學完才走）
- 🗄️ 已放棄區：`/maigo:board --drop` 的軟刪落點（tombstone），保留留痕，7 天後才可清——
  本輪只做軟刪，purge 尚未實作（見 `commands/board.md` §8）

## 2. 型別偵測與球權判定

### 型別偵測（加 item 時跑一次）

1. URL → 直接解析 owner/repo + 型別 + 編號
2. 裸編號 → `gh api repos/<owner>/<repo>/issues/<n>`，有 `pull_request` key ＝ PR
3. PR 再看 `author.login` 是否等於 `gh api user --jq .login` → 🔀 vs 👀
4. `gh` 抓不到 → 進 📥，附錯誤末行

### 刷新時抓的欄位

```bash
# issue
gh issue view <n> --repo <r> --json state,stateReason,assignees,author,comments,updatedAt,labels,closedByPullRequestsReferences
# PR（自己的與在審的同一組）
gh pr view <n> --repo <r> --json state,isDraft,mergedAt,mergeable,reviewDecision,updatedAt,reviews,comments,author,statusCheckRollup,additions,deletions
```

「你」＝ `gh api user --jq .login`（沿用 review board 既有做法）。
「你最後活動 vs 他人最後活動」的比對邏輯：把 comments + reviews 的 author + 時間戳整理成
`gh_meta`，交給 [`scripts/board_state.py`](https://github.com/Lee-W/maigo/blob/main/scripts/board_state.py)
的 `classify()` 純函式比較——這是這次重構後的**判定邏輯正典**，本節三張表只是它的人類可讀
鏡像，兩者不一致以程式為準（`tests/test_board_state.py` 逐條守）。

呼叫方式（薄 CLI，stdin 餵 JSON 陣列 `[{type, gh_meta, prior_status}]`）：

```bash
echo '[{"type": "🐛", "gh_meta": {"state": "OPEN"}, "prior_status": null}]' \
  | python3 scripts/board_state.py --you <login>
```

`mergeable` 欄位可能回 `CONFLICTING` / `MERGEABLE` / `UNKNOWN`（GitHub 尚在計算）；
`classify()` 只在明確 `CONFLICTING` 時判定衝突，`UNKNOWN` fallthrough 到其他規則，不誤判。

### 球權判定表（merged / closed 一律優先 → ✅；由上往下第一個命中）

**🐛 issue**：

| 條件 | 狀態 | bucket | tier |
|---|---|---|---|
| `state == CLOSED` | `closed`（stateReason / linked PR 併入旁註） | ✅ | done |
| prior 為 `DUP` / `CLOSE` | 保留該 verdict | ✅ | done |
| board 無 verdict（剛加入、從未 triage） | `待 triage` → `/maigo:triage-issue <n>` | 🎯 | act |
| prior `READY` 且無 assignee（或 assignee 是你） | `READY` → `/maigo:take-issue <n>` | 🎯 | act |
| 已 take（prior `IN_PROGRESS`） | `IN_PROGRESS`（旁註 branch 名） | 🎯 | wip |
| 你最後活動後有別人新 comment | `有新回覆` → `/maigo:triage-issue <n>`（重判） | 🎯 | act |
| prior `NEEDS_INFO` 或你留言後無新活動 | `NEEDS_INFO` | ⏳ | wait |

**🔀 你的 PR**（每次刷新純由 gh metadata 重算，不看 prior_status）：

| 條件 | 狀態 | bucket | tier |
|---|---|---|---|
| merged / closed | `merged` / `closed` | ✅ | done |
| `isDraft == true` | `WIP`（自己 draft＝還在寫） | 🎯 | wip |
| `mergeable == CONFLICTING` | `有衝突` → `/maigo:address-comments` | 🎯 | blocked |
| `statusCheckRollup` 有 FAILURE | `CI 紅` | 🎯 | blocked |
| `reviewDecision == CHANGES_REQUESTED` | `CHANGES_REQUESTED` → `/maigo:address-comments` | 🎯 | blocked |
| 你最後 push/comment 後有別人 review/comment | `有新 comment` → `/maigo:address-comments` | 🎯 | act |
| `reviewDecision == APPROVED` 且 CI 綠 | `可合併` | 🎯 | act |
| `statusCheckRollup` 有 PENDING（其餘正常） | `CI 等待` | ⏳ | wait |
| 其他（最後活動是你） | `等 review` | ⏳ | wait |

**👀 在審的 PR**（重建斷鏈的判定表——舊版沿用 review board 四格表已於本次重構退役）：

| 條件 | 狀態 | bucket | tier |
|---|---|---|---|
| merged / closed | `merged` / `closed` | ✅ | done |
| `isDraft == true` | `他人草稿`（未被邀請不主動審） | ⏳ | wait |
| 你從未 review（無 prior verdict） | `待 review` → `/maigo:review <n>` | 🎯 | act |
| 有 prior verdict 且你上次 review 後 author 有新 commit/comment | `↩︎ 回你的球` → `/maigo:review <n>`（重審） | 🎯 | act |
| 有 prior verdict 且無新 author 活動 | 保留該 verdict：`BLOCKED` / `NEEDS_CHANGES` / `APPROVE_WITH_NITS` / `APPROVE` | ⏳ | wait |

review verdict 詞彙沿用 [`strict-review`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md)；
per-PR queue 排序 / 前置處理（merged / closed / draft 自動 skip 或問使用者）另見
[`review-batch-queue.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/review-batch-queue.md)，
那份文件管的是 **per-run 排隊**，跟本表管的**跨 session 落點**是兩件事。

## 3. 各命令回寫合約

**upsert 規則**：以 `#<n>`（含 repo 全稱時用全稱）為 key；行存在→整行替換
（**保留原 checkbox 與 🧠 狀態**），不存在→append 到對應 section；board 檔不存在就先建骨架。

| 命令 | 回寫時機 | 行為 |
|---|---|---|
| `/maigo:review` | 每顆 PR 出完 report | 本地 verdict → 🎯 留著；已送 GitHub → ⏳ |
| `/maigo:triage-issue` | 每個 verdict 出爐 | `READY`→🎯（next: take）；`NEEDS_INFO`→⏳；`DUP`/`CLOSE`→✅ 附理由。board 是本地檔，不違反 triage「不主動寫 GitHub」原則 |
| `/maigo:take-issue` | 開工時＋收尾 | 開工：issue 行標 `IN_PROGRESS` ＋ branch 名；收尾若開了 PR：新增 🔀 行、issue 行旁註 linked PR |
| `/maigo:describe-pr` | PR 開出後（若使用者說已開） | 新增/更新對應 🔀 行 → ⏳ `等 review` |
| `/maigo:address-comments` | 回覆送出後 | 🔀 行 → ⏳ `等 review` |

maigo 命令自己處理的項目**不勾 checkbox**——checkbox 專屬「使用者親自處理」的訊號（見 §5）。

## 4. 併入遷移（review-board.md 退役）

首次跑 `/maigo:board`（或某回寫命令要寫 board 時）偵測到 `.maigo/review-board.md`
存在且 `board.md` 不存在：

1. 讀舊檔，按分區映射搬行：`Active` + `↩︎ 回你的球` → 🎯；`Off-board` → ⏳；
   `Merged/closed` → ✅；`🔍 本批佇列` → 依 §2 重判
2. 舊行格式 `- #<PR> (<author>) …` 補上 `- [ ] 👀` 前綴，狀態詞照搬
3. 舊檔改名 `review-board.md.migrated`（留底不刪），之後一切只寫 `board.md`
4. [`review-batch-queue.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/review-batch-queue.md)
   的「持久 review board」段落改為指向本 skill，只保留 review 特有的 verdict 語彙說明

## 5. 學習閘門（checkbox → `--learn` → 記憶層）

使用者需求原文脈絡：打勾＝「我看過/我親自處理了」，maigo 去看**你實際怎麼處理的**，判斷要不要把這項知識學下來。

1. **勾**：使用者在任何編輯器把 `- [ ]` 改 `- [x]`（nvim 一鍵）。勾與分區正交、跨刷新保留。
   也可用 `/maigo:board --check <n...>`；要取消就用 `--uncheck`。這兩個命令只改
   checkbox，保留分區、整行內容與 `🧠`，並且 idempotent。
2. **偵測**：`/maigo:board` 刷新時列出「已勾且無 🧠」的項目，提示跑 `--learn`。刷新本身**不**
   自動進學習——學習有 AskUserQuestion 確認，不該混進快速刷新。
3. **抓料**（`--learn`，委派 sonnet，一項一隻或小批）：抓該 item 上**你的**實際輸出——
   review：你的 review comments / verdict；issue：你的 triage 回覆；你的 PR：你怎麼回 reviewer。
   對照 maigo 記憶層現有條目，蒸餾 0–3 條候選知識（「使用者在 X 類 PR 特別看 Y」「使用者回
   NEEDS_INFO 的口吻慣例是 Z」）。沒有可學的就回「無候選」，不硬湊。
4. **確認**：orchestrator 走既有
   [`memory-propose-confirm`](https://github.com/Lee-W/maigo/blob/main/skills/memory-propose-confirm/SKILL.md) skill，
   逐條 AskUserQuestion，確認的寫進 `~/.config/maigo/memory/`（type: feedback / project 按內容判）。
5. **標記**：處理完（含「無候選」）該行加 `🧠`；之後刷新不再提示。反覆出現的知識日後由
   [`/maigo:crystallize`](https://github.com/Lee-W/maigo/blob/main/commands/crystallize.md) 畢業成 skill——學習閘門只負責進料，不重造管線。

## 6. 閱讀層：`--serve`（MkDocs Material 表格）

真相層永遠是純 markdown 的 `.maigo/board.md`——agent 跟人都直接改它，不為排版
混入 HTML wrapper。`/maigo:board --serve` 跑
[`scripts/board_serve.py`](https://github.com/Lee-W/maigo/blob/main/scripts/board_serve.py)
把它變成一個會 live reload 的本地網頁：

1. **scaffold**：首跑在 `.maigo/_serve/` 生成 `mkdocs.yml` ＋ `board-style.css`
   （gitignored 工作區，不是真相層）。未修改的舊版 scaffold 會自動升級；
   偵測到使用者自訂內容時不覆寫，而是提示手動合併。
2. **docs_dir 直指 `.maigo/`**：`board.md` 跟其他 `.md`（📄 連結的 review report 等產物）
   由同一個 server 直接渲染——不再有另外的 render 步驟，也不再另外產生一份閱讀層檔案。
3. **表格 hook**：[`scripts/board_serve_hook.py`](https://github.com/Lee-W/maigo/blob/main/scripts/board_serve_hook.py)
   只在渲染 `board.md` 時把每個球權分區的單行資料轉成七欄表格：「我處理過、項目、
   作者、改動、狀態、現況、下一步」。不做 Kanban 橫向分欄；依然保留球權 section 的語意。
   狀態欄底色查 `board_state.tier_for_status()`，回 5 個 tier class
   （`status-blocked/act/wip/wait/done`）而非固定四色；不在 enum 內的狀態詞回
   `status-unknown`（紅框 + 「⚠ 未知狀態」字樣），不靜默落灰。
4. **可點的閱讀層**：`#n` 會連到 GitHub issue / PR，`📄 \`路徑\`` 會連到同站渲染的
   本地 report。導覽只列 Work Board，不把 `.maigo/` 內所有 report 擠成頂部清單。
5. **checkbox**：表格保留「我處理過」checkbox 與 `🧠` 學習狀態，但網頁仍是唯讀；
   勾選回寫一樣只改真相層 `board.md` 本身。`pymdownx.tasklist` 保留作為無法解析行的 fallback。
6. **篩選與排序**：原生 JavaScript 在閱讀層提供全文搜尋、類型 / 狀態篩選，以及
   作者、標題、改動量排序。排序只改當下 DOM，且只在各球權 section 內進行；
   不回寫 `board.md`，不破壞「球到你手上的時間」責任排序。
7. **列操作選單**：每列可複製 `maigo:board --check` / `--uncheck` / `--drop`。
   這只是 clipboard helper；served 頁面不開寫檔 API，不直接變更真相層。
8. **首頁**：`board.md` 不是 `index.md`——script 不額外造一份 index scaffold 去污染
   `.maigo/`，直接印出 board 頁網址（`http://<addr>/board/`）。
9. **啟動優先序**：cwd 專案 venv 已裝 MkDocs Material 與 pymdown-extensions →
   `uv run mkdocs serve -f <config>`；沒有 →
   `uvx --from mkdocs-material --with pymdown-extensions mkdocs serve -f <config>`
   （zero repo 相依，maigo 在其他 repo 的 `.maigo/` 一樣可用）。
10. **live reload**：MkDocs 內建 watch，agent 寫 board.md 或使用者 nvim 存檔，served
   頁面幾秒內更新，不需要手動重跑任何 render 指令。
11. **退場門**：serve 引擎只是手段——`config` 極小、真相層是純 markdown，隨時可換掉
   整個引擎。Zensical 曾是 v2 原定候選，但實作輪驗證出對 hidden 開頭目錄
   （`.maigo/`）靜默零收錄、symlink 繞法會讓 watcher 追不到真相層變更兩個阻斷性
   問題，v2.1 起降為未來選項（待上游修復再評估回歸；證據見
   `.maigo/board-design.md` §12 修訂段）。v1 的靜態 HTML ＋ pandoc materialize_docs
   渲染腳本已整檔退役，不再維護。
12. **只能前景執行**：`--serve` 要一直開著終端機、Ctrl-C 結束，不要背景 detach——
   父行程被 SIGTERM 終止時子行程會孤兒化佔 port。

## What this skill does NOT cover

- `/maigo:board` 的命令面（無參數刷新 / `<targets...>` / `--all` / `--serve` / `--learn` /
  `--check` / `--uncheck` / `--drop`）——
  見 [`commands/board.md`](https://github.com/Lee-W/maigo/blob/main/commands/board.md)
- Review verdict 本身的判斷標準——那是
  [`strict-review`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md) /
  [`strict-triage`](https://github.com/Lee-W/maigo/blob/main/skills/strict-triage/SKILL.md) 的事，本 skill 只管球權落點與行文法
