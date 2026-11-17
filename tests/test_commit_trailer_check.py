"""Tests for hooks.commit_trailer_check — blocks `git commit` carrying a Co-Authored-By trailer."""

from __future__ import annotations

import io
import json
from pathlib import Path

import hooks.commit_trailer_check as ctc
import pytest

TRAILER = "Co-Authored-By: Claude <noreply@anthropic.com>"


def run_hook(
    raw: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> str:
    monkeypatch.setattr("sys.stdin", io.StringIO(raw))
    with pytest.raises(SystemExit) as exc:
        ctc.main()
    assert exc.value.code == 0
    return capsys.readouterr().out


def bash(command: str, **extra: object) -> str:
    return json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": command}, **extra}
    )


BLOCKED = [
    f'git commit -m "fix: x\n\n{TRAILER}"',
    f"git commit -m 'fix: x' -m '{TRAILER}'",
    f'git commit --message="fix: x\n\n{TRAILER}"',
    f'git commit --message "fix: x\n\n{TRAILER}"',
    f'git commit -am "fix: x\n\n{TRAILER}"',
    f'git commit -m"fix: x\n\n{TRAILER}"',
    f'git commit --amend -m "fix: x\n\n{TRAILER}"',
    f'git -C /tmp/repo commit -m "fix: x\n\n{TRAILER}"',
    f'git -c user.name=x commit -m "fix: x\n\n{TRAILER}"',
    f'git add a.py && git commit -m "fix: x\n\n{TRAILER}"',
    f'git add a.py; git commit -m "fix: x\n\n{TRAILER}"',
    f'cd repo && git add . && git commit -m "x\n\n{TRAILER}" && git status',
    'git commit -m "x\n\nco-authored-by: Bot <b@x.io>"',
    'git commit -m "x\n\nCO-AUTHORED-BY: Bot <b@x.io>"',
    f'git commit --trailer "{TRAILER}" -m "x"',
    f"git commit -F - <<'EOF'\nfix: x\n\n{TRAILER}\nEOF",
    f"git commit -F - <<EOF\nfix: x\n\n{TRAILER}\nEOF",
    f"git commit -m \"$(cat <<'EOF'\nfix: x\n\n{TRAILER}\nEOF\n)\"",
    f"git add a && git commit -F - <<'EOF'\nfix: x\n\n{TRAILER}\nEOF\ngit status",
]

ALLOWED = [
    'git commit -m "fix: x"',
    'git commit -am "fix: x" && git push',
    "git commit -F msg.txt",
    "git commit -F - < msg.txt",
    "git commit --amend --no-edit",
    "git commit -F - <<'EOF'\nfix: x\n\nbody text\nEOF",
    'git commit -m "docs: explain why we avoid the Co-Authored-By: line"',
    "git log --grep Co-Authored-By",
    "git log --grep 'Co-Authored-By:' --oneline",
    "git log -1 --format=%b | grep -c Co-Authored-By",
    f'echo "{TRAILER}"',
    "grep -c 'Co-Authored-By' file.txt && git commit -m 'fix: x'",
    f"cat <<'EOF' | grep Co-Authored-By\n{TRAILER}\nEOF\ngit commit -m 'fix: x'",
    f'git status && echo "{TRAILER}"',
    f"git commit-tree HEAD^{{tree}} -m '{TRAILER}'",
    'git commit -m "unbalanced',
    "",
    "   ",
]


@pytest.mark.parametrize("command", BLOCKED)
def test_blocks_trailer(
    command: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    out = run_hook(bash(command), monkeypatch, capsys)
    payload = json.loads(out)
    assert payload["decision"] == "block"
    assert "Co-Authored-By" in payload["reason"]


@pytest.mark.parametrize("command", ALLOWED)
def test_allows_everything_else(
    command: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    assert run_hook(bash(command), monkeypatch, capsys) == ""


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",
        "null",
        "{}",
        json.dumps({"tool_name": "Bash"}),
        json.dumps({"tool_name": "Bash", "tool_input": "git commit"}),
        json.dumps({"tool_name": "Bash", "tool_input": {"command": 42}}),
        json.dumps(
            {
                "tool_name": "Write",
                "tool_input": {"command": f'git commit -m "{TRAILER}"'},
            }
        ),
    ],
)
def test_malformed_or_other_tool_fails_open(
    raw: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    assert run_hook(raw, monkeypatch, capsys) == ""


def test_skip_file_disables_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    command = f'git commit -m "x\n\n{TRAILER}"'
    assert run_hook(bash(command, cwd=str(tmp_path)), monkeypatch, capsys) != ""
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / ctc.SKIP_FILE).write_text("# why\nvendor repo needs it\n")
    assert run_hook(bash(command, cwd=str(tmp_path)), monkeypatch, capsys) == ""


def test_skip_file_without_reason_does_not_disable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / ctc.SKIP_FILE).write_text("# only a comment\n")
    command = f'git commit -m "x\n\n{TRAILER}"'
    assert run_hook(bash(command, cwd=str(tmp_path)), monkeypatch, capsys) != ""
