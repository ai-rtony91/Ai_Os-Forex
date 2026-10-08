"""Build and validate an immutable, GET-only OANDA Practice M5 corpus."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from automation.forex_engine.oanda_read_only_client import OandaReadOnlyClient, OandaReadOnlyClientError


CORPUS_ID = "AIOS_FOREX_M5_IMMUTABLE_CORPUS_V1"
PACKET_ID = "PKT-EAST-FOREX-M5-RECOVERY-007"
ROOT = Path(".aios/runtime/forex_m5_immutable_corpus_v1")
SOURCE_CACHE = Path(".aios/runtime/forex_multipair_m5_replay_mba_v1/replay_cache.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_M5_CORPUS_REPORT.md")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_M5_CORPUS_STATE.json")
DD_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_DRAWDOWN_CONTRACT_REPORT.md")
DD_STATE = Path("Reports/forex_delivery/AIOS_FOREX_DRAWDOWN_CONTRACT_STATE.json")
GRANULARITY = "M5"
STEP = timedelta(minutes=5)
DEFAULT_DAYS = 90
CHUNK_DAYS = 14


def stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_stamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="ascii")
    os.replace(temporary, path)


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(value.rstrip() + "\n", encoding="ascii")
    os.replace(temporary, path)


def approved_universe(cache_path: Path = SOURCE_CACHE) -> list[str]:
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    names = payload.get("pair_history_names") or sorted(payload.get("pair_histories", {}))
    result = sorted({str(name).upper() for name in names})
    if not result or any(len(name) != 7 or name[3] != "_" for name in result):
        raise ValueError("INVALID_APPROVED_UNIVERSE")
    return result


def corpus_window(now: datetime, days: int) -> tuple[datetime, datetime]:
    end = now.astimezone(timezone.utc).replace(second=0, microsecond=0)
    end -= timedelta(minutes=end.minute % 5)
    return end - timedelta(days=days), end


def chunk_windows(start: datetime, end: datetime, days: int = CHUNK_DAYS) -> list[tuple[datetime, datetime]]:
    windows = []
    cursor = start
    while cursor < end:
        boundary = min(cursor + timedelta(days=days), end)
        windows.append((cursor, boundary))
        cursor = boundary
    return windows


def _side(item: Mapping[str, Any], name: str) -> dict[str, float]:
    source = item.get(name)
    if not isinstance(source, Mapping):
        raise ValueError(f"MISSING_{name.upper()}")
    values = {key: float(source[key]) for key in ("o", "h", "l", "c")}
    if min(values.values()) <= 0 or values["h"] < max(values["o"], values["c"], values["l"]) or values["l"] > min(values["o"], values["c"], values["h"]):
        raise ValueError(f"INVALID_{name.upper()}_OHLC")
    return values


def normalize_candle(instrument: str, item: Mapping[str, Any]) -> dict[str, Any] | None:
    if item.get("complete") is not True:
        return None
    when = parse_stamp(str(item["time"]))
    bid, ask, mid = _side(item, "bid"), _side(item, "ask"), _side(item, "mid")
    if any(ask[key] < bid[key] for key in ("o", "h", "l", "c")):
        raise ValueError("NEGATIVE_BID_ASK_SPREAD")
    return {
        "instrument": instrument,
        "timestamp": stamp(when),
        "complete": True,
        "volume": int(item.get("volume", 0)),
        "bid": bid,
        "ask": ask,
        "mid": mid,
    }


def quality(candles: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(candles, key=lambda row: row["timestamp"])
    timestamps = [row["timestamp"] for row in ordered]
    duplicates = len(timestamps) - len(set(timestamps))
    gaps = {"weekend_or_market_close": 0, "unexpected": 0}
    largest_gap_minutes = 0
    for previous, current in zip(ordered, ordered[1:]):
        delta = parse_stamp(current["timestamp"]) - parse_stamp(previous["timestamp"])
        minutes = int(delta.total_seconds() // 60)
        largest_gap_minutes = max(largest_gap_minutes, minutes)
        if delta <= STEP:
            continue
        if previous["timestamp"][:10] != current["timestamp"][:10] and delta >= timedelta(hours=24):
            gaps["weekend_or_market_close"] += 1
        else:
            gaps["unexpected"] += 1
    return {
        "chronological": timestamps == sorted(timestamps),
        "duplicate_timestamps": duplicates,
        "gap_counts": gaps,
        "largest_gap_minutes": largest_gap_minutes,
        "record_count": len(ordered),
    }


def fetch_chunk(client: OandaReadOnlyClient, instrument: str, start: datetime, end: datetime) -> dict[str, Any]:
    params = {"granularity": GRANULARITY, "price": "MBA", "from": stamp(start), "to": stamp(end), "includeFirst": "true", "smooth": "false"}
    last_error = "UNKNOWN"
    for attempt in range(1, 4):
        try:
            payload = client.request_json("GET", f"/v3/instruments/{instrument}/candles", params=params)
            raw = payload.get("candles")
            if not isinstance(raw, list):
                raise OandaReadOnlyClientError("CANDLES_LIST_MISSING_SANITIZED")
            return {"payload": raw, "attempt": attempt, "status_class": "2XX"}
        except (OandaReadOnlyClientError, TimeoutError) as exc:
            last_error = getattr(exc, "public_reason", "NETWORK_TIMEOUT_SANITIZED")
            if attempt < 3:
                time.sleep(attempt)
    raise OandaReadOnlyClientError(last_error)


def write_pair(path: Path, candles: Iterable[dict[str, Any]]) -> None:
    with gzip.open(path, "wt", encoding="ascii", newline="\n", compresslevel=6) as stream:
        for candle in candles:
            stream.write(stable_json(candle) + "\n")


def read_pair(path: Path) -> list[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="ascii") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def validate_existing(root: Path = ROOT) -> dict[str, Any] | None:
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for artifact in manifest.get("artifacts", []):
        path = root / artifact["relative_path"]
        if not path.is_file() or sha256(path) != artifact["sha256"] or path.stat().st_size != artifact["byte_size"]:
            raise ValueError("EXISTING_CORPUS_HASH_MISMATCH")
    return manifest


def drawdown_contract() -> dict[str, Any]:
    return {
        "schema": "AIOS_FOREX_DRAWDOWN_CONTRACT_V1",
        "canonical_unit": "PERCENT_OF_RUNNING_PEAK_EQUITY",
        "formula": "100 * (running_peak_equity - current_equity) / running_peak_equity",
        "starting_equity_required": True,
        "position_risk_fraction_required": True,
        "r_to_percent_relationship": "When each trade risks fixed fraction f of then-current equity, equity compounds by (1 + f * realized_R); drawdown percent is measured from the compounded equity curve peak.",
        "paper60_conversion_status": "NOT_RELIABLY_CONVERTIBLE",
        "paper60_reason": "Paper60 preserves R outcomes but does not canonically bind a starting equity and fixed per-trade equity-risk fraction in its certification artifacts.",
        "implementation_defect": "Paper60 labeled and gated maximum_drawdown_r while the owner certification requirement is percentage drawdown.",
        "future_requirement": "Every candidate result must record starting equity, risk fraction, per-trade equity before/after, running peak equity, drawdown percent, and maximum drawdown percent.",
        "gate_limit_percent": 10.0,
    }


def build(days: int = DEFAULT_DAYS, now: datetime | None = None) -> dict[str, Any]:
    existing = validate_existing()
    if existing is not None:
        return existing
    token, account = os.environ.get("OANDA_API_TOKEN"), os.environ.get("OANDA_ACCOUNT_ID")
    if not token or not account:
        raise RuntimeError("OANDA_PRACTICE_RUNTIME_CREDENTIALS_MISSING")
    universe = approved_universe()
    start, end = corpus_window(now or datetime.now(timezone.utc), days)
    temporary = ROOT.with_name(ROOT.name + ".tmp")
    temporary.mkdir(parents=True, exist_ok=True)
    client = OandaReadOnlyClient(api_token=token, account_id=account, environment="practice", timeout_seconds=20)
    artifacts, acquisitions, total = [], [], 0
    for instrument in universe:
        path = temporary / f"{instrument}.jsonl.gz"
        if path.exists():
            candles = read_pair(path)
            assessment = quality(candles)
            if (
                candles
                and parse_stamp(candles[0]["timestamp"]) >= start
                and parse_stamp(candles[-1]["timestamp"]) <= end
                and assessment["record_count"] >= 1000
                and not assessment["duplicate_timestamps"]
                and assessment["chronological"]
            ):
                total += len(candles)
                artifacts.append({"instrument": instrument, "relative_path": path.name, "byte_size": path.stat().st_size, "sha256": sha256(path), "first_utc": candles[0]["timestamp"], "last_utc": candles[-1]["timestamp"], **assessment})
                acquisitions.append({"instrument": instrument, "granularity": GRANULARITY, "requested_start_utc": stamp(start), "requested_end_utc": stamp(end), "actual_first_utc": candles[0]["timestamp"], "actual_last_utc": candles[-1]["timestamp"], "retrieval_utc": stamp(datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)), "completed_candle_count": len(candles), "source": "OANDA_PRACTICE_GET_ONLY_RESUMED_TEMP_ARTIFACT", "response_status_class": "2XX_PREVIOUS_BOUNDED_RUN", "artifact_sha256": sha256(path)})
                continue
            raise ValueError(f"TEMP_PAIR_ARTIFACT_INVALID:{instrument}")
        by_time: dict[str, dict[str, Any]] = {}
        for chunk_start, chunk_end in chunk_windows(start, end):
            response = fetch_chunk(client, instrument, chunk_start, chunk_end)
            accepted = 0
            for raw in response["payload"]:
                candle = normalize_candle(instrument, raw)
                if candle is not None:
                    by_time[candle["timestamp"]] = candle
                    accepted += 1
            acquisitions.append({"instrument": instrument, "granularity": GRANULARITY, "requested_start_utc": stamp(chunk_start), "requested_end_utc": stamp(chunk_end), "retrieval_utc": stamp(datetime.now(timezone.utc)), "completed_candle_count": accepted, "source": "OANDA_PRACTICE_GET_ONLY", "response_status_class": response["status_class"], "attempt": response["attempt"]})
        candles = [by_time[key] for key in sorted(by_time)]
        assessment = quality(candles)
        if assessment["record_count"] < 1000 or assessment["duplicate_timestamps"] or not assessment["chronological"]:
            raise ValueError(f"PAIR_QUALITY_REJECTED:{instrument}")
        write_pair(path, candles)
        reread = read_pair(path)
        if reread != candles:
            raise ValueError(f"PAIR_REREAD_MISMATCH:{instrument}")
        total += len(candles)
        artifacts.append({"instrument": instrument, "relative_path": path.name, "byte_size": path.stat().st_size, "sha256": sha256(path), "first_utc": candles[0]["timestamp"], "last_utc": candles[-1]["timestamp"], **assessment})
    aggregate = hashlib.sha256(stable_json([{"instrument": row["instrument"], "sha256": row["sha256"]} for row in artifacts]).encode("ascii")).hexdigest()
    manifest = {
        "schema": "AIOS_FOREX_M5_IMMUTABLE_CORPUS_MANIFEST_V1", "corpus_id": CORPUS_ID, "created_utc": stamp(datetime.now(timezone.utc)),
        "data_source": "OANDA_PRACTICE_GET_ONLY", "environment": "practice", "http_method": "GET", "granularity": GRANULARITY,
        "requested_start_utc": stamp(start), "requested_end_utc": stamp(end), "pair_universe": universe, "pair_count": len(universe), "total_records": total,
        "representation_type": "DETERMINISTIC_GZIP_JSONL_MBA_COMPLETED_CANDLES", "bid_ask_mid": True, "completed_only": True,
        "artifacts": artifacts, "acquisitions": acquisitions, "aggregate_corpus_fingerprint": aggregate,
        "repository_head": os.popen("git rev-parse HEAD").read().strip(),
        "known_limitations": ["OANDA Practice candle availability varies by instrument and market closure.", "Unexpected timestamp gaps are reported, never filled."],
        "safety": {"broker_write": False, "practice_order": False, "live": False, "money_movement": False, "credentials_persisted": False},
    }
    atomic_json(temporary / "manifest.json", manifest)
    os.replace(temporary, ROOT)
    return manifest


def publish(manifest: dict[str, Any]) -> None:
    dd = drawdown_contract()
    atomic_json(DD_STATE, dd)
    atomic_text(DD_REPORT, f"""# Forex Drawdown Contract\n\nThe canonical gate is maximum drawdown as a percentage of running peak equity:\n\n`100 * (running_peak_equity - current_equity) / running_peak_equity`\n\nPaper60's R-only drawdown cannot be reliably converted because its canonical artifacts do not bind starting equity and a fixed per-trade equity-risk fraction. Future research must persist the full compounded equity curve inputs. This is a measurement-contract defect; historical evidence remains unchanged.\n""")
    state = {"schema": "AIOS_FOREX_M5_CORPUS_STATE_V1", "status": "FROZEN_VALID", "manifest_path": (ROOT / "manifest.json").as_posix(), "corpus_id": manifest["corpus_id"], "pair_count": manifest["pair_count"], "total_records": manifest["total_records"], "start_utc": manifest["requested_start_utc"], "end_utc": manifest["requested_end_utc"], "aggregate_corpus_fingerprint": manifest["aggregate_corpus_fingerprint"], "freeze_validation": "PASS", "safety": manifest["safety"]}
    atomic_json(STATE, state)
    unexpected = sum(row["gap_counts"]["unexpected"] for row in manifest["artifacts"])
    atomic_text(REPORT, f"""# Immutable M5 Corpus\n\n- Corpus ID: `{manifest['corpus_id']}`\n- Source: OANDA Practice GET-only\n- Pairs: {manifest['pair_count']}\n- Period: {manifest['requested_start_utc']} to {manifest['requested_end_utc']}\n- Completed M5 candles: {manifest['total_records']}\n- Representation: deterministic gzip JSONL with bid, ask, and mid OHLC\n- Unexpected gaps: {unexpected} (reported, never filled)\n- Aggregate fingerprint: `{manifest['aggregate_corpus_fingerprint']}`\n- Freeze validation: PASS\n""")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute or not 30 <= args.days <= 180:
        parser.error("--execute and --days between 30 and 180 are required")
    manifest = build(days=args.days)
    publish(manifest)
    print(stable_json({"status": "FROZEN_VALID", "pair_count": manifest["pair_count"], "total_records": manifest["total_records"], "broker_write": False, "live": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
