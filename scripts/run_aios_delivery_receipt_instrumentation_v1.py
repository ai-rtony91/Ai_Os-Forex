#!/usr/bin/env python3
"""Local-only command line interface for AIOS delivery receipts."""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from automation.orchestration.aios_delivery_receipt_instrumentation_v1 import (  # noqa: E402
    block_task_timing, complete_task_timing, normalize_github_event_receipt,
    append_velocity_event, merge_codex_delivery_metadata, rebuild_codex_delivery_metadata,
    rebuild_github_pr_delivery_metadata, render_owner_report, stable_json,
    start_task_timing, task_receipt_velocity_events, validate_task_receipt,
)
MAX_BYTES = 1_000_000
RUNTIME = ROOT / ".aios/runtime/engineering_timing"
TERMINALS = RUNTIME / "terminal"
CODEX_METADATA = ROOT / "Reports/orchestration/AIOS_CODEX_TASK_DELIVERY_METADATA_V1.json"
VELOCITY_LOG = ROOT / "Reports/orchestration/AIOS_ENGINEERING_VELOCITY_EVENT_LOG_V1.jsonl"

def load_json(path: Path, *, github_event: bool = False):
    if path.is_symlink(): raise ValueError("symlink input rejected")
    resolved = path.resolve()
    if not github_event:
        try: resolved.relative_to(ROOT)
        except ValueError as exc: raise ValueError("input outside repository") from exc
    if path.stat().st_size > MAX_BYTES: raise ValueError("oversized input rejected")
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out: raise ValueError(f"duplicate JSON key: {key}")
            out[key] = value
        return out
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"non-finite JSON: {value}")))

def git(*args: str) -> str:
    allowed = {("rev-parse", "HEAD"), ("branch", "--show-current"), ("rev-parse", "--show-toplevel")}
    if args not in allowed: raise ValueError("Git command is not approved read-only inspection")
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()

def parser():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="command", required=True)
    for name in ("task-start","task-complete","task-blocked"):
        q=sub.add_parser(name); q.add_argument("--task-id",required=True); q.add_argument("--packet-id",required=True); q.add_argument("--timestamp",required=True)
    sub.choices["task-start"].add_argument("--lane",required=True); sub.choices["task-start"].add_argument("--branch"); sub.choices["task-start"].add_argument("--starting-head")
    sub.choices["task-blocked"].add_argument("--reason",action="append",required=True)
    for name in ("task-complete", "task-blocked"):
        q=sub.choices[name]; q.add_argument("--metadata-output",default=str(CODEX_METADATA.relative_to(ROOT))); q.add_argument("--event-log",default=str(VELOCITY_LOG.relative_to(ROOT)))
    q=sub.choices["task-complete"]
    q.add_argument("--validation-status", choices=("PASS", "FAILED", "UNAVAILABLE"), default="UNAVAILABLE")
    for field in ("files-changed-count", "lines-added", "lines-deleted", "tests-run", "tests-passed", "tests-failed", "tests-skipped", "blockers-found", "blockers-closed"):
        q.add_argument(f"--{field}", type=int, default=0)
    q=sub.add_parser("github-event"); q.add_argument("--event-path"); q.add_argument("--output",required=True)
    q=sub.add_parser("ingest-github-receipts"); q.add_argument("paths",nargs="+"); q.add_argument("--output",required=True)
    q=sub.add_parser("rebuild-metadata"); q.add_argument("paths",nargs="+"); q.add_argument("--output",required=True)
    q=sub.add_parser("validate"); q.add_argument("path")
    q=sub.add_parser("report"); q.add_argument("state"); q.add_argument("--output",required=True)
    return p

def output_path(value: str) -> Path:
    path=(ROOT/value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
    try: path.relative_to(ROOT)
    except ValueError as exc: raise ValueError("output outside repository") from exc
    if path.exists() and path.is_symlink(): raise ValueError("symlink output rejected")
    path.parent.mkdir(parents=True,exist_ok=True); return path

def persist_terminal(value, metadata_value: str, event_value: str):
    metadata_path, event_path = output_path(metadata_value), output_path(event_value)
    existing = load_json(metadata_path) if metadata_path.exists() else []
    if not isinstance(existing, list): raise ValueError("Codex metadata must be a JSON array")
    rebuilt = merge_codex_delivery_metadata(existing, value)
    # Validate all event conflicts before changing tracked metadata.
    current_lines = event_path.read_text(encoding="utf-8").splitlines() if event_path.exists() else []
    current = {json.loads(line).get("event_id"): json.loads(line) for line in current_lines if line.strip()}
    for event in task_receipt_velocity_events(value):
        if event["event_id"] in current and stable_json(current[event["event_id"]]) != stable_json(event):
            raise ValueError(f"conflicting velocity event: {event['event_id']}")
    metadata_path.write_text(stable_json(rebuilt), encoding="utf-8")
    for event in task_receipt_velocity_events(value): append_velocity_event(event_path, event)

def main(argv=None):
    a=parser().parse_args(argv)
    if a.command=="task-start": value=start_task_timing(RUNTIME,task_id=a.task_id,packet_id=a.packet_id,lane=a.lane,branch=a.branch or git("branch","--show-current"),starting_head=a.starting_head or git("rev-parse","HEAD"),started_utc=a.timestamp)
    elif a.command=="task-complete":
        head=git("rev-parse","HEAD"); safe_name=re.sub("[^A-Za-z0-9_.-]", "-", a.packet_id); marker=RUNTIME/f"{safe_name}.json"; start_head=load_json(marker).get("starting_head") if marker.exists() else None
        value=complete_task_timing(RUNTIME,TERMINALS,task_id=a.task_id,packet_id=a.packet_id,completed_utc=a.timestamp,ending_head=head,
            validation_status=a.validation_status,files_changed_count=a.files_changed_count,lines_added=a.lines_added,lines_deleted=a.lines_deleted,
            tests_run=a.tests_run,tests_passed=a.tests_passed,tests_failed=a.tests_failed,tests_skipped=a.tests_skipped,
            blockers_found=a.blockers_found,blockers_closed=a.blockers_closed,commit_created=bool(start_head and start_head != head),commit_sha=head if start_head and start_head != head else None)
        persist_terminal(value,a.metadata_output,a.event_log)
    elif a.command=="task-blocked":
        value=block_task_timing(RUNTIME,TERMINALS,task_id=a.task_id,packet_id=a.packet_id,blocked_utc=a.timestamp,blocker_reasons=a.reason)
        persist_terminal(value,a.metadata_output,a.event_log)
    elif a.command=="github-event":
        event=Path(a.event_path or os.environ.get("GITHUB_EVENT_PATH", "")); value=normalize_github_event_receipt(load_json(event,github_event=bool(os.environ.get("GITHUB_ACTIONS"))))
        if value is None: return 0
        output_path(a.output).write_text(stable_json(value),encoding="utf-8")
    elif a.command=="ingest-github-receipts": value=rebuild_github_pr_delivery_metadata([load_json(Path(p)) for p in a.paths]); output_path(a.output).write_text(stable_json(value),encoding="utf-8")
    elif a.command=="rebuild-metadata": value=rebuild_codex_delivery_metadata([load_json(Path(p)) for p in a.paths]); output_path(a.output).write_text(stable_json(value),encoding="utf-8")
    elif a.command=="validate": value=validate_task_receipt(load_json(Path(a.path)))
    else: value=render_owner_report(load_json(Path(a.state))); output_path(a.output).write_text(value,encoding="utf-8")
    print(stable_json(value),end=""); return 0
if __name__=="__main__": raise SystemExit(main())
