---
description: 列出 ~/.config/maigo/memory/ 目前的跨專案記憶。read-only。可選 type filter。
allowed-tools: Read, Bash(cat:*), Bash(ls:*), Bash(test:*)
---

<!-- mkdocs-include-start -->

# /maigo:memory

列出記憶層目前儲存的跨專案偏好 / 慣例 / 反饋。

**Orchestrator 親自跑，不開新 agent。**

## 使用

```
/maigo:memory             # 列全部
/maigo:memory project     # 只列 project type
/maigo:memory user        # 只列 user type
/maigo:memory feedback
/maigo:memory reference
```

## 流程

1. 檢查 `~/.config/maigo/memory/MEMORY.md` 是否存在。
   - 不存在 / 空 → 印友善訊息：「目前無跨專案記憶。要建立第一筆，用 `/maigo:remember <自然語言描述>`。」並結束。

2. 讀 `MEMORY.md`，解析每行 `- [<name>](<slug>.md) — <description>`。

3. 對每個 slug，讀 `~/.config/maigo/memory/<slug>.md` 的 YAML frontmatter，
   抽出 `name` / `type` / `description` / `triggers`（optional）。

4. 若使用者帶了 `<type>` 參數，filter 掉 type 不符的 entry。
   - `<type>` 不在 `{user, feedback, project, reference}` → 印「不支援的 type `<x>`，可用值：user / feedback / project / reference」並報錯結束（非 0 退出）。
   - filter 後 0 筆 → 印「（目前無 type=`<type>` 的記憶）」並正常結束（不視為錯誤）。

5. 以 markdown table 輸出：

   | Name | Type | Description | Triggers |
   |------|------|-------------|----------|
   | ...  | ...  | ...         | ...（無 triggers 留空） |

6. table 末尾印一行 footer：「共 N 筆。詳全文：`cat ~/.config/maigo/memory/<slug>.md`」

## Orchestrator 守則

- **旁白**：orchestrator 對使用者說話時戴上旁白的臉——開場、收場由 🌙 Doloris / 🌑 Mortis 旁白，依 [`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md)。
- **不寫任何檔**——read-only。
- **不 delegate 給任何 agent**。
- **parse frontmatter 失敗的 entry → 跳過**，印 warning「`<slug>.md` frontmatter 解析失敗，已跳過」，繼續處理其他 entry，不 crash。
- **filter 參數比對忽略大小寫**。

→ 完整 storage spec：[Memory reference](../docs/reference/memory.md)
