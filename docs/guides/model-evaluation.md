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

不同宿主可以替換 `--agent-command`。**目前自動工具證據與 usage 解析針對 Codex JSONL**；
其他格式照樣保存原始輸出，但沒有對應解析器時無法確認工具證據，需要這項證據的案例
不會自動判通過；review 目前只檢查回覆中的缺陷位置與原始碼是否不變。
遠端模型沿用宿主既有設定；不要把 API key 寫進 command，argv 會被保存。
Codex 的旗標需以本機 `codex exec --help` 核對；參考
[官方 CLI 文件](https://developers.openai.com/codex/cli/reference) 與
[Ollama 的 Codex 整合說明](https://docs.ollama.com/integrations/codex)。

每次都指定新的 `--output`。已存在的結果目錄會拒絕覆寫，也不可把結果放進 Maigo 原始碼
目錄。runner 複製本次 Maigo source snapshot，要求模型讀這份 snapshot，不沿用舊 plugin
快照；評測不讀使用者私人記憶、不連網取任務資料、不派 subagents、不 commit。
模型工具的權限仍由呼叫的宿主 CLI 控制，runner 本身不提供檔案沙箱；請保留宿主的
sandbox 設定。quick 的獨立測試會執行模型修改後的 Python fixture。

## 保存的證據

結果目錄包含 source snapshot、fixture、`prompt.txt`、`response.txt`、`events.jsonl`、
`stderr.log`、`result.json`，quick 另有 `oracle.log`。
JSON 保存實際 argv、source SHA-256、耗時、host exit code／timeout、每項檢查、工具紀錄、
宿主回報的 usage、trace 中最後的模型訊息，以及可辨識的工具錯誤。即使模型已輸出訊息，
仍須完成指定的回覆檔案與格式要求。usage 未提供時是 null；input tokens 是宿主
回報的整次執行總量，不能拿它當作單次 prompt 大小或實際費用。
模型版本／權重 digest、宿主與服務版本、推論設定仍應另外記在本次評測報告。

到時限會停止本次啟動的程序群組，保存部分結果並判為未通過；不因已有一段成功輸出
就忽略 timeout 或 host 非零 exit。先區分啟動／連線失敗、工具參數錯誤、未正確收尾，
再解讀模型表現。更換模型時重用案例，改動 prompt 或推論設定時記錄差異，不混成同一組統計。

`tests/test_model_eval.py` 使用 stub host 驗證紀錄與 grader；那些測試不算真實模型評測。
