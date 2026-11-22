from __future__ import annotations

from pathlib import Path

from automation.orchestration.aios_self_build_apply_result_verifier import (
    SCHEMA,
    build_self_build_apply_result_verifier,
)


def _allowed_paths():
    return [
        "automation/orchestration/aios_self_build_apply_result_verifier.py",
        "tests/orchestration/test_aios_self_build_apply_result_verifier.py",
        "docs/orchestration/AIOS_SELF_BUILD_APPLY_RESULT_VERIFIER.md",
    ]


def _queue_item(**overrides):
    item = {
        "schema": "AIOS_SELF_BUILD_WORK_QUEUE_ITEM.v1",
        "action_id": "build_self_build_apply_result_verifier",
        "allowed_paths": _allowed_paths(),
        "validators": [
            "python -m pytest -p no:cacheprovider tests/orchestration/test_aios_self_build_apply_result_verifier.py",
        ],
    }
    item.update(overrides)
    return item


def _executor(**overrides):
    executor = {
        "schema": "AIOS_SELF_BUILD_SINGLE_ACTION_EXECUTOR.v1",
        "selected_action": "build_self_build_apply_result_verifier",
        "command_would_run": True,
        "command_executed": True,
        "allowed_paths": _allowed_paths(),
        "max_files_changed": 3,
    }
    executor.update(overrides)
    return executor


def _validators(*, passed: bool = True):
    return [
        {
            "name": "pytest",
            "command": "python -m pytest -p no:cacheprovider tests/orchestration/test_aios_self_build_apply_result_verifier.py",
            "returncode": 0 if passed else 1,
            "passed": passed,
        }
    ]


def test_import_and_schema():
    result = build_self_build_apply_result_verifier()

    assert result["schema"] == SCHEMA
    assert result["verifier_status"] == "blocked"
    assert result["safety"]["commands_executed"] is False


def test_blocks_when_command_not_executed():
    result = build_self_build_apply_result_verifier(
        _queue_item(),
        _executor(command_executed=False),
        "",
        " M automation/orchestration/aios_self_build_apply_result_verifier.py",
        _validators(),
        _allowed_paths(),
        3,
    )

    assert result["verifier_status"] == "blocked"
    assert "command_not_executed" in result["rejection_reasons"]
    assert result["result_safe_to_package"] is False


def test_passes_when_changed_files_are_allowed_and_validators_pass(tmp_path):
    case = _p505_full_fixture(tmp_path, initial={}, operations=tuple(("write", path, b"owned newly added\n") for path in _allowed_paths()))
    result = build_self_build_apply_result_verifier(
        case["queue"],
        case["executor"],
        "",
        "\n".join(
            [
                " M automation/orchestration/aios_self_build_apply_result_verifier.py",
                "?? tests/orchestration/test_aios_self_build_apply_result_verifier.py",
                "?? docs/orchestration/AIOS_SELF_BUILD_APPLY_RESULT_VERIFIER.md",
            ]
        ),
        _validators(),
        _allowed_paths(),
        3,
        preservation_context=case["context"],
        before_manifest=case["before_raw"],
        after_manifest=case["after_raw"],
    )

    assert result["verifier_status"] == "passed"
    assert result["changed_files"] == sorted(_allowed_paths())
    assert result["unexpected_files"] == []
    assert result["validators_passed"] == 1
    assert result["validators_failed"] == 0
    assert result["file_count_ok"] is True
    assert result["allowed_paths_ok"] is True
    assert result["result_safe_to_report"] is True
    assert result["result_safe_to_package"] is True


def test_fails_for_unexpected_files(tmp_path):
    case = _p505_full_fixture(tmp_path, operations=(("write", "automation/orchestration/outside_scope.py", b"owned outside addition\n"),))
    result = build_self_build_apply_result_verifier(
        case["queue"],
        case["executor"],
        "",
        " M automation/orchestration/outside_scope.py",
        _validators(),
        _allowed_paths(),
        3,
        preservation_context=case["context"],
        before_manifest=case["before_raw"],
        after_manifest=case["after_raw"],
    )

    assert result["verifier_status"] == "failed"
    assert result["unexpected_files"] == ["automation/orchestration/outside_scope.py"]
    assert "unexpected_files_outside_allowed_paths" in result["rejection_reasons"]


def test_fails_when_file_count_exceeds_limit(tmp_path):
    case = _p505_full_fixture(tmp_path, maximum=2, operations=tuple(("write", path, b"owned changed bytes and size\n") for path in _allowed_paths()))
    result = build_self_build_apply_result_verifier(
        case["queue"],
        case["executor"],
        "",
        "\n".join(f" M {path}" for path in _allowed_paths()),
        _validators(),
        _allowed_paths(),
        2,
        preservation_context=case["context"],
        before_manifest=case["before_raw"],
        after_manifest=case["after_raw"],
    )

    assert result["verifier_status"] == "failed"
    assert result["file_count_ok"] is False
    assert "max_files_changed_exceeded" in result["rejection_reasons"]


def test_fails_when_validator_fails(tmp_path):
    case = _p505_full_fixture(tmp_path, operations=(("write", _allowed_paths()[0], b"owned allowed change\n"),))
    result = build_self_build_apply_result_verifier(
        case["queue"],
        case["executor"],
        "",
        " M automation/orchestration/aios_self_build_apply_result_verifier.py",
        _validators(passed=False),
        _allowed_paths(),
        3,
        preservation_context=case["context"],
        before_manifest=case["before_raw"],
        after_manifest=case["after_raw"],
    )

    assert result["verifier_status"] == "failed"
    assert result["validators_passed"] == 0
    assert result["validators_failed"] == 1
    assert "validators_failed" in result["rejection_reasons"]


def test_fails_when_validators_are_missing(tmp_path):
    case = _p505_full_fixture(tmp_path, operations=(("write", _allowed_paths()[0], b"owned allowed change\n"),))
    result = build_self_build_apply_result_verifier(
        case["queue"],
        case["executor"],
        "",
        " M automation/orchestration/aios_self_build_apply_result_verifier.py",
        [],
        _allowed_paths(),
        3,
        preservation_context=case["context"],
        before_manifest=case["before_raw"],
        after_manifest=case["after_raw"],
    )

    assert result["verifier_status"] == "failed"
    assert result["validators"] == []
    assert "validators_missing" in result["rejection_reasons"]


def test_subtracts_before_status_from_after_status(tmp_path):
    initial = {path: b"owned unchanged initial\n" for path in _allowed_paths()}
    initial["Reports/sandbox/already.txt"] = b"owned unchanged preexisting dirty fixture\n"
    case = _p505_full_fixture(tmp_path, initial=initial, operations=(("write", _allowed_paths()[0], b"owned allowed change\n"),))
    result = build_self_build_apply_result_verifier(
        case["queue"],
        case["executor"],
        "?? Reports/sandbox/",
        "\n".join(
            [
                "?? Reports/sandbox/",
                " M automation/orchestration/aios_self_build_apply_result_verifier.py",
            ]
        ),
        _validators(),
        _allowed_paths(),
        3,
        preservation_context=case["context"],
        before_manifest=case["before_raw"],
        after_manifest=case["after_raw"],
    )

    assert result["changed_files"] == ["automation/orchestration/aios_self_build_apply_result_verifier.py"]
    assert result["verifier_status"] == "passed"


def test_sandbox_1312_is_runner_blocker_not_code_failure():
    result = build_self_build_apply_result_verifier(
        _queue_item(),
        _executor(command_executed=False),
        "",
        "",
        [{"name": "pytest", "stderr": "CreateProcessAsUserW failed: 1312"}],
        _allowed_paths(),
        3,
    )

    assert result["verifier_status"] == "blocked"
    assert result["safety"]["sandbox_1312_blocker"] is True
    assert "sandbox_1312_runner_blocker" in result["rejection_reasons"]
    assert "not a code failure" in result["next_safe_action"]


def test_module_has_no_command_network_or_file_write_usage():
    source = (Path(__file__).resolve().parents[2] / "automation/orchestration/aios_self_build_apply_result_verifier.py").read_text()

    forbidden = [
        "subprocess",
        "requests",
        "socket",
        "urllib",
        ".write_text",
        ".write_bytes",
        "open(",
    ]
    for token in forbidden:
        assert token not in source


# P505 causal baseline: owned files plus the unchanged seven-argument public API.
# These supplied status strings are diagnostic fixtures, not a Git observation.
import hashlib as _p505_hashlib
import json as _p505_json
import os as _p505_os


def _p505_old_api(*, executor=None, before="", after="", validators=None, maximum=3):
    return build_self_build_apply_result_verifier(
        _queue_item(),
        _executor() if executor is None else executor,
        before,
        after,
        _validators() if validators is None else validators,
        _allowed_paths(),
        maximum,
    )


def _p505_observe(path):
    raw = path.read_bytes()
    observed = path.stat()
    return raw, {
        "sha256": _p505_hashlib.sha256(raw).hexdigest(),
        "size": observed.st_size,
        "mode": observed.st_mode,
        "device": observed.st_dev,
        "inode": observed.st_ino,
        "mtime_ns": observed.st_mtime_ns,
        "ctime_ns": observed.st_ctime_ns,
        "file_attributes": getattr(observed, "st_file_attributes", None),
    }


def _p505_save_case(tmp_path, case_id, result, **evidence):
    payload = {"schema": "P505_CAUSAL_FIXTURE.v1", "case_id": case_id,
               "actual_result": result, "synthetic_git_status_only": True, **evidence}
    (tmp_path / "p505-case-evidence.json").write_text(
        _p505_json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return payload


def _p505_causal_case(tmp_path, case_id, relative, status, operation):
    tree = tmp_path / "tree"
    target = tree / relative
    target.parent.mkdir(parents=True)
    initial = b"owned P505 original bytes\n"
    with target.open("xb") as stream:
        stream.write(initial)
    before_bytes, before_state = _p505_observe(target)
    if operation == "edit":
        target.write_bytes(b"owned P505 changed bytes and length\n")
    elif operation == "replace":
        target.unlink()
        with target.open("xb") as stream:
            stream.write(b"owned P505 recreated distinct bytes\n")
    elif operation == "mtime":
        actual_before = target.stat()
        _p505_os.utime(target, ns=(actual_before.st_atime_ns, before_state["mtime_ns"] + 2_000_000_000))
    else:
        raise AssertionError("unexpected fixture operation")
    after_bytes, after_state = _p505_observe(target)
    if operation == "mtime":
        assert before_bytes == after_bytes, "fixture timestamp proof must preserve real bytes"
        assert after_state["mtime_ns"] != before_state["mtime_ns"], "actual timestamp change unsupported; not causal RED"
    else:
        assert before_bytes != after_bytes, "fixture must retain an actual byte mutation"
    # Evidence is outside the compared tree, never a new proof authority.
    (tmp_path / "before-bytes.bin").write_bytes(before_bytes)
    (tmp_path / "after-bytes.bin").write_bytes(after_bytes)
    result = _p505_old_api(before=status, after=status)
    final_bytes, final_state = _p505_observe(target)
    assert final_bytes == after_bytes and final_state == after_state, "verifier changed fixture"
    _p505_save_case(tmp_path, case_id, result, relative=relative, operation=operation,
                   before_status=status, after_status=status,
                   before=before_state, after=after_state,
                   before_bytes_path=str(tmp_path / "before-bytes.bin"),
                   after_bytes_path=str(tmp_path / "after-bytes.bin"),
                   target_path=str(target), target_state_after_call=final_state)
    return result


def test_p505_red_same_dirty_name_further_content_edit_cannot_package(tmp_path):
    result = _p505_causal_case(tmp_path, "RED-01", "outside/already.txt", " M outside/already.txt", "edit")
    assert result["result_safe_to_package"] is False, "P505_CAUSAL_PACKAGE_REJECTION_REQUIRED:RED-01"


def test_p505_red_same_untracked_name_further_edit_cannot_package(tmp_path):
    result = _p505_causal_case(tmp_path, "RED-02", "outside/untracked.txt", "?? outside/untracked.txt", "edit")
    assert result["result_safe_to_package"] is False, "P505_CAUSAL_PACKAGE_REJECTION_REQUIRED:RED-02"


def test_p505_red_same_name_delete_recreate_cannot_package(tmp_path):
    result = _p505_causal_case(tmp_path, "RED-03", "outside/replaced.txt", " M outside/replaced.txt", "replace")
    assert result["result_safe_to_package"] is False, "P505_CAUSAL_PACKAGE_REJECTION_REQUIRED:RED-03"


def test_p505_red_same_name_real_timestamp_state_change_cannot_package(tmp_path):
    result = _p505_causal_case(tmp_path, "RED-04", "outside/state.txt", " M outside/state.txt", "mtime")
    assert result["result_safe_to_package"] is False, "P505_CAUSAL_PACKAGE_REJECTION_REQUIRED:RED-04"


def test_p505_valid_default_schema_preexecution_is_blocked(tmp_path):
    result = build_self_build_apply_result_verifier()
    _p505_save_case(tmp_path, "VALID-01", result)
    assert result["schema"] == SCHEMA
    assert result["verifier_status"] == "blocked"
    assert result["result_safe_to_package"] is False
    assert result["safety"]["commands_executed"] is False
    assert set(result["rejection_reasons"]) == {"command_not_executed", "validators_missing"}


def test_p505_valid_not_executed_with_validators_stays_blocked(tmp_path):
    result = _p505_old_api(executor=_executor(command_executed=False))
    _p505_save_case(tmp_path, "VALID-02", result)
    assert result["verifier_status"] == "blocked"
    assert result["validators_passed"] == 1
    assert "command_not_executed" in result["rejection_reasons"]
    assert result["result_safe_to_package"] is False


def test_p505_valid_1312_remains_runner_blocker(tmp_path):
    result = _p505_old_api(
        executor=_executor(command_executed=False),
        validators=[{"name": "pytest", "stderr": "CreateProcessAsUserW failed: 1312"}],
    )
    _p505_save_case(tmp_path, "VALID-03", result)
    assert result["verifier_status"] == "blocked"
    assert result["safety"]["sandbox_1312_blocker"] is True
    assert "sandbox_1312_runner_blocker" in result["rejection_reasons"]
    assert "not a code failure" in result["next_safe_action"]
    assert result["result_safe_to_package"] is False


def test_p505_valid_explicit_outside_status_path_is_not_packaged(tmp_path):
    result = _p505_old_api(after=" M outside/new.txt")
    _p505_save_case(tmp_path, "VALID-04", result)
    # Baseline runner also inspects the actual old outside-path rejection.
    # A later missing-evidence block remains fail closed; full evidence tests isolate scope.
    assert result["result_safe_to_package"] is False


def test_p505_valid_old_endpoint_count_over_bound_is_not_packaged(tmp_path):
    result = _p505_old_api(after="\n".join(" M " + path for path in _allowed_paths()), maximum=2)
    _p505_save_case(tmp_path, "VALID-05", result)
    assert result["max_files_changed"] == 2
    assert result["result_safe_to_package"] is False


def test_p505_valid_missing_validators_remains_not_packaged(tmp_path):
    result = _p505_old_api(validators=[])
    _p505_save_case(tmp_path, "VALID-06", result)
    assert "validators_missing" in result["rejection_reasons"]
    assert result["result_safe_to_package"] is False


def test_p505_valid_actual_driver_normalizes_only_preexecution_reasons(tmp_path):
    from automation.orchestration.aios_self_build_dry_run_driver import _verifier_for_pre_execution_controller
    original = _p505_old_api(executor=_executor(command_executed=False), validators=[])
    original_bytes = _p505_json.dumps(original, sort_keys=True, allow_nan=False)
    normalized = _verifier_for_pre_execution_controller(original)
    _p505_save_case(tmp_path, "VALID-07", original, normalized_result=normalized)
    assert set(original["rejection_reasons"]) == {"command_not_executed", "validators_missing"}
    assert normalized["rejection_reasons"] == ["command_not_executed"]
    assert normalized["result_safe_to_package"] is False
    assert _p505_json.dumps(original, sort_keys=True, allow_nan=False) == original_bytes


def test_p505_valid_unchanged_owned_dirty_fixture_truth(tmp_path):
    target = tmp_path / "tree" / "outside" / "unchanged.txt"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"owned unchanged fixture\n")
    before_bytes, before_state = _p505_observe(target)
    result = _p505_old_api(executor=_executor(command_executed=False),
                           before=" M outside/unchanged.txt", after=" M outside/unchanged.txt")
    after_bytes, after_state = _p505_observe(target)
    _p505_save_case(tmp_path, "VALID-08", result, before=before_state, after=after_state)
    assert before_bytes == after_bytes and before_state == after_state
    assert result["verifier_status"] == "blocked"
    assert result["result_safe_to_package"] is False


# P505 full supplied-state fixtures. Owned test capture is not a live capture owner.
import copy as _p505_copy
import stat as _p505_stat
import pytest as _p505_pytest


_P505_BEFORE_TIME = "2026-10-17T12:00:00.000000Z"
_P505_START_TIME = "2026-10-17T12:00:01.000000Z"
_P505_END_TIME = "2026-10-17T12:00:02.000000Z"
_P505_AFTER_TIME = "2026-10-17T12:00:03.000000Z"


