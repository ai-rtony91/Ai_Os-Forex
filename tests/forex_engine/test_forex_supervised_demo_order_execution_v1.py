from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from automation.forex_engine.forex_supervised_demo_order_execution_v1 import (
    DEFAULT_RUNTIME_ALLOWED_MODES,
    OWNER_RUNTIME_ORDER_FLAG_REQUIRED,
    OWNER_SUPERVISED_DEMO_APPROVAL_REQUIRED,
    PREREQUISITES_REQUIRED,
    PROTECTED_BOUNDARY_VIOLATION,
    RUNTIME_CREDENTIAL_ACCESS_REQUIRED,
    PRACTICE_DEMO_BOUNDARY_REQUIRED,
    KILL_SWITCH_BLOCKED,
    EXECUTION_CONTROL_BLOCKED,
    SUPERVISED_DEMO_ORDER_READY,
    RUNTIME_MODE_DRY_RUN,
    RUNTIME_MODE_OWNER_APPROVED_SUPERVISED_DEMO_ORDER,
    SupervisedDemoOrderInput,
    build_default_input,
    evaluate_supervised_demo_order_execution,
)
from scripts.forex_delivery import run_forex_supervised_demo_order_execution_v1 as runtime_script
from scripts.forex_delivery.run_forex_supervised_demo_order_execution_v1 import (
    run_forex_supervised_demo_order_execution_v1,
)


def _input(**changes) -> SupervisedDemoOrderInput:
    return replace(build_default_input(), **changes)


def _runtime_ready_input() -> SupervisedDemoOrderInput:
    parsed_item_fields = {
        "broker_api_token": "token",
        "broker_account_id": "account",
        "endpoint": "https://api-fxpractice.oanda.com",
        "environment": "practice_demo",
        "allowed_mode": DEFAULT_RUNTIME_ALLOWED_MODES[0],
    }
    return _input(
        owner_supervised_demo_approval=True,
        owner_runtime_order_flag=True,
        bw_session_present=True,
        bitwarden_cli_available=True,
        bitwarden_item_read_success=True,
        credential_values_available_to_runtime=bool(parsed_item_fields),
        endpoint_is_oanda_practice=True,
        environment_is_practice_demo=True,
        allowed_mode_is_demo_only=True,
        broker_api_called=False,
        bitwarden_cli_called=False,
        credentials_read=False,
        env_file_read=False,
        demo_order_execution=False,
        live_order_execution=False,
        money_movement=False,
        scheduler_started=False,
        daemon_started=False,
        webhook_started=False,
        kill_switch_enabled=True,
        kill_switch_triggered=False,
        max_daily_loss_defined=True,
        daily_loss_within_limit=True,
        max_trade_risk_defined=True,
        proposed_trade_risk_within_limit=True,
        duplicate_order_guard_enabled=True,
        duplicate_order_detected=False,
        audit_log_enabled=True,
        audit_log_write_success=True,
        stop_loss_defined=True,
        take_profit_defined=True,
        units=1,
        side="buy",
        order_type="market",
        time_in_force="FOK",
        instrument="EUR_USD",
    )


def test_default_input_returns_owner_supervised_demo_approval_required():
    result = evaluate_supervised_demo_order_execution(_input())
    assert result.demo_order_status == OWNER_SUPERVISED_DEMO_APPROVAL_REQUIRED
    assert result.current_stage == "supervised_demo_order_execution"
    assert result.next_stage == "owner_supervised_demo_approval"


def test_missing_prerequisites_block():
    result = evaluate_supervised_demo_order_execution(
        _input(
            broker_runtime_read_only_auth_proven=False,
            execution_control_stack_landed=False,
        ),
    )
    assert result.demo_order_status == PREREQUISITES_REQUIRED
    assert result.next_stage == "complete_prior_execution_lanes"


def test_missing_owner_runtime_flag_blocks():
    result = evaluate_supervised_demo_order_execution(
        _input(owner_supervised_demo_approval=True, owner_runtime_order_flag=False),
    )
    assert result.demo_order_status == OWNER_RUNTIME_ORDER_FLAG_REQUIRED
    assert result.next_stage == "owner_run_supervised_demo_order"


