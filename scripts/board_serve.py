#!/usr/bin/env python3
"""
Serve `.maigo/board.md`（與同目錄下其它 `.md`，如 review report）為一個會
live reload 的本地網站（work-board 閱讀層 v3）。

跑：`python3 scripts/board_serve.py [.maigo 路徑] [--addr HOST:PORT]`
預設 `.maigo`、`localhost:8000`。

首跑會在 `.maigo/_serve/`（gitignored 工作區，不是真相層）生成最小 mkdocs
scaffold（`mkdocs.yml` ＋ `board-style.css`）；舊版未修改的 scaffold 會自動升級，
使用者自訂版則保留並提示手動合併。
`docs_dir` 直指 `.maigo/` 本身——`.maigo/board.md` 原封不動當作真相層來源，
`_serve/` 本身用 `exclude_docs` 排除掉那份 `mkdocs.yml` 不外流，其餘 `.maigo/*.md`
（review report 等 `📄` 連結的產物）由同一個 server 直接渲染。

啟動優先序：
1. cwd 專案的 venv 已裝 mkdocs-material 與 pymdown-extensions
   → `uv run mkdocs serve -f <config>`
2. 否則 → `uvx --from mkdocs-material --with pymdown-extensions mkdocs serve -f <config>`
   （zero repo 相依；checkbox 渲染要的 `pymdownx.tasklist` 來自
   `pymdown-extensions`，一併帶上，其他 repo 的 `.maigo/` 一樣可用）

checkbox（`- [ ]`）用 `pymdownx.tasklist` 渲染成真正的 `<input type="checkbox">`，
不會退化成純文字。MkDocs 只有 `docs_dir`（＝ `.maigo/`）根目錄真的有一個叫
`index.md` 的檔案時才會產生根目錄首頁；首跑因此連帶生成
`.maigo/index.md`，內容純粹是重導向到 `board/`，每次 scaffold 都直接覆寫，
不算真相層內容。

python3 stdlib-only：不 import 任何第三方套件；只用 subprocess 呼叫 uv/uvx。
serve 本體會一直跑在前景直到使用者 Ctrl-C，回傳其 exit code。
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SERVE_DIRNAME = "_serve"
CONFIG_NAME = "mkdocs.yml"
CSS_NAME = "board-style.css"
JS_NAME = "board-interactions.js"
SCAFFOLD_VERSION = 7
V3_CSS_SHA256 = "00ca2aabe9c85d5d73a5b6b16cf2f31a4acff990bcaefa7bc57a8fca5c9749b8"
V4_CSS_SHA256 = "6f578df0d1a502058fc711ed41d31e880112a87cdfb8b9c83e5024a0f1e9937e"
V5_CSS_SHA256 = "30be21255dc29eb1c74bd4915f07a1d1d49108d9c59618759792bf3c1542b853"
V6_CSS_SHA256 = "ea2a345279372172ebf68d4049270a74ce20d0dbccd3ab4fb142f115e0602f85"

CONFIG_TEMPLATE = """\
# maigo-board-scaffold: {version}
site_name: Work Board
docs_dir: ..
site_dir: {site_dir}
theme:
  name: material
  language: zh-TW
  features:
    - navigation.instant
    - navigation.sections
  palette:
    - media: "(prefers-color-scheme: light)"
      scheme: default
      primary: indigo
      accent: indigo
    - media: "(prefers-color-scheme: dark)"
      scheme: slate
      primary: indigo
      accent: indigo
nav:
  - 工作板: board.md
not_in_nav: |
  *.md
hooks:
  - {hook_path}
extra_css:
  - {serve_dirname}/{css_name}
extra_javascript:
  - {serve_dirname}/{js_name}
exclude_docs: |
  {serve_dirname}/{config_name}
markdown_extensions:
  - md_in_html
  - pymdownx.tasklist:
      custom_checkbox: true
"""

CSS_TEMPLATE = """\
/* maigo-board-scaffold: 7
   maigo work-board serve 樣式——首跑自動生成，改壞了刪掉這個檔案，
   下次跑 board_serve.py 會重新生成預設版本；正常改動請直接編輯這個檔案。 */
