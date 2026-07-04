---
description: 把 /maigo:triage-issue 判定 READY 的 GitHub issue 接進實作——orchestrator 前置抓料，整理成需求敘述後交給標準 teammate-flow（樂奈探索、燈寫 plan、愛音實作、爽世 review、立希驗證），收尾草擬帶 issue 參照的 commit，不自動 push / 開 PR。
allowed-tools: Bash(gh issue view:*), Read
---

<!-- mkdocs-include-start -->

# /maigo:take-issue

接住 [`/maigo:triage-issue`](https://github.com/Lee-W/maigo/blob/main/commands/triage-issue.md)
判定 READY 之後斷掉的那一段——把 issue 接進真正的實作。

## 使用

```
/maigo:take-issue <issue 編號或 URL>
```

## 流程

### 1. 前置抓料（orchestrator 親跑，不開新 agent）

```bash
gh issue view <n> --json title,body,labels,comments
```

若 `.maigo/` 底下有先前 triage 產物（如 `triage-rubric.md`）就一併讀，沒有也不擋。把 issue
body + comments 整理成需求敘述：acceptance criteria 從 body 與 maintainer 在 comments 的
補充萃取，帶著這份 issue context 進下一步。

**邊界**：issue 明顯不是 READY 形狀（缺重現步驟、需求空泛、單純提問）→ 停下建議先跑
`/maigo:triage-issue`，不硬做。

### 2. Teammate flow

依 [`skills/teammate-flow`](https://github.com/Lee-W/maigo/blob/main/skills/teammate-flow/SKILL.md)
走完整流程——🐱 樂奈探索（帶著步驟 1 的 issue context，「看完了。相關的在這三個檔案。」）→
🩵 燈寫 plan（**必須引用 issue 編號與萃取出的 acceptance criteria**，「……讓我先理清楚它想
做什麼。」）→ 使用者確認 → 🎀 愛音實作 → 🟡 爽世完整 9 項 review → 🟣 立希驗證。流程細節
不在此重抄。

### 3. 收尾

🟣 立希全綠後，依 [`skills/git-workflow`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/SKILL.md) /
[`skills/commit-message`](https://github.com/Lee-W/maigo/blob/main/skills/commit-message/SKILL.md)
草擬 commit（body 帶 issue 參照，如 `Fixes #<n>` 或 repo 既有慣例）——**不自動 commit、不
push、不開 PR**。完成後提示可接 [`/maigo:describe-pr`](https://github.com/Lee-W/maigo/blob/main/commands/describe-pr.md) 產 PR title/description。

## 失敗處理

依 [`skills/failure-handling`](https://github.com/Lee-W/maigo/blob/main/skills/failure-handling/SKILL.md)。

## Orchestrator 守則

- **旁白**：開場、收場、卡關節點由 🌙 Doloris / 🌑 Mortis 旁白，依
  [`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md)。
- **步驟 1 orchestrator 親自跑、不開新 agent**；步驟 2 一律用 Task tool 啟動各 agent，不要自己探索 / 實作 / review。
- **不硬做、不寫 GitHub、不自動 commit**：issue 不是 READY 就建議 `/maigo:triage-issue`；commit 只草擬文字，push / 開 PR 交使用者或 `/maigo:describe-pr`。

→ 跟 `/maigo:triage-issue` / `/maigo:go` 的差異、場景對照：[Commands reference](https://github.com/Lee-W/maigo/blob/main/docs/reference/commands.md)