def test_protected_boundary_flags_block():
    for field_name in [
        "broker_api_called",
        "bitwarden_cli_called",
        "credentials_read",
        "env_file_read",
        "demo_order_execution",
        "live_order_execution",
        "money_movement",
        "scheduler_started",
        "daemon_started",
        "webhook_started",
    ]:
        result = evaluate_supervised_demo_order_execution(
            _input(
                owner_supervised_demo_approval=True,
                owner_runtime_order_flag=True,
                **{field_name: True},
            ),
        )
        assert result.demo_order_status == PROTECTED_BOUNDARY_VIOLATION
        assert result.next_stage == "stop_and_owner_review"
        assert result.live_order_execution is False
        assert result.money_movement is False
        assert result.scheduler_started is False


def test_owner_approved_runtime_mode_allows_runtime_flags_and_reaches_ready():
    result = evaluate_supervised_demo_order_execution(
        _input(
            owner_supervised_demo_approval=True,
            owner_runtime_order_flag=True,
            runtime_mode=RUNTIME_MODE_OWNER_APPROVED_SUPERVISED_DEMO_ORDER,
            bw_session_present=True,
            bitwarden_cli_available=True,
            bitwarden_item_read_success=True,
            credential_values_available_to_runtime=True,
            broker_api_called=True,
            bitwarden_cli_called=True,
            credentials_read=True,
            demo_order_execution=False,
            live_order_execution=False,
            money_movement=False,
            scheduler_started=False,
            daemon_started=False,
            webhook_started=False,
            endpoint_is_oanda_practice=True,
            environment_is_practice_demo=True,
            allowed_mode_is_demo_only=True,
        ),
    )
    assert result.demo_order_status == SUPERVISED_DEMO_ORDER_READY
    assert result.runtime_mode == RUNTIME_MODE_OWNER_APPROVED_SUPERVISED_DEMO_ORDER
    assert result.broker_api_called is True
    assert result.bitwarden_cli_called is True
    assert result.credentials_read is True


def test_missing_runtime_access_blocked():
    for field_name in [
        "bw_session_present",
        "bitwarden_cli_available",
        "bitwarden_item_read_success",
        "credential_values_available_to_runtime",
    ]:
        kwargs = {
            "owner_supervised_demo_approval": True,
            "owner_runtime_order_flag": True,
        }
        for required in [
            "bw_session_present",
            "bitwarden_cli_available",
            "bitwarden_item_read_success",
            "credential_values_available_to_runtime",
        ]:
            kwargs[required] = required == field_name
        kwargs[field_name] = False
        result = evaluate_supervised_demo_order_execution(_input(**kwargs))
        assert result.demo_order_status == RUNTIME_CREDENTIAL_ACCESS_REQUIRED
        assert result.next_stage == "owner_unlock_bitwarden_cli"


def test_non_practice_boundary_blocks():
    for field_name in [
        "endpoint_is_oanda_practice",
        "environment_is_practice_demo",
        "allowed_mode_is_demo_only",
    ]:
        result = evaluate_supervised_demo_order_execution(
            _input(
                owner_supervised_demo_approval=True,
                owner_runtime_order_flag=True,
                bw_session_present=True,
                bitwarden_cli_available=True,
                bitwarden_item_read_success=True,
                credential_values_available_to_runtime=True,
                **{field_name: False},
            ),
        )
        assert result.demo_order_status == PRACTICE_DEMO_BOUNDARY_REQUIRED
        assert result.next_stage == "repair_demo_boundary"


def test_kill_switch_blocks_when_disabled_or_triggered():
    result = evaluate_supervised_demo_order_execution(
        _input(
            owner_supervised_demo_approval=True,
            owner_runtime_order_flag=True,
            bw_session_present=True,
            bitwarden_cli_available=True,
            bitwarden_item_read_success=True,
            credential_values_available_to_runtime=True,
            kill_switch_enabled=False,
        ),
    )
    assert result.demo_order_status == KILL_SWITCH_BLOCKED
    assert result.next_stage == "owner_review_required"

    result = evaluate_supervised_demo_order_execution(
        _input(
            owner_supervised_demo_approval=True,
            owner_runtime_order_flag=True,
            bw_session_present=True,
            bitwarden_cli_available=True,
            bitwarden_item_read_success=True,
            credential_values_available_to_runtime=True,
            kill_switch_triggered=True,
        ),
    )
    assert result.demo_order_status == KILL_SWITCH_BLOCKED
    assert result.next_stage == "owner_review_required"


