# Tooling 慣例

review 碰到 pyproject.toml / git hook / 工具升版的 diff 時，對照以下 Wei 的常駐偏好把關。

## pytest 設定表
pyproject.toml 設定 pytest 時偏好 `[tool.pytest]`（pytest 9.0+ 原生讀取），而非傳統 `[tool.pytest.ini_options]`。套用此偏好時一併確認 `requires-python>=3.10`（pytest 9 的要求）。

## git hook 用 pre-commit framework
設定 git hook 時用 `.pre-commit-config.yaml`（pre-commit framework），不手寫 `.git/hooks/` 下的 raw script。先檢查專案有無 `.pre-commit-config.yaml`：有就在那裡加 hook（找對應 hook repo / id），沒有就建一份。除非使用者明講，不寫 raw `.git/hooks` script。

## 工具版本升級策略
升 linter / pre-commit hook / 工具版本時，採用最新穩定（安全）版，不為了避免新規則報錯而退回舊版。新版冒出的新規則錯誤，列清單交使用者手動處理——不自作主張退版、也不自動在設定檔加 `RuleX: false` 關規則（除非使用者明講要關）。

**Scope gate（以下細則只在 diff 是 linter / formatter / 依賴版本 bump 時適用）**：bump PR
的職責只是換版本號，維持行為中性——新版本冒出的新規則**不在同一個 PR 裡掃修**，即使那些
規則落在專案本來就整包 select 的規則區段內。「這個區段本來就 opt-in」跟「這個區段裡每一條
新規則都已經被審過」是兩件事，前者不能替後者背書。

- **延後機制**：把新觸發的規則放進 `ignore`，且設定檔那行 `ignore` 必須帶**追蹤 issue 連結
  的註解**。這跟上面「不自動加 `RuleX: false` 關規則」的預設不衝突——上面管的是使用者沒
  表態時你自己決定關規則；這裡是 bump PR 明確劃 scope boundary（規則要不要啟用是另一個
  決策，這個 PR 只換版本號），且留了可追蹤的線頭，不是靜默關掉。
- **行為中性要有量化證據**：比對升級前後的 enabled rule 數（例如
  `ruff check --show-settings` 的 `linter.rules.enabled` 筆數），一致才算「中性」成立。
  **reviewer APPROVE 不算清除這個問題**——APPROVE 審的是逐行程式碼，不觸及「這個 PR 的
  邊界該不該包含規則修法」這個更上層的 scope 判斷。
- 列給使用者的新規則清單本身不是「已妥善處理」的證據，要附上面的量化中性性佐證才算。
