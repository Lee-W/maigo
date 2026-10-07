# Strict Review — Delegating a Whole Review to One Subagent

Loaded on demand when the orchestrator hands an entire PR review (or a delta
re-review) to a single subagent instead of running the stages itself — typically
inside a multi-PR batch ([`review-batch-queue.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/review-batch-queue.md)).
Covers the minimum delegation clauses, the text hand-back contract, who re-runs
which claim before publishing, and stacked PRs whose upstream already merged.

---

## 交辦的最小必備條款

subagent 不能再 spawn，所以整顆 review 由它一人依序扮演 🐱🩵🟡🟣，報告必須明示「同一
模型、共用 context」——與 [`model-dispatch`](https://github.com/Lee-W/maigo/blob/main/skills/model-dispatch/SKILL.md)
的 `execution=inline` 一致，不能宣稱獨立審查。

**整顆 review** 的交辦文至少要有：

1. **目標／動機**：PR 號、審查 mode、這顆在 batch 裡的用途（例如「作者在等 maintainer 意見」）。
2. **先讀哪些檔**：`skills/strict-review/SKILL.md`、對應 domain skill（如 `airflow-aware`）、
   本 PR 的 rubric 路徑（若 orchestrator 已備好）。不要把這些檔的內容複製進交辦文。
3. **取得 PR**：`git remote -v` 先確認哪個 remote 是 apache/airflow（`origin` 常是 fork，
   沒有 pull ref），再 `git fetch <該 remote> pull/<N>/head:review-pr-<N>`；之後一律用
   `review-pr-<N>` 這個具名 ref，禁用 `FETCH_HEAD`（下一次 fetch 就被蓋掉）。
4. **head 查兩次**：開審前與交件前各跑一次 `gh pr view <N> --json headRefOid`，兩個值都寫進報告。
5. **唯讀紀律**：不 commit、不 push、不改 PR 分支；變異驗證照
   [`SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md) 的
   共用 working tree 審查紀律還原並對帳。
6. **測試隔離**：在**同一個 Bash 呼叫**內加 `env AIRFLOW_HOME=<預建空目錄>` 前綴（理由見
   `review-batch-queue.md`「大批平行 spawn」）。
7. **防停滯條款**：長指令背景化＋輪詢＋progress 檔（全文與續跑上限見
   [`failure-handling`](https://github.com/Lee-W/maigo/blob/main/skills/failure-handling/SKILL.md)
   「Subagent 中途被切斷」）。
8. **覆蓋範圍**：報告必須明列三類——逐行審過的檔案／只做分類層級（看過檔名與性質）／未驗證。
9. **hand-back 結構**：見下一節。

**delta 重審**另外再給：舊報告路徑、已用兩步檢查算好的 `<old>`／`<new>` SHA（見
[`review-modes.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/review-modes.md)
「Delta re-review」），以及「逐條回報舊 must-fix 狀態」的要求；1、3–9 照抄。

## 報告以文字 hand-back，不用 Write 寫報告檔

**規則**：交辦文寫明「最終回覆以文字完整回傳報告正文，不要用 Write 寫報告檔；rubric 與
progress 檔可寫 scratchpad」。hand-back 固定結構：

```text
<≤10 行摘要：verdict、must-fix 數、head 前後值、覆蓋範圍一句>
--- REPORT BODY ---
<報告正文，只含 H2/H3，可直接交 publisher>
```

orchestrator 收到後自己把正文寫入 scratchpad，再走 publisher。

**為什麼**：harness 會拒絕 subagent 寫報告檔（訊息為 `Subagents should return findings as
text, not write report files`）。交辦文若叫它寫 `report-<N>.md`，有的 agent 會誠實回報被擋，
有的會靜默改回傳文字——orchestrator 無法事先知道是哪一種，只能事後代寫、逐顆確認。

> 案例（2026-10 batch）：十幾個 review agent 寫 `report-<N>.md` 都被拒；部分回報、部分靜默改
> 回文字，orchestrator 逐顆代寫。之後交辦文改成上面的結構，就不再需要猜。

這與 [`handback-content-missing.md`](https://github.com/Lee-W/maigo/blob/main/skills/failure-handling/references/handback-content-missing.md)
是不同問題：那裡是 handback 送達但內容遺失；這裡是內容的**載體**選錯。

## 報告裡的實跑結論由誰重跑

orchestrator 不重跑 subagent 的全部 PoC，但**發佈前至少獨立核對一兩個最容易驗證的承重
事實**——CI 狀態（`gh pr checks`）、lock 內容、`headRefOid`。報告 Verification 段要分開標：
哪些是 orchestrator 自己核對的、哪些只是 reviewer 的 PoC。

**為什麼**：同一模型扮演四角已經沒有獨立性；連 orchestrator 也不看，報告裡每一句都只有
一個來源。挑最便宜的承重事實核對，成本低，又能抓到「整份報告建立在錯的 head／錯的 CI 狀態上」
這種最致命的錯。

## Stacked PR：上游已 squash 進 main

**規則**：審 stacked PR 前先查上游 PR 是否已 merge。已 merge 時：

- 真實 delta ＝ `git diff <上游 squash 前最後一個 commit> <head>`，或直接看 PR 自己的 commit
  清單（`gh pr view <N> --json commits`）；不要用 `gh pr diff` 的整包 diff 下判斷。
- 報告把「需要 `git rebase --onto upstream/main <舊上游 commit> <branch>`」列為**流程性阻擋**
  ，不是程式缺陷；並在 Context 更正 PR 頁面顯示的規模數字。

**為什麼**：上游 squash 後，main 上是一個新 hash，PR 分支卻還帶著上游 squash 前的 commit。
GitHub 把那些 commit 算進本 PR，規模與 diff 都會虛報，而且 `mergeStateStatus=DIRTY`／
`CONFLICTING`——看起來像作者要解大衝突，實際上一個 `rebase --onto` 就消失。

> 案例：#74380／#74381 顯示 +613/-54（14 檔）與 +607/-4（13 檔），屬於 PR 本身的只有最後兩個
> commit（各 5 檔：#74380 約 +95/-70、#74381 約 +74/-5）；其餘是上游 #74379 squash 前的 `98a8c386c8`，main 上已有
> 它的 squash 版 `72d612c357`。
