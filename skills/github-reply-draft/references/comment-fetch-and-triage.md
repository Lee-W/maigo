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

## Triage 檔模板（`.maigo/pr-comments-<id>.md`，路徑由 [`scripts/artifact_path.py`](https://github.com/Lee-W/maigo/blob/main/scripts/artifact_path.py) 算出，見 [`artifact-ownership`](https://github.com/Lee-W/maigo/blob/main/skills/harness-discipline/references/artifact-ownership.md)）

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

### pushback 打的是提案還是類比

提案者常舉先例說服人（「這是 X 已經在用的 pattern」）。後續 reviewer 反對時，反對的對象
可能是**那個先例**，而不是提案本身——先例把它自己的包袱一起帶進了討論。

分辨方法：把提案**實際借走了什麼**列出來，逐項對照 reviewer 點名的顧慮：

- 顧慮落在借走的那些項目上 → 打的是提案實質，重新考慮設計
- 顧慮落在先例自己的其他性質上（用途、persona、約束來源）→ 打的是類比

實例：提案者建議把某欄位放寬並加進 `template_fields`，理由是「這是另一種 operator 已經在用
的 pattern」；另一位審查者回覆擔心兩種概念被混在一起（該類比的限制來源通常是系統參數，
與這裡的欄位是不同 persona）。查證發現實作只借了「接受可模板化的值、在 execute 時建出型別
物件」這個**形狀**，欄位仍是自己的，沒有任何被擔心的東西混進來——那次 pushback 打的是類比。

打類比時的正確回應是**澄清，不是改 code**：先說明現況（訴求已落地在哪幾個位置），再逐項
回應對方點名的顧慮為何不適用（借的是哪個形狀、沒借的是哪些）。不要因為有人說了「不」就
默認要動實作。

反過來的教訓：自己舉先例說服人時，先例愈大愈知名，愈容易被連帶質疑——舉最小的那個。

## 套用前的驗證紀律

**Reviewer 建議的修法也要實跑驗證再套用。** 對方的診斷正確不代表順手給的建議修法沒有副作用
——reviewer 通常是在 diff 片段裡讀，沒有實際跑過修法對全量資料的效果。套用任何建議修法前，
先自己跑一次全量前後對照，不只驗 reviewer 舉的那個例子。若建議版本有副作用，改用安全的變體，
並在回覆裡明講具體反例（哪個輸入、變成什麼、為何誤判）——不要默默改成別的寫法讓對方以為你照做
了字面建議。回覆本身仍維持 Convention 1 的簡短：反例是對方需要的內容，驗證過程敘述不是，不要
把「我重跑過一次、結果一致」這類驗證敘述寫進 thread。

**「統一 / 清理」型 sweep 前先查 review threads。** 動到自己（或本輪 agent 鏈）沒寫過的行之前，
先用 `git log -L` 或查 PR review threads 追它為什麼長這樣——working tree 上「看起來不一致」的
地方可能是 reviewer 在 inline thread 指定、使用者已用 `fixup!` 落地的刻意改動。PR 進行中時，
review threads 是「現狀真相」的一部分；用「一致性」理由把它蓋回去，等於默默回退了 reviewer 的
要求。
