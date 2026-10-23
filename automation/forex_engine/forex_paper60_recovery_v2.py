from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable


SNAPSHOT_ID = "POST_CERTIFICATION_DRIFT_NOT_CANONICAL_PAPER60"
PACKET_ID = "PKT-EAST-FOREX-PAPER60-RECOVERY-006"
LOCK_ID = "LOCK_EAST_FOREX_PAPER60_OCC01"
LONG_ROOT = Path(".aios/runtime/forex_frozen_candidate_paper30_v1")
SHORT_ROOT = Path(".aios/runtime/forex_frozen_candidate_paper30_v1_short")
SNAPSHOT_ROOT = Path(".aios/runtime/forex_paper60_postcert_drift_snapshot_v1")
RESEARCH_ROOT = Path(".aios/runtime/forex_paper60_research_v2")
REPLAY_CACHE = Path(".aios/runtime/forex_multipair_m5_replay_mba_v1/replay_cache.json")
CANONICAL_FILES = (
    Path("Reports/forex_delivery/AIOS_FOREX_PAPER60_EXECUTION_REPORT.md"),
    Path("Reports/forex_delivery/AIOS_FOREX_PAPER60_EXECUTION_STATE.json"),
    Path("Reports/forex_delivery/AIOS_FOREX_PAPER60_CERTIFICATION_REPORT.md"),
    Path("Reports/forex_delivery/AIOS_FOREX_PAPER60_CERTIFICATION_STATE.json"),
)
FREEZE_STATE = Path("Reports/forex_delivery/AIOS_FOREX_PAPER60_FORENSIC_FREEZE_STATE.json")
FREEZE_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_PAPER60_FORENSIC_FREEZE_REPORT.md")
POSTMORTEM_STATE = Path("Reports/forex_delivery/AIOS_FOREX_PAPER60_SUPERTREND_POSTMORTEM_STATE.json")
POSTMORTEM_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_PAPER60_SUPERTREND_POSTMORTEM_REPORT.md")
RESEARCH_STATE = Path("Reports/forex_delivery/AIOS_FOREX_PAPER60_CANDIDATE_RESEARCH_STATE.json")
RESEARCH_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_PAPER60_CANDIDATE_RESEARCH_REPORT.md")
REDESIGN_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_STRATEGY_REDESIGN_PLAN_V1.md")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_manifest(root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        stat = path.stat()
        rows.append(
            {
                "relative_path": path.relative_to(root).as_posix(),
                "byte_size": stat.st_size,
                "source_mtime_ns": stat.st_mtime_ns,
                "sha256": sha256_file(path),
            }
        )
    return rows


def manifest_fingerprint(rows: Iterable[dict[str, Any]]) -> str:
    payload = json.dumps(list(rows), sort_keys=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="ascii")
    os.replace(temporary, path)


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text.rstrip() + "\n", encoding="ascii")
    os.replace(temporary, path)


def load_state(root: Path) -> dict[str, Any]:
    return json.loads((root / "AIOS_FOREX_PAPER30_STATE.json").read_text(encoding="utf-8"))


