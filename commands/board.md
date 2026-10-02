---
description: 讀寫 `.maigo/board.md` Work Board——混合追蹤 issue、自己的 PR、在審的 PR，依單一優先序階梯排進「下一件 / 等別人 / 最近結案」三區，供 nvim 直接開檔閱讀。orchestrator 直跑，不 delegate 五人。
allowed-tools: Bash(gh api:*), Bash(gh issue view:*), Bash(gh pr view:*), Bash(gh repo view:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/board_state.py:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/board_sync.py:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/board_index.py:*), Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/review_report.py:*), Read, Write, Edit
---

<!-- mkdocs-include-start -->

# /maigo:board

> 🌙 Doloris：「先看清楚球在誰手上，再決定下一步要往哪裡走。」

> 本檔的 `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/…` 刻意不加引號：為了讓 `allowed-tools` 的前綴放行與替換後的命令字串字面一致；plugin 安裝路徑含空白時不支援。

Work Board 是跨 session 的工作看板：issue triage / 接工、自己的 PR、正在 review 的 PR
全都放進 `.maigo/board.md`，依單一優先序排名（下一件事排最上面）分成三個 section。

命令由 orchestrator 直跑，不動員五人；正典規格在
[`skills/work-board`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md)。

## 使用

```
/maigo:board <targets...>   # 混貼 issue/PR 編號或 URL；入板後刷新全板、印 🎯
/maigo:board                # 無參數：對帳 .maigo/ 產物＋discovery 該 repo 指名你審的 PR，刷新全板、印 🎯 + 其他區計數
/maigo:board --all          # 刷新後印整板
/maigo:board --reviews      # 只顯示現在需要我看的 PR（標題、貢獻者、最後 review）
/maigo:board --reviewed <n...> # 等同在 board 勾 [x]：本地 ack 這版 report、勾上、加 🔖；不送 GitHub
/maigo:board --unreviewed <n...> # 等同取消勾：撤銷本地 ack、改回 [ ]
/maigo:board --learn        # 對「已勾 [x] 或 🔖、但沒有 🧠」的項目跑學習盤點
/maigo:board --check <n...> # 只翻 [ ]→[x]（等同 nvim 手勾），下次刷新才判斷是否 ack
/maigo:board --uncheck <n...> # 只翻 [x]→[ ]
/maigo:board --drop <n...>  # 不追了，移進 ✅ 最近結案（狀態詞 已放棄），並寫入排除紀錄，之後刷新不再補回
/maigo:board --cross-repo   # 本地刷新照舊，額外產出跨 repo 總索引
```

`targets` 可混用裸編號、GitHub issue URL、GitHub PR URL。裸編號以當前 repo 判定；
URL 若指到其他 repo，行內保留 `owner/repo#n` 全稱。

## 流程

### 1. 載入或建立 board

若 `.maigo/board.md` 不存在，先建立骨架。若偵測到舊的 `.maigo/review-board.md`
且 `board.md` 尚不存在，依
[`work-board` 的併入遷移規則](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md)
搬到新 board，舊檔改名成 `.maigo/review-board.md.migrated` 留底。

若 `board.md` 存在但仍是球權三分區時代的舊格式（讀到舊版 section 標題），刷新時取每行的
checkbox / `🧠` / 狀態詞後，整檔以新的三 section 骨架重寫，不做逐行 in-place 遷移。

### 2. 加入 targets（有參數時）

targets 直接交給 script：`refresh --apply --add <targets>`（§3）。型別偵測（URL 解析、裸編號查
`gh api …/issues/<n>`、PR 作者比對、抓不到標 `抓不到`）、`revive --reason manual` 都由 script 處理，
revive 事件在 CAS 通過、寫回成功之後才寫。`--add` 的項目只在那一輪不受 7 天老化影響；下一輪它已是
board 上的一般行，結案超過 7 天就會照常被清掉。以下是 script 無法執行時的手動流程（§3 的 fallback）要照做的規則。

每個 target 先做型別偵測：

