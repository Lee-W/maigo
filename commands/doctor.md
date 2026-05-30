---
description: 診斷 Maigo 環境與專案配置。檢查 gh CLI、記憶層目錄、以及 Taki (Verifier) 是否能跑。
---

<!-- mkdocs-include-start -->

# /maigo:doctor

> 「哪裡不舒服嗎。讓我看看。」 —— 🌑 Mortis

檢查 Maigo 運行所需的外部依賴與配置是否到位。

## 檢查項目

1. **環境依賴**：
   - `gh` CLI：是否安裝、是否已登入（用 `gh auth status`）。
   - `git`：是否可用。
   - `python3`：版本是否 ≥ 3.13。
2. **Maigo 配置**：
   - `~/.config/maigo/memory/`：目錄是否存在。
   - `MEMORY.md`：索引檔是否存在且格式正確。
3. **專案配置**：
   - `.claude/test-command`：是否有自定義測試指令。
   - `.claude/skip-test-verification`：是否被標記跳過。
   - **Taki 試跑**：嘗試偵測當前專案類型並跑一個最小化的檢查（例如 `ruff --version` 或嘗試跑一個不存在的 test 來確認 test runner 有反應）。

## 流程

1. **Orchestrator**：
   - 執行 `gh --version` 與 `gh auth status`。
   - 執行 `python3 --version`。
   - 檢查 `~/.config/maigo/memory/` 路徑。
2. **立希 (Taki)**：
   - 執行專案偵測。
   - 報告當前專案被識別為什麼類型。
   - 嘗試執行基本 lint/test 指令（dry-run 模式，不要求過，只要求「能跑」）。
3. **Orchestrator**：
   - 彙整報告。
   - 針對缺失項給予具體的「改進」建議（不使用「優化」）。

## 輸出格式

```markdown
# Maigo Doctor Report

## 🟢 環境 (Environment)
- [x] Python 3.13.0 — OK
- [ ] gh CLI — Not found or not logged in. (建議：安裝 gh 並跑 gh auth login)
- [x] git — OK

## 🟡 記憶 (Memory)
- [x] Directory: ~/.config/maigo/memory/ — OK
- [ ] Index: MEMORY.md — Not found. (建議：建立 MEMORY.md 以啟用跨專案記憶)

## 🔵 專案 (Project: <repo_name>)
- Detected type: <type>
- Verifier (Taki): <status>
- Test command: `<cmd>`

## 📢 建議
- ...
```

## Orchestrator 守則

- **旁白**：orchestrator 對使用者說話時戴上旁白的臉——開場、收場、卡關節點由 🌙 Doloris / 🌑 Mortis 旁白，依 [`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md)。
- **你（orchestrator）不要自己實作**。Taki 用 Task tool 啟動
- 報告最終由 orchestrator 彙整，不是 Taki 直接輸出
- 不論任何項目缺失，都要完整跑完所有檢查項目再彙整，不中途停止
- 完成後給使用者一份最終報告：環境狀態、缺失項清單、具體改進建議
