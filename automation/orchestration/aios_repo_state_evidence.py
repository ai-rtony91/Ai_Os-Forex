"""AI_OS repo-state evidence bridge.

Generates a deterministic read-only JSON report for the Autonomy Decision
Governor. It runs safe git inspection commands only and mutates nothing except
the declared report output path.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_OUTPUT = Path("Reports") / "repo_state" / "AIOS_REPO_STATE_LATEST.json"
Runner = Callable[..., subprocess.CompletedProcess[str]]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _completed(
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
    args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=args or [], returncode=returncode, stdout=stdout, stderr=stderr)


def _run_git(repo_root: Path, args: list[str], runner: Runner = subprocess.run) -> subprocess.CompletedProcess[str]:
    try:
        return runner(
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            shell=False,
            check=False,
            timeout=20,
        )
    except FileNotFoundError:
        return _completed(returncode=127, stderr="git executable not found", args=["git", *args])
    except subprocess.TimeoutExpired:
        return _completed(returncode=124, stderr="git command timed out", args=["git", *args])



def collect_repo_identity(
    repo_root: str | Path,
    *,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    """Read Git's worktree identity without parsing status or editing metadata."""
    root = Path(repo_root).resolve()
    identity: dict[str, Any] = {
        "resolved": False,
        "reason": "git_unavailable",
        "repo_root": str(root),
        "git_dir": None,
        "branch": "unknown",
        "symbolic_ref": None,
        "detached": None,
        "commit": None,
    }

    def inspect(args: list[str]) -> subprocess.CompletedProcess[str]:
        result = _run_git(root, ["--no-optional-locks", *args], runner)
        if result.returncode == 127:
            raise FileNotFoundError("git")
        if result.returncode == 124:
            raise subprocess.TimeoutExpired("git", 20)
        return result

    def single_line(value: str) -> str:
        value = value.rstrip("\r\n")
        return value if value and not any(character in value for character in "\r\n\x00") else ""

    def absolute_path(value: str) -> str | None:
        value = single_line(value)
        return str(Path(value).resolve()) if value and Path(value).is_absolute() else None

    try:
        result = inspect(["rev-parse", "--show-toplevel"])
        if result.returncode != 0:
            identity["reason"] = "not_inside_git_worktree"
            return identity
        git_root = absolute_path(result.stdout)
        if git_root is None:
            identity["reason"] = "git_root_unresolved"
            return identity
        identity["repo_root"] = git_root
        root = Path(git_root)

        result = inspect(["rev-parse", "--absolute-git-dir"])
        git_dir = absolute_path(result.stdout) if result.returncode == 0 else None
        if git_dir is None:
            identity["reason"] = "git_dir_unresolved"
            return identity
        identity["git_dir"] = git_dir

        result = inspect(["symbolic-ref", "--quiet", "HEAD"])
        if result.returncode == 0:
            ref = single_line(result.stdout)
            if not ref.startswith("refs/heads/") or not ref[len("refs/heads/"):]:
                identity["reason"] = "git_branch_unresolved"
                return identity
            identity.update(branch=ref[len("refs/heads/"):], symbolic_ref=ref, detached=False)
        elif result.returncode == 1 and not result.stdout.strip():
            identity.update(branch="detached", symbolic_ref=None, detached=True)
        else:
            identity["reason"] = "git_branch_unresolved"
            return identity

        result = inspect(["rev-parse", "--verify", "HEAD^{commit}"])
        commit = single_line(result.stdout) if result.returncode == 0 else ""
        if not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", commit):
            identity["reason"] = "git_commit_unresolved"
            return identity
        identity.update(commit=commit.lower(), resolved=True, reason="resolved")
    except FileNotFoundError:
        identity["reason"] = "git_unavailable"
    except subprocess.TimeoutExpired:
        identity["reason"] = "git_timeout"
    except (OSError, ValueError, UnicodeError):
        identity["reason"] = "git_inspection_failed"
    return identity


def collect_planner_repository_state(repo_root: str | Path, *, runner: Runner = subprocess.run) -> dict[str, Any] | None:
    """Observe preview identity only; this does not assert cleanliness or grant APPLY."""
    identity = collect_repo_identity(repo_root, runner=runner)
    if not identity["resolved"] or identity["detached"] is not False:
        return None
    return {"worktree": identity["repo_root"], "branch": identity["branch"], "commit": identity["commit"]}


def _valid_status_code(code: str) -> bool:
    ordinary = {x + y for x in "MTARC" for y in " MTD"}
    ordinary.update({" M", " T", " D", " A", " R", " C", "D "})
    return code in ordinary | {"??", "DD", "AU", "UD", "UA", "DU", "AA", "UU"}


def _status_path_bytes(value: bytes) -> str:
    if not value or any(part in {b"", b".", b".."} for part in value.split(b"/")):
        raise ValueError("invalid_status_path")
    # Git -z emits raw pathname bytes. This reversible contract never uses the
    # platform locale, strips whitespace, or interprets quoting/backslashes.
    return value.decode("utf-8", errors="surrogateescape")


def parse_git_status_z(payload: bytes) -> dict[str, Any]:
    """Parse porcelain v1 -z, retaining both rename/copy endpoints and errors.

    A rename/copy is destination NUL source NUL (opposite the text display).
    UTF-8 plus surrogateescape makes every non-NUL filename byte reversible.
    Valid neighbors survive malformed input so security policy retains priority.
    """
    result: dict[str, Any] = {"entries": [], "branch_line": "", "errors": []}
    if not isinstance(payload, bytes):
        result["errors"].append("status_not_bytes")
        return result
    if not payload:
        return result
    fields = payload.split(b"\0")
    if fields[-1] == b"":
        fields.pop()
    else:
        result["errors"].append("unterminated_status_record")
    index = 0
    while index < len(fields):
        record = fields[index]
        index += 1
        if record.startswith(b"## "):
            if index != 1 or result["branch_line"]:
                result["errors"].append("misplaced_branch_record")
            else:
                result["branch_line"] = record.decode("utf-8", errors="surrogateescape")
            continue
        try:
            code = record[:2].decode("ascii")
            if len(record) < 4 or record[2:3] != b" " or not _valid_status_code(code):
                raise ValueError("invalid_status_record")
            entry = {"git_code": code, "path": _status_path_bytes(record[3:])}
        except (ValueError, UnicodeError):
            result["errors"].append("invalid_status_record")
            continue
        result["entries"].append(entry)
        if "R" in code or "C" in code:
            if index >= len(fields):
                result["errors"].append("missing_rename_source")
                continue
            source = fields[index]
            index += 1
            try:
                entry["source_path"] = _status_path_bytes(source)
            except ValueError:
                result["errors"].append("invalid_rename_source")
    return result


def _decode_git_text_path(value: bytes) -> bytes:
    if not value.startswith(b'"'):
        if not value or b"\0" in value:
            raise ValueError("invalid_text_path")
        return value
    if len(value) < 2 or not value.endswith(b'"'):
        raise ValueError("invalid_git_quoting")
    escaped = {ord("a"): 7, ord("b"): 8, ord("t"): 9, ord("n"): 10,
               ord("v"): 11, ord("f"): 12, ord("r"): 13, ord('"'): 34, ord("\\"): 92}
    out = bytearray()
    index = 1
    while index < len(value) - 1:
        current = value[index]
        index += 1
        if current == ord('"'):
            raise ValueError("invalid_git_quoting")
        if current != ord("\\"):
            out.append(current)
            continue
        if index >= len(value) - 1:
            raise ValueError("invalid_git_escape")
        current = value[index]
        index += 1
        if current in escaped:
            out.append(escaped[current])
        elif ord("0") <= current <= ord("3"):
            octal = bytes([current]) + value[index:index + 2]
            if len(octal) != 3 or any(char not in b"01234567" for char in octal):
                raise ValueError("invalid_git_octal")
            out.append(int(octal, 8))
            index += 2
        else:
            raise ValueError("invalid_git_escape")
    if not out or 0 in out:
        raise ValueError("invalid_text_path")
    return bytes(out)


def _text_rename_endpoints(value: bytes) -> tuple[bytes, bytes]:
    separators = []
    quoted = False
    escaped = False
    for index, current in enumerate(value):
        if escaped:
            escaped = False
        elif quoted and current == ord("\\"):
            escaped = True
        elif current == ord('"'):
            quoted = not quoted
        elif not quoted and value[index:index + 4] == b" -> ":
            separators.append(index)
    if quoted or len(separators) != 1:
        raise ValueError("ambiguous_text_rename")
    at = separators[0]
    return _decode_git_text_path(value[:at]), _decode_git_text_path(value[at + 4:])


def parse_git_status_text_lines(status_lines: list[str]) -> dict[str, Any]:
    """Diagnostic/legacy adapter only; live collection always uses raw -z."""
    if not isinstance(status_lines, list):
        return {"entries": [], "branch_line": "", "errors": ["status_not_text_lines"]}
    chunks: list[bytes] = []
    errors: list[str] = []
    for raw in status_lines:
        try:
            if not isinstance(raw, str):
                raise ValueError("invalid_text_record")
            line = raw.removesuffix("\n").removesuffix("\r")
            if not line:
                continue
            record = line.encode("utf-8", errors="surrogateescape")
            if record.startswith(b"## "):
                chunks.append(record + b"\0")
                continue
            code = record[:2].decode("ascii")
            if len(record) < 4 or record[2:3] != b" " or not _valid_status_code(code):
                raise ValueError("invalid_text_record")
            if "R" in code or "C" in code:
                source, destination = _text_rename_endpoints(record[3:])
                chunks.append(record[:3] + destination + b"\0" + source + b"\0")
            else:
                chunks.append(record[:3] + _decode_git_text_path(record[3:]) + b"\0")
        except (ValueError, UnicodeError):
            errors.append("invalid_text_status_record")
    parsed = parse_git_status_z(b"".join(chunks))
    parsed["errors"] = errors + parsed["errors"]
    return parsed


