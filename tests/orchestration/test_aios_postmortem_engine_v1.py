import json
from copy import deepcopy
import pytest
from automation.orchestration.postmortem.aios_postmortem_engine_v1 import (
    DuplicateEventError, PatternMemory, PostmortemEngine, ValidationError,
    analyze_trades, build_hypothesis, canonical_json, classify, classify_trade_patterns,
    learn, performance_statistics, progress_accounting, qualify_trades,
    recommend_experiments, transition, validate_analysis_result, validate_event, validate_pattern,
)

def event(eid="event-1", iid="incident-1"):
    h="a"*64
    return {"event_id":eid,"incident_id":iid,"packet_id":"packet-1","task_id":"task-1","run_id":"run-1",
      "worker_identity":"EAST_OCC_01","supervisor_identity":"Codex-East","lane":"postmortem",
      "timestamp":"2026-08-12T00:00:00Z","repository_identity":"ai-rtony91/Ai_Os","worktree":"/workspace/Ai_Os",
      "branch":"work","base_sha":"1"*40,"head_sha":"2"*40,"tree_sha":"3"*40,"worktree_state":"CLEAN",
      "remote_state":"LOCAL_ONLY","failing_stage":"publication","sanitized_detection_signature":"local-commit-unpublished",
      "evidence_references":["git:3ae69d3"],"evidence_hashes":[h],"outcome_classification":"LOCAL_COMMIT_AT_RISK",
      "root_cause_status":"UNVERIFIED","verified_root_cause":None,"hypotheses":[],"recovery_attempts":[],
      "recovery_result":"NOT_ATTEMPTED","validators_after_recovery":[],"durability_state":"AT_RISK",
      "lesson_status":"PENDING","promotion_status":"NOT_ELIGIBLE","next_safe_action":"PUBLISH_AND_VERIFY_COMMIT"}

def test_valid_and_malformed_and_duplicates():
    assert validate_event(event())["event_id"] == "event-1"
    bad=event(); del bad["packet_id"]
    with pytest.raises(ValidationError): validate_event(bad)
    eng=PostmortemEngine(); eng.analyze(event())
    with pytest.raises(DuplicateEventError): eng.analyze(event())

def test_secret_nonfinite_path_and_contradiction_rejected():
    for mutate in (lambda x:x.update(password="x"),lambda x:x.update(worktree="../escape"),lambda x:x.update(recovery_result=float("nan"))):
      x=event(); mutate(x)
      with pytest.raises(ValidationError): validate_event(x)
    x=event(); x["durability_state"]="REMOTE_VERIFIED"
    with pytest.raises(ValidationError): validate_event(x)

def test_classification_is_deterministic_and_bounded():
    assert classify({"dirty_worktree":True}) == classify({"dirty_worktree":True})
    cases={"origin_absent":"ORIGIN_ABSENT","origin_incorrect":"ORIGIN_INCORRECT","authorization_unavailable":"AUTHORIZATION_UNAVAILABLE","local_commit_only":"LOCAL_COMMIT_AT_RISK","missing_commit":"MISSING_COMMIT","missing_branch":"MISSING_BRANCH","worker_lease_expired":"WORKER_LEASE_EXPIRED","worker_active":"WORKER_STILL_ACTIVE","application_lock_expired":"STALE_APPLICATION_LOCK","git_index_lock_persistent":"GIT_LOCK_REVIEW_REQUIRED","orphaned_apply":"ORPHANED_APPLY","duplicate_apply":"DUPLICATE_APPLY","packet_collision":"PACKET_COLLISION","corrupt_evidence":"CORRUPT_STATE","validators_failed":"VALIDATION_FAILURE","ci_failed":"CI_FAILURE"}
    for flag, outcome in cases.items(): assert classify({flag:True})["outcome_classification"] == outcome
    assert classify({"local_commit_only":True})["durability_state"] == "AT_RISK"

def test_hypotheses_do_not_become_causes_without_proof_and_keep_contradictions():
    h=build_hypothesis("h1","cause",["i1"],["i2"],"bounded test","PASSED")
    assert h["confidence_level"] == "UNVERIFIED" and h["contradicting_incidents"] == ["i2"]
    assert build_hypothesis("h1","cause",["i1"],[],"bounded test","PASSED")["promotion_eligible"]

def test_lesson_is_evidence_not_authority():
    lesson=learn(event())
    assert lesson["verified_root_cause"] is None and lesson["authority"] == "EVIDENCE_NOT_GOVERNANCE"
    assert lesson["governance_promotion"] == "SEPARATE_HUMAN_OWNER_APPROVAL_REQUIRED"

