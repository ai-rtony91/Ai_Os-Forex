from automation.forex_engine import forex_institutional_data_breakthrough_v1 as module


def test_inventory_freezes_four_distinct_lawful_routes_per_series():
    manifest = module.inventory_manifest()
    assert manifest["source_count"] >= 15
    assert manifest["route_count"] == manifest["source_count"] * 4
    for source in manifest["sources"]:
        urls = [route["url"] for route in source["routes"]]
        route_ids = [route["route_id"] for route in source["routes"]]
        assert route_ids == ["A", "B", "C", "D"]
        assert len(urls) == len(set(urls))
        assert all(url.startswith("https://") for url in urls)
        assert all(route["request_client"].endswith("_get") for route in source["routes"])


def test_human_drop_items_exclude_acquired_usable_sources():
    results = [
        {"source_id": "FRED_DFF", "classification": "ACQUIRED_USABLE"},
        {"source_id": "FRED_ECBDFR", "classification": "SOURCE_UNAVAILABLE_AUTOMATICALLY"},
    ]
    items = module.human_drop_items(results)
    assert [item["series_id"] for item in items] == ["ECBDFR"]
    assert items[0]["credential_requirement"] == "NONE"
    assert "manual_drop_inbox" in items[0]["expected_destination_inbox"]


def test_normalized_records_include_point_in_time_fields():
    source = module.source_series_inventory()[0]
    data = b"DATE,DFF\n2024-01-02,5.33\n"
    records = module.normalize_csv_source(source, data, module.sha256(data))
    required = {
        "source_id",
        "series_id",
        "observation_time_utc",
        "publication_time_utc",
        "strategy_available_time_utc",
        "vintage_or_revision_status",
        "retrieval_time_utc",
        "source_artifact_hash",
        "normalization_code_hash",
    }
    assert len(records) == 1
    assert required.issubset(records[0])
    assert records[0]["strategy_available_time_utc"] >= records[0]["publication_time_utc"]
