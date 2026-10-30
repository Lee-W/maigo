---
name: python-aware
description: This skill should be used when writing, testing, or reviewing Python code — in any repository. It is the Python language layer: toolchain habits, coding rules, and pytest/mock conventions that hold regardless of the repo. Repo-aware skills such as airflow-aware and commitizen-aware compose it; strict-review reads it when a diff contains Python.
---

<!-- mkdocs-include-start -->

# Python-Aware

**Loaded by**: composed by repo-aware skills (`airflow-aware`, `commitizen-aware`); read by `strict-review` when a diff contains Python; may also trigger from its description during any Python work.
**Applies to**: Writing, testing, or reviewing Python code in any repository.

## When to apply

This is a **knowledge layer**, not a review checklist. It holds Python language and
toolchain conventions that stay true no matter which repo you are in. Anything that only
holds for one repository (its class names, directory layout, CI matrix, custom tooling)
belongs in that repo's `<repo>-aware` skill, not here.

Once loaded, treat every convention as background — do not re-read each task.

## Layering & precedence

1. The repo's own `AGENTS.md` / `CLAUDE.md` (and contributor docs) — always wins.
2. The repo-aware skill (`airflow-aware`, `commitizen-aware`, …).
3. This skill — the default when nothing above says otherwise.

A repo-aware skill that wants to change a default here must say so explicitly
(an "override: …" line); silence means the default below applies.

## Toolchain

- **Use the repo-managed environment** (`uv run …`, or whatever the repo specifies) — never the
  host's globally installed `pytest`, `mypy`, or `ruff`; they run a different version than CI.
- **Hook runner**: if the repo uses `prek`, run `prek`, not `pre-commit`. Hook-runner behavior
  that produces false greens (stash, `git add -N`, `rebase --continue`, wrong `files:` regex) is
  language-neutral — see
  [`hook-runner-verification.md`](https://github.com/Lee-W/maigo/blob/main/skills/git-workflow/references/hook-runner-verification.md).
- **Ruff**: `ruff format` then `ruff check --fix`, with the repo's own configuration
  (line length, rule selection) — do not impose defaults.
- **`uv.lock` diff you did not cause**: if it returns after `git checkout HEAD -- uv.lock` plus
  the next `uv sync`, suspect lockfile drift already on `main` (someone edited a
  `pyproject.toml` without re-running `uv lock`), not your environment. Keep the re-lock out
  of a feature PR.
- **pytest config**: prefer `[tool.pytest]` (pytest 9.0+ reads it natively) over
  `[tool.pytest.ini_options]`; this needs `requires-python >= 3.10`.

## References index

| Reference | Read when |
|---|---|
| `references/code-style.md` | Writing or reviewing Python style: import placement and aliasing, naming and constants, raise-vs-document validation, `ContextVar` in async generators, mypy narrowing, docstring conventions, subprocess `returncode` checks |
| `references/test-conventions.md` | Writing or reviewing tests and one of the named patterns below applies (mock assertions, parametrize, reject-path shapes, tripwires, class-attribute / stub-shape / codespell traps, unix-socket path length…) — full rationale and recipes |
| `references/runtime-gotchas.md` | Code that passes a type checker and a casual read but misbehaves at runtime: pydantic `Annotated` constraints, nested enums, subscripted generics, `Decimal` → `int`, chained `.append()` on an ORM query result (weak identity map) |
| `references/tooling.md` | Dependency-floor bumps that make a stale venv go red, several agents sharing one worktree `.venv`, a script a hook runner executes directly, or measuring coverage with `--cov` |

## Coding rules

- **No `assert` in production code** — raise a real exception (`ValueError`, `RuntimeError`, …);
  `assert` disappears under `python -O`.
- **`time.monotonic()` for elapsed time** — not `time.time()`, which can jump.
- **Imports go at the top of the file** by default, including in `__init__` and any function
  that runs on every public touch of a class. Use the function-body form for exactly four cases:
  (1) a `TYPE_CHECKING` block, (2) breaking a known circular-import cycle, (3) a multi-process
  worker-isolation path, (4) a deferred-execution callback (a body not called at module import
  time). Say which case it is in a comment.
  Self-check: "does this function run on every public touch of the class?" If yes, top-level.
  Never re-import, inside a function, a name the module already imports at top level; a test
  file is not an exception (`references/code-style.md` → Imports).
- **Name threshold constants for the bound they encode**, not the use site, cite the value's source in a comment, and never reuse one constant as two thresholds — `references/code-style.md`.

## Testing

- **pytest only** — do not subclass `unittest.TestCase`.
- **Every mock carries `spec=` or `autospec=True`** — a bare `MagicMock()` is allowed only for a
  logger attribute (`instance._log = mock.MagicMock()`); exact rule in `references/test-conventions.md`.
- **Time-dependent tests use the repo's existing time-travel library** (`time_machine`,
  `freezegun`, …) — do not monkey-patch `datetime.now` by hand.
