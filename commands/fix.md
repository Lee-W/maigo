---
description: 輕量任務入口。Orchestrator 直接呼叫 Anon 做小改動，跳過 Raana / Tomori，Anon 做完跑輕量 Soyo（4 項 checklist subset）。Stop hook 自動兜底測試。
---

<!-- mkdocs-include-start -->

# /maigo:fix

「這個小東西改一下」級別的任務。跳過 Raana 探索 / Tomori 寫 plan 的 overhead，
orchestrator 直接呼叫 Anon 動手，做完跑 Soyo 輕量 review（9 項 → 4 項）。
Test 不顯式喊 Taki——stop hook 在任務完成前自動跑測試兜底。

## 使用

```
/maigo:fix <小任務描述>
```

例：

```
/maigo:fix 把 README 第三段的拼字 "occured" 改成 "occurred"
/maigo:fix 在 auth.py:42 加 type hint
```

## 邊界（trust user）

使用者說「這是 quick-fix」就是 quick-fix——orchestrator 不自動 gate（不偵測 LoC、不偵測 file 數）。

若使用者描述聽起來像大改動（多檔案、跨 module、看起來會牽動行為），orchestrator 在啟動前**一次**提醒：「這個看起來不像 quick-fix，要改用 `/maigo:go` 嗎？」使用者回「不用、就 fix」→ 照走 fix 流程，**不再追問**。

## 流程

1. **愛音 (Anon)** — 直接動手實作（無 Raana 探索、無 Tomori plan）。「OK 那我先做這步！」
   - Anon 自己看周邊 1-2 個檔抓慣例，不做大範圍探索
   - 不寫 plan.md
2. **爽世 (Soyo)** — 輕量 review，只跑 9 項中的 4 項。「這裡這樣寫的話……應該不太對哦？」
3. **Stop hook 自動跑 test** — 不顯式呼叫 Taki
4. **Orchestrator** — Stop hook 綠後，若還有未 commit 的本次變更，依 [`skills/commit-message`](https://github.com/Lee-W/maigo/blob/main/skills/commit-message/SKILL.md) 草擬一段 commit message 附在 final summary。**不自動跑 git commit**。

## Soyo 輕量 checklist（9 項 → 4 項）

| 項 | 跑？ |
|---|------|
| 1. acceptance match | ✅ |
| 2. evidence per function | ❌ skip（stop hook 跑 test 兜底） |
| 3. edge case coverage | ❌ skip |
| 4. convention conformance | ✅ |
| 5. no unsafe pattern | ✅ |
| 6. no unexplained magic | ❌ skip |
| 7. no TODO evasion | ✅ |
| 8. no defensive bloat | ❌ skip |
| 9. no completeness theatre | ❌ skip |

合計 4 項：1 / 4 / 5 / 7。

orchestrator 啟動 Soyo 時 prompt 必須明示「mode=quick-fix」與上述 subset。Soyo 輸出 checklist 表時 subset 內項照常 `[x]` / `[ ]`，subset 外項標 `[—]` 附 reason `skipped by mode=quick-fix`。

詳細「為什麼這 4 項」與「為什麼略掉那 5 項」見
[`skills/strict-review/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md)
的 "Adapting per context" 表。

## 失敗處理

### Soyo 擋下（NEEDS_CHANGES / BLOCKED）

跟 `/maigo:go` 同——把 must-fix 完整給 Anon、修完重 review、3 次同條才停下找使用者。
詳見 [`/maigo:go`](https://github.com/Lee-W/maigo/blob/main/commands/go.md) 失敗處理段。

### Stop hook 測試紅

stop hook 會把 failure 自動顯示給使用者。orchestrator 接到後把錯誤完整貼給 Anon 重修。

## Memory propose confirm flow

當 Soyo 或 Anon 的輸出末尾含 `## Memory propose` 段時，orchestrator 在該 agent 完成後、繼續下一步前，立刻執行 confirm flow：

1. 檢查 propose 段的 6 個必填欄位（name / slug / description / body / type / rationale）是否齊全。
   缺任一欄位 → 不 confirm，印一行提示「偵測到 propose 段但格式不完整，已跳過」，繼續正常流程。
2. 顯示目前兩個 memory 來源的 index：
   - `~/.config/maigo/memory/MEMORY.md`（cross-project）
   - `~/.claude/projects/<current-project>/memory/MEMORY.md`（per-project，若存在）
3. 印出 propose 摘要（type / name / description / rationale）。
4. **AskUserQuestion**，選項：`存` / `修改` / `跳過`。
5. 選「存」或「修改」→ reuse [`/maigo:remember`](https://github.com/Lee-W/maigo/blob/main/commands/remember.md) 步驟 5+6
   （以 propose 的欄位為預填值；「修改」時步驟 5 讓使用者改各欄位）。
6. 選「跳過」→ 繼續正常流程，不寫任何檔。

Confirm flow 完成後繼續主線流程——不改變 fix 的步驟結構。

## Orchestrator 守則

- **不能跳過 Soyo**——quick-fix 砍的是 stage 數量（無 Raana / Tomori / 顯式 Taki），不是 review 本身
- **不能改 Soyo 的 4 項 subset 為更少**——這 4 項是硬底線
- **不能因為「使用者說 quick-fix」就放寬 must-fix 標準**——subset 內的項仍照 strict-review 規則
- **不要自己 review / 不要自己實作**——分別交給 Anon 與 Soyo Task
- 偵測 `## Memory propose` 標頭時，只掃描 code fence 外的行；
  code block 內（triple-backtick fence 之間）的同名標頭不觸發 confirm flow。
  追蹤法：從輸出文字開頭往下追蹤 triple-backtick 計數（奇數 → in-fence），遇到 `^## Memory propose` 且 in-fence 為 true 時跳過。

## 與 `/maigo:go` / `/maigo:team` 的差異

| 項目 | `/maigo:fix` | `/maigo:go` | `/maigo:team` |
|------|-------------|-------------|---------------|
| Raana 探索 | ❌ skip | ✅ | ✅ |
| Tomori plan | ❌ skip | ✅ | ✅ |
| Anon 實作 | ✅ | ✅ | ✅ |
| Soyo review | ✅ 輕量（4 項） | ✅ 完整（9 項） | ✅ 完整（9 項） |
| Taki 顯式 | ❌（stop hook 兜底） | ✅ | ✅（並行） |

→ 場景對照、其他命令：[Commands reference](https://github.com/Lee-W/maigo/blob/main/docs/reference/commands.md)