def test_pattern_independence_duplicate_suppression_and_promotion():
    memory=PatternMemory(); first=memory.observe(event())
    assert first["independent_incident_count"] == 1 and not first["promotion_eligible"]
    replay=memory.observe(event()); assert replay["duplicate_suppressed"] and replay["independent_incident_count"] == 1
    second=memory.observe(event("event-2","incident-2")); assert second["independent_incident_count"] == 2 and second["promotion_eligible"]
    critical=memory.pattern("local-commit-unpublished",safety_critical=True)
    assert not critical["promotion_eligible"] and critical["human_owner_review_required"]

def test_mutable_replay_and_contradictory_incident_rejected():
    memory=PatternMemory(); memory.observe(event())
    x=event(); x["recovery_result"]="CHANGED"
    with pytest.raises(ValidationError): memory.observe(x)
    x=event("event-2","incident-1"); x["recovery_result"]="CHANGED"
    with pytest.raises(ValidationError): memory.observe(x)

def test_state_machine_fails_closed_and_is_idempotent():
    assert transition("OBSERVED","OBSERVED")["changed"] is False
    with pytest.raises(ValidationError): transition("OBSERVED","CLOSED")
    assert transition("VERIFIED","CLOSED")["state"] == "CLOSED"

def test_lost_supertrend_commit_is_analysis_only():
    result=classify({"local_commit_only":True,"commit":"3ae69d3"})
    assert result["outcome_classification"] == "LOCAL_COMMIT_AT_RISK"
    assert set(result)=={"outcome_classification","next_safe_action","durability_state"}

def test_corrupt_evidence_quarantine_plan_and_no_authority():
    result=classify({"corrupt_evidence":True})
    assert result["next_safe_action"] == "QUARANTINE_EVIDENCE"
    forbidden="broker credential order campaign strategy deployment scheduler daemon money"
    assert all(word not in canonical_json(result).lower() for word in forbidden.split())

def test_deterministic_machine_output_and_end_to_end():
    e=event(); engine=PostmortemEngine(); analyzed=engine.analyze(e); lesson=engine.learn(analyzed)
    plan=engine.plan({"local_commit_only":True}); verified=engine.verify({"validators_passed":True,"evidence_intact":True})
    closed=engine.close(verified["state"])
    assert canonical_json(lesson)==canonical_json(lesson)
    assert plan["durability_state"]=="AT_RISK" and closed["state"]=="CLOSED"

def test_pattern_schema_is_closed_and_count_is_consistent():
    pattern=PatternMemory().observe(event())
    assert validate_pattern(pattern) == pattern
    pattern["independent_incident_count"]=2
    with pytest.raises(ValidationError): validate_pattern(pattern)

def test_pattern_cannot_promote_one_incident():
    pattern=PatternMemory().observe(event()); pattern["promotion_eligible"]=True
    with pytest.raises(ValidationError): validate_pattern(pattern)

def typed_evidence(kind="trade_execution", ref="exec:1"):
    return {"evidence_type":kind,"reference":ref,"evidence_hash":"b"*64,"source":"test"}

def trade(trade_id="t1", pnl=10.0, status="CLOSED", metrics=None, **overrides):
    value={"trade_id":trade_id,"status":status,"instrument":"EUR_USD","side":"BUY",
      "entry_timestamp":"2026-01-01T00:00:00Z","exit_timestamp":"2026-01-01T00:05:00Z",
      "entry_price":1.1,"exit_price":1.2,"realized_pnl":pnl,"fees":1.0,
      "evidence":[typed_evidence()],"metrics":metrics or {}}
    value.update(overrides); return value

def test_zero_trades_and_unproven_progress():
    result=analyze_trades([])
    assert result["performance_statistics"]["total_trades"]==0 and result["performance_statistics"]["win_rate"] is None
    assert result["progress"]["qualifying_trades"]=="NOT_PROVEN"

def test_winner_loser_mixed_and_breakeven_statistics():
    accepted=qualify_trades([trade("w",11),trade("l",-4),trade("b",1)])["qualifying"]
    stats=performance_statistics(accepted)
    assert (stats["wins"],stats["losses"],stats["breakeven"])==(1,1,1)
    assert stats["net_pnl"]==5 and stats["expectancy"]==pytest.approx(5/3)

def test_duplicate_open_malformed_and_unproven_rejected():
    records=[trade("d"),trade("d"),trade("o",status="OPEN"),trade("u",status="NOT_PROVEN"),{"trade_id":"bad"}]
    result=qualify_trades(records)
    assert [x["reason"] for x in result["rejected"]]==["DUPLICATE","OPEN","UNPROVEN_CLOSED_STATE","MALFORMED"]

