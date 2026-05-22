---
description: 讀當前 branch 對應 PR 的 review 意見，列出讓使用者挑、提路由計畫確認後，逐項走 /maigo:fix · go · team 處理。讀不到 PR 直接擋下。
---

<!-- mkdocs-include-start -->

# /maigo:address-comments

把 PR 上的 review 意見一條一條收掉。

讀當前 branch 對應的 PR、抓 GitHub 上的 comments、列出來讓你挑哪些要處理，
擬一份「哪條意見走哪條 workflow」的路由計畫給你確認，確認後逐項實作。

**Orchestrator 親自跑步驟 1–4（不開新 agent）；步驟 5 才把每個 work item
交給 [`/maigo:fix`](https://github.com/Lee-W/maigo/blob/main/commands/fix.md) /
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

- **Conversation comments**（PR 對話串、非 diff 行上的留言）：
  `gh pr view --json comments`

抓不到任何一種就標 `n/a`，不要因為單一來源空了就中止。

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

把被選中的意見寫進 `/tmp/maigo/<repo>/pr-comments.md`（`<repo>` = `basename "$PWD"`；目錄不存在先 `mkdir -p`），並擬路由計畫：

```markdown
# PR comments: <PR title> (#<number>)

- **PR**: <url>
- **Branch**: <head> → <base>
- **Fetched at**: <ISO8601 UTC，用 `date -u +%Y-%m-%dT%H:%M:%SZ`>

## 選中的意見
- **C1** — inline src/auth.py:42 @reviewer — 「<截斷的 body>」 — <url>
- **C2** — review REQUEST_CHANGES @reviewer — 「<截斷的 body>」

## Work items
### W1 — 補 src/auth.py 的 None 檢查
- **Comments**: C1
- **Route**: /maigo:fix  ← rationale: 單檔、局部、機械性
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
| 單檔、局部、機械性（typo / rename / 補 type hint / 改字串 / 補一個 None 檢查） | `/maigo:fix` |
| 跨檔、動到行為、需要先探索或設計 | `/maigo:go` |
| 同 `/maigo:go` 但 work item 大且低風險、想省牆鐘 | `/maigo:team` |

**預設盡量走 `/maigo:fix`**——多數 review 意見是局部修正。
不確定 fix 還是 go → 偏 `/maigo:go`（多一輪探索 + 完整 9 項 review，往上靠較安全）。

把 work item 清單 + 各自的 route + rationale 印給使用者，用 **AskUserQuestion** 確認：
`照計畫跑` / `我要調整路由或分組` / `取消`。選「調整」→ 收使用者修改後重印計畫再確認；選「取消」→ 不動任何檔（triage 檔可留著）並結束。

### 5. 逐 work item 實作

使用者確認後，orchestrator 依 triage 檔的順序，逐個 work item 跑它被指定的 route：

- route = `/maigo:fix` → 照 [`commands/fix.md`](https://github.com/Lee-W/maigo/blob/main/commands/fix.md) 完整流程跑
- route = `/maigo:go` → 照 [`commands/go.md`](https://github.com/Lee-W/maigo/blob/main/commands/go.md) 完整流程跑
- route = `/maigo:team` → 照 [`commands/team.md`](https://github.com/Lee-W/maigo/blob/main/commands/team.md) 完整流程跑

該 route 的「任務描述」= 這個 work item 對應的 comment 原文 + triage 檔裡的 context（檔案路徑、行號、reviewer 在意什麼）。

- 每個 work item 開跑前把 triage 檔該項 `Status` 改 `in-progress`，完成改 `done`。
- 被選 route 的失敗處理、Soyo 擋下、Taki 紅、3 次同條卡關才停下找使用者——**全部承襲該 command 的規格**，address-comments 不另立規則。
- 某個 work item 卡死（依該 route 規則停下找使用者）→ 該項標 `blocked`，**其餘 work item 照常繼續**，最後在 summary 點出卡住的那項。

### 6. Finale

全部 work item 走完後，orchestrator 給一份 summary：

1. **處理對照**：每條選中的 comment → 對應 work item → `done` / `blocked` + 改了哪些檔。
2. **回覆草稿（不自動送出）**：為每條已處理的 comment 擬一段建議回覆，附對應的 `gh` 指令讓使用者**自己**貼上去——address-comments **不替使用者回覆、不 resolve thread、不 push**：

   ```
   C1 建議回覆：「已補上 None 檢查並加了對應測試，見 <commit>。」
   貼上去：gh api repos/{owner}/{repo}/pulls/<number>/comments/<comment-id>/replies -f body='...'
   ```

3. **commit message 草稿**：收齊各 work item 的 route finale 產出的 commit message 草稿一併列出（依 [`skills/commit-message`](https://github.com/Lee-W/maigo/blob/main/skills/commit-message/SKILL.md)）。**不自動 `git commit`**，由使用者決定要不要分 commit。

## Memory propose confirm flow

address-comments 步驟 1–4 是 orchestrator 直跑、沒有 Soyo / Anon，不會產生 `## Memory propose`。
步驟 5 委派出去的 `/maigo:fix` / `/maigo:go` / `/maigo:team` **各自帶自己的 Memory propose confirm flow**——orchestrator 跑該 route 時連同它的 confirm flow 一起照規格走，不在這裡另寫一份。

## Orchestrator 守則

- **讀不到 PR 一定擋**——步驟 1 的 gate 是硬規則，沒有 PR 不准往下跑。
- **步驟 1–4 orchestrator 親自跑、不開新 agent**——pattern 跟 [`/maigo:describe-pr`](https://github.com/Lee-W/maigo/blob/main/commands/describe-pr.md) / [`/maigo:remember`](https://github.com/Lee-W/maigo/blob/main/commands/remember.md) 一致；步驟 2–4 要跟使用者多輪互動，必須由 orchestrator 掌握。
- **不替使用者決定哪些要處理**——步驟 3 由使用者挑，orchestrator 不自作主張全收或全略。
- **路由要被確認**——步驟 4 的計畫（分組 + route）必須經 AskUserQuestion 同意才進步驟 5。
- **不自己實作 / 不自己 review**——步驟 5 一律走 fix / go / team 的 agent 流程。
- **不碰 GitHub 寫入**——不回覆 comment、不 resolve thread、不 push、不開 / 關 PR；只產草稿。
- **唯一會寫的 repo 外檔案是 `/tmp/maigo/<repo>/pr-comments.md`**——triage / 進度追蹤用。

## 與其他命令的差異

| 項目 | `/maigo:review` | `/maigo:address-comments` |
|------|-----------------|---------------------------|
| 輸入 | PR / branch / range | 當前 branch 的 PR（讀不到就擋） |
| 意見從哪來 | Soyo 當下產出 | GitHub 上既有的 review 意見 |
| 有沒有實作 | 沒有（只出報告） | 有——逐項走 fix / go / team |
| 終態 | review 報告 | 變更落地 + 回覆草稿 |

→ 場景對照、其他命令：[Commands reference](https://github.com/Lee-W/maigo/blob/main/docs/reference/commands.md)
