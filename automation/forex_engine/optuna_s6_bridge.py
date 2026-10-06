"""Optuna ordering inside an unchanged, genuinely admitted S6 finite catalog.

This is not an authority, signer, market loader, scorer replacement, or ledger.
``PinnedS6Evaluator`` uses an existing OwnerSession and live native supervisor
from ``research_binding.build_market_session``. Its ready-policy wrapper keeps
the native policy and chooses one already-signed unit. The public supervisor
``run(max_cycles=1, max_units=1)`` still owns leases, dispatch, and core receipts.

The signed research scope must additionally bind ``optuna`` with exactly the
contract, parameter-mapping and frozen-objective hashes. Old macro approvals
cannot authorize this route. No adapter or genuine session means no dispatch.
Engineering doubles require an explicit separate mode and always report zero
market calls. Hash seals on bridge artifacts are consistency checks; genuine
provenance comes from the existing owner, core store and S6 acceptance journal.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import weakref


_HASH = re.compile(r"[0-9a-f]{64}\Z")
_SCENARIOS = ("BASE", "STRESSED", "SEVERE_BUT_PLAUSIBLE")
_OBJECTIVE = {"kind": "S6_STRESSED_NET_USD_V1"}
_REQUEST_IDENTITIES = ("job_id", "proposal_hash", "spec_sha256", "economic_sha256",
                       "input_sha256", "source_sha256", "scope_sha256",
                       "configurations", "physical_calls")
_NATIVE_CONTROLLERS = weakref.WeakKeyDictionary()
_NATIVE_DISPATCHES = {}
_NATIVE_USED_STARTS = weakref.WeakKeyDictionary()
_NATIVE_DISPATCH_GUARD = threading.RLock()


def _require_native_methods(evaluator):
    if type(evaluator) is not PinnedS6Evaluator or any(name in vars(evaluator) for name in
            ("_check_native", "bind_controller", "_bound_controller", "preflight", "authorize_campaign_budget",
             "read_campaign_integrity", "require_dispatch_permit", "evaluate", "_ready_policy",
             "verify_result", "load_saved_result", "_supported_scope")):
        raise PermissionError("NATIVE_ADMISSION_METHOD_SUBSTITUTED")


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _copy(value):
    return json.loads(_json(value))


def _hash(value):
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _utc(value):
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return stamp.astimezone(timezone.utc)


def _save_once(path, value):
    """Evidence only, written under the existing Optuna directory writer lock."""
    raw = _json(value)
    if path.exists():
        if _json(json.loads(path.read_text())) != raw:
            raise ValueError("S6_EVIDENCE_CONFLICT")
        return
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=".s6-pending-", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temporary, path)
        # Persist the rename as well as the content on systems that support it.
        if os.name != "nt":
            fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    finally:
        temporary.unlink(missing_ok=True)


def _input_pins(spec):
    pins = {}
    maps = [{s["path"]: s["sha256"] for s in spec["price_shards"]},
            spec.get("history", {}).get("covered", {}), spec.get("entry_admission_evidence", {})]
    maps.extend(c.get("evidence_hashes", {}) for c in spec["contracts"].values())
    if "gap_audit_path" in spec:
        maps.append({spec["gap_audit_path"]: spec["gap_audit_sha256"]})
    for mapping in maps:
        if not isinstance(mapping, dict):
            raise ValueError("INPUT_PIN_MAP_REQUIRED")
        for path, pin in mapping.items():
            if not isinstance(path, str) or not _hash(pin):
                raise ValueError("EXACT_INPUT_PINS_REQUIRED")
            if path in pins and pins[path] != pin:
                raise ValueError("INPUT_PIN_CONFLICT")
            pins[path] = pin
    return pins


def _accepted_core_receipt(store, run_id, candidate_id):
    """Inspect already-open canonical core tables; this alone grants no authority."""
    if store.run_id != run_id:
        raise ValueError("CORE_RECEIPT_NOT_AUTHENTICALLY_ACCEPTED")
    rows = store.conn.execute("""SELECT r.*, u.stage_id, u.run_id AS unit_run_id,
        u.status AS unit_status, u.output_hash AS unit_output_hash,
        u.output_path_published AS unit_output_path, u.lease_generation AS unit_generation,
        a.unit_id AS attempt_unit_id, a.status AS attempt_status,
        a.output_hash AS attempt_output_hash, a.lease_generation AS attempt_generation
        FROM receipts r JOIN units u ON u.unit_id=r.unit_id
        JOIN attempts a ON a.attempt_id=r.attempt_id
        WHERE r.run_id=? AND u.stage_id=?""", (run_id, candidate_id)).fetchall()
    if len(rows) != 1:
        raise ValueError("ONE_AUTHENTIC_CORE_RECEIPT_REQUIRED")
    core = dict(rows[0])
    if (core["status"] != "ACCEPTED" or core["unit_status"] != "COMPLETED" or
            core["attempt_status"] != "SUCCESS" or core["unit_run_id"] != core["run_id"] or
            core["attempt_unit_id"] != core["unit_id"] or
            core["output_hash"] != core["unit_output_hash"] or
            core["output_hash"] != core["attempt_output_hash"] or
            core["unit_output_path"] != core["output_path"] or
            core["lease_generation"] != core["unit_generation"] or
            core["lease_generation"] != core["attempt_generation"]):
        raise ValueError("CORE_RECEIPT_NOT_AUTHENTICALLY_ACCEPTED")
    return core


def _claimed_context_identity(supervisor, unit, context, *, attempt_directory):
    """Pinned core claims first attempt zero; its receipt is recorded afterwards."""
    try:
        expected_output = attempt_directory(unit["output_path"], unit["lease_token"]) / (
            context.attempt_id + Path(unit["output_path"]).suffix)
        return (unit["status"] == "RUNNING" and int(unit["attempts"]) == 0 and
            context.run_id == supervisor.run_id and context.stage_id == unit["stage_id"] and
            context.unit_id == unit["unit_id"] and context.shard_id == unit["shard_id"] and
            type(context.unit_attempt) is int and context.unit_attempt == 0 and
            isinstance(context.attempt_id, str) and re.fullmatch(r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}", context.attempt_id) is not None and
            context.worker_token == unit["lease_owner"] and isinstance(context.worker_token, str) and
            context.worker_token.startswith(supervisor.controller_id + ":") and
            re.fullmatch(r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}",
                         context.worker_token[len(supervisor.controller_id) + 1:]) is not None and
            context.job_token == unit["lease_token"] and bool(unit["lease_token"]) and
            type(unit["lease_generation"]) is int and unit["lease_generation"] > 0 and
            _number(unit["lease_expires_at"]) and unit["lease_expires_at"] > datetime.now(timezone.utc).timestamp() and
            Path(context.work_root).resolve() == Path(supervisor.state_root).resolve().parent and
            Path(context.input_path).resolve() == Path(unit["input_path"]).resolve() and
            Path(context.output_path).resolve() == Path(expected_output).resolve())
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def _continue_native_window(supervisor, authority, binding):
    """Use supported resume only for our exact completed caller window.

    Called after native construction/source/owner/receipt checks and before the
    next global reservation. Integrity, deadline, owner and unknown pauses stay
    blocked. This changes lifecycle state only; it never evaluates market rows.
    """
    checkpoint = supervisor.store.load_checkpoint()
    if checkpoint.get("state") in {"RUNNING", "PENDING"} and checkpoint.get("mode") in {"ACTIVE", "RUNNING", "PENDING"}:
        return False
    try:
        continuation = json.loads(supervisor.state.message)
    except (TypeError, ValueError):
        continuation = {}
    stop = supervisor.stop_reason
    if (checkpoint.get("state") != "PAUSED" or checkpoint.get("mode") != "RESOURCE_LIMIT" or
            continuation.get("state") != "RESOURCE_LIMIT" or
            continuation.get("reason") != "caller_bounded_execution_window" or
            not isinstance(stop, dict) or stop != continuation.get("stop_reason") or
            stop.get("class") != "RESOURCE_TIME_BLOCK" or stop.get("code") != "caller_bounded_execution_window" or
            stop.get("owner_action_needed") is not False):
        raise PermissionError("NATIVE_STOP_REQUIRES_OWNER_RECOVERY")
    progress = supervisor.store.load_progress()
    if any(progress.get(key, 0) for key in ("running", "failed", "retry_ready")):
        raise PermissionError("NATIVE_STOP_REQUIRES_OWNER_RECOVERY")
    authority.check("resume")
    binding.require_classified_market_resume(supervisor)
    result = supervisor.resume()
    current = supervisor.store.load_checkpoint()
    if result.get("status") != "resumed" or current.get("state") != "RUNNING" or current.get("mode") != "RUNNING":
        raise PermissionError("NATIVE_SUPPORTED_RESUME_REQUIRED")
    return True


def _native_session_origin(binding, authority, supervisor, *, ready_policy=None):
    """Require the exact live builder registry, signed manifest and core DB."""
    record = getattr(binding, "_MARKET_SESSIONS", {}).get(id(supervisor))
    if (not isinstance(record, dict) or record.get("authority") is not authority or
            record.get("supervisor") is not supervisor or record.get("store") is not supervisor.store):
        raise PermissionError("NATIVE_BUILDER_SESSION_REQUIRED")
    manifest = Path(supervisor.manifest_path).resolve()
    if record.get("manifest_path") != str(manifest) or not manifest.is_relative_to(binding.ROOT.resolve()):
        raise PermissionError("NATIVE_BUILDER_SESSION_REQUIRED")
    manifest_sha = binding.sha(manifest)
    identity = binding.digest({"manifest": manifest_sha, "sources": authority._gate["source_hashes"],
                               "revision": binding.approval_identity()["revision"]})
    expected_root = (binding.ROOT / "tests" / ("market_" + identity)).resolve()
    native_ready = record.get("ready_policy")
    current_ready = native_ready if ready_policy is None else ready_policy
    if (record.get("manifest_path") != str(manifest) or record.get("manifest_sha256") != manifest_sha or
            authority._gate["research_scope"].get("manifest_sha256") != manifest_sha or
            Path(supervisor.state_root).resolve() != expected_root or
            record.get("state_root") != str(expected_root) or
            Path(supervisor.store.state_root).resolve() != expected_root or
            Path(supervisor.store.sqlite_path).resolve() != expected_root / "state.db" or
            record.get("run_id") != supervisor.run_id or supervisor.store.run_id != supervisor.run_id or
            supervisor.manifest.run_id != supervisor.run_id or supervisor.ready_policy != current_ready or
            not callable(native_ready) or
            Path(inspect.getsourcefile(native_ready)).resolve() != Path(binding.__file__).resolve()):
        raise PermissionError("NATIVE_BUILDER_SESSION_REQUIRED")
    databases = supervisor.store.conn.execute("PRAGMA database_list").fetchall()
    main = [row[2] for row in databases if row[1] == "main"]
    if len(main) != 1 or not main[0] or Path(main[0]).resolve() != expected_root / "state.db":
        raise PermissionError("NATIVE_BUILDER_SESSION_REQUIRED")
    return record


class PinnedS6Evaluator:
    """Concrete adapter for the native S6 owner/supervisor receipt contract.

    The caller supplies a session already verified by the installed owner.
    This class never constructs an OwnerSession, reads a key, or approves a gate.
    Construction alone does not touch the native store or evaluate anything.
    """
    engineering_only = False

    def __init__(self, binding, authority, supervisor, *, objective_contract=None):
        self.binding, self.authority, self.supervisor = binding, authority, supervisor
        self.objective_contract = _copy(objective_contract or _OBJECTIVE)
        self._selection = None
        self._proposal = None
        self._bound_binding = None
        self._recovery_selection = None
        self._native_ready_policy = None

    def _check_native(self, operation):
        b, authority, supervisor = self.binding, self.authority, self.supervisor
        if authority is None or type(authority) is not b.OwnerSession:
            raise PermissionError("GENUINE_MARKET_SESSION_REQUIRED")
        # The native check rejects a forged instance before any import/store work.
        if any(name in vars(authority) for name in ("check", "check_input", "check_inputs")):
            raise PermissionError("OWNER_SESSION_METHOD_SUBSTITUTED")
        b.OwnerSession.check(authority, operation)
        path = Path(b.__file__).resolve()
        if (sys.modules.get("research_binding") is not b or
                Path(inspect.getfile(b.OwnerSession)).resolve() != path or
                b.sha(path) != b._LOADED_SOURCE_SHA or
                authority._gate["source_hashes"].get(str(path)) != b._LOADED_SOURCE_SHA):
            raise PermissionError("PINNED_S6_BINDING_REQUIRED")
        for name in ("optuna_s6_bridge.py", "optuna_research.py", "optuna_campaign_budget.py"):
            own = Path(__file__).resolve().with_name(name)
            if authority._gate["source_hashes"].get(str(own)) != b.sha(own):
                raise PermissionError("SIGNED_OPTUNA_BRIDGE_SOURCE_REQUIRED")
        sources = b.required_launch_sources()
        if any(authority._gate["source_hashes"].get(path) != pin for path, pin in sources.items()):
            raise PermissionError("COMPLETE_SIGNED_IMPORT_CLOSURE_REQUIRED")
        Supervisor, _, _ = b.runtime_dependencies()
        if (not isinstance(supervisor, Supervisor) or
                type(supervisor.approval_validator) is not b.StageAdmission or
                supervisor.approval_validator.authority is not authority):
            raise PermissionError("EXISTING_ADMITTED_SUPERVISOR_REQUIRED")
        record = _native_session_origin(b, authority, supervisor,
                                        ready_policy=self._ready_policy if self._native_ready_policy is not None else None)
        if self._native_ready_policy is not None and record["ready_policy"] is not self._native_ready_policy:
            raise PermissionError("NATIVE_BUILDER_SESSION_REQUIRED")
        integrity = supervisor.store.reconcile_durable_state()
        if any(integrity.get(k, 0) for k in ("missing", "mismatched", "missing_receipts", "conflicting_receipts")):
            raise ValueError("CORE_DURABLE_INTEGRITY_BLOCKED")
        checkpoint = supervisor.store.load_checkpoint()
        if checkpoint.get("mode") == "SAFETY_STOP":
            raise PermissionError("ORIGINAL_SAFETY_STOP_REQUIRES_OWNER_RECOVERY")
        return sources

    def bind_controller(self, controller):
        """Capture only the actual source-bound factory and canonical owners."""
        _require_native_methods(self)
        self._check_native("construct")
        from .optuna_research import OptunaResearchSearch
        from .optuna_campaign_budget import CampaignBudgetBridge
        if (type(controller) is not OptunaS6Bridge or controller.engineering is not False or
                controller.evaluator is not self or type(controller.search) is not OptunaResearchSearch or
                type(controller.budget) is not CampaignBudgetBridge or
                controller.budget.noncanonical_copy is not False or controller.budget.native_evaluator is not self or
                controller.budget.core_store is not self.supervisor.store or
                any(name in vars(controller) for name in ("_check", "_binding", "_request", "_begin_reserved",
                    "_validate_verified", "_artifact", "_save_accepted", "run", "recover")) or
                any(name in vars(controller.search) for name in ("_check_open", "_proposal", "_make_proposal", "_path"))):
            raise PermissionError("BOUND_NATIVE_FACTORY_CONTROLLER_REQUIRED")
        OptunaResearchSearch._check_open(controller.search)
        scope = self.authority._gate["research_scope"]
        if controller.search.contract_hash != scope.get("optuna", {}).get("contract_sha256"):
            raise PermissionError("MATCHING_SIGNED_OPTUNA_DOMAIN_REQUIRED")
        previous = _NATIVE_CONTROLLERS.get(self)
        previous_controller = previous() if previous is not None else None
        active = _NATIVE_DISPATCHES.get(id(self.supervisor))
        if (previous_controller is not None and previous_controller is not controller or
                active is not None and active.get("controller") is not controller):
            raise PermissionError("NATIVE_FACTORY_CONTROLLER_ALREADY_BOUND")
        record = self.binding._MARKET_SESSIONS.get(id(self.supervisor))
        if (not isinstance(record, dict) or record.get("authority") is not self.authority or
                record.get("supervisor") is not self.supervisor or record.get("store") is not self.supervisor.store):
            raise PermissionError("NATIVE_BUILDER_SESSION_REQUIRED")
        # Validate the existing canonical path/inode/source/signed baseline
        # before enabling its narrow native ledger I/O context. This creates no
        # allocation and grants no general writes to the original repository.
        CampaignBudgetBridge._canonical_binding(controller.budget)
        if record.get("optuna_budget") is not None and record["optuna_budget"] is not controller.budget:
            raise PermissionError("CANONICAL_BUDGET_OWNER_ALREADY_BOUND")
        record["optuna_budget"] = controller.budget
        _NATIVE_CONTROLLERS[self] = weakref.ref(controller)

    def _bound_controller(self, proposal=None):
        from .optuna_research import OptunaResearchSearch
        from .optuna_campaign_budget import CampaignBudgetBridge
        reference = _NATIVE_CONTROLLERS.get(self)
        controller = reference() if reference is not None else None
        if (type(controller) is not OptunaS6Bridge or controller.evaluator is not self or
                controller.engineering is not False or type(controller.search) is not OptunaResearchSearch or
                type(controller.budget) is not CampaignBudgetBridge or
                controller.budget.noncanonical_copy is not False or controller.budget.native_evaluator is not self or
                controller.budget.core_store is not self.supervisor.store or
                any(name in vars(controller) for name in ("_check", "_binding", "_request", "_begin_reserved",
                    "_validate_verified", "_artifact", "_save_accepted", "run", "recover")) or
                any(name in vars(controller.search) for name in ("_check_open", "_proposal", "_make_proposal", "_path"))):
            raise PermissionError("BOUND_NATIVE_FACTORY_CONTROLLER_REQUIRED")
        OptunaResearchSearch._check_open(controller.search)
        if proposal is not None:
            from optuna.trial import TrialState
            pending = [trial for trial in controller.search._study.trials if trial.state == TrialState.RUNNING]
            if (len(pending) != 1 or OptunaResearchSearch._proposal(controller.search, pending[0]) != proposal or
                    controller.search._path("duplicate", pending[0].number).exists() or
                    controller.search._path("receipt", pending[0].number).exists()):
                raise PermissionError("AUTHENTIC_PENDING_OPTUNA_PROPOSAL_REQUIRED")
        return controller

    def _supported_scope(self, spec):
        """Require compiler-derived, owner-bound v2 scope before any reservation."""
        _require_native_methods(self)
        self._check_native("dispatch")
        b, gate = self.binding, self.authority._gate
        scope = gate["research_scope"]
        jobs = scope.get("jobs", [])
        selected = [job for job in jobs if job.get("candidate_id") == spec.get("candidate_id")]
        if len(selected) != 1 or _digest(selected[0]) != _digest(spec):
            raise PermissionError("EXACT_SIGNED_SUPPORTED_ENTRY_JOB_REQUIRED")
        compiler_path = b.ROOT / "optuna_request_preparation.py"
        compiler_sha = gate["source_hashes"].get(str(compiler_path))
        if not _hash(compiler_sha):
            raise PermissionError("PINNED_SUPPORTED_ENTRY_COMPILER_REQUIRED")
        compiler = b.exact_module("s6_supported_entry_scope_owner", compiler_path, compiler_sha)
        derive = getattr(compiler, "supported_scope_bindings", None)
        if (not callable(derive) or
                Path(inspect.getsourcefile(derive)).resolve() != compiler_path.resolve()):
            raise PermissionError("PINNED_SUPPORTED_ENTRY_COMPILER_REQUIRED")
        expected = derive(jobs, gate["source_hashes"], scope.get("campaign_budget"), b.digest)
        if (expected.get("schema") != "AIOS_SUPPORTED_ENTRY_SCOPE_BINDINGS_V1" or
                scope.get("supported_entry_scope") != expected):
            raise PermissionError("MATCHING_SIGNED_SUPPORTED_ENTRY_SCOPE_REQUIRED")
        helper_path = Path(__file__).resolve().with_name("supported_entry_question.py")
        helper_pins = {str(helper_path): b.sha(helper_path)}
        if (any(gate["source_hashes"].get(path) != pin for path, pin in helper_pins.items()) or
                any(job.get("supported_entry_source_pins") != helper_pins for job in jobs)):
            raise PermissionError("PINNED_SUPPORTED_ENTRY_HELPER_REQUIRED")
        return _digest(expected)

    def preflight(self, proposal, spec, binding):
        _require_native_methods(self)
        sources = self._check_native("dispatch")
        self._bound_controller(proposal)
        b, authority, supervisor = self.binding, self.authority, self.supervisor
        scope = authority._gate["research_scope"]
        expected = {"contract_sha256": proposal["contract_hash"],
                    "parameter_bindings_sha256": binding["parameter_bindings_sha256"],
                    "objective_sha256": binding["objective_sha256"]}
        if scope.get("optuna") != expected:
            raise PermissionError("MATCHING_SIGNED_OPTUNA_DOMAIN_REQUIRED")
        jobs = scope.get("jobs", [])
        matches = [job for job in jobs if job.get("candidate_id") == spec["candidate_id"]]
        if len(matches) != 1 or b.digest(matches[0]) != binding["spec_sha256"]:
            raise PermissionError("EXACT_SIGNED_CATALOG_JOB_REQUIRED")
        context = b._CONTEXTS.get(b.digest(jobs))
        if (context is None or context[0] is not authority or
                b.digest(context[1].get(spec["candidate_id"])) != binding["spec_sha256"]):
            raise PermissionError("PROCESS_LOCAL_FULL_CATALOG_CONTEXT_REQUIRED")
        if spec["candidate_id"] not in supervisor.manifest.stage_lookup:
            raise PermissionError("SIGNED_MANIFEST_STAGE_REQUIRED")
        b.require_ready(spec)
        launcher_path = b.ROOT / "run_research.py"
        launcher = b.exact_module("s6_optuna_pinned_launcher", launcher_path,
                                  authority._gate["source_hashes"][str(launcher_path)])
        if launcher.b is not b:
            raise PermissionError("S6_BINDING_IMPORT_SUBSTITUTION")
        checked_inputs = launcher.verify_job_inputs(spec)
        if not isinstance(checked_inputs, dict):
            raise ValueError("NATIVE_INPUT_PIN_MISMATCH")
        complete_inputs = dict(checked_inputs)
        for path, pin in _input_pins(spec).items():
            if path in complete_inputs and complete_inputs[path] != pin:
                raise ValueError("NATIVE_INPUT_PIN_MISMATCH")
            complete_inputs[path] = pin
        authority.check_inputs(complete_inputs)
        consumer_path = b.ROOT / "research_consumer.py"
        consumer_hash = authority._gate["source_hashes"][str(consumer_path)]
        b.exact_module("s6_admitted_consumer", consumer_path, consumer_hash)
        units = supervisor.store.list_units_for_stage(spec["candidate_id"])
        if (len(units) != 1 or units[0]["status"] != "PENDING" or int(units[0]["attempts"]) != 0):
            raise RuntimeError("RECEIPT_RECOVERY_REQUIRED_NOT_NEW_DISPATCH")
        _continue_native_window(supervisor, authority, b)
        if self._native_ready_policy is None:
            previous = supervisor.ready_policy
            if not callable(previous):
                raise PermissionError("NATIVE_S6_READY_POLICY_REQUIRED")
            self._native_ready_policy = previous
            supervisor.ready_policy = self._ready_policy
        elif supervisor.ready_policy != self._ready_policy:
            raise PermissionError("S6_READY_POLICY_CHANGED")
        self._selection = _copy(spec)
        self._proposal = _copy(proposal)
        self._bound_binding = _copy(binding)
        self._recovery_selection = None
        return {"scope_sha256": b.digest(scope), "source_sha256": b.digest(authority._gate["source_hashes"]),
                "consumer_sha256": consumer_hash, "engineering_only": False}

    def authorize_campaign_budget(self, budget, request, action):
        """Bind the existing global ledger allocation to this exact owner/job.

        A callback, copied ledger, different core store or self-declared label
        cannot authorize a canonical allocation. The native owner scope pins
        the ledger's path/inode, conservative baseline and public owner code.
        """
        if action not in {"reserve", "begin", "accept", "validate_started"}:
            raise ValueError("UNKNOWN_CAMPAIGN_BUDGET_ACTION")
        self._check_native("publish" if action == "accept" else "dispatch")
        from .optuna_campaign_budget import CampaignBudgetBridge, TRIAL_OWNER_SHA256
        if (type(budget) is not CampaignBudgetBridge or budget.noncanonical_copy is not False or
                budget.core_store is not self.supervisor.store or getattr(budget, "native_evaluator", None) is not self):
            raise PermissionError("NATIVE_CANONICAL_CAMPAIGN_BUDGET_REQUIRED")
        if self._bound_controller().budget is not budget:
            raise PermissionError("BOUND_NATIVE_FACTORY_CONTROLLER_REQUIRED")
        budget._check_owner()
        selection = self._recovery_selection if action == "accept" and self._recovery_selection is not None else None
        proposal, spec = (selection[0], selection[1]) if selection is not None else (self._proposal, self._selection)
        if proposal is None or spec is None:
            raise PermissionError("BOUND_OWNER_CATALOG_SELECTION_REQUIRED")
        b, gate = self.binding, self.authority._gate
        economic = {key: spec[key] for key in ("mechanism_fingerprint", "rules_hash", "pairs", "period", "data_hash",
                                              "cost_risk_hash", "source_hash", "stage", "implementation_fingerprint")}
        economic_hash = b.digest(economic)
        expected_request = {"job_id": economic_hash, "proposal_hash": proposal["proposal_hash"],
            "spec_sha256": b.digest(spec), "economic_sha256": economic_hash,
            "input_sha256": b.digest(_input_pins(spec)),
            "source_sha256": gate["source_hashes"][str(b.ROOT / "research_consumer.py")],
            "scope_sha256": b.digest(gate["research_scope"]), "configurations": spec["configuration_count"],
            "physical_calls": spec["physical_call_reservation"]}
        if request != expected_request:
            raise PermissionError("EXACT_OWNER_BUDGET_REQUEST_REQUIRED")
        path = budget.path.resolve()
        stat = path.stat()
        expected_contract = {"ledger_path": str(path), "ledger_file_identity": {"device": stat.st_dev, "inode": stat.st_ino},
            "baseline_sha256": budget.baseline_sha256, "ledger_prefix_count": budget.baseline["ledger_prefix_count"],
            "ledger_prefix_head": budget.baseline["ledger_prefix_head"],
            "history_scope_sha256": budget.baseline["history_scope_sha256"], "core_run_id": self.supervisor.run_id,
            "trial_owner_sha256": TRIAL_OWNER_SHA256,
            "budget_source_sha256": b.sha(Path(__file__).with_name("optuna_campaign_budget.py"))}
        contract = gate["research_scope"].get("campaign_budget")
        if contract != expected_contract:
            raise PermissionError("SIGNED_CANONICAL_CAMPAIGN_BUDGET_CONTRACT_REQUIRED")
        original = getattr(budget, "original_ledger_path", None)
        if original is None or not os.path.samefile(path, original):
            raise PermissionError("CANONICAL_LEDGER_PATH_REQUIRED")
        return {"authenticated": True, "action": action, "request_sha256": b.digest(request),
                "campaign_budget_sha256": b.digest(contract)}

    def read_campaign_integrity(self, budget):
        """Independently verify an explicit successor-only history adoption.

        The original R17 stop remains true. An unsigned reconciliation or a
        caller-supplied false stop label cannot grant authority. The additive
        native verifier rechecks coherent immutable copied history and its
        published adoption receipt under the fresh genuine signed owner scope.
        It never opens the original SQLite database or replays market work.
        """
        sources = self._check_native("publish")
        b, authority = self.binding, self.authority
        gate = getattr(authority, "_gate", {})
        scope = gate.get("research_scope", {})
        contract = scope.get("original_history_resolution")
        if not isinstance(contract, dict) or not contract:
            raise RuntimeError("ORIGINAL_HISTORY_INTEGRITY_CONTRACT_REQUIRED")
        from .optuna_campaign_budget import CampaignBudgetBridge
        if (type(budget) is not CampaignBudgetBridge or budget.noncanonical_copy is not False or
                budget.core_store is not self.supervisor.store or getattr(budget, "native_evaluator", None) is not self):
            raise PermissionError("NATIVE_CANONICAL_CAMPAIGN_BUDGET_REQUIRED")
        path = (b.ROOT / "r17_history_resolution.py").resolve()
        pin = gate["source_hashes"].get(str(path))
        if not _hash(pin) or sources.get(str(path)) != pin or b.sha(path) != pin:
            raise PermissionError("ORIGINAL_HISTORY_VERIFIER_SOURCE_REQUIRED")
        helper = b.exact_module("s6_pinned_r17_history_resolution", path, pin)
        reader = getattr(helper, "read_campaign_integrity", None)
        if (Path(helper.__file__).resolve() != path or not callable(reader) or
                Path(inspect.getsourcefile(reader)).resolve() != path):
            raise PermissionError("ORIGINAL_HISTORY_VERIFIER_SOURCE_REQUIRED")
        # This is exact pinned native code, not an injected integrity callback.
        # The helper authenticates owner inputs, original provenance, independent
        # reconciliation and the immutable successor receipt on every read.
        result = reader(b, authority, budget)
        hashes = {"original_stop_sha256", "resolution_contract_sha256", "verifier_source_sha256",
                  "reconciliation_sha256", "adoption_receipt_sha256", "scope_sha256",
                  "history_scope_sha256", "baseline_sha256"}
        flags = {"authenticated": True, "original_integrity_stop": True, "original_stop_preserved": True,
                 "successor_history_adopted": True, "successor_dispatch_integrity_blocked": False,
                 "originals_modified": False, "automatic_replay_allowed": False}
        expected_keys = hashes | flags.keys() | {"schema", "new_market_calls"}
        if (not isinstance(result, dict) or set(result) != expected_keys or
                result.get("schema") != "AIOS_R17_SUCCESSOR_HISTORY_INTEGRITY_V1" or
                any(result.get(key) is not value for key, value in flags.items()) or
                type(result.get("new_market_calls")) is not int or result["new_market_calls"] != 0 or
                any(not _hash(result.get(key)) for key in hashes) or
                result["verifier_source_sha256"] != pin or
                result["resolution_contract_sha256"] != b.digest(contract) or
                result["scope_sha256"] != b.digest(scope) or
                result["history_scope_sha256"] != budget.baseline["history_scope_sha256"] or
                result["baseline_sha256"] != budget.baseline_sha256):
            raise PermissionError("AUTHENTICATED_SUCCESSOR_HISTORY_REQUIRED")
        return _copy(result)

    def _ready_policy(self, units, supervisor):
        if supervisor is not self.supervisor or self._selection is None:
            raise PermissionError("BOUND_S6_SELECTION_REQUIRED")
        # Preserve native fresh owner admission, publication and lifecycle checks.
        selected = [u for u in units if u.stage_id == self._selection["candidate_id"]]
        if len(selected) > 1:
            raise ValueError("ONE_FROZEN_UNIT_REQUIRED")
        return self._native_ready_policy(selected, supervisor)

    def require_dispatch_permit(self, authority, supervisor, candidate_id, *, consume=False, context=None):
        """Native ready/callback guard: private permit plus durable fresh BEGIN."""
        _require_native_methods(self)
        permit = _NATIVE_DISPATCHES.get(id(supervisor))
        if (permit is None or permit.get("evaluator") is not self or permit.get("authority") is not authority or
                permit.get("supervisor") is not supervisor or permit.get("candidate_id") != candidate_id or
                permit.get("state") != "ARMED" or authority is not self.authority or supervisor is not self.supervisor):
            raise PermissionError("NATIVE_OPTUNA_DISPATCH_PERMIT_REQUIRED")
        self._check_native("dispatch")
        record = self.binding._MARKET_SESSIONS.get(id(supervisor))
        controller = self._bound_controller(self._proposal)
        if (not isinstance(record, dict) or record.get("optuna_dispatch") is not permit or
                permit.get("controller") is not controller or permit.get("budget") is not controller.budget or
                self._selection != permit.get("spec") or self._selection["candidate_id"] != candidate_id):
            raise PermissionError("NATIVE_OPTUNA_DISPATCH_PERMIT_REQUIRED")
        units = supervisor.store.list_units_for_stage(candidate_id)
        if len(units) != 1:
            raise PermissionError("ONE_FROZEN_NATIVE_DISPATCH_UNIT_REQUIRED")
        unit = units[0]
        if consume:
            from automation.orchestration.adaptive_workforce.adapters import AdapterContext
            from automation.orchestration.adaptive_workforce.lifecycle import attempt_directory
            if (type(context) is not AdapterContext or not _claimed_context_identity(
                    supervisor, unit, context, attempt_directory=attempt_directory)):
                raise PermissionError("AUTHENTIC_CLAIMED_NATIVE_ATTEMPT_REQUIRED")
            if supervisor.store.conn.execute("SELECT 1 FROM attempts WHERE attempt_id=?", (context.attempt_id,)).fetchone() is not None:
                raise PermissionError("AUTHENTIC_CLAIMED_NATIVE_ATTEMPT_REQUIRED")
        elif unit["status"] != "PENDING" or int(unit["attempts"]) != 0:
            raise PermissionError("RECEIPT_RECOVERY_REQUIRED_NOT_NEW_DISPATCH")
        # A saved/reconstructed STARTED dict is not the fresh BEGIN object. The
        # budget rechecks its existing ledger bytes, signed owner/history/caps and
        # one-use token; no new allocation or second BEGIN is created here.
        from .optuna_campaign_budget import CampaignBudgetBridge
        CampaignBudgetBridge.validate_started(controller.budget, permit["reservation"], self,
                                              permit["reservation"]["request"], consume=consume)
        if consume:
            permit["state"] = "CONSUMED"
        return True

    def evaluate(self, spec, reservation):
        _require_native_methods(self)
        self._check_native("dispatch")
        controller = self._bound_controller(self._proposal)
        if (self._selection != spec or reservation.get("state") != "STARTED" or
                reservation.get("noncanonical_copy") is not False or
                reservation.get("authorized_to_evaluate") is not True):
            raise PermissionError("CANONICAL_STARTED_RESERVATION_REQUIRED")
        from .optuna_campaign_budget import CampaignBudgetBridge
        CampaignBudgetBridge.validate_started(controller.budget, reservation, self)
        record = self.binding._MARKET_SESSIONS.get(id(self.supervisor))
        permit = {"evaluator": self, "authority": self.authority, "supervisor": self.supervisor,
            "controller": controller, "budget": controller.budget, "candidate_id": spec["candidate_id"],
            "spec": _copy(spec), "reservation": reservation, "state": "ARMED"}
        with _NATIVE_DISPATCH_GUARD:
            used = _NATIVE_USED_STARTS.setdefault(controller.budget, set())
            if reservation["record_sha256"] in used:
                raise RuntimeError("NATIVE_STARTED_CALL_ALREADY_ATTEMPTED_NO_REPLAY")
            if not isinstance(record, dict) or record.get("optuna_dispatch") is not None or id(self.supervisor) in _NATIVE_DISPATCHES:
                raise PermissionError("NATIVE_OPTUNA_DISPATCH_PERMIT_REQUIRED")
            # Even a native return before its callback is an attempted boundary.
            # Standard restart is already denied by the ledger; this also
            # prevents same-process direct API retries with the old BEGIN object.
            used.add(reservation["record_sha256"])
            _NATIVE_DISPATCHES[id(self.supervisor)] = permit
            record["optuna_dispatch"] = permit
        try:
            self.supervisor.run(max_cycles=1, max_units=1)
            if permit["state"] != "CONSUMED":
                raise RuntimeError("NATIVE_OPTUNA_DISPATCH_NOT_CONSUMED_NO_REPLAY")
        finally:
            with _NATIVE_DISPATCH_GUARD:
                record["optuna_dispatch"] = None
                _NATIVE_DISPATCHES.pop(id(self.supervisor), None)
        self.binding.accept_finished_before_next(self.supervisor, self.authority,
                                                  self.authority._gate["research_scope"]["jobs"])
        return self.load_saved_result(spec)

    def load_saved_result(self, spec):
        self._check_native("publish")
        return self.binding.read(self.binding.scope(spec["output_root"]) / "RESULT.json")

    def verify_result(self, spec, reservation, result, binding):
        self._check_native("publish")
        b, store = self.binding, self.supervisor.store
        core = _accepted_core_receipt(store, self.supervisor.run_id, spec["candidate_id"])
        output = b.scope(core["output_path"])
        folder = b.scope(spec["output_root"])
        consumer_hash = self.authority._gate["source_hashes"][str(b.ROOT / "research_consumer.py")]
        if (b.sha(output) != core["output_hash"] or b.read(output) != result or
                b.read(folder / "RESULT.json") != result or
                result.get("spec_sha256") != binding["spec_sha256"] or
                result.get("source_sha256") != consumer_hash or
                result.get("candidate_id") != spec["candidate_id"] or
                result.get("physical_calls") != 6 or result.get("evaluator_calls") != 6 or
                result.get("new_configurations") != spec["configuration_count"] or
                result.get("proof_level") != "DEVELOPMENT_USED_NOT_INDEPENDENT_EDGE" or
                result.get("paper_ready") is not False or result.get("live_ready") is not False):
            raise ValueError("S6_RESULT_PROVENANCE_MISMATCH")
        seal = b.read(folder / "RECEIPT.json")
        if seal != {"spec_sha256": binding["spec_sha256"], "result_sha256": b.sha(folder / "RESULT.json"),
                    "physical_calls": 6, "evaluator_calls": 6}:
            raise ValueError("S6_FULL_RECEIPT_SEAL_MISMATCH")
        for section, prefix in (("scenarios", "CANDIDATE_"), ("baselines", "CONTROL_")):
            for scenario in _SCENARIOS:
                if b.read(folder / (prefix + scenario + ".json")) != result[section][scenario]:
                    raise ValueError("S6_SCENARIO_JOURNAL_CHANGED")
        journal = [json.loads(line) for line in (b.ROOT / "RESULT_RECEIPTS.jsonl").read_text().splitlines() if line.strip()]
        accepted = [r for r in journal if r.get("kind") == "ACCEPTED_MARKET_UNIT" and r.get("receipt_id") == core["receipt_id"]]
        if (not accepted or any(row != accepted[0] for row in accepted) or
                accepted[0].get("output_hash") != core["output_hash"] or
                accepted[0].get("spec_sha256") != binding["spec_sha256"] or
                accepted[0].get("new_configurations") != spec["configuration_count"] or
                accepted[0].get("physical_calls") != 6 or accepted[0].get("evaluator_calls") != 6):
            raise ValueError("S6_OWNER_ACCEPTANCE_JOURNAL_REQUIRED")
        metrics = result["scenarios"]["STRESSED"]["metrics"]
        count = metrics["trades"]
        if self.objective_contract != _OBJECTIVE or not _number(metrics["net_usd"]):
            raise ValueError("FROZEN_FINITE_AFTER_COST_OBJECTIVE_REQUIRED")
        if type(count) is not int or count < 0 or count != len(result["scenarios"]["STRESSED"]["trades"]):
            raise ValueError("AUTHENTIC_SAMPLE_COUNT_REQUIRED")
        request = reservation["request"]
        actual = {key: request[key] for key in _REQUEST_IDENTITIES}
        actual.update(receipt_id=core["receipt_id"], status="ACCEPTED", output_sha256=core["output_hash"],
                      core_run_id=core["run_id"], core_unit_id=core["unit_id"], core_attempt_id=core["attempt_id"])
        return {"actual_receipt": actual, "result_sha256": seal["result_sha256"],
                "accepted_journal_sha256": b.digest(accepted[0]), "objective": float(metrics["net_usd"]),
                "sample_count": count, "fixture_only": False,
                "classification": "ACCEPTED_DEVELOPMENT_USED_NOT_INDEPENDENT_EDGE"}


class OptunaS6Bridge:
    """Durable reserve/start/accepted-receipt/tell handoff, using existing owners."""
    def __init__(self, search, budget, evaluator=None, *, engineering=False):
        self.search, self.budget, self.evaluator = search, budget, evaluator
        self.engineering = engineering
        self.directory = Path(search._directory).resolve()

    def _check(self):
        self.search._check_open()
        if self.evaluator is None:
            raise RuntimeError("S6_EVALUATOR_REQUIRED")
        if self.engineering:
            if getattr(self.evaluator, "engineering_only", None) is not True:
                raise PermissionError("EXPLICIT_ENGINEERING_ADAPTER_REQUIRED")
            if getattr(self.budget, "noncanonical_copy", None) is not True:
                raise PermissionError("ENGINEERING_COPY_BUDGET_REQUIRED")
        elif type(self.evaluator) is not PinnedS6Evaluator:
            raise PermissionError("PINNED_NATIVE_S6_ADAPTER_REQUIRED")
        else:
            from .optuna_research import OptunaResearchSearch
            from .optuna_campaign_budget import CampaignBudgetBridge
            if (type(self.search) is not OptunaResearchSearch or type(self.budget) is not CampaignBudgetBridge or
                    self.budget.core_store is not self.evaluator.supervisor.store or
                    self.budget.noncanonical_copy is not False or
                    getattr(self.budget, "native_evaluator", None) is not self.evaluator):
                raise PermissionError("PINNED_NATIVE_CONTROLLER_AND_BUDGET_REQUIRED")
            PinnedS6Evaluator.bind_controller(self.evaluator, self)
            CampaignBudgetBridge._canonical_binding(self.budget)
        if self.evaluator.objective_contract != _OBJECTIVE:
            raise ValueError("FROZEN_S6_OBJECTIVE_REQUIRED")

    def _binding(self, proposal, spec, parameter_bindings):
        spec = _copy(spec)
        manifest = self.search._contract["manifest"]
        if (set(proposal) != {"trial_number", "params", "contract_hash", "proposal_hash"} or
                proposal["contract_hash"] != self.search.contract_hash or
                proposal["proposal_hash"] != _digest([proposal["contract_hash"], proposal["params"]])):
            raise ValueError("EXACT_OPTUNA_PROPOSAL_REQUIRED")
        if (spec.get("stage") != "DEVELOPMENT_SCREEN" or spec.get("handler") not in
                {"supertrend_development_v1", "supertrend_entry_development_v1", "supported_entry_development_v1"}):
            raise ValueError("DEVELOPMENT_ONLY_SUPPORTED_S6_SUPERTREND_REQUIRED")
        if spec.get("handler") == "supported_entry_development_v1":
            from .supported_entry_question import validate_supported_entry_job_metadata_v1
            validate_supported_entry_job_metadata_v1(spec)
            if not self.engineering:
                if type(self.evaluator) is not PinnedS6Evaluator:
                    raise PermissionError("PINNED_NATIVE_S6_ADAPTER_REQUIRED")
                PinnedS6Evaluator._supported_scope(self.evaluator, spec)
        if spec.get("status") != "READY" or spec.get("history", {}).get("status") != "NEW_WITHIN_CHECKED_HISTORY":
            raise ValueError("HISTORY_NOT_NEW_OR_NOT_READY")
        if any(c.get("synthetic_only") for c in spec.get("contracts", {}).values()) and not self.engineering:
            raise PermissionError("SYNTHETIC_CONTRACT_NOT_MARKET_ADMISSION")
        if spec.get("rules_hash") != _digest(spec["rules"]):
            raise ValueError("RULES_HASH_MISMATCH")
        if spec.get("cost_risk_hash") != _digest({"costs": spec["costs"], "risk": spec["risk"]}):
            raise ValueError("COST_RISK_HASH_MISMATCH")
        if spec.get("data_hash") != _digest({"shards": spec["price_shards"], "quarantine_intervals": spec["quarantine_intervals"]}):
            raise ValueError("DATA_HASH_MISMATCH")
        if set(parameter_bindings) != set(proposal["params"]):
            raise ValueError("EXACT_PARAMETER_BINDINGS_REQUIRED")
        for name, path in parameter_bindings.items():
            if (not isinstance(path, list) or not path or any(not isinstance(k, str) for k in path) or
                    path[0] not in {"catalog_index", "rules", "implementation"} or
                    (path[0] == "catalog_index" and len(path) != 1)):
                raise ValueError("PARAMETER_PATH_NOT_SEARCHABLE")
            current = spec
            try:
                for key in path:
                    current = current[key]
            except (KeyError, TypeError) as error:
                raise ValueError("PARAMETER_BINDING_MISMATCH") from error
            if _json(current) != _json(proposal["params"][name]):
                raise ValueError("PARAMETER_BINDING_MISMATCH")
        development = [spec["period"]["start"], spec["period"]["end_exclusive"]]
        if development != manifest["development"]:
            raise ValueError("DEVELOPMENT_SPLIT_MISMATCH")
        if not _utc(development[0]) < _utc(development[1]) <= _utc(manifest["holdout"][0]) < _utc(manifest["holdout"][1]):
            raise ValueError("CHRONOLOGICAL_DISJOINT_SPLIT_REQUIRED")
        if spec.get("physical_call_reservation") != 6:
            raise ValueError("SIX_SCENARIOS_REQUIRED")
        if type(spec.get("configuration_count")) is not int or spec["configuration_count"] < 1:
            raise ValueError("EXACT_CONFIGURATION_EXPOSURE_REQUIRED")
        identities = {"parameter_sha256": _digest(proposal["params"]), "spec_sha256": _digest(spec),
            "rules_sha256": spec["rules_hash"], "data_sha256": spec["data_hash"],
            "input_sha256": _digest(_input_pins(spec)), "cost_sha256": _digest(spec["costs"]),
            "risk_sha256": _digest(spec["risk"]), "cost_risk_sha256": spec["cost_risk_hash"],
            "split_sha256": _digest({"development": manifest["development"], "holdout": manifest["holdout"]}),
            "implementation_sha256": spec["implementation_fingerprint"],
            "objective_sha256": _digest(self.evaluator.objective_contract),
            "parameter_bindings_sha256": _digest(parameter_bindings), "contract_hash": proposal["contract_hash"],
            "proposal_hash": proposal["proposal_hash"]}
        if any(not _hash(pin) for pin in identities.values()):
            raise ValueError("EXACT_S6_IDENTITIES_REQUIRED")
        if any(identities[k] != manifest[k] for k in ("data_sha256", "cost_sha256", "risk_sha256", "objective_sha256")):
            raise ValueError("OPTUNA_MANIFEST_S6_IDENTITY_MISMATCH")
        economic = {key: spec[key] for key in ("mechanism_fingerprint", "rules_hash", "pairs", "period", "data_hash",
                                              "cost_risk_hash", "source_hash", "stage", "implementation_fingerprint")}
        identities["economic_sha256"] = _digest(economic)
        identities["identity_sha256"] = _digest(economic)
        return identities

    def _request(self, proposal, spec, binding):
        authenticated = self.evaluator.preflight(proposal, spec, binding)
        if authenticated.get("engineering_only") is not self.engineering:
            raise PermissionError("S6_PROVENANCE_MODE_MISMATCH")
        if authenticated["consumer_sha256"] != self.search._contract["manifest"]["adapter_sha256"]:
            raise ValueError("OPTUNA_EVALUATOR_SOURCE_MISMATCH")
        for field in ("source_sha256", "scope_sha256"):
            if not _hash(authenticated[field]):
                raise ValueError("AUTHENTICATED_S6_PIN_REQUIRED")
        binding["source_closure_sha256"] = authenticated["source_sha256"]
        binding["source_sha256"] = authenticated["consumer_sha256"]
        binding["scope_sha256"] = authenticated["scope_sha256"]
        return self._request_from_binding(proposal, spec, binding)

    def _request_from_binding(self, proposal, spec, binding):
        request = {"job_id": binding["identity_sha256"], "proposal_hash": proposal["proposal_hash"],
                   "spec_sha256": binding["spec_sha256"], "economic_sha256": binding["economic_sha256"],
                   "input_sha256": binding["input_sha256"], "source_sha256": binding["source_sha256"],
                   "scope_sha256": binding["scope_sha256"], "configurations": spec["configuration_count"],
                   "physical_calls": spec["physical_call_reservation"]}
        return request

    def _begin_reserved(self, request):
        if self.engineering:
            reservation = self.budget.reserve(request)
        else:
            from .optuna_campaign_budget import CampaignBudgetBridge
            if type(self.budget) is not CampaignBudgetBridge:
                raise PermissionError("PINNED_CANONICAL_CAMPAIGN_BUDGET_REQUIRED")
            reservation = CampaignBudgetBridge.reserve(self.budget, request)
        if reservation.get("state") != "RESERVED":
            raise RuntimeError("RECEIPT_RECOVERY_REQUIRED_NOT_REPLAY")
        if not self.engineering and reservation.get("noncanonical_copy") is not False:
            raise PermissionError("CANONICAL_GLOBAL_RESERVATION_REQUIRED")
        # reserve() is idempotent allocation evidence, never dispatch permission.
        reservation = self.budget.begin(reservation) if self.engineering else CampaignBudgetBridge.begin(self.budget, reservation)
        if reservation.get("state") != "STARTED" or reservation.get("request") != request:
            raise RuntimeError("DURABLE_EXACT_STARTED_RESERVATION_REQUIRED")
        if not self.engineering and (reservation.get("noncanonical_copy") is not False or
                                    reservation.get("authorized_to_evaluate") is not True):
            raise PermissionError("CANONICAL_STARTED_RESERVATION_REQUIRED")
        return reservation

    def _validate_verified(self, verified, request):
        receipt = verified["actual_receipt"]
        if receipt.get("status") != "ACCEPTED" or any(receipt.get(k) != request[k] for k in _REQUEST_IDENTITIES):
            raise ValueError("ACTUAL_RECEIPT_IDENTITY_MISMATCH")
        if (not receipt.get("receipt_id") or not _hash(receipt.get("output_sha256")) or
                any(not _hash(verified.get(k)) for k in ("result_sha256", "accepted_journal_sha256"))):
            raise ValueError("AUTHENTIC_ACTUAL_RECEIPT_REQUIRED")
        if verified.get("fixture_only") is not self.engineering:
            raise PermissionError("S6_RESULT_PROVENANCE_MODE_MISMATCH")
        if not _number(verified["objective"]) or type(verified["sample_count"]) is not int or verified["sample_count"] < 0:
            raise ValueError("FINITE_VERIFIED_OBJECTIVE_AND_COUNT_REQUIRED")

    def _artifact(self, proposal, binding, reservation, verified):
        receipt = {"contract_hash": proposal["contract_hash"], "proposal_hash": proposal["proposal_hash"],
                   "phase": "development", "status": "COMPLETE" if verified["sample_count"] else "INSUFFICIENT_DATA",
                   "objective": verified["objective"] if verified["sample_count"] else None,
                   "cost_adjusted": True, "sample_count": verified["sample_count"],
                   "evidence_sha256": _digest(verified), "metrics": {"trade_count": verified["sample_count"],
                   "fixture_only": self.engineering}, "reason": "ENGINEERING_ONLY" if self.engineering else
                   "Authenticated S6 development receipt; independent proof remains required"}
        return {"schema": "AIOS_OPTUNA_S6_RECEIPT_V1", "proposal": proposal, "binding": binding,
                "reservation": reservation, "actual_receipt": verified["actual_receipt"], "verified_result": verified,
                "search_receipt": receipt, "classification": "ENGINEERING_ONLY" if self.engineering else
                "ACCEPTED_DEVELOPMENT_USED_NOT_INDEPENDENT_EDGE", "market_evaluator_calls": 0 if self.engineering else 6,
                "verified_edge": False, "paper_ready": False, "live_ready": False}

    def _save_accepted(self, number, artifact):
        _save_once(self.directory / f"s6-accepted-{number}.json", artifact)
        _save_once(self.directory / f"s6-accepted-{number}.sha256.json", {"sha256": _digest(artifact)})

    def run(self, spec, *, parameter_bindings):
        self._check()
        spec, parameter_bindings = _copy(spec), _copy(parameter_bindings)
        proposal = self.search.ask()
        binding = self._binding(proposal, spec, parameter_bindings)
        request = self._request(proposal, spec, binding)
        number = proposal["trial_number"]
        start_path = self.directory / f"s6-started-{number}.json"
        if start_path.exists() or (self.directory / f"s6-accepted-{number}.json").exists():
            raise RuntimeError("RECEIPT_RECOVERY_REQUIRED_NOT_REPLAY")
        reservation = self._begin_reserved(request)
        _save_once(start_path, {"proposal": proposal, "binding": binding, "reservation": reservation})
        result = self.evaluator.evaluate(spec, reservation)
        if self.engineering:
            _save_once(self.directory / f"s6-engineering-result-{number}.json", result)
        verified = self.evaluator.verify_result(spec, reservation, result, binding)
        self._validate_verified(verified, request)
        artifact = self._artifact(proposal, binding, reservation, verified)
        self._save_accepted(number, artifact)
        if self.engineering:
            self.budget.accept(reservation, verified["actual_receipt"])
        else:
            from .optuna_campaign_budget import CampaignBudgetBridge
            CampaignBudgetBridge.accept(self.budget, reservation, verified["actual_receipt"])
        self.search.tell(number, artifact["search_receipt"])
        return artifact

    def recover(self, trial_number, spec, *, parameter_bindings):
        """Authenticate saved accepted work and finish tell; never invoke evaluate."""
        self._check()
        if type(trial_number) is not int or trial_number < 0:
            raise ValueError("S6_TRIAL_NUMBER_REQUIRED")
        path = self.directory / f"s6-accepted-{trial_number}.json"
        artifact = json.loads(path.read_text()) if path.exists() else None
        started = json.loads((self.directory / f"s6-started-{trial_number}.json").read_text())
        seal_path = self.directory / f"s6-accepted-{trial_number}.sha256.json"
        if artifact is not None and seal_path.exists():
            if json.loads(seal_path.read_text()) != {"sha256": _digest(artifact)}:
                raise ValueError("SAVED_S6_RECEIPT_CHANGED")
        proposal = started["proposal"]
        if proposal["trial_number"] != trial_number:
            raise ValueError("SAVED_S6_TRIAL_IDENTITY_MISMATCH")
        binding = self._binding(proposal, spec, parameter_bindings)
        if self.engineering:
            request = self._request(proposal, spec, binding)
            result = json.loads((self.directory / f"s6-engineering-result-{trial_number}.json").read_text())
        else:
            # Reconciliation checks the genuine owner but never admits a new unit.
            self.evaluator._check_native("publish")
            authority = self.evaluator.authority
            b = self.evaluator.binding
            signed_optuna = authority._gate["research_scope"].get("optuna")
            if signed_optuna != {"contract_sha256": proposal["contract_hash"],
                                  "parameter_bindings_sha256": binding["parameter_bindings_sha256"],
                                  "objective_sha256": binding["objective_sha256"]}:
                raise PermissionError("MATCHING_SIGNED_OPTUNA_DOMAIN_REQUIRED")
            matches = [job for job in authority._gate["research_scope"]["jobs"]
                       if job.get("candidate_id") == spec["candidate_id"]]
            if len(matches) != 1 or _digest(matches[0]) != binding["spec_sha256"]:
                raise PermissionError("EXACT_SIGNED_CATALOG_JOB_REQUIRED")
            binding.update(source_closure_sha256=_digest(authority._gate["source_hashes"]),
                           source_sha256=authority._gate["source_hashes"][str(b.ROOT / "research_consumer.py")],
                           scope_sha256=_digest(authority._gate["research_scope"]))
            request = self._request_from_binding(proposal, spec, binding)
            result = self.evaluator.load_saved_result(spec)
        if binding != started["binding"] or request != started["reservation"]["request"]:
            raise ValueError("SAVED_S6_BINDING_CHANGED")
        if not self.engineering:
            # Acceptance authorization only; no selector or dispatch admission.
            self.evaluator._recovery_selection = (_copy(proposal), _copy(spec), _copy(binding))
        verified = self.evaluator.verify_result(spec, started["reservation"], result, binding)
        self._validate_verified(verified, request)
        rebuilt = self._artifact(proposal, binding, started["reservation"], verified)
        if artifact is not None and artifact != rebuilt:
            raise ValueError("SAVED_S6_RECEIPT_CHANGED")
        self._save_accepted(trial_number, rebuilt)
        if self.engineering:
            self.budget.accept(started["reservation"], verified["actual_receipt"])
        else:
            from .optuna_campaign_budget import CampaignBudgetBridge
            CampaignBudgetBridge.accept(self.budget, started["reservation"], verified["actual_receipt"])
        self.search.tell(trial_number, rebuilt["search_receipt"])
        return rebuilt
