"""Validation helpers for sanitized Forex evidence bundles."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, Mapping


EVIDENCE_PASS = "EVIDENCE_PASS"
EVIDENCE_REPAIRABLE = "EVIDENCE_REPAIRABLE"
OWNER_EVIDENCE_REQUIRED = "OWNER_EVIDENCE_REQUIRED"
SAFETY_REJECT = "SAFETY_REJECT"
INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
EXTERNAL_ONLY_BLOCKED = "EXTERNAL_ONLY_BLOCKED"

REQUIRED_SECTIONS = (
    "candidate evidence",
    "risk control",
    "expectancy",
    "drawdown",
    "owner approval",
)

SENSITIVE_LINE_PATTERNS = [
    re.compile(r"(?im)^\s*(api[_-]?key|apikey|secret|password|token)\s*[:=]"),
    re.compile(r"(?im)^\s*access[_-]?key\s*[:=]"),
]

BROKER_COMMAND_PATTERNS = [
    re.compile(r"(?im)\b(place|send|submit)\s+(an?\s+)?order\b"),
    re.compile(r"(?im)\bplace\s+trade\b"),
    re.compile(r"(?im)\bconnect\s+to\s+(oanda|broker)\b"),
]


def scan_sensitive_patterns(text: str) -> list[dict[str, str]]:
    matches: list[dict[str, str]] = []
    for pattern in SENSITIVE_LINE_PATTERNS + BROKER_COMMAND_PATTERNS:
        for hit in pattern.finditer(text):
            matches.append({"pattern": pattern.pattern, "value": hit.group(0).strip()})
    return matches


def scan_required_sections(text: str) -> dict[str, Any]:
    lowered = text.lower()
    missing = [section for section in REQUIRED_SECTIONS if section not in lowered]
    return {
        "missing_sections": missing,
        "required_sections": list(REQUIRED_SECTIONS),
        "present_sections": [section for section in REQUIRED_SECTIONS if section in lowered],
    }


def validate_evidence_text(
    text: str,
    *,
    strict: bool = False,
    min_sample: int = 30,
) -> dict[str, Any]:
    sensitive = scan_sensitive_patterns(text)
    section_report = scan_required_sections(text)
    sample_match = re.search(r"sample[ _-]count[:=]\s*(\d+)", text, re.IGNORECASE)
    sample_size = int(sample_match.group(1)) if sample_match else None
    status = EVIDENCE_PASS
    blockers: list[str] = []
    repair_instructions: list[str] = []
    if sensitive:
        status = SAFETY_REJECT
        blockers.append("sensitive content or command pattern detected")
        repair_instructions.append("Remove sensitive lines and command text.")
    elif sample_match and sample_size is not None and sample_size < min_sample:
        status = INSUFFICIENT_SAMPLE
        blockers.append("sample_count below minimum")
        repair_instructions.append("Collect additional sample rows for review.")
    elif section_report["missing_sections"]:
        status = EVIDENCE_REPAIRABLE
        blockers.append("missing required sections")
        repair_instructions.append("Add all required sections.")
    elif strict:
        status = OWNER_EVIDENCE_REQUIRED
        blockers.append("strict mode owner confirmation required")
        repair_instructions.append("Attach owner review proof.")
    if status == EVIDENCE_PASS:
        repair_instructions = ["No repair action required."]
    return {
        "status": status,
        "sample_size": sample_size,
        "sensitive_hits": sensitive,
        "section_report": section_report,
        "owner_evidence_required": strict and status == OWNER_EVIDENCE_REQUIRED,
        "blockers": blockers,
        "repair_instructions": repair_instructions,
    }


def _normalize_cross_platform_path(path: str | Path) -> Path:
    text = str(path)
    if "\\" in text:
        text = text.replace("\\", "/")
    return Path(text)


def validate_evidence_file(path: str | Path, **kwargs: Any) -> dict[str, Any]:
    path_obj = _normalize_cross_platform_path(path)
    payload = path_obj.read_text(encoding="utf-8", errors="ignore")
    result = validate_evidence_text(payload, **kwargs)
    result["path"] = str(path_obj)
    return result


def validate_evidence_bundle(
    paths: Iterable[str | Path],
    *,
    strict: bool = False,
) -> dict[str, Any]:
    evaluated = [validate_evidence_file(path, strict=strict) for path in list(paths)]
    if any(item["status"] == SAFETY_REJECT for item in evaluated):
        status = SAFETY_REJECT
    elif any(item["status"] == INSUFFICIENT_SAMPLE for item in evaluated):
        status = INSUFFICIENT_SAMPLE
    elif any(item["status"] in {EVIDENCE_REPAIRABLE, OWNER_EVIDENCE_REQUIRED} for item in evaluated):
        status = EVIDENCE_REPAIRABLE
    else:
        status = EVIDENCE_PASS
    return {
        "status": status,
        "path_count": len(evaluated),
        "results": evaluated,
    }


def quality_result_to_markdown(result: Mapping[str, Any]) -> str:
    lines = [
        "# Forex Evidence Quality Validator V1",
        f"Status: {result.get('status')}",
        f"- Paths: {result.get('path_count', 0)}",
        "",
    ]
    for item in result.get("results", []):
        lines.append(f"## {item.get('path')}")
        lines.append(f"- status: {item.get('status')}")
        lines.append(f"- sample_size: {item.get('sample_size')}")
        section_report = item.get("section_report", {})
        lines.append(f"- missing_sections: {section_report.get('missing_sections', [])}")
        if item.get("sensitive_hits"):
            lines.append("- sensitive_hits:")
            for hit in item.get("sensitive_hits", []):
                lines.append(f"  - {hit['pattern']}: {hit['value']}")
        lines.append("- repair_instructions:")
        for note in item.get("repair_instructions", []):
            lines.append(f"  - {note}")
    return "\n".join(lines)


def quality_result_to_jsonable_dict(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": result.get("status"),
        "path_count": int(result.get("path_count", 0)),
        "results": [
            {
                "path": item.get("path"),
                "status": item.get("status"),
                "sample_size": item.get("sample_size"),
                "sensitive_hits": list(item.get("sensitive_hits", [])),
                "blockers": list(item.get("blockers", [])),
                "repair_instructions": list(item.get("repair_instructions", [])),
            }
            for item in result.get("results", [])
        ],
    }


__all__ = [
    "EVIDENCE_PASS",
    "EVIDENCE_REPAIRABLE",
    "OWNER_EVIDENCE_REQUIRED",
    "SAFETY_REJECT",
    "INSUFFICIENT_SAMPLE",
    "EXTERNAL_ONLY_BLOCKED",
    "REQUIRED_SECTIONS",
    "scan_sensitive_patterns",
    "scan_required_sections",
    "validate_evidence_text",
    "validate_evidence_file",
    "validate_evidence_bundle",
    "quality_result_to_markdown",
    "quality_result_to_jsonable_dict",
]
