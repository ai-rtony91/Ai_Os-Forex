"""Bounded bridge from the campaign prompt generator to the existing relay."""

from __future__ import annotations

import argparse
import json
import hashlib
import base64
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import (
    PROTECTED_FLAGS,
    enqueue_prompt,
    bound_path,
    canonical_json,
    validate_bound_request,
    request_binding,
)


DEFAULT_FLAGS = {name: False for name in PROTECTED_FLAGS}


def build_next_pr_lifecycle_packet() -> str:
    """Return the unexecuted, approval-gated next handoff packet."""
    return """CODEX-ONLY PROMPT

AI_OS EXECUTION TOKEN
TOKEN ID: AIOS-GITHUB-PR-LIFECYCLE-CONTROLLER-V1
AI_OS BOOTSTRAP REQUIRED
VALUE: YES
IDENTITY MARKER: AI_OS OWNER-SUPERVISED PR AUTOMATION
SUPERVISOR IDENTITY: HUMAN OWNER ANTHONY
WORKER IDENTITY: CODEX
PACKET ID: AIOS-GITHUB-PR-LIFECYCLE-CONTROLLER-V1
MODE: DRY_RUN
ZONE: LOCAL_REPOSITORY
LANE: PR_LIFECYCLE
WORKTREE: /workspace/Ai_Os
BRANCH: resolve after preflight

ALLOWED PATHS
- automation/orchestration/pr_lifecycle/
- tests/orchestration/
- relay/README.md

FORBIDDEN PATHS
- AGENTS.md
- RISK_POLICY.md
- .git/
- .github/
- credentials/
- secrets/
- broker/

APPROVAL AUTHORITY
Human Owner authorizes read-only design and validation only. Commit, push, PR mutation, merge, and branch deletion require separate approval.

VALIDATOR CHAIN
python -m pytest tests/orchestration -q -p no:cacheprovider
git diff --check
git status --short --branch

STOP POINT
Stop after a read-only design for validated commit creation, PR creation, review, conflict and supersession classification, obsolete PR closure, merge approval, post-merge branch cleanup, refreshed-main continuation, and owner SOS escalation.

MISSION
Design AI_OS GitHub PR Lifecycle Controller V1 without performing protected Git or GitHub actions.

PREFLIGHT
pwd
git status --short --branch
git branch --show-current
git remote -v

FINAL REPORT FORMAT
STATUS:
DESIGN:
PROTECTED ACTIONS NOT PERFORMED:
VALIDATION:
NEXT SAFE ACTION:

END OF PACKET
"""


@dataclass(frozen=True)
class CycleResult:
    status: str
    cycles: int
    prompt_sha256: str = ""
    detail: str = ""
    task_id: str = ""
    attempt_id: str = ""
    request_sha256: str = ""
    retry_allowed: bool = False


