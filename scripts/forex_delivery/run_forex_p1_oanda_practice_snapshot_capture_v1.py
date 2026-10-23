#!/usr/bin/env python3
"""Owner-local, one-shot OANDA Practice snapshot handoff."""
from __future__ import annotations
import argparse, json, os, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from automation.forex_engine.forex_p1_oanda_practice_snapshot_capture_v1 import (build_capture_state, extract_sanitized_price_snapshot, open_session_through_canonical_controller, prepare_session_open_request, render_owner_report, resolve_canonical_practice_transport, stable_json, validate_practice_runtime_configuration, validate_sanitized_snapshot)

SNAPSHOT_DEFAULT = ".aios/runtime/forex_market_snapshots/EUR_USD_latest.json"
SESSION = ROOT / ".aios/runtime/forex_p1_supervised_paper_sessions/active.json"
STATE = ROOT / "Reports/forex_delivery/AIOS_FOREX_P1_OANDA_PRACTICE_SNAPSHOT_CAPTURE_V1_STATE.json"
MAX_BYTES = 1_000_000

def local_path(value: str, *, must_exist=False) -> Path:
    path = ROOT / value; resolved = path.resolve(strict=must_exist)
    if ROOT != resolved and ROOT not in resolved.parents: raise ValueError("repository_local_path_required")
    if must_exist and (path.is_symlink() or resolved.stat().st_size > MAX_BYTES): raise ValueError("unsafe_input_path")
    return resolved

def load(value: str) -> dict:
    result=json.loads(local_path(value, must_exist=True).read_text(encoding="utf-8"))
    if not isinstance(result, dict): raise ValueError("object_required")
    return result

def handoff() -> str:
    return r'''Set-Location 'C:\Dev\Ai.Os'
python --version
if ([string]::IsNullOrWhiteSpace($env:OANDA_API_TOKEN) -and -not [string]::IsNullOrWhiteSpace($env:OANDA_DEMO_ACCESS_TOKEN)) { $env:OANDA_API_TOKEN = $env:OANDA_DEMO_ACCESS_TOKEN }
if ([string]::IsNullOrWhiteSpace($env:OANDA_ACCOUNT_ID) -and -not [string]::IsNullOrWhiteSpace($env:OANDA_DEMO_ACCOUNT_ID)) { $env:OANDA_ACCOUNT_ID = $env:OANDA_DEMO_ACCOUNT_ID }
$HasToken = -not [string]::IsNullOrWhiteSpace($env:OANDA_API_TOKEN)
$HasAccount = -not [string]::IsNullOrWhiteSpace($env:OANDA_ACCOUNT_ID)
Write-Host "OANDA demo/practice token present: $HasToken"
Write-Host "OANDA demo/practice account present: $HasAccount"
if (-not ($HasToken -and $HasAccount)) { throw 'Required runtime environment variables are missing.' }
python scripts/forex_delivery/run_forex_p1_oanda_practice_snapshot_capture_v1.py preflight
$Candidate = Get-ChildItem '.aios/runtime/forex_candidates' -Filter '*.json' -File -ErrorAction SilentlyContinue | Where-Object { $j = Get-Content $_.FullName -Raw | ConvertFrom-Json; $j.status -eq 'PAPER_ELIGIBLE' -and $j.instrument -eq 'EUR_USD' -and $j.current -eq $true -and $j.sanitized -eq $true } | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
if ($Candidate) {
  python scripts/forex_delivery/run_forex_p1_oanda_practice_snapshot_capture_v1.py capture-and-open --owner-local-runtime --environment practice --instrument EUR_USD --snapshot-output .aios/runtime/forex_market_snapshots/EUR_USD_latest.json --candidate $Candidate.FullName --reviewer 'Human Owner Anthony' --owner-supervision-confirmed
} else {
  python scripts/forex_delivery/run_forex_p1_oanda_practice_snapshot_capture_v1.py capture --owner-local-runtime --environment practice --instrument EUR_USD --snapshot-output .aios/runtime/forex_market_snapshots/EUR_USD_latest.json
}
Write-Host 'Snapshot: C:\Dev\Ai.Os\.aios\runtime\forex_market_snapshots\EUR_USD_latest.json'
python scripts/forex_delivery/run_forex_p1_oanda_practice_snapshot_capture_v1.py status
Write-Host 'No OANDA order is placed.'
'''

def parser():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="command")
    for name in ("preflight","status","report","print-owner-handoff"): sub.add_parser(name)
    val=sub.add_parser("validate-snapshot"); val.add_argument("snapshot")
    for name in ("capture","capture-and-open"):
        c=sub.add_parser(name); c.add_argument("--owner-local-runtime",action="store_true"); c.add_argument("--environment",required=True); c.add_argument("--instrument",required=True); c.add_argument("--snapshot-output",required=True)
        if name == "capture-and-open": c.add_argument("--candidate",required=True); c.add_argument("--reviewer",required=True); c.add_argument("--owner-supervision-confirmed",action="store_true")
    return p

def main(argv=None):
    args=parser().parse_args(argv); command=args.command or "preflight"
    if command=="print-owner-handoff": print(handoff(),end=""); return 0
    if command=="status": print(stable_json({"snapshot_path": SNAPSHOT_DEFAULT,"paper_session_status":"ACTIVE" if SESSION.exists() else "NO_ACTIVE_SESSION","no_oanda_order_placed":True}),end=""); return 0
    if command=="report": print(render_owner_report(json.loads(STATE.read_text())),end=""); return 0
    if command=="validate-snapshot": print(stable_json(validate_sanitized_snapshot(load(args.snapshot))),end=""); return 0
    if command=="preflight": print(stable_json({"status":"PRACTICE_READ_ONLY_PREFLIGHT_READY","network_call_performed":False,"canonical_transport":f"{resolve_canonical_practice_transport().__module__}.{resolve_canonical_practice_transport().__name__}","capture_requires_owner_local_runtime":True,"no_oanda_order_placed":True}),end=""); return 0
    validate_practice_runtime_configuration(environment=args.environment,instrument=args.instrument,owner_local_runtime=args.owner_local_runtime)
    token=os.environ.get("OANDA_API_TOKEN") or os.environ.get("OANDA_DEMO_ACCESS_TOKEN")
    account=os.environ.get("OANDA_ACCOUNT_ID") or os.environ.get("OANDA_DEMO_ACCOUNT_ID")
    if not token or not account: raise ValueError("runtime_credentials_missing")
    client=resolve_canonical_practice_transport()(api_token=token,account_id=account,environment="practice")
    raw=client.pricing((args.instrument,))
    snapshot=extract_sanitized_price_snapshot(raw,instrument=args.instrument,broker_call_performed=True,credentials_loaded_runtime_only=True)
    output=local_path(args.snapshot_output); output.parent.mkdir(parents=True,exist_ok=True); output.write_text(stable_json(snapshot),encoding="utf-8")
    status="NO_PAPER_TRADE_CANDIDATE"
    if command=="capture-and-open":
        if not args.owner_supervision_confirmed: raise ValueError("owner_supervision_confirmation_required")
        request=prepare_session_open_request(load(args.candidate),snapshot,args.reviewer,datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),SESSION)
        open_session_through_canonical_controller(request); status="PAPER_SESSION_OPENED_RUNTIME_ONLY"
    print(stable_json({"status":status,"snapshot_path":str(output.relative_to(ROOT)),"broker_call_performed":True,"broker_write_performed":False,"p1_credit":0}),end=""); return 0
if __name__=="__main__": raise SystemExit(main())
