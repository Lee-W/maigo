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

## Delta re-review against a stored report

When a PR that's already been reviewed gets new commits or a new maintainer
review, don't restart from scratch — do a **delta re-review** against the
stored report:

1. Read the previous report (`files/.../review-<n>.md`) as baseline.
2. Pull the current `gh pr diff` + `gh pr view --json commits,reviewDecision`
   + existing human review threads (GraphQL `reviewThreads{isResolved,...}`
   plus reviews/comments).
3. Report, per finding:
   - **what changed since baseline** — which new commits (watch for a
     rebase; see below)
   - **finding-by-finding status** — each prior must-fix/should-fix as
     addressed / still-open / partial, with `file:line`
   - **maintainer thread state** — flag any `OPEN` thread that names you
   - **new concerns** introduced by the new commits
   - bottom line + updated verdict

Be precise relaying maintainer thread state: "author replied, awaiting
reviewer re-confirmation" is not the same as "no response" — GitHub's
`isResolved: false` often just means nobody has clicked Resolve yet.

### Establish the delta with a two-step check — not `gh pr diff`, not a raw commit range

"What changed since the stored report" is **not** any of:

- `gh pr diff <n>` / `gh pr diff --name-only` — that's the **whole PR vs
  `main`**, not the delta since the report's `<oldSha>`.
- A pasted GitHub `.../changes/<oldSha>..<newSha>` range — see below, it
  often carries rebase/merge noise.
- `git log <old>..<new>` — only meaningful when `<old>` is actually an
  ancestor of `<new>`.

Two-step check, run before handing a delta re-review to a subagent (put the
resolved SHAs in the delegation prompt, not the stale ones from the stored
report):

```bash
git merge-base --is-ancestor <old_head> <new_head>        # 1. not an ancestor → old..new is unreliable
git log --format='%h %ad %s' --date=short <old>..<new>    # 2. read the dates
```

1. **Ancestor check.** After a force-push/rebase, the old head is no longer
   an ancestor of the new one — `old..new` then lists rebase-rehashed *old*
   content as if it were new commits.
2. **Date check.** Any commit dated before the stored report's review date
   cannot be a response to that review — the cheapest check, and the one most
   often skipped.

For the real content delta, use `git diff --stat <old> <new>`; an implausibly
large file count (hundreds+) means the range still contains a `main` merge —
fall back to reading the actual `git log` commits.

**Case studies** (apache/airflow, three same-session recurrences of this
mistake):

- **PR #70671** — `gh pr diff` read as the delta led to asserting the author
  had responded to three must-fix items and possibly changed design
  direction. `git diff --stat <old> <new>` showed only one new Markdown file
  (+124 lines); the seven previously-reviewed source files were
  byte-identical to the head already reviewed.
- **PR #58543** — `git log old..new` listed 4 "new" commits.
  `merge-base --is-ancestor` returned NO (the branch had been rebased); one
  of the 4 had a commit message identical to the old head's tip (same
  content, rehashed), and 3 of the 4 were dated before the review — only 1
  was genuinely new.
- **PR #68778** — a subagent given a stale worktree SHA in its delegation
  prompt noticed on its own that the head had moved and re-fetched before
  reviewing — a fallback that caught the mistake, not a substitute for
  running the two-step check upfront.

### A `<oldSha>..<newSha>` compare range spanning a rebase is noise

A pasted GitHub `.../changes/<oldSha>..<newSha>` range that spans a
**rebase / merge-main-into-branch** makes `gh api compare/<old>...<new>`
list the entire intervening `main` history (doc links, dependency bumps,
unrelated PRs) — not the PR's own delta. Before treating that range as "the
PR's new change," check whether its `.commits` include commits that
obviously belong to a different, unrelated PR
(`gh api compare/<old>...<new> --jq '.commits[].commit.message'`). If so,
it's a rebase — use the current `gh pr diff <n>` (against `main`) instead to
see the PR's actual delta.
