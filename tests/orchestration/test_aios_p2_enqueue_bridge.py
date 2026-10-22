from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = (
    REPO_ROOT
    / "automation"
    / "orchestration"
    / "runtime_closure"
    / "aios_p2_enqueue_bridge.py"
)
QUEUE_GATE_PATH = (
    REPO_ROOT
    / "automation"
    / "orchestration"
    / "work_packets"
    / "aios_queue_mutation_gate.py"
)
ADAPTER_MODULE_PATH = (
    REPO_ROOT
    / "automation"
    / "orchestration"
    / "approval_inbox"
    / "aios_approval_evidence_adapter.py"
)
HUMAN_GATE_REPORT = REPO_ROOT / "Reports" / "human_gate" / "human_gate_packet_dogfood_report.json"
AUTONOMY_GAP_REPORT = REPO_ROOT / "Reports" / "autonomy_gap" / "autonomy_gap_reassessment_report.json"
COMMAND_QUEUE = REPO_ROOT / "automation" / "orchestration" / "command_queue" / "AIOS_COMMAND_QUEUE.json"
WORKER_INBOX = REPO_ROOT / "automation" / "orchestration" / "workers" / "inbox" / "AIOS_WORKER_INBOX.json"
ACTIVE_PACKETS = REPO_ROOT / "automation" / "orchestration" / "work_packets" / "active"
RUNTIME_TELEMETRY = REPO_ROOT / "telemetry" / "runtime"