def test_execution_controls_blocked_for_risk_audit_duplicate_or_sl_tp():
    for field_name in [
        "max_daily_loss_defined",
        "daily_loss_within_limit",
        "max_trade_risk_defined",
        "proposed_trade_risk_within_limit",
        "duplicate_order_guard_enabled",
        "audit_log_enabled",
        "audit_log_write_success",
        "stop_loss_defined",
        "take_profit_defined",
    ]:
        kwargs = {
            "owner_supervised_demo_approval": True,
            "owner_runtime_order_flag": True,
            "bw_session_present": True,
            "bitwarden_cli_available": True,
            "bitwarden_item_read_success": True,
            "credential_values_available_to_runtime": True,
            field_name: False if field_name not in {"duplicate_order_detected"} else True,
        }
        if field_name == "duplicate_order_guard_enabled":
            kwargs["duplicate_order_detected"] = False
        if field_name == "daily_loss_within_limit":
            kwargs["duplicate_order_detected"] = False
        result = evaluate_supervised_demo_order_execution(_input(**kwargs))
        assert result.demo_order_status == EXECUTION_CONTROL_BLOCKED
        assert result.next_stage == "repair_execution_controls"

    result = evaluate_supervised_demo_order_execution(
        _input(
            owner_supervised_demo_approval=True,
            owner_runtime_order_flag=True,
            bw_session_present=True,
            bitwarden_cli_available=True,
            bitwarden_item_read_success=True,
            credential_values_available_to_runtime=True,
            duplicate_order_guard_enabled=True,
            duplicate_order_detected=True,
        ),
    )
    assert result.demo_order_status == EXECUTION_CONTROL_BLOCKED
    assert result.next_stage == "repair_execution_controls"


def test_runtime_ready_when_all_controls_true():
    result = evaluate_supervised_demo_order_execution(_runtime_ready_input())
    assert result.demo_order_status == SUPERVISED_DEMO_ORDER_READY
    assert result.next_stage == "owner_execute_one_supervised_demo_order"
    assert result.current_stage == "supervised_demo_order_execution"


def test_output_gates_and_actions_are_false_in_runtime_ready():
    result = evaluate_supervised_demo_order_execution(_runtime_ready_input())
    assert result.live_order_execution is False
    assert result.money_movement is False
    assert result.scheduler_started is False
    assert result.daemon_started is False
    assert result.webhook_started is False


def test_run_default_dry_run_returns_owner_approval_required(tmp_path: Path):
    state_path = tmp_path / "AIOS_FOREX_SUPERVISED_DEMO_ORDER_EXECUTION_V1_STATE.json"
    report_path = tmp_path / "AIOS_FOREX_SUPERVISED_DEMO_ORDER_EXECUTION_V1_REPORT.md"
    result = run_forex_supervised_demo_order_execution_v1(
        owner_approved_supervised_demo_order=False,
        state_output=state_path,
        report_output=report_path,
        write_report=True,
    )
    assert result["result"]["demo_order_status"] == OWNER_SUPERVISED_DEMO_APPROVAL_REQUIRED
    assert result["result"]["runtime_mode"] == RUNTIME_MODE_DRY_RUN
    assert result["result"]["next_stage"] == "owner_supervised_demo_approval"
    assert result["runtime_summary"]["runtime_enabled"] is False
    assert result["runtime_summary"]["owner_approved_supervised_demo_order"] is False
    assert result["result"]["live_order_execution"] is False
    assert result["result"]["money_movement"] is False


def test_runner_dry_run_writes_state_and_report(tmp_path: Path):
    state_path = tmp_path / "AIOS_FOREX_SUPERVISED_DEMO_ORDER_EXECUTION_V1_STATE.json"
    report_path = tmp_path / "AIOS_FOREX_SUPERVISED_DEMO_ORDER_EXECUTION_V1_REPORT.md"
    payload = run_forex_supervised_demo_order_execution_v1(
        owner_approved_supervised_demo_order=False,
        state_output=state_path,
        report_output=report_path,
        write_report=True,
    )
    assert state_path.exists()
    assert report_path.exists()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["result"]["demo_order_status"] == OWNER_SUPERVISED_DEMO_APPROVAL_REQUIRED
    assert state["result"]["current_stage"] == "supervised_demo_order_execution"
    assert state["result"]["next_stage"] == "owner_supervised_demo_approval"
    assert state["result"]["live_order_execution"] is False
    assert state["result"]["money_movement"] is False
    assert state["runtime_summary"]["owner_approved_supervised_demo_order"] is False
    assert state["runtime_summary"]["runtime_mode"] == RUNTIME_MODE_DRY_RUN
    assert "OWNER_SUPERVISED_DEMO_APPROVAL_REQUIRED" in report_path.read_text(encoding="utf-8")
    assert "owner_approved_supervised_demo_order: false" in report_path.read_text(
        encoding="utf-8",
    )
    assert payload["result"]["demo_order_status"] == OWNER_SUPERVISED_DEMO_APPROVAL_REQUIRED