def strict_json_equal(left: object, right: object) -> bool:
    """Compare JSON without Python's bool/int/float equality aliases."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return (all(type(key) is str for key in left) and all(type(key) is str for key in right)
                and left.keys() == right.keys() and all(strict_json_equal(left[key], right[key]) for key in left))
    if isinstance(left, list):
        return len(left) == len(right) and all(strict_json_equal(a, b) for a, b in zip(left, right, strict=True))
    if left is None or type(left) in (str, bool, int):
        return left == right
    if type(left) is float:
        import math
        return math.isfinite(left) and math.isfinite(right) and left == right
    return False


def verify_process_success(process: object, *, cwd: str, input_bytes: int) -> None:
    if not isinstance(process,dict):raise ValueError("process_evidence_missing")
    for field in ("shape_valid","root_exit_confirmed","tree_exit_confirmed","drains_completed","stdin_completed","stdin_writer_joined"):
        if process.get(field) is not True:raise ValueError("process_confirmation_missing:"+field)
    for field in ("timed_out","startup_failed","process_error_present"):
        if process.get(field) is not False:raise ValueError("process_failure_or_unknown:"+field)
    for field in ("exit_code","child_exit_code","stdin_error_code","stdin_close_error_code","cleanup_error_code","cancellation_error_code"):
        if type(process.get(field)) is not int or process[field]!=0:raise ValueError("process_code_invalid:"+field)
    if (process.get("cleanup_state")!="CONFIRMED" or process.get("working_directory")!=cwd
            or type(process.get("stdin_bytes_written")) is not int or process["stdin_bytes_written"]!=input_bytes):
        raise ValueError("process_input_cwd_or_cleanup_mismatch")


def read_capture_status(capture):
    """Read original v2 before/after observations; never reconstruct old status."""
    from automation.orchestration.aios_repo_state_evidence import validate_status_evidence
    from automation.orchestration.aios_resume_state import require_hash
    if type(capture) is not dict or capture.get("schema") != "AIOS_RELAY_EXECUTION.v2":
        raise ValueError("native_original_status_capture_unavailable")
    value = capture.get("status")
    if type(value) is not dict or set(value) != {"before", "after", "parser_sha256"}:
        raise ValueError("native_original_status_capture_invalid")
    require_hash(value["parser_sha256"], "native_original_status_parser_invalid")
    return {"before": validate_status_evidence(value["before"]),
            "after": validate_status_evidence(value["after"]), "parser_sha256": value["parser_sha256"]}


def verify_observation(enqueued: dict, response: object) -> dict:
    if not isinstance(response,dict):raise ValueError("observation_not_object")
    task=enqueued["task"];request=json.loads(task["request_json"])
    expected={**request_binding(request,task["request_sha256"]),"repo_root":request["repo_root"],"relay_root":request["relay_root"]}
    if any(not strict_json_equal(response.get(k),v) for k,v in expected.items()) or response.get("authority_granted") is not False or response.get("retry_allowed") is not False:
        raise ValueError("observation_binding_mismatch")
    statuses={"EXECUTED_AWAITING_VALIDATION","DEFERRED","REQUEST_REJECTED","EXECUTION_FAILED","SAFETY_INTEGRITY_BLOCK","FINALIZATION_RECONCILIATION_REQUIRED","STOP_FLAG"}
    if response.get("status") not in statuses:raise ValueError("observation_status_not_authority")
    path=bound_path(response.get("observation_path"),root=Path(request["relay_root"])/"outbox")
    if not path.name.startswith(task["id"]+"."):raise ValueError("observation_filename_mismatch")
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=response.get("observation_sha256"):raise ValueError("observation_readback_mismatch")
    saved=json.loads(data)
    if not strict_json_equal(saved,{k:v for k,v in response.items() if k not in {"observation_path","observation_sha256"}}):
        raise ValueError("observation_payload_mismatch")
    if saved.get("schema")!="AIOS_RELAY_OBSERVATION.v1" or saved.get("retry_allowed") is not False:raise ValueError("observation_shape_invalid")
    if saved["status"]=="EXECUTED_AWAITING_VALIDATION":
        execution=bound_path(saved.get("execution_path"),root=Path(request["relay_root"])/"outbox")
        if execution.name!=task["id"]+".execution.json":raise ValueError("execution_path_mismatch")
        raw=execution.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=saved.get("execution_sha256"):raise ValueError("execution_readback_mismatch")
        capture=json.loads(raw)
        if type(capture) is not dict:raise ValueError("execution_envelope_not_object")
        if (capture.get("schema") not in {"AIOS_RELAY_EXECUTION.v1", "AIOS_RELAY_EXECUTION.v2"} or not strict_json_equal(capture.get("binding"),request_binding(request,task["request_sha256"]))
                or capture.get("request_json")!=task["request_json"] or capture.get("packet_sha256")!=enqueued["packet_sha256"]
                or capture.get("authority_granted") is not False or capture.get("retry_allowed") is not False):raise ValueError("execution_binding_mismatch")
        if capture.get("schema") == "AIOS_RELAY_EXECUTION.v2":
            read_capture_status(capture)
        verify_process_success(capture.get("process"),cwd=request["repo_root"],input_bytes=len(task["prompt_text"].encode("utf-8")))
        verify_worker_observation(request,capture,prompt_utf8=task['prompt_text'])
    return saved


def run_self_consuming_cycle(*,generate:Callable[[],Mapping|None],relay_root:Path,
        flags:Mapping[str,object]=DEFAULT_FLAGS,invoke_worker:Callable[[dict],dict]|None=None,
        dry_run:bool=False,max_cycles:int=12,max_elapsed_minutes:float=480,
        worker_observation_host=None,
        monotonic:Callable[[],float]=time.monotonic)->CycleResult:
    if type(max_cycles) is not int or max_cycles<1 or max_elapsed_minutes<=0:raise ValueError("invalid_cycle_limits")
    start=monotonic()
    for cycle in range(1,max_cycles+1):
        if (relay_root/"STOP.flag").exists():return CycleResult("STOP_FLAG",cycle-1)
        if (monotonic()-start)/60>=max_elapsed_minutes:return CycleResult("MAX_ELAPSED",cycle-1)
        generated=generate()
        if generated is None:return CycleResult("NO_ADMITTED_WORK",cycle-1)
        if not isinstance(generated,Mapping):return CycleResult("BOUND_REQUEST_REQUIRED",cycle)
        try:
            request=validate_bound_request(generated)
            if 'worker_observation_contract' in request and not dry_run:
                from automation.orchestration.aios_self_build_apply_result_verifier import WindowsWorkerObservationHost
                if type(worker_observation_host) is not WindowsWorkerObservationHost:
                    return CycleResult('WINDOWS_OBSERVATION_HOST_REQUIRED',cycle,
                        task_id=request['task_id'],attempt_id=request['attempt_id'])
            result=enqueue_prompt(Path(request["prompt_path"]),relay_root,flags,dry_run=dry_run,bound_request=request)
        except (OSError,ValueError,TypeError,KeyError) as exc:return CycleResult("REQUEST_REJECTED",cycle,detail=str(exc))
        task=result["task"];fields=dict(prompt_sha256=task["prompt_sha256"],task_id=request["task_id"],attempt_id=request["attempt_id"],request_sha256=task["request_sha256"])
        if result["status"]=="APPROVAL_REQUIRED":return CycleResult("APPROVAL_REQUIRED",cycle,**fields)
        if dry_run:return CycleResult("DRY_RUN",cycle,detail=result["target"],**fields)
        if invoke_worker is None:return CycleResult("CODEX_RUNTIME_UNAVAILABLE",cycle,**fields)
        try:
            observed = (worker_observation_host.invoke(result, invoke_worker)
                        if 'worker_observation_contract' in request else invoke_worker(result))
            response=verify_observation(result,observed)
        except Exception as exc:return CycleResult("INTEGRITY_BLOCKED",cycle,detail=type(exc).__name__+":"+str(exc),**fields)
        # Transport cannot grant requirement acceptance or advance the frontier.
        # The existing dispatcher/claim/publication adapter must consume this
        # observation before another native obligation is admitted.
        return CycleResult(response["status"],cycle,detail=str(response.get("reason","")),**fields)
    return CycleResult("MAX_CYCLES",max_cycles)


def _worker(repo_root:Path)->Callable[[dict],dict]|None:
    shell=shutil.which("powershell.exe") or shutil.which("powershell")
    if not shell:return None
    def invoke(enqueued:dict, *, before_resume=None, collect_protected_child=None)->dict:
        task=enqueued["task"];request=validate_bound_request(json.loads(task["request_json"]))
        if ('worker_observation_contract' in request or before_resume is not None
                or collect_protected_child is not None):
            raise ValueError('worker_observation_transport_unconnected')
        selected=bound_path(request["repo_root"])
        if selected!=repo_root.resolve() or selected!=Path(__file__).resolve().parents[3]:raise ValueError("worker_source_repository_mismatch")
        script=selected/"automation/orchestration/relay/Invoke-AiOsRelayWorker.ps1"
        worker_args=["-NoProfile","-File",str(script),"-Apply","-RepoRoot",str(selected),"-RelayRoot",request["relay_root"],
            "-RequestPath",enqueued["target"],"-ExpectedPacketSha256",enqueued["packet_sha256"],"-PythonExecutable",request["python_executable"]]
        parameters={"FilePath":shell,"ArgumentList":worker_args,"TimeoutSec":request["timeout_sec"]+60,"WorkingDirectory":str(selected)}
        encoded=base64.b64encode(canonical_json(parameters)).decode("ascii")
        adapter=str(selected/"automation/orchestration/timeout/Invoke-AiOsCliWithTimeout.ps1").replace("'","''")
        worker_source=str(script).replace("'","''")
        bootstrap="""$ErrorActionPreference='Stop';[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
foreach($path in @('ADAPTER','WORKER')) {
 $t=$null;$e=$null;$a=[Management.Automation.Language.Parser]::ParseFile($path,[ref]$t,[ref]$e);if($e.Count){throw 'HOST_SOURCE_PARSE_FAILED'}
 foreach($d in $a.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst]},$false)){Set-Item -Path ('Function:'+$d.Name) -Value $d.Body.GetScriptBlock()}
}
$p=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('PARAMS'))|ConvertFrom-Json;$argsHost=@{};foreach($v in $p.PSObject.Properties){$argsHost[$v.Name]=$v.Value}
$run=Invoke-AiOsCliProcess @argsHost
$answer=@{host_process=(Get-AiOsBoundProcessProjection $run);observation_json=[string]::new(([string]$run.stdout).ToCharArray())}
[Console]::WriteLine(($answer|ConvertTo-Json -Depth 15 -Compress))
""".replace("ADAPTER",adapter).replace("WORKER",worker_source).replace("PARAMS",encoded)
        command=[shell,"-NoProfile","-EncodedCommand",base64.b64encode(bootstrap.encode("utf-16-le")).decode("ascii")]
        # The bootstrap creates no task child except through N03's gated Job.
        # Killing/timing out the bootstrap loses confirmed cleanup evidence and
        # is a hard integrity outcome; no retry or successful status is inferred.
        try:
            run=subprocess.run(command,cwd=selected,check=False,capture_output=True,text=True,encoding="utf-8",timeout=request["timeout_sec"]+120)
        except subprocess.TimeoutExpired as exc:
            raise ValueError("worker_host_timeout_cleanup_unknown_no_retry") from exc
        if run.returncode!=0:raise ValueError("worker_host_failed_cleanup_unknown_no_retry")
        envelope=json.loads(run.stdout)
        verify_process_success(envelope.get("host_process"),cwd=str(selected),input_bytes=0)
        if not isinstance(envelope.get("observation_json"),str):raise ValueError("worker_host_observation_missing")
        return json.loads(envelope["observation_json"])

    return invoke


def main()->int:
    parser=argparse.ArgumentParser(description="Observe one explicitly admitted relay request; no completion authority.")
    parser.add_argument("--request-json",type=Path)
    parser.add_argument("--dry-run",action="store_true")
    parser.add_argument("--print-next-packet",action="store_true")
    args=parser.parse_args()
    if args.print_next_packet:
        if args.request_json is not None or args.dry_run:
            parser.error("--print-next-packet cannot be combined with --request-json or --dry-run")
        print(build_next_pr_lifecycle_packet())
        return 0
    if args.request_json is None:
        parser.error("one of --request-json or --print-next-packet is required")
    request=validate_bound_request(json.loads(args.request_json.read_bytes()))
    result=run_self_consuming_cycle(generate=lambda:request,relay_root=Path(request["relay_root"]),dry_run=args.dry_run,
        invoke_worker=None if args.dry_run else _worker(Path(request["repo_root"])))
    notification = _preview_selected_event(Path(request["repo_root"]), request, result.__dict__)
    print(json.dumps({**result.__dict__, "notification": notification},indent=2))
    return 0 if result.status in {"DRY_RUN","EXECUTED_AWAITING_VALIDATION","DEFERRED"} else 2


def _preview_selected_event(repo_root, request, result, *, expected_request=None,
                            admitted_context=None, native_admission_reader=None):
    """Observe through the existing notifier; no selected output/effect grant exists."""
    unavailable = {"status": "UNKNOWN", "effect_scope": "PREVIEW_ONLY", "delivery_accepted": False,
                   "canonical_integrity": "UNKNOWN", "canonical_current": False}
    try:
        native = any(value is not None for value in (expected_request, admitted_context, native_admission_reader))
        if native:
            data = _verify_native_context(repo_root, admitted_context, native_admission_reader, live=False)
            if (not strict_json_equal(_native_request_dict(expected_request), _native_request_dict(admitted_context.request))
                    or not strict_json_equal(request, _native_json(data["request_json"]))):
                raise ValueError("selected_event_native_request_mismatch")
        selected = validate_bound_request(request)
        if bound_path(selected["repo_root"]) != bound_path(str(repo_root)):
            raise ValueError("selected_event_root_mismatch")
        digest = hashlib.sha256(canonical_json(selected)).hexdigest()
        if any(result.get(field) not in (None, "", expected) for field, expected in (
                ("task_id", selected["task_id"]), ("attempt_id", selected["attempt_id"]),
                ("request_sha256", digest), ("prompt_sha256", selected["prompt_sha256"]))):
            raise ValueError("selected_event_transport_mismatch")
        from services.python_supervisor import notifier
        # New material diagnostics contain only existing public result codes or
        # an exception class, never arbitrary provider/exception payload text.
        cause = str(result.get("detail", "")).partition(":")[0]
        if cause not in {"ValueError", "OSError", "RuntimeError", "PromptValidationError", "KeyError", "TypeError"}:
            cause = result["status"]
        event = {"schema": "AIOS_SELECTED_CYCLE_EVENT.v1", "phase": "POST_PUBLICATION" if native else "TRANSPORT",
                 "status": result["status"], "task_id": selected["task_id"], "attempt_id": selected["attempt_id"],
                 "attempt_number": selected["attempt_number"], "transport_request_sha256": digest,
                 "prompt_sha256": selected["prompt_sha256"], "cause_code": cause,
                 "requirement_request_sha256": expected_request.request_sha256 if native else "",
                 "claim_sha256": expected_request.claim_sha256 if native else ""}
        return notifier.preview_selected_event(repo_root, event, expected_request=expected_request,
            admitted_context=admitted_context, native_admission_reader=native_admission_reader)
    except Exception as error:
        # Diagnostics cannot change the original transport/acceptance outcome,
        # its error cause, provider count, claim or no-replay state.
        name = type(error).__name__
        public_name = name if name in {"ValueError", "OSError", "RuntimeError", "PromptValidationError", "KeyError", "TypeError"} else "Exception"
        return {**unavailable, "reason": "selected_event_preview_unavailable:" + public_name}


# Native publication is an explicit component API, never a command-line mode.
@dataclass(frozen=True)
class NativeRequirementContext:
    request: object
    context_json: str


NativeAdmissionReader = Callable[[object], NativeRequirementContext]
NATIVE_IDENTITY = "AIOS_NATIVE_EXECUTION_IDENTITY.v1"
NATIVE_RESULT = "AIOS_NATIVE_REQUIREMENT_RESULT.v1"
VALIDATOR_MARKER = b"AIOS aggregate validator reserved; result unavailable\n"


def _native_json(raw):
    def pairs(items):
        answer = {}
        for key, value in items:
            if key in answer:
                raise ValueError("native_duplicate_json_key")
            answer[key] = value
        return answer
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("native_nonfinite_json")))


def _native_hash(value):
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _native_file(path, limit=16777216):
    import os
    import stat
    path = bound_path(str(path))
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
        raise ValueError("native_evidence_file_invalid")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    if (len(data) > limit or before.st_size != len(data)
            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            or (path.stat().st_dev, path.stat().st_ino, path.stat().st_size, path.stat().st_mtime_ns)
            != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)):
        raise ValueError("native_evidence_changed_during_read")
    return data


def _native_pin(path, digest):
    from automation.orchestration.aios_resume_state import require_hash
    require_hash(digest, "native_hash_invalid")
    if hashlib.sha256(_native_file(path)).hexdigest() != digest:
        raise ValueError("native_input_changed")


def _native_nonprivate_path(value, *, anchor=None):
    from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import source_relative
    path = bound_path(value)
    if anchor is not None and path.is_relative_to(anchor):
        relative = path.relative_to(anchor).as_posix()
    else:
        relative = Path(*path.parts[1:]).as_posix()
    source_relative(relative)
    return path


def _native_request_dict(request):
    from automation.orchestration.aios_abcd_autonomy_runner import RequirementReadRequest
    if type(request) is not RequirementReadRequest:
        raise ValueError("native_admission_request_invalid")
    values = vars(request)
    if any(type(value) is not str or not value for value in values.values()):
        raise ValueError("native_admission_request_invalid")
    from automation.orchestration.aios_resume_state import require_hash
    for key in ("request_sha256", "claim_sha256"):
        require_hash(values[key], "native_admission_request_hash_invalid")
    return dict(values)


def _native_admitted(context, reader):
    if type(context) is not NativeRequirementContext or not callable(reader):
        raise ValueError("native_admission_reader_required")
    _native_request_dict(context.request)
    if type(context.context_json) is not str:
        raise ValueError("native_context_json_invalid")
    data = _native_json(context.context_json)
    if type(data) is not dict or canonical_json(data).decode("ascii") != context.context_json:
        raise ValueError("native_context_not_canonical")
    resolved = reader(context.request)
    if (type(resolved) is not NativeRequirementContext
            or not strict_json_equal(_native_request_dict(resolved.request), _native_request_dict(context.request))
            or resolved.context_json != context.context_json):
        raise ValueError("native_admission_context_mismatch")
    # All existing publication owners enter this shared read boundary before
    # their own error-recording regions. Reject unproven intervals here as well
    # as at full verification, before even failure-diagnostic publication.
    try:
        request = _native_json(data["request_json"])
        from automation.orchestration.aios_abcd_autonomy_runner import (
            _acceptance_request,
        )
        from automation.orchestration.claims.aios_task_claim_control import (
            normalize_claim,
        )
        calculated = _acceptance_request(data["dispatch_item"], data["queue_item"], data["claim"])
        if not strict_json_equal(_native_request_dict(calculated), _native_request_dict(context.request)):
            raise ValueError("preservation_selection_claim_mismatch")
        claim = normalize_claim(data["claim"])
        if bound_path(request["repo_root"]) != bound_path(str(Path(claim["worktree"]).resolve())):
            raise ValueError("preservation_selected_root_mismatch")
        evidence = data["evidence"]
        capture = _native_json(evidence["capture"]["utf8"])
        verify_provider_preservation(request, evidence["packet"]["sha256"], evidence["launch"]["sha256"], capture)
        if "worker_launch_contract" in request or "launch_witness" in capture.get("process", {}):
            from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import validate_prompt
            launch_prompt = validate_prompt(_NativePromptBytes(evidence["prompt"]["utf8"].encode("utf-8")))
            if launch_prompt.sha256 != request["prompt_sha256"]:
                raise ValueError("provider_launch_prompt_binding_mismatch")
            verify_provider_launch_witness(request, capture["process"], prompt_utf8=launch_prompt.text)
            verify_worker_observation(request,capture,prompt_utf8=launch_prompt.text)
        original = data["original_resolver_packet"]
        if type(original) is not dict:
            raise ValueError("preservation_selected_packet_invalid")
        if ("action_id" in original and "selected_action" in original
                and not strict_json_equal(original["action_id"], original["selected_action"])):
            raise ValueError("preservation_selected_action_conflict")
        action = original.get("action_id", original.get("selected_action", context.request.task_id))
        if request["preservation_contract"]["action_id"] != action:
            raise ValueError("preservation_selected_action_mismatch")
    except (KeyError, TypeError, UnicodeError) as exc:
        raise ValueError("preservation_admission_incomplete") from exc
    return data


def _native_manifest(root, manifest, *, live):
    from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import source_relative
    from automation.orchestration.aios_resume_state import require_hash
    if type(manifest) is not dict or not manifest:
        raise ValueError("native_manifest_missing")
    for relative, expected in manifest.items():
        path = bound_path(str(root / source_relative(relative)), root=root)
        if path.exists() and not path.is_file():
            raise ValueError("native_manifest_path_not_file")
        if expected is not None:
            require_hash(expected, "native_manifest_hash_invalid")
        if live:
            actual = hashlib.sha256(_native_file(path)).hexdigest() if path.is_file() else None
            if actual != expected:
                raise ValueError("native_manifest_changed")


class _NativePromptBytes:
    """Read-only bytes adapter to the unchanged N04 grammar; no path I/O."""
    def __init__(self, raw):
        self.raw = raw

    def resolve(self, *, strict):
        return self

    def read_bytes(self):
        return self.raw


def _native_repository_identity(root, data):
    from automation.orchestration.aios_repo_state_evidence import collect_repo_identity
    actual = collect_repo_identity(root)
    expected = _native_json(data["request_json"])["repository_identity"]
    if (type(actual) is not dict or actual.get("resolved") is not True or actual.get("detached") is not False
            or any(not strict_json_equal(actual.get(key), expected[key]) for key in ("repo_root", "git_dir", "branch", "commit"))):
        raise ValueError("native_current_repository_identity_changed")
    return actual


def _native_controller_slots(root, request):
    relay = bound_path(request["relay_root"], root=root)
    selected = "bound-" + _native_hash(request)
    paths = [relay / folder / (selected + suffix) for folder, suffix in
             (("inbox", ".task.json"), ("running", ".task.json"), ("outbox", ".launch.json"), ("outbox", ".execution.json"))]
    paths += [relay / "logs" / filename for filename in ("cost_ledger.jsonl", "preflight.log", "output_validator.log")]
    return {path.relative_to(root).as_posix() for path in paths}


def _native_descriptor(descriptor, *, live=False, allowed=(), source_root=None):
    from automation.orchestration.aios_resume_state import require_hash
    required = {"schema", "validator_id", "executable", "executable_sha256", "argv", "cwd", "environment",
                "stdin_utf8", "stdin_byte_count", "receipt_path", "receipt_max_bytes", "required_cases",
                "required_counts", "result_contract", "input_manifest", "observed_producer_sources"}
    if type(descriptor) is not dict or set(descriptor) != required:
        raise ValueError("native_descriptor_shape_invalid")
    if descriptor["schema"] != "AIOS_PYTEST_JUNIT_REQUIREMENT.v1" or descriptor["result_contract"] != "exact-case-set-and-all-pass":
        raise ValueError("native_descriptor_contract_invalid")
    if type(descriptor["validator_id"]) is not str or not descriptor["validator_id"]:
        raise ValueError("native_validator_id_invalid")
    cwd = bound_path(descriptor["cwd"])
    exe = bound_path(descriptor["executable"])
    if live:
        _native_nonprivate_path(str(exe), anchor=cwd if exe.is_relative_to(cwd) else source_root)
    receipt = bound_path(descriptor["receipt_path"], root=cwd)
    require_hash(descriptor["executable_sha256"], "native_validator_executable_hash_invalid")
    args = descriptor["argv"]
    if type(args) is not list or not args or any(type(value) is not str or not value or "\0" in value for value in args):
        raise ValueError("native_validator_argv_invalid")
    if (type(descriptor["stdin_utf8"]) is not str or type(descriptor["stdin_byte_count"]) is not int
            or descriptor["stdin_byte_count"] != len(descriptor["stdin_utf8"].encode("utf-8"))):
        raise ValueError("native_validator_stdin_invalid")
    if type(descriptor["receipt_max_bytes"]) is not int or not 1 <= descriptor["receipt_max_bytes"] <= 16777216:
        raise ValueError("native_validator_bound_invalid")
    env = descriptor["environment"]
    if type(env) is not dict or not env or len({key.casefold() for key in env if type(key) is str}) != len(env):
        raise ValueError("native_validator_environment_invalid")
    if any(type(key) is not str or not key or "=" in key or "\0" in key or type(value) is not str or "\0" in value for key, value in env.items()):
        raise ValueError("native_validator_environment_invalid")
    cases = descriptor["required_cases"]
    if type(cases) is not list or not cases:
        raise ValueError("native_required_cases_missing")
    for case in cases:
        if (type(case) is not dict or set(case) != {"node_id", "classname", "name"}
                or any(type(value) is not str or not value for value in case.values())):
            raise ValueError("native_case_identity_invalid")
    if len({case["node_id"] for case in cases}) != len(cases) or len({(case["classname"], case["name"]) for case in cases}) != len(cases):
        raise ValueError("native_case_identity_duplicate")
    counts = descriptor["required_counts"]
    expected = {"tests": len(cases), "failures": 0, "errors": 0, "skipped": 0}
    if not strict_json_equal(counts, expected):
        raise ValueError("native_required_counts_invalid")
    if args.count("--junitxml=" + str(receipt)) != 1 or args[-len(cases):] != [case["node_id"] for case in cases]:
        raise ValueError("native_validator_selection_mismatch")
    if any(value == "-k" or value.startswith("--junitxml") and value != "--junitxml=" + str(receipt) for value in args):
        raise ValueError("native_validator_selection_mismatch")
    if type(descriptor["input_manifest"]) is not dict or type(descriptor["observed_producer_sources"]) is not dict:
        raise ValueError("native_validator_sources_invalid")
    immutable = {str(exe), *descriptor["input_manifest"], *descriptor["observed_producer_sources"]}
    if not descriptor["input_manifest"] or live and not descriptor["observed_producer_sources"]:
        raise ValueError("native_validator_sources_missing")
    for manifest in (descriptor["input_manifest"], descriptor["observed_producer_sources"]):
        if type(manifest) is not dict:
            raise ValueError("native_validator_sources_invalid")
        for path, digest in manifest.items():
            selected = bound_path(path)
            if live:
                _native_nonprivate_path(path, anchor=cwd if selected.is_relative_to(cwd) else source_root)
            if manifest is descriptor["input_manifest"] and not selected.is_relative_to(cwd):
                raise ValueError("native_validator_input_outside_cwd")
            require_hash(digest, "native_validator_source_hash_invalid")
            if selected == receipt:
                raise ValueError("native_validator_receipt_overlaps_input")
            if live:
                _native_pin(selected, digest)
    for target in allowed:
        path = bound_path(str(target))
        if any(path == bound_path(item) or path in bound_path(item).parents or bound_path(item) in path.parents for item in (*immutable, str(receipt))):
            raise ValueError("native_validator_overlaps_provider_scope")
    if live:
        _native_pin(exe, descriptor["executable_sha256"])
    return descriptor


def _parse_native_junit(descriptor: dict, raw_xml: bytes) -> dict:
    import re
    import xml.etree.ElementTree as ET
    _native_descriptor(descriptor)
    if type(raw_xml) is not bytes or not raw_xml or len(raw_xml) > descriptor["receipt_max_bytes"]:
        raise ValueError("native_junit_size_invalid")
    try:
        text = raw_xml.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError("native_junit_encoding_invalid") from exc
    if "\0" in text or text.startswith("\ufeff") or "<!" in text.upper():
        raise ValueError("native_junit_declaration_forbidden")
    body = text
    if body.startswith("<?xml"):
        match = re.match(r'''<\?xml version=(?:"1\.0"|'1\.0') encoding=(?:"utf-8"|'utf-8')\?>''', body)
        if not match:
            raise ValueError("native_junit_encoding_declaration_invalid")
        body = body[match.end():]
    if "<?" in body:
        raise ValueError("native_junit_processing_instruction_forbidden")
    try:
        root = ET.fromstring(text)
    except (ET.ParseError, ValueError) as exc:
        raise ValueError("native_junit_malformed") from exc
    if (root.tag != "testsuites" or root.attrib not in ({}, {"name": "pytest tests"})
            or len(root) != 1 or root[0].tag != "testsuite"):
        raise ValueError("native_junit_root_invalid")
    suite = root[0]
    if any(element.text and element.text.strip() or element.tail and element.tail.strip() for element in root.iter()):
        raise ValueError("native_junit_unexpected_text")
    counters = ("tests", "failures", "errors", "skipped")
    permitted = {*counters, "name", "time", "timestamp", "hostname"}
    if not set(suite.attrib) <= permitted:
        raise ValueError("native_junit_suite_attributes_invalid")
    totals = {}
    for key in counters:
        value = suite.get(key)
        if type(value) is not str or not re.fullmatch(r"0|[1-9][0-9]*", value):
            raise ValueError("native_junit_counter_invalid")
        totals[key] = int(value)
    pairs = []
    for child in suite:
        if child.tag != "testcase" or set(child.attrib) - {"classname", "name", "time"} or len(child):
            raise ValueError("native_junit_case_result_invalid")
        if child.text and child.text.strip():
            raise ValueError("native_junit_case_body_forbidden")
        pair = (child.get("classname"), child.get("name"))
        if any(type(value) is not str or not value for value in pair) or pair in pairs:
            raise ValueError("native_junit_case_duplicate_or_invalid")
        pairs.append(pair)
    required = [(item["classname"], item["name"]) for item in descriptor["required_cases"]]
    if sorted(pairs) != sorted(required) or not strict_json_equal(totals, descriptor["required_counts"]):
        raise ValueError("native_junit_semantic_failure")
    if totals["tests"] != len(pairs):
        raise ValueError("native_junit_counter_mismatch")
    return {**totals, "cases": [{"classname": a, "name": b} for a, b in sorted(pairs)]}


def _native_windows_arguments(argv):
    # N03 applies the standard Windows CreateProcess argument quoting rule.
    import re
    def quote(value):
        value = re.sub(r'(\\*)"', lambda match: match[1] * 2 + '\\"', value)
        value = re.sub(r'(\\+)$', lambda match: match[1] * 2, value)
        return '"' + value + '"'
    return " ".join(quote(value) for value in argv)


def _verify_native_process(process: dict, *, executable: str, argv: list[str], cwd: str, stdin_utf8: str) -> None:
    import math
    fields = {"shape_valid", "root_exit_confirmed", "tree_exit_confirmed", "drains_completed", "stdin_completed",
        "stdin_writer_joined", "timed_out", "startup_failed", "process_error_present", "stdout_truncated", "stderr_truncated",
        "retry_allowed", "exit_code", "child_exit_code", "stdin_error_code", "stdin_close_error_code", "cleanup_error_code",
        "cancellation_error_code", "root_process_id", "stdin_bytes_written", "duration_sec", "cleanup_state", "executable",
        "arguments", "command_line_arguments", "working_directory"}
    if type(process) is not dict or set(process) != fields:
        raise ValueError("native_process_projection_fields_invalid")
    verify_process_success(process, cwd=cwd, input_bytes=len(stdin_utf8.encode("utf-8")))
    for key in ("stdout_truncated", "stderr_truncated"):
        if process.get(key) is not False:
            raise ValueError("native_process_truncated_or_unknown")
    if (type(process.get("root_process_id")) is not int or not 1 <= process["root_process_id"] <= 4294967295
            or type(process.get("duration_sec")) not in (int, float)
            or not math.isfinite(process["duration_sec"]) or process["duration_sec"] < 0
            or process.get("retry_allowed") is not True):
        raise ValueError("native_process_identity_or_duration_invalid")
    if (type(process.get("executable")) is not str or process["executable"] != executable
            or not strict_json_equal(process.get("arguments"), argv)
            or process.get("command_line_arguments") != _native_windows_arguments(argv)):
        raise ValueError("native_process_launch_mismatch")


def verify_native_validation(descriptor, raw_xml, process, *, context):
    if type(context) is not dict or context.get("descriptor_sha256") != _native_hash(descriptor):
        raise ValueError("native_validator_descriptor_binding_mismatch")
    _verify_native_process(process, executable=descriptor["executable"], argv=descriptor["argv"],
                           cwd=descriptor["cwd"], stdin_utf8=descriptor["stdin_utf8"])
    return _parse_native_junit(descriptor, raw_xml)


def _reserve_native_receipt(descriptor: dict) -> None:
    import os
    _native_descriptor(descriptor)
    path = bound_path(descriptor["receipt_path"], root=bound_path(descriptor["cwd"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    bound_path(str(path))
    try:
        with path.open("xb") as stream:
            stream.write(VALIDATOR_MARKER)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise ValueError("native_validator_existing_receipt_no_replay") from exc
    if _native_file(path) != VALIDATOR_MARKER:
        raise ValueError("native_validator_reservation_readback_failed_no_replay")


def _native_utc_timestamp(value):
    import re
    from datetime import datetime
    if type(value) is not str:
        raise ValueError("native_execution_timestamp_invalid")
    matched = re.fullmatch(r"([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})(?:\.([0-9]{1,7}))?(?:Z|\+00:00)", value)
    if matched is None:
        raise ValueError("native_execution_timestamp_invalid")
    try:
        second = datetime.fromisoformat(matched[1] + "+00:00")
    except ValueError as exc:
        raise ValueError("native_execution_timestamp_invalid") from exc
    return second, int((matched[2] or "").ljust(7, "0"))


def provider_preservation_binding(request, packet_sha256, launch_sha256):
    """Bind the existing selected invocation, claim and full source closure."""
    from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import (
        validate_preservation_contract,
    )
    contract = validate_preservation_contract(request)
    from automation.orchestration.aios_resume_state import require_hash
    require_hash(packet_sha256, "preservation_packet_hash_invalid")
    require_hash(launch_sha256, "preservation_launch_hash_invalid")
    identity = request["repository_identity"]
    identity = {"resolved": identity["resolved"], "reason": "resolved", "repo_root": identity["repo_root"],
                "git_dir": identity["git_dir"], "branch": identity["branch"],
                "symbolic_ref": "refs/heads/" + identity["branch"], "detached": False, "commit": identity["commit"]}
    return {"task": {"task_id": request["task_id"], "packet_id": request["packet_id"],
                     "attempt_id": request["attempt_id"], "action_id": contract["action_id"]},
            "repository_identity": identity,
            "interval_ref": _native_hash({"request": request, "packet_sha256": packet_sha256, "launch_sha256": launch_sha256}),
            "allowed_paths": request["allowed_paths"], "max_files_changed": contract["max_files_changed"],
            "implementation_manifest": request["source_manifest"],
            "capture_contract": {"schema": "AIOS_FULL_WORKTREE_STATE_CAPTURE.v1", "domain": "entire_worktree_subtree",
                                 "platform": "nt", "rules_sha256": contract["rules_sha256"]}}


def _compare_provider_preservation(binding, execution, before_raw, after_raw):
    from automation.orchestration.aios_self_build_apply_result_verifier import (
        build_self_build_apply_result_verifier,
    )
    task = binding["task"]
    queue = {**task, "allowed_paths": binding["allowed_paths"]}
    executor = {**task, "selected_action": task["action_id"], "command_executed": True,
                "allowed_paths": binding["allowed_paths"], "max_files_changed": binding["max_files_changed"],
                "repository_identity": binding["repository_identity"], "interval_ref": binding["interval_ref"],
                "execution_record_sha256": _native_hash(execution),
                "execution_started_at_utc": execution["started_at_utc"], "execution_ended_at_utc": execution["ended_at_utc"]}
    context = {"schema": "AIOS_APPLY_PRESERVATION_CONTEXT.v1", "binding": binding,
               "execution": {"record_sha256": _native_hash(execution), "started_at_utc": execution["started_at_utc"],
                             "ended_at_utc": execution["ended_at_utc"]},
               "before_manifest_sha256": hashlib.sha256(before_raw).hexdigest(),
               "after_manifest_sha256": hashlib.sha256(after_raw).hexdigest()}
    # Scoped preservation only: no invented validator PASS or completion result.
    result = build_self_build_apply_result_verifier(queue, executor, "", "", [], binding["allowed_paths"],
        binding["max_files_changed"], preservation_context=context, before_manifest=before_raw, after_manifest=after_raw)
    if result.get("preservation_comparison_passed") is not True:
        raise ValueError("preservation_rejected:" + str(result.get("preservation_reasons")))
    return result


def capture_provider_preservation(request, packet_sha256, launch_sha256, phase):
    """Actual collector seam; no writes and no substituted live domain/rules."""
    import sys

    from automation.orchestration.aios_repo_state_evidence import (
        capture_full_worktree_state,
    )
    binding = provider_preservation_binding(request, packet_sha256, launch_sha256)
    if str(Path(sys.executable).resolve()) != request["python_executable"]:
        raise ValueError("preservation_running_runtime_mismatch")
    raw = capture_full_worktree_state(request["repo_root"], binding=binding, phase=phase)
    # Reject incomplete BEFORE evidence before invoking the provider, using
    # the accepted comparator's exact snapshot parser. Never manufacture the
    # other phase; only the later real pair can establish preservation.
    from automation.orchestration.aios_self_build_apply_result_verifier import (
        _preservation_manifest,
    )
    stamp = _native_json(raw)["captured_at_utc"]
    _preservation_manifest(raw, {"binding": binding, phase + "_manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "execution": {"started_at_utc": stamp, "ended_at_utc": stamp}}, phase)
    return {"utf8": raw.decode("ascii"), "sha256": hashlib.sha256(raw).hexdigest()}


def complete_provider_preservation(request, packet_sha256, launch_sha256, capture, before, after, provider_started):
    interval = {"schema": "AIOS_SELECTED_PROVIDER_INTERVAL.v1",
                "binding": provider_preservation_binding(request, packet_sha256, launch_sha256),
                "execution": {"request_sha256": _native_hash(request), "packet_sha256": packet_sha256,
                    "launch_sha256": launch_sha256, "started_at_utc": provider_started,
                    "ended_at_utc": capture["ended_at"], "process_sha256": _native_hash(capture["process"])},
                "before": before, "after": after}
    candidate = {**capture, "provider_interval": interval}
    verify_provider_preservation(request, packet_sha256, launch_sha256, candidate)
    return interval


def verify_worker_observation(request, capture, *, prompt_utf8):
    """Read saved originals for the optional profile, without granting admission."""
    from automation.orchestration.aios_self_build_apply_result_verifier import check_worker_observation_handoff
    from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import validate_worker_observation_contract
    if 'worker_observation_contract' not in request:
        if 'worker_observation' in capture:
            raise ValueError('unbound_worker_observation')
        return None
    contract = validate_worker_observation_contract(request['worker_observation_contract'])
    checked = check_worker_observation_handoff(capture.get('worker_observation'))
    spec = checked['recording_request']
    witness = capture.get('process', {}).get('launch_witness', {})
    emitter = spec['process_chain'][1]
    if (spec['attempt_id'] != request['attempt_id']
            or any(spec[key] != contract[key] for key in ('session_id', 'mxc_identity', 'policy_sha256'))
            or emitter['pid'] != witness.get('child_process_id')
            or emitter['creation_filetime'] != witness.get('child_creation_filetime')
            or emitter['parent_pid'] != witness.get('creator_process_id')
            or emitter['image_sha256'] != request['provider_sha256']):
        raise ValueError('worker_observation_emitter_or_attempt_mismatch')
    verify_provider_launch_witness(request, capture['process'], prompt_utf8=prompt_utf8)
    return checked


def verify_provider_launch_witness(request, process, *, prompt_utf8):
    """Recompute the optional record; existing original-proof authority is unchanged.

    Identity fields supplied by this same record are not an independent OS
    observation. This check therefore returns no origin or qualification credit.
    """
    from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import validate_worker_launch_contract
    from automation.orchestration.aios_self_build_apply_result_verifier import check_windows_launch_witness
    if type(request) is not dict or type(process) is not dict:
        raise ValueError('provider_launch_record_invalid')
    contract = request.get('worker_launch_contract')
    witness = process.get('launch_witness')
    if 'worker_launch_contract' not in request:
        if 'launch_witness' in process:
            raise ValueError('unbound_provider_launch_record')
        return None
    contract = validate_worker_launch_contract(contract)
    if type(witness) is not dict:
        raise ValueError('provider_launch_record_missing')
    if (process.get('executable') != request['provider_executable'] or process.get('arguments') != request['provider_args']
            or process.get('working_directory') != request['repo_root']):
        raise ValueError('provider_launch_route_mismatch')
    command = '"' + request['provider_executable'] + '" ' + _native_windows_arguments(request['provider_args'])
    if process.get('command_line_arguments') != _native_windows_arguments(request['provider_args']):
        raise ValueError('provider_launch_command_mismatch')
    process_fields = ('root_process_id', 'cleanup_state', 'root_exit_confirmed', 'tree_exit_confirmed',
        'drains_completed', 'stdin_completed', 'stdin_writer_joined', 'stdin_bytes_written',
        'stdin_error_code', 'stdin_close_error_code', 'cleanup_error_code', 'cancellation_error_code',
        'timed_out', 'startup_failed', 'process_error_present', 'exit_code', 'child_exit_code')
    return check_windows_launch_witness(witness,
        api_inputs={'executable':request['provider_executable'], 'command_line':command,
            'working_directory':request['repo_root'], 'environment':contract['environment'],
            'stdin_utf8':prompt_utf8},
        observed_identity={key:witness.get(key) for key in ('creator_process_id','child_process_id','child_creation_filetime')},
        process={key:process.get(key) for key in process_fields})


def verify_provider_preservation(request, packet_sha256, launch_sha256, capture):
    """Recompute from archived exact bytes before aggregate or publication."""
    if type(request) is not dict or type(capture) is not dict:
        raise ValueError("preservation_envelope_invalid")
    value = capture.get("provider_interval")
    if (type(value) is not dict or set(value) != {"schema", "binding", "execution", "before", "after"}
            or value["schema"] != "AIOS_SELECTED_PROVIDER_INTERVAL.v1"):
        raise ValueError("preservation_interval_missing")
    binding = provider_preservation_binding(request, packet_sha256, launch_sha256)
    if not strict_json_equal(value["binding"], binding):
        raise ValueError("preservation_binding_mismatch")
    execution = value["execution"]
    if (type(execution) is not dict or set(execution) != {"request_sha256", "packet_sha256", "launch_sha256",
            "started_at_utc", "ended_at_utc", "process_sha256"}
            or execution["request_sha256"] != _native_hash(request) or execution["packet_sha256"] != packet_sha256
            or execution["launch_sha256"] != launch_sha256 or execution["process_sha256"] != _native_hash(capture["process"])
            or _native_utc_timestamp(execution["started_at_utc"]) < _native_utc_timestamp(capture["started_at"])
            or execution["ended_at_utc"] != capture["ended_at"]):
        raise ValueError("preservation_execution_mismatch")
    raw = {}
    for phase in ("before", "after"):
        entry = value[phase]
        if (type(entry) is not dict or set(entry) != {"utf8", "sha256"} or type(entry["utf8"]) is not str
                or not 0 < len(entry["utf8"]) <= 16777216):
            raise ValueError("preservation_bytes_missing")
        raw[phase] = entry["utf8"].encode("ascii")
        if hashlib.sha256(raw[phase]).hexdigest() != entry["sha256"]:
            raise ValueError("preservation_bytes_changed")
    result = _compare_provider_preservation(binding, execution, raw["before"], raw["after"])
    # Tie the full-domain census to the existing explicit inventory, rather
    # than accepting a separately resealed unrelated ordinary-tree fixture.
    for phase in ("before", "after"):
        entries = _native_json(raw[phase])["entries"]
        for relative, expected in capture["before_manifest"].items():
            if phase == "after" and relative in request["allowed_paths"]:
                continue
            node = entries.get(relative, {"kind": "absent"})
            actual = node.get("sha256") if node.get("kind") == "file" else None
            if actual != expected or (expected is None and node.get("kind") not in {"absent"}):
                raise ValueError("preservation_explicit_inventory_mismatch")
    return result


def _verify_native_context(repo_root, context, reader, *, live):
    from automation.orchestration.aios_abcd_autonomy_runner import _acceptance_request
    from automation.orchestration.claims.aios_task_claim_control import normalize_claim
    from automation.orchestration.aios_repo_state_evidence import parse_git_status_z
    from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import source_relative
    root = bound_path(str(repo_root))
    data = _native_admitted(context, reader)
    required = {"schema", "dispatch_item", "queue_item", "claim", "request_json", "evidence",
                "implementation_manifest", "descriptor", "descriptor_sha256", "task_before", "task_after",
                "status", "requested", "host", "original_resolver_packet", "after_manifest"}
    if set(data) != required or data["schema"] != "AIOS_NATIVE_REQUIREMENT_CONTEXT.v1":
        raise ValueError("native_context_fields_invalid")
    calculated = _acceptance_request(data["dispatch_item"], data["queue_item"], data["claim"])
    if not strict_json_equal(_native_request_dict(calculated), _native_request_dict(context.request)):
        raise ValueError("native_selection_claim_mismatch")
    claim = normalize_claim(data["claim"])
    request = _native_json(data["request_json"])
    if type(request) is not dict:
        raise ValueError("native_request_object_required")
    evidence = data["evidence"]
    if type(evidence) is not dict or set(evidence) != {"packet", "observation", "launch", "capture", "prompt"}:
        raise ValueError("native_saved_evidence_missing")
    prompt_entry = evidence["prompt"]
    if (type(prompt_entry) is not dict or set(prompt_entry) != {"path", "sha256", "utf8"}
            or type(prompt_entry["utf8"]) is not str):
        raise ValueError("native_raw_prompt_evidence_missing")
    from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import validate_prompt, ValidatedPrompt
    prompt_path = bound_path(prompt_entry["path"], root=root)
    source_relative(prompt_path.relative_to(root).as_posix())
    parsed_prompt = validate_prompt(_NativePromptBytes(prompt_entry["utf8"].encode("utf-8")))
    archived_prompt = ValidatedPrompt(prompt_path, parsed_prompt.text, parsed_prompt.sha256,
                                     parsed_prompt.packet_id, parsed_prompt.mode, parsed_prompt.allowed_paths)
    _native_nonprivate_path(request.get("provider_executable"), anchor=root)
    validate_bound_request(request, archived_prompt)
    from automation.orchestration.aios_resume_state import requested_projections
    requested_projections(root, data["requested"])
    for key in ("state_path", "resume_dir", "control_dir"):
        source_relative(data["requested"][key])
        _native_nonprivate_path(str(root / data["requested"][key]), anchor=root)
    if (data["requested"]["write_control"] is not False
            or data["requested"]["emit_continuation_controller"] is not False):
        raise ValueError("native_initial_projection_profile_invalid")
    if data["requested"]["write_resume"] is not True:
        raise ValueError("native_resume_publication_required")
    if canonical_json(request).decode("ascii") != data["request_json"]:
        raise ValueError("native_request_not_canonical")
    if live:
        validate_bound_request(request)
    if (request.get("repo_root") != str(root) or request.get("task_id") != context.request.task_id
            or request.get("packet_id") != context.request.packet_id or request.get("attempt_id") != claim.get("attempt_id")
            or type(request.get("attempt_number")) is not int or request["attempt_number"] != claim.get("attempt")
            or request["attempt_number"] != data["dispatch_item"].get("attempt", 0)
            or type(request.get("max_attempts")) is not int or request["max_attempts"] != data["dispatch_item"].get("max_attempts", 1)
            or not strict_json_equal(request.get("claim_ref"), {"owner": "TaskClaimController", "task_id": context.request.task_id,
                "acquired_at": context.request.acquired_at, "identity_sha256": context.request.claim_sha256})):
        raise ValueError("native_original_attempt_mismatch")
    manifest = data["implementation_manifest"]
    required_sources = {"automation/orchestration/" + name for name in __import__("automation.orchestration.aios_resume_state", fromlist=["SOURCE_FILES"]).SOURCE_FILES}
    from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import BOUND_IMPLEMENTATIONS
    running_sources = required_sources | set(BOUND_IMPLEMENTATIONS) | {"automation/orchestration/relay/aios_self_consuming_codex_cycle_v1.py",
        "automation/orchestration/aios_abcd_autonomy_runner.py", "automation/orchestration/claims/aios_task_claim_control.py",
        "automation/orchestration/aios_repo_state_evidence.py"}
    required_sources = running_sources | set(request["source_manifest"])
    if type(manifest) is not dict or not required_sources <= manifest.keys():
        raise ValueError("native_implementation_manifest_incomplete")
    _native_manifest(root, manifest, live=True)
    if any(value is None for value in manifest.values()):
        raise ValueError("native_implementation_hash_missing")
    actual_source_root = Path(__file__).resolve().parents[3]
    for relative in running_sources:
        if hashlib.sha256(_native_file(actual_source_root / relative)).hexdigest() != manifest[relative]:
            raise ValueError("native_running_implementation_mismatch")
    if any(manifest.get(key) != value for key, value in request["source_manifest"].items()):
        raise ValueError("native_request_source_mismatch")
    policy_relative = bound_path(request["policy_path"], root=root).relative_to(root).as_posix()
    if policy_relative not in manifest:
        raise ValueError("native_policy_source_pin_missing")
    _native_pin(request["provider_executable"], request["provider_sha256"])
    if request["repository_identity"]["commit"] != claim["base_sha"] or request["repository_identity"]["branch"] != claim["branch"]:
        raise ValueError("native_claim_head_branch_mismatch")
    if set(data["task_before"]) != set(request["allowed_paths"]) or set(data["task_after"]) != set(request["allowed_paths"]):
        raise ValueError("native_task_manifest_scope_mismatch")
    if set(manifest) & set(data["task_after"]):
        raise ValueError("native_implementation_target_overlap")
    _native_manifest(root, data["task_before"], live=False)
    _native_manifest(root, data["task_after"], live=live)
    descriptor = _native_descriptor(data["descriptor"], live=True, source_root=root,
                                   allowed=[root / path for path in request["allowed_paths"]])
    if data["descriptor_sha256"] != _native_hash(descriptor) or request.get("validator_spec_sha256") != data["descriptor_sha256"]:
        raise ValueError("native_descriptor_digest_mismatch")
    status = data["status"]
    parser_path = "automation/orchestration/aios_repo_state_evidence.py"
    if type(status) is not dict or set(status) != {"before", "after", "parser_sha256"} or status["parser_sha256"] != manifest[parser_path]:
        raise ValueError("native_status_parser_mismatch")
    for phase in ("before", "after"):
        evidence = status[phase]
        if type(evidence) is not dict or set(evidence) != {"raw_base64", "sha256", "paths"}:
            raise ValueError("native_status_evidence_missing")
        raw = base64.b64decode(evidence["raw_base64"], validate=True)
        if hashlib.sha256(raw).hexdigest() != evidence["sha256"]:
            raise ValueError("native_status_bytes_mismatch")
        if len(raw) > 16777216:
            raise ValueError("native_status_size_invalid")
        parsed = parse_git_status_z(raw)
        _native_status_entries(parsed, request["repository_identity"]["branch"])
        if parsed["errors"]:
            raise ValueError("native_status_incomplete")
        paths = sorted({item[key] for item in parsed["entries"] for key in ("path", "source_path") if key in item})
        if not strict_json_equal(evidence["paths"], paths):
            raise ValueError("native_status_endpoint_mismatch")
        for relative in paths:
            source_relative(relative)
            if relative not in {*request["source_paths"], *request["controller_metadata_paths"], *_native_controller_slots(root, request)}:
                raise ValueError("native_status_uninspectable_endpoint")
    evidence = data["evidence"]
    if type(evidence) is not dict or set(evidence) != {"packet", "observation", "launch", "capture", "prompt"}:
        raise ValueError("native_saved_evidence_missing")
    decoded = {}
    for role, entry in evidence.items():
        if type(entry) is not dict or set(entry) != {"path", "sha256", "utf8"} or type(entry["utf8"]) is not str:
            raise ValueError("native_saved_evidence_shape_invalid")
        path = bound_path(entry["path"], root=root)
        source_relative(path.relative_to(root).as_posix())
        raw = entry["utf8"].encode("utf-8")
        if len(raw) > 16777216 or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ValueError("native_saved_evidence_digest_mismatch")
        if live and _native_file(path) != raw:
            raise ValueError("native_saved_evidence_readback_mismatch")
        if role == "prompt":
            decoded[role] = raw
        else:
            decoded[role] = _native_json(raw)
            if type(decoded[role]) is not dict:
                raise ValueError("native_saved_role_object_required")
    packet = decoded["packet"]
    from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import validate_prompt
    prompt = validate_prompt(_NativePromptBytes(decoded["prompt"]))
    if (evidence["prompt"]["path"] != request["prompt_path"] or prompt.sha256 != request["prompt_sha256"]
            or prompt.packet_id != request["packet_id"] or prompt.mode != "APPLY"
            or list(prompt.allowed_paths) != request["allowed_paths"] or packet.get("prompt_text") != prompt.text):
        raise ValueError("native_archived_prompt_binding_mismatch")
    digest = _native_hash(request)
    binding = request_binding(request, digest)
    task_id = "bound-" + digest
    # Reconstruct exact unchanged-producer bytes from archived prompt bytes.
    # The adapter supplies bytes only; its admitted real Path is restored above.
    from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import _enqueue_bound
    expected_packet = _enqueue_bound(archived_prompt, bound_path(request["relay_root"], root=root), DEFAULT_FLAGS, request, True)
    packet_raw = evidence["packet"]["utf8"].encode("utf-8")
    if (expected_packet["status"] != "DRY_RUN" or not strict_json_equal(packet, expected_packet["task"])
            or packet_raw != canonical_json(expected_packet["task"]) + b"\n"
            or evidence["packet"]["sha256"] != expected_packet["packet_sha256"]):
        raise ValueError("native_packet_mismatch")
    relay = bound_path(request["relay_root"], root=root)
    if bound_path(evidence["packet"]["path"], root=root) not in {relay / state / (task_id + ".task.json") for state in ("inbox", "running", "done", "error")}:
        raise ValueError("native_packet_path_mismatch")
    launch_fields = {"schema", "binding", "request_json", "packet_sha256", "started_at", "authority_granted"}
    capture_fields = launch_fields | {"ended_at", "process", "controller_capture_contract", "before_manifest", "before_status_paths", "retry_allowed", "provider_interval"}
    capture_schema = decoded["capture"].get("schema")
    if capture_schema == "AIOS_RELAY_EXECUTION.v2":
        capture_fields.add("status")
        if not strict_json_equal(read_capture_status(decoded["capture"]), data["status"]):
            raise ValueError("native_original_status_capture_mismatch")
    elif capture_schema != "AIOS_RELAY_EXECUTION.v1":
        raise ValueError("native_capture_schema_invalid")
    if "provider_interval" not in decoded["capture"]:
        raise ValueError("preservation_interval_missing")
    if set(decoded["launch"]) != launch_fields or set(decoded["capture"]) != capture_fields:
        raise ValueError("native_saved_role_fields_invalid")
    for role, schema in (("launch", "AIOS_RELAY_LAUNCH_OBSERVATION.v1"), ("capture", capture_schema)):
        saved = decoded[role]
        if (saved.get("schema") != schema or not strict_json_equal(saved.get("binding"), binding)
                or saved.get("request_json") != data["request_json"] or saved.get("packet_sha256") != evidence["packet"]["sha256"]
                or saved.get("authority_granted") is not False):
            raise ValueError("native_saved_binding_mismatch")
    capture = decoded["capture"]
    original_action = data["original_resolver_packet"].get("action_id", data["original_resolver_packet"].get("selected_action", context.request.task_id))
    if request["preservation_contract"]["action_id"] != original_action:
        raise ValueError("preservation_selected_action_mismatch")
    verify_provider_preservation(request, evidence["packet"]["sha256"], evidence["launch"]["sha256"], capture)
    verify_provider_launch_witness(request, capture["process"], prompt_utf8=prompt.text)
    capture_path = relay / "outbox" / (task_id + ".execution.json")
    launch_path = relay / "outbox" / (task_id + ".launch.json")
    if bound_path(evidence["capture"]["path"]) != capture_path or bound_path(evidence["launch"]["path"]) != launch_path:
        raise ValueError("native_capture_path_mismatch")
    contract = {"path": capture_path.relative_to(root).as_posix(), "required_before": None, "write_mode": "CreateNew"}
    before = capture.get("before_manifest")
    if (capture.get("retry_allowed") is not False or not strict_json_equal(capture.get("controller_capture_contract"), contract)
            or type(before) is not dict or before.get(contract["path"], "missing") is not None
            or before.get(launch_path.relative_to(root).as_posix()) != evidence["launch"]["sha256"]
            or any(before.get(path, "missing") != value for path, value in data["task_before"].items())
            or not strict_json_equal(capture.get("before_status_paths"), status["before"]["paths"])
            or capture.get("started_at") != decoded["launch"].get("started_at")
            or type(capture.get("ended_at")) is not str or not capture["ended_at"]):
        raise ValueError("native_capture_provenance_incomplete")
    started = _native_utc_timestamp(capture["started_at"])
    ended = _native_utc_timestamp(capture["ended_at"])
    if ended < started:
        raise ValueError("native_execution_time_order_invalid")
    _native_manifest(root, before, live=False)
    required_inventory = {*request["source_paths"], *request["controller_metadata_paths"],
                          *_native_controller_slots(root, request), policy_relative}
    after_inventory = data["after_manifest"]
    if set(before) != required_inventory or type(after_inventory) is not dict or set(after_inventory) != required_inventory:
        raise ValueError("native_provider_inventory_coverage_invalid")
    _native_manifest(root, after_inventory, live=False)
    full_after = _native_json(capture["provider_interval"]["after"]["utf8"])["entries"]
    for relative, expected in data["task_after"].items():
        if full_after.get(relative, {}).get("sha256") != expected:
            raise ValueError("preservation_task_after_mismatch")
    for relative, prior in before.items():
        if relative in request["allowed_paths"]:
            if after_inventory[relative] != data["task_after"][relative]:
                raise ValueError("native_task_after_inventory_mismatch")
        elif relative == contract["path"]:
            if prior is not None or after_inventory[relative] != evidence["capture"]["sha256"]:
                raise ValueError("native_capture_owned_delta_mismatch")
        elif not strict_json_equal(prior, after_inventory[relative]):
            raise ValueError("native_non_task_provider_delta")
    _verify_native_process(capture.get("process"), executable=request["provider_executable"], argv=request["provider_args"],
                           cwd=str(root), stdin_utf8=packet["prompt_text"])
    observation = decoded["observation"]
    observation_fields = {*binding, "schema", "repo_root", "relay_root", "status", "reason", "authority_granted", "retry_allowed", "execution_path", "execution_sha256"}
    if set(observation) != observation_fields or observation["reason"] != "INDEPENDENT_ACCEPTANCE_REQUIRED":
        raise ValueError("native_observation_fields_invalid")
    if (observation.get("schema") != "AIOS_RELAY_OBSERVATION.v1" or observation.get("status") != "EXECUTED_AWAITING_VALIDATION"
            or observation.get("authority_granted") is not False or observation.get("retry_allowed") is not False
            or any(not strict_json_equal(observation.get(key), value) for key, value in binding.items())
            or observation.get("execution_path") != str(capture_path) or observation.get("execution_sha256") != evidence["capture"]["sha256"]
            or observation.get("repo_root") != str(root) or observation.get("relay_root") != str(relay)):
        raise ValueError("native_observation_not_authentic_execution")
    if not bound_path(evidence["observation"]["path"]).is_relative_to(relay / "outbox"):
        raise ValueError("native_observation_path_mismatch")
    if Path(evidence["observation"]["path"]).name != task_id + ".result." + evidence["observation"]["sha256"] + ".json":
        raise ValueError("native_observation_filename_mismatch")
    original = data["original_resolver_packet"]
    if type(original) is not dict or not original:
        raise ValueError("native_original_resolver_packet_missing")
    host = data["host"]
    if type(host) is not dict or set(host) != {"executable", "sha256", "timeout_sec", "maximum_output_characters"}:
        raise ValueError("native_host_contract_missing")
    _native_pin(_native_nonprivate_path(host["executable"], anchor=root), host["sha256"])
    protected = [root / relative for relative in manifest] + [Path(host["executable"])]
    for relative in request["allowed_paths"]:
        target = root / relative
        if any(target == path or target in path.parents or path in target.parents for path in protected):
            raise ValueError("native_provider_overlaps_implementation_or_host")
    if type(host["timeout_sec"]) is not int or not 1 <= host["timeout_sec"] <= 2147483 or type(host["maximum_output_characters"]) is not int or not 1 <= host["maximum_output_characters"] <= 16777216:
        raise ValueError("native_host_limits_invalid")
    if live:
        _native_repository_identity(root, data)
    return data


def _verify_native_result(data, validation_record):
    if type(validation_record) is not dict or set(validation_record) != {"schema", "descriptor_sha256", "process", "receipt_utf8", "receipt_sha256", "summary"}:
        raise ValueError("native_validation_record_invalid")
    if validation_record["schema"] != NATIVE_RESULT or type(validation_record["receipt_utf8"]) is not str:
        raise ValueError("native_validation_record_invalid")
    raw = validation_record["receipt_utf8"].encode("utf-8")
    summary = verify_native_validation(data["descriptor"], raw, validation_record["process"], context=data)
    if (validation_record["descriptor_sha256"] != data["descriptor_sha256"]
            or hashlib.sha256(raw).hexdigest() != validation_record["receipt_sha256"]
            or not strict_json_equal(summary, validation_record["summary"])):
        raise ValueError("native_validation_record_binding_mismatch")
    return raw


def native_execution_identity(repo_root, context, validation_record, *, native_admission_reader, live=True):
    data = _verify_native_context(repo_root, context, native_admission_reader, live=live)
    raw = _verify_native_result(data, validation_record)
    if live and _native_file(data["descriptor"]["receipt_path"], data["descriptor"]["receipt_max_bytes"]) != raw:
        raise ValueError("native_validator_receipt_changed")
    request = _native_json(data["request_json"])
    identity = {"identity_contract": NATIVE_IDENTITY, "repo_root": str(bound_path(str(repo_root))),
        "requirement_request": _native_request_dict(context.request), "context_json": context.context_json,
        "context_sha256": hashlib.sha256(context.context_json.encode("ascii")).hexdigest(),
        "task_id": request["task_id"], "attempt_id": request["attempt_id"], "attempt_number": request["attempt_number"],
        "source_hashes": data["implementation_manifest"],
        "prompt_binding": {"raw_sha256": data["evidence"]["prompt"]["sha256"],
            "text_sha256": hashlib.sha256(_native_json(data["evidence"]["packet"]["utf8"])["prompt_text"].encode("utf-8")).hexdigest(),
            "stdin_byte_count": len(_native_json(data["evidence"]["packet"]["utf8"])["prompt_text"].encode("utf-8"))},
        "successful_result": validation_record,
        "successful_result_sha256": _native_hash(validation_record)}
    if live:
        _native_verify_live_state(bound_path(str(repo_root)), data, context, native_admission_reader, identity)
    return identity


def _native_process_bridge_source():
    # The only widened source field is the actual N02 UInt32 process id.
    # Raw values are checked before any cast; fresh scalars remove ETS aliases.
    return r'''function ConvertTo-AiOsNativeProcessProjectionInput {
 param([object]$Run)
 $fresh=[ordered]@{}
 foreach($name in @('timed_out','startup_failed','root_exit_confirmed','tree_exit_confirmed','drains_completed','retry_allowed','stdin_completed','stdin_writer_joined','stdout_truncated','stderr_truncated')){
  $property=$Run.PSObject.Properties[$name]
  if($null -eq $property -or $property.Value -isnot [bool]){throw 'NATIVE_PROCESS_BOOLEAN_TYPE_INVALID'}
  $fresh[$name]=[bool]$property.Value
 }
 foreach($name in @('exit_code','child_exit_code','stdin_error_code','stdin_close_error_code','cleanup_error_code','cancellation_error_code')){
  $property=$Run.PSObject.Properties[$name]
  if($null -eq $property -or $property.Value -isnot [int]){throw 'NATIVE_PROCESS_INTEGER_TYPE_INVALID'}
  $fresh[$name]=[int]$property.Value
 }
 $property=$Run.PSObject.Properties['root_process_id']
 if($null -eq $property -or $property.Value -isnot [uint32] -or $property.Value -eq 0){throw 'NATIVE_PROCESS_PID_TYPE_INVALID'}
 $fresh['root_process_id']=[long]$property.Value
 $property=$Run.PSObject.Properties['stdin_bytes_written']
 if($null -eq $property -or $property.Value -isnot [long] -or $property.Value -lt 0){throw 'NATIVE_PROCESS_INPUT_COUNT_TYPE_INVALID'}
 $fresh['stdin_bytes_written']=[long]$property.Value
 foreach($name in @('cleanup_state','executable','working_directory','command_line_arguments','process_error')){
  $property=$Run.PSObject.Properties[$name]
  if($null -eq $property -or $property.Value -isnot [string]){throw 'NATIVE_PROCESS_STRING_TYPE_INVALID'}
  $fresh[$name]=[string]$property.Value
 }
 $property=$Run.PSObject.Properties['duration_sec']
 if($null -eq $property -or $property.Value -isnot [double] -or [double]::IsNaN($property.Value) -or [double]::IsInfinity($property.Value) -or $property.Value -lt 0){throw 'NATIVE_PROCESS_DURATION_TYPE_INVALID'}
 $fresh['duration_sec']=[double]$property.Value
 $property=$Run.PSObject.Properties['arguments']
 if($null -eq $property -or $property.Value -isnot [array]){throw 'NATIVE_PROCESS_ARGUMENTS_TYPE_INVALID'}
 $argv=[Collections.Generic.List[string]]::new()
 foreach($arg in $property.Value){if($arg -isnot [string]){throw 'NATIVE_PROCESS_ARGUMENT_TYPE_INVALID'};$argv.Add([string]$arg)}
 $fresh['arguments']=[string[]]$argv.ToArray()
 return [pscustomobject]$fresh
}'''


def _invoke_native_aggregate_host(repo_root, data):
    descriptor = data["descriptor"]
    host = data["host"]
    parameters = {"FilePath": descriptor["executable"], "ArgumentList": descriptor["argv"],
        "TimeoutSec": host["timeout_sec"], "StdIn": descriptor["stdin_utf8"], "WorkingDirectory": descriptor["cwd"],
        "MaximumOutputCharacters": host["maximum_output_characters"]}
    pins = {str(repo_root / relative): digest for relative, digest in data["implementation_manifest"].items()}
    pins.update(descriptor["input_manifest"])
    pins.update(descriptor["observed_producer_sources"])
    pins[descriptor["executable"]] = descriptor["executable_sha256"]
    transport = canonical_json({"parameters": parameters, "environment": descriptor["environment"], "pins": pins}).decode("ascii")
    adapter = str(repo_root / "automation/orchestration/timeout/Invoke-AiOsCliWithTimeout.ps1").replace("'", "''")
    worker = str(repo_root / "automation/orchestration/relay/Invoke-AiOsRelayWorker.ps1").replace("'", "''")
    bootstrap = r"""$ErrorActionPreference='Stop';[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$p=[Console]::In.ReadToEnd()|ConvertFrom-Json
foreach($pin in $p.pins.PSObject.Properties){$h=[Security.Cryptography.SHA256]::Create();try{$digest=[BitConverter]::ToString($h.ComputeHash([IO.File]::ReadAllBytes($pin.Name))).Replace('-','').ToLowerInvariant()}finally{$h.Dispose()};if($digest -cne [string]$pin.Value){throw 'HOST_INPUT_PIN_CHANGED_NO_REPLAY'}}
foreach($path in @('ADAPTER','WORKER')) {
 $t=$null;$e=$null;$a=[Management.Automation.Language.Parser]::ParseFile($path,[ref]$t,[ref]$e);if($e.Count){throw 'HOST_SOURCE_PARSE_FAILED'}
 foreach($d in $a.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst]},$false)){Set-Item -Path ('Function:'+$d.Name) -Value $d.Body.GetScriptBlock()}
}
$argsHost=@{};foreach($v in $p.parameters.PSObject.Properties){$argsHost[$v.Name]=$v.Value}
$expected=@{};foreach($v in $p.environment.PSObject.Properties){$expected[$v.Name]=[string]$v.Value}
foreach($key in @([Environment]::GetEnvironmentVariables('Process').Keys)){[Environment]::SetEnvironmentVariable([string]$key,$null,'Process')}
foreach($key in $expected.Keys){[Environment]::SetEnvironmentVariable($key,$expected[$key],'Process')}
. Import-AiOsCliProcessPrimitive
Initialize-AiOsOwnedValidatorProcess
$actual=[Environment]::GetEnvironmentVariables('Process');if($actual.Count -ne $expected.Count){throw 'HOST_EXACT_ENV_COUNT_MISMATCH'}
foreach($key in $expected.Keys){if(-not $actual.Contains($key) -or -not [string]::Equals([string]$actual[$key],$expected[$key],[StringComparison]::Ordinal)){throw 'HOST_EXACT_ENV_VALUE_MISMATCH'}}
NATIVE_BRIDGE
$run=Invoke-AiOsCliProcess @argsHost
$readback=@{};foreach($key in [Environment]::GetEnvironmentVariables('Process').Keys){$readback[[string]$key]=[string][Environment]::GetEnvironmentVariable([string]$key,'Process')}
$projection=Get-AiOsBoundProcessProjection $run
$result=@{process=$projection;environment=$readback}
try{$fresh=ConvertTo-AiOsNativeProcessProjectionInput $run;$result.process=Get-AiOsBoundProcessProjection $fresh}
catch{
 $result['bridge_error']='NATIVE_PROCESS_RAW_TYPES_REJECTED'
 $types=@{};foreach($property in $run.PSObject.Properties){if($null -ne $property.Value){$types[$property.Name]=$property.Value.GetType().FullName}}
 $result['raw_field_types']=$types
}
[Console]::WriteLine(($result|ConvertTo-Json -Depth 15 -Compress))
""".replace("ADAPTER", adapter).replace("WORKER", worker).replace("NATIVE_BRIDGE", _native_process_bridge_source())
    command = [host["executable"], "-NoProfile", "-EncodedCommand", base64.b64encode(bootstrap.encode("utf-16-le")).decode("ascii")]
    try:
        result = subprocess.run(command, cwd=descriptor["cwd"], env=dict(descriptor["environment"]), input=transport,
            capture_output=True, text=True, encoding="utf-8", timeout=host["timeout_sec"] + 120, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("native_validator_host_cleanup_unknown_no_replay") from exc
    if result.returncode != 0:
        raise ValueError("native_validator_host_failed_cleanup_unknown_no_replay")
    envelope = _native_json(result.stdout)
    if type(envelope) is dict and set(envelope) == {"process", "environment", "bridge_error", "raw_field_types"}:
        error = ValueError("native_validator_host_raw_process_types_invalid_no_replay")
        error.native_process_projection = envelope["process"]
        error.native_raw_process_field_types = envelope["raw_field_types"]
        raise error
    if type(envelope) is not dict or set(envelope) != {"process", "environment"} or not strict_json_equal(envelope["environment"], descriptor["environment"]):
        raise ValueError("native_validator_host_readback_invalid_no_replay")
    return envelope["process"]


def _native_rejected_process_evidence(process, descriptor):
    # Retain only known bounded projection fields, never stdout/stderr or XML.
    # Missing/unknown raw fields remain missing; no process result is invented.
    import math
    if type(process) is not dict:
        return {"available": False, "projection": None, "field_types": {}, "projection_sha256": None}
    fields = {"shape_valid", "root_exit_confirmed", "tree_exit_confirmed", "drains_completed", "stdin_completed",
        "stdin_writer_joined", "timed_out", "startup_failed", "process_error_present", "stdout_truncated", "stderr_truncated",
        "retry_allowed", "exit_code", "child_exit_code", "stdin_error_code", "stdin_close_error_code", "cleanup_error_code",
        "cancellation_error_code", "root_process_id", "stdin_bytes_written", "duration_sec", "cleanup_state", "executable",
        "arguments", "command_line_arguments", "working_directory"}
    selected = {}
    allowed_strings = {"cleanup_state": {"CONFIRMED", "UNRESOLVED"}, "executable": {descriptor["executable"]},
        "working_directory": {descriptor["cwd"]}, "command_line_arguments": {_native_windows_arguments(descriptor["argv"])}}
    for name in fields & process.keys():
        value = process[name]
        if value is None or type(value) is bool or type(value) is int and -(2**63) <= value < 2**63:
            selected[name] = value
        elif type(value) is float and math.isfinite(value):
            selected[name] = value
        elif type(value) is str and len(value) <= 32768 and value in allowed_strings.get(name, set()):
            selected[name] = value
        elif name == "arguments" and strict_json_equal(value, descriptor["argv"]):
            selected[name] = list(descriptor["argv"])
    try:
        digest = _native_hash(process)
    except (TypeError, ValueError, OverflowError):
        digest = None
    return {"available": True, "projection": selected,
        "field_types": {key: type(process[key]).__name__ for key in sorted(fields & process.keys())},
        "projection_sha256": digest}


def _record_native_validator_rejection(repo_root, context, reader, data, process, exc):
    from automation.orchestration import aios_wake_continue as wake, aios_resume_state as owner
    owner._native_selected_owner(repo_root, context, reader)
    receipt = {"path": data["descriptor"]["receipt_path"], "sha256": None, "size": None,
               "read_error_type": None}
    try:
        path = _native_nonprivate_path(receipt["path"], anchor=bound_path(data["descriptor"]["cwd"]))
        receipt["size"] = path.stat().st_size if path.is_file() else None
        raw = _native_file(path, data["descriptor"]["receipt_max_bytes"])
        receipt["sha256"] = hashlib.sha256(raw).hexdigest()
    except Exception as secondary:
        receipt["read_error_type"] = type(secondary).__name__
    report = {"schema": "AIOS_NATIVE_VALIDATION_FAILURE.v1", "result": "BLOCKED",
        "requirement_request": _native_request_dict(context.request), "native_context_sha256": _native_hash(data),
        "descriptor_sha256": data["descriptor_sha256"],
        "execution_capture": {key: data["evidence"]["capture"][key] for key in ("path", "sha256")},
        "validator_receipt": receipt, "process_evidence": _native_rejected_process_evidence(process, data["descriptor"]),
        "replay_allowed": False, "finalization": {"status": "incomplete", "errors": []}}
    raw_types = getattr(exc, "native_raw_process_field_types", None)
    if type(raw_types) is dict:
        report["raw_process_field_types"] = {key: value for key, value in raw_types.items()
            if key in report["process_evidence"]["field_types"] and type(value) is str and len(value) < 128}
    return wake.record_finalization_failure(repo_root, report, {"requested": data["requested"]},
        "native_aggregate_validation", exc, _immutable_only=True)


def run_native_aggregate_validator(context, *, native_admission_reader):
    data = _native_admitted(context, native_admission_reader)
    request = _native_json(data["request_json"])
    root = bound_path(request["repo_root"])
    from automation.orchestration import aios_resume_state as owner
    saved = owner.find_native_attempt(root, admitted_context=context, native_admission_reader=native_admission_reader)
    if saved is not None:
        return saved
    data = _verify_native_context(root, context, native_admission_reader, live=True)
    _native_verify_live_state(root, data, context, native_admission_reader)
    process = None
    try:
        _reserve_native_receipt(data["descriptor"])
        data = _verify_native_context(root, context, native_admission_reader, live=True)
        _native_verify_live_state(root, data, context, native_admission_reader)
        # Creator identity is this live control flow only, never matching bytes.
        process = _invoke_native_aggregate_host(root, data)
        raw = _native_file(data["descriptor"]["receipt_path"], data["descriptor"]["receipt_max_bytes"])
        summary = verify_native_validation(data["descriptor"], raw, process, context=data)
        record = {"schema": NATIVE_RESULT, "descriptor_sha256": data["descriptor_sha256"], "process": process,
            "receipt_utf8": raw.decode("utf-8"), "receipt_sha256": hashlib.sha256(raw).hexdigest(), "summary": summary}
    except Exception as exc:
        available = getattr(exc, "native_process_projection", process)
        try:
            exc.native_failure_report = _record_native_validator_rejection(root, context, native_admission_reader, data, available, exc)
        except Exception as secondary:
            # Retain the original primary outcome even if failure evidence fails.
            exc.native_failure_evidence_error = type(secondary).__name__
        raise
    # Complete authentic validation is captured before any projection builder.
    from automation.orchestration import aios_wake_continue as wake
    return wake.capture_native_finalization(root, admitted_context=context, validation_record=record,
        requested=data["requested"], native_admission_reader=native_admission_reader)


def make_native_acceptance_reader(repo_root, *, output_dir, native_admission_reader):
    from automation.orchestration import aios_resume_state as owner
    from automation.orchestration.aios_abcd_autonomy_runner import AcceptedRequirement
    def read(request):
        context = native_admission_reader(request)
        state = owner.load_native_requirement(repo_root, output_dir=output_dir, expected_request=request,
            admitted_context=context, native_admission_reader=native_admission_reader)
        return AcceptedRequirement(request) if state is not None else None
    return read


def make_native_execution_adapter(repo_root, *, expected_request, native_admission_reader, claim_controller, requested):
    from automation.orchestration import aios_resume_state as owner, aios_wake_continue as wake
    from automation.orchestration.claims.aios_task_claim_control import TaskClaimController
    if type(claim_controller) is not TaskClaimController:
        raise ValueError("native_existing_claim_controller_required")
    def execute(_packet):
        context = native_admission_reader(expected_request)
        data = _verify_native_context(repo_root, context, native_admission_reader, live=False)
        if not strict_json_equal(_packet, data["original_resolver_packet"]) or not strict_json_equal(requested, data["requested"]):
            raise ValueError("native_original_packet_or_projection_mismatch")
        claim = data["claim"]
        identity = _native_repository_identity(repo_root, data)
        changed_task_paths = sorted(path for path in data["task_before"]
                                    if not strict_json_equal(data["task_before"][path], data["task_after"][path]))
        # Concrete existing guard owns permission; context carries no new lease.
        decision = claim_controller.guard(expected_request.task_id, repository=claim["repository"], worktree=Path(claim["worktree"]),
            branch=claim["branch"], head_is_descendant=identity["commit"] == claim["base_sha"], changed_paths=changed_task_paths, expected_claim=claim)
        # The existing guard returns its selected normalized claim or raises;
        # it does not return a status envelope. Verify the actual owner result.
        from automation.orchestration.claims.aios_task_claim_control import normalize_claim, _claim_contract
        if (type(decision) is not dict or decision.get("state") not in {"ACTIVE", "VERIFYING", "INTEGRATING"}
                or _claim_contract(normalize_claim(decision)) != expected_request.claim_sha256):
            raise ValueError("native_existing_claim_guard_blocked")
        attempt = owner.find_native_attempt(repo_root, admitted_context=context, native_admission_reader=native_admission_reader)
        if attempt is None:
            attempt = run_native_aggregate_validator(context, native_admission_reader=native_admission_reader)
        report = wake.recover_native_finalization(repo_root, attempt, admitted_context=context, native_admission_reader=native_admission_reader)
        state = owner.load_native_requirement(repo_root, output_dir=requested["resume_dir"], expected_request=expected_request,
            admitted_context=context, native_admission_reader=native_admission_reader)
        if report.get("result") != "COMPLETE" or state is None:
            raise ValueError("native_publication_not_committed")
        notification = _preview_selected_event(repo_root, _native_json(data["request_json"]), {"status": "COMPLETE"},
            expected_request=expected_request, admitted_context=context, native_admission_reader=native_admission_reader)
        return {"status": "COMPLETE", "passed": True, "notification": notification}
    return execute


def _native_collect_status(root):
    from automation.orchestration import aios_repo_state_evidence as evidence
    result = evidence._run_git_status(root, subprocess.run)
    if (type(getattr(result, "returncode", None)) is not int or result.returncode != 0
            or type(getattr(result, "stdout", None)) is not bytes or len(result.stdout) > 16777216):
        raise ValueError("native_current_status_unavailable")
    return result.stdout


def _native_status_entries(parsed, branch):
    header = parsed["branch_line"]
    prefix = "## " + branch
    if (parsed["errors"] or type(header) is not str or not header
            or not (header == prefix or header.startswith(prefix + "...") or header.startswith(prefix + " ["))):
        raise ValueError("native_current_status_branch_or_parse_invalid")
    entries = {}
    for entry in parsed["entries"]:
        key = entry["path"]
        if key in entries:
            raise ValueError("native_status_duplicate_entry")
        entries[key] = entry
    return entries


def _native_status_owned_delta(root, relative, context, reader, data, identity):
    # This proves one exact byte projection; a directory or filename alone
    # never exempts an endpoint. Historical verification does not call here.
    from automation.orchestration import aios_resume_state as owner
    from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import source_relative
    path = _native_nonprivate_path(str(root / source_relative(relative)), anchor=root)
    descriptor = data["descriptor"]
    if path == Path(descriptor["receipt_path"]):
        raw = _native_file(path, descriptor["receipt_max_bytes"])
        expected = VALIDATOR_MARKER if identity is None else _verify_native_result(data, identity["successful_result"])
        return raw == expected
    if identity is None:
        return False
    target = owner._native_selected_owner(root, context, reader)
    if path == root / data["requested"]["state_path"]:
        raw = _native_file(path)
        projection = _native_json(raw)
        if type(projection) is not dict or type(projection.get("resume_state")) is not dict:
            return False
        pending = projection["resume_state"]
        attempt = owner._native_pending_attempt(root, pending, target, context, reader, identity)
        return raw == owner.serialized_bytes(owner._native_generic_projection(attempt, pending))
    if path.parent != target:
        return False
    if path.name == ".publication.lock":
        return _native_file(path, 1) == b"\0"
    if path.name.startswith("AIOS_RESUME_ATTEMPT_"):
        attempt = owner._load_native_attempt(root, path, admitted_context=context, native_admission_reader=reader, live=False)
        return strict_json_equal(attempt["execution_identity"], identity) and _native_file(path) == owner.serialized_bytes(attempt)
    if ".projection-generic-" in path.name:
        path = owner._native_owner_path(root, path, target, "snapshot")
        raw = _native_file(path)
        projection = _native_json(raw)
        if type(projection) is not dict or type(projection.get("resume_state")) is not dict:
            return False
        pending = projection["resume_state"]
        attempt = owner._native_pending_attempt(root, pending, target, context, reader, identity)
        expected = owner.serialized_bytes(owner._native_generic_projection(attempt, pending))
        pending_path = Path(root / pending["resume_state_paths"]["timestamped"])
        expected_path = pending_path.with_name(pending_path.stem + ".projection-generic-" + hashlib.sha256(expected).hexdigest() + ".json")
        return path == expected_path and raw == expected
    completion = path.name.endswith(".completion.json")
    if completion:
        path = owner._native_owner_path(root, path, target, "completion")
        archive = path.with_name(path.name.removesuffix(".completion.json") + ".json")
        archive = owner._native_owner_path(root, archive, target, "archive")
        state = _native_json(_native_file(archive))
    elif path.name == owner.LATEST_FILENAME:
        path = owner._native_owner_path(root, path, target, "latest")
        state = _native_json(_native_file(path))
    else:
        # No failure, temporary, unknown or foreign role is exempted.
        path = owner._native_owner_path(root, path, target, "archive")
        state = _native_json(_native_file(path))
    publication = state.get("publication") if type(state) is dict else None
    if type(publication) is not dict:
        return False
    if "accepted_outputs" not in publication:
        if completion or path.name == owner.LATEST_FILENAME:
            return False
        owner._native_pending_attempt(root, state, target, context, reader, identity)
        return _native_file(path) == owner.serialized_bytes(state)
    resolved, verified = owner._verify_archived_native_state(root, state, target, reader)
    if (resolved.context_json != context.context_json or not strict_json_equal(verified["execution_identity"], identity)):
        return False
    if completion:
        archive, raw = owner._native_checkpoint_bytes(root, state, target)
        expected = {"checkpoint_id": state["checkpoint_id"], "archive_sha256": hashlib.sha256(raw).hexdigest(),
            "execution_identity": identity, "outputs": verified["accepted_outputs"]}
        return _native_file(path) == owner.serialized_bytes(expected)
    return _native_file(path) == owner.serialized_bytes(state)


def _native_verify_live_state(root, data, context, reader, identity=None):
    from automation.orchestration.aios_repo_state_evidence import parse_git_status_z
    expected_raw = base64.b64decode(data["status"]["after"]["raw_base64"], validate=True)
    expected = parse_git_status_z(expected_raw)
    current = parse_git_status_z(_native_collect_status(root))
    branch = _native_json(data["request_json"])["repository_identity"]["branch"]
    expected_entries = _native_status_entries(expected, branch)
    current_entries = _native_status_entries(current, branch)
    if current["branch_line"] != expected["branch_line"]:
        raise ValueError("native_current_status_header_changed")
    # Every additional/changed endpoint must be one exact verified controller
    # projection. Renames/copies are never controller output operations.
    for relative in expected_entries.keys() | current_entries.keys():
        prior = expected_entries.get(relative)
        current_entry = current_entries.get(relative)
        if strict_json_equal(prior, current_entry):
            continue
        if any(entry is not None and "source_path" in entry for entry in (prior, current_entry)):
            raise ValueError("native_current_status_foreign_delta")
        old_code = prior["git_code"] if prior is not None else "  "
        new_code = current_entry["git_code"] if current_entry is not None else "  "
        if new_code == "??":
            permitted_code = prior is None
        else:
            permitted_code = old_code != "??" and old_code[0] == new_code[0] and new_code[1] in {" ", "M"}
        if not permitted_code or not _native_status_owned_delta(root, relative, context, reader, data, identity):
            raise ValueError("native_current_status_foreign_delta")
    request = _native_json(data["request_json"])
    for relative, expected_hash in data["after_manifest"].items():
        path = _native_nonprivate_path(str(root / relative), anchor=root)
        actual = hashlib.sha256(_native_file(path)).hexdigest() if path.is_file() else None
        if actual != expected_hash:
            if relative in request["allowed_paths"] or not _native_status_owned_delta(root, relative, context, reader, data, identity):
                raise ValueError("native_current_after_manifest_changed")
    _native_repository_identity(root, data)


if __name__ == "__main__":
    raise SystemExit(main())