def _load():
    spec = importlib.util.spec_from_file_location("aios_p2_enqueue_bridge_for_tests", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_queue_gate():
    spec = importlib.util.spec_from_file_location("aios_queue_mutation_gate_for_p2_tests", QUEUE_GATE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_adapter():
    spec = importlib.util.spec_from_file_location("aios_approval_evidence_adapter_for_tests", ADAPTER_MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fingerprint(path: Path):
    if path.is_file():
        return ("file", path.read_bytes())
    if path.is_dir():
        entries = sorted(str(item.relative_to(path)) for item in path.rglob("*"))
        return ("dir", entries)
    return ("missing", None)


def _ready_evidence() -> dict:
    return {
        "human_gate_report": {
            "dogfood_status": "PASS",
            "mutation_check_status": "PASS",
            "mutated_sources": [],
            "queue_validation_summary": {"queue_validation_status": "PASS"},
            "runtime_proof_gate_summary": {"final_verdict": "READY_FOR_HUMAN_GATE"},
            "human_gate_packet_summary": {"packet_status": "READY_FOR_HUMAN_REVIEW"},
            "summary": {
                "runtime_proof_gate_verdict": "READY_FOR_HUMAN_GATE",
                "packet_status": "READY_FOR_HUMAN_REVIEW",
            },
            "approval_granted": False,
            "execution_allowed": False,
            "dispatch_allowed": False,
            "apply_allowed": False,
            "runtime_launch_allowed": False,
            "queue_mutation_allowed": False,
            "telemetry_mutation_allowed": False,
            "scheduler_creation_allowed": False,
            "service_creation_allowed": False,
            "sos_allowed": False,
            "live_trading_allowed": False,
            "credentials_accessed": False,
            "unsafe_autonomy_claim": False,
            "vacation_mode_complete": False,
        },
        "autonomy_gap_report": {
            "reassessment_status": "PASS",
            "p2_enqueue_bridge_readiness": {"status": "READY"},
            "readiness_scorecard": {"p2_enqueue_bridge_ready": {"status": "READY"}},
            "live_execution_readiness": {"status": "BLOCKED"},
            "recommended_next_lanes": [
                {
                    "lane_id": "P2_REVIEW_TO_QUEUE_ENQUEUE_BRIDGE_V1",
                    "scope": "DRY_RUN_ONLY",
                }
            ],
            "summary": {
                "recommended_next_lane": "P2_REVIEW_TO_QUEUE_ENQUEUE_BRIDGE_V1",
                "p2_enqueue_bridge_ready": "READY",
            },
            "approval_granted": False,
            "execution_allowed": False,
            "dispatch_allowed": False,
            "apply_allowed": False,
            "runtime_launch_allowed": False,
            "queue_mutation_allowed": False,
            "telemetry_mutation_allowed": False,
            "scheduler_creation_allowed": False,
            "service_creation_allowed": False,
            "sos_allowed": False,
            "live_trading_allowed": False,
            "credentials_accessed": False,
            "unsafe_autonomy_claim": False,
            "vacation_mode_complete": False,
        },
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _build_repo_with_reports(repo_root: Path, *, apply_gate_status: str = "pending_review") -> None:
    _write_json(
        repo_root / "Reports" / "human_gate" / "human_gate_packet_dogfood_report.json",
        _ready_evidence()["human_gate_report"],
    )
    _write_json(
        repo_root / "Reports" / "autonomy_gap" / "autonomy_gap_reassessment_report.json",
        _ready_evidence()["autonomy_gap_report"],
    )
    _write_json(
        repo_root / "automation" / "orchestration" / "approval_inbox" / "APPLY_APPROVAL_GATE_001.json",
        {
            "approval_gate_id": "APPLY_APPROVAL_GATE_001",
            "approval_status": apply_gate_status,
            "approved_by_human": False,
            "approval_authority": "Anthony / Human Owner",
            "approved_by": "system-reviewer",
            "packet_id": "AIOS-ENRICHMENT-TEST-001",
            "allowed_paths": ["automation/orchestration/work_packets/"],
            "blocked_paths": ["automation/orchestration/work_packets/active/"],
            "validator_chain_required": True,
            "commit_package_required": True,
        },
    )
    _write_json(
        repo_root / "automation" / "orchestration" / "approval_inbox" / "APPROVAL_INBOX_001.json",
        {
            "schema": "AIOS_APPROVAL_INBOX.v1",
            "approval_gate_id": "APPROVAL_INBOX_001",
            "authority_status": "active_authority",
            "approval_status": "completed",
            "approved_by_human": True,
            "approval_authority": "Anthony / Human Owner",
            "approved_by": "Anthony",
            "allowed_paths": ["tests/orchestration/"],
            "blocked_paths": ["services/"],
            "validator_chain_required": True,
            "commit_package_required": True,
        },
    )


def test_module_imports_cleanly():
    mod = _load()
    assert mod.SCHEMA == "AIOS_P2_ENQUEUE_BRIDGE_PREVIEW.v1"
    assert mod.MODE == "DRY_RUN"
    assert mod.BRIDGE_TYPE == "p2_enqueue_bridge"


def test_current_repo_evidence_builds_blocked_preview(tmp_path):
    mod = _load()
    report = mod.build_p2_enqueue_bridge_report(
        repo_root=REPO_ROOT,
        output_dir=tmp_path / "Reports" / "p2_enqueue_bridge",
        now="2026-01-02T03:04:05Z",
    )
    preview = report["proposed_queue_item_preview"]
    assert report["bridge_status"] == "BLOCKED"
    assert report["validation"]["status"] == "PASS"
    assert report["queue_mutation_allowed"] is False
    assert report["runtime_launch_allowed"] is False
    assert report["scheduler_creation_allowed"] is False
    assert report["sos_allowed"] is False
    assert report["live_trading_allowed"] is False
    assert preview["enqueue_allowed"] is False
    assert preview["canonical_queue_write_allowed"] is False
    assert preview["worker_inbox_write_allowed"] is False
    assert preview["active_packet_write_allowed"] is False
    assert preview["runtime_execution_allowed"] is False
    assert preview["allowed_paths"] == ["automation/orchestration/work_packets/"]
    assert "automation/orchestration/work_packets/active/" in preview["forbidden_paths"]


def test_bridge_writes_only_preview_json_and_markdown(tmp_path):
    mod = _load()
    output_dir = tmp_path / "Reports" / "p2_enqueue_bridge"
    report = mod.run_p2_enqueue_bridge(
        repo_root=REPO_ROOT,
        output_dir=output_dir,
        now="2026-01-02T03:04:05Z",
    )
    json_path = output_dir / mod.REPORT_JSON_NAME
    md_path = output_dir / mod.REPORT_MD_NAME
    assert json_path.exists()
    assert md_path.exists()
    assert sorted(path.name for path in output_dir.iterdir()) == [
        mod.REPORT_JSON_NAME,
        mod.REPORT_MD_NAME,
    ]
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["summary"]["bridge_status"] == report["bridge_status"]
    assert "This preview does not approve execution." in md_path.read_text(encoding="utf-8")


def test_ready_evidence_still_produces_preview_only_item(tmp_path):
    mod = _load()
    report = mod.build_p2_enqueue_bridge_report(
        repo_root=REPO_ROOT,
        output_dir=tmp_path / "Reports" / "p2_enqueue_bridge",
        now="2026-01-02T03:04:05Z",
        evidence=_ready_evidence(),
    )
    preview = report["proposed_queue_item_preview"]
    assert report["bridge_status"] == "READY_FOR_DRY_RUN_PREVIEW"
    assert report["bridge_blockers"] == []
    assert report["invalid_reasons"] == []
    assert report["validation"]["status"] == "PASS"
    assert preview["preview_state"] == "PREVIEW_READY"
    assert preview["enqueue_allowed"] is False
    assert preview["dispatch_allowed"] is False
    assert preview["runtime_execution_allowed"] is False
    assert preview["allowed_paths"] == ["automation/orchestration/work_packets/"]
    assert "automation/orchestration/workers/inbox/" in preview["forbidden_paths"]


def test_enriched_preview_passes_queue_gate_contract_without_mutation(tmp_path):
    mod = _load()
    queue_gate = _load_queue_gate()
    protected_paths = [COMMAND_QUEUE, WORKER_INBOX, ACTIVE_PACKETS, RUNTIME_TELEMETRY]
    before = {str(path): _fingerprint(path) for path in protected_paths}
    report = mod.build_p2_enqueue_bridge_report(
        repo_root=REPO_ROOT,
        output_dir=tmp_path / "Reports" / "p2_enqueue_bridge",
        now="2026-01-02T03:04:05Z",
        evidence=_ready_evidence(),
    )
    json_path = tmp_path / "Reports" / "p2_enqueue_bridge" / mod.REPORT_JSON_NAME
    mod.write_p2_enqueue_bridge_reports(report, output_dir=json_path.parent)

    gate_report = queue_gate.run_queue_mutation_gate(
        repo_root=REPO_ROOT,
        proposed_item_path=json_path,
        output_dir=tmp_path / "Reports" / "queue_mutation_gate",
        now="2026-01-02T03:04:05Z",
    )

    after = {str(path): _fingerprint(path) for path in protected_paths}
    assert before == after
    assert gate_report["gate_status"] == queue_gate.BLOCKED
    assert gate_report["approval_check"]["approval_evidence_present"] is True
    assert gate_report["approval_check"]["explicit_approval"] is False
    assert gate_report["approval_check"]["approval_gate_packet_mismatch"] is True
    assert gate_report["validation"]["blockers"]
    assert gate_report["validation"]["invalid_reasons"] == []
    assert gate_report["proposed_queue_item"]["allowed_paths"] == ["automation/orchestration/work_packets/"]
    assert "automation/orchestration/work_packets/active/" in gate_report["proposed_queue_item"]["forbidden_paths"]
    assert gate_report["queue_write_allowed"] is False
    assert gate_report["canonical_queue_mutated"] is False
    assert gate_report["worker_inbox_mutation_allowed"] is False
    assert gate_report["runtime_execution_allowed"] is False


def test_approval_adapter_marks_pending_apply_gate_as_non_authorizing(tmp_path):
    adapter = _load_adapter()
    repo_root = tmp_path / "repo"
    approval_gate = (
        repo_root / "automation" / "orchestration" / "approval_inbox" / "APPLY_APPROVAL_GATE_001.json"
    )
    approval_inbox = (
        repo_root / "automation" / "orchestration" / "approval_inbox" / "APPROVAL_INBOX_001.json"
    )
    _write_json(
        approval_gate,
        {
            "approval_gate_id": "APPLY_APPROVAL_GATE_001",
            "approval_status": "pending_review",
            "approved_by_human": False,
            "bound_by": "APPLY_PENDING_SCOPE",
            "packet_id": "AIOS-PENDING-APPROVAL",
            "validator_chain_required": True,
            "commit_package_required": True,
            "allowed_paths": ["automation/orchestration/work_packets/"],
            "blocked_paths": ["automation/orchestration/work_packets/active/"],
        },
    )
    _write_json(
        approval_inbox,
        {
            "schema": "AIOS_APPROVAL_INBOX.v1",
            "approval_gate_id": "APPROVAL_INBOX_001",
            "authority_status": "active_authority",
            "approval_status": "completed",
            "approved_by_human": True,
            "approval_authority": "Anthony / Human Owner",
            "validator_chain_required": False,
            "commit_package_required": False,
        },
    )

    evidence = adapter.build_queue_mutation_approval_evidence(
        repo_root=repo_root,
        approval_gate_path=approval_gate,
        approval_inbox_path=approval_inbox,
        target_packet_id="P2_REVIEW_TO_QUEUE_ENQUEUE_BRIDGE_V1",
    )

    assert evidence
    assert isinstance(evidence, dict)
    assert evidence["approval_status"] == "pending_review"
    assert evidence["approved_by_human"] is False
    assert evidence["approval_granted"] is False
    assert evidence["explicit_approval"] is False
    assert evidence["approval_gate_packet_id"] == "AIOS-PENDING-APPROVAL"
    assert evidence["approval_gate_packet_mismatch"] is True
    assert evidence["target_packet_id"] == "P2_REVIEW_TO_QUEUE_ENQUEUE_BRIDGE_V1"
    assert evidence["apply_gate_pending"] is True
    assert evidence["non_authorizing_placeholder"] is True
    assert "does not match target_packet_id" in evidence["non_authorizing_reason"]


def test_approval_inbox_authority_is_not_queue_authorization_by_itself(tmp_path):
    adapter = _load_adapter()
    repo_root = tmp_path / "repo"
    approval_gate = (
        repo_root / "automation" / "orchestration" / "approval_inbox" / "APPLY_APPROVAL_GATE_001.json"
    )
    approval_inbox = (
        repo_root / "automation" / "orchestration" / "approval_inbox" / "APPROVAL_INBOX_001.json"
    )
    _write_json(
        approval_inbox,
        {
            "schema": "AIOS_APPROVAL_INBOX.v1",
            "approval_gate_id": "APPROVAL_INBOX_001",
            "authority_status": "active_authority",
            "approval_status": "completed",
            "approved_by_human": True,
            "approval_authority": "Anthony / Human Owner",
            "approved_by": "Anthony / Human Owner",
            "allowed_paths": ["tests/orchestration/"],
            "blocked_paths": ["services/"],
            "validator_chain_required": True,
            "commit_package_required": True,
        },
    )

    evidence = adapter.build_queue_mutation_approval_evidence(
        repo_root=repo_root,
        approval_gate_path=approval_gate,
        approval_inbox_path=approval_inbox,
        target_packet_id="P2_REVIEW_TO_QUEUE_ENQUEUE_BRIDGE_V1",
    )

    assert evidence["approval_status"] == "missing_approval_status"
    assert evidence["explicit_approval"] is False
    assert evidence["apply_gate_pending"] is False
    assert evidence["file_exists"] is False
    assert evidence["authority_active"] is True
    assert evidence["approval_gate_packet_mismatch"] is False


def test_queue_specific_approval_gate_is_preferred_when_present(tmp_path):
    adapter = _load_adapter()
    repo_root = tmp_path / "repo"
    queue_specific_gate = (
        repo_root
        / "automation"
        / "orchestration"
        / "approval_inbox"
        / "APPLY_APPROVAL_GATE_P2_REVIEW_TO_QUEUE_ENQUEUE_BRIDGE_V1.json"
    )
    approval_inbox = (
        repo_root / "automation" / "orchestration" / "approval_inbox" / "APPROVAL_INBOX_001.json"
    )
    _write_json(
        queue_specific_gate,
        {
            "approval_gate_id": "APPLY_APPROVAL_GATE_P2_REVIEW_TO_QUEUE_ENQUEUE_BRIDGE_V1",
            "packet_id": "P2_REVIEW_TO_QUEUE_ENQUEUE_BRIDGE_V1",
            "requested_mode": "APPLY",
            "approved_mode": "APPLY",
            "approval_status": "approved_for_apply",
            "approved_by_human": True,
            "approval_authority": "Anthony / Human Owner",
            "approved_by": "Anthony / Human Owner",
            "approval_timestamp_utc": "2026-06-10T15:20:28Z",
            "allowed_paths": ["automation/orchestration/work_packets/"],
            "blocked_paths": ["automation/orchestration/work_packets/active/"],
            "validator_chain_required": True,
            "commit_package_required": True,
            "approval_evidence": {
                "type": "HMAC_SHA256",
                "approval_nonce": "queue-specific-test",
                "approval_hmac_sha256": "test",
            },
        },
    )
    _write_json(
        approval_inbox,
        {
            "schema": "AIOS_APPROVAL_INBOX.v1",
            "approval_gate_id": "APPROVAL_INBOX_001",
            "authority_status": "active_authority",
            "approval_status": "completed",
            "approved_by_human": True,
            "approval_authority": "Anthony / Human Owner",
            "validator_chain_required": True,
            "commit_package_required": True,
        },
    )

    evidence = adapter.build_queue_mutation_approval_evidence(
        repo_root=repo_root,
        target_packet_id="P2_REVIEW_TO_QUEUE_ENQUEUE_BRIDGE_V1",
    )

    assert evidence["approval_gate_selected_from_queue_specific"] is True
    assert evidence["approval_gate_path_used"].endswith(
        "APPLY_APPROVAL_GATE_P2_REVIEW_TO_QUEUE_ENQUEUE_BRIDGE_V1.json"
    )
    assert evidence["approval_gate_packet_mismatch"] is False
    assert evidence["explicit_approval"] is True
    assert evidence["approval_granted"] is True


def test_p2_bridge_embeds_pending_approval_evidence_and_queue_gate_consumes_it(tmp_path):
    mod = _load()
    queue_gate = _load_queue_gate()
    repo_root = tmp_path / "repo"
    _build_repo_with_reports(repo_root)

    output_dir = repo_root / "Reports" / "p2_enqueue_bridge"
    report = mod.build_p2_enqueue_bridge_report(
        repo_root=repo_root,
        output_dir=output_dir,
        now="2026-01-02T03:04:05Z",
        evidence=_ready_evidence(),
    )
    preview = report["proposed_queue_item_preview"]
    approval_evidence = preview["approval_evidence"]
    assert approval_evidence["approval_status"] == "pending_review"
    assert approval_evidence["source_files"]
    assert "automation/orchestration/approval_inbox/APPLY_APPROVAL_GATE_001.json" in " ".join(approval_evidence["source_files"])
    assert approval_evidence["explicit_approval"] is False
    assert approval_evidence["explicit_apply_approved"] is False
    assert approval_evidence["target_packet_id"] == "P2_REVIEW_TO_QUEUE_ENQUEUE_BRIDGE_V1"
    assert approval_evidence["approval_gate_packet_id"] != "P2_REVIEW_TO_QUEUE_ENQUEUE_BRIDGE_V1"
    assert approval_evidence["approval_gate_packet_mismatch"] is True
    assert "does not match target_packet_id" in approval_evidence["non_authorizing_reason"]

    output_path = output_dir / mod.REPORT_JSON_NAME
    mod.write_p2_enqueue_bridge_reports(report, output_dir=output_dir)

    protected_paths = [
        repo_root / "automation" / "orchestration" / "work_packets" / "active",
        repo_root / "automation" / "orchestration" / "workers" / "inbox" / "AIOS_WORKER_INBOX.json",
    ]
    before = {str(path): _fingerprint(path) for path in protected_paths}
    gate_report = queue_gate.run_queue_mutation_gate(
        repo_root=repo_root,
        proposed_item_path=output_path,
        output_dir=tmp_path / "Reports" / "queue_mutation_gate",
        now="2026-01-02T03:04:05Z",
    )
    after = {str(path): _fingerprint(path) for path in protected_paths}

    assert before == after
    assert gate_report["gate_status"] == queue_gate.BLOCKED
    assert gate_report["approval_check"]["approval_evidence_present"] is True
    assert gate_report["approval_check"]["explicit_approval"] is False
    assert gate_report["approval_check"]["approval_gate_packet_mismatch"] is True
    assert "approval evidence is not explicit" in gate_report["validation"]["blockers"]
    assert "approval evidence packet_id does not match proposed queue packet_id" in gate_report["validation"]["blockers"]
    assert gate_report["queue_write_allowed"] is False
    assert gate_report["canonical_queue_mutated"] is False


def test_missing_evidence_is_invalid_not_ready(tmp_path):
    mod = _load()
    report = mod.build_p2_enqueue_bridge_report(
        repo_root=tmp_path,
        output_dir=tmp_path / "Reports" / "p2_enqueue_bridge",
        now="2026-01-02T03:04:05Z",
    )
    assert report["bridge_status"] == "INVALID"
    assert report["evidence_missing"]
    assert report["validation"]["status"] == "PASS"
    assert report["proposed_queue_item_preview"]["enqueue_allowed"] is False


def test_validation_blocks_dangerous_tamper(tmp_path):
    mod = _load()
    report = mod.build_p2_enqueue_bridge_report(
        repo_root=REPO_ROOT,
        output_dir=tmp_path / "Reports" / "p2_enqueue_bridge",
        now="2026-01-02T03:04:05Z",
    )
    tampered = deepcopy(report)
    tampered["queue_mutation_allowed"] = True
    tampered["proposed_queue_item_preview"]["enqueue_allowed"] = True
    validation = mod.validate_p2_enqueue_bridge_report(tampered)
    assert validation["status"] == "BLOCK"
    assert any("queue_mutation_allowed" in blocker for blocker in validation["blockers"])
    assert any("enqueue_allowed" in blocker for blocker in validation["blockers"])


def test_ready_status_with_blockers_is_blocked_by_validator(tmp_path):
    mod = _load()
    report = mod.build_p2_enqueue_bridge_report(
        repo_root=REPO_ROOT,
        output_dir=tmp_path / "Reports" / "p2_enqueue_bridge",
        now="2026-01-02T03:04:05Z",
    )
    report["bridge_status"] = "READY_FOR_DRY_RUN_PREVIEW"
    validation = mod.validate_p2_enqueue_bridge_report(report)
    assert validation["status"] == "BLOCK"
    assert any("bridge_blockers" in blocker for blocker in validation["blockers"])


def test_bridge_does_not_mutate_canonical_queue_or_worker_inbox(tmp_path):
    mod = _load()
    protected_paths = [COMMAND_QUEUE, WORKER_INBOX, ACTIVE_PACKETS, RUNTIME_TELEMETRY]
    before = {str(path): _fingerprint(path) for path in protected_paths}
    report = mod.run_p2_enqueue_bridge(
        repo_root=REPO_ROOT,
        output_dir=tmp_path / "Reports" / "p2_enqueue_bridge",
        now="2026-01-02T03:04:05Z",
    )
    after = {str(path): _fingerprint(path) for path in protected_paths}
    assert before == after
    assert report["proposed_queue_item_preview"]["canonical_queue_write_allowed"] is False
    assert report["proposed_queue_item_preview"]["worker_inbox_write_allowed"] is False
    assert report["proposed_queue_item_preview"]["active_packet_write_allowed"] is False


def test_cli_defaults_to_dry_run_and_writes_preview(tmp_path, monkeypatch, capsys):
    mod = _load()
    outdir = tmp_path / "Reports" / "p2_enqueue_bridge"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aios_p2_enqueue_bridge",
            "--repo-root",
            str(REPO_ROOT),
            "--output-dir",
            str(outdir),
            "--now",
            "2026-01-02T03:04:05Z",
        ],
    )
    rc = mod.main()
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert rc == 0
    assert parsed["bridge_status"] == "BLOCKED"
    assert (outdir / mod.REPORT_JSON_NAME).exists()
    assert (outdir / mod.REPORT_MD_NAME).exists()
    cli_report = json.loads((outdir / mod.REPORT_JSON_NAME).read_text(encoding="utf-8"))
    approval_evidence = cli_report["proposed_queue_item_preview"]["approval_evidence"]
    assert cli_report["proposed_queue_item_preview"]["approval_evidence"]
    assert approval_evidence["approval_status"] == "pending_review"
    assert approval_evidence["approved_by_human"] is False
    assert approval_evidence["approval_granted"] is False
    assert approval_evidence["approval_gate_selected_from_queue_specific"] is False
    assert approval_evidence["approval_gate_packet_mismatch"] is True
    assert approval_evidence["approval_gate_packet_id"] != "P2_REVIEW_TO_QUEUE_ENQUEUE_BRIDGE_V1"
    assert parsed["enqueue_allowed"] is False


def test_required_evidence_files_exist():
    assert HUMAN_GATE_REPORT.exists()
    assert AUTONOMY_GAP_REPORT.exists()
