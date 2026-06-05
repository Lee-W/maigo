# Hooks Reference

Maigo 註冊三個 hook，定義在 `hooks/hooks.json`。
只要 plugin 載入就自動生效，使用者不用設定。

## SessionStart — `hooks/repo_detect.py`

session 開啟時觸發。偵測目前 repo 是否命中已知 project，若命中就 emit
systemMessage 要求 agent 載入對應的 project-aware skill；未命中則 silent
approve。讓 contributor 進到熟悉的 codebase 時，自動拿到該 repo 的慣例知識
（命名、測試模式、PR 規範等），不用使用者手動引用。

### 偵測流程

1. 讀 stdin JSON 取 `cwd`（缺欄位 → fallback `os.getcwd()`）
2. **確保 `.maigo/` 被 git 忽略**（`ensure_maigo_ignored`，見下）
3. 對 `REPO_RULES` 內每個 rule，依序跑其 `detectors`
4. **任一** detector 命中即視為 rule 命中（OR 邏輯）
5. 命中 → emit `approve` + systemMessage（要求載入 `skills/<skill>/SKILL.md`）
6. 全部未命中 → emit `approve` + 空 systemMessage（silent）

### 目前 registry

| Project | Skill | Detector 條件 |
|---------|-------|--------------|
| `apache-airflow` | `airflow-aware` | git remote 含 `apache/airflow`，**或** `airflow/__init__.py` 存在且 `airflow/models/dag.py` / `airflow/dag.py` 至少有一個 |
| `commitizen-tools-commitizen` | `commitizen-aware` | git remote 含 `commitizen-tools/commitizen`，**或** `commitizen/__init__.py` 存在且 `commitizen/cli.py` / `commitizen/commands/__init__.py` / `commitizen/bump.py` 至少有一個 |

### `ensure_maigo_ignored`

不分 project，每次 SessionStart 都跑（在 rule 偵測之前）。maigo 的所有 command
（go / quick / team / review / address-comments）都把 plan、review rubric、
pr-comments、retry log 等 artefact 寫進 repo root 的 `.maigo/`，這些絕不該被
commit。

為了不動到 host repo 被追蹤的 `.gitignore`（例如 apache/airflow 的 `.gitignore`
是上游檔案），hook 改寫該 repo 的 `info/exclude`——路徑用
`git rev-parse --git-path info/exclude` 解析，所以在 linked worktree 下也會落到
共用 git dir、一次涵蓋所有 worktree。

特性：

- **冪等**：`.maigo/` 已被任何機制忽略（global excludesfile、被追蹤的
  `.gitignore`、或前次寫入的 exclude）→ 不重複寫；entry 已在 exclude 裡 → 跳過。
- **fail-open**：非 git repo、git 不存在、timeout 或任何 OS error → 靜默略過，
  不影響 session 啟動。

### `claude_config_seeds`

Rule dict 的可選欄位。偵測命中時，hook 在 user project 的 `.claude/` 目錄 **write-once** 寫入指定檔案——若檔案已存在（使用者手動編輯過、或前次 session 已寫入）則跳過，永遠不覆寫。

```python
"claude_config_seeds": {
    "skip-test-verification": "...",   # key = 檔案名；value = 初始內容
}
```

