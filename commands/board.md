---
description: 讀寫 `.maigo/board.md` Work Board——混合追蹤 issue、自己的 PR、在審的 PR，依「你的球 / 等別人 / merged-closed」分區刷新；`--serve` 用 mkdocs 起本地 live reload 閱讀層。orchestrator 直跑，不 delegate 五人。
allowed-tools: Bash(gh api:*), Bash(gh issue view:*), Bash(gh pr view:*), Bash(gh repo view:*), Bash(python3 scripts/board_serve.py:*), Bash(python3 scripts/board_state.py:*), Read, Write, Edit
---

<!-- mkdocs-include-start -->

# /maigo:board

> 🌙 Doloris：「先看清楚球在誰手上，再決定下一步要往哪裡走。」

Work Board 是跨 session 的工作看板：issue triage / 接工、自己的 PR、正在 review 的 PR
全都放進 `.maigo/board.md`，依「誰該動」分成三欄。

命令由 orchestrator 直跑，不動員五人；正典規格在
[`skills/work-board`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md)。

## 使用

```
/maigo:board <targets...>   # 混貼 issue/PR 編號或 URL；入板後刷新全板、印 🎯
/maigo:board                # 無參數：刷新全板、印 🎯 + 其他區計數
/maigo:board --all          # 刷新後印整板
/maigo:board --serve        # 起本地 live reload 網頁（mkdocs），改 board.md 存檔即所見
/maigo:board --learn        # 對已勾但未 🧠 的項目跑學習盤點
/maigo:board --check <n...> # 標記「我親自處理過」，作為 --learn 訊號
/maigo:board --uncheck <n...> # 取消「我親自處理過」標記
/maigo:board --drop <n...>  # 不追了，軟刪移到 🗄️ 已放棄（tombstone，留痕 7 天）
```

`targets` 可混用裸編號、GitHub issue URL、GitHub PR URL。裸編號以當前 repo 判定；
URL 若指到其他 repo，行內保留 `owner/repo#n` 全稱。

## 流程

### 1. 載入或建立 board

若 `.maigo/board.md` 不存在，先建立骨架。若偵測到舊的 `.maigo/review-board.md`
且 `board.md` 尚不存在，依
[`work-board` 的併入遷移規則](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md)
搬到新 board，舊檔改名成 `.maigo/review-board.md.migrated` 留底。

### 2. 加入 targets（有參數時）

每個 target 先做型別偵測：

- URL 直接解析 owner / repo / issue-or-PR / number
- 裸編號用 `gh api repos/<owner>/<repo>/issues/<n>`；有 `pull_request` key 就是 PR
- PR 再比對 `gh api user --jq .login` 與 author，分成 🔀 你的 PR / 👀 在審的 PR
- 抓不到就進 `📥 無法分類`，附錯誤末行

加入時以 `#<n>` 或 `owner/repo#<n>` 為 key upsert；既有 checkbox 與 `🧠` 狀態必須保留。

### 3. 刷新分區

