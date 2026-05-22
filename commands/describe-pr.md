---
description: 從當前 branch 的 commits / diff 產 GitHub PR title 與 description。Orchestrator 前置抓料，燈 (Tomori) 套 `github-title-description` skill 寫草稿。
---

<!-- mkdocs-include-start -->

# /maigo:describe-pr

幫忙寫 PR 的 title 跟 description——拿你 branch 已經有的 commits / diff，
產出符合「user-impact title + Why / What / Test Plan」結構的草稿。
你 review / 修改後再用 `gh pr create` 或 GitHub UI 開 PR。

這條命令是**燈一個人的舞台**：orchestrator 先把 git 那些料抓齊（燈沒有 Bash），
交給燈把它寫成一份 reviewer 讀得懂的 PR narrative。

## 使用

```
/maigo:describe-pr                    # 預設 base = main，當前 HEAD
/maigo:describe-pr --base develop     # 指定 base branch
/maigo:describe-pr --base origin/main # 指定 remote base
```

## 流程

### 1. Orchestrator 前置——抓料

燈沒有 Bash，git 相關的料由 orchestrator 先抓齊：

1. **決定 base**：
   - 有 `--base <ref>` → 用該值
   - 無 → 預設 `main`；若 `main` 不存在則試 `master`，再不行 → 印錯誤「找不到 base branch，請用 `--base` 指定」並結束（非 0 退出）。

2. **抓 git context**：
   - `git rev-parse --abbrev-ref HEAD`（當前 branch 名；若 == base → 印「目前 HEAD 就在 base 上，沒有可描述的變更」並結束）
   - `git log <base>..HEAD --pretty=format:'%h %s%n%b' --no-merges`（無 commit → 印「`<base>..HEAD` 沒有 commit，沒東西可描述」並結束）
   - `git diff <base>...HEAD --stat`
   - `git diff <base>...HEAD`（過大時取前 2000 行 + 結尾標註「diff truncated」）

3. **偵測 commit-style**：
   - 讀 `pyproject.toml`（找 `[tool.commitizen]`）/ `.cz.toml` / `.cz.json` / `cz.yaml` / `commitlint.config.js` / `.commitlintrc*`
   - 命中 → 標記 `commit_style = conventional`；否則 `commit_style = freeform`
   - **此偵測只供 skill 參考既有 commit message 風格用——PR title 本身永不套 conventional commits 格式**

4. **偵測 PR template**：
   - 依序找：`.github/PULL_REQUEST_TEMPLATE.md` → `.github/pull_request_template.md` → `.github/PULL_REQUEST_TEMPLATE/` 目錄內第一個 `.md` 檔
   - 找到 → 讀取 template 內容，作為描述框架傳給燈（取代預設 Why / What / Test Plan 結構）
   - 找不到 → 用 skill 預設結構

把 1–4 的結果整理成一份 bundle，連同「不 hallucinate」守則一起寫進啟動燈的 Task prompt。

### 2. 燈 (Tomori) — 把料寫成 PR 草稿。「……讓我先理清楚它想做什麼。」

orchestrator 用 Task tool 啟動燈，把前置 bundle 交給她。燈：

- 做啟動時的記憶載入（照 [`agents/Tomori.md`](https://github.com/Lee-W/maigo/blob/main/agents/Tomori.md)），輸出開頭印 `## Loaded memory entries`——
  若有相關 `user` / `convention` entry（例：PR 描述偏好、語言偏好）納入草稿考量
- 依 [`skills/github-title-description/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/github-title-description/SKILL.md)
  產出 PR title + description，遵循該 skill 的 Output format（`## Suggested PR title` + `## Suggested PR description`）
- **describe-pr 模式不寫 plan.md、不寫任何檔**——直接把草稿回給 orchestrator

### 3. Orchestrator 收尾

- 把燈的草稿原樣印到對話。**不寫任何檔**（不存 `/tmp/maigo/`、不 push、不開 PR）。
- **附帶提示**（最末）：
  - 「若要直接開 PR：`gh pr create --title '<title>' --body-file -`（接 stdin 貼 description）」
  - 若燈的草稿標出 `<待補：...>`，列出來提醒使用者補。

## 失敗處理

- base / branch 的問題（找不到 base、HEAD == base、無 commit）在**步驟 1 前置**就判掉，不啟動燈。
- 燈回的草稿被 TeammateIdle hook 擋下（缺 `## Loaded memory entries`，或 PR 草稿缺 `## Suggested PR title` / `## Suggested PR description`）→ orchestrator 把擋下原因完整轉給燈重產。

## Orchestrator 守則

- **旁白**：orchestrator 對使用者說話時戴上旁白的臉——開場、收場、卡關節點由 🌙 Doloris / 🌑 Mortis 旁白，依 [`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md)。
- **只開一個 agent（燈）**——前置抓料與收尾印出是 orchestrator 的事；中間「把混亂寫成 narrative」交給燈。其他命令的 orchestrator-solo pattern（`/maigo:remember` / `/maigo:memory` / `/maigo:retro`）不適用這條。
- **不寫任何檔**——describe-pr read-only on filesystem；燈在這條命令是 PR-draft 模式，也不寫 `plan.md`。
- **不開 PR / 不 push**——只產草稿，使用者自己貼到 GitHub。
- **不 hallucinate**：commits / diff 沒給的訊號就標 `<待補：...>`，不要編造 motivation 或 test plan——這條守則要明寫進給燈的 Task prompt。
- **不對 title 套 conventional commits**——即使 repo 用 commitizen 也不套；那是 commit message 的事，不是 PR title 的事。

→ Skill 完整內容：
[`skills/github-title-description/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/github-title-description/SKILL.md)

→ 場景對照、其他命令：[Commands reference](https://github.com/Lee-W/maigo/blob/main/docs/reference/commands.md)
