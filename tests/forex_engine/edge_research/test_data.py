"""Synthetic local tests for the PKT-045 paired-tick corpus only."""

from datetime import datetime, timezone
import json
import lzma
from pathlib import Path
import struct
import subprocess

import pytest

from automation.forex_engine.edge_research import data
from automation.forex_engine.edge_research import dukascopy_acquisition as acquisition
from automation.forex_engine.edge_research.dukascopy_bi5 import daily_tick_key


UTC = timezone.utc
TICK_RECORD = struct.Struct(">IIIff")
START = datetime(2024, 1, 1, tzinfo=UTC)
END = datetime(2024, 1, 2, tzinfo=UTC)


def tick_payload():
    raw = b"".join((
        TICK_RECORD.pack(0, 100_002, 100_000, 1.0, 1.0),
        TICK_RECORD.pack(60_000, 100_006, 100_004, 1.0, 1.0),
        TICK_RECORD.pack(240_000, 100_004, 100_002, 1.0, 1.0),
        TICK_RECORD.pack(300_000, 100_010, 100_008, 1.0, 1.0),
    ))
    return lzma.compress(raw, format=lzma.FORMAT_ALONE)


def inventory_for(payload):
    key = daily_tick_key("EUR_USD", START.date())
    source = acquisition.SourceObject(
        pair="EUR_USD", trading_day="2024-01-01", side="BID_ASK", key=key,
        size=len(payload), etag='"etag"', last_modified="2024-01-01T00:00:00+00:00",
        data_type="TICK", storage_class="STANDARD",
    )
    return acquisition.PairedTickInventory(
        start="2024-01-01T00:00:00Z", end="2024-01-02T00:00:00Z", pair_count=1,
        calendar_date_count=1, expected_tick_object_count=1, available_tick_object_count=1,
        total_listed_bytes=len(payload), missing_expected_object_count=0,
        non_target_object_count=0, unexpected_object_count=0, objects=(source,),
        missing_expected_keys=(), non_target_keys=(), unexpected_keys=(),
        per_pair={"EUR_USD": {"PAIR": "EUR_USD", "STATUS": "INVENTORY_COMPLETE"}},
    )


def acquisition_gate(inventory):
    requirement = acquisition.SourceSemanticsRequirement(
        strategy_specification_id="EXP_FOREX_045_DUKASCOPY_PAIRED_TICK_MID_AB_V1",
        required_pair_count=1, required_price_sides=("BID", "ASK"),
        midpoint_semantics="PAIRED_TICK_MIDPOINT_THEN_M5_AGGREGATION",
        timestamp_granularity="TICK", candle_construction="PAIRED_TICKS_THEN_M5",
        activity_semantics="NOT_REQUIRED", preregistration_status="FROZEN",
    )
    semantics = acquisition.evaluate_paired_tick_preacquisition_gate(
        requirement=requirement, mapped_pair_count=1, local_tick_proof_id="a" * 64,
        local_tick_proof_passed=True,
    )
    pricing = acquisition.CostBasis(.005, .0004, .0004, .09, "official", "2026-09-08T00:00:00Z", "NONE")
    cost = acquisition.build_paired_tick_cost_gate(
        inventory=inventory, semantics_gate=semantics, mapped_pair_count=1,
        total_list_requests_actual=1, prior_spend_estimate_usd=.2, pricing=pricing,
        retry_and_uncertainty_reserve_usd=.01,
    )
    return acquisition.authorize_paired_tick_acquisition(
        preacquisition_gate=semantics, inventory=inventory, cost_gate=cost,
    ), cost


def acquire_synthetic(tmp_path, payload):
    inventory = inventory_for(payload)
    gate, cost = acquisition_gate(inventory)

    def fake_run(command, **_kwargs):
        key = command[command.index("--key") + 1]
        destination = Path(command[command.index(key) + 1])
        destination.write_bytes(payload)
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps({"ContentLength": len(payload), "ETag": '"etag"'}), stderr="",
        )

    client = acquisition.AwsRequesterPaysClient(runner=fake_run)
    client.executable = Path(__file__)
    root = tmp_path / "stage1"
    result = acquisition.acquire_paired_tick_inventory(
        inventory=inventory, acquisition_gate=gate, cost_gate=cost,
        raw_root=root / "raw_ticks", receipt_root=root / "receipts",
        checkpoint_path=root / "checkpoints" / "acquisition.json", output_root=root, client=client,
    )
    assert result["complete"] is True
    return root, inventory


def test_paired_tick_corpus_is_deterministic_and_keeps_midpoint_before_m5_aggregation(tmp_path):
    root, inventory = acquire_synthetic(tmp_path, tick_payload())
    kwargs = {
        "inventory": inventory,
        "raw_root": root / "raw_ticks",
        "receipt_root": root / "receipts",
        "corpus_root": root / "corpus_m5",
        "output_root": root,
        "source_metadata": {"EUR_USD": {"source_price_scale": 100_000}},
        "development_start": START,
        "development_end": END,
    }
    first = data.build_paired_tick_m5_corpus(**kwargs)
    second = data.build_paired_tick_m5_corpus(**kwargs)
    assert first == second
    assert first["source_type"] == "PAIRED_TICK"
    rows = data.read_paired_tick_m5_rows(corpus_root=root / "corpus_m5", pair="EUR_USD")
    assert len(rows) == 2
    assert rows[0]["mid"] == {"o": pytest.approx(1.00001), "h": pytest.approx(1.00005), "l": pytest.approx(1.00001), "c": pytest.approx(1.00003)}
    assert rows[0]["bid"]["h"] == pytest.approx(1.00004)
    assert rows[0]["ask"]["h"] == pytest.approx(1.00006)
    assert rows[0]["midpoint_method"] == data.PKT045_MIDPOINT_METHOD


def test_paired_tick_corpus_refuses_partial_pair_output(tmp_path):
    root, inventory = acquire_synthetic(tmp_path, tick_payload())
    partial = root / "corpus_m5" / "pairs" / "EURUSD.m5.jsonl.gz.part"
    partial.parent.mkdir(parents=True)
    partial.write_bytes(b"partial")
    with pytest.raises(data.Pkt045CorpusError, match="PARTIAL_OR_CONFLICTING"):
        data.build_paired_tick_m5_corpus(
            inventory=inventory, raw_root=root / "raw_ticks", receipt_root=root / "receipts",
            corpus_root=root / "corpus_m5", output_root=root,
            source_metadata={"EUR_USD": {"source_price_scale": 100_000}},
            development_start=START, development_end=END,
        )


def test_documented_dukascopy_fx_scale_mapping_is_source_specific_and_complete():
    metadata = data.dukascopy_fx_tick_metadata(("EUR_USD", "USD_JPY", "HKD_JPY"))
    assert metadata["EUR_USD"]["source_price_scale"] == 100_000
    assert metadata["EUR_USD"]["pip_size"] == pytest.approx(.0001)
    assert metadata["USD_JPY"]["source_price_scale"] == 1_000
    assert metadata["USD_JPY"]["pip_size"] == pytest.approx(.01)
    assert metadata["HKD_JPY"]["source_scale_rule_version"] == data.PKT045_DUKASCOPY_FX_SCALE_RULE_VERSION
