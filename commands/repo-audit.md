---
description: repo 自身內部健診（read-only orchestrator 主持）——掃已合併可刪的 branch、未關 PR、TODO/FIXME 積壓，彙整成可複製的處置 checklist，不執行任何寫入。🌑 Mortis 一句結算。不 delegate 五人，orchestrator 直跑。
allowed-tools: Bash(git branch --merged:*), Bash(gh pr list:*), Bash(grep:*)
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

## 三個資料源（全 read-only）

### A. 已合併可刪的 branch

```bash
git branch --merged main
```

過濾掉 `main` 與當前 branch 自身，列出其餘已合入 main 的本地 branch。
→ **列出，不刪除。**

> **限制**：假設 main-based 工作流（`main` 為基準 branch）。detached HEAD 或其他分支策略的邊界情況暫不處理。

### B. 未關 PR（需要 `gh` CLI）

```bash
gh pr list --state open
```

列出 open 狀態的 PR。
→ **列出，不關閉。**

若 `gh` 未安裝或未登入：跳過本段，🌑 Mortis 一句告知，A / C 照跑，整輪不中斷。

### C. 程式碼積壓（TODO / FIXME）

```bash
grep -rn -E "TODO|FIXME" agents/ commands/ skills/ scripts/ docs/ hooks/
```

限定 repo 自有目錄，**排除 `.venv/`、`node_modules/` 等第三方目錄**，避免第三方套件 TODO 噪音。
→ **列出，不修改。**

## 輸出結構

各段有發現時，彙整成**單一 fenced code block** 的處置 checklist：

```
# repo-audit 處置 checklist（以下指令 repo-audit 不會執行，確認後自行貼）

## A. 可刪 branch
git branch -d <branch-name>
# 若需要刪遠端：git push origin --delete <branch-name>

## B. 待處理 PR
gh pr view <number>
# gh pr close <number>  # 若確認要關

## C. TODO / FIXME
# <file>:<line>: <內容>
# → 自行決定修復或移除
```

各段無發現則**省略該段**；三段全空則省略整個 checklist。
**範例 code block 內不寫絕對路徑**——以相對路徑或 `~/` 表示。

## 結算

```
🌑 Mortis：<結算句>
```

- 全乾淨：「這次是乾淨的。就這樣。」
- 有積壓：靜靜指出剩幾件，不催促（1 句、克制）。

## Orchestrator 守則

- **完全 read-only**：不刪 branch、不關 PR、不改 code；處置只輸出文字，不執行。
- **不 delegate 五人**：orchestrator 直接執行 git / gh / grep 指令，彙整輸出。
- **任一指令失敗 → 跳過該段 + Mortis 1 句告知，不中斷整輪**：
  - `gh` 失敗（未安裝 / 未登入）→ 跳過 B 段
  - `git` / `grep` 失敗 → 跳過對應段
- **開場**：🌙 Doloris 帶入（鋪陳語氣，見 [`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md)）。
- **收場**：🌑 Mortis 1 句結算。

## 與其他命令的差異

| 命令 | 對象 | 場景 |
|------|------|------|
| `/maigo:doctor` | 環境依賴（gh, git, python） | 「東西跑不起來，先診斷」 |
| `/maigo:triage-issue` | inbound GitHub issue | 「inbox 積了一堆 issue，批次 triage」 |
| `/maigo:repo-audit` | repo 自身（branch / PR / TODO） | 「定期清 repo，看積壓了什麼」 |

→ 場景對照、其他命令：[Commands reference](https://github.com/Lee-W/maigo/blob/main/docs/reference/commands.md)
