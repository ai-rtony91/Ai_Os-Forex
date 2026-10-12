"""Collect and classify local C2 walk-forward/OOS source evidence.

This module is review-only. It does not trade, contact brokers, read
credentials, start services, or promote sample/test data into proof.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from automation.forex_engine.forex_110_c2_walkforward_oos_evidence_generation_v1 import (
    TARGET_CANDIDATE_ID,
)
from automation.forex_engine.forex_110_profit_evidence_truth_lock_v1 import (
    run_profit_evidence_truth_lock,
)
from automation.forex_engine.forex_110_walkforward_oos_sufficiency_truth_lock_v1 import (
    run_walkforward_oos_sufficiency_truth_lock,
)
from automation.forex_engine.walk_forward_evidence_intake_v1 import DEFAULT_REPORT_ROOT
from automation.forex_engine.walk_forward_oos_evidence_v1 import (
    WALK_FORWARD_OOS_READY,
    evaluate_walk_forward_oos_evidence,
)


PACKET_ID = "PKT-FOREX-110-C2-WALKFORWARD-OOS-SOURCE-COLLECTION-V1"
ENGINE_VERSION = "forex_110_c2_walkforward_oos_source_collection_v1"

REAL_SANITIZED_LOCAL_SOURCE_FOUND = "REAL_SANITIZED_LOCAL_SOURCE_FOUND"
REAL_SANITIZED_LOCAL_SOURCE_GENERATED = "REAL_SANITIZED_LOCAL_SOURCE_GENERATED"
SAMPLE_TEST_ONLY = "SAMPLE_TEST_ONLY"
SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
REVIEW_REQUIRED_CONFLICT = "REVIEW_REQUIRED_CONFLICT"

SOURCE_COLLECTION_PROVEN = "PROVEN_REAL_SANITIZED_LOCAL_C2_SOURCE"
SOURCE_COLLECTION_BLOCKED = "BLOCKED_NO_REAL_C2_OOS_SOURCE"

SOURCE_REPORT_NAME = "AIOS_FOREX_110_C2_WALKFORWARD_OOS_SOURCE_V1.md"
SOURCE_COLLECTION_STATE_NAME = "AIOS_FOREX_110_C2_WALKFORWARD_OOS_SOURCE_COLLECTION_V1_STATE.json"
SOURCE_COLLECTION_REPORT_NAME = "AIOS_FOREX_110_C2_WALKFORWARD_OOS_SOURCE_COLLECTION_V1_REPORT.md"
CANONICAL_OWNER_FILE = "automation/forex_engine/walk_forward_evidence_intake_v1.py"
TEST_FILE = "tests/forex_engine/test_forex_110_c2_walkforward_oos_source_collection_v1.py"
RUNNER_SCRIPT = "scripts/forex_delivery/run_forex_110_c2_walkforward_oos_source_collection_v1.py"

REQUIRED_SOURCE_FIELDS = (
    "candidate",
    "windows_total",
    "windows_passed",
    "oos_segments_total",
    "oos_segments_passed",
    "min_pass_rate",
    "max_drawdown",
    "max_allowed_drawdown",
    "sanitized",
    "evidence_age_days",
    "max_evidence_age_days",
)

PROTECTED_PERMISSION_FLAGS = {
    "next_demo_trade_allowed": False,
    "broker_action_allowed": False,
    "real_money_allowed": False,
    "compounding_allowed": False,
    "bank_movement_allowed": False,
    "live_trading_allowed": False,
    "credential_access_allowed": False,
    "order_submission_allowed": False,
    "owner_approval_created": False,
}

DEFAULT_SEARCH_ROOTS = (
    "automation/forex_engine",
    "scripts/forex_delivery",
    "tests/forex_engine",
    "Reports/forex_delivery",
    "docs/trading_lab/forex",
    "apps/trading_lab",
)

TEST_OR_SAMPLE_MARKERS = (
    "test",
    "tests",
    "fixture",
    "fixtures",
    "sample",
    "samples",
    "example",
    "mock-data",
    "mock_data",
)

BLOCKER_REPORT_MARKERS = (
    "blocked_no_real_c2_oos_source",
    "sample_test_only",
    "not promoted into proof",
    "does not contain real sanitized oos segment counts",
    "provide a sanitized walk-forward/oos evidence report",
)


def collect_c2_walkforward_oos_source(
    report_root: str | Path = DEFAULT_REPORT_ROOT,
    search_roots: Iterable[str | Path] | None = None,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """Return a deterministic C2 source collection state."""

    root = Path(report_root)
    base = Path(repo_root) if repo_root is not None else _repo_root_from_report_root(root)
    roots = list(search_roots) if search_roots is not None else list(DEFAULT_SEARCH_ROOTS)
    profit_lock = run_profit_evidence_truth_lock(root)
    truth_lock = run_walkforward_oos_sufficiency_truth_lock(root)
    top_candidate_id = str(profit_lock.get("top_candidate_id") or "NONE")
    candidates = _scan_candidate_sources(base, roots)
    valid_sources = [item for item in candidates if item["source_is_real_sanitized_local"]]
    conflicts = _conflicting_real_sources(valid_sources)
    source = valid_sources[0] if valid_sources and not conflicts else None
    diagnostic_sources = [item["path"] for item in candidates if item["diagnostic_summary_complete"]]
    sample_refs = [item["path"] for item in candidates if item["source_is_test_or_sample"]]

    if conflicts:
        classification = REVIEW_REQUIRED_CONFLICT
        status = "REVIEW_REQUIRED_CONFLICT"
        found = False
        generated = False
        candidate_alignment = "REVIEW_REQUIRED_CONFLICT"
        blockers = conflicts
    elif source is not None:
        classification = REAL_SANITIZED_LOCAL_SOURCE_FOUND
        status = SOURCE_COLLECTION_PROVEN
        found = True
        generated = False
        candidate_alignment = "ALIGNED"
        blockers = []
    else:
        classification = (
            "UNVERIFIED_LOCAL_SUMMARY" if diagnostic_sources
            else (SAMPLE_TEST_ONLY if sample_refs else SOURCE_UNAVAILABLE)
        )
        status = SOURCE_COLLECTION_BLOCKED
        found = False
        generated = False
        candidate_alignment = "BLOCKED_NO_REAL_C2_OOS_SOURCE"
        blockers = _dedupe(
            [
                "no real sanitized local C2 walk-forward/OOS source found",
                "missing field: oos_segments_total",
                "missing field: oos_segments_passed",
                "missing field: candidate_alignment",
            ]
        )

    blockers = _dedupe([*blockers, "NO_INDEPENDENT_VERIFIER_CONNECTED"])
    selected_fields = dict(source["fields"]) if source else _empty_source_fields()
    walkforward_status = str(truth_lock.get("walk_forward_oos_status") or "UNKNOWN")
    result = {
        "packet_id": PACKET_ID,
        "engine_version": ENGINE_VERSION,
        "source_collection_status": status,
        "source_authentication_status": "UNVERIFIED",
        "diagnostic_source_paths": diagnostic_sources,
        "evidence_source_classification": classification,
        "target_candidate_id": TARGET_CANDIDATE_ID,
        "top_candidate_id": top_candidate_id,
        "c2_source_found": found,
        "c2_source_generated": generated,
        "source_path": source["path"] if source else None,
        "source_is_test_or_sample": bool(source["source_is_test_or_sample"]) if source else bool(sample_refs),
        "source_is_real_sanitized_local": bool(source),
        "candidate_alignment": candidate_alignment,
        "oos_segments_total": selected_fields.get("oos_segments_total"),
        "oos_segments_passed": selected_fields.get("oos_segments_passed"),
        "windows_total": selected_fields.get("windows_total"),
        "windows_passed": selected_fields.get("windows_passed"),
        "min_pass_rate": selected_fields.get("min_pass_rate"),
        "max_drawdown": selected_fields.get("max_drawdown"),
        "max_allowed_drawdown": selected_fields.get("max_allowed_drawdown"),
        "sanitized": selected_fields.get("sanitized"),
        "evidence_age_days": selected_fields.get("evidence_age_days"),
        "max_evidence_age_days": selected_fields.get("max_evidence_age_days"),
        "walkforward_oos_status_after_rerun": walkforward_status,
        "profit_persistence_unlocked": bool(truth_lock.get("profit_persistence_unlocked")) if source else False,
        "source_report_path": SOURCE_REPORT_NAME if source else None,
        "source_is_test_or_sample_references": sample_refs,
        "candidate_sources_inspected": [item["path"] for item in candidates],
        "blockers": blockers,
        "permissions": dict(PROTECTED_PERMISSION_FLAGS),
        **PROTECTED_PERMISSION_FLAGS,
        "attack_to_finish": _attack_to_finish(
            status=status,
            classification=classification,
            blockers=blockers,
            source_path=source["path"] if source else None,
        ),
        "next_safe_action": _next_safe_action(classification),
    }
    return result


def build_report_markdown(result: Mapping[str, Any]) -> str:
    """Build the source collection report."""

    # Rendering a historical or caller-supplied label is not source verification.
    result = dict(result)
    result["source_authentication_status"] = "UNVERIFIED"
    result["source_is_real_sanitized_local"] = False
    result["permissions"] = dict(PROTECTED_PERMISSION_FLAGS)
    result["blockers"] = list(dict.fromkeys([
        *(result.get("blockers") or []), "NO_INDEPENDENT_VERIFIER_CONNECTED"
    ]))
    result["next_safe_action"] = (
        "Provide independently verified candidate-bound source, trades and costs "
        "through the existing evidence owner. Do not trade."
    )
    result["source_collection_status"] = SOURCE_COLLECTION_BLOCKED
    for flag in ("c2_source_found", "c2_source_generated", "profit_persistence_unlocked"):
        result[flag] = False
    if result.get("evidence_source_classification") in {
        REAL_SANITIZED_LOCAL_SOURCE_FOUND, REAL_SANITIZED_LOCAL_SOURCE_GENERATED,
    }:
        result["evidence_source_classification"] = "UNVERIFIED_LOCAL_SUMMARY"
    result["walkforward_oos_status_after_rerun"] = "BLOCKED_SOURCE_AUTHENTICITY"
    result["attack_to_finish"] = {
        **dict(result.get("attack_to_finish") or {}),
        "blocker_id": "MISSING_SOURCE_AUTHENTICITY",
        "blocker_status": "BLOCKED",
        "exact_blocker": "candidate source, trade receipts, costs and independent replay are unverified",
        "missing_evidence_field": "independent_source_verification",
        "stop_condition": "source authenticity remains unverified",
    }

    attack = result.get("attack_to_finish") if isinstance(result.get("attack_to_finish"), Mapping) else {}
    lines = [
        "# AIOS Forex 110 C2 Walk-Forward OOS Source Collection V1",
        "",
        f"Packet ID: `{result.get('packet_id', PACKET_ID)}`",
        f"Source collection status: `{result.get('source_collection_status')}`",
        f"Evidence source classification: `{result.get('evidence_source_classification')}`",
        f"Target candidate: `{result.get('target_candidate_id', TARGET_CANDIDATE_ID)}`",
        f"Top candidate: `{result.get('top_candidate_id')}`",
        f"C2 source found: `{_bool_text(result.get('c2_source_found'))}`",
        f"C2 source generated: `{_bool_text(result.get('c2_source_generated'))}`",
        f"Source path: `{_markdown_value(result.get('source_path'))}`",
        f"Source is test or sample: `{_bool_text(result.get('source_is_test_or_sample'))}`",
        f"Source is real sanitized local: `{_bool_text(result.get('source_is_real_sanitized_local'))}`",
        f"Candidate alignment: `{result.get('candidate_alignment')}`",
        "",
        "## Required Source Fields",
    ]
    for field in REQUIRED_SOURCE_FIELDS:
        lines.append(f"- {field}: `{_markdown_value(result.get(field))}`")
    lines.extend(["", "## Walk-Forward/OOS After Rerun"])
    lines.append(f"- walkforward_oos_status_after_rerun: `{result.get('walkforward_oos_status_after_rerun')}`")
    lines.append(f"- profit_persistence_unlocked: `{_bool_text(result.get('profit_persistence_unlocked'))}`")
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in result.get("blockers") or ["none"])
    lines.extend(["", "## Candidate Sources Inspected"])
    lines.extend(f"- {item}" for item in result.get("candidate_sources_inspected") or ["none"])
    lines.extend(["", "## Sample Or Test References"])
    lines.extend(f"- {item}" for item in result.get("source_is_test_or_sample_references") or ["none"])
    lines.extend(["", "## Permission Locks"])
    for key, value in (result.get("permissions") or {}).items():
        lines.append(f"- {key}: `{str(value).lower()}`")
    lines.extend(
        [
            "",
            "## ATTACK_TO_FINISH",
            f"- blocker_id: {attack.get('blocker_id', 'UNKNOWN')}",
            f"- blocker_status: {attack.get('blocker_status', 'UNKNOWN')}",
            f"- exact_blocker: {attack.get('exact_blocker', 'UNKNOWN')}",
            f"- canonical_owner_file: {attack.get('canonical_owner_file', 'UNKNOWN')}",
            f"- test_file: {attack.get('test_file', 'UNKNOWN')}",
            f"- runner_script: {attack.get('runner_script', 'UNKNOWN')}",
            f"- missing_evidence_field: {attack.get('missing_evidence_field', 'UNKNOWN')}",
            f"- unlock_status_required: {attack.get('unlock_status_required', 'UNKNOWN')}",
            f"- next_packet_name: {attack.get('next_packet_name', 'UNKNOWN')}",
            f"- owner_action_required: {attack.get('owner_action_required', 'UNKNOWN')}",
            f"- stop_condition: {attack.get('stop_condition', 'UNKNOWN')}",
            f"- no_bloat_guard: {attack.get('no_bloat_guard', 'UNKNOWN')}",
            "",
            "## Next Safe Action",
            str(result.get("next_safe_action", "")),
            "",
        ]
    )
    return "\n".join(lines)


def build_source_markdown(result: Mapping[str, Any]) -> str:
    """Build a consumable C2 source report only from a proven real source."""

    raise ValueError(
        "C2 source report requires real sanitized local source evidence; "
        "independent source verifier is unavailable"
    )


def _scan_candidate_sources(base: Path, roots: Iterable[str | Path]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for root_value in roots:
        root = Path(root_value)
        if not root.is_absolute():
            root = base / root
        if root.is_file():
            paths = [root]
        elif root.exists():
            paths = [path for path in root.rglob("*") if path.is_file()]
        else:
            paths = []
        for path in sorted(paths):
            if _should_skip(path):
                continue
            item = _candidate_from_path(base, path)
            if item is not None:
                candidates.append(item)
    return _dedupe_candidate_paths(candidates)


def _candidate_from_path(base: Path, path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if TARGET_CANDIDATE_ID not in text:
        return None
    fields = _extract_fields(path, text)
    source_is_test_or_sample = _is_test_or_sample(path, text)
    source_is_blocker_report = _is_blocker_report(text)
    evaluation = evaluate_walk_forward_oos_evidence(_summary_for_evaluation(fields))
    diagnostic_summary_complete = (
        not source_is_test_or_sample
        and not source_is_blocker_report
        and fields.get("candidate") == TARGET_CANDIDATE_ID
        and not _missing_required_fields(fields)
        and evaluation.get("walk_forward_oos_status") == WALK_FORWARD_OOS_READY
    )
    return {
        "path": _display_path(base, path),
        "fields": fields,
        "source_is_test_or_sample": source_is_test_or_sample,
        "source_is_blocker_report": source_is_blocker_report,
        # Completeness and a file location cannot verify market-data custody,
        # candidate trade receipts, costs or an independent replay.
        "source_is_real_sanitized_local": False,
        "diagnostic_summary_complete": diagnostic_summary_complete,
        "evaluation_status": evaluation.get("walk_forward_oos_status"),
        "evaluation_blockers": list(evaluation.get("blockers") or []),
        "missing_fields": _missing_required_fields(fields),
    }


def _extract_fields(path: Path, text: str) -> dict[str, Any]:
    data: Mapping[str, Any] = {}
    if path.suffix.lower() == ".json":
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError:
            loaded = {}
        if isinstance(loaded, Mapping):
            data = loaded
    fields: dict[str, Any] = {}
    for field in REQUIRED_SOURCE_FIELDS:
        if field == "candidate":
            fields[field] = _candidate_from_json(data) or _candidate_from_text(text)
        elif field == "sanitized":
            fields[field] = _bool_from_json(data, field)
            if fields[field] is None:
                fields[field] = _bool_from_key_values(text, field)
        else:
            fields[field] = _number_from_json(data, field)
            if fields[field] is None:
                fields[field] = _number_from_key_values(text, field)
    return fields


def _summary_for_evaluation(fields: Mapping[str, Any]) -> dict[str, Any] | None:
    if _missing_required_fields(fields):
        return None
    return {field: fields[field] for field in REQUIRED_SOURCE_FIELDS if field != "candidate"}


def _candidate_from_json(data: Mapping[str, Any]) -> str | None:
    for key in ("candidate", "candidate_id", "target_candidate_id", "top_candidate_id"):
        value = _find_key(data, key)
        if str(value) == TARGET_CANDIDATE_ID:
            return TARGET_CANDIDATE_ID
    return None


def _candidate_from_text(text: str) -> str | None:
    patterns = (
        re.compile(r"(?im)^\s*-?\s*(?:candidate|candidate_id|target_candidate_id|top_candidate_id)\s*:\s*`?([^`\n]+?)`?\s*$"),
        re.compile(r"(?im)^\s*(?:candidate|candidate_id|target_candidate_id|top_candidate_id)\s*=\s*['\"]?([^'\"\n]+?)['\"]?\s*$"),
    )
    for pattern in patterns:
        for match in pattern.finditer(text):
            if match.group(1).strip().strip(".") == TARGET_CANDIDATE_ID:
                return TARGET_CANDIDATE_ID
    return None


def _number_from_json(data: Mapping[str, Any], key: str) -> float | None:
    return _number(_find_key(data, key))


def _bool_from_json(data: Mapping[str, Any], key: str) -> bool | None:
    return _safe_bool(_find_key(data, key))


def _number_from_key_values(text: str, key: str) -> float | None:
    fields = _key_values(text)
    return _number(fields.get(_key(key)))


def _bool_from_key_values(text: str, key: str) -> bool | None:
    fields = _key_values(text)
    return _safe_bool(fields.get(_key(key)))


def _find_key(value: Any, target_key: str) -> Any:
    target = _key(target_key)
    if isinstance(value, Mapping):
        for key, item in value.items():
            if _key(str(key)) == target:
                return item
        for item in value.values():
            found = _find_key(item, target_key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_key(item, target_key)
            if found is not None:
                return found
    return None


def _key_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    pattern = re.compile(r"(?im)^\s*-?\s*([A-Za-z0-9 _/\-_]+):\s*`?([^`\n]+?)`?\s*\.?\s*$")
    for match in pattern.finditer(text):
        values[_key(match.group(1))] = match.group(2).strip()
    return values


def _missing_required_fields(fields: Mapping[str, Any]) -> list[str]:
    return [field for field in REQUIRED_SOURCE_FIELDS if fields.get(field) is None]


def _conflicting_real_sources(sources: list[Mapping[str, Any]]) -> list[str]:
    if len(sources) <= 1:
        return []
    field_sets = {json.dumps(source.get("fields", {}), sort_keys=True) for source in sources}
    if len(field_sets) <= 1:
        return []
    return ["conflicting real sanitized C2 source candidates found"]


def _empty_source_fields() -> dict[str, Any]:
    return {field: None for field in REQUIRED_SOURCE_FIELDS}


def _is_test_or_sample(path: Path, text: str) -> bool:
    path_parts = {_key(part) for part in path.parts}
    name = _key(path.name)
    if any(marker in path_parts or marker in name for marker in TEST_OR_SAMPLE_MARKERS):
        return True
    lowered = text.lower()
    return "build_sample" in lowered or "sample-" in lowered or "sample_" in lowered


def _is_blocker_report(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in BLOCKER_REPORT_MARKERS)


def _should_skip(path: Path) -> bool:
    lowered = path.name.lower()
    if path.name in {SOURCE_COLLECTION_STATE_NAME, SOURCE_COLLECTION_REPORT_NAME}:
        return True
    if lowered == ".env" or lowered.endswith(".env") or ".env" in [part.lower() for part in path.parts]:
        return True
    return path.suffix.lower() not in {".py", ".md", ".json", ".txt"}


def _attack_to_finish(
    *,
    status: str,
    classification: str,
    blockers: list[str],
    source_path: str | None,
) -> dict[str, str]:
    if status == SOURCE_COLLECTION_PROVEN:
        return {
            "blocker_id": "NO_BLOCKER",
            "blocker_status": "PROVEN",
            "exact_blocker": "NONE",
            "canonical_owner_file": CANONICAL_OWNER_FILE,
            "test_file": TEST_FILE,
            "runner_script": RUNNER_SCRIPT,
            "missing_evidence_field": "NONE",
            "unlock_status_required": "PROVEN",
            "next_packet_name": "NONE",
            "owner_action_required": "NONE",
            "stop_condition": "NONE",
            "no_bloat_guard": "Create the C2 source report only from real sanitized local evidence.",
        }
    missing = "oos_segments_total,oos_segments_passed,candidate_alignment"
    return {
        "blocker_id": "MISSING_EVIDENCE_FIELD",
        "blocker_status": "BLOCKED" if classification != REVIEW_REQUIRED_CONFLICT else "REVIEW_REQUIRED",
        "exact_blocker": "; ".join(blockers) if blockers else f"no consumable C2 source at {source_path or 'NONE'}",
        "canonical_owner_file": CANONICAL_OWNER_FILE,
        "test_file": TEST_FILE,
        "runner_script": RUNNER_SCRIPT,
        "missing_evidence_field": missing,
        "unlock_status_required": "PROVEN",
        "next_packet_name": "PKT-FOREX-110-C2-WALKFORWARD-OOS-SOURCE-COLLECTION-FOLLOWUP-V1",
        "owner_action_required": f"provide missing field {missing}",
        "stop_condition": "BLOCKED_NO_REAL_C2_OOS_SOURCE",
        "no_bloat_guard": "Do not create AIOS_FOREX_110_C2_WALKFORWARD_OOS_SOURCE_V1.md from tests, samples, examples, or blocker reports.",
    }


def _next_safe_action(classification: str) -> str:
    if classification in {REAL_SANITIZED_LOCAL_SOURCE_FOUND, REAL_SANITIZED_LOCAL_SOURCE_GENERATED}:
        return "Rerun the walk-forward/OOS sufficiency truth lock and review the generated C2 source report. Do not trade."
    return (
        "Provide or generate a real sanitized non-test C2 walk-forward/OOS source with "
        "candidate alignment and OOS segment counts. Do not trade."
    )


def _repo_root_from_report_root(root: Path) -> Path:
    resolved = root.resolve()
    if resolved.name == "forex_delivery" and resolved.parent.name == "Reports":
        return resolved.parent.parent
    return Path.cwd()


def _display_path(base: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().strip("`").rstrip(".")
    match = re.fullmatch(r"(-?[0-9]+(?:\.[0-9]+)?)%?", text)
    if match:
        return float(match.group(1))
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _safe_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().strip("`").lower()
        if lowered in {"true", "1", "yes", "pass", "passed", "ready", "ok"}:
            return True
        if lowered in {"false", "0", "no", "fail", "failed", "blocked"}:
            return False
    return None


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _markdown_value(value: Any) -> str:
    return "MISSING" if value is None else str(value)


def _bool_text(value: Any) -> str:
    return "true" if value is True else "false"


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _dedupe_candidate_paths(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for value in values:
        path = str(value.get("path"))
        if path not in seen:
            seen.add(path)
            result.append(value)
    return result


__all__ = [
    "PACKET_ID",
    "REAL_SANITIZED_LOCAL_SOURCE_FOUND",
    "REAL_SANITIZED_LOCAL_SOURCE_GENERATED",
    "REVIEW_REQUIRED_CONFLICT",
    "SAMPLE_TEST_ONLY",
    "SOURCE_UNAVAILABLE",
    "TARGET_CANDIDATE_ID",
    "build_report_markdown",
    "build_source_markdown",
    "collect_c2_walkforward_oos_source",
]