def test_runner_state_and_report_are_overwritten_by_latest_run(tmp_path: Path):
    state_path = tmp_path / "AIOS_FOREX_SUPERVISED_DEMO_ORDER_EXECUTION_V1_STATE.json"
    report_path = tmp_path / "AIOS_FOREX_SUPERVISED_DEMO_ORDER_EXECUTION_V1_REPORT.md"
    stale_state = {"stale": True}
    stale_report = "stale-report"
    state_path.write_text(json.dumps(stale_state), encoding="utf-8")
    report_path.write_text(stale_report, encoding="utf-8")

    payload = run_forex_supervised_demo_order_execution_v1(
        owner_approved_supervised_demo_order=True,
        state_output=state_path,
        report_output=report_path,
        write_report=True,
    )

    assert state_path.exists()
    assert report_path.exists()
    parsed_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert parsed_state != stale_state
    assert parsed_state["result"] == payload["result"]
    assert parsed_state["runtime_summary"]["runtime_enabled"] is True
    assert "owner_approved_supervised_demo_order" in report_path.read_text(encoding="utf-8")


def test_run_owner_approved_without_session_requires_runtime_credentials(tmp_path: Path):
    state_path = tmp_path / "AIOS_FOREX_SUPERVISED_DEMO_ORDER_EXECUTION_V1_STATE.json"
    report_path = tmp_path / "AIOS_FOREX_SUPERVISED_DEMO_ORDER_EXECUTION_V1_REPORT.md"
    payload = run_forex_supervised_demo_order_execution_v1(
        owner_approved_supervised_demo_order=True,
        state_output=state_path,
        report_output=report_path,
        write_report=True,
    )
    assert payload["result"]["demo_order_status"] == RUNTIME_CREDENTIAL_ACCESS_REQUIRED
    assert (
        payload["result"]["runtime_mode"]
        == RUNTIME_MODE_OWNER_APPROVED_SUPERVISED_DEMO_ORDER
    )
    assert payload["runtime_summary"]["runtime_enabled"] is True
    assert payload["runtime_summary"]["owner_approved_supervised_demo_order"] is True
    assert payload["result"]["next_stage"] == "owner_unlock_bitwarden_cli"


def test_run_owner_approved_supervised_demo_order_attempts_one_order(
    tmp_path: Path,
    monkeypatch,
):
    state_path = tmp_path / "AIOS_FOREX_SUPERVISED_DEMO_ORDER_EXECUTION_V1_STATE.json"
    report_path = tmp_path / "AIOS_FOREX_SUPERVISED_DEMO_ORDER_EXECUTION_V1_REPORT.md"

    fake_bw_output = json.dumps(
        {
            "fields": [
                {"name": "broker_api_token", "value": "demo-token"},
                {"name": "broker_account_id", "value": "demo-account"},
                {"name": "endpoint", "value": "https://api-fxpractice.oanda.com"},
                {"name": "environment", "value": "practice_demo"},
                {"name": "allowed_mode", "value": "read_only_until_owner_demo_approval"},
            ],
        },
    )

    class FakeCompleted:
        returncode = 0
        stdout = fake_bw_output

    monkeypatch.setenv("BW_SESSION", "session-token")
    monkeypatch.setattr(runtime_script.shutil, "which", lambda _: "bw")
    monkeypatch.setattr(
        runtime_script.subprocess,
        "run",
        lambda *args, **kwargs: FakeCompleted(),
    )
    monkeypatch.setattr(
        runtime_script,
        "_post_json_request",
        lambda request_payload: (
            {"orderId": "order-1"},
            201,
            True,
        ),
    )

    payload = runtime_script.run_forex_supervised_demo_order_execution_v1(
        owner_approved_supervised_demo_order=True,
        state_output=state_path,
        report_output=report_path,
        write_report=True,
    )

    assert (
        payload["runtime_summary"]["runtime_mode"]
        == RUNTIME_MODE_OWNER_APPROVED_SUPERVISED_DEMO_ORDER
    )
    assert payload["runtime_summary"]["owner_approved_supervised_demo_order"] is True
    assert payload["result"]["demo_order_status"] == SUPERVISED_DEMO_ORDER_READY
    assert payload["runtime_summary"]["order_attempt_requested"] is True
    assert payload["runtime_summary"]["order_attempted"] is True
    assert payload["runtime_summary"]["order_attempt_count"] == 1
    assert payload["runtime_summary"]["order_attempt_success"] is True
    assert payload["result"]["broker_api_called"] is True
    assert payload["result"]["demo_order_execution"] is True
    assert payload["result"]["live_order_execution"] is False
    assert payload["result"]["money_movement"] is False
    assert payload["result"]["scheduler_started"] is False
    assert payload["result"]["daemon_started"] is False
    assert payload["result"]["webhook_started"] is False


