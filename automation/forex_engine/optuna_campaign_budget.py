"""Exposure adapter for the existing Forex global hash-chained trial ledger.

This adds no ledger, scheduler, lease or approval authority. Budget records use
the pinned trial owner's parser, validator and record constructor, under its
existing ledger-file byte lock. Older physical-call counts are not reconstructible
from selection increments; their independently checked conservative allocation
must be supplied and remains frozen. Original integrity stops remain preserved.
Canonical successor admission requires independently authenticated history
adoption through the genuine existing owner. Copies confer no authority.
"""
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import threading

CAMPAIGN_DEADLINE_UTC = "2026-10-18T18:34:14Z"
TRIAL_OWNER_SHA256 = "7e8b143d1f2c5dcbe9f246a6de8bdd8fdb19c6afc0f6bceff3df90f281d66486"
_KIND = "AIOS_EXISTING_GLOBAL_CAMPAIGN_ALLOCATION_V1"
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_REQUEST_HASHES = ("job_id", "proposal_hash", "spec_sha256", "economic_sha256",
                   "input_sha256", "source_sha256", "scope_sha256")
_REQUEST_FIELDS = {*_REQUEST_HASHES, "configurations", "physical_calls"}
_BASELINE_FIELDS = {"campaign_id", "deadline_utc", "configuration_ceiling", "physical_call_ceiling",
    "ledger_prefix_count", "ledger_prefix_head", "canonical_configuration_upper",
    "canonical_physical_call_upper", "canonical_physical_call_lower",
    "retained_configuration_reservation", "retained_physical_call_reservation",
    "retained_reported_calls", "retained_receipt_ids", "history_scope_sha256"}
_RECEIPT_FIELDS = _REQUEST_FIELDS | {"receipt_id", "status", "output_sha256", "core_run_id", "core_unit_id", "core_attempt_id"}
_CANONICAL_BUDGET_FIELDS = {"ledger_path", "ledger_file_identity", "baseline_sha256", "ledger_prefix_count",
    "ledger_prefix_head", "history_scope_sha256", "core_run_id", "trial_owner_sha256", "budget_source_sha256"}
_HISTORY_HASHES = {"original_stop_sha256", "resolution_contract_sha256", "verifier_source_sha256",
    "reconciliation_sha256", "adoption_receipt_sha256", "scope_sha256", "history_scope_sha256", "baseline_sha256"}
_HISTORY_FLAGS = {"authenticated": True, "original_integrity_stop": True, "original_stop_preserved": True,
    "successor_history_adopted": True, "successor_dispatch_integrity_blocked": False,
    "originals_modified": False, "automatic_replay_allowed": False}
_BUDGET_METHODS = ("reserve", "begin", "validate_started", "accept", "summary", "_canonical_binding", "_native_admission",
    "_check_owner", "_locked", "_states", "_dispatch_guard", "_successor_history_guard", "_envelope", "_append",
    "_reservation_request", "_require_started_token", "_validate_receipt", "_verify_core", "_summary")
_LOCKS = {}
_LOCKS_GUARD = threading.Lock()
_LOADED_OWNERS = {}


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _copy(value):
    return json.loads(_json(value))


def _hash(value):
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _moment(value):
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str):
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("UTC_TIMESTAMP_REQUIRED")
    if moment.tzinfo is None:
        raise ValueError("UTC_TIMESTAMP_REQUIRED")
    return moment.astimezone(timezone.utc)


