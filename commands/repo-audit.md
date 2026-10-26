---
description: repo 自身內部健診（read-only orchestrator 主持）——掃已合併可刪的 branch、未關 PR、TODO/FIXME 積壓、skill 健診（孤兒 / 重疊候選 / 指向失效）、已合併可清的 worktree（不限佈局），彙整成可複製的處置 checklist，不執行任何寫入。🌑 Mortis 一句結算。不 delegate 五人，orchestrator 直跑。
allowed-tools: Bash(git branch --merged:*), Bash(git cherry:*), Bash(git rev-parse:*), Bash(git merge-base:*), Bash(gh pr list:*), Bash(grep:*), Bash(git worktree list:*), Bash(gh search prs:*), Read
---

<!-- mkdocs-include-start -->

# /maigo:repo-audit

> 🌙 Doloris：讓我們看清楚，這個 repo 裡還留著什麼。

read-only 內部健診——不刪 branch、不關 PR、不改 code。
只掃描、彙整，把可執行的處置選項交回給你。

## 使用

```
/maigo:repo-audit
```

無參數。對當前所在的 git repo 執行。

## 五個資料源（全 read-only）

### A. 已合併可刪的 branch

```bash
git branch --merged main
```

過濾掉 `main` 與當前 branch 自身，列出其餘已合入 main 的本地 branch，理由標「已合入 main（ancestor）」。

`git branch --merged` 只認 commit ancestry；rebase / squash / cherry-pick 合併後 commit hash
不同，認不出來，但這些 branch 仍可刪。對**未被 `--merged` 列出**的其餘本地 branch（同樣排除
`main` 與當前 branch；`--merged` 已列出的跳過下面兩項，避免重複列出）各跑兩項唯讀辨識：

```bash
git cherry main <branch>
gh pr list --state merged --head <branch> --base main --json number,url,mergedAt,headRefOid
```

（`--base` 用實際主 branch，上面以 `main` 示意。）

- `git cherry` 輸出**每一行都是 `-`**（patch 內容已等價存在於 main；rebase / cherry-pick 場景）→
  理由標「patch-equivalent 已在 main」。有任何 `+` 行表示至少一個 commit 還沒進 main，這項不命中。
  輸出為空不當作命中（該情形 branch 多半已是 ancestor，本應被 `--merged` 列出；空輸出不足以證明可刪）。
- `gh pr list` 回傳非空（該 head branch 有 MERGED 的 PR；squash 場景 patch 不等價，只能靠這項）→
  多筆時取 `mergedAt` 最新的一筆，再做機械式防護：
  - `git rev-parse <branch>` 等於該筆 `headRefOid`，或
  - `git merge-base --is-ancestor $(git rev-parse <branch>) <headRefOid>` exit 0（branch tip 是
    PR 合併時 head 的 ancestor；`headRefOid` 在本機不存在則視為不通過）

  任一成立 → 理由標「PR #N merged」。兩者皆不成立（例如 **PR 合併後 branch 又加了 commit**，或同名
  branch 被重複使用做新工作）→ **不列入可刪**，改在 checklist 以註解標「PR #N 合併後 branch 有新
  commit，勿刪」。若 `git cherry` 已命中（patch 內容確實已在 main），仍以 cherry 的理由列入，
不標勿刪。

兩項都命中就並列兩個理由。**每個辨識出的 branch 都附理由**，寫進 checklist（見輸出結構）；
`gh` 不可用時只做 `git cherry` 那項。這類 branch 不是 ancestor，之後刪除要用 `git branch -D`
而非 `-d`，checklist 已照此區分。
→ **列出，不刪除。**

> **限制**：假設 main-based 工作流（`main` 為基準 branch）。detached HEAD 或其他分支策略的邊界情況暫不處理。

### B. 未關 PR（需要 `gh` CLI）

```bash
gh pr list --state open
```

列出 open 狀態的 PR。
→ **列出，不關閉。**

若 `gh` 未安裝或未登入：跳過本段，🌑 Mortis 一句告知，A / C / D 照跑，整輪不中斷。

### C. 程式碼積壓（TODO / FIXME）

```bash
grep -rn -E "TODO|FIXME" agents/ commands/ skills/ scripts/ docs/ hooks/
```

限定 repo 自有目錄，**排除 `.venv/`、`node_modules/` 等第三方目錄**，避免第三方套件 TODO 噪音。
→ **列出，不修改。**

### D. Skill 健診

orchestrator 讀 `skills/*/SKILL.md`（不開新 agent），三類檢查：

1. **孤兒 skill**：對每個 `skills/<name>/`，grep `commands/`、`agents/`、`skills/`（排除自身）、
   `hooks/` 找 inbound 引用；零引用 → 孤兒候選。但部分 skill 純靠 frontmatter `description`
   被 model 觸發（repo-detect 型，如 `airflow-aware`、`commitizen-aware`），不靠文字引用——
   這類即使零 grep 命中也**標註「model-triggered，非引用型」**，不當真孤兒。
2. **重疊候選**：讀所有 SKILL.md 的 description + Consumers，用判斷力標出兩個 description
   幾乎互相涵蓋、consumer 集合高度重疊的配對 → 列為「考慮合併」候選，附一句理由。
   **注意**：co-load（同一命令常同時載入兩個 skill）不等於重疊——先確認兩者是刻意分工
   （如各自負責不同關注點）還是內容真的重複，分工型不列為候選。
