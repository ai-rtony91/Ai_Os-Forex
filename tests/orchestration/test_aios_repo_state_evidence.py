from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE = REPO_ROOT / "automation" / "orchestration" / "aios_repo_state_evidence.py"
FIXED_NOW = "2026-06-14T12:00:00Z"


def _load():
    spec = importlib.util.spec_from_file_location("aios_repo_state_evidence", MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _runner(stdout_by_key: dict[tuple[str, ...], tuple[int, str, str]]):
    def run(args, **_kwargs):
        key = tuple(args[1:])
        code, stdout, stderr = stdout_by_key.get(key, (0, "", ""))
        return subprocess.CompletedProcess(args=args, returncode=code, stdout=stdout, stderr=stderr)

    return run


def _clean_runner(root: Path):
    return _runner(
        {
            ("rev-parse", "--show-toplevel"): (0, str(root), ""),
            ("branch", "--show-current"): (0, "main\n", ""),
            ("--no-optional-locks", "status", "--porcelain=v1", "-z", "--branch", "--untracked-files=all"): (
                0,
                b"## main...origin/main\0",
                b"",
            ),
        }
    )


def test_planner_identity_requires_observed_named_committed_branch(tmp_path):
    m = _load()
    root = tmp_path / "repo"
    subprocess.run(["git", "init", "-b", "lane/observed", str(root)], check=True, capture_output=True)
    assert m.collect_planner_repository_state(root) is None  # unborn
    assert m.collect_planner_repository_state(tmp_path) is None  # no repository
    subprocess.run(["git", "-C", str(root), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                    "commit", "--allow-empty", "-m", "offline fixture"], check=True, capture_output=True)
    state = m.collect_planner_repository_state(root)
    assert state["worktree"] == str(root)
    assert state["branch"] == "lane/observed"
    assert len(state["commit"]) == 40
    assert "safe_for_apply" not in state and "is_clean" not in state
    subprocess.run(["git", "-C", str(root), "checkout", "--detach"], check=True, capture_output=True)
    assert m.collect_planner_repository_state(root) is None


def test_repo_state_collector_emits_required_fields(tmp_path: Path) -> None:
    m = _load()
    report = m.collect_repo_state(tmp_path, generated_at_utc=FIXED_NOW, runner=_clean_runner(tmp_path))

    assert {
        "schema_version",
        "system",
        "component",
        "generated_at_utc",
        "repo_root",
        "branch",
        "git_available",
        "inside_worktree",
        "is_clean",
        "status_short",
        "tracked_dirty_files",
        "untracked_files",
        "staged_files",
        "ahead_behind",
        "safe_for_apply",
        "blocked_reason",
        "evidence_quality",
    }.issubset(report)


def test_clean_simulated_repo_marks_safe_for_apply_true(tmp_path: Path) -> None:
    m = _load()
    report = m.collect_repo_state(tmp_path, generated_at_utc=FIXED_NOW, runner=_clean_runner(tmp_path))

    assert report["branch"] == "main"
    assert report["is_clean"] is True
    assert report["safe_for_apply"] is True
    assert report["blocked_reason"] is None
    assert report["evidence_quality"] == "strong"


def test_dirty_simulated_repo_marks_safe_for_apply_false(tmp_path: Path) -> None:
    m = _load()
    runner = _runner(
        {
            ("rev-parse", "--show-toplevel"): (0, str(tmp_path), ""),
            ("branch", "--show-current"): (0, "main\n", ""),
            ("--no-optional-locks", "status", "--porcelain=v1", "-z", "--branch", "--untracked-files=all"): (
                0,
                b"## main...origin/main\0 M tracked.py\0?? new.py\0A  staged.py\0",
                b"",
            ),
        }
    )

    report = m.collect_repo_state(tmp_path, generated_at_utc=FIXED_NOW, runner=runner)

    assert report["is_clean"] is False
    assert report["safe_for_apply"] is False
    assert report["blocked_reason"] == "dirty_working_tree"
    assert report["tracked_dirty_files"] == ["tracked.py", "staged.py"]
    assert report["untracked_files"] == ["new.py"]
    assert report["staged_files"] == ["staged.py"]


def test_git_unavailable_or_failure_marks_unsafe(tmp_path: Path) -> None:
    m = _load()

    def missing_git(args, **_kwargs):
        raise FileNotFoundError("git")

    missing = m.collect_repo_state(tmp_path, generated_at_utc=FIXED_NOW, runner=missing_git)
    assert missing["git_available"] is False
    assert missing["safe_for_apply"] is False
    assert missing["evidence_quality"] == "missing"

    failing = m.collect_repo_state(
        tmp_path,
        generated_at_utc=FIXED_NOW,
        runner=_runner({("rev-parse", "--show-toplevel"): (1, "", "not a repo")}),
    )
    assert failing["git_available"] is True
    assert failing["inside_worktree"] is False
    assert failing["safe_for_apply"] is False


def test_output_json_parses_and_is_deterministic_ignoring_timestamp(tmp_path: Path) -> None:
    m = _load()
    first = m.collect_repo_state(tmp_path, generated_at_utc=FIXED_NOW, runner=_clean_runner(tmp_path))
    second = m.collect_repo_state(tmp_path, generated_at_utc=FIXED_NOW, runner=_clean_runner(tmp_path))
    output = m.write_repo_state_report(tmp_path, first)
    parsed = json.loads(output.read_text(encoding="utf-8"))

    assert parsed == first
    assert first == second



def test_raw_status_preserves_all_filename_bytes_and_rename_copy_endpoints():
    m = _load()
    paths = [b"Reports/ leading and trailing .md ", b'Reports/a"b.md', "Reports/café.md".encode(),
             b"Reports/a\tb\nc.md", b"Reports/run -> summary.md", b"Reports/back\\slash.md", b"Reports/nonutf8-\xff.md"]
    payload = b"".join(b"?? " + path + b"\0" for path in paths)
    payload += b"R  Reports/destination.md\0docs/governance/source.md\0C  Reports/copy.md\0docs/security/original.md\0"
    parsed = m.parse_git_status_z(payload)
    assert parsed["errors"] == []
    assert [entry["path"].encode("utf-8", "surrogateescape") for entry in parsed["entries"][:7]] == paths
    assert parsed["entries"][-2] == {"git_code": "R ", "path": "Reports/destination.md", "source_path": "docs/governance/source.md"}
    assert parsed["entries"][-1] == {"git_code": "C ", "path": "Reports/copy.md", "source_path": "docs/security/original.md"}


def test_legacy_text_adapter_decodes_git_c_quoting_and_only_rename_arrows():
    m = _load()
    parsed = m.parse_git_status_text_lines([
        '?? Reports/plain -> arrow.md ', r'?? "Reports/caf\303\251\tline\nname\"quote\\slash.md"',
        'R  "docs/governance/a -> b.md" -> "Reports/a -> b.md"',
    ])
    assert parsed["errors"] == []
    assert parsed["entries"] == [
        {"git_code": "??", "path": "Reports/plain -> arrow.md "},
        {"git_code": "??", "path": 'Reports/café\tline\nname"quote\\slash.md'},
        {"git_code": "R ", "path": "Reports/a -> b.md", "source_path": "docs/governance/a -> b.md"},
    ]


def test_repo_state_uses_raw_status_and_reports_both_dirty_rename_endpoints(tmp_path):
    m = _load()
    def run(args, **kwargs):
        key = tuple(args[1:])
        if key == ("rev-parse", "--show-toplevel"):
            return subprocess.CompletedProcess(args, 0, str(tmp_path), "")
        if key == ("branch", "--show-current"):
            return subprocess.CompletedProcess(args, 0, "fixture/topic\n", "")
        assert key == ("--no-optional-locks", "status", "--porcelain=v1", "-z", "--branch", "--untracked-files=all")
        assert kwargs["text"] is False
        return subprocess.CompletedProcess(args, 0, b"## fixture/topic\0R  Reports/new name.md\0docs/governance/old name.md\0?? Reports/a -> b.md \0", b"")
    report = m.collect_repo_state(tmp_path, runner=run)
    assert report["tracked_dirty_files"] == ["Reports/new name.md", "docs/governance/old name.md"]
    assert report["staged_files"] == ["Reports/new name.md", "docs/governance/old name.md"]
    assert report["untracked_files"] == ["Reports/a -> b.md "]
    assert report["safe_for_apply"] is False


def test_repo_state_malformed_or_text_status_cannot_claim_clean(tmp_path):
    m = _load()
    status_key = ("--no-optional-locks", "status", "--porcelain=v1", "-z", "--branch", "--untracked-files=all")
    for payload in (b"bad\0", b"ZZ Reports/benign.md\0", b"R  Reports/dest.md\0", b"?? Reports/incomplete.md", ""):
        runner = _runner({("rev-parse", "--show-toplevel"): (0, str(tmp_path), ""),
                          ("branch", "--show-current"): (0, "main\n", ""), status_key: (0, payload, b"")})
        report = m.collect_repo_state(tmp_path, runner=runner)
        assert report["is_clean"] is None
        assert report["safe_for_apply"] is False
        assert report["blocked_reason"] == "git_status_parse_failed"


def _campaign_fixture(tmp_path, monkeypatch, *, queue_item=None, selection=None):
    """Owned files + mocked Git I/O. Never native approval or repository proof."""
    import hashlib

    from automation.orchestration import aios_repo_state_evidence as owner
    if queue_item is None:
        from tests.orchestration.test_aios_execution_packet_resolver import item
        queue_item = item(allowed_paths=["src/task.py"], commit_message="", pr_authority="")
    root = tmp_path.resolve()
    git_dir = root / "git-metadata"
    git_dir.mkdir(exist_ok=True)
    identity = {"resolved": True, "reason": "resolved", "repo_root": str(root), "git_dir": str(git_dir),
                "branch": "fixture/topic", "symbolic_ref": "refs/heads/fixture/topic", "detached": False, "commit": "a" * 40}
    paths = set(owner.CAMPAIGN_PROTECTED) | set(owner.CAMPAIGN_IMPLEMENTATIONS) | set(queue_item["allowed_paths"])
    for relative in paths:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("owned fixture baseline " + relative).encode())
    inventory = {relative: {"exists": True, "sha256": hashlib.sha256((root / relative).read_bytes()).hexdigest()} for relative in sorted(paths)}
    raw = b"## fixture/topic\0" + b"".join(b" M " + path.encode() + b"\0" for path in queue_item["allowed_paths"])
    parsed = owner.parse_git_status_z(raw)
    display = [parsed["branch_line"]] + [entry["git_code"] + " " + json.dumps(entry["path"]) for entry in parsed["entries"]]
    state = {"worktree": str(root), "branch": "fixture/topic", "status_lines": display, "dependency_states": {}}
    selection = selection or ("fixture-task", queue_item["packet_id"], "b" * 64, "c" * 64, "2026-10-17T12:00:00+00:00")
    contract = {"schema": owner.CAMPAIGN_SOURCE_SCHEMA, "selection": list(selection), "queue_item_sha256": owner._campaign_digest(queue_item),
                "repository_identity": identity, "status_sha256": hashlib.sha256(raw).hexdigest(), "inventory": inventory,
                "immutable_manifest": {path: inventory[path]["sha256"] for path in owner.CAMPAIGN_IMPLEMENTATIONS},
                "protected_pins": {path: inventory[path]["sha256"] for path in owner.CAMPAIGN_PROTECTED},
                "allowed_paths": queue_item["allowed_paths"], "forbidden_paths": queue_item["forbidden_paths"],
                "validators": queue_item["validators"], "approval_authority": queue_item["approval_authority"], "git_actions": [],
                "delivery": {name: str(root / "relay" / "delivery" / name) for name in ("runtime_dir", "terminal_dir", "metadata_path", "event_log_path")}}
    mutable = {"raw": raw, "identity": identity, "calls": []}
    def run(args, **kwargs):
        mutable["calls"].append(args)
        key = tuple(args[2:])
        assert args[:2] == ["git", "--no-optional-locks"]
        observed = mutable["identity"]
        values = {("rev-parse", "--show-toplevel"): observed["repo_root"],
                  ("rev-parse", "--absolute-git-dir"): observed["git_dir"],
                  ("symbolic-ref", "--quiet", "HEAD"): observed["symbolic_ref"],
                  ("rev-parse", "--verify", "HEAD^{commit}"): observed["commit"]}
        if key == ("status", "--porcelain=v1", "-z", "--branch", "--untracked-files=all"):
            assert kwargs["text"] is False
            return subprocess.CompletedProcess(args, 0, mutable["raw"], b"")
        assert key in values
        return subprocess.CompletedProcess(args, 0, values[key] + "\n", "")
    monkeypatch.setattr(owner.subprocess, "run", run)
    def seal():
        raw_reference = owner.campaign_json(contract).encode("ascii")
        profile = owner.CampaignPacketProfile(tuple(selection), hashlib.sha256(raw_reference).hexdigest(), owner.campaign_json(queue_item))
        def reader(expected):
            assert expected == tuple(selection)
            return raw_reference
        return profile, reader
    profile, reader = seal()
    return owner, queue_item, state, profile, reader, contract, mutable, seal


def test_campaign_owner_observes_dirty_without_relabeling_legacy(tmp_path, monkeypatch):
    owner, item, state, profile, reader, contract, mutable, _ = _campaign_fixture(tmp_path, monkeypatch)
    evidence = owner.verify_campaign_packet_profile(profile, admission_reader=reader, selection=profile.selection,
                                                    repository_state=state, queue_item=item)
    observed = json.loads(evidence.repository_state_json)
    assert observed["is_clean"] is False and observed["safe_for_apply"] is False
    assert len(mutable["calls"]) == 10 and observed["status_sha256"] == contract["status_sha256"]
    assert not (tmp_path / "relay").exists()


