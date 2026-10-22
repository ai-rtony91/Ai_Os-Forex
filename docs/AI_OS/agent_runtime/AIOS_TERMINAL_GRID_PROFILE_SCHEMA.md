# AIOS Terminal Grid Profile Schema

## Purpose

This file defines the schema-only planning contract for future AI_OS terminal grid layout profiles.

The schema is for local operator planning only. It does not launch terminals, create startup persistence, register scheduled tasks, connect brokers, call OANDA, store API keys, store secrets, or enable live trading.

## Scope

Allowed profile files live under:

- `automation/operator/layout_profiles/`

The first example profile is:

- `automation/operator/layout_profiles/AIOS_TERMINAL_GRID_PROFILE.example.json`

## Non-goals

This schema does not create or approve:

- A launcher script.
- `Start-AIOSTerminalGrid.ps1`.
- Edits to `Start-AIOSMultiCodexWorkers.ps1`.
- Startup persistence.
- Scheduled tasks.
- Broker connections.
- OANDA integration.
- API key handling.
- Secret handling.
- Live trading.

## Required top-level fields

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `schema_version` | string | Yes | Must be `1.0.0`. |
| `profile_id` | string | Yes | Stable machine-readable identifier for the profile. |
| `profile_name` | string | Yes | Human-readable profile name. |
| `profile_type` | string | Yes | Must be `terminal_grid_layout_profile`. |
| `mode` | string | Yes | Must be `schema_only` until a future approved launcher exists. |
| `local_only` | boolean | Yes | Must be `true`. |
| `startup_persistence` | boolean | Yes | Must be `false`. |
| `scheduled_tasks` | boolean | Yes | Must be `false`. |
| `trading_safety` | object | Yes | Safety assertions that keep the profile paper-only and non-executing. |
| `display` | object | Yes | Planning metadata for the target display. |
| `grid` | object | Yes | Row and column planning metadata. |
| `panes` | array | Yes | Planned terminal panes. |
| `validation` | object | Yes | Manual validation expectations. |
| `notes` | array | Yes | Operator-readable notes and constraints. |

The profile is a closed object: fields not listed above are rejected. All
required string values must be non-empty and must not contain terminal control
characters. String arrays must contain unique, non-empty strings without
terminal control characters.

## `trading_safety` object

| Field | Type | Required | Required value |
| --- | --- | --- | --- |
| `live_trading_enabled` | boolean | Yes | `false` |
| `broker_connection_enabled` | boolean | Yes | `false` |
| `oanda_enabled` | boolean | Yes | `false` |
| `api_keys_allowed` | boolean | Yes | `false` |
| `secrets_allowed` | boolean | Yes | `false` |
| `real_orders_allowed` | boolean | Yes | `false` |

The `trading_safety` object is closed; additional fields are rejected.

## `display` object

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `target_width_px` | integer | Yes | Planned display width in pixels. Must be from 1 through 100,000. |
| `target_height_px` | integer | Yes | Planned display height in pixels. Must be from 1 through 100,000. |
| `display_label` | string | Yes | Operator-friendly display name. |
| `scaling_note` | string | Yes | Note for DPI or scaling assumptions. |

The `display` object is closed; additional fields are rejected.

## `grid` object

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `columns` | integer | Yes | Planned number of columns. |
| `rows` | integer | Yes | Planned number of rows. |
| `layout_strategy` | string | Yes | Operator-readable layout approach. |
| `reserved_zones` | array | Yes | Must be an empty array until reserved-zone planning is implemented. |

### Grid constraints

- `columns` and `rows` must be integers from 1 through 100.
- Every pane must fit completely inside the declared grid.
- Pane rectangles must not overlap.
- Every `pane_id` must be unique.
- Empty grid cells are allowed.
- The `grid` object is closed; additional fields are rejected.

Reserved-zone item objects are not part of version `1.0.0`. A non-empty
`reserved_zones` array is rejected rather than ignored.

## `panes` array item

Each pane is a planned terminal area only.

