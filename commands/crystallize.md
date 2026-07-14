---
description: 把記憶層裡反覆出現、convention 形狀的條目，畢業成常駐 skill——orchestrator 主持逐筆 propose / 使用者確認，確認的批次委派 🎀 愛音寫 skill（quick 模式），綠後退役來源記憶。
---

<!-- mkdocs-include-start -->

# /maigo:crystallize

> 🌙 Doloris：「請讓散落的記憶在今夜結晶；往後的路，不必再由偶然照亮。」

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

對每筆 entry 套一組準則，**全中才是候選**：形狀是 convention / workflow / 規則（非一次性事實）、
有明確 consumer、有反覆性 signal；額外強訊號與排除規則見
`skills/maigo-self-check/references/skill-graduation.md`「Step 2 — 挑畢業候選：criteria 細節」。

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
- **目的地**（先過落點決策表——條目形狀對應的落點、併進優先原則、~150 行尺寸預算，見
  `skills/maigo-self-check/references/skill-graduation.md`「Step 4 — 目的地決策表」）
- **來源記憶處置**：`退役（刪 entry + 移除 index 行）` 或
  `留一行降級指針指向 skill`

**AskUserQuestion**，選項：
`畢業（新建 skill）` / `併進既有 skill` / `修改方案` / `跳過` / `結束 crystallize`。

- 回傳空 answers → **不可視為跳過**，必須用文字再次確認（見
  [`AskUserQuestion 無回應要文字再確認`] 慣例）。
- 「修改方案」→ 讓使用者改 name / description / 目的地 / 處置後再確認。

**隱私檢查**（propose 前先跑，早於公開性檢查，每筆候選都做）：條目內容含以下任一者，
預設**不畢業**進公開 skill（留在記憶層，或建議使用者轉 mujica 私有層）：

1. 生活細節（行程、健康、作息、消費、閱讀 / 娛樂紀錄）
2. 可識別的個人資訊（住處、工作內部資訊、人際關係）
3. 使用者私人系統的結構或內容（Reminders 清單名、MWeb 筆記內容、帳號資訊）

技術慣例 / 工具用法 / 語言用詞規範（例如台灣漢語用詞、指稱中國一律寫「中國」的命名規範）
屬事實準確與寫作規範，非隱私敏感，**不得**歸類為「立場偏好」而攔下。

propose 給使用者的 AskUserQuestion 摘要須標明本筆的隱私檢查結果：
「隱私檢查：通過」或「隱私檢查：攔下（理由）」。

**公開性檢查**（隱私檢查通過後才跑，每筆候選都做）：掃來源記憶 body 對照四類敏感內容
（私有專案名 / 個資 / 本機絕對路徑 / 不宜公開的事件細節），命中即預設泛化改寫、
在摘要標註；沒命中則標「通過」。完整分類與改寫格式見
`skills/maigo-self-check/references/skill-graduation.md`「Step 4 — 公開性檢查」。

每筆確認後**記進批次清單**（manifest）一筆——`{來源 slug, 目的地 skill name, 新建 or 併進,
來源記憶處置}`——**先不寫任何檔**。處理完回步驟 3 的下一個候選，直到候選跑完或使用者「結束」。

### 5. 批次委派 🎀 愛音寫 skill（quick 模式，一次 spawn）

manifest 非空 → **一次** spawn 🎀 愛音，把整份 manifest 交給她，照
[`/maigo:quick`](https://github.com/Lee-W/maigo/blob/main/commands/quick.md) 的輕量模式跑
（不 per-entry spawn——攤平冷啟動）：

**🎀 愛音實作**——對 manifest 每一筆，走 repo 既有的
[**Add New Skill Checklist**](https://github.com/Lee-W/maigo/blob/main/docs/reference/skills.md#add-new-skill-checklist)
（不在此複製 spec，指向它就好）；5 步驟清單、「併進既有 skill」的簡化路徑、跨檔 link 規範，見
`skills/maigo-self-check/references/skill-graduation.md`「Step 5 — 🎀 愛音實作 checklist」。

**驗證（skill side 必須先綠）**——愛音寫完依
[`skills/maigo-self-check`](https://github.com/Lee-W/maigo/blob/main/skills/maigo-self-check/SKILL.md)
跑：

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

核心原則：**在 skill side（validator + mkdocs strict + Soyo）轉綠前，orchestrator 不退役任何
來源記憶**——記憶是知識的最後一份拷貝，skill 沒寫成就退役會讓知識消失。propose/confirm 階段
打斷、驗證紅、批次部分成功、退役失敗、同名 skill 衝突等各情況的完整處置矩陣見
`skills/maigo-self-check/references/skill-graduation.md`「中斷 / rollback 處理矩陣」。

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
- **公開性把關**：私有記憶畢業進公開 repo 前一律過公開性檢查，預設泛化改寫——不把本機路徑 / 個資 / 私有專案名原樣入庫。
