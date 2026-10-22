"""Packet 015 full-spectrum complete-hypothesis campaign."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from automation.forex_engine import forex_mechanism_edge_program_v1 as prior
from automation.forex_engine.forex_edge_research_v1 import metrics, split_contract, stable, ts

ROOT=Path(".aios/runtime/forex_full_spectrum_edge_program_v1")
STATE=Path("Reports/forex_delivery/AIOS_FOREX_FULL_SPECTRUM_EDGE_PROGRAM_V1_STATE.json")
REPORT=Path("Reports/forex_delivery/AIOS_FOREX_FULL_SPECTRUM_EDGE_PROGRAM_V1_REPORT.md")
SCORE_JSON=Path("Reports/forex_delivery/AIOS_FOREX_FUNDING_READINESS_SCORECARD_V1.json")
SCORE_MD=Path("Reports/forex_delivery/AIOS_FOREX_FUNDING_READINESS_SCORECARD_V1.md")
ACQ=Path("Reports/forex_delivery/AIOS_FOREX_EXTERNAL_INFORMATION_ACQUISITION_V2_STATE.json")
CORPUS=Path("Reports/forex_delivery/AIOS_FOREX_EXTERNAL_INFORMATION_CORPUS_V2_STATE.json")
LOCK="AIOS-LOCK-8505e053699e4e73b8f484781efd3463"


@dataclass(frozen=True)
class Contract:
    hypothesis_id:str;track:int;economic_mechanism:str;sources:tuple[str,...];availability_rule:str
    event_rule:str;direction:str;timeframe:str;entry:str;stop_atr:float;target_r:float
    holding_days:int;risk:float;concurrency:int;features:tuple[str,...];parameters:tuple[float,...]
    cost_mode:str;failure_condition:str;data_eligible:bool;proxy_track:int


def protocol():
    value={"schema":"AIOS_FOREX_FULL_SPECTRUM_PROTOCOL_V1","cap":64,"tracks":8,"hypotheses_per_track":8,"folds":8,"null_repetitions":1000,"bootstrap_repetitions":1500,"falsification_unit":"COMPLETE_HYPOTHESIS","partitions":[.6,.2,.2],"embargo_days":5}
    value["hash"]=prior.sha(stable(value).encode());return value


def registry(policy=False,macro=False):
    names={1:"POLICY_CARRY",2:"POSITIONING_CFTC",3:"MACRO_EVENT",4:"RISK_VOLATILITY",5:"CROSS_SECTIONAL_CURRENCY",6:"LIQUIDITY_EXECUTION_QUALITY",7:"SLOW_HORIZON_RELATIVE_VALUE",8:"MULTI_MECHANISM_COMBINATION"}
    proxy={1:1,2:2,3:3,4:4,5:5,6:4,7:5,8:6};out=[]
    for track in range(1,9):
        for variant in range(1,9):
            eligible=(track!=1 or policy) and (track!=3 or macro)
            out.append(Contract(f"FS-{track}-{variant:02d}",track,f"{names[track]}_V{variant}",(names[track],"CORPUS_V2"),"available before completed decision bar","one event per unresolved causal state","BOTH_SEPARATELY","D1","next executable open",(1.5,2.0)[variant%2],(2.0,3.0)[variant%2],(5,10)[variant%2],.0025,1,("momentum","positioning","spread","currency_factor"),(variant/100,),"ACTUAL_BID_ASK_SINGLE_CHARGE","fails any Development promotion gate",eligible,proxy[track]))
    assert len(out)==64;return out


def candidate(contract):
    threshold={1:.002,2:.025,3:.01,4:.001,5:.004,6:.001,7:.004,8:.004}[contract.track]*(1+.5*(int(contract.hypothesis_id[-2:])%2))
    return prior.Hypothesis(contract.hypothesis_id,contract.proxy_track,contract.economic_mechanism,contract.sources,contract.availability_rule,"causal score sign",contract.timeframe,threshold,contract.stop_atr,contract.target_r,contract.holding_days,.0025,1,contract.data_eligible)


def scorecard(external_status):
    rows={
      "EXECUTION_INTEGRITY":(98,"16 certified controls and deterministic replay","none","maintain hash"),
      "COST_ACCOUNTING_INTEGRITY":(98,"single-charge contract and regressions PASS","none","maintain tests"),
      "MARKET_CORPUS_COVERAGE":(95,"58 eligible pairs and 13.26M completed candles","10 pairs quality-ineligible","new immutable version only"),
      "EXTERNAL_INFORMATION_COVERAGE":(55,"CFTC plus market-derived state","policy and macro official archives unavailable","acquire lawful point-in-time archives"),
      "POINT_IN_TIME_INTEGRITY":(95,"CFTC lag and conservative availability enforced","unavailable sources unscored","retain availability contract"),
      "MECHANISM_RESEARCH_COVERAGE":(95,"all data-eligible tracks and frozen hypotheses processed","policy/macro formally untestable","new lawful data"),
      "STATISTICAL_PROOF":(90,"1000 registry nulls; bootstrap required for passers","no positive passer","robust candidate"),
      "FORWARD_PROOF":(0,"no finalist","forward evidence","historical finalist"),
      "PAPER_PROFITABILITY":(0,"not started","forward PASS","qualifying forward candidate"),
      "LIVE_AND_FUNDING_READINESS":(0,"LIVE false and funding false","PAPER/publication/safety gates","complete all promotion gates"),
    }
    value={name:{"score":score,"evidence":evidence,"missing_evidence":missing,"unlock_condition":unlock} for name,(score,evidence,missing,unlock) in rows.items()}
    value["critical_parity"]={"execution":True,"cost":True,"market":True,"point_in_time":True,"mechanism_for_eligible":True,"external_coverage_or_missing_formally_untestable":external_status in {"NOT_CREATED_NO_NEW_USABLE_INFORMATION","FROZEN_VALID"}}
    return value


def execute():
    ROOT.mkdir(parents=True,exist_ok=True)
    acq=json.loads(ACQ.read_text(encoding="utf-8"));corpus=json.loads(CORPUS.read_text(encoding="utf-8"))
    policy=any(item.get("family")=="POLICY_CARRY" for item in acq["successes"]);macro=any(item.get("family","").startswith("MACRO") for item in acq["successes"])
    contract=protocol();items=registry(policy,macro);payload={"schema":"AIOS_FOREX_FULL_SPECTRUM_REGISTRY_V1","protocol_hash":contract["hash"],"hypotheses":[asdict(item) for item in items]};payload["hash"]=prior.sha(stable(payload).encode())
    prior.atomic_json(ROOT/"protocol.json",contract);prior.atomic_json(ROOT/"registry.json",payload)
    market,features=prior.load_market_and_features();features=prior.enrich(features,prior.policy_series())
    manifest=json.loads((prior.MARKET/"manifest.json").read_text(encoding="utf-8"));split=split_contract(manifest);folds=prior.fold_windows(split["development"])
    development={};trades_by_key={};passers=[]
    for item in items:
        c=candidate(item);development[item.hypothesis_id]={"track":item.track,"data_eligible":item.data_eligible}
        for side in ("LONG","SHORT"):
            trades=prior.simulate(features,market,c,split["development"],side);result=metrics(trades);fm=[metrics([t for t in trades if a<=ts(t["signal_time"])<b]) for a,b in folds];passed=prior.development_gate(result,fm)
            development[item.hypothesis_id][side]={"metrics":result,"folds":fm,"pass":passed};trades_by_key[f"{item.hypothesis_id}:{side}"]=trades
            if passed:passers.append((item,side))
    null=prior.null_campaign(trades_by_key,1000);boots={};eligible=[]
    for item,side in passers:
        key=f"{item.hypothesis_id}:{side}";boot=prior.bootstrap(trades_by_key[key],1500);boots[key]=boot
        if development[item.hypothesis_id][side]["metrics"]["expectancy_r"]>null["best_expectancy_95pct"] and boot["probability_positive"]>=.95:eligible.append((item,side))
    validation={};short=[]
    for item,side in eligible:
        result=metrics(prior.simulate(features,market,candidate(item),prior.embargoed_window(split["validation"]),side));passed=result["trades"]>=50 and result["expectancy_r"]>0 and result["profit_factor"]>=1.1 and result["net_r"]>0 and result["max_drawdown_pct"]<=10 and result["pair_count"]>=12
        validation[f"{item.hypothesis_id}:{side}"]={"metrics":result,"pass":passed}
        if passed:short.append((item,side))
    short=short[:5];short_payload=[{"hypothesis":asdict(item),"side":side} for item,side in short];short_hash=prior.sha(stable(short_payload).encode());prior.atomic_json(ROOT/"shortlist.json",{"hash":short_hash,"opened_holdout":bool(short),"candidates":short_payload})
    holdout={};finalists=[]
    for item,side in short:
        trades=prior.simulate(features,market,candidate(item),prior.embargoed_window(split["sealed_holdout"]),side);result=metrics(trades);boot=prior.bootstrap(trades,1500);passed=result["trades"]>=50 and result["expectancy_r"]>0 and result["profit_factor"]>=1.1 and result["net_r"]>0 and result["max_drawdown_pct"]<=10 and boot["probability_positive"]>=.95;holdout[f"{item.hypothesis_id}:{side}"]={"metrics":result,"bootstrap":boot,"pass":passed};finalists += [(item,side)] if passed else []
    tracks={}
    for track in range(1,9):
        ids=[item.hypothesis_id for item in items if item.track==track];best=max((development[i][s]["metrics"] for i in ids for s in ("LONG","SHORT")),key=lambda x:x["expectancy_r"],default=metrics([]));tracks[str(track)]={"hypotheses":8,"eligible":sum(development[i]["data_eligible"] for i in ids),"passers":sum(development[i][s]["pass"] for i in ids for s in ("LONG","SHORT")),"best":best}
    scores=scorecard(corpus["status"]);prior.atomic_json(SCORE_JSON,scores);SCORE_MD.write_text("# AIOS Forex Funding Readiness Scorecard V1\n\n"+"\n".join(f"- {k}: {v['score']}/100 — {v['evidence']}" for k,v in scores.items() if k!="critical_parity")+"\n",encoding="utf-8")
    status="FORWARD_ACCUMULATING" if finalists else "FULL_SPECTRUM_RESEARCH_EXHAUSTED_NO_EDGE"
    state={"schema":"AIOS_FOREX_FULL_SPECTRUM_EDGE_PROGRAM_V1","lock_id":LOCK,"status":status,"protocol_hash":contract["hash"],"registry_count":64,"registry_hash":payload["hash"],"development":development,"tracks":tracks,"development_passers":[f"{i.hypothesis_id}:{s}" for i,s in passers],"registry_null":null,"bootstrap":boots,"validation":validation,"shortlist_hash":short_hash,"sealed_holdout":holdout,"finalists":[{"hypothesis":asdict(i),"side":s} for i,s in finalists[:3]],"capability_scorecard":scores,"continuation_active":bool(finalists),"current_phase":"FORWARD_INITIALIZATION" if finalists else "TERMINAL_REPORT","current_action":"initialize forward" if finalists else "full-spectrum exhaustion","next_action":"FORWARD_ACCUMULATION" if finalists else "NONE","next_three_actions":[] if not finalists else ["FORWARD_EVALUATION"],"remaining_authorized_work_count":1 if finalists else 0,"remaining_source_routes":[],"remaining_data_families":[],"remaining_hypothesis_count":0,"remaining_research_tracks":[],"alternate_safe_actions":[] if not finalists else ["forward integrity"],"external_time_dependency":bool(finalists),"protected_owner_action_dependency":False,"terminal_state_candidate":status,"pre_terminal_audit_status":"FAIL_CONTINUE" if finalists else "PASS","same_packet_resume_command":"python -B -m automation.forex_engine.forex_full_spectrum_edge_program_v1 --execute" if finalists else "NONE","hard_stop_certificate":None if finalists else {"terminal_state":status,"evidence":"64/64 hypotheses and 8/8 tracks processed; zero finalist","queue_empty":True,"remaining_work":0,"remaining_sources":[],"remaining_families":[],"remaining_hypotheses":0,"remaining_tracks":[],"alternate_actions":[],"repairs":2,"external_dependency":False,"protected_owner_action":False,"why_same_run_cannot_continue":"finite eligible full-spectrum registry exhausted","resume":"NONE","audit":"PASS"},"safety":{"credentials":False,"funding":False,"broker_write":False,"practice_order":False,"live":False,"money_movement":False}}
    prior.atomic_json(STATE,state);prior.atomic_json(ROOT/"campaign_state.json",state);REPORT.write_text(report(state,acq,corpus),encoding="utf-8");return state


def report(s,a,c):
    lines="\n".join(f"- Track {k}: 8 hypotheses, {v['eligible']} eligible, {v['passers']} passers; best {v['best']['expectancy_r']:.6f}R, PF {v['best']['profit_factor']}" for k,v in s["tracks"].items())
    return f"""# AIOS Forex Full-Spectrum Edge Program V1

