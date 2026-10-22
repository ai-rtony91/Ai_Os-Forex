from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path.cwd()
SCRIPT = ROOT / "scripts/forex_delivery/Acquire-AiOsOandaPracticeScalpingHistory.HUMAN_ONLY.ps1"
TEST_TOKEN = "AIOS_TEST_SECRET_SHOULD_NOT_APPEAR"


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _run_harness(tmp_path: Path, body: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    harness = tmp_path / "harness.ps1"
    harness.write_text(body, encoding="utf-8")
    env = os.environ.copy()
    env["AIOS_TEST_TOKEN"] = TEST_TOKEN
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    if check and result.returncode != 0:
        raise AssertionError(f"PowerShell failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
    return result


def _candle_function() -> str:
    return r"""
function New-AiOsTestCandle {
    param([string]$Time)
    return [pscustomobject]@{
        complete = $true
        time = $Time
        bid = [pscustomobject]@{ o = '1.0'; h = '1.1'; l = '0.9'; c = '1.0' }
        ask = [pscustomobject]@{ o = '1.0'; h = '1.1'; l = '0.9'; c = '1.0' }
    }
}
"""


def _base_success_harness(output_root: Path, uri_log: Path, max_batches: int = 0) -> str:
    script = _ps_quote(str(SCRIPT))
    output = _ps_quote(str(output_root))
    uri_log_q = _ps_quote(str(uri_log))
    max_part = f" -MaxBatchesPerSeries {max_batches}" if max_batches else ""
    return rf"""
$ErrorActionPreference = 'Stop'
$global:Uris = @()
{_candle_function()}
function Read-Host {{
    param([string]$Prompt, [switch]$AsSecureString)
    $secure = New-Object System.Security.SecureString
    foreach ($char in $env:AIOS_TEST_TOKEN.ToCharArray()) {{ $secure.AppendChar($char) }}
    $secure.MakeReadOnly()
    return $secure
}}
function Invoke-RestMethod {{
    param([string]$Method, [string]$Uri, $Headers, [int]$TimeoutSec)
    if ($Method -ne 'Get') {{ throw 'METHOD_NOT_GET' }}
    if ($TimeoutSec -ne 30) {{ throw 'TIMEOUT_NOT_BOUNDED' }}
    if ($Uri -match 'api-fxtrade|/orders|/accounts') {{ throw 'FORBIDDEN_ENDPOINT' }}
    if ($Uri -notmatch 'from=') {{
        return [pscustomobject]@{{ instrument = 'EUR_USD'; granularity = 'S5'; candles = @() }}
    }}
    $global:Uris += $Uri
    if (($Uri -match '00%3A00%3A00') -and ($Uri -match 'includeFirst=true')) {{
        $candles = @((New-AiOsTestCandle '2020-01-01T00:00:00.0000000Z'), (New-AiOsTestCandle '2020-01-01T00:00:05.0000000Z'))
    }} elseif (($Uri -match '00%3A00%3A05') -and ($Uri -match 'includeFirst=false')) {{
        $candles = @((New-AiOsTestCandle '2020-01-01T00:00:10.0000000Z'), (New-AiOsTestCandle '2020-01-01T00:00:15.0000000Z'))
    }} else {{
        throw "UNEXPECTED_CURSOR: $Uri"
    }}
    return [pscustomobject]@{{ instrument = 'EUR_USD'; granularity = 'S5'; candles = $candles }}
}}
& {script} -OutputRoot {output} -Instruments EUR_USD -Granularities S5 -FromUtc '2020-01-01T00:00:00Z' -ToUtc '2020-01-01T00:00:20Z' -CandlesPerRequest 2{max_part}
if ($global:Uris.Count -eq 0) {{
    '[]' | Set-Content -LiteralPath {uri_log_q} -Encoding UTF8
}} else {{
    $global:Uris | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath {uri_log_q} -Encoding UTF8
}}
"""


def _retry_harness(output_root: Path, status: str, expected_failures: int) -> str:
    script = _ps_quote(str(SCRIPT))
    output = _ps_quote(str(output_root))
    status_expr = _ps_quote(status)
    return rf"""
$ErrorActionPreference = 'Stop'
$global:Attempts = 0
$global:Sleeps = @()
{_candle_function()}
function Read-Host {{
    param([string]$Prompt, [switch]$AsSecureString)
    $secure = New-Object System.Security.SecureString
    foreach ($char in $env:AIOS_TEST_TOKEN.ToCharArray()) {{ $secure.AppendChar($char) }}
    $secure.MakeReadOnly()
    return $secure
}}
function Start-Sleep {{
    param([int]$Seconds)
    $global:Sleeps += $Seconds
}}
function Invoke-RestMethod {{
    param([string]$Method, [string]$Uri, $Headers, [int]$TimeoutSec)
    if ($TimeoutSec -ne 30) {{ throw 'TIMEOUT_NOT_BOUNDED' }}
    if ($Uri -notmatch 'from=') {{
        return [pscustomobject]@{{ instrument = 'EUR_USD'; granularity = 'S5'; candles = @() }}
    }}
    $global:Attempts += 1
    if ($global:Attempts -le {expected_failures}) {{
        throw {status_expr}
    }}
    return [pscustomobject]@{{
        instrument = 'EUR_USD'
        granularity = 'S5'
        candles = @(New-AiOsTestCandle '2020-01-01T00:00:00.0000000Z')
    }}
}}
& {script} -OutputRoot {output} -Instruments EUR_USD -Granularities S5 -FromUtc '2020-01-01T00:00:00Z' -ToUtc '2020-01-01T00:00:05Z' -CandlesPerRequest 1 -MaxRetries 3
@{{ attempts = $global:Attempts; sleeps = $global:Sleeps }} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath { _ps_quote(str(output_root / "retry_log.json")) } -Encoding UTF8
"""


def _response_validation_harness(output_root: Path, response_body: str) -> str:
    script = _ps_quote(str(SCRIPT))
    output = _ps_quote(str(output_root))
    return rf"""
$ErrorActionPreference = 'Stop'
{_candle_function()}
function Read-Host {{
    param([string]$Prompt, [switch]$AsSecureString)
    $secure = New-Object System.Security.SecureString
    foreach ($char in $env:AIOS_TEST_TOKEN.ToCharArray()) {{ $secure.AppendChar($char) }}
    $secure.MakeReadOnly()
    return $secure
}}
function Invoke-RestMethod {{
    param([string]$Method, [string]$Uri, $Headers, [int]$TimeoutSec)
    if ($TimeoutSec -ne 30) {{ throw 'TIMEOUT_NOT_BOUNDED' }}
    if ($Uri -notmatch 'from=') {{
        return [pscustomobject]@{{ instrument = 'EUR_USD'; granularity = 'S5'; candles = @() }}
    }}
    {response_body}
}}
& {script} -OutputRoot {output} -Instruments EUR_USD -Granularities S5 -FromUtc '2020-01-01T00:00:00Z' -ToUtc '2020-01-01T00:00:10Z' -CandlesPerRequest 2
"""


def _weekend_gap_harness(output_root: Path, uri_log: Path) -> str:
    script = _ps_quote(str(SCRIPT))
    output = _ps_quote(str(output_root))
    uri_log_q = _ps_quote(str(uri_log))
    return rf"""
$ErrorActionPreference = 'Stop'
$global:Uris = @()
{_candle_function()}
function Read-Host {{
    param([string]$Prompt, [switch]$AsSecureString)
    $secure = New-Object System.Security.SecureString
    foreach ($char in $env:AIOS_TEST_TOKEN.ToCharArray()) {{ $secure.AppendChar($char) }}
    $secure.MakeReadOnly()
    return $secure
}}
function Invoke-RestMethod {{
    param([string]$Method, [string]$Uri, $Headers, [int]$TimeoutSec)
    if ($TimeoutSec -ne 30) {{ throw 'TIMEOUT_NOT_BOUNDED' }}
    if ($Uri -notmatch 'from=') {{
        return [pscustomobject]@{{ instrument = 'EUR_USD'; granularity = 'S5'; candles = @() }}
    }}
    $global:Uris += $Uri
    if (($Uri -match '2020-01-03T21') -and ($Uri -match 'includeFirst=true')) {{
        $candles = @((New-AiOsTestCandle '2020-01-03T21:59:55.0000000Z'))
    }} elseif (($Uri -match '2020-01-03T21') -and ($Uri -match 'includeFirst=false')) {{
        $candles = @((New-AiOsTestCandle '2020-01-06T22:00:00.0000000Z'))
    }} else {{
        throw "UNEXPECTED_CURSOR: $Uri"
    }}
    return [pscustomobject]@{{ instrument = 'EUR_USD'; granularity = 'S5'; candles = $candles }}
}}
& {script} -OutputRoot {output} -Instruments EUR_USD -Granularities S5 -FromUtc '2020-01-03T21:59:55Z' -ToUtc '2020-01-06T22:00:05Z' -CandlesPerRequest 1
$global:Uris | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath {uri_log_q} -Encoding UTF8
"""


def _auth_failure_harness(output_root: Path, call_log: Path, status: str = "HTTP_STATUS:401") -> str:
    script = _ps_quote(str(SCRIPT))
    output = _ps_quote(str(output_root))
    call_log_q = _ps_quote(str(call_log))
    status_q = _ps_quote(status)
    return rf"""
$ErrorActionPreference = 'Stop'
$global:Calls = 0
function Read-Host {{
    param([string]$Prompt, [switch]$AsSecureString)
    $secure = New-Object System.Security.SecureString
    foreach ($char in $env:AIOS_TEST_TOKEN.ToCharArray()) {{ $secure.AppendChar($char) }}
    $secure.MakeReadOnly()
    return $secure
}}
function Invoke-RestMethod {{
    param([string]$Method, [string]$Uri, $Headers, [int]$TimeoutSec)
    $global:Calls += 1
    if ($Method -ne 'Get') {{ throw 'METHOD_NOT_GET' }}
    if ($Uri -match 'api-fxtrade|/orders|/accounts') {{ throw 'FORBIDDEN_ENDPOINT' }}
    throw {status_q}
}}
try {{
    & {script} -OutputRoot {output} -Instruments EUR_USD -Granularities S5 -FromUtc '2020-01-01T00:00:00Z' -ToUtc '2020-01-01T00:00:20Z' -CandlesPerRequest 2
}}
finally {{
    @{{ calls = $global:Calls }} | ConvertTo-Json | Set-Content -LiteralPath {call_log_q} -Encoding UTF8
}}
"""


def _authorization_continuity_harness(
    output_root: Path, state_log: Path, retry_first_acquisition: bool = False
) -> str:
    script = _ps_quote(str(SCRIPT))
    output = _ps_quote(str(output_root))
    state_log_q = _ps_quote(str(state_log))
    retry_flag = "$true" if retry_first_acquisition else "$false"
    return rf"""
$ErrorActionPreference = 'Stop'
$global:AuthorizationStates = @()
$global:AcquisitionAttempts = 0
{_candle_function()}
function Read-Host {{
    param([string]$Prompt, [switch]$AsSecureString)
    $secure = New-Object System.Security.SecureString
    foreach ($char in $env:AIOS_TEST_TOKEN.ToCharArray()) {{ $secure.AppendChar($char) }}
    $secure.MakeReadOnly()
    return $secure
}}
function Start-Sleep {{
    param([int]$Seconds)
}}
function Invoke-RestMethod {{
    param([string]$Method, [string]$Uri, $Headers, [int]$TimeoutSec)
    if ($Method -ne 'Get') {{ throw 'METHOD_NOT_GET' }}
    if ($Uri -match 'api-fxtrade|/orders|/accounts') {{ throw 'FORBIDDEN_ENDPOINT' }}
    $phase = if ($Uri -match 'from=') {{ 'ACQUISITION' }} else {{ 'AUTHENTICATION_CHECK' }}
    $expectedAuthorization = 'Be' + 'arer ' + $env:AIOS_TEST_TOKEN
    $authorizationValid = (
        ($null -ne $Headers) -and
        $Headers.ContainsKey('Authorization') -and
        ([string]$Headers['Authorization'] -ceq $expectedAuthorization)
    )
    $global:AuthorizationStates += [pscustomobject]@{{
        phase = $phase
        authorization_valid = $authorizationValid
    }}
    if (-not $authorizationValid) {{ throw 'HTTP_STATUS:401' }}

    [void]$Headers.Remove('Authorization')

    if ($phase -eq 'AUTHENTICATION_CHECK') {{
        return [pscustomobject]@{{ instrument = 'EUR_USD'; granularity = 'S5'; candles = @() }}
    }}
    $global:AcquisitionAttempts += 1
    if ({retry_flag} -and $global:AcquisitionAttempts -eq 1) {{
        throw 'HTTP_STATUS:503 RETRY_AFTER:1'
    }}
    return [pscustomobject]@{{
        instrument = 'EUR_USD'
        granularity = 'S5'
        candles = @(New-AiOsTestCandle '2020-01-01T00:00:00.0000000Z')
    }}
}}
try {{
    & {script} -OutputRoot {output} -Instruments EUR_USD -Granularities S5 -FromUtc '2020-01-01T00:00:00Z' -ToUtc '2020-01-01T00:00:05Z' -CandlesPerRequest 1 -MaxRetries 2
}}
finally {{
    $global:AuthorizationStates | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath {state_log_q} -Encoding UTF8
}}
"""


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _load_uri_log(path: Path) -> list[str]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(value, str):
        return [value]
    return value


def _all_artifact_text(root: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8-sig") for path in root.rglob("*.json"))


def test_what_if_reports_repaired_contract_and_needs_no_credential(tmp_path: Path):
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-OutputRoot",
            str(tmp_path / "out"),
            "-Instruments",
            "EUR_USD",
            "-Granularities",
            "S5",
            "-FromUtc",
            "2020-01-01T00:00:00Z",
            "-ToUtc",
            "2020-01-01T00:00:20Z",
            "-WhatIfOnly",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    plan = json.loads(result.stdout)
    assert plan["pagination_contract"] == "FROM_PLUS_COUNT"
    assert plan["request_count"] == 5000
    assert plan["candles_per_request"] == 5000
    assert plan["overall_from_utc"] == "2020-01-01T00:00:00Z"
    assert plan["overall_to_utc"] == "2020-01-01T00:00:20Z"
    assert plan["to_sent_on_each_request"] is False
    assert plan["resume_enabled"] is True
    assert plan["checkpoint_enabled"] is True
    assert plan["include_first_strategy"] == "FIRST_REQUEST_TRUE_THEN_FROM_LAST_ACCEPTED_WITH_INCLUDE_FIRST_FALSE"
    assert plan["atomic_promotion_enabled"] is True
    assert plan["retry_enabled"] is True
    assert plan["maximum_attempts_per_request"] == 5
    assert plan["request_timeout_seconds"] == 30
    assert plan["maximum_transport_wait_seconds_upper_bound"] == 390
    assert plan["request_parallelism"] == 1
    assert plan["parallel_request_allowed"] is False
    assert plan["burst_control"] == "SINGLE_SEQUENTIAL_REQUEST_LOOP_WITH_BOUNDED_RETRY"
    assert plan["batch_count_field_deprecated_or_misnamed"] is True
    assert plan["scope_fingerprint"]
    assert plan["helper_sha256"]
    assert plan["collector_sha256"]
    assert plan["what_if_only"] is True
    assert "Enter OANDA Practice token" not in result.stdout + result.stderr


def test_paginated_uri_uses_from_and_count_without_to_and_to_is_local_boundary(tmp_path: Path):
    output_root = tmp_path / "history"
    uri_log = tmp_path / "uris.json"
    result = _run_harness(tmp_path, _base_success_harness(output_root, uri_log))
    uris = _load_uri_log(uri_log)

    assert len(uris) == 2
    assert all("from=" in uri for uri in uris)
    assert all("count=2" in uri for uri in uris)
    assert all("to=" not in uri for uri in uris)
    assert "includeFirst=true" in uris[0]
    assert "includeFirst=false" in uris[1]
    assert all("/candles?" in uri for uri in uris)
    assert all("/orders" not in uri and "/accounts" not in uri for uri in uris)

    manifest = _load_json(output_root / "AIOS_FOREX_SCALPING_HISTORY_MANIFEST.json")
    checkpoint = _load_json(output_root / "EUR_USD_S5" / "AIOS_FOREX_SCALPING_HISTORY_CHECKPOINT.json")
    assert manifest["overall_to_utc"] == "2020-01-01T00:00:20.0000000Z"
    assert manifest["to_boundary_semantics"] == "exclusive"
    assert checkpoint["next_cursor_utc"] == "2020-01-01T00:00:15.0000000Z"
    assert checkpoint["next_local_boundary_utc"] == "2020-01-01T00:00:20.0000000Z"
    assert checkpoint["status"] == "SERIES_COMPLETE"
    assert checkpoint["batches"][0]["request_cursor_utc"] == "2020-01-01T00:00:00.0000000Z"
    assert checkpoint["batches"][0]["include_first"] is True
    assert checkpoint["batches"][1]["request_cursor_utc"] == "2020-01-01T00:00:05.0000000Z"
    assert checkpoint["batches"][1]["include_first"] is False
    assert TEST_TOKEN not in result.stdout + result.stderr + _all_artifact_text(output_root)
    assert manifest["request_parallelism"] == 1
    assert manifest["parallel_request_allowed"] is False
    runtime_state = _load_json(output_root / "AIOS_FOREX_SCALPING_HISTORY_RUNTIME_STATE.json")
    assert runtime_state["status"] == "ACQUISITION_COMPLETE"
    assert runtime_state["process_id"] > 0
    assert runtime_state["request_timeout_seconds"] == 30
    assert runtime_state["last_checkpoint_path"].endswith("AIOS_FOREX_SCALPING_HISTORY_CHECKPOINT.json")
    assert runtime_state["secret_value_exposed"] is False
    assert "AUTHENTICATION_CHECK_STARTED pair=EUR_USD granularity=S5" in result.stdout
    assert "AUTHENTICATION_CHECK_PASS pair=EUR_USD granularity=S5" in result.stdout
    assert "AUTHENTICATION_CHECK_FAIL" not in result.stdout
    assert "HEARTBEAT phase=ACQUISITION_REQUEST pair=EUR_USD granularity=S5 batch=0 candles=0 last=NONE retry=0" in result.stdout


def test_declared_dataset_scope_fingerprint_is_preserved_after_reliability_repair(tmp_path: Path):
    script = _ps_quote(str(SCRIPT))
    result = _run_harness(
        tmp_path,
        rf"""
& {script} -OutputRoot '.aios/runtime/forex_scalping_history_human_inbox_v1' -Instruments @('EUR_USD','GBP_USD','USD_JPY') -Granularities @('M1','M2','M4','S10','S15','S30','S5') -FromUtc '2024-01-01T00:00:00Z' -ToUtc '2026-08-30T00:00:00Z' -WhatIfOnly
""",
    )
    plan = json.loads(result.stdout)
    assert plan["scope_fingerprint"] == "e7ea1cf452a0cbafc9e2071c250c81b6cef242f800e2a2d0e694bcabfbade680"
    assert plan["helper_sha256"] == "719045663d658d2a1d3e288273c61cb6b4ec81a523b06974232a3f21e691cfa8"
    assert plan["collector_sha256"] != plan["helper_sha256"]

    reordered = _run_harness(
        tmp_path,
        rf"""
& {script} -OutputRoot '.aios/runtime/forex_scalping_history_human_inbox_v1' -Instruments @('USD_JPY','EUR_USD','GBP_USD') -Granularities @('S5','S10','S15','S30','M1','M2','M4') -FromUtc '2024-01-01T00:00:00Z' -ToUtc '2026-08-30T00:00:00Z' -WhatIfOnly
""",
    )
    reordered_plan = json.loads(reordered.stdout)
    assert reordered_plan["scope_fingerprint"] == plan["scope_fingerprint"]
    assert reordered_plan["scope_fingerprint"] == "e7ea1cf452a0cbafc9e2071c250c81b6cef242f800e2a2d0e694bcabfbade680"


def test_authentication_pass_then_first_acquisition_uses_fresh_valid_authorization_and_progresses(
    tmp_path: Path,
):
    output_root = tmp_path / "authorization_continuity"
    state_log = tmp_path / "authorization_states.json"
    result = _run_harness(
        tmp_path,
        _authorization_continuity_harness(output_root, state_log),
    )
    states = json.loads(state_log.read_text(encoding="utf-8-sig"))
    assert states == [
        {"phase": "AUTHENTICATION_CHECK", "authorization_valid": True},
        {"phase": "ACQUISITION", "authorization_valid": True},
    ]

    ordered_markers = [
        "AUTHENTICATION_CHECK_PASS",
        "HEARTBEAT phase=ACQUISITION_REQUEST",
        "HEARTBEAT phase=ACQUISITION_RESPONSE",
        "PROGRESS EUR_USD S5 batch=1 candles=1",
    ]
    positions = [result.stdout.index(marker) for marker in ordered_markers]
    assert positions == sorted(positions)

    checkpoint_path = output_root / "EUR_USD_S5" / "AIOS_FOREX_SCALPING_HISTORY_CHECKPOINT.json"
    checkpoint = _load_json(checkpoint_path)
    assert checkpoint["complete_candles"] == 1
    assert checkpoint["status"] == "SERIES_COMPLETE"
    assert len(checkpoint["batches"]) == 1
    assert Path(checkpoint["batches"][0]["artifact_path"]).is_file()
    assert TEST_TOKEN not in result.stdout + result.stderr + state_log.read_text(encoding="utf-8-sig")
    assert TEST_TOKEN not in _all_artifact_text(output_root)


def test_retry_rebuilds_authorization_headers_from_process_lifetime_state(tmp_path: Path):
    output_root = tmp_path / "authorization_retry_continuity"
    state_log = tmp_path / "authorization_retry_states.json"
    result = _run_harness(
        tmp_path,
        _authorization_continuity_harness(output_root, state_log, retry_first_acquisition=True),
    )
    states = json.loads(state_log.read_text(encoding="utf-8-sig"))
    assert [state["phase"] for state in states] == [
        "AUTHENTICATION_CHECK",
        "ACQUISITION",
        "ACQUISITION",
    ]
    assert all(state["authorization_valid"] is True for state in states)
    assert "HEARTBEAT phase=ACQUISITION_RETRY_WAIT" in result.stdout
    assert "HEARTBEAT phase=ACQUISITION_RESPONSE" in result.stdout
    assert TEST_TOKEN not in result.stdout + result.stderr + state_log.read_text(encoding="utf-8-sig")
    assert TEST_TOKEN not in _all_artifact_text(output_root)


def test_cursor_advances_without_duplicates_and_final_data_respects_exclusive_to(tmp_path: Path):
    output_root = tmp_path / "history"
    _run_harness(tmp_path, _base_success_harness(output_root, tmp_path / "uris.json"))

    candles = []
    for batch in sorted((output_root / "EUR_USD_S5").glob("[0-9]*_EUR_USD_S5.json")):
        candles.extend(_load_json(batch)["candles"])

    times = [datetime.fromisoformat(candle["time"].replace("Z", "+00:00")) for candle in candles]
    assert len(times) == len(set(times))
    assert times == sorted(times)
    assert times == [
        datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        datetime(2020, 1, 1, 0, 0, 5, tzinfo=timezone.utc),
        datetime(2020, 1, 1, 0, 0, 10, tzinfo=timezone.utc),
        datetime(2020, 1, 1, 0, 0, 15, tzinfo=timezone.utc),
    ]
    assert all(t < datetime(2020, 1, 1, 0, 0, 20, tzinfo=timezone.utc) for t in times)


def test_checkpoint_resume_starts_first_missing_batch_and_completed_series_not_redownloaded(tmp_path: Path):
    output_root = tmp_path / "history"
    first_uri_log = tmp_path / "first_uris.json"
    second_uri_log = tmp_path / "second_uris.json"
    third_uri_log = tmp_path / "third_uris.json"

    _run_harness(tmp_path, _base_success_harness(output_root, first_uri_log, max_batches=1))
    _run_harness(tmp_path, _base_success_harness(output_root, second_uri_log))
    _run_harness(tmp_path, _base_success_harness(output_root, third_uri_log))

    first_uris = _load_uri_log(first_uri_log)
    second_uris = _load_uri_log(second_uri_log)
    third_uris = _load_uri_log(third_uri_log)

    assert len(first_uris) == 1
    assert "00%3A00%3A00" in first_uris[0]
    assert len(second_uris) == 1
    assert "00%3A00%3A05" in second_uris[0]
    assert "includeFirst=false" in second_uris[0]
    assert third_uris is None or third_uris == []

    checkpoint = _load_json(output_root / "EUR_USD_S5" / "AIOS_FOREX_SCALPING_HISTORY_CHECKPOINT.json")
    assert checkpoint["status"] == "SERIES_COMPLETE"
    assert checkpoint["complete_candles"] == 4


def test_cursor_uses_include_first_false_across_market_gap_without_fixed_skip(tmp_path: Path):
    output_root = tmp_path / "history_gap"
    uri_log = tmp_path / "gap_uris.json"
    _run_harness(tmp_path, _weekend_gap_harness(output_root, uri_log))
    uris = _load_uri_log(uri_log)

    assert len(uris) == 2
    assert "includeFirst=true" in uris[0]
    assert "includeFirst=false" in uris[1]
    assert "2020-01-03T21%3A59%3A55" in uris[1]

    checkpoint = _load_json(output_root / "EUR_USD_S5" / "AIOS_FOREX_SCALPING_HISTORY_CHECKPOINT.json")
    assert checkpoint["status"] == "SERIES_COMPLETE"
    assert checkpoint["last_candle_utc"] == "2020-01-06T22:00:00.0000000Z"


def test_checkpoint_hash_mismatch_fails_closed_before_redownload(tmp_path: Path):
    output_root = tmp_path / "history_hash_mismatch"
    _run_harness(tmp_path, _base_success_harness(output_root, tmp_path / "first.json", max_batches=1))
    batch_path = output_root / "EUR_USD_S5" / "000000_EUR_USD_S5.json"
    original = batch_path.read_text(encoding="utf-8-sig")
    batch_path.write_text(original.replace("AIOS_FOREX_SCALPING_HISTORY_BATCH.v1", "TAMPERED_BATCH"), encoding="utf-8")

    result = _run_harness(tmp_path, _base_success_harness(output_root, tmp_path / "second.json"), check=False)
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "CHECKPOINT_ARTIFACT_HASH_MISMATCH" in combined
    assert TEST_TOKEN not in combined


def test_legacy_checkpoint_with_missing_artifact_fails_closed(tmp_path: Path):
    output_root = tmp_path / "history_missing_artifact"
    series_dir = output_root / "EUR_USD_S5"
    series_dir.mkdir(parents=True)
    checkpoint = {
        "schema": "AIOS_FOREX_SCALPING_HISTORY_CHECKPOINT.v1",
        "status": "SERIES_IN_PROGRESS",
        "host": "https://api-fxpractice.oanda.com",
        "method": "GET_ONLY",
        "instrument": "EUR_USD",
        "granularity": "S5",
        "price": "BA",
        "overall_from_utc": "2020-01-01T00:00:00.0000000Z",
        "overall_to_utc": "2020-01-01T00:00:20.0000000Z",
        "pagination_contract": "FROM_PLUS_COUNT",
        "to_sent_on_each_request": False,
        "candles_per_request": 2,
        "next_cursor_utc": "2020-01-01T00:00:10.0000000Z",
        "next_batch_index": 1,
        "complete_candles": 2,
        "last_candle_utc": "2020-01-01T00:00:05.0000000Z",
    }
    (series_dir / "AIOS_FOREX_SCALPING_HISTORY_CHECKPOINT.json").write_text(json.dumps(checkpoint), encoding="utf-8")

    result = _run_harness(tmp_path, _base_success_harness(output_root, tmp_path / "uris.json"), check=False)
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "CHECKPOINT_ARTIFACT_MISSING" in combined
    assert TEST_TOKEN not in combined


def test_mismatched_price_scope_fails_closed_without_mixing_artifacts(tmp_path: Path):
    output_root = tmp_path / "history_price_scope"
    _run_harness(tmp_path, _base_success_harness(output_root, tmp_path / "first.json", max_batches=1))
    script = _ps_quote(str(SCRIPT))
    output = _ps_quote(str(output_root))
    harness = rf"""
$ErrorActionPreference = 'Stop'
{_candle_function()}
function Read-Host {{
    param([string]$Prompt, [switch]$AsSecureString)
    $secure = New-Object System.Security.SecureString
    foreach ($char in $env:AIOS_TEST_TOKEN.ToCharArray()) {{ $secure.AppendChar($char) }}
    $secure.MakeReadOnly()
    return $secure
}}
function Invoke-RestMethod {{
    param([string]$Method, [string]$Uri, $Headers, [int]$TimeoutSec)
    if ($Uri -notmatch 'from=') {{
        return [pscustomobject]@{{ instrument = 'EUR_USD'; granularity = 'S5'; candles = @() }}
    }}
    throw 'SHOULD_NOT_REDOWNLOAD_MISMATCHED_SCOPE'
}}
& {script} -OutputRoot {output} -Instruments EUR_USD -Granularities S5 -FromUtc '2020-01-01T00:00:00Z' -ToUtc '2020-01-01T00:00:20Z' -CandlesPerRequest 2 -Price M
"""
    result = _run_harness(tmp_path, harness, check=False)
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "SCOPE_FINGERPRINT_MISMATCH" in combined
    assert "SHOULD_NOT_REDOWNLOAD_MISMATCHED_SCOPE" not in combined
    assert TEST_TOKEN not in combined


def test_empty_response_is_lawful_partial_end_and_json_artifacts_parse(tmp_path: Path):
    output_root = tmp_path / "history_empty"
    body = "return [pscustomobject]@{ instrument = 'EUR_USD'; granularity = 'S5'; candles = @() }"
    _run_harness(tmp_path, _response_validation_harness(output_root, body))
    checkpoint = _load_json(output_root / "EUR_USD_S5" / "AIOS_FOREX_SCALPING_HISTORY_CHECKPOINT.json")
    manifest = _load_json(output_root / "AIOS_FOREX_SCALPING_HISTORY_MANIFEST.json")
    assert checkpoint["status"] == "SERIES_COMPLETE"
    assert manifest["complete_series"] == 1
    assert manifest["incomplete_series"] == 0
    assert manifest["secret_value_exposed"] is False


def test_authentication_401_fails_immediately_with_sanitized_classification(tmp_path: Path):
    output_root = tmp_path / "auth_401"
    call_log = tmp_path / "auth_401_calls.json"
    result = _run_harness(tmp_path, _auth_failure_harness(output_root, call_log), check=False)
    combined = result.stdout + result.stderr

    assert result.returncode != 0
    assert "AUTHENTICATION_CHECK_STARTED pair=EUR_USD granularity=S5" in combined
    assert "AUTHENTICATION_CHECK_FAIL classification=OANDA_PRACTICE_AUTHENTICATION_REJECTED" in combined
    assert "AUTHENTICATION_CHECK_PASS" not in combined
    assert "OANDA_PRACTICE_AUTHENTICATION_REJECTED" in combined
    assert _load_json(call_log)["calls"] == 1
    assert _load_json(output_root / "AIOS_FOREX_SCALPING_HISTORY_RUNTIME_STATE.json")["status"] == "OANDA_PRACTICE_AUTHENTICATION_REJECTED"
    assert not list(output_root.rglob("[0-9]*_EUR_USD_S5.json"))
    assert TEST_TOKEN not in combined + _all_artifact_text(output_root)
    assert "Authorization" not in combined + _all_artifact_text(output_root)


def test_authentication_failure_does_not_modify_durable_checkpoint_or_candles(tmp_path: Path):
    output_root = tmp_path / "auth_preserves_durable"
    _run_harness(tmp_path, _base_success_harness(output_root, tmp_path / "initial_uris.json", max_batches=1))
    checkpoint_path = output_root / "EUR_USD_S5" / "AIOS_FOREX_SCALPING_HISTORY_CHECKPOINT.json"
    batch_path = output_root / "EUR_USD_S5" / "000000_EUR_USD_S5.json"
    checkpoint_before = checkpoint_path.read_bytes()
    batch_before = batch_path.read_bytes()

    result = _run_harness(
        tmp_path,
        _auth_failure_harness(output_root, tmp_path / "preserve_calls.json"),
        check=False,
    )

    assert result.returncode != 0
    assert checkpoint_path.read_bytes() == checkpoint_before
    assert batch_path.read_bytes() == batch_before


def test_response_validation_failures_are_closed_and_sanitized(tmp_path: Path):
    cases = [
        ("wrong_instrument", "return [pscustomobject]@{ instrument = 'GBP_USD'; granularity = 'S5'; candles = @(New-AiOsTestCandle '2020-01-01T00:00:00.0000000Z') }", "RESPONSE_INSTRUMENT_MISMATCH"),
        ("wrong_granularity", "return [pscustomobject]@{ instrument = 'EUR_USD'; granularity = 'M1'; candles = @(New-AiOsTestCandle '2020-01-01T00:00:00.0000000Z') }", "RESPONSE_GRANULARITY_MISMATCH"),
        ("duplicate", "$c = New-AiOsTestCandle '2020-01-01T00:00:00.0000000Z'; return [pscustomobject]@{ instrument = 'EUR_USD'; granularity = 'S5'; candles = @($c, $c) }", "DUPLICATE_CANDLE_IN_BATCH"),
        ("out_of_order", "return [pscustomobject]@{ instrument = 'EUR_USD'; granularity = 'S5'; candles = @((New-AiOsTestCandle '2020-01-01T00:00:05.0000000Z'), (New-AiOsTestCandle '2020-01-01T00:00:00.0000000Z')) }", "NON_CHRONOLOGICAL_CANDLES"),
        ("missing_bid", "$c = New-AiOsTestCandle '2020-01-01T00:00:00.0000000Z'; $c.PSObject.Properties.Remove('bid'); return [pscustomobject]@{ instrument = 'EUR_USD'; granularity = 'S5'; candles = @($c) }", "PRICE_CONTRACT_FAILURE"),
    ]
    for name, body, expected in cases:
        output_root = tmp_path / name
        result = _run_harness(tmp_path, _response_validation_harness(output_root, body), check=False)
        combined = result.stdout + result.stderr
        assert result.returncode != 0
        assert expected in combined
        assert TEST_TOKEN not in combined
        assert "Authorization" not in combined


def test_malformed_response_failure_is_closed_and_sanitized(tmp_path: Path):
    output_root = tmp_path / "malformed_response"
    body = "throw 'Invalid JSON primitive: provider response could not be parsed'"
    result = _run_harness(tmp_path, _response_validation_harness(output_root, body), check=False)
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "Invalid JSON primitive" in combined
    assert TEST_TOKEN not in combined
    assert "Authorization" not in combined


def test_incomplete_candle_is_excluded_without_secret_output(tmp_path: Path):
    output_root = tmp_path / "history_incomplete"
    body = """
    if ($Uri -match 'includeFirst=false') {
        return [pscustomobject]@{ instrument = 'EUR_USD'; granularity = 'S5'; candles = @() }
    }
    $complete = New-AiOsTestCandle '2020-01-01T00:00:00.0000000Z'
    $incomplete = New-AiOsTestCandle '2020-01-01T00:00:05.0000000Z'
    $incomplete.complete = $false
    return [pscustomobject]@{ instrument = 'EUR_USD'; granularity = 'S5'; candles = @($complete, $incomplete) }
    """
    result = _run_harness(tmp_path, _response_validation_harness(output_root, body))
    assert TEST_TOKEN not in result.stdout + result.stderr + _all_artifact_text(output_root)
    batch = _load_json(output_root / "EUR_USD_S5" / "000000_EUR_USD_S5.json")
    assert batch["candle_count"] == 1
    assert batch["candles"][0]["time"] == "2020-01-01T00:00:00.0000000Z"


def test_crash_leftover_temp_file_does_not_corrupt_completed_resume(tmp_path: Path):
    output_root = tmp_path / "history_temp_leftover"
    first_uri_log = tmp_path / "first_temp_uris.json"
    second_uri_log = tmp_path / "second_temp_uris.json"
    _run_harness(tmp_path, _base_success_harness(output_root, first_uri_log))
    leftover = output_root / "EUR_USD_S5" / "000001_EUR_USD_S5.json.tmp"
    leftover.write_text("{not valid json", encoding="utf-8")

    _run_harness(tmp_path, _base_success_harness(output_root, second_uri_log))
    assert _load_uri_log(second_uri_log) is None or _load_uri_log(second_uri_log) == []
    checkpoint = _load_json(output_root / "EUR_USD_S5" / "AIOS_FOREX_SCALPING_HISTORY_CHECKPOINT.json")
    manifest = _load_json(output_root / "AIOS_FOREX_SCALPING_HISTORY_MANIFEST.json")
    assert checkpoint["status"] == "SERIES_COMPLETE"
    assert manifest["complete_series"] == 1


def test_unsupported_granularity_fails_before_credential_request(tmp_path: Path):
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-OutputRoot",
            str(tmp_path / "out"),
            "-Instruments",
            "EUR_USD",
            "-Granularities",
            "S1",
            "-FromUtc",
            "2020-01-01T00:00:00Z",
            "-ToUtc",
            "2020-01-01T00:00:20Z",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "Enter OANDA Practice token" not in combined
    assert TEST_TOKEN not in combined


def test_supported_granularity_duration_contract_static():
    text = SCRIPT.read_text(encoding="utf-8")
    expected = {
        "S5": 5,
        "S10": 10,
        "S15": 15,
        "S30": 30,
        "M1": 60,
        "M2": 120,
        "M4": 240,
    }
    for granularity, seconds in expected.items():
        assert f"{granularity} = {seconds}" in text


def test_retryable_statuses_and_timeout_retry_then_succeed(tmp_path: Path):
    for status in [
        "HTTP_STATUS:408",
        "HTTP_STATUS:425",
        "HTTP_STATUS:429",
        "HTTP_STATUS:429 RETRY_AFTER:7",
        "HTTP_STATUS:500",
        "HTTP_STATUS:502",
        "HTTP_STATUS:503",
        "HTTP_STATUS:504",
        "The operation has timed out",
    ]:
        output_root = tmp_path / status.replace(":", "_").replace(" ", "_")
        result = _run_harness(tmp_path, _retry_harness(output_root, status, expected_failures=2))
        retry_log = _load_json(output_root / "retry_log.json")
        assert retry_log["attempts"] == 3
        assert len(retry_log["sleeps"]) == 2
        assert all(1 <= int(value) <= 60 for value in retry_log["sleeps"])
        if "RETRY_AFTER:7" in status:
            assert int(retry_log["sleeps"][0]) >= 7
        assert "HEARTBEAT phase=ACQUISITION_RETRY_WAIT pair=EUR_USD granularity=S5 batch=0 candles=0 last=NONE retry=1" in result.stdout


def test_retry_exhaustion_fails_closed_without_token_output(tmp_path: Path):
    output_root = tmp_path / "retry_exhausted"
    result = _run_harness(tmp_path, _retry_harness(output_root, "HTTP_STATUS:503", expected_failures=99), check=False)
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "RETRY_EXHAUSTED" in combined
    assert TEST_TOKEN not in combined
    assert "Authorization" not in combined


def test_credential_authorization_and_request_contract_4xx_fail_closed_without_token_output(tmp_path: Path):
    cases = {
        "HTTP_STATUS:401": "OANDA_PRACTICE_AUTHENTICATION_REJECTED",
        "HTTP_STATUS:403": "OANDA_PRACTICE_AUTHORIZATION_REJECTED",
        "HTTP_STATUS:400": "REQUEST_CONTRACT_FAILURE",
        "HTTP_STATUS:404": "REQUEST_CONTRACT_FAILURE",
    }
    for status, expected in cases.items():
        output_root = tmp_path / status.replace(":", "_")
        result = _run_harness(tmp_path, _retry_harness(output_root, status, expected_failures=99), check=False)
        combined = result.stdout + result.stderr
        assert result.returncode != 0
        assert expected in combined
        assert TEST_TOKEN not in combined
        assert "Authorization" not in combined


def test_scalping_history_helper_static_safety_contract():
    text = SCRIPT.read_text(encoding="utf-8")
    lower = text.lower()
    assert "api-fxpractice.oanda.com" in text
    assert "api-fxtrade.oanda.com" in text
    assert "GET_ONLY" in text
    assert "order_endpoint_allowed = $false" in text
    assert "live_host_allowed = $false" in text
    assert "token_persistence_allowed = $false" in text
    assert "token_output_allowed = $false" in text
    assert "bearer " not in lower
    assert "sk-" not in lower
    assert "/orders" not in lower
    assert "-method post" not in lower
    assert "Invoke-RestMethod -Method Get" in text
    assert "-TimeoutSec $RequestTimeoutSeconds" in text
    assert "to_sent_on_each_request = $false" in text
    uri_lines = [line for line in text.splitlines() if "$Uri =" in line]
    assert uri_lines
    assert all("from=" in line and "count=" in line and "to=" not in line for line in uri_lines)
