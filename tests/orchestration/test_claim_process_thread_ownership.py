"""Public temp-file lock checks; no AI worker, runtime board, or secret input."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

import pytest

from automation.orchestration.claims import aios_task_claim_control as claims


@pytest.fixture
def process_shared_os_lock(monkeypatch):
    # Model only POSIX same-process record-lock behavior. This is not Linux proof.
    monkeypatch.setattr(claims, "_region_lock", lambda descriptor, **kwargs: None)


def test_nested_process_owner_refused_before_open(tmp_path, monkeypatch, process_shared_os_lock):
    board = tmp_path / "board.json"
    with claims._exclusive_lock(board):
        marker = board.with_suffix(".json.lock")
        held = marker.read_bytes()
        calls = []
        original_open = os.open
        def observed_open(*args, **kwargs):
            calls.append(args[0])
            return original_open(*args, **kwargs)
        monkeypatch.setattr(os, "open", observed_open)
        with pytest.raises(claims.ClaimError, match="locked"):
            with claims._exclusive_lock(board):
                pytest.fail("nested same-process owner entered")
        assert calls == []
        assert marker.read_bytes() == held


def test_other_thread_cannot_enter_same_process_owner(tmp_path, process_shared_os_lock):
    board = tmp_path / "board.json"
    def contender():
        with pytest.raises(claims.ClaimError, match="locked"):
            with claims._exclusive_lock(board):
                pytest.fail("second thread entered held owner")
    with claims._exclusive_lock(board):
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(contender).result(timeout=5)
    with claims._exclusive_lock(board):
        pass


def test_separately_loaded_controller_shares_process_owner(tmp_path, monkeypatch, process_shared_os_lock):
    name = "claim_alias_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, Path(claims.__file__))
    alias = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, alias)
    spec.loader.exec_module(alias)
    monkeypatch.setattr(alias, "_region_lock", lambda descriptor, **kwargs: None)
    board = tmp_path / "board.json"
    with claims._exclusive_lock(board):
        with pytest.raises(alias.ClaimError, match="locked"):
            with alias._exclusive_lock(board):
                pytest.fail("second module instance entered same process owner")


def test_independent_paths_can_be_owned_together(tmp_path, process_shared_os_lock):
    with claims._exclusive_lock(tmp_path / "one.json"):
        with claims._exclusive_lock(tmp_path / "two.json"):
            pass


def test_body_error_releases_process_and_os_owner(tmp_path):
    board = tmp_path / "board.json"
    with pytest.raises(ValueError, match="public-test-error"):
        with claims._exclusive_lock(board):
            raise ValueError("public-test-error")
    with claims._exclusive_lock(board):
        pass


def test_failed_open_does_not_leave_process_owner(tmp_path, monkeypatch):
    board = tmp_path / "board.json"
    original_open = os.open
    def fail(*args, **kwargs):
        raise OSError("public-test-open-error")
    monkeypatch.setattr(os, "open", fail)
    with pytest.raises(OSError, match="public-test-open-error"):
        with claims._exclusive_lock(board):
            pytest.fail("failed open entered owner")
    monkeypatch.setattr(os, "open", original_open)
    with claims._exclusive_lock(board):
        pass


def test_board_replacement_cannot_change_lock_owner_key(tmp_path, monkeypatch, process_shared_os_lock):
    board = tmp_path / "board.json"
    earlier_target = tmp_path / "earlier-target.json"
    replaced = False
    original_resolve = Path.resolve
    # Model a board symlink replaced by atomic save. The persistent lock path
    # stays the same; this does not require Windows symlink permission.
    def observed_resolve(self, *args, **kwargs):
        if self == board and not replaced:
            return original_resolve(earlier_target, *args, **kwargs)
        return original_resolve(self, *args, **kwargs)
    monkeypatch.setattr(Path, "resolve", observed_resolve)
    with claims._exclusive_lock(board):
        replaced = True
        calls = []
        original_open = os.open
        def observed_open(*args, **kwargs):
            calls.append(args[0])
            return original_open(*args, **kwargs)
        monkeypatch.setattr(os, "open", observed_open)
        with pytest.raises(claims.ClaimError):
            with claims._exclusive_lock(board):
                pytest.fail("changed board identity entered held lock")
        assert calls == []


def test_real_os_lock_still_refuses_separate_process(tmp_path):
    board = tmp_path / "board.json"
    code = '''
import sys
from pathlib import Path
from automation.orchestration.claims import aios_task_claim_control as c
try:
    with c._exclusive_lock(Path(sys.argv[1])):
        sys.exit(3)
except c.ClaimError:
    sys.exit(0)
'''
    root = str(Path(__file__).resolve().parents[2])
    environment = {"SystemRoot": os.environ.get("SystemRoot", ""),
                   "PYTHONPATH": root, "PYTHONDONTWRITEBYTECODE": "1"}
    with claims._exclusive_lock(board):
        result = subprocess.run([sys.executable, "-B", "-c", code, str(board)],
                                cwd=root, env=environment, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr


def test_new_guard_is_bound_to_execution_file_identity(tmp_path):
    path = Path(__file__).with_name("test_aios_self_build_one_action_local_apply_executor.py")
    spec = importlib.util.spec_from_file_location("public_thread_test_helpers", path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    fixture = helper._auth003_fixture(tmp_path, module=claims)
    guard_path = "automation/orchestration/claims/aios_process_path_lock.py"
    assert guard_path in fixture["identity"]["source_hashes"]
    target = tmp_path / guard_path
    target.write_bytes(target.read_bytes() + b"\n# public-test-change\n")
    calls = []
    with pytest.raises(claims.ClaimError, match="source"):
        fixture["controller"].execute_once(
            expected_claim=fixture["claim"], invocation=fixture["invocation"],
            authority_reader=lambda: fixture["material"],
            action=lambda: calls.append(True), allow_test_trust=True,
        )
    assert calls == []


def test_registered_fork_callback_resets_held_process_guard(tmp_path, monkeypatch):
    callbacks = []
    monkeypatch.setattr(os, "register_at_fork", lambda **kw: callbacks.append(kw["after_in_child"]), raising=False)
    path = Path(claims.process_locks.__file__)
    spec = importlib.util.spec_from_file_location("public_fork_guard_model", path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    assert len(callbacks) == 1
    marker = tmp_path / "board.json.lock"
    with helper.process_path_lock(marker):
        callbacks[0]()  # Model the registered child callback; no fork on Windows.
        with helper.process_path_lock(marker):
            pass


@pytest.mark.skipif(not hasattr(os, "fork"), reason="Requires real POSIX fork; not proved on Windows")
def test_real_fork_resets_process_guard_but_preserves_parent_os_owner(tmp_path):
    board = tmp_path / "board.json"
    other = tmp_path / "other.json"
    with claims._exclusive_lock(board):
        pid = os.fork()
        if pid == 0:
            try:
                # Prove child-local reset separately from the real OS lock.
                with claims.process_locks.process_path_lock(board.with_suffix(".json.lock")):
                    pass
                with claims._exclusive_lock(other):
                    pass
                try:
                    with claims._exclusive_lock(board):
                        os._exit(3)
                except claims.ClaimError:
                    os._exit(0)
            except BaseException:
                os._exit(4)
        deadline = time.monotonic() + 5
        while True:
            done, status = os.waitpid(pid, os.WNOHANG)
            if done:
                break
            if time.monotonic() >= deadline:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
                pytest.fail("public fork lock-check child exceeded five seconds")
            time.sleep(0.01)
        assert os.waitstatus_to_exitcode(status) == 0
