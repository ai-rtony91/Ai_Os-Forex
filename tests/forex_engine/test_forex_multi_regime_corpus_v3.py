from automation.forex_engine import forex_multi_regime_corpus_v3 as module
import copy
import gzip
import hashlib
import json
from pathlib import Path
import pytest


def development_fixture(tmp_path, stamps=None):
    source = tmp_path / "source"
    path = source / "partitions/EUR_USD/2024-01.jsonl.gz"
    path.parent.mkdir(parents=True)
    stamps = stamps or ["2024-01-02T00:00:00Z", "2024-01-02T00:05:00Z"]
    with gzip.open(path, "wt", encoding="ascii") as stream:
        for stamp in stamps:
            row = {"instrument":"EUR_USD", "complete":True, "timestamp":stamp}
            row.update({side:{k:value for k in "ohlc"} for side,value in (("bid",1.0),("ask",1.01),("mid",1.005))})
            stream.write(json.dumps(row)+"\n")
    artifact = {"instrument":"EUR_USD", "path":"partitions/EUR_USD/2024-01.jsonl.gz",
                "start_utc":"2024-01-01T00:00:00Z", "end_utc":"2024-02-01T00:00:00Z",
                "records":len(stamps), "sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest = {"artifacts":[artifact], "aggregate_corpus_fingerprint":"fixture"}
    return source,manifest


def development_plan(source, manifest):
    return module.plan_development_partition_slice(manifest,source,pairs=["EUR_USD"],
            start_utc="2024-01-01T00:00:00Z",end_utc="2024-02-01T00:00:00Z",holdout_start_utc="2026-01-01T00:00:00Z")


def repin_plan(plan):
    plan["plan_sha256"] = hashlib.sha256(json.dumps({k:v for k,v in plan.items() if k!="plan_sha256"},
            sort_keys=True,separators=(",",":")).encode()).hexdigest()


def test_development_isolation_never_opens_mixed_or_holdout(tmp_path, monkeypatch):
    source,manifest = development_fixture(tmp_path)
    sealed = {**manifest["artifacts"][0],"path":"partitions/EUR_USD/2026-01.jsonl.gz",
              "start_utc":"2026-01-01T00:00:00Z","end_utc":"2026-02-01T00:00:00Z"}
    manifest["artifacts"].append(sealed)
    forbidden = source / sealed["path"]
    mixed = tmp_path / "EUR_USD.H1.json"
    original = Path.open
    opened = []
    def guarded(path,*args,**kwargs):
        assert path not in (forbidden,mixed)
        opened.append(str(path))
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,"open",guarded)
    receipt = module.certify_development_partition_slice(development_plan(source,manifest),tmp_path/"output")
    assert receipt["certified_development_only"] and receipt["total_records_verified"]==2
    assert receipt["holdout_files_opened"]==receipt["holdout_hashes_computed"]==receipt["mixed_H1_files_opened"]==0
    assert receipt["market_calls"]==0 and not receipt["monthly_scout_admitted"]
    quotes = json.loads(Path(receipt["monthly_quotes_path"]).read_text())
    assert len(quotes["rows"])==1 and quotes["rows"][0]["financing"] is None
    assert quotes["rows"][0]["quote_available_at_utc"]=="2024-01-02T00:10:00+00:00"
    assert not forbidden.exists() and not mixed.exists()


def test_development_rechecks_all_entries_before_any_price_read(tmp_path, monkeypatch):
    source,manifest = development_fixture(tmp_path)
    plan = development_plan(source,manifest)
    bad = {**plan["partitions"][0],"path":str(source/"partitions/EUR_USD/2026-01.jsonl.gz")}
    plan["partitions"].append(bad);repin_plan(plan)
    def no_open(*args,**kwargs):raise AssertionError("price file opened before complete boundary validation")
    monkeypatch.setattr(Path,"open",no_open)
    with pytest.raises(ValueError,match="DEVELOPMENT_SLICE_ENTRY_INVALID"):
        module.certify_development_partition_slice(plan,tmp_path/"output")
    assert not (tmp_path/"output").exists()


def test_development_refuses_crossing_hash_change_duplicate_and_incomplete(tmp_path):
    source,manifest = development_fixture(tmp_path)
    with pytest.raises(ValueError,match="BOUNDARY_INVALID"):
        module.plan_development_partition_slice(manifest,source,pairs=["EUR_USD"],start_utc="2024-01-01T00:00:00Z",
            end_utc="2026-02-01T00:00:00Z",holdout_start_utc="2026-01-01T00:00:00Z")
    duplicate = copy.deepcopy(manifest);duplicate["artifacts"] *= 2
    with pytest.raises(ValueError,match="DUPLICATE") :development_plan(source,duplicate)
    with pytest.raises(ValueError,match="COVERAGE_INCOMPLETE"):development_plan(source,{"artifacts":[]})
    plan = development_plan(source,manifest)
    with Path(plan["partitions"][0]["path"]).open("ab") as stream:stream.write(b"changed")
    with pytest.raises(ValueError,match="HASH_CHANGED"):
        module.certify_development_partition_slice(plan,tmp_path/"changed")
    assert not (tmp_path/"changed/DEVELOPMENT_ONLY_MANIFEST.json").exists()


def test_development_preserves_open_gap_and_existing_weekend_rule(tmp_path):
    source,manifest = development_fixture(tmp_path,["2024-01-05T21:55:00Z","2024-01-07T22:00:00Z","2024-01-07T22:10:00Z"])
    receipt = module.certify_development_partition_slice(development_plan(source,manifest),tmp_path/"output")
    assert receipt["unexpected_gaps_preserved"]==1
    assert receipt["total_records_verified"]==3  # no interpolation
    assert receipt["partitions"][0]["maximum_gap_minutes"]==2885