- URL 直接解析 owner / repo / issue-or-PR / number
- 裸編號用 `gh api repos/<owner>/<repo>/issues/<n>`；有 `pull_request` key 就是 PR
- PR 再比對 `gh api user --jq .login` 與 author，分成 🔀 你的 PR / 👀 在審的 PR
- 抓不到就標狀態詞 `抓不到`（rank P0，併進 🎯 最上面），附錯誤末行

加入時以 `#<n>` 或 `owner/repo#<n>` 為 key upsert；既有 checkbox 與 `🧠` 狀態必須保留。
使用者明確加入的 target 要**先**呼叫 `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/board_sync.py revive --reason manual <url...>`
（只對目前被排除的項目寫 revive 事件，回 `revived` / `not_excluded`），否則曾被 `dd` / `--drop` 的項目
會因排除紀錄而不重新分類。

### 3. 刷新分區

除 `--learn` 外，每次都做完整刷新。解析、對帳、discovery、排除紀錄、勾選轉換、抓料、分類、渲染與寫回
都在 [`scripts/board_sync.py`](https://github.com/Lee-W/maigo/blob/main/scripts/board_sync.py) 的
`refresh` 子命令（實作在 `scripts/board_refresh.py`）；它用 compare-and-swap 保護寫回（規則見
[`skills/work-board` §3(b)](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md)）：

1. 跑 `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/board_sync.py refresh --apply --json [--add <targets>] [--max-new N] [--no-discovery]`
   （在 board 所在 repo 的任一 worktree 內跑即可；`--maigo-root`／`--repo`／`--you` 沒給時自動判斷）。
2. 依 exit code 分流：
   - **exit 0** → 依輸出的 JSON（`pending_reviews`、`top`、`counts`、`warnings`、`errors`、`removed`、
     `overflow`、`unattributed`、`pending_orphans`、`excluded_detail_files`、`learn_pending`）做 §4。
   - **exit 2**（CAS 衝突：board.md 或細節檔在刷新期間被改過；除了 review.md 的 ack 標記外未寫任何檔）→ 直接重跑一次；再撞到就停下，
     告訴使用者 board 正被別的 session 寫。**不要**改用 `Write`。
   - **exit 1**（前置條件拒絕）→ 依訊息分流：舊格式或 `review-board.md` → 走下面的「手動流程 fallback」
     做整檔正規化後重跑；找不到 board 或有多份 → 問使用者；board 有壞行／細節檔缺 `## 判斷` → 回報原文。
   - **exit 3**（寫入階段失敗）→ 回報備份路徑與錯誤，不 fallback。`--json` 的 `exit_reason` 是 `write_failed`
     ＝已從備份還原；是 `post_write_failed` ＝board 已是新版、只有 ledger／snapshot 沒寫成，把輸出列出的
     未寫事件回報給使用者，說明重跑是安全的。

#### 手動流程 fallback（只在 script 無法執行或拒絕時用）

解析、對帳、discovery、排除紀錄、勾選轉換由 `board_sync.py` 的 `plan` / `ack` / `drop` / `revive` /
`snapshot` 子命令做；這些子命令**不寫** `board.md` 與 `.maigo/i/*.md`，orchestrator 負責呼叫順序、
`gh pr view` 抓料與 `Edit` 寫回。以下 `<root>` 是 `.maigo/` 所在的存活 worktree：

1. **規劃**——讀現檔 board、`i/*.md` 的 `- 連結：`、snapshot、排除紀錄與 `.maigo/` 產物型錄，
   再用 `gh search` 找出該 repo 指名你審或你審過的 PR。`--dry-run` 不寫任何檔：

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/board_sync.py plan --maigo-root <root> --repo <owner/name> --you <login> \
     [--dry-run] [--max-new 50] [--no-discovery]
   ```

   輸出 JSON：`lines`（每行的 `url` / `checked` / `checkbox_change` / `inferred` / `excluded`）、
   `removed`（偵測到被 `dd` 的項目，已寫進排除紀錄）、`revived`（重新被指名而復活）、
   `additions` / `overflow`、`unattributed`、`pending_orphans`、`excluded_detail_files`、`errors`。
   board 仍是舊版格式時 `plan` 直接失敗：先依 §1 整檔正規化再重跑。
2. **抓料與分類**——對每一行（`excluded: true` 的行**不重新分類**，原樣保留，`已放棄` 才不會被
   洗回 `待 review`）與每一筆 `additions` 做型別偵測並跑 `gh pr view` / `gh issue view`，
   沿用 §2 的流程。
3. **ack**——把 `checkbox_change` 非 null 的 👀 行組成 JSON 餵給 `ack`，逐項取回結果
   （`acked` / `already_acked` / `no_report` / `head_changed` / `unacked` / `locked` / `error`）：

   ```bash
   echo '[{"url": "<url>", "head": "<full head sha>", "change": "checked", "inferred": false}]' \
     | python3 ${CLAUDE_PLUGIN_ROOT}/scripts/board_sync.py ack --maigo-root <root> --repo <owner/name> --you <login>
   ```

   `change` 與 `inferred` 直接取自 `plan` 的對應行。`[ ]→[x]` 是使用者明確操作，一律重打 ack；
   `inferred`（沒有 snapshot、由已勾推斷）且同 head 已 ack 則回 `already_acked`，不重打。
4. **分類**——把每項的 `type` / `gh_meta` / `prior_status`（讀自現有 board 行）/ `url`，加上
   `checked` / `checkbox_change` / `prior_badges`（該行現有 badge），餵給
   [`scripts/board_state.py`](https://github.com/Lee-W/maigo/blob/main/scripts/board_state.py)：

   ```bash
   echo '<[{type, gh_meta, prior_status, url, local_verdict_at, checked, checkbox_change, prior_badges}, ...]>' \
     | python3 ${CLAUDE_PLUGIN_ROOT}/scripts/board_state.py --you <login> --repo <owner/name> --maigo-root <repo root>
   ```

   **一定要帶 `--maigo-root <repo root>`**：CLI 讀 report 的 `reviewed_at`、`head_sha`、verdict 與你的
   已看完標記；source 歸屬不符會失敗。GitHub metadata 必須含 `title`、`author`、`headRefOid`、
   `commits`、`reviews`、`comments`，否則純 push 沒有留言時會漏掉重審（欄位完整清單見 work-board skill）。
   回傳除既有欄位外，另有最終 `checked`（`null` ＝不要動 checkbox）、`learn_pending`、`acked_current`。
   三張球權判定表、排序與 ✅ 保留天數見
   [`skills/work-board`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md)；
   `classify()` 是判定邏輯的唯一正典。
5. **寫回**——用 `Edit`（不整份 `Write`）：依 rank 升序 ＋ 同 rank 內 `updatedAt` 升序寫回 🎯 的編號清單
   （`⏳`/`✅` 依 `updatedAt` 降序、無編號）；行內容用 `index_entry`，加最終 checkbox、badge、編號。
   - `learn_pending` 為 true 的行加 `🔖`（跨刷新保留，跟 `🧠` 一樣）。checkbox 一律以 `board_state` 回傳
     的 `checked` 為準：👀 勾了卻回 `no_report` 或 `head_changed`，若分類結果仍是待看
     （`needs_review`），該行自動取消勾，並在對話警告「#n 沒有本版 report／head 已變，未標記已看完；
     請先 `/maigo:review <n>`」；但 GitHub 已送出你的 review、又沒有 report 時，該行不在待看清單，
     使用者自己勾的 `[x]` 保留。
   - **已知限制**：`acknowledged_at` 記的是刷新當下，不是勾選當下；第一次跑（沒有 snapshot）時，
     已勾的 👀 行以推斷模式補 ack（同 head 已 ack 則不重打）。
   - 由 artifact 對帳補進來、但分類結果是 `merged` / `closed` 的項目**不寫入 board**，改呼叫
     `board_sync.py drop --reason closed <url...>`，否則 `review/<id>/review.md` 還在時每次刷新都會補回。
   - ✅ 區超過 7 天老化清掉的行，清掉的同時呼叫 `board_sync.py drop --reason aged <url...>`。
   - **同步寫細節檔**：每項索引行寫回的同時，用回傳的 `detail_path` 建立或更新對應的
     `.maigo/i/<slug>.md`——只重寫事實區（標題行 ＋ 連結/規模/下一步/最後 review/已看完等 metadata），
     `## 判斷` 與 `## 筆記` 原樣保留；細節檔不存在才整份新建。格式規格見
     [`skills/work-board` §1a](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md)。
   - **孤兒 `i/` 檔就是 dd 訊號**：使用者在 nvim 用 `dd` 刪行後，細節檔還留著，`plan` 會把它判成 dd
     並寫進排除紀錄（剛寫好的檔有 10 分鐘寬限，列在 `pending_orphans`，本輪不判）。只有
     `excluded_detail_files`（排除項目殘留的細節檔）要列出來，**等使用者確認後才刪**，不自動刪。
6. **快照**——全部寫回後呼叫 `snapshot`，它會重讀最終的 board 寫入 `.maigo/_internal/board/snapshot.json`
   （下次刷新據此偵測 `dd` 與勾選變化）：

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/board_sync.py snapshot --maigo-root <root> --repo <owner/name> --you <login>
   ```

`board_sync.py drop --reason {drop,dd,aged,closed} <url...>` 單獨使用時只 append 排除紀錄。
`board_sync.py revive --reason manual <url...>` 則對目前被排除的項目 append `revive` 事件（§2 明確加入 target 時用）。
`.maigo/_internal/`（含 `backup/`）底下的檔案只由 script 寫入，orchestrator 不要用 `Write` / `Edit` 碰。

### 3a. 從 shell 刷新（零 token）

不經過 Claude，直接從 shell（或 nvim 的 `:!`）刷新 board，不花 token：

```bash
python3 "$MAIGO_HOME/scripts/board_sync.py" refresh           # 預覽：印 diff，不寫任何檔、不 ack
python3 "$MAIGO_HOME/scripts/board_sync.py" refresh --apply   # 寫回
```

`$MAIGO_HOME` 是 maigo 的 checkout 或 plugin 安裝目錄（由你在 dotfiles 裡指向）。cwd 在 board 所在 repo
的任一 worktree 內都可以，script 會用 `git worktree list` 自動找到唯一一份 `.maigo/board.md`
（找不到或有多份就拒絕，用 `--maigo-root` 指定）；`--repo` 預設取 board 第一行 header，`--you` 預設取
`gh api user`。可用旗標：`--add <url|n>...`、`--max-new`、`--no-discovery`、`--stale-days`、`--jobs`、`--json`。

在 nvim 裡開著 board 時：先 `:w`，再 `:!python3 "$MAIGO_HOME/scripts/board_sync.py" refresh --apply`，最後
`:e` 重新載入。script 讀的是磁碟，refresh 之後沒 `:e` 就存檔會用舊 buffer 蓋掉刷新結果（nvim 會先跳
W12 警告）；script 看不到未存檔的 buffer，只能靠這個順序。

| exit code | 意思 |
|-----------|------|
| 0 | 成功（含沒有變動）；預覽模式永遠 0 |
| 1 | 前置條件拒絕：舊格式、`review-board.md`、壞行或未知狀態詞、細節檔缺 `## 判斷`、找不到／多份 board |
| 2 | CAS 衝突：刷新期間 board.md 或細節檔被改過；除了 review.md 的 ack 標記外未寫任何檔，直接重跑 |
| 3 | 寫入階段失敗（抓料失敗的列恢復時從細節檔 H1 取回舊狀態詞，同輪手改狀態詞不保留）：`write_failed` ＝已從 `.maigo/_internal/board/backup/` 還原（或列出未還原的檔）；`post_write_failed` ＝board 已是新版，只有 ledger／snapshot 沒寫成，重跑安全 |

### 4. 輸出

無參數與 `<targets...>` 先印「現在要看的 PR」：從完整分類結果取 `needs_review=true`，
列出 PR 標題、貢獻者、狀態、最後 review 時間；沒有就明說目前沒有待看的 PR。
再印 🎯「下一件」的前幾行 ＋ 其他區計數 ＋ board.md 路徑；另外**只在有內容時**列出以下摘要
（對話是拋棄式的，真相仍在 board.md，不另造閱讀層）：

- `overflow`：超過 `--max-new` 沒補進來的項目（編號、標題、作者），下次刷新接著補；
- `unattributed`：未歸屬產物（`plan-*`、舊固定檔名、沒有可靠 PR 對應的本地 review 等），依類別計數＋檔名；
- ack 警告（`no_report` / `head_changed` / `locked` / `error`）與 `errors` 原文；
- `pending_orphans`（寬限期內，本輪未判）、`removed`（本輪判為 dd 的項目）、`excluded_detail_files`
  （等你確認是否刪除）。

輸出沿用 [`/maigo:doctor`](https://github.com/Lee-W/maigo/blob/main/commands/doctor.md)
的 emoji 分段慣例。`--all` 印完整 board。

若刷新後有「(`[x]` 或 `🔖`) 且沒有 `🧠`」的項目，結尾加：

```
🧠 有 N 項你勾了還沒盤點 → /maigo:board --learn
```

**`--reviews`**：完整刷新與寫回仍使用未過濾的結果；對話只顯示待看 PR。
可另以 `board_state.py --reviews` 取得依 rank 排序的檢視結果，**不可用過濾後結果覆寫
整份 board**。包含 `待 review`、`↩︎ 回你的球`、`待送出`；已看完、等人、草稿與結案不列入。

### 4a. `--reviewed` / `--unreviewed`

這是使用者說「我已看完這版，不需留在待看清單」的明確操作，**等同在 nvim 勾 `[x]`**：
`--reviewed` ＝ 把該行勾上（ack ＋ `[x]` ＋ `🔖`），`--unreviewed` ＝ 取消勾（undo ＋ `[ ]`）。
只處理 👀 PR；兩者都走完整刷新（§3），不是只改單行，結束時寫 snapshot。做法：先把目標行的
checkbox 改成目標狀態（`--reviewed` 改 `[x]`、`--unreviewed` 改 `[ ]`，用 `Edit`），再跑
`refresh --apply`（取代再跑 §3 的規劃）——它依 snapshot 偵測到 `[ ]→[x]`（或 `[x]→[ ]`），經 `ack` 呼叫
`review_report.py acknowledge`（`--unreviewed` 對應 `--undo`），不改最後 review 時間、不送 GitHub。
需要已有新版 report，且 head 必須與報告一致；舊報告先重新 review，head 已變則請先重審
（回 `no_report` / `head_changed`，待看的行取消勾並警告）。錯誤逐項列出，不把失敗項目標成已看完。

### 5. `--learn`

`--learn` 不刷新其他項目，只處理 `.maigo/board.md` 裡「(`[x]` 或 `🔖`) 且沒有 `🧠`」的行
（`🔖` 是學習訊號的持久化：👀 行被勾過之後即使自動取消勾，訊號也還在）。
orchestrator 逐項抓使用者在 GitHub 的實際處理方式，蒸餾 0-3 條候選知識，接
[`memory-propose-confirm`](https://github.com/Lee-W/maigo/blob/main/skills/memory-propose-confirm/SKILL.md)
讓使用者確認；處理完（含沒有候選）就在該行加 `🧠`、移除 `🔖`。

學習閘門只負責進料，不取代 `/maigo:crystallize`。

### 6. `--check` / `--uncheck`

`--check <n...>` 把對應行的 `[ ]` 改為 `[x]`，表示「這項是使用者親自處理的」；
`--uncheck <n...>` 改回 `[ ]`。兩者都可接裸編號或 `owner/repo#n`，且：

- 只改 checkbox，保留 section、整行內容與 `🧠` / `🔖`
- **不寫 snapshot、不呼叫 `ack`**：效果等同在 nvim 裡手勾，下次完整刷新才依 snapshot 判斷這次翻轉
  （對 👀 行而言，`--check` 就是「看完」，下次刷新會 ack）
- 已是目標狀態時視為成功（idempotent）
- 找不到的 target 列出錯誤，其他 target 照常處理
- `--check` 完成後若該行沒有 `🧠`，照常提示可跑 `/maigo:board --learn`

### 7. `--drop`

`--drop <n...>` 表示「不追了」：依 `#<n>` 或 `owner/repo#<n>` 找到對應行後，狀態詞改為
`已放棄`，整行移進 `✅ 最近結案`——跟其他結案行共用同一條 7 天老化規則，不再有獨立的
留痕區。保留原 checkbox 與 `🧠` 狀態；**並呼叫 `board_sync.py drop --reason drop <url...>`
寫入排除紀錄**，之後的 discovery 與 artifact 對帳都不再補回，刷新也不會把 `已放棄` 洗回 `待 review`
（該行 `excluded: true`）。對應細節檔不動，等 7 天老化清除時跟索引行一起刪
（見 [`skills/work-board` §3 細節檔生命週期](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md)）。

### 8. `--cross-repo`

opt-in，預設不開——跨 13 個 repo 掃描比本地刷新慢得多，不該預設每次都跑。
先照舊完成本地 `.maigo/board.md` 刷新（§1–§4），flag 有帶時追加呼叫：

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/board_index.py [--repo-list ~/.config/maigo/repos.txt]
```

印出輸出檔 `~/.config/maigo/board-index.md` 的路徑。**不影響本地 `board.md`
的行文法／upsert 規則**——`board_index.py` 全程唯讀，只讀各 repo 的
`board.md`、逐字複製 `## 🎯 下一件` 整段，不重寫任何被掃描 repo 的內容，也不
新增獨立命令（併入這個 flag）。正典規格見
[`skills/work-board`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md)。

## 與其他命令的差異

| 命令 | 對象 | 做什麼 |
|------|------|--------|
| `/maigo:board` | issue / 自己 PR / 在審 PR 的集合 | 決定下一步是誰的哪個動作；維護跨 session board |
| `/maigo:review` | PR / branch / commit range | 實際做嚴格 code review |
| `/maigo:triage-issue` | inbound GitHub issue | 實際下 triage verdict，產 gh 草稿 |
| `/maigo:repo-audit` | repo 自身積壓 | read-only 盤點 branch / PR / TODO / skill 健診 |

## Orchestrator 守則

- **orchestrator 直跑**：不要 delegate 五人；`gh view --json` 抓料可並行，但輸出要有界。
- **board 是唯一真相層**：`.maigo/board.md` 保留 checkbox 與 `🧠`；maigo 不提供任何呈現層，
  nvim 直接開檔即讀即改。
- **回寫照 upsert 合約**：行存在就替換整行並保留 checkbox / `🧠`；行不存在才 append 到對應 section。
  **整行替換時對應細節檔（`.maigo/i/<slug>.md`）必須跟著同步更新，不可只改索引行漏改細節檔**
  ——兩者是同一次寫回的兩個產物。同步更新＝只重寫事實區，`## 判斷` 與 `## 筆記`
  依 [`skills/work-board`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md)
  的硬規則原樣保留，沒有例外。
- **`--learn` 必須確認**：候選知識要經 `memory-propose-confirm`，不可靜默寫入 memory。
- **`refresh --apply` 是唯一會整檔寫 board 的寫入者**，靠 CAS 防覆蓋；`plan` / `ack` / `drop` /
  `revive` / `snapshot` 不寫 `board.md` / `i/*.md`。Claude 自己仍只用 `Edit`，`Write` 只用在建立骨架；
  `.maigo/_internal/`（含 `backup/`）只由 script 寫入，不要用 `Write` / `Edit` 碰。
- **不寫 GitHub**：board 只讀 GitHub metadata，不回覆、不 label、不 close、不 push。
