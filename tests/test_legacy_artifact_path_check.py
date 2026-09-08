"""Tests for hooks.legacy_artifact_path_check — blocks writes to legacy `.maigo/`
fixed-name artifacts (`plan.md`, `review-rubric.md`, ...)."""

from __future__ import annotations

import importlib
import io
import json
import sys

import pytest

import hooks.legacy_artifact_path_check as lac


def run_silent_hook(
    payload: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> str:
    """Run the hook's main() and return raw stdout (empty string = pass-through)."""
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    with pytest.raises(SystemExit) as exc:
        lac.main()
    assert exc.value.code == 0
    return capsys.readouterr().out


def _write_payload(file_path: str, tool_name: str = "Write") -> dict:
    return {"tool_name": tool_name, "tool_input": {"file_path": file_path}}


class TestIsLegacyArtifactPath:
    @pytest.mark.parametrize(
        "path",
        [
            ".maigo/plan.md",
            ".maigo/review-rubric.md",
            ".maigo/pr-comments.md",
            ".maigo/triage-rubric.md",
            ".maigo/review.md",
            "/Users/x/repo/.maigo/plan.md",
        ],
    )
    def test_legacy_fixed_names_are_flagged(self, path: str):
        assert lac.is_legacy_artifact_path(path) is not None

    @pytest.mark.parametrize(
        "path",
        [
            ".maigo/plan-main.md",
            ".maigo/board.md",
            ".maigo/local-model-dispatch-plan.md",
            ".maigo/i/9201.md",
            "plan.md",
            "notes/not.maigo/plan.md",
        ],
    )
    def test_non_legacy_paths_are_not_flagged(self, path: str):
        assert lac.is_legacy_artifact_path(path) is None

    def test_returns_the_matched_kind(self):
        assert lac.is_legacy_artifact_path(".maigo/review-rubric.md") == "review-rubric"


class TestLegacyArtifactPathHook:
    def test_write_to_plan_md_blocks_with_command_example(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ):
        result = json.loads(
            run_silent_hook(
                _write_payload(".maigo/plan.md"), monkeypatch, capsys
            ).strip()
        )
        assert result["decision"] == "block"
        assert "scripts/artifact_path.py plan" in result["reason"]

    @pytest.mark.parametrize(
        "path",
        [
            ".maigo/review-rubric.md",
            ".maigo/pr-comments.md",
            ".maigo/triage-rubric.md",
            ".maigo/review.md",
        ],
    )
    def test_all_legacy_kinds_block(
        self, path: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ):
        result = json.loads(
            run_silent_hook(_write_payload(path), monkeypatch, capsys).strip()
        )
        assert result["decision"] == "block"

    def test_new_identifier_named_path_passes(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ):
        assert (
            run_silent_hook(_write_payload(".maigo/plan-main.md"), monkeypatch, capsys)
            == ""
        )

    def test_board_md_passes(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ):
        assert (
            run_silent_hook(_write_payload(".maigo/board.md"), monkeypatch, capsys)
            == ""
        )

    def test_ad_hoc_named_file_passes(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ):
        assert (
            run_silent_hook(
                _write_payload(".maigo/local-model-dispatch-plan.md"),
                monkeypatch,
                capsys,
            )
            == ""
        )

    def test_detail_file_under_i_passes(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ):
        assert (
            run_silent_hook(_write_payload(".maigo/i/9201.md"), monkeypatch, capsys)
            == ""
        )

    def test_edit_tool_also_blocks(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ):
        result = json.loads(
            run_silent_hook(
                _write_payload(".maigo/plan.md", tool_name="Edit"), monkeypatch, capsys
            ).strip()
        )
        assert result["decision"] == "block"

    def test_same_filename_outside_maigo_dir_passes(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ):
        assert run_silent_hook(_write_payload("plan.md"), monkeypatch, capsys) == ""

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"tool_name": "Write", "tool_input": None},
            {"tool_name": "Write", "tool_input": {}},
            {"tool_name": "Write", "tool_input": {"file_path": "   "}},
            {"tool_name": "Write", "tool_input": {"file_path": 42}},
            {"tool_name": "Bash", "tool_input": {"file_path": ".maigo/plan.md"}},
        ],
    )
    def test_malformed_or_irrelevant_input_fails_open(
        self,
        payload: dict,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        assert run_silent_hook(payload, monkeypatch, capsys) == ""

    def test_non_json_stdin_fails_open(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ):
        monkeypatch.setattr("sys.stdin", io.StringIO("not json at all"))
        with pytest.raises(SystemExit) as exc:
            lac.main()
        assert exc.value.code == 0
        assert capsys.readouterr().out == ""


class TestBrokenArtifactPathImportFailsOpen:
    """Regression for the must-fix: `scripts/artifact_path.py` breaking (e.g. a
    syntax error while a new `kind` is being added) must not take down every
    Write/Edit in every repo with an uncaught exception."""

    def _reload_with_broken_artifact_path(self):
        """Simulate `from artifact_path import _KNOWN_KINDS` failing at import
        time, then reload the hook module so it re-runs its own top-level
        try/except and falls back to `_KNOWN_KINDS = ()`."""
        sys.modules.pop("artifact_path", None)
        sys.modules["artifact_path"] = None  # forces ModuleNotFoundError on import
        try:
            importlib.reload(lac)
        finally:
            sys.modules.pop("artifact_path", None)

    def _restore(self):
        """Reload again with the real `artifact_path` module so later tests in
        this process see the normal, non-empty `_KNOWN_KINDS`."""
        importlib.reload(lac)

    def test_import_failure_falls_back_to_empty_known_kinds(self):
        self._reload_with_broken_artifact_path()
        try:
            assert lac._KNOWN_KINDS == ()
            # regex built from an empty alternation must never match a real path
            assert lac.is_legacy_artifact_path(".maigo/plan.md") is None
            assert lac.is_legacy_artifact_path(".maigo/review-rubric.md") is None
        finally:
            self._restore()

    def test_import_failure_still_fails_open_for_legacy_looking_path(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ):
        """Before the fix this scenario crashed with an uncaught
        `ModuleNotFoundError`/`SyntaxError`, exit code 1, no stdout at all.
        After the fix, main() must still run to completion (exit 0) and the
        write must not be blocked (no `block` payload) — matching this hook's
        own documented silent fail-open style."""
        self._reload_with_broken_artifact_path()
        try:
            monkeypatch.setattr(
                "sys.stdin", io.StringIO(json.dumps(_write_payload(".maigo/plan.md")))
            )
            with pytest.raises(SystemExit) as exc:
                lac.main()
            assert exc.value.code == 0
            assert capsys.readouterr().out == ""
        finally:
            self._restore()
