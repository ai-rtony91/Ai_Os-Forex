from __future__ import annotations

import hashlib
from pathlib import Path
import importlib.util


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = (
    REPO_ROOT
    / "automation"
    / "orchestration"
    / "control_loop"
    / "aios_observe_spine_runner.py"
)

ACTIVE_QUEUE = REPO_ROOT / "automation" / "orchestration" / "work_packets" / "active"
WORKER_INBOX = REPO_ROOT / "automation" / "orchestration" / "workers" / "inbox" / "AIOS_WORKER_INBOX.json"
APPROVAL_INBOX = REPO_ROOT / "automation" / "orchestration" / "approval_inbox"
COMMAND_QUEUE = REPO_ROOT / "automation" / "orchestration" / "command_queue" / "AIOS_COMMAND_QUEUE.json"
SERVICES = REPO_ROOT / "services"
TELEMETRY = REPO_ROOT / "telemetry"
RUNTIME_APPLY_MODULE_PATH = REPO_ROOT / "automation" / "orchestration" / "runtime_closure" / "aios_runtime_apply_lane_preview.py"
RUNTIME_PROOF_HELPERS_PATH = REPO_ROOT / "tests" / "orchestration" / "test_runtime_proof_gate.py"


def _load():
    spec = importlib.util.spec_from_file_location("aios_observe_spine_runner_test_module", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_runtime_proof_helpers():
    spec = importlib.util.spec_from_file_location("runtime_proof_gate_test_helpers_for_observe", RUNTIME_PROOF_HELPERS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_runtime_apply_module():
    spec = importlib.util.spec_from_file_location("runtime_apply_lane_preview_test_module", RUNTIME_APPLY_MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65_536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fingerprint(path: Path):
    if path.is_file():
        return ("file", path.stat().st_size, _sha256(path))
    if path.is_dir():
        return ("dir", sorted(str(item.relative_to(path).as_posix()) for item in path.rglob("*") if item.is_file()))
    return ("missing", None)


def _ready_evidence():
    return {
        "p2_bridge": {"bridge_status": "READY_FOR_DRY_RUN_PREVIEW", "validation": {"status": "PASS"}},
        "queue_mutation_gate": {
            "gate_status": "READY_FOR_HUMAN_REVIEW",
            "proposed_queue_item": {"allowed_paths": ["automation/orchestration/work_packets/"], "forbidden_paths": ["automation/orchestration/work_packets/active/"]},
            "validation": {"status": "PASS"},
        },
        "runtime_apply": {"apply_status": "READY_FOR_RUNTIME_PREVIEW", "validation": {"status": "PASS"}},
        "sos_arming": {"sos_status": "READY_FOR_SOS_PREVIEW", "validation": {"status": "PASS"}},
        "scheduler_registration": {"scheduler_status": "READY_FOR_SCHEDULER_PREVIEW", "validation": {"status": "PASS"}},
    }


def test_module_exports():
    mod = _load()
    assert mod.SCHEMA == "AIOS_OBSERVE_SPINE_RUNNER.v1"
    assert mod.MODE == "DRY_RUN_PREVIEW_ONLY"
    assert mod.READY == "OBSERVE_LOOP_READY"
    assert mod.BLOCKED == "OBSERVE_LOOP_BLOCKED"
    assert mod.INVALID == "OBSERVE_LOOP_INVALID"


def test_runner_builds_all_layer_reports_and_keeps_mutations_false(tmp_path):
    mod = _load()
    report = mod.run_observe_spine_runner(
        repo_root=REPO_ROOT,
        output_dir=tmp_path / "control_loop",
        closure_dir=tmp_path / "autonomy_closure",
        now="2026-06-10T15:20:28Z",
        evidence=_ready_evidence(),
        write_reports=True,
    )

    assert report["observe_loop_status"] == mod.READY
    assert report["runtime_apply_status"] == "READY_FOR_RUNTIME_PREVIEW"
    assert report["queue_gate_status"] == "READY_FOR_HUMAN_REVIEW"
    assert report["p2_bridge_status"] == "READY_FOR_DRY_RUN_PREVIEW"
    assert report["scheduler_status"] == "READY_FOR_SCHEDULER_PREVIEW"
    assert report["sos_status"] == "READY_FOR_SOS_PREVIEW"
    assert report["stale_layers"] == []
    assert set(report["layers"].keys()) == {
        "p2_bridge",
        "queue_mutation_gate",
        "runtime_apply_lane",
        "sos_arming",
        "scheduler_registration",
    }
    assert all(value is False for value in report["mutation_projection"].values())
    assert all(value is False for value in report["validate_mutation_boundaries"].values())

    json_path = tmp_path / "control_loop" / mod.REPORT_JSON_NAME
    md_path = tmp_path / "control_loop" / mod.REPORT_MD_NAME
    assert json_path.exists()
    assert md_path.exists()
    closure_path = tmp_path / "autonomy_closure" / mod.CLOSURE_JSON_NAME
    closure_md_path = tmp_path / "autonomy_closure" / mod.CLOSURE_MD_NAME
    assert closure_path.exists()
    assert closure_md_path.exists()


def test_stale_layer_is_flagged_not_real_blocker(tmp_path):
    mod = _load()
    evidence = _ready_evidence()
    evidence["p2_bridge"] = {
        "bridge_status": "INVALID",
        "invalid_reasons": ["allowed_paths is required; forbidden_paths is required"],
        "validation": {"status": "PASS"},
    }

    report = mod.build_observe_spine_report(
        repo_root=REPO_ROOT,
        output_dir=tmp_path / "ignore",
        now="2026-06-10T15:20:28Z",
        evidence=evidence,
    )

    p2_layer = report["layers"]["p2_bridge"]
    assert p2_layer["stale"] is True
    assert p2_layer["real_blocker"] is False
    assert report["observe_loop_status"] == mod.INVALID
    assert "Resolve stale/invalid evidence" in report["safe_next_action"]


def test_governance_and_code_blocker_classification(tmp_path):
    mod = _load()
    evidence = _ready_evidence()
    evidence["queue_mutation_gate"] = {
        "gate_status": "BLOCKED",
        "gate_status_reason": "approval evidence is not explicit",
        "validation": {"status": "PASS"},
    }
    evidence["runtime_apply"] = {
        "apply_status": "INVALID",
        "invalid_reasons": ["missing required evidence: runtime proof gate"],
        "validation": {"status": "PASS"},
    }
    evidence["sos_arming"] = {"sos_status": "READY_FOR_SOS_PREVIEW", "validation": {"status": "PASS"}}
    evidence["scheduler_registration"] = {
        "scheduler_status": "BLOCKED",
        "validation": {"status": "PASS"},
        "blockers": ["approval evidence is not explicit"],
    }

    report = mod.build_observe_spine_report(
        repo_root=REPO_ROOT,
        output_dir=tmp_path / "ignore",
        now="2026-06-10T15:20:28Z",
        evidence=evidence,
    )

    assert report["layers"]["queue_mutation_gate"]["governance_blocker"] is True
    assert report["layers"]["runtime_apply_lane"]["code_blocker"] is True
    assert report["layers"]["runtime_apply_lane"]["real_blocker"] is True
    assert report["layers"]["sos_arming"]["stale"] is False


def test_default_evidence_loading_uses_repo_reports_and_keeps_mutations_false(tmp_path):
    mod = _load()
    protected = [ACTIVE_QUEUE, WORKER_INBOX, APPROVAL_INBOX, COMMAND_QUEUE, SERVICES, TELEMETRY]
    before = {str(path): _fingerprint(path) for path in protected}

    report = mod.build_observe_spine_report(
        repo_root=REPO_ROOT,
        output_dir=tmp_path / "ignore",
        now="2026-06-10T15:20:28Z",
    )

    assert report["layers"]["p2_bridge"]["status"] == "BLOCKED"
    assert report["layers"]["runtime_apply_lane"]["status"] == "BLOCKED"
    assert report["observe_loop_status"] == mod.BLOCKED
    assert report["runtime_apply_status"] == "BLOCKED"
    assert report["queue_gate_status"] == "BLOCKED"
    assert report["p2_bridge_status"] == "BLOCKED"
    assert report["stale_layers"] == []
    assert all(value is False for value in report["mutation_projection"].values())
    assert all(value is False for value in report["validate_mutation_boundaries"].values())

    after = {str(path): _fingerprint(path) for path in protected}
    assert before == after


def test_real_paths_do_not_mutate_when_running_runner(tmp_path):
    mod = _load()
    protected = [ACTIVE_QUEUE, WORKER_INBOX, APPROVAL_INBOX, COMMAND_QUEUE, SERVICES, TELEMETRY]
    before = {str(path): _fingerprint(path) for path in protected}

    _ = mod.run_observe_spine_runner(
        repo_root=REPO_ROOT,
        output_dir=tmp_path / "control_loop",
        closure_dir=tmp_path / "autonomy_closure",
        now="2026-06-10T15:20:28Z",
        evidence=_ready_evidence(),
        write_reports=True,
    )

    after = {str(path): _fingerprint(path) for path in protected}
    assert before == after


def test_blocked_runtime_proof_file_keeps_observe_loop_blocked_not_invalid(tmp_path):
    mod = _load()
    helpers = _load_runtime_proof_helpers()
    proof_mod = helpers._load(helpers.GATE_PATH, "aios_runtime_proof_gate_for_observe_tests")
    queue, processor, _, restart, retention, soak, ledger, selector = helpers._ready_inputs()
    blocked_proof = proof_mod.build_runtime_proof_gate(
        runtime_queue_readout=queue,
        relay_processor_readout=processor,
        restart_timeouts_proof=restart,
        retention_rotation_proof=retention,
        soak_proof=soak,
        operator_dependency_ledger=ledger,
        reduction_target_selector=selector,
        now="2026-06-10T15:20:28Z",
    )
    assert blocked_proof["final_verdict"] == "BLOCKED"

    proof_outdir = tmp_path / "Reports" / "runtime_proof_gate"
    proof_mod.write_runtime_proof_gate_reports(blocked_proof, repo_root=tmp_path, output_dir=proof_outdir)
    runtime_apply_mod = _load_runtime_apply_module()
    p2_preview = {
        "bridge_status": "READY_FOR_DRY_RUN_PREVIEW",
        "validation": {"status": "PASS"},
        "summary": {"recommended_next_lane": "QUEUE_BLOCKER_TRIAGE_V1"},
        "proposed_queue_item_preview": {
            "preview_id": "P2_REVIEW_TO_QUEUE_ENQUEUE_BRIDGE_V1",
            "lane_id": "p2_review_to_queue_enqueue_bridge",
            "mode": "DRY_RUN_PREVIEW_ONLY",
            "allowed_paths": ["automation/orchestration/work_packets/"],
            "forbidden_paths": [
                "automation/orchestration/work_packets/active/",
                "automation/orchestration/work_packets/blocked/",
                "automation/orchestration/work_packets/complete/",
            ],
            "runtime_execution_allowed": False,
            "scheduler_creation_allowed": False,
            "sos_allowed": False,
            "live_trading_allowed": False,
            "queue_mutation_allowed": False,
            "runtime_launch_allowed": False,
            "worker_inbox_write_allowed": False,
        },
    }
    queue_gate = {
        "gate_status": "READY_FOR_HUMAN_REVIEW",
        "validation": {"status": "PASS", "blockers": []},
        "proposed_queue_item": {
            "packet_id": "AIOS-RUNTIME-APPLY-PREVIEW-001",
            "lane": "feature/runtime-apply-lane-preview-v1",
            "mode": "DRY_RUN_PREVIEW_ONLY",
            "allowed_paths": ["automation/orchestration/work_packets/"],
            "forbidden_paths": ["automation/orchestration/work_packets/active/"],
            "target_paths": ["automation/orchestration/work_packets/"],
        },
        "approval_check": {"approval_evidence_present": True, "explicit_approval": True},
        "runtime_execution_allowed": False,
        "runtime_launch_allowed": False,
        "scheduler_creation_allowed": False,
        "sos_allowed": False,
        "live_trading_allowed": False,
        "queue_mutation_allowed": False,
        "worker_inbox_mutation_allowed": False,
        "approval_inbox_mutation_allowed": False,
        "command_queue_mutation_allowed": False,
    }
    runtime_apply = runtime_apply_mod.build_runtime_apply_lane_report(
        repo_root=tmp_path,
        now="2026-06-10T15:20:28Z",
        p2_preview=p2_preview,
        queue_mutation_gate_preview=queue_gate,
    )

    evidence = _ready_evidence()
    evidence["runtime_apply"] = runtime_apply

    report = mod.build_observe_spine_report(
        repo_root=REPO_ROOT,
        output_dir=tmp_path / "control_loop",
        now="2026-06-10T15:20:28Z",
        evidence=evidence,
    )

    assert report["layers"]["runtime_apply_lane"]["status"] == mod.LAYER_BLOCKED
    assert report["layers"]["runtime_apply_lane"]["stale"] is False
    assert report["layers"]["runtime_apply_lane"]["real_blocker"] is True
    assert report["observe_loop_status"] == mod.BLOCKED
    assert report["observe_loop_status"] != mod.INVALID
