---
name: harness-discipline
description: This skill should be used when the maigo orchestrator, running in the Claude Code harness, decides whether to delegate work to a subagent instead of doing it on the main thread, needs to keep a long task's acceptance criteria from drifting after context compaction, or needs to keep verification independent from whoever produced the work. Scope note: 只在 Claude Code harness 下才適用——這裡的 orchestrator context 會被計費、可能被壓縮、且可 spawn subagent 分攤負載；沒有 subagent 能力的 harness 不適用此 skill。
---

<!-- mkdocs-include-start -->

# Harness Discipline

**Owner**: orchestrator
**Consumers**: maigo orchestrator，在 Claude Code harness 下執行任何 `/maigo:*` 命令時

只在 Claude Code harness 下適用——這裡的 orchestrator 主線 context 是最貴的 token（塞進
主線的每一行都在後續每一輪重複計費），且可能被 session 壓縮、可 spawn subagent 分攤負載。
沒有 subagent 能力的 harness 不適用本 skill。

## 委派門檻

任一成立就必須派 subagent，orchestrator 只讀結論，不親自下場：

- 預估要開 **4 個以上檔案**，或合計讀 **400 行以上**
- 要跑輸出無法預估上限的指令（整包 test suite、`git log -p`、爬網頁）
- 同一種修改要套用到 **3 個以上檔案**

## 回報合約

交辦 subagent 的 prompt 照抄以下段落：

- 只回結論、逐條驗收結果、`檔案:行號` 引用
- 長產物（diff、報告、log）：寫到檔案，回傳路徑，禁止貼原文超過 20 行
- 失敗時：回「試了什麼／錯誤原文最後 10 行／卡在哪」，不要只回「失敗了」

## Task-state 防失焦

任務預估超過 **10 輪工具呼叫**，或涉及多個交付物，適用以下流程：

1. 動工前把目標／驗收條件（逐條可勾）／明確不做的事寫進 `.maigo/plan.md`。
2. 每完成一項立刻存檔、立刻更新該項的勾選狀態——存檔的就是全部，沒存的等於沒做。
3. 察覺 context 被壓縮過（開頭出現 summary）時，先重讀 `.maigo/plan.md` 再繼續，不信任
   摘要裡的轉述——摘要會讓原始驗收條件的細節失真。
4. 使用者中途的更正，當下就寫回 `.maigo/plan.md`，不是只記在對話裡。

## 驗證紀律

- 寫的人不驗自己的產出——驗證一律派 fresh-context subagent（沒參與產出過程的）。
- 檔案類產物 → read-back：讀回來逐條對照驗收條件。
- 程式碼類產物 → 跑測試或實跑，以 exit code 為準，不採信任何敘述性的「應該可以」。
- 要填任何型號／參數／欄位名／旗標，必須有本次 session 內的實據（tool schema、官方
  文件、實跑輸出）；三者都查不到 → 標「未確認」，絕不憑印象編造。
