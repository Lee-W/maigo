---
description: 讀當前 branch 對應 PR 的 review 意見，列出讓使用者挑、提路由計畫確認後，逐項走 /maigo:quick · go · team 處理。讀不到 PR 直接擋下。
---

<!-- mkdocs-include-start -->

# /maigo:address-comments

把 PR 上的 review 意見一條一條收掉。

讀當前 branch 對應的 PR、抓 GitHub 上的 comments、列出來讓你挑哪些要處理，
擬一份「哪條意見走哪條 workflow」的路由計畫給你確認，確認後逐項實作。

**Orchestrator 親自跑步驟 1–4（不開新 agent）；步驟 5 才把每個 work item
交給 [`/maigo:quick`](https://github.com/Lee-W/maigo/blob/main/commands/quick.md) /
[`/maigo:go`](https://github.com/Lee-W/maigo/blob/main/commands/go.md) /
[`/maigo:team`](https://github.com/Lee-W/maigo/blob/main/commands/team.md) 的完整流程。**

## 使用

```
/maigo:address-comments
```

不收參數——一律針對**當前 branch** 對應的 PR。當前 branch 讀不到 PR 就擋下（見步驟 1）。

## 流程

orchestrator 親自跑步驟 1–4：

### 1. Pre-flight gate — 讀不到 PR 直接擋下

依序檢查，**任一項不過就印錯誤並以非 0 退出，不往下走**：

| 檢查 | 命令 | 不過時的訊息 |
|------|------|------------|
| 在 git repo 內 | `git rev-parse --is-inside-work-tree` | 「不在 git repo 內，address-comments 需要一個有 PR 的 branch。」 |
| `gh` 可用且已登入 | `gh auth status` | 「`gh` CLI 未安裝或未登入。先 `gh auth login`。」 |
| 當前 branch 有對應 PR | `gh pr view --json number,title,url,state,headRefName,baseRefName,isDraft` | 「當前 branch `<branch>` 沒有對應的 PR。address-comments 需要一個 PR 才能跑——先開 PR（可用 `/maigo:describe-pr` 產草稿）。」 |

`gh pr view` 不帶位置參數時會自動解析當前 branch 的 PR；exit 非 0 或回
「no pull requests found」即視為**讀不到 PR**，擋下。

過關後記下 `number` / `title` / `url` / `headRefName` / `baseRefName`，往下走。
PR 若是 `MERGED` / `CLOSED` 狀態——不擋，但在列表時標出狀態提醒使用者。

### 2. 抓 GitHub 上的 comments

把三種意見來源都抓齊（orchestrator 直接跑 `gh`）：

- **Inline review threads**（diff 行上的留言，含已解決狀態）——用 GraphQL 才拿得到 `isResolved`：

  ```bash
  gh api graphql -f query='
  query($owner:String!,$repo:String!,$number:Int!){
    repository(owner:$owner,name:$repo){
      pullRequest(number:$number){
        reviewThreads(first:100){ nodes{
          isResolved isOutdated
          comments(first:50){ nodes{ author{login} body path line url } }
        }}
      }
    }
  }' -F owner=<owner> -F repo=<repo> -F number=<number>
  ```

  `<owner>` / `<repo>`：`gh repo view --json owner,name -q '.owner.login+" "+.name'`。

- **Review 摘要**（APPROVE / REQUEST_CHANGES / COMMENT + 整體留言）：
  `gh pr view --json reviews`

  > **注意**：`--json reviews` 的 review 物件**不含 `url`**——補一道 GraphQL 抓：
  >
  > ```bash
  > gh api graphql -f query='
  > query($owner:String!,$repo:String!,$number:Int!){
  >   repository(owner:$owner,name:$repo){
  >     pullRequest(number:$number){
  >       reviews(first:100){ nodes{ id state body url author{login} submittedAt } }
  >     }
  >   }
  > }' -F owner=<owner> -F repo=<repo> -F number=<number>
  > ```
  >
  > 回傳 `url` 格式 `<PR-url>#pullrequestreview-<id>`，供步驟 4 triage 檔與步驟 6 Finale 使用。

- **Conversation comments**（PR 對話串、非 diff 行上的留言）：
  `gh pr view --json comments`

  > `gh pr view --json comments` 回傳的 comment 物件**含 `url`**（格式 `<PR-url>#issuecomment-<id>`），
  > 可直接記下供後續使用。

抓不到任何一種就標 `n/a`，不要因為單一來源空了就中止。

**三種來源都要記下各自的 `url`**，供步驟 4 triage 檔格式填寫與步驟 6 Finale 回覆草稿使用：
inline comment 的 `url` 已由上方 Inline review threads 的 GraphQL query 傳回；review 的 `url` 由上述補充 GraphQL query 取得；conversation comment 的 `url` 由 `gh pr view --json comments` 直接提供。

**若全部來源加起來沒有任何意見** → 印「PR #`<number>` 目前沒有任何 review 意見，沒東西可處理。」並**正常結束（exit 0）**——這不是錯誤。

### 3. 列出來，問哪些要處理

把意見編號列成清單印給使用者。預設**摺疊已解決 / outdated 的 thread**（只印一行「另有 N 條已解決，預設略過」），其餘逐條列：

```
C1  [inline · unresolved]  src/auth.py:42  @reviewer
    「這裡沒檢查 None，traceback 會炸。」
C2  [review · REQUEST_CHANGES]  @reviewer
    「整體 OK，但 error path 缺測試。」
C3  [conversation]  @reviewer
    「順問一下，這個為什麼不用 dataclass？」
```

接著問使用者**哪些要處理**：

- comment 數 ≤ 4 → 用 **AskUserQuestion**（`multiSelect`）逐條列為選項。
- comment 數 > 4 → 直接純文字提問「哪些要處理？回編號（如 `C1 C3`），或 `全部未解決`」。

提醒：不是每條都要改 code——像 C3 那種純提問可能只需回覆、不需改動。使用者挑完才往下。
使用者一條都沒挑 → 印「沒有要處理的意見」並正常結束。

### 4. 寫 triage + 提路由計畫，確認

把被選中的意見寫進 `.maigo/pr-comments.md`（目錄不存在先 `mkdir -p .maigo`），並擬路由計畫：

```markdown
# PR comments: <PR title> (#<number>)

- **PR**: <url>
- **Branch**: <head> → <base>
- **Fetched at**: <ISO8601 UTC，用 `date -u +%Y-%m-%dT%H:%M:%SZ`>

## 選中的意見
- **C1** — inline src/auth.py:42 @reviewer — 「<截斷的 body>」 — <url>
- **C2** — review REQUEST_CHANGES @reviewer — 「<截斷的 body>」 — <url>
- **C3** — conversation @reviewer — 「<截斷的 body>」 — <url>

## Work items
### W1 — 補 src/auth.py 的 None 檢查
- **Comments**: C1
- **Route**: /maigo:quick  ← rationale: 單檔、局部、機械性
- **Status**: pending

### W2 — error path 補測試
- **Comments**: C2
- **Route**: /maigo:go  ← rationale: 跨檔、要先看既有 test 結構
- **Status**: pending
```

**分組**：相關的意見（同檔 / 同區域 / 同一件事）併成一個 work item，不必一條一個。

**路由判斷**（每個 work item 標一條 route + 一句 rationale）：

| 訊號 | 建議 route |
|------|-----------|
| 單檔、局部、機械性（typo / rename / 補 type hint / 改字串 / 補一個 None 檢查） | `/maigo:quick` |
| 跨檔、動到行為、需要先探索或設計 | `/maigo:go` |
| 同 `/maigo:go` 但 work item 大且低風險、想省牆鐘 | `/maigo:team` |

**預設盡量走 `/maigo:quick`**——多數 review 意見是局部修正。
不確定 quick 還是 go → 偏 `/maigo:go`（多一輪探索 + 完整 9 項 review，往上靠較安全）。

把 work item 清單 + 各自的 route + rationale 印給使用者，同一輪 **AskUserQuestion** 同時問兩個問題：

1. 確認計畫：`照計畫跑` / `我要調整路由或分組` / `取消`。選「調整」→ 收使用者修改後重印計畫再確認；選「取消」→ 不動任何檔（triage 檔可留著）並結束。
2. **Commit 格式**：`各自獨立 commit（預設）` / `fixup! commit（autosquash 用）`。

### 5. 逐 work item 實作

使用者確認後，orchestrator 依 triage 檔的順序，逐個 work item 跑它被指定的 route：

- route = `/maigo:quick` → 照 [`commands/quick.md`](https://github.com/Lee-W/maigo/blob/main/commands/quick.md) 完整流程跑
- route = `/maigo:go` → 照 [`commands/go.md`](https://github.com/Lee-W/maigo/blob/main/commands/go.md) 完整流程跑
- route = `/maigo:team` → 照 [`commands/team.md`](https://github.com/Lee-W/maigo/blob/main/commands/team.md) 完整流程跑

該 route 的「任務描述」= 這個 work item 對應的 comment 原文 + triage 檔裡的 context（檔案路徑、行號、reviewer 在意什麼）。

- 每個 work item 開跑前把 triage 檔該項 `Status` 改 `in-progress`，完成改 `done`。
- 被選 route 的失敗處理、Soyo 擋下、Taki 紅、**2** 次同條卡關才停下找使用者——依 [`skills/failure-handling`](https://github.com/Lee-W/maigo/blob/main/skills/failure-handling/SKILL.md)，address-comments 不另立規則。
- 某個 work item 卡死（依該 route 規則停下找使用者）→ 該項標 `blocked`，**其餘 work item 照常繼續**，最後在 summary 點出卡住的那項。
- **Commit 政策覆寫**：多個 work item 共享 working tree——若不 commit，後一個 work item 的 Anon / Soyo 會看到前一個的未 commit 改動，污染 diff、混淆 review 焦點。**因此覆寫 inner route 的「不自動 `git commit`」預設**（`/maigo:quick` 流程步驟 4、`/maigo:go` / `/maigo:team` 的 finale 規則）：每個 work item 完成、Soyo 過、Stop hook 綠後，orchestrator 依步驟 4 使用者選擇的 commit 格式落地：

  - **各自獨立 commit（預設）**：直接用 inner route 草擬的 commit message 落地（本 repo 偵測為 CC，subject 為 `type(scope): ...`）。
  - **fixup! commit（使用者在步驟 4 選擇）**：subject 改為 `fixup! <原 PR 主題>`，讓 `git rebase --autosquash` 接得起來。

  **仍不 push、不 amend、不 rebase**——拆 / 合由使用者最後決定。落地時的 staging（明確列檔、不用 `git add -A`）、
  不 `cd`（用絕對路徑 / `git -C`）依 [`skills/git-workflow`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/SKILL.md)。

### 6. Finale

全部 work item 走完後，orchestrator 給一份 summary：

1. **處理對照**：每條選中的 comment → 對應 work item → `done` / `blocked` + 改了哪些檔。
2. **回覆草稿（不自動送出）**：為每條已處理的 comment 擬一段建議回覆——address-comments **不替使用者回覆、不 resolve thread、不 push**。呈現方式：每條給**原始 comment 連結**（取自步驟 4 triage 檔的 `url`），其下接一個可一鍵複製的 fenced code block，內含純回覆內文，使用者在 GitHub 網頁直接貼上送出：

   C1 原始 comment：<url>

   ````
   已補上 None 檢查並加了對應測試，見 <commit>。
   ````

   依 [`skills/copyable-deliverable`](https://github.com/Lee-W/maigo/blob/main/skills/copyable-deliverable/SKILL.md)：回覆內文放單一 fenced block（內文若可能含三個 backtick 就用四個 backtick 外層）。不加 `>` blockquote。

   每則回覆草稿的措辭依 [`skills/github-reply-draft`](https://github.com/Lee-W/maigo/blob/main/skills/github-reply-draft/SKILL.md)：預設簡短、不引 commit SHA、只提最終 diff 裡存在的 symbol、一 thread 一則、不過度宣稱已解決、附 attribution footer。

3. **Commit 落地對照**：步驟 5 的 commit 政策覆寫已替每個 done work item 落地一支新 commit（獨立或 fixup!，依步驟 4 的選擇）。Finale 列出落地 commit 的 SHA + subject + body 對照表（依 [`skills/commit-message`](https://github.com/Lee-W/maigo/blob/main/skills/commit-message/SKILL.md) 的格式），讓使用者一眼看出哪條 comment 對應哪個 commit。需要拆 / 合 / 改 wording → 使用者自行 `git commit --amend` 或 `git reset HEAD~N` + 重 stage；**orchestrator 不 push、不 force-push、不 amend、不 rebase**。

### 7. 學習收尾——從處理過的 comment 萃取慣例

全部 work item 走完、Finale summary 印完後，orchestrator **親自**過一遍已處理（`done`）的 comment，
篩出「值得記住的教訓」。**靜默進行**——不額外問「要不要做學習收尾」；候選為 0 就無聲結束。
不開新 agent——orchestrator 直跑（不 delegate），pattern 同步驟 1–4。

**篩選啟發式（orchestrator 自己先過一輪，再攤給使用者勾，不替使用者拍板）：**

收進候選（convention 形狀、會再犯）：

- reviewer 指出的是**通用慣例 / 設計原則**（命名、結構、錯誤處理風格、測試策略…），非單點 bug
- 描述帶「以後 / 每次 / 慣例 / 一律 / 都要」語氣，或同類 comment 在這次 PR 出現多筆

排除（不收）：

- 一次性 typo / rename / 純 bug fix（改完就沒了，記了也用不到）
- 純提問型 comment（C3 那種）

orchestrator 印出候選清單（每筆一句「為什麼值得記 + 建議 type:project」），
用 **AskUserQuestion**（multiSelect）讓使用者勾哪些真的要記；一筆都沒勾 / 候選為 0 →
印「本次沒有要記住的慣例」正常結束，不寫任何記憶。

**step 7 的失敗或使用者取消不 rollback 前序**——前面的 comment 處理與 commit 已落地、不受影響。

使用者勾選的每一筆，**依序各跑一輪 [`/maigo:remember`](https://github.com/Lee-W/maigo/blob/main/commands/remember.md) 步驟 5+6** 寫入
（type 預填 `project`——這是能被 Soyo 當 review item 4 的唯一可行 type；name/body 由 comment
提煉，使用者可在 remember 步驟 5 改）。**每筆獨立——某筆在 remember 步驟 5 取消只跳過該筆、繼續往下一筆，不中止其餘**。
寫入路徑、rollback、同 slug 處理全交給 remember 既有規格，**不在此另寫一份**。

**crystallize 提示（不自動執行）：** 若某筆候選明顯是「反覆出現、夠結構化」（這次 PR 多筆同主題，
或使用者表示常踩），在寫完記憶後**加一行提示**：「這條看起來會反覆出現——之後可考慮
`/maigo:crystallize` 把它畢業成常駐 skill（review 會自動逐條擋）。」**只提示、不代跑**——
crystallize 要 spawn 愛音寫 skill，不塞進本 flow。

## Memory propose confirm flow

address-comments 步驟 1–4 是 orchestrator 直跑、沒有 Soyo / Anon，不會產生 `## Memory propose`。
步驟 5 委派出去的 `/maigo:quick` / `/maigo:go` / `/maigo:team` **各自帶自己的 Memory propose confirm flow**——orchestrator 跑該 route 時連同它的 confirm flow 一起照規格走，不在這裡另寫一份。
步驟 7 是 orchestrator 親自的學習收尾，不走 propose-confirm，而是 reuse [`/maigo:remember`](https://github.com/Lee-W/maigo/blob/main/commands/remember.md) 步驟 5+6 寫入。

## Orchestrator 守則

- **旁白**：orchestrator 對使用者說話時戴上旁白的臉——開場、收場、卡關節點由 🌙 Doloris / 🌑 Mortis 旁白，依 [`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md)。
- **讀不到 PR 一定擋**——步驟 1 的 gate 是硬規則，沒有 PR 不准往下跑。
- **步驟 1–4 及 7 orchestrator 親自跑、不開新 agent**——pattern 跟 [`/maigo:remember`](https://github.com/Lee-W/maigo/blob/main/commands/remember.md) / [`/maigo:memory`](https://github.com/Lee-W/maigo/blob/main/commands/memory.md) / [`/maigo:retro`](https://github.com/Lee-W/maigo/blob/main/commands/retro.md) 一致；步驟 2–4 要跟使用者多輪互動，必須由 orchestrator 掌握。
- **不替使用者決定哪些要處理**——步驟 3 由使用者挑，orchestrator 不自作主張全收或全略。
- **路由要被確認**——步驟 4 的計畫（分組 + route）必須經 AskUserQuestion 同意才進步驟 5。
- **不自己實作 / 不自己 review**——步驟 5 一律走 quick / go / team 的 agent 流程。
- **不碰 GitHub 寫入**——不回覆 comment、不 resolve thread、不 push、不開 / 關 PR；只產草稿。
- **repo 內唯一寫的 artefact 是 `.maigo/pr-comments.md`**——triage / 進度追蹤用；步驟 7 的學習收尾另會（經使用者確認後）寫 `~/.config/maigo/memory/`，reuse [`/maigo:remember`](https://github.com/Lee-W/maigo/blob/main/commands/remember.md) 的寫入。

## 與其他命令的差異

| 項目 | `/maigo:review` | `/maigo:address-comments` |
|------|-----------------|---------------------------|
| 輸入 | PR / branch / range | 當前 branch 的 PR（讀不到就擋） |
| 意見從哪來 | Soyo 當下產出 | GitHub 上既有的 review 意見 |
| 有沒有實作 | 沒有（只出報告） | 有——逐項走 quick / go / team |
| 終態 | review 報告 | 變更落地 + 回覆草稿 |

→ 場景對照、其他命令：[Commands reference](https://github.com/Lee-W/maigo/blob/main/docs/reference/commands.md)
