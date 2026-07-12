---
name: model-dispatch
description: This skill should be used when the maigo orchestrator, running in the Claude Code harness (Agent tool available for spawning subagents), decides which model tier to dispatch a subagent task to, or judges an escalation / de-escalation after a subagent's result. Scope note: 只在 Claude Code harness 下才適用——這裡的 Agent tool 支援逐次 `model` override；其他 harness（例如 Codex 的 command-router 環境）沒有這個能力，此 skill 不適用。
---

<!-- mkdocs-include-start -->

# Model Dispatch

**Owner**: orchestrator
**Consumers**: maigo orchestrator，在 Claude Code harness 下透過 Agent tool spawn subagent 時

只在 Claude Code harness 下適用——Agent tool 的 `model` 參數能讓 orchestrator 對每次
spawn 個別 override 檔位；沒有這個能力的 harness（例如 Codex 的 command-router 環境）
不適用本 skill，交辦一律走該 harness 原生的模型設定。

## 檔位政策

| 檔位 | 用途 |
|------|------|
| `haiku` | 機械批次：格式轉換、read-back、逐檔套用已定型的修法 |
| `sonnet` | 預設工作馬：搜尋、實作、重構、審查、研究——多數交辦都用這檔 |
| `opus` | 升級檔位：卡關救援、高風險判斷的第二意見 |

Orchestrator 本身執行所在的模型若高於以上三檔，只用在規劃、制度設計、品味判斷這類需要
「取捨」的工作——**不實作、不掃 repo、不批次改檔**。凡是可交辦的機械或搜尋工作，一律往
下派給對應檔位的 subagent，不因為自己在高檔位上就順手代勞。

## 升降級

- **haiku 錯 1 次** → 同任務升 `sonnet` 重派。
- **sonnet 同一子任務連錯 2 次** → 升 `opus`，且必須帶完整失敗軌跡（原始交辦 prompt、
  前兩次的輸出與錯誤原文）——不是重講一次題目給 opus 猜。
- **opus 解出模式後** → 降回 `sonnet` / `haiku` 批次套用到其餘案例。「解出模式」的判準：
  解法能寫成 ≤5 步、不需再做判斷、其他檔位可照抄執行的固定步驟；寫不成就還沒解出，
  不要降級。

## 重試預算

同一件事最多重試兩輪，計數明確定義：初次交辦不算重試；重試第 1 輪＝原檔位修一次；
重試第 2 輪＝升級後（`opus`）修一次。**opus 輪在兩輪預算之內**；opus 輪仍失敗即停手——
判斷是方向錯（換路）還是需要使用者輸入（去問），不再無聲重試第三輪。

## SendMessage 續用與換檔位

`SendMessage` 續用既有 agent 時**不能換 model**；要換檔位就開新 agent、附上前情
（原交辦內容＋已知結果），不能讓新 agent 從零猜任務背景。

## 不升檔的情況

Reviewer 已指定具體修法、且修法已機械化（可照抄執行、不需再判斷）時，續用原檔位即可——
不因為「上一輪出過錯」就自動升檔；升檔只在「同一子任務連錯」時觸發，不是每次失敗都升。

## 與既有 skill 的分工

「要不要派 subagent」與「派了之後怎麼交辦、怎麼防止 orchestrator 失焦」屬於
[`skills/harness-discipline`](https://github.com/Lee-W/maigo/blob/main/skills/harness-discipline/SKILL.md)
的範圍；本 skill 只管「派給哪個檔位」。兩者搭配使用：先用 harness-discipline 的門檻判斷
要不要派，再用本 skill 判斷派給誰。
