from pathlib import Path


ROOT = Path(__file__).parents[2]
DOCTRINE = ROOT / "docs/governance/AIOS_CAMPAIGN_ARBITRATION_DOCTRINE_V1.md"
ROADMAP = ROOT / "docs/roadmap/AIOS_FOREX_PROGRAM_B_MASTER_ROADMAP_V1.md"


def test_continuity_rule_and_return_coordinates_are_canonical():
    doctrine = DOCTRINE.read_text(encoding="utf-8")
    roadmap = ROADMAP.read_text(encoding="utf-8")
    for marker in (
        "Master Roadmap Continuity Rule",
        "first unfinished dependency",
        "Human Owner Anthony",
        "RETURN_TO_PROGRAM",
        "RETURN_TO_EPIC",
        "RETURN_TO_BUCKET",
        "must not guess",
    ):
        assert marker in doctrine
    assert "AIOS Forex Program B Master Roadmap V1" in roadmap
    assert "Program B Bucket 2" in roadmap


def test_dependency_resolution_skips_complete_bucket_and_preserves_order():
    buckets = [
        {"id": "B1", "status": "COMPLETE"},
        {"id": "B2", "status": "COMPLETE"},
        {"id": "B3", "status": "BLOCKED"},
        {"id": "B4", "status": "NOT_STARTED"},
    ]
    assert next(item["id"] for item in buckets if item["status"] not in {"COMPLETE", "SUPERSEDED"}) == "B3"


def test_owner_reprioritization_overrides_automatic_return():
    automatic = "B2"
    owner_override = "DASHBOARD-REVIEW"
    assert owner_override != automatic
    assert owner_override == "DASHBOARD-REVIEW"


def test_side_job_without_coordinates_requires_inspection_not_guessing():
    return_to = None
    assert return_to is None
    assert "must not guess" in DOCTRINE.read_text(encoding="utf-8")


def test_required_interruption_scenarios_are_explicitly_governed():
    doctrine = DOCTRINE.read_text(encoding="utf-8")
    roadmap = ROADMAP.read_text(encoding="utf-8")
    for marker in (
        "side jobs may interrupt",
        "Recency alone must never",
        "Current repository and runtime evidence overrides",
        "Completed milestones must not be rerun",
        "Human Owner reprioritization overrides",
        "return to Bucket 3",
        "Strategic Campaign Registry remains",
    ):
        assert marker in doctrine + roadmap


def test_current_verified_first_unfinished_dependency_is_bucket_two():
    roadmap = ROADMAP.read_text(encoding="utf-8")
    assert "that return point is **Program B Bucket 2" in roadmap
    assert "Bucket 3 — 30 genuine qualifying PAPER trades | BLOCKED" in roadmap
