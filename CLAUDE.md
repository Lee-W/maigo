# maigo contributor instructions for Claude Code agents

## Tone

This project is emoji-friendly. When working in this repository
(including meta-discussion about maigo's own design — skills,
commands, agents, docs), default to allowing emoji use where it
aids clarity or matches the project's voice:

- Agent identity markers — 🐱 樂奈 / 🩵 燈 / 🎀 愛音 / 🟡 爽世 / 🟣 立希
- Narrator markers — 🌙 Doloris / 🌑 Mortis (per [`skills/narration`](skills/narration/SKILL.md))
- Section / status markers in chat output where they aid scanning

The global Claude Code default "avoid emojis unless asked" does
not apply here — that default is overridden for this repository.

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
live in [`skills/narration`](skills/narration/SKILL.md).

## Hooks vs Skills boundary

- **`hooks/`** = 機器擋。Code-driven 強制檢查，agent 沒得繞過。例：🩵 Tomori 沒寫
  plan path → `teammate_quality_check.py` block；任務宣告完成沒跑 test →
  `verify_completion.py` block。
- **`skills/`** = 知識共享。Prompt-driven 共用 narrative / convention / workflow。
  被 commands / agents 用 markdown link 引用、合進 context。例：
  [`skills/strict-review`](skills/strict-review/SKILL.md)、[`skills/commit-message`](skills/commit-message/SKILL.md)、[`skills/narration`](skills/narration/SKILL.md)。

新增 enforcement 時的判斷：

- 「失敗應該擋下整個 turn」→ hook
- 「失敗只是品質下降、人可自決定要不要做」→ skill 段落
- 兩者都要：先 skill 寫清楚 narrative、hook 做最小 regex 兜底