- **Mock assertions: prefer `.mock_calls` equality** — `m.method.mock_calls == [mock.call(...)]`
  expresses "called exactly once, with these arguments, and nothing else" in one assertion, and
  pytest diffs it directly. Use the child-mock form (`m.method.mock_calls`), not the parent's.
  A repo that standardizes on `assert_called_once_with` can say so as an explicit override.
- **Parametrize by default** — stacked asserts or near-duplicate test methods are must-fix in review;
  split into `@pytest.mark.parametrize` with `pytest.param(..., id=...)` naming each case, and extract
  repeated setup/cleanup into a fixture.
- **Full-sequence assertions** — assert the whole iterable/list, not head + tail + length.
- **Cap-boundary pairs** — a numeric cap needs both an at-cap (allowed) and a one-over-cap (trips) test.
- **No thin test helpers** — assert only the field the function under test decides; skip one-use wrapper helpers.
- **Minimize forced test churn** — keep an existing test's diff to the forced minimum; add a new test for new behavior.
- **Build the fixture, don't defer** — a missing example fixture is not "can't test"; build the smallest purpose-built one.
- **Drift guard green in its own commit** — the commit that adds an "every X needs an entry" test
  must add the existing entries and doc rows too, or it fails when checked out alone.
- **Private SDK path: fail, don't skip** — a test that depends on a third-party SDK's private
  module `pytest.fail`s when the path is missing; a skip hides the gap behind a green CI.
- **Tripwire tests: prove which assertion fails, name the component** — mutate one deny-list
  entry and name the assertion that turns red; a test name must not credit a rejection that only
  a downstream function performs.
- **Log assertion when the log IS the observable** — a repo rule against `caplog` targets
  scraping raw log text, not asserting an operator-visible log call via a mocked logger.
- **A reviewer's concrete repro becomes a named parametrize case** even if it already passes (check it goes red on the base, else say which mutation it guards), and **a test that needs `# type: ignore[arg-type]` to feed a documented value means the signature and docs disagree** — fix annotation, docstring and docs together; both in `references/test-conventions.md`.

Worked examples and the rest of the named patterns (parametrize + shared fixtures,
reject-path shapes, prose-guard windows) are in `references/test-conventions.md`.

## Composing with other skills

- **`strict-review`**: when the diff contains Python, the Testing and Coding rules sections above
  strengthen base review items 3–6. Raise a violation as a finding with the rule named; the recipe
  detail lives in `references/test-conventions.md`.
- **Repo-aware skills** (`airflow-aware`, `commitizen-aware`): they declare "read python-aware first"
  and list only what differs. If a repo-aware rule and a rule here conflict, the repo-aware rule
  wins when it is written as an explicit override; the repo's `AGENTS.md` beats both.
- Layering guidance for adding another language layer:
  [`docs/reference/skills.md`](https://github.com/Lee-W/maigo/blob/main/docs/reference/skills.md).
