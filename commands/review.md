---
description: 對 PR / branch / commit range 做嚴格 review——樂奈看 context、燈寫對照基準、爽世挑問題、立希跑 verify。愛音不上場。
---

<!-- mkdocs-include-start -->

# /maigo:review

開始命令時先讀 [`skills/model-dispatch`](https://github.com/Lee-W/maigo/blob/main/skills/model-dispatch/SKILL.md)
並消費 `--model-profile <path>`；執行角色前依宿主能力解析派工，無 subagents 時依序執行。

對**既有的**變更做嚴格 review。跟 `/maigo:go` 不同，這裡沒有實作環節——
變更已經寫好了，要做的是**判斷它對不對**。

## 使用

```
/maigo:review <github-pr-url>          # GitHub PR（需要 gh CLI）
/maigo:review <pr-1> <pr-2> ...         # 多 PR 批次（空白或逗號分隔）
/maigo:review <branch-name>             # 本地 branch（跟 main / 預設 base 比）
/maigo:review <commit-range>            # 例：HEAD~3..HEAD 或 main..feature
```

不給參數 → 預設 `HEAD` 對 `main`（review 你目前 branch 的所有變更）。
要新增 / 刷新跨 session Work Board，直接用
[`/maigo:board`](https://github.com/Lee-W/maigo/blob/main/commands/board.md)。

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
`skills/strict-review/references/review-batch-queue.md`。多 PR 參數代表「現在要開始逐顆 review」；
若只是要把一批 PR 放進跨 session board，改用 `/maigo:board <pr-1> <pr-2> ...`。
長期跨 session 追一批 PR 時用
[`/maigo:board`](https://github.com/Lee-W/maigo/blob/main/commands/board.md) 的 Work Board
（`.maigo/board.md`）——queue 是 per-run，board 記得跨 session 的狀態轉移
（含「你回過但作者又推新東西」）。

## 雙語輸出

`--bilingual` 旗標或 repo-detect 自動觸發時（如 `apache/airflow`），最終 report 前面加一段 Taiwanese Mandarin 快結。觸發規則、zh-TW 行文規範見
`skills/strict-review/references/review-modes.md`「雙語輸出」；版型範本在
`skills/strict-review/references/review-templates.md`「雙語版」小節。

## 流程

### 1. 樂奈 (Raana) — 抓變更 + 周邊 context。「看完了。相關的在這三個檔案。」

**先套 [`skills/pr-context-cache`](https://github.com/Lee-W/maigo/blob/main/skills/pr-context-cache/SKILL.md)**：跑 `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pr_context_cache.py" <source>`——context 寫入本次 review rubric 檔（stdout 的 `rubric:` 路徑）開頭的 `<!-- pr-context-cache:start v1 -->` 段。PR 每次刷新 diff、metadata、CI 與討論；本地 branch／range 才在同 source 且 diff sha 未變時還原快取。script 跑不起來，或 `status: conflict`（exit 3） → 依下面指令手動抓（不寫 cache）。

- **取 diff**：
  - GitHub PR → `gh pr view <num/url> --json title,body,additions,deletions`、`gh pr diff <num/url>`
  - 本地 branch → `git diff <base>...<branch>`、`git log <base>...<branch>`
  - commit range → `git diff <range>`
- **看周邊**：diff 涉及檔案的呼叫關係（被誰用、用了誰）、同檔案 / 同 module 既有的寫法慣例
- 回報：變更摘要 + 周邊 context + 既有慣例

### 2. 燈 (Tomori) — 寫 review rubric。「……讓我先理清楚它想做什麼。」

派 🩵 燈前，**orchestrator** 取 pr-context-cache 印出的 `rubric:` 路徑（沒跑 pr-context-cache 時由 orchestrator 呼叫
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/artifact_path.py" review-rubric --topic "Review rubric: <PR title>" --url <PR url> --repo <owner/name>` 並處理 ownership 結果，
`--repo` 取值見「## 輸出」段的 `pr_context_cache.repo_slug()`；本地 branch / commit range 沒有 PR url，省略 `--url`/`--repo` 即可），
歸屬規則見 [`artifact-ownership`](https://github.com/Lee-W/maigo/blob/main/skills/harness-discipline/references/artifact-ownership.md)
（目錄不存在由 orchestrator 先建立該路徑的父目錄），再把絕對路徑、原樣 H1 與 ownership status 交給 🩵 燈。她沒有 Bash，不執行 helper 或 `mkdir`。

**派燈之前，先給她一份可讀的 diff 檔**：燈沒有 Bash，跑不了 `git diff` / `git show`，只靠
樂奈的摘要加讀現檔分不出一行是不是這個 commit 新增的。orchestrator 把 diff 存成
`<scratchpad>/diff-<id>.patch`（`git diff <base>...HEAD > <path>`；PR 來源用
`gh pr diff <num/url> > <path>`）並把路徑寫進交辦文，要求她用 diff 的**新增行**判斷
「是不是本次新增」——pr-context-cache 寫進 rubric 的 Full diff 段已覆蓋大部分情況，
只有走 fallback 手動抓（第 1 步 pr-context-cache 跑不起來）時才需要額外補這份檔案。
（實例：一次 review 曾因此把既有內容誤標成本次新增、也誤判 changelog 沒改。）

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
- item 4 命名審查：先機械列出 diff 新增的 def/method/inner function 再逐一判定，不要只讀 diff 找（見 SKILL.md item 4）

**Mode-aware：** orchestrator 傳給 Soyo 的 prompt 必須明示 mode 與對應 checklist subset。Soyo 輸出 checklist 表時：mode subset 內的項照常 `[x]` / `[ ]`；不在 subset 內的項標 `[—]`，附 `skipped by mode=<name>`。

### 4. 立希 (Taki) — 跑驗證。「跑出來爆了，看 line 42。」

**若 mode=design-preview → 不啟動本 stage，最終報告 Verification 段標「Skipped (mode=design-preview)」。**

- **checkout 變更**：
  - PR → `gh pr checkout <num/url>`
  - branch → `git checkout <branch>`
- 跑 test / lint / type check，照 `agents/Taki.md` 的標準回報
- **不接受「CI 已經綠了」當理由略過**——至少重跑一次 lint/type 確認本地能複現

### 4.5 裁決 gate（有 Soyo findings 才觸發）

report 印完後，orchestrator 邀請使用者**逐條**對 must-fix / nit 表態。選項依「PR 作者是不是使用者本人」分流
（GitHub PR 比對 `gh pr view --json author` 與 `gh api user`；本地 branch / commit range 視為自己的變更）：

**自己的變更**——要決定的是「這次修不修」：

- `採納`——這次修，不寫記憶
- `駁回（一般）`——這次跳過，不寫記憶
- `標記本 repo 不適用 + 理由`——導向 Soyo 的即時 propose（依 `agents/Soyo.md` 寫「本 repo 不適用 X 因為 Y」、type:project、input-not-waiver entry）

**別人的 PR**——使用者是 reviewer，不修 code；要決定的是「送出的 review 裡放什麼」：

- `放進 review`——照 Soyo 的嚴重度送（must-fix → request changes 的理由；nit → 建議）
- `降成建議`——must-fix 改以非阻擋的建議送出
- `不提`——不寫進 review，不寫記憶
- `標記本 repo 不適用 + 理由`——同上，導向 Soyo propose

選完後 orchestrator 依 [`skills/github-reply-draft`](https://github.com/Lee-W/maigo/blob/main/skills/github-reply-draft/SKILL.md)
起草 review 內文與 inline comment（每則 finding 一則 inline，錨點寫成 symbol 而非行號）,呼叫
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/artifact_path.py" review-draft --url <PR url> --repo <owner/name> --topic "Review draft: <PR title>"`
取得落檔路徑（`.maigo/review/<id>/draft.md`），把草稿逐字寫進那個路徑，並寫進 board 細節檔的
`## 筆記`。只起草、不送出。

**只有「標記不適用 + 理由」才觸發 propose + 寫記憶**；其餘選項不寫任何記憶。

**gate 不 block report、不改 verdict**——report 出完後純收集意願，不影響 Soyo 的 APPROVE / REQUEST_CHANGES / BLOCKED 結論。
使用者沉默 / 全採納（外部 PR 為全「放進 review」，仍照常起草） / Soyo 無任何 finding（must-fix 與 nit 皆空，即 APPROVED 且無 suggest）→ 無聲略過整個裁決 gate（不問使用者選項），
但仍照上面同一支 `artifact_path.py review-draft` 呼叫寫一份**最小 draft**（approve 用的短 body，例如「LGTM，見 review 報告」）——
`board_state.py` 的 `待送出` 發送草稿動作指向這個路徑，這步驟讓它永遠存在，不因為零 finding 而跳過；APPROVED 但有 nit 仍觸發完整 gate（nit 非空）。

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
三種版型的完整骨架見
[`skills/strict-review/references/review-templates.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/review-templates.md)「輸出」——
正文套用這份骨架；publisher 補上共用檔頭／TOC 後，讀回檔案呈現，不另外維護對話版。

報告正文先寫到 scratchpad（只含 H2/H3，雙語快結也從 H2 開始）。記下本次實際審查的
commit：PR 用 context cache 的 `Reviewed head`；本地 branch / range 用 reviewed tip 的
完整 SHA。完成驗證後重新讀 PR 的 `headRefOid`；若已改變，報告明示只涵蓋舊 head，
board 判為需要重審，不把新 head 冒充已審。

由 orchestrator 呼叫共同 publisher，再讀回產物呈現給使用者：

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/review_report.py" publish \
  --cwd <repo-root> --repo <owner/name> --source <canonical-PR-url-or-branch-or-range> \
  --head <reviewed-full-commit-sha> --title <title> --verdict <verdict> \
  --author <login-or-git-author> --body-file <scratchpad/report-body.md>
```

`--author` 是被審對象的原作者，檔頭會顯示 `**Author:**`：GitHub PR 用
`gh pr view <n> --json author --jq .author.login`（檔頭自動加 `@`）；本地 branch / range 用
`git log --format=%an <range>` 去重後以 `, ` 串接。

`verdict` 使用 `APPROVE` / `APPROVE_WITH_NITS` / `NEEDS_CHANGES` / `BLOCKED`；
🟡 爽世的 `REQUEST_CHANGES` 對應 `NEEDS_CHANGES`，`APPROVED` 對應 `APPROVE`。PR URL 用 `gh pr view --json url`
的 canonical 值，`--repo` 是 board 所在 repo；跨 repo 不拿目標 repo 冒充 home repo。

[`scripts/review_report.py`](https://github.com/Lee-W/maigo/blob/main/scripts/review_report.py)
重用 artifact_path 的命名，生成 `.maigo/review/<id>/review.md`，並統一提供：

- H1、來源、原作者（`**Author:**`）、**最後 review 時間（含時區）**、實際 reviewed commit、verdict。
- **TOC**：所有 H2/H3 的可跳轉目錄，不把 fenced code 範例誤當章節。
- 同 source 重審直接換成最新完整報告；PR 改標題仍是同一個 source。
- 新版原子寫入成功後，刪除同目錄 `review-N.md` 與舊扁平 `review-<id>.md` 中
  能確認同 source 的過期報告；草稿、rubric、手寫筆記、別顆 PR、無法確認歸屬的檔案保留。
  stdout 列出 `removed` / `retained`；清除不依賴 mtime 猜「同一份」。
- 新報告清除上一輪「已看完」標記；要由使用者看完這一版再標記。

source 衝突或檔案正在被另一個 session 寫入 → 明確失敗，保留舊檔；不要直接 Write 繞過。
舊版（沒有 metadata 的）報告只有在含 `# Review:` 標題**且**有一行 `**PR:** <canonical-url>` 時，
才會被認成同一個 source。標題寫成 `# Review: <owner/repo>#<n> — …`、卻少了 `**PR:**` 那一行的舊報告，
會被判成 `Review ownership conflict`。先確認該檔確實是同一顆 PR 的舊報告，在 H1 下方補一行
`**PR:** <canonical-url>`，再重新 publish；不要改用 Write 覆寫。
此 publisher 是 `review` kind 的寫入入口，其餘 kind 繼續使用 artifact_path 的 ownership
合約。多 PR 每顆分別 publish；roll-up 留在本輪對話，不覆蓋任何單顆 PR 的 report。

若 `removed` 含細節檔筆記中引用的舊報告，立即重讀該細節檔，用 Edit **只替換那個路徑**
成最新 `review/<id>/review.md`，保留其餘手寫內容。最後回覆附最新報告連結、最後 review
時間，以及 `/maigo:board --reviewed <n>`（或直接在 board 勾 `[x]`）和 `/maigo:board --reviews`，讓使用者知道下一步。

## Work Board 回寫

GitHub PR review 每跑完一顆並輸出 report 後，依
[`skills/work-board`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md) 的 upsert 合約
更新 `.maigo/board.md`：

- 本地 report 剛完成 → 先讀 report metadata 再跑 `board_state.py --maigo-root <repo-root>`。
  同步標題、`@貢獻者`、最後 review 時間與 report 路徑。
- 本地 verdict 尚未送 GitHub、且使用者尚未標「已看完」→ 👀 行留在 🎯 下一件，
  狀態詞寫 `待送出`——不再寫成 `BLOCKED` / `NEEDS_CHANGES` / `APPROVE_WITH_NITS` /
  `APPROVE` 之一硬留 🎯；這修掉一個既知的漂移：舊寫法在下次刷新會被 `classify()`
  判成 ⏳，本地 verdict 就此靜靜沉底
- 已在 GitHub 回覆 / approve，且之後無新活動 → 👀 行進 ⏳ 等別人，狀態詞寫實際 verdict
  （`BLOCKED` / `NEEDS_CHANGES` / `APPROVE_WITH_NITS` / `APPROVE`）
- merged / closed → 👀 行進 ✅ 最近結案
- 使用者以 `/maigo:board --reviewed <n>` 或在 board 勾 `[x]` 標記本地已看完 → ⏳；不代表已送 GitHub。
  新 head 或作者新留言會回 🎯 `↩︎ 回你的球`。
- 上面 publisher 回傳的 `path`（即
  `review/<id>/review.md` 產物的實際路徑）寫進對應細節檔（`.maigo/i/<slug>.md`，見
  [`skills/work-board` §1a](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md)）
  的 `## 筆記` 區，一行裸相對路徑連結（相對 `.maigo/`，例如 `review/9301/review.md`）——
  不再寫進索引行

回寫時必須保留原 checkbox 與 `🧠` / `🔖` 標記。刷新 / 查看 board 用 `/maigo:board`；
`/maigo:review` 不提供 board-only alias。

## 與 `/maigo:go` 的差異

| 項目 | `/maigo:go` | `/maigo:review` |
|------|---------|---------------|
| Anon 上場 | 是（核心） | 不上場 |
| 燈的產出 | 實作計畫 (`plan-<id>.md`) | review rubric (`review/<id>/rubric.md`) |
| 終態 | 變更落地 + 全綠 | review 報告 |
| 適用 | 開發新功能、修 bug | PR review、code audit |

## Orchestrator 守則

- **旁白**：orchestrator 對使用者說話時戴上旁白的臉——開場、收場、卡關節點由 🌙 Doloris / 🌑 Mortis 旁白，依 [`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md)。
- **對話**：對話本體（旁白節點以外）的互動節奏與用詞，依 [`skills/orchestrator-voice`](https://github.com/Lee-W/maigo/blob/main/skills/orchestrator-voice/SKILL.md)。
- **不能跳過燈**——沒有 rubric 的 review 就是憑感覺（唯一例外：[rebase-only 重審](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/review-modes.md)，PR 自己的 patch 逐字相同時可壓縮成樂奈＋立希，報告必須明講）
- **不能跳過樂奈**——脫離 context 的 review 會把「不熟悉」誤判成「有問題」
- 爽世的 verdict 不因為「author 是大佬」放水
- 立希拒絕「CI 已綠就不跑」，本地至少要重跑 lint/type
- 有 subagents 時把 review 交給角色執行；沒有時依 model-dispatch 的 inline 流程，checklist 與 rubric 不省略
- Soyo 的 review 輸出若含 `## Memory propose`，
  把 review report 完整呈現給使用者後再觸發 confirm flow；
  不要在使用者讀完 report 之前插入確認問題。
- **多 PR batch**：queue 排序、merged/closed 自動 skip、draft 先問、PR 與 PR 間等 go-ahead——細節見「## 多 PR 批次與狀態前置處理」；不要一次 fire 多個 review，不要自己決定 draft 要不要看。
- **Work Board**：使用者長期追一批 PR 時維護 `.maigo/board.md`；每跑完一顆依
  [`skills/work-board`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md) 回寫狀態。
  刷新 / 查看 board 用 `/maigo:board`。board 決定誰該看，review 負責看，兩者不重疊。
- **雙語自動觸發**：repo-detect 回報 `apache/airflow` 時 orchestrator 自動加 `--bilingual`；偵測非 Airflow repo 但使用者顯式傳 `--bilingual` 也照樣執行——`--bilingual` 純粹是輸出層 flag，不會改變 agent 行為。
- orchestrator 草擬要貼到 PR 的回覆 / comment 時，遵守 [`skills/copyable-deliverable`](https://github.com/Lee-W/maigo/blob/main/skills/copyable-deliverable/SKILL.md)——放單一 fenced code block 供複製。
- 草擬 GitHub PR review thread 回覆時，依 [`skills/github-reply-draft`](https://github.com/Lee-W/maigo/blob/main/skills/github-reply-draft/SKILL.md)——預設簡短、不引 SHA、只提最終 diff 裡存在的 symbol、一 thread 一則、不過度宣稱已解決、附 attribution footer。
- **裁決 gate（§4.5）與 Soyo propose 的關係**：gate 把「不適用+理由」導向 Soyo 的即時 propose；
  orchestrator 自己不寫記憶、不 soften review；記憶寫入唯一路徑是 Soyo propose → confirm flow。
  gate 在單一 PR 的 report 之後、下一個 PR 的 go-ahead 之前——不與批次推進混淆。
- **A 步驟（§5 學習收尾）**：orchestrator 親跑、不開新 agent、只讀 GitHub（不回覆 / 不 resolve thread、不 push、不碰 GitHub 寫入）。
