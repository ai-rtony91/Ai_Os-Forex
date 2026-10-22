"""Validate a schema-only terminal grid profile and produce a pixel layout plan.

This module is deliberately a planner, not a launcher.  It never starts a
process, moves a window, persists configuration, or evaluates pane commands.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path
from typing import Any, NoReturn


SCHEMA = "AIOS_TERMINAL_LAYOUT_PLAN.v1"
PROFILE_SCHEMA_VERSION = "1.0.0"
PROFILE_TYPE = "terminal_grid_layout_profile"
MAX_PROFILE_BYTES = 1_000_000
MAX_DISPLAY_DIMENSION_PX = 100_000
MAX_GRID_TRACKS = 100
MAX_PANES = 1_000
REQUIRED_BLOCKED_ACTIONS = {
    "live_trading",
    "broker_connection",
    "oanda_connection",
    "startup_persistence",
    "scheduled_task_creation",
}
TRADING_SAFETY_FIELDS = {
    "live_trading_enabled",
    "broker_connection_enabled",
    "oanda_enabled",
    "api_keys_allowed",
    "secrets_allowed",
    "real_orders_allowed",
}

PROFILE_FIELDS = {
    "schema_version", "profile_id", "profile_name", "profile_type", "mode",
    "local_only", "startup_persistence", "scheduled_tasks", "trading_safety",
    "display", "grid", "panes", "validation", "notes",
}
DISPLAY_FIELDS = {"target_width_px", "target_height_px", "display_label", "scaling_note"}
GRID_FIELDS = {"columns", "rows", "layout_strategy", "reserved_zones"}
PANE_FIELDS = {
    "pane_id", "title", "role", "grid_position", "working_directory",
    "startup_command", "allowed_actions", "blocked_actions", "notes",
}
POSITION_FIELDS = {"column", "row", "column_span", "row_span"}
VALIDATION_FIELDS = {
    "json_parse_required", "launcher_required", "manual_review_required", "expected_checks",
}


class ProfileValidationError(ValueError):
    """Raised when a terminal grid profile is unsafe or malformed."""


def _fail(message: str) -> NoReturn:
    raise ProfileValidationError(message)


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{field} must be an object")
    return value


def _array(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(f"{field} must be an array")
    return value


def _text_array(value: Any, field: str) -> list[str]:
    values = _array(value, field)
    if not all(_is_safe_text(item) for item in values):
        _fail(f"{field} must contain only non-empty strings")
    if len(values) != len(set(values)):
        _fail(f"{field} must not contain duplicates")
    return values


def _text(value: Any, field: str) -> str:
    if not _is_safe_text(value):
        _fail(f"{field} must be a non-empty string")
    return value


def _is_safe_text(value: Any) -> bool:
    """Return whether text is nonblank and safe to print in a terminal plan."""
    return (
        isinstance(value, str)
        and bool(value.strip())
        and not any(ord(character) < 32 or ord(character) == 127 for character in value)
    )


def _closed_object(mapping: dict[str, Any], allowed: set[str], field: str) -> None:
    unexpected = set(mapping).difference(allowed)
    if unexpected:
        _fail(f"{field} contains unsupported fields: {', '.join(sorted(unexpected))}")


def _positive_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail(f"{field} must be a positive integer")
    return value


def _bounded_positive_integer(value: Any, field: str, maximum: int) -> int:
    result = _positive_integer(value, field)
    if result > maximum:
        _fail(f"{field} must not exceed {maximum}")
    return result


def _required(mapping: dict[str, Any], field: str, parent: str = "profile") -> Any:
    if field not in mapping:
        _fail(f"{parent}.{field} is required")
    return mapping[field]


def _track_edges(length: int, count: int) -> list[int]:
    """Return gap-free integer track boundaries for a dimension."""
    return [(index * length) // count for index in range(count + 1)]


def build_terminal_layout_plan(profile: dict[str, Any]) -> dict[str, Any]:
    """Validate *profile* and return a deterministic, non-executable plan."""
    if not isinstance(profile, dict):
        _fail("profile must be an object")
    _closed_object(profile, PROFILE_FIELDS, "profile")

    profile_id = _text(_required(profile, "profile_id"), "profile.profile_id")
    profile_name = _text(_required(profile, "profile_name"), "profile.profile_name")
    if _required(profile, "schema_version") != PROFILE_SCHEMA_VERSION:
        _fail(f"profile.schema_version must be '{PROFILE_SCHEMA_VERSION}'")
    if _required(profile, "profile_type") != PROFILE_TYPE:
        _fail(f"profile.profile_type must be '{PROFILE_TYPE}'")

    if _required(profile, "mode") != "schema_only":
        _fail("profile.mode must be 'schema_only'")
    for field, expected in (
        ("local_only", True),
        ("startup_persistence", False),
        ("scheduled_tasks", False),
    ):
        if _required(profile, field) is not expected:
            _fail(f"profile.{field} must be {str(expected).lower()}")

    safety = _object(_required(profile, "trading_safety"), "profile.trading_safety")
    _closed_object(safety, TRADING_SAFETY_FIELDS, "profile.trading_safety")
    for field in sorted(TRADING_SAFETY_FIELDS):
        if _required(safety, field, "profile.trading_safety") is not False:
            _fail(f"profile.trading_safety.{field} must be false")

    display = _object(_required(profile, "display"), "profile.display")
    _closed_object(display, DISPLAY_FIELDS, "profile.display")
    width = _bounded_positive_integer(
        _required(display, "target_width_px", "profile.display"),
        "profile.display.target_width_px",
        MAX_DISPLAY_DIMENSION_PX,
    )
    height = _bounded_positive_integer(
        _required(display, "target_height_px", "profile.display"),
        "profile.display.target_height_px",
        MAX_DISPLAY_DIMENSION_PX,
    )
    _text(_required(display, "display_label", "profile.display"), "profile.display.display_label")
    _text(_required(display, "scaling_note", "profile.display"), "profile.display.scaling_note")

    grid = _object(_required(profile, "grid"), "profile.grid")
    _closed_object(grid, GRID_FIELDS, "profile.grid")
    columns = _bounded_positive_integer(
        _required(grid, "columns", "profile.grid"),
        "profile.grid.columns",
        MAX_GRID_TRACKS,
    )
    rows = _bounded_positive_integer(
        _required(grid, "rows", "profile.grid"), "profile.grid.rows", MAX_GRID_TRACKS
    )
    _text(_required(grid, "layout_strategy", "profile.grid"), "profile.grid.layout_strategy")
    reserved_zones = _array(
        _required(grid, "reserved_zones", "profile.grid"), "profile.grid.reserved_zones"
    )
    if reserved_zones:
        _fail("profile.grid.reserved_zones must be empty until reserved zones are supported")

    panes = _array(_required(profile, "panes"), "profile.panes")
    if not panes:
        _fail("profile.panes must contain at least one pane")
    if len(panes) > MAX_PANES:
        _fail(f"profile.panes must not contain more than {MAX_PANES} panes")

    x_edges = _track_edges(width, columns)
    y_edges = _track_edges(height, rows)
    occupied: set[tuple[int, int]] = set()
    pane_ids: set[str] = set()
    planned_panes: list[dict[str, Any]] = []

    for index, raw_pane in enumerate(panes):
        prefix = f"profile.panes[{index}]"
        pane = _object(raw_pane, prefix)
        _closed_object(pane, PANE_FIELDS, prefix)
        pane_id = _text(_required(pane, "pane_id", prefix), f"{prefix}.pane_id")
        if pane_id in pane_ids:
            _fail(f"{prefix}.pane_id duplicates '{pane_id}'")
        pane_ids.add(pane_id)

        title = _text(_required(pane, "title", prefix), f"{prefix}.title")
        role = _text(_required(pane, "role", prefix), f"{prefix}.role")
        working_directory = _text(
            _required(pane, "working_directory", prefix), f"{prefix}.working_directory"
        )
        if _required(pane, "startup_command", prefix) is not None:
            _fail(f"{prefix}.startup_command must be null")
        allowed = _text_array(
            _required(pane, "allowed_actions", prefix), f"{prefix}.allowed_actions"
        )
        blocked = _text_array(
            _required(pane, "blocked_actions", prefix), f"{prefix}.blocked_actions"
        )
        missing_blocks = REQUIRED_BLOCKED_ACTIONS.difference(blocked)
        if missing_blocks:
            _fail(f"{prefix}.blocked_actions is missing: {', '.join(sorted(missing_blocks))}")
        conflicting_actions = set(allowed).intersection(blocked)
        if conflicting_actions:
            _fail(
                f"{prefix}.allowed_actions conflicts with blocked_actions: "
                f"{', '.join(sorted(conflicting_actions))}"
            )
        _text_array(_required(pane, "notes", prefix), f"{prefix}.notes")

        position = _object(_required(pane, "grid_position", prefix), f"{prefix}.grid_position")
        _closed_object(position, POSITION_FIELDS, f"{prefix}.grid_position")
        column = _positive_integer(
            _required(position, "column", f"{prefix}.grid_position"),
            f"{prefix}.grid_position.column",
        )
        row = _positive_integer(
            _required(position, "row", f"{prefix}.grid_position"),
            f"{prefix}.grid_position.row",
        )
        column_span = _positive_integer(
            _required(position, "column_span", f"{prefix}.grid_position"),
            f"{prefix}.grid_position.column_span",
        )
        row_span = _positive_integer(
            _required(position, "row_span", f"{prefix}.grid_position"),
            f"{prefix}.grid_position.row_span",
        )
        last_column = column + column_span - 1
        last_row = row + row_span - 1
        if last_column > columns or last_row > rows:
            _fail(f"{prefix}.grid_position is outside the declared grid")

        cells = {
            (cell_column, cell_row)
            for cell_column in range(column, last_column + 1)
            for cell_row in range(row, last_row + 1)
        }
        if cells & occupied:
            _fail(f"{prefix}.grid_position overlaps another pane")
        occupied.update(cells)

        left = x_edges[column - 1]
        top = y_edges[row - 1]
        right = x_edges[last_column]
        bottom = y_edges[last_row]
        planned_panes.append(
            {
                "pane_id": pane_id,
                "title": title,
                "role": role,
                "working_directory": working_directory,
                "grid_position": {
                    "column": column,
                    "row": row,
                    "column_span": column_span,
                    "row_span": row_span,
                },
                "bounds_px": {
                    "x": left,
                    "y": top,
                    "width": right - left,
                    "height": bottom - top,
                },
            }
        )

    validation = _object(_required(profile, "validation"), "profile.validation")
    _closed_object(validation, VALIDATION_FIELDS, "profile.validation")
    for field, expected in (
        ("json_parse_required", True),
        ("launcher_required", False),
        ("manual_review_required", True),
    ):
        if _required(validation, field, "profile.validation") is not expected:
            _fail(f"profile.validation.{field} must be {str(expected).lower()}")
    _text_array(
        _required(validation, "expected_checks", "profile.validation"),
        "profile.validation.expected_checks",
    )
    _text_array(_required(profile, "notes"), "profile.notes")

    return {
        "schema": SCHEMA,
        "status": "PLANNED_NOT_LAUNCHED",
        "profile_id": profile_id,
        "profile_name": profile_name,
        "display": {"width_px": width, "height_px": height},
        "grid": {"columns": columns, "rows": rows},
        "panes": planned_panes,
        "safety": {
            "executable_commands_included": False,
            "windows_launched": False,
            "startup_persistence_changed": False,
            "scheduled_tasks_changed": False,
            "broker_or_live_trading_enabled": False,
        },
    }


def load_and_plan(profile_path: Path) -> dict[str, Any]:
    """Load a JSON profile from disk and build its layout plan."""
    try:
        if profile_path.is_symlink():
            _fail("profile path must not be a symbolic link")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(profile_path, flags)
        with os.fdopen(descriptor, "rb") as profile_file:
            metadata = os.fstat(profile_file.fileno())
            if not stat.S_ISREG(metadata.st_mode):
                _fail("profile path must be a regular file")
            raw_profile = profile_file.read(MAX_PROFILE_BYTES + 1)
        if len(raw_profile) > MAX_PROFILE_BYTES:
            _fail(f"profile must not exceed {MAX_PROFILE_BYTES} bytes")
        profile = json.loads(
            raw_profile.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite_number,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProfileValidationError(f"cannot read profile: {exc}") from exc
    return build_terminal_layout_plan(profile)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject ambiguous JSON objects instead of silently accepting the last value."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_non_finite_number(value: str) -> NoReturn:
    _fail(f"non-finite JSON number is not allowed: {value}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate an AI_OS terminal grid profile and print a non-executable pixel plan."
    )
    parser.add_argument("profile", type=Path, help="path to a terminal grid profile JSON file")
    args = parser.parse_args(argv)
    try:
        plan = load_and_plan(args.profile)
    except ProfileValidationError as exc:
        parser.exit(2, f"BLOCKED: {exc}\n")
    print(json.dumps(plan, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
