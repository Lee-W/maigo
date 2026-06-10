---
name: copyable-deliverable
description: This skill should be used whenever a maigo command produces a deliverable destined to be pasted elsewhere (a PR/issue comment, a reply draft, a commit message, a gh command draft). It mandates wrapping that content in a single fenced code block so the user gets raw, one-click-copyable markdown instead of a rendered-only version.
---

<!-- mkdocs-include-start -->

# Copyable Deliverable

**Owner Agent**: orchestrator（呈現 deliverable 給使用者時）

**Consumers**:
[`/maigo:review`](https://github.com/Lee-W/maigo/blob/main/commands/review.md)、
[`/maigo:triage-issue`](https://github.com/Lee-W/maigo/blob/main/commands/triage-issue.md)、
[`/maigo:describe-pr`](https://github.com/Lee-W/maigo/blob/main/commands/describe-pr.md)、
[`skills/github-title-description`](https://github.com/Lee-W/maigo/blob/main/skills/github-title-description/SKILL.md)、
[`skills/commit-message`](https://github.com/Lee-W/maigo/blob/main/skills/commit-message/SKILL.md)

## When to apply

**Deliverable** = 使用者會拿去貼到別處的內容：PR comment / issue reply 草稿、
commit message 草稿、`gh` 指令草稿、PR title / description。

**不適用**：純對話 / 分析 / 背景說明、review verdict 的 judgement 段落
（checklist / evidence）、純狀態 / queue 表——除非使用者明確要求弄成可複製。

## The rule

**Deliverable 一律放進單一 fenced code block，內含 raw markdown。**

- 外層 fence 用**四個 backtick**（```` ```` ````）——deliverable 內部若有三-backtick
  code block（例：Test Plan 的指令）才不會把外層截斷。
- 整份 deliverable 在同一個 block 裡，不要拆成多塊。
- block 外可以有說明文字（「可整段複製貼到 GitHub：」），但 deliverable 本身要在 block 內。

範例：

`````markdown
可整段複製貼到 GitHub PR comment：

````markdown
幾個問題想確認：

1. `auth.py:42` 的 early return 在 `token == None` 時會跳過 audit log，是預期行為嗎？

整體設計方向 OK，等回覆再 approve。
````
`````

## Why

平台 render markdown 後，使用者從 UI 框選複製到的是 rendered 結果，不是 raw 語法——
手動框選費工又容易在內部 code block 處截斷。**一個 fenced block = 一鍵複製 = 零選取誤差。**

## What this skill does NOT cover

- 純對話 / 分析 / 狀態表——那是 orchestrator 的敘述，不是 deliverable
- 自動化路徑——`commit-message` 的 output 若直接 pipe 進 `git commit -F -`，不加外層 fence
  （fence 會破壞 pipe）；**呈現給使用者過目**時才適用本 skill。這個 pipe vs 呈現的區分已在
  [`commit-message`](https://github.com/Lee-W/maigo/blob/main/skills/commit-message/SKILL.md) 內部說明。