The profile must contain from 1 through 1,000 panes. Each pane is a closed
object; additional fields are rejected.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `pane_id` | string | Yes | Stable pane identifier. |
| `title` | string | Yes | Operator-readable pane title. |
| `role` | string | Yes | Planned role, such as `operator_console`, `codex_worker`, `validator`, or `telemetry_viewer`. |
| `grid_position` | object | Yes | Column and row placement metadata. |
| `working_directory` | string | Yes | Planned local working directory. |
| `startup_command` | string or null | Yes | Must be `null` while this remains schema-only. |
| `allowed_actions` | array | Yes | Planning-only action labels. |
| `blocked_actions` | array | Yes | Actions that must not happen from this pane. |
| `notes` | array | Yes | Operator-readable pane notes. |

## `grid_position` object

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `column` | integer | Yes | One-based starting column. |
| `row` | integer | Yes | One-based starting row. |
| `column_span` | integer | Yes | Number of columns used by the pane. |
| `row_span` | integer | Yes | Number of rows used by the pane. |

All four position values must be positive integers. The `grid_position` object
is closed; additional fields are rejected.

## `validation` object

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `json_parse_required` | boolean | Yes | Must be `true` for JSON profile files. |
| `launcher_required` | boolean | Yes | Must be `false` until a future approved implementation task. |
| `manual_review_required` | boolean | Yes | Must be `true`. |
| `expected_checks` | array | Yes | Validation checks an operator should run or confirm. |

The `validation` object is closed; additional fields are rejected.

## Planner result contract

The reference implementation returns a deterministic, non-executable object
with:

- `schema: "AIOS_TERMINAL_LAYOUT_PLAN.v1"`.
- `status: "PLANNED_NOT_LAUNCHED"`.
- The validated profile ID and name.
- The display dimensions and grid track counts.
- Pane identity, role, working directory, grid position, and calculated pixel
  bounds. It does not copy `startup_command`, action labels, or notes into the
  result.
- Safety flags confirming that commands, windows, persistence, scheduled tasks,
  and broker or live-trading behavior were not enabled. Every flag is `false`.

Pixel track edges use integer division from the display origin. This makes
adjacent pane bounds gap-free even when a display dimension is not evenly
divisible by its track count.

## Profile file loading constraints

The reference implementation accepts only a regular, non-symbolic-link UTF-8
JSON file no larger than 1,000,000 bytes. It rejects duplicate object keys and
non-finite JSON numbers such as `NaN` and `Infinity`.

## Validation procedure

A profile is validated only when all of these checks pass:

1. Parse the profile as JSON.
2. Confirm every required field and nested field listed in this contract exists and has the declared type.
3. Confirm all constant safety values match this contract, including `mode: "schema_only"`, `local_only: true`, and every execution or persistence control set to `false`.
4. Reject unsupported fields at every closed-object level, unsafe text, duplicate string-array values, duplicate JSON keys, and non-finite numbers.
5. Confirm `reserved_zones` is empty and the display, grid, and pane counts are within their limits.
6. Confirm every pane has `startup_command: null`.
7. Confirm pane IDs are unique, pane positions are in bounds, and pane rectangles do not overlap.
8. Confirm each pane blocks `live_trading`, `broker_connection`, `oanda_connection`, `startup_persistence`, and `scheduled_task_creation`, and that no action appears in both its allowed and blocked lists.
9. Confirm the profile contains no credential values, API keys, secrets, broker endpoints, or executable commands.
10. Run `git diff --check` after changes.

Parsing alone is necessary but is not sufficient to validate conformance to this contract.

## Safety invariants

A valid schema-only terminal grid profile must keep these invariants true:

1. It is local-only.
2. It does not define a runnable launcher.
3. It does not create startup persistence.
4. It does not create scheduled tasks.
5. It does not store or reference secrets.
6. It does not connect to brokers.
7. It does not enable OANDA.
8. It does not place real orders.
9. It keeps any trading-related usage paper-only and non-executing.
10. It remains an operator planning artifact until a future APPLY task explicitly approves implementation.
11. Its pane identifiers are unique and its pane rectangles are in bounds and non-overlapping.

## Example

See `automation/operator/layout_profiles/AIOS_TERMINAL_GRID_PROFILE.example.json` for a parseable example profile.
