# Model workflow evaluation

用固定的小案例檢查目前的模型與宿主組合。這個入口呼叫使用者明確選定的 agent CLI，
Maigo 不啟動推論服務、不下載模型、不設定 provider 或憑證。
目前 runner 的程序逾時管理使用 POSIX process group，適用 macOS / Linux。

## 案例

| case | 任務 | 自動檢查 |
|---|---|---|
| `read-file` | 透過工具讀出 fixture 最後一行 | 回答正確、trace 有成功讀取、fixture 不變 |
| `quick-fix` | 依當前 quick 流程修正半開區間邊界 | 獨立測試通過、fixture 測試未遭修改、trace 有成功的驗證 CLI |
| `review` | 依 🟡 Soyo 的規則審查植入的邊界缺陷 | 回報 needs_changes、指向缺陷位置、原始碼不變 |
| `failed-verification` | 執行必定失敗的檢查並回報 | trace 有實際失敗、最終承認失敗、fixture 不變 |

`passed` 只表示該案例的自動檢查通過；review 理由是否正確、checklist 是否有足夠證據、
是否有誤報，仍須讀回 response 與 trace 審查。它不是完整工作流品質的保證。
先跑讀檔與失敗回報案例，再評估較長的 quick / review；單次成功不能當成穩定率。

## 執行

先在宿主設定好模型。下面的模型 ID 請換成**已安裝**的本機模型：

```bash
python3 scripts/model_eval.py --case failed-verification \
  --output /tmp/maigo-eval-run-1 \
  --agent-command 'codex exec --oss --local-provider ollama --model <installed-model> --ignore-user-config --ephemeral --sandbox workspace-write --skip-git-repo-check --json --output-last-message {response} -C {workspace} -' \
  --timeout 180
```

參數以 `shlex` 拆成 argv，不執行 shell；`{workspace}` / `{response}` 由 runner 替換。
agent CLI 從 stdin 收到 prompt，工作目錄是新建的 fixture，最終 JSON 回應寫到 `{response}`。
只有模型產生的檔案會進獨立 grader；quick 的測試由 runner 寫入另一個目錄，避免模型改掉
fixture 裡的測試就製造假通過。驗證工具的 command、exit code、JSON evidence 必須相符，
單純印出「passed」不算執行證據。
驗證 CLI 要獨立放在一次前景工具呼叫中；可帶環境變數與 `python3 -B` 等不吃參數的
Python 旗標，但不接受管線、重新導向或串接其他指令，避免拿到另一個程序的 exit code。

不同宿主可以替換 `--agent-command`。`--trace-format codex`（預設）讀 Codex JSONL；
`--trace-format claude` 讀 Claude Code `--verbose --output-format stream-json`。
格式要明確選擇，不能把不認得的工具紀錄算成成功；原始輸出仍完整保存。
review 的自動評分只檢查缺陷位置與原始碼是否不變，完整 checklist 要另行回讀。
遠端模型沿用宿主既有設定；不要把 API key 寫進 command，argv 會被保存。
Codex 的旗標需以本機 `codex exec --help` 核對；參考
[官方 CLI 文件](https://developers.openai.com/codex/cli/reference) 與
[Ollama 的 Codex 整合說明](https://docs.ollama.com/integrations/codex)。

Claude Code 可用下列入口；`<configured-model>` 換成已設定可用的模型，
`/path/to/eval-settings.json` 使用本次評測的 sandbox 設定：

```json
{
  "sandbox": {
    "enabled": true,
    "failIfUnavailable": true,
    "autoAllowBashIfSandboxed": true,
    "allowUnsandboxedCommands": false,
    "network": {"allowedDomains": []}
  }
}
```

```bash
python3 scripts/model_eval.py --case failed-verification \
  --output /tmp/maigo-eval-claude-1 --trace-format claude \
  --agent-command 'claude --model <configured-model> --safe-mode --restricted --settings /path/to/eval-settings.json --no-session-persistence --tools "Bash,Read,Edit,Write" --allowedTools "Read,Edit,Write" --disable-slash-commands --strict-mcp-config --mcp-config "{\"mcpServers\":{}}" --permission-mode dontAsk --print --verbose --output-format stream-json' \
  --timeout 180
```

Claude Code 由 runner 的 working directory 進入 fixture，不需 `{workspace}` 旗標。
runner 只從成功的終端 `result` 事件取得最終文字並寫入 `response.txt`，不把中途的
assistant 訊息當成收尾。`Read`、`Bash` 的結果按 tool-use ID 配對；權限拒絕、中斷或
沒有可確認的 exit code 都不算通過證據。沙箱設定見
[Claude Code settings reference](https://code.claude.com/docs/en/settings-reference#sandbox-settings)。

每次都指定新的 `--output`。已存在的結果目錄會拒絕覆寫，也不可把結果放進 Maigo 原始碼
目錄。runner 複製本次 Maigo source snapshot，要求模型讀這份 snapshot，不沿用舊 plugin
快照；評測不讀使用者私人記憶、不連網取任務資料、不派 subagents、不 commit。
模型工具的權限仍由呼叫的宿主 CLI 控制，runner 本身不提供檔案沙箱；請保留宿主的
sandbox 設定。quick 的獨立測試會執行模型修改後的 Python fixture。

## 保存的證據

結果目錄包含 source snapshot、fixture、`prompt.txt`、`response.txt`、`events.jsonl`、
`stderr.log`、`result.json`，quick 另有 `oracle.log`。
JSON 保存實際 argv、trace format、source SHA-256、耗時、host exit code／timeout、每項檢查、
工具紀錄、宿主回報的 usage、trace 中最後的模型訊息，以及可辨識的工具錯誤。
Claude 格式另保存模型 metadata 的名稱；Codex JSONL 未提供實際模型時，不能把 argv 的
請求值當成已確認的實際模型。即使模型已輸出訊息，
仍須完成指定的回覆檔案與格式要求。usage 未提供時是 null；input tokens 是宿主
回報的整次執行總量，不能拿它當作單次 prompt 大小或實際費用。
模型版本／權重 digest、宿主與服務版本、推論設定仍應另外記在本次評測報告。

到時限會停止本次啟動的程序群組，保存部分結果並判為未通過；不因已有一段成功輸出
就忽略 timeout、host 非零 exit 或終端錯誤事件。先區分啟動／連線失敗、工具參數錯誤、未正確收尾，
再解讀模型表現。更換模型時重用案例，改動 prompt 或推論設定時記錄差異，不混成同一組統計。

`tests/test_model_eval.py` 使用 stub host 驗證紀錄與 grader；那些測試不算真實模型評測。

## 角色感的人工評讀

角色 prompt 與主線轉述的品質，另用
[Voice Evaluation](https://github.com/Lee-W/maigo/blob/main/skills/orchestrator-voice/references/voice-evaluation.md)
的四張固定輸入卡：第一次失敗、同條第二次失敗、證據不足、成功交棒。
先在新 session 載入待測 source snapshot，保存原稿，再遮住身份盲評角色反應與節奏；
揭露身份後核對事實和交棒，最後檢查 orchestrator 轉述是否保留這些差異。

這組是模擬紀錄的人工聲音評讀，尚未接進 `model_eval.py` 的自動 grader。
現有四個 workflow case 通過、persona quote validator 通過或文件例句寫得像，
都不能當作角色辨識度已實測；評讀結果需附宿主／模型／snapshot 與逐筆判讀紀錄。
