# Hooks Reference

Maigo 註冊兩個 hook，定義在 `hooks/hooks.json`。
只要 plugin 載入就自動生效，使用者不用設定。

## TeammateIdle — `hooks/teammate_quality_check.py`

agent 跑完輸出送回 orchestrator 時觸發。
檢查輸出符合該角色的最低規格，不符合就 block 並要求補完。

### 各角色擋的條件

| Agent | 必須包含 | 違反時的 block message |
|-------|---------|----------------------|
| **Raana** | `## Loaded memory entries` 段（即使無相關 entry 也要明寫「（無相關 entry）」）| 「缺 memory 載入回報」 |
| **Tomori** | `## Loaded memory entries` 段 | 「缺 memory 載入回報」 |
| **Tomori** | 提到 `/tmp/maigo/<repo>/plan.md` 或 `/tmp/maigo/<repo>/review-rubric.md` 路徑 | 「沒提到計畫檔路徑」 |
| **Tomori** | 結構段落：`## Goal` / `## Steps` / `## Rubric` / `## Acceptance` / `## 目標` / `## 步驟` 之一 | 「缺計畫結構」 |
| **Soyo** | `## Loaded memory entries` 段 | 「缺 memory 載入回報」 |
| **Soyo** | verdict 字串：`APPROVED` / `NEEDS_CHANGES` / `BLOCKED` | 「沒下 verdict」 |
| **Soyo** | checklist 項目：`[x]` / `[X]` / `[ ]` | 「沒 checklist」 |
| **Soyo** | 非 APPROVED 時：`must-fix` / `改法` / `evidence` / `待補` 之一 | 「擋下卻沒列 must-fix」 |
| **Taki** | `exit <number>` 模式 | 「沒貼 exit code」 |
| **Taki** | `PASS` 或 `FAIL` 之一 | 「沒給最終 verdict」 |
| **Taki** | **不能包含** `should work` / `looks good` / `應該可以` / `看起來沒問題` 等 hedge 語 | 「verifier 只能拿 exit code 講話」 |

### 不檢查的角色

- **Anon** — implementer 透過 plan 取得 context、不直接讀記憶；輸出規格較鬆，預設通過
- 不在已知名單的角色 → 預設通過

### Fail-open 情況

- malformed input（沒 `teammate_role` 或 `teammate_output`）→ approve
- input 不是有效 JSON → approve

### Timeout

30 秒上限。hook 只做 regex match，理論上毫秒級完成；30 秒為保護性上限，不應在正常情況被觸發。

### 加新規格

編輯 `hooks/teammate_quality_check.py`，在 `ROLE_HANDLERS` 字典加一個新 mapping，
並寫對應的 `check_<role>` 函式。每個 handler 都要呼叫 `emit("block", ...)` 或 `emit("approve", ...)`。

## Stop — `hooks/verify_completion.py`

任務宣告完成前觸發。即使 orchestrator 想跳過 Taki 也擋下。

### 偵測順序

| 偵測到 | 跑什麼指令 |
|--------|----------|
| `uv.lock` | `uv run pytest` |
| `pyproject.toml` 或 `setup.py` + `tests/` 或 `test/` 目錄 | `pytest` |
| `package.json` 內 `scripts.test` 存在 | `npm test --silent` |
| `Cargo.toml` | `cargo test --quiet` |
| `go.mod` | `go test ./...` |
| 都沒有 | 跳過（no-op approve） |

### 設定檔（放在 user 專案的 `.claude/` 下）

| 檔案 | 行為 |
|------|------|
| `skip-test-verification` | 第一行非空非註解視為原因，整個檢查跳過 |
| `test-command` | 完全覆寫 test 指令（用 `shlex.split` 解析，支援引號） |
| `known-test-failures` | 已知失敗名單（一行一個），不擋這些；只擋「新的」失敗 |

### Fatal markers

偵測到 `\bImportError:` / `\bModuleNotFoundError:` / `\bSyntaxError:`（必須有冒號，
避免誤判 test 名稱裡的字串）→ 視為 collection 錯，比 test 失敗更優先擋下，
message 強調「這不是 test fail，是 import 錯」。

### 抓 failure 名稱的 regex

| 框架 | 模式 |
|------|------|
| pytest | `FAILED <name>` 或 `<file>::<test> FAILED` |
| jest | `FAIL <file>.test.[jt]sx?` |
| cargo test | `test <name> ... FAILED` |
| go test | `--- FAIL: <name>` |

抓不出名稱但 exit 非 0 → 仍 block，附最後 500 chars 原始 output。

### Timeout

預設 90 秒（hook 自身 timeout 120 秒，留 30 秒 buffer）。
編輯 `TEST_TIMEOUT_SEC` 常數可調。

### Fail-open 情況

- 偵測不到任何專案類型（沒有 `uv.lock` / `pyproject.toml` / `package.json` / `Cargo.toml` / `go.mod`）→ approve（no-op）
- `.claude/skip-test-verification` 存在 → approve 並記錄原因
- stdin JSON 解析失敗或無 `cwd` 欄位 → fallback 到 `os.getcwd()`，照常嘗試偵測；如果偵測不到還是會 no-op approve

## 觀察 hook 行為

要看 hook 真的有跑、回傳什麼：

```bash
# 模擬 TeammateIdle 觸發
python3 -c "import json,sys; print(json.dumps({'teammate_role':'Soyo','teammate_output':'## Verdict\nBLOCKED\n## Checklist\n- [ ] foo'}))" \
  | python3 hooks/teammate_quality_check.py

# 模擬 Stop 觸發
python3 -c "import json,sys; print(json.dumps({'cwd':'/path/to/project'}))" \
  | python3 hooks/verify_completion.py
```
