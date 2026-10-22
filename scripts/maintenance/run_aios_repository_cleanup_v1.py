#!/usr/bin/env python3
"""Deterministic, fail-closed AI_OS repository cleanup controller."""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Iterable

BASELINE = "563681dc1b42aec312f62830dedae9c19f4244f5"
RUNTIME = Path(".aios/runtime/repository_cleanup")
AUDIT_JSON = "AIOS_REPOSITORY_CLEANUP_AUDIT_V1.json"
AUDIT_MD = "AIOS_REPOSITORY_CLEANUP_AUDIT_V1.md"
PLAN_JSON = "AIOS_REPOSITORY_CLEANUP_PLAN_V1.json"
RECEIPT_JSON = "AIOS_REPOSITORY_CLEANUP_APPLY_RECEIPT_V1.json"
STATUSES = {"PASS", "WARN", "BLOCKED", "NOT_AVAILABLE"}
PROTECTED_PREFIXES = (
    "AGENTS.md", "CLAUDE.md", "RISK_POLICY.md", "SECURITY.md",
    "COMPLIANCE_BASELINE.md", ".git/", ".github/", ".githooks/",
    "automation/", "aios/", "apps/", "services/", "scripts/forex_delivery/",
    "tests/forex_engine/", "tests/forex_delivery/", "Reports/", "docs/security/",
    "docs/governance/", "runtime/", "dispatcher/runtime/", "work_packets/",
)
TEXT_SUFFIXES = {".py", ".pyi", ".json", ".md", ".txt", ".yml", ".yaml", ".ps1", ".toml", ".ini", ".cfg", ".sh"}
SECRET_RE = re.compile(r"(?i)\b(api[_-]?key|secret|token|password|broker)\b\s*[:=]\s*(['\"]?)([^\s,'\"}]+)")
MARKER_RE = re.compile(r"\b(TODO|TBD|FIXME|HACK|XXX)\b")
WINDOWS_PATH_RE = re.compile(r"(?i)\b[A-Z]:\\(?:[^\s\"']+)")
MD_LINK_RE = re.compile(r"!?\[[^]]*]\(([^)]+)\)")


class ControllerError(RuntimeError):
    """An expected safety or validation failure with an exit code."""

    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


def run(args: list[str], root: Path, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    """Run a bounded local command without a shell."""
    return subprocess.run(args, cwd=root, text=True, capture_output=True, timeout=timeout, check=False)


def git(root: Path, *args: str) -> str:
    result = run(["git", *args], root)
    if result.returncode:
        raise ControllerError(f"Git command failed: git {' '.join(args)}", 3)
    return result.stdout


def tracked_files(root: Path) -> list[str]:
    """Return Git's canonical, sorted tracked-file inventory."""
    result = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, timeout=30, check=False)
    if result.returncode:
        raise ControllerError("Category B: git ls-files failed", 3)
    return sorted(item.decode("utf-8", "surrogateescape") for item in result.stdout.split(b"\0") if item)


def safe_path(root: Path, relative: str) -> Path:
    """Resolve a repository-relative path and reject traversal or escape."""
    normalized = relative.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(relative)
    if not relative or posix.is_absolute() or windows.is_absolute() or ".." in posix.parts or any(c in relative for c in "*?[]"):
        raise ControllerError(f"Unsafe repository path: {relative!r}", 5)
    root_resolved = root.resolve()
    candidate = root.joinpath(*posix.parts)
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root_resolved)
    except (OSError, ValueError):
        raise ControllerError(f"Repository path escapes root: {relative!r}", 5) from None
    return candidate


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def redact(text: str) -> str:
    """Redact values assigned to secret-like names."""
    return SECRET_RE.sub(lambda m: f"{m.group(1)}={m.group(2)}[REDACTED]{m.group(2)}", text)


def finding(category: str, code: str, severity: str, path: str, line: int | None, evidence: str,
            validator: str = "manual review", mechanism: str = "report only", eligible: bool = False) -> dict[str, Any]:
    return {"automatic_eligibility": eligible, "category": category, "evidence": redact(evidence)[:300],
            "id": f"{category}-{code}", "line": line, "path": path, "proposed_fix_mechanism": mechanism,
            "proposed_validator": validator, "severity": severity}


