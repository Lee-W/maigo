---
description: 對 PR / branch / commit range 做嚴格 review——樂奈看 context、燈寫對照基準、爽世挑問題、立希跑 verify。愛音不上場。
---

<!-- mkdocs-include-start -->

# /maigo:review

對**既有的**變更做嚴格 review。跟 `/maigo:go` 不同，這裡沒有實作環節——
變更已經寫好了，要做的是**判斷它對不對**。

## 使用

```
/maigo:review <github-pr-url>          # GitHub PR（需要 gh CLI）
/maigo:review <pr-1> <pr-2> ...         # 多 PR 批次（空白或逗號分隔）
/maigo:review <branch-name>             # 本地 branch（跟 main / 預設 base 比）
/maigo:review <commit-range>            # 例：HEAD~3..HEAD 或 main..feature
/maigo:review --refresh-board           # 只刷新持久 board、列出該看的，不進 review
```

不給參數 → 預設 `HEAD` 對 `main`（review 你目前 branch 的所有變更）。
`--refresh-board` 見 `skills/strict-review/references/review-batch-queue.md`「持久 review board」。

**模式（optional）：**

```
/maigo:review --mode=design-preview <target>     # 只看設計層，不查 evidence
/maigo:review --mode=compliance-only <target>    # 只查 convention/safety/magic/TODO/bloat
/maigo:review --bilingual <target>                # 雙語輸出（zh-TW 快結 + English detail）
/maigo:review <target>                            # 預設 full mode（9 項全跑）
```

Mode 對照表（checklist subset、Taki 是否跑）與 `--bilingual` 正交關係、mode 旗標的處理機制
（rubric 註解、Soyo 收到的 checklist subset、Taki skip 規則）見
`skills/strict-review/references/review-modes.md`。

## 多 PR 批次與狀態前置處理

`/maigo:review` 接受**多個** PR 用空白或逗號分隔。orchestrator 自動排序後一次一個 review；每完成一個 PR 等使用者 go-ahead 才推進。完整排序規則、queue 表格式、merged/closed/draft 前置處理表、一次一個 PR 的 go-ahead 規則，見
`skills/strict-review/references/review-batch-queue.md`。長期跨 session 追一批 PR 時用同檔的「持久 review board」（`.maigo/review-board.md` + `--refresh-board`）——queue 是 per-run，board 記得跨 session 的狀態轉移（含「你回過但作者又推新東西」）。

## 雙語輸出

`--bilingual` 旗標或 repo-detect 自動觸發時（如 `apache/airflow`），最終 report 前面加一段 Taiwanese Mandarin 快結。觸發規則、zh-TW 行文規範見
`skills/strict-review/references/review-modes.md`「雙語輸出」；版型範本在
`skills/strict-review/references/review-templates.md`「雙語版」小節。

## 流程

### 1. 樂奈 (Raana) — 抓變更 + 周邊 context。「看完了。相關的在這三個檔案。」