3. **指向失效**：grep 各 SKILL.md 內文的 inline code 路徑（`skills/...`、`scripts/...`、
   `${CLAUDE_PLUGIN_ROOT}/...`），確認目標存在——markdown link 已由 `validate_plugin.py` 的
   `check_relative_links` 擋，這裡只補它不查的 inline code 指向類。

→ **三類都只列出，不合併、不刪除、不改指向**——advisory，判斷與執行留給使用者或後續
[`/maigo:crystallize`](https://github.com/Lee-W/maigo/blob/main/commands/crystallize.md)。

### E. 已合併可清的 worktree（不限佈局）

```bash
git worktree list --porcelain
```

列出所有 linked worktree（不能用「目錄名長得像 `<repo>-*`」去猜——`ring` /
`ring-codex` 是兩個各自獨立的 clone，不是彼此的 worktree，必須用 `git worktree
list --porcelain` 這種權威來源）。這個指令不管實體路徑在哪——不論 worktree
放在 `.worktrees/`（見
[`skills/git-workflow/references/worktree-hygiene.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/references/worktree-hygiene.md)）
或其他位置（例如舊的 sibling 佈局遺留），只要是這個 repo 的 linked worktree
都會列出來。對每個 worktree 的 branch 名，比照 A 段既有的「已合併」判斷方法
（squash-merge 場景用 `gh search prs` 而非 `git branch --merged`，見上述
worktree-hygiene.md）判斷是否已合併，命中就把 `git worktree remove <path>` +
`git branch -D <branch>` 加進處置 checklist。

→ **列出，不執行。** 這是 repo-audit 既有的「單一 repo、cwd 視角」報告——跟
Group F 的跨 repo 總索引是不同東西，不在這裡順手加跨 repo 掃描。

## 輸出結構

各段有發現時，彙整成**單一 fenced code block** 的處置 checklist：

```
# repo-audit 處置 checklist（以下指令 repo-audit 不會執行，確認後自行貼）

## A. 可刪 branch
git branch -d <branch-name>  # 已合入 main（ancestor）
git branch -D <branch-name>  # patch-equivalent 已在 main（已確認 tip 無未合併 commit）
git branch -D <branch-name>  # PR #<number> merged（已確認 tip 無未合併 commit）
# <branch-name>：PR #<number> 合併後 branch 有新 commit，勿刪
# 若需要刪遠端：git push origin --delete <branch-name>

## B. 待處理 PR
gh pr view <number>
# gh pr close <number>  # 若確認要關

## C. TODO / FIXME
# <file>:<line>: <內容>
# → 自行決定修復或移除

## D. Skill 健診
# 孤兒（非 model-triggered）：<skill> — 零 inbound 引用
# 重疊候選：<skill A> / <skill B> — <一句理由>
# 指向失效：<skill>/SKILL.md → `<path>` 不存在
# → 合併 / 退役 / 修指向，交你或 /maigo:crystallize 判斷

## E. 已合併可清的 worktree
git worktree remove <path>
git branch -D <branch-name>
```

各段無發現則**省略該段**；五段全空則省略整個 checklist。
**範例 code block 內不寫絕對路徑**——以相對路徑或 `~/` 表示。

## 結算

```
🌑 Mortis：<結算句>
```

- 全乾淨：「這次是乾淨的。就這樣。」
- 有積壓：靜靜指出剩幾件，不催促（1 句、克制）。

## Orchestrator 守則

- **完全 read-only**：不刪 branch、不關 PR、不改 code；處置只輸出文字，不執行。
- **不 delegate 五人**：orchestrator 直接執行 git / gh / grep 指令 + 讀 SKILL.md 判斷，彙整輸出。
- **任一指令失敗 → 跳過該段 + Mortis 1 句告知，不中斷整輪**：
  - `gh` 失敗（未安裝 / 未登入）→ 跳過 B 段與 A 段的「PR merged」辨識（`git cherry` 照跑）（判斷 E 段合併狀態用的 `gh search prs` 同樣受影響，跳過即可，不擋 E 段其餘列表輸出）
  - `git` / `grep` 失敗 → 跳過對應段
- **D 段是判斷型 advisory**：孤兒 / 重疊 / 指向失效三類都只列出候選，不代使用者拍板合併或刪除。
- **開場**：🌙 Doloris 帶入（鋪陳語氣，見 [`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md)）。
- **收場**：🌑 Mortis 1 句結算。
- **對話**：對話本體（旁白節點以外）的互動節奏與用詞，依 [`skills/orchestrator-voice`](https://github.com/Lee-W/maigo/blob/main/skills/orchestrator-voice/SKILL.md)。

## 與其他命令的差異

| 命令 | 對象 | 場景 |
|------|------|------|
| `/maigo:doctor` | 環境依賴（gh, git, python） | 「東西跑不起來，先診斷」 |
| `/maigo:triage-issue` | inbound GitHub issue | 「inbox 積了一堆 issue，批次 triage」 |
| `/maigo:repo-audit` | repo 自身（branch / PR / TODO） | 「定期清 repo，看積壓了什麼」 |

→ 場景對照、其他命令：[Commands reference](https://github.com/Lee-W/maigo/blob/main/docs/reference/commands.md)
