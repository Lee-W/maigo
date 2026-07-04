# Maigo Self-Check — `/maigo:crystallize` Graduation Mechanics Reference

Loaded on demand by [`commands/crystallize.md`](https://github.com/Lee-W/maigo/blob/main/commands/crystallize.md) —
crystallize is the command that actually writes into `skills/`, so this reference extends
maigo-self-check's "touches skills/" domain with the detail specific to crystallize's own
steps: graduation-candidate criteria, the destination decision table, the publicity
(sanitization) check, Anon's implementation checklist, and the interrupt/rollback matrix.
Read this file when executing the corresponding crystallize step.

---

## Step 2 — 挑畢業候選：criteria 細節

對每筆 entry 套以下準則，**全中才是候選**：

- **形狀是 convention / workflow / 規則**，不是一次性事實
  （✅「批次 PR review 純按行數升序」「回覆草稿給連結＋可複製內文」
  ❌「我叫 Wei Lee」「AppleScript date 屬性會 timeout」這類 atomic fact）
- **有明確 consumer**——某個 command / agent 載入它時會真的用到
  （能講出「這條畢業後該掛在哪個 command / agent 的哪一步」）
- **反覆性 signal**——描述含「以後都 / 每次 / 慣例 / 一律」，
  或多筆記憶指向同一主題、可合併成一個 skill 段落

**額外強訊號**：entry 自己標註了畢業意圖（如 `**How to apply**` 寫了
「未來可寫進 `<script>` / 降級此記憶」）——這類直接列為高優先候選。

**排除**：`type: user`（身份事實）、`type: reference`（外部指針）、
以及任何一次性踩雷 fact。不確定形狀 → 不列為候選（寧缺勿濫）。

## Step 4 — 目的地決策表

- **目的地**（先過落點決策表）：

  | 條目形狀 | 落點 |
  |---|---|
  | 一行講完的通用規則 | 併進既有 skill 本體的對應段 |
  | 帶案例敘事的 pattern | 既有 skill 本體加一行摘要；案例展開寫進該 skill 的 `references/<topic>.md` |
  | 專案限定知識（如 Airflow 案例） | 對應 repo-aware skill（如 `airflow-aware`）的本體或其 `references/`，**不進通用 skill** |
  | 自成一群的新慣例 | 先評估能否掛進相近既有 skill 的 `references/`；真的無處可掛才 `新建 skill <name>`（給建議 name + 一句 description + 預定 owner / consumer） |

  **併進優先**：落點預設先試「併進既有 skill / references」，新建 standalone skill 是
  last resort——避免 skill 增殖、控 context 成本。連「自成一群的新慣例」也先問能否掛進
  相近的既有 skill，而不是一律新建。

  **尺寸預算**：目的地 SKILL.md 本體超過 ~150 行時，預設改走 `references/`——
  本體留摘要與觸發條件，展開內容放 references 檔（progressive disclosure：
  SKILL.md 觸發就付 token，references 檔被 Read 才付）。

## Step 4 — 公開性檢查

**公開性檢查**（propose 前先跑，每筆候選都做）：

掃來源記憶 body，對照下列四類敏感內容：

- 私有專案名（不宜公開的內部 / 客戶專案代號）
- 個資（姓名以外的個人識別資訊、聯絡方式等）
- `~/...` 或其他本機絕對路徑
- 不宜公開的事件細節

命中任一類 → **預設把該段泛化改寫**（去識別化 / 抽象成通則），並在 propose 摘要加一行：

> 公開性檢查：命中 `<類別>`，已泛化改寫如下——[改寫後內容]

使用者確認的是**消毒後版本**，不是原始私密文字。使用者仍可在「修改方案」裡進一步調整改寫。

沒命中任何類別 → 在摘要加一行：`公開性檢查：通過` 帶過。

## Step 5 — 🎀 愛音實作 checklist

對 manifest 每一筆，走 repo 既有的
[**Add New Skill Checklist**](https://github.com/Lee-W/maigo/blob/main/docs/reference/skills.md#add-new-skill-checklist)
（不在此複製 spec，指向它就好）：

1. `skills/<name>/SKILL.md`（frontmatter `name` == 目錄名、內文含 `<!-- mkdocs-include-start -->`）
2. `docs/skills/<name>.md` include shim
3. `mkdocs.yml` 的 `Skills (source):` 段加一條
4. `docs/reference/skills.md` catalog 加一列（Owner / Consumers / 摘要）
5. 在 owner agent / command 的 prompt 加引用（若 manifest 指定了 consumer）

「併進既有 skill」的那幾筆只 Edit 目標 `SKILL.md` 加一段（落點是 `references/` 的，
本體加一行摘要 + 新增 / Edit 該 references 檔），跳過 1–4 的新建。
跨檔 link **一律用絕對 GitHub URL**，遵守
[`skills/doc-link-convention`](https://github.com/Lee-W/maigo/blob/main/skills/doc-link-convention/SKILL.md)——
dual-context 檔的相對 link 會炸 `mkdocs build --strict`。

## 中斷 / rollback 處理矩陣（atomic：skill side 綠才動 memory）

- **使用者在 propose / confirm 階段打斷 / 取消**：尚未委派愛音 → 不寫任何檔；
  回報「未畢業，已取消」。manifest 作廢。
- **skill side 驗證紅（validator 或 mkdocs strict）或爽世擋下**：愛音依
  failure-handling 重修；**在 skill side 轉綠前，orchestrator 不退役任何來源記憶**——
  記憶是知識的最後一份拷貝，skill 沒寫成就退役會讓知識消失。
- **批次中部分成功**：愛音回報哪幾筆綠、哪幾筆卡住。orchestrator **只退役綠的那幾筆**
  對應的來源記憶，卡住的 entry 維持原狀。
- **skill 已綠但退役記憶失敗**：skill 保留（已驗證綠），回報記憶層退役失敗，
  該 entry 維持原狀；不留半成品。
- **同名 skill 已存在但使用者選了「新建」**：propose 階段就額外 AskUserQuestion——
  `改成併進該既有 skill` / `換個 skill name` / `取消這筆`，再寫進 manifest。
