"""Exercise profile selection and host capability failures through the real CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/resolve_dispatch.py"


def dispatch(tmp_path, *args, profile=None):
    argv = [sys.executable, str(SCRIPT), *args]
    if profile is not None:
        path = tmp_path / "models.json"
        path.write_text(json.dumps(profile))
        argv.extend(["--profile", str(path)])
    proc = subprocess.run(argv, cwd=tmp_path, capture_output=True, text=True)
    assert not proc.stderr, proc.stderr
    return proc.returncode, json.loads(proc.stdout)


def test_no_profile_or_capabilities_preserves_native_models_and_role_order(tmp_path):
    # A nearby config must not silently enable another provider.
    (tmp_path / "models.json").write_text('{"default_model": "remote"}')
    rc, result = dispatch(tmp_path, "--roles", "Anon", "Soyo")
    assert rc == 0
    assert result["execution"] == "inline"
    assert result["parallel"] is False
    assert result["profile"] is None
    assert [(r["role"], r["model"]) for r in result["roles"]] == [
        ("Anon", None),
        ("Soyo", None),
    ]
    assert all(Path(r["agent_file"]).is_file() for r in result["roles"])


def test_profile_precedence_and_null_opt_out(tmp_path):
    rc, result = dispatch(
        tmp_path,
        "--roles",
        "Raana",
        "Tomori",
        "Anon",
        "Soyo",
        "Taki",
        "--subagents",
        "--model-override",
        "--parallel",
        profile={
            "schema_version": 1,
            "default_model": "local/model:quant",
            "roles": {"Tomori": "remote/planner", "Soyo": None},
        },
    )
    assert rc == 0
    assert result["execution"] == "subagents"
    assert result["parallel"] is True
    assert [r["model"] for r in result["roles"]] == [
        "local/model:quant",
        "remote/planner",
        "local/model:quant",
        None,
        "local/model:quant",
    ]


def test_single_model_profile_does_not_require_parallelism(tmp_path):
    rc, result = dispatch(
        tmp_path,
        "--roles",
        "Anon",
        "Soyo",
        "--subagents",
        "--model-override",
        profile={"schema_version": 1, "default_model": "local-coder"},
    )
    assert rc == 0
    assert result["parallel"] is False
    assert {r["model"] for r in result["roles"]} == {"local-coder"}


@pytest.mark.parametrize("flags", [[], ["--subagents"]])
def test_explicit_model_is_not_silently_discarded_without_override(tmp_path, flags):
    rc, result = dispatch(
        tmp_path,
        "--roles",
        "Anon",
        "Soyo",
        *flags,
        profile={"schema_version": 1, "roles": {"Soyo": "remote-reviewer"}},
    )
    assert rc == 2
    assert result["status"] == "error"
    assert "cannot apply" in result["reason"]
    assert "roles" not in result


def test_unused_override_does_not_require_override_capability(tmp_path):
    rc, result = dispatch(
        tmp_path,
        "--roles",
        "Taki",
        "--subagents",
        profile={"schema_version": 1, "roles": {"Soyo": "reviewer"}},
    )
    assert rc == 0
    assert result["roles"][0]["model"] is None


@pytest.mark.parametrize("flags", [["--parallel"], ["--model-override"]])
def test_impossible_capability_combination_is_rejected(tmp_path, flags):
    rc, result = dispatch(tmp_path, "--roles", "Anon", *flags)
    assert rc == 2
    assert "require subagents" in result["reason"]


@pytest.mark.parametrize("roles", [["Unknown"], ["soyo"], ["Anon", "Anon"]])
def test_invalid_roles_are_rejected(tmp_path, roles):
    rc, result = dispatch(tmp_path, "--roles", *roles)
    assert rc == 2
    assert result["status"] == "error"


@pytest.mark.parametrize(
    "profile",
    [
        [],
        {},
        {"schema_version": True},
        {"schema_version": 2},
        {"schema_version": 1, "default_modle": "typo"},
        {"schema_version": 1, "subagents": True},
        {"schema_version": 1, "roles": []},
        {"schema_version": 1, "roles": {"soyo": "typo"}},
        *(
            {"schema_version": 1, "default_model": model}
            for model in [False, 42, {}, "", " ", " coder", "coder\n", "co\nder"]
        ),
        {"schema_version": 1, "roles": {"Soyo": []}},
    ],
)
def test_invalid_profile_never_produces_dispatch(tmp_path, profile):
    rc, result = dispatch(
        tmp_path, "--roles", "Soyo", "--subagents", "--model-override", profile=profile
    )
    assert rc == 2
    assert result["status"] == "error"
    assert result["reason"]
    assert "roles" not in result


@pytest.mark.parametrize(
    "contents",
    [
        b"{",
        b"\xff",
        b'{"schema_version": 1, "roles": {"Soyo": "local", "Soyo": "remote"}}',
    ],
)
def test_malformed_or_duplicate_profile_returns_json_error(tmp_path, contents):
    path = tmp_path / "bad.json"
    path.write_bytes(contents)
    rc, result = dispatch(tmp_path, "--roles", "Soyo", "--profile", str(path))
    assert rc == 2
    assert result["status"] == "error"


@pytest.mark.parametrize("filename", ["missing.json", "."])
def test_unreadable_profile_returns_json_error(tmp_path, filename):
    rc, result = dispatch(tmp_path, "--roles", "Soyo", "--profile", filename)
    assert rc == 2
    assert result["status"] == "error"


def test_relative_profile_path_is_resolved_from_invocation_cwd(tmp_path):
    (tmp_path / "chosen.json").write_text('{"schema_version": 1}')
    rc, result = dispatch(tmp_path, "--roles", "Taki", "--profile", "chosen.json")
    assert rc == 0
    assert Path(result["profile"]) == tmp_path / "chosen.json"
