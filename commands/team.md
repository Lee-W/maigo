---
description: 跟 /maigo:go 一樣的流程，但 Soyo + Taki 並行跑。Wall-clock 省 ~30%；fallback 用 --force-sequential。
---

<!-- mkdocs-include-start -->

# /maigo:team

跟 `/maigo:go` 同一條工作流，差別在最後審查 + 驗證階段**並行**。
🟡 爽世跟 🟣 立希互不依賴（爽世讀 diff、立希跑 command），可同時動。

## 使用

```
/maigo:team <任務描述>
/maigo:team --force-sequential <任務描述>    # 退回 /maigo:go 順序版
```

## 流程

共通 sequential 段（🐱 樂奈 → 🩵 燈 → 使用者確認 → 🎀 愛音）依
[`skills/teammate-flow`](https://github.com/Lee-W/maigo/blob/main/skills/teammate-flow/SKILL.md)。

**Parallel（同時觸發兩個 Task）**

5a. **🟡 爽世 (Soyo)** — review 變更（依 `skills/strict-review`）。「你說的『應該』，是有跑過、還是只是『應該』？」
5b. **🟣 立希 (Taki)** — 跑 test / lint / type check。「跑出來爆了，看 line 42。」

6. **合流**——兩邊都回來後一起處理。

Orchestrator 守則（旁白、不自實作、不跳關、commit message draft、fence tracking）依
[`skills/teammate-flow`](https://github.com/Lee-W/maigo/blob/main/skills/teammate-flow/SKILL.md)，
並行專屬追加規則：
- **真的並行**：用一條 message 內兩個 Task tool call 觸發 🟡 爽世和 🟣 立希
- **不要假裝並行**（先爽世完才呼叫立希不算）
- 合流時把兩份輸出**分開呈現**給使用者，不要混在一起

## Trade-off

| 模式 | Wall clock | 「白做工」風險 |
|------|-----------|--------------|
| `/maigo:go` 順序 | 100% | 0（爽世擋下就不跑 test） |
| `/maigo:team` 並行 | ~60-70% | 中（爽世擋下時，立希已經跑完了） |

多數情況淨值正——大部分變更會通過 review，並行省的時間 > 偶爾白跑 test 的成本。
但若是高風險變更（重構、scope 大）建議用 `/maigo:go` 避免白做工。

## 合流邏輯

| 爽世 | 立希 | 處理 |
|------|------|------|
| APPROVED | PASS | 完成。給使用者 summary |
| APPROVED | FAIL | 回到愛音修 test failure（review 通過不重跑） |
| NEEDS_CHANGES / BLOCKED | PASS | 回到愛音修 must-fix，**修完要重跑 Soyo + Taki**（不能假設 test 還會綠） |
| NEEDS_CHANGES / BLOCKED | FAIL | 回到愛音兩邊一起修，重跑 Soyo + Taki |

## 失敗處理

依 [`skills/failure-handling`](https://github.com/Lee-W/maigo/blob/main/skills/failure-handling/SKILL.md)——一樣 **2** 次同條卡關才停下找使用者。

## `--force-sequential`

使用者明確要求順序版時用。等於把 step 5a/5b 改回 5 → 6（先 🟡 爽世再 🟣 立希）。
適用場景：
- 變更高風險，不想白跑 test
- Debug 並行流程本身（懷疑兩邊互相影響）
