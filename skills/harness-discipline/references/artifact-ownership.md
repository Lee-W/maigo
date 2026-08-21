# Harness Discipline — Artifact Ownership

Loaded on demand by [`skills/harness-discipline/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/harness-discipline/SKILL.md) —
`.maigo/` 底下 agent 寫的 markdown 產物（`plan.md` / `review-rubric.md` /
`triage-rubric.md` / `pr-comments.md` 這類）曾經被兩個並行 session 靜默覆寫過，
因為它們共用同一個固定檔名，語意上卻該有各自一份。Read this file when 你要在
`.maigo/` 寫入這類 markdown 產物、或需要幫它取路徑之前。

---

## 規則（四條，全部程式碼強制，不是靠你記得檢查）

1. **每份這類 markdown 必須以能識別主題的 H1 開頭**（例：`# Plan: <task>`、
   `# Review rubric: <PR title>`、`# Triage rubric: <issue title> (#<N>)`、
   `# PR comments: <PR title> (#<number>)`）。

   這些範例**必須與各自模板實際寫出的 H1 逐字相同** —— `--topic` 與 H1 對不上，
   `same_topic` 就不成立，續跑會被誤判成 `conflict`。pr-comments 的權威模板在
   [`skills/github-reply-draft/references/comment-fetch-and-triage.md`](https://github.com/Lee-W/maigo/blob/main/skills/github-reply-draft/references/comment-fetch-and-triage.md)。

2. **取路徑一律呼叫**
   [`scripts/artifact_path.py`](https://github.com/Lee-W/maigo/blob/main/scripts/artifact_path.py)，
   帶上 `--topic "<你打算寫的 H1>"`：

   ```
   python3 "${CLAUDE_PLUGIN_ROOT:-.}/scripts/artifact_path.py" <kind> --topic "<H1 主題>" \
       [--url <issue/PR URL>] [--repo <owner/name>]
   ```

   **不要自己組檔名，也不要自己記得比對 H1**——命名的四級識別碼鏈與歸屬比對
   全部在這支 script 裡，有測試把關；散文只負責提醒你呼叫它。

3. **`status: conflict`（exit 3）時，停下來問使用者**，把 stdout 的
   `conflict_owner:`（現有檔案屬於誰）與 `suggest:`（候選新檔名）一起呈現給
   使用者，不要自作主張換名或覆寫。`status: same_topic` 才是安全續寫；
   `status: new` 直接照 `path:` 那行的路徑寫入。

4. **舊固定檔名（stdout 的 `legacy_exists:` 那行指的檔案）只可讀、不可當寫入
   目標**——有續跑語意的產物（如 `plan.md`）在新路徑讀不到內容時可以退回讀舊
   檔繼續，但下一次寫入一律寫到 script 回的新路徑，不回寫舊檔。

`pr-comments` 另外還有
[`commands/address-comments.md`](https://github.com/Lee-W/maigo/blob/main/commands/address-comments.md)
自己的加碼規則（同一個 PR 續跑要保留 `Status`，不得把 `done` 打回
`pending`）——那對應的是 `status: same_topic` 的情境，是該命令特有的加碼，
不是本頁要重複的內容。
