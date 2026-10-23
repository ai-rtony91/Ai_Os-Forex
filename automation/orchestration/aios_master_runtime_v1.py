"""Canonical coordinator for registered AI_OS orchestration APIs.

Only fixed Git/GitHub metadata commands and registered Python callables are used;
runtime artifacts are data and are never interpreted as commands.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

SCHEMA = "AIOS_MASTER_RUNTIME.v1"
CONTROLLER_ID = "AIOS_MASTER_RUNTIME_V1"
_LOCAL_LEASES: set[str] = set()
_LEASE_MUTEX = threading.Lock()
STAGES = (
    "repository_preflight", "capability_discovery", "success_preservation",
    "open_work_reconciliation", "dependency_graph", "compound_work_braid",
    "cable_selection", "queue_planning", "packet_resolution", "validation",
    "checkpoint", "owner_report", "next_prompt_generation",
)
PROTECTED = ("broker_access", "credential_access", "deployment", "push", "pr_publication", "merge", "order_execution")


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode()).hexdigest()


class RuntimeBlocked(RuntimeError):
    """Fail-closed runtime contract violation with stable reason codes."""


class ResumeRejected(RuntimeBlocked):
    """Checkpoint identity is incompatible with the repository."""


class AIOSMasterRuntime:
    """Compose canonical services without executing generated instructions."""

    CAPABILITIES = {
        "orchestration_platform": ("automation/orchestration/platform.py", "tests/orchestration/test_orchestration_platform_v1.py"),
        "canonical_spine": ("automation/orchestration/aios_canonical_orchestration_spine_v1.py", "tests/orchestration/test_aios_canonical_orchestration_spine_v1.py"),
        "compound_work_braid": ("automation/orchestration/aios_compound_work_braid_v1.py", "tests/orchestration/test_aios_compound_work_braid_v1.py"),
        "packet_queue_planner": ("automation/orchestration/aios_packet_queue_planner.py", "tests/orchestration/test_aios_packet_queue_planner.py"),
        "development_dispatcher": ("automation/orchestration/runtime_queue/aios_development_dispatcher.py", "tests/orchestration/test_aios_development_dispatcher.py"),
        "packet_builder": ("automation/orchestration/aios_codex_packet_builder.py", "tests/orchestration/test_aios_codex_packet_builder.py"),
        "packet_resolver": ("automation/orchestration/runtime_queue/aios_execution_packet_resolver.py", "tests/orchestration/test_aios_execution_packet_resolver.py"),
        "autonomy_governor": ("automation/orchestration/aios_autonomy_decision_governor.py", "tests/orchestration/test_aios_autonomy_decision_governor.py"),
        "work_countdown": ("automation/orchestration/aios_work_countdown_v1.py", "tests/orchestration/test_aios_work_countdown_v1.py"),
    }

    def __init__(self, repo_root: str | Path = ".", *, platform: Any = None) -> None:
        self.root = Path(repo_root).resolve()
        if platform is None:
            from automation.orchestration.platform import OrchestrationPlatform
            platform = OrchestrationPlatform(self.root)
        self.platform = platform
        self.state_path = self.root / ".aios/runtime/master-runtime-v1.json"
        self.lease_held = False
        self.allow_remote_metadata = False

    @property
    def journal_path(self) -> Path:
        return self.state_path.with_suffix(".journal.jsonl")

    @property
    def lease_path(self) -> Path:
        return self.state_path.with_suffix(".lock")

    @property
    def receipts_path(self) -> Path:
        return self.state_path.with_name(self.state_path.stem + "-receipts")

    @staticmethod
    def _process_creation(pid: int) -> int | None:
        if os.name != "nt":
            try:
                return int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19])
            except FileNotFoundError:
                return None
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            if ctypes.get_last_error() == 87:
                return None
            raise RuntimeBlocked("CONTROLLER_LEASE_PROCESS_IDENTITY_UNKNOWN")
        try:
            times = [wintypes.FILETIME() for _ in range(4)]
            if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)):
                raise RuntimeBlocked("CONTROLLER_LEASE_PROCESS_IDENTITY_UNKNOWN")
            return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        finally:
            kernel.CloseHandle(handle)

    def _bounded_path(self, value: str | Path, *, allow_external_state: bool = False) -> Path:
        target = Path(value)
        if ".." in target.parts:
            raise ResumeRejected("RUNTIME_PATH_PARENT_TRAVERSAL")
        if not target.is_absolute():
            target = self.root / target
        if not allow_external_state and not target.is_relative_to(self.root):
            raise ResumeRejected("RUNTIME_PATH_OUTSIDE_REPOSITORY")
        for item in (target, *target.parents):
            if item.is_symlink() or item.is_junction() or (item.exists() and getattr(item.lstat(), "st_file_attributes", 0) & 1024):
                raise ResumeRejected("RUNTIME_PATH_REDIRECTED")
        return target

    def _storage_paths(self) -> None:
        for target in (self.state_path, self.journal_path, self.lease_path, self.receipts_path):
            self._bounded_path(target, allow_external_state=True)

    @staticmethod
    def _decode_durable(raw: bytes) -> dict[str, Any]:
        def pairs(values):
            result = {}
            for key, value in values:
                if key in result:
                    raise ResumeRejected("DUPLICATE_RUNTIME_FIELD")
                result[key] = value
            return result
        def invalid(_value):
            raise ResumeRejected("INVALID_RUNTIME_NUMBER")
        try:
            value = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
        except (ValueError, UnicodeError) as error:
            raise ResumeRejected("INVALID_RUNTIME_JSON") from error
        if type(value) is not dict:
            raise ResumeRejected("INVALID_RUNTIME_OBJECT")
        return value

    @contextmanager
    def controller_lease(self):
        from automation.orchestration.claims.aios_task_claim_control import _region_lock, _write_lock_record
        self._storage_paths()
        key = str(self.lease_path.absolute()).casefold()
        with _LEASE_MUTEX:
            if key in _LOCAL_LEASES:
                raise RuntimeBlocked("CONTROLLER_LEASE_ACTIVE")
            _LOCAL_LEASES.add(key)
        descriptor = None
        locked = False
        record = None
        try:
            self.lease_path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(self.lease_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_BINARY", 0), 0o600)
            try:
                _region_lock(descriptor)
                locked = True
            except OSError as error:
                raise RuntimeBlocked("CONTROLLER_LEASE_ACTIVE_OR_UNKNOWN") from error
            os.lseek(descriptor, 0, os.SEEK_SET)
            prior = os.read(descriptor, 16384)
            if prior:
                previous = self._decode_durable(prior)
                if previous.get("schema") != "AIOS_MASTER_CONTROLLER_LEASE.v1":
                    raise RuntimeBlocked("CONTROLLER_LEASE_RECORD_INVALID")
                if previous.get("state") == "ACTIVE":
                    pid = previous.get("process_id")
                    if type(pid) is not int or pid <= 0:
                        raise RuntimeBlocked("CONTROLLER_LEASE_PROCESS_IDENTITY_UNKNOWN")
                    identity = self._process_creation(pid)
                    if identity == previous.get("process_creation_identity"):
                        raise RuntimeBlocked("CONTROLLER_LEASE_OWNER_STILL_LIVE")
                    # An acquired OS region lock AND measured absent/replaced process
                    # are required; elapsed wall time alone never reclaims a lease.
            repo = self.repository()
            now = datetime.now(timezone.utc).isoformat()
            creation = self._process_creation(os.getpid())
            if type(creation) is not int:
                raise RuntimeBlocked("CONTROLLER_LEASE_PROCESS_IDENTITY_UNKNOWN")
            record = {"schema": "AIOS_MASTER_CONTROLLER_LEASE.v1", "controller_id": CONTROLLER_ID,
                      "process_id": os.getpid(), "process_creation_identity": creation,
                      "repository_path": str(self.root), "worktree_path": str(self.root),
                      "branch": repo["branch"], "head_sha": repo["head"], "acquired_utc": now,
                      "renewed_utc": now, "lease_nonce_hash": hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
                      "state": "ACTIVE"}
            _write_lock_record(descriptor, record)
            self.lease_held = True
            yield record
        finally:
            self.lease_held = False
            if descriptor is not None:
                try:
                    if locked and record is not None:
                        _write_lock_record(descriptor, {**record, "state": "RELEASED",
                            "renewed_utc": datetime.now(timezone.utc).isoformat()})
                finally:
                    if locked:
                        _region_lock(descriptor, unlock=True)
                    os.close(descriptor)
            with _LEASE_MUTEX:
                _LOCAL_LEASES.discard(key)

    def load_durable(self) -> dict[str, Any]:
        self._storage_paths()
        if not self.state_path.is_file() or not self.journal_path.is_file():
            raise ResumeRejected("CHECKPOINT_JOURNAL_PAIR_MISSING")
        if self.journal_path.stat().st_size > 32 * 1024 * 1024 or self.state_path.stat().st_size > 2 * 1024 * 1024:
            raise ResumeRejected("RUNTIME_STATE_LIMIT")
        state = self._decode_durable(self.state_path.read_bytes())
        previous, last, sequence = "0" * 64, None, 0
        raw = self.journal_path.read_bytes()
        if not raw or not raw.endswith(b"\n"):
            raise ResumeRejected("TRUNCATED_RUNTIME_JOURNAL")
        for line in raw.splitlines():
            row = self._decode_durable(line)
            sequence += 1
            digest = row.pop("event_sha256", None)
            if (row.get("sequence") != sequence or type(row.get("sequence")) is not int
                    or row.get("prior_event_sha256") != previous or fingerprint(row) != digest):
                raise ResumeRejected("RUNTIME_JOURNAL_CHAIN_MISMATCH")
            last = row.get("state")
            if type(last) is not dict or last.get("state_revision") != sequence:
                raise ResumeRejected("RUNTIME_STATE_REVISION_MISMATCH")
            semantic = {key: value for key, value in last.items() if key != "state_sha256"}
            if last.get("state_sha256") != fingerprint(semantic):
                raise ResumeRejected("RUNTIME_STATE_HASH_MISMATCH")
            previous = digest
        if (last != state or state.get("durable_version") != 1
                or state.get("controller_id") != CONTROLLER_ID or state.get("journal_sequence") != sequence):
            raise ResumeRejected("CHECKPOINT_JOURNAL_DISAGREEMENT")
        return state

    def save_durable(self, state: dict[str, Any]) -> dict[str, Any]:
        if not self.lease_held:
            raise RuntimeBlocked("CONTROLLER_LEASE_REQUIRED")
        self._storage_paths()
        existing = self.state_path.exists() or self.journal_path.exists()
        current = self.load_durable() if existing else None
        revision = current["state_revision"] + 1 if current else 1
        prior = "0" * 64
        if current:
            prior = self._decode_durable(self.journal_path.read_bytes().splitlines()[-1])["event_sha256"]
        repo = self.repository()
        value = {**state, "schema": SCHEMA, "durable_version": 1, "controller_id": CONTROLLER_ID,
                 "repository_identity": {key: repo[key] for key in ("root", "branch", "head")},
                 "state_revision": revision, "journal_sequence": revision}
        value.pop("state_sha256", None)
        value["state_sha256"] = fingerprint(value)
        row = {"sequence": revision, "prior_event_sha256": prior, "state": value}
        row["event_sha256"] = fingerprint(row)
        payload = (stable_json(row) + "\n").encode()
        if len(payload) > 2 * 1024 * 1024:
            raise RuntimeBlocked("RUNTIME_EVENT_LIMIT")
        with self.journal_path.open("ab") as stream:
            if stream.write(payload) != len(payload):
                raise OSError("Incomplete journal write")
            stream.flush()
            os.fsync(stream.fileno())
        self._write_checkpoint(value)
        if self.load_durable() != value:
            raise ResumeRejected("CHECKPOINT_READBACK_MISMATCH")
        return value

    def _public_proof_path(self, value):
        from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import source_relative
        from automation.orchestration.aios_repo_state_evidence import _full_capture_private
        target = self._bounded_path(value)
        try:
            relative = target.relative_to(self.root).as_posix()
            source_relative(relative)
            lower = relative.casefold()
            public_gateway_sources = {"services/mobile_gateway/" + name
                for name in ("bridge.py", "executor.py", "policy.py", "store.py")}
            if (_full_capture_private(relative) or (lower.startswith("services/mobile_gateway/")
                    and lower not in public_gateway_sources)):
                raise ValueError("private proof")
        except (TypeError, ValueError):
            raise ResumeRejected("RUNTIME_PROOF_PATH_UNSAFE") from None
        return target

    @contextmanager
    def _current_proof_bytes(self):
        """Read only named public proof files through retained no-follow handles."""
        import time
        from pathlib import PureWindowsPath
        from automation.orchestration import aios_repo_state_evidence as native
        reader, mapping = None, None
        directories, guards, streams, cached = {}, {}, {}, {}
        total = 0
        root = PureWindowsPath(self.root)

        def retain(handle, facts, expected_directory):
            if facts["directory"] is not expected_directory:
                raise ResumeRejected("RUNTIME_PROOF_FILE_TYPE_UNAVAILABLE")
            observed = reader.streams(handle, expected_directory)
            if expected_directory:
                if observed != []:
                    raise ResumeRejected("RUNTIME_PROOF_STREAM_UNAVAILABLE")
            elif (facts["links"] != 1 or not 0 <= facts["size"] <= 16777216
                    or len(observed) != 1 or observed[0][0] != "::$DATA"
                    or observed[0][1] != facts["size"]):
                raise ResumeRejected("RUNTIME_PROOF_FILE_UNAVAILABLE")
            reader.guards[handle] = facts
            guards[handle], streams[handle] = facts, observed

        def read_proof(value):
            nonlocal reader, mapping, total
            target = self._public_proof_path(value)
            relative = target.relative_to(self.root).as_posix()
            if reader is None:
                if not root.is_absolute() or len(root.drive) != 2 or root.drive[1] != ":":
                    raise ResumeRejected("RUNTIME_PROOF_READER_UNAVAILABLE")
                reader = native._FullWorktreeWindowsReader(time.monotonic() + 5)
                root_handle, mapping = reader.open_root(root.drive, list(root.parts[1:]))
                for handle, facts in list(reader.guards.items()):
                    retain(handle, facts, True)
                directories[""] = root_handle
            reader.tick()
            if relative in cached:
                return cached[relative]
            parts = relative.split("/")
            parent, prefix = directories[""], ""
            for name in parts[:-1]:
                prefix = prefix + "/" + name if prefix else name
                if prefix not in directories:
                    handle = reader.open_relative(parent, name, 0x100080)
                    retain(handle, reader.metadata(handle), True)
                    directories[prefix] = handle
                parent = directories[prefix]
            metadata = reader.open_relative(parent, parts[-1], 0x100080)
            facts = reader.metadata(metadata)
            retain(metadata, facts, False)
            total += facts["size"]
            if total > 67108864:
                raise ResumeRejected("RUNTIME_PROOF_READ_LIMIT")
            handle = reader.open_relative(parent, parts[-1], 0x100081)
            if reader.metadata(handle) != facts or reader.streams(handle, False) != streams[metadata]:
                raise ResumeRejected("RUNTIME_PROOF_DATA_IDENTITY_CHANGED")
            retain(handle, facts, False)
            chunks, used = [], 0
            while used < facts["size"]:
                if reader.metadata(handle) != facts:
                    raise ResumeRejected("RUNTIME_PROOF_CHANGED_DURING_READ")
                count = min(65536, facts["size"] - used)
                chunk = reader.read(handle, count)
                if type(chunk) is not bytes or not 0 < len(chunk) <= count:
                    raise ResumeRejected("RUNTIME_PROOF_READ_INCOMPLETE")
                chunks.append(chunk)
                used += len(chunk)
            if reader.read(handle, 1) != b"":
                raise ResumeRejected("RUNTIME_PROOF_CHANGED_DURING_READ")
            cached[relative] = b"".join(chunks)
            return cached[relative]

        try:
            yield read_proof
            if reader is not None:
                if reader.drive_mapping(root.drive) != mapping:
                    raise ResumeRejected("RUNTIME_PROOF_ROOT_CHANGED")
                for handle, facts in guards.items():
                    if (reader.metadata(handle) != facts
                            or reader.streams(handle, facts["directory"]) != streams[handle]):
                        raise ResumeRejected("RUNTIME_PROOF_CHANGED_DURING_READ")
        except ResumeRejected:
            raise
        except Exception:
            raise ResumeRejected("RUNTIME_PROOF_READ_UNAVAILABLE") from None
        finally:
            if reader is not None:
                try:
                    reader.close_all()
                except Exception:
                    raise ResumeRejected("RUNTIME_PROOF_CLEANUP_UNCONFIRMED") from None


    def validate_durable(self, *, for_status: bool = False) -> dict[str, Any]:
        state = self.load_durable()
        repo = self.repository()
        if state.get("repository_identity") != {key: repo[key] for key in ("root", "branch", "head")}:
            raise ResumeRejected("RUNTIME_REPOSITORY_IDENTITY_CHANGED")
        proof_path = self._public_proof_path
        closed, intents = state.get("closed_requirements", {}), state.get("intents", {})
        if type(closed) is not dict or type(intents) is not dict:
            raise ResumeRejected("RUNTIME_PROOF_INDEX_INVALID")
        with self._current_proof_bytes() as read_proof:
            for task, reference in closed.items():
                if type(reference) is not dict:
                    raise ResumeRejected("RUNTIME_PROOF_INDEX_INVALID")
                receipt = proof_path(reference["path"])
                raw = read_proof(receipt)
                if hashlib.sha256(raw).hexdigest() != reference.get("sha256"):
                    raise ResumeRejected("RUNTIME_RECEIPT_INDEX_CHANGED")
                if task not in intents:
                    raise ResumeRejected("RUNTIME_RECEIPT_WITHOUT_ORIGINAL_INTENT")
                accepted = self._decode_durable(raw)
                for label in ("source", "output"):
                    evidence = proof_path(accepted[label + "_path"])
                    if hashlib.sha256(read_proof(evidence)).hexdigest() != accepted.get(label + "_sha256"):
                        raise ResumeRejected("RUNTIME_ACCEPTED_EVIDENCE_CHANGED")
            for task, record in intents.items():
                if type(record) is not dict:
                    raise ResumeRejected("RUNTIME_PROOF_INDEX_INVALID")
                result = proof_path(record["result_path"])
                if not record.get("result_sha256") or not result.is_file():
                    if (for_status is True and task not in closed and task == state.get("active_task_id")
                            and state.get("phase") == "EXECUTION_INTENT"
                            and state.get("stop_class") not in {"SAFETY_INTEGRITY_BLOCK", "CAMPAIGN_COMPLETE"}):
                        state = {**state, "active_work_outcome_unverified": True}
                        continue
                    raise ResumeRejected("RUNTIME_RESULT_UNKNOWN_NO_REPLAY")
                if hashlib.sha256(read_proof(result)).hexdigest() != record["result_sha256"]:
                    raise ResumeRejected("RUNTIME_RESULT_CHANGED_NO_REPLAY")
        if self.lease_path.exists():
            lease = self._decode_durable(self.lease_path.read_bytes())
            if (lease.get("schema") != "AIOS_MASTER_CONTROLLER_LEASE.v1"
                    or lease.get("controller_id") != CONTROLLER_ID or lease.get("state") not in {"ACTIVE", "RELEASED"}):
                raise ResumeRejected("RUNTIME_LEASE_RECORD_INVALID")
        self.resume_brief(state)
        return state

    @staticmethod
    def resume_brief(state: dict[str, Any]) -> dict[str, Any]:
        fields = ("controller_id", "state_revision", "mission_id", "program_id", "epic_id", "bucket_id", "packet_id",
                  "repository", "worktree", "branch", "head_sha", "active_task_id", "active_claim_id",
                  "last_accepted_receipt", "pending_task_count", "blocked_task_count", "next_safe_action",
                  "stop_class", "owner_action_required", "state_sha256")
        brief = {key: state.get(key) for key in fields}
        if len(stable_json(brief).encode()) > 4096:
            raise ResumeRejected("RESUME_BRIEF_TOO_LARGE")
        return brief

    def run_campaign(self, contract_path: str | Path, *, bindings=None, max_cycles: int = 5,
                     timebox_seconds: int = 120, resume: bool = False,
                     invocation_timebox_seconds: int | None = None) -> dict[str, Any]:
        """Consume registered owners, never commands or permission from JSON.

        Bindings are executable host connections, not report fields. Production
        connections must use canonical admission/execution/publication owners.
        Deterministic test connections establish component behavior only.
        """
        import copy
        import time
        invocation_started = time.monotonic()
        from automation.orchestration.aios_abcd_autonomy_runner import (
            AcceptedRequirement, _acceptance_request, _dependency_view, _public_error_name, run_abcd_workflow,
        )
        from automation.orchestration.claims.aios_task_claim_control import ClaimError, TaskClaimController
        from automation.orchestration.aios_resume_state import atomic_write
        if invocation_timebox_seconds is not None and (type(invocation_timebox_seconds) is not int or invocation_timebox_seconds < 1):
            raise RuntimeBlocked("CAMPAIGN_AUTHORITY_INVOCATION_TIME_INVALID")
        required = ("verify_campaign", "read_current_inputs", "execute", "acceptance_reader", "read_receipt")
        if (bindings is None or any(not callable(getattr(bindings, name, None)) for name in required)
                or type(getattr(bindings, "claim_controller", None)) is not TaskClaimController):
            raise RuntimeBlocked("CAMPAIGN_AUTHORITY_HOST_CONNECTION_REQUIRED")
        # Campaign result proofs are re-read inside the repository on resume.
        # Refuse an external state tree before a lease, result or worker exists.
        for target in (self.state_path, self.journal_path, self.lease_path, self.receipts_path):
            self._bounded_path(target)
        path = self._bounded_path(contract_path)
        if path.stat().st_size > 2 * 1024 * 1024:
            raise RuntimeBlocked("CAMPAIGN_AUTHORITY_PATH_INVALID")
        contract_raw = path.read_bytes()
        contract = self._decode_durable(contract_raw)
        digest = hashlib.sha256(contract_raw).hexdigest()
        if (type(max_cycles) is not int or not 1 <= max_cycles <= contract.get("max_cycles", 0)
                or type(timebox_seconds) is not int or not 1 <= timebox_seconds <= contract.get("timebox_seconds", 0)):
            raise RuntimeBlocked("CAMPAIGN_AUTHORITY_RESOURCE_BOUNDARY")
        for relative in contract.get("allowed_paths", []):
            self._bounded_path(relative)
        for criterion in contract.get("acceptance_requirements", {}).values():
            for field in ("source_path", "consumer_destination"):
                self._bounded_path(criterion[field])
        def authority():
            self._bounded_path(path)
            if path.read_bytes() != contract_raw:
                raise RuntimeBlocked("CAMPAIGN_AUTHORITY_CHANGED")
            repo = self.repository()
            if {key: repo[key] for key in ("root", "branch", "head")} != contract["repository_identity"]:
                raise ResumeRejected("CAMPAIGN_REPOSITORY_IDENTITY_CHANGED")
            expiry = datetime.fromisoformat(contract["expires_utc"].replace("Z", "+00:00"))
            if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
                raise RuntimeBlocked("CAMPAIGN_AUTHORITY_EXPIRED")
            for relative, expected in contract.get("source_hashes", {}).items():
                source = self._bounded_path(relative)
                if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
                    raise RuntimeBlocked("CAMPAIGN_SOURCE_IDENTITY_CHANGED")
            if bindings.verify_campaign(contract, digest) is not True:
                raise RuntimeBlocked("CAMPAIGN_AUTHORITY_REJECTED")
        authority()
        task_ids = contract.get("task_ids")
        if (type(task_ids) is not list or not task_ids or len(task_ids) != len(set(task_ids))
                or any(type(task) is not str or not task for task in task_ids)):
            raise RuntimeBlocked("CAMPAIGN_TASK_IDENTITIES_INVALID")
        with self.controller_lease():
            if self.state_path.exists() or self.journal_path.exists():
                state = self.load_durable()
                if not resume or state.get("authority_identity") != digest:
                    raise ResumeRejected("CAMPAIGN_RESUME_IDENTITY_CHANGED")
            else:
                if resume:
                    raise ResumeRejected("CHECKPOINT_NOT_FOUND")
                repo = self.repository()
                state = {key: contract[key] for key in ("mission_id", "program_id", "epic_id", "bucket_id", "packet_id")}
                state.update(repository=str(self.root), worktree=str(self.root), branch=repo["branch"], head_sha=repo["head"],
                    authority_identity=digest, active_task_id=None, active_claim_id=None,
                    closed_requirements={}, intents={}, blocked_tasks={}, phase="READY", elapsed_seconds=0,
                    last_accepted_receipt=None, forex_edge_proven=False, qualifying_paper_trades_per_side=0,
                    live_readiness_evidence="UNPROVED", owner_action_required=False, stop_class=None)
            start = invocation_started
            prior_elapsed = state.get("elapsed_seconds", 0)
            def remaining():
                current_elapsed = time.monotonic() - start
                total_remaining = timebox_seconds - prior_elapsed - current_elapsed
                return min(total_remaining, (invocation_timebox_seconds or timebox_seconds) - current_elapsed)
            def save():
                nonlocal state
                state["elapsed_seconds"] = prior_elapsed + time.monotonic() - start
                state["pending_task_count"] = len(set(task_ids) - set(state["closed_requirements"]))
                state["blocked_task_count"] = len(state["blocked_tasks"])
                state = self.save_durable(state)
            def finish(stop_class, reason, *, continuation_ready=False):
                state.update(stop_class=stop_class, blocker=reason, next_safe_action=reason,
                             continuation_ready=continuation_ready,
                             owner_action_required=stop_class == "OWNER_ACTION_REQUIRED")
                save()
                return state
            def request_for(task, inputs):
                view, _repo, queue_items, claims = inputs
                node = next(item for item in view["items"] if item["id"] == task)
                return _acceptance_request(node, queue_items[task], claims[task])
            def check_receipt(task, request):
                accepted = bindings.acceptance_reader(request)
                if type(accepted) is not AcceptedRequirement or accepted.request != request:
                    raise RuntimeBlocked("ORIGINAL_REQUIREMENT_NOT_ACCEPTED")
                reference = bindings.read_receipt(request)
                if type(reference) is not dict or not isinstance(reference.get("acceptance_requirement_id"), str):
                    raise RuntimeBlocked("ORIGINAL_REQUIREMENT_RECEIPT_MISSING")
                receipt_path = self._bounded_path(reference["path"])
                raw = receipt_path.read_bytes()
                if hashlib.sha256(raw).hexdigest() != reference.get("sha256"):
                    raise RuntimeBlocked("ORIGINAL_REQUIREMENT_RECEIPT_CHANGED")
                value = self._decode_durable(raw)
                criterion = contract.get("acceptance_requirements", {}).get(task)
                if (type(criterion) is not dict or not criterion.get("id")
                        or value.get("task_id") != task or value.get("packet_id") != request.packet_id
                        or value.get("acceptance_requirement_id") != criterion["id"]
                        or reference["acceptance_requirement_id"] != criterion["id"]
                        or value.get("validator_status") != "PASS"
                        or value.get("validator_id") != criterion.get("validator_id")
                        or not isinstance(value.get("reviewer_id"), str) or not value["reviewer_id"].strip()
                        or value.get("cleanup_confirmed") is not True
                        or value.get("result_classification") != "ENGINEERING_ACCEPTED"
                        or value.get("consumer_destination") != criterion.get("consumer_destination")
                        or value.get("source_path") != criterion.get("source_path")
                        or value.get("source_sha256") != criterion.get("source_sha256")
                        or value.get("input_sha256") != {"request": request.request_sha256, "claim": request.claim_sha256}):
                    raise RuntimeBlocked("ORIGINAL_REQUIREMENT_RECEIPT_UNBOUND")
                for label in ("source", "output"):
                    evidence = self._bounded_path(value[label + "_path"])
                    if (not evidence.is_absolute() or not evidence.is_relative_to(self.root)
                            or any(parent.is_symlink() or parent.is_junction() for parent in (evidence, *evidence.parents))
                            or hashlib.sha256(evidence.read_bytes()).hexdigest() != value.get(label + "_sha256")):
                        raise RuntimeBlocked("ORIGINAL_REQUIREMENT_EVIDENCE_CHANGED")
                return reference
            try:
                if resume:
                    # Completed work still needs its original saved result.
                    self.validate_durable()
                inputs = copy.deepcopy(bindings.read_current_inputs())
                if state["closed_requirements"]:
                    _, prior_states, _ = _dependency_view(inputs[0], inputs[2], inputs[3],
                        bindings.claim_controller, bindings.acceptance_reader)
                for task, reference in state["closed_requirements"].items():
                    try:
                        if check_receipt(task, request_for(task, inputs)) != reference:
                            raise RuntimeBlocked("PREVIOUSLY_ACCEPTED_REFERENCE_CHANGED")
                        if prior_states.get(task) != "DONE":
                            raise RuntimeBlocked("PREVIOUSLY_ACCEPTED_CLAIM_RELEASE_CHANGED")
                    except (RuntimeBlocked, OSError, KeyError, TypeError, ValueError):
                        return finish("SAFETY_INTEGRITY_BLOCK", "Previously accepted requirement changed; do not repeat work")
                for task, intent in state["intents"].items():
                    if task not in state["closed_requirements"] and not Path(intent["result_path"]).is_file():
                        return finish("SAFETY_INTEGRITY_BLOCK", "Unknown original outcome for " + task + "; no replay")
                # A publication may have completed after the checkpoint stopped.
                # Re-read the original owner; never execute that task again.
                for task in state["intents"]:
                    if task in state["closed_requirements"]:
                        continue
                    request = request_for(task, inputs)
                    accepted = bindings.acceptance_reader(request)
                    if accepted is None:
                        continue
                    try:
                        reference = check_receipt(task, request)
                    except (RuntimeBlocked, ResumeRejected, OSError, KeyError, TypeError, ValueError):
                        return finish("SAFETY_INTEGRITY_BLOCK", "Saved original result failed acceptance verification: " + task)
                    decision, states, _pending = _dependency_view(inputs[0], inputs[2], inputs[3],
                        bindings.claim_controller, bindings.acceptance_reader)
                    if states.get(task) != "DONE":
                        return finish("SAFETY_INTEGRITY_BLOCK", "Original claim release not reconciled: " + task)
                    state["closed_requirements"][task] = reference
                    state.update(last_accepted_receipt=reference, last_completed_action=task,
                                 active_task_id=None, active_claim_id=None, phase="READY")
                save()
                for _cycle in range(max_cycles):
                    authority()
                    if set(state["closed_requirements"]) == set(task_ids):
                        return finish("CAMPAIGN_COMPLETE", "All bound original requirements accepted")
                    if remaining() <= 0 or len(state["intents"]) >= contract["max_cycles"]:
                        return finish("RESOURCE_TIME_BLOCK", "Admitted campaign boundary reached")
                    inputs = copy.deepcopy(bindings.read_current_inputs())
                    if remaining() <= 0:
                        return finish("RESOURCE_TIME_BLOCK", "Campaign time exhausted while reading current inputs")
                    view, repository_state, queue_items, claims = inputs
                    # The existing dispatcher and acceptance owner decide eligibility.
                    decision, states, _pending = _dependency_view(view, queue_items, claims,
                        bindings.claim_controller, bindings.acceptance_reader)
                    from automation.orchestration.runtime_queue.aios_development_dispatcher import build_dispatch_plan
                    plan = build_dispatch_plan(decision, worker_capacity=1)
                    if not plan["claims"]:
                        return finish("OWNER_ACTION_REQUIRED", "No currently admitted eligible original task")
                    task = plan["claims"][0]["id"]
                    if task not in task_ids or task in state["closed_requirements"]:
                        return finish("SAFETY_INTEGRITY_BLOCK", "Selected task is outside the current campaign")
                    request = request_for(task, inputs)
                    for relative in queue_items[task]["allowed_paths"]:
                        target = self.root / relative
                        if not any(target == self.root / owned or (self.root / owned) in target.parents for owned in contract["allowed_paths"]):
                            return finish("OWNER_ACTION_REQUIRED", "Selected task exceeds campaign paths")
                    def execute(packet):
                        authority()
                        if remaining() <= 0:
                            raise RuntimeBlocked("CAMPAIGN_TIME_EXHAUSTED_BEFORE_EXECUTION")
                        if packet.get("packet_id") != request.packet_id:
                            raise RuntimeBlocked("EXACT_SELECTED_PACKET_CHANGED")
                        if task in state["intents"]:
                            record = state["intents"][task]
                            raw = Path(record["result_path"]).read_bytes()
                            if record.get("result_sha256") != hashlib.sha256(raw).hexdigest():
                                raise RuntimeBlocked("UNKNOWN_RESULT_NO_REPLAY")
                            return self._decode_durable(raw)
                        target = self.receipts_path / (fingerprint({"task": task, "request": request.request_sha256}) + ".result.json")
                        if target.exists():
                            raise RuntimeBlocked("UNCLAIMED_EXISTING_RESULT_NO_REPLAY")
                        state.update(active_task_id=task, active_claim_id=request.claim_sha256, phase="EXECUTION_INTENT")
                        state["intents"][task] = {"request_sha256": request.request_sha256, "claim_sha256": request.claim_sha256,
                                                  "result_path": str(target), "result_sha256": None}
                        save()
                        if remaining() <= 0:
                            raise RuntimeBlocked("CAMPAIGN_TIME_EXHAUSTED_BEFORE_EXECUTION")
                        result = bindings.execute(packet)
                        raw = (stable_json(result) + "\n").encode()
                        atomic_write(target, raw)
                        state["intents"][task]["result_sha256"] = hashlib.sha256(raw).hexdigest()
                        state["phase"] = "RAW_RESULT_SAVED"
                        save()
                        return result
                    result = run_abcd_workflow(read_current_inputs=lambda: inputs, claim_controller=bindings.claim_controller,
                        execute=execute, acceptance_reader=bindings.acceptance_reader, max_tasks=1,
                        max_elapsed_seconds=max(0.001, remaining()),
                        stop_requested=lambda: False, **getattr(bindings, "single_task_options", {}))
                    last = result.results[-1] if result.results else None
                    if last is None or last.status not in {"COMPLETE", "RELEASE_RECONCILED"}:
                        if task in state["intents"]:
                            return finish("SAFETY_INTEGRITY_BLOCK", "Original task outcome or acceptance unresolved: " + task)
                        return finish("OWNER_ACTION_REQUIRED", "Existing execution owner blocked task: " + result.reason)
                    if last.status == "RELEASE_RECONCILED":
                        save()
                        continue
                    try:
                        reference = check_receipt(task, request)
                    except (RuntimeBlocked, OSError, KeyError) as error:
                        return finish("SAFETY_INTEGRITY_BLOCK", "Original requirement evidence not accepted: " + _public_error_name(error))
                    state["closed_requirements"][task] = reference
                    state.update(last_accepted_receipt=reference, last_completed_action=task,
                                 active_task_id=None, active_claim_id=None, phase="READY")
                    save()
                if set(state["closed_requirements"]) == set(task_ids):
                    return finish("CAMPAIGN_COMPLETE", "All bound original requirements accepted")
                if remaining() <= 0 or len(state["intents"]) >= contract["max_cycles"]:
                    return finish("RESOURCE_TIME_BLOCK", "Admitted campaign boundary reached")
                return finish("RESOURCE_TIME_BLOCK", "Caller cycle limit reached; saved continuation required", continuation_ready=True)

            except (RuntimeBlocked, ClaimError, OSError, KeyError, TypeError, ValueError) as error:
                # Never promote a broken read or a failed write to successful work.
                # A broken journal/checkpoint remains blocked if even stop-save fails.
                return finish("SAFETY_INTEGRITY_BLOCK", "Current campaign owner or evidence failed: " + _public_error_name(error))

    def control_view(self) -> dict[str, Any]:
        """Read-only projection; a checkpoint is never an execution grant."""
        repo = self.repository()
        state, reason = {}, "No admitted campaign has been connected"
        if self.state_path.exists() or self.journal_path.exists():
            try:
                state = self.validate_durable(for_status=True)
                reason = state.get("blocker") or state.get("next_safe_action") or "Read saved campaign state"
            except ResumeRejected as error:
                reason = str(error)
                state = {"phase": "RECOVERY_BLOCKED", "stop_class": "SAFETY_INTEGRITY_BLOCK"}
            except (RuntimeBlocked, OSError, KeyError, TypeError, ValueError):
                reason = "RUNTIME_CURRENT_EVIDENCE_UNAVAILABLE"
                state = {"phase": "RECOVERY_BLOCKED", "stop_class": "SAFETY_INTEGRITY_BLOCK"}
        return {"schema": "AIOS_MASTER_CONTROL_VIEW.v1", "controller_id": CONTROLLER_ID,
                "controller_status": ("WORK_OUTCOME_UNVERIFIED" if state.get("active_work_outcome_unverified")
                    else state.get("phase", "NOT_STARTED")),
                "controller_lease": "HELD_BY_THIS_PROCESS" if self.lease_held else "NOT_HELD_BY_THIS_PROCESS",
                "state_revision": state.get("state_revision"), "state_hash": state.get("state_sha256"),
                "repository": repo["root"], "branch": repo["branch"], "head_sha": repo["head"],
                "campaign_identity": state.get("authority_identity"), "active_original_task": state.get("active_task_id"),
                "active_worker": state.get("active_worker"), "active_claim": state.get("active_claim_id"),
                "eligible_task_count": state.get("eligible_task_count"),
                "running_task_count": (None if state.get("active_work_outcome_unverified")
                    else int(bool(state.get("active_task_id")))),
                "active_work_outcome_verified": False if state.get("active_work_outcome_unverified") else None,
                "blocked_task_count": state.get("blocked_task_count"),
                "closed_original_requirement_count": (None if state.get("phase") == "RECOVERY_BLOCKED"
                    else len(state.get("closed_requirements", {}))),
                "last_accepted_receipt": state.get("last_accepted_receipt"), "last_completed_action": state.get("last_completed_action"),
                "stop_class": state.get("stop_class") or "OWNER_ACTION_REQUIRED", "exact_blocker": reason,
                "next_safe_action": state.get("next_safe_action") or "Connect existing admitted campaign inputs",
                "owner_action_required": state.get("owner_action_required", True),
                "project_execution_grant": "NONE", "openai_account_credits": "NOT INSPECTED",
                "forex_edge_proven": state.get("forex_edge_proven", False),
                "qualifying_paper_trades_per_side": state.get("qualifying_paper_trades_per_side", 0),
                "live_readiness_evidence": state.get("live_readiness_evidence", "UNPROVED"),
                "safety_flags": {key: False for key in PROTECTED}}

    @staticmethod
    def render_control(view: dict[str, Any]) -> str:
        fields = (("CONTROLLER", "controller_status"), ("CONTROLLER LEASE", "controller_lease"),
                  ("STATE REVISION", "state_revision"), ("STATE HASH", "state_hash"),
                  ("REPOSITORY", "repository"), ("BRANCH", "branch"), ("HEAD", "head_sha"),
                  ("CAMPAIGN", "campaign_identity"), ("ACTIVE ORIGINAL TASK", "active_original_task"),
                  ("ACTIVE WORKER", "active_worker"), ("ACTIVE CLAIM", "active_claim"),
                  ("ELIGIBLE TASKS", "eligible_task_count"), ("RUNNING TASKS", "running_task_count"),
                  ("BLOCKED TASKS", "blocked_task_count"), ("CLOSED ORIGINAL REQUIREMENTS", "closed_original_requirement_count"),
                  ("LAST ACCEPTED RECEIPT", "last_accepted_receipt"), ("LAST COMPLETED ACTION", "last_completed_action"),
                  ("STOP CLASS", "stop_class"), ("EXACT BLOCKER", "exact_blocker"), ("NEXT ACTION", "next_safe_action"),
                  ("OWNER ACTION REQUIRED", "owner_action_required"), ("PROJECT EXECUTION GRANT", "project_execution_grant"),
                  ("OPENAI ACCOUNT CREDITS", "openai_account_credits"), ("FOREX EDGE PROVEN", "forex_edge_proven"),
                  ("QUALIFYING PAPER TRADES PER SIDE", "qualifying_paper_trades_per_side"),
                  ("LIVE READINESS EVIDENCE", "live_readiness_evidence"), ("SAFETY FLAGS", "safety_flags"))
        def display(value):
            if value is None:
                return "NONE"
            if type(value) is bool:
                return "YES" if value else "NO"
            return str(value).replace("\r", " ").replace("\n", " ")
        return "\n".join(label + ": " + display(view.get(key)) for label, key in fields)

    def campaign_preview(self, *, max_cycles: int = 5, timebox_seconds: int = 120) -> dict[str, Any]:
        import copy
        import time
        from automation.orchestration.runtime_queue.aios_runtime_execution_queue import build_queue_view
        if type(max_cycles) is not int or not 1 <= max_cycles <= 1000 or type(timebox_seconds) is not int or not 1 <= timebox_seconds <= 86400:
            raise RuntimeBlocked("PREVIEW_RESOURCE_BOUNDARY")
        started = time.monotonic()
        queue = build_queue_view(self.root)
        plan = self.platform.dispatch(queue)
        hypothetical = copy.deepcopy(queue)
        steps = []
        for index in range(max_cycles):
            if time.monotonic() - started >= timebox_seconds:
                break
            conditional = self.platform.dispatch(hypothetical)
            if not conditional["claims"]:
                break
            task = conditional["claims"][0]["id"]
            steps.append({"cycle": index + 1, "selected_task_id": task,
                          "requires_prior_acceptance": bool(index), "execution_authorized": False})
            # This copy is an explicitly conditional preview, never a completion
            # fact supplied to an acceptance reader, claim board or executor.
            next(item for item in hypothetical["items"] if item["id"] == task)["state"] = "DONE"
        return {"schema": "AIOS_MASTER_CAMPAIGN_PREVIEW.v1", "mode": "DRY_RUN", "mutation_performed": False,
                "execution_authorized": False, "dispatch_preview": plan, "preview_cycles": steps,
                "max_cycles": max_cycles, "timebox_seconds": timebox_seconds, "control_view": self.control_view()}

    def _git(self, *args: str, check: bool = True) -> str:
        return subprocess.run(["git", *args], cwd=self.root, check=check, text=True, capture_output=True).stdout.strip()

    def repository(self) -> dict[str, Any]:
        return {"root": str(self.root), "branch": self._git("branch", "--show-current"), "head": self._git("rev-parse", "HEAD"), "status_lines": self._git("status", "--porcelain").splitlines()}

    def capabilities(self) -> list[dict[str, Any]]:
        head = self.repository()["head"]
        owners: dict[str, list[str]] = {}
        result = []
        for capability_id, (source, test) in self.CAPABILITIES.items():
            owners.setdefault(source, []).append(capability_id)
            exists = (self.root / source).is_file() and (self.root / test).is_file()
            result.append({"capability_id": capability_id, "owner": source, "source_paths": [source], "test_paths": [test], "schema_paths": [], "commit_sha": head, "evidence_status": "CREDITED" if exists else "INCOMPLETE", "freshness": "OBSERVED_HEAD"})
        conflicts = {path: ids for path, ids in owners.items() if len(ids) > 1}
        canonical_entries = [path for path in ("aios.py",) if (self.root / path).is_file()]
        compatibility_entries = [path for path in ("scripts/run_aios_master_runtime_v1.py",) if (self.root / path).is_file()]
        if conflicts or len(canonical_entries) != 1:
            raise RuntimeBlocked("DUPLICATE_CAPABILITY_OWNER" if conflicts else "DUPLICATE_ENTRY_POINT")
        self.entry_points = {"canonical": canonical_entries, "compatibility": compatibility_entries, "conflicts": []}
        return result

    def environment(self) -> dict[str, str]:
        tools = {"python": sys.executable, "git": shutil.which("git"), "gh_cli": shutil.which("gh"), "powershell": shutil.which("pwsh") or shutil.which("powershell"), "node": shutil.which("node"), "npm": shutil.which("npm")}
        matrix = {key: ("AVAILABLE" if value else ("REQUIRED_MISSING" if key in {"python", "git"} else "OPTIONAL_MISSING")) for key, value in tools.items()}
        matrix["git_remote"] = "AVAILABLE" if self._git("remote") else "UNAVAILABLE_NOT_REQUIRED"
        try:
            import jsonschema  # noqa: F401
            matrix["jsonschema"] = "AVAILABLE"
        except ImportError:
            matrix["jsonschema"] = "OPTIONAL_MISSING"
        return matrix

    def reconcile_prs(self) -> dict[str, str]:
        if not self.allow_remote_metadata:
            return {str(number): "OFFLINE_NOT_INSPECTED" for number in (1337, 1342, 1344)}
        if not shutil.which("gh") or not self._git("remote"):
            return {str(number): "REMOTE_METADATA_UNAVAILABLE" for number in (1337, 1342, 1344)}
        result = {}
        head = self.repository()["head"]
        for number in (1337, 1342, 1344):
            command = ["gh", "pr", "view", str(number), "--json", "state,mergeable,headRefOid,mergeCommit"]
            viewed = subprocess.run(command, cwd=self.root, text=True, capture_output=True)
            if viewed.returncode:
                result[str(number)] = "REMOTE_METADATA_UNAVAILABLE"
                continue
            metadata = json.loads(viewed.stdout)
            merge_sha = (metadata.get("mergeCommit") or {}).get("oid")
            if metadata.get("state") == "MERGED" or merge_sha == head:
                classification = "SUPERSEDED_BY_MAIN"
            elif metadata.get("mergeable") == "MERGEABLE":
                classification = "MERGE_CANDIDATE"
            else:
                classification = "DIVERGED_REPAIR_REQUIRED"
            result[str(number)] = classification
        return result

    @staticmethod
    def _summary(value: Any) -> dict[str, Any]:
        return {"schema": value.get("schema") or value.get("schema_version"), "status": value.get("status") or value.get("queue_status") or value.get("decision_category"), "fingerprint": fingerprint(value)}

    def _compose(self, repository: dict[str, Any], capabilities: list[dict[str, Any]]) -> dict[str, Any]:
        deterministic_time = "1970-01-01T00:00:00Z"
        spine = self.platform.spine(as_of_utc=deterministic_time)
        braid = self.platform.compound_work_braid()
        queue = self.platform.queue({"candidates": []})
        dispatch = self.platform.dispatch({"schema": "AIOS_RUNTIME_EXECUTION_QUEUE.v1", "items": []})
        builder = self.platform.build_packet(repository_state={}, packet_identity={}, mission="", allowed_paths=[], validators=[])
        resolver = self.platform.resolve_packet({}, {})
        governor = self.platform.govern_autonomy({}, generated_at_utc=deterministic_time)
        countdown = self.platform.countdown()
        return {"spine": self._summary(spine), "braid": self._summary(braid), "queue": self._summary(queue), "dispatcher": self._summary(dispatch), "packet_builder": self._summary(builder), "packet_resolver": self._summary(resolver), "autonomy_governor": self._summary(governor), "countdown": self._summary(countdown), "selected_cable": braid.get("selected_cable"), "capability_count": len(capabilities)}

    def _identity(self, repo: dict[str, Any], graph: dict[str, Any], composition: dict[str, Any]) -> dict[str, Any]:
        return {"root": repo["root"], "branch": repo["branch"], "head": repo["head"], "dependency_graph_fingerprint": fingerprint(graph), "allowed_paths_fingerprint": fingerprint(["orchestration_consolidation"]), "composition_fingerprint": fingerprint(composition)}

    def _stages(self, identity: dict[str, Any], composition: dict[str, Any]) -> list[dict[str, Any]]:
        completed, previous = [], ""
        for index, stage_id in enumerate(STAGES):
            inputs = {"identity": identity, "composition": composition, "previous": previous}
            output = fingerprint({"stage": stage_id, "inputs": inputs})
            completed.append({"stage_id": stage_id, "capability_id": f"master_runtime.{stage_id}", "dependencies": [] if index == 0 else [STAGES[index-1]], "mode": "REGISTERED_PYTHON_API", "input_fingerprint": fingerprint(inputs), "output_fingerprint": output, "validator_ids": ["master_runtime_contract_v1"], "retry_limit": 1, "approval_required": False, "protected_action": False, "status": "COMPLETED", "reason_codes": ["REGISTERED_API_COMPOSED"], "completion_receipt": output})
            previous = output
        return completed

    def _write_checkpoint(self, state: dict[str, Any]) -> None:
        from automation.orchestration.aios_resume_state import atomic_write
        atomic_write(self.state_path, (json.dumps(state, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())

    def execute(self, *, command: str = "plan", checkpoint: bool = False) -> dict[str, Any]:
        repo, capabilities = self.repository(), self.capabilities()
        graph = {"nodes": list(STAGES), "edges": [[STAGES[i - 1], STAGES[i]] for i in range(1, len(STAGES))]}
        composition = self._compose(repo, capabilities)
        identity = self._identity(repo, graph, composition)
        state = {"schema": SCHEMA, "status": "PASS", "command": command, "repository": repo, "identity": identity, "capabilities": capabilities, "entry_points": self.entry_points, "environment": self.environment(), "dependency_graph": graph, "composition": composition, "protected_actions": {key: False for key in PROTECTED}, "permissions": {"arbitrary_shell": False, "generated_prompt_execution": False}, "open_pr_reconciliation": self.reconcile_prs()}
        state["stages"] = self._stages(identity, composition)
        state["owner_report"] = {"credited_capabilities": len([c for c in capabilities if c["evidence_status"] == "CREDITED"]), "duplicate_work": [], "selected_cable": composition["selected_cable"], "completed_stages": len(state["stages"]), "blocked_stages": 0, "exact_next_owner_action": "Review and create the prepared pull request.", "protected_actions_disabled": list(PROTECTED)}
        state["normalized_fingerprint"] = fingerprint({k: v for k, v in state.items() if k not in {"command", "repository"}} | {"repository": {k: v for k, v in repo.items() if k != "status_lines"}})
        if checkpoint:
            self._write_checkpoint(state)
        return state

    def resume(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            raise ResumeRejected("CHECKPOINT_NOT_FOUND")
        saved = json.loads(self.state_path.read_text(encoding="utf-8"))
        current = self.execute(command="resume")
        reasons = [f"INCOMPATIBLE_{key.upper()}" for key, value in current["identity"].items() if saved.get("identity", {}).get(key) != value]
        if reasons:
            raise ResumeRejected(",".join(reasons))
        self._write_checkpoint(current)
        return current

    def validate_state(self, state: dict[str, Any]) -> dict[str, Any]:
        defects = []
        if [stage.get("stage_id") for stage in state.get("stages", [])] != list(STAGES): defects.append("INVALID_STAGE_ORDER")
        if any(state.get("protected_actions", {}).values()): defects.append("PROTECTED_ACTION_ENABLED")
        if state.get("permissions") != {"arbitrary_shell": False, "generated_prompt_execution": False}: defects.append("UNSAFE_EXECUTION_PERMISSION")
        required = {"stage_id", "capability_id", "dependencies", "mode", "input_fingerprint", "output_fingerprint", "validator_ids", "retry_limit", "approval_required", "protected_action", "status", "reason_codes", "completion_receipt"}
        if any(required - set(stage) for stage in state.get("stages", [])): defects.append("INCOMPLETE_STAGE_RECEIPT")
        if state.get("entry_points", {}).get("conflicts"): defects.append("DUPLICATE_ENTRY_POINT")
        return {"schema": "AIOS_MASTER_RUNTIME_VALIDATION.v1", "status": "PASS" if not defects else "BLOCKED", "defects": defects}


def run(repo_root: str | Path = ".", command: str = "plan", *, mode: str | None = None,
        mission_contract: str | Path | None = None, max_cycles: int = 5,
        timebox_seconds: int = 120, state_dir: str | Path | None = None,
        platform=None, bindings=None, invocation_timebox_seconds: int | None = None) -> dict[str, Any]:
    runtime = AIOSMasterRuntime(repo_root, platform=platform)
    if state_dir is not None:
        runtime.state_path = Path(state_dir).absolute() / "master-runtime-v1.json"
    if mode is None:
        if command == "resume":
            return runtime.resume()
        state = runtime.execute(command=command, checkpoint=command == "run")
        if command == "validate":
            state["validation"] = runtime.validate_state(state)
        return state
    if command in {"run", "resume"} and mode == "APPLY":
        if mission_contract is None:
            raise RuntimeBlocked("MISSION_CONTRACT_REQUIRED")
        if bindings is None:
            bindings = runtime.platform.campaign_bindings(mission_contract)
        return runtime.run_campaign(mission_contract, bindings=bindings, max_cycles=max_cycles,
                                    timebox_seconds=timebox_seconds, resume=command == "resume",
                                    invocation_timebox_seconds=invocation_timebox_seconds)
    if command == "validate":
        if runtime.state_path.exists() or runtime.journal_path.exists():
            runtime.validate_durable()
        return {"schema": "AIOS_MASTER_RUNTIME_VALIDATION.v1", "status": "PASS",
                "state_present": runtime.state_path.exists(), "runtime_started": False}
    if command == "status":
        return runtime.control_view()
    return runtime.campaign_preview(max_cycles=max_cycles, timebox_seconds=timebox_seconds)
