# `.maigo/` 跨機器同步

[集中儲存](state-storage.md) 讓同一台機器上的所有 worktree 共用一份 `.maigo/`。這一頁說明怎麼讓**另一台機器**
也拿到其中一部分：集中 root 本身是一個 git work tree，remote 叫 `origin`，指向你自己的私有 repo。
同步是兩個手動動作，沒有 daemon、沒有自動解衝突，也不呼叫 `gh`。

## 預設拒絕

集中 root 底下的東西預設**全都不同步**。只有寫在 `<root>/allowlist` 的 `owner/repo` 才會被追蹤：

- `allowlist` 是一個明文檔，每行一個 `owner/repo`（`#` 開頭為註解）。maigo 沒有內建任何項目，一開始是空的。
- 排除規則由 allowlist 產生，寫在 `<root>/.git/info/exclude`（不追蹤、不要手改；`init`、`allow`、`status`、`pull`、`push`
  都會重新產生，所以 clone 下來的第二台機器第一次跑 `status` 就有）：沒在 allowlist 的 `<owner>/<repo>/`、`_local/`、`_migration-backup/`，
  以及每個 allowlisted repo 底下的 `_internal/`（機器日誌、tidy 備份、board snapshot）都不會被追蹤；`*.zip` 一律排除。
  唯一從 `_internal/` 放行的是 `_internal/board/dropped.jsonl`（只增不改的排除紀錄），`.gitattributes` 讓它用
  `merge=union` 合併，兩台機器各加一行不會衝突。
- `allowlist` 與 `.gitattributes` 兩個中繼檔本身會被追蹤，所以另一台機器 clone 下來就有同一份規則。
  `allowlist` 也用 `merge=union`：兩台機器各自 `allow` 不同的 repo，`pull` 之後是兩邊的聯集，不會衝突。
- `push` 在排除規則之外再檢查一次：`git add -f` 可以繞過 ignore，所以 index 與尚未推送的 commit 裡
  每個路徑都必須落在 allowlist 內（或是兩個中繼檔），否則拒絕、exit 1，什麼都不推。

identity 解成同一個 `owner/repo` 不代表可以同步。公司或私人內容不要加進 allowlist；
board 與 review 報告是你尚未發佈的意見，放上私有 repo 也要自己先決定。

## 指令

```text
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/maigo_state_sync.py" init [--url URL]
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/maigo_state_sync.py" allow OWNER/REPO
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/maigo_state_sync.py" status [--fetch]
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/maigo_state_sync.py" pull
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/maigo_state_sync.py" push
```

集中 root 由 `$MAIGO_STATE_HOME` 決定（預設 `~/.local/share/maigo/state`），同步指令用同一個位置。

- `init [--url URL]`：把集中 root 變成 git repo（分支 `main`），有給 `--url` 就加 remote `origin`，
  建立 `allowlist`（空的）、`.gitattributes`，並寫入排除規則。可重跑；已有不同的 `origin` 時拒絕。不 commit、不連網。
- `allow OWNER/REPO`：把一行加進 `allowlist` 並重新產生排除規則。`_` 或 `.` 開頭的 owner（`_local` 等）一律拒絕。
- `status [--fetch]`：印出 `branch`、`ahead`、`behind`、`uncommitted`，以及 allowlist 內但還沒被追蹤的目錄
  （`untracked-allowlist: owner/repo`）。加 `--fetch` 才會先連 `origin`，否則用上次 fetch 的結果；fetch 失敗或超過 10 秒只警告。本機還沒有任何 commit、remote 卻已有歷史時，
  `behind` 是 remote 的 commit 數，並多印一行 `note:` 提示改用 clone。
  集中 root 不是 git repo 時印一行說明、exit 0。
- `pull`：先把本機變更 commit 成一個快照，再 fetch 並 merge `origin/<目前分支>`。
- `push`：檢查通過後 commit 並推到 `origin`。merge 還沒收尾（有衝突標記或 `MERGE_HEAD`）時拒絕，exit 1。
- `pull` 發現 `origin` 沒有目前分支時，會警告 remote 上有哪些其他分支，exit 0。

