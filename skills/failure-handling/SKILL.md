---
name: failure-handling
description: This skill should be used when handling failures in go-class command flows — Soyo blocking with NEEDS_CHANGES / BLOCKED, Taki test failures, and infinite-loop protection for repeated same must-fix or same test ID. Applies to /maigo:go, /maigo:quick, /maigo:team, and /maigo:address-comments step 5.
---

<!-- mkdocs-include-start -->

# Failure Handling

**Consumers**: [`/maigo:go`](https://github.com/Lee-W/maigo/blob/main/commands/go.md) 失敗處理段、[`/maigo:quick`](https://github.com/Lee-W/maigo/blob/main/commands/quick.md) 同段、[`/maigo:team`](https://github.com/Lee-W/maigo/blob/main/commands/team.md) 同段、[`/maigo:address-comments`](https://github.com/Lee-W/maigo/blob/main/commands/address-comments.md) step 5 都引用本 skill。

### 爽世擋下（NEEDS_CHANGES / BLOCKED）

1. **完整把爽世 (Soyo) 的輸出傳給愛音 (Anon)**——must-fix 清單 + evidence 待補 + 具體改法
2. 愛音修完後，**必須附上每條 must-fix 的對應 diff 與 evidence**（不接受「都改好了」這種模糊回報）
3. 重新請爽世 review。爽世會逐條對照——任何一條沒清就維持 BLOCKED

### 立希驗證紅

1. 把 failure 完整貼給愛音 (Anon)（command + exit code + output）
2. 愛音修完後立希 (Taki) 重跑——**不接受愛音口頭說「修好了」**
3. 修到全綠才算過

### 無限迴圈防護

- 爽世連續擋 **2 次**同一條 must-fix → 停下，請使用者介入（可能是計畫本身有問題）
- 立希連續紅 **2 次**同一個 test → 停下，請使用者介入（可能 test 本身需要更新）

「同一條 must-fix」判準：Soyo 輸出的 must-fix 條目**指向同一個檔案 + 同一個函式 / 區段 + 同一類問題描述**（不要求 wording 完全相同，但語意相同算同條）。Anon 改 wording、換實作方式但問題本質沒解掉 → 仍算同條。

「同一個 test」判準：test runner 報出的**同一個 test ID**（pytest 的 `path::TestClass::test_method[param]`、其他 framework 的等價 identifier）。**錯誤訊息字串變化不算「不同 test」**——ID 相同就是同一條。一次 run 裡多個 test ID 同時紅 → 各自獨立計次，不互相抵消。
