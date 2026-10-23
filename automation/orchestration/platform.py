"""Canonical public API for the AI_OS Orchestration Platform V1.

This module is intentionally a facade: domain logic remains in the established,
tested components.  Callers should depend on this module instead of composing
queue, dispatch, packet, resolution, spine, reporting, and countdown modules.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from automation.orchestration.aios_canonical_orchestration_spine_v1 import (
    build_orchestration_spine,
    render_orchestration_report,
)
from automation.orchestration.aios_codex_packet_builder import build_repository_aligned_apply_packet
from automation.orchestration.aios_codex_packet_from_queue import build_codex_packet_from_queue_item
from automation.orchestration.aios_packet_queue_planner import build_packet_queue_planner
from automation.orchestration.aios_work_countdown_v1 import (
    build_work_countdown,
    load_canonical_work_packet_inventory,
)
from automation.orchestration.aios_compound_work_braid_v1 import CompoundWorkBraidController
from automation.orchestration.runtime_queue.aios_development_dispatcher import build_dispatch_plan
from automation.orchestration.runtime_queue.aios_execution_packet_resolver import resolve_execution_packet

__all__ = ["OrchestrationPlatform", "create_platform"]


class OriginalCampaignRecordReaders:
    """Read pinned originals without creating claims, approvals or results."""

    def __init__(self, repo_root, original_record_sources, claim_controller, *, native_admission_reader):
        import json
        from automation.orchestration.aios_repo_state_evidence import campaign_json
        from automation.orchestration.claims.aios_task_claim_control import TaskClaimController
        if type(claim_controller) is not TaskClaimController:
            raise ValueError("ORIGINAL_RECORD_CLAIM_OWNER_REQUIRED")
        if native_admission_reader is not None and not callable(native_admission_reader):
            raise ValueError("ORIGINAL_RECORD_NATIVE_READER_REQUIRED")
        self.root = Path(repo_root).resolve(strict=True)
        self.sources = json.loads(campaign_json(original_record_sources))
        if (type(self.sources) is not dict or set(self.sources) != {"inputs", "tasks"}
                or type(self.sources["tasks"]) is not dict or not self.sources["tasks"]):
            raise ValueError("ORIGINAL_RECORD_SOURCES_INVALID")
        self.claim_controller = claim_controller
        self.native_admission_reader = native_admission_reader

    def _path(self, relative):
        from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import source_relative
        try:
            path = self.root / source_relative(relative)
            for part in (path, *path.parents):
                if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
                    raise ValueError("reparse path")
            if not path.resolve().is_relative_to(self.root):
                raise ValueError("outside root")
            return path
        except (OSError, ValueError, TypeError) as exc:
            raise ValueError("ORIGINAL_RECORD_PATH_INVALID") from exc

    def _raw(self, reference):
        import hashlib
        import re
        from automation.orchestration.relay.aios_self_consuming_codex_cycle_v1 import _native_file
        if (type(reference) is not dict or set(reference) != {"path", "sha256"}
                or type(reference["sha256"]) is not str
                or not re.fullmatch(r"[0-9a-f]{64}", reference["sha256"])):
            raise ValueError("ORIGINAL_RECORD_PIN_INVALID")
        try:
            raw = _native_file(self._path(reference["path"]))
        except (OSError, ValueError, TypeError) as exc:
            raise ValueError("ORIGINAL_RECORD_UNREADABLE") from exc
        if hashlib.sha256(raw).hexdigest() != reference["sha256"]:
            raise ValueError("ORIGINAL_RECORD_CHANGED")
        return raw

    def _json(self, reference):
        from automation.orchestration.relay.aios_self_consuming_codex_cycle_v1 import _native_json
        from automation.orchestration.aios_repo_state_evidence import campaign_json
        try:
            value = _native_json(self._raw(reference))
            campaign_json(value)
            if type(value) is not dict:
                raise ValueError("object required")
            return value
        except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
            raise ValueError("ORIGINAL_RECORD_JSON_INVALID") from exc

    def _task_id(self, identity):
        # The existing executor calls by packet ID; task IDs can differ.
        matches = []
        for task, refs in self.sources["tasks"].items():
            if type(task) is not str or type(refs) is not dict:
                raise ValueError("ORIGINAL_RECORD_TASK_INVALID")
            selected = self._json(refs.get("selection"))
            packet = selected.get("packet")
            if type(packet) is not dict:
                raise ValueError("ORIGINAL_RECORD_SELECTION_INVALID")
            if identity == task or identity == packet.get("packet_id"):
                matches.append(task)
        if type(identity) is not str or len(matches) != 1:
            raise ValueError("ORIGINAL_RECORD_TASK_MISSING_OR_AMBIGUOUS")
        return matches[0]

    def _task(self, task):
        return self.sources["tasks"][self._task_id(task)]

    @staticmethod
    def _same(left, right):
        from automation.orchestration.aios_repo_state_evidence import campaign_json
        return campaign_json(left) == campaign_json(right)

    def read_original_selection(self, task):
        task = self._task_id(task)
        value = self._json(self.sources["tasks"][task].get("selection"))
        if (set(value) != {"packet", "claim", "queue_item"}
                or any(type(value[key]) is not dict for key in value)
                or type(value["packet"].get("packet_id")) is not str or not value["packet"]["packet_id"].strip()
                or value["queue_item"].get("packet_id") != value["packet"]["packet_id"]
                or value["claim"].get("task_id") != task
                or value["claim"].get("packet_id") != value["packet"]["packet_id"]):
            raise ValueError("ORIGINAL_RECORD_SELECTION_UNBOUND")
        return value

    def read_current_inputs(self):
        value = self._json(self.sources["inputs"])
        keys = ("queue_view", "repository_state", "queue_items", "claims")
        if set(value) != set(keys) or any(type(value[key]) is not dict for key in keys):
            raise ValueError("ORIGINAL_RECORD_INPUTS_INVALID")
        nodes = value["queue_view"].get("items")
        if type(nodes) is not list or any(type(node) is not dict or type(node.get("id")) is not str for node in nodes):
            raise ValueError("ORIGINAL_RECORD_QUEUE_INVALID")
        ids = [node["id"] for node in nodes]
        if (len(set(ids)) != len(ids) or set(ids) != set(self.sources["tasks"])
                or set(ids) != set(value["queue_items"]) or set(ids) != set(value["claims"])):
            raise ValueError("ORIGINAL_RECORD_TASKS_UNBOUND")
        for task in ids:
            original = self.read_original_selection(task)
            if (not self._same(value["queue_items"][task], original["queue_item"])
                    or not self._same(value["claims"][task], original["claim"])):
                raise ValueError("ORIGINAL_RECORD_INPUTS_UNBOUND")
        return tuple(value[key] for key in keys)

    def read_claim(self, task):
        from automation.orchestration.claims.aios_task_claim_control import _read_board, _select_claim, ClaimError
        from automation.orchestration.relay.aios_self_consuming_codex_cycle_v1 import _native_file, _native_json
        try:
            task = self._task_id(task)
            board = Path(self.claim_controller.board_path).absolute()
            path = self._path(board.relative_to(self.root).as_posix())
            before = _native_file(path)
            _native_json(before)  # Reject duplicate keys before the owner's parser.
            selected = _select_claim(_read_board(path), task, self.read_original_selection(task)["claim"])
            if selected is None or before != _native_file(path):
                raise ValueError("missing or changed claim")
            return selected
        except (OSError, ValueError, TypeError, ClaimError) as exc:
            raise ValueError("ORIGINAL_RECORD_CLAIM_UNBOUND") from exc

    def read_executor_inputs(self, task):
        value = self._json(self._task(task).get("executor_inputs"))
        keys = {"selected_queue_item", "apply_approval", "local_apply_executor_bridge", "single_action_executor",
                "one_action_execution_controller", "one_action_apply_runner", "one_action_execute_gate",
                "apply_result_verifier", "execution_request", "local_executor_request", "executor_options"}
        if (set(value) != keys or any(type(value[key]) is not dict for key in keys)
                or not self._same(value["selected_queue_item"], self.read_original_selection(task)["queue_item"])):
            raise ValueError("ORIGINAL_RECORD_EXECUTOR_UNBOUND")
        return value

    def read_verification_inputs(self, task, execution_result):
        refs = self._task(task)
        value = self._json(refs.get("verification_inputs"))
        allowed = {"selected_queue_item", "single_action_executor", "before_git_status", "after_git_status",
                   "validator_results", "allowed_paths", "max_files_changed", "preservation_context"}
        if (not set(value).issubset(allowed)
                or not self._same(value.get("selected_queue_item"), self.read_original_selection(task)["queue_item"])
                or not self._same(value.get("single_action_executor"), execution_result)):
            raise ValueError("ORIGINAL_RECORD_VERIFICATION_UNBOUND")
        value["before_manifest"] = self._raw(refs.get("before_manifest"))
        value["after_manifest"] = self._raw(refs.get("after_manifest"))
        return value

    def _bound_request(self, request):
        from automation.orchestration.aios_abcd_autonomy_runner import RequirementReadRequest, _acceptance_request
        from automation.orchestration.claims.aios_task_claim_control import ClaimError
        if type(request) is not RequirementReadRequest:
            raise ValueError("ORIGINAL_RECORD_REQUEST_INVALID")
        try:
            view, _repo, items, claims = self.read_current_inputs()
            node = next(item for item in view["items"] if item["id"] == request.task_id)
            if request != _acceptance_request(node, items[request.task_id], claims[request.task_id]):
                raise ValueError("request changed")
        except (KeyError, StopIteration, ValueError, TypeError, ClaimError) as exc:
            raise ValueError("ORIGINAL_RECORD_REQUEST_UNBOUND") from exc

    def acceptance_reader(self, request):
        from automation.orchestration.aios_abcd_autonomy_runner import RequirementReadRequest
        from automation.orchestration.relay.aios_self_consuming_codex_cycle_v1 import make_native_acceptance_reader
        self._bound_request(request)
        if type(request) is not RequirementReadRequest or not callable(self.native_admission_reader):
            raise ValueError("ORIGINAL_RECORD_NATIVE_READER_REQUIRED")
        output = self._path(self._task(request.task_id).get("output_dir"))
        return make_native_acceptance_reader(self.root, output_dir=output,
            native_admission_reader=self.native_admission_reader)(request)

    def read_receipt(self, request):
        self._bound_request(request)
        reference = self._task(request.task_id).get("receipt")
        value = self._json(reference)
        if (value.get("task_id") != request.task_id or value.get("packet_id") != request.packet_id
                or value.get("input_sha256") != {"request": request.request_sha256, "claim": request.claim_sha256}
                or type(value.get("acceptance_requirement_id")) is not str or not value["acceptance_requirement_id"].strip()):
            raise ValueError("ORIGINAL_RECORD_RECEIPT_UNBOUND")
        return {"path": str(self._path(reference["path"])), "sha256": reference["sha256"],
                "acceptance_requirement_id": value["acceptance_requirement_id"]}


class DefaultCampaignRecordConnection:
    """Default original-source routing, not Windows qualification or a runner.

    The existing mission contract names data only. It cannot install code,
    create an active board, qualify a native context, or mint permission.
    """

    def __init__(self, repo_root, contract_path):
        import hashlib
        from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import bound_path, source_relative
        from automation.orchestration.relay.aios_self_consuming_codex_cycle_v1 import _native_file, _native_json
        from automation.orchestration.claims.aios_task_claim_control import TaskClaimController
        self.root = bound_path(str(Path(repo_root).absolute()))
        path = Path(contract_path)
        if not path.is_absolute():
            path = self.root / path
        self.path = bound_path(str(path), root=self.root)
        self.relative = source_relative(self.path.relative_to(self.root).as_posix())
        self.original = _native_file(self.path, 2 * 1024 * 1024)
        self.digest = hashlib.sha256(self.original).hexdigest()
        contract = _native_json(self.original)
        if type(contract) is not dict:
            raise ValueError('DEFAULT_CAMPAIGN_CONTRACT_INVALID')
        source = contract.get('worker_connection')
        if (type(source) is not dict or set(source) != {'schema', 'claim_board', 'records'}
                or source['schema'] != 'AIOS_ORIGINAL_CAMPAIGN_RECORD_CONNECTION.v1'):
            raise ValueError('DEFAULT_CAMPAIGN_RECORD_SOURCES_REQUIRED')
        board = self.root / source_relative(source['claim_board'])
        self.board = bound_path(str(board), root=self.root)
        # The existing claim owner treats a missing board as empty. A default
        # connection must not convert a missing original into a replacement.
        try:
            _native_file(self.board, 2 * 1024 * 1024)
        except (OSError, ValueError):
            raise ValueError('DEFAULT_CAMPAIGN_EXISTING_BOARD_UNAVAILABLE') from None
        if self.board == self.path:
            raise ValueError('DEFAULT_CAMPAIGN_BOARD_OVERLAP')
        self.claim_controller = TaskClaimController(self.board)
        self.readers = OriginalCampaignRecordReaders(self.root, source['records'], self.claim_controller,
                                                     native_admission_reader=None)
        self._check_originals(contract)

    def _check_originals(self, contract):
        import re
        from automation.orchestration.claims.aios_task_claim_control import normalize_claim, _claim_contract, _read_board, _select_claim
        from automation.orchestration.relay.aios_self_consuming_codex_cycle_v1 import _native_file, _native_json
        from automation.orchestration.aios_repo_state_evidence import campaign_json
        if campaign_json(self.readers.sources) != campaign_json(contract['worker_connection']['records']):
            raise ValueError('DEFAULT_CAMPAIGN_RECORD_SOURCES_CHANGED')
        identity = contract.get('repository_identity')
        tasks = contract.get('task_ids')
        if (type(identity) is not dict or set(identity) != {'root', 'branch', 'head'}
                or identity['root'] != str(self.root)
                or type(identity['branch']) is not str or not identity['branch']
                or type(identity['head']) is not str or not re.fullmatch(r'[0-9a-f]{40}(?:[0-9a-f]{24})?', identity['head'])
                or type(tasks) is not list or not tasks or any(type(task) is not str or not task for task in tasks)
                or len(tasks) != len(set(tasks)) or set(tasks) != set(self.readers.sources['tasks'])):
            raise ValueError('DEFAULT_CAMPAIGN_ORIGINAL_IDENTITIES_INVALID')
        view, state, queue_items, claims = self.readers.read_current_inputs()
        if (set(queue_items) != set(tasks) or set(claims) != set(tasks)
                or state.get('worktree') != str(self.root)):
            raise ValueError('DEFAULT_CAMPAIGN_CURRENT_INPUTS_UNBOUND')
        board_bytes = _native_file(self.board, 2 * 1024 * 1024)
        _native_json(board_bytes)
        board = _read_board(self.board)
        if _native_file(self.board, 2 * 1024 * 1024) != board_bytes:
            raise ValueError('DEFAULT_CAMPAIGN_EXISTING_BOARD_CHANGED')
        for task in tasks:
            selected = self.readers.read_original_selection(task)
            claim = normalize_claim(selected['claim'])
            actual = _select_claim(board, task, claim)
            if (claim['worktree'] != self.root.as_posix().casefold()
                    or claim['branch'] != identity['branch'] or claim['base_sha'] != identity['head']
                    or actual is not None and _claim_contract(normalize_claim(actual)) != _claim_contract(claim)):
                raise ValueError('DEFAULT_CAMPAIGN_EXISTING_CLAIM_UNBOUND')
            if actual is None:
                terminal = [item for item in board.get('completed_receipts', []) if item['task_id'] == task]
                if terminal:
                    # Validate the explicit nonprivate endpoint before asking
                    # the existing owner to verify its terminal lifecycle proof.
                    if len(terminal) != 1:
                        raise ValueError('DEFAULT_CAMPAIGN_TERMINAL_CLAIM_INVALID')
                    receipt = self.readers._path(Path(terminal[0]['receipt_path']).relative_to(self.root).as_posix())
                    original_receipt = _native_file(receipt)
                    _native_json(original_receipt)
                    if (self.claim_controller._receipt_for_task(task, expected_claim=claim, board=board) is None
                            or _native_file(receipt) != original_receipt):
                        raise ValueError('DEFAULT_CAMPAIGN_TERMINAL_CLAIM_CHANGED')
                elif any(item['claim_sha256'] == _claim_contract(claim) for item in board.get('execution_intents', [])):
                    raise ValueError('DEFAULT_CAMPAIGN_CLAIM_OUTCOME_UNRESOLVED')
                # Otherwise this is an original not-yet-acquired task. Only the
                # existing task owner may acquire it later; nothing is written.
            self.readers.read_executor_inputs(task)
        if _native_file(self.board, 2 * 1024 * 1024) != board_bytes:
            raise ValueError('DEFAULT_CAMPAIGN_EXISTING_BOARD_CHANGED')
        return view, state, queue_items, claims

    def _current(self, contract, digest):
        from automation.orchestration.aios_repo_state_evidence import campaign_json
        from automation.orchestration.relay.aios_self_consuming_codex_cycle_v1 import _native_file, _native_json
        if (digest != self.digest or _native_file(self.path, 2 * 1024 * 1024) != self.original
                or campaign_json(contract) != campaign_json(_native_json(self.original))):
            raise ValueError('DEFAULT_CAMPAIGN_CONTRACT_CHANGED')
        self._check_originals(contract)

    def verify_authority(self, contract, digest):
        """Read canonical permission without consuming it or qualifying Windows."""
        from automation.orchestration.claims.aios_task_claim_control import make_canonical_authority_reader
        from automation.validators.aios_approval_authority_integrity_validator import validate_authority_bundle, V2_PAYLOAD_SCHEMA
        self._current(contract, digest)
        try:
            material = make_canonical_authority_reader()()
            gate = material['gate']
            # data_hashes is already covered by the canonical v2 signature.
            # execution_contract_sha256 keeps its exact per-invocation meaning.
            if (type(gate) is not dict or gate.get('schema') != V2_PAYLOAD_SCHEMA
                    or type(gate.get('data_hashes')) is not dict
                    or gate['data_hashes'].get(self.relative) != digest):
                raise ValueError('unbound campaign')
            result = validate_authority_bundle(gate, material['authority'],
                hmac_key=material.get('hmac_key'), trust_metadata=material.get('trust_metadata'),
                approval_roots=material.get('approval_roots', ()), current_gate_path=material.get('current_gate_path'),
                allow_test_trust=False)
            if result.status != 'PASS' or result.hardened_approval_verified is not True:
                raise ValueError('unverified campaign')
        except Exception:
            # No private permission material, key, or original exception text
            # may escape the canonical boundary.
            raise ValueError('DEFAULT_CAMPAIGN_AUTHORITY_UNBOUND_OR_UNVERIFIED') from None
        self._current(contract, digest)
        return True


class OrchestrationPlatform:
    """Stable, side-effect-free entry point over canonical orchestration components."""

    def __init__(self, repo_root: str | Path = ".", *, campaign_host=None) -> None:
        self.repo_root = Path(repo_root).resolve()
        # Executable, source-qualified host ports only; never loaded from JSON.
        self._campaign_host = campaign_host

    def queue(self, evidence: dict[str, Any]) -> dict[str, Any]:
        return build_packet_queue_planner(evidence)

    def dispatch(self, queue_view: dict[str, Any], *, worker_capacity: int = 1) -> dict[str, Any]:
        return build_dispatch_plan(queue_view, worker_capacity=worker_capacity)

    def build_packet(self, **packet_fields: Any) -> dict[str, Any]:
        return build_repository_aligned_apply_packet(**packet_fields)

    def generate_packet(self, queue_item: dict[str, Any], **options: Any) -> dict[str, Any]:
        return build_codex_packet_from_queue_item(queue_item, **options)

    def resolve_packet(
        self,
        queue_item: dict[str, Any],
        repository_state: dict[str, Any],
        *,
        existing_packets: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return resolve_execution_packet(queue_item, repository_state, existing_packets=existing_packets)

    def spine(self, *, as_of_utc: str | None = None) -> dict[str, Any]:
        return build_orchestration_spine(self.repo_root, as_of_utc=as_of_utc)

    def report(self, state: dict[str, Any]) -> str:
        return render_orchestration_report(state)

    def countdown(self, evidence: Any | None = None, **options: Any) -> dict[str, Any]:
        source = evidence if evidence is not None else load_canonical_work_packet_inventory(self.repo_root)
        return build_work_countdown(source, **options)

    def compound_work_braid(self, **options: Any) -> dict[str, Any]:
        """Build a deterministic, non-executing compound work plan."""
        return CompoundWorkBraidController(self.repo_root).build(**options)

    def govern_autonomy(
        self, evidence: dict[str, Any], *, generated_at_utc: str | None = None
    ) -> dict[str, Any]:
        """Return a non-mutating decision from the canonical autonomy governor."""
        from automation.orchestration.aios_autonomy_decision_governor import choose_next_decision

        return choose_next_decision(evidence, generated_at_utc=generated_at_utc)

    def campaign_bindings(self, contract_path: str | Path):
        """Bind existing owners without inventing a Windows qualification reader.

        Construction is inert. A production host must provide qualified original
        input/publication readers and its fixed bounded Python runner. A report
        saying approved/qualified is not such a host and cannot become one.
        """
        from types import SimpleNamespace
        from automation.orchestration.aios_master_runtime_v1 import RuntimeBlocked
        from automation.orchestration.claims.aios_task_claim_control import TaskClaimController
        from automation.orchestration.aios_self_build_one_action_local_apply_executor import make_campaign_execution_connection
        host = self._campaign_host
        if host is None:
            try:
                connection = DefaultCampaignRecordConnection(self.repo_root, contract_path)
                from automation.orchestration.relay.aios_self_consuming_codex_cycle_v1 import _native_json
                connection.verify_authority(_native_json(connection.original), connection.digest)
            except Exception:
                raise RuntimeBlocked("QUALIFIED_WINDOWS_WORKER_CONNECTION_REQUIRED:DEFAULT_ORIGINAL_SOURCES_UNVERIFIED") from None
            # Original sources and a valid signature still do not supply the
            # independent Windows admission producer required by the native
            # acceptance owner. Never install JSON or a success stub in its place.
            raise RuntimeBlocked("QUALIFIED_WINDOWS_WORKER_CONNECTION_REQUIRED:NATIVE_ADMISSION_PRODUCER_REQUIRED")
        if (host is not None and not isinstance(host, dict)
                and getattr(host, "original_record_sources", None) is not None):
            readers = OriginalCampaignRecordReaders(self.repo_root, host.original_record_sources,
                getattr(host, "claim_controller", None),
                native_admission_reader=getattr(host, "native_admission_reader", None))
            ports = {key: getattr(readers, key) for key in (
                "read_current_inputs", "read_claim", "read_executor_inputs", "read_verification_inputs",
                "read_original_selection", "acceptance_reader", "read_receipt")}
            # Results and their hashes can first exist after execution. Keep
            # the host's executable owner readers; pinned originals are the
            # fallback, never a replacement for fresh output or verified absence.
            for key in ("read_current_inputs", "read_verification_inputs", "acceptance_reader", "read_receipt"):
                supplied = getattr(host, key, None)
                if supplied is not None:
                    ports[key] = supplied
            host = SimpleNamespace(claim_controller=readers.claim_controller,
                verify_campaign=getattr(host, "verify_campaign", None),
                command_runner=getattr(host, "command_runner", None),
                single_task_options=getattr(host, "single_task_options", {}), **ports)
        required = ("verify_campaign", "read_current_inputs", "read_claim", "read_executor_inputs",
                    "read_verification_inputs", "command_runner", "read_original_selection", "acceptance_reader", "read_receipt")
        if (host is None or isinstance(host, dict) or any(not callable(getattr(host, key, None)) for key in required)
                or type(getattr(host, "claim_controller", None)) is not TaskClaimController):
            raise RuntimeBlocked("QUALIFIED_WINDOWS_WORKER_CONNECTION_REQUIRED")
        # The exact board belongs to the existing host; never repurpose the
        # differently shaped WORKER_CLAIM_REGISTRY as an active-task board.
        execute = make_campaign_execution_connection(host.claim_controller, read_claim=host.read_claim,
            read_executor_inputs=host.read_executor_inputs, read_verification_inputs=host.read_verification_inputs,
            command_runner=host.command_runner, read_original_selection=host.read_original_selection)
        return SimpleNamespace(verify_campaign=host.verify_campaign, read_current_inputs=host.read_current_inputs,
            claim_controller=host.claim_controller, execute=execute, acceptance_reader=host.acceptance_reader,
            read_receipt=host.read_receipt, single_task_options=getattr(host, "single_task_options", {}))

    def master_runtime(self, **options: Any) -> dict[str, Any]:
        """Run the registered master-runtime coordinator through this facade."""
        from automation.orchestration.aios_master_runtime_v1 import AIOSMasterRuntime

        if "mode" in options:
            from automation.orchestration.aios_master_runtime_v1 import run
            return run(self.repo_root, platform=self, **options)
        return AIOSMasterRuntime(self.repo_root, platform=self).execute(**options)

    def validate(self, state: dict[str, Any]) -> dict[str, Any]:
        """Validate the shared platform contract without granting execution authority."""
        defects: list[str] = []
        if not isinstance(state, dict):
            defects.append("state_not_object")
        else:
            for field in ("schema", "status", "permissions", "protected_actions"):
                if field not in state:
                    defects.append(f"missing_{field}")
            for gate in ("permissions", "protected_actions"):
                values = state.get(gate, {})
                if not isinstance(values, dict) or any(value is not False for value in values.values()):
                    defects.append(f"unsafe_{gate}")
        return {
            "schema": "AIOS_ORCHESTRATION_PLATFORM_VALIDATION.v1",
            "status": "PASS" if not defects else "BLOCKED",
            "defects": defects,
            "grants_approval": False,
            "performs_mutation": False,
        }


def create_platform(repo_root: str | Path = ".") -> OrchestrationPlatform:
    """Create the canonical orchestration facade."""
    return OrchestrationPlatform(repo_root)
