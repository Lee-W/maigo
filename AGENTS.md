# maigo contributor instructions for Codex agents

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

- **`hooks/`** = machine-enforced checks, but only inside a **Claude Code**
  session — Claude Code's harness runs the scripts under `hooks/` and blocks
  the turn automatically. Example: 🩵 Tomori 沒寫 plan path →
  `teammate_quality_check.py` block；任務宣告完成沒跑 test →
  `verify_completion.py` block.
  **Codex has no equivalent hook runtime.** When working as a Codex agent,
  nothing will stop you from skipping what these scripts check — treat each
  hook script's logic as a required manual step (read it, or run it directly
  with `python3 hooks/<script>.py` where that's meaningful) rather than
  something the environment enforces for you.
- **`skills/`** = 知識共享。Prompt-driven 共用 narrative / convention /
  workflow，靠 command / agent 定義檔用 markdown link 引用進 context 才生效
  ——這點在 Claude Code 與 Codex 都一樣，都是「讀了才知道」，不是機器強制。例：
  [`skills/strict-review`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/SKILL.md)、
  [`skills/commit-message`](https://github.com/Lee-W/maigo/blob/main/skills/commit-message/SKILL.md)、
  [`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md)。

新增 enforcement 時的判斷：

- 「失敗應該擋下整個 turn」→ hook（Claude Code 專屬機制；Codex 端沒有等價
  runtime，只能靠 agent 自律照做）
- 「失敗只是品質下降、人可自決定要不要做」→ skill 段落
- 兩者都要：先 skill 寫清楚 narrative、hook 做最小 regex 兜底（Codex 這半邊
  沒有 hook 兜底，全靠讀過 skill 之後自律）

## Verification quirks

- **ruff 只能經 pre-commit 跑**：`uv run ruff` 會 `Failed to spawn`；改用
  `uv run pre-commit run --files <files>`。注意 `--all-files` 不掃 untracked 檔，
  新增檔案要明確列進 `--files`。
- **工具邊界**：venv 工具（`pytest` / `mkdocs` / `pre-commit`）一律用 `uv run` 執行；
  `hooks/` 底下的腳本與 stdlib-only script 用 `python3` 直接執行，不經 `uv run`。
- **Version bump 由 CI 執行**：`cz bump` 是 CI 的職責，不屬於任何 plan / 任務步驟 /
  open question——規劃或交辦時不得把手動 bump 列為待辦項目。
- **`scripts/board_serve.py` 的 `V{N}_CSS_SHA256` 常數必須用程式算，不可手填**：每次
  scaffold CSS 版本升級（bump `SCAFFOLD_VERSION`）都要新增一個對應舊版本的 hash 常數，
  用來判斷使用者的 `_serve/board-style.css` 是不是原封不動、可以安全升級。這個常數**必須**
  用 `hashlib.sha256(舊版 CSS_TEMPLATE.encode()).hexdigest()` 程式算出來（例如
  `git show <改動前 commit>:scripts/board_serve.py` 取出舊內容再算），不能手填或憑印象——
  算錯會讓所有真實使用者的舊版 CSS 被誤判成「使用者自訂過」，永遠拿不到升級，且不會有任何
  測試失敗提醒你（除非你也補了對應測試）。每次新增常數都要比照 `tests/test_board_serve.py`
  既有的 `test_upgrades_unmodified_v*_css_to_current` / `test_preserves_genuinely_modified_v*_css`
  補一對回歸測試，並把舊版 CSS 存成 `tests/fixtures/board_serve_v*.css` fixture 釘住實際內容。