@pytest.mark.parametrize("defect", ["no_reader", "dict_profile", "wrong_selection", "false_selection", "float_selection", "array_selection", "wrong_reference", "reference_array", "reference_error", "fake_clean", "identity", "bytes", "new_status", "bad_status", "status_type", "scope", "writable_implementation", "false_exists", "float_attempt", "false_attempt", "array_digest", "extra_approval_flag", "missing_protected", "delivery_overlap", "commit_instruction", "absent_created"])
def test_campaign_owner_boundary_negatives_block(tmp_path, monkeypatch, defect):
    from dataclasses import replace
    owner, item, state, profile, reader, contract, mutable, seal = _campaign_fixture(tmp_path, monkeypatch)
    selection = profile.selection
    if defect == "no_reader": reader = None
    elif defect == "dict_profile": profile = {"approved": True, "dirty_allowed": True}
    elif defect == "wrong_selection": selection = ("other", *selection[1:])
    elif defect in {"false_selection", "float_selection", "array_selection"}:
        selection = ({"false_selection": False, "float_selection": 1.0, "array_selection": ["fixture-task"]}[defect], *selection[1:])
    elif defect == "wrong_reference": profile = replace(profile, reference_sha256="d" * 64)
    elif defect == "reference_array": reader = lambda _: [b"not bytes"]
    elif defect == "reference_error": reader = lambda _: (_ for _ in ()).throw(RuntimeError("unknown owner evidence"))
    elif defect == "fake_clean": state["status_lines"] = []
    elif defect == "identity": mutable["identity"] = {**mutable["identity"], "commit": "d" * 40}
    elif defect == "bytes": (tmp_path / item["allowed_paths"][0]).write_text("changed but same dirty status")
    elif defect == "new_status": mutable["raw"] += b"?? unknown.py\0"
    elif defect == "bad_status": mutable["raw"] = b"## fixture/topic\0?? unterminated"
    elif defect == "status_type": mutable["raw"] = "not raw bytes"
    elif defect == "scope": contract["allowed_paths"] = ["different.py"]
    elif defect == "writable_implementation": contract["immutable_manifest"][item["allowed_paths"][0]] = contract["inventory"][item["allowed_paths"][0]]["sha256"]
    elif defect == "false_exists": contract["inventory"][item["allowed_paths"][0]]["exists"] = 1
    elif defect == "float_attempt": item["attempt"] = 0.0
    elif defect == "false_attempt": item["attempt"] = False
    elif defect == "array_digest": contract["inventory"][item["allowed_paths"][0]]["sha256"] = ["e" * 64]
    elif defect == "extra_approval_flag": contract["approved"] = True
    elif defect == "missing_protected": contract["protected_pins"].pop("RISK_POLICY.md")
    elif defect == "delivery_overlap": contract["delivery"]["runtime_dir"] = str(tmp_path / item["allowed_paths"][0])
    elif defect == "commit_instruction": item["commit_message"] = "not authorized"
    else:
        contract["inventory"]["new.py"] = {"exists": False, "sha256": None}
        (tmp_path / "new.py").write_text("unexpected")
    if defect in {"scope", "writable_implementation", "false_exists", "array_digest", "extra_approval_flag", "missing_protected", "delivery_overlap", "absent_created", "float_attempt", "false_attempt", "commit_instruction"}:
        contract["queue_item_sha256"] = owner._campaign_digest(item) if defect not in {"float_attempt"} else contract["queue_item_sha256"]
        if defect == "float_attempt":
            with pytest.raises(ValueError): owner.campaign_json(item)
            return
        profile, reader = seal()
    with pytest.raises((ValueError, TypeError)):
        owner.verify_campaign_packet_profile(profile, admission_reader=reader, selection=selection, repository_state=state, queue_item=item)


def test_campaign_owner_rechecks_bytes_during_collection(tmp_path, monkeypatch):
    owner, item, state, profile, reader, _, mutable, _ = _campaign_fixture(tmp_path, monkeypatch)
    actual = owner.collect_repo_identity
    calls = []
    def identity(*args, **kwargs):
        calls.append(1)
        value = actual(*args, **kwargs)
        if len(calls) == 2:
            (tmp_path / item["allowed_paths"][0]).write_text("changed after status bracket")
        return value
    monkeypatch.setattr(owner, "collect_repo_identity", identity)
    with pytest.raises(ValueError, match="bytes changed during collection"):
        owner.verify_campaign_packet_profile(profile, admission_reader=reader, selection=profile.selection, repository_state=state)
    assert mutable["calls"]


def test_campaign_original_execution_registry_guard_cannot_be_omitted(tmp_path, monkeypatch):
    owner, item, state, _, _, contract, _, seal = _campaign_fixture(tmp_path, monkeypatch)
    critical = "automation/orchestration/validators/Invoke-AiOsExecutionRegistryGuard.ps1"
    assert critical in owner.CAMPAIGN_PROTECTED
    contract["protected_pins"].pop(critical)
    profile, reader = seal()
    with pytest.raises(ValueError, match="protected/implementation coverage missing"):
        owner.verify_campaign_packet_profile(profile, admission_reader=reader, selection=profile.selection,
            repository_state=state, queue_item=item)



@pytest.mark.parametrize("defect", ["header", "header_false", "header_array", "protected", "immutable", "immutable_ancestor", "protected_descendant", "protected_case", "scope", "scope_alias"])
def test_campaign_owner_and_direct_builder_share_exact_contract_boundaries(tmp_path, monkeypatch, defect):
    from automation.orchestration.aios_codex_packet_builder import (
        build_repository_aligned_apply_packet,
    )

    owner, item, state, _, _, contract, _, seal = _campaign_fixture(tmp_path, monkeypatch)
    if defect.startswith("header"):
        item["packet_identity"]["packet_id"] = {"header": "PKT-CONFLICT", "header_false": False, "header_array": [item["packet_id"]]}[defect]
    elif defect.startswith("scope"):
        conflict = item["allowed_paths"][0]
        item["forbidden_paths"] = [conflict if defect == "scope" else conflict.replace("/", "\\")]
        contract["forbidden_paths"] = item["forbidden_paths"]
    else:
        destinations = {"protected": "AGENTS.md", "immutable": owner.CAMPAIGN_IMPLEMENTATIONS[0],
                        "immutable_ancestor": "automation/orchestration", "protected_descendant": "AGENTS.md/child", "protected_case": "agents.md"}
        contract["delivery"]["metadata_path"] = str(tmp_path / destinations[defect])
    contract["queue_item_sha256"] = owner._campaign_digest(item)
    profile, reader = seal()
    with pytest.raises((ValueError, OSError)):
        owner.verify_campaign_packet_profile(profile, admission_reader=reader, selection=profile.selection,
            repository_state=state, queue_item=item)
    result = build_repository_aligned_apply_packet(repository_state=state, packet_identity=item["packet_identity"],
        mission=item["mission"], allowed_paths=item["allowed_paths"], forbidden_paths=item["forbidden_paths"],
        validators=item["validators"], approval_authority=item["approval_authority"], campaign_profile=profile,
        campaign_admission_reader=reader, campaign_selection=profile.selection)
    assert result["packet_ready"] is False and result["reason_code"] == "campaign_source_blocked"


# P505 acquisition child: actual generated files, declared fixture identity only.
# No Git/provider/runtime operation or authenticated task acceptance is asserted.
import copy as _p505c_copy
import hashlib as _p505c_hashlib
import os as _p505c_os
import shutil as _p505c_shutil
import traceback as _p505c_traceback
from datetime import UTC as _p505c_UTC, datetime as _p505c_datetime


_P505C_CAPTURE_RULES_DESCRIPTOR = 'AIOS_FULL_WORKTREE_CAPTURE_RULES.v1\ndomain=entire_worktree_subtree\nplatform=nt\npath_identity=raw_utf8_surrogateescape_no_normalization\ncensus=all_named_entries_no_exclusions\ncontent=ordinary_default_stream_only\nmetadata=mode,device,inode,size,mtime_ns,ctime_ns,file_attributes\nnt_ctime=creation_time;change_time=internal_stability_guard\nacquisition=retained_parent_handle_single_component_no_follow\npayload=validated_same_file_handle_before_read\nrefuse=private,reparse,nonregular,multilink,alternate_stream,offline,recall,remote\nuncertainty=explicit_incomplete_or_root_unavailable\nmanifest=AIOS_WORKTREE_STATE_MANIFEST.v1\ncanonical=ascii_sorted_compact_json_final_newline\nmanifest_limit_bytes=16777216\nauthority=caller_admission_separate_not_conferred_by_rules_digest\n'

def _p505c_canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")


def _p505c_sha(raw):
    return _p505c_hashlib.sha256(raw).hexdigest()


def _p505c_api(owner):
    api = getattr(owner, "capture_full_worktree_state", None)
    assert callable(api), "P505_COLLECTOR_CAUSAL_REQUIRED:complete acquisition API is absent"
    return api


def _p505c_case(tmp_path, *, initial=None, allowed=None):
    owner = _load()
    root = tmp_path / "worktree"
    root.mkdir()
    initial = ({"src/task.py": b"owned task original\n", "outside/dirty.txt": b"owned outside original\n"}
               if initial is None else initial)
    for relative, payload in initial.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    allowed = ["src/task.py"] if allowed is None else list(allowed)
    binding = {
        "task": {"task_id": "fixture-p505c", "packet_id": "fixture-p505c-packet",
                 "action_id": "fixture-observe-capture", "attempt_id": "fixture-p505c-attempt"},
        "repository_identity": {"resolved": True, "reason": "resolved", "repo_root": str(root),
                                "git_dir": str(tmp_path / "declared-fixture-git-metadata"),
                                "branch": "fixture-p505c", "symbolic_ref": "refs/heads/fixture-p505c",
                                "detached": False, "commit": "a" * 40},
        "interval_ref": "fixture-declared-interval-no-provider",
        "allowed_paths": allowed,
        "max_files_changed": 8,
        "implementation_manifest": {
            "automation/orchestration/aios_repo_state_evidence.py": _p505c_sha(MODULE.read_bytes()),
        },
        "capture_contract": {"schema": "AIOS_FULL_WORKTREE_STATE_CAPTURE.v1",
                             "domain": "entire_worktree_subtree", "platform": _p505c_os.name,
                             "rules_sha256": _p505c_sha(_P505C_CAPTURE_RULES_DESCRIPTOR.encode("ascii"))},
    }
    return owner, root, binding


def _p505c_write_exact(directory, name, raw):
    # Caller supplies the already owned root.parent, outside compared worktree.
    # Exclusive creation retains the first original; no overwrite or replay.
    target = directory / name
    with target.open("xb") as stream:
        written = stream.write(raw)
        assert written == len(raw), "P505_COLLECTOR_EVIDENCE_SHORT_WRITE"
        stream.flush()
        _p505c_os.fsync(stream.fileno())
    return target


def _p505c_write_json(directory, name, value):
    return _p505c_write_exact(directory, name, _p505c_canonical(value))


