import json

import pytest

from automation.forex_engine.forex_external_strategy_evidence_inventory_v1 import SOURCE_FILES, acquisition_proposal, build_inventory, write_outputs


def make_sources(root):
    v2 = {"status": "NOT_CREATED_NO_NEW_USABLE_INFORMATION", "records": 0, "frozen": False}
    v3 = {"status": "FROZEN_VALID", "frozen": True, "record_count": 35755, "aggregate_hash": "a" * 64, "official_artifacts": {"artifacts": [{"path": "CFTC_2024.zip", "bytes": 2, "sha256": "b" * 64, "source_id": "CFTC_POSITIONING_HISTORY", "validation": "PASS"}]}}
    institutional = {"status": "FROZEN_VALID", "frozen": True, "record_count": 4121, "aggregate_hash": "c" * 64, "normalized_artifacts": [{"path": "FRED_DFF.json", "records": 10, "sha256": "d" * 64}]}
    values = [json.dumps(v2), "v2 report", json.dumps(v3), "point-in-time report", json.dumps(institutional), "institutional report"]
    for name, value in zip(SOURCE_FILES, values):
        (root / name).write_text(value, encoding="utf-8")


def test_inventory_requires_all_six_exact_sources(tmp_path):
    make_sources(tmp_path)
    assert len(build_inventory(tmp_path)["sources"]) == 6
    (tmp_path / SOURCE_FILES[0]).unlink()
    with pytest.raises(FileNotFoundError):
        build_inventory(tmp_path)


def test_inventory_distinguishes_reported_from_directly_verified(tmp_path):
    make_sources(tmp_path)
    result = build_inventory(tmp_path)
    assert result["status"] == "LOCAL_POINT_IN_TIME_EVIDENCE_SUFFICIENT_FOR_PREREGISTRATION"
    assert result["corpora"]["external_v3"]["direct_record_inspection"] == "NOT_AUTHORIZED_IN_THIS_PACKET"
    assert result["evidence_classes"]["historical_swap_financing"]["availability"] == "NO_EVIDENCE"
    assert result["evidence_classes"]["currency_positioning"]["availability"] == "REPORTED_FROZEN_LOCAL_EVIDENCE"


def test_invalid_corpus_fails_closed(tmp_path):
    make_sources(tmp_path)
    path = tmp_path / SOURCE_FILES[2]
    value = json.loads(path.read_text())
    value["status"] = "FAILED"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError):
        build_inventory(tmp_path)


def test_proposal_never_authorizes_acquisition(tmp_path):
    make_sources(tmp_path)
    proposal = acquisition_proposal(build_inventory(tmp_path))
    assert proposal["acquisition_executed"] is False
    assert "SEPARATE_HUMAN_OWNER_AUTHORIZATION" in proposal["authority_required"]


def test_outputs_are_deterministic_and_safe(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    make_sources(source)
    inventory = build_inventory(source)
    for name in ("one", "two"):
        root = tmp_path / name
        root.mkdir()
        write_outputs(inventory, root / "state.json", root / "report.md", root / "proposal.json", root / "runtime")
    for relative in ("state.json", "report.md", "proposal.json", "runtime/AIOS_FOREX_EXTERNAL_STRATEGY_EVIDENCE_MANIFEST.json", "runtime/AIOS_FOREX_EXTERNAL_STRATEGY_EVIDENCE_RECEIPT.json"):
        assert (tmp_path / "one" / relative).read_bytes() == (tmp_path / "two" / relative).read_bytes()
    receipt = json.loads((tmp_path / "one/runtime/AIOS_FOREX_EXTERNAL_STRATEGY_EVIDENCE_RECEIPT.json").read_text())
    assert all(value == "PASS" for value in receipt["acceptance"].values())
    assert not any(receipt["safety"].values())