def _status_path(line: str) -> str:
    parsed = parse_git_status_text_lines([line])
    if parsed["errors"]:
        raise ValueError("invalid_git_status")
    return parsed["entries"][0]["path"] if parsed["entries"] else ""


def _run_git_status(repo_root: Path, runner: Runner) -> subprocess.CompletedProcess[bytes]:
    args = ["git", "--no-optional-locks", "status", "--porcelain=v1", "-z", "--branch", "--untracked-files=all"]
    try:
        return runner(args, cwd=str(repo_root), capture_output=True, text=False, shell=False, check=False, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return subprocess.CompletedProcess(args, 1, stdout=b"", stderr=b"")


def _parse_ahead_behind(branch_line: str) -> dict[str, Any]:
    ahead = None
    behind = None
    ahead_match = re.search(r"ahead\s+(\d+)", branch_line)
    behind_match = re.search(r"behind\s+(\d+)", branch_line)
    if ahead_match:
        ahead = int(ahead_match.group(1))
    if behind_match:
        behind = int(behind_match.group(1))
    return {"ahead": ahead, "behind": behind, "raw": branch_line}


def capture_status_evidence(payload: bytes) -> dict[str, Any]:
    """Retain original Git stdout, including invalid observations for diagnosis."""
    if type(payload) is not bytes or len(payload) > 16777216:
        raise ValueError("status_original_bytes_unavailable")
    parsed = parse_git_status_z(payload)
    paths = sorted({entry[key] for entry in parsed["entries"] for key in ("path", "source_path") if key in entry})
    return {"raw_base64": base64.b64encode(payload).decode("ascii"),
            "sha256": hashlib.sha256(payload).hexdigest(), "paths": paths}


def validate_status_evidence(value: Any) -> dict[str, Any]:
    """Validate saved bytes; display text and caller-supplied path lists are not originals."""
    try:
        if (type(value) is not dict or set(value) != {"raw_base64", "sha256", "paths"}
                or type(value["raw_base64"]) is not str or len(value["raw_base64"]) > 22369624
                or type(value["sha256"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"])
                or type(value["paths"]) is not list or any(type(path) is not str for path in value["paths"])):
            raise ValueError("invalid status shape")
        payload = base64.b64decode(value["raw_base64"], validate=True)
        expected = capture_status_evidence(payload)
        parsed = parse_git_status_z(payload)
        if value != expected or parsed["errors"] or not parsed["branch_line"]:
            raise ValueError("invalid or changed status")
        return expected
    except (ValueError, TypeError, UnicodeError) as error:
        raise ValueError("status_original_evidence_invalid") from error


def _base_report(repo_root: Path, generated_at_utc: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "system": "AI_OS",
        "component": "repo_state_evidence",
        "generated_at_utc": generated_at_utc,
        "repo_root": str(repo_root),
        "branch": "",
        "git_available": False,
        "inside_worktree": False,
        "is_clean": None,
        "status_short": [],
        "status_evidence": None,
        "status_entries": [],
        "status_parse_errors": [],
        "tracked_dirty_files": [],
        "untracked_files": [],
        "staged_files": [],
        "ahead_behind": {"ahead": None, "behind": None, "raw": ""},
        "safe_for_apply": False,
        "blocked_reason": "git_unavailable",
        "evidence_quality": "missing",
    }


def collect_repo_state(
    repo_root: str | Path | None = None,
    *,
    generated_at_utc: str | None = None,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    root = Path(repo_root or Path.cwd()).resolve()
    report = _base_report(root, generated_at_utc or utc_now())

    git_root_result = _run_git(root, ["rev-parse", "--show-toplevel"], runner)
    if git_root_result.returncode == 127:
        return report
    report["git_available"] = True
    if git_root_result.returncode != 0:
        report["blocked_reason"] = "not_inside_git_worktree"
        report["evidence_quality"] = "missing"
        return report

    git_root = Path(git_root_result.stdout.strip()).resolve()
    report["repo_root"] = str(git_root)
    report["inside_worktree"] = True

    branch_result = _run_git(git_root, ["branch", "--show-current"], runner)
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else ""
    report["branch"] = branch

    status_result = _run_git_status(git_root, runner)
    if status_result.returncode != 0:
        report["blocked_reason"] = "git_status_failed"
        report["evidence_quality"] = "partial"
        return report

    if type(status_result.stdout) is bytes:
        try:
            report["status_evidence"] = capture_status_evidence(status_result.stdout)
        except ValueError:
            report.update(blocked_reason="git_status_export_unavailable", evidence_quality="partial")
            return report
    parsed = parse_git_status_z(status_result.stdout)
    branch_line = parsed["branch_line"]
    entries = parsed["entries"]
    # Display strings are never reparsed as filename identity.
    status_lines = ([branch_line] if branch_line else []) + [
        entry["git_code"] + " " + json.dumps(entry["path"], ensure_ascii=True)
        + (" (source " + json.dumps(entry["source_path"], ensure_ascii=True) + ")" if "source_path" in entry else "")
        for entry in entries
    ]
    tracked_dirty: list[str] = []
    untracked: list[str] = []
    staged: list[str] = []
    for entry in entries:
        code = entry["git_code"]
        for path in dict.fromkeys([entry["path"], *([entry["source_path"]] if "source_path" in entry else [])]):
            if code == "??":
                untracked.append(path)
                continue
            tracked_dirty.append(path)
            if code[0] != " ":
                staged.append(path)

    is_clean = not entries and not parsed["errors"]
    branch_known = bool(branch)
    safe_for_apply = bool(report["inside_worktree"] and branch_known and is_clean)

    report.update(
        {
            "status_short": status_lines,
            "status_entries": entries,
            "status_parse_errors": parsed["errors"],
            "tracked_dirty_files": tracked_dirty,
            "untracked_files": untracked,
            "staged_files": staged,
            "ahead_behind": _parse_ahead_behind(branch_line),
            "is_clean": is_clean,
            "safe_for_apply": safe_for_apply,
            "evidence_quality": "strong" if branch_known else "partial",
            "blocked_reason": None,
        }
    )

    if parsed["errors"]:
        report["safe_for_apply"] = False
        report["is_clean"] = None
        report["blocked_reason"] = "git_status_parse_failed"
        report["evidence_quality"] = "partial"
    elif not branch_known:
        report["safe_for_apply"] = False
        report["blocked_reason"] = "branch_unknown"
        report["evidence_quality"] = "partial"
    elif not is_clean:
        report["blocked_reason"] = "dirty_working_tree"

    return report



# Campaign observations are separate from the legacy clean-only safety facts.
# These values cannot approve a task or runtime operation. The actual native
# admission/receiving caller remains independently qualified outside this API.
@dataclass(frozen=True)
class CampaignPacketProfile:
    selection: tuple[str, str, str, str, str]
    reference_sha256: str
    queue_item_json: str


@dataclass(frozen=True)
class CampaignPacketEvidence:
    contract_json: str
    repository_state_json: str


CAMPAIGN_SOURCE_SCHEMA = "AIOS_CAMPAIGN_PACKET_SOURCE.v1"
CAMPAIGN_PROTECTED = (
    "AGENTS.md", "README.md", "RISK_POLICY.md",
    "automation/orchestration/execution_registry/AIOS_EXECUTION_CLASSIFICATION_REGISTRY.json",
    "automation/orchestration/validators/Invoke-AiOsExecutionRegistryGuard.ps1",
)
CAMPAIGN_IMPLEMENTATIONS = (
    "automation/orchestration/aios_repo_state_evidence.py",
    "automation/orchestration/aios_codex_packet_builder.py",
    "automation/orchestration/runtime_queue/aios_execution_packet_resolver.py",
    "automation/orchestration/aios_abcd_autonomy_runner.py",
)


def campaign_json(value: Any) -> str:
    """Strict JSON bytes decide identity; bool/int/float aliases cannot compare."""
    def check(item):
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ValueError("campaign object keys must be strings")
            for child in item.values():
                check(child)
        elif type(item) is list:
            for child in item:
                check(child)
        elif item is not None and type(item) not in {str, int, bool}:
            raise ValueError("campaign input has unsupported raw type")
    try:
        check(value)
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, RecursionError) as exc:
        raise ValueError("invalid campaign JSON") from exc


def _campaign_load(raw: str | bytes) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate campaign JSON key")
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite campaign JSON")))
    except (TypeError, UnicodeError, RecursionError) as exc:
        raise ValueError("invalid campaign JSON encoding/shape") from exc
    campaign_json(value)
    return value


def _campaign_digest(value: Any) -> str:
    return hashlib.sha256(campaign_json(value).encode("ascii")).hexdigest()


def _campaign_selection(selection: Any) -> None:
    if type(selection) is not tuple or len(selection) != 5 or any(type(value) is not str or not value for value in selection):
        raise ValueError("campaign selection raw types invalid")
    if any(not re.fullmatch(r"[0-9a-f]{64}", selection[index]) for index in (2, 3)):
        raise ValueError("campaign selection digest invalid")
    try:
        acquired = datetime.fromisoformat(selection[4])
        if acquired.tzinfo is None or acquired.utcoffset().total_seconds() != 0:
            raise ValueError("campaign claim timestamp must be UTC")
    except (ValueError, OverflowError) as exc:
        raise ValueError("campaign claim timestamp invalid") from exc


def verify_campaign_packet_profile(
    profile: CampaignPacketProfile,
    *,
    admission_reader: Callable | None,
    selection: tuple[str, str, str, str, str] | None,
    repository_state: dict[str, Any],
    queue_item: dict[str, Any] | None = None,
    runner: Runner | None = None,
) -> CampaignPacketEvidence:
    """Independently observe a source-qualified admitted request, never approve it.

    The caller must qualify the executable reader against the existing exact
    campaign authorization/reference. A profile class/JSON/flag cannot waive
    this reader or the current owner I/O below. Fixture readers and runners
    establish component behavior only, never native admission or runtime rights.
    The reader returns the pinned reference's original bytes for this selection;
    unknown, conflicting or unauthorized reference evidence must raise.
    """
    from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import (
        bound_path,
        source_relative,
    )
    if type(profile) is not CampaignPacketProfile or not callable(admission_reader):
        raise ValueError("campaign profile requires qualified admission reader")
    _campaign_selection(profile.selection)
    _campaign_selection(selection)
    if profile.selection != selection or type(profile.reference_sha256) is not str or not re.fullmatch(r"[0-9a-f]{64}", profile.reference_sha256):
        raise ValueError("campaign profile selection/reference mismatch")
    if type(profile.queue_item_json) is not str:
        raise ValueError("campaign packet request raw type invalid")
    saved_item = _campaign_load(profile.queue_item_json)
    if type(saved_item) is not dict or campaign_json(saved_item) != profile.queue_item_json:
        raise ValueError("campaign packet request is not canonical")
    if queue_item is not None and campaign_json(queue_item) != profile.queue_item_json:
        raise ValueError("campaign selected packet request changed")
    try:
        raw = admission_reader(selection)
    except Exception as exc:
        raise ValueError(f"campaign admission reader failed: {exc}") from exc
    if type(raw) is not bytes or hashlib.sha256(raw).hexdigest() != profile.reference_sha256:
        raise ValueError("campaign admission reference changed or has invalid raw type")
    contract = _campaign_load(raw)
    fields = {"schema", "selection", "queue_item_sha256", "repository_identity", "status_sha256", "inventory",
              "immutable_manifest", "protected_pins", "allowed_paths", "forbidden_paths", "validators",
              "approval_authority", "git_actions", "delivery"}
    if type(contract) is not dict or set(contract) != fields or contract["schema"] != CAMPAIGN_SOURCE_SCHEMA:
        raise ValueError("campaign admission reference shape invalid")
    if campaign_json(contract["selection"]) != campaign_json(list(selection)) or contract["queue_item_sha256"] != _campaign_digest(saved_item):
        raise ValueError("campaign admission task/request/claim mismatch")
    if saved_item.get("packet_id") != selection[1] or contract["git_actions"] != [] or type(contract["git_actions"]) is not list:
        raise ValueError("campaign task identity or no-Git contract invalid")
    packet_identity = saved_item.get("packet_identity")
    if (type(packet_identity) is not dict or type(packet_identity.get("packet_id")) is not str
            or packet_identity["packet_id"] != selection[1]):
        raise ValueError("campaign nested packet identity differs from selection")
    if (saved_item.get("mode") != "APPLY" or saved_item.get("approval_state") != "APPROVED"
            or type(saved_item.get("protected_action", False)) is not bool or saved_item.get("protected_action", False)):
        raise ValueError("campaign mode/approval/protected contract invalid")
    for name in ("attempt", "max_attempts"):
        if type(saved_item.get(name)) is not int or saved_item[name] < 0:
            raise ValueError("campaign attempt raw type invalid")
    if saved_item["attempt"] >= saved_item["max_attempts"]:
        raise ValueError("campaign attempts exhausted")
    for name in ("commit_message", "pr_authority"):
        if name in saved_item and (type(saved_item[name]) is not str or saved_item[name]):
            raise ValueError("campaign forbids commit/PR instructions")
    for name in ("allowed_paths", "forbidden_paths", "validators"):
        values = contract[name]
        if type(values) is not list or not values or any(type(value) is not str or not value for value in values) or len(set(values)) != len(values):
            raise ValueError("campaign scope/validator raw types invalid")
        if campaign_json(values) != campaign_json(saved_item.get(name)):
            raise ValueError("campaign scope/validator contract changed")
    if type(contract["approval_authority"]) is not str or not contract["approval_authority"] or contract["approval_authority"] != saved_item.get("approval_authority"):
        raise ValueError("campaign authority reference changed")
    expected = contract["repository_identity"]
    identity_fields = {"resolved", "reason", "repo_root", "git_dir", "branch", "symbolic_ref", "detached", "commit"}
    if (type(expected) is not dict or set(expected) != identity_fields or expected["resolved"] is not True
            or expected["detached"] is not False or any(type(expected[name]) is not str or not expected[name]
                for name in identity_fields - {"resolved", "detached"}) or expected["reason"] != "resolved"):
        raise ValueError("campaign expected repository identity invalid")
    root = bound_path(expected["repo_root"])
    bound_path(expected["git_dir"])
    if (type(repository_state) is not dict or repository_state.get("worktree") != str(root)
            or repository_state.get("branch") != expected["branch"]):
        raise ValueError("campaign supplied repository identity differs")
    allowed_targets = {bound_path(str(root / source_relative(relative)), root=root) for relative in contract["allowed_paths"]}
    forbidden_targets = {bound_path(str(root / relative), root=root) for relative in contract["forbidden_paths"]}
    if allowed_targets & forbidden_targets:
        raise ValueError("campaign canonical allowed/forbidden paths conflict")
    run = runner if runner is not None else subprocess.run
    first_identity = collect_repo_identity(root, runner=run)
    if campaign_json(first_identity) != campaign_json(expected):
        raise ValueError("campaign current repository identity changed")
    status = _run_git_status(root, run)
    if type(status.returncode) is not int or status.returncode != 0 or type(status.stdout) is not bytes:
        raise ValueError("campaign raw status unavailable")
    parsed = parse_git_status_z(status.stdout)
    if parsed["errors"] or not parsed["branch_line"] or hashlib.sha256(status.stdout).hexdigest() != contract["status_sha256"]:
        raise ValueError("campaign raw status changed or invalid")
    display = [parsed["branch_line"]] + [entry["git_code"] + " " + json.dumps(entry["path"], ensure_ascii=True)
        + (" (source " + json.dumps(entry["source_path"], ensure_ascii=True) + ")" if "source_path" in entry else "")
        for entry in parsed["entries"]]
    if campaign_json(repository_state.get("status_lines")) != campaign_json(display):
        raise ValueError("campaign supplied status differs from actual owner observation")
    inventory = contract["inventory"]
    manifests = (contract["immutable_manifest"], contract["protected_pins"])
    if type(inventory) is not dict or not inventory or any(type(value) is not dict for value in manifests):
        raise ValueError("campaign inventory/manifests invalid")
    if not set(CAMPAIGN_PROTECTED).issubset(manifests[1]) or not set(CAMPAIGN_IMPLEMENTATIONS).issubset(manifests[0]):
        raise ValueError("campaign protected/implementation coverage missing")
    if set(contract["allowed_paths"]) & (set(manifests[0]) | set(manifests[1])):
        raise ValueError("campaign writable immutable/protected input")
    covered = set(contract["allowed_paths"]) | set(manifests[0]) | set(manifests[1])
    for entry in parsed["entries"]:
        covered.add(entry["path"])
        if "source_path" in entry:
            covered.add(entry["source_path"])
    if not covered.issubset(inventory):
        raise ValueError("campaign unknown status/inventory endpoint")
    for relative, observation in inventory.items():
        source_relative(relative)
        path = bound_path(str(root / relative), root=root)
        if type(observation) is not dict or set(observation) != {"exists", "sha256"} or type(observation["exists"]) is not bool:
            raise ValueError("campaign inventory observation raw types invalid")
        digest = observation["sha256"]
        if observation["exists"]:
            if type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError("campaign current inventory bytes changed")
        elif digest is not None or path.exists():
            raise ValueError("campaign expected absent target changed")
    for manifest in manifests:
        for relative, digest in manifest.items():
            if type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest) or inventory.get(relative) != {"exists": True, "sha256": digest}:
                raise ValueError("campaign immutable/protected pin differs")
    delivery = contract["delivery"]
    if type(delivery) is not dict or set(delivery) != {"runtime_dir", "terminal_dir", "metadata_path", "event_log_path"}:
        raise ValueError("campaign delivery destinations invalid")
    destinations = []
    for value in delivery.values():
        destination = bound_path(value, root=root)
        source_relative(destination.relative_to(root).as_posix())
        if destination == root or any(destination == other for other in destinations):
            raise ValueError("campaign delivery destinations conflict")
        for relative in set(contract["allowed_paths"]) | set(manifests[0]) | set(manifests[1]):
            target = bound_path(str(root / source_relative(relative)), root=root)
            if destination == target or destination in target.parents or target in destination.parents:
                raise ValueError("campaign source/immutable/protected delivery scopes overlap")
        destinations.append(destination)
    last_status = _run_git_status(root, run)
    last_identity = collect_repo_identity(root, runner=run)
    if (type(last_status.returncode) is not int or last_status.returncode != 0 or type(last_status.stdout) is not bytes
            or last_status.stdout != status.stdout or campaign_json(last_identity) != campaign_json(first_identity)):
        raise ValueError("campaign observation changed during collection")
    # Re-read explicit bytes after the status/identity bracket as well: Git
    # status can stay identical while a dirty file's bytes change again.
    for relative, observation in inventory.items():
        path = bound_path(str(root / relative), root=root)
        if observation["exists"]:
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != observation["sha256"]:
                raise ValueError("campaign bytes changed during collection")
        elif path.exists():
            raise ValueError("campaign absent target changed during collection")
    state = {"worktree": str(root), "branch": expected["branch"], "status_lines": display,
             "status_entries": parsed["entries"], "status_sha256": contract["status_sha256"],
             "is_clean": not parsed["entries"], "safe_for_apply": not parsed["entries"]}
    return CampaignPacketEvidence(campaign_json(contract), campaign_json(state))


def write_repo_state_report(
    repo_root: str | Path,
    report: dict[str, Any],
    output_path: str | Path | None = None,
) -> Path:
    root = Path(repo_root).resolve()
    target = Path(output_path) if output_path is not None else root / DEFAULT_OUTPUT
    if not target.is_absolute():
        target = root / target
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(report, indent=2, sort_keys=True))
            handle.write("\n")
        os.replace(tmp_name, target)
    except Exception:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        raise
    return target


def main(repo_root: str | Path | None = None, output_path: str | Path | None = None) -> dict[str, Any]:
    root = Path(repo_root or Path.cwd()).resolve()
    report = collect_repo_state(root)
    write_repo_state_report(root, report, output_path)
    return report


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Emit AI_OS repo-state evidence JSON.")
    parser.add_argument("--repo-root", default=".", help="Repository root to inspect.")
    parser.add_argument("--output-path", default=None, help="Optional report output path.")
    args = parser.parse_args()
    report = main(repo_root=args.repo_root, output_path=args.output_path)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())