def _json_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def _tool(root: Path, names: Iterable[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for name in names:
        executable = shutil.which(name)
        if executable:
            result = run([executable, "--version"], root, 10)
            found[name] = redact((result.stdout or result.stderr).splitlines()[0] if (result.stdout or result.stderr) else "available")
        else:
            found[name] = "NOT_AVAILABLE"
    return found


def repository_state(root: Path) -> dict[str, Any]:
    branch = git(root, "branch", "--show-current").strip()
    head = git(root, "rev-parse", "HEAD").strip()
    status = git(root, "status", "--porcelain", "--untracked-files=no")
    ancestor = run(["git", "merge-base", "--is-ancestor", BASELINE, "HEAD"], root).returncode == 0
    remotes = [line.split()[0] for line in git(root, "remote", "-v").splitlines()]
    return {"baseline_ancestor": ancestor, "branch": branch, "clean": not status.strip(), "head": head,
            "remotes": sorted(set(remotes)), "repository_root": str(root.resolve())}


def audit_repository(root: Path, generated_at: str | None = None) -> dict[str, Any]:
    """Inspect tracked repository content without modifying it."""
    root = root.resolve()
    state = repository_state(root)
    paths = tracked_files(root)
    tools = _tool(root, ("python", "pytest", "ruff", "black", "mypy", "pyright", "pwsh", "powershell", "yamllint"))
    categories = {letter: "PASS" for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"}
    findings: list[dict[str, Any]] = []
    skipped: dict[str, int] = {}
    inspected = 0
    hashes: dict[str, list[str]] = {}
    lower: dict[str, list[str]] = {}
    required = ["AGENTS.md", "README.md", "SECURITY.md", "COMPLIANCE_BASELINE.md", ".github/workflows/ci.yml"]
    for required_path in required:
        if required_path not in paths:
            categories["S"] = "BLOCKED"
            findings.append(finding("S", "MISSING_REQUIRED", "BLOCKING", required_path, None, "Required authority/security file missing"))
    if not state["branch"] or not state["clean"] or not state["baseline_ancestor"]:
        categories["B"] = "BLOCKED"
        findings.append(finding("B", "UNSAFE_STATE", "BLOCKING", "", None, "Detached, dirty, or missing baseline ancestry"))
    if not any(p == "AGENTS.md" for p in paths):
        categories["A"] = "BLOCKED"
    for relative in paths:
        lower.setdefault(relative.casefold(), []).append(relative)
        try:
            path = safe_path(root, relative)
        except ControllerError:
            categories["A"] = "BLOCKED"
            findings.append(finding("A", "PATH_ESCAPE", "BLOCKING", relative, None, "Tracked path or symlink resolves outside repository"))
            skipped["symlink_escape"] = skipped.get("symlink_escape", 0) + 1
            continue
        if path.is_symlink():
            try:
                path.resolve(strict=True).relative_to(root)
            except (OSError, ValueError):
                categories["A"] = "BLOCKED"
                findings.append(finding("A", "SYMLINK_ESCAPE", "BLOCKING", relative, None, "Tracked symlink resolves outside repository"))
            skipped["symlink"] = skipped.get("symlink", 0) + 1
            continue
        try:
            data = path.read_bytes()
        except OSError:
            skipped["unreadable"] = skipped.get("unreadable", 0) + 1
            categories["M"] = "WARN"
            continue
        hashes.setdefault(sha256(data), []).append(relative)
        if b"\0" in data:
            skipped["binary"] = skipped.get("binary", 0) + 1
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"AGENTS.md", "README.md", "LICENSE", ".gitignore"}:
            skipped["unsupported_type"] = skipped.get("unsupported_type", 0) + 1
            continue
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            skipped["unsupported_encoding"] = skipped.get("unsupported_encoding", 0) + 1
            categories["M"] = "WARN"
            findings.append(finding("M", "ENCODING", "WARNING", relative, None, "Unsupported non-UTF-8 encoding"))
            continue
        inspected += 1
        if b"\r\n" in data and data.replace(b"\r\n", b"").find(b"\n") >= 0:
            categories["M"] = "WARN"; findings.append(finding("M", "MIXED_EOL", "WARNING", relative, None, "Mixed line endings"))
        if data and not data.endswith((b"\n", b"\r")):
            categories["M"] = "WARN"; findings.append(finding("M", "FINAL_NEWLINE", "INFO", relative, None, "Missing final newline"))
        if len(data) > 1_000_000 or text.count("\n") > 3000:
            categories["L"] = "WARN"; findings.append(finding("L", "LARGE_FILE", "WARNING", relative, None, f"Large review surface: {len(data)} bytes"))
        for number, line_text in enumerate(text.splitlines(), 1):
            if SECRET_RE.search(line_text):
                categories["H"] = "WARN"; findings.append(finding("H", "SECRET_LIKE", "WARNING", relative, number, line_text))
            if MARKER_RE.search(line_text):
                categories["K"] = "WARN"; findings.append(finding("K", "MARKER", "INFO", relative, number, line_text))
            if WINDOWS_PATH_RE.search(line_text):
                categories["X"] = "WARN"; findings.append(finding("X", "PLATFORM_PATH", "INFO", relative, number, line_text))
        if relative.endswith(".py"):
            try:
                tree = ast.parse(text, filename=relative)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and getattr(node, "end_lineno", node.lineno) - node.lineno > 100:
                        categories["L"] = "WARN"; findings.append(finding("L", "LARGE_FUNCTION", "INFO", relative, node.lineno, node.name))
            except SyntaxError as exc:
                categories["I"] = "BLOCKED"; findings.append(finding("I", "SYNTAX", "BLOCKING", relative, exc.lineno, exc.msg))
        if relative.endswith(".json"):
            try:
                json.loads(text, object_pairs_hook=_json_duplicates)
            except (json.JSONDecodeError, ValueError) as exc:
                categories["J"] = "WARN"; findings.append(finding("J", "INVALID_JSON", "WARNING", relative, getattr(exc, "lineno", None), str(exc)))
        if relative.endswith(".md"):
            for number, line_text in enumerate(text.splitlines(), 1):
                for target in MD_LINK_RE.findall(line_text):
                    target = target.split("#", 1)[0]
                    if target and not re.match(r"^[a-z]+://", target, re.I) and not target.startswith(("#", "mailto:")):
                        try:
                            linked = safe_path(root, str((PurePosixPath(relative).parent / target)))
                        except ControllerError:
                            categories["R"] = "WARN"; findings.append(finding("R", "LINK_ESCAPE", "WARNING", relative, number, target)); continue
                        if not linked.exists():
                            categories["R"] = "WARN"; findings.append(finding("R", "MISSING_LINK", "INFO", relative, number, target))
        if relative.startswith(("runtime/", "dispatcher/runtime/", "work_packets/")):
            categories["G"] = "WARN"; findings.append(finding("G", "TRACKED_RUNTIME", "WARNING", relative, None, "Tracked runtime material"))
    for digest, duplicates in sorted(hashes.items()):
        if len(duplicates) > 1:
            categories["E"] = "WARN"; findings.append(finding("E", "DUPLICATE", "INFO", duplicates[0], None, f"SHA-256 {digest}; duplicates: {', '.join(duplicates)}"))
    for collision in lower.values():
        if len(collision) > 1:
            categories["N"] = "WARN"; findings.append(finding("N", "CASE_COLLISION", "WARNING", collision[0], None, ", ".join(collision)))
    if tools["pwsh"] == tools["powershell"] == "NOT_AVAILABLE": categories["P"] = "NOT_AVAILABLE"
    if all(tools[name] == "NOT_AVAILABLE" for name in ("ruff", "black", "mypy", "pyright")):
        categories["Q"] = "NOT_AVAILABLE"
    # Availability alone is not configuration authority. This repository has no
    # configured unused-code analyzer, so V1 must not infer or run one.
    categories["U"] = "NOT_AVAILABLE"
    if tools["yamllint"] == "NOT_AVAILABLE": categories["Y"] = "NOT_AVAILABLE"
    for letter in ("C", "D", "F", "O", "T", "V", "W"):
        # These categories are inventory/evidence categories; their PASS means inspection completed.
        categories[letter] = categories.get(letter, "PASS")
    findings.sort(key=lambda x: (x["severity"], x["category"], x["path"], x["line"] or 0, x["id"], x["evidence"]))
    grouped = {severity: [f for f in findings if f["severity"] == severity] for severity in ("BLOCKING", "WARNING", "INFO")}
    return {"baseline_ancestry_result": state["baseline_ancestor"], "branch": state["branch"], "categories": categories,
            "clean_state_result": state["clean"], "discovered_tools": tools,
            "findings_by_severity": grouped, "generated_at_utc": generated_at or dt.datetime.now(dt.timezone.utc).isoformat(),
            "head": state["head"], "inspected_file_count": inspected, "repository_root": str(root),
            "schema": "aios.repository_cleanup.audit.v1", "skipped_file_count": sum(skipped.values()),
            "skipped_file_reasons": dict(sorted(skipped.items())), "tracked_file_count": len(paths)}


def markdown_report(report: dict[str, Any]) -> str:
    lines = ["# AIOS Repository Cleanup Audit V1", "", f"Generated: {report['generated_at_utc']}",
             f"Repository: `{report['repository_root']}`", f"Branch / HEAD: `{report['branch']}` / `{report['head']}`", "", "## A–Z Status", ""]
    lines.extend(f"- **{key}** — {value}" for key, value in sorted(report["categories"].items()))
    lines += ["", "## Findings", ""]
    for severity, items in report["findings_by_severity"].items():
        lines.append(f"### {severity}")
        lines.extend(f"- `{item['id']}` `{item['path']}`{':' + str(item['line']) if item['line'] else ''}: {item['evidence']}" for item in items)
        if not items: lines.append("- None")
    return "\n".join(lines) + "\n"


def stable_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False, newline="\n") as handle:
        handle.write(data); temporary = Path(handle.name)
    os.replace(temporary, path)


def runtime_is_ignored(root: Path) -> bool:
    return run(["git", "check-ignore", "-q", str(RUNTIME / "probe")], root).returncode == 0


def build_plan(report: dict[str, Any], root: Path) -> dict[str, Any]:
    """Classify findings; V1 deliberately grants no automatic mutation authority."""
    entries = []
    for severity in ("BLOCKING", "WARNING", "INFO"):
        for item in report["findings_by_severity"][severity]:
            relative = item["path"]
            digest = sha256(safe_path(root, relative).read_bytes()) if relative and safe_path(root, relative).is_file() else None
            classification = "BLOCKED_PROTECTED_PATH" if is_protected(relative) else ("SEPARATE_PACKET_REQUIRED" if severity == "BLOCKING" else "REPORT_ONLY")
            entries.append({"automatic_eligibility": False, "classification": classification, "configured_tool_name": None,
                            "exact_command_arguments": [], "expected_changed_paths": [], "finding_identifier": item["id"],
                            "original_sha256": digest, "path": relative, "post_fix_validators": [],
                            "reason_semantics_preserving": "No automatic change is authorized.", "rollback_evidence": "Original SHA-256 recorded; report-only entry."})
    return {"branch": report["branch"], "entries": entries, "generated_at_utc": report["generated_at_utc"], "head": report["head"],
            "repository_root": report["repository_root"], "schema": "aios.repository_cleanup.plan.v1"}


def is_protected(relative: str) -> bool:
    normalized = relative.replace("\\", "/").lstrip("./")
    return any(normalized == prefix.rstrip("/") or normalized.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def validate_plan(plan: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    if plan.get("schema") != "aios.repository_cleanup.plan.v1" or not isinstance(plan.get("entries"), list):
        raise ControllerError("Malformed plan schema", 4)
    validated = []
    for entry in plan["entries"]:
        if entry.get("classification") != "EXISTING_TOOL_SAFE_FIX" or not entry.get("automatic_eligibility"):
            continue
        relative = entry.get("path", "")
        safe_path(root, relative)
        if is_protected(relative) or relative.startswith((".aios/", "Reports/")):
            raise ControllerError(f"Protected plan path: {relative}", 5)
        expected = entry.get("expected_changed_paths")
        if expected != [relative]: raise ControllerError("Plan must authorize one exact path", 4)
        args = entry.get("exact_command_arguments")
        tool = entry.get("configured_tool_name")
        if not args or args[0] != tool or shutil.which(tool) is None: raise ControllerError("Unknown or malformed configured tool", 4)
        if any(any(c in arg for c in "*?[]") for arg in args): raise ControllerError("Wildcard command argument rejected", 5)
        validated.append(entry)
    return validated


def apply_plan(root: Path, plan_path: Path, confirmed: bool) -> dict[str, Any]:
    """Apply exact eligible entries with state gates and byte rollback."""
    if not confirmed: raise ControllerError("APPLY requires --confirm-safe-apply", 2)
    state = repository_state(root)
    if not state["branch"] or state["branch"] == "main": raise ControllerError("APPLY requires a non-main attached branch", 2)
    if not state["clean"]: raise ControllerError("APPLY requires a clean worktree", 2)
    try: plan = json.loads(plan_path.read_text(encoding="utf-8"), object_pairs_hook=_json_duplicates)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc: raise ControllerError(f"Malformed plan: {type(exc).__name__}", 4) from None
    if plan.get("head") != state["head"]: raise ControllerError("Plan HEAD is stale", 4)
    entries = validate_plan(plan, root)
    originals: dict[str, bytes] = {}
    touched: list[str] = []
    before_status = set(git(root, "status", "--porcelain", "--untracked-files=no").splitlines())
    try:
        for entry in entries:
            relative = entry["path"]; path = safe_path(root, relative); original = path.read_bytes()
            if sha256(original) != entry.get("original_sha256"): raise ControllerError(f"Stale file hash: {relative}", 4)
            originals[relative] = original
            result = run(entry["exact_command_arguments"], root, 120)
            if result.returncode: raise ControllerError(f"Configured tool failed for {relative}", 3)
            changed = {line[3:] for line in git(root, "status", "--porcelain", "--untracked-files=no").splitlines() if len(line) > 3}
            unexpected = changed - set(originals)
            if unexpected: raise ControllerError(f"Unexpected changed files: {sorted(unexpected)}", 5)
            touched.append(relative)
            for validator in entry.get("post_fix_validators", []):
                if not isinstance(validator, list) or not validator: raise ControllerError("Malformed validator", 4)
                result = run(validator, root, 120)
                if result.returncode: raise ControllerError(f"Validator failed for {relative}", 3)
    except ControllerError:
        for relative, data in originals.items():
            path = safe_path(root, relative)
            with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle: handle.write(data); temp = Path(handle.name)
            os.replace(temp, path)
        raise
    receipt = {"changed_paths": touched, "head": state["head"], "schema": "aios.repository_cleanup.apply_receipt.v1", "staged": False, "committed": False,
               "status_before": sorted(before_status)}
    if runtime_is_ignored(root): atomic_write(root / RUNTIME / RECEIPT_JSON, stable_json(receipt))
    return receipt


def execute(command: str, root: Path, plan_path: Path | None = None, confirmed: bool = False) -> int:
    root = root.resolve()
    if command == "apply":
        if plan_path is None: raise ControllerError("APPLY requires --plan", 2)
        apply_plan(root, plan_path if plan_path.is_absolute() else root / plan_path, confirmed); return 0
    report = audit_repository(root)
    ignored = runtime_is_ignored(root)
    if command in {"audit", "verify"}:
        if ignored:
            atomic_write(root / RUNTIME / AUDIT_JSON, stable_json(report)); atomic_write(root / RUNTIME / AUDIT_MD, markdown_report(report))
        else: print(stable_json(report), end="")
    elif command == "plan":
        plan = build_plan(report, root)
        if ignored: atomic_write(root / RUNTIME / PLAN_JSON, stable_json(plan))
        else: print(stable_json(plan), end="")
    blocking = any(status == "BLOCKED" for status in report["categories"].values())
    warnings = any(status == "WARN" for status in report["categories"].values())
    return 2 if blocking else (1 if warnings else 0)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)
    for command in ("audit", "plan", "verify"):
        child = subparsers.add_parser(command); child.add_argument("--repo-root", required=True, type=Path)
    apply = subparsers.add_parser("apply"); apply.add_argument("--repo-root", required=True, type=Path)
    apply.add_argument("--plan", required=True, type=Path); apply.add_argument("--confirm-safe-apply", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try: return execute(args.command, args.repo_root, getattr(args, "plan", None), getattr(args, "confirm_safe_apply", False))
    except ControllerError as exc:
        print(redact(str(exc)), file=sys.stderr); return exc.code


if __name__ == "__main__":
    raise SystemExit(main())