:root {
  --board-border: color-mix(in srgb, var(--md-default-fg-color) 16%, transparent);
  --board-muted: color-mix(in srgb, var(--md-default-fg-color) 62%, transparent);
}
.md-grid {
  max-width: 92rem;
}
.md-content__inner > blockquote:first-of-type {
  margin: 0 0 1.75rem;
  padding: 0.8rem 1rem;
  border: 1px solid var(--board-border);
  border-left: 0.25rem solid var(--md-accent-fg-color);
  border-radius: 0.45rem;
  background: color-mix(in srgb, var(--md-accent-fg-color) 7%, transparent);
}
.work-table-wrap {
  width: 100%;
  margin: 0.5rem 0 2rem;
  overflow-x: auto;
  border: 1px solid var(--board-border);
  border-radius: 0.55rem;
}
.md-typeset .work-table {
  display: table;
  width: 100%;
  min-width: 58rem;
  margin: 0;
  border: 0;
  font-size: 0.88rem;
}
.md-typeset .work-table th {
  padding: 0.65rem 0.75rem;
  border: 0;
  border-bottom: 1px solid var(--board-border);
  background: color-mix(in srgb, var(--md-default-fg-color) 5%, transparent);
  color: var(--board-muted);
  font-weight: 650;
  white-space: nowrap;
}
.md-typeset .work-table td {
  padding: 0.8rem 0.75rem;
  border: 0;
  border-bottom: 1px solid var(--board-border);
  vertical-align: top;
}
.md-typeset .work-table tbody tr:last-child td {
  border-bottom: 0;
}
.md-typeset .work-table tbody tr:hover {
  background: color-mix(in srgb, var(--md-accent-fg-color) 5%, transparent);
}
.handled-cell {
  width: 4.5rem;
  text-align: center !important;
}
.item-cell {
  width: 23%;
}
.author-cell {
  width: 8rem;
}
.diff-cell {
  width: 6.5rem;
  white-space: nowrap;
}
.status-cell {
  width: 9rem;
}
.reason-cell {
  width: 26%;
}
.next-cell {
  width: 21%;
}
.learn-checkbox {
  width: 1rem;
  height: 1rem;
  accent-color: var(--md-accent-fg-color);
}
.work-item-title {
  margin-bottom: 0.2rem;
  font-weight: 700;
}
.work-item-id {
  white-space: nowrap;
}
.work-title {
  line-height: 1.4;
}
.work-meta,
.muted {
  margin-top: 0.2rem;
  color: var(--board-muted);
  font-size: 0.8rem;
}
.work-status {
  display: inline-block;
  padding: 0.12rem 0.42rem;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 700;
  line-height: 1.4;
  white-space: nowrap;
}
.status-blocked {
  background: color-mix(in srgb, #e53935 16%, transparent);
  color: #c62828;
}
.status-act {
  background: color-mix(in srgb, #ef6c00 16%, transparent);
  color: #d65f00;
}
.status-wip {
  background: color-mix(in srgb, #1565c0 16%, transparent);
  color: #1565c0;
}
.status-wait {
  background: color-mix(in srgb, var(--md-default-fg-color) 9%, transparent);
  color: var(--md-default-fg-color);
}
.status-done {
  background: color-mix(in srgb, #2e7d32 16%, transparent);
  color: #2e7d32;
}
.status-unknown {
  background: color-mix(in srgb, #e53935 8%, transparent);
  color: #c62828;
  border: 1px solid #c62828;
}
.stale {
  margin-left: 0.15rem;
  font-size: 0.8rem;
}
[data-md-color-scheme="slate"] .status-blocked { color: #ff8a80; }
[data-md-color-scheme="slate"] .status-act { color: #ffb36b; }
[data-md-color-scheme="slate"] .status-wip { color: #82b1ff; }
[data-md-color-scheme="slate"] .status-wait { color: var(--md-default-fg-color); }
[data-md-color-scheme="slate"] .status-done { color: #80d88a; }
[data-md-color-scheme="slate"] .status-unknown { color: #ff8a80; border-color: #ff8a80; }
.work-command {
  display: block;
  width: fit-content;
  max-width: 100%;
  margin-bottom: 0.4rem;
  overflow-wrap: anywhere;
  white-space: normal;
}
.artifact-link {
  display: inline-block;
  margin-bottom: 0.45rem;
  font-size: 0.82rem;
}
.row-actions {
  position: relative;
  width: fit-content;
  margin-top: 0.35rem;
  font-size: 0.8rem;
}
.row-actions summary {
  color: var(--md-accent-fg-color);
  cursor: pointer;
  list-style: none;
  user-select: none;
}
.row-actions summary::-webkit-details-marker {
  display: none;
}
.row-actions-menu {
  display: grid;
  min-width: 8rem;
  margin-top: 0.3rem;
  overflow: hidden;
  border: 1px solid var(--board-border);
  border-radius: 0.35rem;
  background: var(--md-default-bg-color);
  box-shadow: 0 0.25rem 0.8rem rgba(0, 0, 0, 0.14);
}
.copy-command {
  padding: 0.4rem 0.55rem;
  border: 0;
  border-bottom: 1px solid var(--board-border);
  background: transparent;
  color: var(--md-default-fg-color);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.copy-command:last-child {
  border-bottom: 0;
}
.copy-command:hover {
  background: color-mix(in srgb, var(--md-accent-fg-color) 8%, transparent);
}
.drop-command {
  color: #c62828;
}
[data-md-color-scheme="slate"] .drop-command {
  color: #ff8a80;
}
.learned {
  margin-left: 0.15rem;
  font-size: 0.8rem;
}
.diff-add {
  color: #2e7d32;
  font-variant-numeric: tabular-nums;
}
.diff-delete {
  color: #c62828;
  font-variant-numeric: tabular-nums;
}
[data-md-color-scheme="slate"] .diff-add { color: #80d88a; }
[data-md-color-scheme="slate"] .diff-delete { color: #ff8a80; }
.work-controls {
  display: flex;
  align-items: end;
  gap: 0.65rem;
  margin: 0 0 1.5rem;
  padding: 0.8rem;
  border: 1px solid var(--board-border);
  border-radius: 0.55rem;
  background: color-mix(in srgb, var(--md-default-fg-color) 3%, transparent);
}
.work-controls label {
  display: grid;
  gap: 0.2rem;
  min-width: 8.5rem;
  color: var(--board-muted);
  font-size: 0.75rem;
}
.work-controls .search-control {
  flex: 1;
  min-width: 12rem;
}
.work-controls input,
.work-controls select,
.work-controls button {
  min-height: 2rem;
  padding: 0.3rem 0.55rem;
  border: 1px solid var(--board-border);
  border-radius: 0.35rem;
  background: var(--md-default-bg-color);
  color: var(--md-default-fg-color);
  font: inherit;
}
.work-controls button {
  cursor: pointer;
}
.visible-count {
  min-width: 5.5rem;
  padding-bottom: 0.45rem;
  color: var(--board-muted);
  font-size: 0.8rem;
  text-align: right;
}
.work-table tr[hidden] {
  display: none;
}
@media (max-width: 76.234375em) {
  .md-typeset .work-table {
    min-width: 68rem;
  }
  .work-controls {
    align-items: stretch;
    flex-wrap: wrap;
  }
  .work-controls label {
    flex: 1 1 10rem;
  }
}
"""

INDEX_TEMPLATE = """\
<!-- maigo-board-scaffold-index: 自動生成的首頁重導向，改壞了刪掉這個檔案，\
下次跑 board_serve.py 會重新生成 -->
<script>window.location.replace("board/");</script>
"""


def _is_legacy_generated_config(text: str) -> bool:
    """Recognize the unversioned v2 scaffold without claiming customized files."""
    required = (
        "site_name: Work Board\n",
        "docs_dir: ..\n",
        "extra_css:\n  - _serve/board-style.css\n",
        "markdown_extensions:\n  - pymdownx.tasklist:\n",
    )
    return all(fragment in text for fragment in required) and "theme:" not in text


def _is_legacy_generated_css(text: str) -> bool:
    return (
        "maigo work-board serve 樣式（scaffold）" in text
        and ".task-list-item" in text
        and "maigo-board-scaffold:" not in text
    )


def _upgrade_generated_config(text: str, site_dir: Path) -> str:
    """Upgrade a versioned scaffold while preserving unrelated custom settings."""
    if "# maigo-board-scaffold:" not in text:
        return text
    text = re.sub(r"(?m)^site_dir: .+$", f"site_dir: {site_dir}", text)
    if "# maigo-board-scaffold: 3" in text:
        text = text.replace(
            "# maigo-board-scaffold: 3", f"# maigo-board-scaffold: {SCAFFOLD_VERSION}"
        )
        if "extra_javascript:" not in text:
            text = text.replace(
                "exclude_docs:",
                f"extra_javascript:\n  - {SERVE_DIRNAME}/{JS_NAME}\nexclude_docs:",
            )
    elif "# maigo-board-scaffold: 4" in text:
        text = text.replace(
            "# maigo-board-scaffold: 4", f"# maigo-board-scaffold: {SCAFFOLD_VERSION}"
        )
    elif "# maigo-board-scaffold: 5" in text:
        text = text.replace(
            "# maigo-board-scaffold: 5", f"# maigo-board-scaffold: {SCAFFOLD_VERSION}"
        )
    elif "# maigo-board-scaffold: 6" in text:
        text = text.replace(
            "# maigo-board-scaffold: 6", f"# maigo-board-scaffold: {SCAFFOLD_VERSION}"
        )
    return text


def scaffold(maigo_dir: Path, site_dir: Path) -> Path:
    """
    在 `<maigo_dir>/_serve/` 生成 MkDocs config ＋ CSS。

    未修改的舊版 scaffold 會升級；自訂檔案不覆寫。

    回傳 config 檔路徑。
    """
    serve_dir = maigo_dir / SERVE_DIRNAME
    serve_dir.mkdir(parents=True, exist_ok=True)

    hook_path = Path(__file__).with_name("board_serve_hook.py").resolve()
    config_path = serve_dir / CONFIG_NAME
    config_exists = config_path.is_file()
    config_text = config_path.read_text(encoding="utf-8") if config_exists else ""
    upgrade_config = config_exists and _is_legacy_generated_config(config_text)
    if not config_exists or upgrade_config:
        config_path.write_text(
            CONFIG_TEMPLATE.format(
                version=SCAFFOLD_VERSION,
                site_dir=site_dir,
                hook_path=str(hook_path),
                serve_dirname=SERVE_DIRNAME,
                css_name=CSS_NAME,
                js_name=JS_NAME,
                config_name=CONFIG_NAME,
            ),
            encoding="utf-8",
        )
    elif "maigo-board-scaffold:" in config_text:
        upgraded_config = _upgrade_generated_config(config_text, site_dir)
        if upgraded_config != config_text:
            config_path.write_text(upgraded_config, encoding="utf-8")

    css_path = serve_dir / CSS_NAME
    css_exists = css_path.is_file()
    css_text = css_path.read_text(encoding="utf-8") if css_exists else ""
    upgrade_css = css_exists and _is_legacy_generated_css(css_text)
    upgrade_v3_css = (
        css_exists
        and "maigo-board-scaffold: 3" in css_text
        and hashlib.sha256(css_text.encode()).hexdigest() == V3_CSS_SHA256
    )
    upgrade_v4_css = (
        css_exists
        and "maigo-board-scaffold: 4" in css_text
        and hashlib.sha256(css_text.encode()).hexdigest() == V4_CSS_SHA256
    )
    upgrade_v5_css = (
        css_exists
        and "maigo-board-scaffold: 5" in css_text
        and hashlib.sha256(css_text.encode()).hexdigest() == V5_CSS_SHA256
    )
    upgrade_v6_css = (
        css_exists
        and "maigo-board-scaffold: 6" in css_text
        and hashlib.sha256(css_text.encode()).hexdigest() == V6_CSS_SHA256
    )
    if (
        not css_exists
        or upgrade_css
        or upgrade_v3_css
        or upgrade_v4_css
        or upgrade_v5_css
        or upgrade_v6_css
    ):
        css_path.write_text(CSS_TEMPLATE, encoding="utf-8")

    js_source = Path(__file__).with_name("board_interactions.js")
    shutil.copyfile(js_source, serve_dir / JS_NAME)

    # docs_dir 是 `.maigo/` 本身；MkDocs 只有在該實體根目錄有一個
    # 真的叫 `index.md` 的檔案時才會生成根目錄首頁。內容是純粹的重導向
    # boilerplate，沒有合理的手動編輯理由，每次都直接覆寫。
    (maigo_dir / "index.md").write_text(INDEX_TEMPLATE, encoding="utf-8")

    if config_exists and not upgrade_config:
        config_text = config_path.read_text(encoding="utf-8")
        if "maigo-board-scaffold:" not in config_text:
            sys.stderr.write(
                "board_serve: 保留自訂 `_serve/mkdocs.yml`；"
                "要套用新表格設計，請合併預設 scaffold 或刪除該檔重建\n"
            )
    if (
        css_exists
        and not upgrade_css
        and not upgrade_v3_css
        and not upgrade_v4_css
        and not upgrade_v5_css
        and not upgrade_v6_css
    ):
        css_text = css_path.read_text(encoding="utf-8")
        if "maigo-board-scaffold:" not in css_text:
            sys.stderr.write(
                "board_serve: 保留自訂 `_serve/board-style.css`；"
                "新表格樣式需由使用者手動合併\n"
            )
        elif "maigo-board-scaffold: 3" in css_text:
            sys.stderr.write(
                "board_serve: 保留自訂的 v3 `board-style.css`；"
                "作者、改動量與篩選列樣式需手動合併\n"
            )
        elif "maigo-board-scaffold: 4" in css_text:
            sys.stderr.write(
                "board_serve: 保留自訂的 v4 `board-style.css`；"
                "列操作選單樣式需手動合併\n"
            )
        elif "maigo-board-scaffold: 5" in css_text:
            sys.stderr.write(
                "board_serve: 保留自訂的 v5 `board-style.css`；"
                "5-tier 狀態色與 💤 badge 樣式需手動合併\n"
            )
        elif "maigo-board-scaffold: 6" in css_text:
            sys.stderr.write(
                "board_serve: 保留自訂的 v6 `board-style.css`；字體放大調整需手動合併\n"
            )

    return config_path


def repo_has_mkdocs() -> bool:
    """cwd 專案的 uv venv 是否有 board 所需的 MkDocs 套件。"""
    try:
        proc = subprocess.run(
            [
                "uv",
                "run",
                "--no-sync",
                "python",
                "-c",
                "import material, mkdocs, pymdownx",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def build_serve_command(config_path: Path, addr: str) -> list[str]:
    if repo_has_mkdocs():
        return ["uv", "run", "mkdocs", "serve", "-f", str(config_path), "-a", addr]
    return [
        "uvx",
        "--from",
        "mkdocs-material",
        "--with",
        "pymdown-extensions",
        "mkdocs",
        "serve",
        "-f",
        str(config_path),
        "-a",
        addr,
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("maigo_dir", nargs="?", default=".maigo")
    parser.add_argument("--addr", default="localhost:8000")
    args = parser.parse_args(argv)

    maigo_dir = Path(args.maigo_dir)
    if not maigo_dir.is_dir():
        sys.stderr.write(f"board_serve: `{maigo_dir}` 不存在\n")
        return 1

    board_path = maigo_dir / "board.md"
    if not board_path.is_file():
        sys.stderr.write(
            f"board_serve: 警告——`{board_path}` 不存在，board 頁會是空的\n"
        )

    site_dir = Path(tempfile.mkdtemp(prefix="maigo-board-site-"))
    try:
        config_path = scaffold(maigo_dir, site_dir)

        cmd = build_serve_command(config_path, args.addr)
        print(f"board_serve: 啟動 {' '.join(cmd)}", flush=True)
        print(f"board_serve: Board 網址 http://{args.addr}/board/", flush=True)

        return subprocess.call(cmd)
    except FileNotFoundError as error:
        sys.stderr.write(f"board_serve: 啟動失敗（{error}）\n")
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        shutil.rmtree(site_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