def load_pinned_trial_owner(source_path):
    """Load public owner code only after verifying the full immutable source pin."""
    path = Path(source_path).resolve(strict=True)
    source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != TRIAL_OWNER_SHA256:
        raise ValueError("EXACT_TRIAL_OWNER_SOURCE_REQUIRED")
    # Compile the same bytes that were checked, avoiding a second source/pyc read.
    spec = importlib.util.spec_from_file_location("aios_pinned_global_trial_owner", path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(spec.name)
    sys.modules[spec.name] = module
    try:
        exec(compile(source, str(path), "exec"), module.__dict__)
    except BaseException:
        if previous is None:
            sys.modules.pop(spec.name, None)
        else:
            sys.modules[spec.name] = previous
        raise
    module._optuna_loaded_source_sha256 = TRIAL_OWNER_SHA256
    _LOADED_OWNERS[module] = {name: getattr(module, name) for name in
        ("canonical_json", "sha256_value", "sha256_bytes", "_ledger_record", "validate_trial_ledger")}
    return module


def _baseline(value):
    if not isinstance(value, dict) or set(value) != _BASELINE_FIELDS:
        raise ValueError("EXACT_CHECKED_CAMPAIGN_BASELINE_REQUIRED")
    value = _copy(value)
    if (value["campaign_id"] != "OUTCOME_CAMPAIGN_V3" or
            value["deadline_utc"] != CAMPAIGN_DEADLINE_UTC or
            type(value["configuration_ceiling"]) is not int or value["configuration_ceiling"] != 12000 or
            type(value["physical_call_ceiling"]) is not int or value["physical_call_ceiling"] != 20000):
        raise ValueError("ORIGINAL_CAMPAIGN_WINDOW_AND_CEILINGS_REQUIRED")
    counts = ["ledger_prefix_count", "canonical_configuration_upper", "canonical_physical_call_upper",
              "canonical_physical_call_lower", "retained_configuration_reservation",
              "retained_physical_call_reservation", "retained_reported_calls"]
    if any(type(value[k]) is not int or value[k] < 0 for k in counts) or value["ledger_prefix_count"] < 1:
        raise ValueError("EXACT_NONNEGATIVE_BASELINE_COUNTS_REQUIRED")
    # Historical R17 charges remain retained until a separately reviewed actual
    # canonical reconciliation replaces this adapter/source and its source grant.
    if (value["canonical_configuration_upper"] < 4882 or value["canonical_physical_call_upper"] < 7824 or
            value["canonical_physical_call_lower"] < 6775 or
            value["retained_configuration_reservation"] != 16 or
            value["retained_physical_call_reservation"] != 12 or value["retained_reported_calls"] != 12):
        raise ValueError("HISTORICAL_EXPOSURE_MUST_BE_RETAINED")
    ids = value["retained_receipt_ids"]
    if (not isinstance(ids, list) or len(ids) != 2 or len(set(ids)) != 2 or
            any(not isinstance(v, str) or not v for v in ids) or
            not _hash(value["ledger_prefix_head"]) or not _hash(value["history_scope_sha256"])):
        raise ValueError("HISTORICAL_RECEIPTS_AND_PREFIX_PINS_REQUIRED")
    if (value["canonical_physical_call_lower"] > value["canonical_physical_call_upper"] or
            value["canonical_configuration_upper"] + 16 > 12000 or value["canonical_physical_call_upper"] + 12 > 20000):
        raise ValueError("BASELINE_ALREADY_EXCEEDS_CAMPAIGN_CEILINGS")
    return value


def _request(value):
    if not isinstance(value, dict) or set(value) != _REQUEST_FIELDS:
        raise ValueError("EXACT_BOUND_RESERVATION_REQUEST_REQUIRED")
    value = _copy(value)
    if any(not _hash(value[k]) for k in _REQUEST_HASHES):
        raise ValueError("FULL_ECONOMIC_INPUT_SOURCE_SCOPE_IDENTITIES_REQUIRED")
    if any(type(value[k]) is not int or value[k] < 1 for k in ("configurations", "physical_calls")):
        raise ValueError("POSITIVE_PHYSICAL_RESERVATION_REQUIRED")
    return value


class CampaignBudgetBridge:
    """Checked allocation events appended to the existing canonical ledger.

    ``integrity_reader`` is only for explicitly noncanonical engineering copies.
    Canonical use reads original history through the concrete native evaluator;
    absent an authenticated original-history contract it remains blocked. Use
    requires the concrete ``PinnedS6Evaluator`` with its existing genuine
    owner session and an exact signed ``research_scope.campaign_budget`` binding.
    Generic callbacks, path labels and copied ledgers cannot grant authority.
    ``core_store`` is the supervisor's already-open WorkloadStore, not a path;
    this adapter never opens an original SQLite database or creates core units.
    """

    def __init__(self, ledger_path, owner_module, baseline, *, integrity_reader=None,
                 noncanonical_copy=True, original_ledger_path=None,
                 admission_verifier=None, core_store=None, native_evaluator=None):
        self.path = Path(ledger_path).absolute()
        self.owner = owner_module
        self.baseline = _baseline(baseline)
        self.baseline_sha256 = _digest(self.baseline)
        self.integrity_reader = integrity_reader
        self.noncanonical_copy = noncanonical_copy
        self.native_evaluator = native_evaluator
        self._issued_starts = {}
        self.original_ledger_path = Path(original_ledger_path).absolute() if original_ledger_path is not None else None
        self.core_store = core_store
        if type(noncanonical_copy) is not bool or (noncanonical_copy and not callable(integrity_reader)):
            raise ValueError("EXACT_COPY_MODE_AND_INTEGRITY_READER_REQUIRED")
        if not noncanonical_copy:
            if any(name in vars(self) for name in _BUDGET_METHODS):
                raise PermissionError("CANONICAL_BUDGET_METHOD_SUBSTITUTED")
            if integrity_reader is not None:
                raise ValueError("NATIVE_ORIGINAL_HISTORY_READER_REQUIRED")
            from .optuna_s6_bridge import PinnedS6Evaluator
            if type(native_evaluator) is not PinnedS6Evaluator or admission_verifier is not None:
                raise ValueError("EXISTING_NATIVE_ADMISSION_REQUIRED")
            if self.original_ledger_path is None:
                raise ValueError("CANONICAL_LEDGER_ORIGINAL_IDENTITY_REQUIRED")
        self._check_owner()
        if self.path.is_symlink() or not self.path.is_file():
            raise ValueError("EXISTING_REGULAR_TRIAL_LEDGER_REQUIRED")
        self._resolved_path = self.path.resolve()
        stat = self.path.stat()
        self._file_identity = (stat.st_dev, stat.st_ino)
        if noncanonical_copy:
            if original_ledger_path is None:
                raise ValueError("COPY_ORIGINAL_IDENTITY_REQUIRED")
            original = Path(original_ledger_path)
            if self.path.resolve() == original.resolve() or (original.exists() and os.path.samefile(self.path, original)):
                raise ValueError("COPY_MUST_NOT_BE_ORIGINAL")
        else:
            CampaignBudgetBridge._canonical_binding(self)

    def _canonical_binding(self):
        """Recheck genuine session plus signed original path/inode/history pins."""
        if any(name in vars(self) for name in _BUDGET_METHODS):
            raise PermissionError("CANONICAL_BUDGET_METHOD_SUBSTITUTED")
        if _digest(self.baseline) != self.baseline_sha256:
            raise ValueError("BASELINE_CHANGED")
        native = self.native_evaluator
        if any(name in vars(native) for name in ("_check_native", "authorize_campaign_budget", "read_campaign_integrity")):
            raise PermissionError("NATIVE_ADMISSION_METHOD_SUBSTITUTED")
        native._check_native("construct")
        if native.supervisor.store is not self.core_store:
            raise PermissionError("CANONICAL_BUDGET_CORE_STORE_CHANGED")
        expected_original = (Path(native.binding.REPO) / ".aios/runtime/forex_edge_validation_pipeline_v1/AIOS_FOREX_GLOBAL_TRIAL_LEDGER_V1.jsonl").resolve()
        original = self.original_ledger_path
        if (original is None or original.is_symlink() or not original.is_file() or
                original.resolve() != expected_original or self.path.resolve() != expected_original or
                not os.path.samefile(self.path, original)):
            raise PermissionError("CANONICAL_LEDGER_PATH_MUST_BE_ORIGINAL")
        stat = original.stat()
        if (stat.st_dev, stat.st_ino) != self._file_identity:
            raise PermissionError("CANONICAL_LEDGER_FILE_IDENTITY_CHANGED")
        gate = native.authority._gate
        contract = gate.get("research_scope", {}).get("campaign_budget")
        expected = {"ledger_path": str(expected_original), "ledger_file_identity": {"device": stat.st_dev, "inode": stat.st_ino},
            "baseline_sha256": self.baseline_sha256, "ledger_prefix_count": self.baseline["ledger_prefix_count"],
            "ledger_prefix_head": self.baseline["ledger_prefix_head"], "history_scope_sha256": self.baseline["history_scope_sha256"],
            "core_run_id": self.core_store.run_id, "trial_owner_sha256": TRIAL_OWNER_SHA256,
            "budget_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        if (not isinstance(contract, dict) or set(contract) != _CANONICAL_BUDGET_FIELDS or contract != expected or
                gate.get("source_hashes", {}).get(str(Path(__file__).resolve())) != expected["budget_source_sha256"]):
            raise PermissionError("EXACT_SIGNED_CANONICAL_BUDGET_SCOPE_REQUIRED")
        return contract

    def _native_admission(self, req, action):
        contract = CampaignBudgetBridge._canonical_binding(self)
        receipt = self.native_evaluator.authorize_campaign_budget(self, _copy(req), action)
        if (not isinstance(receipt, dict) or receipt != {"authenticated": True, "action": action,
                "request_sha256": _digest(req), "campaign_budget_sha256": _digest(contract)}):
            raise PermissionError("AUTHENTICATED_NATIVE_BUDGET_RECEIPT_REQUIRED")

    def _check_owner(self):
        required = ("validate_trial_ledger", "_ledger_record", "canonical_json")
        if any(not callable(getattr(self.owner, name, None)) for name in required):
            raise ValueError("EXISTING_TRIAL_OWNER_API_REQUIRED")
        if getattr(self.owner, "_optuna_loaded_source_sha256", None) == TRIAL_OWNER_SHA256:
            loaded = _LOADED_OWNERS.get(self.owner)
            if (not loaded or any(getattr(self.owner, name, None) is not function for name, function in loaded.items()) or
                    hashlib.sha256(Path(self.owner.__file__).read_bytes()).hexdigest() != TRIAL_OWNER_SHA256):
                raise ValueError("EXACT_TRIAL_OWNER_SOURCE_REQUIRED")
        elif not (self.noncanonical_copy and getattr(self.owner, "synthetic_fixture_only", False) is True):
            raise ValueError("EXACT_TRIAL_OWNER_SOURCE_REQUIRED")

    @contextmanager
    def _locked(self):
        if _digest(self.baseline) != self.baseline_sha256:
            raise ValueError("BASELINE_CHANGED")
        if not self.noncanonical_copy:
            CampaignBudgetBridge._canonical_binding(self)
        self._check_owner()
        ledger_io = nullcontext()
        if not self.noncanonical_copy:
            factory = getattr(self.native_evaluator.binding, "canonical_ledger_io", None)
            if not callable(factory):
                raise PermissionError("EXISTING_CANONICAL_LEDGER_IO_GUARD_REQUIRED")
            ledger_io = factory(self)
        if self.path.is_symlink() or self.path.resolve() != self._resolved_path:
            raise ValueError("EXISTING_REGULAR_TRIAL_LEDGER_REQUIRED")
        # POSIX record locks are per-process. All hardlink aliases therefore
        # need the same in-process guard before opening/reading the ledger.
        key = (os.getpid(), *self._file_identity)
        with _LOCKS_GUARD:
            guard = _LOCKS.setdefault(key, threading.RLock())
        with guard, ledger_io, self.path.open("r+", encoding="ascii", newline="") as handle:
            stat = os.fstat(handle.fileno())
            if (stat.st_dev, stat.st_ino) != self._file_identity:
                raise ValueError("TRIAL_LEDGER_FILE_IDENTITY_CHANGED")
            # Matches append_trial_record's first-byte lock on Windows. POSIX
            # copies use the corresponding advisory record lock, same file.
            if os.name == "nt":
                import msvcrt
                handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.lockf(handle.fileno(), fcntl.LOCK_EX, 1, 0, os.SEEK_SET)
            try:
                handle.seek(0)
                raw = handle.read()
                if not raw or not raw.endswith("\n") or any(not row.strip() for row in raw.splitlines()):
                    raise ValueError("TRIAL_LEDGER_TORN_OR_BLANK_RECORD")
                rows = [json.loads(line) for line in raw.splitlines()]
                self.owner.validate_trial_ledger(rows)
                prefix_count = self.baseline["ledger_prefix_count"]
                if len(rows) < prefix_count or rows[prefix_count-1]["record_sha256"] != self.baseline["ledger_prefix_head"]:
                    raise ValueError("CHECKED_HISTORY_PREFIX_CHANGED")
                yield handle, rows
            finally:
                if os.name == "nt":
                    handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.lockf(handle.fileno(), fcntl.LOCK_UN, 1, 0, os.SEEK_SET)

    def _states(self, rows):
        states = {}
        receipts = set()
        for row in rows[self.baseline["ledger_prefix_count"]:]:
            if row.get("kind") != _KIND:
                raise ValueError("UNRECONCILED_GLOBAL_TRIAL_RECORD")
            if row.get("baseline") != self.baseline or row.get("baseline_sha256") != self.baseline_sha256:
                raise ValueError("BASELINE_CHANGED")
            req = _request(row.get("request"))
            job = req["job_id"]; previous = states.get(job); state = row.get("state")
            if previous and previous["request"] != req:
                raise ValueError("RESERVATION_IDENTITY_CONFLICT")
            if (row.get("noncanonical_copy") is not self.noncanonical_copy or
                    row.get("scored_trial_increment") != (req["configurations"] if state == "RESERVED" else 0)):
                raise ValueError("ALLOCATION_LEDGER_SCOPE_CHANGED")
            if state == "RESERVED":
                if previous or row.get("status") != "INVALID_TEST":
                    raise ValueError("INVALID_RESERVATION_TRANSITION")
            elif state == "STARTED":
                if previous is None or previous["state"] != "RESERVED" or row.get("status") != "INVALID_TEST":
                    raise ValueError("INVALID_RESERVATION_TRANSITION")
            elif state == "ACCEPTED":
                receipt = row.get("receipt", {})
                self._validate_receipt(req, receipt)
                if (previous is None or previous["state"] != "STARTED" or row.get("status") != "OUTCOME_EXAMINED" or
                        receipt["receipt_id"] in receipts):
                    raise ValueError("INVALID_ACCEPTED_TRANSITION")
                receipts.add(receipt["receipt_id"])
            else:
                raise ValueError("UNKNOWN_ALLOCATION_STATE")
            states[job] = row
        return states

    def _successor_history_guard(self, current, req):
        fields = _HISTORY_HASHES | _HISTORY_FLAGS.keys() | {"schema", "new_market_calls"}
        if (not isinstance(current, dict) or set(current) != fields or
                current.get("schema") != "AIOS_R17_SUCCESSOR_HISTORY_INTEGRITY_V1" or
                any(current.get(key) is not value for key, value in _HISTORY_FLAGS.items()) or
                type(current.get("new_market_calls")) is not int or current["new_market_calls"] != 0 or
                any(not _hash(current.get(key)) for key in _HISTORY_HASHES) or
                current["baseline_sha256"] != self.baseline_sha256 or
                current["history_scope_sha256"] != self.baseline["history_scope_sha256"]):
            raise PermissionError("AUTHENTICATED_SUCCESSOR_HISTORY_REQUIRED")
        native = self.native_evaluator
        gate = native.authority._gate
        scope = gate.get("research_scope")
        contract = scope.get("original_history_resolution") if isinstance(scope, dict) else None
        helper = (Path(native.binding.ROOT) / "r17_history_resolution.py").resolve()
        if (not isinstance(contract, dict) or not contract or
                current["scope_sha256"] != native.binding.digest(scope) or current["scope_sha256"] != req["scope_sha256"] or
                current["resolution_contract_sha256"] != native.binding.digest(contract) or
                current["verifier_source_sha256"] != gate.get("source_hashes", {}).get(str(helper))):
            raise PermissionError("AUTHENTICATED_SUCCESSOR_HISTORY_REQUIRED")

    def _dispatch_guard(self, req, action, now):
        if self.noncanonical_copy:
            try:
                current = self.integrity_reader()
            except Exception as error:
                raise RuntimeError("INTEGRITY_EVIDENCE_REQUIRED") from error
            if (not isinstance(current, dict) or type(current.get("original_integrity_stop")) is not bool or
                    current.get("history_scope_sha256") != self.baseline["history_scope_sha256"]):
                raise RuntimeError("INTEGRITY_EVIDENCE_REQUIRED")
            if current["original_integrity_stop"]:
                raise RuntimeError("ORIGINAL_INTEGRITY_STOP_UNRESOLVED")
        else:
            reader = getattr(self.native_evaluator, "read_campaign_integrity", None)
            if not callable(reader):
                raise PermissionError("ORIGINAL_HISTORY_INTEGRITY_CONTRACT_REQUIRED")
            # A current new-run checkpoint cannot establish that the original
            # R17 integrity stop was reconciled. The native owner must prove it.
            current = reader(self)
            self._successor_history_guard(current, req)
        if _moment(now) >= _moment(CAMPAIGN_DEADLINE_UTC):
            raise RuntimeError("CAMPAIGN_DEADLINE_REACHED")
        if not self.noncanonical_copy:
            self._native_admission(req, action)

    def _envelope(self, row, *, dispatch_authorized=False):
        return {"job_id": row["request"]["job_id"], "request": _copy(row["request"]), "state": row["state"],
            "baseline_sha256": self.baseline_sha256, "reservation_sha256": _digest(row["request"]),
            "record_sha256": row["record_sha256"], "noncanonical_copy": self.noncanonical_copy,
            "evidence_level": "NONCANONICAL_ENGINEERING_COPY" if self.noncanonical_copy else "EXISTING_OWNER_GLOBAL_ALLOCATION",
            "authorized_to_evaluate": not self.noncanonical_copy and dispatch_authorized}

    def _append(self, handle, rows, req, state, now, receipt=None):
        payload = {"kind": _KIND, "event_id": f"OPTUNA_ALLOCATION:{req['job_id']}:{state}",
            "status": "OUTCOME_EXAMINED" if state == "ACCEPTED" else "INVALID_TEST", "state": state,
            "scored_trial_increment": req["configurations"] if state == "RESERVED" else 0, "proposed_count": 0,
            "request": req, "baseline": self.baseline, "baseline_sha256": self.baseline_sha256,
            "noncanonical_copy": self.noncanonical_copy,
            "recorded_utc": _moment(now).isoformat(), "scientific_result": state == "ACCEPTED"}
        if receipt is not None:
            payload["receipt"] = receipt
        record = self.owner._ledger_record(len(rows)+1, rows[-1]["record_sha256"], payload)
        self.owner.validate_trial_ledger(rows+[record])
        handle.seek(0, os.SEEK_END)
        handle.write(self.owner.canonical_json(record)+"\n"); handle.flush(); os.fsync(handle.fileno())
        return self._envelope(record, dispatch_authorized=state == "STARTED")

    def reserve(self, request, *, now=None):
        """Commit maximum configuration/call exposure before any evaluator call."""
        req = _request(request)
        with self._locked() as (handle, rows):
            states = self._states(rows)
            prior = states.get(req["job_id"])
            if prior is not None:
                if prior["request"] != req:
                    raise ValueError("RESERVATION_IDENTITY_CONFLICT")
                return self._envelope(prior)
            self._dispatch_guard(req, "reserve", now)
            if any(row.get("candidate_fingerprint") == req["economic_sha256"] for row in rows[:self.baseline["ledger_prefix_count"]]):
                raise ValueError("HISTORICAL_ECONOMIC_JOB_ALREADY_EXAMINED")
            if any((r["request"]["economic_sha256"], r["request"]["input_sha256"]) ==
                   (req["economic_sha256"], req["input_sha256"]) for r in states.values()):
                raise ValueError("ECONOMIC_JOB_ALREADY_RESERVED")
            summary = self._summary(states)
            if (summary["configuration_committed_upper_bound"]+req["configurations"] > 12000 or
                    summary["conservative_physical_call_upper_bound"]+req["physical_calls"] > 20000):
                raise RuntimeError("CAMPAIGN_BUDGET_EXCEEDED")
            return self._append(handle, rows, req, "RESERVED", now)

    def _reservation_request(self, reservation):
        if not isinstance(reservation, dict):
            raise ValueError("RESERVATION_ENVELOPE_REQUIRED")
        req = _request(reservation.get("request"))
        if (reservation.get("job_id") != req["job_id"] or reservation.get("baseline_sha256") != self.baseline_sha256 or
                reservation.get("reservation_sha256") != _digest(req) or
                reservation.get("noncanonical_copy") is not self.noncanonical_copy):
            raise ValueError("RESERVATION_ENVELOPE_SCOPE_CHANGED")
        return req

    def begin(self, reservation, *, now=None):
        """One-use durable dispatch marker; a crash afterwards forbids replay."""
        req = self._reservation_request(reservation)
        with self._locked() as (handle, rows):
            states = self._states(rows); prior = states.get(req["job_id"])
            if prior is None or prior["request"] != req:
                raise ValueError("RESERVATION_IDENTITY_CONFLICT")
            if prior["state"] != "RESERVED":
                raise RuntimeError("AMBIGUOUS_ATTEMPT_OR_SETTLED_JOB_NO_REPLAY")
            self._dispatch_guard(req, "begin", now)
            started = self._append(handle, rows, req, "STARTED", now)
            self._issued_starts[started["record_sha256"]] = started
            return started

    def _require_started_token(self, reservation, req, rows, *, consume=False):
        prior = self._states(rows).get(req["job_id"])
        if (prior is None or prior["request"] != req or prior["state"] != "STARTED" or
                self._issued_starts.get(prior["record_sha256"]) is not reservation or
                reservation != self._envelope(prior, dispatch_authorized=True)):
            raise RuntimeError("FRESH_STARTED_RESERVATION_REQUIRED")
        if consume:
            self._issued_starts.pop(prior["record_sha256"])
        return prior

    def validate_started(self, reservation, native_evaluator, request=None, *, consume=False, now=None):
        """Verify/consume this process's fresh BEGIN object before native dispatch.

        Saved/reconstructed STARTED values cannot re-create issuance after a
        crash. The native controller consumes the original object once before
        its evaluator callback; exposure remains committed if that call fails.
        This performs no ledger transition and never reauthorizes a new BEGIN.
        """
        if self.noncanonical_copy or native_evaluator is not self.native_evaluator or native_evaluator is None:
            raise PermissionError("CANONICAL_STARTED_RESERVATION_REQUIRED")
        if type(consume) is not bool:
            raise ValueError("EXACT_CONSUME_FLAG_REQUIRED")
        CampaignBudgetBridge._canonical_binding(self)
        req = self._reservation_request(reservation)
        if request is not None and _request(request) != req:
            raise ValueError("RESERVATION_IDENTITY_CONFLICT")
        with self._locked() as (_, rows):
            self._require_started_token(reservation, req, rows)
            self._dispatch_guard(req, "validate_started", now)
            self._require_started_token(reservation, req, rows, consume=consume)
            return reservation

    def _validate_receipt(self, req, receipt):
        if (not isinstance(receipt, dict) or set(receipt) != _RECEIPT_FIELDS or receipt.get("status") != "ACCEPTED" or
                any(receipt.get(k) != v for k, v in req.items()) or not _hash(receipt.get("output_sha256")) or
                any(not isinstance(receipt.get(k), str) or not receipt[k] for k in
                    ("receipt_id", "core_run_id", "core_unit_id", "core_attempt_id"))):
            raise ValueError("ACCEPTED_RECEIPT_SCOPE_CHANGED")
        _request({key: receipt[key] for key in _REQUEST_FIELDS})

    def _verify_core(self, req, receipt):
        store = self.core_store
        if store is None or store.run_id != receipt["core_run_id"]:
            raise ValueError("EXISTING_CORE_RECEIPT_VERIFIER_REQUIRED")
        row = store.conn.execute("""
            SELECT r.*, u.status AS unit_status, u.output_hash AS unit_output_hash,
                u.output_path_published AS unit_output_path, u.lease_generation AS unit_generation, u.run_id AS unit_run_id,
                a.status AS attempt_status, a.output_hash AS attempt_output_hash,
                a.lease_generation AS attempt_generation, a.unit_id AS attempt_unit_id
            FROM receipts r JOIN units u ON u.unit_id=r.unit_id JOIN attempts a ON a.attempt_id=r.attempt_id
            WHERE r.receipt_id=? AND r.run_id=? AND r.unit_id=? AND r.attempt_id=?
            """, (receipt["receipt_id"], receipt["core_run_id"], receipt["core_unit_id"], receipt["core_attempt_id"])).fetchone()
        if row is None:
            raise ValueError("CORE_RECEIPT_NOT_ACCEPTED")
        row = dict(row)
        if (row["status"] != "ACCEPTED" or row["unit_status"] != "COMPLETED" or row["attempt_status"] != "SUCCESS" or
                row["attempt_unit_id"] != row["unit_id"] or row["unit_run_id"] != row["run_id"] or
                any(row[k] != receipt["output_sha256"] for k in ("output_hash", "unit_output_hash", "attempt_output_hash")) or
                row["unit_output_path"] != row["output_path"] or
                row["lease_generation"] != row["unit_generation"] or row["lease_generation"] != row["attempt_generation"]):
            raise ValueError("CORE_RECEIPT_NOT_ACCEPTED")
        path = Path(row["output_path"])
        if path.is_symlink() or not path.is_file():
            raise ValueError("CORE_OUTPUT_CHANGED")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != receipt["output_sha256"]:
            raise ValueError("CORE_OUTPUT_CHANGED")
        body = json.loads(raw)
        if isinstance(body, dict) and "payload" in body:
            metadata = body.get("metadata")
            if (not isinstance(metadata, dict) or metadata.get("research") is not True or
                    metadata.get("spec_sha256") != req["spec_sha256"]):
                raise ValueError("CORE_OUTPUT_SCOPE_CHANGED")
        payload = body.get("payload", body)
        if (not isinstance(payload, dict) or payload.get("spec_sha256") != req["spec_sha256"] or
                payload.get("source_sha256") != req["source_sha256"] or
                type(payload.get("physical_calls")) is not int or payload["physical_calls"] != req["physical_calls"] or
                type(payload.get("new_configurations")) is not int or payload["new_configurations"] != req["configurations"]):
            raise ValueError("CORE_OUTPUT_SCOPE_CHANGED")

    def accept(self, reservation, receipt, *, now=None):
        """Bind a verified existing accepted core output without refund/replay."""
        req = self._reservation_request(reservation)
        self._validate_receipt(req, receipt)
        with self._locked() as (handle, rows):
            states = self._states(rows); prior = states.get(req["job_id"])
            if prior is None or prior["request"] != req:
                raise ValueError("RESERVATION_IDENTITY_CONFLICT")
            if not self.noncanonical_copy:
                self._native_admission(req, "accept")
            self._verify_core(req, receipt)
            if prior["state"] == "ACCEPTED":
                if prior["receipt"] != receipt:
                    raise ValueError("ACCEPTED_RECEIPT_CONFLICT")
                return self._envelope(prior)
            if prior["state"] != "STARTED":
                raise ValueError("ACCEPTED_RECEIPT_REQUIRES_STARTED_RESERVATION")
            if receipt["receipt_id"] in self.baseline["retained_receipt_ids"] or any(
                    r.get("receipt", {}).get("receipt_id") == receipt["receipt_id"] for r in states.values()):
                raise ValueError("CORE_RECEIPT_ALREADY_CHARGED")
            return self._append(handle, rows, req, "ACCEPTED", now, _copy(receipt))

    def _summary(self, states):
        configurations = self.baseline["canonical_configuration_upper"] + self.baseline["retained_configuration_reservation"]
        upper = self.baseline["canonical_physical_call_upper"] + self.baseline["retained_physical_call_reservation"]
        lower = self.baseline["canonical_physical_call_lower"] + self.baseline["retained_reported_calls"]
        configurations += sum(row["request"]["configurations"] for row in states.values())
        upper += sum(row["request"]["physical_calls"] for row in states.values())
        lower += sum(row["receipt"]["physical_calls"] for row in states.values() if row["state"] == "ACCEPTED")
        if configurations > 12000 or upper > 20000 or lower > upper:
            raise ValueError("CAMPAIGN_LEDGER_EXCEEDS_CEILINGS")
        return {"canonical_configuration_upper": self.baseline["canonical_configuration_upper"],
            "configuration_committed_upper_bound": configurations, "conservative_physical_call_upper_bound": upper,
            "reported_physical_call_lower_bound": lower, "configurations_remaining": 12000-configurations,
            "physical_calls_remaining_conservative": 20000-upper, "deadline_utc": CAMPAIGN_DEADLINE_UTC,
            "configuration_ceiling": 12000, "physical_call_ceiling": 20000, "canonical_reconciled": False,
            "retained_receipt_ids": self.baseline["retained_receipt_ids"], "reserved_jobs": len(states),
            "ambiguous_started_jobs": sum(row["state"] == "STARTED" for row in states.values()),
            "noncanonical_copy": self.noncanonical_copy, "authorized_to_evaluate": False}

    def summary(self):
        with self._locked() as (_, rows):
            return self._summary(self._states(rows))
