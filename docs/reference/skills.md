# Skills Reference

Skill 是跨 agent / command 引用的共用流程模組。內容寫一次、多處引用，
比塞進每個 agent 的長 prompt 更不容易被「自動省略」。

每個 skill 一個目錄：`skills/<name>/SKILL.md`。
Source-of-truth 是 `skills/*/SKILL.md` 本身；本頁只是 catalog。

## 為什麼用 skill 而不是直接寫進 agent

不用 skill 的寫法：

```
agents/Soyo.md (200 行：包含 checklist + 評審原則 + 輸出格式 + ...)
agents/Soyo 被呼叫 → 整份 prompt 送進 context → 細節容易被 LLM 自動「跳過」
```

用 skill 的寫法：

```
agents/Soyo.md (40 行：人設 + 引用 skills/strict-review)
skills/strict-review/SKILL.md (140 行：完整 checklist + 原則 + 格式)
agent 收到指引時，skill 內容會 on-demand 被拉進來，而且訊號明確（標題「Strict Review」會引導注意力）
```

額外好處：
- 一處更新（改 checklist 不用同步多個 agent prompt）
- 多個 consumer 共用（`/maigo:go` 和 `/maigo:review` 都用 Soyo + strict-review）
- 跟 agent 個性解耦（換個 reviewer 角色也能套同個 skill）

## Skill catalog

| Skill | Owner agent | Consumers | 摘要 |
|-------|-------------|-----------|------|
| [`strict-review`](../../skills/strict-review/SKILL.md) | Soyo | `/maigo:go` step 5、`/maigo:review` step 3 | 預設 BLOCKED + 9 項 checklist + evidence-driven |

## skill 檔案規格

```yaml
---
name: <skill-name>           # 必填，需與目錄名一致
description: This skill should be used when ...    # 必填
---

# <Title>

## Overview / 為什麼這個 skill 存在
...

## 主要內容
...
```

`description` 欄位很重要——Claude 在判斷該不該拉某個 skill 進來時讀的就是這欄。
寫成 `This skill should be used when ...` 模式比較容易被正確匹配。

## 加新 skill 的 checklist

1. `mkdir skills/<new-name>/`
2. 寫 `skills/<new-name>/SKILL.md`（記得 frontmatter `name` 跟目錄名一樣）
3. 在 owner agent 的 prompt 加引用：「process 依 `skills/<new-name>/SKILL.md`」
4. 在這份 catalog 加一列
5. 跑 `python3 scripts/validate_plugin.py` 確認 cross-ref 通
