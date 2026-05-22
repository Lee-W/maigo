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
agents/Soyo.md：人設 + 引用 skills/strict-review（保持短，只放角色）
skills/strict-review/SKILL.md：完整 checklist + 原則 + 格式
agent 收到指引時，skill 內容會 on-demand 被拉進來，訊號明確（標題「Strict Review」引導注意力）
```

額外好處：
- 一處更新（改 checklist 不用同步多個 agent prompt）
- 多個 consumer 共用（`/maigo:go` 和 `/maigo:review` 都用 Soyo + strict-review）
- 跟 agent 個性解耦（換個 reviewer 角色也能套同個 skill）

## Skill catalog

| Skill | Owner agent | Consumers | 摘要 |
|-------|-------------|-----------|------|
| [`strict-review`](../skills/strict-review.md) | Soyo | `/maigo:go` step 5、`/maigo:review` step 3 | 預設 BLOCKED + 9 項 checklist + evidence-driven |
| [`airflow-aware`](../skills/airflow-aware.md) | — (知識層) | 任何 skill（在 apache-airflow contributor checkout 時由 repo-detect hook 自動載入） | Airflow contributor 慣例：命名（Dag/DAG）、Breeze/uv 環境、Ruff/Mypy 風格、coding rules、pytest patterns、PR hygiene |
| [`commitizen-aware`](../skills/commitizen-aware.md) | — (知識層) | 任何 skill（在 commitizen-tools/commitizen contributor checkout 時由 repo-detect hook 自動載入） | commitizen contributor 慣例：uv + poe 任務、Conventional Commits 自舉、ruff/mypy lint、pytest、PR guidelines |
| [`commit-message`](../skills/commit-message.md) | — (orchestrator 直跑) | `/maigo:go` step 7、`/maigo:fix` step 4、`/maigo:team` step 7 | 從 diff 草擬 user-impact subject + 短 body 的 commit message，避免把 PR motivation 倒進 commit log |
| [`github-title-description`](../skills/github-title-description.md) | — (orchestrator 直跑) | `/maigo:describe-pr` | 從 branch commits / diff 產 user-impact PR title + Summary / Motivation / Test plan |
| [`pr-context-cache`](../skills/pr-context-cache.md) | Raana | `/maigo:review` step 1 | 把 PR title/body/diff/CI status/linked issues cache 到 review-rubric.md，re-review 時跳過重抓 |

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

## Memory-triggered skill 載入

skill 也可以被 memory entry 觸發載入——不需要在 agent prompt 裡直接引用。

機制：`type: convention` 的 entry 可在 frontmatter 加 `triggers: [<skill-name>]` 欄位。
Soyo 在跨專案記憶 v1.1 之後支援此機制：載入 convention entry 時，
對每個 triggered skill name 嘗試讀 `skills/<name>/SKILL.md`，
存在就附加為 base 9 項 checklist 之後的 item 10+；
不存在 → log「triggered skill `<name>` 找不到，忽略」，不 crash。

**注意**：只有 `type: convention` 的 entry 適用 `triggers`——
`user` / `feedback` / `reference` type 的 triggers 欄位會被無聲忽略。

詳見 [`memory.md` frontmatter schema](memory.md#entry-frontmatter-schema) 與
[`strict-review/SKILL.md` Domain skill composition 段](../skills/strict-review.md#domain-skill-composition)。

## Add New Skill Checklist

1. `mkdir skills/<new-name>/`
2. 寫 `skills/<new-name>/SKILL.md`（記得 frontmatter `name` 跟目錄名一樣）
3. 在 owner agent 的 prompt 加引用：「process 依 `skills/<new-name>/SKILL.md`」
4. 在這份 catalog 加一列
5. 跑 `python3 scripts/validate_plugin.py` 確認 cross-ref 通
