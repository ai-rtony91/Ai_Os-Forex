from automation.forex_engine import forex_external_information_corpus_v3 as module


def test_record_validator_rejects_missing_point_in_time_fields():
    quality = module.validate_records([{"source_id": "x"}])
    assert quality["pass"] is False
    assert quality["violations"][0]["reason"] == "MISSING_REQUIRED_FIELDS"


def test_record_validator_accepts_conservative_availability():
    record = {"source_id": "fred:DFF", "series_id": "DFF", "observation_time_utc": "2024-01-01T00:00:00+00:00", "publication_time_utc": "2024-01-02T00:00:00+00:00", "strategy_available_time_utc": "2024-01-02T00:00:00+00:00", "vintage_or_revision_status": "conservative", "retrieval_time_utc": "2026-08-30T00:00:00+00:00", "raw_artifact_hash": "abc", "normalized_record_hash": "def"}
    assert module.validate_records([record])["pass"] is True


def test_official_artifact_validator_rejects_missing_inbox(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "HUMAN_INBOX", tmp_path / "missing")
    state = module.validate_official_artifacts()
    assert state["status"] == "FAIL"
    assert state["artifact_count"] == 0
    assert state["failures"]