def test_config_template_has_expected_no_secret_fields():
    data = json.loads(
        Path(
            "configs/forex/AIOS_FOREX_SUPERVISED_DEMO_ORDER_EXECUTION_V1.example.json",
        ).read_text(encoding="utf-8"),
    )
    required = [
        "default_mode",
        "runtime_flag",
        "broker",
        "environment",
        "endpoint",
        "instrument",
        "units",
        "side",
        "order_type",
        "time_in_force",
        "stop_loss_required",
        "take_profit_required",
        "max_orders_per_run",
        "live_order_execution_by_this_packet",
        "scheduler_started_by_this_packet",
        "daemon_started_by_this_packet",
        "webhook_started_by_this_packet",
        "next_stage_after_success",
    ]
    for field_name in required:
        assert field_name in data
    assert data["default_mode"] == "dry_run"
    assert data["runtime_flag"] == "--owner-approved-supervised-demo-order"
    assert data["endpoint"] == "https://api-fxpractice.oanda.com"
    assert data["environment"] == "practice_demo"
    assert data["units"] == 1
    assert data["stop_loss_required"] is True
    assert data["take_profit_required"] is True
    assert data["max_orders_per_run"] == 1
    assert data["next_stage_after_success"] == "supervised_demo_evidence_review"
    assert data["live_order_execution_by_this_packet"] is False
    assert data["scheduler_started_by_this_packet"] is False
    assert data["daemon_started_by_this_packet"] is False
    assert data["webhook_started_by_this_packet"] is False
    raw = json.dumps(data).lower()
    assert "token" not in raw
    assert "secret" not in raw


def test_docs_mention_no_live_authorization_and_single_demo_order():
    text = Path(
        "docs/trading_lab/forex/FOREX_SUPERVISED_DEMO_ORDER_EXECUTION_V1.md",
    ).read_text(encoding="utf-8").lower()
    phrases = [
        "first owner-run supervised demo order execution path",
        "default validation does not place orders",
        "runtime mode requires explicit owner flag",
        "oanda practice only",
        "at most one",
        "does not authorize live trading",
        "does not start 22h/6d runtime",
        "success moves to supervised_demo_evidence_review",
        "final target remains live 22hr/day, 6day/week autonomous execution",
    ]
    for phrase in phrases:
        assert phrase in text


def test_build_order_payload_uses_market_type_uppercase():
    input_data = build_default_input(
        owner_supervised_demo_approval=True,
        owner_runtime_order_flag=True,
    )
    input_data = input_data.__class__(
        **{**input_data.__dict__, "order_type": "market"},
    )
    payload = runtime_script._build_order_payload(input_data)
    assert payload["order"]["type"] == "MARKET"


def test_build_order_payload_units_follow_side_orientation():
    buy_input = build_default_input(
        owner_supervised_demo_approval=True,
        owner_runtime_order_flag=True,
    )
    buy_input = buy_input.__class__(**{**buy_input.__dict__, "side": "buy"})
    assert int(runtime_script._build_order_payload(buy_input)["order"]["units"]) > 0

    sell_input = build_default_input(
        owner_supervised_demo_approval=True,
        owner_runtime_order_flag=True,
    )
    sell_input = sell_input.__class__(
        **{**sell_input.__dict__, "side": "sell", "units": 1},
    )
    assert int(runtime_script._build_order_payload(sell_input)["order"]["units"]) < 0

    units_default_input = build_default_input(
        owner_supervised_demo_approval=True,
        owner_runtime_order_flag=True,
    )
    units_default_input = units_default_input.__class__(
        **{**units_default_input.__dict__, "units": 0},
    )
    assert runtime_script._build_order_payload(units_default_input)["order"]["units"] == "1"


