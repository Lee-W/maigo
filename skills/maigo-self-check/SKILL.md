---
name: maigo-self-check
description: This skill should be used when a maigo diff touches agents/, commands/, skills/ (including SKILL.md and references/), mkdocs.yml, or docs/ — in those cases validate_plugin + mkdocs --strict are the verification standard, not just pytest.
---

<!-- mkdocs-include-start -->

# Maigo Self-Check

**Owner**: Taki (Verifier)
**Consumers**: `/maigo:go`, `/maigo:quick`, `/maigo:team`, `/maigo:crystallize`

## 觸發條件

diff 動到以下任一路徑時啟用本 skill：

- `agents/`
- `commands/`
- `skills/`（含 `SKILL.md` 與 `references/` 子目錄）
- `mkdocs.yml`
- `docs/`

純動 Python source（`hooks/`、`scripts/`、`tests/`）→ 只跑 pytest，不觸發本 skill。
兩者都動（如同時改 `scripts/` 與 `docs/`）→ pytest + 本 skill 兩條都跑。

## 驗證指令

```
python3 scripts/validate_plugin.py
uv run mkdocs build --strict
```

**為什麼分開用不同執行器**：

- `python3 scripts/validate_plugin.py` — `validate_plugin.py` 只用 stdlib，不需要
  venv 套件；遵守 maigo 慣例「stdlib-only script 用 `python3`」。
- `uv run mkdocs build --strict` — mkdocs 是 venv 工具（在 `pyproject.toml` 的
  dev dependency 裡）；遵守「venv 工具用 `uv run`」。

## 這兩條抓的是 pytest 抓不到的東西

| 問題類型 | 被哪條抓到 |
|---------|-----------|
| include shim 缺失（`docs/skills/<name>.md` 沒建） | `validate_plugin.py` |
| frontmatter `name` 對不上目錄名 | `validate_plugin.py` |
| skill catalog（`docs/reference/skills.md`）漏列 | `validate_plugin.py` |
| mermaid 相依圖缺 skill 節點 | `validate_plugin.py` |
| 相對 link 在 include-markdown rewrite 後炸 strict-mode | `mkdocs build --strict` |
| docs nav 指到不存在的 page | `mkdocs build --strict` |

pytest 測的是 Python 行為；上述問題都在 plugin 結構層——pytest 對它們是盲的。

## 兩條都必須綠才算完成

任何一條紅 → 驗證未通過，不算 Taki PASS。回報實際錯誤，不跳過、不假裝綠。
