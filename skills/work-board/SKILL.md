---
name: work-board
description: This skill should be used when reading, writing, or migrating `.maigo/board.md` — the single cross-session Work Board that tracks issues to triage, your own PRs, and PRs you're reviewing, ranked into a single priority ladder (🎯 下一件 / ⏳ 等別人 / ✅ 最近結案). Covers the line grammar, possession-判定 tables per item type, the upsert contract each writing command follows, the review-board.md migration path, and the checkbox → `--learn` memory gate.
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

### Sections（固定順序，三個 section 即 treesitter fold 邊界）

```markdown
# Work Board — Lee-W/maigo
> 最後刷新：2026-08-18 14:30 ｜ 🎯 3 ｜ ⏳ 2 ｜ ✅ 1 ｜ 🧠 待學習盤點 1

## 🎯 下一件（3）

1. [ ] 🔀 CHANGES_REQUESTED i/9201.md — Redesign Work Board reading view
2. [x] 👀 ↩︎ 回你的球 i/9301.md — Avoid duplicate GitHub requests
3. [ ] 🐛 待 triage 💤 i/9101.md — CLI 在空設定檔時會 crash

## ⏳ 等別人（2）

- [ ] 🔀 等 review i/9202.md — Document plugin installation flow
- [ ] 🐛 NEEDS_INFO（已請補作業系統與完整 log） i/9103.md — Hook occasionally exits without output

## ✅ 最近結案（1）

- [x] 👀 APPROVE（merged 07-12） 🧠 i/9303.md — Add structured review verdicts
```

`i/9201.md` 對應的細節檔（相對 `.maigo/`）：

```markdown
# 🔀 CHANGES_REQUESTED — Redesign Work Board reading view

- 連結：https://github.com/Lee-W/maigo/pull/9201
- 規模：Δ+286/-74
- 下一步：`/maigo:address-comments`

## 判斷

補測試還是反駁 reviewer

## 筆記

<!-- 手寫區 -->
```

細節檔格式規格見 §1a；欄位省略規則（`作者`／`規模`／`下一步` 何時整行不寫）與 upsert
生命週期（建立/更新/回收/孤兒偵測）也在該節。

- **🎯 下一件**：Rank P0–P7，**編號清單**（`1. [ ]`），第 1 行就是下一件事。
- **⏳ 等別人**：Rank P8，checkbox 清單、無編號——球不在你手上，這區是查閱，不是待辦。
- **✅ 最近結案**：Rank P9，checkbox 清單、無編號，7 天後自動清（`🧠` 待盤點未完成的行不清）。
- 舊版另外兩個獨立 section（收 `gh` 抓不到的項目、收軟刪項目的那兩區）**已取消**：
  `gh` 抓不到的項目改判 `抓不到`（P0），併進 🎯 最上面；`--drop` 改成把該行移進 ✅ 最近結案、狀態詞
  `已放棄`，跟其他結案行共用同一條 7 天老化規則。

### 行文法

**設計原則：行動資訊全部壓在前段（最寬 60 顯示欄內），title 放最後、允許被視窗切掉、
不截斷。** 視窗窄時被切掉的永遠只有 title 尾巴，決策段（編號/checkbox/型別/狀態/
細節檔路徑）一定看得到；視窗寬時 title 自動看全，不必為截斷取捨。`.maigo/` 已被
`.gitignore:2` 排除，board.md **不進 repo、不被任何 renderer 渲染**——唯一要滿足的是
「treesitter 高亮/fold 不出錯 ＋ 人讀得順 ＋ parser 切得開」，不必為 GFM 相容性讓步。
URL、規模（Δ+A/-D）、作者、下一步、判斷句這些細節全部搬進 `.maigo/i/<slug>.md`
細節檔（§1a），索引行只留決策當下要看的欄位。

```text
🎯 區：<n>. [ ] <型別emoji> <狀態詞>[（旁註）][ <badges>] <細節檔路徑> — <title>
⏳/✅ 區：- [ ] <型別emoji> <狀態詞>[（旁註）][ <badges>] <細節檔路徑> — <title>
```

