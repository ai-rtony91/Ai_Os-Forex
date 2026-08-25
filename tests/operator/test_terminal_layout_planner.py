import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "automation" / "operator" / "terminal_layout_planner.py"
PROFILE_PATH = (
    ROOT
    / "automation"
    / "operator"
    / "layout_profiles"
    / "AIOS_TERMINAL_GRID_PROFILE.example.json"
)


def load_module():
    spec = importlib.util.spec_from_file_location("terminal_layout_planner", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def planner():
    return load_module()


@pytest.fixture
def profile():
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def test_example_profile_uses_canonical_working_directory(profile):
    assert all(pane["working_directory"] == r"C:\Dev\Ai.Os" for pane in profile["panes"])
    prohibited_legacy_root = "C:" + r"\Users\mylab\OneDrive\GitHub"
    assert prohibited_legacy_root not in json.dumps(profile)


def test_example_profile_produces_gap_free_four_column_plan(planner, profile):
    result = planner.build_terminal_layout_plan(profile)

    assert result["schema"] == "AIOS_TERMINAL_LAYOUT_PLAN.v1"
    assert result["status"] == "PLANNED_NOT_LAUNCHED"
    assert [pane["bounds_px"] for pane in result["panes"]] == [
        {"x": 0, "y": 0, "width": 860, "height": 1440},
        {"x": 860, "y": 0, "width": 860, "height": 1440},
        {"x": 1720, "y": 0, "width": 860, "height": 1440},
        {"x": 2580, "y": 0, "width": 860, "height": 1440},
    ]
    assert not any(result["safety"].values())
    assert all("startup_command" not in pane for pane in result["panes"])


def test_uneven_dimensions_and_spans_have_no_rounding_gap(planner, profile):
    profile["display"]["target_width_px"] = 10
    profile["display"]["target_height_px"] = 7
    profile["grid"] = {
        "columns": 3,
        "rows": 1,
        "layout_strategy": "test grid",
        "reserved_zones": [],
    }
    profile["panes"] = [copy.deepcopy(profile["panes"][0])]
    profile["panes"][0]["grid_position"] = {
        "column": 1,
        "row": 1,
        "column_span": 3,
        "row_span": 1,
    }

    result = planner.build_terminal_layout_plan(profile)

    assert result["panes"][0]["bounds_px"] == {
        "x": 0,
        "y": 0,
        "width": 10,
        "height": 7,
    }


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.update(mode="apply"), "mode must be 'schema_only'"),
        (
            lambda value: value["trading_safety"].update(live_trading_enabled=True),
            "live_trading_enabled must be false",
        ),
        (
            lambda value: value["panes"][0].update(startup_command="pwsh"),
            "startup_command must be null",
        ),
        (
            lambda value: value["panes"][0]["blocked_actions"].remove("live_trading"),
            "blocked_actions is missing: live_trading",
        ),
        (
            lambda value: value["panes"][1].update(
                grid_position={"column": 1, "row": 1, "column_span": 1, "row_span": 1}
            ),
            "overlaps another pane",
        ),
        (
            lambda value: value["panes"][0]["grid_position"].update(column=5),
            "outside the declared grid",
        ),
    ],
)
def test_unsafe_or_invalid_profiles_fail_closed(planner, profile, mutate, message):
    mutate(profile)

    with pytest.raises(planner.ProfileValidationError, match=message):
        planner.build_terminal_layout_plan(profile)


def test_cli_prints_plan_without_writing_files(planner, capsys, tmp_path, profile):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    before = set(tmp_path.iterdir())

    assert planner.main([str(profile_path)]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "PLANNED_NOT_LAUNCHED"
    assert set(tmp_path.iterdir()) == before


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.update(schema_version="2.0.0"), "schema_version must be"),
        (lambda value: value["grid"]["reserved_zones"].append({}), "must be empty"),
        (
            lambda value: value["panes"][0]["allowed_actions"].append("live_trading"),
            "conflicts with blocked_actions",
        ),
        (
            lambda value: value["validation"].update(manual_review_required=False),
            "manual_review_required must be true",
        ),
        (
            lambda value: value["panes"][0]["notes"].append(7),
            "notes must contain only non-empty strings",
        ),
        (
            lambda value: value["display"].update(target_width_px=100_001),
            "target_width_px must not exceed",
        ),
    ],
)
def test_untrusted_profile_metadata_fails_closed(planner, profile, mutate, message):
    mutate(profile)

    with pytest.raises(planner.ProfileValidationError, match=message):
        planner.build_terminal_layout_plan(profile)


def test_loader_rejects_duplicate_json_keys(planner, tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text('{"profile_id": "first", "profile_id": "second"}', encoding="utf-8")

    with pytest.raises(planner.ProfileValidationError, match="duplicate JSON key: profile_id"):
        planner.load_and_plan(profile_path)


def test_loader_rejects_oversized_profile_before_parsing(planner, tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_bytes(b" " * (planner.MAX_PROFILE_BYTES + 1))

    with pytest.raises(planner.ProfileValidationError, match="must not exceed"):
        planner.load_and_plan(profile_path)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(launcher_command="pwsh"),
        lambda value: value["panes"][0].update(executable=True),
        lambda value: value["panes"][0]["grid_position"].update(z_index=1),
        lambda value: value["validation"].update(auto_approve=True),
    ],
)
def test_profile_rejects_unsupported_fields(planner, profile, mutate):
    mutate(profile)

    with pytest.raises(planner.ProfileValidationError, match="contains unsupported fields"):
        planner.build_terminal_layout_plan(profile)


def test_profile_rejects_terminal_control_characters(planner, profile):
    profile["panes"][0]["title"] = "Operator\x1b[2J"

    with pytest.raises(planner.ProfileValidationError, match="must be a non-empty string"):
        planner.build_terminal_layout_plan(profile)


def test_loader_rejects_non_finite_json_numbers(planner, tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text('{"value": NaN}', encoding="utf-8")

    with pytest.raises(planner.ProfileValidationError, match="non-finite JSON number"):
        planner.load_and_plan(profile_path)


def test_loader_rejects_symbolic_link(planner, tmp_path, monkeypatch):
    target = tmp_path / "profile.json"
    target.write_text("{}", encoding="utf-8")
    link = tmp_path / "profile-link.json"
    link.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(planner.Path, "is_symlink", lambda self: self == link or Path.is_symlink(self))

    with pytest.raises(planner.ProfileValidationError, match="must not be a symbolic link"):
        planner.load_and_plan(link)
