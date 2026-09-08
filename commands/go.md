---
description: MyGO!!!!! 跑一遍——樂奈先看、燈寫計畫、愛音動手、爽世擋、立希驗。
---

<!-- mkdocs-include-start -->

# /maigo:go

> 「It's MyGO!!!!!」

把這件事交給 MyGO!!!!!。從前奏到尾聲，五個人各自負責自己那一段。

## 使用

```
/maigo:go <任務描述>
/maigo:go --worktree <任務描述>   # 在獨立的 sibling worktree 裡跑整趟流程
```

## 流程

完整流程依 [`skills/teammate-flow`](https://github.com/Lee-W/maigo/blob/main/skills/teammate-flow/SKILL.md)——
🐱 樂奈探索 → 🩵 燈寫 plan → 使用者確認 → 🎀 愛音實作 → 🟡 爽世 review → 🟣 立希驗證。

審查與驗證為**順序**進行（先 🟡 爽世擋，通過後才跑 🟣 立希）。

## `--worktree`（opt-in，預設不開）

帶這個旗標時，在 🐱 樂奈開始之前，orchestrator 親自跑：

```bash
git fetch <remote>
python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/worktree_path.py" --repo <name> --topic "<任務描述>"
git worktree add -b <branch> <path> <remote>/<default-branch>
```

`<remote>` 判定：先試 `upstream`，否則退回 `origin`。之後每個 delegate 的 prompt
都要帶上這個 `path` 當 cwd（見
[`skills/teammate-flow`](https://github.com/Lee-W/maigo/blob/main/skills/teammate-flow/SKILL.md)
的 cwd 交辦紀律）。

收尾（🟣 立希全綠、commit 草擬完）時印出這個 worktree 的路徑與 branch，明講
「留在原地，等 PR merge 後可用 `/maigo:repo-audit` 看到清理建議」——**不在這裡
自動移除**。細節、`.maigo/` 歸屬規則見
[`skills/git-workflow/references/worktree-automation.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/references/worktree-automation.md)。

## 失敗處理

詳見 [`skills/failure-handling`](https://github.com/Lee-W/maigo/blob/main/skills/failure-handling/SKILL.md)。
