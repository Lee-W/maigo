# Work Board — review-board.md 併入遷移與看完標記（§4、§4a）

Loaded on demand by [`skills/work-board/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/work-board/SKILL.md) §4 與 §4a — 舊 review-board.md 的遷移步驟，以及 `[x]` 看完 review 的 ack 流程。
本檔內文原樣自 SKILL.md 搬出，章節編號（§1a、§3a 等）沿用原編號，SKILL.md 內仍以這些編號互相引用。

## 4. 併入遷移（review-board.md 退役）

首次跑 `/maigo:board`（或某回寫命令要寫 board 時）偵測到 `.maigo/review-board.md`
存在且 `board.md` 不存在：

1. 讀舊檔，按分區映射搬行：`Active` + `↩︎ 回你的球` → 👀；`Off-board` → ⏳；
   `Merged/closed` → ✅；`🔍 本批佇列` → 依 §2 重判
2. 解析舊行的 author / URL / 規模（`- #<PR> (<author>) …` 這個舊尾註形狀）→ 用
   [`detail_path()`](https://github.com/Lee-W/maigo/blob/main/scripts/board_state.py)
   算出細節檔路徑並依 §1a 格式建檔（事實區填入解析出的 author/URL/規模，`## 判斷` /
   `## 筆記` 留空）→ 索引行改寫成新文法，只留
   `- [ ] 👀 <狀態詞> @<author> — <title> <細節檔路徑>`；author 已知就保留於索引，URL 移至細節檔
3. 舊檔改名 `review-board.md.migrated`（留底不刪），之後一切只寫 `board.md`
4. [`review-batch-queue.md`](https://github.com/Lee-W/maigo/blob/main/skills/strict-review/references/review-batch-queue.md)
   的「持久 review board」段落改為指向本 skill，只保留 review 特有的 verdict 語彙說明

## 4a. 看完 review 的標記

在 board 把 👀 行勾成 `[x]`，或跑 `/maigo:board --reviewed <n...>`（等同勾上），都表示使用者
已看完目前報告、不需再留在待看清單；`--unreviewed`（或把 `[x]` 改回 `[ ]`）取消。下次刷新由
[`scripts/board_sync.py ack`](https://github.com/Lee-W/maigo/blob/main/scripts/board_sync.py)
呼叫
[`review_report.acknowledge`](https://github.com/Lee-W/maigo/blob/main/scripts/review_report.py)
把時間、使用者 login 寫進該 report metadata，須與目前 PR head 及上次顯示的 `reviewed_at` 相符（規則見 §3a），再依 classify
結果更新 board。它不送 GitHub review。`--reviewed` 同時加 `🔖`，後續照 §5 學習。完整流程見
[`commands/board.md`](https://github.com/Lee-W/maigo/blob/main/commands/board.md)。

新報告會清除上一版的確認；新 commit／作者留言也會重新排入待看（👀 行自動取消勾）。單純碰檔案
mtime 或刷新 board 不會改最後 review 時間。cleanup 刪掉同 source 舊報告後，細節檔的舊 report
連結要用 Edit 換成 canonical `../review/<id>/review.md`（自己的 PR 為 `../pr/<id>/review.md`，檔案相對，獨立成清單項或包反引號）；只改路徑，保留其餘手寫內容。
