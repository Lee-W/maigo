# Work Board — 學習閘門（§5）

Loaded on demand by [`skills/work-board/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md) §5 — checkbox → `--learn` → 記憶層的完整流程。
本檔內文原樣自 SKILL.md 搬出，章節編號（§1a、§3a 等）沿用原編號，SKILL.md 內仍以這些編號互相引用。

## 5. 學習閘門（checkbox → `--learn` → 記憶層）

使用者需求原文脈絡：打勾＝「我看過/我親自處理了」，maigo 去看**你實際怎麼處理的**，判斷要不要把這項知識學下來。

1. **勾**：使用者在任何編輯器把 `- [ ]` 改 `- [x]`（nvim 一鍵）。勾與分區正交。🐛/🔀 的勾跨刷新保留；
   👀 的勾代表「看完報告」（§4a），回你的球時會自動取消勾，但 `🔖` 會把學習訊號留下來。
   也可用 `/maigo:board --check <n...>`；要取消就用 `--uncheck`。這兩個命令只改
   checkbox（不寫 snapshot、不 ack，效果等同手勾，下次刷新才判斷），保留分區、整行內容與
   `🧠` / `🔖`，並且 idempotent。
2. **偵測**：`/maigo:board` 刷新時列出「(`[x]` 或 `🔖`) 且沒有 🧠」的項目，提示跑 `--learn`。刷新本身**不**
   自動進學習——學習有 AskUserQuestion 確認，不該混進快速刷新。
3. **抓料**（`--learn`，委派 sonnet，一項一隻或小批）：抓該 item 上**你的**實際輸出——
   review：你的 review comments / verdict；issue：你的 triage 回覆；你的 PR：你怎麼回 reviewer。
   對照 maigo 記憶層現有條目，蒸餾 0–3 條候選知識（「使用者在 X 類 PR 特別看 Y」「使用者回
   NEEDS_INFO 的口吻慣例是 Z」）。沒有可學的就回「無候選」，不硬湊。
4. **確認**：orchestrator 走既有
   [`memory-propose-confirm`](https://github.com/Lee-W/maigo/blob/main/skills/memory-propose-confirm/SKILL.md) skill，
   逐條 AskUserQuestion，確認的寫進 `~/.config/maigo/memory/`（type: feedback / project 按內容判）。
5. **標記**：處理完（含「無候選」）該行加 `🧠`、拿掉 `🔖`；之後刷新不再提示。反覆出現的知識日後由
   [`/maigo:crystallize`](https://github.com/Lee-W/maigo/blob/main/commands/crystallize.md) 畢業成 skill——學習閘門只負責進料，不重造管線。