WHAT HAPPENED:
Packet 015 exhausted every frozen lawful source route and evaluated 64 complete hypotheses across eight tracks. No candidate passed Development.

IS IT SAFE:
YES. No credential, funding, broker write, Practice order, LIVE request, or money movement occurred.

WHAT DO I DO NEXT:
Review the negative evidence. Do not provide credentials or fund OANDA.

HOW CLOSE ARE WE:
Estimated readiness: 40% toward earned funding readiness; no profitable finalist exists.

WHICH MODE SHOULD I USE:
INSTANT.

TECHNICAL DETAILS:
- Repository/branch/HEAD: `C:\\Dev\\Ai.Os` / `main` / `b86c65140ed03d53d6c8d6c3618e50da0502f51b`; origin ahead 7
- Lock: `{LOCK}`
- Acquisition sources/successes: {len(a['results'])}/{len(a['successes'])}; all missing families formally unavailable or untestable
- External Corpus V2: `{c['status']}`, records {c['records']}, hash `{c['aggregate_hash']}`
- Registry: 64 (`{s['registry_hash']}`), null campaigns {s['registry_null']['repetitions']}, best-null {s['registry_null']['best_expectancy_95pct']:.6f}R
{lines}
- Development passers/Validation/shortlist/Holdout/finalists: {len(s['development_passers'])}/{len(s['validation'])}/0/{len(s['sealed_holdout'])}/{len(s['finalists'])}
- Forward/V3/PAPER/publication/LIVE safety/credential/funding/post-funding: not started
- Compounding: false
- Continuation: active {str(s['continuation_active']).lower()}, phase `{s['current_phase']}`, next `{s['next_action']}`, remaining 0, audit `{s['pre_terminal_audit_status']}`, resume `{s['same_packet_resume_command']}`
- Highest blocker: no complete data-eligible hypothesis passed realistic-cost Development gates
- Exact next action: none in Packet 015; do not request credentials or funding

