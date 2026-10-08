"""Bounded Optuna proposer for the existing research controller.

This module never loads prices, dispatches workers, classifies an edge, or places
orders. The caller owns scientific scoring and verified admission. Local receipt
hashes provide consistency, not proof that the underlying evidence is authentic.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import tempfile

import optuna
from optuna.trial import TrialState

OPTUNA_VERSION = "5.0.0"
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_HASH_FIELDS = ("adapter_sha256", "data_sha256", "cost_sha256", "risk_sha256", "objective_sha256")
_METRICS = {"net_return", "max_drawdown", "sharpe", "profit_factor", "turnover",
            "trade_count", "fold_count", "fixture_only"}


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _utc(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("SPLIT_TIMEZONE_REQUIRED")
    return parsed.astimezone(timezone.utc)


def _validate_manifest(value):
    required = {"strategy_id", *_HASH_FIELDS, "development", "holdout", "space", "baseline",
                "seed", "max_evaluations", "max_proposals"}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("EXACT_RESEARCH_MANIFEST_REQUIRED")
    value = json.loads(_json(value))
    if not isinstance(value["strategy_id"], str) or not value["strategy_id"].strip():
        raise ValueError("STRATEGY_ID_REQUIRED")
    if any(not isinstance(value[k], str) or not _HASH.fullmatch(value[k]) for k in _HASH_FIELDS):
        raise ValueError("SOURCE_DATA_COST_RISK_OBJECTIVE_HASHES_REQUIRED")
    if any(not isinstance(value[k], list) or len(value[k]) != 2 for k in ("development", "holdout")):
        raise ValueError("DEVELOPMENT_AND_HOLDOUT_INTERVALS_REQUIRED")
    dev_start, dev_end = map(_utc, value["development"])
    proof_start, proof_end = map(_utc, value["holdout"])
    if not dev_start < dev_end <= proof_start < proof_end:
        raise ValueError("HOLDOUT_MUST_FOLLOW_DEVELOPMENT_WITHOUT_OVERLAP")
    for name in ("seed", "max_evaluations", "max_proposals"):
        if type(value[name]) is not int or value[name] < (0 if name == "seed" else 1):
            raise ValueError("FINITE_INTEGER_BUDGET_AND_SEED_REQUIRED")
    if value["max_proposals"] < value["max_evaluations"]:
        raise ValueError("PROPOSAL_BUDGET_BELOW_EVALUATION_BUDGET")
    space = value["space"]
    if not isinstance(space, dict) or not space or not isinstance(value["baseline"], dict) or set(space) != set(value["baseline"]):
        raise ValueError("SPACE_AND_EXACT_BASELINE_REQUIRED")
    for name, spec in space.items():
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
            raise ValueError("PARAMETER_NAME_INVALID")
        if any(term in name for term in ("cost", "fee", "slippage", "commission", "risk", "leverage", "holdout", "proof", "gate", "position_size")):
            raise ValueError("SAFETY_OR_EVIDENCE_CONTROL_NOT_SEARCHABLE")
        if not isinstance(spec, dict):
            raise ValueError("PARAMETER_SPEC_INVALID")
        base = value["baseline"][name]
        if spec.get("kind") == "categorical":
            choices = spec.get("choices")
            if set(spec) != {"kind", "choices"} or not isinstance(choices, list) or not choices:
                raise ValueError("CATEGORICAL_CHOICES_REQUIRED")
            if len({type(x) for x in choices}) != 1 or any(type(x) not in (str, bool, int, float) for x in choices):
                raise ValueError("HOMOGENEOUS_SCALAR_CHOICES_REQUIRED")
            if len({_json(x) for x in choices}) != len(choices) or _json(base) not in {_json(x) for x in choices}:
                raise ValueError("BASELINE_OR_CHOICES_INVALID")
        else:
            if set(spec) != {"kind", "low", "high", "step"} or spec["kind"] not in ("int", "float"):
                raise ValueError("FINITE_PARAMETER_RANGE_REQUIRED")
            low, high, step = (spec[k] for k in ("low", "high", "step"))
            if not all(_number(x) for x in (low, high, step, base)) or step <= 0 or not low <= base <= high:
                raise ValueError("BASELINE_OR_RANGE_INVALID")
            if spec["kind"] == "int" and any(type(x) is not int for x in (low, high, step, base)):
                raise ValueError("INTEGER_PARAMETER_REQUIRED")
            if any(not math.isclose((x-low)/step, round((x-low)/step), abs_tol=1e-9) for x in (high, base)):
                raise ValueError("RANGE_AND_BASELINE_MUST_ALIGN_TO_STEP")
    return value


def _save_once(path, value):
    """Atomic, fsynced, content-idempotent write under the directory writer lock."""
    data = _json(value)
    if path.exists():
        if _json(json.loads(path.read_text(encoding="utf-8"))) != data:
            raise ValueError("RECEIPT_CONFLICT")
        return
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=".pending-", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class OptunaResearchSearch:
    """Single-controller, development-only proposal and receipt boundary."""

    def __init__(self, directory, manifest):
        manifest = _validate_manifest(manifest)
        if optuna.__version__ != OPTUNA_VERSION:
            raise RuntimeError("PINNED_OPTUNA_VERSION_REQUIRED")
        self._contract = {"schema": "AIOS_OPTUNA_RESEARCH_V1", "optuna": OPTUNA_VERSION,
                          "sampler": "PER_TRIAL_SEEDED_TPE_V1", "manifest": manifest}
        self.contract_hash = _digest(self._contract)
        self._directory = Path(directory).resolve()
        self._directory.mkdir(parents=True, exist_ok=True)
        self._guard = sqlite3.connect(self._directory / "writer.sqlite3", timeout=0)
        self._storage = None
        self._closed = False
        try:
            self._guard.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            self._guard.close()
            raise RuntimeError("STUDY_WRITER_BUSY") from exc
        try:
            url = "sqlite:///" + (self._directory / "study.sqlite3").as_posix()
            self._storage = optuna.storages.RDBStorage(url)
            try:
                self._study = optuna.create_study(storage=self._storage, study_name="aios_research",
                    direction="maximize", sampler=self._sampler(0), pruner=optuna.pruners.NopPruner())
            except optuna.exceptions.DuplicatedStudyError:
                self._study = optuna.load_study(storage=self._storage, study_name="aios_research",
                    sampler=self._sampler(0), pruner=optuna.pruners.NopPruner())
                if self._study.user_attrs.get("contract") != self._contract:
                    raise ValueError("CONTRACT_MISMATCH")
            else:
                self._study.set_user_attr("contract", self._contract)
            if not self._study.trials:
                self._study.enqueue_trial(manifest["baseline"])
            self._reconcile()
        except BaseException:
            self.close()
            raise

    def _sampler(self, number):
        seed = int(_digest([self._contract["manifest"]["seed"], number])[:8], 16)
        return optuna.samplers.TPESampler(seed=seed, n_startup_trials=10, multivariate=False,
                                         constant_liar=False)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if not self._closed:
            self._closed = True
            if self._storage is not None:
                self._storage.remove_session()
                self._storage.engine.dispose()
            self._guard.close()

    def _check_open(self):
        if self._closed:
            raise RuntimeError("STUDY_CLOSED")
        if (self._study.user_attrs.get("contract") != self._contract
                or self._study.directions != [optuna.study.StudyDirection.MAXIMIZE]):
            raise ValueError("CONTRACT_MISMATCH")

    def _path(self, kind, number):
        if type(number) is not int or number < 0:
            raise ValueError("INVALID_TRIAL_NUMBER")
        return self._directory / f"{kind}-{number}.json"

    def _proposal(self, trial):
        path = self._path("proposal", trial.number)
        if not path.exists():
            raise RuntimeError("INCOMPLETE_PROPOSAL_REQUIRES_CONTROLLER_RECONCILIATION")
        proposal = json.loads(path.read_text(encoding="utf-8"))
        expected = self._make_proposal(trial.number, trial.params)
        if proposal != expected:
            raise ValueError("PROPOSAL_IDENTITY_MISMATCH")
        return proposal

    def _make_proposal(self, number, params):
        return {"trial_number": number, "params": params, "contract_hash": self.contract_hash,
                "proposal_hash": _digest([self.contract_hash, params])}

    def ask(self):
        """Return one proposal; returning pending work does not authorize redispatch."""
        self._check_open()
        self._reconcile()
        pending = [t for t in self._study.trials if t.state == TrialState.RUNNING]
        if len(pending) > 1:
            raise RuntimeError("MULTIPLE_PENDING_TRIALS")
        if pending:
            return self._proposal(pending[0])
        manifest = self._contract["manifest"]
        summary = self.summary()
        if summary["unique_evaluations"] >= manifest["max_evaluations"]:
            raise RuntimeError("EVALUATION_BUDGET_REACHED")
        seen = {self._proposal(t)["proposal_hash"] for t in self._study.trials if t.state.is_finished()}
        while len([t for t in self._study.trials if t.state != TrialState.WAITING]) < manifest["max_proposals"]:
            trials = self._study.trials
            waiting = [t for t in trials if t.state == TrialState.WAITING]
            next_number = waiting[0].number if waiting else len(trials)
            self._study.sampler = self._sampler(next_number)
            trial = self._study.ask()
            for name, spec in sorted(manifest["space"].items()):
                if spec["kind"] == "categorical":
                    trial.suggest_categorical(name, spec["choices"])
                elif spec["kind"] == "int":
                    trial.suggest_int(name, spec["low"], spec["high"], step=spec["step"])
                else:
                    trial.suggest_float(name, spec["low"], spec["high"], step=spec["step"])
            proposal = self._make_proposal(trial.number, trial.params)
            _save_once(self._path("proposal", trial.number), proposal)
            if proposal["proposal_hash"] in seen:
                _save_once(self._path("duplicate", trial.number), proposal)
                self._study.tell(trial.number, state=TrialState.FAIL)
                continue
            return proposal
        raise RuntimeError("PROPOSAL_BUDGET_REACHED_NOT_NO_EDGE")

    def _validate_receipt(self, proposal, receipt):
        required = {"contract_hash", "proposal_hash", "phase", "status", "objective",
                    "cost_adjusted", "sample_count", "evidence_sha256", "metrics", "reason"}
        if not isinstance(receipt, dict) or set(receipt) != required:
            raise ValueError("EXACT_RESULT_RECEIPT_REQUIRED")
        if any(receipt[k] != proposal[k] for k in ("contract_hash", "proposal_hash")):
            raise ValueError("RESULT_IDENTITY_MISMATCH")
        if receipt["phase"] != "development" or receipt["cost_adjusted"] is not True:
            raise ValueError("COST_ADJUSTED_DEVELOPMENT_ONLY")
        if not isinstance(receipt["evidence_sha256"], str) or not _HASH.fullmatch(receipt["evidence_sha256"]):
            raise ValueError("EVIDENCE_HASH_REQUIRED")
        if type(receipt["sample_count"]) is not int or receipt["sample_count"] < 0:
            raise ValueError("SAMPLE_COUNT_INVALID")
        if not isinstance(receipt["metrics"], dict) or not isinstance(receipt["reason"], str):
            raise ValueError("RESULT_DETAILS_REQUIRED")
        if set(receipt["metrics"]) - _METRICS or any(
            type(value) is not bool if name == "fixture_only" else not _number(value)
            for name, value in receipt["metrics"].items()
        ):
            raise ValueError("DEVELOPMENT_SUMMARY_METRICS_ONLY")
        if receipt["status"] == "COMPLETE":
            if not _number(receipt["objective"]) or receipt["sample_count"] == 0:
                raise ValueError("FINITE_OBJECTIVE_AND_NONEMPTY_SAMPLE_REQUIRED")
        elif receipt["status"] in ("ERROR", "INSUFFICIENT_DATA"):
            if receipt["objective"] is not None or not receipt["reason"].strip():
                raise ValueError("UNRESOLVED_REQUIRES_REASON_WITHOUT_OBJECTIVE")
        else:
            raise ValueError("UNSUPPORTED_RESULT_STATUS")
        _json(receipt)

    def tell(self, trial_number, receipt):
        """Store a verified caller receipt, then finish exactly that proposal."""
        self._check_open()
        self._path("receipt", trial_number)
        trials = self._study.trials
        if trial_number >= len(trials):
            raise ValueError("UNKNOWN_TRIAL")
        trial = trials[trial_number]
        if self._path("duplicate", trial_number).exists() or trial.state == TrialState.WAITING:
            raise ValueError("TRIAL_NOT_EVALUABLE")
        proposal = self._proposal(trial)
        self._validate_receipt(proposal, receipt)
        path = self._path("receipt", trial_number)
        if trial.state.is_finished() and not path.exists():
            raise ValueError("FINISHED_TRIAL_MISSING_RECEIPT")
        _save_once(path, receipt)
        self._finish(trial_number, receipt)

    def _finish(self, number, receipt):
        trial = self._study.trials[number]
        expected = TrialState.COMPLETE if receipt["status"] == "COMPLETE" else TrialState.FAIL
        digest_key = f"receipt_sha256_{number}"
        digest = _digest(receipt)
        saved_digest = self._study.user_attrs.get(digest_key)
        if saved_digest is not None and saved_digest != digest:
            raise ValueError("STORED_RESULT_MISMATCH")
        if trial.state.is_finished():
            if (saved_digest != digest or trial.state != expected
                    or (expected == TrialState.COMPLETE and trial.value != receipt["objective"])):
                raise ValueError("STORED_RESULT_MISMATCH")
            return
        # Public study metadata remains writable after a trial finishes. Commit
        # the entire receipt identity before finalizing, including FAIL reasons.
        if saved_digest is None:
            self._study.set_user_attr(digest_key, digest)
        if expected == TrialState.COMPLETE:
            self._study.tell(number, receipt["objective"])
        else:
            self._study.tell(number, state=TrialState.FAIL)

    def _reconcile(self):
        self._check_open()
        seen = set()
        for trial in self._study.trials:
            if trial.state == TrialState.WAITING:
                continue
            proposal = self._proposal(trial)
            duplicate = self._path("duplicate", trial.number)
            if duplicate.exists() or proposal["proposal_hash"] in seen:
                if ((duplicate.exists() and json.loads(duplicate.read_text(encoding="utf-8")) != proposal)
                        or proposal["proposal_hash"] not in seen
                        or trial.state not in (TrialState.RUNNING, TrialState.FAIL)
                        or self._path("receipt", trial.number).exists()
                        or f"receipt_sha256_{trial.number}" in self._study.user_attrs):
                    raise ValueError("INVALID_DUPLICATE_RECEIPT")
                # Recover the crash between proposal persistence and deduplication.
                _save_once(duplicate, proposal)
                if trial.state == TrialState.RUNNING:
                    self._study.tell(trial.number, state=TrialState.FAIL)
                continue
            path = self._path("receipt", trial.number)
            if path.exists():
                receipt = json.loads(path.read_text(encoding="utf-8"))
                self._validate_receipt(proposal, receipt)
                self._finish(trial.number, receipt)
                seen.add(proposal["proposal_hash"])
            elif trial.state.is_finished() or f"receipt_sha256_{trial.number}" in self._study.user_attrs:
                raise ValueError("FINISHED_TRIAL_MISSING_RECEIPT")

    def summary(self):
        self._check_open()
        self._reconcile()
        trials = [t for t in self._study.trials if t.state != TrialState.WAITING]
        duplicates = sum(self._path("duplicate", t.number).exists() for t in trials)
        complete = [t for t in trials if t.state == TrialState.COMPLETE]
        unresolved = sum(t.state == TrialState.FAIL and not self._path("duplicate", t.number).exists() for t in trials)
        return {"contract_hash": self.contract_hash, "proposals": len(trials),
                "unique_evaluations": len(trials) - duplicates,
                "completed_evaluations": len(complete), "unresolved_evaluations": unresolved,
                "duplicate_proposals": duplicates, "pending_evaluations": sum(t.state == TrialState.RUNNING for t in trials),
                "best_development_objective": max((t.value for t in complete), default=None),
                "edge_status": "UNPROVEN", "paper_ready": False, "live_ready": False}
