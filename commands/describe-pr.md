---
description: 從當前 branch 的 commits / diff 產出 GitHub PR title 與 description。Orchestrator 直跑，套 `github-title-description` skill。
---

<!-- mkdocs-include-start -->

# /maigo:describe-pr

幫忙寫 PR 的 title 跟 description——拿你 branch 已經有的 commits / diff，
產出符合「user-impact title + Summary / Motivation / Test plan」結構的草稿。
你 review / 修改後再用 `gh pr create` 或 GitHub UI 開 PR。

**Orchestrator 親自跑，不開新 agent。**

## 使用

```
/maigo:describe-pr                    # 預設 base = main，當前 HEAD
/maigo:describe-pr --base develop     # 指定 base branch
/maigo:describe-pr --base origin/main # 指定 remote base
```

## 流程

orchestrator 親自跑以下步驟：

1. **決定 base**：
   - 有 `--base <ref>` → 用該值
   - 無 → 預設 `main`；若 `main` 不存在則試 `master`，再不行 → 印錯誤「找不到 base branch，請用 `--base` 指定」並結束（非 0 退出）。

2. **抓 git context**：
   - `git rev-parse --abbrev-ref HEAD`（當前 branch 名；若 == base → 印「目前 HEAD 就在 base 上，沒有可描述的變更」並結束）
   - `git log <base>..HEAD --pretty=format:'%h %s%n%b' --no-merges`
   - `git diff <base>...HEAD --stat`
   - `git diff <base>...HEAD`（過大時取前 2000 行 + 結尾標註「diff truncated」）

3. **偵測 commit-style**：
   - 讀 `pyproject.toml`（找 `[tool.commitizen]`）/ `.cz.toml` / `.cz.json` / `cz.yaml` / `commitlint.config.js` / `.commitlintrc*`
   - 命中 → 標記 `commit_style = conventional`；否則 `commit_style = freeform`
   - **此偵測只供 skill 參考既有 commit message 風格用——PR title 本身永不套 conventional commits 格式**

4. **偵測 PR template**：
   - 依序找：`.github/PULL_REQUEST_TEMPLATE.md` → `.github/pull_request_template.md` → `.github/PULL_REQUEST_TEMPLATE/` 目錄內第一個 `.md` 檔
   - 找到 → 讀取 template 內容，傳給 skill 作為描述框架（取代預設 Summary / Motivation / Test plan 結構）
   - 找不到 → 用 skill 預設結構

5. **套 skill 產出**：依
   [`skills/github-title-description/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/github-title-description/SKILL.md)
   的指引產出 title + description，遵循該 skill 的 Output format。

6. **印給使用者**：直接把 skill 的 output 印到對話。**不寫任何檔**（不存 `/tmp/maigo/`、不 push、不開 PR）。

7. **附帶提示**（最末）：
   - 「若要直接開 PR：`gh pr create --title '<title>' --body-file -`（接 stdin 貼 description）」
   - 若步驟 5 標出 `<待補：...>`，列出來提醒使用者補。

## Orchestrator 守則

- **不開新 agent**——這條 orchestrator 自己跑。pattern 跟
  [`/maigo:remember`](https://github.com/Lee-W/maigo/blob/main/commands/remember.md)
  / [`/maigo:memory`](https://github.com/Lee-W/maigo/blob/main/commands/memory.md)
  / [`/maigo:retro`](https://github.com/Lee-W/maigo/blob/main/commands/retro.md) 一致。
- **不寫任何檔**——read-only on filesystem；只 print 到對話。
- **不開 PR / 不 push**——只產草稿，使用者自己貼到 GitHub。
- **不 hallucinate**：commits / diff 沒給的訊號就標 `<待補：...>`，不要編造 motivation 或 test plan。
- **不對 title 套 conventional commits**——即使 repo 用 commitizen 也不套；那是 commit message 的事，不是 PR title 的事。

→ Skill 完整內容：
[`skills/github-title-description/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/github-title-description/SKILL.md)

→ 場景對照、其他命令：[Commands reference](../docs/reference/commands.md)