def _p505_canonical(value):
    return (_p505_json.dumps(value, sort_keys=True, ensure_ascii=True,
                             separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")


def _p505_sha(raw):
    return _p505_hashlib.sha256(raw).hexdigest()


def _p505_raw_key(value):
    return value.encode("utf-8", "surrogateescape")


def _p505_file_token(observed):
    return (observed.st_dev, observed.st_ino, observed.st_mode, observed.st_size,
            observed.st_mtime_ns, observed.st_ctime_ns,
            getattr(observed, "st_file_attributes", None))


def _p505_fixture_snapshot(tree, phase, binding_sha):
    # Enumerate the entire small fixture tree; evidence files live outside it.
    # No production acquisition or authenticated execution is asserted here.
    entries = {}
    root = tree.lstat()
    assert _p505_stat.S_ISDIR(root.st_mode) and root.st_ino > 0
    platform = _p505_os.name
    def identity(observed):
        assert observed.st_dev >= 0 and observed.st_ino > 0
        return {"device": observed.st_dev, "inode": observed.st_ino}
    def attributes(observed):
        value = getattr(observed, "st_file_attributes", None) if platform == "nt" else None
        if platform == "nt":
            assert type(value) is int and value >= 0 and not value & 0x400
        return value
    def visit(directory):
        children = sorted(directory.iterdir(), key=lambda child: _p505_raw_key(child.name))
        for path in children:
            relative = path.relative_to(tree).as_posix()
            first = path.lstat()
            attrs = attributes(first)
            assert not _p505_stat.S_ISLNK(first.st_mode)
            if _p505_stat.S_ISDIR(first.st_mode):
                names = sorted((child.name for child in path.iterdir()), key=_p505_raw_key)
                entries[relative] = {"kind": "directory", "mode": first.st_mode,
                                     "identity": identity(first), "children": names,
                                     "file_attributes": attrs}
                visit(path)
            else:
                assert _p505_stat.S_ISREG(first.st_mode)
                raw = path.read_bytes()
                last = path.lstat()
                assert _p505_file_token(first) == _p505_file_token(last)
                assert len(raw) == first.st_size
                entries[relative] = {"kind": "file", "sha256": _p505_sha(raw),
                                     "size": len(raw), "mode": first.st_mode,
                                     "identity": identity(first), "mtime_ns": first.st_mtime_ns,
                                     "ctime_ns": first.st_ctime_ns, "file_attributes": attrs}
    visit(tree)
    return {"schema": "AIOS_WORKTREE_STATE_MANIFEST.v1", "binding_sha256": binding_sha,
            "phase": phase, "captured_at_utc": _P505_BEFORE_TIME if phase == "before" else _P505_AFTER_TIME,
            "coverage": {"enumeration_complete": True, "inspection_complete": True, "errors": []},
            "root_state": {"mode": root.st_mode, "identity": identity(root),
                           "children": sorted((child.name for child in tree.iterdir()), key=_p505_raw_key)},
            "entries": entries}


def _p505_reseal(case, *, update_binding=True):
    if update_binding:
        binding_sha = _p505_sha(_p505_canonical(case["context"]["binding"]))
        case["before"]["binding_sha256"] = binding_sha
        case["after"]["binding_sha256"] = binding_sha
    case["before_raw"] = _p505_canonical(case["before"])
    case["after_raw"] = _p505_canonical(case["after"])
    case["context"]["before_manifest_sha256"] = _p505_sha(case["before_raw"])
    case["context"]["after_manifest_sha256"] = _p505_sha(case["after_raw"])
    return case


def _p505_full_fixture(tmp_path, *, allowed=None, maximum=3, initial=None, operations=(), precreate_allowed_parents=True, initial_directories=()):
    allowed = list(_allowed_paths() if allowed is None else allowed)
    tree = tmp_path / "worktree"
    tree.mkdir()
    # Malformed raw-path tests mutate records after fixture creation, not filesystem paths.
    for relative in allowed:
        assert type(relative) is str and relative and not relative.startswith("/")
        assert all(part not in {"", ".", ".."} for part in relative.split("/"))
        if precreate_allowed_parents:
            (tree / relative).parent.mkdir(parents=True, exist_ok=True)
    for relative in initial_directories:
        directory = tree / relative
        directory.resolve().relative_to(tree.resolve())
        directory.mkdir()
    initial = {path: b"owned unchanged initial\n" for path in allowed} if initial is None else dict(initial)
    for relative, raw in initial.items():
        path = tree / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw)
    # This is a declared owner-shaped fixture identity; no Git collector is run.
    # Names/times identify this component case, not an actual process or campaign claim.
    task = {"task_id": "fixture-p505-task", "packet_id": "fixture-p505-packet",
            "action_id": "build_self_build_apply_result_verifier", "attempt_id": "fixture-p505-attempt"}
    repository_identity = {"resolved": True, "reason": "resolved", "repo_root": str(tree.resolve()),
                           "git_dir": str((tmp_path / "declared-fixture-git-dir").resolve()),
                           "branch": "fixture-p505", "symbolic_ref": "refs/heads/fixture-p505",
                           "detached": False, "commit": "a" * 40}
    binding = {"task": task, "repository_identity": repository_identity,
               "interval_ref": "fixture-only-existing-interval-reference", "allowed_paths": list(allowed),
               "max_files_changed": maximum,
               "implementation_manifest": {"fixture-archive/capture-contract.txt": _p505_sha(b"owned fixture capture contract v1"),
                                           "fixture-archive/comparator.py": _p505_sha((Path(__file__).resolve().parents[2] / "automation/orchestration/aios_self_build_apply_result_verifier.py").read_bytes())},
               "capture_contract": {"schema": "AIOS_FULL_WORKTREE_STATE_CAPTURE.v1", "domain": "entire_worktree_subtree",
                                    "platform": _p505_os.name, "rules_sha256": _p505_sha(b"entire small owned fixture subtree; no exclusions")}}
    execution = {"record_sha256": _p505_sha(b"fixture supplied process-correlation record; no process launched"),
                 "started_at_utc": _P505_START_TIME, "ended_at_utc": _P505_END_TIME}
    binding_sha = _p505_sha(_p505_canonical(binding))
    before = _p505_fixture_snapshot(tree, "before", binding_sha)
    for operation in operations:
        kind, relative, *values = operation
        path = tree / relative
        path.resolve().relative_to(tree.resolve())
        if kind == "write":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(values[0])
        elif kind == "unlink":
            path.unlink()
        elif kind == "mkdir":
            path.mkdir()
        elif kind == "rmdir":
            path.rmdir()
        elif kind == "rename":
            destination = tree / values[0]
            destination.resolve().relative_to(tree.resolve())
            path.rename(destination)
        elif kind == "mtime":
            observed = path.stat()
            _p505_os.utime(path, ns=(observed.st_atime_ns, observed.st_mtime_ns + 2_000_000_000))
            assert path.stat().st_mtime_ns != observed.st_mtime_ns
        else:
            raise AssertionError("unknown owned fixture operation")
    after = _p505_fixture_snapshot(tree, "after", binding_sha)
    for snapshot in [before, after]:
        for relative in allowed:
            if relative not in snapshot["entries"]:
                snapshot["entries"][relative] = {"kind": "absent"}
    queue = _queue_item(**task)
    queue["allowed_paths"] = list(allowed)
    executor = _executor(task_id=task["task_id"], packet_id=task["packet_id"], attempt_id=task["attempt_id"],
                         interval_ref=binding["interval_ref"], repository_identity=_p505_copy.deepcopy(repository_identity),
                         execution_record_sha256=execution["record_sha256"], execution_started_at_utc=execution["started_at_utc"],
                         execution_ended_at_utc=execution["ended_at_utc"], allowed_paths=list(allowed), max_files_changed=maximum)
    case = {"tree": tree, "queue": queue, "executor": executor, "allowed": list(allowed), "maximum": maximum,
            "before": before, "after": after,
            "context": {"schema": "AIOS_APPLY_PRESERVATION_CONTEXT.v1", "binding": binding, "execution": execution,
                        "before_manifest_sha256": "0" * 64, "after_manifest_sha256": "0" * 64}}
    return _p505_reseal(case)


def _p505_full_call(case, **overrides):
    arguments = {"selected_queue_item": case["queue"], "single_action_executor": case["executor"],
                 "before_git_status": " M outside/already.txt", "after_git_status": " M outside/already.txt",
                 "validator_results": _validators(), "allowed_paths": case["allowed"], "max_files_changed": case["maximum"],
                 "preservation_context": case["context"], "before_manifest": case["before_raw"], "after_manifest": case["after_raw"]}
    arguments.update(overrides)
    return build_self_build_apply_result_verifier(**arguments)


def _p505_assert_unavailable(result, *, status=None):
    if status is not None:
        assert result["preservation_status"] == status
    assert result["preservation_status"] in {"missing", "invalid", "incomplete", "not_evaluated_pre_execution"}
    assert result["preservation_assurance"] == "supplied_manifest_comparison_only"
    assert result["preservation_comparison_passed"] is False
    assert result["preservation_root_changed"] is None
    assert result["changed_files"] is None
    assert result["changed_file_count"] is None
    assert result["unexpected_files"] is None
    assert result["before_entry_count"] is None
    assert result["after_entry_count"] is None
    assert result["file_count_ok"] is False
    assert result["allowed_paths_ok"] is False
    assert result["result_safe_to_package"] is False


def _p505_assert_compared(result, expected_changed, *, package=True):
    assert result["preservation_status"] == "compared"
    assert result["preservation_assurance"] == "supplied_manifest_comparison_only"
    assert result["changed_files"] == sorted(expected_changed, key=_p505_raw_key)
    assert result["changed_file_count"] == len(expected_changed)
    assert result["result_safe_to_package"] is package


@_p505_pytest.mark.parametrize("status", [" M outside/already.txt", "?? outside/already.txt"])
def test_p505_complete_unchanged_preexisting_file_is_compared_not_subtracted(tmp_path, status):
    case = _p505_full_fixture(tmp_path, initial={"outside/already.txt": b"unchanged outside bytes\n"})
    result = _p505_full_call(case, before_git_status=status, after_git_status=status)
    _p505_assert_compared(result, [])
    assert result["preservation_comparison_passed"] is True
    assert result["preservation_root_changed"] is False
    assert result["before_manifest_sha256"] == _p505_sha(case["before_raw"])
    assert result["after_manifest_sha256"] == _p505_sha(case["after_raw"])
    assert result["before_entry_count"] == len(case["before"]["entries"])
    assert result["after_entry_count"] == len(case["after"]["entries"])
    assert result["verifier_status"] == "passed"


@_p505_pytest.mark.parametrize("relative,status", [
    ("outside/already.txt", " M outside/already.txt"),
    ("outside/untracked.txt", "?? outside/untracked.txt"),
    (".hidden-fixture", ""),
    ("ignored-style/file.txt", ""),
])
def test_p505_complete_same_name_real_outside_edit_fails(tmp_path, relative, status):
    case = _p505_full_fixture(tmp_path, initial={relative: b"actual before\n"},
                               operations=(("write", relative, b"actual changed after bytes\n"),))
    assert case["before"]["entries"][relative]["sha256"] != case["after"]["entries"][relative]["sha256"]
    result = _p505_full_call(case, before_git_status=status, after_git_status=status)
    _p505_assert_compared(result, [relative], package=False)
    assert result["verifier_status"] == "failed"
    assert result["unexpected_files"] == [relative]
    assert "unexpected_files_outside_allowed_paths" in result["rejection_reasons"]


@_p505_pytest.mark.parametrize("operation", ["content", "mtime", "replace"])
def test_p505_real_allowed_state_change_is_detected(tmp_path, operation):
    relative = _allowed_paths()[0]
    if operation == "content":
        operations = (("write", relative, b"actual changed allowed bytes\n"),)
    elif operation == "mtime":
        operations = (("mtime", relative),)
    else:
        operations = (("unlink", relative), ("write", relative, b"actual recreated different bytes\n"))
    case = _p505_full_fixture(tmp_path, operations=operations)
    assert case["before"]["entries"][relative] != case["after"]["entries"][relative]
    if operation == "mtime":
        assert case["before"]["entries"][relative]["sha256"] == case["after"]["entries"][relative]["sha256"]
        assert case["before"]["entries"][relative]["mtime_ns"] != case["after"]["entries"][relative]["mtime_ns"]
    _p505_assert_compared(_p505_full_call(case), [relative])


@_p505_pytest.mark.parametrize("kind", ["add", "delete", "rename"])
def test_p505_real_add_delete_and_both_rename_endpoints_count(tmp_path, kind):
    allowed = ["safe/a.txt", "safe/b.txt"]
    initial = {} if kind == "add" else {"safe/a.txt": b"actual original\n"}
    operations = {"add": (("write", "safe/a.txt", b"actual addition\n"),),
                  "delete": (("unlink", "safe/a.txt"),),
                  "rename": (("rename", "safe/a.txt", "safe/b.txt"),)}[kind]
    case = _p505_full_fixture(tmp_path, allowed=allowed, initial=initial, operations=operations)
    expected = ["safe/a.txt", "safe/b.txt"] if kind == "rename" else ["safe/a.txt"]
    result = _p505_full_call(case)
    _p505_assert_compared(result, expected)
    assert "safe" not in result["changed_files"]


@_p505_pytest.mark.parametrize("initial,operations,expected", [
    ({}, (("mkdir", "newdir"), ("write", "newdir/file.txt", b"actual new file\n")), ["newdir", "newdir/file.txt"]),
    ({}, (("mkdir", "empty"),), ["empty"]),
])
def test_p505_real_new_directories_and_child_endpoints_count(tmp_path, initial, operations, expected):
    case = _p505_full_fixture(tmp_path, allowed=expected, initial=initial, operations=operations,
                               precreate_allowed_parents=False)
    result = _p505_full_call(case)
    _p505_assert_compared(result, expected)
    assert result["preservation_root_changed"] is False


def test_p505_absent_allowed_target_does_not_require_invented_parent(tmp_path):
    case = _p505_full_fixture(tmp_path, allowed=["not-created/allowed.txt"], initial={}, precreate_allowed_parents=False)
    assert case["before"]["root_state"]["children"] == []
    assert case["before"]["entries"] == {"not-created/allowed.txt": {"kind": "absent"}}
    _p505_assert_compared(_p505_full_call(case), [])


@_p505_pytest.mark.parametrize("field", ["mode", "identity", "file_attributes"])
def test_p505_pure_directory_state_contract_change_counts(tmp_path, field):
    # Only the small fixture tree is actual; the following record delta is a pure contract input.
    case = _p505_full_fixture(tmp_path, allowed=["safe", "safe/a.txt"], initial={"safe/a.txt": b"bytes\n"})
    record = case["after"]["entries"]["safe"]
    if field == "mode":
        record["mode"] ^= 0o100
    elif field == "identity":
        record["identity"]["inode"] += 1
    else:
        case["context"]["binding"]["capture_contract"]["platform"] = "nt"
        for snapshot in [case["before"], case["after"]]:
            for entry in snapshot["entries"].values():
                if entry["kind"] in {"file", "directory"}:
                    entry["file_attributes"] = 0x10 if entry["kind"] == "directory" else 0
        record["file_attributes"] = 0x30
    _p505_reseal(case)
    _p505_assert_compared(_p505_full_call(case), ["safe"])


@_p505_pytest.mark.parametrize("field", ["mode", "identity"])
def test_p505_pure_root_state_change_has_reserved_diagnostic_and_never_packages(tmp_path, field):
    case = _p505_full_fixture(tmp_path)
    if field == "mode":
        case["after"]["root_state"]["mode"] ^= 0o100
    else:
        case["after"]["root_state"]["identity"]["inode"] += 1
    _p505_reseal(case)
    result = _p505_full_call(case)
    _p505_assert_compared(result, ["."], package=False)
    assert result["preservation_root_changed"] is True
    assert result["preservation_comparison_passed"] is False
    assert "preservation_root_changed" in result["preservation_reasons"]
    assert result["verifier_status"] == "failed"
    assert result["before_entry_count"] == len(case["before"]["entries"])


def test_p505_actual_call_preserves_inputs_and_owned_files(tmp_path):
    case = _p505_full_fixture(tmp_path)
    inputs = {key: _p505_copy.deepcopy(value) for key, value in case.items() if key != "tree"}
    before = _p505_fixture_snapshot(case["tree"], "after", case["after"]["binding_sha256"])
    result = _p505_full_call(case)
    _p505_assert_compared(result, [])
    assert {key: value for key, value in case.items() if key != "tree"} == inputs
    after = _p505_fixture_snapshot(case["tree"], "after", case["after"]["binding_sha256"])
    assert before == after



def test_p505_real_owned_empty_directory_deletion_counts_endpoint(tmp_path):
    case = _p505_full_fixture(tmp_path, allowed=["empty"], initial={},
                               initial_directories=("empty",), operations=(("rmdir", "empty"),))
    assert case["before"]["entries"]["empty"]["kind"] == "directory"
    assert case["after"]["entries"]["empty"] == {"kind": "absent"}
    _p505_assert_compared(_p505_full_call(case), ["empty"])


class _P505BytesSubclass(bytes):
    pass


class _P505StringSubclass(str):
    pass


class _P505IntegerSubclass(int):
    pass


class _P505ListSubclass(list):
    pass


class _P505DictSubclass(dict):
    pass


def _p505_get(root, path):
    for key in path:
        root = root[key]
    return root


def _p505_put(root, path, value):
    parent = _p505_get(root, path[:-1])
    parent[path[-1]] = value


def _p505_raw_before_call(case, raw):
    context = _p505_copy.deepcopy(case["context"])
    context["before_manifest_sha256"] = _p505_sha(raw) if type(raw) is bytes else context["before_manifest_sha256"]
    return _p505_full_call(case, preservation_context=context, before_manifest=raw)


@_p505_pytest.mark.parametrize("keyword", ["allowed_paths", "max_files_changed"])
def test_p505_explicit_none_cannot_borrow_independent_scope_or_count(tmp_path, keyword):
    case = _p505_full_fixture(tmp_path)
    result = _p505_full_call(case, **{keyword: None})
    _p505_assert_unavailable(result, status="invalid")


@_p505_pytest.mark.parametrize("source,field", [
    ("queue", "task_id"), ("queue", "packet_id"), ("queue", "action_id"), ("queue", "attempt_id"),
    ("executor", "task_id"), ("executor", "packet_id"), ("executor", "selected_action"), ("executor", "attempt_id"),
    ("executor", "interval_ref"), ("executor", "repository_identity"),
    ("executor", "execution_record_sha256"), ("executor", "execution_started_at_utc"),
    ("executor", "execution_ended_at_utc"), ("executor", "allowed_paths"), ("executor", "max_files_changed"),
])
def test_p505_context_does_not_supply_missing_independent_caller_fields(tmp_path, source, field):
    case = _p505_full_fixture(tmp_path)
    del case[source][field]
    _p505_assert_unavailable(_p505_full_call(case), status="invalid")


@_p505_pytest.mark.parametrize("path", [
    ("binding", "task", "task_id"), ("binding", "task", "packet_id"),
    ("binding", "task", "action_id"), ("binding", "task", "attempt_id"),
    ("binding", "interval_ref"), ("binding", "repository_identity", "reason"),
    ("binding", "repository_identity", "symbolic_ref"),
    ("binding", "capture_contract", "schema"), ("binding", "capture_contract", "domain"),
    ("binding", "capture_contract", "platform"), ("binding", "capture_contract", "rules_sha256"),
])
@_p505_pytest.mark.parametrize("bad", [None, False, 1, 1.0, [], {}, "string-subclass"])
def test_p505_context_string_fields_have_exact_raw_types(tmp_path, path, bad):
    case = _p505_full_fixture(tmp_path)
    original = _p505_get(case["context"], path)
    bad = _P505StringSubclass(original) if bad == "string-subclass" else bad
    _p505_put(case["context"], path, bad)
    _p505_reseal(case)
    _p505_assert_unavailable(_p505_full_call(case), status="invalid")


@_p505_pytest.mark.parametrize("path", [
    ("size",), ("mode",), ("mtime_ns",), ("ctime_ns",),
    ("identity", "device"), ("identity", "inode"),
])
@_p505_pytest.mark.parametrize("bad", [None, False, 1.0, "1", [], {}, -1])
def test_p505_file_metadata_integer_fields_reject_coercion(tmp_path, path, bad):
    case = _p505_full_fixture(tmp_path)
    record = case["after"]["entries"][_allowed_paths()[0]]
    _p505_put(record, path, bad)
    _p505_reseal(case)
    _p505_assert_unavailable(_p505_full_call(case), status="invalid")


@_p505_pytest.mark.parametrize("path", [
    ("binding", "max_files_changed"), ("binding", "repository_identity", "resolved"),
    ("binding", "repository_identity", "detached"),
])
@_p505_pytest.mark.parametrize("bad", [None, 0, 1.0, "true", [], {}])
def test_p505_count_and_bool_context_fields_reject_typed_aliases(tmp_path, path, bad):
    case = _p505_full_fixture(tmp_path)
    _p505_put(case["context"], path, bad)
    _p505_reseal(case)
    _p505_assert_unavailable(_p505_full_call(case), status="invalid")


@_p505_pytest.mark.parametrize("location", ["context", "binding", "task", "queue", "executor", "allowed"])
def test_p505_python_container_subclasses_are_not_plain_contract_values(tmp_path, location):
    case = _p505_full_fixture(tmp_path)
    if location == "context":
        case["context"] = _P505DictSubclass(case["context"])
    elif location == "binding":
        case["context"]["binding"] = _P505DictSubclass(case["context"]["binding"])
    elif location == "task":
        case["context"]["binding"]["task"] = _P505DictSubclass(case["context"]["binding"]["task"])
    elif location == "allowed":
        case["allowed"] = _P505ListSubclass(case["allowed"])
    else:
        case[location] = _P505DictSubclass(case[location])
    _p505_assert_unavailable(_p505_full_call(case), status="invalid")


@_p505_pytest.mark.parametrize("raw_kind", ["set", "callable", "object", "cyclic-list", "cyclic-dict", "nan"])
@_p505_pytest.mark.parametrize("keyword", ["selected_queue_item", "single_action_executor", "before_git_status", "after_git_status"])
def test_p505_raw_python_nonjson_callers_are_controlled_invalid_not_json_claims(tmp_path, keyword, raw_kind):
    case = _p505_full_fixture(tmp_path)
    if raw_kind == "set":
        value = {"not-json"}
    elif raw_kind == "callable":
        value = lambda: "not executed"
    elif raw_kind == "object":
        value = object()
    elif raw_kind == "cyclic-list":
        value = []; value.append(value)
    elif raw_kind == "cyclic-dict":
        value = {}; value["self"] = value
    else:
        value = float("nan")
    _p505_assert_unavailable(_p505_full_call(case, **{keyword: value}), status="invalid")


@_p505_pytest.mark.parametrize("missing", ["preservation_context", "before_manifest", "after_manifest", "all"])
def test_p505_executed_partial_or_absent_capture_is_unknown_not_empty(tmp_path, missing):
    case = _p505_full_fixture(tmp_path)
    overrides = {key: None for key in ["preservation_context", "before_manifest", "after_manifest"]} if missing == "all" else {missing: None}
    result = _p505_full_call(case, **overrides)
    _p505_assert_unavailable(result, status="missing")
    assert result["verifier_status"] == "blocked"
    assert "preservation_evidence_missing" in result["preservation_reasons"]


def test_p505_only_all_absent_preexecution_preserves_original_two_reason_preview(tmp_path):
    result = _p505_old_api(executor=_executor(command_executed=False), validators=[])
    _p505_assert_unavailable(result, status="not_evaluated_pre_execution")
    assert set(result["rejection_reasons"]) == {"command_not_executed", "validators_missing"}
    assert result["preservation_reasons"] == []


@_p505_pytest.mark.parametrize("input_name", ["preservation_context", "before_manifest", "after_manifest"])
def test_p505_partial_supplied_evidence_never_becomes_preexecution_exemption(tmp_path, input_name):
    case = _p505_full_fixture(tmp_path)
    supplied = {"preservation_context": None, "before_manifest": None, "after_manifest": None}
    supplied[input_name] = {"malformed": True} if input_name == "preservation_context" else b"malformed\n"
    result = _p505_full_call(case, single_action_executor=_executor(command_executed=False), **supplied)
    _p505_assert_unavailable(result)
    assert result["preservation_status"] != "not_evaluated_pre_execution"


@_p505_pytest.mark.parametrize("variant", ["no-lf", "two-lfs", "pretty", "leading-space", "nonascii", "invalid-byte", "duplicate", "nonfinite", "extra", "array"])
def test_p505_raw_manifest_parser_rejects_noncanonical_or_malformed_input(tmp_path, variant):
    case = _p505_full_fixture(tmp_path)
    raw = case["before_raw"]
    if variant == "no-lf": raw = raw[:-1]
    elif variant == "two-lfs": raw += b"\n"
    elif variant == "pretty": raw = (_p505_json.dumps(case["before"], indent=2) + "\n").encode("ascii")
    elif variant == "leading-space": raw = b" " + raw
    elif variant == "nonascii": raw = raw.replace(b'"before"', '"b\u00e9fore"'.encode("utf-8"), 1)
    elif variant == "invalid-byte": raw = raw[:-1] + b"\xff\n"
    elif variant == "duplicate": raw = b'{"phase":"before",' + raw[1:]
    elif variant == "nonfinite": raw = raw.replace(b'"enumeration_complete":true', b'"enumeration_complete":NaN', 1)
    elif variant == "extra":
        value = _p505_copy.deepcopy(case["before"]); value["extra"] = True; raw = _p505_canonical(value)
    elif variant == "array": raw = b"[]\n"
    _p505_assert_unavailable(_p505_raw_before_call(case, raw), status="invalid")


@_p505_pytest.mark.parametrize("kind", ["str", "bytearray", "memoryview", "list", "bytes-subclass"])
def test_p505_manifest_requires_exact_raw_bytes(tmp_path, kind):
    case = _p505_full_fixture(tmp_path)
    raw = {"str": lambda: case["before_raw"].decode("ascii"),
           "bytearray": lambda: bytearray(case["before_raw"]),
           "memoryview": lambda: memoryview(case["before_raw"]),
           "list": lambda: list(case["before_raw"]),
           "bytes-subclass": lambda: _P505BytesSubclass(case["before_raw"])}[kind]()
    _p505_assert_unavailable(_p505_full_call(case, before_manifest=raw), status="invalid")


@_p505_pytest.mark.parametrize("variant", ["raw-hash", "binding-hash", "immutable-reference", "phase"])
def test_p505_original_raw_binding_and_phase_correlation_is_required(tmp_path, variant):
    case = _p505_full_fixture(tmp_path)
    if variant == "raw-hash":
        case["context"]["before_manifest_sha256"] = "0" * 64
    elif variant == "binding-hash":
        case["before"]["binding_sha256"] = "0" * 64; _p505_reseal(case, update_binding=False)
    elif variant == "immutable-reference":
        # Change one proposed admitted reference without rewriting the original snapshot binding.
        # A coordinated rewrite of every supplied input is not authenticated by this comparator.
        case["context"]["binding"]["implementation_manifest"]["fixture-archive/comparator.py"] = "0" * 64
    else:
        case["before"]["phase"] = "after"; _p505_reseal(case)
    result = _p505_full_call(case)
    _p505_assert_unavailable(result, status="invalid")


@_p505_pytest.mark.parametrize("value", ["2026-10-17T12:00:01Z", "2026-10-17T12:00:01.000Z", "2026-10-17T12:00:01.000000+00:00", "2026-02-30T12:00:01.000000Z", "2026-10-17T12:00:60.000000Z", True, 1, [], {}])
def test_p505_execution_time_requires_exact_six_digit_gregorian_utc(tmp_path, value):
    case = _p505_full_fixture(tmp_path)
    case["context"]["execution"]["started_at_utc"] = value
    case["executor"]["execution_started_at_utc"] = value
    _p505_assert_unavailable(_p505_full_call(case), status="invalid")


@_p505_pytest.mark.parametrize("variant", ["before-after-start", "end-before-start", "after-before-end", "equal"])
def test_p505_complete_declared_execution_interval_boundaries(tmp_path, variant):
    case = _p505_full_fixture(tmp_path)
    if variant == "before-after-start": case["before"]["captured_at_utc"] = _P505_END_TIME
    elif variant == "end-before-start":
        case["context"]["execution"]["ended_at_utc"] = _P505_BEFORE_TIME
        case["executor"]["execution_ended_at_utc"] = _P505_BEFORE_TIME
    elif variant == "after-before-end": case["after"]["captured_at_utc"] = _P505_START_TIME
    else:
        for snapshot in [case["before"], case["after"]]: snapshot["captured_at_utc"] = _P505_START_TIME
        case["context"]["execution"]["ended_at_utc"] = _P505_START_TIME
        case["executor"]["execution_ended_at_utc"] = _P505_START_TIME
    _p505_reseal(case)
    result = _p505_full_call(case)
    if variant == "equal": _p505_assert_compared(result, [])
    else:
        _p505_assert_unavailable(result, status="invalid")
        assert "preservation_interval_mismatch" in result["preservation_reasons"]


@_p505_pytest.mark.parametrize("reason", ["private_refused", "reparse_refused", "nonregular_refused", "read_failed", "stat_failed", "identity_unavailable", "unstable", "budget_exceeded"])
def test_p505_unobserved_endpoint_is_incomplete_even_with_true_declarations(tmp_path, reason):
    case = _p505_full_fixture(tmp_path)
    case["after"]["entries"][_allowed_paths()[0]] = {"kind": "unobserved", "reason": reason}
    _p505_reseal(case)
    result = _p505_full_call(case)
    _p505_assert_unavailable(result, status="incomplete")
    assert "preservation_coverage_incomplete" in result["preservation_reasons"]


@_p505_pytest.mark.parametrize("field,value", [("enumeration_complete", False), ("inspection_complete", False), ("errors", [{"path": "unknown.txt", "reason": "read_failed"}])])
def test_p505_declared_coverage_refusal_or_error_cannot_compare_empty(tmp_path, field, value):
    case = _p505_full_fixture(tmp_path)
    case["after"]["coverage"][field] = value
    _p505_reseal(case)
    _p505_assert_unavailable(_p505_full_call(case), status="incomplete")


@_p505_pytest.mark.parametrize("variant", ["root-child-missing", "duplicate-child", "missing-parent", "absent-parent", "file-parent", "absent-unallowed"])
def test_p505_complete_census_must_link_every_present_endpoint(tmp_path, variant):
    case = _p505_full_fixture(tmp_path, allowed=["safe", "safe/a.txt"], initial={"safe/a.txt": b"actual\n"})
    snapshot = case["after"]
    if variant == "root-child-missing": snapshot["root_state"]["children"] = []
    elif variant == "duplicate-child": snapshot["entries"]["safe"]["children"] = ["a.txt", "a.txt"]
    elif variant == "missing-parent":
        del snapshot["entries"]["safe"]; snapshot["root_state"]["children"] = []
    elif variant == "absent-parent":
        snapshot["entries"]["safe"] = {"kind": "absent"}; snapshot["root_state"]["children"] = []
    elif variant == "file-parent": snapshot["entries"]["safe"] = _p505_copy.deepcopy(snapshot["entries"]["safe/a.txt"])
    else: snapshot["entries"]["outside-absent"] = {"kind": "absent"}
    _p505_reseal(case)
    _p505_assert_unavailable(_p505_full_call(case), status="invalid")


@_p505_pytest.mark.parametrize("path", ["literal -> arrow.txt", " leading and trailing ", "quote\".txt", "line\nbreak.txt", "caf\u00e9.txt", "raw-\udc80.txt", "literal\\backslash.txt"])
def test_p505_pure_raw_path_record_identity_is_not_status_text_or_filesystem_claim(tmp_path, path):
    # Several raw names cannot be created on Windows. These are explicit pure supplied-record controls.
    case = _p505_full_fixture(tmp_path)
    for snapshot in [case["before"], case["after"]]:
        snapshot["entries"][path] = _p505_copy.deepcopy(snapshot["entries"][_allowed_paths()[0]])
        snapshot["root_state"]["children"] = sorted(snapshot["root_state"]["children"] + [path], key=_p505_raw_key)
    _p505_reseal(case)
    result = _p505_full_call(case)
    _p505_assert_compared(result, [])
    case["after"]["entries"][path]["sha256"] = _p505_sha(b"pure changed record")
    _p505_reseal(case)
    _p505_assert_compared(_p505_full_call(case), [path], package=False)


@_p505_pytest.mark.parametrize("path", ["", ".", "..", "../escape", "/absolute", "a//b", "a/./b", "a/../b", "nul\x00name", "bad-\ud800"])
def test_p505_invalid_raw_manifest_path_never_resolves_or_coerces(tmp_path, path):
    case = _p505_full_fixture(tmp_path)
    case["after"]["entries"][path] = _p505_copy.deepcopy(case["after"]["entries"][_allowed_paths()[0]])
    case["after"]["root_state"]["children"] += [path]  # Intentionally invalid IDs cannot supply a valid raw-byte census.
    _p505_reseal(case)
    _p505_assert_unavailable(_p505_full_call(case), status="invalid")


@_p505_pytest.mark.parametrize("path", ["C:/foo", "C:foo", "safe/a.txt:stream"])
def test_p505_nt_allowed_target_rejects_drive_or_colon_without_path_io(tmp_path, path):
    case = _p505_full_fixture(tmp_path)
    case["context"]["binding"]["capture_contract"]["platform"] = "nt"
    case["context"]["binding"]["allowed_paths"] = [path]
    case["queue"]["allowed_paths"] = [path]
    case["executor"]["allowed_paths"] = [path]
    case["allowed"] = [path]
    for snapshot in [case["before"], case["after"]]:
        for entry in snapshot["entries"].values():
            if entry["kind"] in {"file", "directory"}: entry["file_attributes"] = 0x10 if entry["kind"] == "directory" else 0
        snapshot["entries"][path] = {"kind": "absent"}
    _p505_reseal(case)
    result = _p505_full_call(case)
    _p505_assert_unavailable(result, status="invalid")
    assert "preservation_context_invalid" in result["preservation_reasons"]



def test_p505_pure_mixed_unicode_surrogateescape_diagnostics_use_raw_byte_order(tmp_path):
    case = _p505_full_fixture(tmp_path)
    names = ["raw-\udc80.txt", "raw-\u00e9.txt", "raw-z.txt"]
    for snapshot in [case["before"], case["after"]]:
        for name in names:
            snapshot["entries"][name] = _p505_copy.deepcopy(snapshot["entries"][_allowed_paths()[0]])
        snapshot["root_state"]["children"] = sorted(snapshot["root_state"]["children"] + names, key=_p505_raw_key)
    for name in names:
        case["after"]["entries"][name]["sha256"] = _p505_sha(b"pure state change")
    _p505_reseal(case)
    result = _p505_full_call(case)
    _p505_assert_compared(result, names, package=False)
    assert result["changed_files"] == ["raw-z.txt", "raw-\udc80.txt", "raw-\u00e9.txt"]



def test_p505_raw_python_integer_subclass_in_context_is_not_plain_int(tmp_path):
    case = _p505_full_fixture(tmp_path)
    case["context"]["binding"]["max_files_changed"] = _P505IntegerSubclass(3)
    _p505_reseal(case)
    _p505_assert_unavailable(_p505_full_call(case), status="invalid")


@_p505_pytest.mark.parametrize("field,value", [("sha256", None), ("sha256", "A" * 64), ("sha256", "0" * 63),
    ("kind", "symlink"), ("kind", "reparse"), ("kind", "device"), ("mode", 0), ("mode", 0o040755),
    ("identity", {"device": 0, "inode": 0}), ("file_attributes", 0x400), ("file_attributes", True), ("extra", "unknown")])
def test_p505_file_record_closed_kind_metadata_and_nonreparse_shape(tmp_path, field, value):
    case = _p505_full_fixture(tmp_path)
    if field == "file_attributes":
        case["context"]["binding"]["capture_contract"]["platform"] = "nt"
        for snapshot in [case["before"], case["after"]]:
            for record in snapshot["entries"].values():
                if record["kind"] in {"file", "directory"}: record["file_attributes"] = 0x10 if record["kind"] == "directory" else 0
    case["after"]["entries"][_allowed_paths()[0]][field] = value
    _p505_reseal(case)
    _p505_assert_unavailable(_p505_full_call(case), status="invalid")


@_p505_pytest.mark.parametrize("field,value", [("enumeration_complete", 1), ("inspection_complete", 0),
    ("errors", {}), ("errors", [{"path": "file", "reason": "read_failed", "extra": True}]), ("extra", True)])
def test_p505_coverage_shape_and_bool_fields_are_exact(tmp_path, field, value):
    case = _p505_full_fixture(tmp_path)
    case["after"]["coverage"][field] = value
    _p505_reseal(case)
    _p505_assert_unavailable(_p505_full_call(case), status="invalid")


@_p505_pytest.mark.parametrize("field,value", [("branch", "other-branch"), ("commit", "b" * 40),
    ("repo_root", "different-declared-root"), ("git_dir", "different-declared-gitdir")])
def test_p505_repository_owner_fields_equal_independent_executor(tmp_path, field, value):
    case = _p505_full_fixture(tmp_path)
    if field in {"repo_root", "git_dir"}:
        alternative = tmp_path / ("different-declared-" + field)
        alternative.mkdir()
        value = str(alternative.resolve())
    case["context"]["binding"]["repository_identity"][field] = value
    if field == "branch": case["context"]["binding"]["repository_identity"]["symbolic_ref"] = "refs/heads/" + value
    _p505_reseal(case)
    result = _p505_full_call(case)
    _p505_assert_unavailable(result, status="invalid")
    assert "preservation_identity_mismatch" in result["preservation_reasons"]


def test_p505_valid_declared_detached_owner_shape_preserves_exact_strings(tmp_path):
    case = _p505_full_fixture(tmp_path)
    identity = case["context"]["binding"]["repository_identity"]
    identity.update(branch="detached", symbolic_ref=None, detached=True)
    case["executor"]["repository_identity"] = _p505_copy.deepcopy(identity)
    _p505_reseal(case)
    _p505_assert_compared(_p505_full_call(case), [])


@_p505_pytest.mark.parametrize("which", ["task_id", "packet_id", "selected_action", "attempt_id", "interval_ref", "execution_record_sha256", "execution_started_at_utc", "execution_ended_at_utc"])
def test_p505_other_attempt_or_process_cannot_reuse_context(tmp_path, which):
    case = _p505_full_fixture(tmp_path)
    if which == "execution_record_sha256": value = "b" * 64
    elif which.endswith("_at_utc"): value = "2026-10-17T12:00:01.500000Z"
    else: value = "other-" + which
    case["executor"][which] = value
    _p505_assert_unavailable(_p505_full_call(case), status="invalid")


@_p505_pytest.mark.parametrize("which", ["allowed-list", "allowed-duplicate", "max", "empty-implementation", "capture-exclusion", "context-extra", "execution-extra"])
def test_p505_scope_implementation_and_context_cannot_grow_authority(tmp_path, which):
    case = _p505_full_fixture(tmp_path)
    if which == "allowed-list": case["queue"]["allowed_paths"] = case["allowed"][:-1]
    elif which == "allowed-duplicate": case["context"]["binding"]["allowed_paths"].append(case["allowed"][0])
    elif which == "max": case["executor"]["max_files_changed"] = 4
    elif which == "empty-implementation": case["context"]["binding"]["implementation_manifest"] = {}
    elif which == "capture-exclusion": case["context"]["binding"]["capture_contract"]["exclude"] = ["ignored-style"]
    elif which == "context-extra": case["context"]["actual_capture_verified"] = True
    else: case["context"]["execution"]["trusted"] = True
    _p505_reseal(case)
    _p505_assert_unavailable(_p505_full_call(case), status="invalid")


def test_p505_large_declared_absent_changed_membership_has_exact_oracle(tmp_path):
    # Pure supplied census control; no runtime measurement or actual large capture claim.
    case = _p505_full_fixture(tmp_path)
    changed = ["changed-%04d.txt" % index for index in range(500)]
    absent = ["absent-%04d/target.txt" % index for index in range(500)]
    allowed = changed + absent
    case["allowed"] = list(allowed); case["maximum"] = 500
    case["context"]["binding"]["allowed_paths"] = list(allowed)
    case["context"]["binding"]["max_files_changed"] = 500
    case["queue"]["allowed_paths"] = list(allowed)
    case["executor"]["allowed_paths"] = list(allowed); case["executor"]["max_files_changed"] = 500
    for snapshot in [case["before"], case["after"]]:
        for relative in changed:
            snapshot["entries"][relative] = _p505_copy.deepcopy(snapshot["entries"][_allowed_paths()[0]])
        for relative in absent: snapshot["entries"][relative] = {"kind": "absent"}
        snapshot["root_state"]["children"] = sorted(snapshot["root_state"]["children"] + changed, key=_p505_raw_key)
    for relative in changed: case["after"]["entries"][relative]["sha256"] = _p505_sha(b"pure changed supplied bytes")
    _p505_reseal(case)
    result = _p505_full_call(case)
    _p505_assert_compared(result, changed)
    assert result["before_entry_count"] == len(case["before"]["entries"])
    assert result["after_entry_count"] == len(case["after"]["entries"])
    assert result["changed_file_count"] == 500



def test_p505_valid_pure_nt_ordinary_target_and_kind_attribute_control(tmp_path):
    case = _p505_full_fixture(tmp_path)
    case["context"]["binding"]["capture_contract"]["platform"] = "nt"
    for snapshot in [case["before"], case["after"]]:
        for entry in snapshot["entries"].values():
            if entry["kind"] in {"file", "directory"}:
                entry["file_attributes"] = 0x10 if entry["kind"] == "directory" else 0
    _p505_reseal(case)
    _p505_assert_compared(_p505_full_call(case), [])



def _p505_receiver_fixture(module, kind, verifier):
    # Existing literal component inputs, real public receiving functions; no checks are patched.
    if kind == "controller":
        return module.build_self_build_one_action_execution_controller(
            module._queue_item(), module._approval(), module._bridge(), module._executor(),
            verifier, module._core(), {}, module._execution_request())
    if kind == "runner":
        return module.build_self_build_one_action_apply_runner(
            module._queue_item(), module._approval(), module._bridge(), module._executor(),
            verifier, module._controller(), module._execution_request(), module._runner_options())
    local = module._local_executor(post_execution_evidence={
        "command_runner_called": True, "returncode": 0, "changed_files": [],
        "validators_run": module._validators()})
    return module.build_self_build_one_action_execution_result_collector(
        module._queue_item(), module._approval(), module._bridge(), module._executor(),
        module._controller(), module._runner(), module._gate(), local, verifier, [])


@_p505_pytest.mark.parametrize("kind", ["controller", "runner", "collector"])
def test_p505_actual_receivers_cannot_credit_executed_missing_capture_from_none_diagnostics(tmp_path, kind):
    from tests.orchestration import test_aios_self_build_one_action_execution_controller as controller_fixture
    from tests.orchestration import test_aios_self_build_one_action_apply_runner as runner_fixture
    from tests.orchestration import test_aios_self_build_one_action_execution_result_collector as collector_fixture
    from automation.orchestration.aios_self_build_dry_run_driver import _verifier_for_pre_execution_controller
    module = {"controller": controller_fixture, "runner": runner_fixture, "collector": collector_fixture}[kind]
    case = _p505_full_fixture(tmp_path, allowed=module._allowed_paths())
    case["context"]["binding"]["task"]["action_id"] = module.ACTION_ID
    case["queue"]["action_id"] = module.ACTION_ID
    case["executor"]["selected_action"] = module.ACTION_ID
    case["queue"]["validators"] = module._validators()
    records = [{"name": "pytest", "command": module._validators()[0], "passed": True, "returncode": 0}]
    _p505_reseal(case)
    # Positive only proves pure supplied-manifest and declared local-execution composition.
    # It does not qualify an actual process, approval, capture producer or package action.
    positive_verifier = _p505_full_call(case, validator_results=records)
    _p505_assert_compared(positive_verifier, [])
    positive = _p505_receiver_fixture(module, kind, positive_verifier)
    status_field = {"controller": "controller_status", "runner": "runner_status", "collector": "collector_status"}[kind]
    assert positive[status_field] == {"controller": "ready", "runner": "preview_ready", "collector": "collected"}[kind]
    missing = _p505_full_call(case, validator_results=records, preservation_context=None, before_manifest=None, after_manifest=None)
    _p505_assert_unavailable(missing, status="missing")
    original = _p505_copy.deepcopy(missing)
    normalized = _verifier_for_pre_execution_controller(missing)
    assert normalized["rejection_reasons"] == missing["rejection_reasons"]
    assert "preservation_evidence_missing" in normalized["rejection_reasons"]
    negative = _p505_receiver_fixture(module, kind, normalized)
    assert missing == original
    assert negative[status_field] == "blocked"
    assert "apply_result_verifier_blocked" in negative["rejection_reasons"]
    if kind == "collector":
        assert negative["changed_files"] == []  # Diagnostic fallback, not a comparison.
        assert negative["result_safe_to_package"] is False
        assert negative["package_decision"] == "not_package_ready"
    else:
        assert negative["command_execution_allowed"] is False
        assert negative["command_executed"] is False


def _p505_cli_arguments(case):
    return ["--queue-item", _p505_json.dumps(case["queue"], ensure_ascii=True),
            "--single-action-executor", _p505_json.dumps(case["executor"], ensure_ascii=True),
            "--validator-results", _p505_json.dumps(_validators()),
            "--allowed-paths", _p505_json.dumps(case["allowed"], ensure_ascii=True),
            "--max-files-changed", str(case["maximum"]),
            "--preservation-context", _p505_json.dumps(case["context"], ensure_ascii=True),
            "--before-manifest", case["before_raw"].decode("ascii"),
            "--after-manifest", case["after_raw"].decode("ascii")]


def test_p505_actual_cli_consumes_raw_json_text_and_same_comparison(tmp_path, capsys):
    from automation.orchestration.aios_self_build_apply_result_verifier import main
    case = _p505_full_fixture(tmp_path, operations=(("write", _allowed_paths()[0], b"actual allowed delta\n"),))
    assert main(_p505_cli_arguments(case)) == 0
    result = _p505_json.loads(capsys.readouterr().out)
    _p505_assert_compared(result, [_allowed_paths()[0]])
    assert result["before_manifest_sha256"] == _p505_sha(case["before_raw"])
    assert result["after_manifest_sha256"] == _p505_sha(case["after_raw"])


@_p505_pytest.mark.parametrize("option,value", [("--preservation-context", "null"),
    ("--preservation-context", "not-json"), ("--preservation-context", '{"schema":NaN}'),
    ("--before-manifest", "C:/not-a-manifest-file.json"), ("--before-manifest", '\u00e9\n')])
def test_p505_actual_cli_malformed_text_never_opens_a_filename(tmp_path, capsys, option, value):
    from automation.orchestration.aios_self_build_apply_result_verifier import main
    case = _p505_full_fixture(tmp_path)
    arguments = _p505_cli_arguments(case)
    arguments[arguments.index(option) + 1] = value
    assert main(arguments) == 0
    result = _p505_json.loads(capsys.readouterr().out)
    _p505_assert_unavailable(result, status="invalid")


def test_p505_exact_raw_snapshot_bound_and_one_byte_overflow(tmp_path):
    # A pure supplied canonical-record size control. The enormous raw name has
    # no actual backing endpoint; it never qualifies actual namespace capture.
    case = _p505_full_fixture(tmp_path)
    limit = 16 * 1024 * 1024
    base = _p505_copy.deepcopy(case["before"])
    record = _p505_copy.deepcopy(base["entries"][_allowed_paths()[0]])
    record["size"] = 0; record["sha256"] = _p505_sha(b"")
    def padded(length):
        snapshot = _p505_copy.deepcopy(base)
        path = "padding-" + "x" * length
        snapshot["entries"][path] = _p505_copy.deepcopy(record)
        snapshot["root_state"]["children"] = sorted(snapshot["root_state"]["children"] + [path], key=_p505_raw_key)
        return snapshot
    baseline_size = len(_p505_canonical(padded(0)))
    if (limit - baseline_size) % 2:
        record["size"] = 10; record["sha256"] = _p505_sha(b"0123456789")
        baseline_size = len(_p505_canonical(padded(0)))
    assert limit > baseline_size and (limit - baseline_size) % 2 == 0
    before = padded((limit - baseline_size) // 2)
    after = _p505_copy.deepcopy(before)
    after["phase"] = "after"; after["captured_at_utc"] = _P505_AFTER_TIME
    case["before"], case["after"] = before, after
    _p505_reseal(case)
    assert len(case["before_raw"]) == limit
    assert len(case["after_raw"]) <= limit
    result = _p505_full_call(case)
    _p505_assert_compared(result, [])
    assert result["before_manifest_sha256"] == _p505_sha(case["before_raw"])
    overflow = case["before_raw"] + b" "
    assert len(overflow) == limit + 1
    result = _p505_raw_before_call(case, overflow)
    _p505_assert_unavailable(result, status="invalid")
    assert result["before_manifest_sha256"] is None


_WINDOWS_ORIGINAL_ROLES = (
    'selected_entry_source', 'configuration_source', 'launch_and_environment_source',
    'process_result_original', 'process_result_independent_verification',
    'same_launch_policy_binding_source', 'backend_source', 'network_proxy_source',
    'qualification_acceptance_review', 'qualification_execution_seal')


def _windows_original_example():
    """Invented bytes only. This example never authenticates a Windows origin."""
    import hashlib
    import json
    def encode(value): return json.dumps(value, sort_keys=True, separators=(',', ':')).encode('ascii')
    def digest(value): return hashlib.sha256(encode(value)).hexdigest()
    attempt = {'task_id': 'example-task', 'packet_id': 'example-packet', 'attempt_id': 'example-attempt',
        'request_sha256': '1' * 64, 'claim_sha256': '2' * 64, 'nonce_sha256': '3' * 64}
    chain = [
        {'pid': 20, 'parent_pid': 10, 'creation_filetime': 20, 'parent_creation_filetime': 10,
         'image_sha256': '4' * 64, 'image_bytes': 123},
        {'pid': 10, 'parent_pid': 9, 'creation_filetime': 10, 'parent_creation_filetime': 5,
         'image_sha256': '5' * 64, 'image_bytes': 456}]
    candidate = {'sha256': '5' * 64, 'bytes': 456}
    expected = {'schema': 'AIOS_WINDOWS_WORKER_CHECK_EXPECTATION.v1', 'attempt': attempt,
        'candidate': candidate, 'session_id': 'example-session',
        'policy_export_manifest_sha256': '6' * 64, 'policy_state_sha256': '7' * 64,
        'profile_reference_sha256': '8' * 64, 'native_cwd': 'C:\\owned',
        'canonical_cwd_uri': 'file:///C:/owned', 'process_chain': chain,
        'interval': {'started_filetime': 30, 'ended_filetime': 40},
        'launch': {'argv': ['-NoProfile', '-File', 'owned-script.ps1'], 'environment_sha256': digest({}),
            'shell_image_sha256': '4' * 64, 'shell_version': '5.1',
            'requested_route': 'WindowsPowerShell5', 'actual_route': 'WindowsPowerShell5',
            'stdin_bytes': 0, 'stdin_sha256': hashlib.sha256(b'').hexdigest()},
        'backend': {'kind': 'windows_mxc', 'applied_policy_sha256': '9' * 64, 'process_token_sha256': 'a' * 64},
        'filesystem': {'private_boundaries': ['.git', 'control'], 'observations': [
            {'path': path, 'operation': operation, 'result': 'access_denied'}
            for path in ['.git', 'control'] for operation in ['read', 'write']] + [
            {'path': 'owned.txt', 'operation': operation, 'result': 'allowed'} for operation in ['read', 'write']]},
        'network': {'mode': 'deny_by_default', 'policy_sha256': 'b' * 64, 'proxy_sha256': 'c' * 64,
            'observations': [{'operation': name, 'target_sha256': digest(name),
                'result': 'allowed' if name == 'approved_endpoint' else 'access_denied'}
                for name in ['direct_outbound', 'proxy_bypass', 'unapproved_endpoint', 'approved_endpoint']]},
        'checker_sha256': 'd' * 64, 'reviewer': 'separate-example-reviewer',
        'producer_manifest': {role: digest('source:' + role) for role in _WINDOWS_ORIGINAL_ROLES}}
    core = {'schema': 'AIOS_NATIVE_SELECTED_EXEC_POLICY_BINDING.v1', 'candidate': candidate,
        **{key: expected[key] for key in ['policy_export_manifest_sha256', 'policy_state_sha256',
            'profile_reference_sha256', 'canonical_cwd_uri', 'native_cwd']}}
    process = {key: True for key in ['shape_valid', 'root_exit_confirmed', 'tree_exit_confirmed',
        'drains_completed', 'stdin_completed', 'stdin_writer_joined']}
    process.update({key: False for key in ['timed_out', 'startup_failed', 'process_error_present']})
    process.update({key: 0 for key in ['exit_code', 'child_exit_code', 'stdin_error_code',
        'stdin_close_error_code', 'cleanup_error_code', 'cancellation_error_code']})
    process.update(cleanup_state='CONFIRMED', working_directory=expected['native_cwd'], stdin_bytes_written=0,
                   root_process_id=20)
    payloads = {
        'selected_entry_source': {'candidate': candidate, 'entry_sha256': expected['producer_manifest']['selected_entry_source']},
        'configuration_source': {key: expected[key] for key in ['policy_export_manifest_sha256',
            'policy_state_sha256', 'profile_reference_sha256']},
        'launch_and_environment_source': {**expected['launch'], 'native_cwd': expected['native_cwd'],
            'canonical_cwd_uri': expected['canonical_cwd_uri'], 'process_chain': chain},
        'process_result_original': process,
        'same_launch_policy_binding_source': {'policy_state_sha256': expected['policy_state_sha256'],
            'profile_reference_sha256': expected['profile_reference_sha256'], 'process_chain': chain,
            'filesystem': expected['filesystem']},
        'backend_source': expected['backend'], 'network_proxy_source': expected['network']}
    originals = {}
    for role in _WINDOWS_ORIGINAL_ROLES:
        hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in originals.items()}
        if role == 'process_result_independent_verification':
            payloads[role] = {'process_result_sha256': hashes['process_result_original'],
                'checker_sha256': expected['checker_sha256'], 'reviewer': expected['reviewer']}
        elif role == 'qualification_acceptance_review':
            payloads[role] = {'evidence_sha256': hashes, 'checker_sha256': expected['checker_sha256'],
                              'reviewer': expected['reviewer']}
        elif role == 'qualification_execution_seal':
            payloads[role] = {'evidence_sha256': hashes, 'review_sha256': hashes['qualification_acceptance_review'],
                'binding_core_sha256': digest(core), 'checker_sha256': expected['checker_sha256'],
                'binding_references_sha256': digest({**core, **{name: {
                    'publication_root': 'EXISTING_APPROVED_EXECUTION_EVIDENCE', 'relative_path': name + '.json',
                    'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
                    for name, raw in originals.items()}})}
        originals[role] = encode({'schema': 'AIOS_WINDOWS_WORKER_OBSERVATION.v1', 'role': role,
            'attempt': attempt, 'session_id': expected['session_id'], 'child_identity': chain[0],
            'interval': expected['interval'], 'producer_sha256': expected['producer_manifest'][role],
            'payload': payloads[role]})
    binding = dict(core)
    for role, raw in originals.items():
        binding[role] = {'publication_root': 'EXISTING_APPROVED_EXECUTION_EVIDENCE', 'relative_path': role + '.json',
                         'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    return expected, json.loads(encode(binding)), originals, encode


def test_windows_originals_complete_example_is_consistent_without_origin_or_admission():
    from automation.orchestration import aios_self_build_apply_result_verifier as owner
    expected, binding, originals, encode = _windows_original_example()
    result = owner.check_windows_worker_originals(encode(binding), originals, expected=expected)
    assert result['check_status'] == 'CONSISTENT'
    assert result['checked_original_count'] == 10
    assert result['origin_authenticated'] is False
    assert result['native_admission_granted'] is False
    assert result['windows_qualification'] is False
    assert result['execution_authority'] is False


@__import__('pytest').mark.parametrize('defect', ['missing-role', 'changed-bytes', 'bool-size', 'float-size',
    'extra-binding-field', 'candidate-helper', 'private-reference', 'duplicate-key', 'nonfinite',
    'pid-reuse', 'wrong-parent', 'wrong-session', 'wrong-attempt', 'wrong-argv', 'wrong-environment',
    'wrong-shell-route', 'wrong-policy', 'wrong-backend', 'wrong-network-child', 'missing-private-denial',
    'process-failed', 'cleanup-unknown', 'review-incomplete', 'seal-incomplete', 'source-substitution'])
def test_windows_originals_reject_changed_or_incomplete_records(defect):
    import hashlib
    import json
    from automation.orchestration import aios_self_build_apply_result_verifier as owner
    expected, binding, originals, encode = _windows_original_example()
    target = None
    if defect == 'missing-role': originals.pop('backend_source')
    elif defect == 'changed-bytes': originals['backend_source'] += b' '
    elif defect == 'bool-size': binding['backend_source']['bytes'] = True
    elif defect == 'float-size': binding['backend_source']['bytes'] = float(binding['backend_source']['bytes'])
    elif defect == 'extra-binding-field': binding['approved'] = True
    elif defect == 'candidate-helper': binding['candidate']['sha256'] = '0' * 64
    elif defect == 'private-reference': binding['backend_source']['relative_path'] = '.env'
    else:
        target = {'pid-reuse': 'launch_and_environment_source', 'wrong-parent': 'launch_and_environment_source',
            'wrong-session': 'backend_source', 'wrong-attempt': 'network_proxy_source',
            'wrong-argv': 'launch_and_environment_source', 'wrong-environment': 'launch_and_environment_source',
            'wrong-shell-route': 'launch_and_environment_source', 'wrong-policy': 'same_launch_policy_binding_source',
            'wrong-backend': 'backend_source', 'wrong-network-child': 'network_proxy_source',
            'missing-private-denial': 'same_launch_policy_binding_source', 'process-failed': 'process_result_original',
            'cleanup-unknown': 'process_result_original', 'review-incomplete': 'qualification_acceptance_review',
            'seal-incomplete': 'qualification_execution_seal', 'source-substitution': 'backend_source',
            'duplicate-key': 'backend_source', 'nonfinite': 'backend_source'}[defect]
        value = json.loads(originals[target])
        if defect == 'pid-reuse': value['payload']['process_chain'][0]['creation_filetime'] += 1
        elif defect == 'wrong-parent': value['payload']['process_chain'][0]['parent_creation_filetime'] += 1
        elif defect == 'wrong-session': value['session_id'] = 'other-session'
        elif defect == 'wrong-attempt': value['attempt']['attempt_id'] = 'other-attempt'
        elif defect == 'wrong-argv': value['payload']['argv'].append('-Extra')
        elif defect == 'wrong-environment': value['payload']['environment_sha256'] = '0' * 64
        elif defect == 'wrong-shell-route': value['payload']['actual_route'] = 'PowerShell7'
        elif defect == 'wrong-policy': value['payload']['policy_state_sha256'] = '0' * 64
        elif defect == 'wrong-backend': value['payload']['kind'] = 'reported_only'
        elif defect == 'wrong-network-child': value['child_identity']['pid'] += 1
        elif defect == 'missing-private-denial': value['payload']['filesystem']['observations'].pop(0)
        elif defect == 'process-failed': value['payload']['exit_code'] = 1
        elif defect == 'cleanup-unknown': value['payload']['tree_exit_confirmed'] = False
        elif defect == 'review-incomplete': value['payload']['evidence_sha256'].pop('backend_source')
        elif defect == 'seal-incomplete': value['payload']['evidence_sha256'].pop('qualification_acceptance_review')
        elif defect == 'source-substitution': value['producer_sha256'] = '0' * 64
        raw = encode(value)
        if defect == 'duplicate-key': raw = b'{"role":"forged",' + raw[1:]
        elif defect == 'nonfinite': raw = raw.replace(b'"payload":{', b'"payload":{"unbounded":NaN,', 1)
        originals[target] = raw
        binding[target]['bytes'] = len(raw)
        binding[target]['sha256'] = hashlib.sha256(raw).hexdigest()
        _windows_reseal_changed_originals(binding, originals, encode, defect)
    result = owner.check_windows_worker_originals(encode(binding), originals, expected=expected)
    assert result['check_status'] == 'BLOCKED'
    assert result['reason_codes']
    if target is not None:
        assert 'windows_originals_reference_bytes_mismatch' not in result['reason_codes']
    if defect in {'pid-reuse', 'wrong-parent', 'wrong-argv', 'wrong-environment', 'wrong-shell-route'}:
        assert result['reason_codes'] == ['windows_originals_payload_mismatch_launch_and_environment_source']
    assert result['origin_authenticated'] is False
    assert result['native_admission_granted'] is False


def test_windows_originals_never_echo_environment_or_exception_content():
    import json
    from automation.orchestration import aios_self_build_apply_result_verifier as owner
    expected, binding, originals, encode = _windows_original_example()
    originals['launch_and_environment_source'] = b'INVENTED_PRIVATE_ENVIRONMENT_TEXT'
    result = owner.check_windows_worker_originals(encode(binding), originals, expected=expected)
    assert 'INVENTED_PRIVATE_ENVIRONMENT_TEXT' not in json.dumps(result)
    assert result['check_status'] == 'BLOCKED'


def test_windows_originals_seal_binds_reference_locations_as_well_as_bytes():
    from automation.orchestration import aios_self_build_apply_result_verifier as owner
    expected, binding, originals, encode = _windows_original_example()
    binding['backend_source']['relative_path'] = 'different-but-public-location.json'
    result = owner.check_windows_worker_originals(encode(binding), originals, expected=expected)
    assert result['check_status'] == 'BLOCKED'


def _windows_reseal_changed_originals(binding, originals, encode, defect):
    """Re-sign no authority: rebuild example hashes to test record meaning."""
    import hashlib
    import json
    for role in _WINDOWS_ORIGINAL_ROLES:
        if role not in {'process_result_independent_verification', 'qualification_acceptance_review',
                        'qualification_execution_seal'}:
            continue
        value = json.loads(originals[role])
        if role == 'process_result_independent_verification':
            value['payload']['process_result_sha256'] = hashlib.sha256(originals['process_result_original']).hexdigest()
        elif role == 'qualification_acceptance_review':
            if defect != 'review-incomplete':
                value['payload']['evidence_sha256'] = {name: hashlib.sha256(originals[name]).hexdigest()
                    for name in _WINDOWS_ORIGINAL_ROLES[:8]}
        else:
            if defect != 'seal-incomplete':
                value['payload']['evidence_sha256'] = {name: hashlib.sha256(originals[name]).hexdigest()
                    for name in _WINDOWS_ORIGINAL_ROLES[:9]}
            value['payload']['review_sha256'] = hashlib.sha256(originals['qualification_acceptance_review']).hexdigest()
            value['payload']['binding_references_sha256'] = hashlib.sha256(encode({
                key: item for key, item in binding.items() if key != 'qualification_execution_seal'})).hexdigest()
        raw = encode(value)
        originals[role] = raw
        binding[role]['bytes'] = len(raw)
        binding[role]['sha256'] = hashlib.sha256(raw).hexdigest()


@__import__('pytest').mark.parametrize('defect', ['bool-pid', 'float-time', 'parent-after-child', 'helper-image',
    'unc-cwd', 'network-incomplete', 'private-allowed', 'approval-flag', 'oversize-binding', 'oversize-original'])
def test_windows_originals_refuse_invalid_expectations_and_size_aliases(defect):
    from automation.orchestration import aios_self_build_apply_result_verifier as owner
    expected, binding, originals, encode = _windows_original_example()
    raw_binding = None
    if defect == 'bool-pid': expected['process_chain'][0]['pid'] = True
    elif defect == 'float-time': expected['process_chain'][0]['creation_filetime'] = 20.0
    elif defect == 'parent-after-child': expected['process_chain'][0]['parent_creation_filetime'] = 21
    elif defect == 'helper-image': expected['candidate']['sha256'] = '0' * 64
    elif defect == 'unc-cwd': expected['native_cwd'] = '\\\\server\\share'
    elif defect == 'network-incomplete': expected['network']['observations'].pop()
    elif defect == 'private-allowed': expected['filesystem']['observations'][0]['result'] = 'allowed'
    elif defect == 'approval-flag': expected['origin_authenticated'] = True
    elif defect == 'oversize-binding': raw_binding = b' ' * 131073
    else: originals['backend_source'] = b' ' * 1048577
    result = owner.check_windows_worker_originals(raw_binding if raw_binding is not None else encode(binding),
                                                originals, expected=expected)
    assert result['check_status'] == 'BLOCKED'
    assert result['reason_codes']
    assert result['native_admission_granted'] is False


def test_windows_originals_do_not_open_files_or_collect_windows_state(monkeypatch):
    import builtins
    from pathlib import Path
    from automation.orchestration import aios_self_build_apply_result_verifier as owner
    # Load source-only dependencies before closing ordinary file APIs.
    from automation.orchestration import aios_repo_state_evidence
    from automation.orchestration.relay import aios_codex_prompt_consumer_v1, aios_self_consuming_codex_cycle_v1
    assert aios_repo_state_evidence and aios_codex_prompt_consumer_v1 and aios_self_consuming_codex_cycle_v1
    expected, binding, originals, encode = _windows_original_example()
    def forbidden(*args, **kwargs):
        raise AssertionError('This checker must use supplied bytes only')
    monkeypatch.setattr(builtins, 'open', forbidden)
    monkeypatch.setattr(Path, 'open', forbidden)
    monkeypatch.setattr(Path, 'read_bytes', forbidden)
    monkeypatch.setattr(Path, 'read_text', forbidden)
    result = owner.check_windows_worker_originals(encode(binding), originals, expected=expected)
    assert result['check_status'] == 'CONSISTENT'
    assert result['origin_authenticated'] is False


class _WindowsCollectorReaderExample:
    def __init__(self, originals, fault=None):
        import copy
        self.copy = copy.deepcopy
        self.originals = originals
        self.fault = fault
        self.guards = {}
        self.handles = []
        self.paths = {}
        self.offsets = {}
        self.calls = []
        self.closed = False
        self.read_started = False

    def tick(self):
        pass

    def drive_mapping(self, drive):
        return 'changed' if self.fault == 'mapping' and self.read_started else 'local-volume'

    def open_root(self, drive, components):
        self.calls.append(('root', drive, components))
        self.handles.append(1)
        self.paths[1] = ''
        self.guards[1] = self.metadata(1)
        return 1, 'local-volume'

    def open_relative(self, parent, name, access):
        from automation.orchestration.aios_repo_state_evidence import _FullCaptureFailure
        self.calls.append(('open', parent, name, access))
        if self.fault == 'open':
            raise _FullCaptureFailure('stat_failed', 'PRIVATE EXCEPTION TEXT')
        handle = len(self.handles) + 1
        self.handles.append(handle)
        self.paths[handle] = (self.paths[parent] + '/' + name).lstrip('/')
        self.offsets[handle] = 0
        return handle

    def metadata(self, handle):
        path = self.paths[handle]
        directory = path == '' or '/' not in path and not path.endswith('.json')
        role = path.rsplit('/', 1)[-1].removesuffix('.json')
        data = b'' if directory else self.originals[role]
        value = {'identity': {'device': 1, 'inode': 2 if directory else 100 + _WINDOWS_ORIGINAL_ROLES.index(role)},
                 'directory': directory, 'links': 1, 'size': len(data), 'changed': 0}
        if self.fault == 'root' and path == '': value['identity']['inode'] += 1
        if self.fault == 'link' and not directory: value['links'] = 2
        if self.fault == 'directory-file' and not directory: value['directory'] = True
        if self.fault == 'size' and not directory: value['size'] += 1
        if self.fault == 'device' and not directory: value['identity']['device'] += 1
        if self.fault == 'file-alias' and not directory: value['identity']['inode'] = 100
        if self.fault == 'drift' and self.read_started: value['changed'] = 1
        if self.fault == 'data-handle' and handle > 2: value['changed'] = handle
        return self.copy(value)

    def streams(self, handle, directory):
        if directory: return []
        role = self.paths[handle].rsplit('/', 1)[-1].removesuffix('.json')
        name = ':hidden:$DATA' if self.fault == 'stream' else '::$DATA'
        return [(name, len(self.originals[role]), len(self.originals[role]))]

    def read(self, handle, count):
        self.calls.append(('read', handle, count))
        self.read_started = True
        role = self.paths[handle].rsplit('/', 1)[-1].removesuffix('.json')
        data = self.originals[role]
        if self.fault == 'short': return b''
        if self.fault == 'long': return b'x' * (count + 1)
        if self.fault == 'read-type': return 'PRIVATE TEXT'
        offset = self.offsets[handle]
        chunk = data[offset:offset + min(count, 11)]
        self.offsets[handle] += len(chunk)
        return chunk

    def close_all(self):
        from automation.orchestration.aios_repo_state_evidence import _FullWorktreeCaptureUnavailable
        self.closed = True
        if self.fault == 'cleanup':
            raise _FullWorktreeCaptureUnavailable('read_failed', 'PRIVATE CLOSE TEXT')


def _windows_collector_example(monkeypatch, fault=None):
    from automation.orchestration import aios_repo_state_evidence as native
    expected, binding, originals, encode = _windows_original_example()
    reader = _WindowsCollectorReaderExample(originals, fault)
    monkeypatch.setattr(native, '_FullWorktreeWindowsReader', lambda deadline: reader)
    return expected, binding, originals, encode, reader


def test_windows_collector_collects_all_exact_bytes_without_native_calls(monkeypatch):
    import builtins
    from pathlib import Path
    from automation.orchestration import aios_self_build_apply_result_verifier as owner
    expected, binding, originals, encode, reader = _windows_collector_example(monkeypatch)
    def forbidden(*args, **kwargs):
        raise AssertionError('No ordinary path opens or enumeration')
    monkeypatch.setattr(builtins, 'open', forbidden)
    monkeypatch.setattr(Path, 'open', forbidden)
    monkeypatch.setattr(Path, 'iterdir', forbidden)
    result = owner.collect_windows_worker_originals('C:\\Evidence', encode(binding), expected=expected,
        root_identity={'device': 1, 'inode': 2})
    assert result['collection_status'] == 'COLLECTED'
    assert result['check']['check_status'] == 'CONSISTENT'
    assert result['original_bytes_by_role'] == originals
    assert result['binding_bytes'] == encode(binding)
    assert reader.closed
    assert all(result[key] is False for key in ['origin_authenticated', 'native_admission_granted',
                                              'windows_qualification', 'execution_authority'])
    assert len([call for call in reader.calls if call[0] == 'open']) == 20
    assert all(call[2] <= 65536 for call in reader.calls if call[0] == 'read')


@__import__('pytest').mark.parametrize('fault', ['root', 'link', 'directory-file', 'size', 'device',
    'file-alias', 'drift', 'data-handle', 'stream', 'open', 'short', 'long', 'read-type', 'cleanup', 'mapping'])
def test_windows_collector_rejects_changed_or_unreadable_sources(monkeypatch, fault):
    from automation.orchestration import aios_self_build_apply_result_verifier as owner
    expected, binding, originals, encode, reader = _windows_collector_example(monkeypatch, fault)
    result = owner.collect_windows_worker_originals('C:\\Evidence', encode(binding), expected=expected,
        root_identity={'device': 1, 'inode': 2})
    assert result['collection_status'] == 'BLOCKED'
    assert result['original_bytes_by_role'] == {}
    assert result['binding_bytes'] is None
    assert result['reason_codes'] and 'PRIVATE' not in str(result)
    assert result['native_admission_granted'] is False
    assert reader.closed
    if fault in {'root', 'link', 'directory-file', 'size', 'device', 'stream'}:
        assert not any(call[0] == 'read' for call in reader.calls)


@__import__('pytest').mark.parametrize('defect', ['private', 'device', 'alias', 'duplicate', 'bool-size',
    'oversize', 'root-relative', 'root-unc', 'root-parent', 'root-identity', 'timeout-bool', 'timeout-large',
    'extra', 'missing', 'expectation'])
def test_windows_collector_rejects_bad_inputs_before_native_reader(monkeypatch, defect):
    from automation.orchestration import aios_self_build_apply_result_verifier as owner
    from automation.orchestration import aios_repo_state_evidence as native
    expected, binding, originals, encode = _windows_original_example()
    root, identity, timeout = 'C:\\Evidence', {'device': 1, 'inode': 2}, 5
    if defect == 'private': binding['backend_source']['relative_path'] = 'private/record.json'
    elif defect == 'device': binding['backend_source']['relative_path'] = 'NUL.json'
    elif defect == 'alias': binding['backend_source']['relative_path'] = 'file.json.'
    elif defect == 'duplicate': binding['backend_source']['relative_path'] = binding['selected_entry_source']['relative_path'].upper()
    elif defect == 'bool-size': binding['backend_source']['bytes'] = True
    elif defect == 'oversize': binding['backend_source']['bytes'] = 1048577
    elif defect == 'root-relative': root = 'Evidence'
    elif defect == 'root-unc': root = '\\\\server\\Evidence'
    elif defect == 'root-parent': root = 'C:\\one\\..\\Evidence'
    elif defect == 'root-identity': identity['inode'] = True
    elif defect == 'timeout-bool': timeout = True
    elif defect == 'timeout-large': timeout = 6
    elif defect == 'extra': binding['allow'] = True
    elif defect == 'missing': binding.pop('backend_source')
    elif defect == 'expectation': expected['launch']['actual_route'] = 'different'
    calls = []
    def forbidden(deadline):
        calls.append(deadline)
        raise AssertionError('Invalid input reached native reader')
    monkeypatch.setattr(native, '_FullWorktreeWindowsReader', forbidden)
    result = owner.collect_windows_worker_originals(root, encode(binding), expected=expected,
        root_identity=identity, timeout_seconds=timeout)
    assert result['collection_status'] == 'BLOCKED'
    assert result['original_bytes_by_role'] == {}
    assert calls == []


def test_windows_collector_rejects_valid_hash_with_invalid_original(monkeypatch):
    import hashlib
    from automation.orchestration import aios_self_build_apply_result_verifier as owner
    expected, binding, originals, encode, reader = _windows_collector_example(monkeypatch)
    originals['backend_source'] = b'{"forged":true}'
    binding['backend_source'].update(bytes=len(originals['backend_source']),
        sha256=hashlib.sha256(originals['backend_source']).hexdigest())
    result = owner.collect_windows_worker_originals('C:\\Evidence', encode(binding), expected=expected,
        root_identity={'device': 1, 'inode': 2})
    assert result['collection_status'] == 'BLOCKED'
    assert result['original_bytes_by_role'] == {}
    assert reader.closed


@__import__('pytest').mark.parametrize('fault', [None, 'ancestor-drift', 'ancestor-open',
                                              'ancestor-file', 'ancestor-device', 'ancestor-stream'])
def test_windows_collector_checks_nested_ancestors_and_reuses_handles(monkeypatch, fault):
    from automation.orchestration import aios_self_build_apply_result_verifier as owner
    from automation.orchestration import aios_repo_state_evidence as native
    expected, binding, originals, encode = _windows_original_example()
    for reference in (binding[role] for role in _WINDOWS_ORIGINAL_ROLES):
        reference['relative_path'] = 'records/nested/' + reference['relative_path']
    _windows_reseal_changed_originals(binding, originals, encode, 'nested-test')

    class NestedReader(_WindowsCollectorReaderExample):
        def metadata(self, handle):
            path = self.paths[handle]
            if path and not path.endswith('.json'):
                value = {'identity': {'device': 1, 'inode': 10 + len(path)},
                         'directory': True, 'links': 1, 'size': 0, 'changed': 0}
                if fault == 'ancestor-drift' and self.read_started: value['changed'] = 1
                if fault == 'ancestor-file': value['directory'] = False
                if fault == 'ancestor-device': value['identity']['device'] = 2
                return value
            return super().metadata(handle)

        def open_relative(self, parent, name, access):
            if fault == 'ancestor-open' and name == 'nested':
                raise native._FullCaptureFailure('reparse_refused', 'PRIVATE EXCEPTION')
            return super().open_relative(parent, name, access)

        def streams(self, handle, directory):
            if fault == 'ancestor-stream' and self.paths[handle] == 'records':
                return [('::$DATA', 0, 0)]
            return super().streams(handle, directory)

    reader = NestedReader(originals)
    monkeypatch.setattr(native, '_FullWorktreeWindowsReader', lambda deadline: reader)
    result = owner.collect_windows_worker_originals('C:\\Evidence', encode(binding), expected=expected,
        root_identity={'device': 1, 'inode': 2})
    assert reader.closed
    if fault is None:
        assert result['collection_status'] == 'COLLECTED'
        assert result['original_bytes_by_role'] == originals
        opened_directories = [call[2] for call in reader.calls if call[0] == 'open' and not call[2].endswith('.json')]
        assert opened_directories == ['records', 'nested']
    else:
        assert result['collection_status'] == 'BLOCKED'
        assert result['original_bytes_by_role'] == {}
        assert result['binding_bytes'] is None
        assert 'PRIVATE' not in str(result)
        if fault != 'ancestor-drift':
            assert not any(call[0] == 'read' for call in reader.calls)


def test_windows_collector_rejects_original_hash_mismatch(monkeypatch):
    from automation.orchestration import aios_self_build_apply_result_verifier as owner
    expected, binding, originals, encode, reader = _windows_collector_example(monkeypatch)
    originals['backend_source'] = originals['backend_source'][:-1] + b' '
    result = owner.collect_windows_worker_originals('C:\\Evidence', encode(binding), expected=expected,
        root_identity={'device': 1, 'inode': 2})
    assert result['reason_codes'] == ['windows_originals_collection_hash_mismatch']
    assert result['original_bytes_by_role'] == {}
    assert reader.closed


import copy
import hashlib
import json

import pytest


def request():
    return {'schema': 'AIOS_WINDOWS_WORKER_RECORDING_REQUEST.v1',
            'attempt_id': 'attempt-one', 'session_id': 'session-one',
            'mxc_identity': 'selected-one', 'policy_sha256': 'c' * 64,
            'process_chain': [
                {'pid': 101, 'parent_pid': 100, 'creation_filetime': 350,
                 'parent_creation_filetime': 100, 'image_sha256': 'a' * 64, 'image_bytes': 40},
                {'pid': 100, 'parent_pid': 99, 'creation_filetime': 100,
                 'parent_creation_filetime': 50, 'image_sha256': 'b' * 64, 'image_bytes': 80}]}


def event(name, fields, *, pid=100, stamp=310, provider=None):
    return {'provider': provider or '7f10def4-a258-5fea-510e-2c3bb976687f',
            'emitter_pid': pid, 'timestamp_filetime': stamp, 'name': name,
            'fields': fields}


class Source:
    def __init__(self, spec, deadline, max_events):
        self.spec = copy.deepcopy(spec)
        self.events = [
            event('MXC.PolicyHash', {'identity': 'selected-one', 'policyHash': 'sha256:' + 'c' * 64}),
            event('MXC.SandboxNetworkPolicyApplied', {'identity': 'selected-one',
                'enforcementMode': 'capabilities', 'defaultPolicy': 'block', 'proxyPort': 0}),
            event('MXC.ProcessExited', {'identity': 'selected-one', 'processId': 101, 'exitCode': 0}, stamp=360),
            event('MXC.SandboxTornDown', {'identity': 'selected-one', 'status': 'success'}, stamp=370)]
        self.started = False
        self.closed = False
        self.clock_value = 200

    def snapshot(self):
        return copy.deepcopy(self.spec['process_chain'])

    def clock(self):
        self.clock_value += 100
        return self.clock_value

    def start(self):
        self.started = True

    def attach(self, spec):
        assert self.started
        self.spec = copy.deepcopy(spec)

    def wait(self, seconds):
        return {'root_exit_confirmed': True, 'exit_code': 0}

    def stop(self, seconds):
        return {'events': self.events, 'events_lost': 0, 'buffers_lost': 0,
                'consumer_complete': True}

    def close(self):
        self.closed = True


def _record(owner, spec, **kwargs):
    """Fake owner's two steps: arm the recorder, then observe its selected child."""
    try:
        owner._request(spec)
        emitter = copy.deepcopy(spec)
        emitter['process_chain'] = emitter['process_chain'][1:]
        with owner.prepare_windows_worker_recording(emitter, **kwargs) as prepared:
            return owner.record_windows_worker(spec, prepared=prepared)
    except owner.RecorderUnavailable as error:
        result = owner.record_windows_worker(spec)
        result['reason_codes'] = [str(error)]
        return result


@pytest.fixture
def native(monkeypatch):
    from automation.orchestration import aios_self_build_apply_result_verifier as owner
    observed = []
    implementation = getattr(owner, '_NativeWindowsSource', None)

    def make(spec, deadline, max_events):
        source = Source(spec, deadline, max_events)
        observed.append(source)
        return source

    make.implementation = implementation
    monkeypatch.setattr(owner, '_NativeWindowsSource', make, raising=False)
    return owner, observed


def test_records_native_observations_without_issuing_qualification(native):
    owner, observed = native
    result = _record(owner, request())
    assert result['recording_status'] == 'RECORDED_REQUIRES_REVIEW'
    assert result['process_chain'] == request()['process_chain']
    assert result['observed_event_names'] == ['MXC.PolicyHash', 'MXC.SandboxNetworkPolicyApplied',
                                           'MXC.ProcessExited', 'MXC.SandboxTornDown']
    assert observed[0].closed
    assert result['native_admission_granted'] is False
    assert result['windows_qualification'] is False
    assert result['complete_worker_proof'] is False
    assert 'launch_and_environment_source' in result['missing_original_roles']
    assert 'qualification_execution_seal' in result['missing_original_roles']
    assert hashlib.sha256(result['recording_bytes']).hexdigest() == result['recording_sha256']
    assert json.loads(result['recording_bytes'])['events'] == observed[0].events


@pytest.mark.parametrize('change', [
    lambda s: s.update(extra='PRIVATE'),
    lambda s: s.update(mxc_identity='PRIVATE/password'),
    lambda s: s['process_chain'][0].update(pid=True),
    lambda s: s['process_chain'][0].update(parent_creation_filetime=99),
    lambda s: s['process_chain'][1].update(pid=101),
    lambda s: s.update(policy_sha256='unknown'),
])
def test_refuses_bad_request_before_native_access(native, change):
    owner, observed = native
    spec = request()
    change(spec)
    result = _record(owner, spec)
    assert result['recording_status'] == 'BLOCKED'
    assert observed == []
    assert result['recording_bytes'] is None
    assert 'PRIVATE' not in str(result)


@pytest.mark.parametrize('seconds', [True, 0, -1, float('nan'), float('inf'), 52, '5'])
def test_limits_checked_before_native_access(native, seconds):
    owner, observed = native
    assert _record(owner, request(), timeout_seconds=seconds)['recording_status'] == 'BLOCKED'
    assert not observed


@pytest.mark.parametrize('field', ['pid', 'parent_pid', 'creation_filetime',
                                   'parent_creation_filetime', 'image_sha256', 'image_bytes'])
def test_detects_changed_process_before_start(native, monkeypatch, field):
    owner, observed = native
    original = Source.snapshot

    def snapshot(self):
        rows = original(self)
        rows[0][field] = 'd' * 64 if field == 'image_sha256' else 999
        return rows

    monkeypatch.setattr(Source, 'snapshot', snapshot)
    result = _record(owner, request())
    assert result['recording_status'] == 'BLOCKED'
    assert observed[0].closed and not observed[0].started


@pytest.mark.parametrize('change', [
    lambda s: s.events[0].update(emitter_pid=99),
    lambda s: s.events[0]['fields'].update(identity='other-run'),
    lambda s: s.events[0]['fields'].update(policyHash='sha256:' + 'd' * 64),
    lambda s: s.events[2]['fields'].update(processId=102),
    lambda s: s.events[0].update(timestamp_filetime=1),
    lambda s: s.events[0].update(provider='00000000-0000-0000-0000-000000000000'),
    lambda s: s.events[0]['fields'].update(secret='PRIVATE'),
    lambda s: s.events[1]['fields'].update(defaultPolicy='allow'),
    lambda s: s.events.append(copy.deepcopy(s.events[2])),
    lambda s: s.events.pop(),
])
def test_refuses_mixed_incomplete_or_unsafe_event_sets(native, monkeypatch, change):
    owner, observed = native
    original = Source.start

    def start(self):
        original(self)
        change(self)

    monkeypatch.setattr(Source, 'start', start)
    result = _record(owner, request())
    assert result['recording_status'] == 'BLOCKED'
    assert result['recording_bytes'] is None
    assert observed[0].closed
    assert 'PRIVATE' not in str(result)


@pytest.mark.parametrize('fault', ['lost', 'buffers', 'consumer', 'timeout', 'exit-code',
                                   'stop', 'close', 'start', 'after-snapshot'])
def test_native_failure_never_leaves_positive_or_partial_output(native, monkeypatch, fault):
    owner, observed = native
    original_stop = Source.stop
    original_snapshot = Source.snapshot

    def stop(self, seconds):
        result = original_stop(self, seconds)
        if fault == 'lost': result['events_lost'] = 1
        if fault == 'buffers': result['buffers_lost'] = 1
        if fault == 'consumer': result['consumer_complete'] = False
        if fault == 'stop': raise OSError('PRIVATE native failure')
        return result

    def wait(self, seconds):
        return {'root_exit_confirmed': fault != 'timeout', 'exit_code': 1 if fault == 'exit-code' else 0}

    def close(self):
        self.closed = True
        if fault == 'close': raise OSError('PRIVATE close failure')

    def start(self):
        self.started = True
        if fault == 'start': raise OSError('PRIVATE start failure')

    def snapshot(self):
        result = original_snapshot(self)
        if fault == 'after-snapshot' and self.started: result[0]['creation_filetime'] = 999
        return result

    monkeypatch.setattr(Source, 'stop', stop)
    monkeypatch.setattr(Source, 'wait', wait)
    monkeypatch.setattr(Source, 'close', close)
    monkeypatch.setattr(Source, 'start', start)
    monkeypatch.setattr(Source, 'snapshot', snapshot)
    result = _record(owner, request())
    assert result['recording_status'] == 'BLOCKED'
    assert result['recording_bytes'] is None
    assert observed[0].closed
    assert 'PRIVATE' not in str(result)


def test_records_no_event_payload_from_other_emitters(native, monkeypatch):
    owner, observed = native
    monkeypatch.setattr(Source, 'start', lambda self: self.events.append(
        event('MXC.Error', {'text': 'PRIVATE'}, pid=999)))
    # Native callback filters by emitter before decoding. Supplied boundary data
    # that violates that contract must never be silently admitted.
    result = _record(owner, request())
    assert result['recording_status'] == 'BLOCKED'
    assert 'PRIVATE' not in str(result)


def test_layouts_match_windows_x64_abi_without_loading_dll(native):
    owner, _ = native
    import ctypes
    abi = owner._windows_types()
    assert ctypes.sizeof(abi.EVENT_RECORD) == 112
    assert ctypes.sizeof(abi.EVENT_TRACE_PROPERTIES) == 120
    assert ctypes.sizeof(abi.EVENT_TRACE_LOGFILE) == 448
    assert abi.TRACE_EVENT_INFO.EventNameOffset.offset == 92


@pytest.mark.parametrize('raw,in_type,kind,wanted', [
    (b'selected-one\x00', 2, 'id', 'selected-one'),
    ('selected-one\x00'.encode('utf-16-le'), 1, 'id', 'selected-one'),
    (b'block\x00', 2, 'policy', 'block'),
    ((101).to_bytes(4, 'little'), 8, 'uint', 101),
    ((0).to_bytes(4, 'little', signed=True), 7, 'uint', 0),
    ((101).to_bytes(8, 'little'), 10, 'uint', 101),
])
def test_decodes_documented_native_scalar_types(native, raw, in_type, kind, wanted):
    owner, _ = native
    assert owner._decode_property(raw, in_type, kind) == wanted


@pytest.mark.parametrize('raw,in_type,kind', [
    (b'PRIVATE/password\x00', 2, 'id'),
    (b'block', 2, 'policy'),
    (b'block\x00PRIVATE', 2, 'policy'),
    (b'\xff\x00', 2, 'id'),
    ((-1).to_bytes(4, 'little', signed=True), 7, 'uint'),
    ((1).to_bytes(2, 'little'), 8, 'uint'),
    ((1).to_bytes(4, 'little'), 13, 'uint'),
])
def test_refuses_unsupported_or_private_native_scalar_values(native, raw, in_type, kind):
    owner, _ = native
    with pytest.raises(owner.RecorderUnavailable) as error:
        owner._decode_property(raw, in_type, kind)
    assert 'PRIVATE' not in str(error.value)


def test_cleanup_time_is_inside_the_recording_deadline(native, monkeypatch):
    owner, _ = native
    clock = [1.0]
    monkeypatch.setattr(owner.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(Source, 'close', lambda self: clock.__setitem__(0, 99.0))
    result = _record(owner, request(), timeout_seconds=5)
    assert result['recording_status'] == 'BLOCKED'
    assert result['recording_bytes'] is None


def _metadata(owner, properties):
    import ctypes
    abi = owner._windows_types()
    size = ctypes.sizeof(abi.TRACE_EVENT_INFO) + len(properties) * ctypes.sizeof(abi.EVENT_PROPERTY_INFO)
    names = [name.encode('utf-16-le') + b'\0\0' for name, _, _, _ in properties]
    raw = ctypes.create_string_buffer(size + sum(map(len, names)))
    info = abi.TRACE_EVENT_INFO.from_buffer(raw)
    info.PropertyCount = info.TopLevelPropertyCount = len(properties)
    offset = size
    for index, ((_, in_type, flags, count), name) in enumerate(zip(properties, names)):
        field = abi.EVENT_PROPERTY_INFO.from_buffer(raw, ctypes.sizeof(info) + index * 24)
        field.NameOffset, field.InType, field.Flags, field.Count = offset, in_type, flags, count
        ctypes.memmove(ctypes.addressof(raw) + offset, name, len(name))
        offset += len(name)
    return raw, abi


def test_native_property_schema_rejects_arrays_and_duplicate_names(native):
    owner, _ = native
    for properties in [ [('identity', 2, 0, 2)], [('identity', 2, 1, 1)],
                        [('identity', 2, 0, 1), ('identity', 1, 0, 1)] ]:
        raw, abi = _metadata(owner, properties)
        with pytest.raises(owner.RecorderUnavailable):
            owner._property_types(raw.raw, abi, {'identity': 'id'})


def test_native_property_schema_matches_exact_field_types(native):
    owner, _ = native
    raw, abi = _metadata(owner, [('identity', 2, 0, 1), ('processId', 8, 0, 1)])
    assert owner._property_types(raw.raw, abi, {'identity': 'id', 'processId': 'uint'}) == {
        'identity': 2, 'processId': 8}


def test_native_callback_filters_other_process_before_decoding(native):
    owner, _ = native
    import ctypes
    import uuid
    implementation = owner._NativeWindowsSource.implementation
    source = object.__new__(implementation)
    source.spec = request()
    source.emitter_pid = 100
    source.failure, source.events = False, []
    source.EventInfo = lambda *args: pytest.fail('Unrelated payload was decoded')
    abi = owner._windows_types()
    record = abi.EVENT_RECORD()
    record.EventHeader.ProcessId = 999
    record.EventHeader.ProviderId = abi.GUID.from_buffer_copy(uuid.UUID(owner.MXC_PROVIDER).bytes_le)
    source._event(ctypes.pointer(record))
    record.EventHeader.ProcessId = 100
    record.EventHeader.ProviderId = abi.GUID()
    source._event(ctypes.pointer(record))
    assert source.failure is False and source.events == []


def test_native_stop_subtracts_time_spent_stopping_windows(native, monkeypatch):
    owner, _ = native
    implementation = owner._NativeWindowsSource.implementation
    source = object.__new__(implementation)
    source.a = owner._windows_types()
    import ctypes
    source.props_buffer = ctypes.create_string_buffer(ctypes.sizeof(source.a.EVENT_TRACE_PROPERTIES))
    source.session, source.deadline = 5, 3.0
    source.events, source.failure, source.consumer_status = [], False, 0
    source.logfile = source.a.EVENT_TRACE_LOGFILE()
    clock, waits = [1.0], []
    monkeypatch.setattr(owner.time, 'monotonic', lambda: clock[0])
    def stop(*args):
        clock[0] = 4.0
        return 0
    source.ControlTrace = stop
    from types import SimpleNamespace
    source.thread = SimpleNamespace(join=lambda seconds: waits.append(seconds), is_alive=lambda: False)
    source.stop(2.0)
    assert waits == [0]


def test_native_filter_is_one_pid_and_enablement_is_synchronous(native, monkeypatch):
    owner, _ = native
    implementation = owner._NativeWindowsSource.implementation
    source = object.__new__(implementation)
    source.a, source.spec, source.emitter_pid = owner._windows_types(), request(), 100
    source.processes, source.deadline = {101: 1, 100: 2}, owner.time.monotonic() + 5
    source.Wait = lambda *args: 258
    source.StartTrace = lambda *args: 0
    observed = []
    def enable(session, provider, control, level, any_keyword, all_keyword, timeout, parameters):
        import ctypes
        params = ctypes.cast(parameters, ctypes.POINTER(source.a.ENABLE_TRACE_PARAMETERS)).contents
        descriptor = params.EnableFilterDesc.contents
        observed.append((descriptor.Type, ctypes.string_at(descriptor.Ptr, descriptor.Size), timeout))
        raise owner.RecorderUnavailable('test_stop_before_native_consumer')
    source.EnableTrace = enable
    with pytest.raises(owner.RecorderUnavailable):
        source.start()
    assert observed[0][0] == 0x80000004
    assert observed[0][1] == (100).to_bytes(4, 'little')
    assert observed[0][2] > 0


def test_collection_requires_prelaunch_recording_and_never_starts_it(native):
    owner, observed = native
    result = owner.record_windows_worker(request())
    assert result['recording_status'] == 'BLOCKED'
    assert observed == []


def test_prepared_recording_is_same_attempt_and_one_use(native):
    owner, observed = native
    spec = request()
    emitter = copy.deepcopy(spec)
    emitter['process_chain'] = emitter['process_chain'][1:]
    with owner.prepare_windows_worker_recording(emitter) as prepared:
        assert observed[0].started
        other = copy.deepcopy(spec)
        other['attempt_id'] = 'other-attempt'
        first = owner.record_windows_worker(other, prepared=prepared)
        assert first['recording_status'] == 'BLOCKED'
        second = owner.record_windows_worker(spec, prepared=prepared)
        assert second['recording_status'] == 'BLOCKED'
    assert observed[0].closed


def test_prelaunch_exit_without_collection_cleans_up(native):
    owner, observed = native
    emitter = request()
    emitter['process_chain'] = emitter['process_chain'][1:]
    with owner.prepare_windows_worker_recording(emitter):
        pass
    assert observed[0].closed


def test_native_property_mapping_matches_pinned_sdk(native):
    owner, _ = native
    assert owner._NATIVE_EVENT_FIELDS['MXC.PolicyHash'] == {
        'identity': 'mxc.identity', 'policyHash': 'mxc.policy_hash'}
    assert owner._NATIVE_EVENT_FIELDS['MXC.ProcessExited'] == {
        'identity': 'mxc.identity', 'processId': 'mxc.process_id', 'exitCode': 'mxc.exit_code'}


@pytest.mark.parametrize('which', ['already-running', 'late-policy', 'early-exit', 'early-teardown'])
def test_native_interval_refuses_events_out_of_launch_order(native, monkeypatch, which):
    owner, _ = native
    spec = request()
    if which == 'already-running':
        spec['process_chain'][0]['creation_filetime'] = 250
    original = Source.start
    def start(self):
        original(self)
        if which == 'late-policy': self.events[0]['timestamp_filetime'] = 355
        if which == 'early-exit': self.events[2]['timestamp_filetime'] = 340
        if which == 'early-teardown': self.events[3]['timestamp_filetime'] = 355
    monkeypatch.setattr(Source, 'start', start)
    assert _record(owner, spec)['recording_status'] == 'BLOCKED'


def test_native_wait_keeps_recording_after_child_exit_until_events_arrive(native, monkeypatch):
    owner, _ = native
    implementation = owner._NativeWindowsSource.implementation
    source = object.__new__(implementation)
    source.a, source.spec = owner._windows_types(), request()
    source.deadline, source.processes = 8.0, {101: 1}
    clock, events = [1.0], []
    monkeypatch.setattr(owner.time, 'monotonic', lambda: clock[0])
    source.Wait = lambda *args: events.append('child-exit') or 0
    def exit_code(handle, value):
        value._obj.value = 0
        clock[0] = 3.0
        return 1
    source.ExitCode = exit_code
    from types import SimpleNamespace
    source.required_events = SimpleNamespace(wait=lambda seconds: events.append(seconds) or True)
    assert source.wait(5.0) == {'root_exit_confirmed': True, 'exit_code': 0}
    assert events == ['child-exit', 3.0]


def test_native_callback_reads_the_real_mxc_property_names(native):
    owner, _ = native
    implementation = owner._NativeWindowsSource.implementation
    source = object.__new__(implementation)
    source.a, source.spec, source.emitter_pid = owner._windows_types(), request(), 100
    source.deadline, source.maximum = owner.time.monotonic() + 5, 20
    source.events, source.failure = [], False
    raw, abi = _metadata(owner, [('mxc.identity', 2, 0, 1), ('mxc.policy_hash', 2, 0, 1)])
    name = 'MXC.PolicyHash'.encode('utf-16-le') + b'\0\0'
    import ctypes
    metadata = ctypes.create_string_buffer(raw.raw + name)
    info = abi.TRACE_EVENT_INFO.from_buffer(metadata)
    info.EventNameOffset = len(raw.raw)
    reads = []
    def event_info(record, count, context, buffer, size):
        size._obj.value = len(metadata.raw)
        if buffer is None: return 122
        ctypes.memmove(buffer, metadata, len(metadata.raw))
        return 0
    source.EventInfo = event_info
    def property_value(record, key, kind, in_type):
        reads.append(key)
        return 'selected-one' if key == 'mxc.identity' else 'sha256:' + 'c' * 64
    source._property = property_value
    record = abi.EVENT_RECORD()
    record.EventHeader.ProcessId, record.EventHeader.TimeStamp = 100, 310
    import uuid
    record.EventHeader.ProviderId = abi.GUID.from_buffer_copy(uuid.UUID(owner.MXC_PROVIDER).bytes_le)
    source._event(ctypes.pointer(record))
    assert not source.failure
    assert reads == ['mxc.identity', 'mxc.policy_hash']
    assert source.events[0]['fields'] == {'identity': 'selected-one', 'policyHash': 'sha256:' + 'c' * 64}


def test_prelaunch_chain_observes_emitter_instead_of_its_ancestor(native, monkeypatch):
    owner, _ = native
    spec = request()
    spec['process_chain'].append({'pid': 99, 'parent_pid': 98, 'creation_filetime': 50,
        'parent_creation_filetime': 25, 'image_sha256': 'd' * 64, 'image_bytes': 20})
    assert _record(owner, spec)['recording_status'] == 'RECORDED_REQUIRES_REVIEW'
    implementation = owner._NativeWindowsSource.implementation
    from types import SimpleNamespace
    def dll(*args, **kwargs):
        return SimpleNamespace(**{name: ((lambda access, inherit, pid: pid) if name == 'OpenProcess' else (lambda *args: 1)) for name in (
            'OpenProcess', 'CloseHandle', 'GetProcessTimes', 'QueryFullProcessImageNameW',
            'NtQueryInformationProcess', 'WaitForSingleObject', 'GetExitCodeProcess',
            'GetSystemTimeAsFileTime', 'CreateFileW', 'GetFileInformationByHandle',
            'ReadFile', 'StartTraceW', 'EnableTraceEx2', 'ControlTraceW', 'OpenTraceW',
            'ProcessTrace', 'CloseTrace', 'TdhGetEventInformation', 'TdhGetPropertySize', 'TdhGetProperty')})
    monkeypatch.setattr(owner.C, 'WinDLL', dll)
    emitter = copy.deepcopy(spec)
    emitter['process_chain'] = emitter['process_chain'][1:]
    source = implementation(emitter, owner.time.monotonic() + 5, 20)
    assert source.emitter_pid == 100
    source.close()


def test_missing_privacy_helper_never_opens_an_image(native, monkeypatch):
    owner, _ = native
    from automation.orchestration.relay import aios_self_consuming_codex_cycle_v1 as relay
    monkeypatch.delattr(relay, '_native_nonprivate_path', raising=False)
    source = object.__new__(owner._NativeWindowsSource.implementation)
    source.processes = {101: 1}
    source.deadline = owner.time.monotonic() + 5
    def image(handle, flags, buffer, length):
        buffer.value = r'C:\Dev\Ai.Os\public-worker.exe'
        length._obj.value = len(buffer.value)
        return 1
    source.GetImage = image
    source.CreateFile = lambda *args: pytest.fail('Image opened without the privacy check')
    with pytest.raises(ImportError):
        source._image(101)


# Launch records are checked with made-up inputs only; no process is started.
from copy import deepcopy
import hashlib
import pytest
from automation.orchestration import aios_self_build_apply_result_verifier as _launch_witness_verifier

def _launch_witness_fixture():
    inputs = dict(executable='C:\\owned\\worker.exe', command_line='"C:\\owned\\worker.exe" "owned task"', working_directory='C:\\owned', environment={'Z': 'end', 'A': 'snow 雪'}, stdin_utf8='task\n')
    identity = dict(creator_process_id=123, child_process_id=456, child_creation_filetime=123456789)
    digest = lambda value: hashlib.sha256(value).hexdigest()
    witness = dict(schema='aios.windows_launch_witness.v1', native_admission=False, qualification=False, execution_authority=False, **identity, environment_block_bytes=len('A=snow 雪\0Z=end\0\0'.encode('utf-16-le')), actual_image_path=inputs['executable'], application_utf16_sha256=digest(inputs['executable'].encode('utf-16-le')), command_line_utf16_sha256=digest(inputs['command_line'].encode('utf-16-le')), directory_utf16_sha256=digest(inputs['working_directory'].encode('utf-16-le')), environment_block_utf16_sha256=digest('A=snow 雪\0Z=end\0\0'.encode('utf-16-le')), stdin_utf8_sha256=digest(inputs['stdin_utf8'].encode('utf-8')), stdin_present=True, created=True, assigned_before_resume=True, resumed=True)
    process = dict(root_process_id=456, cleanup_state='CONFIRMED', root_exit_confirmed=True, tree_exit_confirmed=True, drains_completed=True, stdin_completed=True, stdin_writer_joined=True, stdin_bytes_written=5, stdin_error_code=0, stdin_close_error_code=0, cleanup_error_code=0, cancellation_error_code=0, timed_out=False, startup_failed=False, process_error_present=False, exit_code=0, child_exit_code=0)
    return witness, inputs, identity, process

def _check_launch_witness_fixture(parts):
    witness, inputs, identity, process = parts
    return _launch_witness_verifier.check_windows_launch_witness(witness, api_inputs=inputs, observed_identity=identity, process=process)

def test_launch_witness_consistent_record_is_only_diagnostic_and_contains_no_input_values():
    parts = _launch_witness_fixture()
    before = deepcopy(parts)
    result = _check_launch_witness_fixture(parts)
    assert parts == before
    assert result['status'] == 'CONSISTENT'
    assert result['origin_authenticated'] is False
    assert result['native_admission'] is False
    assert result['qualification'] is False
    assert result['execution_authority'] is False
    assert set(result) == {'schema', 'status', 'origin_authenticated', 'native_admission', 'qualification', 'execution_authority', 'witness_sha256'}
    assert 'snow' not in repr(result) and 'owned task' not in repr(result)

@pytest.mark.parametrize('field,value', [
    ('native_admission', True), ('qualification', True), ('execution_authority', True),
    ('creator_process_id', 999), ('child_process_id', True), ('child_creation_filetime', 1),
    ('created', False), ('assigned_before_resume', False), ('resumed', False),
    ('actual_image_path', 'C:\\other\\worker.exe'), pytest.param('actual_image_path', 'x'*32767, id='oversized-image'), ('environment_block_bytes', True),
    ('application_utf16_sha256', '0'*64), ('command_line_utf16_sha256', '0'*64),
    ('directory_utf16_sha256', '0'*64), ('environment_block_utf16_sha256', '0'*64),
    ('stdin_utf8_sha256', '0'*64), ('stdin_present', False), ('environment_values', {'secret': 'value'}),
])
def test_launch_witness_changed_or_extra_witness_field_is_refused(field, value):
    parts = _launch_witness_fixture(); parts[0][field] = value
    with pytest.raises(ValueError): _check_launch_witness_fixture(parts)

@pytest.mark.parametrize('field,value', [('cleanup_state','UNRESOLVED'), ('tree_exit_confirmed',False), ('stdin_completed',False), ('stdin_writer_joined',False), ('stdin_bytes_written',4), ('cleanup_error_code',1), ('timed_out',True), ('root_process_id',999), ('exit_code',True)])
def test_launch_witness_uncertain_or_failed_process_is_refused(field, value):
    parts = _launch_witness_fixture(); parts[3][field] = value
    with pytest.raises(ValueError): _check_launch_witness_fixture(parts)

@pytest.mark.parametrize('environment', [{'A':'one','a':'two'}, {'A':'bad\0value'}, {'1A':'bad'}, {'A':None}, {'A':'\ud800'}, {'A':'x'*32768}, {str(i):'x' for i in range(257)}])
def test_launch_witness_invalid_explicit_environment_is_refused(environment):
    parts = _launch_witness_fixture(); parts[1]['environment'] = environment
    with pytest.raises(ValueError): _check_launch_witness_fixture(parts)

def test_launch_witness_empty_and_absent_input_are_distinct():
    parts = _launch_witness_fixture(); parts[1]['stdin_utf8'] = ''
    parts[0]['stdin_utf8_sha256'] = hashlib.sha256(b'').hexdigest()
    parts[3]['stdin_bytes_written'] = 0
    assert _check_launch_witness_fixture(parts)['status'] == 'CONSISTENT'
    parts[1]['stdin_utf8'] = None
    with pytest.raises(ValueError): _check_launch_witness_fixture(parts)
    parts[0]['stdin_present'] = False
    assert _check_launch_witness_fixture(parts)['status'] == 'CONSISTENT'

def test_launch_witness_empty_environment_has_two_wide_nulls():
    parts = _launch_witness_fixture(); parts[1]['environment'] = {}
    parts[0]['environment_block_utf16_sha256'] = hashlib.sha256(b'\0'*4).hexdigest()
    parts[0]['environment_block_bytes'] = 4
    assert _check_launch_witness_fixture(parts)['status'] == 'CONSISTENT'

def test_launch_witness_non_bmp_input_over_byte_limit_is_refused():
    parts = _launch_witness_fixture()
    parts[1]['stdin_utf8'] = '\U0001f600' * (4194304 + 1)
    parts[3]['stdin_bytes_written'] = 16777220
    with pytest.raises(ValueError): _check_launch_witness_fixture(parts)


# Reviewed selected-worker launch connection checks. Fake records only.
from copy import deepcopy as _worker_connection_deepcopy
import hashlib as _worker_connection_hashlib
from pathlib import Path as _worker_connection_Path
import pytest as _worker_connection_pytest
from automation.orchestration import aios_self_build_apply_result_verifier as _worker_connection_verifier
from automation.orchestration.relay import aios_codex_prompt_consumer_v1 as _worker_connection_consumer
from automation.orchestration.relay import aios_self_consuming_codex_cycle_v1 as _worker_connection_receiver

def _worker_connection_contract(environment=None):
    environment = {'Z': 'end', 'A': 'snow ' + chr(38634)} if environment is None else environment
    text = ''.join((key + '=' + environment[key] + '\x00' for key in sorted(environment, key=str.lower))) + '\x00'
    if not environment:
        text += '\x00'
    block = text.encode('utf-16-le')
    return dict(schema='AIOS_SELECTED_WORKER_LAUNCH.v1', environment=environment, environment_block_utf16_sha256=_worker_connection_hashlib.sha256(block).hexdigest(), environment_block_bytes=len(block))

def _worker_connection_fixture():
    request = dict(provider_executable='C:\\owned\\worker.exe', provider_args=['owned task'], repo_root='C:\\owned', worker_launch_contract=_worker_connection_contract())
    prompt = 'task\n'
    command = '"C:\\owned\\worker.exe" "owned task"'
    digest = lambda text: _worker_connection_hashlib.sha256(text.encode('utf-16-le')).hexdigest()
    c = request['worker_launch_contract']
    witness = dict(schema='aios.windows_launch_witness.v1', native_admission=False, qualification=False, execution_authority=False, creator_process_id=123, child_process_id=456, child_creation_filetime=123456789, environment_block_bytes=c['environment_block_bytes'], actual_image_path=request['provider_executable'], application_utf16_sha256=digest(request['provider_executable']), command_line_utf16_sha256=digest(command), directory_utf16_sha256=digest(request['repo_root']), environment_block_utf16_sha256=c['environment_block_utf16_sha256'], stdin_utf8_sha256=_worker_connection_hashlib.sha256(prompt.encode('utf-8')).hexdigest(), stdin_present=True, created=True, assigned_before_resume=True, resumed=True)
    process = dict(root_process_id=456, cleanup_state='CONFIRMED', root_exit_confirmed=True, tree_exit_confirmed=True, drains_completed=True, stdin_completed=True, stdin_writer_joined=True, stdin_bytes_written=5, stdin_error_code=0, stdin_close_error_code=0, cleanup_error_code=0, cancellation_error_code=0, timed_out=False, startup_failed=False, process_error_present=False, exit_code=0, child_exit_code=0, executable=request['provider_executable'], arguments=request['provider_args'], working_directory=request['repo_root'], command_line_arguments='"owned task"', launch_witness=witness)
    return (request, process, prompt)

def test_worker_connection_shared_builder_matches_known_exact_utf16_bytes():
    assert _worker_connection_verifier.build_windows_launch_environment_block({'Z': 'end', 'A': 'snow ' + chr(38634)}) == ('A=snow ' + chr(38634) + '\x00Z=end\x00\x00').encode('utf-16-le')
    assert _worker_connection_verifier.build_windows_launch_environment_block({}) == bytes(4)

def test_worker_connection_contract_copy_and_all_input_fields_are_bound():
    value = _worker_connection_contract()
    before = _worker_connection_deepcopy(value)
    result = _worker_connection_consumer.validate_worker_launch_contract(value)
    assert result == value and value == before
    result['environment']['A'] = 'changed'
    assert value == before

@_worker_connection_pytest.mark.parametrize('field,value', [('schema', 'wrong'), ('environment_block_bytes', True), ('environment_block_bytes', 1), ('environment_block_utf16_sha256', '0' * 64), ('authority_granted', True)])
def test_worker_connection_wrong_contract_fields_are_refused(field, value):
    c = _worker_connection_contract()
    c[field] = value
    with _worker_connection_pytest.raises(ValueError):
        _worker_connection_consumer.validate_worker_launch_contract(c)

@_worker_connection_pytest.mark.parametrize('environment', [None, [], {'A': 'one', 'a': 'two'}, {'A': None}, {'A': 'bad\x00text'}, {'1A': 'text'}, {'A': chr(55296)}, {'A': 'x' * 32768}])
def test_worker_connection_invalid_maps_are_refused(environment):
    c = _worker_connection_contract()
    c['environment'] = environment
    with _worker_connection_pytest.raises(ValueError):
        _worker_connection_consumer.validate_worker_launch_contract(c)

def test_worker_connection_request_checks_invalid_contract_before_any_path_read(monkeypatch):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError('No path use before contract refusal')
    monkeypatch.setattr(_worker_connection_consumer, 'bound_path', forbidden)
    with _worker_connection_pytest.raises(ValueError):
        _worker_connection_consumer.validate_bound_request({'schema': _worker_connection_consumer.REQUEST_SCHEMA, 'worker_launch_contract': {}})
    assert calls == []

def test_worker_connection_consistent_fake_record_never_authenticates_its_origin():
    request, process, prompt = _worker_connection_fixture()
    before = _worker_connection_deepcopy((request, process))
    result = _worker_connection_receiver.verify_provider_launch_witness(request, process, prompt_utf8=prompt)
    assert (request, process) == before
    assert result['status'] == 'CONSISTENT'
    assert all((result[key] is False for key in ('origin_authenticated', 'native_admission', 'qualification', 'execution_authority')))

@_worker_connection_pytest.mark.parametrize('field,value', [('root_process_id', 999), ('working_directory', 'C:\\other'), ('arguments', ['changed']), ('command_line_arguments', 'different'), ('cleanup_state', 'UNRESOLVED'), ('stdin_bytes_written', 4), ('tree_exit_confirmed', False)])
def test_worker_connection_changed_process_is_refused(field, value):
    request, process, prompt = _worker_connection_fixture()
    process[field] = value
    with _worker_connection_pytest.raises(ValueError):
        _worker_connection_receiver.verify_provider_launch_witness(request, process, prompt_utf8=prompt)

@_worker_connection_pytest.mark.parametrize('field,value', [('qualification', True), ('child_creation_filetime', 0), ('environment_block_utf16_sha256', '0' * 64), ('stdin_utf8_sha256', '0' * 64), ('resumed', False)])
def test_worker_connection_changed_witness_is_refused(field, value):
    request, process, prompt = _worker_connection_fixture()
    process['launch_witness'][field] = value
    with _worker_connection_pytest.raises(ValueError):
        _worker_connection_receiver.verify_provider_launch_witness(request, process, prompt_utf8=prompt)

def test_worker_connection_missing_or_unbound_record_is_refused():
    request, process, prompt = _worker_connection_fixture()
    saved = process.pop('launch_witness')
    with _worker_connection_pytest.raises(ValueError):
        _worker_connection_receiver.verify_provider_launch_witness(request, process, prompt_utf8=prompt)
    del request['worker_launch_contract']
    process['launch_witness'] = saved
    with _worker_connection_pytest.raises(ValueError):
        _worker_connection_receiver.verify_provider_launch_witness(request, process, prompt_utf8=prompt)
    del process['launch_witness']
    assert _worker_connection_receiver.verify_provider_launch_witness(request, process, prompt_utf8=prompt) is None

def test_worker_connection_changed_prompt_is_refused():
    request, process, prompt = _worker_connection_fixture()
    with _worker_connection_pytest.raises(ValueError):
        _worker_connection_receiver.verify_provider_launch_witness(request, process, prompt_utf8=prompt + 'changed')

def test_worker_connection_present_null_contract_cannot_fall_back_to_legacy():
    request, process, prompt = _worker_connection_fixture()
    request['worker_launch_contract'] = None
    del process['launch_witness']
    with _worker_connection_pytest.raises(ValueError):
        _worker_connection_receiver.verify_provider_launch_witness(request, process, prompt_utf8=prompt)

def test_worker_connection_prepared_ps_passes_map_and_copies_declared_fields_only():
    root = _worker_connection_Path(_worker_connection_verifier.__file__).parents[2]
    text = (root / 'automation/orchestration/relay/Invoke-AiOsRelayWorker.ps1').read_text(encoding='utf-8')
    assert "$extra['LaunchEnvironment']=$exact" in text
    assert '-WorkingDirectory $Request.repo_root @extra' in text
    assert "GetFields([Reflection.BindingFlags]'Public,Instance,DeclaredOnly')" in text
    assert '$field.GetValue($Witness)' in text
    assert "$projection['launch_witness']=Get-AiOsBoundLaunchWitness" in text

def _worker_connection_shared_boundary_fixture(tmp_path, monkeypatch, corruption=None):
    import json
    from types import SimpleNamespace
    from automation.orchestration import aios_abcd_autonomy_runner as abcd
    from automation.orchestration.claims import aios_task_claim_control as claims
    prompt = _worker_connection_prompt_text()
    request, process, _ = _worker_connection_fixture()
    request['repo_root'] = str(tmp_path)
    process['working_directory'] = str(tmp_path)
    process['launch_witness']['directory_utf16_sha256'] = _worker_connection_hashlib.sha256(str(tmp_path).encode('utf-16-le')).hexdigest()
    process['stdin_bytes_written'] = len(prompt.encode('utf-8'))
    process['launch_witness']['stdin_utf8_sha256'] = _worker_connection_hashlib.sha256(prompt.encode('utf-8')).hexdigest()
    request['prompt_sha256'] = _worker_connection_hashlib.sha256(prompt.encode('utf-8')).hexdigest()
    request['preservation_contract'] = {'action_id': 'one'}
    if corruption == 'witness':
        process['launch_witness']['environment_block_utf16_sha256'] = '0' * 64
    elif corruption == 'contract':
        request['worker_launch_contract']['environment_block_utf16_sha256'] = '0' * 64
    elif corruption == 'prompt':
        request['prompt_sha256'] = '0' * 64
    elif corruption == 'null_contract':
        request['worker_launch_contract'] = None
        del process['launch_witness']
    data = {'request_json': json.dumps(request), 'dispatch_item': {}, 'queue_item': {}, 'claim': {}, 'evidence': {'packet': {'sha256': '1' * 64}, 'launch': {'sha256': '2' * 64}, 'capture': {'utf8': json.dumps({'process': process})}, 'prompt': {'utf8': prompt}}, 'original_resolver_packet': {'action_id': 'one'}}

    class FakeContext:

        def __init__(self):
            self.request = SimpleNamespace(task_id='one')
            self.context_json = _worker_connection_consumer.canonical_json(data).decode('ascii')
    context = FakeContext()
    monkeypatch.setattr(_worker_connection_receiver, 'NativeRequirementContext', FakeContext)
    monkeypatch.setattr(_worker_connection_receiver, '_native_request_dict', lambda request: {'task_id': 'one'})
    monkeypatch.setattr(_worker_connection_receiver, 'bound_path', lambda value: _worker_connection_Path(value))
    monkeypatch.setattr(_worker_connection_receiver, 'verify_provider_preservation', lambda *args: None)
    monkeypatch.setattr(abcd, '_acceptance_request', lambda *args: context.request)
    monkeypatch.setattr(claims, 'normalize_claim', lambda claim: {'worktree': str(tmp_path)})
    return context

def test_worker_connection_actual_shared_boundary_passes_consistent_fake_record(tmp_path, monkeypatch):
    context = _worker_connection_shared_boundary_fixture(tmp_path, monkeypatch)
    assert _worker_connection_receiver._native_admitted(context, lambda request: context)['original_resolver_packet'] == {'action_id': 'one'}

@_worker_connection_pytest.mark.parametrize('corruption', ['witness', 'contract', 'prompt', 'null_contract'])
def test_worker_connection_actual_shared_boundary_refuses_changed_record_before_publication(tmp_path, monkeypatch, corruption):
    context = _worker_connection_shared_boundary_fixture(tmp_path, monkeypatch, corruption)
    with _worker_connection_pytest.raises(ValueError):
        _worker_connection_receiver._native_admitted(context, lambda request: context)

def _worker_connection_prompt_text(allowed: tuple[str, ...]=('safe/file.py',)) -> str:
    paths = '\n'.join((f'- {path}' for path in allowed))
    return f'CODEX-ONLY PROMPT\n\nAI_OS EXECUTION TOKEN\nAI_OS BOOTSTRAP REQUIRED\nIDENTITY MARKER: AI_OS\nSUPERVISOR IDENTITY: OWNER\nWORKER IDENTITY: CODEX\nPACKET ID: PACKET-1\nMODE: APPLY\nZONE: LOCAL\nLANE: TEST\n\nALLOWED PATHS\n{paths}\n\nFORBIDDEN PATHS\n- AGENTS.md\n\nAPPROVAL AUTHORITY\nLocal edits only.\n\nVALIDATOR CHAIN\npython -m pytest\n\nSTOP POINT\nStop after validation.\n\nMISSION\nPerform bounded local work.\n\nPREFLIGHT\ngit status --short\n\nFINAL REPORT FORMAT\nSTATUS:\nEND OF PACKET\n'

# Selected-worker observation composition. Every OS/launcher port below is fake.
def _observed_worker_contract():
    return {'schema': 'AIOS_SELECTED_WORKER_OBSERVATION.v1', 'session_id': 'session-one',
            'mxc_identity': 'selected-one', 'policy_sha256': 'c' * 64,
            'timeout_seconds': 5, 'max_events': 256}


def _observation_cycle_inputs(tmp_path, monkeypatch):
    owner = _worker_connection_verifier
    cycle = _worker_connection_receiver
    selected, process, prompt = _worker_connection_fixture()
    selected.update(attempt_id='attempt-one', task_id='task-one', timeout_sec=5,
                    relay_root=str(tmp_path / 'relay'), provider_sha256='b' * 64,
                    worker_observation_contract=_observed_worker_contract())
    witness = process['launch_witness']
    witness.update(creator_process_id=99, child_process_id=100,
                   child_creation_filetime=100, resumed=False)
    task = {'request_json': json.dumps(selected), 'prompt_text': prompt,
            'prompt_sha256': 'a' * 64, 'request_sha256': 'b' * 64}
    queued = {'status': 'ENQUEUED', 'task': task, 'target': 'fake-inbox'}
    monkeypatch.setattr(cycle, 'validate_bound_request', lambda value: value)
    monkeypatch.setattr(cycle, 'enqueue_prompt', lambda *args, **kwargs: queued)
    monkeypatch.setattr(cycle, 'verify_observation', lambda queued, response: response)
    selected['prompt_path'] = str(tmp_path / 'fake-prompt')
    task['request_json'] = json.dumps(selected)
    return owner, cycle, selected, witness, prompt


def test_windows_observation_required_cycle_refuses_missing_host_before_launcher(tmp_path, monkeypatch):
    _, cycle, selected, _, _ = _observation_cycle_inputs(tmp_path, monkeypatch)
    calls = []
    result = cycle.run_self_consuming_cycle(generate=lambda: selected,
        relay_root=tmp_path / 'relay', invoke_worker=lambda value: calls.append(value))
    assert result.status == 'WINDOWS_OBSERVATION_HOST_REQUIRED'
    assert calls == []


@pytest.mark.parametrize('bad', [None, {}, {'schema': 'wrong'},
    {**_observed_worker_contract(), 'timeout_seconds': True},
    {**_observed_worker_contract(), 'max_events': 0},
    {**_observed_worker_contract(), 'execution_authority': True}])
def test_windows_observation_request_rejects_bad_contract_before_path_access(monkeypatch, bad):
    calls = []
    monkeypatch.setattr(_worker_connection_consumer, 'bound_path', lambda *args, **kwargs: calls.append(True))
    with pytest.raises(ValueError, match='worker_observation_'):
        _worker_connection_consumer.validate_bound_request({
            'schema': _worker_connection_consumer.REQUEST_SCHEMA,
            'worker_launch_contract': _worker_connection_contract(),
            'worker_observation_contract': bad})
    assert calls == []


def _observed_worker_host(owner, native, trace, *, fault=None):
    spec = request()
    emitter = copy.deepcopy(spec)
    emitter['process_chain'] = emitter['process_chain'][1:]
    if fault == 'emitter_pid':
        emitter['process_chain'][0]['pid'] = 102
    if fault == 'emitter_time':
        emitter['process_chain'][0]['creation_filetime'] = 101
    if fault == 'child_parent':
        spec['process_chain'][0]['parent_pid'] = 102
    if fault == 'same_child':
        spec['process_chain'][0]['pid'] = 100
    return owner.WindowsWorkerObservationHost(
        emitter_reader=lambda witness, *, deadline: (trace.append('emitter_read') or copy.deepcopy(emitter)),
        protected_child_reader=lambda: (trace.append('child_read') or copy.deepcopy(spec)))


def test_windows_observation_actual_cycle_composes_recorder_and_later_child(tmp_path, monkeypatch, native):
    owner, cycle, selected, witness, _ = _observation_cycle_inputs(tmp_path, monkeypatch)
    trace = []
    original_start, original_attach, original_close = Source.start, Source.attach, Source.close
    monkeypatch.setattr(Source, 'start', lambda self: (trace.append('record_start'), original_start(self))[-1])
    monkeypatch.setattr(Source, 'attach', lambda self, spec: (trace.append('attach_child'), original_attach(self, spec))[-1])
    monkeypatch.setattr(Source, 'close', lambda self: (trace.append('close'), original_close(self))[-1])
    host = _observed_worker_host(owner, native, trace)

    def launch(queued, *, before_resume, collect_protected_child):
        assert before_resume(copy.deepcopy(witness), 1000) is True
        assert native[1][0].started
        trace.append('resume_emitter')
        result = collect_protected_child()
        assert result['recording_status'] == 'RECORDED_REQUIRES_REVIEW'
        handoff = owner.worker_observation_handoff(request(), result)
        capture = {'worker_observation': handoff}
        outbox = tmp_path / 'relay' / 'outbox'
        outbox.mkdir(parents=True)
        path = outbox / 'fake.execution.json'
        raw = json.dumps(capture).encode()
        path.write_bytes(raw)
        return {'status': 'EXECUTED_AWAITING_VALIDATION', 'execution_path': str(path),
                'execution_sha256': hashlib.sha256(raw).hexdigest()}

    result = cycle.run_self_consuming_cycle(generate=lambda: selected,
        relay_root=tmp_path / 'relay', invoke_worker=launch, worker_observation_host=host)
    assert result.status == 'EXECUTED_AWAITING_VALIDATION'
    assert trace == ['emitter_read', 'record_start', 'resume_emitter', 'child_read', 'attach_child', 'close']
    assert host.used and native[1][0].closed
    with pytest.raises(ValueError):
        host.invoke({}, launch)


@pytest.mark.parametrize('fault', ['emitter_pid', 'emitter_time', 'child_parent', 'same_child',
                                  'not_paused', 'deadline', 'no_collection', 'tampered_capture'])
def test_windows_observation_cycle_refuses_bad_actual_connection(tmp_path, monkeypatch, native, fault):
    owner, cycle, selected, witness, _ = _observation_cycle_inputs(tmp_path, monkeypatch)
    trace = []
    host = _observed_worker_host(owner, native, trace, fault=fault)
    if fault == 'not_paused':
        witness['resumed'] = True

    def launch(queued, *, before_resume, collect_protected_child):
        before_resume(copy.deepcopy(witness), 0 if fault == 'deadline' else 1000)
        trace.append('resume_emitter')
        if fault == 'no_collection':
            return {'status': 'EXECUTED_AWAITING_VALIDATION'}
        result = collect_protected_child()
        assert result['recording_status'] == 'RECORDED_REQUIRES_REVIEW'
        return {'status': 'EXECUTED_AWAITING_VALIDATION', 'execution_path': str(tmp_path / 'missing'),
                'execution_sha256': '0' * 64}

    result = cycle.run_self_consuming_cycle(generate=lambda: selected,
        relay_root=tmp_path / 'relay', invoke_worker=launch, worker_observation_host=host)
    assert result.status == 'INTEGRITY_BLOCKED'
    if fault in {'emitter_pid', 'emitter_time', 'not_paused', 'deadline'}:
        assert 'resume_emitter' not in trace
    assert all(source.closed for source in native[1])
    assert result.retry_allowed is False


def test_windows_observation_legacy_cycle_never_calls_observation_host(tmp_path, monkeypatch):
    _, cycle, selected, _, _ = _observation_cycle_inputs(tmp_path, monkeypatch)
    del selected['worker_observation_contract']
    result = cycle.run_self_consuming_cycle(generate=lambda: selected,
        relay_root=tmp_path / 'relay', invoke_worker=lambda value: {'status': 'DEFERRED'})
    assert result.status == 'DEFERRED'


def test_windows_observation_handoff_never_grants_qualification(native):
    owner, _ = native
    result = _record(owner, request())
    handoff = owner.worker_observation_handoff(request(), result)
    assert handoff['authority_granted'] is False and handoff['qualification'] is False
    assert hashlib.sha256(__import__('base64').b64decode(handoff['recording_base64'])).hexdigest() == handoff['recording_sha256']
    handoff['qualification'] = True
    with pytest.raises(ValueError):
        owner.check_worker_observation_handoff(handoff)


def test_windows_observation_pre_resume_managed_port_and_real_forwarding_present():
    root = _worker_connection_Path(__file__).resolve().parents[2]
    helper = (root / 'automation/orchestration/validator_chain_runner/Invoke-AiOsValidatorChain.DRY_RUN.ps1').read_text(encoding='utf-8')
    timeout = (root / 'automation/orchestration/timeout/Invoke-AiOsCliWithTimeout.ps1').read_text(encoding='utf-8')
    relay = (root / 'automation/orchestration/relay/Invoke-AiOsRelayWorker.ps1').read_text(encoding='utf-8')
    assert helper.index('CheckObservationReady(api, witness,') < helper.index('Check(api.Resume(child.Thread)')
    assert "$invoke['ProcessApi'] = $ProcessApi" in timeout
    assert "$extra['RequireObservation']=$true" in relay
    assert '-WorkerObservationApi $WorkerObservationApi' in relay


@pytest.mark.parametrize('fault', ['lost_events', 'close_failed', 'start_failed'])
def test_windows_observation_composed_cycle_refuses_collection_or_cleanup_failure(tmp_path, monkeypatch, native, fault):
    owner, cycle, selected, witness, _ = _observation_cycle_inputs(tmp_path, monkeypatch)
    trace = []
    host = _observed_worker_host(owner, native, trace)
    original = Source.stop
    if fault == 'lost_events':
        def stop(self, seconds):
            captured = original(self, seconds)
            captured['events_lost'] = 1
            return captured
        monkeypatch.setattr(Source, 'stop', stop)
    elif fault == 'close_failed':
        def close(self):
            self.closed = True
            raise OSError('private-error-must-not-escape')
        monkeypatch.setattr(Source, 'close', close)
    else:
        def start(self):
            raise OSError('private-error-must-not-escape')
        monkeypatch.setattr(Source, 'start', start)

    def launch(queued, *, before_resume, collect_protected_child):
        before_resume(copy.deepcopy(witness), 1000)
        trace.append('resume_emitter')
        collect_protected_child()
        raise AssertionError('No positive result after a recording failure')

    result = cycle.run_self_consuming_cycle(generate=lambda: selected,
        relay_root=tmp_path / 'relay', invoke_worker=launch, worker_observation_host=host)
    assert result.status == 'INTEGRITY_BLOCKED'
    assert 'private-error' not in result.detail
    assert result.retry_allowed is False
    assert all(source.closed for source in native[1])


def test_windows_observation_handoff_refuses_boolean_alias_for_chain_number(native):
    import base64
    owner, _ = native
    spec = request()
    spec['process_chain'][0]['image_bytes'] = 1
    result = _record(owner, spec)
    handoff = owner.worker_observation_handoff(spec, result)
    raw = json.loads(base64.b64decode(handoff['recording_base64']))
    raw['process_chain'][0]['image_bytes'] = True
    changed = json.dumps(raw).encode()
    handoff['recording_base64'] = base64.b64encode(changed).decode()
    handoff['recording_sha256'] = hashlib.sha256(changed).hexdigest()
    with pytest.raises(ValueError):
        owner.check_worker_observation_handoff(handoff)


# Paused-emitter measurements: fake low-level calls, actual measurement owner.
class _IdentityApi:
    def __init__(self, owner):
        self.owner = owner
        self.now = 10.0
        self.calls, self.closed, self.opened = [], [], []
        self.path = r'C:\owned\worker.exe'
        self.data = b'x' * 80
        self.births = {100: 100, 99: 50}
        self.parent, self.actual_pid = 99, 100
        self.read_offset = 0
        self.fail, self.slow, self.cleanup_fail = None, None, False
        self.metadata_reads, self.image_reads = 0, 0
        self.changed_metadata, self.changed_path, self.bad_count = False, False, False
        self.declared_size = 80

    def dll(self, name, **kwargs):
        from types import SimpleNamespace
        assert name in ('kernel32.dll', 'ntdll.dll'), 'Reader must not load a recorder DLL'
        self.calls.append(('dll', name))
        def wrapper(method):
            def call(*args):
                self.calls.append((method, args[0] if args else None))
                if self.slow == method:
                    self.now += 2
                if self.fail == method:
                    return 0 if method != 'NtQueryInformationProcess' else -1
                return getattr(self, method)(*args)
            return call
        return SimpleNamespace(**{method: wrapper(method) for method in (
            'OpenProcess', 'CloseHandle', 'GetProcessTimes', 'QueryFullProcessImageNameW',
            'NtQueryInformationProcess', 'CreateFileW', 'GetFileInformationByHandle', 'ReadFile')})

    def OpenProcess(self, access, inherit, pid):
        assert access == 0x101000 and inherit is False and pid in (99, 100)
        self.opened.append(pid)
        return pid

    def CloseHandle(self, handle):
        self.closed.append(handle)
        if self.cleanup_fail:
            raise OSError('private native detail must not escape')
        return 1

    def GetProcessTimes(self, handle, birth, exit_time, kernel, user):
        birth._obj.low = self.births[handle]
        return 1

    def QueryFullProcessImageNameW(self, handle, flags, buffer, length):
        assert handle == 100
        self.image_reads += 1
        buffer.value = self.path if not self.changed_path or self.image_reads == 1 else r'C:\owned\other.exe'
        length._obj.value = len(buffer.value)
        return 1

    def NtQueryInformationProcess(self, handle, kind, info, size, returned):
        assert handle == 100 and kind == 0
        info._obj.UniqueProcessId = self.actual_pid
        info._obj.InheritedFromUniqueProcessId = self.parent
        returned._obj.value = size
        return 0

    def CreateFileW(self, path, access, share, security, disposition, flags, template):
        assert path == self.path and access == 0x80000000 and share == 1 and disposition == 3
        self.opened.append(500)
        return 500

    def GetFileInformationByHandle(self, handle, info):
        assert handle == 500
        self.metadata_reads += 1
        info._obj.FileSizeLow = self.declared_size
        info._obj.NumberOfLinks = 1
        info._obj.VolumeSerialNumber = 7
        info._obj.FileIndexLow = 9 + (self.changed_metadata and self.metadata_reads > 1)
        return 1

    def ReadFile(self, handle, buffer, maximum, count, overlapped):
        assert handle == 500 and maximum == 65536
        chunk = self.data[self.read_offset:self.read_offset + maximum]
        self.owner.C.memmove(buffer, chunk, len(chunk))
        count._obj.value = maximum + 1 if self.bad_count else len(chunk)
        self.read_offset += len(chunk)
        return 1


@pytest.fixture
def identity_api(monkeypatch):
    from automation.orchestration import aios_self_build_apply_result_verifier as owner
    api = _IdentityApi(owner)
    monkeypatch.setattr(owner.C, 'WinDLL', api.dll)
    monkeypatch.setattr(owner.time, 'monotonic', lambda: api.now)
    return owner, api


def _identity_context(api):
    return dict(attempt_id='attempt-one', session_id='session-one', mxc_identity='selected-one',
                policy_sha256='c' * 64, provider_sha256=hashlib.sha256(b'x' * 80).hexdigest(),
                provider_executable=api.path)


def _identity_witness(api):
    witness = _launch_witness_fixture()[0]
    witness.update(creator_process_id=99, child_process_id=100, child_creation_filetime=100,
                   actual_image_path=api.path, resumed=False)
    return witness


def _identity_reader(owner, context):
    factory = getattr(owner, 'WindowsEmitterIdentityReader', None)
    assert callable(factory), 'Missing source-owned measured emitter reader'
    return factory(context)


def test_identity_reader_measures_one_row_and_is_inert_until_called(identity_api):
    owner, api = identity_api
    context = _identity_context(api)
    reader = _identity_reader(owner, context)
    context['session_id'] = 'changed-after-construction'
    assert api.calls == []
    result = reader(_identity_witness(api), deadline=11.0)
    assert result == {'schema': 'AIOS_WINDOWS_WORKER_RECORDING_REQUEST.v1',
        'attempt_id': 'attempt-one', 'session_id': 'session-one', 'mxc_identity': 'selected-one',
        'policy_sha256': 'c' * 64, 'process_chain': [{'pid': 100, 'parent_pid': 99,
        'creation_filetime': 100, 'parent_creation_filetime': 50,
        'image_sha256': hashlib.sha256(b'x' * 80).hexdigest(), 'image_bytes': 80}]}
    assert sorted(api.closed) == [99, 100, 500]
    assert len(api.closed) == len(set(api.closed))


@pytest.mark.parametrize('fault', ['stale_birth', 'wrong_parent', 'late_parent', 'reused_pid',
    'wrong_content', 'wrong_size', 'changed_metadata', 'changed_path', 'bad_count'])
def test_identity_reader_refuses_changed_measured_identity(identity_api, fault):
    owner, api = identity_api
    reader = _identity_reader(owner, _identity_context(api))
    if fault == 'stale_birth': api.births[100] = 101
    if fault == 'wrong_parent': api.parent = 98
    if fault == 'late_parent': api.births[99] = 101
    if fault == 'reused_pid': api.actual_pid = 102
    if fault == 'wrong_content': api.data = b'y' * 80
    if fault == 'wrong_size': api.declared_size = 81
    if fault == 'changed_metadata': api.changed_metadata = True
    if fault == 'changed_path': api.changed_path = True
    if fault == 'bad_count': api.bad_count = True
    with pytest.raises(owner.RecorderUnavailable):
        reader(_identity_witness(api), deadline=11.0)
    assert sorted(api.closed) == sorted(api.opened)
    assert len(api.closed) == len(set(api.closed))


def test_identity_reader_refuses_private_image_before_open(identity_api):
    owner, api = identity_api
    reader = _identity_reader(owner, _identity_context(api))
    witness = _identity_witness(api)
    api.path = r'C:\Users\mylab\.ssh\worker.exe'
    with pytest.raises(owner.RecorderUnavailable): reader(witness, deadline=11.0)
    assert 500 not in api.opened
    assert sorted(api.closed) == sorted(api.opened)


@pytest.mark.parametrize('method', ['OpenProcess', 'GetProcessTimes', 'NtQueryInformationProcess',
    'QueryFullProcessImageNameW', 'CreateFileW', 'GetFileInformationByHandle', 'ReadFile'])
def test_identity_reader_refuses_denied_or_unsupported_api_and_cleans_up(identity_api, method):
    owner, api = identity_api
    reader = _identity_reader(owner, _identity_context(api)); api.fail = method
    with pytest.raises(owner.RecorderUnavailable): reader(_identity_witness(api), deadline=11.0)
    assert sorted(api.closed) == sorted(api.opened)


@pytest.mark.parametrize('method', ['OpenProcess', 'GetProcessTimes', 'NtQueryInformationProcess',
    'QueryFullProcessImageNameW', 'CreateFileW', 'GetFileInformationByHandle', 'ReadFile'])
def test_identity_reader_refuses_late_api_reply_and_cleans_acquired_handles(identity_api, method):
    owner, api = identity_api
    reader = _identity_reader(owner, _identity_context(api)); api.slow = method
    with pytest.raises(owner.RecorderUnavailable): reader(_identity_witness(api), deadline=11.0)
    assert sorted(api.closed) == sorted(api.opened)


def test_identity_reader_cleanup_exception_closes_every_handle_once(identity_api):
    owner, api = identity_api
    reader = _identity_reader(owner, _identity_context(api)); api.cleanup_fail = True
    with pytest.raises(owner.RecorderUnavailable, match='cleanup'):
        reader(_identity_witness(api), deadline=11.0)
    assert sorted(api.closed) == [99, 100, 500]
    assert len(api.closed) == len(set(api.closed))


@pytest.mark.parametrize('field,value', [('child_process_id', True), ('creator_process_id', 100),
    ('child_creation_filetime', 0), ('resumed', True)])
def test_identity_reader_bad_witness_never_opens_api(identity_api, field, value):
    owner, api = identity_api
    reader = _identity_reader(owner, _identity_context(api)); witness = _identity_witness(api)
    witness[field] = value
    with pytest.raises(owner.RecorderUnavailable): reader(witness, deadline=11.0)
    assert api.calls == []


@pytest.mark.parametrize('deadline', [True, float('nan'), float('inf'), 10.0, -1])
def test_identity_reader_invalid_deadline_never_opens_api(identity_api, deadline):
    owner, api = identity_api
    reader = _identity_reader(owner, _identity_context(api))
    with pytest.raises(owner.RecorderUnavailable): reader(_identity_witness(api), deadline=deadline)
    assert api.calls == []


def test_identity_request_refuses_a_chain_loop(identity_api):
    owner, api = identity_api
    spec = request(); spec['process_chain'][-1]['parent_pid'] = 101
    spec['process_chain'][-1]['parent_creation_filetime'] = 50
    with pytest.raises(owner.RecorderUnavailable): owner._request(spec)


def test_identity_host_uses_measured_reader_and_one_deadline(tmp_path, monkeypatch, native, identity_api):
    owner, api = identity_api
    _, _, selected, witness, prompt = _observation_cycle_inputs(tmp_path, monkeypatch)
    api.path = selected['provider_executable']; selected['provider_sha256'] = _identity_context(api)['provider_sha256']
    spec = request(); spec['process_chain'][1]['image_sha256'] = selected['provider_sha256']
    context = _identity_context(api)
    host = owner.WindowsWorkerObservationHost(emitter_reader=_identity_reader(owner, context),
                                             protected_child_reader=lambda: copy.deepcopy(spec))
    witness['actual_image_path'] = api.path
    queued = {'task': {'request_json': json.dumps(selected), 'prompt_text': prompt}}
    original = api.ReadFile
    def slow_read(*args):
        api.now += .2
        return original(*args)
    api.ReadFile = slow_read
    deadlines = []
    original_prepare = owner.prepare_windows_worker_recording
    def prepare(*args, **kwargs):
        prepared = original_prepare(*args, **kwargs); deadlines.append(prepared.deadline)
        return prepared
    monkeypatch.setattr(owner, 'prepare_windows_worker_recording', prepare)
    def launch(enqueued, *, before_resume, collect_protected_child):
        assert before_resume(copy.deepcopy(witness), 1000) is True
        assert api.now > 10 and deadlines == [11.0]
        assert sorted(api.closed) == [99, 100, 500]
        assert native[1][0].started
        recorded = collect_protected_child()
        outbox = tmp_path/'relay'/'outbox';outbox.mkdir(parents=True)
        path = outbox/'measured.execution.json'
        raw = json.dumps({'worker_observation': owner.worker_observation_handoff(spec, recorded)}).encode()
        path.write_bytes(raw)
        return {'execution_path': str(path), 'execution_sha256': hashlib.sha256(raw).hexdigest()}
    assert host.invoke(queued, launch)['execution_path'].endswith('measured.execution.json')


def test_identity_prepare_never_resets_an_existing_deadline(identity_api, native):
    owner, api = identity_api
    emitter = request();emitter['process_chain'] = emitter['process_chain'][1:]
    api.now = 10.8
    with owner.prepare_windows_worker_recording(emitter, timeout_seconds=1, deadline=11.0) as prepared:
        assert prepared.deadline == 11.0
        api.now = 11.0
        with pytest.raises(owner.RecorderUnavailable): prepared.remaining()



@pytest.mark.parametrize('handle', [-2, 2**64, None, 0, -1, True])
def test_identity_reader_invalid_handles_are_not_owned_or_closed(identity_api, handle):
    owner, api = identity_api
    api.OpenProcess = lambda *args: handle
    reader = _identity_reader(owner, _identity_context(api))
    with pytest.raises(owner.RecorderUnavailable): reader(_identity_witness(api), deadline=11.0)
    assert api.closed == []


def test_identity_reader_multi_chunk_hash_and_exact_size(identity_api):
    owner, api = identity_api
    api.data = b'z' * 65537;api.declared_size = len(api.data)
    context = _identity_context(api);context['provider_sha256'] = hashlib.sha256(api.data).hexdigest()
    result = _identity_reader(owner, context)(_identity_witness(api), deadline=11.0)
    assert result['process_chain'][0]['image_bytes'] == 65537
    assert result['process_chain'][0]['image_sha256'] == hashlib.sha256(b'z'*65537).hexdigest()
    assert api.read_offset == 65537
    assert sum(name == 'ReadFile' for name, _ in api.calls) == 3


def test_identity_reader_oversized_file_is_refused_before_read(identity_api):
    owner, api = identity_api
    api.declared_size = 2**31
    with pytest.raises(owner.RecorderUnavailable):
        _identity_reader(owner, _identity_context(api))(_identity_witness(api), deadline=11.0)
    assert not any(name == 'ReadFile' for name, _ in api.calls)
    assert sorted(api.closed) == [99, 100, 500]


def test_identity_reader_changed_parent_birth_during_measurement_is_refused(identity_api):
    owner, api = identity_api
    original = api.GetProcessTimes;reads = []
    def birth(handle, *args):
        reads.append(handle)
        if handle == 99 and reads.count(99) == 2:api.births[99] = 51
        return original(handle, *args)
    api.GetProcessTimes = birth
    with pytest.raises(owner.RecorderUnavailable):
        _identity_reader(owner, _identity_context(api))(_identity_witness(api), deadline=11.0)
    assert sorted(api.closed) == [99, 100, 500]


def test_identity_reader_cleanup_time_consumes_shared_budget(identity_api):
    owner, api = identity_api
    original = api.CloseHandle
    def close(handle):
        api.now += .4
        return original(handle)
    api.CloseHandle = close
    with pytest.raises(owner.RecorderUnavailable, match='deadline'):
        _identity_reader(owner, _identity_context(api))(_identity_witness(api), deadline=11.0)
    assert sorted(api.closed) == [99, 100, 500]


def test_identity_reader_false_close_refuses_success_and_closes_remaining_handles(identity_api):
    owner, api = identity_api
    def close(handle):
        api.closed.append(handle);return 0
    api.CloseHandle = close
    with pytest.raises(owner.RecorderUnavailable, match='cleanup'):
        _identity_reader(owner, _identity_context(api))(_identity_witness(api), deadline=11.0)
    assert sorted(api.closed) == [99, 100, 500]


def test_identity_native_trace_cleanup_failure_cannot_skip_identity_handles(identity_api):
    owner, api = identity_api
    source = object.__new__(owner._NativeWindowsSource)
    source.a = owner._windows_types();source.deadline = 11
    source.session, source.trace, source.thread = 1, None, None
    source.props_buffer = owner.C.create_string_buffer(owner.C.sizeof(source.a.EVENT_TRACE_PROPERTIES))
    source.processes = {100: 100, 99: 99};source.images = {100: (500, '', None, None, None)}
    source.CloseHandle = api.CloseHandle
    def stop(*args):raise OSError('native stop failed')
    source.ControlTrace = stop
    with pytest.raises(owner.RecorderUnavailable, match='cleanup'):source.close()
    assert sorted(api.closed) == [99, 100, 500]
    with pytest.raises(owner.RecorderUnavailable):source.close()
    assert sorted(api.closed) == [99, 100, 500]


@pytest.mark.parametrize('change', ['extra_callback', 'bad_context', 'oversized_chain', 'duplicate_chain'])
def test_identity_input_shape_refuses_executable_or_oversized_data_before_api(identity_api, change):
    owner, api = identity_api
    with pytest.raises(owner.RecorderUnavailable):
        if change == 'extra_callback':
            _identity_reader(owner, {**_identity_context(api), 'callback': 'run-anything'})
        elif change == 'bad_context':
            _identity_reader(owner, {**_identity_context(api), 'provider_sha256': lambda: None})
        else:
            spec = request();spec['process_chain'] *= 9 if change == 'oversized_chain' else 2
            owner._request(spec)
    assert api.calls == []


@pytest.mark.parametrize('fault', ['measurement_spent_budget', 'prepare_spent_budget'])
def test_identity_host_refuses_release_when_shared_budget_is_spent(tmp_path, monkeypatch, native, identity_api, fault):
    owner, api = identity_api
    _, _, selected, witness, prompt = _observation_cycle_inputs(tmp_path, monkeypatch)
    api.path = selected['provider_executable'];selected['provider_sha256'] = _identity_context(api)['provider_sha256']
    host = owner.WindowsWorkerObservationHost(emitter_reader=_identity_reader(owner, _identity_context(api)),
                                             protected_child_reader=lambda: pytest.fail('Child was released'))
    queued = {'task': {'request_json': json.dumps(selected), 'prompt_text': prompt}}
    if fault == 'measurement_spent_budget':api.slow = 'ReadFile'
    else:
        original = owner.prepare_windows_worker_recording
        def prepare(*args, **kwargs):
            api.now = 11.0
            return original(*args, **kwargs)
        monkeypatch.setattr(owner, 'prepare_windows_worker_recording', prepare)
    def launch(enqueued, *, before_resume, collect_protected_child):
        before_resume(copy.deepcopy(witness), 1000)
        pytest.fail('Expired measurement or preparation allowed release')
    with pytest.raises(owner.RecorderUnavailable):host.invoke(queued, launch)
    assert native[1] == []
    assert sorted(api.closed) == [99, 100, 500]



@pytest.mark.parametrize('method', ['GetProcessTimes', 'QueryFullProcessImageNameW',
    'GetFileInformationByHandle', 'ReadFile', 'CloseHandle', 'NtQueryInformationProcess'])
def test_identity_reader_refuses_non_native_api_return_types(identity_api, method):
    owner, api = identity_api
    original = getattr(api, method)
    def unsupported(*args):
        original(*args)
        return False if method == 'NtQueryInformationProcess' else 'unsupported'
    setattr(api, method, unsupported)
    with pytest.raises(owner.RecorderUnavailable):
        _identity_reader(owner, _identity_context(api))(_identity_witness(api), deadline=11.0)
    assert sorted(api.closed) == sorted(api.opened)


def test_identity_reader_can_measure_its_own_process_as_emitter_parent(identity_api, monkeypatch):
    owner, api = identity_api
    monkeypatch.setattr(owner.os, 'getpid', lambda: 99)
    result = _identity_reader(owner, _identity_context(api))(_identity_witness(api), deadline=11.0)
    assert result['process_chain'][0]['parent_creation_filetime'] == 50
    assert sorted(api.closed) == [99, 100, 500]


def test_identity_reader_still_refuses_observing_itself_as_emitter(identity_api, monkeypatch):
    owner, api = identity_api
    monkeypatch.setattr(owner.os, 'getpid', lambda: 100)
    with pytest.raises(owner.RecorderUnavailable):
        _identity_reader(owner, _identity_context(api))(_identity_witness(api), deadline=11.0)
    assert api.opened == [] and api.closed == []


def test_environment_block_uses_windows_name_order_for_underscores():
    from automation.orchestration.aios_self_build_apply_result_verifier import (
        build_windows_launch_environment_block,
    )

    environment = {"_X": "one", "a": "two", "A_Z": "three", "Aa": "four"}
    expected = "a=two\0Aa=four\0A_Z=three\0_X=one\0\0".encode("utf-16-le")

    assert build_windows_launch_environment_block(environment) == expected