def test_development_refuses_count_change_and_output_overwrite(tmp_path):
    source,manifest = development_fixture(tmp_path)
    plan = development_plan(source,manifest)
    bad = copy.deepcopy(plan);bad["partitions"][0]["records"]=3;repin_plan(bad)
    with pytest.raises(ValueError,match="COUNT_OR_HASH_CHANGED"):
        module.certify_development_partition_slice(bad,tmp_path/"bad")
    output = tmp_path/"valid"
    module.certify_development_partition_slice(plan,output)
    with pytest.raises(ValueError,match="OUTPUT_EXISTS"):
        module.certify_development_partition_slice(plan,output)
    with pytest.raises(ValueError,match="IMMUTABLE_SOURCE_OUTPUT_OVERLAP"):
        module.certify_development_partition_slice(plan,source/"new")


def test_development_financing_retains_asymmetry_and_does_not_double_days():
    table = {"timestamp":"2025-10-08T21:00:00Z","divisionId":1,"tradingGroupId":1,
        "financingRates":[{"instrument":"EUR/USD","currency":"USD","units":100000,"days":3,
            "longCharge":"-30.12","shortCharge":"8.21","longRate":"-0.09","shortRate":"0.025"}]}
    result = module.validate_development_financing_table(table,day="2025-10-08",pairs=["EUR_USD"],holdout_start_utc="2026-01-01T00:00:00Z")
    assert result["rows"][0]["longCharge"]==-30.12 and result["rows"][0]["shortCharge"]==8.21
    assert result["rows"][0]["settlement_days"]==3 and result["rows"][0]["charges_already_daily"]
    assert not result["forward_contract_complete"] and not result["account_specific_execution_admitted"]
    for change,code in (({"timestamp":"2026-10-08T21:00:00Z"},"DATE_OR_DIVISION"),
                        ({"divisionId":2},"DATE_OR_DIVISION"),({"financingRates":[]},"PAIR_COVERAGE")):
        with pytest.raises(ValueError,match=code):
            module.validate_development_financing_table({**table,**change},day="2025-10-08",pairs=["EUR_USD"],holdout_start_utc="2026-01-01T00:00:00Z")
    invalid = copy.deepcopy(table);invalid["financingRates"][0]["longRate"]="NaN"
    with pytest.raises(ValueError,match="VALUES_INVALID"):
        module.validate_development_financing_table(invalid,day="2025-10-08",pairs=["EUR_USD"],holdout_start_utc="2026-01-01T00:00:00Z")


@pytest.mark.parametrize("defect,code",[("nonfinite","QUOTE_GEOMETRY"),("duplicate","NOT_CHRONOLOGICAL"),("out_of_bounds","ROW_OUTSIDE")])
def test_development_invalid_rows_fail_with_safe_codes(tmp_path,defect,code):
    source,manifest = development_fixture(tmp_path)
    path=source/manifest["artifacts"][0]["path"]
    with gzip.open(path,"rt") as stream:rows=[json.loads(line) for line in stream]
    if defect=="nonfinite":rows[0]["bid"]["o"]="NaN"
    elif defect=="duplicate":rows[1]["timestamp"]=rows[0]["timestamp"]
    else:rows[0]["timestamp"]="2026-01-02T00:00:00Z"
    with gzip.open(path,"wt") as stream:
        for row in rows:stream.write(json.dumps(row)+"\n")
    manifest["artifacts"][0]["sha256"]=hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError,match=code):
        module.certify_development_partition_slice(development_plan(source,manifest),tmp_path/"output")
    assert not (tmp_path/"output/DEVELOPMENT_ONLY_MANIFEST.json").exists()


def test_multi_regime_gate_does_not_read_credentials_or_freeze_without_data(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "ROOT", tmp_path / "runtime")
    monkeypatch.setattr(module, "PRACTICE_INBOX", tmp_path / "practice")
    monkeypatch.setattr(module, "M5_ROOT", tmp_path / "m5")
    monkeypatch.setattr(module, "STATE", tmp_path / "state.json")
    monkeypatch.setattr(module, "REPORT", tmp_path / "report.md")
    monkeypatch.setattr(module, "COVERAGE_STATE", tmp_path / "coverage.json")
    monkeypatch.setattr(module, "COVERAGE_REPORT", tmp_path / "coverage.md")
    monkeypatch.setattr(module, "MARKET_V2_STATE", tmp_path / "missing_m5_state.json")
    state = module.execute()
    assert state["frozen"] is False
    assert state["status"] == "HUMAN_PRACTICE_DATA_ACQUISITION_REQUIRED"
    assert state["safety"]["credentials_read"] is False
    assert state["safety"]["practice_orders"] is False


def test_pair_coverage_classifies_missing_intended_pair(tmp_path, monkeypatch):
    m5_state = tmp_path / "m5_state.json"
    m5_state.write_text(
        '{"quality_reconciliation":{"coverage":{"EUR_USD":0.99}},"eligible_pairs":["EUR_USD"]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "PRACTICE_INBOX", tmp_path / "practice")
    monkeypatch.setattr(module, "MARKET_V2_STATE", m5_state)
    state = module.build_pair_coverage_matrix()
    assert state["intended_pair_count"] == 1
    assert state["excluded_pair_count"] == 1
    assert state["rows"][0]["state"] == "INELIGIBLE_INSUFFICIENT_HISTORY"