# Opt-in bounded acquisition. A binding identifies observations; it is not read
# permission, a native execution interval, approval, or runtime admission.
FULL_WORKTREE_CAPTURE_RULES_DESCRIPTOR = (
    "AIOS_FULL_WORKTREE_CAPTURE_RULES.v1\n"
    "domain=entire_worktree_subtree\n"
    "platform=nt\n"
    "path_identity=raw_utf8_surrogateescape_no_normalization\n"
    "census=all_named_entries_no_exclusions\n"
    "content=ordinary_default_stream_only\n"
    "metadata=mode,device,inode,size,mtime_ns,ctime_ns,file_attributes\n"
    "nt_ctime=creation_time;change_time=internal_stability_guard\n"
    "acquisition=retained_parent_handle_single_component_no_follow\n"
    "payload=validated_same_file_handle_before_read\n"
    "refuse=private,reparse,nonregular,multilink,alternate_stream,offline,recall,remote\n"
    "uncertainty=explicit_incomplete_or_root_unavailable\n"
    "manifest=AIOS_WORKTREE_STATE_MANIFEST.v1\n"
    "canonical=ascii_sorted_compact_json_final_newline\n"
    "manifest_limit_bytes=16777216\n"
    "authority=caller_admission_separate_not_conferred_by_rules_digest\n"
)
FULL_WORKTREE_CAPTURE_RULES_SHA256 = hashlib.sha256(
    FULL_WORKTREE_CAPTURE_RULES_DESCRIPTOR.encode("ascii")
).hexdigest()
NONPRIVATE_WORKTREE_CAPTURE_RULES_DESCRIPTOR = (
    "AIOS_NONPRIVATE_WORKTREE_CAPTURE_RULES.v1\n"
    "domain=nonprivate_contents_with_private_boundaries\n"
    "platform=nt\n"
    "path_identity=raw_utf8_surrogateescape_no_normalization\n"
    "census=all_named_entries;private_descendants_not_enumerated\n"
    "content=nonprivate_ordinary_default_stream_only\n"
    "metadata=mode,device,inode,size,mtime_ns,ctime_ns,file_attributes\n"
    "nt_ctime=creation_time;change_time=internal_stability_guard\n"
    "acquisition=retained_parent_handle_single_component_no_follow\n"
    "payload=validated_same_file_handle_before_read\n"
    "private=parent_census_identity_and_attributes_only;no_endpoint_open_or_descendant_walk\n"
    "private_contents_observed=false;full_preservation_not_established\n"
    "refuse_nonprivate=reparse,nonregular,multilink,alternate_stream,offline,recall,remote\n"
    "uncertainty=explicit_incomplete_or_root_unavailable\n"
    "manifest=AIOS_NONPRIVATE_WORKTREE_STATE_MANIFEST.v1\n"
    "canonical=ascii_sorted_compact_json_final_newline\n"
    "manifest_limit_bytes=16777216\n"
    "authority=caller_admission_separate_not_conferred_by_rules_digest\n"
)
NONPRIVATE_WORKTREE_CAPTURE_RULES_SHA256 = hashlib.sha256(
    NONPRIVATE_WORKTREE_CAPTURE_RULES_DESCRIPTOR.encode("ascii")
).hexdigest()