def _p505c_error_snapshot(directory, stage, error, **facts):
    record = {"stage": stage,
              "recorded_at_utc": _p505c_datetime.now(_p505c_UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
              "error_type": type(error).__module__ + "." + type(error).__qualname__,
              "error_message": str(error),
              "traceback": _p505c_traceback.format_exception(error), **facts}
    try:
        _p505c_write_json(directory, stage + ".error.json", record)
    except BaseException as evidence_error:
        # Retain both causes if recording itself fails; do not mask the producer.
        raise error from evidence_error


def _p505c_capture(owner, root, binding, phase, **limits):
    api = _p505c_api(owner)  # Missing-API baseline fails before evidence creation.
    original_binding = _p505c_canonical(binding)
    evidence = root.parent
    stage = "capture-" + phase
    _p505c_write_exact(evidence, stage + ".binding.json", original_binding)
    entered = _p505c_datetime.now(_p505c_UTC)
    try:
        raw = api(str(root), binding=binding, phase=phase, **limits)
    except BaseException as error:
        _p505c_error_snapshot(evidence, stage, error,
                             binding_sha256=_p505c_sha(original_binding),
                             entered_at_utc=entered.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                             root=str(root), phase=phase, limits=limits)
        raise
    returned = _p505c_datetime.now(_p505c_UTC)
    output_sha = None
    if isinstance(raw, bytes):
        # Persist exact original bytes immediately, before decode/shape assertions.
        _p505c_write_exact(evidence, stage + ".raw.json", raw)
        output_sha = _p505c_sha(raw)
    else:
        _p505c_write_json(evidence, stage + ".invalid-return.json", {
            "return_type": type(raw).__module__ + "." + type(raw).__qualname__,
            "return_value": raw if type(raw) in {dict, list, str, int, bool, float, type(None)} else None,
        })
    _p505c_write_json(evidence, stage + ".observation.json", {
        "root": str(root), "phase": phase, "limits": limits,
        "binding_sha256": _p505c_sha(original_binding), "output_sha256": output_sha,
        "output_bytes": len(raw) if isinstance(raw, bytes) else None,
        "entered_at_utc": entered.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "returned_at_utc": returned.isoformat(timespec="microseconds").replace("+00:00", "Z"),
    })
    assert type(raw) is bytes and 0 < len(raw) <= 16 * 1024 * 1024
    record = json.loads(raw.decode("ascii"))
    assert _p505c_canonical(record) == raw
    assert set(record) == {"schema", "binding_sha256", "phase", "captured_at_utc", "coverage", "root_state", "entries"}
    assert record["schema"] == "AIOS_WORKTREE_STATE_MANIFEST.v1" and record["phase"] == phase
    assert record["binding_sha256"] == _p505c_sha(original_binding)
    assert _p505c_canonical(binding) == original_binding
    stamp = record["captured_at_utc"]
    observed = _p505c_datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    assert observed.isoformat(timespec="microseconds").replace("+00:00", "Z") == stamp
    assert entered <= observed <= returned, "P505_COLLECTOR_ACTUAL_TIME_REQUIRED"
    return raw, record


def _p505c_compare(binding, before_raw, after_raw, started, ended, *, evidence_root):
    from automation.orchestration.aios_self_build_apply_result_verifier import (
        build_self_build_apply_result_verifier,
    )
    task = binding["task"]
    allowed = binding["allowed_paths"]
    maximum = binding["max_files_changed"]
    queue = {"schema": "AIOS_SELF_BUILD_WORK_QUEUE_ITEM.v1", **task,
             "allowed_paths": list(allowed), "validators": ["fixture-semantic-control"]}
    executor = {"schema": "AIOS_SELF_BUILD_SINGLE_ACTION_EXECUTOR.v1",
                "task_id": task["task_id"], "packet_id": task["packet_id"], "attempt_id": task["attempt_id"],
                "selected_action": task["action_id"], "command_would_run": True, "command_executed": True,
                "allowed_paths": list(allowed), "max_files_changed": maximum,
                "interval_ref": binding["interval_ref"],
                "repository_identity": _p505c_copy.deepcopy(binding["repository_identity"]),
                "execution_record_sha256": _p505c_sha(b"declared fixture interval; no process executed"),
                "execution_started_at_utc": started, "execution_ended_at_utc": ended}
    context = {"schema": "AIOS_APPLY_PRESERVATION_CONTEXT.v1", "binding": _p505c_copy.deepcopy(binding),
               "execution": {"record_sha256": executor["execution_record_sha256"],
                             "started_at_utc": started, "ended_at_utc": ended},
               "before_manifest_sha256": _p505c_sha(before_raw), "after_manifest_sha256": _p505c_sha(after_raw)}
    validators = [{"name": "fixture", "returncode": 0, "passed": True}]
    inputs = {"queue": queue, "executor": executor, "context": context,
              "validators": validators, "allowed_paths": list(allowed), "max_files_changed": maximum}
    hashes = {"before_manifest_sha256": _p505c_sha(before_raw),
              "after_manifest_sha256": _p505c_sha(after_raw)}
    for name, value in inputs.items():
        raw_input = _p505c_canonical(value)
        _p505c_write_exact(evidence_root, "comparator." + name + ".json", raw_input)
        hashes[name + "_sha256"] = _p505c_sha(raw_input)
    _p505c_write_json(evidence_root, "comparator.input-hashes.json", hashes)
    entered = _p505c_datetime.now(_p505c_UTC)
    try:
        result = build_self_build_apply_result_verifier(
            queue, executor, "", "", validators,
            list(allowed), maximum, preservation_context=context,
            before_manifest=before_raw, after_manifest=after_raw,
        )
        returned = _p505c_datetime.now(_p505c_UTC)
        # Actual returned result is retained before any semantic assertion.
        raw_result = _p505c_canonical(result)
        _p505c_write_exact(evidence_root, "comparator.actual-result.json", raw_result)
        _p505c_write_json(evidence_root, "comparator.observation.json", {
            "entered_at_utc": entered.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "returned_at_utc": returned.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "input_hashes": hashes, "result_sha256": _p505c_sha(raw_result),
            "declared_fixture_only_no_execution_or_approval": True,
        })
    except BaseException as error:
        _p505c_error_snapshot(evidence_root, "comparator", error,
                             input_hashes=hashes,
                             entered_at_utc=entered.isoformat(timespec="microseconds").replace("+00:00", "Z"))
        raise
    assert result["preservation_assurance"] == "supplied_manifest_comparison_only"
    assert result["safety"]["commands_executed"] is False
    return result


def _p505c_pair(owner, root, binding, operation):
    before_raw, before = _p505c_capture(owner, root, binding, "before")
    started = _p505c_datetime.now(_p505c_UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    operation()
    ended = _p505c_datetime.now(_p505c_UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    after_raw, after = _p505c_capture(owner, root, binding, "after")
    return before, after, _p505c_compare(binding, before_raw, after_raw, started, ended, evidence_root=root.parent)


def _p505c_complete(record):
    assert record["coverage"] == {"enumeration_complete": True, "inspection_complete": True, "errors": []}
    assert all(node["kind"] != "unobserved" for node in record["entries"].values())


def _p505c_refused(record, reason):
    coverage = record["coverage"]
    assert not (coverage["enumeration_complete"] and coverage["inspection_complete"] and not coverage["errors"])
    assert any(error["reason"] == reason for error in coverage["errors"])
    assert any(node == {"kind": "unobserved", "reason": reason} for node in record["entries"].values())


def test_p505c_complete_owned_tree_reaches_unchanged_public_comparator(tmp_path):
    owner, root, binding = _p505c_case(tmp_path)
    before, after, result = _p505c_pair(owner, root, binding, lambda: None)
    _p505c_complete(before)
    _p505c_complete(after)
    assert set(before["entries"]) == {"src", "src/task.py", "outside", "outside/dirty.txt"}
    observed = before["entries"]["outside/dirty.txt"]
    assert observed["sha256"] == _p505c_sha(b"owned outside original\n")
    assert observed["size"] == len(b"owned outside original\n")
    assert observed["identity"]["inode"] > 0 and observed["identity"]["device"] >= 0
    assert result["preservation_status"] == "compared" and result["changed_files"] == []
    assert result["result_safe_to_package"] is True


def test_p505c_allowed_edit_is_actual_capture_and_public_comparison(tmp_path):
    owner, root, binding = _p505c_case(tmp_path)
    before, after, result = _p505c_pair(owner, root, binding, lambda: (root / "src/task.py").write_bytes(b"owned allowed changed\n"))
    _p505c_complete(before)
    _p505c_complete(after)
    assert before["entries"]["src/task.py"]["sha256"] != after["entries"]["src/task.py"]["sha256"]
    assert result["changed_files"] == ["src/task.py"] and result["result_safe_to_package"] is True


@pytest.mark.parametrize("name", ["new-unlisted.txt", ".hidden-new.txt", "ignored-new.txt"])
def test_p505c_new_hidden_or_declared_ignored_sibling_cannot_disappear(tmp_path, name):
    owner, root, binding = _p505c_case(tmp_path, initial={"src/task.py": b"owned task\n", ".gitignore": b"ignored-new.txt\n"})
    before, after, result = _p505c_pair(owner, root, binding, lambda: (root / name).write_bytes(b"owned unlisted new bytes\n"))
    _p505c_complete(before)
    _p505c_complete(after)
    assert name not in before["entries"] and name in after["entries"]
    assert ".gitignore" in before["entries"] and ".gitignore" in after["entries"]
    assert name in result["unexpected_files"] and result["result_safe_to_package"] is False


@pytest.mark.parametrize("operation", ["dirty-edit", "rename", "copy", "recreate", "mtime"])
def test_p505c_same_status_names_and_endpoint_mutations_are_observed(tmp_path, operation):
    owner, root, binding = _p505c_case(tmp_path)
    original = root / "outside/dirty.txt"
    expected = {"outside/dirty.txt"}
    def change():
        if operation == "dirty-edit":
            original.write_bytes(b"owned outside content changed with same status name\n")
        elif operation == "rename":
            original.rename(root / "outside/renamed.txt")
        elif operation == "copy":
            _p505c_shutil.copyfile(original, root / "outside/copied.txt")
        elif operation == "recreate":
            original.rename(tmp_path / "preserved-old-object.bin")
            original.write_bytes(b"owned distinct replacement object\n")
        else:
            observed = original.stat()
            _p505c_os.utime(original, ns=(observed.st_atime_ns, observed.st_mtime_ns + 2_000_000_000))
    if operation == "rename":
        expected.add("outside/renamed.txt")
    elif operation == "copy":
        expected = {"outside/copied.txt"}
    before, after, result = _p505c_pair(owner, root, binding, change)
    _p505c_complete(before)
    _p505c_complete(after)
    assert set(result["changed_files"]) == expected
    assert set(result["unexpected_files"]) == expected and result["result_safe_to_package"] is False
    if operation == "recreate":
        assert before["entries"]["outside/dirty.txt"]["identity"] != after["entries"]["outside/dirty.txt"]["identity"]
    if operation == "mtime":
        assert before["entries"]["outside/dirty.txt"]["sha256"] == after["entries"]["outside/dirty.txt"]["sha256"]
        assert before["entries"]["outside/dirty.txt"]["mtime_ns"] != after["entries"]["outside/dirty.txt"]["mtime_ns"]


def test_p505c_unicode_and_literal_brackets_keep_raw_identity(tmp_path):
    names = [" leading.name.txt", "café-漢字-🧪.txt", "raw[bracket].txt", "space before suffix .txt"]
    initial = {name: ("owned exact name " + name).encode("utf-8") for name in names}
    owner, root, binding = _p505c_case(tmp_path, initial=initial, allowed=["not-created.txt"])
    _, record = _p505c_capture(owner, root, binding, "before")
    _p505c_complete(record)
    assert set(record["entries"]) == {*names, "not-created.txt"}
    assert record["root_state"]["children"] == sorted(names, key=lambda name: name.encode("utf-8", "surrogateescape"))
    for name in names:
        assert record["entries"][name]["sha256"] == _p505c_sha(initial[name])


def test_p505c_empty_tree_and_absent_allowed_descendant_need_no_invented_parent(tmp_path):
    owner, root, binding = _p505c_case(tmp_path, initial={}, allowed=["missing-parent/target.txt"])
    before, after, result = _p505c_pair(owner, root, binding, lambda: None)
    _p505c_complete(before)
    _p505c_complete(after)
    assert before["entries"] == {"missing-parent/target.txt": {"kind": "absent"}}
    assert before["root_state"]["children"] == []
    assert not (root / "missing-parent").exists()
    assert result["result_safe_to_package"] is True


@pytest.mark.parametrize("private_name", [".env", ".git", "private/payload.bin", "control/mode/cost_ledger.jsonl", "key.pem", "approvals/request.json"])
def test_p505c_generated_private_endpoint_is_incomplete_not_omitted(tmp_path, private_name):
    owner, root, binding = _p505c_case(tmp_path)
    def create():
        target = root / private_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"generated inert refusal sentinel, never a real private payload\n")
    before, after, result = _p505c_pair(owner, root, binding, create)
    _p505c_complete(before)
    _p505c_refused(after, "private_refused")
    assert private_name.split("/")[0] in after["root_state"]["children"]
    assert result["preservation_status"] == "incomplete" and result["result_safe_to_package"] is False
    # Structural refusal only. Actual FFI no-payload-read instrumentation is a
    # separate native-backend acceptance case, not inferred from this assertion.


def test_p505c_actual_hardlink_alias_is_refused_before_complete_credit(tmp_path):
    owner, root, binding = _p505c_case(tmp_path)
    target = root / "outside/dirty.txt"
    before, after, result = _p505c_pair(owner, root, binding, lambda: _p505c_os.link(target, root / "outside/alias.txt"))
    _p505c_complete(before)
    assert target.stat().st_nlink > 1
    _p505c_refused(after, "private_refused")
    assert result["preservation_status"] == "incomplete" and result["result_safe_to_package"] is False


@pytest.mark.parametrize("limits", [{"max_entries": 1}, {"max_file_bytes": 3}, {"max_total_bytes": 3}])
def test_p505c_actual_budget_exhaustion_is_incomplete_or_unavailable(tmp_path, limits):
    owner, root, binding = _p505c_case(tmp_path)
    _p505c_api(owner)  # Missing producer is never mistaken for expected unavailable.
    if "max_entries" in limits:
        # One entry cannot encode both observed src and required src/task.py.
        # Keep original binding/error evidence through the normal capture helper.
        with pytest.raises(ValueError, match=r"^capture_unavailable:budget_exceeded(?:$|:)"):
            _p505c_capture(owner, root, binding, "before", **limits)
        return
    _, record = _p505c_capture(owner, root, binding, "before", **limits)
    coverage = record["coverage"]
    assert not (coverage["enumeration_complete"] and coverage["inspection_complete"] and not coverage["errors"])
    assert any(error["reason"] == "budget_exceeded" for error in coverage["errors"])


@pytest.mark.parametrize("phase", [None, "", True, [], "BEFORE", "later"])
def test_p505c_phase_raw_types_and_values_are_not_coerced(tmp_path, phase):
    owner, root, binding = _p505c_case(tmp_path)
    api = _p505c_api(owner)
    with pytest.raises(ValueError):
        api(str(root), binding=binding, phase=phase)


@pytest.mark.parametrize("defect", ["not-object", "array", "missing-task", "extra", "bool-task", "bool-max", "bad-digest", "wrong-rules-digest", "wrong-platform", "string-paths", "wrong-root"])
def test_p505c_binding_shape_and_raw_identity_fail_closed(tmp_path, defect):
    owner, root, binding = _p505c_case(tmp_path)
    api = _p505c_api(owner)
    if defect == "not-object":
        binding = "declared-context"
    elif defect == "array":
        binding = []
    elif defect == "missing-task":
        binding.pop("task")
    elif defect == "extra":
        binding["caller_approved"] = True
    elif defect == "bool-task":
        binding["task"]["task_id"] = True
    elif defect == "bool-max":
        binding["max_files_changed"] = True
    elif defect == "bad-digest":
        binding["capture_contract"]["rules_sha256"] = "f" * 63
    elif defect == "wrong-rules-digest":
        binding["capture_contract"]["rules_sha256"] = "0" * 64
    elif defect == "wrong-platform":
        binding["capture_contract"]["platform"] = "posix"
    elif defect == "string-paths":
        binding["allowed_paths"] = "src/task.py"
    else:
        binding["repository_identity"]["repo_root"] = str(tmp_path / "different-uncreated-tree")
    with pytest.raises(ValueError):
        api(str(root), binding=binding, phase="before")


@pytest.mark.parametrize("field,bad", [("max_entries", True), ("max_entries", 0), ("max_entries", -1), ("max_entries", "2"), ("max_entries", 1.5), ("max_file_bytes", False), ("max_file_bytes", 0), ("max_total_bytes", True), ("max_total_bytes", -1), ("timeout_seconds", False), ("timeout_seconds", 0), ("timeout_seconds", float("inf")), ("timeout_seconds", float("nan"))])
def test_p505c_budget_raw_types_and_nonfinite_deadlines_are_invalid(tmp_path, field, bad):
    owner, root, binding = _p505c_case(tmp_path)
    api = _p505c_api(owner)
    with pytest.raises(ValueError):
        api(str(root), binding=binding, phase="before", **{field: bad})


@pytest.mark.parametrize("root_kind", ["none", "empty", "relative", "bool"])
def test_p505c_root_requires_explicit_absolute_owned_identity(tmp_path, root_kind):
    owner, root, binding = _p505c_case(tmp_path)
    api = _p505c_api(owner)
    supplied = {"none": None, "empty": "", "relative": "worktree", "bool": True}[root_kind]
    with pytest.raises(ValueError):
        api(supplied, binding=binding, phase="before")


# Native acquisition appendix. Real observations and scripted units have
# separate test names/evidence tiers. No helper below grants read authority.
import ctypes as _p505n_c
import struct as _p505n_struct
import time as _p505n_time


def _p505n_class(owner):
    _p505c_api(owner)
    kind = getattr(owner, "_FullWorktreeWindowsReader", None)
    assert isinstance(kind, type), "P505_NATIVE_SEAM_REQUIRED:Windows reader is absent"
    return kind


def _p505n_integer(value):
    return int(value.value if hasattr(value, "value") else value or 0)


def _p505n_reader(owner):
    # DLL/prototype binding only. Every unit replaces relevant FFI callables
    # before any real file API; fake handle values must never reach Windows.
    reader = _p505n_class(owner)(_p505n_time.monotonic() + 5)
    reader._close_handle = lambda handle: 1
    return reader


def _p505n_unit_evidence(tmp_path, name, facts):
    _p505c_write_json(tmp_path, "native-unit." + name + ".json", {
        "tier": "SCRIPTED_ADAPTER_UNIT_ONLY", **facts,
        "native_enforcement_credit": False,
    })


def _p505n_unit_call(tmp_path, stage, invoke):
    # Unit inputs/status/buffers are synthetic; the method under test is real.
    # Retain original returned result/error before caller assertion/matching.
    try:
        result = invoke()
    except BaseException as error:
        _p505c_error_snapshot(tmp_path, "native-unit." + stage, error,
                             tier="SCRIPTED_ADAPTER_UNIT_ONLY",
                             native_enforcement_credit=False)
        raise
    if type(result) is bytes:
        _p505c_write_exact(tmp_path, "native-unit." + stage + ".return.bin", result)
    else:
        _p505c_write_json(tmp_path, "native-unit." + stage + ".return.json", {
            "tier": "SCRIPTED_ADAPTER_UNIT_ONLY",
            "return_type": type(result).__module__ + "." + type(result).__qualname__,
            "result": result if type(result) in {dict, list, tuple, str, int, bool, float, type(None)} else None,
            "native_enforcement_credit": False,
        })
    return result


def _p505n_directory_record(name="alpha.txt", *, following=0, inode=77):
    # Independent FILE_ID_BOTH_DIR_INFO literal layout, no product serializer.
    encoded = name.encode("utf-16-le", "surrogatepass")
    raw = bytearray(104 + len(encoded))
    _p505n_struct.pack_into("<IIqqqqqqIII", raw, 0, following, 0,
        116444736000000010, 116444736000000010, 116444736000000020,
        116444736000000030, 3, 8, 0x80, len(encoded), 0)
    _p505n_struct.pack_into("<Q", raw, 96, inode)
    raw[104:] = encoded
    return bytes(raw)


def _p505n_stream_record(name="::$DATA", *, following=0, size=3):
    encoded = name.encode("utf-16-le", "surrogatepass")
    return _p505n_struct.pack("<IIqq", following, len(encoded), size, 8) + encoded


def _p505n_script_volume(reader, *, result=0, io_status=0, device=7,
                         characteristics=0, filesystem="NTFS", used_override=None):
    calls = []
    def query(handle, status_pointer, buffer, length, information):
        information = _p505n_integer(information)
        assert information in {4, 5}
        raw = (_p505n_struct.pack("<II", device, characteristics) if information == 4 else
               _p505n_struct.pack("<IiI", 0, 255, len(filesystem.encode("utf-16-le"))) + filesystem.encode("utf-16-le"))
        assert len(raw) <= _p505n_integer(length)
        _p505n_c.memmove(buffer, raw, len(raw))
        status = _p505n_c.cast(status_pointer, _p505n_c.POINTER(reader._IoStatusBlock)).contents
        status.State.Status = io_status
        status.Information = (used_override[information] if used_override and information in used_override else len(raw))
        calls.append({"information": information, "allocated": _p505n_integer(length),
                      "reported": int(status.Information), "raw_hex": raw.hex(),
                      "result": result, "io_status": io_status})
        return result
    reader._nt_query_volume = query
    return calls


def _p505n_trace_factory(owner, monkeypatch, root, *, close_fault=None, on_event=None):
    original = _p505n_class(owner)
    root_parts = tuple(str(root)[3:].split("\\"))
    trace = {"tier": "REAL_NATIVE_OBSERVED", "root": str(root), "events": [], "instances": [], "held_text_characters": 0,
             "helper_cleanup": [], "close_fault": close_fault}
    def append(event):
        assert len(trace["events"]) < 4096, "P505_NATIVE_TRACE_BUDGET"
        trace["held_text_characters"] += sum(len(value) for value in event.values() if isinstance(value, str))
        assert trace["held_text_characters"] <= 16 * 1024 * 1024, "P505_NATIVE_TRACE_BYTES_BUDGET"
        trace["events"].append(event)
    class Observed(original):
        def __init__(self, deadline):
            super().__init__(deadline)
            instance = len(trace["instances"])
            phase = "before" if instance == 0 else "after"
            state = {"phase": phase, "opened": [], "closed": set(), "lineages": {},
                     "actual_close": self._close_handle, "close_fault_used": False}
            trace["instances"].append(state)
            def relative(handle):
                parts = state["lineages"].get(handle, ())
                return "/".join(parts[len(root_parts):]) if parts[:len(root_parts)] == root_parts else None
            for attribute in ("_nt_create_file", "_get_file_information", "_nt_query_volume",
                              "_get_file_type", "_read_file", "_close_handle", "_query_dos_device"):
                actual = getattr(self, attribute)
                def wrapped(*args, _attribute=attribute, _actual=actual):
                    event = {"instance": instance, "phase": phase, "function": _attribute}
                    if _attribute == "_nt_create_file":
                        attrs = _p505n_c.cast(args[2], _p505n_c.POINTER(self._ObjectAttributes)).contents
                        string = attrs.ObjectName.contents
                        raw_name = _p505n_c.string_at(string.Buffer, string.Length)
                        parent = _p505n_integer(attrs.RootDirectory)
                        name = raw_name.decode("utf-16-le", "surrogatepass")
                        event.update(parent=parent, component_utf16_hex=raw_name.hex(),
                                     access=_p505n_integer(args[1]), share=_p505n_integer(args[6]),
                                     disposition=_p505n_integer(args[7]), options=_p505n_integer(args[8]),
                                     object_attributes=int(attrs.Attributes))
                    elif _attribute == "_query_dos_device":
                        event.update(drive=str(args[0]), capacity=_p505n_integer(args[2]))
                    else:
                        handle = _p505n_integer(args[0])
                        event.update(handle=handle, relative=relative(handle))
                        if _attribute == "_get_file_information":
                            event.update(information=_p505n_integer(args[1]), allocated=_p505n_integer(args[3]))
                        elif _attribute == "_nt_query_volume":
                            event.update(information=_p505n_integer(args[4]), allocated=_p505n_integer(args[3]))
                        elif _attribute == "_read_file":
                            event["requested"] = _p505n_integer(args[2])
                    if (_attribute == "_close_handle" and phase == "after" and close_fault
                            and not state["close_fault_used"]):
                        state["close_fault_used"] = True
                        event["controlled_test_fault"] = close_fault
                        append(event)
                        if close_fault == "raise":
                            raise OSError("P505_OWNED_CLOSE_FAULT")
                        return 0
                    try:
                        result = _actual(*args)
                    except BaseException as error:
                        event["call_error"] = type(error).__name__ + ":" + str(error)
                        append(event)
                        raise
                    event.update(result=_p505n_integer(result), last_error=_p505n_c.get_last_error())
                    if _attribute == "_nt_create_file":
                        handle = _p505n_c.cast(args[0], _p505n_c.POINTER(_p505n_c.c_void_p)).contents.value
                        status = _p505n_c.cast(args[3], _p505n_c.POINTER(self._IoStatusBlock)).contents
                        event.update(handle=handle, io_status=int(status.State.Status), information=int(status.Information))
                        if (handle not in {None, 0, _p505n_c.c_void_p(-1).value}
                                and event["result"] == 0 and event["io_status"] == 0 and event["information"] == 1):
                            lineage = state["lineages"].get(parent, ()) + (name,) if parent else ()
                            state["lineages"][handle] = lineage
                            state["opened"].append(handle)
                            event["relative"] = relative(handle)
                    elif _attribute == "_read_file":
                        used = _p505n_c.cast(args[3], _p505n_c.POINTER(_p505n_c.c_uint32)).contents.value
                        event["returned"] = used
                        if 0 <= used <= event["requested"] <= 65536:
                            event["returned_bytes_hex"] = _p505n_c.string_at(args[1], used).hex()
                            event["bytes_sha256"] = _p505c_sha(bytes.fromhex(event["returned_bytes_hex"]))
                    elif _attribute == "_get_file_information" and result:
                        assert event["allocated"] <= 65536
                        event["returned_buffer_hex"] = _p505n_c.string_at(args[2], event["allocated"]).hex()
                    elif _attribute == "_nt_query_volume":
                        status = _p505n_c.cast(args[1], _p505n_c.POINTER(self._IoStatusBlock)).contents
                        event.update(io_status=int(status.State.Status), information_bytes=int(status.Information))
                        if 0 <= status.Information <= event["allocated"]:
                            event["returned_buffer_hex"] = _p505n_c.string_at(args[2], status.Information).hex()
                    elif _attribute == "_close_handle" and result:
                        state["closed"].add(handle)
                    append(event)
                    if on_event is not None:
                        on_event(event)
                    return result
                setattr(self, attribute, wrapped)
    monkeypatch.setattr(owner, "_FullWorktreeWindowsReader", Observed)
    return trace


def _p505n_finish(trace, evidence_root):
    # No trace-file writes while capture has retained root ancestors. Close
    # exact remaining owned handles first, explicitly as TEST helper cleanup.
    # These successful calls never repair the product-cleanup verdict.
    for index, state in reversed(list(enumerate(trace["instances"]))):
        for handle in reversed(state["opened"]):
            if handle not in state["closed"]:
                try:
                    result = state["actual_close"](handle)
                except BaseException as error:
                    trace["helper_cleanup"].append({"instance": index, "handle": handle,
                        "result": 0, "error": type(error).__name__ + ":" + str(error), "credit": "TEST_HELPER_ONLY"})
                    continue
                trace["helper_cleanup"].append({"instance": index, "handle": handle,
                    "result": _p505n_integer(result), "credit": "TEST_HELPER_ONLY"})
                if result:
                    state["closed"].add(handle)
        state.pop("actual_close")
        state["closed"] = sorted(state["closed"])
        state["lineages"] = {str(key): list(value) for key, value in state["lineages"].items()}
    _p505c_write_json(evidence_root, "native.actual-trace.json", trace)


def _p505n_active_control(trace, record):
    _p505c_complete(record)
    assert record["entries"]["src/task.py"]["sha256"] == _p505c_sha(b"owned task original\n")
    reads = [event for event in trace["events"] if event["phase"] == "before"
             and event["function"] == "_read_file" and event.get("relative") == "src/task.py"]
    assert reads and sum(event["returned"] for event in reads) == len(b"owned task original\n")
    assert all(event["result"] and event["returned"] > 0 for event in reads)
    assert b"".join(bytes.fromhex(event["returned_bytes_hex"]) for event in reads) == b"owned task original\n"


def _p505n_assert_product_closes(trace):
    for index, state in enumerate(trace["instances"]):
        attempts = [event for event in trace["events"] if event["instance"] == index
                    and event["function"] == "_close_handle"]
        assert [event["handle"] for event in attempts] == list(reversed(state["opened"]))
        if not trace["close_fault"]:
            assert all(event.get("result") for event in attempts)
    if not trace["close_fault"]:
        assert trace["helper_cleanup"] == []


def test_p505n_real_native_hash_trace_and_owned_close_lineage(tmp_path, monkeypatch):
    owner, root, binding = _p505c_case(tmp_path)
    trace = _p505n_trace_factory(owner, monkeypatch, root)
    try:
        _, before = _p505c_capture(owner, root, binding, "before")
        _p505n_active_control(trace, before)
    finally:
        _p505n_finish(trace, root.parent)
    _p505n_assert_product_closes(trace)


@pytest.mark.parametrize("name", [".env", ".git", "private/payload.bin", "control/mode/cost_ledger.jsonl", "key.pem", "approvals/request.json"])
def test_p505n_real_private_refusal_has_zero_native_payload_or_descent(tmp_path, monkeypatch, name):
    owner, root, binding = _p505c_case(tmp_path)
    trace = _p505n_trace_factory(owner, monkeypatch, root)
    try:
        _, before = _p505c_capture(owner, root, binding, "before")
        _p505n_active_control(trace, before)
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"generated inert private refusal sentinel\n")
        _, after = _p505c_capture(owner, root, binding, "after")
        _p505c_refused(after, "private_refused")
        first = name.split("/")[0]
        assert not [event for event in trace["events"] if event["phase"] == "after"
            and event.get("relative") is not None
            and (event["relative"] == first or event["relative"].startswith(first + "/"))
            and (event["function"] == "_read_file" or event["function"] == "_get_file_information"
                 and event.get("information") in {10, 11})]
    finally:
        _p505n_finish(trace, root.parent)
    _p505n_assert_product_closes(trace)


def test_p505n_real_multilink_refusal_has_zero_native_payload(tmp_path, monkeypatch):
    owner, root, binding = _p505c_case(tmp_path)
    trace = _p505n_trace_factory(owner, monkeypatch, root)
    try:
        _, before = _p505c_capture(owner, root, binding, "before")
        _p505n_active_control(trace, before)
        _p505c_os.link(root / "outside/dirty.txt", root / "outside/alias.txt")
        _, after = _p505c_capture(owner, root, binding, "after")
        _p505c_refused(after, "private_refused")
        assert not [event for event in trace["events"] if event["phase"] == "after"
            and event["function"] == "_read_file"
            and event.get("relative") in {"outside/dirty.txt", "outside/alias.txt"}]
    finally:
        _p505n_finish(trace, root.parent)
    _p505n_assert_product_closes(trace)


@pytest.mark.parametrize("fault", ["false", "raise"])
def test_p505n_real_controlled_close_failure_attempts_all_owned_cleanup(tmp_path, monkeypatch, fault):
    owner, root, binding = _p505c_case(tmp_path)
    trace = _p505n_trace_factory(owner, monkeypatch, root, close_fault=fault)
    try:
        _, before = _p505c_capture(owner, root, binding, "before")
        _p505n_active_control(trace, before)
        with pytest.raises(ValueError, match="^capture_unavailable:read_failed"):
            _p505c_capture(owner, root, binding, "after")
    finally:
        _p505n_finish(trace, root.parent)
    _p505n_assert_product_closes(trace)
    assert trace["helper_cleanup"], "The controlled failed product close must remain helper-only cleanup"
    assert all(item["result"] for item in trace["helper_cleanup"])


def test_p505n_unit_x64_layout_and_ffi_prototypes_are_independently_pinned(tmp_path):
    owner = _load()
    # Bind actual prototypes only; no native file API is invoked here.
    reader = _p505n_class(owner)(_p505n_time.monotonic() + 5)
    expected = [(reader._UnicodeString, 16, {"Length": 0, "MaximumLength": 2, "Buffer": 8}),
        (reader._ObjectAttributes, 48, {"Length": 0, "RootDirectory": 8, "ObjectName": 16, "Attributes": 24, "SecurityDescriptor": 32, "SecurityQualityOfService": 40}),
        (reader._IoStatusBlock, 16, {"State": 0, "Information": 8}),
        (reader._BasicInfo, 40, {"CreationTime": 0, "LastAccessTime": 8, "LastWriteTime": 16, "ChangeTime": 24, "FileAttributes": 32}),
        (reader._StandardInfo, 24, {"AllocationSize": 0, "EndOfFile": 8, "NumberOfLinks": 16, "DeletePending": 20, "Directory": 21}),
        (reader._AttributeTagInfo, 8, {"FileAttributes": 0, "ReparseTag": 4}),
        (reader._IdInfo, 24, {"VolumeSerialNumber": 0, "FileId": 8})]
    def type_info(kind):
        if kind is None:
            return None
        result = {"type": kind.__module__ + "." + kind.__qualname__,
                  "size": _p505n_c.sizeof(kind)}
        if hasattr(kind, "_fields_"):
            result["fields"] = [{"name": field[0], "offset": getattr(kind, field[0]).offset,
                                 "size": _p505n_c.sizeof(field[1]),
                                 "type": field[1].__module__ + "." + field[1].__qualname__}
                                for field in kind._fields_]
        return result
    observed = []
    for kind, size, offsets in expected:
        actual = {name: getattr(kind, name).offset for name in offsets}
        observed.append({"type": kind.__name__, "size": _p505n_c.sizeof(kind),
                         "alignment": _p505n_c.alignment(kind), "offsets": actual,
                         "declaration": type_info(kind)})
    scalars = [{"label": label, **type_info(kind)} for label, kind in [
        ("HANDLE_pointer", _p505n_c.c_void_p), ("ULONG", _p505n_c.c_uint32),
        ("NTSTATUS_signed", _p505n_c.c_int32), ("WCHAR", _p505n_c.c_wchar),
        ("BOOLEAN", _p505n_c.c_ubyte)]]
    prototypes = []
    for name in ("_nt_create_file", "_nt_query_volume", "_get_file_information",
                 "_get_file_type", "_read_file", "_close_handle", "_query_dos_device"):
        function = getattr(reader, name)
        prototypes.append({"function": name, "restype": type_info(function.restype),
                           "argtypes": [type_info(kind) for kind in function.argtypes]
                                       if function.argtypes is not None else None})
    # Preserve the full actual table before the first ABI semantic assertion.
    _p505n_unit_evidence(tmp_path, "x64-abi", {"structures": observed,
        "scalars": scalars, "prototypes": prototypes,
        "ntstatus_minus_one": _p505n_c.c_int32(-1).value, "native_file_calls": 0})
    for kind, size, offsets in expected:
        actual = {name: getattr(kind, name).offset for name in offsets}
        assert _p505n_c.sizeof(kind) == size and actual == offsets
    assert [_p505n_c.sizeof(kind) for kind in (_p505n_c.c_void_p, _p505n_c.c_uint32,
        _p505n_c.c_int32, _p505n_c.c_wchar, _p505n_c.c_ubyte)] == [8, 4, 4, 2, 1]
    assert reader._nt_create_file.restype is _p505n_c.c_int32 and len(reader._nt_create_file.argtypes) == 11
    assert reader._nt_query_volume.restype is _p505n_c.c_int32 and len(reader._nt_query_volume.argtypes) == 5
    assert reader._read_file.argtypes[0] is _p505n_c.c_void_p and reader._read_file.argtypes[2] is _p505n_c.c_uint32


@pytest.mark.parametrize("result,io_status,information,handle", [
    (0x103, 0, 1, 4242), (0x40000000, 0, 1, 4242), (-2147483643, 0, 1, 4242),
    (0, 0x103, 1, 4242), (0, 0, 0, 4242), (0, 0, 2, 4242),
    (0, 0, 1, None), (0, 0, 1, 0), (0, 0, 1, _p505n_c.c_void_p(-1).value)])
def test_p505n_unit_nonterminal_or_invalid_open_output_never_becomes_owned_success(tmp_path, result, io_status, information, handle):
    owner = _load()
    reader = _p505n_reader(owner)
    calls = []
    def native(output, access, attributes, status_pointer, allocation, flags, share, disposition, options, ea, ea_length):
        _p505n_c.cast(output, _p505n_c.POINTER(_p505n_c.c_void_p)).contents.value = handle
        status = _p505n_c.cast(status_pointer, _p505n_c.POINTER(reader._IoStatusBlock)).contents
        status.State.Status, status.Information = io_status, information
        calls.append({"access": access, "share": share, "disposition": disposition, "options": options})
        return result
    reader._nt_create_file = native
    reader._close_handle = lambda value: calls.append({"fake_close_only": value}) or 1
    try:
        with pytest.raises(owner._FullCaptureFailure, match="stat_failed"):
            _p505n_unit_call(tmp_path, "test_p505n_unit_nonterminal_or_invalid_open_output_never_becomes_owned_success", lambda: reader.open_relative(None, "\\Device\\HarddiskVolume3\\", 0x100080))
    finally:
        reader.close_all()
        _p505n_unit_evidence(tmp_path, "open-terminal-output", {"script": [result, io_status, information, handle], "calls": calls})
    assert not [call for call in calls if "fake_close_only" in call], "Failed or invalid output is not established owned handle"


@pytest.mark.parametrize("result,io_status,used", [(0x103, 0, None), (0x40000000, 0, None),
    (0, 0x103, None), (0, 0, {4: 0}), (0, 0, {4: 7}), (0, 0, {4: 9}),
    (0, 0, {5: 11}), (0, 0, {5: 1025}), (0, 0, {5: 13})])
def test_p505n_unit_volume_status_and_returned_lengths_are_checked_before_parse(tmp_path, result, io_status, used):
    owner = _load()
    reader = _p505n_reader(owner)
    calls = _p505n_script_volume(reader, result=result, io_status=io_status, used_override=used)
    try:
        with pytest.raises(owner._FullCaptureFailure, match="identity_unavailable"):
            _p505n_unit_call(tmp_path, "test_p505n_unit_volume_status_and_returned_lengths_are_checked_before_parse", lambda: reader._volume(4242))
    finally:
        _p505n_unit_evidence(tmp_path, "volume-boundaries", {"calls": calls})


@pytest.mark.parametrize("device,characteristics,filesystem", [(7, 0x10, "NTFS"),
    (7, 0x40, "NTFS"), (7, 0x1000, "NTFS"), (7, 0x2000, "NTFS"),
    (2, 0, "NTFS"), (7, 0, "ReFS"), (7, 0, "FAT32")])
def test_p505n_unit_remote_or_unsupported_volume_is_not_native_credit(tmp_path, device, characteristics, filesystem):
    owner = _load()
    reader = _p505n_reader(owner)
    calls = _p505n_script_volume(reader, device=device, characteristics=characteristics, filesystem=filesystem)
    try:
        with pytest.raises(owner._FullCaptureFailure, match="nonregular_refused"):
            _p505n_unit_call(tmp_path, "test_p505n_unit_remote_or_unsupported_volume_is_not_native_credit", lambda: reader._volume(4242))
    finally:
        _p505n_unit_evidence(tmp_path, "synthetic-volume-refusal", {"calls": calls, "actual_remote_fixture": False})


@pytest.mark.parametrize("kind,defect", [("directory", "short"), ("directory", "odd-name"),
    ("directory", "cross-buffer"), ("directory", "overlap"), ("directory", "misaligned"),
    ("directory", "offset-past-end"), ("directory", "last-header-truncated"),
    ("stream", "short"), ("stream", "odd-name"), ("stream", "cross-buffer"),
    ("stream", "overlap"), ("stream", "misaligned"), ("stream", "offset-past-end"),
    ("stream", "last-header-truncated")])
def test_p505n_unit_raw_native_record_bounds_fail_closed(tmp_path, kind, defect):
    owner = _load()
    _p505n_class(owner)
    raw = bytearray(_p505n_directory_record() if kind == "directory" else _p505n_stream_record())
    header, length_offset = (104, 60) if kind == "directory" else (24, 4)
    if defect == "short":
        raw = raw[:header - 1]
    elif defect == "odd-name":
        _p505n_struct.pack_into("<I", raw, length_offset, 3)
    elif defect == "cross-buffer":
        _p505n_struct.pack_into("<I", raw, length_offset, len(raw) + 2)
    elif defect == "overlap":
        _p505n_struct.pack_into("<I", raw, 0, 8)
    elif defect == "misaligned":
        _p505n_struct.pack_into("<I", raw, 0, len(raw) + 1)
    elif defect == "offset-past-end":
        _p505n_struct.pack_into("<I", raw, 0, 65528)
    else:
        step = (len(raw) + 7) // 8 * 8
        _p505n_struct.pack_into("<I", raw, 0, step)
        raw.extend(b"\0" * (step - len(raw) + header - 1))
    parser = owner._full_capture_directory_buffer if kind == "directory" else owner._full_capture_stream_buffer
    _p505c_write_exact(tmp_path, "native-unit.buffer.bin", bytes(raw))
    with pytest.raises(owner._FullCaptureFailure, match="read_failed"):
        _p505n_unit_call(tmp_path, "test_p505n_unit_raw_native_record_bounds_fail_closed", lambda: parser(bytes(raw)))


@pytest.mark.parametrize("kind", ["directory", "stream"])
def test_p505n_unit_final_record_exact_buffer_boundary_is_a_valid_batch(tmp_path, kind):
    owner = _load()
    _p505n_class(owner)
    raw = _p505n_directory_record() if kind == "directory" else _p505n_stream_record()
    _p505c_write_exact(tmp_path, "native-unit.boundary-buffer.bin", raw)
    result = _p505n_unit_call(tmp_path, "final-record-boundary", lambda: (owner._full_capture_directory_buffer(raw) if kind == "directory" else owner._full_capture_stream_buffer(raw)))
    assert len(result) == 1
    assert result[0]["name"] == "alpha.txt" if kind == "directory" else result == [("::$DATA", 3, 8)]


@pytest.mark.parametrize("ending", ["duplicate-next-batch", "partial-error-next-batch", "two-distinct-then-explicit-end"])
def test_p505n_unit_enumeration_batch_boundary_and_crossbatch_duplicates(tmp_path, ending):
    owner = _load()
    reader = _p505n_reader(owner)
    replies = [(_p505n_directory_record("alpha.txt"), 0),
        ((_p505n_directory_record("alpha.txt") if ending == "duplicate-next-batch" else _p505n_directory_record("beta.txt")), 234 if ending == "partial-error-next-batch" else 0),
        (None, 18)]
    calls = []
    def query(handle, information, buffer, capacity):
        raw, error = replies.pop(0)
        calls.append({"information": information, "error": error, "raw_hex": raw.hex() if raw else None})
        if raw:
            _p505n_c.memmove(buffer, raw, len(raw))
        _p505n_c.set_last_error(error)
        return 0 if error else 1
    reader._get_file_information = query
    try:
        if ending == "two-distinct-then-explicit-end":
            assert [record["name"] for record in _p505n_unit_call(tmp_path, "test_p505n_unit_enumeration_batch_boundary_and_crossbatch_duplicates", lambda: reader.list_directory(4242, 10))] == ["alpha.txt", "beta.txt"]
            assert replies == []
        else:
            with pytest.raises(owner._FullCaptureFailure, match="unstable" if ending == "duplicate-next-batch" else "read_failed"):
                _p505n_unit_call(tmp_path, "test_p505n_unit_enumeration_batch_boundary_and_crossbatch_duplicates", lambda: reader.list_directory(4242, 10))
    finally:
        _p505n_unit_evidence(tmp_path, "batch-census", {"calls": calls})


@pytest.mark.parametrize("raw_name", ["trailing.", "trailing ", "NUL", "x\ud800y"])
def test_p505n_unit_unsupported_raw_names_cannot_be_omitted_as_complete(tmp_path, raw_name):
    owner = _load()
    reader = _p505n_reader(owner)
    raw = _p505n_directory_record(raw_name)
    _p505c_write_exact(tmp_path, "native-unit.raw-name-buffer.bin", raw)
    def query(handle, information, buffer, capacity):
        _p505n_c.memmove(buffer, raw, len(raw))
        return 1
    reader._get_file_information = query
    with pytest.raises(owner._FullCaptureFailure, match="nonregular_refused"):
        _p505n_unit_call(tmp_path, "test_p505n_unit_unsupported_raw_names_cannot_be_omitted_as_complete", lambda: reader.list_directory(4242, 10))


@pytest.mark.parametrize("fault", ["false", "raise"])
def test_p505n_unit_cleanup_attempts_remaining_handles_and_retains_failure(tmp_path, fault):
    owner = _load()
    reader = _p505n_reader(owner)
    reader.handles = [4201, 4202, 4203]
    calls = []
    def close(handle):
        calls.append(handle)
        if handle == 4203:
            if fault == "raise":
                raise OSError("P505_SCRIPTED_CLOSE_FAULT")
            return 0
        return 1
    reader._close_handle = close  # All handles fake: never call real Windows CloseHandle.
    try:
        with pytest.raises(ValueError, match="^capture_unavailable:read_failed"):
            _p505n_unit_call(tmp_path, "test_p505n_unit_cleanup_attempts_remaining_handles_and_retains_failure", lambda: reader.close_all())
    finally:
        _p505n_unit_evidence(tmp_path, "close-failure", {"fault": fault, "fake_owned_handles": [4201, 4202, 4203], "attempts": calls})
    assert calls == [4203, 4202, 4201]


def test_p505n_unit_required_ancestry_budget_stops_validation_before_native_factory(tmp_path, monkeypatch):
    owner, root, binding = _p505c_case(tmp_path, allowed=["/".join(["owned-depth-token"] * 512) + "/target.txt"])
    native = _p505n_class(owner)
    counts = {"component_checks": 0, "native_factory_calls": 0}
    original_name = owner._full_capture_name
    def counted(value):
        if value == "owned-depth-token":
            counts["component_checks"] += 1
        return original_name(value)
    def forbidden_factory(deadline):
        counts["native_factory_calls"] += 1
        raise AssertionError("P505_NO_NATIVE_CALL_FOR_UNREPRESENTABLE_BUDGET")
    monkeypatch.setattr(owner, "_full_capture_name", counted)
    monkeypatch.setattr(owner, "_FullWorktreeWindowsReader", forbidden_factory)
    try:
        with pytest.raises(ValueError, match="^capture_unavailable:budget_exceeded"):
            _p505c_capture(owner, root, binding, "before", max_entries=2)
    finally:
        _p505n_unit_evidence(tmp_path, "early-ancestry-budget", counts)
    assert counts["native_factory_calls"] == 0
    assert counts["component_checks"] <= 3, "Budget must bound work before scanning all512 repeated ancestry components"


@pytest.mark.parametrize("defect,want", [("offline", "nonregular_refused"),
    ("recall-open", "nonregular_refused"), ("recall-data", "nonregular_refused"),
    ("reparse", "reparse_refused"), ("multilink", "private_refused"),
    ("delete-pending", "nonregular_refused"), ("unknown-id", "identity_unavailable"),
    ("attributes-mismatch", "unstable")])
def test_p505n_unit_metadata_refusals_precede_any_payload_path(tmp_path, defect, want):
    owner = _load()
    reader = _p505n_reader(owner)
    calls = _p505n_script_volume(reader)
    forbidden_reads = []
    reader._read_file = lambda *args: forbidden_reads.append(args) or 0
    reader._get_file_type = lambda handle: 1
    def query(handle, information, buffer, capacity):
        kinds = {0: reader._BasicInfo, 1: reader._StandardInfo, 9: reader._AttributeTagInfo, 18: reader._IdInfo}
        assert information in kinds
        value = kinds[information]()
        attributes = 0x80 | {"offline": 0x1000, "recall-open": 0x40000,
                            "recall-data": 0x400000, "reparse": 0x400}.get(defect, 0)
        if information == 0:
            value.CreationTime = value.LastAccessTime = value.LastWriteTime = value.ChangeTime = 116444736000000100
            value.FileAttributes = attributes
        elif information == 1:
            value.AllocationSize, value.EndOfFile = 8, 3
            value.NumberOfLinks = 2 if defect == "multilink" else 1
            value.DeletePending, value.Directory = int(defect == "delete-pending"), 0
        elif information == 9:
            value.FileAttributes = 0 if defect == "attributes-mismatch" else attributes
            value.ReparseTag = 0xA0000003 if defect == "reparse" else 0
        else:
            value.VolumeSerialNumber = 5
            value.FileId[0] = 0 if defect == "unknown-id" else 77
        assert _p505n_c.sizeof(value) == capacity
        _p505n_c.memmove(buffer, _p505n_c.byref(value), capacity)
        return 1
    reader._get_file_information = query
    try:
        with pytest.raises(owner._FullCaptureFailure, match=want):
            _p505n_unit_call(tmp_path, "test_p505n_unit_metadata_refusals_precede_any_payload_path", lambda: reader.metadata(4242))
    finally:
        _p505n_unit_evidence(tmp_path, "metadata-refusal", {"defect": defect, "volume_calls": calls, "payload_calls": len(forbidden_reads)})
    assert forbidden_reads == []


@pytest.mark.parametrize("directory,name", [(False, ":extra:$DATA"), (True, ":extra:$DATA")])
def test_p505n_unit_nondefault_streams_are_refused_without_content_read(tmp_path, directory, name):
    owner = _load()
    reader = _p505n_reader(owner)
    raw = _p505n_stream_record(name)
    reads = []
    reader._read_file = lambda *args: reads.append(args) or 0
    def query(handle, information, buffer, capacity):
        assert information == 7
        _p505n_c.memmove(buffer, raw, len(raw))
        return 1
    reader._get_file_information = query
    _p505c_write_exact(tmp_path, "native-unit.named-stream-buffer.bin", raw)
    with pytest.raises(owner._FullCaptureFailure, match="private_refused"):
        _p505n_unit_call(tmp_path, "test_p505n_unit_nondefault_streams_are_refused_without_content_read", lambda: reader.streams(4242, directory))
    assert reads == []


def test_p505n_unit_virtual_tree_depth_is_controlled_before_python_recursion_limit(tmp_path, monkeypatch):
    owner, root, binding = _p505c_case(tmp_path, allowed=["missing.txt"])
    _p505n_class(owner)
    observations = {"tier": "SCRIPTED_ADAPTER_UNIT_ONLY", "listed_depths": [], "closed": False}
    class VirtualReader:
        def __init__(self, deadline):
            self.handles, self.guards = [1, 2], {}
            self.directory_guards, self.stream_guards = {}, {}
            self.depths = {1: -1, 2: 0}
            self.guards[2] = self.metadata(2)
        def tick(self):
            assert len(self.handles) < 4096, "P505_VIRTUAL_FIXTURE_BOUND"
        def drive_mapping(self, drive):
            return "\\Device\\HarddiskVolume3"
        def open_root(self, drive, components):
            return 2, self.drive_mapping(drive)
        def open_relative(self, parent, name, access):
            handle = max(self.depths) + 1
            self.depths[handle] = self.depths[parent] + 1
            self.handles.append(handle)
            return handle
        def metadata(self, handle):
            depth = self.depths[handle]
            return {"identity": {"device": 5, "inode": 100 + depth}, "attributes": 0x10,
                    "directory": True, "links": 1, "size": 0, "mode": 0o40755,
                    "created": 116444736000000100, "modified": 116444736000000100,
                    "changed": 116444736000000100, "ctime_ns": 10000, "mtime_ns": 10000,
                    "volume": (7, 0, "NTFS")}
        def streams(self, handle, is_directory):
            assert is_directory
            return []
        def list_directory(self, handle, maximum):
            depth = self.depths[handle]
            observations["listed_depths"].append(depth)
            return [] if depth >= 512 else [{"name": "level%03d" % depth,
                "inode": 101 + depth, "attributes": 0x10, "size": 0,
                "created": 116444736000000100, "modified": 116444736000000100,
                "changed": 116444736000000100}]
        def close_all(self):
            self.handles.clear()
            observations["closed"] = True
    monkeypatch.setattr(owner, "_FullWorktreeWindowsReader", VirtualReader)
    try:
        _, record = _p505c_capture(owner, root, binding, "before")
        # Directory metadata may be genuinely known while its deeper census
        # is unavailable. Do not invent an unobserved node for known metadata.
        coverage = record["coverage"]
        assert not (coverage["enumeration_complete"] and coverage["inspection_complete"])
        assert any(error["reason"] == "budget_exceeded" for error in coverage["errors"])
    finally:
        _p505n_unit_evidence(tmp_path, "virtual-depth-budget", observations)
    assert observations["closed"] is True
    assert observations["listed_depths"] and max(observations["listed_depths"]) < 128


def _p505n_create_owned_native_fixture(root, kind):
    # HELD until this exact helper is independently reviewed by root. Fixed
    # generated endpoints only; no privilege, account, ACL, policy or process.
    calls = {"tier": "TEST_FIXTURE_CREATION_ONLY_NOT_COLLECTOR_ENFORCEMENT", "kind": kind, "calls": []}
    _p505c_write_json(root.parent, "native.fixture-plan.json", {
        "root": str(root), "kind": kind, "all_targets_owned_generated": True,
        "no_privilege_adjustment": True,
    })
    kernel = _p505n_c.WinDLL("kernel32", use_last_error=True)
    create, close = kernel.CreateFileW, kernel.CloseHandle
    create.argtypes = [_p505n_c.c_wchar_p, _p505n_c.c_uint32, _p505n_c.c_uint32,
                      _p505n_c.c_void_p, _p505n_c.c_uint32, _p505n_c.c_uint32, _p505n_c.c_void_p]
    create.restype = _p505n_c.c_void_p
    close.argtypes, close.restype = [_p505n_c.c_void_p], _p505n_c.c_int32
    handle = None
    try:
        if kind in {"file-ads", "directory-ads"}:
            base = root / ("outside/dirty.txt" if kind == "file-ads" else "outside")
            path = "\\\\?\\" + str(base) + ":p505-owned:$DATA"
            handle = create(path, 2, 7, None, 1, 0x80, None)
            calls["calls"].append({"function": "CreateFileW", "path": path, "handle": handle, "error": _p505n_c.get_last_error()})
            if handle in {None, 0, _p505n_c.c_void_p(-1).value}:
                raise RuntimeError("P505_FIXTURE_UNQUALIFIED:owned ADS creation failed")
            write = kernel.WriteFile
            write.argtypes = [_p505n_c.c_void_p, _p505n_c.c_void_p, _p505n_c.c_uint32,
                              _p505n_c.POINTER(_p505n_c.c_uint32), _p505n_c.c_void_p]
            write.restype = _p505n_c.c_int32
            payload = b"owned generated alternate stream sentinel\n"
            used = _p505n_c.c_uint32()
            buffer = _p505n_c.create_string_buffer(payload)
            result = write(handle, buffer, len(payload), _p505n_c.byref(used), None)
            calls["calls"].append({"function": "WriteFile", "result": result, "bytes": used.value, "sha256": _p505c_sha(payload)})
            if not result or used.value != len(payload):
                raise RuntimeError("P505_FIXTURE_UNQUALIFIED:owned ADS payload creation failed")
        else:
            assert kind == "junction"
            target, link = root / "private", root / "alias"
            target.mkdir()
            (target / "payload.bin").write_bytes(b"owned generated private junction target; collector never reads\n")
            link.mkdir()
            path = "\\\\?\\" + str(link)
            handle = create(path, 0x40000000, 7, None, 3, 0x02200000, None)
            calls["calls"].append({"function": "CreateFileW", "path": path, "handle": handle, "error": _p505n_c.get_last_error()})
            if handle in {None, 0, _p505n_c.c_void_p(-1).value}:
                raise RuntimeError("P505_FIXTURE_UNQUALIFIED:owned junction handle failed")
            substitute, printed = ("\\??\\" + str(target)).encode("utf-16-le"), str(target).encode("utf-16-le")
            paths = substitute + b"\0\0" + printed + b"\0\0"
            body = _p505n_struct.pack("<HHHH", 0, len(substitute), len(substitute) + 2, len(printed)) + paths
            raw = _p505n_struct.pack("<IHH", 0xA0000003, len(body), 0) + body
            assert len(raw) <= 16384
            control = kernel.DeviceIoControl
            control.argtypes = [_p505n_c.c_void_p, _p505n_c.c_uint32, _p505n_c.c_void_p,
                                _p505n_c.c_uint32, _p505n_c.c_void_p, _p505n_c.c_uint32,
                                _p505n_c.POINTER(_p505n_c.c_uint32), _p505n_c.c_void_p]
            control.restype = _p505n_c.c_int32
            used, buffer = _p505n_c.c_uint32(), _p505n_c.create_string_buffer(raw)
            result = control(handle, 0x000900A4, buffer, len(raw), None, 0, _p505n_c.byref(used), None)
            calls["calls"].append({"function": "DeviceIoControl", "control": 0x000900A4,
                                    "result": result, "error": _p505n_c.get_last_error(), "raw_hex": raw.hex()})
            if not result:
                raise RuntimeError("P505_FIXTURE_UNQUALIFIED:owned junction setup failed")
    except BaseException as error:
        calls["error"] = type(error).__name__ + ":" + str(error)
        raise
    finally:
        if handle not in {None, 0, _p505n_c.c_void_p(-1).value}:
            result = close(handle)
            calls["calls"].append({"function": "CloseHandle", "result": result})
            if not result:
                calls["cleanup_error"] = "owned native fixture handle close failed"
        _p505c_write_json(root.parent, "native.fixture-actual.json", calls)
        if calls.get("cleanup_error"):
            raise RuntimeError("P505_FIXTURE_UNQUALIFIED:" + calls["cleanup_error"])


@pytest.mark.parametrize("kind", ["file-ads", "directory-ads", "junction"])
def test_p505n_real_owned_ads_or_junction_never_reaches_refused_payload(tmp_path, monkeypatch, kind):
    owner, root, binding = _p505c_case(tmp_path)
    trace = _p505n_trace_factory(owner, monkeypatch, root)
    try:
        _, before = _p505c_capture(owner, root, binding, "before")
        _p505n_active_control(trace, before)
        _p505n_create_owned_native_fixture(root, kind)
        _, after = _p505c_capture(owner, root, binding, "after")
        if kind == "junction":
            assert after["entries"]["alias"] == {"kind": "unobserved", "reason": "reparse_refused"}
            forbidden = {"alias", "private"}
        else:
            assert not (after["coverage"]["enumeration_complete"] and after["coverage"]["inspection_complete"])
            assert any(error["reason"] == "private_refused" for error in after["coverage"]["errors"])
            forbidden = {"outside/dirty.txt"} if kind == "file-ads" else {"outside"}
        assert not [event for event in trace["events"] if event["phase"] == "after"
            and event.get("relative") is not None and any(event["relative"] == name
                or event["relative"].startswith(name + "/") for name in forbidden)
            and (event["function"] == "_read_file" or event["function"] == "_get_file_information"
                 and event.get("information") in {10, 11})]
    finally:
        _p505n_finish(trace, root.parent)
    _p505n_assert_product_closes(trace)


@pytest.mark.parametrize("boundary", ["file-metadata-to-data", "after-first-read", "after-initial-root-census"])
def test_p505n_real_owned_boundary_mutation_records_actual_block_or_refusal(tmp_path, monkeypatch, boundary):
    owner, root, binding = _p505c_case(tmp_path)
    mutation = {"boundary": boundary, "attempted": False, "changed": False, "blocked": False}
    def event_hook(event):
        if mutation["attempted"] or event["phase"] != "after":
            return
        at_boundary = ((boundary == "file-metadata-to-data" and event["function"] == "_nt_create_file"
            and event.get("relative") == "src/task.py" and event.get("access") == 0x100080)
            or (boundary == "after-first-read" and event["function"] == "_read_file"
                and event.get("relative") == "src/task.py")
            or (boundary == "after-initial-root-census" and event["function"] == "_get_file_information"
                and event.get("relative") == "" and event.get("information") == 11 and event.get("result")))
        if not at_boundary:
            return
        mutation["attempted"] = True
        target = root / "src/task.py"
        try:
            if boundary == "file-metadata-to-data":
                target.rename(root.parent / "preserved-original-src.bin")
                target.write_bytes(b"owned distinct replacement object, forbidden before ID check\n")
            elif boundary == "after-first-read":
                facts = target.stat()
                _p505c_os.utime(target, ns=(facts.st_atime_ns, facts.st_mtime_ns + 2_000_000_000))
            else:
                (root / "new-arrived.txt").write_bytes(b"owned new census sibling\n")
            mutation["changed"] = True
        except OSError as error:
            mutation.update(blocked=True, error_type=type(error).__name__, error=str(error),
                            winerror=getattr(error, "winerror", None), errno=error.errno)
    trace = _p505n_trace_factory(owner, monkeypatch, root, on_event=event_hook)
    trace["controlled_mutation"] = mutation
    try:
        _, before = _p505c_capture(owner, root, binding, "before")
        _p505n_active_control(trace, before)
        try:
            _, after = _p505c_capture(owner, root, binding, "after")
        except ValueError as error:
            assert str(error).startswith("capture_unavailable:unstable"), str(error)
            assert mutation["changed"] is True
            mutation["outcome"] = "actual_changed_state_named_unavailable"
        else:
            assert mutation["attempted"] is True
            if mutation["changed"]:
                assert not (after["coverage"]["enumeration_complete"] and after["coverage"]["inspection_complete"])
                assert any(error["reason"] == "unstable" for error in after["coverage"]["errors"])
                mutation["outcome"] = "actual_changed_state_incomplete"
            else:
                assert mutation["blocked"] is True
                _p505c_complete(after)
                assert after["entries"]["src/task.py"]["sha256"] == _p505c_sha(b"owned task original\n")
                mutation["outcome"] = "actual_mutation_blocked_stable_object_only"
        if boundary == "file-metadata-to-data" and mutation["changed"]:
            assert not [event for event in trace["events"] if event["phase"] == "after"
                and event["function"] == "_read_file" and event.get("relative") == "src/task.py"]
    finally:
        _p505n_finish(trace, root.parent)
    _p505n_assert_product_closes(trace)


@pytest.mark.parametrize("access", [0x100080, 0x100081])
def test_p505n_unit_relative_open_checks_parent_and_literal_component_before_native(tmp_path, access):
    owner = _load()
    reader = _p505n_reader(owner)
    expected_parent = {"directory": True, "identity": {"device": 5, "inode": 7}}
    reader.guards[4000] = expected_parent
    calls = []
    def metadata(handle):
        calls.append({"stage": "parent-guard", "handle": handle})
        assert handle == 4000
        return _p505c_copy.deepcopy(expected_parent)
    def native(output, requested, attributes, status_pointer, allocation, flags, share, disposition, options, ea, ea_length):
        attrs = _p505n_c.cast(attributes, _p505n_c.POINTER(reader._ObjectAttributes)).contents
        name = attrs.ObjectName.contents
        calls.append({"stage": "native-open", "parent": attrs.RootDirectory,
            "component": _p505n_c.string_at(name.Buffer, name.Length).decode("utf-16-le"),
            "access": requested, "share": share, "disposition": disposition,
            "options": options, "attributes": attrs.Attributes})
        _p505n_c.cast(output, _p505n_c.POINTER(_p505n_c.c_void_p)).contents.value = 4242
        status = _p505n_c.cast(status_pointer, _p505n_c.POINTER(reader._IoStatusBlock)).contents
        status.State.Status, status.Information = 0, 1
        return 0
    reader.metadata, reader._nt_create_file = metadata, native
    reader._close_handle = lambda handle: calls.append({"stage": "scripted-owned-close", "handle": handle}) or 1
    try:
        assert _p505n_unit_call(tmp_path, "test_p505n_unit_relative_open_checks_parent_and_literal_component_before_native", lambda: reader.open_relative(4000, "literal[child].txt", access)) == 4242
    finally:
        reader.close_all()
        _p505n_unit_evidence(tmp_path, "relative-open-order", {"calls": calls})
    assert calls == [{"stage": "parent-guard", "handle": 4000},
        {"stage": "native-open", "parent": 4000, "component": "literal[child].txt", "access": access,
         "share": 1, "disposition": 1, "options": 0x00600020, "attributes": 0},
        {"stage": "scripted-owned-close", "handle": 4242}]


def test_p505n_unit_changed_retained_parent_stops_before_native_open(tmp_path):
    owner = _load()
    reader = _p505n_reader(owner)
    reader.guards[4000] = {"directory": True, "identity": {"device": 5, "inode": 7}}
    reader.metadata = lambda handle: {"directory": True, "identity": {"device": 5, "inode": 8}}
    calls = []
    reader._nt_create_file = lambda *args: calls.append("UNEXPECTED_NATIVE_OPEN") or 0
    try:
        with pytest.raises(owner._FullCaptureFailure, match="unstable"):
            _p505n_unit_call(tmp_path, "test_p505n_unit_changed_retained_parent_stops_before_native_open", lambda: reader.open_relative(4000, "child.txt", 0x100080))
    finally:
        _p505n_unit_evidence(tmp_path, "changed-parent", {"native_open_calls": calls})
    assert calls == []


def test_p505n_unit_metadata_to_data_identity_mismatch_never_reads_bytes(tmp_path, monkeypatch):
    owner, root, binding = _p505c_case(tmp_path, allowed=["task.txt"])
    _p505n_class(owner)
    facts = {"read_calls": 0, "closed": False, "tier": "SCRIPTED_ADAPTER_UNIT_ONLY"}
    class TransitionReader:
        def __init__(self, deadline):
            self.handles, self.guards = [1, 2], {}
            self.directory_guards, self.stream_guards = {}, {}
            self.kinds = {1: "root", 2: "root"}
            self.guards[2] = self.metadata(2)
        def tick(self):
            assert len(self.handles) <= 16
        def drive_mapping(self, drive):
            return "\\Device\\HarddiskVolume3"
        def open_root(self, drive, components):
            return 2, self.drive_mapping(drive)
        def open_relative(self, parent, name, access):
            handle = max(self.kinds) + 1
            self.kinds[handle] = "root" if parent == 1 else "different-file" if access == 0x100081 else "file"
            self.handles.append(handle)
            return handle
        def metadata(self, handle):
            directory = self.kinds[handle] == "root"
            inode = 100 if directory else 999 if self.kinds[handle] == "different-file" else 77
            return {"identity": {"device": 5, "inode": inode}, "attributes": 0x10 if directory else 0x80,
                "directory": directory, "links": 1, "size": 0 if directory else 3,
                "mode": 0o40755 if directory else 0o100666,
                "created": 116444736000000100, "modified": 116444736000000100,
                "changed": 116444736000000100, "ctime_ns": 10000, "mtime_ns": 10000, "volume": (7, 0, "NTFS")}
        def streams(self, handle, is_directory):
            return [] if is_directory else [("::$DATA", 3, 8)]
        def list_directory(self, handle, maximum):
            return [{"name": "task.txt", "inode": 77, "attributes": 0x80, "size": 3,
                "created": 116444736000000100, "modified": 116444736000000100, "changed": 116444736000000100}]
        def read(self, handle, count):
            facts["read_calls"] += 1
            raise AssertionError("P505_IDENTITY_MISMATCH_READ_FORBIDDEN")
        def close_all(self):
            self.handles.clear()
            facts["closed"] = True
    monkeypatch.setattr(owner, "_FullWorktreeWindowsReader", TransitionReader)
    try:
        _, record = _p505c_capture(owner, root, binding, "before")
        assert record["entries"]["task.txt"] == {"kind": "unobserved", "reason": "unstable"}
        _p505c_refused(record, "unstable")
    finally:
        _p505n_unit_evidence(tmp_path, "metadata-data-mismatch", facts)
    assert facts["read_calls"] == 0 and facts["closed"] is True


@pytest.mark.parametrize("defect", ["pointer", "wchar", "structure"])
def test_p505n_unit_bad_abi_refuses_before_dll_or_file_api_binding(tmp_path, monkeypatch, defect):
    owner = _load()
    kind = _p505n_class(owner)
    original_sizeof = _p505n_c.sizeof
    calls = []
    def sizeof(value):
        if defect == "pointer" and value is _p505n_c.c_void_p:
            return 4
        if defect == "wchar" and value is _p505n_c.c_wchar:
            return 4
        if defect == "structure" and getattr(value, "__name__", None) == "UnicodeString":
            return 15
        return original_sizeof(value)
    def forbidden_dll(*args, **kwargs):
        calls.append("UNEXPECTED_DLL_BINDING")
        raise AssertionError("P505_BAD_ABI_MUST_NOT_BIND_NATIVE_APIS")
    try:
        with monkeypatch.context() as scoped:
            scoped.setattr(_p505n_c, "sizeof", sizeof)
            scoped.setattr(_p505n_c, "WinDLL", forbidden_dll)
            with pytest.raises(ValueError, match="^capture_unavailable:(?:identity_unavailable|nonregular_refused)"):
                _p505n_unit_call(tmp_path, "test_p505n_unit_bad_abi_refuses_before_dll_or_file_api_binding", lambda: kind(_p505n_time.monotonic() + 5))
    finally:
        _p505n_unit_evidence(tmp_path, "bad-abi-before-native", {"defect": defect, "dll_calls": calls})
    assert calls == []


def test_p505n_unit_valid_volume_buffer_control_has_exact_literal_identity(tmp_path):
    owner = _load()
    reader = _p505n_reader(owner)
    calls = _p505n_script_volume(reader)
    try:
        assert _p505n_unit_call(tmp_path, "test_p505n_unit_valid_volume_buffer_control_has_exact_literal_identity", lambda: reader._volume(4242)) == (7, 0, "NTFS")
        assert [entry["information"] for entry in calls] == [4, 5]
        assert [entry["reported"] for entry in calls] == [8, 20]
    finally:
        _p505n_unit_evidence(tmp_path, "valid-volume-buffer", {"calls": calls})


# Attempt2 cause: advisory Link census fields are not current handle facts.
# Every test below is scripted adapter coverage, not native Windows evidence.
def _p505a_directory_bytes(name, inode, directory, advisory, version, defect=None):
    encoded = name.encode("utf-16-le")
    raw = bytearray(104 + len(encoded))
    if advisory == "matching":
        created = accessed = modified = changed = 116444736000001000
        size, allocation = (0, 0) if directory else (3, 8)
        attributes = 0x10 if directory else 0x80
    else:
        # All duplicated fields differ from authoritative handle observations;
        # the second census changes them again without changing name/ID/type.
        created = 116444736000000100 + version
        accessed = 116444736000000200 + version
        modified = 116444736000000300 + version
        changed = 116444736000000400 + version
        size, allocation = 999 + version, 8192 + version * 8192
        attributes = (0x10 if directory else 0) | (0x22 if version == 0 else 0x1404)
    if defect == "id":
        inode += 1
    elif defect == "type":
        attributes ^= 0x10
    _p505n_struct.pack_into("<IIqqqqqqIII", raw, 0, 0, 0, created, accessed,
        modified, changed, size, allocation, attributes, len(encoded), 0)
    _p505n_struct.pack_into("<Q", raw, 96, inode)
    raw[104:] = encoded
    return bytes(raw)


def _p505a_scripted_factory(owner, monkeypatch, root, advisory, defect):
    _p505n_class(owner)
    audit = {"tier": "SCRIPTED_ADAPTER_UNIT_ONLY", "advisory": advisory, "defect": defect,
             "native_calls": 0, "instances": [], "raw_inputs": {}}
    for phase in ("before", "after"):
        phase_defect = None if phase == "before" else defect
        for directory in ("root", "src"):
            for version in (0, 1):
                name, inode, is_directory = ("src", 30, True) if directory == "root" else ("task.py", 77, False)
                row_defect = None
                if directory == "src" and phase_defect in {"entry-id", "entry-type"}:
                    row_defect = phase_defect.removeprefix("entry-")
                if directory == "root" and version and phase_defect in {"recensus-name", "recensus-id", "recensus-type"}:
                    if phase_defect == "recensus-name":
                        name = "different-src"
                    else:
                        row_defect = phase_defect.removeprefix("recensus-")
                raw = _p505a_directory_bytes(name, inode, is_directory, advisory, version, row_defect)
                stage = phase + "." + directory + "." + str(version)
                audit["raw_inputs"][stage] = {"sha256": _p505c_sha(raw), "bytes": len(raw), "raw_hex": raw.hex()}
                # Persist exact literal native-buffer input before producer use.
                _p505c_write_exact(root.parent, "attempt02.input." + stage + ".bin", raw)
    _p505c_write_json(root.parent, "attempt02.script-inputs.json", {
        "tier": audit["tier"], "advisory": advisory, "defect": defect,
        "actual_handle_facts": {"device": 5, "root_inode": 100, "src_inode": 30,
            "file_inode": 77, "created_modified_changed": 116444736000001000,
            "file_size": 3, "file_attributes": 0x80, "directory_attributes": 0x10,
            "file_payload_hex": b"abc".hex(), "file_sha256": _p505c_sha(b"abc")},
        "raw_inputs": audit["raw_inputs"], "authority": "declared synthetic fixture only",
    })
    class ScriptedReader:
        def __init__(self, deadline):
            phase = "before" if not audit["instances"] else "after"
            self.phase = phase
            self.defect = None if phase == "before" else defect
            self.state = {"phase": phase, "metadata": [], "census": [], "reads": [],
                          "operations": 0, "closed": False, "file_metadata_queries": 0,
                          "current_change_observed": False, "changed_recensus_supplied": False}
            audit["instances"].append(self.state)
            self.handles, self.guards = [1, 2], {}
            self.directory_guards, self.stream_guards = {}, {}
            self.nodes = {1: ("parent", False), 2: ("root", False)}
            self.query_counts, self.census_counts, self.positions = {}, {}, {}
            self.guards[2] = self.metadata(2)
        def tick(self):
            self.state["operations"] += 1
            assert self.state["operations"] <= 512 and len(self.handles) <= 32, "P505_ATTEMPT2_SCRIPT_BOUND"
        def drive_mapping(self, drive):
            return "\\Device\\HarddiskVolume3"
        def open_root(self, drive, components):
            return 2, self.drive_mapping(drive)
        def open_relative(self, parent, name, access):
            self.tick()
            if parent == 1:
                assert name == root.name
                kind = "root"
            elif self.nodes[parent][0] == "root":
                assert name == "src"
                kind = "src"
            else:
                assert self.nodes[parent][0] == "src" and name == "task.py"
                kind = "file"
            assert access in {0x100080, 0x100081}
            handle = max(self.nodes) + 1
            self.nodes[handle] = kind, kind == "file" and access == 0x100081
            self.handles.append(handle)
            return handle
        def metadata(self, handle):
            self.tick()
            kind, data = self.nodes[handle]
            directory = kind != "file"
            inode = {"parent": 99, "root": 100, "src": 30, "file": 77}[kind]
            value = {"identity": {"device": 5, "inode": inode},
                "attributes": 0x10 if directory else 0x80, "directory": directory,
                "links": 1, "size": 0 if directory else 3,
                "mode": 0o40755 if directory else 0o100666,
                "created": 116444736000001000, "modified": 116444736000001000,
                "changed": 116444736000001000, "ctime_ns": 100000, "mtime_ns": 100000,
                "volume": (7, 0, "NTFS")}
            if kind == "file":
                self.state["file_metadata_queries"] += 1
                if self.defect == "entry-volume":
                    value["identity"]["device"] = 6
            self.query_counts[handle] = self.query_counts.get(handle, 0) + 1
            if data and self.defect and self.defect.startswith("current-") and self.query_counts[handle] >= 3:
                field = self.defect.removeprefix("current-")
                if field in {"inode", "device"}:
                    value["identity"][field] += 1
                elif field == "attributes":
                    value[field] ^= 2
                else:
                    value[field] += 1
                    if field == "created":
                        value["ctime_ns"] += 100
                    elif field == "modified":
                        value["mtime_ns"] += 100
                self.state["current_change_observed"] = True
            self.state["metadata"].append({"handle": handle, "kind": kind, "data_handle": data,
                "query_index": self.query_counts[handle], "raw_facts": _p505c_copy.deepcopy(value)})
            return value
        def streams(self, handle, is_directory):
            self.tick()
            assert is_directory == (self.nodes[handle][0] != "file")
            return [] if is_directory else [("::$DATA", 3, 8)]
        def list_directory(self, handle, maximum):
            self.tick()
            kind = self.nodes[handle][0]
            assert kind in {"root", "src"}
            version = 0 if not self.census_counts.get(handle) else 1
            self.census_counts[handle] = self.census_counts.get(handle, 0) + 1
            stage = self.phase + "." + kind + "." + str(version)
            raw = bytes.fromhex(audit["raw_inputs"][stage]["raw_hex"])
            # Exercise the unchanged real byte-buffer parser, not a mock parser.
            parsed = owner._full_capture_directory_buffer(raw)
            self.state["census"].append({"handle": handle, "kind": kind, "version": version,
                "raw_sha256": _p505c_sha(raw), "records": _p505c_copy.deepcopy(parsed)})
            if kind == "root" and version and self.defect and self.defect.startswith("recensus-"):
                self.state["changed_recensus_supplied"] = True
            return parsed
        def read(self, handle, count):
            self.tick()
            assert self.nodes[handle] == ("file", True) and 0 < count <= 65536
            position = self.positions.get(handle, 0)
            chunk = b"abc"[position:position + count]
            self.positions[handle] = position + len(chunk)
            self.state["reads"].append({"handle": handle, "requested": count,
                "returned_hex": chunk.hex(), "returned_sha256": _p505c_sha(chunk)})
            return chunk
        def close_all(self):
            self.state["scripted_close_attempts"] = list(reversed(self.handles))
            self.handles.clear()
            self.state["closed"] = True
    monkeypatch.setattr(owner, "_FullWorktreeWindowsReader", ScriptedReader)
    return audit


def _p505a_pair(owner, root, binding, audit):
    try:
        return _p505c_pair(owner, root, binding, lambda: None)
    finally:
        # Exact scripted replies and original manifests/context/result are kept
        # before any caller assertion. No real FFI/native positive is inferred.
        _p505c_write_json(root.parent, "attempt02.actual-script-observations.json", audit)


@pytest.mark.parametrize("advisory", ["matching", "stale"])
def test_p505n_attempt02_scripted_advisory_census_fields_do_not_override_current_handle_facts(tmp_path, monkeypatch, advisory):
    owner, root, binding = _p505c_case(tmp_path, initial={"src/task.py": b"abc"})
    audit = _p505a_scripted_factory(owner, monkeypatch, root, advisory, None)
    before, after, result = _p505a_pair(owner, root, binding, audit)
    _p505c_complete(before)
    _p505c_complete(after)
    assert set(before["entries"]) == {"src", "src/task.py"}
    for record in (before, after):
        node = record["entries"]["src/task.py"]
        assert node["sha256"] == _p505c_sha(b"abc") and node["size"] == 3
        assert node["identity"] == {"device": 5, "inode": 77}
        assert node["file_attributes"] == 0x80 and node["ctime_ns"] == 100000 and node["mtime_ns"] == 100000
    assert result["preservation_status"] == "compared" and result["changed_files"] == []
    assert result["result_safe_to_package"] is True
    assert result["preservation_assurance"] == "supplied_manifest_comparison_only"
    assert audit["native_calls"] == 0 and all(state["closed"] for state in audit["instances"])
    assert [len(state["reads"]) for state in audit["instances"]] == [1, 1]
    if advisory == "stale":
        for state in audit["instances"]:
            rows = [entry for entry in state["census"] if entry["kind"] == "src"]
            assert {entry["version"] for entry in rows} == {0, 1}
            assert rows[0]["records"] != rows[-1]["records"]


@pytest.mark.parametrize("defect", ["entry-id", "entry-type", "entry-volume"])
def test_p505n_attempt02_scripted_namespace_identity_type_or_volume_mismatch_prevents_payload(tmp_path, monkeypatch, defect):
    owner, root, binding = _p505c_case(tmp_path, initial={"src/task.py": b"abc"})
    audit = _p505a_scripted_factory(owner, monkeypatch, root, "stale", defect)
    before, after, result = _p505a_pair(owner, root, binding, audit)
    _p505c_complete(before)
    assert len(audit["instances"][0]["reads"]) == 1
    _p505c_refused(after, "unstable")
    assert after["entries"]["src/task.py"] == {"kind": "unobserved", "reason": "unstable"}
    assert audit["instances"][1]["file_metadata_queries"] > 0
    assert audit["instances"][1]["reads"] == []
    assert result["preservation_status"] == "incomplete" and result["result_safe_to_package"] is False


@pytest.mark.parametrize("defect", ["recensus-name", "recensus-id", "recensus-type"])
def test_p505n_attempt02_scripted_final_semantic_census_change_still_blocks_completeness(tmp_path, monkeypatch, defect):
    owner, root, binding = _p505c_case(tmp_path, initial={"src/task.py": b"abc"})
    audit = _p505a_scripted_factory(owner, monkeypatch, root, "stale", defect)
    before, after, result = _p505a_pair(owner, root, binding, audit)
    _p505c_complete(before)
    assert all(len(state["reads"]) == 1 for state in audit["instances"])
    assert audit["instances"][1]["changed_recensus_supplied"] is True
    assert not (after["coverage"]["enumeration_complete"] and after["coverage"]["inspection_complete"])
    assert any(error["reason"] == "unstable" for error in after["coverage"]["errors"])
    assert result["preservation_status"] == "incomplete" and result["result_safe_to_package"] is False


@pytest.mark.parametrize("defect", ["current-created", "current-modified", "current-changed",
    "current-size", "current-attributes", "current-inode", "current-device"])
def test_p505n_attempt02_scripted_actual_current_handle_metadata_changes_remain_unstable(tmp_path, monkeypatch, defect):
    owner, root, binding = _p505c_case(tmp_path, initial={"src/task.py": b"abc"})
    audit = _p505a_scripted_factory(owner, monkeypatch, root, "stale", defect)
    before, after, result = _p505a_pair(owner, root, binding, audit)
    _p505c_complete(before)
    assert all(len(state["reads"]) == 1 for state in audit["instances"])
    assert audit["instances"][1]["current_change_observed"] is True
    _p505c_refused(after, "unstable")
    assert result["preservation_status"] == "incomplete" and result["result_safe_to_package"] is False


def test_original_status_bytes_export_without_text_reconstruction(tmp_path):
    import base64
    import hashlib
    m = _load()
    payload = b'## main\0R  dest\nname.py\0src\xff.py\0?? literal -> name.py\0'
    status_key = ('--no-optional-locks', 'status', '--porcelain=v1', '-z', '--branch', '--untracked-files=all')
    runner = _runner({('rev-parse', '--show-toplevel'): (0, str(tmp_path), ''),
                      ('branch', '--show-current'): (0, 'main\n', ''), status_key: (0, payload, b'')})
    report = m.collect_repo_state(tmp_path, runner=runner)
    evidence = report['status_evidence']
    assert base64.b64decode(evidence['raw_base64'], validate=True) == payload
    assert evidence['sha256'] == hashlib.sha256(payload).hexdigest()
    assert evidence['paths'] == sorted(['dest\nname.py', 'src\udcff.py', 'literal -> name.py'])
    assert m.validate_status_evidence(evidence) == evidence


def test_original_status_export_retains_bad_bytes_but_acceptance_rejects_them(tmp_path):
    import base64
    m = _load()
    raw = b'## main\0R  missing-source.py\0'
    evidence = m.capture_status_evidence(raw)
    assert base64.b64decode(evidence['raw_base64']) == raw
    with pytest.raises(ValueError):
        m.validate_status_evidence(evidence)
    for field, value in [('sha256', '0' * 64), ('paths', ['other.py']), ('raw_base64', 'invalid')]:
        original = m.capture_status_evidence(b'## main\0?? file.py\0')
        original[field] = value
        with pytest.raises(ValueError):
            m.validate_status_evidence(original)
    with pytest.raises(ValueError):
        m.capture_status_evidence('## main\n')


def _private_boundary_scripted_case(tmp_path, monkeypatch):
    """Directory-census model only. No Windows reader or private file is opened."""
    owner, root, binding = _p505c_case(tmp_path, initial={}, allowed=['task.py'])
    names = {'.git': 20, 'control': 21, 'approvals': 22}
    opened = []
    class Reader:
        def __init__(self, deadline):
            self.handles = [1, 2]
            self.guards = {2: self.metadata(2)}
            self.directory_guards = {}; self.stream_guards = {}
        def tick(self): pass
        def drive_mapping(self, drive): return '\\Device\\HarddiskVolume3'
        def open_root(self, drive, components): return 2, self.drive_mapping(drive)
        def open_relative(self, parent, name, access):
            assert name == root.name, 'Private endpoint or descendant must never be opened'
            opened.append(name)
            self.handles.append(3)
            return 3
        def metadata(self, handle):
            assert handle in {2, 3}
            return {'identity': {'device': 5, 'inode': 10}, 'attributes': 0x10,
                    'directory': True, 'links': 1, 'size': 0, 'mode': 0o40755,
                    'created': 116444736000000100, 'modified': 116444736000000100,
                    'changed': 116444736000000100, 'ctime_ns': 10000, 'mtime_ns': 10000,
                    'volume': (7, 0, 'NTFS')}
        def streams(self, handle, directory):
            assert handle in {2, 3} and directory
            return []
        def list_directory(self, handle, maximum):
            assert handle == 3
            return [{'name': name, 'inode': inode, 'attributes': 0x10, 'size': 0,
                     'created': 116444736000000100, 'modified': 116444736000000100,
                     'changed': 116444736000000100} for name, inode in sorted(names.items())]
        def close_all(self): self.handles.clear()
    monkeypatch.setattr(owner, '_FullWorktreeWindowsReader', Reader)
    return owner, root, binding, names, opened


def test_nonprivate_capture_records_opaque_boundaries_without_endpoint_reads(tmp_path, monkeypatch):
    owner, root, binding, names, opened = _private_boundary_scripted_case(tmp_path, monkeypatch)
    binding['capture_contract'] = owner.nonprivate_capture_contract()
    raw = owner.capture_nonprivate_worktree_state(str(root), binding=binding, phase='before')
    record = json.loads(raw)
    assert record['schema'] == 'AIOS_NONPRIVATE_WORKTREE_STATE_MANIFEST.v1'
    assert record['coverage'] == {'enumeration_complete': True, 'nonprivate_inspection_complete': True,
        'private_contents_observed': False, 'private_boundary_paths': sorted(names), 'errors': []}
    assert record['root_state']['children'] == sorted(names)
    for name in names:
        assert record['entries'][name]['kind'] == 'private_boundary'
        assert record['entries'][name]['contents_observed'] is False
        assert 'sha256' not in record['entries'][name]
    assert opened == [root.name]
    # The old full-tree profile still refuses the same privately hidden data.
    from copy import deepcopy
    full = deepcopy(binding)
    full['capture_contract'] = {'schema': 'AIOS_FULL_WORKTREE_STATE_CAPTURE.v1', 'domain': 'entire_worktree_subtree',
        'platform': 'nt', 'rules_sha256': owner.FULL_WORKTREE_CAPTURE_RULES_SHA256}
    old = json.loads(owner.capture_full_worktree_state(str(root), binding=full, phase='before'))
    assert old['coverage']['inspection_complete'] is False


def test_nonprivate_comparison_is_honest_and_detects_boundary_change(tmp_path, monkeypatch):
    from automation.orchestration import aios_self_build_apply_result_verifier as verifier
    owner, root, binding, names, _ = _private_boundary_scripted_case(tmp_path, monkeypatch)
    binding['capture_contract'] = owner.nonprivate_capture_contract()
    before = owner.capture_nonprivate_worktree_state(str(root), binding=binding, phase='before')
    after = owner.capture_nonprivate_worktree_state(str(root), binding=binding, phase='after')
    options = {'binding': binding, 'execution_started_at_utc': json.loads(before)['captured_at_utc'],
               'execution_ended_at_utc': json.loads(after)['captured_at_utc']}
    result = verifier.compare_nonprivate_worktree_states(before, after, **options)
    assert result['nonprivate_comparison_passed'] is True
    assert result['preservation_comparison_passed'] is False
    assert result['result_safe_to_package'] is False
    assert result['private_contents_observed'] is False
    assert result['private_contents_unchanged'] is None
    assert result['private_boundary_proof_required'] == sorted(names)
    names['.git'] = 99
    changed = owner.capture_nonprivate_worktree_state(str(root), binding=binding, phase='after')
    options['execution_ended_at_utc'] = json.loads(changed)['captured_at_utc']
    result = verifier.compare_nonprivate_worktree_states(before, changed, **options)
    assert result['nonprivate_comparison_passed'] is False
    assert '.git' in result['unexpected_files']
    forged = json.loads(changed); forged['coverage']['private_contents_observed'] = True
    forged = owner._full_capture_json(forged)
    with pytest.raises(ValueError):
        verifier.compare_nonprivate_worktree_states(before, forged, **options)


def test_nonprivate_capture_cannot_admit_a_private_write_target(tmp_path, monkeypatch):
    owner, root, binding, _, opened = _private_boundary_scripted_case(tmp_path, monkeypatch)
    binding['capture_contract'] = owner.nonprivate_capture_contract()
    binding['allowed_paths'] = ['.git/config']
    with pytest.raises(ValueError, match='private'):
        owner.capture_nonprivate_worktree_state(str(root), binding=binding, phase='before')
    assert opened == []


def test_private_root_name_precheck_never_touches_an_endpoint(tmp_path, monkeypatch):
    owner = _load()
    class Entry:
        def __init__(self, name): self.name = name
        def stat(self, *args, **kwargs): raise AssertionError('No private endpoint metadata read')
        def is_dir(self, *args, **kwargs): raise AssertionError('No private endpoint open')
    class Census:
        def __enter__(self): return iter([Entry('.git'), Entry('control'), Entry('public.py')])
        def __exit__(self, *args): pass
    monkeypatch.setattr(owner.os, 'scandir', lambda path: Census())
    assert owner.private_root_boundaries(str(tmp_path)) == ['.git', 'control']


def test_nonprivate_snapshot_cannot_enter_full_preservation(tmp_path, monkeypatch):
    from automation.orchestration import aios_self_build_apply_result_verifier as verifier
    owner, root, binding, _, opened = _private_boundary_scripted_case(tmp_path, monkeypatch)
    binding['capture_contract'] = owner.nonprivate_capture_contract()
    with pytest.raises(ValueError, match='full_capture'):
        owner.capture_full_worktree_state(str(root), binding=binding, phase='before')
    assert opened == []
    before = owner.capture_nonprivate_worktree_state(str(root), binding=binding, phase='before')
    after = owner.capture_nonprivate_worktree_state(str(root), binding=binding, phase='after')
    context = {'binding': binding, 'before_manifest_sha256': _p505c_sha(before),
        'after_manifest_sha256': _p505c_sha(after), 'execution': {'started_at_utc': json.loads(before)['captured_at_utc'],
        'ended_at_utc': json.loads(after)['captured_at_utc']}}
    with pytest.raises(ValueError):
        verifier._preservation_manifest(before, context, 'before')
    for defect in ['missing-boundary', 'extra-success', 'unknown-coverage']:
        changed = json.loads(after)
        if defect == 'missing-boundary':
            changed['coverage']['private_boundary_paths'].pop()
        elif defect == 'extra-success':
            changed['entries']['.git']['approved'] = True
        else:
            changed['coverage']['nonprivate_inspection_complete'] = False
        raw = owner._full_capture_json(changed)
        with pytest.raises(ValueError):
            verifier.compare_nonprivate_worktree_states(before, raw, binding=binding,
                execution_started_at_utc=context['execution']['started_at_utc'],
                execution_ended_at_utc=context['execution']['ended_at_utc'])


def test_nonprivate_rules_are_distinct_and_original_rules_stay_exact():
    owner = _load()
    assert owner.FULL_WORKTREE_CAPTURE_RULES_DESCRIPTOR == _P505C_CAPTURE_RULES_DESCRIPTOR
    rules = owner.NONPRIVATE_WORKTREE_CAPTURE_RULES_DESCRIPTOR
    assert rules.startswith('AIOS_NONPRIVATE_WORKTREE_CAPTURE_RULES.v1\n')
    assert rules.count('domain=') == 1 and rules.count('manifest=') == 1
    assert 'domain=entire_worktree_subtree' not in rules
    assert 'private_contents_observed=false;full_preservation_not_established' in rules
    assert owner.NONPRIVATE_WORKTREE_CAPTURE_RULES_SHA256 != owner.FULL_WORKTREE_CAPTURE_RULES_SHA256


@pytest.mark.parametrize('change', ['added', 'removed', 'attributes', 'nested', 'nested-descendant'])
def test_nonprivate_boundary_changes_and_hidden_descendants_are_refused(tmp_path, monkeypatch, change):
    from automation.orchestration import aios_self_build_apply_result_verifier as verifier
    owner, root, binding, _, _ = _private_boundary_scripted_case(tmp_path, monkeypatch)
    binding['capture_contract'] = owner.nonprivate_capture_contract()
    before = owner.capture_nonprivate_worktree_state(str(root), binding=binding, phase='before')
    after = json.loads(owner.capture_nonprivate_worktree_state(str(root), binding=binding, phase='after'))
    start = json.loads(before)['captured_at_utc']
    end = after['captured_at_utc']
    if change == 'added':
        after['entries']['secrets'] = dict(after['entries']['.git'])
        after['root_state']['children'].append('secrets')
        after['root_state']['children'].sort()
        after['coverage']['private_boundary_paths'].append('secrets')
        after['coverage']['private_boundary_paths'].sort()
    elif change == 'removed':
        del after['entries']['.git']
        after['root_state']['children'].remove('.git')
        after['coverage']['private_boundary_paths'].remove('.git')
    elif change == 'attributes':
        after['entries']['.git']['file_attributes'] |= 0x400
    else:
        boundary = after['entries'].pop('.git')
        after['entries']['public'] = {'kind': 'directory', 'mode': after['root_state']['mode'],
            'identity': {'device': 5, 'inode': 30}, 'children': ['.git'], 'file_attributes': 0x10}
        after['entries']['public/.git'] = boundary
        after['root_state']['children'].remove('.git')
        after['root_state']['children'].append('public')
        after['root_state']['children'].sort()
        after['coverage']['private_boundary_paths'].remove('.git')
        after['coverage']['private_boundary_paths'].append('public/.git')
        after['coverage']['private_boundary_paths'].sort()
        if change == 'nested-descendant':
            after['entries']['public/.git/secrets'] = dict(boundary)
            after['coverage']['private_boundary_paths'].append('public/.git/secrets')
            after['coverage']['private_boundary_paths'].sort()
    raw = owner._full_capture_json(after)
    options = {'binding': binding, 'execution_started_at_utc': start, 'execution_ended_at_utc': end}
    if change == 'nested-descendant':
        with pytest.raises(ValueError):
            verifier.compare_nonprivate_worktree_states(before, raw, **options)
    else:
        result = verifier.compare_nonprivate_worktree_states(before, raw, **options)
        assert result['nonprivate_comparison_passed'] is False
        assert result['unexpected_files']
        assert result['preservation_comparison_passed'] is False
        assert result['result_safe_to_package'] is False
