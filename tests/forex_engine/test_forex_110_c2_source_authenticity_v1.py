"""Unverified numeric inputs must never become authenticated economic evidence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import pytest
from automation.forex_engine import forex_110_c2_real_walkforward_oos_harness_v1 as c2
from scripts.forex_delivery.run_forex_110_c2_real_walkforward_oos_harness_v1 import main, STATE_NAME, SOURCE_NAME


@pytest.mark.parametrize('change', ['version', 'name', 'outcomes', 'claims', 'extra_fields'])
def test_numeric_payload_cannot_authenticate_itself(change):
    payload = c2.build_default_c2_harness_input()
    if change == 'version':
        payload['strategy_version'] = 'renamed-synthetic-fixture'
    elif change == 'name':
        payload['strategy_name'] = 'different-label'
    elif change == 'outcomes':
        payload['walkforward_windows'] = [[0.5, 0.25, -0.05, 0.75] for _ in range(6)]
        payload['oos_segments'] = [[0.5, 0.25, -0.05] for _ in range(4)]
    elif change == 'claims':
        payload.update(strategy_version='unverified', source_is_real_sanitized_local=True,
                       source_authentication_status='VERIFIED', sanitized=True)
    else:
        payload.update(strategy_version='unverified', evidence_sha256='a' * 64)
    result = c2.run_c2_real_walkforward_oos_harness(payload)
    assert result['source_is_real_sanitized_local'] is False
    assert result['harness_status'] == c2.HARNESS_BLOCKED
    assert 'source authenticity is not independently verified' in result['blockers']
    assert result['source_authentication_status'] == 'UNVERIFIED'
    assert result['windows_total'] == 6
    assert result['oos_segments_total'] == 4
    for flag in c2.PROTECTED_PERMISSION_FLAGS:
        assert result[flag] is False
        assert result['permissions'][flag] is False
    with pytest.raises(ValueError, match='source markdown requires proven harness evidence'):
        c2.build_source_markdown(result)


def test_cli_does_not_publish_source_for_renamed_fixture(tmp_path, capsys):
    payload = c2.build_default_c2_harness_input()
    payload['strategy_version'] = 'renamed-synthetic-fixture'
    input_path = tmp_path / 'synthetic_input.json'
    input_path.write_text(json.dumps(payload), encoding='utf-8')
    output = tmp_path / 'output'
    assert main(['--input-json', str(input_path), '--output-root', str(output),
                 '--write-state', '--write-source']) == 0
    state = json.loads((output / STATE_NAME).read_text(encoding='utf-8'))
    assert state['source_is_real_sanitized_local'] is False
    assert state['harness_status'] == c2.HARNESS_BLOCKED
    assert not (output / SOURCE_NAME).exists()
    capsys.readouterr()


def test_source_formatter_rejects_actual_historical_false_proven_state():
    # Exact saved output from the earlier renamed-synthetic-input regression.
    # Its old PROVEN label is the defect being tested, not economic evidence.
    fixture = Path(__file__).with_name('fixtures') / 'c2_historical_false_proven_state.json'
    # Git may check out JSON with CRLF on Windows; pin canonical LF content.
    data = fixture.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(data).hexdigest() == (
        '0751e66c41eb2653c7391165e34e5b3aeecbd87c34e5fad88b6804ce653ae8f9'
    )
    historical = json.loads(data)
    assert historical['harness_status'] == c2.HARNESS_PROVEN
    assert historical['source_is_real_sanitized_local'] is True
    assert 'source_authentication_status' not in historical
    before = deepcopy(historical)
    with pytest.raises(ValueError, match='source markdown requires proven harness evidence'):
        c2.build_source_markdown(historical)
    assert historical == before


@pytest.mark.parametrize('claimed_authenticity', [
    'UNVERIFIED', 'VERIFIED', 'INDEPENDENTLY_VERIFIED',
])
def test_source_formatter_rejects_self_declared_proven_result(claimed_authenticity):
    result = c2.run_c2_real_walkforward_oos_harness()
    # This public formatter also accepts mappings without evaluator provenance.
    result.update(
        harness_status=c2.HARNESS_PROVEN,
        source_authentication_status=claimed_authenticity,
        source_is_real_sanitized_local=True,
        source_is_test_or_sample=False,
        source_classification='REAL_SANITIZED_LOCAL_HARNESS',
        evidence_sha256='a' * 64,
        blockers=[],
    )
    before = deepcopy(result)
    report_before = c2.build_report_markdown(result)
    with pytest.raises(ValueError, match='source markdown requires proven harness evidence'):
        c2.build_source_markdown(result)
    assert result == before
    assert c2.build_report_markdown(result) == report_before
    assert result['windows_total'] == result['windows_passed'] == 6
    assert result['oos_segments_total'] == result['oos_segments_passed'] == 4
    for flag in c2.PROTECTED_PERMISSION_FLAGS:
        assert result[flag] is False
        assert result['permissions'][flag] is False
