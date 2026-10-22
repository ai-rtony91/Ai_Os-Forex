"""One bounded connection through the existing Optuna, S6 and paper owners.

This module owns no admission, scheduler, scientific scorer or budget. Its saved
catalog is an immutable consistency record; its cycle checkpoint is a disposable
projection. Native permission still comes from the existing signed owner session,
global ledger and supervisor. A loss is told unchanged before the next proposal.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from .factory_paper_handoff import check_factory_paper_handoff, run_synthetic_paper_wiring_smoke
from .optuna_campaign_budget import CampaignBudgetBridge
from .optuna_research import OptunaResearchSearch
from .optuna_s6_bridge import OptunaS6Bridge, PinnedS6Evaluator, _copy, _digest, _json, _save_once


_GATES = {"CAMPAIGN_BUDGET_EXCEEDED", "CAMPAIGN_DEADLINE_REACHED",
          "ORIGINAL_INTEGRITY_STOP_UNRESOLVED", "INTEGRITY_EVIDENCE_REQUIRED",
          "EVALUATION_BUDGET_REACHED", "PROPOSAL_BUDGET_REACHED_NOT_NO_EDGE",
          "RECEIPT_RECOVERY_REQUIRED_NOT_REPLAY", "AMBIGUOUS_ATTEMPT_OR_SETTLED_JOB_NO_REPLAY",
          "UNIQUE_UNCHANGED_FROZEN_CATALOG_MATCH_REQUIRED",
          "ECONOMIC_JOB_ALREADY_RESERVED", "HISTORICAL_ECONOMIC_JOB_ALREADY_EXAMINED"}


def _check_owners(budget, evaluator, engineering):
    if type(budget) is not CampaignBudgetBridge:
        raise RuntimeError("EXISTING_GLOBAL_CAMPAIGN_BUDGET_REQUIRED")
    if evaluator is None:
        raise RuntimeError("S6_EVALUATOR_REQUIRED")
    if type(engineering) is not bool:
        raise ValueError("EXPLICIT_FACTORY_PROVENANCE_MODE_REQUIRED")
    if engineering:
        if getattr(evaluator, "engineering_only", None) is not True:
            raise PermissionError("EXPLICIT_ENGINEERING_ADAPTER_REQUIRED")
        if budget.noncanonical_copy is not True:
            raise PermissionError("ENGINEERING_COPY_BUDGET_REQUIRED")
    else:
        if type(evaluator) is not PinnedS6Evaluator:
            raise PermissionError("PINNED_NATIVE_S6_ADAPTER_REQUIRED")
        if budget.noncanonical_copy is not False:
            raise PermissionError("CANONICAL_GLOBAL_RESERVATION_REQUIRED")
        # Authenticate an already-created owner session before creating a study.
        # Publish is also the recovery operation; dispatch is checked by the S6
        # bridge and the original budget owner immediately before new work.
        evaluator._check_native("publish")


def _catalog(value, parameter_bindings):
    if not isinstance(value, list) or not value or any(not isinstance(job, dict) for job in value):
        raise ValueError("EXPLICIT_FROZEN_S6_CATALOG_REQUIRED")
    if (not isinstance(parameter_bindings, dict) or not parameter_bindings
            or any(not isinstance(path, list) or not path or
                   any(not isinstance(key, str) for key in path) for path in parameter_bindings.values())):
        raise ValueError("EXACT_PARAMETER_BINDINGS_REQUIRED")
    jobs = _copy(value)
    ids = [job.get("candidate_id") for job in jobs]
    if any(not isinstance(identity, str) or not identity for identity in ids) or len(set(ids)) != len(ids):
        raise ValueError("UNIQUE_FROZEN_CATALOG_IDENTITIES_REQUIRED")
    return jobs, _copy(parameter_bindings)


def _select(proposal, catalog, parameter_bindings):
    if set(proposal["params"]) != set(parameter_bindings):
        raise ValueError("EXACT_PARAMETER_BINDINGS_REQUIRED")
    matches = []
    for job in catalog:
        values = {}
        try:
            for name, path in parameter_bindings.items():
                value = job
                for key in path:
                    value = value[key]
                values[name] = value
        except (KeyError, TypeError):
            continue
        if _json(values) == _json(proposal["params"]):
            matches.append(job)
    if len(matches) != 1:
        raise RuntimeError("UNIQUE_UNCHANGED_FROZEN_CATALOG_MATCH_REQUIRED")
    return _copy(matches[0])


def _freeze(directory, catalog, bindings):
    path = directory / "factory-frozen-catalog.json"
    frozen = {"schema": "AIOS_FACTORY_CATALOG_CONSISTENCY_V1", "catalog": catalog,
              "parameter_bindings": bindings, "authority": False}
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != frozen:
        raise ValueError("FROZEN_FACTORY_CATALOG_CHANGED")
    _save_once(path, frozen)


def _projection(directory, value):
    # Never read this as permission, a receipt, a budget or a recovery source.
    path = directory / "factory-cycle-projection.json"
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                     prefix=".factory-projection-", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(_json(value))
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _budget_blocker(budget, catalog):
    summary = budget.summary()
    exposures = [(job.get("configuration_count"), job.get("physical_call_reservation")) for job in catalog]
    if all(type(configurations) is int and type(calls) is int and configurations > 0 and calls > 0
           for configurations, calls in exposures):
        if not any(configurations <= summary["configurations_remaining"] and
                   calls <= summary["physical_calls_remaining_conservative"]
                   for configurations, calls in exposures):
            return "CAMPAIGN_BUDGET_EXCEEDED"
    return None


def _envelope(search, budget, engineering):
    return {"schema": "AIOS_BOUNDED_FACTORY_CYCLE_V1",
            "mode": "ENGINEERING_DRY_RUN" if engineering else "EXISTING_OWNER_DEVELOPMENT",
            "checkpoint_authority": False, "summary": search.summary(), "global_budget": budget.summary(),
            "market_evaluator_calls": 0, "verified_edge": False, "paper_ready": False,
            "live_ready": False, "execution_allowed": False}


def run_optuna_factory_cycle(directory, manifest, catalog, *, parameter_bindings,
                             budget=None, evaluator=None, engineering=False,
                             paper_payload=None, artifact_verifier=None):
    """Accept or recover one frozen development job, then propose bounded work.

    The caller supplies already-open, existing owner adapters. A missing native
    session or canonical global budget blocks before study creation. Engineering
    is explicit and can only allocate a noncanonical ledger copy. No callback can
    stand in for the native evaluator. The S6 bridge authenticates durable core
    receipts on recovery and never evaluates a started job again. The returned
    paper check is evidence for the existing review gate, never paper authority.
    """
    _check_owners(budget, evaluator, engineering)
    jobs, bindings = _catalog(catalog, parameter_bindings)
    if not engineering and jobs != evaluator.authority._gate["research_scope"].get("jobs"):
        raise PermissionError("EXACT_SIGNED_FULL_CATALOG_REQUIRED")
    with OptunaResearchSearch(directory, manifest) as search:
        bridge = OptunaS6Bridge(search, budget, evaluator, engineering=engineering)
        bridge._check()
        _freeze(search._directory, jobs, bindings)
        # Search reopening may already finish a saved search receipt. Locate
        # undelivered started work by the authenticated study proposal, rather
        # than treating absence of a RUNNING trial as permission for new work.
        undelivered = [trial for trial in search._study.trials
            if (search._directory / f"s6-started-{trial.number}.json").exists()
            and not (search._directory / f"factory-handoff-{trial.number}.json").exists()]
        recovering = bool(undelivered)
        progression = []
        try:
            if not recovering:
                blocker = _budget_blocker(budget, jobs)
                if blocker:
                    raise RuntimeError(blocker)
            proposal = search._proposal(undelivered[0]) if recovering else search.ask()
            spec = _select(proposal, jobs, bindings)
            progression.append("SAVED_ACCEPTANCE_RECOVERY" if recovering else "PROPOSED")
            if recovering:
                try:
                    artifact = bridge.recover(proposal["trial_number"], spec, parameter_bindings=bindings)
                except FileNotFoundError as error:
                    raise RuntimeError("ACCEPTED_RECEIPT_RECOVERY_REQUIRED_NO_REDISPATCH") from error
            else:
                artifact = bridge.run(spec, parameter_bindings=bindings)
                progression.append("GLOBAL_BUDGET_STARTED")
            progression.extend(["CORE_RECEIPT_ACCEPTED", "OPTUNA_TOLD"])
        except (RuntimeError, ValueError) as error:
            if str(error) not in _GATES | {"ACCEPTED_RECEIPT_RECOVERY_REQUIRED_NO_REDISPATCH"}:
                raise
            result = {**_envelope(search, budget, engineering), "status": "BLOCKED", "blocker": str(error),
                      "progression": progression, "next_proposal": None}
            _projection(search._directory, result)
            return result

        payload = _copy(paper_payload) if isinstance(paper_payload, dict) else {}
        # The upstream accepted artifact is always supplied directly. An external
        # payload cannot replace its frozen lineage with a different receipt.
        payload["research_artifact"] = artifact
        handoff = check_factory_paper_handoff(payload, artifact_verifier=artifact_verifier)
        # Delivery consistency only: this record cannot admit a job or establish
        # readiness. On recovery the S6 bridge still reauthenticates core bytes.
        _save_once(search._directory / f"factory-handoff-{proposal['trial_number']}.json",
                   {"schema": "AIOS_FACTORY_HANDOFF_DELIVERY_V1", "authority": False,
                    "trial_number": proposal["trial_number"], "proposal_hash": proposal["proposal_hash"],
                    "research_artifact_sha256": _digest(artifact), "handoff": handoff})
        progression.append("PAPER_HANDOFF_CHECK_PASSED" if handoff["engineering_handoff_passed"] else "PAPER_HANDOFF_BLOCKED")
        continuation_blocker = _budget_blocker(budget, jobs)
        next_proposal = None
        if continuation_blocker is None:
            try:
                next_proposal = search.ask()
                _select(next_proposal, jobs, bindings)
                progression.append("NEXT_PROPOSAL")
            except (RuntimeError, ValueError) as error:
                if str(error) not in _GATES:
                    raise
                continuation_blocker = str(error)
                next_proposal = None
        result = {**_envelope(search, budget, engineering),
                  "status": "RECOVERED_ACCEPTED_DEVELOPMENT" if recovering else "ACCEPTED_DEVELOPMENT",
                  "bridge_artifact": artifact, "handoff": handoff,
                  "market_evaluator_calls": 0 if recovering else artifact["market_evaluator_calls"],
                  "progression": progression, "next_proposal": next_proposal,
                  "continuation_blocker": continuation_blocker}
        if engineering:
            result["synthetic_paper_wiring"] = run_synthetic_paper_wiring_smoke(research_artifact=artifact)
        _projection(search._directory, result)
        return result
