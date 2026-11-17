# Work Board — 跨 session 接續（§7）

Loaded on demand by [`skills/work-board/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md) §7 — `ListAgents` 查不到對應 session 時如何從 board 與 plan 接續。
本檔內文原樣自 SKILL.md 搬出，章節編號（§1a、§3a 等）沿用原編號，SKILL.md 內仍以這些編號互相引用。

## 7. 跨 session 接續：`ListAgents` 查不到對應 session 時

使用者說「有個 session 在做 X」，但 `ListAgents` 查不到可觸及的對應 session——session 本身
消失了不代表工作內容跟著消失。**先查 `.maigo/board.md` 有沒有這個 issue/PR 的 `IN_PROGRESS`
行**（`/maigo:take-issue` 開工時會旁註 branch 名，見 `commands/take-issue.md` 步驟 4），有的話
直接用旁註的 branch 名定位 worktree；board 沒記到，才退而找對應 worktree 本身（該任務的
`.maigo/pr/<id>/plan.md` / `.maigo/issue/<id>/plan.md` / `.maigo/topic/<slug>/plan.md`——或遷移前留下的頂層 `.maigo/plan-<id>.md` / 舊 `.maigo/plan.md`——是否存在、`git log`/`git status`
做到哪一步）——兩者都能讓 orchestrator 從既有進度接著跑，不必
等原 session 復活，也不必整個重新走一次 Raana 探索 + Tomori 規劃。

**不確定該任務在哪個 repo時**：這台機器裝了 maigo 的 repo 不只一個，先查
`~/.config/maigo/board-index.md`（沒有就先跑一次 `/maigo:board --cross-repo`
產生）縮小範圍，再進到命中的那個 repo 查 `board.md` 與各 plan（`pr/` / `issue/` / `topic/` 底下的 `plan.md`），比逐一
`cd` 進每個 repo 問一輪快。
