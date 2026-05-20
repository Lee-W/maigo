---
name: github-title-description
description: This skill should be used when drafting a GitHub PR title and description from a branch's commits and diff. It produces a user-impact title (not conventional-commits formatted) and a Summary / Motivation / Test plan body with optional Breaking changes / Related issues sections.
---

<!-- mkdocs-include-start -->

# GitHub Title & Description

**Owner Agent**: orchestrator（`/maigo:describe-pr` 直跑，不 delegate）
**Consumers**: [`/maigo:describe-pr`](https://github.com/Lee-W/maigo/blob/main/commands/describe-pr.md)

## Why this skill exists

PR title / description 是 reviewer 對這次變更的第一印象。常見的失敗：
- title 抄最後一個 commit message（內部視角，reviewer 看不出價值）
- description 只寫「改了 X / Y / Z」（檔案清單 reviewer 自己看 diff 就有）
- 沒講為什麼（reviewer 得逆向工程動機）
- 沒講怎麼驗證（reviewer 得自己想 test scope）

這個 skill 把這四件事變成有結構的 process。

## Inputs（caller 必須給 / 自己抓的東西）

1. **Base branch**（通常 `main`；caller 可覆寫）
2. **Branch commits**：`git log <base>..HEAD --pretty=format:'%h %s%n%b' --no-merges`
3. **Branch diff stat**：`git diff <base>...HEAD --stat`
4. **Branch diff**：`git diff <base>...HEAD`（必要時 truncate）
5. **Repo commit-style 偵測**（決定要不要參考既有 commit message 風格）：
   - `pyproject.toml` 有 `[tool.commitizen]` → conventional commits
   - 有 `.cz.toml` / `.cz.json` / `cz.yaml` → conventional commits
   - 有 `commitlint.config.js` / `.commitlintrc*` → 通常 conventional commits
   - 都沒有 → 自由格式
   - **這只影響 commit message 風格參考；PR title 本身永不套 `type:` prefix。**
6. **PR template（若存在）**：caller 在 `.github/PULL_REQUEST_TEMPLATE.md`（含大小寫變體與 `.github/PULL_REQUEST_TEMPLATE/` 目錄）找到的 template 內容。
   - 找到 → 以 template 結構作為描述框架，填入從 commits / diff 萃取的內容，取代預設的 Summary / Motivation / Test plan 結構
   - 找不到 → 用本 skill 預設結構

## Title 規則（user-impact 句子）

- **一句話、user 視角**：寫「使用者 / reviewer 看完會知道這 PR 做了什麼」
- **開頭大寫**（英文）；中文無此限
- **不加 conventional-commits prefix**（不要 `feat: `、`fix: `）
- **長度建議 ≤ 72 字**（GitHub UI 一行不截斷）
- **不寫檔名**：「Refactor `auth.py`」← bad；「Reject empty emails before hashing」← good
- **動詞開頭** 比名詞開頭更直接（「Add X」、「Fix Y」、「Allow Z」）

### Bad → Good 對照

| Bad | Good |
|-----|------|
| `feat: add email validator` | `Reject empty emails at signup` |
| `update auth.py and tests` | `Block login when MFA token expired` |
| `WIP fix` | `Stop retry storm on 5xx from upstream` |

## Description 結構

**必填三段**：

```markdown
## Summary
<2–4 句：這個 PR 改了什麼行為。reviewer 讀完就知道要看什麼。>

## Motivation
<為什麼要做：bug repro / 痛點 / 觸發場景。可以引用 issue / 對話 / log。>

## Test plan
- <怎麼驗證：跑了哪些 test / 手動測了什麼 / 看了哪個 metric>
- <command + 預期結果>
```

**可選段（有才加，不要為了塞而塞）**：

```markdown
## Breaking changes
<API / config / behaviour 改了什麼會打破既有 caller。沒有就不加這段。>

## Related issues
- Closes #<n>
- Refs #<n>
```

**若 repo 有 PR template**（Inputs 第 6 條）：
- 以 template 的 section 結構作為描述框架
- 用 commits / diff 萃取的內容填入對應 section
- template 內原有的 checklist / 說明文字保留在適當位置
- 不要增加 template 沒有的 section；不要刪掉 template 要求的 section

## 怎麼從 commits / diff 萃取這四段

| 段落 | 訊號來源 |
|------|---------|
| Summary | branch commits 的主旨合併 + diff 摘要的 net effect |
| Motivation | commit body 裡的「why」段、PR 描述對話、issue link |
| Test plan | diff 裡新增 / 改動的 test 檔 + 推測的手動驗證 |
| Breaking changes | public API signature 改變、config key 改名、預設值翻轉 |
| Related issues | commit message 裡的 `#<n>` / `Closes #<n>` / `Refs #<n>` |

**找不到 signal 不要編造**——標記 `<待補：...>` 留給使用者填，不要 hallucinate。

## Output format

skill 跑完直接給 caller 兩塊 markdown：

```markdown
## Suggested PR title

<one line, user-impact>

## Suggested PR description

## Summary
...

## Motivation
...

## Test plan
- ...

## Breaking changes  <!-- 若無，整段刪 -->
...

## Related issues  <!-- 若無，整段刪 -->
- Closes #...
```

## What this skill does NOT cover

- 開 PR（這是 caller / 使用者 的 `gh pr create` 或 GitHub UI）
- 寫 commit message（skill 只看既有 commits）
- 改 commit history（rebase / squash 不是這裡的事）
- 跑 test（test plan 是「描述要跑什麼」，不是跑它）
