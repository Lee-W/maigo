# Failure Handling — 環境假紅與 Stop hook 假陽性迴圈

Loaded on demand by [`skills/failure-handling/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/failure-handling/SKILL.md) — 測試紅燈疑似環境造成、想把測試加進 known-test-failures、或 Stop hook 逐輪重觸發時讀。
本檔內文原樣自 SKILL.md 搬出。

### 環境造成的假紅

測試紅燈被診斷為**環境造成的假紅**（Node/OS/工具版本行為差異，不是程式碼缺陷）時，
判準：乾淨環境會綠、紅的成因指向 Node/OS/工具版本而非被測程式碼本身。

優先順序：

1. **改環境設定讓它真的綠**（例如 `.claude/settings.local.json` 的 `env`、正確的 flag、
   對版本的工具）
2. 治本的 repo 改動（測試 setup 層的隔離），範圍合理時另開 PR
3. **最後才是遮蔽**（本 repo 的 known-test-failures 機制）

**Why**：遮蔽名單是全檔粒度，遮掉噪音的同時把該檔案未來的**真回歸**一起遮掉；環境修法
沒有這個代價，還會讓別的 session 也直接受益。

**不要把「加進 known-test-failures」當預設收尾動作**——寫之前先問使用者，並在選項裡說明
代價；修完環境要回報「修掉幾個 / 還剩幾個」，剩下的說清楚為什麼修不掉。


### Stop hook 假陽性迴圈

當 Stop-hook 的 test verifier 因為**環境 / collection 層**問題（不是變更本身壞掉）逐輪重新觸發：

1. **先確認一次成因**——是 host 環境結構性壞掉（bootstrap / install-time 失敗），還是單純
   monorepo scope 抓錯 test 指令。前者才適用「寫 skip 檔」；後者且變更有真正新行為要覆蓋時，
   應該修對應的 `.claude/test-command` 成正確 scoped 指令、寫一個真的 test 去測，不要圖方便
   直接跳過驗證。
2. 環境結構性壞掉、且已經用該 repo 的真實 runner 確認過一次是綠的 → 立刻寫
   `.claude/skip-test-verification`（帶非空、非註解的原因說明）disarm 該 worktree 的 verifier，
   不要每輪重新解釋同一個假陽性——任何一次回覆都會重新觸發 Stop hook，逐輪重複解釋等於空轉。
3. 使用者明確說「忽略這個 hook」時，**輸出零字元**——連 `.`、`[ignored]`、空白都不行。任何輸出
   都會結束該輪、讓 harness 重跑 Stop hook、hook 再次擋下，形成迴圈。等使用者修 hook 設定 /
   中斷 session / 送新任務，不要逐次確認每次觸發。
4. **受限權限模式下，第 1、2 點的寫檔動作本身可能被擋。** `.claude/` 是 harness 的設定目錄，
   權限 classifier 會把寫入判成 self-modification / safety bypass（實例 2026-09-17，Claude Code
   auto mode：Bash heredoc 回 `[Self-Modification]`、Write 工具回 `[Safety Bypass Flag]`，同一個
   檔案兩條路都不通，hook 連擋五輪）。這道防護的用意是對的——不該讓模型自己關掉測試驗證——
   所以**不要繞**，也**不要換工具重試**（換工具做同一個動作，仍是同一個動作）。第一次被擋就
   停手交給使用者，並給**可直接執行的一行**，而不是「請你去寫個檔案」：

   ```text
   ! printf '%s\n' "<scoped test command>" > .claude/test-command
   ```

   `!` 前綴讓使用者在自己的 session 裡跑，輸出直接進對話。使用者授權後再由模型寫入亦可。