- **證據必須獨立於嫌疑來源**：斷言資料狀態要先查 git 歷史、判監控工具要取帶外真相、
  分析自產 log 要用結構化欄位而非 substring、定罪某次改動要跑對照組、單點觀測不能
  當全稱結論（換一個會改變結果的觀測點來隔離）——八個具體案例見
  [`references/evidence-discipline.md`](https://github.com/Lee-W/maigo/blob/main/skills/harness-discipline/references/evidence-discipline.md)。

### docs-only 批次的例外

上面「寫的人不驗自己的產出」的明文例外：**docs-only 修正批次**（純文字/散文類
低風險改動）可以用 orchestrator inline 輕量檢查取代 fresh-context subagent——
prek 局部 hook、grep read-back、diff 範圍確認就夠，不必為此再燒一隻 subagent。

驗證工具本身卡住時（例如 prek 全套 hooks 首跑建環境逾時），不要讓 commit 等
驗證：`git commit --no-verify` 先落盤，完整驗證丟背景跑，跑完後如實回報結果。

適用邊界：僅限 docs / prose 類低風險改動；程式碼、migration、對外發佈物仍照
上面「驗證紀律」的原規則派 fresh-context 驗證。用 `--no-verify` commit 先行時
必須（a）向使用者明說用了 `--no-verify`，（b）背景驗證真的跑完並回報結果，
不是跳過不管。

### Review 委派的三種場景

「要不要派 review subagent」不是單一判準，依觸發方式分三種：

- 使用者要求審**自己的 branch**（例如「這個 branch 有很多細小的問題，全部抓出來」）
  → orchestrator **inline** 做：讀檔 + `git diff main..HEAD` + 逐條回報。檔數多也一樣
  留在主線，不因為量大就改派 subagent——這種場景是互動來回，使用者要邊看邊給意見、
  隨時插話調整，subagent 回一份不透明報告會打斷這個迴圈。唯一的例外是 diff 真的巨大
  （>10k 行、跨多個子系統）**且**使用者這輪還沒表態要怎麼審，此時才考慮改派。
- 使用者要求審**別人的 PR**（貼 PR 連結、「review PR NNN」）→ 派 review subagent（如
  🟡 Soyo / `strict-review`）。
- 使用者明講 `/maigo:review`（或其他多 agent review 命令）→ 走該命令的 crew 流程，這是
  opt-in 訊號，蓋掉上面兩條的預設判斷。

**與 `failure-handling` 的 529 代打不是同一件事**：那條講的是 review subagent 因基礎設施
過載反覆啟動失敗時，orchestrator 主線代打當 fallback（見
[`failure-handling`](https://github.com/Lee-W/maigo/blob/main/skills/failure-handling/SKILL.md)
「Subagent 過載 / 不可用」段），且明示違反分工守則、嚴格度不打折。這裡講的是**預設路由**——
審自己 branch 本來就該 inline，不是過載才退而求其次的代打。

## Scope discipline

執行任務時若發現「相鄰但不在被要求範圍內」的問題，先停下來回報、讓使用者決定，不要
直接動手修。特定 scope 的命令（唯讀 / 單一職責，例如只負責蒐集候選並寫記憶的流程）
尤其不要順手做修補、改 git 歷史、或碰使用者的工作區。

**Why**：曾有一次任務裡反覆超範圍——因為讀到一條舊偏好就跑去改 git 歷史
（`filter-branch`），還卡進使用者平行工作中的未暫存改動；同一個 session 還有 stash
誤觸、commit 切分來回三次。共通病根是「發現問題 → 直接動手」而非「發現問題 → 先
回報」。

**How to apply**：

- 命令有明確 scope（review / retro / audit 等唯讀或單一職責）時，發現的額外問題只
  列出來當觀察 / 候選，修補留給使用者另外明講。
- 改 git 歷史、stash、碰未暫存改動屬高風險動作，動之前先確認工作區是不是只有自己
  的改動；不是就停手回報。

### 改善建議要先界定審查範圍

使用者詢問專案有何改善空間時，不可默默把範圍縮成 working-tree diff；應明示審查
範圍，若語意指向整體則執行 repository 層健診。曾因只審未 commit 的 diff，讓局部
結論被誤解成全案結論。

### 破壞性操作先給可逆做法

在 runbook / 建議裡出現不可逆操作（刪除資料、清空歷史、硬刪 entry……）時：

1. 主動標明「這一步不可逆，會失去 X」。
2. **先給可逆 / 軟做法**當預設（archive、停用、標記 inactive、保留歷史），把硬刪
   列為「確認沒問題後才做的可選收尾」。
3. 不要把破壞性步驟寫成部署/流程的必要步驟。

**Why**：一次部署 runbook 把「刪掉改名後的孤兒資源」當成必做步驟，使用者反問
「刪掉會太激進嗎，還是有可能 archive」。實情是刪除會永久清掉歷史紀錄、不可復原；
而那些資源在新版部署後本來就會自動變 inactive（停止排程、保留歷史）——那才是天然
的 archive。預設了激進路徑，但使用者偏好保守可逆。

**How to apply**：寫含刪除/清空的步驟前先自問「有沒有不刪也能達標的軟狀態？」
（停用、改名後自動 stale、移到 archive 區）有就讓它當預設；講清楚可逆性差異；把
硬刪降級成「跑穩幾天、確認不需要歷史後再做」的可選收尾，而非流程必經。

## 與既有 skill 的分工

本 skill 只管「省 token、防失焦、驗證獨立性」三件事，不重複：

- [`teammate-flow`](https://github.com/Lee-W/maigo/blob/main/skills/teammate-flow/SKILL.md)——
  MyGO!!!!! 五人協作的流程編排（誰接誰、順序）
- [`failure-handling`](https://github.com/Lee-W/maigo/blob/main/skills/failure-handling/SKILL.md)——
  Soyo 擋下 / Taki 驗證紅 / 修正輪閉環 / 無限迴圈防護的具體處置步驟

重疊處一律連結指過去，不複製內文。派 subagent 時要用哪個模型檔位，見
[`skills/model-dispatch`](https://github.com/Lee-W/maigo/blob/main/skills/model-dispatch/SKILL.md)——
本 skill 管「要不要派」，那邊管「派給誰」。
