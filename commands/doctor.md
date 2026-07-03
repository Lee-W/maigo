---
description: 診斷 Maigo 環境與專案配置。檢查 gh CLI、記憶層目錄、Taki (Verifier) 是否能跑、以及 retry / failure log 統計（哪個環節最常卡）。
allowed-tools: Bash(gh --version:*), Bash(gh auth status:*), Bash(python3:*), Bash(git --version:*), Bash(ls:*), Bash(test:*), Bash(cat:*), Read, Task
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
4. **Retry / failure 統計**（read-only，只讀不清）：讀 `.maigo/soyo-must-fix.jsonl`
   （🟡 爽世 must-fix 觸發，`teammate_quality_check.py` 寫入）與 `.maigo/test-failures.jsonl`
   （🟣 立希 test failure 觸發，`verify_completion.py` 寫入），彙整各 key 的觸發次數 + 最近
   3 筆摘要。**兩個 log 都是相對當前 repo 的 `.maigo/` 底下**，不存在或是空的 → 印正常訊息
   （新環境 / 還沒觸發過 retry 本來就不該有），不算 error。

## 流程

1. **Orchestrator**：
   - 執行 `gh --version` 與 `gh auth status`。
   - 執行 `python3 --version`。
   - 檢查 `~/.config/maigo/memory/` 路徑。
2. **立希 (Taki)**：
   - 執行專案偵測。
   - 報告當前專案被識別為什麼類型。
   - 嘗試執行基本 lint/test 指令（dry-run 模式，不要求過，只要求「能跑」）。
3. **Orchestrator**：讀 retry / failure log，彙整統計（不存在 / 空 → 印正常訊息，不中止）：

```bash
python3 - <<'PY'
import json, collections, pathlib

SOURCES = {
    ".maigo/soyo-must-fix.jsonl": "must_fix_keys",
    ".maigo/test-failures.jsonl": "failures",
}
for path, field in SOURCES.items():
    p = pathlib.Path(path)
    entries = []
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    if not entries:
        print(f"{path}: 無紀錄（正常，尚未觸發過 retry）")
        continue
    counts = collections.Counter(k for e in entries for k in e.get(field, []))
    print(f"{path}（{len(entries)} 筆）：" + ", ".join(f"{k}×{c}" for k, c in counts.most_common()))
    for e in entries[-3:]:
        print(f"  最近：{e.get('ts')} — {e.get(field)}")
PY
```

4. **Orchestrator**：
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

## 🔁 Retry / Failure 統計
- `.maigo/soyo-must-fix.jsonl`：<N 筆，或「無紀錄（正常）」> — <key×次數 摘要>
- `.maigo/test-failures.jsonl`：<N 筆，或「無紀錄（正常）」> — <key×次數 摘要>
- 最近 3 筆：<ts — key>

## 📢 建議
- ...
```

## Orchestrator 守則

- **旁白**：orchestrator 對使用者說話時戴上旁白的臉——開場、收場、卡關節點由 🌙 Doloris / 🌑 Mortis 旁白，依 [`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md)。
- **你（orchestrator）不要自己實作**。Taki 用 Task tool 啟動
- 報告最終由 orchestrator 彙整，不是 Taki 直接輸出
- 不論任何項目缺失，都要完整跑完所有檢查項目再彙整，不中途停止
- 完成後給使用者一份最終報告：環境狀態、缺失項清單、具體改進建議
