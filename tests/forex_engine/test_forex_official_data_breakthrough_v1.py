from automation.forex_engine import forex_official_data_breakthrough_v1 as module


def test_source_matrix_freezes_required_families_and_four_routes():
    matrix = module.source_matrix()
    families = {item["family"] for item in matrix["requirements"]}
    assert "CENTRAL_BANK_POLICY_HISTORY" in families
    assert "CFTC_POSITIONING_HISTORY" in families
    assert "OFFICIAL_MACRO_RELEASE_SCHEDULES" in families
    assert all(len(item["routes"]) == 4 for item in matrix["requirements"])
    assert matrix["safety"]["credentials_required"] is False


def test_human_manifest_has_no_secret_or_private_account_requirement():
    requirement = module.asdict(module.requirements()[0])
    manifest = module.human_manifest([{"status": "SOURCE_UNAVAILABLE_AUTOMATED", "family": requirement["family"], "series_or_artifact": requirement["series_or_artifact"], "requirement": requirement}])
    assert manifest["status"] == "HUMAN_OFFICIAL_DATA_DOWNLOAD_REQUIRED"
    assert manifest["items"][0]["secret_required"] is False
    assert manifest["items"][0]["private_account_required"] is False
    assert "human_download_inbox" in manifest["items"][0]["expected_destination_relative_path"]


def test_normalized_records_carry_point_in_time_fields():
    requirement = module.requirements()[0]
    rows = module.normalize_csv(requirement, b"DATE,DFF\n2024-01-02,5.33\n", "abc")
    assert rows
    assert rows[0]["strategy_available_time_utc"] >= rows[0]["publication_time_utc"]
    assert rows[0]["raw_artifact_hash"] == "abc"
    assert rows[0]["normalized_record_hash"]