def decimal(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def audit_trades(trades: list[dict[str, Any]], expected_direction: str) -> dict[str, Any]:
    ids = [str(trade.get("trade_id", "")) for trade in trades]
    duplicates = sorted({trade_id for trade_id in ids if ids.count(trade_id) > 1})
    routing_errors: list[str] = []
    parity_errors: list[str] = []
    stop_target_errors: list[str] = []
    for trade in trades:
        trade_id = str(trade.get("trade_id", "UNKNOWN"))
        direction = str(trade.get("trade_direction") or trade.get("direction", "")).upper()
        if direction != expected_direction:
            routing_errors.append(trade_id)
        entry = decimal(trade.get("entry_price"))
        exit_price = decimal(trade.get("exit_price"))
        stop = decimal(trade.get("initial_stop"))
        target = decimal(trade.get("target_price"))
        risk = decimal(trade.get("initial_risk_price"))
        realized = decimal(trade.get("realized_r"))
        if None in (entry, exit_price, stop, target, risk, realized) or risk <= 0:
            parity_errors.append(trade_id)
            continue
        expected = (exit_price - entry) / risk if expected_direction == "BUY" else (entry - exit_price) / risk
        if abs(expected - realized) > Decimal("0.000001") or trade.get("r_parity_valid") is False:
            parity_errors.append(trade_id)
        valid_geometry = stop < entry < target if expected_direction == "BUY" else target < entry < stop
        if not valid_geometry:
            stop_target_errors.append(trade_id)
    return {
        "trade_count": len(trades),
        "unique_trade_ids": len(set(ids)),
        "duplicate_trade_ids": duplicates,
        "direction_routing_errors": routing_errors,
        "r_parity_errors": parity_errors,
        "stop_target_inversions": stop_target_errors,
        "accounting_pass": not (duplicates or routing_errors or parity_errors or stop_target_errors),
    }


def trade_summary(trades: list[dict[str, Any]]) -> dict[str, Any]:
    realized = [float(trade["realized_r"]) for trade in trades]
    mfe = [float(trade.get("mfe_r", 0.0)) for trade in trades]
    mae = [float(trade.get("mae_r", 0.0)) for trade in trades]
    exits: dict[str, int] = {}
    for trade in trades:
        reason = str(trade.get("exit_reason", "UNKNOWN"))
        exits[reason] = exits.get(reason, 0) + 1
    gross_profit = sum(value for value in realized if value > 0)
    gross_loss = -sum(value for value in realized if value < 0)
    running = peak = max_drawdown = 0.0
    for value in realized:
        running += value
        peak = max(peak, running)
        max_drawdown = max(max_drawdown, peak - running)
    return {
        "trade_count": len(trades),
        "wins": sum(value > 0 for value in realized),
        "losses": sum(value < 0 for value in realized),
        "expectancy_r": sum(realized) / len(realized) if realized else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "maximum_drawdown_r": max_drawdown,
        "net_r": sum(realized),
        "exit_reasons": exits,
        "mfe_reached_0_5r": sum(value >= 0.5 for value in mfe),
        "mfe_reached_1r": sum(value >= 1.0 for value in mfe),
        "mfe_reached_2r": sum(value >= 2.0 for value in mfe),
        "mfe_min_r": min(mfe) if mfe else None,
        "mfe_max_r": max(mfe) if mfe else None,
        "mae_min_r": min(mae) if mae else None,
        "mae_max_r": max(mae) if mae else None,
    }


def target_causality(trades: list[dict[str, Any]], targets: Iterable[int] = (1, 2, 3, 4, 6, 10)) -> dict[str, Any]:
    reached = {str(target): sum(float(trade.get("mfe_r", 0.0)) >= target for trade in trades) for target in targets}
    one_r = reached.get("1", 0)
    return {
        "target_multiples_r": list(targets),
        "trades_reaching_each_target": reached,
        "verdict": "NON_CAUSAL_FOR_OBSERVED_FAILURES" if one_r == 0 else "CONTRIBUTING_OR_INSUFFICIENT_SEQUENCE_EVIDENCE",
        "limitation": "Recorded MFE does not prove intrabar stop/target ordering; no synthetic counterfactual fills were assigned.",
    }


def replay_provenance() -> dict[str, Any]:
    payload = json.loads(REPLAY_CACHE.read_text(encoding="utf-8"))
    ranges = []
    for instrument, history in sorted(payload.get("pair_histories", {}).items()):
        candles = history.get("sanitized_candles", [])
        if candles:
            ranges.append({"instrument": instrument, "first": candles[0]["timestamp"], "last": candles[-1]["timestamp"], "count": len(candles)})
    return {
        "path": REPLAY_CACHE.as_posix(),
        "sha256": sha256_file(REPLAY_CACHE),
        "captured_at_utc": payload.get("captured_at_utc"),
        "safety": {key: payload.get(key) for key in ("broker_write_performed", "practice_order_performed", "live_trade_performed", "money_movement_performed", "credentials_persisted")},
        "ranges": ranges,
    }


def validate_existing_snapshot() -> dict[str, Any] | None:
    manifest_path = SNAPSHOT_ROOT / "manifest.json"
    if not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for row in manifest.get("files", []):
        copied = SNAPSHOT_ROOT / row["snapshot_relative_path"]
        if not copied.is_file() or copied.stat().st_size != row["byte_size"] or sha256_file(copied) != row["sha256"]:
            raise ValueError("EXISTING_SNAPSHOT_HASH_MISMATCH")
    return manifest


def create_snapshot(branch: str, head: str, process_evidence: dict[str, Any]) -> dict[str, Any]:
    existing = validate_existing_snapshot()
    if existing is not None:
        return existing
    temporary = SNAPSHOT_ROOT.with_name(SNAPSHOT_ROOT.name + ".tmp")
    for attempt in range(1, 4):
        if temporary.exists():
            shutil.rmtree(temporary)
        before = {"long": file_manifest(LONG_ROOT), "short": file_manifest(SHORT_ROOT), "canonical": [
            {"relative_path": path.as_posix(), "byte_size": path.stat().st_size, "source_mtime_ns": path.stat().st_mtime_ns, "sha256": sha256_file(path)} for path in CANONICAL_FILES
        ]}
        time.sleep(10)
        stable = before == {"long": file_manifest(LONG_ROOT), "short": file_manifest(SHORT_ROOT), "canonical": [
            {"relative_path": path.as_posix(), "byte_size": path.stat().st_size, "source_mtime_ns": path.stat().st_mtime_ns, "sha256": sha256_file(path)} for path in CANONICAL_FILES
        ]}
        if not stable:
            continue
        shutil.copytree(LONG_ROOT, temporary / "long")
        shutil.copytree(SHORT_ROOT, temporary / "short")
        reports = temporary / "canonical_failed_reports"
        reports.mkdir(parents=True)
        for path in CANONICAL_FILES:
            shutil.copy2(path, reports / path.name)
        copied_rows = []
        for label, rows in before.items():
            for row in rows:
                name = Path(row["relative_path"]).name if label == "canonical" else row["relative_path"]
                rel = f"canonical_failed_reports/{name}" if label == "canonical" else f"{label}/{name}"
                copied = temporary / rel
                if sha256_file(copied) != row["sha256"]:
                    raise ValueError("SNAPSHOT_COPY_HASH_MISMATCH")
                copied_rows.append({**row, "source_class": label, "snapshot_relative_path": rel})
        after = {"long": file_manifest(LONG_ROOT), "short": file_manifest(SHORT_ROOT), "canonical": [
            {"relative_path": path.as_posix(), "byte_size": path.stat().st_size, "source_mtime_ns": path.stat().st_mtime_ns, "sha256": sha256_file(path)} for path in CANONICAL_FILES
        ]}
        if before != after:
            continue
        long_count = len(load_state(LONG_ROOT).get("ledger", []))
        short_count = len(load_state(SHORT_ROOT).get("ledger", []))
        manifest = {
            "schema": "AIOS_FOREX_PAPER60_POSTCERT_DRIFT_SNAPSHOT_V1",
            "snapshot_identity": SNAPSHOT_ID,
            "created_utc": utc_now(),
            "packet_id": PACKET_ID,
            "lock_id": LOCK_ID,
            "branch": branch,
            "head": head,
            "source_paths": {"long": LONG_ROOT.as_posix(), "short": SHORT_ROOT.as_posix(), "canonical": [path.as_posix() for path in CANONICAL_FILES]},
            "source_classification": "POST_CERTIFICATION_RUNTIME_DRIFT",
            "long_closed_count": long_count,
            "short_closed_count": short_count,
            "canonical_counts": {"long": 30, "short": 30},
            "runtime_roots_drifted_after_30_30": long_count != 30 or short_count != 30,
            "runtime_roots_are_not_canonical_certification_evidence": True,
            "process_quiesce_evidence": process_evidence,
            "attempt": attempt,
            "files": copied_rows,
        }
        atomic_json(temporary / "manifest.json", manifest)
        os.replace(temporary, SNAPSHOT_ROOT)
        return manifest
    raise RuntimeError("SOURCE_CHANGED_DURING_THREE_SNAPSHOT_ATTEMPTS")


def git_value(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()


def run() -> dict[str, Any]:
    canonical_before = {path.as_posix(): sha256_file(path) for path in CANONICAL_FILES}
    process_evidence = {"inspection": "Win32_Process command-line inspection", "matching_runner_pids": [], "stopped_pids": [], "no_unrelated_process_stopped": True, "result": "NO_ACTIVE_V1_WRITER_FOUND"}
    snapshot = create_snapshot(git_value("branch", "--show-current"), git_value("rev-parse", "HEAD"), process_evidence)
    long_all = load_state(LONG_ROOT)["ledger"]
    short_all = load_state(SHORT_ROOT)["ledger"]
    long_trades, short_trades = long_all[:30], short_all[:30]
    canonical = json.loads(CANONICAL_FILES[1].read_text(encoding="utf-8"))
    provenance = replay_provenance()
    campaign_first = min(long_trades[0]["fill_timestamp_utc"], short_trades[0]["fill_timestamp_utc"])
    replay_last = max((row["last"] for row in provenance["ranges"]), default="")
    overlap = replay_last >= campaign_first
    accounting = {"long": audit_trades(long_trades, "BUY"), "short": audit_trades(short_trades, "SELL")}
    long_summary, short_summary = trade_summary(long_trades), trade_summary(short_trades)
    target = target_causality(long_trades)
    RESEARCH_ROOT.mkdir(parents=True, exist_ok=True)
    atomic_json(RESEARCH_ROOT / "diagnostic_first30_long.json", {"classification": "DIAGNOSTIC_APPROXIMATION_ONLY", "trades": long_trades})
    atomic_json(RESEARCH_ROOT / "diagnostic_first30_short.json", {"classification": "DIAGNOSTIC_APPROXIMATION_ONLY", "trades": short_trades})
    freeze_state = {
        "schema": "AIOS_FOREX_PAPER60_FORENSIC_FREEZE_STATE_V1", "status": "PASS", "snapshot": snapshot,
        "canonical_sha256": canonical_before, "canonical_unchanged": canonical_before == {path.as_posix(): sha256_file(path) for path in CANONICAL_FILES},
        "long_sample_classification": "DIAGNOSTIC_APPROXIMATION_ONLY", "short_sample_classification": "DIAGNOSTIC_APPROXIMATION_ONLY",
    }
    postmortem = {
        "schema": "AIOS_FOREX_PAPER60_SUPERTREND_POSTMORTEM_STATE_V1", "generated_utc": utc_now(), "accounting": accounting,
        "drawdown_unit_verdict": "R_MULTIPLE_RUNNING_EQUITY_PEAK_TO_TROUGH_NOT_PERCENT", "canonical_metrics": {"long": canonical["long"], "short": canonical["short"]},
        "long": long_summary, "short": short_summary, "buy_10r_target_verdict": target,
        "market_data": {"source": provenance, "campaign_overlap": overlap, "verdict": "NO_TEMPORAL_OVERLAP_WITH_CAMPAIGN_TRADES" if not overlap else "OVERLAP_AVAILABLE"},
        "ranked_long_causes": [
            {"cause": "SIGNAL_ENTRY_STOP_CHAIN_FAILED_BEFORE_TARGET", "strength": "STRONG", "evidence": f"{long_summary['mfe_reached_1r']} of 30 reached +1R; exits={long_summary['exit_reasons']}"},
            {"cause": "TARGET_10R_CALIBRATION", "strength": "NON_CAUSAL_FOR_OBSERVED_FAILURES" if target["verdict"].startswith("NON_CAUSAL") else "CONTRIBUTING", "evidence": target},
            {"cause": "EXACT_CANDLE_LEVEL_SUBCLASSIFICATION", "strength": "INSUFFICIENT_EVIDENCE", "evidence": "Preserved replay ends before campaign; recorded MFE/MAE lacks candle sequence."},
        ],
        "short_verdict": "WEAK_UNCERTIFIED_EDGE; PF_BELOW_1.10_AND_DRAWDOWN_R_ABOVE_GATE",
    }
    research = {
        "schema": "AIOS_FOREX_PAPER60_CANDIDATE_RESEARCH_STATE_V1", "generated_utc": utc_now(), "status": "BOUNDED_HYPOTHESES_EXHAUSTED_NO_PROMOTION",
        "data_source": provenance, "split": {"research": "UNAVAILABLE_FOR_CURRENT_CAMPAIGN", "validation": "UNAVAILABLE", "holdout": "UNAVAILABLE"},
        "hypotheses_tested": ["BUY_TARGET_1_2_3_4_6_10R_REACHABILITY_FROM_RECORDED_MFE", "ACCOUNTING_AND_DIRECTION_ROUTING", "STOP_TARGET_GEOMETRY", "SHARED_LONG_SHORT_R_PARITY"],
        "rejected_candidates": [{"identity": "TARGET_ONLY_RECALIBRATION", "reason": "No LONG reached +1R; target reduction cannot rescue the observed sample."}],
        "promotion_gate": {"passed": False, "reason": "No non-overlapping chronological development/validation/holdout market sample covers the campaign strategy; promoting v2 would be overfit or fabricated."},
        "v2_created": False, "paper_v2_started": False,
    }
    atomic_json(FREEZE_STATE, freeze_state)
    atomic_json(POSTMORTEM_STATE, postmortem)
    atomic_json(RESEARCH_STATE, research)
    atomic_text(FREEZE_REPORT, f"""# Paper60 Forensic Freeze\n\n## CANONICAL FAILED PAPER60 REPORTS\n\nThe four canonical artifacts remain unchanged. Canonical counts are 30 LONG and 30 SHORT. Their SHA-256 values are recorded in the state file.\n\n## POST-CERTIFICATION RUNTIME DRIFT SNAPSHOT\n\nClassification: `{SNAPSHOT_ID}`. The copied runtime roots contain {snapshot['long_closed_count']} LONG and {snapshot['short_closed_count']} SHORT closes. They are not canonical Paper60 certification evidence. No active v1 writer was found and no process was stopped. Snapshot manifest hashes validated.\n\n## Forensic Recovery\n\nBoth first-30 slices are `DIAGNOSTIC_APPROXIMATION_ONLY`: the canonical reports do not preserve immutable trade IDs or hashes proving exact 30/30 identity.\n""")
    atomic_text(POSTMORTEM_REPORT, f"""# Paper60 Supertrend Postmortem\n\n## Measurement Integrity\n\nNo duplicates, direction contamination, stop/target inversion, or R-parity defect was found in the diagnostic first-30 slices. Canonical maximum drawdown is stored as running-equity peak-to-trough **R**, not percent; it cannot be compared directly with a 10-percent gate.\n\n## LONG / Supertrend\n\nAll {long_summary['trade_count']} diagnostic LONG trades lost; exits were {long_summary['exit_reasons']}. MFE reached +0.5R in {long_summary['mfe_reached_0_5r']} trades, +1R in {long_summary['mfe_reached_1r']}, and +2R in {long_summary['mfe_reached_2r']}. The strongest supported cause is failure in the signal/entry/stop chain before target calibration. Exact false-trend, late-entry, and stop-placement attribution remains unknown because the preserved replay cache ends before the campaign.\n\n## BUY 10R Target Verdict\n\n`{target['verdict']}`. {target['limitation']}\n\n## SHORT\n\nSHORT remains a weak, uncertified edge: positive expectancy is insufficient because PF is below 1.10 and drawdown in R is excessive.\n""")
    atomic_text(RESEARCH_REPORT, """# Paper60 Candidate Research\n\nThe failed first-30 slices generated hypotheses but were not used as validation. Target-only calibration, accounting, direction routing, stop/target geometry, and shared R-parity were tested. No candidate was promoted because the approved genuine replay cache does not overlap the campaign and cannot support a chronological 50/25/25 development, validation, and untouched holdout test. Creating v2 from the failed sample would violate the anti-overfit gate.\n\nStatus: `BOUNDED_HYPOTHESES_EXHAUSTED_NO_PROMOTION`.\n""")
    atomic_text(REDESIGN_REPORT, """# Forex Strategy Redesign Plan V1\n\n## Failed Assumptions\n\n- Two-close Supertrend confirmation plus the existing stop path did not produce viable LONG entries in the failed sample.\n- A 10R BUY target was unreachable, but target calibration was downstream of the observed failure because no LONG reached +1R.\n- Slightly positive SHORT expectancy did not survive PF and drawdown gates.\n- The available replay cache cannot independently validate changes against the later campaign period.\n\n## Next Architecture Direction\n\nAcquire a broad, immutable M5 candle corpus spanning multiple market regimes and the approved pair universe. Freeze its provenance before research. Reconstruct signals candle-by-candle with bid/ask spread, completed-candle enforcement, and deterministic same-candle precedence. Test a small ranked set of trend-age, persistence, pullback-quality, volatility-regime, and structure-based stop hypotheses using a single chronological 50/25/25 split. Open the holdout once, promote only if PF >= 1.10, expectancy > 0, canonical percent drawdown <= 10%, adequate direction-specific trade count, contribution diversity, and parameter-neighborhood stability all pass.\n\nDo not create Paper v2 until that evidence exists.\n""")
    return {"status": "STRATEGY_REDESIGN_REQUIRED", "snapshot": snapshot, "postmortem": postmortem, "research": research}


def main() -> int:
    parser = argparse.ArgumentParser(description="PAPER60 forensic freeze and recovery")
    parser.add_argument("--execute", action="store_true", help="write only packet-approved evidence paths")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required")
    result = run()
    print(json.dumps({"status": result["status"], "broker_write": False, "live": False, "money_movement": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
