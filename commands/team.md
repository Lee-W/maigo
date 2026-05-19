---
description: 跟 /maigo:go 一樣的流程，但 Soyo + Taki 並行跑。Wall-clock 省 ~30%；fallback 用 --force-sequential。
---

<!-- mkdocs-include-start -->

# /maigo:team

跟 `/maigo:go` 同一條工作流，差別在最後審查 + 驗證階段**並行**。
Soyo 跟 Taki 互不依賴（Soyo 讀 diff、Taki 跑 command），可同時動。

## 使用

```
/maigo:team <任務描述>
/maigo:team --force-sequential <任務描述>    # 退回 /maigo:go 順序版
```

## 流程

**Sequential（必須照順序）**

1. **樂奈 (Raana)** — 探 codebase
2. **燈 (Tomori)** — 寫 `/tmp/maigo/<repo>/plan.md`
3. **使用者確認 plan**
4. **愛音 (Anon)** — 按 plan 實作

**Parallel（同時觸發兩個 Task）**

5a. **爽世 (Soyo)** — review 變更（依 `skills/strict-review`）
5b. **立希 (Taki)** — 跑 test / lint / type check

6. **合流**——兩邊都回來後一起處理

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

跟 `/maigo:go` 一樣（見該命令的「失敗處理」）。一樣 3 次同條卡關才停下找使用者。

## `--force-sequential`

使用者明確要求順序版時用。等於把 step 5a/5b 改回 5 → 6（先 Soyo 再 Taki）。
適用場景：
- 變更高風險，不想白跑 test
- Debug 並行流程本身（懷疑兩邊互相影響）

## Orchestrator 守則

- **真的並行**：用一條 message 內兩個 Task tool call 觸發 Soyo 和 Taki
- **不要假裝並行**（先 Soyo 完才呼叫 Taki 不算）
- 合流時把兩份輸出**分開呈現**給使用者，不要混在一起
- 其餘規則承襲 `/maigo:go`（不能跳關、不能放水、不能因為輪數多了打折）
