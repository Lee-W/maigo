"""Resolve role models against declared host capabilities, without calling a model.

Usage: python3 /path/to/maigo/scripts/resolve_dispatch.py --roles Anon Soyo
Only explicitly selected profiles are read. Host tools remain responsible for
model availability, credentials, endpoints, permissions and actual execution.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

AGENTS_DIR = Path(__file__).resolve().parents[1] / "agents"


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate settings instead of silently discarding an earlier one."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate profile key: {key}")
        result[key] = value
    return result


def read_profile(path: Path, known_roles: set[str]) -> dict[str, Any]:
    profile = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=unique_object
    )
    if not isinstance(profile, dict):
        raise ValueError("Profile must be a JSON object")
    unknown = profile.keys() - {"schema_version", "default_model", "roles"}
    if unknown:
        raise ValueError(f"Unknown profile fields: {', '.join(sorted(unknown))}")
    if type(profile.get("schema_version")) is not int or profile["schema_version"] != 1:
        raise ValueError("Profile schema_version must be 1")
    roles = profile.get("roles", {})
    if not isinstance(roles, dict):
        raise ValueError("Profile roles must be an object")
    unknown = roles.keys() - known_roles
    if unknown:
        raise ValueError(f"Unknown profile roles: {', '.join(sorted(unknown))}")
    for field, model in [
        ("default_model", profile.get("default_model")),
        *roles.items(),
    ]:
        if model is not None and (
            not isinstance(model, str)
            or not model.strip()
            or model != model.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in model)
        ):
            raise ValueError(
                f"{field} must be null or a nonempty model ID without surrounding whitespace or control characters"
            )
    return profile


def resolve_dispatch(
    roles: list[str],
    profile_path: Path | None = None,
    *,
    subagents: bool = False,
    model_override: bool = False,
    parallel: bool = False,
) -> dict[str, Any]:
    """Return dispatch instructions; capabilities are observations, not probes."""
    known_roles = {path.stem for path in AGENTS_DIR.glob("*.md")}
    if not roles or len(roles) != len(set(roles)) or set(roles) - known_roles:
        raise ValueError(
            "Select distinct roles from: " + ", ".join(sorted(known_roles))
        )
    if (model_override or parallel) and not subagents:
        raise ValueError("Model override and parallel capabilities require subagents")
    profile = read_profile(profile_path, known_roles) if profile_path else {}
    models = {
        role: profile.get("roles", {}).get(role, profile.get("default_model"))
        for role in roles
    }
    if not model_override and any(model is not None for model in models.values()):
        raise ValueError(
            "This host cannot apply per-role model overrides. Select the model in "
            "the host and use native defaults (null), or use a host with model override support."
        )
    return {
        "schema_version": 1,
        "status": "ready",
        "profile": str(profile_path) if profile_path else None,
        "execution": "subagents" if subagents else "inline",
        "parallel": parallel,
        "roles": [
            {"role": role, "model": model, "agent_file": str(AGENTS_DIR / f"{role}.md")}
            for role, model in models.items()
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roles", nargs="+", required=True)
    parser.add_argument("--profile", type=Path, help="Explicitly selected JSON profile")
    parser.add_argument(
        "--subagents", action="store_true", help="Host can spawn subagents"
    )
    parser.add_argument(
        "--model-override",
        action="store_true",
        help="Host can select a model per spawn",
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Host can run independent subagents concurrently",
    )
    args = parser.parse_args()
    try:
        result = resolve_dispatch(
            args.roles,
            args.profile.expanduser().resolve() if args.profile else None,
            subagents=args.subagents,
            model_override=args.model_override,
            parallel=args.parallel,
        )
    except (OSError, ValueError) as exc:
        print(json.dumps({"schema_version": 1, "status": "error", "reason": str(exc)}))
        sys.exit(2)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