def nonprivate_capture_contract() -> dict[str, str]:
    return {"schema": "AIOS_NONPRIVATE_WORKTREE_STATE_CAPTURE.v1",
            "domain": "nonprivate_contents_with_private_boundaries", "platform": "nt",
            "rules_sha256": NONPRIVATE_WORKTREE_CAPTURE_RULES_SHA256}


def private_root_boundaries(root: str | Path) -> list[str]:
    """Names only, for an early known-refusal check; not a full-tree safety proof."""
    import time
    path = Path(root)
    if not path.is_absolute() or any(_full_capture_private(part) for part in path.parts):
        raise ValueError("private_or_relative_capture_root")
    from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import bound_path
    path = bound_path(str(path))
    deadline = time.monotonic() + 5
    boundaries = []
    with os.scandir(path) as entries:
        for count, entry in enumerate(entries, 1):
            if count > 10000 or time.monotonic() > deadline:
                raise ValueError("private_boundary_name_check_incomplete")
            # Do not ask this entry for metadata, a handle, children or bytes.
            if _full_capture_private(entry.name):
                boundaries.append(entry.name)
    return sorted(boundaries)


_FULL_CAPTURE_MAX_DEPTH = 128
_FULL_CAPTURE_MAX_PATH_CHARS = 32768
_FULL_CAPTURE_MAX_RELATIVE_CHARS = 4096
_FULL_CAPTURE_MAX_BINDING_TEXT_CHARS = 1048576


class _FullWorktreeCaptureUnavailable(ValueError):
    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        super().__init__("capture_unavailable:" + reason + (":" + detail if detail else ""))


class _FullCaptureFailure(Exception):
    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(reason + (":" + detail if detail else ""))


def _full_capture_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")


def _full_capture_text(value: Any) -> bool:
    if (type(value) is not str or not value or len(value) > _FULL_CAPTURE_MAX_PATH_CHARS
            or "\0" in value):
        return False
    try:
        value.encode("utf-8", "surrogateescape")
    except UnicodeError:
        return False
    return True


