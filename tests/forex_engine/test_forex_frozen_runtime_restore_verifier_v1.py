from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from automation.forex_engine.forex_frozen_runtime_restore_verifier_v1 import verify_restore_bundle


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/forex_delivery/run_forex_frozen_runtime_restore_verifier_v1.py"


def test_verify_restore_bundle_blocks_missing_expected_inputs(tmp_path: Path) -> None:
    result = verify_restore_bundle(tmp_path / "missing")

    assert result["status"] == "BLOCKED_RESTORE_BUNDLE_MISSING_INPUTS"
    assert result["counts"] == {"expected": 5, "present": 0, "matched": 0, "missing": 5, "mismatched": 0}
    assert result["safe_to_rerun_postmortem"] is False
    assert "AIOS_FOREX_PHASE1_CANDIDATE_REGISTRY.json" in result["missing"]
    assert result["next_safe_action"] == "restore_authoritative_runtime_bundle_then_rerun_verifier"


def test_verify_restore_bundle_passes_only_when_every_hash_matches(tmp_path: Path) -> None:
    files = {
        "AIOS_FOREX_PHASE1_CANDIDATE_REGISTRY.json": b"registry\n",
        "AIOS_FOREX_PHASE1_CHECKPOINT.json": b"checkpoint\n",
    }
    expected = {
        "AIOS_FOREX_PHASE1_CANDIDATE_REGISTRY.json": "a2782aa6fc01988c16bb63c7cd88d694790db18dd7ae101967ce118bd7d701e4",
        "AIOS_FOREX_PHASE1_CHECKPOINT.json": "74c24dae6de5def220b3b9c31540dbb31934b9e5b6dbd37427ee1f21abe7e7e6",
    }
    for name, payload in files.items():
        (tmp_path / name).write_bytes(payload)

    result = verify_restore_bundle(tmp_path, expected_hashes=expected)

    assert result["status"] == "PASS"
    assert result["counts"] == {"expected": 2, "present": 2, "matched": 2, "missing": 0, "mismatched": 0}
    assert result["safe_to_rerun_postmortem"] is False
    assert result["postmortem_rerun_command"] is None


def test_verify_restore_bundle_rejects_symlinked_input(tmp_path: Path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"registry\n")
    input_root = tmp_path / "runtime"
    input_root.mkdir()
    try:
        (input_root / "AIOS_FOREX_PHASE1_CANDIDATE_REGISTRY.json").symlink_to(outside)
    except OSError:
        pytest.skip("file symlinks unavailable")

    result = verify_restore_bundle(
        input_root,
        expected_hashes={"AIOS_FOREX_PHASE1_CANDIDATE_REGISTRY.json": "a2782aa6fc01988c16bb63c7cd88d694790db18dd7ae101967ce118bd7d701e4"},
    )

    assert result["status"] == "BLOCKED_RESTORE_BUNDLE_HASH_MISMATCH"
    assert result["counts"]["matched"] == 0
    assert result["safe_to_rerun_postmortem"] is False


def test_verify_restore_bundle_rejects_traversal_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="plain filename"):
        verify_restore_bundle(
            tmp_path,
            expected_hashes={"../outside.json": "a2782aa6fc01988c16bb63c7cd88d694790db18dd7ae101967ce118bd7d701e4"},
        )


def test_verify_restore_bundle_accepts_uppercase_digest(tmp_path: Path) -> None:
    (tmp_path / "AIOS_FOREX_PHASE1_CANDIDATE_REGISTRY.json").write_bytes(b"registry\n")
    result = verify_restore_bundle(
        tmp_path,
        expected_hashes={"AIOS_FOREX_PHASE1_CANDIDATE_REGISTRY.json": "A2782AA6FC01988C16BB63C7CD88D694790DB18DD7AE101967CE118BD7D701E4"},
    )

    assert result["status"] == "PASS"
    assert result["safe_to_rerun_postmortem"] is False


def test_verify_restore_bundle_blocks_present_file_with_wrong_hash(tmp_path: Path) -> None:
    (tmp_path / "AIOS_FOREX_PHASE1_RECEIPT.json").write_bytes(b"wrong archive bytes\n")

    result = verify_restore_bundle(
        tmp_path,
        expected_hashes={
            "AIOS_FOREX_PHASE1_RECEIPT.json": "20d099f8ee0e7318fbd18b7b935ab2e2f40ed50a6fb83051790f2be8acf486a5",
        },
    )

    assert result["status"] == "BLOCKED_RESTORE_BUNDLE_HASH_MISMATCH"
    assert result["counts"] == {"expected": 1, "present": 1, "matched": 0, "missing": 0, "mismatched": 1}
    assert result["safe_to_rerun_postmortem"] is False
    assert result["mismatched"][0]["name"] == "AIOS_FOREX_PHASE1_RECEIPT.json"


