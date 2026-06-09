---
description: 把記憶層裡反覆出現、convention 形狀的條目，畢業成常駐 skill——orchestrator 主持逐筆 propose / 使用者確認，確認的批次委派 🎀 愛音寫 skill（quick 模式），綠後退役來源記憶。
---

<!-- mkdocs-include-start -->

# /maigo:crystallize

記憶層是**扁平、relevance-ranked、capped 10 筆**的事實儲存（見
[`skills/memory-loading`](https://github.com/Lee-W/maigo/blob/main/skills/memory-loading/SKILL.md)）。
但有些條目其實不是「一次性事實」，而是**反覆出現的慣例 / workflow / 規則**——
塞在 memory 裡每次只被當事實載入，相關條目一多還會被擠出前 10 筆。

crystallize 把這類條目「畢業」成常駐 **skill**：trigger 命中就一定在 context、
結構化、可被 command / agent 直接引用。這是 maigo 知識成熟度階梯往上爬一階的動作：

```
memory（單一事實，relevance-ranked、capped 10）
   ↓ 反覆出現、夠結構化、有明確 consumer  ← crystallize 走這一步
skill（共用 convention / workflow，trigger 命中就常駐）
   ↓ 失敗該整個 turn 擋下
hook（機器強制）
```

**分工**：互動的「挑候選 → 逐筆 propose → 使用者拍板」由 orchestrator + 旁白主持
（這段需要對話 context，不下放）；確認的畢業攢成一批，**寫 skill + 驗證那段委派
🎀 愛音**，照 [`/maigo:quick`](https://github.com/Lee-W/maigo/blob/main/commands/quick.md)
的輕量模式（愛音實作 + 輕量 🟡 爽世 4 項 review + 顯式驗證）。

為什麼這樣切：挑候選 / 確認天生是 orchestrator 的活；但「寫 SKILL.md + shim + mkdocs +
catalog 再跑 validator」是一個該被 review、被 verify 的 code change，不該 orchestrator 自己
偷雞。**批次**委派（不 per-entry spawn）是為了攤平冷啟動成本——一次 run 畢業幾條都只 spawn
愛音一次。

## 使用

```
/maigo:crystallize
```

（無參數——掃整個記憶層找畢業候選）

## 流程

### 1. 載入記憶層（全讀，不做 relevance 排序）

```
cat ~/.config/maigo/memory/MEMORY.md
```

讀 cross-project index 全文，再 `cat ~/.claude/projects/<current-project>/memory/MEMORY.md`
（若存在）讀 per-project index。

跟 [`skills/memory-loading`](https://github.com/Lee-W/maigo/blob/main/skills/memory-loading/SKILL.md)
的差別：那個 skill 為「當前 task」按相關性取前 10 筆；**crystallize 要掃全部**，
因為畢業候選跟當前 task 無關。Read 每個 index 行指向的 entry 全文。

Fallback：記憶目錄 / index 不存在或為空 → 印「記憶層是空的，沒有可畢業的條目」，結束。

### 2. 挑畢業候選（criteria）

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

掃完印一段 `## 畢業候選`，列出 N 個候選 + 每個的一句畢業理由。候選為 0 → 跳到步驟 7 的空結算。

### 3. 世界觀隔離 gate

每個候選 propose 前，先判斷它屬於哪個 plugin 的世界觀。

- **maigo 記憶只能畢業進 maigo skill。** 若候選描述的是 mujica（寫作 / 部落格審稿 /
  daily-plan 等）世界觀的慣例 → **不在此命令處理**，標記「跳過（mujica 世界觀，
  請在 mujica 端處理）」，不 propose。
- 共用底層（記憶層路徑、frontmatter schema）不算特定世界觀，可畢業進 maigo skill。

依據 [`maigo/mujica plugin 分工`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md)
的世界觀隔離原則。

### 4. 逐筆 propose + 使用者拍板

**一次只 propose 一筆**（不要一次列完讓使用者勾選——勾選 UI 鼓勵草率）。
對候選 #i / N：

印一段摘要：

- **來源**：記憶條目 `<slug>`（引用其 description / body）
- **畢業理由**：命中哪些 criteria
- **目的地**：
  - `新建 skill <name>`（給出建議 name + 一句 description + 預定 owner / consumer），或
  - `併進既有 skill <name> 的某段`（指出要 Edit 哪個 SKILL.md 的哪一段）
- **來源記憶處置**：`退役（刪 entry + 移除 index 行）` 或
  `留一行降級指針指向 skill`

**AskUserQuestion**，選項：
`畢業（新建 skill）` / `併進既有 skill` / `修改方案` / `跳過` / `結束 crystallize`。

- 回傳空 answers → **不可視為跳過**，必須用文字再次確認（見
  [`AskUserQuestion 無回應要文字再確認`] 慣例）。
- 「修改方案」→ 讓使用者改 name / description / 目的地 / 處置後再確認。

每筆確認後**記進批次清單**（manifest）一筆——`{來源 slug, 目的地 skill name, 新建 or 併進,
來源記憶處置}`——**先不寫任何檔**。處理完回步驟 3 的下一個候選，直到候選跑完或使用者「結束」。

### 5. 批次委派 🎀 愛音寫 skill（quick 模式，一次 spawn）

manifest 非空 → **一次** spawn 🎀 愛音，把整份 manifest 交給她，照
[`/maigo:quick`](https://github.com/Lee-W/maigo/blob/main/commands/quick.md) 的輕量模式跑
（不 per-entry spawn——攤平冷啟動）：

**🎀 愛音實作**——對 manifest 每一筆，走 repo 既有的
[**Add New Skill Checklist**](https://github.com/Lee-W/maigo/blob/main/docs/reference/skills.md#add-new-skill-checklist)
（不在此複製 spec，指向它就好）：

1. `skills/<name>/SKILL.md`（frontmatter `name` == 目錄名、內文含 `<!-- mkdocs-include-start -->`）
2. `docs/skills/<name>.md` include shim
3. `mkdocs.yml` 的 `Skills (source):` 段加一條
4. `docs/reference/skills.md` catalog 加一列（Owner / Consumers / 摘要）
5. 在 owner agent / command 的 prompt 加引用（若 manifest 指定了 consumer）

「併進既有 skill」的那幾筆只 Edit 目標 `SKILL.md` 加一段，跳過 1–4 的新建。
跨檔 link **一律用絕對 GitHub URL**，遵守
[`skills/doc-link-convention`](https://github.com/Lee-W/maigo/blob/main/skills/doc-link-convention/SKILL.md)——
dual-context 檔的相對 link 會炸 `mkdocs build --strict`。

**驗證（skill side 必須先綠）**——愛音寫完跑：

```
python3 scripts/validate_plugin.py     # stdlib-only → python3
uv run mkdocs build --strict           # venv 工具 → uv run
```

兩者皆綠才算寫成。（crystallize 的「測試」就是這兩條結構檢查——不靠 quick 的 Stop hook
跑單元測試兜底，因為畢業改的是 plugin 結構不是 code。）

**🟡 爽世輕量 review**——跑 strict-review 9 項中的 4 項（`mode=quick`，subset = 1 / 4 / 5 / 7），
額外盯 doc-link-convention 與 skill 形狀（frontmatter name == 目錄名、description 寫成
`This skill should be used when ...`）。詳見
[`/maigo:quick` 的 Soyo 輕量 checklist](https://github.com/Lee-W/maigo/blob/main/commands/quick.md)。

爽世擋下 / 驗證紅 → 把 must-fix 完整回給愛音重修，依
[`skills/failure-handling`](https://github.com/Lee-W/maigo/blob/main/skills/failure-handling/SKILL.md)
（2 次同條才停下找使用者）。

### 6. 退役來源記憶（orchestrator，skill side 綠後）

愛音批次綠回來後，orchestrator 對 manifest 每一筆按確認的處置處理來源 entry：

- **退役**：unlink `~/.config/maigo/memory/<slug>.md` + 從 MEMORY.md 移除該行
  （reuse [`/maigo:remember`](https://github.com/Lee-W/maigo/blob/main/commands/remember.md)
  步驟 6 的反向操作——刪 entry 檔 + 改 index）。
- **降級指針**：保留 MEMORY.md 該行但改 description 為
  `— 已畢業成 skill <name>，詳見該 skill`，並把 entry body 收斂成一句指針。

退役是 orchestrator 自己做（mirror remember / retro——記憶層寫入不下放給 agent）。

### 7. Summary + 🌑 Mortis 結算

印 summary：「本次 crystallize 畢業了 K 筆：`<slug1>` → skill `<name1>`、…」。

再加一行——把本次核心壓縮成**一句**（硬性 1 句、不感嘆號、不鼓勵語）：

```
🌑 Mortis：本次把散落的 <主題> 凝結成了 <name>。
```

候選為 0 / 一筆都沒畢業 → 跳過結算。

## 中斷 / rollback 處理（atomic：skill side 綠才動 memory）

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

## Orchestrator 守則

（流程細節見上面各步驟；以下只列貫穿全程的原則。）

- **旁白**：開場、收場、卡關節點由 🌙 Doloris / 🌑 Mortis 旁白，依
  [`skills/narration`](https://github.com/Lee-W/maigo/blob/main/skills/narration/SKILL.md)。
- **互動留 orchestrator、寫 skill 下放愛音**：挑候選 / propose / confirm / 退役記憶是
  orchestrator 的活（需對話 context，不下放）；寫 SKILL.md + shim + mkdocs + catalog + 驗證
  批次委派 🎀 愛音、review 交 🟡 爽世——不要自己寫 skill、自己 review。一次 spawn，不 per-entry。
- **不延伸推斷**：只畢業記憶層裡實際存在的條目，不順手補使用者「可能也想要」的 skill。
- **跟 retro 的關係**：[`/maigo:retro`](https://github.com/Lee-W/maigo/blob/main/commands/retro.md)
  把 session 學到的事**寫進** memory；crystallize 把夠成熟的條目**升階成** skill——前者餵養、後者收割。