def test_recursive_sanitizer_redacts_runtime_secrets(tmp_path: Path):
    sensitive = {
        "broker_api_token": "topsecret",
        "broker_account_id": "12345",
        "order_endpoint": "https://api-fxpractice.oanda.com/v3/accounts/12345/orders",
        "request": {
            "Authorization": "Bearer abcdefg",
            "AccountId": {
                "value": "account-999",
            },
        },
        "details": {
            "accountID": "raw-id",
            "account_id": "raw-id",
            "nested": [
                {"accountId": "nested-id"},
                "Bearer qwerty",
            ],
            "bw_session": "should-not-pass",
        },
    }
    sanitized = runtime_script._redact_runtime_state(sensitive)
    assert sanitized["broker_api_token"] == "REDACTED_TOKEN"
    assert sanitized["broker_account_id"] == "REDACTED_ACCOUNT_ID"
    assert (
        sanitized["order_endpoint"]
        == "https://api-fxpractice.oanda.com/v3/accounts/REDACTED_ACCOUNT_ID/orders"
    )
    assert sanitized["request"]["Authorization"] == "REDACTED_TOKEN"
    assert sanitized["request"]["AccountId"] == "REDACTED_ACCOUNT_ID"
    assert sanitized["details"]["accountID"] == "REDACTED_ACCOUNT_ID"
    assert sanitized["details"]["account_id"] == "REDACTED_ACCOUNT_ID"
    assert sanitized["details"]["nested"][0]["accountId"] == "REDACTED_ACCOUNT_ID"
    assert sanitized["details"]["nested"][1] == "REDACTED_TOKEN"
    assert "bw_session" not in sanitized


def test_persisted_runtime_report_redacts_order_endpoint_and_tokens(tmp_path: Path, monkeypatch):
    state_path = tmp_path / "AIOS_FOREX_SUPERVISED_DEMO_ORDER_EXECUTION_V1_STATE.json"
    report_path = tmp_path / "AIOS_FOREX_SUPERVISED_DEMO_ORDER_EXECUTION_V1_REPORT.md"

    # Synthetic fixture only; never use a real broker account identifier.
    synthetic_account_id = "synthetic-demo-account-id"
    fake_bw_output = json.dumps(
        {
            "fields": [
                {"name": "broker_api_token", "value": "demo-token"},
                {"name": "broker_account_id", "value": synthetic_account_id},
                {"name": "endpoint", "value": "https://api-fxpractice.oanda.com"},
                {"name": "environment", "value": "practice_demo"},
                {"name": "allowed_mode", "value": "read_only_until_owner_demo_approval"},
                {"name": "owner", "value": "Anthony"},
            ],
        },
    )

    class FakeCompleted:
        returncode = 0
        stdout = fake_bw_output

    monkeypatch.setenv("BW_SESSION", "session-token")
    monkeypatch.setattr(runtime_script.shutil, "which", lambda _: "bw")
    monkeypatch.setattr(
        runtime_script.subprocess,
        "run",
        lambda *args, **kwargs: FakeCompleted(),
    )
    monkeypatch.setattr(
        runtime_script,
        "_post_json_request",
        lambda request_payload: (
            {"errorCode": "oanda::rest::core::InvalidParameterException"},
            400,
            False,
        ),
    )

    payload = runtime_script.run_forex_supervised_demo_order_execution_v1(
        owner_approved_supervised_demo_order=True,
        state_output=state_path,
        report_output=report_path,
        write_report=True,
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    report = report_path.read_text(encoding="utf-8")

    assert payload["runtime_summary"]["order_attempt_count"] == 1
    assert payload["runtime_summary"]["order_status_code"] == 400
    assert (
        synthetic_account_id
        not in json.dumps(state).replace("/", "")
    )
    assert (
        synthetic_account_id
        not in report.replace("/", "")
    )
    assert payload["runtime_summary"]["order_payload"]["order"]["type"] == "MARKET"
    assert "REDACTED_TOKEN" in report
    assert "REDACTED_ACCOUNT_ID" in report
