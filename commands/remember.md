---
description: 把使用者一句話的偏好 / 慣例 / 反饋，存進跨專案記憶層（~/.config/maigo/memory/）。orchestrator 推斷 type / name，AskUserQuestion 確認後寫檔。
---

<!-- mkdocs-include-start -->

# /maigo:remember

把「該被記得的事」從使用者腦袋移到共用的記憶層。

**Orchestrator 親自跑，不開新 agent。**

## 使用

```
/maigo:remember <自然語言描述>
```

例：

```
/maigo:remember 以後 review 要記得我偏好 integration test 而非 mock
/maigo:remember 我在所有專案的 commit message 都用 Conventional Commits
/maigo:remember 上次 Soyo 的 review 說明太長，希望更精簡
```

## 流程

Orchestrator 親自執行以下步驟（不 delegate 給 Tomori 或 Anon）：

1. 讀 input 自然語言

2. 推斷 `type`（`user` / `feedback` / `convention` / `reference` 之一）

   啟發式判斷：

   | 輸入特徵 | 推斷 type |
   |---------|---------|
   | 含「偏好」「習慣」「慣例」「以後都」 | `convention` |
   | 含「上次」「之前」「那次」「有人說」 | `feedback` |
   | 含 URL 或「文件」「參考」「spec」 | `reference` |
   | 含「我是」「我叫」「稱呼我」「語言」 | `user` |

   不確定 → 在 AskUserQuestion 列最可能的兩個，讓使用者選。

3. 生成 candidate `name`（短、可讀；例：「Integration test 偏好」）

4. 生成 candidate `slug`（lowercase + hyphen + ASCII only；例：`integration-test-preference`）

   - 確認 `~/.config/maigo/memory/<slug>.md` **不存在**
   - 若已存在 → 見下方「同 slug 已存在」處理

5. **AskUserQuestion**：

   - **共同三題（所有 type）**：
     - 確認或修改 **type**（列出推斷的 type 及理由）
     - 確認或修改 **name**
     - 要不要編輯 **body**？（預設 body = 從 input 提煉的一句話 + 原 input 當補充；使用者可直接接受或提供新版）

   - **第四題（僅 `type: convention`）**：
     - 要 tag triggered skills 嗎？（optional，list，例：`airflow-aware`、`commitizen-aware`）。預設空，直接 Enter 略過
     - 非空 → frontmatter 加 `triggers: [...]`；空 → 不加 `triggers` 欄位
     - 此欄位只對 `type: convention` 有效；其他 type 不詢問、不寫入

6. 使用者確認後：

   a. `mkdir -p ~/.config/maigo/memory/`

   b. 寫 `~/.config/maigo/memory/<slug>.md`：

      （`triggers` 行只在 `type: convention` 且使用者第四題回非空時加進 frontmatter）

      ```markdown
      ---
      name: <確認的 name>
      description: <一句話摘要>
      type: <確認的 type>
      ---

      <body 內容>
      ```

      若 `type: convention` 且使用者填了 triggers，在 `type:` 行後加一行：

      ```markdown
      triggers: [<skill-name>, ...]
      ```

   c. 更新 `~/.config/maigo/memory/MEMORY.md`：
      - 若不存在 → 建立，含一行說明 + 第一個 entry
      - 若已存在 → append 一行 `- [<name>](<slug>.md) — <description>`

   d. 回報使用者：寫了哪兩個檔、type、name、slug

## 失敗 / 中斷處理（rollback 規則）

- **使用者在 AskUserQuestion 階段打斷 / 取消**（包含第四題 triggered skills 詢問階段）：不寫任何檔（包含 MEMORY.md）；回報「未寫入，已取消」。

- **寫 entry 檔成功但更新 MEMORY.md 失敗**：把已寫的 entry 檔 unlink，回報失敗；不留半成品（atomic-ish）。

- **同 slug 已存在**：額外 AskUserQuestion，讓使用者三選一：
  1. 覆蓋現有 entry
  2. 重命名（提供新 slug）
  3. 取消

## Orchestrator 守則

- **旁白**：orchestrator 對使用者說話時戴上旁白的臉——開場、收場、卡關節點由 🌙 Doloris / 🌑 Mortis 旁白，依 [`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md)。
- **不要替使用者推斷後直接寫**——type / name 必須經過 AskUserQuestion 確認，使用者看到後同意才寫
- **不要把這條 delegate 給 Tomori 或 Anon**——這條命令是 orchestrator 自己跑（mirror Claude Code 內建 memory command 的設計）
- **不要碰 repo 內任何檔案**——這條命令只動 `~/.config/maigo/memory/`
- **不要在使用者確認前就開始寫檔**——確認 AskUserQuestion 收到「同意」回覆後才執行步驟 6

→ 完整 storage spec、types 說明、entry 範例：[Memory reference](../docs/reference/memory.md)