除 `--learn` 外，每次都刷新 board 上所有抓得到的項目：把每項的 `type` / `gh_meta` /
`prior_status`（讀自現有 board 行）組成 JSON 陣列，餵給
[`scripts/board_state.py`](https://github.com/Lee-W/maigo/blob/main/scripts/board_state.py)
的 `classify()` 分類，取回 `bucket` / `status` / `tier` / `next_action` 逐行回寫：

```bash
echo '<[{type, gh_meta, prior_status}, ...]>' | python3 scripts/board_state.py --you <login>
```

三張完整球權判定表、排序與 ✅ 保留天數見
[`skills/work-board`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md)；
`classify()` 是判定邏輯的唯一正典，本命令不再自行複述規則。

### 4. 輸出

無參數與 `<targets...>` 預設只印 🎯「你的球」清單，並在最後補其他區計數。
`--all` 印完整 board。

若刷新後有「已勾 `[x]` 但沒有 `🧠`」的項目，結尾加：

```
🧠 有 N 項你勾了還沒盤點 → /maigo:board --learn
```

### 5. `--serve`（閱讀層）

跑 `python3 scripts/board_serve.py`：

- 首跑在 `.maigo/_serve/` 生成 MkDocs Material scaffold（config ＋ CSS；gitignored
  工作區）；未修改的舊版會自動升級，使用者自訂版會保留並提示合併
- 導覽只顯示 Work Board；不把 `.maigo/` 所有 report 排在頁面上方
- 每個球權 section 渲染成「我處理過／項目／作者／改動／狀態／現況／下一步」七欄表格，
  不做 Kanban 橫向分欄；GitHub item 與 📄 report 皆可直接點開
- PR 行從 GitHub `additions` / `deletions` 寫入 `Δ +A/-D`；頁面可搜尋、依類型 / 狀態篩選，
  並在各球權 section 內依作者、標題或改動量排序，不回寫真相層
- 啟動優先序：repo venv 有 MkDocs Material 與 pymdown-extensions →
  `uv run mkdocs serve`；沒有 → `uvx` 臨時取得套件
- checkbox 與 `🧠` 學習狀態在表格內保留（唯讀，勾選還是只能改 `board.md`）
- 每列的「操作」選單可複製 `--check` / `--uncheck` / `--drop` 命令；網頁本身
  不開寫檔 API、不直接修改 `board.md`
- 改真相層 `board.md` 存檔，served 頁面幾秒內自動更新（mkdocs 內建 live reload）
- 細節、退場門見 [`skills/work-board` §6](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md)

### 6. `--learn`

`--learn` 不刷新其他項目，只處理 `.maigo/board.md` 裡已勾 `[x]` 且沒有 `🧠` 的行。
orchestrator 逐項抓使用者在 GitHub 的實際處理方式，蒸餾 0-3 條候選知識，接
[`memory-propose-confirm`](https://github.com/Lee-W/maigo/blob/main/skills/memory-propose-confirm/SKILL.md)
讓使用者確認；處理完（含沒有候選）就在該行加 `🧠`。

學習閘門只負責進料，不取代 `/maigo:crystallize`。

### 7. `--check` / `--uncheck`

`--check <n...>` 把對應行的 `[ ]` 改為 `[x]`，表示「這項是使用者親自處理的」；
`--uncheck <n...>` 改回 `[ ]`。兩者都可接裸編號或 `owner/repo#n`，且：

- 只改 checkbox，保留 section、整行內容與 `🧠`
- 已是目標狀態時視為成功（idempotent）
- 找不到的 target 列出錯誤，其他 target 照常處理
- `--check` 完成後若該行沒有 `🧠`，照常提示可跑 `/maigo:board --learn`

### 8. `--drop`

`--drop <n...>` 表示「不追了」：依 `#<n>` 或 `owner/repo#<n>` 找到對應行後**軟刪**——
狀態詞改為 `已放棄`，整行移到 `🗄️ 已放棄` section（tombstone，留痕 7 天），不是直接刪除、
也不是移到 ✅。保留原 checkbox 與 `🧠` 狀態。7 天後的清除（purge）本輪不做，
沒有 `--purge` flag。

## 與其他命令的差異

| 命令 | 對象 | 做什麼 |
|------|------|--------|
| `/maigo:board` | issue / 自己 PR / 在審 PR 的集合 | 決定下一步是誰的哪個動作；維護跨 session board |
| `/maigo:review` | PR / branch / commit range | 實際做嚴格 code review |
| `/maigo:triage-issue` | inbound GitHub issue | 實際下 triage verdict，產 gh 草稿 |
| `/maigo:repo-audit` | repo 自身積壓 | read-only 盤點 branch / PR / TODO / skill 健診 |

## Orchestrator 守則

- **orchestrator 直跑**：不要 delegate 五人；`gh view --json` 抓料可並行，但輸出要有界。
- **board 是真相層**：`.maigo/board.md` 保留 checkbox 與 `🧠`；`--serve` 起的網頁只是唯讀閱讀層，不寫回。
- **回寫照 upsert 合約**：行存在就替換整行並保留 checkbox / `🧠`；行不存在才 append 到對應 section。
- **`--learn` 必須確認**：候選知識要經 `memory-propose-confirm`，不可靜默寫入 memory。
- **不寫 GitHub**：board 只讀 GitHub metadata，不回覆、不 label、不 close、不 push。
