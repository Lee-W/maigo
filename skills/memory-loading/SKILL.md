---
name: memory-loading
description: This skill should be used by all maigo agents at startup, before beginning work, to load relevant cross-project memory entries with relevance-based ordering and a 10-entry cap. Consumers: Raana, Tomori, Soyo, and any future agent that reads ~/.config/maigo/memory/.
---

<!-- mkdocs-include-start -->

# Memory Loading

**Owner**: all agents
**Consumers**: [`agents/Raana.md`](https://github.com/Lee-W/maigo/blob/main/agents/Raana.md)、[`agents/Tomori.md`](https://github.com/Lee-W/maigo/blob/main/agents/Tomori.md)、[`agents/Soyo.md`](https://github.com/Lee-W/maigo/blob/main/agents/Soyo.md)

## 為什麼這個 skill 存在

三個 agent 在啟動時都要做相同的「讀記憶 → schema 自檢 → fallback」流程，但過去各自在 agent prompt 裡重複寫。這個 skill 是三者共通行為的 single source of truth。

## 標準 5 步流程

啟動後、正式開始工作之前，先載入跨專案記憶：

1. **`cat ~/.config/maigo/memory/MEMORY.md`** — 讀 index 全文
2. **讀 index 每行** `- [Title](file.md) — description`，判斷哪些 description 跟當前 task 的 keyword / 主題有 overlap
3. **相關性排序**：根據當前任務的關鍵字與 description 的匹配度進行排序
4. **限量載入**：若相關條目過多，僅 Read 最相關的前 10 筆 entry 全文，當作這次工作的 context
5. **在輸出開頭印 `## Loaded memory entries` 段**，列出用了哪些 entry

## Schema 自檢（lazy）

對每個讀進來的 entry frontmatter 做最小檢查：

- 缺 `name` / `description` / `type` 任一欄位
- `type` 值不在 `{user, feedback, project, reference}`

遇到問題**不 abort**，繼續使用該 entry（lenient），但在 `## Loaded memory entries` 段該行末尾加 `[schema warn: <缺什麼或 type 不合法>]`。

完整檢查可手動跑 [`python3 scripts/validate_memory.py`](https://github.com/Lee-W/maigo/blob/main/scripts/validate_memory.py)。

## Fallback 規則（不報錯、不抱怨、繼續做事）

- `~/.config/maigo/memory/` 不存在 → 當「沒記憶」處理
- `MEMORY.md` 不存在或是空的 → 當「沒記憶」處理
- index 裡完全沒有跟當前 task 相關的 entry → 當「沒記憶」處理

不要求使用者建立 memory 目錄或 index。

## 輸出格式範例

```
## Loaded memory entries
- [Integration test 偏好](integration-test-preference.md) — 已載入
- [Some entry](some-entry.md) — 已載入 [schema warn: 缺 type]
（若無相關 entry：「（無相關 entry）」）
```

## 客製延伸點

各 agent 在引用本 skill 後，可在自己的 prompt 內補充客製差異：

- **🩵 Tomori（Planner）**：若有相關 `project` 或 `user` entry，在 plan 開頭新增 `## Honoured memory` 段，把使用者偏好 / 慣例如何影響步驟安排寫出來——讓 fresh-context 的 🎀 Anon 透過讀 plan 就能間接拿到記憶，不必自己讀 MEMORY。詳見 `agents/Tomori.md`。
- **🟡 Soyo（Reviewer）**：對 `type: project` 的 entry 額外蒐集 `triggers` 欄位，把觸發的 skill 加進 review checklist。詳見 `agents/Soyo.md`。
- 其他 agent 若有額外需求，可在自己的 prompt 內說明，不修改本 skill。