def test_missing_execution_evidence_rejected():
    result=qualify_trades([trade(evidence=[typed_evidence("signal")])])
    assert result["rejected"][0]["reason"]=="MISSING_REQUIRED_EVIDENCE"

def test_unsupported_evidence_type_rejected():
    result=qualify_trades([trade(evidence=[typed_evidence("broker_claim")])])
    assert result["rejected"][0]["reason"]=="MALFORMED"

def test_missing_optional_fields_remain_null():
    value=qualify_trades([trade()])["qualifying"][0]
    assert value["strategy"] is None and value["supertrend_multiplier"] is None

def test_profit_factor_zero_losses_and_with_losses():
    winners=qualify_trades([trade("w",11)])["qualifying"]
    assert performance_statistics(winners)["profit_factor"]=="INFINITE"
    mixed=qualify_trades([trade("w",11),trade("l",-4)])["qualifying"]
    assert performance_statistics(mixed)["profit_factor"]==pytest.approx(10/5)

def test_net_pnl_after_fees_and_max_drawdown():
    values=qualify_trades([trade("a",11),trade("b",-4),trade("c",-3)])["qualifying"]
    stats=performance_statistics(values)
    assert stats["cumulative_pnl"]==[10.0,5.0,1.0] and stats["max_drawdown"]==9.0

def test_invalid_nonfinite_pnl_rejected():
    assert qualify_trades([trade(pnl=float("nan"))])["rejected"][0]["reason"]=="MALFORMED"

def test_false_flip_proven_and_not_proven():
    proven=qualify_trades([trade(metrics={"flip_count":1,"bars_to_reversal":2},evidence=[typed_evidence(),typed_evidence("signal","signal:1")])])["qualifying"][0]
    assert next(x for x in classify_trade_patterns(proven) if x["pattern"]=="FALSE_FLIP")["status"]=="PROVEN"
    absent=qualify_trades([trade()])["qualifying"][0]
    assert next(x for x in classify_trade_patterns(absent) if x["pattern"]=="FALSE_FLIP")["status"]=="NOT_PROVEN"

def test_low_volatility_whipsaw():
    value=qualify_trades([trade(metrics={"atr":0.2,"atr_floor":0.5,"reversal_count":2},evidence=[typed_evidence(),typed_evidence("market_condition","market:1")])])["qualifying"][0]
    assert next(x for x in classify_trade_patterns(value) if x["pattern"]=="LOW_VOLATILITY_WHIPSAW")["status"]=="PROVEN"

def test_multiplier_metadata_and_sensitivity():
    value=qualify_trades([trade(supertrend_multiplier=3,metrics={"supertrend_multiplier":3,"comparison_multiplier":2},evidence=[typed_evidence(),typed_evidence("signal","signal:1")])])["qualifying"][0]
    assert value["supertrend_multiplier"]==3
    assert next(x for x in classify_trade_patterns(value) if x["pattern"]=="MULTIPLIER_SENSITIVITY")["status"]=="PROVEN"

def test_recommendations_cite_trades_and_evidence():
    metrics={"flip_count":1,"bars_to_reversal":1}
    evidence=[typed_evidence(),typed_evidence("signal","signal:1")]
    values=qualify_trades([trade("a",metrics=metrics,evidence=evidence),trade("b",metrics=metrics,evidence=evidence)])["qualifying"]
    recommendation=recommend_experiments(values)[0]
    assert recommendation["supporting_trade_ids"]==["a","b"] and recommendation["supporting_evidence_refs"]==["exec:1","signal:1"]
    assert recommendation["evidence_status"]=="ELIGIBLE" and recommendation["authority"]=="ANALYSIS_ONLY"

def test_recommendation_below_threshold_blocked():
    value=qualify_trades([trade(metrics={"flip_count":1,"bars_to_reversal":1},evidence=[typed_evidence(),typed_evidence("signal","signal:1")])])["qualifying"]
    assert recommend_experiments(value)[0]["evidence_status"]=="BLOCKED_BELOW_THRESHOLD"

def test_recommendations_limited_to_three():
    metrics={"flip_count":1,"bars_to_reversal":1,"atr":0.1,"atr_floor":0.5,"reversal_count":3,"duration_seconds":20,
      "supertrend_multiplier":3,"comparison_multiplier":2,"trend_bars":1,"minimum_trend_bars":4}
    evidence=[typed_evidence(),typed_evidence("signal","signal:1"),typed_evidence("market_condition","market:1")]
    values=qualify_trades([trade("a",-2,metrics=metrics,evidence=evidence),trade("b",-2,metrics=metrics,evidence=evidence)])["qualifying"]
    assert len(recommend_experiments(values))==3

