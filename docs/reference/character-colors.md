# 角色代表色

MyGO!!!!! 五位角色在 maigo 的 canonical 代表色，套用於 [Commands (source)](https://github.com/Lee-W/maigo/tree/main/commands) 的 mermaid 圖 `classDef`。改色從這裡改，再同步到 4 張 mermaid 圖。

| Class | 角色 | 樂團位置 | Fill (hex) | Stroke | Color |
|---|---|---|---|---|---|
| `raana` | 要 樂奈 | Gt | `#6EEB83` | `#333` | `#000` |
| `tomori` | 高松 燈 | Vo | `#6EC1E4` | `#333` | `#000` |
| `anon` | 千早 愛音 | Gt | `#FF6F91` | `#333` | `#000` |
| `soyo` | 長崎 爽世 | Ba | `#FFC857` | `#333` | `#000` |
| `taki` | 椎名 立希 | Dr | `#7A5CFF` | `#333` | `#fff` |

色票來源：原作兩位元色。立希紫色較深，文字 `color` 用白色保證對比。

## 套用位置

4 張 command mermaid 圖各自頭尾都列了完整 5 個 `classDef` header（即使該圖只用部分角色）：

- [`commands/go.md`](https://github.com/Lee-W/maigo/blob/main/commands/go.md) — 五人全套
- [`commands/team.md`](https://github.com/Lee-W/maigo/blob/main/commands/team.md) — 五人全套
- [`commands/fix.md`](https://github.com/Lee-W/maigo/blob/main/commands/fix.md) — 僅 Anon / Soyo 有 `class` 賦值
- [`commands/review.md`](https://github.com/Lee-W/maigo/blob/main/commands/review.md) — Raana / Tomori / Soyo / Taki 有賦值

`commands/remember.md` 與 `commands/retro.md` 的 mermaid 圖無人物 node，不套色。
