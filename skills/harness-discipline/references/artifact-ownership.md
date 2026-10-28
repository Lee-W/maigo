# Harness Discipline — Artifact Ownership

Loaded on demand by [`skills/harness-discipline/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/harness-discipline/SKILL.md) —
`.maigo/` 底下 agent 寫的 markdown 產物（`plan` / `review` / `review-rubric` /
`review-draft` / `triage-rubric` / `pr-comments` / `reply-draft` 這類）曾經被兩個並行
session 靜默覆寫過，因為它們共用同一個固定檔名，語意上卻該有各自一份；後續
又改成按 PR/issue 分資料夾，PR 類產物再依 PR 作者分流：別人的 PR 在
`.maigo/review/<id>/{review,rubric,draft,pr-comments,reply-draft}.md`，自己的 PR 在
`.maigo/pr/<id>/` 同名檔，issue 在 `.maigo/issue/<id>/rubric.md`；作者判斷用
[`scripts/pr_owner.py`](https://github.com/Lee-W/maigo/blob/main/scripts/pr_owner.py)
取得後以 `--owner mine|others` 傳給 `artifact_path.py`；`plan` 例外，維持扁平
`.maigo/plan-<id>.md`。
Read this file when 你要在 `.maigo/` 寫入這類 markdown 產物、或需要幫它取
路徑之前。`.maigo/` 全貌型錄（含非 markdown 機器狀態檔、Work Board、舊固定
檔名、分目錄前扁平檔與未登記檔案）見
[`docs/reference/artifacts.md`](https://github.com/Lee-W/maigo/blob/main/docs/reference/artifacts.md)。

---

## 規則（四條，全部程式碼強制，不是靠你記得檢查）

1. **每份這類 markdown 必須以能識別主題的 H1 開頭**（例：`# Plan: <task>`、
   `# Review rubric: <PR title>`、`# Review: <PR title / branch / range>`、
   `# Triage rubric: <issue title> (#<N>)`、`# PR comments: <PR title> (#<number>)`、
   `# Reply drafts: <PR title> (#<number>)`）。

   這些範例**必須與各自模板實際寫出的 H1 逐字相同** —— `--topic` 與 H1 對不上，
   `same_topic` 就不成立，續跑會被誤判成 `conflict`。pr-comments 的權威模板在
   [`skills/github-reply-draft/references/comment-fetch-and-triage.md`](https://github.com/Lee-W/maigo/blob/main/skills/github-reply-draft/references/comment-fetch-and-triage.md)。

2. **一般產物取路徑呼叫**
   [`scripts/artifact_path.py`](https://github.com/Lee-W/maigo/blob/main/scripts/artifact_path.py)，
   帶上 `--topic "<你打算寫的 H1>"`：

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/artifact_path.py" <kind> --topic "<H1 主題>" \
       [--url <issue/PR URL>] [--repo <owner/name>] [--owner mine|others]
   ```

   PR 類 kind（`review` / `review-rubric` / `review-draft` / `pr-comments` / `reply-draft`）
   帶 `--url` 時 `--owner` 必填，沒給 exit 2；先跑
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pr_owner.py" --url <PR url>` 取得。另一組資料夾
   已有同 id 的同名檔案時，stdout 多一行 `other_group_exists: <path>`，同 `flat_exists:`
   只供讀取退路，不當寫入目標。
   **不要自己組檔名，也不要自己記得比對 H1**——命名的四級識別碼鏈與歸屬比對
   全部在這支 script 裡，有測試把關；散文只負責提醒你呼叫它。

   **寫手沒有 Bash 時由 orchestrator 代跑**：在目標 cwd 呼叫 helper、處理 ownership
   結果並建立父目錄後，交付絕對路徑、原樣 H1 與 status，寫手只用 Write／Edit 寫內容。
   🩵 燈的 plan、review rubric 與 triage rubric 都適用；缺交付資料時回報 orchestrator，
   不靠手算或改工具權限繞過。

3. **`status: conflict`（exit 3）時，停下來問使用者**，把 stdout 的
   `conflict_owner:`（現有檔案屬於誰）與 `suggest:`（候選新檔名）一起呈現給
   使用者，不要自作主張換名或覆寫。`status: same_topic` 才是安全續寫；
   `status: new` 直接照 `path:` 那行的路徑寫入。

   **`suggest:` 已經幫你往下找過空位**：它是從第 2 個 attempt 起，第一個
   「檔案不存在、沒有 H1、或 H1 與本次主題相同」的路徑，不是固定的 `-2`。
   同一個 branch/PR 跑過多輪 `/maigo:go`、`/maigo:quick` 留下 `-2`、`-3`……
   不同主題的產物時，候選會自動跳過它們——非巢狀 kind（`plan`）長成
   `plan-<id>-3.md` 這類；巢狀 kind（`review` / `review-rubric` /
   `review-draft` / `pr-comments` / `reply-draft` / `triage-rubric`）後綴落在檔名層、不是目錄
   層，長成 `review/<id>/rubric-3.md` 這類，不是另開 `review/<id>-3/` 資料夾。
   候選若剛好是 H1 與本次主題相同的既有檔，代表以前已經用同一個主題續寫過，
   status 仍是 `conflict`，只是在 `suggest:` 提示可以接著用那一份。

   **不論候選長什麼樣，都要經使用者同意才使用**——找到空位不等於可以直接寫入，
   同意閘門不因此放寬。**這一步要有 Bash 才做得到**——沒有 Bash 的 agent
   （🩵 Tomori）永遠不會走到這裡：conflict 一律由 orchestrator 在 spawn 她之前
   處理掉，處理結果連同最終路徑才交給她。

4. **舊固定檔名（stdout 的 `legacy_exists:` 那行指的檔案）與分目錄前扁平檔
   （`flat_exists:` 那行指的檔案，只有巢狀 kind 才可能有）都只可讀、不可當
   寫入目標**——有續跑語意的產物（如 `plan-<id>.md`）在新路徑讀不到內容時
   可以退回依序讀 `flat_exists:` 再讀 `legacy_exists:` 繼續，但下一次寫入
   一律寫到 script 回的 `path:` 新路徑，不回寫任何一種舊檔。這條現在不是只
   靠你記得——`Write` / `Edit` 寫入 `.maigo/` 底下的舊固定檔名或分目錄前
   扁平檔都會被
   [`hooks/legacy_artifact_path_check.py`](https://github.com/Lee-W/maigo/blob/main/hooks/legacy_artifact_path_check.py)
   （PreToolUse）直接擋下，訊息會附上正確的 `artifact_path.py` 呼叫指令，
   也會提醒既有舊檔可用
   [`scripts/migrate_legacy_artifacts.py`](https://github.com/Lee-W/maigo/blob/main/scripts/migrate_legacy_artifacts.py)
   搬過去。

**最終 review 報告的專用入口**：
[`scripts/review_report.py publish`](https://github.com/Lee-W/maigo/blob/main/scripts/review_report.py)
重用 artifact_path 命名，以 canonical source 身分判斷同一份報告，允許同 PR 改標題後
更新最新 `review.md`，不再為每輪 review 累積 `review-2.md`。新檔成功後僅回收已確認
同 source 的舊 report，細則見
[`commands/review.md`](https://github.com/Lee-W/maigo/blob/main/commands/review.md)。
歸屬衝突仍明確失敗；不適用這個 publisher 的其他 kind 繼續遵守上述 H1 合約。

`pr-comments` 另外還有
[`commands/address-comments.md`](https://github.com/Lee-W/maigo/blob/main/commands/address-comments.md)
自己的加碼規則（同一個 PR 續跑要保留 `Status`，不得把 `done` 打回
`pending`）——那對應的是 `status: same_topic` 的情境，是該命令特有的加碼，
不是本頁要重複的內容。