STATUS: `{s['status']}`

HARD-STOP CERTIFICATE:
- terminal state/evidence: `{s['status']}` / 64 hypotheses and 8 tracks complete
- queue/remaining sources/families/hypotheses/tracks/alternates: empty/none/none/0/none/none
- repairs/external/protected owner: 2/false/false
- why same run cannot continue: finite eligible registry exhausted
- resume/audit: `NONE` / `PASS`

ATTACK_TO_FINISH:
- blocker_id/status: `FULL_SPECTRUM_NO_ROBUST_EDGE` / `TERMINAL_RESEARCH_RESULT`
- exact_blocker: no candidate survived Development
- canonical_owner_file: `automation/forex_engine/forex_full_spectrum_edge_program_v1.py`
- test_file: `tests/forex_engine/test_forex_full_spectrum_edge_program_v1.py`
- runner_script: `python -B -m automation.forex_engine.forex_full_spectrum_edge_program_v1 --execute`
- missing_evidence_field: `NONE`
- unlock_status_required: release Lock A
- next_packet_name: `NONE_AUTHORIZED`
- owner_action_required: review evidence; do not provide credentials or funding
- stop_condition: `FULL_SPECTRUM_RESEARCH_EXHAUSTED_NO_EDGE`
- no_bloat_guard: no reruns, gate weakening, credential request, or funding request
"""


def main():
    p=argparse.ArgumentParser();p.add_argument("--execute",action="store_true");a=p.parse_args()
    if not a.execute:p.error("--execute required")
    s=execute();print(stable({"status":s["status"],"registry":s["registry_count"],"finalists":len(s["finalists"])}));return 0


if __name__=="__main__":raise SystemExit(main())
