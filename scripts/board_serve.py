#!/usr/bin/env python3
"""
Serve `.maigo/board.md`（與同目錄下其它 `.md`，如 review report）為一個會
live reload 的本地網站（work-board 閱讀層 v2，見 `.maigo/board-design.md` §12）。

跑：`python3 scripts/board_serve.py [.maigo 路徑] [--addr HOST:PORT]`
預設 `.maigo`、`localhost:8000`。

首跑會在 `.maigo/_serve/`（gitignored 工作區，不是真相層）生成最小 mkdocs
scaffold（`mkdocs.yml` ＋ `board-style.css`）；已存在就不覆寫，保留使用者調整。
`docs_dir` 直指 `.maigo/` 本身——`.maigo/board.md` 原封不動當作真相層來源，
`_serve/` 本身用 `exclude_docs` 排除掉那份 `mkdocs.yml` 不外流，其餘 `.maigo/*.md`
（review report 等 `📄` 連結的產物）由同一個 server 直接渲染。

啟動優先序：
1. cwd 專案的 venv 已裝 mkdocs（`uv run --no-sync mkdocs --version` 成功）
   → `uv run mkdocs serve -f <config>`
2. 否則 → `uvx --from mkdocs --with pymdown-extensions mkdocs serve -f <config>`
   （zero repo 相依；checkbox 渲染要的 `pymdownx.tasklist` 來自
   `pymdown-extensions`，一併帶上，其他 repo 的 `.maigo/` 一樣可用）

checkbox（`- [ ]`）用 `pymdownx.tasklist` 渲染成真正的 `<input type="checkbox">`，
不會退化成純文字。`.maigo/` 沒有首頁（`board.md` 不是 `index.md`）——本 script
直接印出 board 頁網址，不額外造一份 index scaffold 去污染真相層目錄。

python3 stdlib-only：不 import 任何第三方套件；只用 subprocess 呼叫 uv/uvx。
serve 本體會一直跑在前景直到使用者 Ctrl-C，回傳其 exit code。
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SERVE_DIRNAME = "_serve"
CONFIG_NAME = "mkdocs.yml"
CSS_NAME = "board-style.css"

CONFIG_TEMPLATE = """\
site_name: Work Board
docs_dir: ..
site_dir: {site_dir}
extra_css:
  - {serve_dirname}/{css_name}
exclude_docs: |
  {serve_dirname}/{config_name}
markdown_extensions:
  - pymdownx.tasklist:
      custom_checkbox: true
"""

CSS_TEMPLATE = """\
/* maigo work-board serve 樣式（scaffold）——首跑自動生成，改壞了刪掉這個檔案，
   下次跑 board_serve.py 會重新生成預設版本；正常改動請直接編輯這個檔案。 */
:root {
  color-scheme: light dark;
}
.task-list-item {
  list-style: none;
  margin: 0.4rem 0;
  padding: 0.5rem 0.75rem;
  border: 1px solid rgba(120, 120, 130, 0.28);
  border-radius: 0.5rem;
  background: rgba(120, 120, 130, 0.06);
}
.task-list-item input[type="checkbox"] {
  width: 1.05rem;
  height: 1.05rem;
  margin-right: 0.5rem;
  vertical-align: middle;
}
.task-list-item strong {
  color: #b3541e;
}
@media (prefers-color-scheme: dark) {
  .task-list-item strong {
    color: #ffab5e;
  }
}
code {
  border-radius: 0.3rem;
}
"""


def scaffold(maigo_dir: Path, site_dir: Path) -> Path:
    """
    在 `<maigo_dir>/_serve/` 生成最小 mkdocs config ＋ CSS（已存在就不覆寫）。

    回傳 config 檔路徑。
    """
    serve_dir = maigo_dir / SERVE_DIRNAME
    serve_dir.mkdir(parents=True, exist_ok=True)

    config_path = serve_dir / CONFIG_NAME
    if not config_path.is_file():
        config_path.write_text(
            CONFIG_TEMPLATE.format(
                site_dir=site_dir,
                serve_dirname=SERVE_DIRNAME,
                css_name=CSS_NAME,
                config_name=CONFIG_NAME,
            ),
            encoding="utf-8",
        )

    css_path = serve_dir / CSS_NAME
    if not css_path.is_file():
        css_path.write_text(CSS_TEMPLATE, encoding="utf-8")

    return config_path


def repo_has_mkdocs() -> bool:
    """cwd 專案的 uv venv 是否已經裝了 mkdocs（不觸發網路 sync）。"""
    try:
        proc = subprocess.run(
            ["uv", "run", "--no-sync", "mkdocs", "--version"],
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
        "mkdocs",
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
