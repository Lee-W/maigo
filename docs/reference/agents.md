# Agents Reference

Maigo 的角色責任與模型選擇分開。角色定義保留探索、計畫、實作、審查、驗證的交棒契約；
本機或遠端推論服務由執行 Maigo 的宿主連接。Maigo 不啟動模型服務、不管理 API key。

## Claude Code 隨附預設

沒有指定 model profile 時，Claude Code 沿用以下 agent frontmatter 預設。
這是隨附設定，並非對其他模型能力的評分。

| Agent | Model | 責任 |
|-------|-------|------|
| 🩵 **Tomori** | opus | 規劃步驟、驗收條件與取捨。 |
| 🐱 **Raana** | sonnet | 探索 codebase、找慣例與影響面。 |
| 🎀 **Anon** | sonnet | 按計畫實作，留下變更與驗證證據。 |
| 🟡 **Soyo** | sonnet | 按 checklist 審查，列出具體 must-fix。 |
| 🟣 **Taki** | haiku | 跑 test / lint / type check，回報實際結果。 |

維護者改隨附預設時，要同步 `agents/*.md` 的 `model:` 與這張表；
`uv run python scripts/validate_plugin.py` 會檢查一致性。
使用者改個人對應可用下面的 profile，無須修改 plugin。

## Model profiles

在原本的命令加 `--model-profile <path>`，例如：

```text
maigo:quick --model-profile /path/to/models.json 修正日期解析
/maigo:team --model-profile /path/to/models.json 實作查詢功能
```

適用於有角色派工的 quick、go、team、review、triage-issue、take-issue、describe-pr、
doctor、crystallize；address-comments 把選擇傳給內層 route。
可明確要求這個 session 沿用同一份檔案。沒有指定就用宿主原生預設；不自動發現設定檔。
相對路徑以呼叫命令時的 project cwd 解析一次，轉為絕對路徑後再傳進 worktree 或內層命令。

JSON 格式：

```json
{
  "schema_version": 1,
  "default_model": "local-coder",
  "roles": {
    "Tomori": "remote-planner",
    "Soyo": "remote-reviewer"
  }
}
```

這些是**示意名稱**，請換成目前宿主 model 參數接受、且已設定連線的模型 ID。
`local-coder` 不會自動指向 Ollama，`remote-reviewer` 也不會自動建立 vLLM 連線。
推論服務的 tool calling、chat template 等設定仍由宿主與服務端負責；設定可解析不等於
該模型能可靠完成 Maigo 工作流。profile 不含 endpoint、provider、金鑰或宿主能力欄位。

| 欄位 | 意義 |
|------|------|
| `schema_version` | 必填，目前為整數 `1` |
| `default_model` | 可省略；本次角色的預設 model override |
| `roles` | 可省略；以角色定義的名稱指定 model override，大小寫須一致 |
| model 值 | 非空字串，或 `null` 表示不傳 model override；不接受前後空白或控制字元 |

優先順序是角色明確值 → `default_model` → `null`。
角色明確填 `null` 可退出 `default_model`，回到宿主原生預設；這不保證是主線模型。
未知欄位、未知角色、重複 JSON key 或不支援的版本會回報錯誤，避免拼錯後悄悄套用預設。
只對本次會執行的角色檢查宿主能否套用 override。

### 只有一個模型

宿主支援逐次指定模型時，全部角色共用一個模型只需：

```json
{"schema_version": 1, "default_model": "local-coder"}
```

宿主只有單一模型、無法逐角色 override 時，先在宿主選好模型，執行 Maigo 時省略 profile，
或使用 `{"schema_version": 1}`。如果仍要求特定 override，resolver 會回報無法套用，
不會把要求丟掉。沒有 subagents 時，主 agent 依序執行角色，並明示共用 context；
review checklist 與實際測試照常保留。team 只有在宿主允許並行時才並行審查與驗證。

### 檢查派工結果

orchestrator 依當前工具 schema 宣告可用能力；下列指令本身不探測或啟動模型：

```bash
python3 /path/to/maigo/scripts/resolve_dispatch.py --roles Anon Soyo \
  --profile /path/to/models.json --subagents --model-override
```

三個能力旗標 `--subagents`、`--model-override`、`--parallel` 預設都為否。
後兩個需要 `--subagents`；有設定檔不代表有這些能力。
輸出的 `execution` 決定 subagents 或 inline，`parallel` 只允許原流程中互不相依的階段並行，
`roles` 保留輸入順序並列出角色檔與模型。exit 0 / `ready` 是設定可套用的派工計畫；
exit 2 / `error` 附原因，不能當作測試結果。

宿主的模型限制仍可能拒絕或替換請求，因此要核對宿主回報的實際模型；沒有證據時標未確認。
Claude Code 的逐次 model 參數與原生預設有自己的解析順序，見
[官方模型選擇說明](https://code.claude.com/docs/en/sub-agents#choose-a-model)。
完整派工與重試規則見 [model-dispatch](../skills/model-dispatch.md)。

## 兩位旁白：🌙 Doloris / 🌑 Mortis

這兩位**不在 `agents/`** 也沒對應 Task agent——他們是 **orchestrator 對使用者說話時戴上的臉**，不下場做事。
所以沒有 frontmatter、沒有 tool list、沒有 model tier，只在開場 / 收場 / 卡關節點出現。

行為規格與何時用哪一位：[`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md)。
