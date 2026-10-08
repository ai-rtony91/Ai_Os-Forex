from __future__ import annotations

from pathlib import Path

import pytest

from scripts.forex_delivery.run_forex_cftc_crowding_unwind_price_confirmation_v1 import (
    artifact_destinations,
    compare_artifacts,
    require_absent,
)


def test_artifact_destinations_are_exactly_eight(tmp_path: Path) -> None:
    destinations = artifact_destinations(tmp_path / "runtime", tmp_path / "report.md", tmp_path / "rejection.json")
    assert len(destinations) == 8
    assert len(set(destinations.values())) == 8


def test_byte_comparison_rejects_any_difference() -> None:
    compare_artifacts({"a": b"same"}, {"a": b"same"})
    with pytest.raises(ValueError, match="DETERMINISTIC_BYTE_MISMATCH"):
        compare_artifacts({"a": b"first"}, {"a": b"second"})


def test_existing_destination_fails_closed(tmp_path: Path) -> None:
    destinations = artifact_destinations(tmp_path / "runtime", tmp_path / "report.md", tmp_path / "rejection.json")
    collision = next(iter(destinations.values()))
    collision.parent.mkdir(parents=True)
    collision.write_bytes(b"existing")
    with pytest.raises(FileExistsError, match="OUTPUT_COLLISION"):
        require_absent(destinations)
