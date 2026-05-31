---
description: 輕量任務入口。Orchestrator 直接呼叫 Anon 做小改動，跳過 Raana / Tomori，Anon 做完跑輕量 Soyo（4 項 checklist subset）。Stop hook 自動兜底測試。
---

<!-- mkdocs-include-start -->

# /maigo:quick

「這個小東西改一下」級別的任務。跳過 Raana 探索 / Tomori 寫 plan 的 overhead，
orchestrator 直接呼叫 Anon 動手，做完跑 Soyo 輕量 review（9 項 → 4 項）。
Test 不顯式喊 Taki——stop hook 在任務完成前自動跑測試兜底。

## 使用

```
/maigo:quick <小任務描述>
```

例：

```
/maigo:quick 把 README 第三段的拼字 "occured" 改成 "occurred"
/maigo:quick 在 auth.py:42 加 type hint
```

## 邊界（trust user）

使用者說「這是 quick-fix」就是 quick-fix——orchestrator 不自動 gate（不偵測 LoC、不偵測 file 數）。

若使用者描述聽起來像大改動（多檔案、跨 module、看起來會牽動行為），orchestrator 在啟動前**一次**提醒：「這個看起來不像 quick-fix，要改用 `/maigo:go` 嗎？」使用者回「不用、就 quick」→ 照走 quick 流程，**不再追問**。

## 流程

1. **愛音 (Anon)** — 直接動手實作（無 Raana 探索、無 Tomori plan）。「嗯！先做 Step 1！」
   - Anon 自己看周邊 1-2 個檔抓慣例，不做大範圍探索
   - 不寫 plan.md
2. **爽世 (Soyo)** — 輕量 review，只跑 9 項中的 4 項。「這裡這樣寫，應該不對。」
3. **Stop hook 自動跑 test** — 不顯式呼叫 Taki
4. **Orchestrator** — Stop hook 綠後，若還有未 commit 的本次變更，依 [`skills/commit-message`](https://github.com/Lee-W/maigo/blob/main/skills/commit-message/SKILL.md) 草擬一段 commit message 附在 final summary。（本 repo 是 CC repo，draft 採 `type(scope): subject` 格式）**不自動跑 git commit**。

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

orchestrator 啟動 Soyo 時 prompt 必須明示「mode=quick」與上述 subset。Soyo 輸出 checklist 表時 subset 內項照常 `[x]` / `[ ]`，subset 外項標 `[—]` 附 reason `skipped by mode=quick`。

詳細「為什麼這 4 項」與「為什麼略掉那 5 項」見
[`skills/strict-review/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md)
的 "Adapting per context" 表。

## 失敗處理

### Soyo 擋下（NEEDS_CHANGES / BLOCKED）

跟 `/maigo:go` 同——把 must-fix 完整給 Anon、修完重 review、**2** 次同條才停下找使用者。
詳見 [`skills/failure-handling`](https://github.com/Lee-W/maigo/blob/main/skills/failure-handling/SKILL.md)。

### Stop hook 測試紅

stop hook 會把 failure 自動顯示給使用者。orchestrator 接到後把錯誤完整貼給 Anon 重修。

## Memory propose confirm flow

依 [`skills/memory-propose-confirm`](https://github.com/Lee-W/maigo/blob/main/skills/memory-propose-confirm/SKILL.md) 處理。Confirm flow 完成後繼續主線流程——不改變 quick 的步驟結構。

## Orchestrator 守則

- **旁白**：orchestrator 對使用者說話時戴上旁白的臉——開場、收場、卡關節點由 🌙 Doloris / 🌑 Mortis 旁白，依 [`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md)。
- **不能跳過 Soyo**——quick-fix 砍的是 stage 數量（無 Raana / Tomori / 顯式 Taki），不是 review 本身
- **不能改 Soyo 的 4 項 subset 為更少**——這 4 項是硬底線
- **不能因為「使用者說 quick-fix」就放寬 must-fix 標準**——subset 內的項仍照 strict-review 規則
- **不要自己 review / 不要自己實作**——分別交給 Anon 與 Soyo Task
- fence tracking 與 `## Memory propose` 偵測規則依 [`skills/memory-propose-confirm`](https://github.com/Lee-W/maigo/blob/main/skills/memory-propose-confirm/SKILL.md)

## 與 `/maigo:go` / `/maigo:team` 的差異

| 項目 | `/maigo:quick` | `/maigo:go` | `/maigo:team` |
|------|-------------|-------------|---------------|
| Raana 探索 | ❌ skip | ✅ | ✅ |
| Tomori plan | ❌ skip | ✅ | ✅ |
| Anon 實作 | ✅ | ✅ | ✅ |
| Soyo review | ✅ 輕量（4 項） | ✅ 完整（9 項） | ✅ 完整（9 項） |
| Taki 顯式 | ❌（stop hook 兜底） | ✅ | ✅（並行） |

/maigo:go 與 /maigo:team 共用 [`skills/teammate-flow`](https://github.com/Lee-W/maigo/blob/main/skills/teammate-flow/SKILL.md)；/maigo:quick 流程結構不同（無 Raana / Tomori、Soyo subset、Stop hook 兜底測試），所以獨立。

→ 場景對照、其他命令：[Commands reference](https://github.com/Lee-W/maigo/blob/main/docs/reference/commands.md)
