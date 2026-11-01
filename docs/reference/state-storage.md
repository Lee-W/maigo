# `.maigo/` 集中儲存

`.maigo/` 的實體放在本機一個集中 root，每個 worktree 的 `.maigo` 只是指向它的 symlink。
同一個 repo 的所有 worktree 因此共用一份 board、plan 與 review 報告，不再各自一份。
這一頁只描述儲存層；它不同步任何東西，也不決定哪些內容可以離開這台機器。

## 位置與 repo identity

```text
$MAIGO_STATE_HOME/<owner>/<repo>/        # 預設 ~/.local/share/maigo/state/<owner>/<repo>/
<worktree>/.maigo  ->  上面那個目錄
```

`<owner>/<repo>` 由 git remote 推出：

- 先看 `upstream`，沒有可用的再看 `origin`。
- 去掉結尾的 `.git` 與斜線，取 URL 路徑的最後兩段；host、使用者名稱、port 都忽略，
  所以 `git@github.com:apache/airflow.git`、`https://github.com/apache/airflow`、
  `ssh://git@github.com/apache/airflow.git` 得到同一個 `apache/airflow`。
- fork 有 `upstream` 時以 upstream 為準（`astronomer/airflow` 的 clone 解成 `apache/airflow`）。
- 沒有可用 remote（或 remote 是本機路徑）→ `_local/<主 worktree 的目錄名>`。這類 repo
  在另一台機器上對不上；目錄名相同的兩個無 remote repo 會共用同一個 `_local/<name>`，`migrate` 的衝突偵測是唯一的保險。

identity 只是目錄名，**不代表任何同步許可**；maigo 沒有內建任何 allowlist。

## 指令

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/maigo_state.py" identity [--cwd DIR]
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/maigo_state.py" link [--cwd DIR]
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/maigo_state.py" migrate [--cwd DIR] [--apply]
```

- `identity`：印出 identity 與集中目錄路徑。
- `link`：`.maigo` 不存在時建 symlink。SessionStart hook（[`repo_detect.py`](hooks.md)）每次 session
  開啟都會做同一件事。`.maigo` 是真目錄、指向別處的 symlink、或一般檔案時只回報，不動。
- `migrate`：把同一個 repo 所有 worktree 的真目錄 `.maigo/` 併進集中目錄。

## 遷移既有 `.maigo/`

`migrate` 預設 dry-run，只印出每個 worktree 要複製幾個檔、哪些內容相同、哪些衝突。

- 同名但內容不同的檔只列出、不覆寫；有任何衝突時連 `--apply` 也不動手（exit 2），
  先自行決定留哪一份再重跑。
- `--apply` 先把每個 worktree 的原目錄備份到 `<root>/_migration-backup/<UTC 時間>/`，
  逐項核對（種類與內容）原目錄的每個項目都與集中目錄一致，才把真目錄換成 symlink；任何一項對不上就保留原目錄、不換。檔案與目錄同名也算衝突。備份是唯一的回退點；若換 symlink 的最後一步失敗，沒有自動回復，要從備份還原。
- 巢狀的 `.maigo/.maigo/` 殘留會列出來，內容原樣併進去，不刪；之後用 `/maigo:tidy` 處理。
- 已經指向正確目標的 worktree 會略過，所以可以重跑。

## 信任邊界

`.maigo` 若是 symlink，寫入端（review 報告發佈、`/maigo:tidy --apply`、`board_sync.py refresh --apply`）
會檢查它的目標落在集中 root（`$MAIGO_STATE_HOME`）之內，否則拒絕——避免 repo commit 了一個
指向任意位置的 `.maigo` 把寫入導到 repo 外。真目錄照舊放行。其餘寫入端（例如 hook 寫的
`_internal/log/`）沒有這道檢查。

`/maigo:tidy` 要在 repo 內跑（`--dir` 預設 `.maigo`），不要把集中目錄本身當 `--dir`，目錄名檢查會拒絕。

## 行為變更

- **board 只有一份**：不再需要 `find` 找「哪個 worktree 有 board」，報告與 board 也一定在同一份
  `.maigo/` 底下。
- **`artifact_path.py` 的 conflict 會更常出現**：兩個 worktree 在不同分支用同一個 `--slug`
  寫 `topic/<slug>/plan.md`，現在會撞在同一個檔，回 `status: conflict`，而不是各寫各的。
- **`/maigo:tidy` 的範圍變成整個 repo**：歸檔候選涵蓋所有 worktree 的產物，仍須逐項確認。
- **機器日誌也共用**：`_internal/log/*`、`session-head.json` 住在同一份 `.maigo/` 之下。
- git 忽略規則是不帶斜線的 `.maigo`（symlink 不被 `.maigo/` 匹配），見
  [`repo_detect.py` 的說明](hooks.md)。
