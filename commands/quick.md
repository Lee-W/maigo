---
description: 輕量任務入口。Anon 做小改動、Soyo 跑 4 項 checklist subset，再顯式執行驗證。支援沒有 lifecycle hooks 或 subagents 的環境。
---

<!-- mkdocs-include-start -->

# /maigo:quick

開始命令時先讀 [`skills/model-dispatch`](https://github.com/Lee-W/maigo/blob/main/skills/model-dispatch/SKILL.md)
並消費 `--model-profile <path>`；執行角色前依宿主能力解析派工，無 subagents 時依序執行。

「這個小東西改一下」級別的任務。跳過 Raana 探索 / Tomori 寫 plan 的 overhead，
orchestrator 直接呼叫 Anon 動手，做完跑 Soyo 輕量 review（9 項 → 4 項）。
測試由 orchestrator 顯式呼叫共用驗證 CLI，不需另外啟動 🟣 立希。

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
3. **Orchestrator 顯式驗證** — 🟡 爽世 APPROVED 後，依下節執行驗證 CLI，保存 command、cwd、exit code 與 output。修過檔案就重跑，不能沿用修改前的結果。
4. **Orchestrator** — 驗證 `passed` 後，若還有未 commit 的本次變更，依 [`skills/commit-message`](https://github.com/Lee-W/maigo/blob/main/skills/commit-message/SKILL.md) 草擬一段 commit message 附在 final summary。格式照該 skill 的偵測跑，**不預設 CC**——target repo 的成文慣例優先（例：apache/airflow 明禁 CC 前綴並有 commit-msg hook 擋）。**不自動跑 git commit**。接著依 [`skills/pr-sync-check`](https://github.com/Lee-W/maigo/blob/main/skills/pr-sync-check/SKILL.md) 核對當前 branch 若已開 PR，其 title/description 是否仍符合現在的實際改動；沒有對應 PR 就跳過，不算失敗。

### 顯式驗證契約（所有宿主共用）

先定位這份 command 所屬的 Maigo plugin root，將 `<maigo-root>` 換成它的絕對路徑；
`<project-cwd>` 是本次實作的 repo／worktree 絕對路徑。不要把 target repo 當成 plugin root。

```bash
python3 <maigo-root>/scripts/verify_task.py --cwd <project-cwd>
```

首次結果的 `run_id` / `task_id` 要隨本 work item 保存；修復後重試時傳
`--run-id <同一 run_id> --task-id <同一 task_id>`，新 work item 則取新範圍。
不要靠新建 ID 規避同一任務的重試上限。

可用 `--command '<實際測試指令>'` 指定任務需要的驗證；參數以 argv 解析，不執行 shell。
未指定時沿用 `.claude/test-command` 與既有 runner 偵測，設定格式見
[Hooks reference](../docs/reference/hooks.md#explicit-task-verification)。

| JSON status | CLI exit | 後續動作 |
|---|---|---|
| `passed` | 0 | 可進步驟 4；仍須 🟡 爽世 APPROVED |
| `failed` | 1 | 把實際 output 給 🎀 愛音修復，再 review／驗證 |
| `unavailable` | 2 | 回報缺少 runner、設定或環境；補齊後重跑，不宣稱驗證通過 |
| `skipped` | 3 | 附既有設定的 skip reason；標示未驗證 |
| `known_failures` | 4 | 附已知失敗與實際非零 exit code；不標示全綠 |

後兩者只能依使用者**已授權**的例外政策收尾；沒有對應授權時回報待決定，不能自行把狀態改成 `passed`。
若另需 lint、type check 或人工驗證，照 target repo 要求補跑；CLI 的 `passed` 只證明該次 command 成功。

沒有 subagents 時，由主 agent 依 🎀 愛音 → 🟡 爽世的順序執行，明示共用 context；
有 fresh context 能力時優先用獨立審查。可以只使用同一個模型，無須有商用升級檔位。
沒有 hooks 時，這是命令要求的顯式檢查，不能宣稱宿主已機器強制。
Claude Code 的 Stop hook 保留額外檢查，不能用「之後 hook 會跑」取代步驟 3。

## Soyo 輕量 checklist（9 項 → 4 項）

| 項 | 跑？ |
|---|------|
| 1. acceptance match | ✅ |
| 2. evidence per function | ❌ skip（步驟 3 顯式跑 test） |
| 3. edge case coverage | ❌ skip |
| 4. convention conformance | ✅ |
| 5. no unsafe pattern | ✅ |
| 6. no unexplained magic | ❌ skip |
| 7. no TODO evasion | ✅ |
| 8. no defensive bloat | ❌ skip |
| 9. no completeness theatre | ❌ skip |

合計 4 項：1 / 4 / 5 / 7。

orchestrator 啟動 🟡 Soyo 時 prompt 必須明示「mode=quick」與上述 subset。輸出 `## Checklist` 段，依序保留完整 9 項；subset 內項照常 `[x]` / `[ ]`，subset 外項標 `[—]` 附 reason `skipped by mode=quick`。

詳細「為什麼這 4 項」與「為什麼略掉那 5 項」見
[`skills/strict-review/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md)
的 "Adapting per context" 表。

## 失敗處理

### Soyo 擋下（NEEDS_CHANGES / BLOCKED）

跟 `/maigo:go` 同——把 must-fix 完整給 Anon、修完重 review、**2** 次同條才停下找使用者。
詳見 [`skills/failure-handling`](https://github.com/Lee-W/maigo/blob/main/skills/failure-handling/SKILL.md)。

### 顯式驗證失敗

orchestrator 讀取驗證 CLI 的 JSON status 與 output，依上述契約處理；失敗內容完整交給 🎀 愛音。

## Memory propose confirm flow

依 [`skills/memory-propose-confirm`](https://github.com/Lee-W/maigo/blob/main/skills/memory-propose-confirm/SKILL.md) 處理。Confirm flow 完成後繼續主線流程——不改變 quick 的步驟結構。

## Orchestrator 守則

- **旁白**：orchestrator 對使用者說話時戴上旁白的臉——開場、收場、卡關節點由 🌙 Doloris / 🌑 Mortis 旁白，依 [`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md)。
- **對話**：對話本體（旁白節點以外）的互動節奏與用詞，依 [`skills/orchestrator-voice`](https://github.com/Lee-W/maigo/blob/main/skills/orchestrator-voice/SKILL.md)。
- **不能跳過 Soyo**——quick-fix 砍的是 stage 數量（無 Raana / Tomori / 顯式 Taki），不是 review 本身
- **不能改 Soyo 的 4 項 subset 為更少**——這 4 項是硬底線
- **不能因為「使用者說 quick-fix」就放寬 must-fix 標準**——subset 內的項仍照 strict-review 規則
- **有 subagents 時分工**——實作與 review 分別交給 🎀 愛音與 🟡 爽世；無此能力時依顯式驗證契約執行 fallback
- fence tracking 與 `## Memory propose` 偵測規則依 [`skills/memory-propose-confirm`](https://github.com/Lee-W/maigo/blob/main/skills/memory-propose-confirm/SKILL.md)

## 與 `/maigo:go` / `/maigo:team` 的差異

| 項目 | `/maigo:quick` | `/maigo:go` | `/maigo:team` |
|------|-------------|-------------|---------------|
| Raana 探索 | ❌ skip | ✅ | ✅ |
| Tomori plan | ❌ skip | ✅ | ✅ |
| Anon 實作 | ✅ | ✅ | ✅ |
| Soyo review | ✅ 輕量（4 項） | ✅ 完整（9 項） | ✅ 完整（9 項） |
| 🟣 Taki 顯式 | ❌（orchestrator 顯式執行 CLI） | ✅ | ✅（並行） |

/maigo:go 與 /maigo:team 共用 [`skills/teammate-flow`](https://github.com/Lee-W/maigo/blob/main/skills/teammate-flow/SKILL.md)；/maigo:quick 採 🎀 愛音實作、🟡 爽世 subset 與 orchestrator 顯式驗證，所以獨立。

→ 場景對照、其他命令：[Commands reference](https://github.com/Lee-W/maigo/blob/main/docs/reference/commands.md)
