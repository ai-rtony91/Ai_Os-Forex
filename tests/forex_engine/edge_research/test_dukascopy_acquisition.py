"""No-network tests for the bounded PKT-044 Requester Pays adapter."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import threading
import time

import pytest

from automation.forex_engine.edge_research.dukascopy_acquisition import (
    AWS_BUCKET,
    AWS_EXECUTABLE,
    AWS_PROFILE,
    AWS_REGION,
    AwsRequesterPaysClient,
    CostBasis,
    DukascopyAcquisitionError,
    PairedTickInventory,
    SourceSemanticsCapability,
    SourceSemanticsRequirement,
    acquire_chunk,
    acquisition_chunks,
    acquire_paired_tick_inventory,
    authorize_paired_tick_acquisition,
    build_cost_gate,
    build_inventory,
    build_paired_tick_cost_gate,
    build_paired_tick_inventory,
    advance_inventory_checkpoints,
    advance_paired_tick_inventory_checkpoints,
    collect_inventory_from_aws,
    collect_paired_tick_inventory_from_aws,
    load_inventory_from_checkpoints,
    load_paired_tick_inventory_from_checkpoints,
    cost_gate_payload,
    evaluate_source_semantics,
    evaluate_paired_tick_preacquisition_gate,
    inventory_payload,
    month_prefixes,
    paired_tick_cost_gate_payload,
    paired_tick_inventory_list_request_count,
    paired_tick_inventory_payload,
    paired_tick_completed_raw_receipts,
    source_semantics_gate_payload,
    write_new_deterministic_json,
)
from automation.forex_engine.edge_research.dukascopy_bi5 import daily_candle_key, daily_tick_key


UTC = timezone.utc
START = datetime(2024, 1, 1, tzinfo=UTC)
END = datetime(2024, 1, 3, tzinfo=UTC)
REPO_ROOT = Path(__file__).resolve().parents[3]
FROZEN_SEMANTICS_RECEIPT = (
    REPO_ROOT
    / ".aios/staging/PKT_FOREX_044/dukascopy_acquisition_occ82_20260907"
    / "PKT044_DUKASCOPY_FROZEN_STRATEGY_SEMANTICS_GATE_V2.json"
)


def list_item(key, size=123):
    return {
        "Key": key, "Size": size, "ETag": '"etag"', "LastModified": "2024-01-01T00:00:00+00:00",
        "StorageClass": "STANDARD",
    }


def complete_listing(pairs=("EUR_USD",)):
    return complete_listing_for_range(START, END, pairs)


def complete_listing_for_range(start, end, pairs=("EUR_USD",)):
    result = {}
    boundary_days = (start.date(), (end - timedelta(days=1)).date())
    for pair, prefix in month_prefixes(pairs, start, end):
        _symbol, year, zero_month = prefix.strip("/").split("/")
        days = [day for day in boundary_days if day.year == int(year) and day.month == int(zero_month) + 1]
        result[(pair, prefix)] = [
            list_item(daily_candle_key(pair, day, side), 100 + day.day)
            for day in days
            for side in ("BID", "ASK")
        ]
    return result


def complete_tick_listing_for_range(start, end, pairs=("EUR_USD",)):
    result = {}
    dates = []
    current = start.date()
    while current < end.date():
        dates.append(current)
        current += timedelta(days=1)
    for pair, prefix in month_prefixes(pairs, start, end):
        _symbol, year, zero_month = prefix.strip("/").split("/")
        result[(pair, prefix)] = [
            list_item(daily_tick_key(pair, day), 100 + day.day)
            for day in dates
            if day.year == int(year) and day.month == int(zero_month) + 1
        ]
    return result


def paired_tick_semantics_gate(*, mapped_pair_count=1, proof=True):
    requirement = SourceSemanticsRequirement(
        strategy_specification_id="PKT045_TICK_MID_AB",
        required_pair_count=1,
        required_price_sides=("BID", "ASK"),
        midpoint_semantics="PAIRED_TICK_MIDPOINT_THEN_M5_AGGREGATION",
        timestamp_granularity="TICK",
        candle_construction="PAIRED_TICKS_THEN_M5",
        activity_semantics="NOT_REQUIRED",
        preregistration_status="FROZEN",
    )
    return evaluate_paired_tick_preacquisition_gate(
        requirement=requirement,
        mapped_pair_count=mapped_pair_count,
        local_tick_proof_id="b" * 64,
        local_tick_proof_passed=proof,
    )


def frozen_native_mid_requirement():
    return SourceSemanticsRequirement(
        strategy_specification_id="PKT044_FROZEN_A_B",
        required_pair_count=1,
        required_price_sides=("BID", "ASK", "MID"),
        midpoint_semantics="NATIVE_PROVIDER_MID_OHLC",
        timestamp_granularity="M5_OR_FINER",
        candle_construction="PROVIDER_NATIVE_MID",
        activity_semantics="NOT_REQUIRED",
        preregistration_status="FROZEN",
    )


def capability(*, sides=("BID", "ASK", "MID"), mapped_pair_count=1, native_mid=True,
               paired_ticks=False, paired_same_record=False, execution_coverage=True,
               granularities=("M5_OR_FINER",), constructions=("PROVIDER_NATIVE_MID",),
               native_mid_objects=2, paired_tick_objects=0):
    return SourceSemanticsCapability(
        source_id="SYNTHETIC_DUKASCOPY",
        evidence_id="SYNTHETIC_SOURCE_PROBE",
        mapped_pair_count=mapped_pair_count,
        available_price_sides=sides,
        timestamp_granularities=granularities,
        candle_constructions=constructions,
        native_mid_coverage_complete=native_mid,
        paired_tick_coverage_complete=paired_ticks,
        paired_tick_same_record=paired_same_record,
        execution_coverage_complete=execution_coverage,
        activity_semantics="NOT_REQUIRED",
        native_mid_object_count=native_mid_objects,
        paired_tick_object_count=paired_tick_objects,
    )


def eligible_semantics_gate():
    return evaluate_source_semantics(
        requirement=frozen_native_mid_requirement(), capability=capability()
    )


def test_month_prefixes_and_inventory_are_deterministic():
    listing = complete_listing()
    inventory = build_inventory(pairs=("EUR_USD",), start=START, end=END, listed_by_prefix=listing)
    assert inventory.calendar_date_count == 2
    assert inventory.total_object_count == 4
    assert inventory.bid_object_count == 2
    assert inventory.ask_object_count == 2
    assert inventory.total_listed_bytes == 406
    assert inventory.missing_expected_object_count == 0
    assert inventory.unexpected_object_count == 0
    assert inventory.per_pair["EUR_USD"]["STATUS"] == "INVENTORY_COMPLETE"
    assert inventory_payload(inventory) == inventory_payload(inventory)


def test_inventory_retains_missing_source_days_and_unexpected_objects():
    listing = complete_listing()
    prefix = next(iter(listing))
    listing[prefix] = listing[prefix][:-1] + [list_item("EURUSD/2024/00/01/not_a_candle.bi5", 10)]
    inventory = build_inventory(pairs=("EUR_USD",), start=START, end=END, listed_by_prefix=listing)
    assert inventory.missing_expected_object_count == 1
    assert inventory.unexpected_object_count == 1
    assert inventory.per_pair["EUR_USD"]["STATUS"] == "SOURCE_DATE_GAPS"


def test_inventory_keeps_available_ticks_out_of_a_complete_minute_candle_plan():
    listing = complete_listing()
    prefix = next(iter(listing))
    listing[prefix].append(list_item("EURUSD/2024/00/01_ticks.bi5", 50))
    inventory = build_inventory(pairs=("EUR_USD",), start=START, end=END, listed_by_prefix=listing)
    assert inventory.available_tick_object_count == 1
    assert inventory.fallback_tick_object_count == 0
    assert inventory.unexpected_object_count == 0


def test_inventory_uses_one_same_provider_tick_only_when_a_minute_side_is_missing():
    listing = complete_listing()
    prefix = next(iter(listing))
    listing[prefix] = [
        item for item in listing[prefix]
        if item["Key"] != daily_candle_key("EUR_USD", START.date(), "ASK")
    ]
    listing[prefix].append(list_item(daily_tick_key("EUR_USD", START.date()), 50))
    inventory = build_inventory(pairs=("EUR_USD",), start=START, end=END, listed_by_prefix=listing)
    assert inventory.missing_expected_object_count == 1
    assert inventory.unresolved_source_day_count == 0
    assert inventory.fallback_tick_object_count == 1
    assert inventory.total_object_count == 3
    planned = {entry.key for entry in inventory.objects}
    assert daily_tick_key("EUR_USD", START.date()) in planned
    assert daily_candle_key("EUR_USD", START.date(), "BID") not in planned
    assert inventory.per_pair["EUR_USD"]["STATUS"] == "INVENTORY_COMPLETE"


def test_inventory_records_monthly_aggregates_as_non_target_layout():
    listing = complete_listing()
    prefix = next(iter(listing))
    listing[prefix].append(list_item("EURUSD/2024/00/BID_candles_hour_1.bi5", 50))
    inventory = build_inventory(pairs=("EUR_USD",), start=START, end=END, listed_by_prefix=listing)
    assert inventory.non_target_object_count == 1
    assert inventory.unexpected_object_count == 0


def test_inventory_fails_on_duplicate_key_or_missing_prefix():
    listing = complete_listing()
    key = next(iter(listing))
    listing[key].append(listing[key][0])
    with pytest.raises(DukascopyAcquisitionError, match="DUPLICATE"):
        build_inventory(pairs=("EUR_USD",), start=START, end=END, listed_by_prefix=listing)
    with pytest.raises(DukascopyAcquisitionError, match="PREFIX_SET_INCOMPLETE"):
        build_inventory(pairs=("EUR_USD",), start=START, end=END, listed_by_prefix={})


def test_cost_gate_uses_no_free_transfer_allowance():
    inventory = build_inventory(pairs=("EUR_USD",), start=START, end=END, listed_by_prefix=complete_listing())
    pricing = CostBasis(
        list_per_1000_usd=.005, get_per_1000_usd=.0004, head_per_1000_usd=.0004,
        transfer_per_gb_usd=.09, price_source="official", retrieved_at_utc="2026-09-07T00:00:00Z",
        free_allowance_assumption="NONE",
    )
    gate = build_cost_gate(
        inventory=inventory, semantics_gate=eligible_semantics_gate(), total_list_requests_planned=1, total_get_requests_planned=4,
        total_head_requests_planned=0, prior_cost_usd=.01, pricing=pricing, safety_margin_usd=.10,
    )
    assert gate.cost_gate == "PASS"
    assert gate.transfer_cost_usd == pytest.approx(406 / 1_000_000_000 * .09)
    payload = cost_gate_payload(gate, pricing)
    assert payload["FREE_ALLOWANCE_ASSUMPTION"] == "NONE"
    assert payload["source_semantic_fit"] == "PASS"
    assert payload["source_acquisition_status"] == "ELIGIBLE"


def test_cost_gate_blocks_above_owner_limit():
    inventory = build_inventory(pairs=("EUR_USD",), start=START, end=END, listed_by_prefix=complete_listing())
    pricing = CostBasis(.005, .0004, .0004, .09, "official", "2026-09-07T00:00:00Z", "NONE")
    gate = build_cost_gate(
        inventory=inventory, semantics_gate=eligible_semantics_gate(), total_list_requests_planned=1, total_get_requests_planned=4,
        total_head_requests_planned=0, prior_cost_usd=.95, pricing=pricing, safety_margin_usd=.10,
    )
    assert gate.cost_gate == "FAIL"


def test_bid_ask_only_source_blocks_frozen_native_mid_before_cost_gate():
    requirement = frozen_native_mid_requirement()
    bid_ask_only = capability(
        sides=("BID", "ASK"), native_mid=False, native_mid_objects=0,
    )
    semantics = evaluate_source_semantics(requirement=requirement, capability=bid_ask_only)
    assert semantics.semantic_fit == "FAIL"
    assert semantics.acquisition_status == "BLOCKED"
    assert "NATIVE_MID_REQUIRED" in semantics.blockers
    assert "REQUIRED_PRICE_SIDE_MISSING_MID" in semantics.blockers

    inventory = build_inventory(pairs=("EUR_USD",), start=START, end=END, listed_by_prefix=complete_listing())
    pricing = CostBasis(.005, .0004, .0004, .09, "official", "2026-09-07T00:00:00Z", "NONE")
    with pytest.raises(DukascopyAcquisitionError, match="SOURCE_SEMANTICS_NOT_ELIGIBLE"):
        build_cost_gate(
            inventory=inventory, semantics_gate=semantics, total_list_requests_planned=1,
            total_get_requests_planned=4, total_head_requests_planned=0, prior_cost_usd=.01,
            pricing=pricing, safety_margin_usd=.10,
        )


def test_saved_pkt044_semantics_evidence_blocks_bid_ask_only_corpus_before_costing():
    assert FROZEN_SEMANTICS_RECEIPT.is_file(), f"SAVED_SEMANTICS_RECEIPT_MISSING:{FROZEN_SEMANTICS_RECEIPT}"
    saved = json.loads(FROZEN_SEMANTICS_RECEIPT.read_text(encoding="utf-8"))
    semantics = evaluate_source_semantics(
        requirement=SourceSemanticsRequirement(
            strategy_specification_id="PKT044_FROZEN_A_B",
            required_pair_count=58,
            required_price_sides=("BID", "ASK", "MID"),
            midpoint_semantics="NATIVE_PROVIDER_MID_OHLC",
            timestamp_granularity="M5_OR_FINER",
            candle_construction="PROVIDER_NATIVE_MID_OHLC",
            activity_semantics="NOT_REQUIRED",
            preregistration_status="FROZEN",
        ),
        capability=capability(
            sides=("BID", "ASK"), mapped_pair_count=58, native_mid=False,
            granularities=("M5_OR_FINER", "TICK"),
            constructions=("BID_ASK_MINUTE_TO_M5", "PAIRED_TICKS_THEN_M5"),
            native_mid_objects=saved["SOURCE_OBJECT_SEMANTICS"]["source_midpoint_objects_found"],
        ),
    )
    assert saved["SOURCE_OBJECT_SEMANTICS"]["midpoint_derivation_authority"] == "NONE"
    assert saved["SOURCE_OBJECT_SEMANTICS"]["source_midpoint_objects_found"] == 0
    assert semantics.semantic_fit == "FAIL"
    assert "NATIVE_MID_REQUIRED" in semantics.blockers


def test_paired_tick_mid_is_a_new_specification_and_cannot_acquire_before_preregistration():
    requirement = SourceSemanticsRequirement(
        strategy_specification_id="PROPOSED_DUKASCOPY_TICK_MID_SUCCESSOR",
        required_pair_count=1,
        required_price_sides=("BID", "ASK"),
        midpoint_semantics="PAIRED_TICK_MIDPOINT_THEN_M5_AGGREGATION",
        timestamp_granularity="TICK",
        candle_construction="PAIRED_TICKS_THEN_M5",
        activity_semantics="NOT_REQUIRED",
        preregistration_status="PROPOSED",
    )
    paired_ticks = capability(
        sides=("BID", "ASK"), native_mid=False, paired_ticks=True, paired_same_record=True,
        granularities=("TICK",), constructions=("PAIRED_TICKS_THEN_M5",),
        native_mid_objects=0, paired_tick_objects=2,
    )
    semantics = evaluate_source_semantics(requirement=requirement, capability=paired_ticks)
    assert semantics.semantic_fit == "PASS"
    assert semantics.acquisition_status == "AWAITING_PREREGISTRATION"
    assert semantics.requires_new_fingerprint is True

    inventory = build_inventory(pairs=("EUR_USD",), start=START, end=END, listed_by_prefix=complete_listing())
    pricing = CostBasis(.005, .0004, .0004, .09, "official", "2026-09-07T00:00:00Z", "NONE")
    with pytest.raises(DukascopyAcquisitionError, match="SOURCE_SEMANTICS_NOT_ELIGIBLE"):
        build_cost_gate(
            inventory=inventory, semantics_gate=semantics, total_list_requests_planned=1,
            total_get_requests_planned=4, total_head_requests_planned=0, prior_cost_usd=.01,
            pricing=pricing, safety_margin_usd=.10,
        )


@pytest.mark.parametrize(
    "source,expected",
    [
        (capability(mapped_pair_count=0), "PAIR_COVERAGE_INCOMPLETE"),
        (capability(sides=("BID", "MID")), "REQUIRED_PRICE_SIDE_MISSING_ASK"),
        (capability(execution_coverage=False), "EXECUTION_PRICE_COVERAGE_UNPROVEN"),
    ],
)
def test_semantics_gate_blocks_missing_pair_side_or_execution_evidence(source, expected):
    result = evaluate_source_semantics(requirement=frozen_native_mid_requirement(), capability=source)
    assert result.semantic_fit == "FAIL"
    assert result.acquisition_status == "BLOCKED"
    assert expected in result.blockers


def test_semantics_gate_payload_is_deterministic_and_contains_no_outcomes():
    requirement = frozen_native_mid_requirement()
    source = capability()
    result = evaluate_source_semantics(requirement=requirement, capability=source)
    first = source_semantics_gate_payload(result, requirement=requirement, capability=source)
    second = source_semantics_gate_payload(result, requirement=requirement, capability=source)
    assert first == second
    assert first["RESULT"]["semantic_fit"] == "PASS"
    assert "profit" not in str(first).lower()
    assert "return" not in str(first).lower()


def test_write_once_is_idempotent_and_rejects_overwrite(tmp_path):
    path = tmp_path / "inventory.json"
    assert write_new_deterministic_json(path, {"b": 2, "a": 1}) == write_new_deterministic_json(path, {"a": 1, "b": 2})
    with pytest.raises(DukascopyAcquisitionError, match="ALREADY_EXISTS_DIFFERENT"):
        write_new_deterministic_json(path, {"a": 2})
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1, "b": 2}


def test_requester_pays_command_is_bounded_and_no_write_operation():
    recorded = []
    def fake_run(command, **kwargs):
        recorded.append(command)
        return subprocess.CompletedProcess(command, 0, stdout='{"Contents": [], "IsTruncated": false}', stderr="")

    client = AwsRequesterPaysClient(runner=fake_run)
    # Avoid host-machine filesystem dependence in this pure command test.
    client.executable = Path(__file__)
    client.list_prefix("EURUSD/2024/00/")
    command = recorded[0]
    assert command[:4] == [str(client.executable), "s3api", "list-objects-v2", "--bucket"]
    assert AWS_BUCKET in command and AWS_PROFILE in command and AWS_REGION in command
    assert "--request-payer" in command and "requester" in command
    assert "put-object" not in command and "sync" not in command and "cp" not in command


def test_exact_sync_is_scoped_to_one_prefix_and_explicit_source_keys(tmp_path):
    recorded = []
    def fake_run(command, **kwargs):
        recorded.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    client = AwsRequesterPaysClient(runner=fake_run)
    client.executable = Path(__file__)
    destination = tmp_path / "raw/EURUSD/2024/00"
    client.sync_exact_objects(
        prefix="EURUSD/2024/00/", destination=destination,
        include_patterns=("01/BID_candles_min_1.bi5", "01/ASK_candles_min_1.bi5"), output_root=tmp_path,
    )
    command = recorded[0]
    assert command[:4] == [str(client.executable), "s3", "sync", "s3://cfg-public-proper-wallaby/EURUSD/2024/00/"]
    assert "--request-payer" in command and "requester" in command
    assert "--exclude" in command and "*" in command
    assert command.count("--include") == 2
    assert "--delete" not in command and "s3api" not in command
    assert client.request_counts["sync"] == 1


def test_chunk_acquisition_is_idempotent_and_only_accepts_inventoried_objects(tmp_path):
    inventory = build_inventory(pairs=("EUR_USD",), start=START, end=END, listed_by_prefix=complete_listing())
    chunk = acquisition_chunks(inventory)[0]
    expected_sizes = {source.key[len(chunk.prefix):]: source.size for source in chunk.objects}
    calls = []
    def fake_run(command, **kwargs):
        calls.append(command)
        destination = Path(command[4])
        for index, token in enumerate(command):
            if token == "--include":
                relative = command[index + 1]
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"x" * expected_sizes[relative])
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    client = AwsRequesterPaysClient(runner=fake_run)
    client.executable = Path(__file__)
    raw_root = tmp_path / "raw"
    receipt_root = tmp_path / "receipts"
    first = acquire_chunk(
        chunk=chunk, raw_root=raw_root, receipt_root=receipt_root, output_root=tmp_path, client=client,
    )
    second = acquire_chunk(
        chunk=chunk, raw_root=raw_root, receipt_root=receipt_root, output_root=tmp_path, client=client,
    )
    assert first == second
    assert first["STATUS"] == "COMPLETE"
    assert len(first["RAW_OBJECTS"]) == 4
    assert len(calls) == 1
    assert client.request_counts["sync"] == 1


def test_chunk_grouping_keeps_explicit_keys_and_reduces_cli_startups():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 3, 1, tzinfo=UTC)
    inventory = build_inventory(pairs=("EUR_USD",), start=start, end=end, listed_by_prefix=complete_listing_for_range(start, end))
    monthly = acquisition_chunks(inventory)
    grouped = acquisition_chunks(inventory, months_per_chunk=6)
    assert len(monthly) == 2
    assert len(grouped) == 1
    assert grouped[0].prefix == "EURUSD/2024/"
    assert grouped[0].chunk_id == "EURUSD_2024_00_01"
    assert {source.key for source in grouped[0].objects} == {source.key for chunk in monthly for source in chunk.objects}


def test_collect_inventory_counts_only_constrained_list_requests_and_resumes(tmp_path):
    def fake_run(command, **kwargs):
        prefix = command[command.index("--prefix") + 1]
        key = prefix + "01/BID_candles_min_1.bi5"
        if key.endswith("/01/BID_candles_min_1.bi5"):
            payload = {"Contents": [list_item(key)], "IsTruncated": False}
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

    client = AwsRequesterPaysClient(runner=fake_run)
    client.executable = Path(__file__)
    inventory, request_count = collect_inventory_from_aws(
        pairs=("EUR_USD",), start=START, end=END, client=client, checkpoint_root=tmp_path
    )
    assert inventory.missing_expected_object_count == 3
    assert request_count == 1
    assert client.request_counts == {"list": 1, "get": 0, "sync": 0}
    resumed, resumed_request_count = collect_inventory_from_aws(
        pairs=("EUR_USD",), start=START, end=END, client=client, checkpoint_root=tmp_path
    )
    assert resumed == inventory
    assert resumed_request_count == 0
    assert client.request_counts == {"list": 1, "get": 0, "sync": 0}


def test_chunked_checkpoint_collection_never_reissues_completed_prefixes(tmp_path):
    calls = []
    def fake_run(command, **kwargs):
        calls.append(command)
        prefix = command[command.index("--prefix") + 1]
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps({"Contents": [list_item(prefix + "01/BID_candles_min_1.bi5")], "IsTruncated": False}), stderr=""
        )
    client = AwsRequesterPaysClient(runner=fake_run)
    client.executable = Path(__file__)
    progress = advance_inventory_checkpoints(
        pairs=("EUR_USD", "USD_JPY"), start=START, end=END,
        checkpoint_root=tmp_path, client=client, max_new_prefixes=1,
    )
    assert progress == {"complete": False, "completed_prefixes": 1, "total_prefixes": 2, "new_prefixes": 1, "new_list_requests": 1}
    resumed = advance_inventory_checkpoints(
        pairs=("EUR_USD", "USD_JPY"), start=START, end=END,
        checkpoint_root=tmp_path, client=client, max_new_prefixes=1,
    )
    assert resumed == {"complete": True, "completed_prefixes": 2, "total_prefixes": 2, "new_prefixes": 1, "new_list_requests": 1}
    assert len(calls) == 2
    inventory = load_inventory_from_checkpoints(
        pairs=("EUR_USD", "USD_JPY"), start=START, end=END, checkpoint_root=tmp_path
    )
    assert inventory.missing_expected_object_count == 6


def test_client_rejects_unapproved_source_scope():
    with pytest.raises(DukascopyAcquisitionError, match="SOURCE_SCOPE"):
        AwsRequesterPaysClient(bucket="another-bucket")


def test_paired_tick_inventory_uses_only_ticks_and_retains_missing_days():
    listing = complete_tick_listing_for_range(START, END)
    prefix = next(iter(listing))
    listing[prefix].append(list_item(daily_candle_key("EUR_USD", START.date(), "BID"), 77))
    listing[prefix] = [
        item for item in listing[prefix]
        if item["Key"] != daily_tick_key("EUR_USD", (END - timedelta(days=1)).date())
    ]
    inventory = build_paired_tick_inventory(
        pairs=("EUR_USD",), start=START, end=END, listed_by_prefix=listing,
    )
    assert inventory.expected_tick_object_count == 2
    assert inventory.available_tick_object_count == 1
    assert inventory.missing_expected_object_count == 1
    assert inventory.non_target_object_count == 1
    assert all(item.data_type == "TICK" and item.side == "BID_ASK" for item in inventory.objects)
    assert inventory.per_pair["EUR_USD"]["STATUS"] == "SOURCE_DATE_GAPS"
    payload = paired_tick_inventory_payload(inventory)
    assert payload["INVENTORY_STATUS"] == "VERIFIED_EXACT_TICK_LISTING"
    assert payload["CORPUS_CERTIFICATION_STATUS"] == "NOT_RUN"


def test_paired_tick_inventory_rejects_duplicate_tick_keys_and_unexpected_prefixes():
    listing = complete_tick_listing_for_range(START, END)
    prefix = next(iter(listing))
    listing[prefix].append(listing[prefix][0])
    with pytest.raises(DukascopyAcquisitionError, match="DUPLICATE"):
        build_paired_tick_inventory(pairs=("EUR_USD",), start=START, end=END, listed_by_prefix=listing)
    with pytest.raises(DukascopyAcquisitionError, match="PREFIX_SET_INCOMPLETE"):
        build_paired_tick_inventory(pairs=("EUR_USD",), start=START, end=END, listed_by_prefix={})


def test_paired_tick_listing_checkpoint_resumes_without_reissuing_completed_prefixes(tmp_path):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        prefix = command[command.index("--prefix") + 1]
        payload = {"Contents": [list_item(prefix + "01_ticks.bi5")], "IsTruncated": False}
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

    client = AwsRequesterPaysClient(runner=fake_run)
    client.executable = Path(__file__)
    first = advance_paired_tick_inventory_checkpoints(
        pairs=("EUR_USD",), start=START, end=END, checkpoint_root=tmp_path,
        client=client, max_new_prefixes=1, max_pages_per_prefix=1,
    )
    assert first["complete"] is True
    assert first["new_list_requests"] == 1
    second = advance_paired_tick_inventory_checkpoints(
        pairs=("EUR_USD",), start=START, end=END, checkpoint_root=tmp_path,
        client=client, max_new_prefixes=1, max_pages_per_prefix=1,
    )
    assert second["new_list_requests"] == 0
    assert len(calls) == 1
    inventory = load_paired_tick_inventory_from_checkpoints(
        pairs=("EUR_USD",), start=START, end=END, checkpoint_root=tmp_path,
    )
    assert inventory.available_tick_object_count == 1
    assert inventory.missing_expected_object_count == 1
    assert paired_tick_inventory_list_request_count(
        pairs=("EUR_USD",), start=START, end=END, checkpoint_root=tmp_path,
    ) == 1


def test_paired_tick_listing_has_explicit_pagination_cap():
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command, 0,
            stdout=json.dumps({"Contents": [], "IsTruncated": True, "NextContinuationToken": "next"}),
            stderr="",
        )

    client = AwsRequesterPaysClient(runner=fake_run)
    client.executable = Path(__file__)
    with pytest.raises(DukascopyAcquisitionError, match="PAGE_LIMIT_EXCEEDED"):
        client.list_prefix("EURUSD/2024/00/", max_pages=1)
    assert client.request_counts["list"] == 1


def test_collect_paired_tick_inventory_builds_only_after_all_checkpoints(tmp_path):
    def fake_run(command, **kwargs):
        prefix = command[command.index("--prefix") + 1]
        payload = {"Contents": [list_item(prefix + "01_ticks.bi5")], "IsTruncated": False}
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

    client = AwsRequesterPaysClient(runner=fake_run)
    client.executable = Path(__file__)
    inventory, progress = collect_paired_tick_inventory_from_aws(
        pairs=("EUR_USD",), start=START, end=END, checkpoint_root=tmp_path,
        client=client, max_pages_per_prefix=1,
    )
    assert progress["complete"] is True
    assert inventory.available_tick_object_count == 1
    assert inventory.missing_expected_object_count == 1


def test_paired_tick_cost_gate_uses_exact_inventory_and_cumulative_spend():
    inventory = build_paired_tick_inventory(
        pairs=("EUR_USD",), start=START, end=END,
        listed_by_prefix=complete_tick_listing_for_range(START, END),
    )
    pricing = CostBasis(.005, .0004, .0004, .09, "official", "2026-09-07T00:00:00Z", "NONE")
    gate = build_paired_tick_cost_gate(
        inventory=inventory, semantics_gate=paired_tick_semantics_gate(), mapped_pair_count=1,
        total_list_requests_actual=1, prior_spend_estimate_usd=.22917987961,
        pricing=pricing, retry_and_uncertainty_reserve_usd=.01,
    )
    assert gate.cost_gate == "PASS"
    assert gate.total_get_requests_planned == inventory.available_tick_object_count
    assert gate.conservative_download_bytes == inventory.total_listed_bytes
    payload = paired_tick_cost_gate_payload(gate, pricing)
    assert payload["FREE_ALLOWANCE_ASSUMPTION"] == "NONE"
    assert payload["AUTOMATIC_GET_RETRIES"] == 0


def test_paired_tick_cost_gate_blocks_invalid_semantics_or_owner_limit():
    inventory = build_paired_tick_inventory(
        pairs=("EUR_USD",), start=START, end=END,
        listed_by_prefix=complete_tick_listing_for_range(START, END),
    )
    pricing = CostBasis(.005, .0004, .0004, .09, "official", "2026-09-07T00:00:00Z", "NONE")
    with pytest.raises(DukascopyAcquisitionError, match="SEMANTICS_FAILED"):
        build_paired_tick_cost_gate(
            inventory=inventory, semantics_gate=paired_tick_semantics_gate(proof=False), mapped_pair_count=1,
            total_list_requests_actual=1, prior_spend_estimate_usd=.2,
            pricing=pricing, retry_and_uncertainty_reserve_usd=.01,
        )
    blocked = build_paired_tick_cost_gate(
        inventory=inventory, semantics_gate=paired_tick_semantics_gate(), mapped_pair_count=1,
        total_list_requests_actual=1, prior_spend_estimate_usd=.99,
        pricing=pricing, retry_and_uncertainty_reserve_usd=.01,
    )
    assert blocked.cost_gate == "FAIL"


def test_paired_tick_cost_gate_requires_known_standard_storage_pricing():
    listing = complete_tick_listing_for_range(START, END)
    prefix = next(iter(listing))
    listing[prefix][0]["StorageClass"] = "GLACIER_IR"
    inventory = build_paired_tick_inventory(
        pairs=("EUR_USD",), start=START, end=END, listed_by_prefix=listing,
    )
    pricing = CostBasis(.005, .0004, .0004, .09, "official", "2026-09-07T00:00:00Z", "NONE")
    with pytest.raises(DukascopyAcquisitionError, match="STORAGE_CLASS_PRICING_REQUIRED"):
        build_paired_tick_cost_gate(
            inventory=inventory, semantics_gate=paired_tick_semantics_gate(), mapped_pair_count=1,
            total_list_requests_actual=1, prior_spend_estimate_usd=.2,
            pricing=pricing, retry_and_uncertainty_reserve_usd=.01,
        )


def test_paired_tick_post_inventory_authorization_requires_all_completed_gates():
    inventory = build_paired_tick_inventory(
        pairs=("EUR_USD",), start=START, end=END,
        listed_by_prefix=complete_tick_listing_for_range(START, END),
    )
    pricing = CostBasis(.005, .0004, .0004, .09, "official", "2026-09-08T00:00:00Z", "NONE")
    cost = build_paired_tick_cost_gate(
        inventory=inventory, semantics_gate=paired_tick_semantics_gate(), mapped_pair_count=1,
        total_list_requests_actual=1, prior_spend_estimate_usd=.2,
        pricing=pricing, retry_and_uncertainty_reserve_usd=.01,
    )
    authorized = authorize_paired_tick_acquisition(
        preacquisition_gate=paired_tick_semantics_gate(), inventory=inventory, cost_gate=cost,
    )
    assert authorized.acquisition_status == "ELIGIBLE_AFTER_FULL_COVERAGE_AND_COST_GATE"
    blocked = build_paired_tick_cost_gate(
        inventory=inventory, semantics_gate=paired_tick_semantics_gate(), mapped_pair_count=1,
        total_list_requests_actual=1, prior_spend_estimate_usd=.999,
        pricing=pricing, retry_and_uncertainty_reserve_usd=.01,
    )
    with pytest.raises(DukascopyAcquisitionError, match="COST_GATE"):
        authorize_paired_tick_acquisition(
            preacquisition_gate=paired_tick_semantics_gate(), inventory=inventory, cost_gate=blocked,
        )


def test_paired_tick_acquisition_receipts_resume_without_duplicate_gets(tmp_path):
    listing = complete_tick_listing_for_range(START, END)
    for items in listing.values():
        for item in items:
            item["Size"] = 7
    inventory = build_paired_tick_inventory(
        pairs=("EUR_USD",), start=START, end=END, listed_by_prefix=listing,
    )
    pricing = CostBasis(.005, .0004, .0004, .09, "official", "2026-09-08T00:00:00Z", "NONE")
    cost = build_paired_tick_cost_gate(
        inventory=inventory, semantics_gate=paired_tick_semantics_gate(), mapped_pair_count=1,
        total_list_requests_actual=1, prior_spend_estimate_usd=.2,
        pricing=pricing, retry_and_uncertainty_reserve_usd=.01,
    )
    gate = authorize_paired_tick_acquisition(
        preacquisition_gate=paired_tick_semantics_gate(), inventory=inventory, cost_gate=cost,
    )
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        assert command[2] == "get-object"
        key = command[command.index("--key") + 1]
        destination = Path(command[command.index(key) + 1])
        destination.write_bytes(b"x" * 7)
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps({"ContentLength": 7, "ETag": '"etag"'}), stderr="",
        )

    client = AwsRequesterPaysClient(runner=fake_run)
    client.executable = Path(__file__)
    kwargs = {
        "inventory": inventory,
        "acquisition_gate": gate,
        "cost_gate": cost,
        "raw_root": tmp_path / "raw_ticks",
        "receipt_root": tmp_path / "receipts",
        "checkpoint_path": tmp_path / "checkpoints" / "acquisition.json",
        "output_root": tmp_path,
        "client": client,
    }
    first = acquire_paired_tick_inventory(**kwargs, max_new_objects=1)
    assert first["complete"] is False
    assert first["completed_objects"] == 1
    second = acquire_paired_tick_inventory(**kwargs, max_new_objects=1)
    assert second["complete"] is True
    assert second["completed_objects"] == 2
    third = acquire_paired_tick_inventory(**kwargs)
    assert third["new_objects"] == 0
    assert len(calls) == 2
    assert len(paired_tick_completed_raw_receipts(
        inventory=inventory, raw_root=tmp_path / "raw_ticks", receipt_root=tmp_path / "receipts",
    )) == 2


def test_paired_tick_acquisition_two_gets_share_one_controller_without_duplicate_keys(tmp_path):
    listing = complete_tick_listing_for_range(START, END)
    for items in listing.values():
        for item in items:
            item["Size"] = 7
    inventory = build_paired_tick_inventory(
        pairs=("EUR_USD",), start=START, end=END, listed_by_prefix=listing,
    )
    pricing = CostBasis(.005, .0004, .0004, .09, "official", "2026-09-08T00:00:00Z", "NONE")
    cost = build_paired_tick_cost_gate(
        inventory=inventory, semantics_gate=paired_tick_semantics_gate(), mapped_pair_count=1,
        total_list_requests_actual=1, prior_spend_estimate_usd=.2,
        pricing=pricing, retry_and_uncertainty_reserve_usd=.01,
    )
    gate = authorize_paired_tick_acquisition(
        preacquisition_gate=paired_tick_semantics_gate(), inventory=inventory, cost_gate=cost,
    )
    active = 0
    peak = 0
    seen = []
    guard = threading.Lock()

    def fake_run(command, **_kwargs):
        nonlocal active, peak
        key = command[command.index("--key") + 1]
        destination = Path(command[command.index(key) + 1])
        with guard:
            active += 1
            peak = max(peak, active)
            seen.append(key)
        time.sleep(.02)
        destination.write_bytes(b"x" * 7)
        with guard:
            active -= 1
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps({"ContentLength": 7, "ETag": '"etag"'}), stderr="",
        )

    client = AwsRequesterPaysClient(runner=fake_run)
    client.executable = Path(__file__)
    result = acquire_paired_tick_inventory(
        inventory=inventory, acquisition_gate=gate, cost_gate=cost,
        raw_root=tmp_path / "raw_ticks", receipt_root=tmp_path / "receipts",
        checkpoint_path=tmp_path / "checkpoints" / "acquisition.json", output_root=tmp_path,
        client=client, max_concurrent_gets=2,
    )
    assert result["completed_objects"] == 2
    assert result["max_concurrent_gets"] == 2
    assert peak == 2
    assert len(seen) == len(set(seen)) == 2


def test_paired_tick_acquisition_conflicting_response_stops_without_certifying_raw_object(tmp_path):
    listing = complete_tick_listing_for_range(START, END)
    for items in listing.values():
        for item in items:
            item["Size"] = 7
    inventory = build_paired_tick_inventory(
        pairs=("EUR_USD",), start=START, end=END, listed_by_prefix=listing,
    )
    pricing = CostBasis(.005, .0004, .0004, .09, "official", "2026-09-08T00:00:00Z", "NONE")
    cost = build_paired_tick_cost_gate(
        inventory=inventory, semantics_gate=paired_tick_semantics_gate(), mapped_pair_count=1,
        total_list_requests_actual=1, prior_spend_estimate_usd=.2,
        pricing=pricing, retry_and_uncertainty_reserve_usd=.01,
    )
    gate = authorize_paired_tick_acquisition(
        preacquisition_gate=paired_tick_semantics_gate(), inventory=inventory, cost_gate=cost,
    )

    def fake_run(command, **_kwargs):
        key = command[command.index("--key") + 1]
        Path(command[command.index(key) + 1]).write_bytes(b"x" * 7)
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps({"ContentLength": 6, "ETag": '"etag"'}), stderr="",
        )

    client = AwsRequesterPaysClient(runner=fake_run)
    client.executable = Path(__file__)
    with pytest.raises(DukascopyAcquisitionError, match="SOURCE_OBJECT_CONFLICT"):
        acquire_paired_tick_inventory(
            inventory=inventory, acquisition_gate=gate, cost_gate=cost,
            raw_root=tmp_path / "raw_ticks", receipt_root=tmp_path / "receipts",
            checkpoint_path=tmp_path / "checkpoints" / "acquisition.json", output_root=tmp_path,
            client=client, max_new_objects=1,
        )
    with pytest.raises(DukascopyAcquisitionError, match="RAW_RECEIPT_SCHEMA_INVALID"):
        paired_tick_completed_raw_receipts(
            inventory=inventory, raw_root=tmp_path / "raw_ticks", receipt_root=tmp_path / "receipts",
        )