def test_cli_writes_state_and_report_without_creating_runtime_inputs(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    report_path = tmp_path / "report.md"
    input_root = tmp_path / "not-restored"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--input-root",
            str(input_root),
            "--state-path",
            str(state_path),
            "--report-path",
            str(report_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "BLOCKED_RESTORE_BUNDLE_MISSING_INPUTS"
    assert json.loads(state_path.read_text(encoding="utf-8"))["status"] == receipt["status"]
    assert "Status: BLOCKED_RESTORE_BUNDLE_MISSING_INPUTS" in report_path.read_text(encoding="utf-8")
    assert not input_root.exists()


def test_cli_exits_nonzero_for_hash_mismatch(tmp_path: Path) -> None:
    input_root = tmp_path / "runtime"
    input_root.mkdir()
    for name in (
        "AIOS_FOREX_PHASE1_CANDIDATE_REGISTRY.json",
        "AIOS_FOREX_PHASE1_CHECKPOINT.json",
        "AIOS_FOREX_PHASE1_RECEIPT.json",
        "AIOS_FOREX_PHASE1_RESEARCH_CONTRACT.json",
        "AIOS_FOREX_PHASE1_RESULTS.json",
    ):
        (input_root / name).write_text("not the authoritative archive\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--input-root",
            str(input_root),
            "--state-path",
            str(tmp_path / "state.json"),
            "--report-path",
            str(tmp_path / "report.md"),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    receipt = json.loads(result.stdout)
    assert result.returncode == 2
    assert receipt["status"] == "BLOCKED_RESTORE_BUNDLE_HASH_MISMATCH"
    assert receipt["counts"]["mismatched"] == 5
    assert receipt["postmortem_rerun_command"] is None


def test_cli_refuses_state_path_inside_frozen_inputs(tmp_path: Path) -> None:
    input_root = tmp_path / "runtime"
    input_root.mkdir()
    frozen_file = input_root / "AIOS_FOREX_PHASE1_RECEIPT.json"
    frozen_file.write_bytes(b"frozen evidence\n")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--input-root", str(input_root),
            "--state-path", str(frozen_file),
            "--report-path", str(tmp_path / "report.md"),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert frozen_file.read_bytes() == b"frozen evidence\n"
    assert not (tmp_path / "report.md").exists()


def test_cli_refuses_report_symlink_to_frozen_input(tmp_path: Path) -> None:
    input_root = tmp_path / "runtime"
    input_root.mkdir()
    frozen_file = input_root / "AIOS_FOREX_PHASE1_RECEIPT.json"
    frozen_file.write_bytes(b"frozen evidence\n")
    report_alias = tmp_path / "report-alias.md"
    try:
        report_alias.symlink_to(frozen_file)
    except OSError:
        pytest.skip("file symlinks unavailable")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--input-root", str(input_root),
            "--state-path", str(tmp_path / "state.json"),
            "--report-path", str(report_alias),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert frozen_file.read_bytes() == b"frozen evidence\n"
    assert not (tmp_path / "state.json").exists()


def test_cli_does_not_follow_preexisting_temporary_symlink(tmp_path: Path) -> None:
    input_root = tmp_path / "runtime"
    input_root.mkdir()
    frozen_file = input_root / "AIOS_FOREX_PHASE1_RECEIPT.json"
    frozen_file.write_bytes(b"frozen evidence\n")
    state_path = tmp_path / "state.json"
    try:
        (tmp_path / ".state.json.tmp").symlink_to(frozen_file)
    except OSError:
        pytest.skip("file symlinks unavailable")

    result = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--input-root", str(input_root),
            "--state-path", str(state_path),
            "--report-path", str(tmp_path / "report.md"),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert state_path.is_file()
    assert frozen_file.read_bytes() == b"frozen evidence\n"


def test_cli_custom_root_cannot_write_into_default_frozen_root(tmp_path: Path) -> None:
    default_root = tmp_path / ".aios/runtime/forex_frozen_21_series_edge_research_v1"
    default_root.mkdir(parents=True)
    frozen_file = default_root / "AIOS_FOREX_PHASE1_RECEIPT.json"
    frozen_file.write_bytes(b"frozen evidence\n")
    alternate = tmp_path / "alternate"
    alternate.mkdir()

    result = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--input-root", str(alternate),
            "--state-path", str(frozen_file),
            "--report-path", str(tmp_path / "report.md"),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert frozen_file.read_bytes() == b"frozen evidence\n"
    assert not (tmp_path / "report.md").exists()
