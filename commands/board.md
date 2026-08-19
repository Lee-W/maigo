---
description: 讀寫 `.maigo/board.md` Work Board——混合追蹤 issue、自己的 PR、在審的 PR，依單一優先序階梯排進「下一件 / 等別人 / 最近結案」三區，供 nvim 直接開檔閱讀。orchestrator 直跑，不 delegate 五人。
allowed-tools: Bash(gh api:*), Bash(gh issue view:*), Bash(gh pr view:*), Bash(gh repo view:*), Bash(python3 scripts/board_state.py:*), Read, Write, Edit
---

<!-- mkdocs-include-start -->

# /maigo:board

> 🌙 Doloris：「先看清楚球在誰手上，再決定下一步要往哪裡走。」

Work Board 是跨 session 的工作看板：issue triage / 接工、自己的 PR、正在 review 的 PR
全都放進 `.maigo/board.md`，依單一優先序排名（下一件事排最上面）分成三個 section。

命令由 orchestrator 直跑，不動員五人；正典規格在
[`skills/work-board`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md)。

## 使用

```
/maigo:board <targets...>   # 混貼 issue/PR 編號或 URL；入板後刷新全板、印 🎯
/maigo:board                # 無參數：刷新全板、印 🎯 + 其他區計數
/maigo:board --all          # 刷新後印整板
/maigo:board --learn        # 對已勾但未 🧠 的項目跑學習盤點
/maigo:board --check <n...> # 標記「我親自處理過」，作為 --learn 訊號
/maigo:board --uncheck <n...> # 取消「我親自處理過」標記
/maigo:board --drop <n...>  # 不追了，移進 ✅ 最近結案（狀態詞 已放棄，7 天後跟其他結案行一起清）
```

`targets` 可混用裸編號、GitHub issue URL、GitHub PR URL。裸編號以當前 repo 判定；
URL 若指到其他 repo，行內保留 `owner/repo#n` 全稱。

## 流程

### 1. 載入或建立 board

若 `.maigo/board.md` 不存在，先建立骨架。若偵測到舊的 `.maigo/review-board.md`
且 `board.md` 尚不存在，依
[`work-board` 的併入遷移規則](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md)
搬到新 board，舊檔改名成 `.maigo/review-board.md.migrated` 留底。

若 `board.md` 存在但仍是球權三分區時代的舊格式（讀到舊版 section 標題），刷新時取每行的
checkbox / `🧠` / 狀態詞後，整檔以新的三 section 骨架重寫，不做逐行 in-place 遷移。

### 2. 加入 targets（有參數時）

每個 target 先做型別偵測：

- URL 直接解析 owner / repo / issue-or-PR / number
- 裸編號用 `gh api repos/<owner>/<repo>/issues/<n>`；有 `pull_request` key 就是 PR
- PR 再比對 `gh api user --jq .login` 與 author，分成 🔀 你的 PR / 👀 在審的 PR
- 抓不到就標狀態詞 `抓不到`（rank P0，併進 🎯 最上面），附錯誤末行

加入時以 `#<n>` 或 `owner/repo#<n>` 為 key upsert；既有 checkbox 與 `🧠` 狀態必須保留。

### 3. 刷新分區

