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
- [ ] 🔀 #456 (你) **CHANGES_REQUESTED** — reviewer 要改 → `/maigo:address-comments` — "feat yyy"
- [x] 👀 #789 (bob) **↩︎ 回你的球** — 你回過後又推新 commit → `/maigo:review 789` — "…"

## ⏳ 等別人（2）
- [ ] 🔀 #460 (你) **等 review** — 最後活動是你 07-08 — "…"
- [ ] 🐛 #130 (carol) **NEEDS_INFO** — 等回報者補資訊 — "…"

## 📥 無法分類（0）
<!-- 只放 gh 抓不到的（權限 / 打錯號碼 / 網路失敗），抓得到的一律直接分桶 -->

## ✅ Merged / closed（最近 7 天）
- [x] 👀 #700 (dave) **APPROVE** 🧠 — merged 07-07 — "…"
```

### 行文法

```text
- [ ] <型別emoji> #<n 或 owner/repo#n> (<相對人>) **<狀態詞>** — <一句話理由> → `<下一步命令>` — "<title>"
```

- **型別 emoji**：🐛 issue ｜ 🔀 你的 PR ｜ 👀 在審的 PR
- **相對人**：issue / PR 的 author；自己的 PR 寫 `(你)`
- **`→ 下一步命令`**：只有 🎯 區的行有——看到就能複製執行，這是「最好讀寫」的核心
- **checkbox**：`[x]` ＝「這項我**親自**處理過了」（學習閘門訊號，見 §5）；與所在分區正交
- **🧠 標記**：學習盤點已完成，不重複學
- **跨 repo**：board 綁 cwd repo（header 記 `gh repo view --json nameWithOwner` 結果）；
  丟進來的 URL 若屬其他 repo，行內用 `owner/repo#n` 全稱
- 旁註沿用 review board 慣例：DRAFT / 指定 anchor / 他人 review decision 放狀態詞後面

### 狀態詞 vocabulary（依型別）

| 型別 | 狀態詞 |
|---|---|
| 🐛 issue | `待 triage` / `READY` / `NEEDS_INFO` / `DUP` / `CLOSE` / `有新回覆` / `IN_PROGRESS` |
| 🔀 你的 PR | `WIP` / `等 review` / `CHANGES_REQUESTED` / `有新 comment` / `CI 紅` |
| 👀 在審的 PR | `待 review` / `↩︎ 回你的球` / `BLOCKED` / `NEEDS_CHANGES` / `APPROVE_WITH_NITS` / `APPROVE` |

triage verdict 沿用 [`strict-triage`](https://github.com/Lee-W/maigo/blob/main/skills/strict-triage/SKILL.md)、
review verdict 沿用 [`strict-review`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md)，不另造詞。

### 排序

- 🎯 區：**球到你手上的時間升序**——最久沒回的最上面（責任感排序）
- ⏳ / ✅ 區：最後活動時間降序
- ✅ 區超過 7 天的行在刷新時自動清掉（唯一例外：`🧠` 待盤點未完成的行不清，學完才走）

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
gh pr view <n> --repo <r> --json state,isDraft,mergedAt,reviewDecision,updatedAt,reviews,comments,author,statusCheckRollup
```

「你」＝ `gh api user --jq .login`（沿用 review board 既有做法）。
「你最後活動 vs 他人最後活動」的比對邏輯沿用 review board：掃 comments + reviews 的 author 與時間戳。

### 球權判定表（merged / closed 一律優先 → ✅）

**🐛 issue**：

| 條件（由上往下第一個命中） | 落點 |
|---|---|
| `state == CLOSED`（stateReason 併入旁註；`closedByPullRequestsReferences` 有值就附連結） | ✅ |
| board 無 verdict（剛加入、從未 triage） | 🎯 `待 triage` → `/maigo:triage-issue <n>` |
| verdict `READY` 且無 assignee（或 assignee 是你） | 🎯 → `/maigo:take-issue <n>` |
| verdict `NEEDS_INFO` / 你最後留言後**無**新活動 | ⏳ |
| 你最後活動後**有**別人新 comment | 🎯 `有新回覆` → `/maigo:triage-issue <n>`（重判） |
| `IN_PROGRESS`（已 take） | 🎯 `IN_PROGRESS`，旁註 branch 名 |

**🔀 你的 PR**：

| 條件 | 落點 |
|---|---|
| merged / closed | ✅ |
| `isDraft == true` | 🎯 `WIP`（自己的 draft ＝ 還在寫） |
| `statusCheckRollup` 有 FAILURE | 🎯 `CI 紅` |
| `reviewDecision == CHANGES_REQUESTED` | 🎯 → `/maigo:address-comments` |
| 你最後 push/comment 後有別人 review/comment | 🎯 `有新 comment` → `/maigo:address-comments` |
| 其他（最後活動是你，等 review） | ⏳ `等 review` |

**👀 在審的 PR**：原樣沿用 review board 已 ship 的四格判定表
（[`review-batch-queue.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/review-batch-queue.md)「刷新 board」），映射：
Active、↩︎ 回你的球 → 🎯；Off-board → ⏳；merged/closed → ✅。
行內狀態詞保留細分（`待 review` / verdict / `↩︎ 回你的球`）。

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

## What this skill does NOT cover

- `/maigo:board` 的命令面（無參數刷新 / `<targets...>` / `--all` / `--learn` / `--drop`）——
  見 [`commands/board.md`](https://github.com/Lee-W/maigo/blob/main/commands/board.md)
- `.maigo/board.html` 閱讀層的渲染規則——見
  [`scripts/board_render.py`](https://github.com/Lee-W/maigo/blob/main/scripts/board_render.py) docstring
- Review verdict 本身的判斷標準——那是
  [`strict-review`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md) /
  [`strict-triage`](https://github.com/Lee-W/maigo/blob/main/skills/strict-triage/SKILL.md) 的事，本 skill 只管球權落點與行文法