**先套 [`skills/pr-context-cache`](https://github.com/Lee-W/maigo/blob/main/skills/pr-context-cache/SKILL.md)**：跑 `python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/pr_context_cache.py" <source>`——第一次 fetch 後 cache 到 `.maigo/review-rubric.md` 開頭的 `<!-- pr-context-cache:start v1 -->` 段，後續 re-review 同 source 且 diff sha 未變 → 直接還原，跳過 `gh pr view / gh pr diff / gh pr checks` 重抓。script 跑不起來 → 依下面指令手動抓（不寫 cache）。

- **取 diff**：
  - GitHub PR → `gh pr view <num/url> --json title,body,additions,deletions`、`gh pr diff <num/url>`
  - 本地 branch → `git diff <base>...<branch>`、`git log <base>...<branch>`
  - commit range → `git diff <range>`
- **看周邊**：diff 涉及檔案的呼叫關係（被誰用、用了誰）、同檔案 / 同 module 既有的寫法慣例
- 回報：變更摘要 + 周邊 context + 既有慣例

### 2. 燈 (Tomori) — 寫 review rubric 到 `.maigo/review-rubric.md`。「……讓我先理清楚它想做什麼。」

（目錄不存在請先 `mkdir -p .maigo`）

從 PR description / commit message / linked issue / 變更本身，萃取出 reviewer 的**對照基準**
（acceptance / edge case / trade-off / 待釐清點）。欄位骨架見
`skills/strict-review/references/review-templates.md`「Review rubric 骨架」。

**為什麼這步很關鍵：** 沒有對照基準的 review = 憑感覺。
這也是 reviewer 不嚴謹最常見的根因。

### 3. 爽世 (Soyo) — 拿 rubric 對 diff 做嚴格 review。「你說的『應該』，是有跑過、還是只是『應該』？」

依 `skills/strict-review/SKILL.md` 操作（預設 BLOCKED、9 項 checklist、要 evidence、不接受 TODO 規避）。

**這條 command 加碼：**
- 每條 must-fix 要對應 rubric 的哪一條（acceptance / edge case / trade-off）
- 內部 / 外部 PR 改法粒度的差異，見 SKILL.md 的 "Adapting per context" 表格

**Mode-aware：** orchestrator 傳給 Soyo 的 prompt 必須明示 mode 與對應 checklist subset。Soyo 輸出 checklist 表時：mode subset 內的項照常 `[x]` / `[ ]`；不在 subset 內的項標 `[—]`，附 `skipped by mode=<name>`。

### 4. 立希 (Taki) — 跑驗證。「跑出來爆了，看 line 42。」

**若 mode=design-preview → 不啟動本 stage，最終報告 Verification 段標「Skipped (mode=design-preview)」。**

- **checkout 變更**：
  - PR → `gh pr checkout <num/url>`
  - branch → `git checkout <branch>`
- 跑 test / lint / type check，照 `agents/Taki.md` 的標準回報
- **不接受「CI 已經綠了」當理由略過**——至少重跑一次 lint/type 確認本地能複現

### 4.5 裁決 gate（有 Soyo findings 才觸發）

report 印完後，orchestrator 邀請使用者**逐條**對 must-fix / nit 表態：

- `採納`——這次修，不寫記憶
- `駁回（一般）`——這次跳過，不寫記憶
- `標記本 repo 不適用 + 理由`——導向 Soyo 的即時 propose（依 `agents/Soyo.md` 寫「本 repo 不適用 X 因為 Y」、type:project、input-not-waiver entry）

**只有「標記不適用 + 理由」才觸發 propose + 寫記憶**；`採納` / `駁回（一般）` 不寫任何記憶。

**gate 不 block report、不改 verdict**——report 出完後純收集意願，不影響 Soyo 的 APPROVE / REQUEST_CHANGES / BLOCKED 結論。
使用者沉默 / 全採納 / Soyo 無任何 finding（must-fix 與 nit 皆空，即 APPROVED 且無 suggest）→ 無聲略過整個 gate；APPROVED 但有 nit 仍觸發 gate（nit 非空）。

**無次數驅動收斂**：orchestrator 不追蹤「某條 finding 被駁回幾次」、不自動 soften；
依 [`docs/skills/strict-review`](https://github.com/Lee-W/maigo/blob/main/docs/skills/strict-review.md) 的「user previously accepted X is not evidence」——純駁回記錄不影響下次 review 標準。

記憶寫入**唯一路徑**：透過 Soyo propose → 使用者 confirm flow（不新增第二條寫入路徑）。

### 5. 學習收尾——從 PR 既有真人 review 萃取慣例

**Gate**：source 是 GitHub PR **且**抓得到任一既有 review / comment 才觸發；
非 GitHub PR（本地 branch / commit range）或 PR 無任何既有意見 → **靜默 skip**，不問使用者。

**抓取**（orchestrator 親跑，不開新 agent）：沿用
`skills/github-reply-draft/references/comment-fetch-and-triage.md`「抓取」的三段 query
（與 [`/maigo:address-comments`](https://github.com/Lee-W/maigo/blob/main/commands/address-comments.md) step 2 共用）——
Inline review threads（GraphQL，含 `isResolved`）、Review 摘要（`gh pr view --json reviews` +
GraphQL url 補丁）、Conversation comments（`gh pr view --json comments`）。

抓不到任何一種 → 靜默 skip。

**萃取**（orchestrator 靜默過一遍，篩「convention 形狀、會再犯」候選）：

收進候選：reviewer 指出的通用慣例 / 設計原則（命名、結構、錯誤處理風格、測試策略），或同類意見在此 PR 出現多筆。

排除：一次性 typo / rename / 純 bug fix、純提問型 comment。

候選為 0 → 靜默結束，不問使用者。

**確認與寫入**：orchestrator 印候選清單（每筆一句「為什麼值得記 + 建議 type:project」），
用 **AskUserQuestion**（multiSelect）讓使用者勾；一筆都沒勾 → 印「本次沒有要記住的慣例」正常結束。
勾中的每筆，依序各跑一輪 [`/maigo:remember`](https://github.com/Lee-W/maigo/blob/main/commands/remember.md) 步驟 5+6 寫入 type:project。
**不另寫一份寫入規格**——路徑、rollback、同 slug 處理全交給 remember 既有規格。

## 輸出

單一 PR / branch / range（預設）輸出 Context / Rubric / Verdict / Verification / Bottom line
五段；batch 內最後一個 PR 跑完後把「Queue 還剩...」那行換成 roll-up；`--bilingual` 或
repo-detect 觸發時最終 report 前加 Taiwanese Mandarin 快結 + horizontal rule 再接英文 detail。
三種版型的完整骨架見 `skills/strict-review/references/review-templates.md`「輸出」。

## 與 `/maigo:go` 的差異

| 項目 | `/maigo:go` | `/maigo:review` |
|------|---------|---------------|
| Anon 上場 | 是（核心） | 不上場 |
| 燈的產出 | 實作計畫 (`plan.md`) | review rubric (`review-rubric.md`) |
| 終態 | 變更落地 + 全綠 | review 報告 |
| 適用 | 開發新功能、修 bug | PR review、code audit |

## Orchestrator 守則

- **旁白**：orchestrator 對使用者說話時戴上旁白的臉——開場、收場、卡關節點由 🌙 Doloris / 🌑 Mortis 旁白，依 [`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md)。
- **不能跳過燈**——沒有 rubric 的 review 就是憑感覺
- **不能跳過樂奈**——脫離 context 的 review 會把「不熟悉」誤判成「有問題」
- 爽世的 verdict 不因為「author 是大佬」放水
- 立希拒絕「CI 已綠就不跑」，本地至少要重跑 lint/type
- 你（orchestrator）不要自己 review，每個 agent 都用 Task tool 啟動
- Soyo 的 review 輸出若含 `## Memory propose`，
  把 review report 完整呈現給使用者後再觸發 confirm flow；
  不要在使用者讀完 report 之前插入確認問題。
- **多 PR batch**：queue 排序、merged/closed 自動 skip、draft 先問、PR 與 PR 間等 go-ahead——細節見「## 多 PR 批次與狀態前置處理」；不要一次 fire 多個 review，不要自己決定 draft 要不要看。
- **持久 board**：使用者長期追一批 PR 時維護 `.maigo/review-board.md`（跨 session）；每跑完一顆回寫該行狀態，`--refresh-board` 只刷新不 review——細節見 `skills/strict-review/references/review-batch-queue.md`「持久 review board」。board 決定誰該看，review 負責看，兩者不重疊。
- **雙語自動觸發**：repo-detect 回報 `apache/airflow` 時 orchestrator 自動加 `--bilingual`；偵測非 Airflow repo 但使用者顯式傳 `--bilingual` 也照樣執行——`--bilingual` 純粹是輸出層 flag，不會改變 agent 行為。
- orchestrator 草擬要貼到 PR 的回覆 / comment 時，遵守 [`skills/copyable-deliverable`](https://github.com/Lee-W/maigo/blob/main/skills/copyable-deliverable/SKILL.md)——放單一 fenced code block 供複製。
- 草擬 GitHub PR review thread 回覆時，依 [`skills/github-reply-draft`](https://github.com/Lee-W/maigo/blob/main/skills/github-reply-draft/SKILL.md)——預設簡短、不引 SHA、只提最終 diff 裡存在的 symbol、一 thread 一則、不過度宣稱已解決、附 attribution footer。
- **裁決 gate（§4.5）與 Soyo propose 的關係**：gate 把「不適用+理由」導向 Soyo 的即時 propose；
  orchestrator 自己不寫記憶、不 soften review；記憶寫入唯一路徑是 Soyo propose → confirm flow。
  gate 在單一 PR 的 report 之後、下一個 PR 的 go-ahead 之前——不與批次推進混淆。
- **A 步驟（§5 學習收尾）**：orchestrator 親跑、不開新 agent、只讀 GitHub（不回覆 / 不 resolve thread、不 push、不碰 GitHub 寫入）。
