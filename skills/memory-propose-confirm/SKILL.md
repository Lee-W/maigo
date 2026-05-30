---
name: memory-propose-confirm
description: This skill should be used by the maigo orchestrator whenever a Soyo or Anon output contains a ## Memory propose section. Handles the 6-step confirm flow, fence-tracking rules for detecting the section, and parallel-mode timing adjustments. Applies to /maigo:go, /maigo:quick, /maigo:team.
---

<!-- mkdocs-include-start -->

# Memory Propose Confirm Flow

**Owner**: orchestrator
**Consumers**: [`/maigo:go`](https://github.com/Lee-W/maigo/blob/main/commands/go.md)、[`/maigo:quick`](https://github.com/Lee-W/maigo/blob/main/commands/quick.md)、[`/maigo:team`](https://github.com/Lee-W/maigo/blob/main/commands/team.md)

## 觸發條件

當 🟡 Soyo 或 🎀 Anon 的輸出末尾含 `## Memory propose` 段時，orchestrator 在該 agent 完成後、繼續下一步前，立刻執行 confirm flow。

## 6 步 Confirm Flow

1. **格式檢查**：檢查 propose 段的 6 個必填欄位（`name` / `slug` / `description` / `body` / `type` / `rationale`）是否齊全。
   缺任一欄位 → 不 confirm，印一行提示「偵測到 propose 段但格式不完整，已跳過」，繼續正常流程。
2. **顯示 index**：顯示目前兩個 memory 來源的 index：
   - `~/.config/maigo/memory/MEMORY.md`（cross-project）
   - `~/.claude/projects/<current-project>/memory/MEMORY.md`（per-project，若存在）
3. **印出摘要**：印出 propose 摘要（type / name / description / rationale）。
4. **AskUserQuestion**，選項：`存` / `修改` / `跳過`。
5. 選「存」或「修改」→ reuse [`/maigo:remember`](https://github.com/Lee-W/maigo/blob/main/commands/remember.md) 步驟 5+6
   （以 propose 的欄位為預填值；「修改」時步驟 5 讓使用者改各欄位）。
6. 選「跳過」→ 繼續正常流程，不寫任何檔。

Confirm flow 完成後繼續主線流程——不改變命令的步驟結構。

## Fence-Tracking 規則

偵測 `## Memory propose` 標頭時，**只掃描 code fence 外的行**；code block 內（triple-backtick fence 之間）的同名標頭不觸發 confirm flow。

追蹤法：從輸出文字開頭往下追蹤 triple-backtick 計數（奇數 → in-fence），遇到 `^## Memory propose` 且 in-fence 為 true 時跳過。

## 並行模式追加

在 `/maigo:team` 的並行場景（🟡 Soyo 和 🟣 Taki 並行）下：若 Soyo 輸出含 `## Memory propose`，等**兩邊都回來後**再跑 confirm flow，不要插在 Taki 還在執行中間。
