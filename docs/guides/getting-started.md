# Getting Started with Maigo

第一次裝 Maigo？這份文件帶你從零到能用 `/maigo:go` 跑完一個任務。
讀完約 5 分鐘，動手約 10 分鐘。

## 1. Maigo 是什麼

Maigo 是 Claude Code plugin，把開發任務拆給五個 agent 接力處理。
角色取自 anime《BanG Dream! It's MyGO!!!!!》——但人設只是包裝，
真正的價值是讓 reviewer 真的會擋、verifier 真的跑 test、planner 真的留下文件。

| 團員 | 開發角色 | 何時上場 |
|------|---------|---------|
| 要 樂奈 Raana | Explorer | 開頭——探索 codebase 找線索 |
| 高松 燈 Tomori | Planner | 探索完——把混亂寫成步驟計畫 |
| 千早 愛音 Anon | Implementer | 有計畫了——照計畫實作 |
| 長崎 爽世 Soyo | Reviewer | 實作完——預設 BLOCKED、要 evidence 才放行 |
| 椎名 立希 Taki | Verifier | review 後——跑 test、看 exit code 不講廢話 |

跟自己一個人開 Claude Code 比，多出來的價值是：reviewer / verifier 不會被
orchestrator 偷雞跳過（hook 會擋），plan 與 review rubric 會寫到
`.maigo/`（repo root 下，gitignored）留存，跨 session 可查。

## 2. Prerequisites

裝之前先確認下面這幾項齊備。沒齊備也能裝起來，但會少功能。

| 需要 | 版本 | 用途 |
|------|------|------|
| Claude Code CLI | latest | Plugin host |
| Python 3 | 3.13+ | hooks 與驗證 script 都用 Python 寫 |
| `git` | any | review 本地 branch、repo-detect hook 讀 remote |
| `gh` CLI | 任意 | 選用——`/maigo:review <PR-URL>` 才需要 |
| `pre-commit` | 任意 | 選用——貢獻 Maigo 本身才需要 |

## 3. 安裝與第一次使用

裝 plugin 並用 `/maigo:go` 跑一個小任務。

```bash
# 在你想用 Maigo 的專案目錄
cd /path/to/your/project

# 用 plugin 模式啟動 Claude Code
claude --plugin-dir /path/to/maigo
```

進 Claude Code 之後輸入 `/`，應該能看到 `/maigo:go`、`/maigo:team`、
`/maigo:review` 等。第一次試跑可以挑個小任務驗 happy path：

```
/maigo:go 加一個 hello world 的 CLI script
```

預期會看到 Raana → Tomori → Anon → Soyo → Taki 順序輸出；中途 plan 會寫到
`.maigo/plan.md`，review rubric 寫到
`.maigo/review-rubric.md`（均在 repo root 下 `.maigo/`，gitignored）。Soyo 若 verdict 是
`NEEDS_CHANGES` / `BLOCKED`，會留 must-fix 清單；Taki 結尾必貼 `exit <N>` 與
`PASS` / `FAIL`。

### 持久化載入

快速試完想長期用，可透過 marketplace 持久化載入：

在 Claude Code 內：

```
/plugin marketplace add Lee-W/maigo
/plugin install maigo@maigo
```

之後啟動 `claude` 就會自動載入，不必再帶 `--plugin-dir`。

更新、停用、移除：

```
/plugin marketplace update maigo
/plugin disable maigo@maigo
/plugin uninstall maigo@maigo
```

## 4. 常見命令速查

開始上手後最常用的三個 command，挑選原則：

| Command | 何時用 | 特性 |
|---------|-------|------|
| `/maigo:go <task>` | 從零做新任務，要照順序穩穩走 | 5 stage 順序版；最完整 |
| `/maigo:team <task>` | 同上，但想省時間 | Soyo + Taki 並行，省 ~30% 牆鐘 |
| `/maigo:review <PR\|branch\|range>` | 不寫 code、只 review 既有變更 | Anon 不上場；Soyo + Taki 上 |

其他輔助 command（不在第一次必學範圍）：

- `/maigo:quick` — 輕量任務入口，跳過 Raana / Tomori，Soyo 跑輕量 4 項 review
- `/maigo:describe-pr` — 從 branch commits / diff 產 PR title + description
- `/maigo:address-comments` — 收當前 branch PR 的 review 意見，逐項路由到 fix / go / team 處理
- `/maigo:memory` — 管理跨專案記憶（讀、寫、刪、瀏覽）
- `/maigo:remember` — 在當下任務裡新增一條 memory entry
- `/maigo:retro` — 結束任務後做一輪 retrospective，候選提案進 memory

## 5. 下一步

跑通 happy path 後，依需求挑一條深入：

- 想知道每個 command 的完整 stage 與 artefact 落點 → [Commands reference](../reference/commands.md)
- 想知道 reviewer / verifier 怎麼擋你的 → [Hooks reference](../reference/hooks.md)
- 想知道跨專案記憶（每個 repo 累積的慣例與決策）怎麼運作 → [Memory reference](../reference/memory.md)
- 想改 Maigo 本身、加新 skill / hook / project-aware rule → [Contributing](contributing.md)
