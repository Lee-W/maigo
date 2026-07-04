# GitHub Reply Draft — Comment Fetch & Triage Reference

Loaded on demand by [`commands/address-comments.md`](https://github.com/Lee-W/maigo/blob/main/commands/address-comments.md)
steps 2 and 4, and shared by [`commands/review.md`](https://github.com/Lee-W/maigo/blob/main/commands/review.md)
step 5 (learning wrap-up reuses the same fetch queries) — the verbatim `gh` / GraphQL queries
for pulling the three PR comment sources, and the triage-file template + routing table used
to turn selected comments into work items. Read this file when actually fetching comments
or writing the triage file.

---

## 抓取：三種意見來源的查詢指令

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

---

## Triage 檔模板（`.maigo/pr-comments.md`）

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

## 路由判斷

每個 work item 標一條 route + 一句 rationale：

| 訊號 | 建議 route |
|------|-----------|
| 單檔、局部、機械性（typo / rename / 補 type hint / 改字串 / 補一個 None 檢查） | `/maigo:quick` |
| 跨檔、動到行為、需要先探索或設計 | `/maigo:go` |
| 同 `/maigo:go` 但 work item 大且低風險、想省牆鐘 | `/maigo:team` |

**預設盡量走 `/maigo:quick`**——多數 review 意見是局部修正。
不確定 quick 還是 go → 偏 `/maigo:go`（多一輪探索 + 完整 9 項 review，往上靠較安全）。