`push` 的警告（印到 stderr，只列出，不擋）：含 `/Users/` 或 `/home/` 絕對路徑的檔案、單檔 ≥ 1 MB 的檔案。
既有筆記裡的絕對路徑不會被改寫；它們在另一台機器上只是失效的文字。

## 第一次設定

`gh repo create` 與第一次 `git push` 由你親手執行，maigo 不會代跑。

```text
gh repo create maigo-state --private
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/maigo_state_sync.py" init --url git@github.com:<you>/maigo-state.git
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/maigo_state_sync.py" allow <owner>/<repo>
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/maigo_state_sync.py" push
```

`push` 會先 commit 再推；先看一眼 `git -C <root> status` 與 `git -C <root> ls-files` 是否只有預期的檔案。

## 日常

- 開工前 `pull`，收工後 `push`。`/maigo:board` 開頭會跑 `status --fetch`，落後 `origin` 時只提示一句，不會自動 pull。
- `pull` 會先把本機未 commit 的變更 commit 成快照，這樣兩邊同時改同一個檔才會走 git 的三方合併，
  而不是被擋在「本機有未 commit 的變更」。快照 commit 只在本機，`push` 才會送出。

## 第二台機器

第二台機器要 `git clone`，不要在已有內容的集中 root 上 `init`（兩邊歷史不相干，`pull` 會停下）。
若那台機器的集中 root 已經有內容，先搬開再 clone，再把不同步的目錄搬回來：

```text
mv ~/.local/share/maigo/state ~/.local/share/maigo/state.old
git clone git@github.com:<you>/maigo-state.git ~/.local/share/maigo/state
```

不同步的目錄（例如 `_local/`、沒進 allowlist 的 repo）從舊目錄搬回來，不要覆蓋 clone 下來的檔案：

```text
cp -Rn ~/.local/share/maigo/state.old/_local ~/.local/share/maigo/state/
cp -Rn ~/.local/share/maigo/state.old/<owner> ~/.local/share/maigo/state/
```

`_migration-backup/` 也是這樣搬。確認都搬回來之後再刪 `state.old`。

clone 下來就帶著 `allowlist` 與 `.gitattributes`；排除規則在第一次 `status`／`pull`／`push` 時產生。
clone 後先跑 `status`（它會產出 `.git/info/exclude`）；在那之前不要在 root 直接 `git add -A`，否則會 stage 到 allowlist 外的目錄
（`push` 會擋，但不必走到那步）。worktree 的 `.maigo` symlink 指向集中 root 的路徑，
所以位置要和原本一致。

## 衝突

兩台機器都改了同一個檔（通常是 `board.md`），`pull` 會停下，exit 1，並印出：

- 衝突檔清單
- `git status --short`

它不會 `--abort`，也不會選邊；工作區保留 git 的衝突標記。用 nvim 打開衝突檔，解完之後：

```text
git -C <root> add <檔案>
git -C <root> commit
```

之後再 `push`。想放棄這次合併就 `git -C <root> merge --abort`。merge 還沒收尾時再跑 `pull` 會直接拒絕。

`pull` 會先把本機變更 commit 成快照再合併，所以 `merge --abort` 只會退回合併前，快照 commit 仍在本機。
要連本機那次修改一起放棄，得自己 reset 掉那個快照 commit，否則下次 `pull` 會再衝突一次：

```text
git -C <root> merge --abort
git -C <root> reset --hard HEAD~1
```

`reset --hard` 會丟掉那次本機修改，執行前先用 `git -C <root> log -1` 確認 `HEAD` 是 `maigo-state: local snapshot before pull` 開頭的那個 commit。

## 另請參閱

- [`.maigo/` 集中儲存](state-storage.md)：位置、identity、遷移、信任邊界
