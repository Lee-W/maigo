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

**Deliverable** = 使用者會拿去貼到 GitHub PR / issue / commit 的內容：

- PR comment 或 issue reply 草稿
- Commit message 草稿
- `gh` CLI 指令草稿（使用者會直接貼到 terminal 執行）
- PR title / description（使用者會貼進 GitHub UI 或 `gh pr create`）

**不適用**：

- 純對話、分析、背景說明（例：「樂奈找到了這三個相關檔案」）
- Review verdict 的 judgement 說明（checklist / evidence 段落）
- 純狀態 / queue 表（review queue、triage batch summary）
- 除非使用者明確要求「幫我把這段弄成可複製的」

## The rule

**Deliverable 一律放進單一 fenced code block，內含 raw markdown。**

- 外層 fence 用**四個 backtick**（```` ```` ````）——這樣 deliverable 內部若有三個 backtick 的 code block（例：Test Plan 的指令）不會把外層截斷。
- 整份 deliverable 都在同一個 block 裡，不要拆成多塊。
- block 外可以有說明文字（「可整段複製貼到 GitHub：」之類），但 deliverable 本身要在 block 內。

### 正例 ✅

使用者可一鍵複製整份 PR comment：

`````markdown
可整段複製貼到 GitHub PR comment：

````markdown
感謝 @contributor 的 PR！

幾個問題想確認：

1. `auth.py:42` 的 early return 在 `token == None` 時會跳過 audit log，是預期行為嗎？
2. Test Plan 裡的 `pytest tests/test_auth.py -k test_empty_token` 跑過了嗎？

整體設計方向 OK，等回覆再 approve。
````
`````

### 反例 ❌

直接 render 出 PR comment，使用者要手動框選複製——遇到 code block 容易斷掉：

---

感謝 @contributor 的 PR！

幾個問題想確認：

1. `auth.py:42` 的 early return 在 `token == None` 時會跳過 audit log，是預期行為嗎？

---

## Why

GitHub 等平台 render markdown 後，使用者從 UI 框選複製得到的是 **rendered 結果**，不是 raw markdown 語法。把 PR comment draft 直接呈現出來，使用者需要：

1. 手動找到 deliverable 的起止位置
2. 確保 code block / emphasis 語法也選進去
3. 在貼到 GitHub 之前手動驗證格式是否完整

這不但費工，遇到內部有 ` ``` ` code block 時很容易截斷。

**一個 fenced block = 一鍵複製 = 零選取誤差。**

## What this skill does NOT cover

- 純對話 / 分析 / 說明段落——那些是 orchestrator 的敘述，不是 deliverable
- Review verdict 的 judgement 部分（APPROVE / BLOCKED + checklist）——那是供閱讀的報告，不是直接貼到 GitHub 的內容
- 非 deliverable 的狀態表 / queue 表（review queue、triage batch summary）
- 自動化路徑——`commit-message` 的 output 若是直接 pipe 進 `git commit -F -`，不加外層 fence（fence 會破壞 pipe）。但若 caller 是**呈現 commit message 給使用者**過目，則適用本 skill。這個 pipe vs 呈現的區分已在 [`commit-message`](https://github.com/Lee-W/maigo/blob/main/skills/commit-message/SKILL.md) 內部說明。
