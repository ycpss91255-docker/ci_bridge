#!/usr/bin/env python3
"""Resolve the managed action catalog and downstream project manifest."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn


SCHEMA_VERSION = 1
CATALOG_TOP_LEVEL_KEYS = {"schema_version", "action"}
ACTION_KEYS = {"id", "description", "required_bindings"}
PROJECT_TOP_LEVEL_KEYS = {"schema_version", "pipeline", "bindings"}
BINDING_KEYS = {"script"}
IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")


class ConfigError(Exception):
    """A configuration error that must stop before task execution."""


@dataclass(frozen=True)
class Action:
    action_id: str
    description: str
    required_bindings: tuple[str, ...]
    source: Path


@dataclass(frozen=True)
class PlannedTask:
    action_id: str
    script: Path


def fail(message: str) -> NoReturn:
    raise ConfigError(message)


def load_toml(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as config_file:
            return tomllib.load(config_file)
    except FileNotFoundError:
        fail(f"required config not found: {path}")
    except tomllib.TOMLDecodeError as error:
        fail(f"invalid TOML in {path}: {error}")


def require_exact_keys(
    value: dict[str, object], allowed: set[str], context: str
) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        fail(f"{context}: unknown key(s): {', '.join(unknown)}")


def require_schema_version(config: dict[str, object], source: Path) -> None:
    version = config.get("schema_version")
    if version != SCHEMA_VERSION:
        fail(
            f"{source}: unsupported schema_version {version!r}; "
            f"expected {SCHEMA_VERSION}"
        )


def require_identifier(value: object, context: str) -> str:
    if not isinstance(value, str) or IDENTIFIER_PATTERN.fullmatch(value) is None:
        fail(f"{context} must match {IDENTIFIER_PATTERN.pattern}: {value!r}")
    return value


def load_catalog(catalog_dir: Path) -> dict[str, Action]:
    sources = sorted(catalog_dir.glob("*.toml"))
    if not sources:
        fail(f"managed action catalog is empty: {catalog_dir}")

    actions: dict[str, Action] = {}
    for source in sources:
        config = load_toml(source)
        require_exact_keys(config, CATALOG_TOP_LEVEL_KEYS, str(source))
        require_schema_version(config, source)

        raw_action = config.get("action")
        if not isinstance(raw_action, dict):
            fail(f"{source}: action must be a TOML table")
        require_exact_keys(raw_action, ACTION_KEYS, f"{source}: action")

        action_id = raw_action.get("id")
        description = raw_action.get("description")
        required_bindings = raw_action.get("required_bindings")
        action_id = require_identifier(action_id, f"{source}: action.id")
        if not isinstance(description, str) or not description:
            fail(f"{source}: action.description must be a non-empty string")
        if not isinstance(required_bindings, list) or not required_bindings:
            fail(f"{source}: action.required_bindings must be a non-empty array")
        if not all(isinstance(item, str) and item for item in required_bindings):
            fail(f"{source}: every required binding must be a non-empty string")
        if len(set(required_bindings)) != len(required_bindings):
            fail(f"{source}: action.required_bindings contains duplicates")
        unsupported_bindings = sorted(set(required_bindings) - BINDING_KEYS)
        if unsupported_bindings:
            fail(
                f"{source}: unsupported required binding(s): "
                f"{', '.join(unsupported_bindings)}"
            )
        if action_id in actions:
            fail(
                f"duplicate action id '{action_id}' in {actions[action_id].source} "
                f"and {source}"
            )

        actions[action_id] = Action(
            action_id=action_id,
            description=description,
            required_bindings=tuple(required_bindings),
            source=source,
        )

    return actions


def resolve_script(repo_root: Path, raw_path: object, context: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path:
        fail(f"{context}: script must be a non-empty string")

    relative_path = Path(raw_path)
    if any(character in raw_path for character in "\t\r\n"):
        fail(f"{context}: script contains a forbidden control character")
    if relative_path.is_absolute() or ".." in relative_path.parts:
        fail(f"{context}: script must be a repo-relative path without '..': {raw_path}")

    resolved_root = repo_root.resolve()
    resolved_script = (resolved_root / relative_path).resolve()
    if not resolved_script.is_relative_to(resolved_root):
        fail(f"{context}: script resolves outside the repository: {raw_path}")
    if not resolved_script.is_file():
        fail(f"{context}: script not found: {raw_path}")
    if resolved_script.stat().st_mode & 0o111 == 0:
        fail(f"{context}: script is not executable: {raw_path}")

    return resolved_script.relative_to(resolved_root)


def load_project(
    repo_root: Path, actions: dict[str, Action]
) -> dict[str, object]:
    source = repo_root / "ci-project.toml"
    config = load_toml(source)
    require_exact_keys(config, PROJECT_TOP_LEVEL_KEYS, str(source))
    require_schema_version(config, source)

    pipeline = config.get("pipeline")
    bindings = config.get("bindings")
    if not isinstance(pipeline, list) or not pipeline:
        fail(f"{source}: pipeline must select at least one action")
    if len(set(map(str, pipeline))) != len(pipeline):
        fail(f"{source}: pipeline contains duplicate action IDs")
    selected_ids = [
        require_identifier(action_id, f"{source}: pipeline action ID")
        for action_id in pipeline
    ]
    unknown_actions = sorted(set(selected_ids) - set(actions))
    if unknown_actions:
        fail(f"{source}: pipeline selects unknown action(s): {', '.join(unknown_actions)}")
    if not isinstance(bindings, dict):
        fail(f"{source}: bindings must be a TOML table")

    for raw_action_id, raw_binding in bindings.items():
        action_id = require_identifier(raw_action_id, f"{source}: binding action ID")
        action = actions.get(action_id)
        if action is None:
            fail(f"{source}: binding names unknown action: {action_id}")
        if not isinstance(raw_binding, dict):
            fail(f"{source}: bindings.{action_id} must be a TOML table")
        require_exact_keys(
            raw_binding, BINDING_KEYS, f"{source}: bindings.{action_id}"
        )
        missing = [key for key in action.required_bindings if key not in raw_binding]
        if missing:
            fail(
                f"action '{action_id}' missing required binding(s): "
                f"{', '.join(missing)}"
            )
        resolve_script(
            repo_root,
            raw_binding["script"],
            f"{source}: bindings.{action_id}",
        )

    missing_binding_tables = [
        action_id for action_id in selected_ids if action_id not in bindings
    ]
    if missing_binding_tables:
        fail(
            f"{source}: selected action(s) missing binding tables: "
            f"{', '.join(missing_binding_tables)}"
        )
    return config


def selected_action_ids(
    project: dict[str, object], mode: str, target: str
) -> list[str]:
    if mode == "action":
        return [target]
    if target != "ci":
        fail(f"unknown pipeline: {target}")
    selected = project["pipeline"]
    assert isinstance(selected, list)
    return selected


def build_plan(repo_root: Path, mode: str, target: str) -> list[PlannedTask]:
    actions = load_catalog(repo_root / ".ci_action" / "catalog")
    project = load_project(repo_root, actions)
    bindings = project["bindings"]
    assert isinstance(bindings, dict)

    plan: list[PlannedTask] = []
    for action_id in selected_action_ids(project, mode, target):
        action = actions.get(action_id)
        if action is None:
            fail(f"unknown action selected by project: {action_id}")

        raw_binding = bindings.get(action_id)
        if not isinstance(raw_binding, dict):
            fail(f"action '{action_id}' requires a [bindings.{action_id}] table")

        script = resolve_script(
            repo_root,
            raw_binding["script"],
            f"ci-project.toml: bindings.{action_id}",
        )
        plan.append(PlannedTask(action_id=action_id, script=script))

    if not plan:
        fail("resolved plan contains zero tasks")
    return plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("mode", choices=("catalog", "action", "pipeline"))
    parser.add_argument("target", nargs="?")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.mode == "catalog":
            if args.target is not None:
                fail("catalog accepts no target")
            catalog = load_catalog(args.repo_root / ".ci_action" / "catalog")
            for action_id, action in sorted(catalog.items()):
                print(f"{action_id}\t{action.source.relative_to(args.repo_root)}")
            return 0

        if args.target is None:
            fail(f"{args.mode} requires a target")
        plan = build_plan(args.repo_root, args.mode, args.target)
    except ConfigError as error:
        print(f"ci-bridge: {error}", file=sys.stderr)
        return 2

    for task in plan:
        print(f"{task.action_id}\t{task.script}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
