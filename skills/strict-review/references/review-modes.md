# Strict Review — `/maigo:review` Mode & Bilingual Reference

Loaded on demand by [`commands/review.md`](https://github.com/Lee-W/maigo/blob/main/commands/review.md) —
full semantics for `--mode` / `--bilingual`: the mode-to-checklist-subset table, how the
orchestrator threads mode into the rubric and into Soyo / Taki prompts, and the bilingual
output trigger + Taiwanese Mandarin prose rules. Read this file when parsing `--mode=*` /
`--bilingual` or deciding whether to skip the Taki stage.

---

## Mode 對照表

| Mode | Soyo checklist | Taki 跑驗證？ | 適用場景 |
|------|----------------|---------------|----------|
| `full`（預設） | 9 項全跑 | ✅ | 一般 PR review |
| `design-preview` | 只跑 1 + 4 | ❌ skip | 早期設計討論、介面預審 |
| `compliance-only` | 只跑 4 / 5 / 6 / 7 / 8 | ✅ | 安全 audit、規範對焦 |

`--bilingual` 是**輸出格式 flag**，跟上面三個 mode 正交——可以跟 `--mode=*` 同時用。
偵測到 `apache/airflow` checkout（`hooks/repo_detect.py` 已 load airflow-aware）時 orchestrator 預設啟用 `--bilingual`，不必手動加旗標。

## Mode 旗標處理

Orchestrator 在啟動 Soyo / Taki 前先解析 `--mode` 與 `--bilingual`：
- 把 mode 名稱寫進 review-rubric.md 開頭 `<!-- mode: <mode-name> -->` 註解，讓 Soyo / Taki 啟動時讀得到
- Soyo 收到 prompt 時被明確告知 checklist subset（mirror `skills/strict-review/SKILL.md` 「Adapting per context」表的寫法——standard 9 項保持，只是把不在 subset 的項在輸出表標 `[—]` 而非 `[x]` / `[ ]`，附 reason「skipped by mode=<name>」）
- mode = `design-preview` → 不啟動 Taki stage；最終報告 Verification 段註記「Skipped (mode=design-preview)」
- mode = `compliance-only` → 正常啟動 Taki stage（與 full mode 相同）
- `--bilingual` 旗標**或** repo-detect 回報 `apache/airflow` → orchestrator 在最終 report 前面加一段 Taiwanese Mandarin 快結（見「## 雙語輸出」）；不影響 Soyo / Taki 行為

## 雙語輸出

`--bilingual` 旗標或 repo-detect 自動觸發時，最終 report 在前面加一段 **Taiwanese Mandarin 快結**（1-3 句），後面接英文 detail。版型範本見 `skills/strict-review/references/review-templates.md` 的「雙語版」小節；本段只定行文規範。

zh-TW 行文規範（通用，跨專案）：

- **「Taiwanese Mandarin」**，不寫「Traditional Chinese」
- 三個以上 item 不要 inline `(1)…(2)…(3)…`，拆 bullets
- 中英文之間留一個半形空格；不雙空格
- 技術名詞英文穿插無妨（PR / merge / refactor / cache / token / scheduler）

Repo-specific 命名規範（例如 Airflow 的 `Dag` title case + code token 例外）由各 repo 的 domain skill 負責（如 `airflow-aware` §2），這裡不重述——`--bilingual` 自動觸發那條路徑下 domain skill 已經被 repo-detect 載入。
