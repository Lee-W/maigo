"""Tests for scripts.board_serve."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import scripts.board_serve as bs


class TestScaffold:
    def test_creates_config_and_css(self, tmp_path: Path):
        maigo_dir = tmp_path / ".maigo"
        maigo_dir.mkdir()
        site_dir = tmp_path / "site-out"

        config_path = bs.scaffold(maigo_dir, site_dir)

        assert config_path == maigo_dir / "_serve" / "mkdocs.yml"
        assert config_path.is_file()
        assert (maigo_dir / "_serve" / "board-style.css").is_file()
        assert (maigo_dir / "_serve" / "board-interactions.js").is_file()

    def test_config_points_docs_dir_at_parent(self, tmp_path: Path):
        maigo_dir = tmp_path / ".maigo"
        maigo_dir.mkdir()

        config_path = bs.scaffold(maigo_dir, tmp_path / "site-out")
        text = config_path.read_text(encoding="utf-8")

        assert "docs_dir: ..\n" in text
        assert str(tmp_path / "site-out") in text

    def test_config_has_tasklist_extension_for_real_checkboxes(self, tmp_path: Path):
        maigo_dir = tmp_path / ".maigo"
        maigo_dir.mkdir()

        config_path = bs.scaffold(maigo_dir, tmp_path / "site-out")
        text = config_path.read_text(encoding="utf-8")

        assert "pymdownx.tasklist" in text
        assert "custom_checkbox: true" in text

    def test_config_uses_material_with_board_only_navigation(self, tmp_path: Path):
        maigo_dir = tmp_path / ".maigo"
        maigo_dir.mkdir()

        config_path = bs.scaffold(maigo_dir, tmp_path / "site-out")
        text = config_path.read_text(encoding="utf-8")

        assert "name: material" in text
        assert "- 工作板: board.md" in text
        assert "navigation.tabs" not in text
        assert "board_serve_hook.py" in text
        assert "extra_javascript" in text
        assert "board-interactions.js" in text

    def test_config_excludes_its_own_yaml_from_docs(self, tmp_path: Path):
        maigo_dir = tmp_path / ".maigo"
        maigo_dir.mkdir()

        config_path = bs.scaffold(maigo_dir, tmp_path / "site-out")
        text = config_path.read_text(encoding="utf-8")

        assert "exclude_docs" in text
        assert "_serve/mkdocs.yml" in text

    def test_css_styles_task_list_items(self, tmp_path: Path):
        maigo_dir = tmp_path / ".maigo"
        maigo_dir.mkdir()

        bs.scaffold(maigo_dir, tmp_path / "site-out")
        css = (maigo_dir / "_serve" / "board-style.css").read_text(encoding="utf-8")

        assert ".work-table" in css
        assert ".work-status" in css
        assert ".work-command" in css
        assert ".work-controls" in css
        assert ".diff-add" in css

    def test_upgrades_unmodified_legacy_scaffold(self, tmp_path: Path):
        maigo_dir = tmp_path / ".maigo"
        serve_dir = maigo_dir / "_serve"
        serve_dir.mkdir(parents=True)
        (serve_dir / "mkdocs.yml").write_text(
            "site_name: Work Board\n"
            "docs_dir: ..\n"
            "site_dir: /tmp/old\n"
            "extra_css:\n  - _serve/board-style.css\n"
            "exclude_docs: |\n  _serve/mkdocs.yml\n"
            "markdown_extensions:\n"
            "  - pymdownx.tasklist:\n      custom_checkbox: true\n",
            encoding="utf-8",
        )
        (serve_dir / "board-style.css").write_text(
            "/* maigo work-board serve 樣式（scaffold） */\n.task-list-item {}\n",
            encoding="utf-8",
        )

        config_path = bs.scaffold(maigo_dir, tmp_path / "site-out")

        assert "maigo-board-scaffold: 7" in config_path.read_text(encoding="utf-8")
        assert "maigo-board-scaffold: 7" in (serve_dir / "board-style.css").read_text(
            encoding="utf-8"
        )

    def test_upgrades_unmodified_v5_css_to_current(self, tmp_path: Path):
        """Regression: `V5_CSS_SHA256` must match the real, byte-for-byte v5
        `CSS_TEMPLATE` (pinned as a fixture) — a wrong constant makes every
        genuine pre-existing v5 install look "user-customized" and silently
        stops receiving CSS upgrades forever."""
        maigo_dir = tmp_path / ".maigo"
        serve_dir = maigo_dir / "_serve"
        serve_dir.mkdir(parents=True)
        v5_css = (Path(__file__).parent / "fixtures" / "board_serve_v5.css").read_text(
            encoding="utf-8"
        )
        css_path = serve_dir / "board-style.css"
        css_path.write_text(v5_css, encoding="utf-8")

        bs.scaffold(maigo_dir, tmp_path / "site-out")

        upgraded = css_path.read_text(encoding="utf-8")
        assert "maigo-board-scaffold: 7" in upgraded
        assert "status-blocked" in upgraded

    def test_preserves_genuinely_modified_v5_css(self, tmp_path: Path, capsys):
        maigo_dir = tmp_path / ".maigo"
        serve_dir = maigo_dir / "_serve"
        serve_dir.mkdir(parents=True)
        css_path = serve_dir / "board-style.css"
        css_path.write_text(
            "/* maigo-board-scaffold: 5\n   使用者自訂過的版本 */\n.custom {}\n",
            encoding="utf-8",
        )

        bs.scaffold(maigo_dir, tmp_path / "site-out")

        assert css_path.read_text(encoding="utf-8") == (
            "/* maigo-board-scaffold: 5\n   使用者自訂過的版本 */\n.custom {}\n"
        )
        assert "v5" in capsys.readouterr().err

    def test_upgrades_unmodified_v6_css_to_current(self, tmp_path: Path):
        """Regression: `V6_CSS_SHA256` must match the real, byte-for-byte v6
        `CSS_TEMPLATE` (pinned as a fixture) — same failure mode as the v5
        constant bug this mirrors: a wrong hash makes every genuine
        pre-existing v6 install look "user-customized" forever."""
        maigo_dir = tmp_path / ".maigo"
        serve_dir = maigo_dir / "_serve"
        serve_dir.mkdir(parents=True)
        v6_css = (Path(__file__).parent / "fixtures" / "board_serve_v6.css").read_text(
            encoding="utf-8"
        )
        css_path = serve_dir / "board-style.css"
        css_path.write_text(v6_css, encoding="utf-8")

        bs.scaffold(maigo_dir, tmp_path / "site-out")

        upgraded = css_path.read_text(encoding="utf-8")
        assert "maigo-board-scaffold: 7" in upgraded
        assert "font-size: 0.88rem" in upgraded

    def test_preserves_genuinely_modified_v6_css(self, tmp_path: Path, capsys):
        maigo_dir = tmp_path / ".maigo"
        serve_dir = maigo_dir / "_serve"
        serve_dir.mkdir(parents=True)
        css_path = serve_dir / "board-style.css"
        css_path.write_text(
            "/* maigo-board-scaffold: 6\n   使用者自訂過的版本 */\n.custom {}\n",
            encoding="utf-8",
        )

        bs.scaffold(maigo_dir, tmp_path / "site-out")

        assert css_path.read_text(encoding="utf-8") == (
            "/* maigo-board-scaffold: 6\n   使用者自訂過的版本 */\n.custom {}\n"
        )
        assert "v6" in capsys.readouterr().err

    def test_upgrades_v3_config_without_discarding_custom_settings(
        self, tmp_path: Path
    ):
        maigo_dir = tmp_path / ".maigo"
        serve_dir = maigo_dir / "_serve"
        serve_dir.mkdir(parents=True)
        config_path = serve_dir / "mkdocs.yml"
        config_path.write_text(
            "# maigo-board-scaffold: 3\n"
            "site_name: Custom Board\n"
            "docs_dir: ..\n"
            "site_dir: /tmp/old\n"
            "extra_css:\n  - _serve/board-style.css\n"
            "exclude_docs: |\n  _serve/mkdocs.yml\n",
            encoding="utf-8",
        )

        bs.scaffold(maigo_dir, tmp_path / "new-site")
        text = config_path.read_text(encoding="utf-8")

        assert "maigo-board-scaffold: 7" in text
        assert "site_name: Custom Board" in text
        assert f"site_dir: {tmp_path / 'new-site'}" in text
        assert "board-interactions.js" in text

    def test_interactions_copy_commands_without_writing_board(self, tmp_path: Path):
        maigo_dir = tmp_path / ".maigo"
        maigo_dir.mkdir()

        bs.scaffold(maigo_dir, tmp_path / "site-out")
        script = (maigo_dir / "_serve" / "board-interactions.js").read_text(
            encoding="utf-8"
        )

        assert "navigator.clipboard.writeText" in script
        assert "data-copy-command" in script
        assert 'table.closest(".work-table-wrap").hidden' in script
        assert "fetch(" not in script

    def test_does_not_overwrite_existing_config(self, tmp_path: Path):
        maigo_dir = tmp_path / ".maigo"
        maigo_dir.mkdir()
        bs.scaffold(maigo_dir, tmp_path / "site-out")

        config_path = maigo_dir / "_serve" / "mkdocs.yml"
        config_path.write_text("# 使用者自訂內容\n", encoding="utf-8")

        bs.scaffold(maigo_dir, tmp_path / "another-site-out")

        assert config_path.read_text(encoding="utf-8") == "# 使用者自訂內容\n"

    def test_scaffolds_root_index_redirect_to_board(self, tmp_path: Path):
        maigo_dir = tmp_path / ".maigo"
        maigo_dir.mkdir()

        bs.scaffold(maigo_dir, tmp_path / "site-out")
        index_text = (maigo_dir / "index.md").read_text(encoding="utf-8")

        assert 'window.location.replace("board/")' in index_text
        assert "<script>" in index_text

    def test_index_redirect_is_always_overwritten(self, tmp_path: Path):
        maigo_dir = tmp_path / ".maigo"
        maigo_dir.mkdir()
        bs.scaffold(maigo_dir, tmp_path / "site-out")

        index_path = maigo_dir / "index.md"
        index_path.write_text("# 手動改過的內容\n", encoding="utf-8")

        bs.scaffold(maigo_dir, tmp_path / "another-site-out")

        assert 'window.location.replace("board/")' in index_path.read_text(
            encoding="utf-8"
        )

    def test_does_not_overwrite_existing_css(self, tmp_path: Path):
        maigo_dir = tmp_path / ".maigo"
        maigo_dir.mkdir()
        bs.scaffold(maigo_dir, tmp_path / "site-out")

        css_path = maigo_dir / "_serve" / "board-style.css"
        css_path.write_text("/* 使用者自訂樣式 */\n", encoding="utf-8")

        bs.scaffold(maigo_dir, tmp_path / "site-out")

        assert css_path.read_text(encoding="utf-8") == "/* 使用者自訂樣式 */\n"


class TestRepoHasMkdocs:
    def test_true_when_uv_run_succeeds(self, monkeypatch):
        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, "mkdocs, version 1.6.1", "")

        monkeypatch.setattr(bs.subprocess, "run", fake_run)
        assert bs.repo_has_mkdocs() is True

    def test_false_when_uv_run_fails(self, monkeypatch):
        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 2, "", "error: Failed to spawn")

        monkeypatch.setattr(bs.subprocess, "run", fake_run)
        assert bs.repo_has_mkdocs() is False

    def test_false_when_uv_missing(self, monkeypatch):
        def fake_run(cmd, **kwargs):
            raise OSError("uv not found")

        monkeypatch.setattr(bs.subprocess, "run", fake_run)
        assert bs.repo_has_mkdocs() is False

    def test_false_on_timeout(self, monkeypatch):
        def fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, 15)

        monkeypatch.setattr(bs.subprocess, "run", fake_run)
        assert bs.repo_has_mkdocs() is False


class TestBuildServeCommand:
    def test_uses_uv_run_when_repo_has_mkdocs(self, monkeypatch, tmp_path: Path):
        monkeypatch.setattr(bs, "repo_has_mkdocs", lambda: True)
        config_path = tmp_path / "mkdocs.yml"

        cmd = bs.build_serve_command(config_path, "localhost:8000")

        assert cmd[:2] == ["uv", "run"]
        assert "mkdocs" in cmd
        assert str(config_path) in cmd
        assert "localhost:8000" in cmd

    def test_falls_back_to_uvx_with_material_and_pymdown_extensions(
        self, monkeypatch, tmp_path: Path
    ):
        monkeypatch.setattr(bs, "repo_has_mkdocs", lambda: False)
        config_path = tmp_path / "mkdocs.yml"

        cmd = bs.build_serve_command(config_path, "localhost:8000")

        assert cmd[0] == "uvx"
        assert "--with" in cmd
        assert "mkdocs-material" in cmd
        assert "pymdown-extensions" in cmd
        assert str(config_path) in cmd


class TestMain:
    def test_missing_maigo_dir_exits_1(self, tmp_path: Path, capsys):
        missing = tmp_path / "nope"
        assert bs.main([str(missing)]) == 1
        assert "不存在" in capsys.readouterr().err

    def test_warns_but_continues_when_board_md_missing(
        self, tmp_path: Path, monkeypatch, capsys
    ):
        maigo_dir = tmp_path / ".maigo"
        maigo_dir.mkdir()
        monkeypatch.setattr(bs.subprocess, "call", lambda cmd: 0)

        result = bs.main([str(maigo_dir)])

        assert result == 0
        assert "board.md" in capsys.readouterr().err

    def test_prints_board_url_and_launches_serve_command(
        self, tmp_path: Path, monkeypatch, capsys
    ):
        maigo_dir = tmp_path / ".maigo"
        maigo_dir.mkdir()
        (maigo_dir / "board.md").write_text("# Work Board\n", encoding="utf-8")
        recorded = {}

        def fake_call(cmd):
            recorded["cmd"] = cmd
            return 0

        monkeypatch.setattr(bs.subprocess, "call", fake_call)
        monkeypatch.setattr(bs, "repo_has_mkdocs", lambda: True)

        result = bs.main([str(maigo_dir), "--addr", "localhost:9999"])

        assert result == 0
        assert "localhost:9999" in " ".join(recorded["cmd"])
        out = capsys.readouterr().out
        assert "http://localhost:9999/board/" in out

    def test_site_dir_removed_after_serve_exits(self, tmp_path: Path, monkeypatch):
        maigo_dir = tmp_path / ".maigo"
        maigo_dir.mkdir()
        (maigo_dir / "board.md").write_text("# Work Board\n", encoding="utf-8")
        created: list[Path] = []
        real_mkdtemp = bs.tempfile.mkdtemp

        def recording_mkdtemp(*args, **kwargs):
            path = real_mkdtemp(*args, **kwargs)
            created.append(Path(path))
            return path

        monkeypatch.setattr(bs.tempfile, "mkdtemp", recording_mkdtemp)
        monkeypatch.setattr(bs.subprocess, "call", lambda cmd: 0)
        monkeypatch.setattr(bs, "repo_has_mkdocs", lambda: True)

        result = bs.main([str(maigo_dir)])

        assert result == 0
        assert len(created) == 1
        assert not created[0].exists()

    def test_site_dir_removed_even_on_keyboard_interrupt(
        self, tmp_path: Path, monkeypatch
    ):
        maigo_dir = tmp_path / ".maigo"
        maigo_dir.mkdir()
        (maigo_dir / "board.md").write_text("# Work Board\n", encoding="utf-8")
        created: list[Path] = []
        real_mkdtemp = bs.tempfile.mkdtemp

        def recording_mkdtemp(*args, **kwargs):
            path = real_mkdtemp(*args, **kwargs)
            created.append(Path(path))
            return path

        def raising_call(cmd):
            raise KeyboardInterrupt

        monkeypatch.setattr(bs.tempfile, "mkdtemp", recording_mkdtemp)
        monkeypatch.setattr(bs.subprocess, "call", raising_call)
        monkeypatch.setattr(bs, "repo_has_mkdocs", lambda: True)

        result = bs.main([str(maigo_dir)])

        assert result == 0
        assert len(created) == 1
        assert not created[0].exists()

    def test_site_dir_removed_when_scaffold_raises_before_serve(
        self, tmp_path: Path, monkeypatch
    ):
        maigo_dir = tmp_path / ".maigo"
        maigo_dir.mkdir()
        (maigo_dir / "board.md").write_text("# Work Board\n", encoding="utf-8")
        created: list[Path] = []
        real_mkdtemp = bs.tempfile.mkdtemp

        def recording_mkdtemp(*args, **kwargs):
            path = real_mkdtemp(*args, **kwargs)
            created.append(Path(path))
            return path

        def raising_scaffold(maigo_dir, site_dir):
            raise PermissionError("scaffold 沒有寫入權限（模擬 chmod 555 .maigo/）")

        monkeypatch.setattr(bs.tempfile, "mkdtemp", recording_mkdtemp)
        monkeypatch.setattr(bs, "scaffold", raising_scaffold)

        with pytest.raises(PermissionError):
            bs.main([str(maigo_dir)])

        assert len(created) == 1
        assert not created[0].exists()
