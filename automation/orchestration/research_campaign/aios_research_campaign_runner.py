#!/usr/bin/env python3
"""Bounded JSON-only entry point for the local research campaign controller."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .aios_research_campaign import (
    CampaignCheckpointError,
    CampaignSpec,
    CampaignValidationError,
    ExperimentOutcome,
    MAX_OUTCOMES,
    build_checkpoint,
    load_checkpoint,
    read_bounded_json_file,
    run_campaign_cycle,
    score_evidence,
    validate_checkpoint_root,
    write_checkpoint,
)


RUN_RESULT_SCHEMA = "AIOS_RESEARCH_CAMPAIGN_RUN_RESULT.v1"
BLOCKED_CAPABILITIES = {
    "network_access": False,
    "cme_data_acquisition": False,
    "broker_or_oanda_access": False,
    "orders_or_money_movement": False,
    "credentials_or_secrets": False,
    "scheduler_registration": False,
    "daemon_or_worker_launch": False,
    "restart_or_repair": False,
    "queue_lock_or_approval_mutation": False,
    "commit_push_or_merge": False,
    "live_trading_authorization": False,
}


class RunnerInputError(ValueError):
    """Raised for invalid runner input without emitting non-JSON output."""


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path_text: str, label: str) -> Any:
    try:
        return read_bounded_json_file(Path(path_text), label)
    except (CampaignValidationError, TypeError, ValueError) as error:
        raise RunnerInputError(str(error)) from error


def _validate_resume_progress(checkpoint: Mapping[str, Any], now_utc: str) -> None:
    """Refuse suspect saved progress before an APPLY can replace its evidence."""

    try:
        now = datetime.fromisoformat(now_utc.replace("Z", "+00:00"))
        progress = datetime.fromisoformat(
            checkpoint["last_progress_utc"].replace("Z", "+00:00")
        )
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise RunnerInputError("checkpoint resume requires a valid UTC clock") from error
    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise RunnerInputError("checkpoint resume requires an explicit UTC clock")
    age_seconds = (now - progress).total_seconds()
    if age_seconds < 0:
        raise RunnerInputError("campaign_progress_future_timestamp")
    if checkpoint["last_decision"]["status"] in {"ADVANCE", "REJECT"} and (
        age_seconds > checkpoint["progress_max_age_seconds"]
    ):
        raise RunnerInputError("campaign_progress_stale")


def run_once(
    campaign_payload: Mapping[str, Any],
    raw_outcomes: Sequence[Mapping[str, Any]],
    mode: str,
    output_root: str | None,
    now_utc: str,
    paper_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one controller decision with no I/O except explicit APPLY checkpointing."""

    if mode not in {"DRY_RUN", "APPLY"}:
        raise RunnerInputError("mode must be DRY_RUN or APPLY")
    if not isinstance(campaign_payload, Mapping):
        raise RunnerInputError("campaign JSON must be an object")
    if isinstance(raw_outcomes, (str, bytes)) or not isinstance(raw_outcomes, Sequence):
        raise RunnerInputError("outcomes JSON must be an array")
    if len(raw_outcomes) > MAX_OUTCOMES:
        raise RunnerInputError("outcomes JSON exceeds 1000 entries")
    if paper_evidence is not None and not isinstance(paper_evidence, Mapping):
        raise RunnerInputError("paper evidence JSON must be an object")
    try:
        spec = CampaignSpec.from_dict(campaign_payload)
        outcomes = [ExperimentOutcome.from_dict(item) for item in raw_outcomes]
    except (CampaignValidationError, TypeError, ValueError, RecursionError) as error:
        raise RunnerInputError(str(error)) from error

    checkpoint: dict[str, Any] = {"written": False, "path": None}
    try:
        if mode == "APPLY":
            if not isinstance(output_root, str) or not output_root.strip():
                raise RunnerInputError("APPLY requires an explicit output_root sandbox")
            checkpoint_root = validate_checkpoint_root(Path(output_root))
            checkpoint_path = checkpoint_root / "campaign_checkpoint.json"
            if checkpoint_path.is_symlink():
                raise RunnerInputError("checkpoint path must not be a symlink")
            persisted = None
            if checkpoint_path.exists():
                if not checkpoint_path.is_file():
                    raise RunnerInputError("checkpoint path must be a regular file")
                persisted = load_checkpoint(checkpoint_path, spec)
                _validate_resume_progress(persisted, now_utc)
                persisted_outcomes = persisted["outcomes"]
                persisted_history = [
                    outcome.to_dict() for outcome in persisted_outcomes
                ]
                supplied_history = [outcome.to_dict() for outcome in outcomes]
                if outcomes and (
                    len(supplied_history) < len(persisted_history)
                    or supplied_history[: len(persisted_history)] != persisted_history
                ):
                    raise RunnerInputError(
                        "APPLY outcomes conflict with the persisted checkpoint history"
                    )
                if not outcomes:
                    outcomes = persisted_outcomes
                if paper_evidence is None:
                    paper_evidence = persisted["routing_context"]["route_inputs"].get(
                        "paper_evidence"
                    )
            decision = run_campaign_cycle(spec, outcomes, now_utc, paper_evidence)
            evidence_score = score_evidence(spec, paper_evidence or {})
            if mode == "APPLY":
                payload = build_checkpoint(
                    spec,
                    outcomes,
                    decision,
                    now_utc,
                    previous_checkpoint=persisted,
                    paper_evidence=paper_evidence,
                )
                path = write_checkpoint(
                    checkpoint_root,
                    payload,
                    expected_digest=persisted["digest"] if persisted is not None else None,
                )
                checkpoint = {"written": True, "path": str(path)}
        else:
            decision = run_campaign_cycle(spec, outcomes, now_utc, paper_evidence)
            evidence_score = score_evidence(spec, paper_evidence or {})
    except RunnerInputError:
        raise
    except (
        CampaignCheckpointError,
        CampaignValidationError,
        TypeError,
        RecursionError,
    ) as error:
        raise RunnerInputError(str(error)) from error

    return {
        "schema": RUN_RESULT_SCHEMA,
        "mode": mode,
        "decision": decision.to_dict(),
        "checkpoint": checkpoint,
        "evidence_score": evidence_score,
        "paper_edge_gate": decision.paper_edge_gate,
        "live_authorization": False,
        "safety": {
            "blocked_capabilities": BLOCKED_CAPABILITIES,
            "live_authorization": False,
            "runner_starts_scheduler": False,
            "runner_starts_daemon": False,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one local AIOS research campaign decision as JSON only."
    )
    parser.add_argument("--campaign-json", required=True)
    parser.add_argument("--outcomes-json", required=True)
    parser.add_argument("--mode", default="DRY_RUN")
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--paper-evidence-json", default=None)
    parser.add_argument(
        "--now-utc",
        default=None,
        help="Optional UTC timestamp for deterministic fixture execution.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        now_utc = args.now_utc or _utc_now_text()
        paper_evidence = (
            _read_json(args.paper_evidence_json, "paper evidence JSON")
            if args.paper_evidence_json is not None
            else None
        )
        if args.paper_evidence_json is not None and not isinstance(paper_evidence, Mapping):
            raise RunnerInputError("paper evidence JSON must be an object")
        result = run_once(
            _read_json(args.campaign_json, "campaign JSON"),
            _read_json(args.outcomes_json, "outcomes JSON"),
            args.mode,
            args.output_root,
            now_utc,
            paper_evidence,
        )
    except RunnerInputError as error:
        result = {
            "schema": RUN_RESULT_SCHEMA,
            "mode": args.mode,
            "status": "BLOCKED",
            "reason": str(error),
            "live_authorization": False,
        }
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
