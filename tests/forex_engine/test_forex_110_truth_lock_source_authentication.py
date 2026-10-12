"""Synthetic engineering regressions. No market, holdout, or native state access."""
import dataclasses
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(os.environ.get('TRUTH_LOCK_SOURCE_ROOT', Path(__file__).resolve().parents[2])).resolve()
sys.path.insert(0, str(ROOT))
from automation.forex_engine.forex_110_profit_evidence_truth_lock_v1 import (
    run_profit_evidence_truth_lock, build_report_markdown as profit_report,
)
from automation.forex_engine.forex_110_walkforward_oos_sufficiency_truth_lock_v1 import (
    run_walkforward_oos_sufficiency_truth_lock, build_report_markdown as walk_report,
)
from automation.forex_engine.profit_proof_ledger_v1 import (
    build_sample_profit_proof_candidates, build_sample_all_blocked_candidates,
)

AUTH_BLOCK = 'NO_INDEPENDENT_VERIFIER_CONNECTED'

def reports(root, candidate='c2-eur-buy-stronger-review-ready', *, profitable=True, complete=True):
    root.mkdir()
    (root / 'AIOS_FOREX_PROFITABILITY_VERDICT_V1.md').write_text('\n'.join([
        '- closed_trade_count: 40', '- min_closed_trade_count: 30',
        '- expectancy: 0.40', '- min_expectancy: 0.05',
        '- profit_factor: 1.50', '- min_profit_factor: 1.25',
        '- max_drawdown: 0.02', '- max_allowed_drawdown: 0.05',
        f'- consecutive_profitable_periods: {5 if profitable else 1}',
        '- min_profitable_periods: 4', '- after_costs: true', '- sanitized: true',
        '- evidence_age_days: 1', '- max_evidence_age_days: 7',
    ]))
    lines = [f'- candidate: `{candidate}`', '- windows_total: 6', '- windows_passed: 6',
             '- min_pass_rate: 0.75', '- max_drawdown: 0.02', '- max_allowed_drawdown: 0.05',
             '- sanitized: true', '- evidence_age_days: 1', '- max_evidence_age_days: 7']
    if complete:
        lines += ['- oos_segments_total: 4', '- oos_segments_passed: 4']
    (root / 'AIOS_FOREX_WALK_FORWARD_DEPTH_PACKET_R_V1_REPORT.md').write_text('\n'.join(lines))

def candidates(kind):
    if kind == 'default':
        return None, 'c2-eur-buy-stronger-review-ready'
    rows = [dataclasses.asdict(x) for x in build_sample_profit_proof_candidates()]
    if kind == 'renamed':
        for row in rows:
            row['candidate_id'] = 'c9-' + row['candidate_id']
            row['evidence_source'] = 'claimed-authenticated-immutable-receipt'
            row['source_authentication_status'] = 'VERIFIED'
            row['untouched_verified'] = True
        return rows, 'c9-c2-eur-buy-stronger-review-ready'
    return rows, 'c2-eur-buy-stronger-review-ready'

def assert_denied(result):
    assert result['truth_lock_status'] != 'PROVEN'
    assert result.get('profit_proof_status') != 'PROVEN'
    assert result.get('walk_forward_oos_status') != 'PROVEN'
    assert result.get('profit_persistence_unlocked', False) is False
    assert AUTH_BLOCK in result['blockers']
    assert result['source_authentication_status'] == 'UNVERIFIED'
    assert not any(result['permissions'].values())

@pytest.mark.parametrize('kind', ['default', 'explicit', 'renamed'])
@pytest.mark.parametrize('evaluate', [run_profit_evidence_truth_lock, run_walkforward_oos_sufficiency_truth_lock])
def test_synthetic_or_self_claimed_summaries_cannot_become_proof(tmp_path, kind, evaluate):
    rows, identity = candidates(kind)
    root = tmp_path / 'reports'
    reports(root, identity)
    before = {p.name:p.read_bytes() for p in root.iterdir()}
    result = evaluate(root, rows)
    assert_denied(result)
    if evaluate is run_walkforward_oos_sufficiency_truth_lock and kind != 'default':
        assert result['top_candidate_alignment']['status'] == 'ALIGNED'
    assert before == {p.name:p.read_bytes() for p in root.iterdir()}

def test_missing_candidate_does_not_select_a_default_fixture(tmp_path):
    root=tmp_path/'reports'; reports(root)
    result=run_profit_evidence_truth_lock(root)
    assert result['top_candidate_id'] == 'NONE'
    assert result['ledger_status'] != 'PROFIT_PROOF_LEDGER_PROMOTABLE'