除 `--learn` 外，每次都刷新 board 上所有抓得到的項目：把每項的 `type` / `gh_meta` /
`prior_status`（讀自現有 board 行）/ `url` 組成 JSON 陣列，餵給
[`scripts/board_state.py`](https://github.com/Lee-W/maigo/blob/main/scripts/board_state.py)
的 `classify()` 分類，取回 `section` / `rank` / `status` / `next_action` / `detail_path`，依
rank 升序 ＋ 同 rank 內 `updatedAt` 升序寫回 🎯 的編號清單（`⏳`/`✅` 依 `updatedAt` 降序、
無編號）：

```bash
echo '<[{type, gh_meta, prior_status, url}, ...]>' \
  | python3 scripts/board_state.py --you <login> --repo <owner/name>
```

三張完整球權判定表、排序與 ✅ 保留天數見
[`skills/work-board`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md)；
`classify()` 是判定邏輯的唯一正典，本命令不再自行複述規則。

**同步寫細節檔**：每項索引行寫回的同時，用回傳的 `detail_path` 建立或更新對應的
`.maigo/i/<slug>.md`——refresh 只重寫事實區（標題行 ＋ 連結/規模/下一步三條 metadata），
`## 判斷` 與 `## 筆記` 原樣保留；細節檔不存在才整份新建。格式規格、欄位省略規則見
[`skills/work-board` §1a](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md)。
刷新完成後比對 `.maigo/i/*.md` 與 board 索引行，多出來的孤兒檔案列出來給使用者確認後刪，
不自動刪。

### 4. 輸出

無參數與 `<targets...>` 預設只印 🎯「下一件」的前幾行 ＋ 其他區計數 ＋ board.md 路徑——
對話裡的輸出是拋棄式的，真相在檔案裡，沿用 [`/maigo:doctor`](https://github.com/Lee-W/maigo/blob/main/commands/doctor.md)
的 emoji 分段慣例。`--all` 印完整 board。

若刷新後有「已勾 `[x]` 但沒有 `🧠`」的項目，結尾加：

```
🧠 有 N 項你勾了還沒盤點 → /maigo:board --learn
```

### 5. `--learn`

`--learn` 不刷新其他項目，只處理 `.maigo/board.md` 裡已勾 `[x]` 且沒有 `🧠` 的行。
orchestrator 逐項抓使用者在 GitHub 的實際處理方式，蒸餾 0-3 條候選知識，接
[`memory-propose-confirm`](https://github.com/Lee-W/maigo/blob/main/skills/memory-propose-confirm/SKILL.md)
讓使用者確認；處理完（含沒有候選）就在該行加 `🧠`。

學習閘門只負責進料，不取代 `/maigo:crystallize`。

### 6. `--check` / `--uncheck`

`--check <n...>` 把對應行的 `[ ]` 改為 `[x]`，表示「這項是使用者親自處理的」；
`--uncheck <n...>` 改回 `[ ]`。兩者都可接裸編號或 `owner/repo#n`，且：

- 只改 checkbox，保留 section、整行內容與 `🧠`
- 已是目標狀態時視為成功（idempotent）
- 找不到的 target 列出錯誤，其他 target 照常處理
- `--check` 完成後若該行沒有 `🧠`，照常提示可跑 `/maigo:board --learn`

### 7. `--drop`

`--drop <n...>` 表示「不追了」：依 `#<n>` 或 `owner/repo#<n>` 找到對應行後，狀態詞改為
`已放棄`，整行移進 `✅ 最近結案`——跟其他結案行共用同一條 7 天老化規則，不再有獨立的
留痕區。保留原 checkbox 與 `🧠` 狀態；對應細節檔不動，等 7 天老化清除時跟索引行一起刪
（見 [`skills/work-board` §3 細節檔生命週期](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md)）。

## 與其他命令的差異

| 命令 | 對象 | 做什麼 |
|------|------|--------|
| `/maigo:board` | issue / 自己 PR / 在審 PR 的集合 | 決定下一步是誰的哪個動作；維護跨 session board |
| `/maigo:review` | PR / branch / commit range | 實際做嚴格 code review |
| `/maigo:triage-issue` | inbound GitHub issue | 實際下 triage verdict，產 gh 草稿 |
| `/maigo:repo-audit` | repo 自身積壓 | read-only 盤點 branch / PR / TODO / skill 健診 |

## Orchestrator 守則

- **orchestrator 直跑**：不要 delegate 五人；`gh view --json` 抓料可並行，但輸出要有界。
- **board 是唯一真相層**：`.maigo/board.md` 保留 checkbox 與 `🧠`；maigo 不提供任何呈現層，
  nvim 直接開檔即讀即改。
- **回寫照 upsert 合約**：行存在就替換整行並保留 checkbox / `🧠`；行不存在才 append 到對應 section。
  **整行替換時對應細節檔（`.maigo/i/<slug>.md`）必須跟著同步更新，不可只改索引行漏改細節檔**
  ——兩者是同一次寫回的兩個產物。同步更新＝只重寫事實區，`## 判斷` 與 `## 筆記`
  依 [`skills/work-board`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md)
  的硬規則原樣保留，沒有例外。
- **`--learn` 必須確認**：候選知識要經 `memory-propose-confirm`，不可靜默寫入 memory。
- **不寫 GitHub**：board 只讀 GitHub metadata，不回覆、不 label、不 close、不 push。
