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

- 把燈的草稿原樣印到對話。**不寫任何檔**（不存 `.maigo/`、不 push、不開 PR）。
- **再附一份「可整段複製」的 description**：把燈草稿 `## Suggested PR description` 底下的 body
  原封不動放進**單一** fenced code block，讓使用者一鍵複製貼到 GitHub。
  - **外層 fence 用四個 backtick**（````` ```` `````），這樣 description 內部的三 backtick code block
    （例：Test Plan 的指令）不會把外層 fence 截斷。
  - title 緊接在這塊下方用一行 `**Title:** <one line>` 給出，方便連 title 一起複製。
  - 這份是「給機器/剪貼簿」的純淨版——**不含旁白、不含 `<待補>` 以外的提示文字**；
    `<待補：...>` 佔位符照樣留在 body 裡（使用者複製後自己替換）。
  - 此為 [`skills/copyable-deliverable`](https://github.com/Lee-W/maigo/blob/main/skills/copyable-deliverable/SKILL.md) 的具體套用。
- **使用者要求修改描述結構時，回覆也必須附 copyable block**：任何針對 PR description 的修改回覆（例：加 Why/What、重整結構），都必須把修改後的完整描述重新放進 4-backtick fence，並在 fence 後附 `**Title:** <one line>`。不能只用 markdown 呈現修改版本——那樣使用者拿不到可複製的純淨文字。
- **附帶提示**（最末，放在可複製 block 之後）：
  - 「若要直接開 PR：`gh pr create --title '<title>' --body-file -`（接 stdin 貼 description）」
  - 若燈的草稿標出 `<待補：...>`，列出來提醒使用者補。

### 4. Work Board 回寫

本命令本身不開 PR；只有使用者明確表示 PR 已開、或提供 PR URL / 編號時，才依
[`skills/work-board`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md) 的 upsert 合約
更新 `.maigo/board.md`：

- 新增 / 更新 🔀 你的 PR 行到 ⏳ `等 review`
- title 用實際 PR title；理由寫最後活動是你或剛開 PR

回寫時必須保留原 checkbox 與 `🧠` 標記。沒有 PR 編號時不猜、不寫 board。

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