def test_economic_failures_are_retained(tmp_path):
    root=tmp_path/'reports'; reports(root, profitable=False)
    result=run_profit_evidence_truth_lock(root, build_sample_all_blocked_candidates())
    assert_denied(result)
    assert 'profitable periods are below threshold' in result['blockers']
    assert result['ledger_status'] != 'PROFIT_PROOF_LEDGER_PROMOTABLE'
    assert len(result['ledger_blockers']) > 0

@pytest.mark.parametrize('complete,candidate', [(False,'c2-eur-buy-stronger-review-ready'), (True,'c1-eur-buy')])
def test_missing_fields_and_candidate_mismatch_remain_blocked(tmp_path, complete, candidate):
    root=tmp_path/'reports'; reports(root, candidate, complete=complete)
    result=run_walkforward_oos_sufficiency_truth_lock(root, build_sample_profit_proof_candidates())
    assert_denied(result)
    if not complete:
        assert 'oos_segments_total' in result['evidence_missing']
    else:
        assert result['top_candidate_alignment']['status'] == 'MISMATCHED'

@pytest.mark.parametrize('name', ['profit_evidence', 'walkforward_oos_sufficiency'])
def test_actual_cli_writes_only_blocked_artifacts_to_isolated_output(tmp_path, name):
    root=tmp_path/'reports'; reports(root)
    output=tmp_path/'out'
    script=ROOT/'scripts'/'forex_delivery'/f'run_forex_110_{name}_truth_lock_v1.py'
    process=subprocess.run([sys.executable,str(script),'--report-root',str(root),'--output-root',str(output),'--write-state','--write-report'],cwd=tmp_path,capture_output=True,text=True)
    assert process.returncode == 0, process.stderr
    result=json.loads(process.stdout); assert_denied(result)
    states=list(output.glob('*.json')); assert len(states) == 1
    assert json.loads(states[0].read_text()) == result
    exported=''.join(p.read_text() for p in output.glob('*.md'))
    assert 'status: `PROVEN`' not in exported
    assert 'Profit persistence unlocked: `true`' not in exported

@pytest.mark.parametrize('formatter', [profit_report, walk_report])
def test_historical_or_self_asserted_proven_labels_cannot_be_reexported(formatter):
    forged={'profit_proof_status':'PROVEN','truth_lock_status':'PROVEN',
            'walk_forward_oos_status':'PROVEN','profit_persistence_unlocked':True,
            'source_authentication_status':'VERIFIED','blockers':[],
            'attack_to_finish':{'blocker_id':'NO_BLOCKER','blocker_status':'PROVEN'},
            'owner_answer':'Profit proof is proven for operator review only.',
            'next_safe_action':'Use this as operator review evidence only.',
            'permissions':{'owner_approval_created': True}}
    before=json.dumps(forged,sort_keys=True)
    text=formatter(forged)
    assert 'status: `PROVEN`' not in text
    assert 'Profit persistence unlocked: `true`' not in text
    assert 'blocker_id: NO_BLOCKER' not in text
    assert 'Profit proof is proven' not in text
    assert 'owner_approval_created: `true`' not in text
    assert 'Use this as operator review evidence only.' not in text
    assert AUTH_BLOCK in text
    assert json.dumps(forged,sort_keys=True) == before

def test_profit_export_cannot_echo_secondary_proven_claims():
    forged={'profit_proof_status':'PROVEN','truth_lock_status':'PROVEN',
            'persistent_profitability_status':'PROVEN','ledger_status':'PROVEN',
            'top_candidate_classification':'PROVEN'}
    text=profit_report(forged)
    assert 'status: `PROVEN`' not in text
    assert 'classification: `PROVEN`' not in text
    assert AUTH_BLOCK in text

@pytest.mark.parametrize('complete,identity', [(False,'c2-eur-buy-stronger-review-ready'), (True,'c1-eur-buy')])
def test_walk_export_retains_original_negative_missing_field(tmp_path, complete, identity):
    root=tmp_path/'reports'; reports(root, identity, complete=complete)
    result=run_walkforward_oos_sufficiency_truth_lock(root, build_sample_profit_proof_candidates())
    original=result['attack_to_finish']['missing_evidence_field']
    assert original != 'source_authentication'
    text=walk_report(result)
    assert f'- missing_evidence_field: {original}\n' in text
    assert AUTH_BLOCK in text