def test_30_trade_progress_accounting():
    evidence=[typed_evidence("campaign_runtime","campaign:1"),typed_evidence("validation","validation:1")]
    ids=[f"t{x}" for x in range(30)]
    result=progress_accounting(software_complete=100,qualifying_trade_ids=ids,evidence_items=evidence,analyzed_trade_ids=ids)
    assert result=={"software_complete":100,"evidence_complete":100.0,"trade_analysis_complete":100.0,"release_ready":100,"qualifying_trades":30,"target_trades":30}

def test_progress_does_not_fabricate_zero():
    result=progress_accounting(software_complete=100,qualifying_trade_ids=None)
    assert result["qualifying_trades"]=="NOT_PROVEN" and result["release_ready"]=="NOT_PROVEN"

def test_typed_evidence_does_not_cross_prove_market_condition():
    value=qualify_trades([trade(evidence=[typed_evidence("trade_execution")])])["qualifying"][0]
    assert value["market_condition"] is None

def test_analysis_output_contract():
    result=analyze_trades([trade()])
    assert set(result)=={"trade_records","qualification_results","performance_statistics","losing_patterns","winning_patterns","recommendations","progress"}

def test_no_broker_or_runtime_mutation_authority():
    import inspect
    from automation.orchestration.postmortem import aios_postmortem_engine_v1 as module
    source=inspect.getsource(module).lower()
    assert "import requests" not in source and "import socket" not in source and "subprocess" not in source

def test_explicit_qualification_statuses():
    result=qualify_trades([trade("q"),trade("o",status="OPEN"),trade("u",status="UNKNOWN"),trade("n",qualifies=False)])
    assert result["qualifying"][0]["qualification_status"]=="QUALIFYING"
    assert [x["reason"] for x in result["rejected"]]==["OPEN","UNPROVEN_CLOSED_STATE","NONQUALIFYING"]

def test_malformed_pattern_metrics_are_not_proven_or_raised():
    value=qualify_trades([trade(metrics={"flip_count":"one","bars_to_reversal":2},evidence=[typed_evidence(),typed_evidence("signal")])])["qualifying"][0]
    pattern=next(x for x in classify_trade_patterns(value) if x["pattern"]=="FALSE_FLIP")
    assert pattern["status"]=="NOT_PROVEN" and pattern["reason"]=="MALFORMED_METRICS"

def test_pattern_requires_typed_supporting_evidence():
    value=qualify_trades([trade(metrics={"flip_count":1,"bars_to_reversal":2})])["qualifying"][0]
    pattern=next(x for x in classify_trade_patterns(value) if x["pattern"]=="FALSE_FLIP")
    assert pattern["status"]=="NOT_PROVEN" and pattern["reason"]=="MISSING_TYPED_EVIDENCE"

def test_malformed_metrics_cannot_enable_recommendation():
    evidence=[typed_evidence(),typed_evidence("signal")]
    values=qualify_trades([trade("a",metrics={"flip_count":"one","bars_to_reversal":1},evidence=evidence),trade("b",metrics={"flip_count":"one","bars_to_reversal":1},evidence=evidence)])["qualifying"]
    assert recommend_experiments(values)==[]

def test_raw_boolean_cannot_promote_progress():
    result=progress_accounting(software_complete=100,qualifying_trade_ids=["t1"],evidence_proven=True,analysis_complete=True)
    assert result["evidence_complete"]=="NOT_PROVEN" and result["release_ready"]=="NOT_PROVEN"

def test_campaign_and_validation_evidence_are_both_required():
    campaign=[typed_evidence("campaign_runtime")]
    result=progress_accounting(software_complete=100,qualifying_trade_ids=["t1"],evidence_items=campaign,analyzed_trade_ids=["t1"])
    assert result["qualifying_trades"]=="NOT_PROVEN"

def test_event_schema_covers_emitted_trade_contracts():
    from pathlib import Path
    schema=json.loads(Path("schemas/aios/orchestration/AIOS_POSTMORTEM_EVENT.v1.schema.json").read_text())
    assert {"typedEvidence","normalizedTrade","rejection","statistics","progress"} <= set(schema["$defs"])
    assert "NONQUALIFYING" in schema["$defs"]["rejection"]["properties"]["reason"]["enum"]
    assert "NOT_PROVEN" in canonical_json(schema["$defs"]["progress"])

def test_pattern_schema_covers_classification_and_recommendation():
    from pathlib import Path
    schema=json.loads(Path("schemas/aios/orchestration/AIOS_POSTMORTEM_PATTERN.v1.schema.json").read_text())
    assert {"tradePattern","patternClassification","recommendation"} <= set(schema["$defs"])
    assert schema["$defs"]["recommendation"]["properties"]["authority"]["const"]=="ANALYSIS_ONLY"

