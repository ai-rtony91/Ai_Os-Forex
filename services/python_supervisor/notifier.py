"""AI_OS local SOS notifier.

Default channel is file only. Email, push, and Telegram live channels are
intentionally disabled until Anthony supplies local credentials and approves
that gate.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import re
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DISPLAY_ALERT_STATUSES = {"BLOCKED", "NEEDS_APPROVAL"}
FILE_NOTIFY_STATUSES = {"BLOCKED"}
SOS_WAKE_STATUSES = {"BLOCKED"}
TELEGRAM_ENV_VARS = ("AIOS_TG_BOT_TOKEN", "AIOS_TG_CHAT_ID")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def status_from_state(state: dict[str, Any]) -> str:
    raw = (
        state.get("night_supervisor_status")
        or state.get("supervisor_status")
        or state.get("status")
        or "UNKNOWN"
    )
    status = str(raw).upper()
    canonical = state.get('canonical_resume', {})
    if 'canonical_resume' in state:
        if status in DISPLAY_ALERT_STATUSES:
            return status
        if canonical.get('integrity') == 'VERIFIED' and canonical.get('freshness', {}).get('current') is True:
            if canonical.get('result') in {'BLOCKED', 'FAILED_OR_BLOCKED'}:
                return 'BLOCKED'
            if canonical.get('result') == 'NEEDS_APPROVAL':
                return 'NEEDS_APPROVAL'
            return 'READY' if canonical.get('resume_ready') is True else 'UNKNOWN'
        return 'UNKNOWN'
    return status


def display_alert_required(status: str) -> bool:
    return status in DISPLAY_ALERT_STATUSES


def sos_wake_required(status: str) -> bool:
    return status in SOS_WAKE_STATUSES


def wake_class(status: str) -> str:
    if sos_wake_required(status):
        return "SOS"
    if display_alert_required(status):
        return "REVIEW_ONLY"
    return "NO_WAKE"


def notification_key(state: dict[str, Any]) -> str:
    status = status_from_state(state)
    generated = str(state.get("generated_at") or "")
    summary = str(state.get("plain_summary") or "")
    return f"{status}|{generated}|{summary}"


def public_reader(root: Path):
    path = root / 'automation/orchestration/dashboard/aios_resume_visibility.py'
    expected = '9200073c227f004afca1703e209b9ee3529eb399dc1aaef07268df6e939625c3'
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('canonical_public_reader_source_changed')
    spec = importlib.util.spec_from_file_location('notifier_public_resume', path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module

def canonical_resume(root: Path, *, expected_request=None, admitted_context=None,
                     native_admission_reader=None) -> dict[str, Any]:
    return public_reader(root).read_public_resume(root, expected_request=expected_request,
        admitted_context=admitted_context, native_admission_reader=native_admission_reader)

def preview_selected_event(root: Path, event: dict[str, Any], *, expected_request=None,
                           admitted_context=None, native_admission_reader=None) -> dict[str, Any]:
    """Selected trigger diagnostics stay separate from verified checkpoint truth."""
    fields = {'schema', 'phase', 'status', 'task_id', 'attempt_id', 'attempt_number',
              'transport_request_sha256', 'prompt_sha256', 'cause_code', 'requirement_request_sha256', 'claim_sha256'}
    if type(event) is not dict or set(event) != fields or event['schema'] != 'AIOS_SELECTED_CYCLE_EVENT.v1':
        raise ValueError('selected_event_shape_invalid')
    if event['phase'] not in {'TRANSPORT', 'POST_PUBLICATION'}:
        raise ValueError('selected_event_phase_invalid')
    statuses = {'DRY_RUN', 'COMPLETE', 'APPROVAL_REQUIRED', 'DEFERRED', 'REQUEST_REJECTED',
                'EXECUTED_AWAITING_VALIDATION', 'EXECUTION_FAILED', 'SAFETY_INTEGRITY_BLOCK',
                'FINALIZATION_RECONCILIATION_REQUIRED', 'STOP_FLAG', 'INTEGRITY_BLOCKED',
                'CODEX_RUNTIME_UNAVAILABLE'}
    if event['status'] not in statuses or event['cause_code'] not in statuses | {
            'ValueError', 'OSError', 'RuntimeError', 'PromptValidationError', 'KeyError', 'TypeError'}:
        raise ValueError('selected_event_public_code_required')
    for field in ('task_id', 'attempt_id'):
        if type(event[field]) is not str or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', event[field]):
            raise ValueError('selected_event_identity_invalid')
    if type(event['attempt_number']) is not int or event['attempt_number'] < 0:
        raise ValueError('selected_event_attempt_invalid')
    native = event['phase'] == 'POST_PUBLICATION'
    for field in ('transport_request_sha256', 'prompt_sha256', 'requirement_request_sha256', 'claim_sha256'):
        pattern = r'[0-9a-f]{64}' if native or field in {'transport_request_sha256', 'prompt_sha256'} else ''
        if type(event[field]) is not str or not re.fullmatch(pattern, event[field]):
            raise ValueError('selected_event_digest_invalid')
    if native:
        from automation.orchestration.relay import aios_self_consuming_codex_cycle_v1 as cycle
        data = cycle._verify_native_context(root, admitted_context, native_admission_reader, live=False)
        bound = cycle._native_json(data['request_json'])
        if not cycle.strict_json_equal(cycle._native_request_dict(expected_request),
                                       cycle._native_request_dict(admitted_context.request)):
            raise ValueError('selected_event_native_request_mismatch')
        expected = {field: bound[field] for field in ('task_id', 'attempt_id', 'attempt_number', 'prompt_sha256')}
        expected.update(transport_request_sha256=cycle._native_hash(bound),
                        requirement_request_sha256=expected_request.request_sha256,
                        claim_sha256=expected_request.claim_sha256)
        if any(not cycle.strict_json_equal(event[field], value) for field, value in expected.items()):
            raise ValueError('selected_event_native_identity_mismatch')
    elif any(value is not None for value in (expected_request, admitted_context, native_admission_reader)):
        raise ValueError('selected_event_unexpected_native_context')
    canonical = canonical_resume(root, expected_request=expected_request,
        admitted_context=admitted_context, native_admission_reader=native_admission_reader)
    if native and canonical.get('integrity') == 'VERIFIED' and canonical.get('task_id') != event['task_id']:
        canonical = {'integrity': 'UNKNOWN', 'result': 'UNKNOWN', 'reason_code': 'selected_event_task_mismatch',
                     'freshness': {'current': False}}
    # A reader exception may resemble a public ID without being a known code.
    # Bound only this new selected-event projection; retain standalone policy.
    public_reasons = {'UNKNOWN', 'verification_unavailable', 'review_required',
        'canonical_selected_owner_mismatch', 'native_admission_reader_required',
        'native_accepted_requirement_unavailable', 'canonical_public_contract_invalid',
        'acceptance_time_in_future', 'selected_event_task_mismatch'}
    reason = canonical.get('reason_code')
    canonical = {**canonical, 'reason_code': reason if type(reason) is str and reason in public_reasons
                 else 'verification_unavailable'}
    state = {'status': 'UNKNOWN', 'canonical_resume': canonical, 'selected_event': dict(event),
             'plain_summary': 'Selected cycle ' + event['status'] + '; checkpoint evidence is reported separately.',
             'must_see': ['Transport/process status is not task acceptance, a live worker or notification authority.'],
             'next_safe_action': canonical.get('next_safe_action', 'Review checkpoint evidence before continuation.')}
    # No selected output owner exists. Preview does not read a dedupe store,
    # acquire/create its lock, save a receipt or call a dispatcher.
    # The selected preview has no application or delivery path.
    outcome = notify_file(root, state, apply=False, read_receipt=lambda: {})
    verified = canonical.get('integrity') == 'VERIFIED' and canonical.get('freshness', {}).get('current') is True
    selected_verified = native and verified
    observed_status = status_from_state({'canonical_resume': canonical})
    # A transport trigger lacks the native request/attempt/claim association,
    # even when a separate checkpoint is verified. Preserve a genuine canonical
    # stop as its own observation, never as selected task acceptance.
    observation = {field: canonical.get(field) for field in (
        'integrity', 'checkpoint_id', 'task_id', 'result', 'reason_code', 'accepted_at')}
    observation.update(current=verified, relation='INDEPENDENT_CHECKPOINT_EVIDENCE', execution_allowed=False)
    return {**outcome, 'effect_scope': 'PREVIEW_ONLY', 'delivery_accepted': False,
            'canonical_integrity': 'VERIFIED' if selected_verified else 'UNKNOWN', 'canonical_current': selected_verified,
            'canonical_reason_code': canonical.get('reason_code', 'UNKNOWN') if native else 'selected_native_admission_unavailable',
            'canonical_checkpoint_id': canonical.get('checkpoint_id') if selected_verified else None,
            'checkpoint_observation': observation,
            'protected_canonical_status': observed_status if observed_status in DISPLAY_ALERT_STATUSES else 'UNKNOWN',
            'selected_event': dict(event),
            'identity_relation': ('CANONICAL_NATIVE_VERIFIED' if verified else 'UNKNOWN') if native else 'TRANSPORT_TRIGGER_ONLY',
            'display_alert': display_alert_required(status_from_state(state)),
            'wake_class': wake_class(status_from_state(state))}

def notify_file(root: Path, state: dict[str, Any], *, apply=False, read_receipt=None,
                save_receipt=None, dispatch=None, lock=None) -> dict[str, Any]:
    """Selected-event preview only; this API never applies or calls an effect owner."""
    if type(apply) is not bool or apply is not False:
        raise ValueError("PREVIEW_APPLY_FORBIDDEN")
    status = status_from_state(state)
    outcome = ("DRY_RUN_WOULD_NOTIFY" if status in FILE_NOTIFY_STATUSES else
               "DISPLAY_ALERT_ONLY" if display_alert_required(status) else "NO_BLOCKER")
    return {"status": outcome, "delivery_accepted": False}

def render_sos(state: dict[str, Any]) -> str:
    status = status_from_state(state)
    summary = str(state.get("plain_summary") or "No summary available.")
    approval_count = state.get("approval_needed_count", "UNKNOWN")
    next_action = str(state.get("next_safe_action") or "Review bridge state before taking action.")
    must_see = state.get("must_see") or []
    if not isinstance(must_see, list):
        must_see = [must_see]

    lines = [
        f"# AI_OS SOS - {status}",
        "",
        f"- Generated: {utc_now()}",
        f"- Bridge generated_at: {state.get('generated_at', 'UNKNOWN')}",
        "- display_alert: true",
        "- sos_wake_required: true",
        "- wake_class: SOS",
        f"- Plain summary: {summary}",
        f"- Waiting approvals: {approval_count}",
        "- Must see:",
    ]
    if must_see:
        lines.extend(f"  - {item}" for item in must_see)
    else:
        lines.append("  - No must-see items reported.")
    lines.append(f"- Next safe action: {next_action}")
    lines.append("")
    lines.append("Channel: file")
    lines.append("Secrets used: none")
    return "\n".join(lines) + "\n"


def telegram_env_presence() -> dict[str, bool]:
    return {name: name in os.environ for name in TELEGRAM_ENV_VARS}


def telegram_config_status() -> str:
    presence = telegram_env_presence()
    if all(presence.values()):
        return "configured"
    return "missing"


def render_telegram_sos_preview(state: dict[str, Any]) -> str:
    status = status_from_state(state)
    summary = str(state.get("plain_summary") or "No summary available.")
    next_action = str(state.get("next_safe_action") or "Review bridge state before taking action.")
    generated = utc_now()
    return "\n".join(
        [
            "#AIOS_SOS AI_OS BLOCKED",
            "severity=CRITICAL",
            f"status={status}",
            f"generated_utc={generated}",
            f"bridge_generated_at={state.get('generated_at', 'UNKNOWN')}",
            f"summary={summary}",
            f"next_safe_action={next_action}",
            "human_action=Wake and inspect AI_OS dashboard/SOS outbox.",
        ]
    )


def report_telegram_dry_run(state: dict[str, Any]) -> int:
    status = status_from_state(state)
    config_status = telegram_config_status()
    print("STATUS=DRY_RUN_TELEGRAM_SCAFFOLD")
    print(f"BRIDGE_STATUS={status}")
    print(f"TELEGRAM_CONFIG={config_status}")
    for name, present in telegram_env_presence().items():
        value_status = "present" if present else "missing"
        print(f"{name}={value_status}")
    print("LIVE_SEND=BLOCKED")
    print("SECRET_VALUES_PRINTED=NO")
    print(f"display_alert={str(display_alert_required(status)).lower()}")
    print(f"sos_wake_required={str(sos_wake_required(status)).lower()}")

    if not sos_wake_required(status):
        print("WAKE_CLASS=NO_WAKE")
        print("REASON=non-SOS status must not wake the Human Owner")
        return 0

    print("WAKE_CLASS=SOS")
    print("MESSAGE_PREVIEW_BEGIN")
    print(render_telegram_sos_preview(state))
    print("MESSAGE_PREVIEW_END")
    return 0


def write_file_channel(root: Path, state: dict[str, Any]) -> Path:
    dispatcher = root / "automation" / "orchestration" / "notifications" / "Send-AiOsNotification.ps1"
    message = render_sos(state)
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(dispatcher),
            "-Message",
            message,
            "-Severity",
            "CRITICAL",
            "-Subject",
            "AI_OS BLOCKER",
            "-Apply",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "SOS dispatcher failed "
            f"exit={completed.returncode} stdout={completed.stdout.strip()} stderr={completed.stderr.strip()}"
        )
    for line in completed.stdout.splitlines():
        if line.startswith("OUTBOX_FILE="):
            return Path(line.split("=", 1)[1])
    raise RuntimeError(f"SOS dispatcher did not report OUTBOX_FILE: {completed.stdout.strip()}")


def main() -> int:
    parser = argparse.ArgumentParser(description="AI_OS file-channel SOS notifier")
    parser.add_argument("--channel", default="file", choices=["file", "email", "push", "telegram"])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--state", default="telemetry/night_supervisor/AUTONOMY_BRIDGE_STATE.json")
    args = parser.parse_args()

    root = repo_root()
    state_path = root / args.state
    last_path = root / "telemetry" / "night_supervisor" / "last_notified.json"

    if args.channel in {"email", "push"}:
        print("STATUS=BLOCKED")
        print("REASON=non-file channels require Anthony-managed environment secrets and are disabled")
        return 2

    if not state_path.exists():
        print("STATUS=NO_STATE")
        print(f"STATE_PATH={state_path}")
        return 0

    state = read_json(state_path)
    status = status_from_state(state)
    key = notification_key(state)
    previous = read_json(last_path) if last_path.exists() else {}

    if args.channel == "telegram":
        if args.apply:
            print("STATUS=BLOCKED")
            print("BRIDGE_STATUS=" + status)
            print("CHANNEL=telegram")
            print("LIVE_SEND=BLOCKED")
            print("REASON=Telegram live send requires a separate explicit approved live-send flag")
            print("SECRET_VALUES_PRINTED=NO")
            return 2
        return report_telegram_dry_run(state)

    if status not in FILE_NOTIFY_STATUSES:
        if args.apply:
            write_json(last_path, {"last_status": status, "last_key": key, "updated_at": utc_now()})
        print("STATUS=DISPLAY_ALERT_ONLY" if display_alert_required(status) else "STATUS=NO_BLOCKER")
        print(f"BRIDGE_STATUS={status}")
        print(f"display_alert={str(display_alert_required(status)).lower()}")
        print(f"sos_wake_required={str(sos_wake_required(status)).lower()}")
        print(f"WAKE_CLASS={wake_class(status)}")
        return 0

    if previous.get("last_key") == key:
        print("STATUS=SUPPRESSED")
        print(f"BRIDGE_STATUS={status}")
        print("REASON=already notified for this state")
        return 0

    if not args.apply:
        print("STATUS=DRY_RUN_WOULD_NOTIFY")
        print(f"BRIDGE_STATUS={status}")
        print("CHANNEL=file")
        print("display_alert=true")
        print("sos_wake_required=true")
        print("WAKE_CLASS=SOS")
        return 0

    target = write_file_channel(root, state)
    write_json(last_path, {"last_status": status, "last_key": key, "updated_at": utc_now(), "channel": "file"})
    print("STATUS=NOTIFIED")
    print(f"BRIDGE_STATUS={status}")
    print(f"OUTBOX_FILE={target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