目前只有 `apache-airflow` rule 使用此機制：偵測命中時自動寫 `.claude/skip-test-verification`，讓 Stop hook 跳過 `uv run pytest`。原因是 Airflow 的 test suite 必須跑在 Breeze container 或透過 `uv run --project <PROJECT> pytest <PATH>`；在 host 端直接跑會因 `jpype1` / cmake FindJava 失敗，且 hook 的 90s timeout 也不夠任何 Airflow subproject 的 test suite 跑完。詳見 [`skills/airflow-aware/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/airflow-aware/SKILL.md)。

如需停用自動跳過，刪除或替換 `.claude/skip-test-verification`（例：改為 `.claude/test-command`，指向一個可在 host 跑的子集）。

### Detector 類型

| `type` | 參數 | 命中條件 |
|--------|------|---------|
| `git_remote` | `pattern: <substring>` | `git config --get remote.origin.url` 輸出含 `pattern` |
| `file_structure` | `all_of: [paths]` / `any_of: [paths]` | `all_of` 全部存在 **且**（若有 `any_of`）至少一個存在 |

### Fail-open 情況

- stdin JSON 解析失敗 → 視為空 dict，仍 fallback `os.getcwd()` 繼續跑
- 個別 detector 拋例外（`subprocess.TimeoutExpired` / `FileNotFoundError` / `OSError`）→ skip 該 detector，繼續下一個
- 個別 rule `match_rule` 拋例外 → skip 該 rule，繼續下一個
- 頂層 unhandled exception → stderr 印一行，emit 空 approve

### Timeout

5 秒上限（`hooks/hooks.json` 設定），單個 git subprocess 內部另設 3 秒上限
（`GIT_TIMEOUT_SEC`）。偵測都是本機檔案或 git config 讀取，毫秒級完成；5 秒
為保護性上限。

### Add New Project Entry

擴充偵測範圍走兩步：

1. **加 registry entry** — 編輯 `hooks/repo_detect.py` 的 `REPO_RULES` list，
   append 一個 dict：
   ```python
   {
       "name": "<project-name>",
       "skill": "<skill-name>",  # 對應 skills/<skill-name>/SKILL.md
       "detectors": [
           {"type": "git_remote", "pattern": "<org>/<repo>"},
           # 可選：加 file_structure detector 當備援
           {"type": "file_structure",
            "all_of": ["<sentinel-file>"],
            "any_of": ["<alt-file-1>", "<alt-file-2>"]},
       ],
   }
   ```
2. **建對應 skill** — 依 [skills.md 加新 skill 的 checklist](skills.md#add-new-skill-checklist) 建 `skills/<skill-name>/SKILL.md`。
   skill 內容定位為「knowledge layer」（contributor 慣例），參考 `skills/airflow-aware/SKILL.md` 結構：
   開頭寫 `**Loaded by**: repo-detect hook (SessionStart) when <project> is detected`，
   後接 When to apply / 命名 / 環境 / 測試 / PR 等子段。

完成後跑 `python3 scripts/validate_plugin.py` 確認 skill cross-ref 通過（check #8 會抓 `repo_detect.py` 引用的 `skills/<name>/` 是否存在）。

## TeammateIdle — `hooks/teammate_quality_check.py`

agent 跑完輸出送回 orchestrator 時觸發。
檢查輸出符合該角色的最低規格，不符合就 block 並要求補完。

### 各角色擋的條件

| Agent | 必須包含 | 違反時的 block message |
|-------|---------|----------------------|
| **Raana** | `## Loaded memory entries` 段（即使無相關 entry 也要明寫「（無相關 entry）」）| 「缺 memory 載入回報」 |
| **Tomori** | `## Loaded memory entries` 段 | 「缺 memory 載入回報」 |
| **Tomori** | 提到 `.maigo/plan.md` 或 `.maigo/review-rubric.md` 路徑 | 「沒提到計畫檔路徑」 |
| **Tomori** | 結構段落：`## Goal` / `## Steps` / `## Rubric` / `## Acceptance` / `## 目標` / `## 步驟` 之一 | 「缺計畫結構」 |
| **Soyo** | `## Loaded memory entries` 段 | 「缺 memory 載入回報」 |
| **Soyo** | verdict 字串：`APPROVED` / `NEEDS_CHANGES` / `BLOCKED` | 「沒下 verdict」 |
| **Soyo** | checklist 項目：`[x]` / `[X]` / `[ ]` | 「沒 checklist」 |
| **Soyo** | 非 APPROVED 時：`must-fix` / `改法` / `evidence` / `待補` 之一 | 「擋下卻沒列 must-fix」 |
| **Soyo** | 同 must-fix key 連續 ≥ 2 次 | block reason 前綴 `⚠️ RETRY LIMIT REACHED (Soyo):` |
| **Taki** | `exit <number>` 模式 | 「沒貼 exit code」 |
| **Taki** | `PASS` 或 `FAIL` 之一 | 「沒給最終 verdict」 |
| **Taki** | **不能包含** `should work` / `looks good` / `應該可以` / `看起來沒問題` 等 hedge 語 | 「verifier 只能拿 exit code 講話」 |
| **Anon** | 至少一個 file path reference（regex 抓 `*.py` / `*.md` / `*.yml` / `*.yaml` / `*.json` / `*.toml` / `*.txt` / `*.sh` / `*.cfg`）| 「沒看到檔案路徑 reference」 |

### Soyo must-fix 計次

Soyo verdict 非 APPROVED 時，hook 會從輸出抽 must-fix 條目，用
backtick 內的 file path（去掉 `:line` 後綴）當 key；無 file 引用的
條目用 normalized 文字當 fallback key。

計數寫到 `.maigo/soyo-must-fix.jsonl`，每行一筆
`{"ts": "...Z", "must_fix_keys": [...]}`。同一 key 累計到
`SOYO_RETRY_LIMIT`（預設 2）時，block reason 前綴
`⚠️ RETRY LIMIT REACHED (Soyo):`，提醒 orchestrator 停下找使用者
——hook 本身仍 block，不會放行。

對齊 Stop hook 的 `RETRY_LIMIT` 機制（見下面 Stop 段）。

### 不檢查的角色

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
- **本次 session 無未提交的檔案修改**（read-only session）→ approve，跳過 test 驗證。偵測方式：`git status --porcelain` 回傳 exit 0 且 stdout 為空；`returncode != 0`（非 git repo 等）→ fail-open，照常跑 test
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