def _schema_documents():
    from pathlib import Path
    event=json.loads(Path("schemas/aios/orchestration/AIOS_POSTMORTEM_EVENT.v1.schema.json").read_text())
    pattern=json.loads(Path("schemas/aios/orchestration/AIOS_POSTMORTEM_PATTERN.v1.schema.json").read_text())
    return event,pattern

def _schema_validate(value, schema, event=None, pattern=None):
    event=event or schema; pattern=pattern or schema
    if "$ref" in schema:
        ref=schema["$ref"]
        local_name=ref.rsplit("/",1)[-1]
        document=pattern if ref.startswith("AIOS_POSTMORTEM_PATTERN") or (ref.startswith("#") and local_name in pattern.get("$defs",{})) else event
        target=ref.split("#",1)[-1]
        for part in target.lstrip("/").split("/") if target else []: document=document[part]
        return _schema_validate(value,document,event,pattern)
    if "oneOf" in schema:
        passed=0
        for candidate in schema["oneOf"]:
            try: _schema_validate(value,candidate,event,pattern); passed+=1
            except AssertionError: pass
        assert passed==1; return
    if "const" in schema: assert value==schema["const"]
    if "enum" in schema: assert value in schema["enum"]
    types=schema.get("type")
    if types:
        types=[types] if isinstance(types,str) else types
        checks={"object":lambda x:isinstance(x,dict),"array":lambda x:isinstance(x,list),"string":lambda x:isinstance(x,str),
          "number":lambda x:isinstance(x,(int,float)) and not isinstance(x,bool),"integer":lambda x:isinstance(x,int) and not isinstance(x,bool),
          "boolean":lambda x:isinstance(x,bool),"null":lambda x:x is None}
        assert any(checks[t](value) for t in types)
    if isinstance(value,dict):
        assert set(schema.get("required",[])) <= set(value)
        if schema.get("additionalProperties") is False: assert set(value) <= set(schema.get("properties",{}))
        for key,item in value.items():
            if key in schema.get("properties",{}): _schema_validate(item,schema["properties"][key],event,pattern)
    if isinstance(value,list):
        if "maxItems" in schema: assert len(value)<=schema["maxItems"]
        for item in value:
            if "items" in schema: _schema_validate(item,schema["items"],event,pattern)

def _validate_emitted_schema(result):
    event,pattern=_schema_documents()
    _schema_validate(result,event["$defs"]["analysisResult"],event,pattern)

def test_valid_mixed_trade_analysis_schema_passes():
    result=analyze_trades([trade("w",11),trade("l",-4)])
    assert validate_analysis_result(result)==result; _validate_emitted_schema(result)

def test_zero_trade_not_proven_schema_passes():
    result=analyze_trades([])
    assert result["progress"]["qualifying_trades"]=="NOT_PROVEN"; _validate_emitted_schema(result)

def test_malformed_normalized_trade_contract_fails():
    result=analyze_trades([trade()]); del result["trade_records"][0]["trade_id"]
    with pytest.raises((ValidationError,AssertionError)): validate_analysis_result(result)
    with pytest.raises(AssertionError): _validate_emitted_schema(result)

def test_undeclared_top_level_analysis_field_fails():
    result=analyze_trades([]); result["unexpected"]=True
    with pytest.raises((ValidationError,AssertionError)): validate_analysis_result(result)
    with pytest.raises(AssertionError): _validate_emitted_schema(result)

def test_malformed_statistics_contract_fails():
    result=analyze_trades([]); result["performance_statistics"]["total_trades"]=1
    with pytest.raises(ValidationError): validate_analysis_result(result)

def test_malformed_recommendation_contract_fails():
    result=analyze_trades([]); result["recommendations"]=[{"authority":"ANALYSIS_ONLY"}]
    with pytest.raises(ValidationError): validate_analysis_result(result)
    with pytest.raises(AssertionError): _validate_emitted_schema(result)

def test_malformed_progress_proof_contract_fails():
    result=analyze_trades([]); result["progress"]["evidence_complete"]=100
    with pytest.raises(ValidationError): validate_analysis_result(result)

def test_engine_generated_campaign_result_validates_end_to_end():
    evidence=[typed_evidence("campaign_runtime","campaign:1"),typed_evidence("validation","validation:1")]
    result=analyze_trades([trade()],campaign_evidence=evidence)
    assert result["progress"]["qualifying_trades"]==1; _validate_emitted_schema(result)
