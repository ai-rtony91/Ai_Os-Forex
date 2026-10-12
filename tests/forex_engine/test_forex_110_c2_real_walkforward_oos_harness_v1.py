from __future__ import annotations

import inspect
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.forex_engine.forex_110_c2_real_walkforward_oos_harness_v1 import (  # noqa: E402
    HARNESS_BLOCKED,
    TARGET_CANDIDATE_ID,
    build_default_c2_harness_input,
    build_report_markdown,
    build_source_markdown,
    run_c2_real_walkforward_oos_harness,
)
from scripts.forex_delivery.run_forex_110_c2_real_walkforward_oos_harness_v1 import (  # noqa: E402
    REPORT_NAME,
    SOURCE_NAME,
    STATE_NAME,
    main,
)


PROTECTED_FLAGS = (
    "next_demo_trade_allowed",
    "broker_action_allowed",
    "real_money_allowed",
    "compounding_allowed",
    "bank_movement_allowed",
    "live_trading_allowed",
    "credential_access_allowed",
    "order_submission_allowed",
    "owner_approval_created",
)


def assert_permissions_false(result: dict) -> None:
    for flag in PROTECTED_FLAGS:
        assert result[flag] is False
        assert result["permissions"][flag] is False


def test_default_synthetic_fixture_is_blocked_as_real_source() -> None:
    result = run_c2_real_walkforward_oos_harness()

    assert result["harness_status"] == HARNESS_BLOCKED
    assert result["candidate"] == TARGET_CANDIDATE_ID
    assert result["candidate_alignment"] == "ALIGNED"
    assert result["walkforward_oos_status"] == "WALK_FORWARD_OOS_READY"
    assert result["windows_total"] == 6
    assert result["windows_passed"] == 6
    assert result["oos_segments_total"] == 4
    assert result["oos_segments_passed"] == 4
    assert result["source_is_real_sanitized_local"] is False
    assert result["source_is_test_or_sample"] is True
    assert "default walk-forward/OOS inputs are synthetic sample data" in result["blockers"]
    assert_permissions_false(result)



def test_explicit_default_fixture_payload_is_blocked_as_real_source() -> None:
    result = run_c2_real_walkforward_oos_harness(build_default_c2_harness_input())

    assert result["harness_status"] == HARNESS_BLOCKED
    assert result["source_is_real_sanitized_local"] is False
    assert result["source_is_test_or_sample"] is True
    assert "default walk-forward/OOS inputs are synthetic sample data" in result["blockers"]
    with pytest.raises(ValueError, match="source markdown requires proven harness evidence"):
        build_source_markdown(result)
    assert_permissions_false(result)

def test_harness_blocks_wrong_candidate() -> None:
    payload = build_default_c2_harness_input()
    payload["candidate"] = "c1-eur-buy"

    result = run_c2_real_walkforward_oos_harness(payload)

    assert result["harness_status"] == HARNESS_BLOCKED
    assert result["candidate_alignment"] == "BLOCKED_CANDIDATE_MISMATCH"
    assert "candidate is not aligned to C2 target" in result["blockers"]
    assert_permissions_false(result)


def test_harness_blocks_insufficient_oos_segments() -> None:
    payload = build_default_c2_harness_input()
    payload["oos_segments"] = payload["oos_segments"][:2]

    result = run_c2_real_walkforward_oos_harness(payload)

    assert result["harness_status"] == HARNESS_BLOCKED
    assert "insufficient OOS segments" in result["blockers"]
    assert_permissions_false(result)


def test_markdown_outputs_are_consumable_and_review_only() -> None:
    result = run_c2_real_walkforward_oos_harness()
    report = build_report_markdown(result)

    assert "Harness status: `BLOCKED_REAL_WALKFORWARD_OOS_HARNESS`" in report
    with pytest.raises(ValueError, match="source markdown requires proven harness evidence"):
        build_source_markdown(result)


def test_runner_writes_state_and_report_but_not_source_for_default_fixture(tmp_path: Path) -> None:
    exit_code = main(
        [
            "--output-root",
            str(tmp_path),
            "--write-state",
            "--write-report",
            "--write-source",
        ]
    )
    state = json.loads((tmp_path / STATE_NAME).read_text(encoding="utf-8"))

    assert exit_code == 0
    assert state["harness_status"] == HARNESS_BLOCKED
    assert state["source_is_real_sanitized_local"] is False
    assert state["source_is_test_or_sample"] is True
    assert (tmp_path / REPORT_NAME).exists()
    assert not (tmp_path / SOURCE_NAME).exists()


def test_module_source_has_no_external_or_execution_access() -> None:
    import automation.forex_engine.forex_110_c2_real_walkforward_oos_harness_v1 as harness

    source = inspect.getsource(harness)
    forbidden = (
        "import requests",
        "from requests",
        "import urllib",
        "from urllib",
        "import subprocess",
        "from subprocess",
        "import socket",
        "from socket",
        "os.environ",
        "getenv(",
        "write_text",
        "write_bytes",
        "open(",
    )
    for token in forbidden:
        assert token not in source


def test_report_formatter_blocks_historical_and_forged_proof_labels():
    import copy
    historical = json.loads((Path(__file__).with_name("fixtures") / "c2_historical_false_proven_state.json").read_text())
    historical["source_authentication_status"] = "VERIFIED"
    for key in historical.get("permissions", {}):
        historical["permissions"][key] = True
    before = copy.deepcopy(historical)
    report = build_report_markdown(historical)
    for forbidden in ['PROVEN_REAL_WALKFORWARD_OOS_HARNESS']:
        assert forbidden not in report
    assert "NO_INDEPENDENT_VERIFIER_CONNECTED" in report
    for flag in PROTECTED_FLAGS:
        assert f"{flag}: `false`" in report
    assert historical == before
