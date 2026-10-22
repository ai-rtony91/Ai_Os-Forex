import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "automation" / "orchestration" / "coordination_spine" / "Update-AiOsCycleMarker.DRY_RUN.ps1"


def run_script(*args: str) -> dict:
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return json.loads(completed.stdout)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def marker_payload(*, updated_at_utc: str = "2026-06-02T16:45:38Z") -> dict:
    return {
        "cycle_id": "1961890c-0b4f-4b0c-bca6-2f8e854b5e45",
        "cycle_in_progress": False,
        "phase_name": "",
        "phase_state": "CYCLE_COMPLETE",
        "started_at": "2026-06-02T16:45:36Z",
        "updated_at_utc": updated_at_utc,
        "apply": False,
        "requested_apply": False,
        "effective_apply": False,
        "mode": "DAY_AUTOPILOT",
        "mode_reason": "DAY_HOURS_AUTOPILOT",
        "observe_only": True,
        "resume_from": "",
        "phases": [{"name": "hygiene"}],
        "completed_phases": ["night-supervisor"],
        "skipped_phases": [],
        "phase_results": [
            {
                "name": "night-supervisor",
                "state": "COMPLETE",
                "result": "completed",
                "reason": "",
                "requested_apply": False,
                "effective_apply": False,
                "mode": "DAY_AUTOPILOT",
                "observe_only": True,
                "updated_at_utc": "2026-06-02T16:45:34Z",
                "exit_code": 0,
            }
        ],
    }


def test_dry_run_does_not_write_marker(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    marker = repo_root / "control" / "cycle" / "last_marker.json"
    original = marker_payload()
    write_json(marker, original)

    result = run_script("-RepoRoot", str(repo_root))

    assert result["mode"] == "DRY_RUN"
    assert result["refresh_mode"] == "marker_only"
    assert result["write_behavior"] == "telemetry_only"
    assert result["write_path_enabled"] is False
    assert marker.read_text(encoding="utf-8") == json.dumps(original)


def test_apply_writes_only_marker_path_and_refreshes_timestamp(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    marker = repo_root / "control" / "cycle" / "last_marker.json"
    original = marker_payload()
    write_json(marker, original)

    result = run_script("-RepoRoot", str(repo_root), "-Apply")

    refreshed = json.loads(marker.read_text(encoding="utf-8"))
    assert result["mode"] == "APPLY"
    assert result["write_path_enabled"] is True
    assert refreshed["updated_at_utc"] != original["updated_at_utc"]
    assert refreshed["marker_refresh_mode"] == "marker_only"
    assert refreshed["marker_refresh_source"] == "Update-AiOsCycleMarker.DRY_RUN.ps1"
    assert refreshed["marker_refresh_applied"] is True
    assert sorted(path.relative_to(repo_root).as_posix() for path in repo_root.rglob("*") if path.is_file()) == [
        "control/cycle/last_marker.json"
    ]


def test_script_contains_atomic_write_pattern_and_no_forbidden_mutating_calls() -> None:
    text = SCRIPT.read_text(encoding="utf-8").lower()

    assert "writealltext" in text
    assert "write-aiosatomicjson" in text
    assert "move-item -literalpath $temppath -destination $destinationfull -force" in text
    assert "invoke-aiosnightcycle" not in text
    assert "queue" not in text
    assert "lock" not in text
    assert "approval" not in text
    assert "dispatcher" not in text
    assert "scheduler" not in text
    assert "sos" not in text
    assert "adb" not in text
    assert "broker" not in text
    assert "webhook" not in text
    assert "secret" not in text
    assert "t2b" not in text
    assert "operation glue" not in text
    assert "auto-loop" not in text
