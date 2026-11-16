# Teammate Flow — Planning Defaults for Decisions needed

Loaded on demand by [`skills/teammate-flow/SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/teammate-flow/SKILL.md) 的第 2 步 —
🩵 燈 (Tomori) 寫 `## Decisions needed` 時，遇到下列三種形狀的選擇，**預設值（`[**default**]`）
照本表放**，另一個選項也要列出並標明它的成本。這些預設來自使用者過去在同形狀選擇上的改選
方向；使用者仍可推翻，表只是讓第一版 plan 不必再被改一輪。

---

| 形狀 | 預設 | 另一選項與成本 |
|------|------|----------------|
| 新功能依賴一條**還沒 merge 的 feature branch** | 不等 merge，從該 branch 的 HEAD 開 worktree 疊上去（stacked）；PR base 設成該 branch，上層 merge 後 rebase 到 `main` | 等 merge 後再從 `main` 開：乾淨，但整個依賴部分被卡住；若被依賴的是別人的 PR，還要把「你的 branch 會帶著對方的 commit」寫進選項，見 `git-workflow` commit-hygiene 的 stacking 一節 |
| 升版時，探索發現一條**重疊的 pending branch**（改同一塊檔案，例如 constraints 整塊），且上游已有比它更新的正式版 | 把相依的升級放進同一次改動一次做完，舊 branch 由使用者自行作廢 | 維持窄 scope、只升一項：diff 小，但之後與那條 pending branch 必然衝突，要付一次 rebase 的成本 |
| 新的 UI／顯示類功能，有多個可以顯示的位置 | 先在最小必要位置上線，其他顯示點做成**預設關閉**的 opt-in 設定 | 一開始鋪滿所有位置：功能完整，但使用者事後曾收回部分位置，還要為此回頭改 |

## review 單位超過一個時：提案拆成一串 PR，由使用者拍板

上表是「使用者過去改選的方向」；這一節是另一種形狀：plan 先列出這次工作的
**review 單位**（可以獨立被 review、獨立被接受的主題，例：公開 API 改名、內部重構、
文件改寫、新功能）。超過一個時，在 `## Decisions needed` 提案：

- **default**：拆成一串 PR，寫明順序、各自範圍、互相標註的方式。這裡的 default 指「建議選項」，不是自動執行；與 `commit-hygiene` 的「splitting ... not the default」不衝突，後者說的是未經使用者同意不拆。
- **另一選項**：單一 PR，並寫出成本（review 單位混在一起，reviewer 要一次判斷多個主題）。

判準以 **review 單位**計，不以行數計。依據：同領域、≥150 行的樣本裡，同領域 maintainer
的 PR 中位數比一般貢獻者的更大，comment 卻少得多；差別在一個 PR 一個主題、成串互相標註，
不在行數。這個比較的樣本小、maintainer 是該領域的 area owner（干擾因素），只當作拆分判準
的方向，不當定論。

這裡只**提案**，不自行拆：拆不拆由使用者決定，與
[`commit-hygiene`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/references/commit-hygiene.md)
的「先問再拆」一致；使用者拍板前不預先執行任一選項。
同一規則在 [`agents/Tomori.md`](https://github.com/Lee-W/maigo/blob/main/agents/Tomori.md)
的「你會做的事」。

## 使用方式

- 「一次升到位」的前提是探索階段已查過 upstream 正式版與 constraints／tag 是否存在（見
  [`SKILL.md`](https://github.com/Lee-W/maigo/blob/main/skills/teammate-flow/SKILL.md) 的 🐱 樂奈探索必含兩項）；沒查過就先退回探索，不要憑印象寫預設。
- 最小範圍原則與 teammate-flow 的 Orchestrator 守則（誠實裁減）同精神：把「要不要鋪開」的
  決定權留給使用者，而不是由 plan 預先決定。
- 形狀不完全吻合時不要硬套：照 Tomori 平常的規則寫 Decisions needed，把表當成參考。