def _full_capture_name(value: Any) -> bool:
    if (not _full_capture_text(value) or value in {".", ".."}
            or any(char in value for char in "/\\:") or value.endswith((".", " "))):
        return False
    stem = value.split(".", 1)[0].upper()
    return not (stem in {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
                or re.fullmatch(r"(?:COM|LPT)[1-9¹²³]", stem))


def _full_capture_private(path: str) -> bool:
    lower = path.casefold()
    parts = lower.split("/")
    tokens = {".git", ".aws", ".codex", ".ssh", "approval", "approvals", "secret", "secrets",
              "credential", "credentials", "private"}
    return (any(part in tokens or part == ".env" or part.startswith(".env.") for part in parts)
            or lower.startswith(".env") or parts[0] in {"control", "runtime"}
            or lower == "automation/orchestration/approval_inbox"
            or lower.startswith("automation/orchestration/approval_inbox/")
            or parts[-1] in {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"}
            or lower.endswith((".pem", ".pfx", ".p12", ".key")))


def _full_capture_relative(value: Any) -> bool:
    return (type(value) is str and 0 < len(value) <= _FULL_CAPTURE_MAX_RELATIVE_CHARS
            and value.count("/") < _FULL_CAPTURE_MAX_DEPTH
            and _full_capture_text(value) and all(_full_capture_name(part) for part in value.split("/"))
            and not _full_capture_private(value))


def _full_capture_validate(
    root: Any, binding: Any, phase: Any, limits: tuple[Any, ...],
) -> tuple[str, bytes, set[str], float]:
    import math
    import time
    from pathlib import PureWindowsPath

    for value, ceiling in zip(limits[:3], (10000, 16777216, 67108864)):
        if type(value) is not int or not 0 < value <= ceiling:
            raise ValueError("invalid capture budget")
    timeout = limits[3]
    if type(timeout) not in {int, float} or not 0 < timeout <= 5 or not math.isfinite(timeout):
        raise ValueError("invalid capture timeout")
    deadline = time.monotonic() + timeout
    text_characters = 0

    def tick() -> None:
        if time.monotonic() > deadline:
            raise _FullWorktreeCaptureUnavailable("budget_exceeded", "binding validation deadline")

    def text(value: Any) -> bool:
        nonlocal text_characters
        tick()
        if type(value) is not str or not value:
            return False
        if (len(value) > _FULL_CAPTURE_MAX_PATH_CHARS
                or len(value) > _FULL_CAPTURE_MAX_BINDING_TEXT_CHARS - text_characters):
            raise _FullWorktreeCaptureUnavailable("budget_exceeded", "binding text ceiling")
        text_characters += len(value)
        return _full_capture_text(value)

    if type(root) is type(Path("C:\\")):
        root = str(root)
    if type(root) is not str:
        raise ValueError("invalid capture root")
    if len(root) > _FULL_CAPTURE_MAX_PATH_CHARS or root.count("\\") > _FULL_CAPTURE_MAX_DEPTH:
        raise _FullWorktreeCaptureUnavailable("budget_exceeded", "root path ceiling")
    if (not re.fullmatch(r"[A-Za-z]:\\(?:[^\\]+(?:\\[^\\]+)*)?", root)
            or "/" in root or not all(_full_capture_name(part) for part in root[3:].split("\\") if part)):
        raise ValueError("invalid capture root")
    if type(phase) is not str or phase not in {"before", "after"}:
        raise ValueError("invalid capture phase")

    def object_fields(value: Any, fields: set[str]) -> None:
        if (type(value) is not dict or len(value) != len(fields)
                or any(type(key) is not str for key in value) or set(value) != fields):
            raise ValueError("invalid capture binding shape")

    object_fields(binding, {"task", "repository_identity", "interval_ref", "allowed_paths",
                            "max_files_changed", "implementation_manifest", "capture_contract"})
    object_fields(binding["task"], {"task_id", "packet_id", "action_id", "attempt_id"})
    if not all(text(value) for value in binding["task"].values()):
        raise ValueError("invalid capture task")
    if not text(binding["interval_ref"]):
        raise ValueError("invalid capture interval")
    repository = binding["repository_identity"]
    object_fields(repository, {"resolved", "reason", "repo_root", "git_dir", "branch",
                                "symbolic_ref", "detached", "commit"})
    if (repository["resolved"] is not True or type(repository["reason"]) is not str
            or repository["reason"] != "resolved" or type(repository["repo_root"]) is not str
            or repository["repo_root"] != root
            or not text(repository["repo_root"])
            or not all(text(repository[key]) for key in ("git_dir", "branch", "commit"))
            or not PureWindowsPath(repository["git_dir"]).is_absolute()
            or type(repository["detached"]) is not bool
            or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", repository["commit"]) is None):
        raise ValueError("invalid capture repository identity")
    if repository["detached"]:
        if repository["branch"] != "detached" or repository["symbolic_ref"] is not None:
            raise ValueError("invalid detached capture identity")
    elif (not text(repository["symbolic_ref"])
          or repository["symbolic_ref"] != "refs/heads/" + repository["branch"]):
        raise ValueError("invalid capture branch identity")
    allowed = binding["allowed_paths"]
    if (type(allowed) is not list or not allowed or type(binding["max_files_changed"]) is not int
            or binding["max_files_changed"] < 1 or binding["max_files_changed"].bit_length() > 64):
        raise ValueError("invalid capture allowed paths")
    if len(allowed) > limits[0]:
        raise _FullWorktreeCaptureUnavailable("budget_exceeded", "allowed target count")
    required: set[str] = set()
    seen_paths: set[str] = set()
    for path in allowed:
        tick()
        if type(path) is not str or not path:
            raise ValueError("invalid capture allowed path")
        if (len(path) > _FULL_CAPTURE_MAX_RELATIVE_CHARS
                or len(path) > _FULL_CAPTURE_MAX_BINDING_TEXT_CHARS - text_characters):
            raise _FullWorktreeCaptureUnavailable("budget_exceeded", "relative path text ceiling")
        text_characters += len(path)
        if path in seen_paths:
            raise ValueError("duplicate capture allowed path")
        seen_paths.add(path)
        start, depth, prefix = 0, 0, ""
        while True:
            tick()
            if depth >= _FULL_CAPTURE_MAX_DEPTH:
                raise _FullWorktreeCaptureUnavailable("budget_exceeded", "allowed path depth")
            end = path.find("/", start)
            part = path[start:] if end < 0 else path[start:end]
            if not _full_capture_name(part):
                raise ValueError("invalid capture allowed component")
            prefix = (prefix + "/" if prefix else "") + part
            if prefix not in required:
                if len(required) >= limits[0]:
                    raise _FullWorktreeCaptureUnavailable("budget_exceeded", "allowed ancestry cannot fit")
                required.add(prefix)
            if _full_capture_private(prefix):
                raise ValueError("private capture allowed path")
            depth += 1
            if end < 0:
                break
            start = end + 1
    implementation = binding["implementation_manifest"]
    if type(implementation) is not dict or not implementation:
        raise ValueError("invalid capture implementation identity")
    if len(implementation) > 10000:
        raise _FullWorktreeCaptureUnavailable("budget_exceeded", "implementation identity count")
    for key, value in implementation.items():
        if (not text(key) or type(value) is not str or len(value) != 64
                or re.fullmatch(r"[0-9a-f]{64}", value) is None or not text(value)):
            raise ValueError("invalid capture implementation identity")
    capture = binding["capture_contract"]
    object_fields(capture, {"schema", "domain", "platform", "rules_sha256"})
    expected = {"schema": "AIOS_FULL_WORKTREE_STATE_CAPTURE.v1", "domain": "entire_worktree_subtree",
                "platform": "nt", "rules_sha256": FULL_WORKTREE_CAPTURE_RULES_SHA256}
    profiles = (expected, nonprivate_capture_contract())
    if not any(all(type(capture[key]) is str and capture[key] == value for key, value in profile.items())
               for profile in profiles):
        raise ValueError("invalid capture rules or platform")
    try:
        raw = _full_capture_json(binding)
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise ValueError("invalid capture binding JSON") from error
    if len(raw) > 16777216:
        raise _FullWorktreeCaptureUnavailable("budget_exceeded", "capture binding bytes")
    tick()
    return root, raw, required, deadline


def _full_capture_directory_buffer(raw: bytes) -> list[dict[str, Any]]:
    import struct

    if type(raw) is not bytes or not 104 <= len(raw) <= 65536:
        raise _FullCaptureFailure("read_failed", "directory buffer size")
    output: list[dict[str, Any]] = []
    offset = 0
    while True:
        if offset + 104 > len(raw):
            raise _FullCaptureFailure("read_failed", "directory header bounds")
        following, _index = struct.unpack_from("<II", raw, offset)
        created, _accessed, modified, changed, size, _allocated = struct.unpack_from("<qqqqqq", raw, offset + 8)
        attributes, length, _ea = struct.unpack_from("<III", raw, offset + 56)
        short_length = raw[offset + 68]
        inode = struct.unpack_from("<Q", raw, offset + 96)[0]
        end = offset + 104 + length
        if (length == 0 or length % 2 or end > len(raw) or short_length > 24 or short_length % 2
                or size < 0 or following and (following % 8 or following < 104 + length
                                             or offset + following > len(raw))):
            raise _FullCaptureFailure("read_failed", "directory record bounds")
        name = raw[offset + 104:end].decode("utf-16-le", "surrogatepass")
        output.append({"name": name, "inode": inode, "attributes": attributes, "size": size,
                       "created": created, "modified": modified, "changed": changed})
        if not following:
            return output
        offset += following


def _full_capture_stream_buffer(raw: bytes) -> list[tuple[str, int, int]]:
    import struct

    if type(raw) is not bytes or not 24 <= len(raw) <= 65536:
        raise _FullCaptureFailure("read_failed", "stream buffer size")
    output: list[tuple[str, int, int]] = []
    offset = 0
    while True:
        if offset + 24 > len(raw):
            raise _FullCaptureFailure("read_failed", "stream header bounds")
        following, length, size, allocation = struct.unpack_from("<IIqq", raw, offset)
        end = offset + 24 + length
        if (length == 0 or length % 2 or end > len(raw) or size < 0 or allocation < 0
                or following and (following % 8 or following < 24 + length or offset + following > len(raw))):
            raise _FullCaptureFailure("read_failed", "stream record bounds")
        name = raw[offset + 24:end].decode("utf-16-le", "surrogatepass")
        output.append((name, size, allocation))
        if not following:
            return output
        offset += following


def _full_capture_census_identity(
    records: list[dict[str, Any]],
) -> tuple[tuple[str, int, bool], ...]:
    # NTFS directory rows duplicate advisory metadata that may be stale.
    # Keep every raw row; compare namespace identity separately from the
    # authoritative metadata of each retained validated handle.
    return tuple((item["name"], item["inode"], bool(item["attributes"] & 0x10)) for item in records)


class _FullWorktreeWindowsReader:
    """Private per-capture native owner; DLL acquisition happens only in __init__."""

    def __init__(self, deadline: float) -> None:
        import ctypes
        import time

        self._ctypes = ctypes
        self._clock = time.monotonic
        self.deadline = deadline
        self.handles: list[int] = []
        self.guards: dict[int, dict[str, Any]] = {}
        self.directory_guards: dict[int, list[dict[str, Any]]] = {}
        self.stream_guards: dict[int, list[tuple[str, int, int]]] = {}
        if os.name != "nt" or ctypes.sizeof(ctypes.c_void_p) != 8 or ctypes.sizeof(ctypes.c_wchar) != 2:
            raise _FullWorktreeCaptureUnavailable("nonregular_refused", "Windows x64 required")
        u16, u32, i32 = ctypes.c_uint16, ctypes.c_uint32, ctypes.c_int32
        ptr, uptr, i64 = ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int64

        class UnicodeString(ctypes.Structure):
            _fields_ = [("Length", u16), ("MaximumLength", u16), ("Buffer", ptr)]

        class ObjectAttributes(ctypes.Structure):
            _fields_ = [("Length", u32), ("RootDirectory", ptr), ("ObjectName", ctypes.POINTER(UnicodeString)),
                        ("Attributes", u32), ("SecurityDescriptor", ptr), ("SecurityQualityOfService", ptr)]

        class StatusUnion(ctypes.Union):
            _fields_ = [("Status", i32), ("Pointer", ptr)]

        class IoStatusBlock(ctypes.Structure):
            _fields_ = [("State", StatusUnion), ("Information", uptr)]

        class BasicInfo(ctypes.Structure):
            _fields_ = [("CreationTime", i64), ("LastAccessTime", i64), ("LastWriteTime", i64),
                        ("ChangeTime", i64), ("FileAttributes", u32)]

        class StandardInfo(ctypes.Structure):
            _fields_ = [("AllocationSize", i64), ("EndOfFile", i64), ("NumberOfLinks", u32),
                        ("DeletePending", ctypes.c_ubyte), ("Directory", ctypes.c_ubyte)]

        class AttributeTagInfo(ctypes.Structure):
            _fields_ = [("FileAttributes", u32), ("ReparseTag", u32)]

        class IdInfo(ctypes.Structure):
            _fields_ = [("VolumeSerialNumber", ctypes.c_uint64), ("FileId", ctypes.c_ubyte * 16)]

        layouts = ((UnicodeString, 16), (ObjectAttributes, 48), (IoStatusBlock, 16),
                   (BasicInfo, 40), (StandardInfo, 24), (AttributeTagInfo, 8), (IdInfo, 24))
        if (any(ctypes.sizeof(kind) != size for kind, size in layouts)
                or UnicodeString.Buffer.offset != 8 or ObjectAttributes.RootDirectory.offset != 8
                or ObjectAttributes.ObjectName.offset != 16 or ObjectAttributes.Attributes.offset != 24
                or IoStatusBlock.Information.offset != 8 or IdInfo.FileId.offset != 8):
            raise _FullWorktreeCaptureUnavailable("identity_unavailable", "native ABI mismatch")
        self._UnicodeString, self._ObjectAttributes, self._IoStatusBlock = UnicodeString, ObjectAttributes, IoStatusBlock
        self._BasicInfo, self._StandardInfo = BasicInfo, StandardInfo
        self._AttributeTagInfo, self._IdInfo = AttributeTagInfo, IdInfo
        try:
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            native = ctypes.WinDLL("ntdll", use_last_error=True)
            self._nt_create_file = native.NtCreateFile
            self._nt_create_file.argtypes = [ctypes.POINTER(ptr), u32, ctypes.POINTER(ObjectAttributes),
                                             ctypes.POINTER(IoStatusBlock), ptr, u32, u32, u32, u32, ptr, u32]
            self._nt_create_file.restype = i32
            self._nt_query_volume = native.NtQueryVolumeInformationFile
            self._nt_query_volume.argtypes = [ptr, ctypes.POINTER(IoStatusBlock), ptr, u32, u32]
            self._nt_query_volume.restype = i32
            self._get_file_information = kernel.GetFileInformationByHandleEx
            self._get_file_information.argtypes = [ptr, i32, ptr, u32]
            self._get_file_information.restype = i32
            self._get_file_type = kernel.GetFileType
            self._get_file_type.argtypes, self._get_file_type.restype = [ptr], u32
            self._read_file = kernel.ReadFile
            self._read_file.argtypes = [ptr, ptr, u32, ctypes.POINTER(u32), ptr]
            self._read_file.restype = i32
            self._close_handle = kernel.CloseHandle
            self._close_handle.argtypes, self._close_handle.restype = [ptr], i32
            self._query_dos_device = kernel.QueryDosDeviceW
            self._query_dos_device.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, u32]
            self._query_dos_device.restype = u32
        except (AttributeError, OSError) as error:
            raise _FullWorktreeCaptureUnavailable("identity_unavailable", "required native API") from error

    def tick(self) -> None:
        if self._clock() > self.deadline:
            raise _FullCaptureFailure("budget_exceeded", "capture deadline")

    def drive_mapping(self, drive: str) -> str:
        self.tick()
        buffer = self._ctypes.create_unicode_buffer(32768)
        count = self._query_dos_device(drive, buffer, len(buffer))
        if not 1 < count <= len(buffer):
            raise _FullCaptureFailure("identity_unavailable", "drive mapping query")
        raw = buffer[:count]
        if "\0" not in raw:
            raise _FullCaptureFailure("identity_unavailable", "drive mapping bounds")
        current = raw.split("\0", 1)[0]
        if re.fullmatch(r"\\Device\\HarddiskVolume[0-9]+", current) is None:
            raise _FullCaptureFailure("nonregular_refused", "drive is not a direct local volume")
        return current

    def open_relative(self, parent: int | None, name: str, access: int) -> int:
        self.tick()
        if parent is not None:
            if parent not in self.guards or not self.guards[parent]["directory"] or not _full_capture_name(name):
                raise _FullCaptureFailure("nonregular_refused", "relative open parent/name")
            if self.metadata(parent) != self.guards[parent]:
                raise _FullCaptureFailure("unstable", "parent changed before relative open")
        elif not re.fullmatch(r"\\Device\\HarddiskVolume[0-9]+\\", name):
            raise _FullCaptureFailure("nonregular_refused", "absolute open outside local volume root")
        if access not in {0x100080, 0x100081}:
            raise _FullCaptureFailure("nonregular_refused", "unsupported native access")
        c = self._ctypes
        encoded = name.encode("utf-16-le", "surrogatepass")
        if len(encoded) > 65532:
            raise _FullCaptureFailure("nonregular_refused", "native name too long")
        buffer = c.create_string_buffer(encoded + b"\0\0")
        string = self._UnicodeString(len(encoded), len(encoded) + 2, c.cast(buffer, c.c_void_p))
        attributes = self._ObjectAttributes(c.sizeof(self._ObjectAttributes), parent, c.pointer(string), 0, None, None)
        status, handle = self._IoStatusBlock(), c.c_void_p()
        # FILE_OPEN, READ sharing only, synchronous/no-follow/no-recall. No
        # directory-type flag, backup intent, inheritance, creation or write.
        result = self._nt_create_file(c.byref(handle), access, c.byref(attributes), c.byref(status),
                                      None, 0, 1, 1, 0x00600020, None, 0)
        valid = handle.value not in {None, 0, c.c_void_p(-1).value}
        if result != 0 or status.State.Status != 0 or status.Information != 1 or not valid:
            # Failure/pending/unsupported outputs do not prove returned ownership.
            raise _FullCaptureFailure("stat_failed", "NtCreateFile completion:"
                                      + str((result, status.State.Status, status.Information, handle.value)))
        if handle.value in self.handles:
            raise _FullCaptureFailure("identity_unavailable", "duplicate owned native handle")
        self.handles.append(handle.value)
        return handle.value

    def _query(self, handle: int, information: int, kind: Any) -> Any:
        self.tick()
        value = kind()
        if not self._get_file_information(handle, information, self._ctypes.byref(value), self._ctypes.sizeof(value)):
            raise _FullCaptureFailure("stat_failed", "GetFileInformationByHandleEx:" + str(information))
        return value

    def _volume(self, handle: int) -> tuple[int, int, str]:
        import struct

        c = self._ctypes
        values = []
        for information, length in ((4, 8), (5, 1024)):
            self.tick()
            buffer, status = c.create_string_buffer(length), self._IoStatusBlock()
            result = self._nt_query_volume(handle, c.byref(status), buffer, length, information)
            if result != 0 or status.State.Status != 0 or not 0 < status.Information <= length:
                raise _FullCaptureFailure("identity_unavailable", "native volume query")
            values.append(buffer.raw[:status.Information])
        if len(values[0]) != 8 or len(values[1]) < 12:
            raise _FullCaptureFailure("identity_unavailable", "volume buffer bounds")
        device, characteristics = struct.unpack("<II", values[0])
        _flags, component_limit, name_length = struct.unpack_from("<IiI", values[1])
        if name_length == 0 or name_length % 2 or 12 + name_length > len(values[1]) or component_limit <= 0:
            raise _FullCaptureFailure("identity_unavailable", "filesystem identity bounds")
        name = values[1][12:12 + name_length].decode("utf-16-le", "surrogatepass")
        if device != 7 or characteristics & (0x10 | 0x40 | 0x1000 | 0x2000) or name != "NTFS":
            raise _FullCaptureFailure("nonregular_refused", "ordinary local NTFS required")
        return device, characteristics, name

    def metadata(self, handle: int) -> dict[str, Any]:
        self.tick()
        if self._get_file_type(handle) != 1:
            raise _FullCaptureFailure("nonregular_refused", "not a disk file")
        basic = self._query(handle, 0, self._BasicInfo)
        standard = self._query(handle, 1, self._StandardInfo)
        tag = self._query(handle, 9, self._AttributeTagInfo)
        identity = self._query(handle, 18, self._IdInfo)
        volume = self._volume(handle)
        attributes, inode = int(basic.FileAttributes), int.from_bytes(bytes(identity.FileId), "little")
        if attributes != tag.FileAttributes:
            raise _FullCaptureFailure("unstable", "attribute observations differ")
        if attributes & 0x400 or tag.ReparseTag:
            raise _FullCaptureFailure("reparse_refused", "reparse object")
        # Only ordinary stat attributes are admitted. Cloud/recall/offline,
        # device, encrypted and unknown attributes are deliberately unavailable.
        if attributes & ~(0x1 | 0x2 | 0x4 | 0x10 | 0x20 | 0x80 | 0x100 | 0x200 | 0x800 | 0x2000 | 0x8000 | 0x20000):
            raise _FullCaptureFailure("nonregular_refused", "unsupported file attributes")
        if (standard.Directory not in {0, 1} or standard.DeletePending not in {0, 1}
                or bool(attributes & 0x10) != bool(standard.Directory) or standard.DeletePending
                or standard.EndOfFile < 0 or standard.NumberOfLinks < 1):
            raise _FullCaptureFailure("nonregular_refused", "unsupported file state")
        if not inode or inode >> 64:
            raise _FullCaptureFailure("identity_unavailable", "NTFS census-compatible file ID required")
        if not standard.Directory and standard.NumberOfLinks != 1:
            raise _FullCaptureFailure("private_refused", "multiple file aliases")
        epoch = 116444736000000000
        times = [int(basic.CreationTime), int(basic.LastWriteTime), int(basic.ChangeTime)]
        if min(times) < epoch:
            raise _FullCaptureFailure("stat_failed", "unsupported file time")
        mode = (0o040111 if standard.Directory else 0o100000) | (0o444 if attributes & 1 else 0o666)
        return {"identity": {"device": int(identity.VolumeSerialNumber), "inode": inode},
                "attributes": attributes, "directory": bool(standard.Directory),
                "links": int(standard.NumberOfLinks), "size": int(standard.EndOfFile),
                "mode": mode, "created": times[0], "modified": times[1], "changed": times[2],
                "ctime_ns": (times[0] - epoch) * 100, "mtime_ns": (times[1] - epoch) * 100,
                "volume": volume}

    def streams(self, handle: int, is_directory: bool) -> list[tuple[str, int, int]]:
        self.tick()
        c = self._ctypes
        buffer = c.create_string_buffer(65536)
        c.set_last_error(0)
        success = self._get_file_information(handle, 7, buffer, len(buffer))
        error = c.get_last_error()
        if not success:
            if error == 38 and is_directory:
                return []
            raise _FullCaptureFailure("read_failed", "stream query:" + str(error))
        if error == 38 and not any(buffer.raw) and is_directory:
            return []
        records = _full_capture_stream_buffer(buffer.raw)
        if is_directory:
            if records:
                raise _FullCaptureFailure("private_refused", "directory data stream")
        elif len(records) != 1 or records[0][0] != "::$DATA":
            raise _FullCaptureFailure("private_refused", "alternate or unknown stream")
        return records

    def list_directory(self, handle: int, maximum: int) -> list[dict[str, Any]]:
        self.tick()
        c = self._ctypes
        records: list[dict[str, Any]] = []
        names: set[str] = set()
        first = True
        calls = 0
        while True:
            self.tick()
            calls += 1
            if calls > maximum + 3:
                raise _FullCaptureFailure("budget_exceeded", "directory query iterations")
            buffer = c.create_string_buffer(65536)
            success = self._get_file_information(handle, 11 if first else 10, buffer, len(buffer))
            first = False
            if not success:
                error = c.get_last_error()
                if error == 18:
                    return sorted(records, key=lambda item: item["name"].encode("utf-8", "surrogateescape"))
                raise _FullCaptureFailure("read_failed", "directory query:" + str(error))
            for record in _full_capture_directory_buffer(buffer.raw):
                name = record["name"]
                if name in {".", ".."}:
                    continue
                if not _full_capture_name(name):
                    raise _FullCaptureFailure("nonregular_refused", "unrepresentable or ambiguous directory name")
                if name in names or record["inode"] == 0:
                    raise _FullCaptureFailure("unstable", "duplicate or unknown directory identity")
                if len(records) >= maximum:
                    raise _FullCaptureFailure("budget_exceeded", "directory census entries")
                names.add(name)
                records.append(record)

    def read(self, handle: int, count: int) -> bytes:
        self.tick()
        if type(count) is not int or not 0 < count <= 65536:
            raise _FullCaptureFailure("budget_exceeded", "read chunk")
        c = self._ctypes
        buffer, used = c.create_string_buffer(count), c.c_uint32()
        if not self._read_file(handle, buffer, count, c.byref(used), None) or used.value > count:
            raise _FullCaptureFailure("read_failed", "ReadFile")
        return buffer.raw[:used.value]

    def open_root(self, drive: str, components: list[str]) -> tuple[int, str]:
        mapping = self.drive_mapping(drive)
        handle = self.open_relative(None, mapping + "\\", 0x100080)
        facts = self.metadata(handle)
        if not facts["directory"]:
            raise _FullCaptureFailure("nonregular_refused", "volume root is not a directory")
        self.guards[handle] = facts
        for component in components:
            handle = self.open_relative(handle, component, 0x100080)
            facts = self.metadata(handle)
            if not facts["directory"]:
                raise _FullCaptureFailure("nonregular_refused", "capture ancestor is not a directory")
            self.guards[handle] = facts
        return handle, mapping

    def close_all(self) -> None:
        failures: list[BaseException] = []
        for handle in reversed(self.handles):
            try:
                if not self._close_handle(handle):
                    failures.append(OSError("CloseHandle returned false for owned handle " + str(handle)))
            except BaseException as error:
                # A failing wrapper must not prevent the remaining owned closes.
                failures.append(error)
        self.handles.clear()
        if failures:
            error = _FullWorktreeCaptureUnavailable("read_failed", "native handle cleanup failed")
            error.cleanup_failures = tuple(failures)
            raise error from BaseExceptionGroup("owned native handle cleanup failures", failures)


def _capture_worktree_state(
    root: str | Path, *, binding: dict[str, Any], phase: str,
    max_entries: int = 10000, max_file_bytes: int = 16777216,
    max_total_bytes: int = 67108864, timeout_seconds: float = 5,
) -> bytes:
    """Observe an admitted ordinary local NTFS subtree without writing anything.

    This Windows x64 callable is intentionally unwired. It does not admit live
    worktrees, private reads, Worker execution, approval or runtime activation.
    The caller must retain returned bytes or unavailable exceptions separately.
    Root/unknown-parent gaps may be unrepresentable by the existing closed
    schema and raise capture_unavailable; no parent or absent node is invented.
    """
    nonprivate = binding.get("capture_contract") == nonprivate_capture_contract() if type(binding) is dict else False
    root, binding_raw, required, deadline = _full_capture_validate(
        root, binding, phase, (max_entries, max_file_bytes, max_total_bytes, timeout_seconds)
    )
    if os.name != "nt":
        raise _FullWorktreeCaptureUnavailable("nonregular_refused", "Windows x64 NTFS required")
    reader = _FullWorktreeWindowsReader(deadline)
    entries: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    listings: dict[str, list[dict[str, Any]]] = {}
    listing_complete: set[str] = set()
    enumeration_complete = True
    total = 0
    root_facts: dict[str, Any] | None = None
    root_children: list[str] = []
    operation_error: BaseException | None = None

    def note(path: str, reason: str) -> None:
        nonlocal enumeration_complete
        record = {"path": path or ".", "reason": reason}
        if record not in errors:
            errors.append(record)
        enumeration_complete = False

    def unobserved(path: str, failure: _FullCaptureFailure) -> None:
        entries[path] = {"kind": "unobserved", "reason": failure.reason}
        note(path, failure.reason)

    def directory_node(facts: dict[str, Any]) -> dict[str, Any]:
        return {"kind": "directory", "mode": facts["mode"], "identity": facts["identity"],
                "children": [], "file_attributes": facts["attributes"]}

    def census(parent: int, name: str | None, path: str, facts: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
        if name is None:
            # The capture root is reopened through its already retained lexical
            # parent, or is the exact already pinned native volume root.
            if components:
                parent = root_parent
                name = components[-1]
            else:
                parent = None
                name = mapping + "\\"
        listing = reader.open_relative(parent, name, 0x100081)
        listing_facts = reader.metadata(listing)
        if listing_facts != facts or not listing_facts["directory"]:
            raise _FullCaptureFailure("unstable", "directory listing handle differs")
        reader.guards[listing] = listing_facts
        streams = reader.streams(listing, True)
        reader.stream_guards[listing] = streams
        result = reader.list_directory(listing, max_entries)
        reader.directory_guards[listing] = result
        listings[path] = result
        listing_complete.add(path)
        return listing, result

    def observe(parent: int, observed: dict[str, Any], path: str, depth: int) -> None:
        nonlocal total
        if len(path) > _FULL_CAPTURE_MAX_RELATIVE_CHARS:
            unobserved(path, _FullCaptureFailure("budget_exceeded", "observed relative path ceiling"))
            return
        if _full_capture_private(path):
            if nonprivate:
                entries[path] = {"kind": "private_boundary", "contents_observed": False,
                                 "identity": {"device": reader.guards[parent]["identity"]["device"],
                                              "inode": observed["inode"]},
                                 "file_attributes": observed["attributes"]}
            else:
                unobserved(path, _FullCaptureFailure("private_refused", "private raw relative path"))
            return
        try:
            reader.tick()
            metadata = reader.open_relative(parent, observed["name"], 0x100080)
            facts = reader.metadata(metadata)
            if (facts["identity"]["inode"] != observed["inode"]
                    or facts["identity"]["device"] != reader.guards[parent]["identity"]["device"]
                    or facts["directory"] != bool(observed["attributes"] & 0x10)):
                raise _FullCaptureFailure("unstable", "directory census and opened object differ")
            reader.guards[metadata] = facts
            if facts["directory"]:
                node = directory_node(facts)
                entries[path] = node
                if depth >= _FULL_CAPTURE_MAX_DEPTH:
                    note(path, "budget_exceeded")
                    return
                try:
                    listing, children = census(parent, observed["name"], path, facts)
                    visit(listing, children, path, node["children"], depth)
                except _FullCaptureFailure as failure:
                    note(path, failure.reason)
                return
            if facts["size"] > max_file_bytes or facts["size"] > max_total_bytes - total:
                raise _FullCaptureFailure("budget_exceeded", "file content budget")
            streams = reader.streams(metadata, False)
            if streams[0][1] != facts["size"]:
                raise _FullCaptureFailure("unstable", "default stream size differs")
            reader.stream_guards[metadata] = streams
            data = reader.open_relative(parent, observed["name"], 0x100081)
            current = reader.metadata(data)
            if current != facts or current["directory"] or reader.streams(data, False) != streams:
                raise _FullCaptureFailure("unstable", "file data handle differs")
            reader.guards[data] = current
            reader.stream_guards[data] = streams
            digest, used = hashlib.sha256(), 0
            while used < facts["size"]:
                if reader.metadata(data) != current:
                    raise _FullCaptureFailure("unstable", "file changed before read")
                chunk = reader.read(data, min(65536, facts["size"] - used))
                if not chunk:
                    raise _FullCaptureFailure("unstable", "unexpected file end")
                digest.update(chunk)
                used += len(chunk)
                total += len(chunk)
            if reader.metadata(data) != current or reader.streams(data, False) != streams:
                raise _FullCaptureFailure("unstable", "file changed during read")
            entries[path] = {"kind": "file", "sha256": digest.hexdigest(), "size": used,
                             "mode": current["mode"], "identity": current["identity"],
                             "mtime_ns": current["mtime_ns"], "ctime_ns": current["ctime_ns"],
                             "file_attributes": current["attributes"]}
        except _FullCaptureFailure as failure:
            unobserved(path, failure)

    def visit(
        parent: int, children: list[dict[str, Any]], prefix: str, represented: list[str], depth: int,
    ) -> None:
        if depth >= _FULL_CAPTURE_MAX_DEPTH:
            note(prefix, "budget_exceeded")
            return
        ordered = sorted(children, key=lambda item: (
            (prefix + "/" if prefix else "") + item["name"] not in required,
            item["name"].encode("utf-8", "surrogateescape")))
        for observed in ordered:
            path = (prefix + "/" if prefix else "") + observed["name"]
            if len(entries) >= max_entries:
                note(prefix, "budget_exceeded")
                break
            represented.append(observed["name"])
            observe(parent, observed, path, depth + 1)
        represented.sort(key=lambda name: name.encode("utf-8", "surrogateescape"))

    try:
        components = root[3:].split("\\") if root[3:] else []
        root_handle, mapping = reader.open_root(root[:2], components)
        root_facts = reader.guards[root_handle]
        root_parent = reader.handles[-2] if components else root_handle
        try:
            listing, children = census(root_handle, None, "", root_facts)
            visit(listing, children, "", root_children, 0)
        except _FullCaptureFailure as failure:
            note("", failure.reason)
        for handle, expected in list(reader.guards.items()):
            try:
                if reader.metadata(handle) != expected:
                    note("", "unstable")
                if handle in reader.stream_guards and reader.streams(handle, expected["directory"]) != reader.stream_guards[handle]:
                    note("", "unstable")
                if (handle in reader.directory_guards
                        and _full_capture_census_identity(reader.list_directory(handle, max_entries))
                        != _full_capture_census_identity(reader.directory_guards[handle])):
                    note("", "unstable")
            except _FullCaptureFailure as failure:
                note("", failure.reason)
        if reader.drive_mapping(root[:2]) != mapping:
            note("", "unstable")
        # Explicit absence requires a complete observed ancestor census. An
        # unknown/refused parent cannot be silently promoted into an absence.
        for path in binding["allowed_paths"]:
            if path in entries:
                continue
            parent = ""
            absent = False
            for component in path.split("/"):
                if parent not in listing_complete:
                    raise _FullWorktreeCaptureUnavailable(
                        errors[0]["reason"] if errors else "identity_unavailable", "allowed ancestry unobserved")
                if component not in {item["name"] for item in listings[parent]}:
                    absent = True
                    break
                parent = (parent + "/" if parent else "") + component
            if not absent or len(entries) >= max_entries:
                raise _FullWorktreeCaptureUnavailable("budget_exceeded" if len(entries) >= max_entries else "identity_unavailable",
                                                     "required allowed target unrepresentable")
            entries[path] = {"kind": "absent"}
        if root_facts is None:
            raise _FullWorktreeCaptureUnavailable("identity_unavailable", "root state missing")
        record = {"schema": "AIOS_WORKTREE_STATE_MANIFEST.v1",
                  "binding_sha256": hashlib.sha256(binding_raw).hexdigest(), "phase": phase,
                  "captured_at_utc": datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
                  "coverage": {"enumeration_complete": enumeration_complete,
                               "inspection_complete": not errors, "errors": errors},
                  "root_state": {"mode": root_facts["mode"], "identity": root_facts["identity"],
                                 "children": root_children}, "entries": entries}
        if nonprivate:
            record["schema"] = "AIOS_NONPRIVATE_WORKTREE_STATE_MANIFEST.v1"
            record["coverage"] = {"enumeration_complete": enumeration_complete,
                "nonprivate_inspection_complete": not errors, "private_contents_observed": False,
                "private_boundary_paths": sorted(path for path, node in entries.items() if node["kind"] == "private_boundary"),
                "errors": errors}
        raw = _full_capture_json(record)
        if len(raw) > 16777216:
            raise _FullWorktreeCaptureUnavailable("budget_exceeded", "canonical manifest ceiling")
        reader.tick()
        return raw
    except _FullCaptureFailure as failure:
        operation_error = _FullWorktreeCaptureUnavailable(failure.reason, failure.detail)
        raise operation_error from failure
    except BaseException as error:
        operation_error = error
        raise
    finally:
        try:
            reader.close_all()
        except BaseException as cleanup_error:
            if operation_error is not None:
                error = _FullWorktreeCaptureUnavailable("read_failed", "operation and cleanup failed")
                error.operation_error = operation_error
                error.cleanup_error = cleanup_error
                raise error from BaseExceptionGroup("capture operation and cleanup failures",
                                                    [operation_error, cleanup_error])
            raise


def capture_full_worktree_state(root: str | Path, *, binding: dict[str, Any], phase: str,
        max_entries: int = 10000, max_file_bytes: int = 16777216,
        max_total_bytes: int = 67108864, timeout_seconds: float = 5) -> bytes:
    """Original full-tree profile. Private/unknown entries still make it incomplete."""
    if type(binding) is dict and binding.get("capture_contract") == nonprivate_capture_contract():
        raise ValueError("full_capture_cannot_use_nonprivate_contract")
    return _capture_worktree_state(root, binding=binding, phase=phase, max_entries=max_entries,
        max_file_bytes=max_file_bytes, max_total_bytes=max_total_bytes, timeout_seconds=timeout_seconds)


def capture_nonprivate_worktree_state(root: str | Path, *, binding: dict[str, Any], phase: str,
        max_entries: int = 10000, max_file_bytes: int = 16777216,
        max_total_bytes: int = 67108864, timeout_seconds: float = 5) -> bytes:
    """Separate diagnostic profile. Opaque private boundaries prove no private contents."""
    if type(binding) is not dict or binding.get("capture_contract") != nonprivate_capture_contract():
        raise ValueError("nonprivate_capture_contract_required")
    return _capture_worktree_state(root, binding=binding, phase=phase, max_entries=max_entries,
        max_file_bytes=max_file_bytes, max_total_bytes=max_total_bytes, timeout_seconds=timeout_seconds)
