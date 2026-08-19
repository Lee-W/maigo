# maigo contributor instructions for Codex agents

> **鏡射檔同步**：`CLAUDE.md` 與 `AGENTS.md` 共用下列 contributor conventions。
> 修改共同規則時必須同步另一份；平台特定措辭、連結格式與 hook runtime 說明可保留差異，
> 否則另一端會照舊快照做事。

## Tone

This project is emoji-friendly. When working in this repository
(including meta-discussion about maigo's own design — skills,
commands, agents, docs), default to allowing emoji use where it
aids clarity or matches the project's voice:

- Agent identity markers — 🐱 樂奈 / 🩵 燈 / 🎀 愛音 / 🟡 爽世 / 🟣 立希
- Narrator markers — 🌙 Doloris / 🌑 Mortis (per [`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md))
- Section / status markers in chat output where they aid scanning

Default assistant behavior that avoids emoji unless asked does not
apply here — the emoji markers below are project convention, not
decoration, and should be used where they aid clarity.

This applies to *prose, chat output, and contributor-facing docs* in
this repo. Source code (Python, YAML config, etc.) follows its own
conventions — do not sprinkle emojis into code where they don't
already belong.

### Agent & narrator emoji — quick-ref (always in context)

**Every mention** of an agent or narrator name in prose, summaries, and chat output
must carry the emoji prefix — not just the line where they speak.

| Role | Emoji | Names |
|------|-------|-------|
| 樂奈 | 🐱 | Raana |
| 燈 | 🩵 | Tomori |
| 愛音 | 🎀 | Anon |
| 爽世 | 🟡 | Soyo |
| 立希 | 🟣 | Taki |
| Doloris | 🌙 | — |
| Mortis | 🌑 | — |

**Not applicable**: content inside code blocks, file paths
(`agents/Soyo.md`), commit messages, and direct quotes from the user.

Full narration rules (when to use Doloris vs Mortis, voice tone, etc.)
live in [`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md).

## Hooks vs Skills boundary

- **`hooks/`** = machine-enforced checks inside a **Claude Code** session —
  Claude Code's harness runs the scripts under `hooks/` and blocks the turn
  automatically. Example: 🩵 Tomori 沒寫 plan path →
  `teammate_quality_check.py` block；任務宣告完成沒跑 test →
  `verify_completion.py` block.
  **Codex 也有 lifecycle hook runtime，但 Maigo 的 Codex manifest 會用空的
  inline hooks 覆蓋這組 Claude Code 專用 hooks**：兩端支援的事件與 I/O schema
  不完全相同，直接共用會讓 Codex 把 Claude Code 的合法輸出判成錯誤。Codex command
  會顯式執行 review / verification；其餘 hook 邏輯仍視為必要的手動步驟（閱讀，或在
  適用時直接執行 `python3 hooks/<script>.py`），不依賴環境自動攔截。
- **`skills/`** = 知識共享。Prompt-driven 共用 narrative / convention /
  workflow，靠 command / agent 定義檔用 markdown link 引用進 context 才生效
  ——這點在 Claude Code 與 Codex 都一樣，都是「讀了才知道」，不是機器強制。例：
  [`skills/strict-review`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md)、
  [`skills/commit-message`](https://github.com/Lee-W/maigo/blob/main/skills/commit-message/SKILL.md)、
  [`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md)。

新增 enforcement 時的判斷：

- 「失敗應該擋下整個 turn」→ hook（Claude Code 由 runtime 強制；Codex manifest
  刻意不載入這組 Claude Code hooks，改由 command 顯式執行或 agent 手動照做）
- 「失敗只是品質下降、人可自決定要不要做」→ skill 段落
- 兩者都要：先 skill 寫清楚 narrative、hook 做最小 regex 兜底（Claude Code）；
  Codex command 則需顯式涵蓋同一檢查，否則靠讀過 skill 之後自律

## Verification quirks

- **ruff 只能經 pre-commit 跑**：`uv run ruff` 會 `Failed to spawn`；改用
  `uv run pre-commit run --files <files>`。注意 `--all-files` 不掃 untracked 檔，
  新增檔案要明確列進 `--files`。
- **工具邊界**：venv 工具（`pytest` / `mkdocs` / `pre-commit`）與要求專案 Python 的
  `scripts/validate_plugin.py` 一律用 `uv run` 執行；`hooks/` 底下的 runtime script
  與其他 standalone stdlib-only script 用 `python3` 直接執行。
- **改完 `commands/` 或 `skills/` 要開新 session 才驗得到**：命令與 skill 定義在
  session 開場就被快照，同一個 session 內跑 `/maigo:*` 載到的仍是**改動前**的版本。
  在原 session 裡「試跑看看」等於在驗舊快照——會誤判成「改動沒生效」，更糟的是
  誤以為驗過了。要實際驗證命令流程的改動，開新 session；同 session 內只能驗
  底層 script（`scripts/*.py` 是執行時才讀，不受快照影響）。
- **Version bump 由 CI 執行**：`cz bump` 是 CI 的職責，不屬於任何 plan / 任務步驟 /
  open question——規劃或交辦時不得把手動 bump 列為待辦項目。
