# GitHub Title & Description — Draft Bundle (抓料流程)

Loaded on demand by [`/maigo:describe-pr`](https://github.com/Lee-W/maigo/blob/main/commands/describe-pr.md)
步驟 1，以及 [`teammate-flow`](https://github.com/Lee-W/maigo/blob/main/skills/teammate-flow/SKILL.md)
收尾的 PR 草稿段。燈 (Tomori) 沒有 Bash，git 相關的料由 orchestrator 先抓齊。

下面四步與其中的失敗分支（「印錯誤並結束」「沒東西可描述並結束」）是 **`/maigo:describe-pr`
獨立執行**時的行為，不變。`/maigo:go`、`/maigo:team` 收尾時的判定與失敗處理不同，見最後一節
「收尾情境」，以該節為準：

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
   - 找到 → 讀取 template 內容，作為描述框架傳給燈（template 其餘區塊照用，但 Why / What 標題仍須保留、層級依 template 的容器 section 往下降，見 skill 的「若 repo 有 PR template」）
   - 找不到 → 用 skill 預設結構

## 收尾情境（`/maigo:go`、`/maigo:team`）

收尾草稿是 final summary 的一部分，**任何失敗都不得中斷 summary**：

1. **是否尚無 PR**：沿用
   [`pr-sync-check`](https://github.com/Lee-W/maigo/blob/main/skills/pr-sync-check/SKILL.md)
   步驟 1 的判定（`gh pr view --json number,title,body,url,state,headRefName,baseRefName,isDraft`；
   exit 非 0 或無對應 PR，或 `state` 為 `MERGED`／`CLOSED`，視為「尚無 PR」）。已有開啟中的 PR
   時不產草稿，改走 `pr-sync-check`。
2. **base**：go／team 沒有 `--base`。依序取：使用者在任務裡明講的 base；
   `git symbolic-ref --short refs/remotes/origin/HEAD`（去掉 `origin/` 前綴）；再不行才試 `main`、`master`。
   base 在 final summary 的草稿旁寫明，讓使用者能發現猜錯。
3. **失敗分支一律改為略過**：找不到 base、HEAD 就在 base 上、`<base>..HEAD` 沒有 commit、
   `gh` 不可用或其他任何抓料失敗，都**略過草稿**，在 summary 印一行原因（例：「PR 草稿略過：找不到 base
   branch」），然後繼續完成 summary；不印錯誤退出、不以非 0 結束。
4. 步驟 3、4（commit-style、PR template）照上面執行；偵測不到時照原本的預設。
