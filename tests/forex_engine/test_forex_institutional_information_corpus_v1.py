from automation.forex_engine import forex_institutional_information_corpus_v1 as module


def test_validate_records_requires_point_in_time_fields():
    result = module.validate_records([{"source_id": "X"}])
    assert not result["pass"]
    assert result["violations"][0]["reason"] == "MISSING_REQUIRED_FIELDS"


def test_validate_records_blocks_duplicate_record_keys():
    record = {
        "source_id": "S",
        "series_id": "X",
        "observation_time_utc": "2024-01-01T00:00:00+00:00",
        "publication_time_utc": "2024-01-02T00:00:00+00:00",
        "strategy_available_time_utc": "2024-01-02T00:00:00+00:00",
        "vintage_or_revision_status": "FIRST_RELEASE",
        "retrieval_time_utc": "2026-08-30T00:00:00+00:00",
        "source_artifact_hash": "abc",
        "normalization_code_hash": "def",
    }
    result = module.validate_records([record, dict(record)])
    assert not result["pass"]
    assert any(item["reason"] == "DUPLICATE_RECORD_KEY" for item in result["violations"])
