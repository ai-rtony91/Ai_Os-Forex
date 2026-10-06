from pathlib import Path

import pytest

from scripts.forex_delivery.run_forex_cftc_positioning_acceleration_price_continuation_v1 import artifact_destinations, require_absent
from scripts.forex_delivery.run_forex_cftc_crowding_unwind_price_confirmation_v1 import compare_artifacts


def test_exact_eight_destinations(tmp_path: Path) -> None:
    assert len(artifact_destinations(tmp_path / "runtime", tmp_path / "report.md", tmp_path / "rejection.json")) == 8


def test_byte_identity_check() -> None:
    compare_artifacts({"a": b"same"}, {"a": b"same"})
    with pytest.raises(ValueError, match="DETERMINISTIC_BYTE_MISMATCH"):
        compare_artifacts({"a": b"one"}, {"a": b"two"})


def test_collision_fails_closed(tmp_path: Path) -> None:
    destinations = artifact_destinations(tmp_path / "runtime", tmp_path / "report.md", tmp_path / "rejection.json")
    path = next(iter(destinations.values()))
    path.parent.mkdir(parents=True)
    path.write_bytes(b"existing")
    with pytest.raises(FileExistsError, match="OUTPUT_COLLISION"):
        require_absent(destinations)