- **一行一項、絕不換行**：`/` 搜尋與 `dd` 刪除都以行為單位；換行會讓兩者都失準。
- **型別 emoji**：🐛 issue ｜ 🔀 你的 PR ｜ 👀 在審的 PR
- **編號 ＋ checkbox 混排（僅 🎯 區）**：`1. [ ]`。使用者選定編號清單，checkbox 是學習閘門
  的唯一訊號（§5），兩者都要留；⏳/✅ 區是查閱不是待辦，維持無編號的 `- [ ]`。
- **旁註**（沿用 review board 慣例，optional）：branch 名、closed 理由、linked PR、DRAFT、
  他人 review decision 這類「per-item 事實」寫在狀態詞後面的括弧裡
  （例：`IN_PROGRESS（分支 fix/xxx）`）——旁註記事實，判斷句記決定，兩者不是同一件事；
  判斷句本身已搬進細節檔（§1a）。
- **badges**（`🧠`/`💤`，optional）：緊接在旁註之後、細節檔路徑之前，用一個空格分隔；
  §2 vocabulary 表下方有各自的觸發規則。
- **細節檔路徑（必填、裸相對路徑、不加反引號）**：相對 `.maigo/`，由
  [`detail_path()`](https://github.com/Lee-W/maigo/blob/main/scripts/board_state.py)
  算出——同 repo 是 `i/<n>.md`，跨 repo 是 `i/<repo>-<n>.md`。**不加反引號**：反引號會擋住
  nvim `gf`；游標停在路徑上 `gf` 直接開對應細節檔（格式見 §1a、操作見 §6）。
- **`— <title>` 的 `—` 分隔符是強制的，parser 不會用啟發式猜**：title 前面那個 `—`
  一定要打；title **不再加引號**（title 已是行尾最後一欄，引號在舊文法是為了跟後續欄位
  切開，現在只是純雜訊）。漏打分隔符一律回報格式壞掉，寫回命令**大聲失敗**，不靜默留空
  ——比照未知狀態詞。
- **checkbox**：`[x]` ＝「這項我**親自**處理過了」（學習閘門訊號，見 §5）；與所在 section 正交。
- **🧠 標記**：學習盤點已完成，不重複學。
- **💤 標記**：`updatedAt` 逾期未更新（stale badge，見 §2 vocabulary 表下方說明），跟
  `🧠` 一樣是正交於狀態詞的 badge，不影響 rank / section。
- **跨 repo**：board 綁 cwd repo（header 記 `gh repo view --json nameWithOwner` 結果）；
  丟進來的 URL 若屬其他 repo，細節檔路徑改用 `i/<repo>-<n>.md` 形式（見上），真 URL
  完整記在該項的細節檔 `連結` 欄裡，不在索引行出現。
- **空白容錯**：旁註 `（…）` 與緊接著的 badges／細節檔路徑之間有沒有留空格，parser 都吃得下
  （nvim 手改最容易漏這格空白）。

### 1a. 細節檔格式 `.maigo/i/<slug>.md`

索引行搬走的欄位（URL、規模 Δ+A/-D、作者、下一步、判斷句、舊 `📄 <產物路徑>`）全部
收進這份細節檔：

```markdown
# <型別emoji> <狀態詞> — <title>

- 連結：<URL>
- 規模：Δ+A/-D ｜ 作者：<author>
- 下一步：`<next_action>`

## 判斷

<判斷句——你現在要決定什麼，不寫發生了什麼>

## 筆記

<!-- 手寫區 -->
```

**硬規則：refresh 或任何寫回只重寫 `## 判斷` 之前的事實區（標題行 ＋ 三條 metadata），
`## 判斷` 與 `## 筆記` 兩段一律原樣保留，絕不覆蓋。** 細節檔不存在時才整份新建
（判斷句寫進 `## 判斷`、`## 筆記` 留空）。這條硬規則適用於**所有**寫回路徑——`/maigo:board`
的 refresh 以及五個 delegate 命令（review / triage-issue / take-issue / describe-pr /
address-comments）各自的 upsert，沒有例外可以整份覆蓋掉細節檔清掉使用者手寫的 `## 筆記`。

**撞號限制與後果**：`detail_path()` 的 `<repo>` 只取 repo 名、不含 owner（見
[`scripts/board_state.py`](https://github.com/Lee-W/maigo/blob/main/scripts/board_state.py)
docstring），所以不同 owner 的同名 repo（例如 `astronomer/astro` 與另一個 owner 的
`astro`）在跨 repo 情境會共用同一個 `i/<repo>-<n>.md`——兩項的事實區與 `## 判斷` /
`## 筆記` 會互相覆蓋。這是刻意的取捨（路徑短優先），目前**不自動處理**；真的撞號時
手動把其中一份細節檔改名（並同步索引行的細節檔路徑）即可繞開。

欄位省略規則：

- **作者**：🔀 你的 PR 省略整個「｜ 作者：…」（型別 emoji 已定義「這是你的 PR」，
  `作者：你` 是贅字）。
- **規模**：issue 省略整行（沒有 additions/deletions 可言）。
- **下一步**：`next_action` 為 `null` 時省略整行——狀態沒有對應下一步，見
  [`scripts/board_state.py`](https://github.com/Lee-W/maigo/blob/main/scripts/board_state.py)
  的 `_STATUS_META`（`WIP` / `IN_PROGRESS` / P8 / P9 / P0 這類狀態）。
- **舊 `📄 <產物路徑>`**（review-<n>.md / triage 筆記等本地產物）：改寫進 `## 筆記`
  區裡的一行裸相對路徑連結（例：`review-9301.md`），不佔事實區欄位。
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
| 🔀 你的 PR | `有新 comment` | P2 |
| 🔀 你的 PR | `可合併` | P3 |
| 🔀 你的 PR | `CI 等待` | P8 |
| 🔀 你的 PR | `等 review` | P8 |
| 👀 在審的 PR | `他人草稿` | P8 |
| 👀 在審的 PR | `待 review` | P4 |
| 👀 在審的 PR | `↩︎ 回你的球` | P2 |
| 👀 在審的 PR | `待送出`（本地 verdict 從未貼上 GitHub） | P3 |
| 👀 在審的 PR | `BLOCKED` / `NEEDS_CHANGES` / `APPROVE_WITH_NITS` / `APPROVE` | P8 |
| 跨型別終端 | `closed` / `merged` | P9 |
| 跨型別 | `已放棄`（`--drop` 軟刪，進 ✅ 最近結案） | P9 |

triage verdict 沿用 [`strict-triage`](https://github.com/Lee-W/maigo/blob/main/skills/strict-triage/SKILL.md)、
review verdict 沿用 [`strict-review`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md)，不另造詞。

**badge（正交於狀態詞，不佔 rank）**：`🧠` 已完成學習盤點；`💤` stale——`updatedAt`
逾 14 天（`scripts/board_state.py --stale-days` 可調），提示這顆球可能被遺忘，不改變 rank / section。
兩者都寫在旁註之後、細節檔路徑之前，例：`🎯 1. [ ] 🔀 WIP 🧠💤 i/12.md — <title>`。

**不在 enum 內的狀態詞**（手改壞、或舊工具寫入的殘留字）——寫回命令刷新該行時大聲失敗，
不靜默正規化成任何看似合理的狀態，比照 `— <title>` 分隔符解析失敗的處理方式。

**向下相容**：新 vocab 是舊 vocab 的超集，沒有任何舊狀態詞被移除或改名（僅新增
`抓不到`／`待送出` 兩個）。第一次 `/maigo:board` 刷新時，`board_state.py` 的 `classify()`
會用 `prior_status` 重算每一行，未知或已停用的狀態詞視為 `None`（等同剛加入），自動
正規化成新表的對應狀態——不需要手動遷移步驟，沿用既有「刷新即正規化」的遷移慣例。
讀到舊版任何 section 標題（球權三分區時代的四個舊標題）時同樣吃得進來：取 checkbox /
`🧠` / 狀態詞後，整檔以新骨架（三個 section）重寫，不做逐行 in-place 遷移。

### 排序

- 🎯 區：**rank 升序 → 同 rank 內 `updatedAt` 升序**——排名先分先後，同一級內最久沒動的
  排前面（沿用舊「責任感排序」的精神，但改成明確的 `updatedAt`）。編號 `1. 2. 3.` 就是
  這個排序結果，排名本身不顯示在行內。
- ⏳ / ✅ 區：`updatedAt` 降序（這兩區是查閱，不是待辦）。
- ✅ 區超過 7 天的行在刷新時自動清掉（唯一例外：`🧠` 待盤點未完成的行不清，學完才走）。
  `/maigo:board --drop` 的落點也是這裡（狀態詞改 `已放棄`），跟其他結案行共用同一條
  老化規則，不再有獨立的 tombstone 區。

## 2. 型別偵測與球權判定

### 型別偵測（加 item 時跑一次）

1. URL → 直接解析 owner/repo + 型別 + 編號
2. 裸編號 → `gh api repos/<owner>/<repo>/issues/<n>`，有 `pull_request` key ＝ PR
3. PR 再看 `author.login` 是否等於 `gh api user --jq .login` → 🔀 vs 👀
4. `gh` 抓不到 → 狀態詞 `抓不到`（P0，orchestrator 指派），併進 🎯 最上面，附錯誤末行

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

| 條件 | 狀態 | section | rank |
|---|---|---|---|
| `state == CLOSED` | `closed`（stateReason / linked PR 併入旁註） | ✅ | P9 |
| prior 為 `DUP` / `CLOSE` | 保留該 verdict | ✅ | P9 |
| board 無 verdict（剛加入、從未 triage） | `待 triage` → `/maigo:triage-issue <n>` | 🎯 | P6 |
| prior `READY` 且無 assignee（或 assignee 是你） | `READY` → `/maigo:take-issue <n>` | 🎯 | P7 |
| 已 take（prior `IN_PROGRESS`） | `IN_PROGRESS`（旁註 branch 名） | 🎯 | P5 |
| 你最後活動後有別人新 comment | `有新回覆` → `/maigo:triage-issue <n>`（重判） | 🎯 | P2 |
| prior `NEEDS_INFO` 或你留言後無新活動 | `NEEDS_INFO` | ⏳ | P8 |

**🔀 你的 PR**（每次刷新純由 gh metadata 重算，不看 prior_status）：

| 條件 | 狀態 | section | rank |
|---|---|---|---|
| merged / closed | `merged` / `closed` | ✅ | P9 |
| `isDraft == true` | `WIP`（自己 draft＝還在寫） | 🎯 | P5 |
| `mergeable == CONFLICTING` | `有衝突` → `/maigo:address-comments` | 🎯 | P1 |
| `statusCheckRollup` 有 FAILURE | `CI 紅` → `gh pr checks <n>` | 🎯 | P1 |
| `reviewDecision == CHANGES_REQUESTED` | `CHANGES_REQUESTED` → `/maigo:address-comments` | 🎯 | P1 |
| 你最後 push/comment 後有別人 review/comment | `有新 comment` → `/maigo:address-comments` | 🎯 | P2 |
| `reviewDecision == APPROVED` 且 CI 綠 | `可合併` → `gh pr merge <n>` | 🎯 | P3 |
| `statusCheckRollup` 有 PENDING（其餘正常） | `CI 等待` | ⏳ | P8 |
| 其他（最後活動是你） | `等 review` | ⏳ | P8 |

**👀 在審的 PR**（重建斷鏈的判定表——舊版沿用 review board 四格表已於本次重構退役）：

| 條件 | 狀態 | section | rank |
|---|---|---|---|
| merged / closed | `merged` / `closed` | ✅ | P9 |
| `isDraft == true` | `他人草稿`（未被邀請不主動審） | ⏳ | P8 |
| 你從未 review（無 prior verdict） | `待 review` → `/maigo:review <n>` | 🎯 | P4 |
| 有 prior verdict（`_REVIEW_ACTIVE_VERDICTS`）但 `reviews` 裡沒有你送出的 review | `待送出` → `gh pr review <n> --comment --body-file .maigo/review-<n>.md` | 🎯 | P3 |
| 有 prior verdict、`reviews` 裡有你、且你上次 review 後 author 有新 commit/comment | `↩︎ 回你的球` → `/maigo:review <n>`（重審） | 🎯 | P2 |
| 有 prior verdict、`reviews` 裡有你、且無新 author 活動 | 保留該 verdict：`BLOCKED` / `NEEDS_CHANGES` / `APPROVE_WITH_NITS` / `APPROVE` | ⏳ | P8 |

review verdict 詞彙沿用 [`strict-review`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md)；
per-PR queue 排序 / 前置處理（merged / closed / draft 自動 skip 或問使用者）另見
[`review-batch-queue.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/review-batch-queue.md)，
那份文件管的是 **per-run 排隊**，跟本表管的**跨 session 落點**是兩件事。

## 3. 各命令回寫合約

**upsert 規則**：以 `#<n>`（含 repo 全稱時用全稱）為 key；行存在→整行替換
（**保留原 checkbox 與 🧠 狀態**），不存在→append 到對應 section；board 檔不存在就先建骨架。
**整行替換時，對應細節檔（`.maigo/i/<slug>.md`）必須跟著整份重寫，不可只改索引行漏改
細節檔**——索引行與細節檔是同一次寫回的兩個產物，不允許其中一個落後。

### 細節檔生命週期

- **建立**：項目首次進 board → 建細節檔（§1a）。
- **更新**：refresh 或任何寫回 → 重寫事實區，`## 判斷` / `## 筆記` 原樣保留（§1a 硬規則）。
- **回收**：項目離開 board（✅ 區 7 天老化清除、`--drop` 後也走同一條老化規則）→
  連細節檔一起刪，不留孤兒檔。
- **孤兒偵測**：`/maigo:board` 刷新時比對 `.maigo/i/*.md` 與 board 索引行，多出來的檔案
  列出來給使用者確認後刪，不自動刪。

| 命令 | 回寫時機 | 行為 |
|---|---|---|
| `/maigo:review` | 每顆 PR 出完 report | 本地 verdict 尚未送 GitHub → 🎯 留著，狀態詞寫 `待送出`；已送 GitHub → ⏳ |
| `/maigo:triage-issue` | 每個 verdict 出爐 | `READY`→🎯（next: take）；`NEEDS_INFO`→⏳；`DUP`/`CLOSE`→✅，duplicate / close 理由放狀態旁註。board 是本地檔，不違反 triage「不主動寫 GitHub」原則 |
| `/maigo:take-issue` | 開工時＋收尾 | 開工：issue 行標 `IN_PROGRESS` ＋ branch 名；收尾若開了 PR：新增 🔀 行、issue 行旁註 linked PR |
| `/maigo:describe-pr` | PR 開出後（若使用者說已開） | 新增/更新對應 🔀 行 → ⏳ `等 review` |
| `/maigo:address-comments` | 步驟 8（全部 work item 走完） | commit 未 push（**預設**——該命令不 push、不替使用者回覆）→ 🎯 留著，細節檔 `## 判斷` 區寫「push 了嗎——還沒就先 push」；使用者已自行 push 且回覆已送出 → ⏳ `等 review`（`## 判斷` 區留空） |

maigo 命令自己處理的項目**不勾 checkbox**——checkbox 專屬「使用者親自處理」的訊號（見 §5）。

**Upsert 紀律**（單項 upsert 的日期更新、容易被漏掉的獨立檢查、verdict 未必已送出 GitHub）
三條實務守則見
[`references/upsert-discipline.md`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/references/upsert-discipline.md)。

## 4. 併入遷移（review-board.md 退役）

首次跑 `/maigo:board`（或某回寫命令要寫 board 時）偵測到 `.maigo/review-board.md`
存在且 `board.md` 不存在：

1. 讀舊檔，按分區映射搬行：`Active` + `↩︎ 回你的球` → 🎯；`Off-board` → ⏳；
   `Merged/closed` → ✅；`🔍 本批佇列` → 依 §2 重判
2. 解析舊行的 author / URL / 規模（`- #<PR> (<author>) …` 這個舊尾註形狀）→ 用
   [`detail_path()`](https://github.com/Lee-W/maigo/blob/main/scripts/board_state.py)
   算出細節檔路徑並依 §1a 格式建檔（事實區填入解析出的 author/URL/規模，`## 判斷` /
   `## 筆記` 留空）→ 索引行改寫成新文法，只留
   `- [ ] 👀 <狀態詞> <細節檔路徑> — <title>`，不保留內嵌的 `(<author>)` 或 URL
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

## 6. 在 nvim 裡怎麼用

真相層永遠是純 markdown 的 `.maigo/board.md`——agent 跟人都直接改它，不為排版
混入 HTML wrapper。**maigo 不提供任何呈現層，也不會建議你裝 nvim plugin**：
`.maigo/board.md` 就是最終產物，`:e` 開檔即讀即改。

1. **三個 fold**：三個 `## ` section 標題就是 treesitter markdown fold 的邊界，`zM`
   收合後只剩三行標題 ＋ 計數，`za`/`zo` 逐一展開想看的區。
2. **`/狀態詞` 搜尋**：狀態詞是純文字（`待 triage`、`CHANGES_REQUESTED`……），
   `/待送出` 之類直接命中；細節檔路徑內含編號（`i/9201.md`），`/9201` 一樣命中對應行。
3. **細節檔路徑用 `gf` 跳過去**：裸相對路徑（不加反引號）就是 nvim `gf` 吃得下的形式，
   游標停在 `i/<slug>.md` 上 `gf`（Neovim 核心內建，不需 plugin）直接開那份細節檔
   （格式見 §1a）；看完 `<C-o>` 跳回 board.md 原本的位置。
4. **細節檔內 `gx` 開 GitHub**：真 URL 搬進了細節檔的「連結」那一行，游標移到該行 `gx`
   直接開瀏覽器到該 issue/PR；「筆記」段落裡的裸相對路徑（例：`review-9301.md`）同樣
   `gf` 可跳。
5. **勾 `[x]` 觸發 `--learn`**：把 `- [ ]` 或 `1. [ ]` 改成 `[x]` 存檔即完成（見 §5），
   不需要額外命令；下次 `/maigo:board` 刷新會列出已勾未 `🧠` 的項目。
6. **一行一項**：`/` 搜尋與 `dd` 刪除都以行為單位，board.md 的每一行對應一個 item，
   nvim 原生操作即可管理，不需要任何格式轉換或外部工具。

## 7. 跨 session 接續：`ListAgents` 查不到對應 session 時

使用者說「有個 session 在做 X」，但 `ListAgents` 查不到可觸及的對應 session——session 本身
消失了不代表工作內容跟著消失。**先查 `.maigo/board.md` 有沒有這個 issue/PR 的 `IN_PROGRESS`
行**（`/maigo:take-issue` 開工時會旁註 branch 名，見 `commands/take-issue.md` 步驟 4），有的話
直接用旁註的 branch 名定位 worktree；board 沒記到，才退而找對應 worktree 本身（`.maigo/plan.md`
是否存在、`git log`/`git status` 做到哪一步）——兩者都能讓 orchestrator 從既有進度接著跑，不必
等原 session 復活，也不必整個重新走一次 Raana 探索 + Tomori 規劃。

## What this skill does NOT cover

- `/maigo:board` 的命令面（無參數刷新 / `<targets...>` / `--all` / `--learn` /
  `--check` / `--uncheck` / `--drop`）——
  見 [`commands/board.md`](https://github.com/Lee-W/maigo/blob/main/commands/board.md)
- Review verdict 本身的判斷標準——那是
  [`strict-review`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md) /
  [`strict-triage`](https://github.com/Lee-W/maigo/blob/main/skills/strict-triage/SKILL.md) 的事，本 skill 只管球權落點與行文法
