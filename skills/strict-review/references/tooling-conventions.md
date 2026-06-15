# Tooling 慣例

review 碰到 pyproject.toml / git hook / 工具升版的 diff 時，對照以下 Wei 的常駐偏好把關。

## pytest 設定表
pyproject.toml 設定 pytest 時偏好 `[tool.pytest]`（pytest 9.0+ 原生讀取），而非傳統 `[tool.pytest.ini_options]`。套用此偏好時一併確認 `requires-python>=3.10`（pytest 9 的要求）。

## git hook 用 pre-commit framework
設定 git hook 時用 `.pre-commit-config.yaml`（pre-commit framework），不手寫 `.git/hooks/` 下的 raw script。先檢查專案有無 `.pre-commit-config.yaml`：有就在那裡加 hook（找對應 hook repo / id），沒有就建一份。除非使用者明講，不寫 raw `.git/hooks` script。

## 工具版本升級策略
升 linter / pre-commit hook / 工具版本時，採用最新穩定（安全）版，不為了避免新規則報錯而退回舊版。新版冒出的新規則錯誤，列清單交使用者手動處理——不自作主張退版、也不自動在設定檔加 `RuleX: false` 關規則（除非使用者明講要關）。
