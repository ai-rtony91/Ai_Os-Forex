{
  "branch": "lane/forex-final-review-decision-gate-v1",
  "event_count": 6,
  "events": [
    {
      "blockers": [],
      "metadata": {
        "lane": "forex_final_review_decision_orchestrator_v1"
      },
      "notes": [
        "lane orchestration started"
      ],
      "route": null,
      "stage": "initialized",
      "status": "STARTED",
      "timestamp": "2026-08-26T01:10:00.510831+00:00"
    },
    {
      "blockers": [
        "loader_status:SAFETY_REJECTED"
      ],
      "metadata": {
        "record_count": 73
      },
      "notes": [
        "loaded final review evidence"
      ],
      "route": null,
      "stage": "evidence_loader",
      "status": "SAFETY_REJECTED",
      "timestamp": "2026-08-26T01:10:00.510831+00:00"
    },
    {
      "blockers": [],
      "metadata": {
        "match_count": 0
      },
      "notes": [
        "boundary_verification:BOUNDARY_CLEAN"
      ],
      "route": "ROUTE_OWNER_EVIDENCE_REQUIRED",
      "stage": "protected_boundary_verification",
      "status": "BOUNDARY_CLEAN",
      "timestamp": "2026-08-26T01:10:00.510831+00:00"
    },
    {
      "blockers": [
        "sample_count below minimum 30",
        "sample_count below minimum 30",
        "sample_count below minimum 30",
        "sample_count below minimum 30",
        "strict mode requires explicit owner confirmation",
        "sample_count below minimum 30"
      ],
      "metadata": {
        "next_safe_actions": [
          "Remove sensitive assignment text and command references",
          "Re-run evidence loading and decision gate"
        ]
      },
      "notes": [
        "final_review_status:FINAL_REVIEW_SAFETY_BLOCKED"
      ],
      "route": "ROUTE_OWNER_EVIDENCE_REQUIRED",
      "stage": "final_review_gate",
      "status": "ORCHESTRATOR_SAFETY_BLOCKED",
      "timestamp": "2026-08-26T01:10:00.510831+00:00"
    },
    {
      "blockers": [],
      "metadata": {},
      "notes": [
        "handoff_status:DEMO_HANDOFF_SAFETY_BLOCKED"
      ],
      "route": null,
      "stage": "demo_readiness_handoff",
      "status": "DEMO_HANDOFF_SAFETY_BLOCKED",
      "timestamp": "2026-08-26T01:10:00.510831+00:00"
    },
    {
      "blockers": [],
      "metadata": {},
      "notes": [
        "authority_status:OWNER_AUTHORITY_SAFETY_BLOCKED"
      ],
      "route": null,
      "stage": "owner_authority_gate",
      "status": "OWNER_AUTHORITY_SAFETY_BLOCKED",
      "timestamp": "2026-08-26T01:10:00.510831+00:00"
    }
  ],
  "generated_at": "2026-08-26T01:10:00.510831+00:00",
  "lane": "forex_final_review_decision_orchestrator_v1",
  "ledger_version": "1.0",
  "packet_id": "AIOS-FOREX-FINAL-REVIEW-DECISION-ORCHESTRATOR-V1",
  "worktree": "C:\\Dev\\Ai.Os"
}