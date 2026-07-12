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

## 與既有 skill 的分工

本 skill 只管「省 token、防失焦、驗證獨立性」三件事，不重複：

- [`teammate-flow`](https://github.com/Lee-W/maigo/blob/main/skills/teammate-flow/SKILL.md)——
  MyGO!!!!! 五人協作的流程編排（誰接誰、順序）
- [`failure-handling`](https://github.com/Lee-W/maigo/blob/main/skills/failure-handling/SKILL.md)——
  Soyo 擋下 / Taki 驗證紅 / 修正輪閉環 / 無限迴圈防護的具體處置步驟

重疊處一律連結指過去，不複製內文。派 subagent 時要用哪個模型檔位，見
[`skills/model-dispatch`](https://github.com/Lee-W/maigo/blob/main/skills/model-dispatch/SKILL.md)——
本 skill 管「要不要派」，那邊管「派給誰」。
