import json
import multiprocessing
import os
import time
import subprocess
import threading
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import automation.forex_engine.forex_p1_paper_autostart_v1 as autostart
from automation.forex_engine.forex_p1_paper_autostart_v1 import (
    LEGACY_STATE_RELATIVE_PATH,
    PAPER_OUTPUT_ROOT_RELATIVE_PATH,
    RUNNER_RELATIVE_PATH,
    STATE_RELATIVE_PATH,
    launch,
    preflight,
)


LOCK_SCHEMA = "AIOS_TEST_RUNTIME_LOCK.v1"
LOCK_CAMPAIGN = "AIOS_TEST_RUNTIME_LOCK_CAMPAIGN"
LOCK_FINGERPRINT = "a" * 64
LOCK_FINGERPRINT_OLD = "b" * 64
LOCK_NOW = datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc)


def _owner(
    pid: int,
    *,
    start: str | None = None,
    host: str = "test-host",
    boot: str = "boot-a",
    fingerprint: str = LOCK_FINGERPRINT,
) -> autostart.RuntimeLockOwnership:
    return autostart.RuntimeLockOwnership(
        schema=LOCK_SCHEMA,
        lock_id=str(uuid.uuid4()),
        pid=pid,
        process_start_identity=start or f"pid-{pid}",
        host_identity=host,
        boot_identity=boot,
        campaign_identity=LOCK_CAMPAIGN,
        source_fingerprint=fingerprint,
    )


def _write_lock(
    path: Path,
    owner: autostart.RuntimeLockOwnership,
    *,
    acquired: datetime,
    expires: datetime,
) -> None:
    payload = autostart._lock_metadata(
        owner,
        acquired_at=acquired,
        heartbeat_at=acquired,
        expires_at=expires,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(autostart._render_lock_json(payload))


def _acquire(
    path: Path,
    *,
    now: datetime = LOCK_NOW,
    pid: int = 101,
    fingerprint: str = LOCK_FINGERPRINT,
    **overrides,
) -> autostart.RuntimeLockOwnership | None:
    options = {
        "process_start_identity": f"pid-{pid}",
        "host_identity": "test-host",
        "boot_identity": "boot-a",
        "process_start_reader": lambda target: f"pid-{target}",
    }
    options.update(overrides)
    return autostart.acquire_runtime_lock(
        path,
        schema=LOCK_SCHEMA,
        campaign_identity=LOCK_CAMPAIGN,
        source_fingerprint_value=fingerprint,
        ttl_seconds=60,
        now=now,
        pid=pid,
        **options,
    )


def _process_lock_contender(
    lock_path: str,
    start_event,
    release_event,
    result_path,
    now_text: str,
) -> None:
    path = Path(lock_path)
    outcome = Path(result_path)
    pid = os.getpid()
    owner = None
    if start_event.wait(10):
        owner = autostart.acquire_runtime_lock(
            path,
            schema=LOCK_SCHEMA,
            campaign_identity=LOCK_CAMPAIGN,
            source_fingerprint_value=LOCK_FINGERPRINT,
            ttl_seconds=60,
            now=datetime.fromisoformat(now_text),
            pid=pid,
            process_start_identity=f"pid-{pid}",
            host_identity="test-host",
            boot_identity="boot-a",
            process_start_reader=lambda target: f"pid-{target}",
        )
    outcome.parent.mkdir(parents=True, exist_ok=True)
    outcome.write_text(
        json.dumps({"pid": pid, "won": owner is not None}),
        encoding="utf-8",
    )
    if owner is not None:
        release_event.wait(10)
        autostart.release_runtime_lock(path, owner)


def _abrupt_lock_owner(lock_path: str, ready_event, now_text: str) -> None:
    path = Path(lock_path)
    pid = os.getpid()
    owner = autostart.acquire_runtime_lock(
        path,
        schema=LOCK_SCHEMA,
        campaign_identity=LOCK_CAMPAIGN,
        source_fingerprint_value=LOCK_FINGERPRINT,
        ttl_seconds=1,
        now=datetime.fromisoformat(now_text),
        pid=pid,
        process_start_identity=f"pid-{pid}",
        host_identity="test-host",
        boot_identity="boot-a",
        process_start_reader=lambda target: f"pid-{target}",
    )
    ready_event.set()
    if owner is not None:
        threading.Event().wait(30)


def _repo(tmp_path: Path, accepted: int = 0) -> Path:
    runner = tmp_path / RUNNER_RELATIVE_PATH
    runner.parent.mkdir(parents=True)
    runner.write_text("# canonical runner\n", encoding="utf-8")
    state = tmp_path / STATE_RELATIVE_PATH
    state.parent.mkdir(parents=True)
    state.write_text(
        json.dumps({"accepted_qualifying_trades": accepted}), encoding="utf-8"
    )
    return tmp_path


def _repo_without_state(tmp_path: Path) -> Path:
    runner = tmp_path / RUNNER_RELATIVE_PATH
    runner.parent.mkdir(parents=True)
    runner.write_text("# canonical runner\n", encoding="utf-8")
    return tmp_path


def _env() -> dict[str, str]:
    return {"OANDA_API_TOKEN": "secret", "OANDA_ACCOUNT_ID": "practice"}


def test_preflight_ready_is_paper_only(tmp_path: Path) -> None:
    result = preflight(
        _repo(tmp_path, 2), environment=_env(), branch_reader=lambda _: "main"
    )

    assert result.status == "READY"
    assert result.accepted_trades == 2
    assert result.paper_only is True
    assert result.live_execution_allowed is False
    assert STATE_RELATIVE_PATH.parent == PAPER_OUTPUT_ROOT_RELATIVE_PATH
    assert "Reports" not in STATE_RELATIVE_PATH.parts


def test_preflight_existing_empty_state_blocks(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / STATE_RELATIVE_PATH).write_text("{}", encoding="utf-8")

    result = preflight(root, environment=_env(), branch_reader=lambda _: "main")

    assert result.status == "BLOCKED"
    assert result.reason == "CAMPAIGN_ACCEPTED_COUNT_MISSING"


def test_preflight_missing_accepted_trade_count_blocks(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / STATE_RELATIVE_PATH).write_text(
        json.dumps({"campaign_status": "WAITING_FOR_NEXT_RUN"}),
        encoding="utf-8",
    )

    result = preflight(root, environment=_env(), branch_reader=lambda _: "main")

    assert result.status == "BLOCKED"
    assert result.reason == "CAMPAIGN_ACCEPTED_COUNT_MISSING"


def test_preflight_explicit_zero_accepted_trade_count_remains_valid(tmp_path: Path) -> None:
    result = preflight(
        _repo(tmp_path, 0), environment=_env(), branch_reader=lambda _: "main"
    )

    assert result.status == "READY"
    assert result.accepted_trades == 0


@pytest.mark.parametrize("value", [None, True, 1.5, -1, 31, "0"])
def test_preflight_invalid_accepted_trade_count_blocks(tmp_path: Path, value: object) -> None:
    root = _repo(tmp_path)
    (root / STATE_RELATIVE_PATH).write_text(
        json.dumps({"accepted_qualifying_trades": value}),
        encoding="utf-8",
    )

    result = preflight(root, environment=_env(), branch_reader=lambda _: "main")

    assert result.status == "BLOCKED"
    assert result.reason == "CAMPAIGN_ACCEPTED_COUNT_INVALID"


@pytest.mark.parametrize("value", [{}, [], None, True, 1, "UNKNOWN"])
def test_preflight_malformed_specialized_position_status_blocks(
    tmp_path: Path,
    value: object,
) -> None:
    root = _repo(tmp_path, 0)
    (root / STATE_RELATIVE_PATH).write_text(
        json.dumps({
            "accepted_qualifying_trades": 0,
            "active_position_status": value,
        }),
        encoding="utf-8",
    )

    result = preflight(root, environment=_env(), branch_reader=lambda _: "main")

    assert result.status == "BLOCKED"
    assert result.reason == "CAMPAIGN_STATE_SPECIALIZED_POSITION_INVALID"


def test_preflight_migrates_legacy_partial_state(tmp_path: Path) -> None:
    root = _repo_without_state(tmp_path)
    legacy = root / LEGACY_STATE_RELATIVE_PATH
    legacy.parent.mkdir(parents=True)
    payload = {"accepted_qualifying_trades": 7, "campaign_status": "WAITING_FOR_NEXT_RUN"}
    legacy.write_text(json.dumps(payload), encoding="utf-8")

    result = preflight(root, environment=_env(), branch_reader=lambda _: "main")

    assert result.status == "READY", result
    assert result.accepted_trades == 7
    assert json.loads((root / STATE_RELATIVE_PATH).read_text(encoding="utf-8")) == payload
    assert json.loads(legacy.read_text(encoding="utf-8")) == payload


def test_preflight_legacy_completed_state_never_relaunches(tmp_path: Path) -> None:
    root = _repo_without_state(tmp_path)
    legacy = root / LEGACY_STATE_RELATIVE_PATH
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps({"accepted_qualifying_trades": 30, "campaign_status": "COMPLETE"}),
        encoding="utf-8",
    )

    result = preflight(root, environment=_env(), branch_reader=lambda _: "main")

    assert result.status == "NO_ACTION"
    assert result.reason == "TARGET_ALREADY_REACHED"
    assert result.accepted_trades == 30


def test_preflight_equivalent_legacy_and_canonical_states_are_idempotent(tmp_path: Path) -> None:
    root = _repo(tmp_path, accepted=4)
    payload = {"accepted_qualifying_trades": 4, "campaign_status": "WAITING_FOR_NEXT_RUN"}
    (root / STATE_RELATIVE_PATH).write_text(json.dumps(payload), encoding="utf-8")
    legacy = root / LEGACY_STATE_RELATIVE_PATH
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps(payload), encoding="utf-8")
    before = (root / STATE_RELATIVE_PATH).read_bytes()

    result = preflight(root, environment=_env(), branch_reader=lambda _: "main")

    assert result.status == "READY"
    assert result.accepted_trades == 4
    assert (root / STATE_RELATIVE_PATH).read_bytes() == before


def test_preflight_canonical_valid_and_stale_legacy_different_accepts(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path, accepted=2)
    canonical_payload = {
        "accepted_qualifying_trades": 2,
        "campaign_status": "WAITING_FOR_NEXT_RUN",
        "active_position_status": "NONE",
    }
    (root / STATE_RELATIVE_PATH).write_text(
        json.dumps(canonical_payload), encoding="utf-8"
    )
    legacy = root / LEGACY_STATE_RELATIVE_PATH
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps({"accepted_qualifying_trades": 3, "campaign_status": "RUNNING"}),
        encoding="utf-8",
    )

    result = preflight(root, environment=_env(), branch_reader=lambda _: "main")

    assert result.status == "READY"
    assert result.accepted_trades == 2


def test_preflight_canonical_valid_and_legacy_identical_accepts(tmp_path: Path) -> None:
    root = _repo(tmp_path, accepted=4)
    payload = {"accepted_qualifying_trades": 4, "campaign_status": "WAITING_FOR_NEXT_RUN"}
    (root / STATE_RELATIVE_PATH).write_text(json.dumps(payload), encoding="utf-8")
    legacy = root / LEGACY_STATE_RELATIVE_PATH
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps(payload), encoding="utf-8")

    result = preflight(root, environment=_env(), branch_reader=lambda _: "main")

    assert result.status == "READY"
    assert result.accepted_trades == 4


def test_preflight_canonical_valid_and_newer_inconsistent_legacy_accepts(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path, accepted=2)
    canonical_payload = {
        "accepted_qualifying_trades": 2,
        "campaign_status": "WAITING_FOR_NEXT_RUN",
        "active_position_status": "NONE",
    }
    (root / STATE_RELATIVE_PATH).write_text(
        json.dumps(canonical_payload), encoding="utf-8"
    )
    legacy = root / LEGACY_STATE_RELATIVE_PATH
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps({"accepted_qualifying_trades": 5, "campaign_status": "RUNNING"}),
        encoding="utf-8",
    )

    result = preflight(root, environment=_env(), branch_reader=lambda _: "main")

    assert result.status == "READY"
    assert result.accepted_trades == 2


def test_preflight_repeated_legacy_migration_preserves_canonical_bytes(tmp_path: Path) -> None:
    root = _repo_without_state(tmp_path)
    legacy = root / LEGACY_STATE_RELATIVE_PATH
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps({"accepted_qualifying_trades": 5}), encoding="utf-8")

    first = preflight(root, environment=_env(), branch_reader=lambda _: "main")
    migrated = (root / STATE_RELATIVE_PATH).read_bytes()
    second = preflight(root, environment=_env(), branch_reader=lambda _: "main")

    assert first.accepted_trades == second.accepted_trades == 5
    assert migrated == (root / STATE_RELATIVE_PATH).read_bytes()


def test_preflight_migration_rejects_canonical_state_appearing_before_publication(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = _repo_without_state(tmp_path)
    legacy = root / LEGACY_STATE_RELATIVE_PATH
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps({"accepted_qualifying_trades": 5}), encoding="utf-8"
    )
    canonical = root / STATE_RELATIVE_PATH
    original_create = autostart._atomic_create_state

    def appear_newer(path: Path, state: dict[str, object]) -> bool:
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_text(
            json.dumps({"accepted_qualifying_trades": 8}), encoding="utf-8"
        )
        return original_create(path, state)

    monkeypatch.setattr(autostart, "_atomic_create_state", appear_newer)
    result = preflight(root, environment=_env(), branch_reader=lambda _: "main")

    assert result.status == "READY"
    assert result.accepted_trades == 8
    assert json.loads(canonical.read_text(encoding="utf-8"))["accepted_qualifying_trades"] == 8


def test_preflight_migration_never_replaces_newer_canonical_progress(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = _repo_without_state(tmp_path)
    legacy = root / LEGACY_STATE_RELATIVE_PATH
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps({"accepted_qualifying_trades": 6}), encoding="utf-8"
    )
    canonical = root / STATE_RELATIVE_PATH

    def publish_newer(path: Path, _state: dict[str, object]) -> bool:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"accepted_qualifying_trades": 9}), encoding="utf-8"
        )
        return False

    monkeypatch.setattr(autostart, "_atomic_create_state", publish_newer)
    result = preflight(root, environment=_env(), branch_reader=lambda _: "main")

    assert result.status == "READY"
    assert result.accepted_trades == 9
    assert json.loads(canonical.read_text(encoding="utf-8"))["accepted_qualifying_trades"] == 9


def test_preflight_canonical_absent_and_valid_legacy_migrates_atomically(
    tmp_path: Path,
) -> None:
    root = _repo_without_state(tmp_path)
    legacy = root / LEGACY_STATE_RELATIVE_PATH
    legacy.parent.mkdir(parents=True)
    payload = {"accepted_qualifying_trades": 5, "campaign_status": "WAITING_FOR_NEXT_RUN"}
    legacy.write_text(json.dumps(payload), encoding="utf-8")

    result = preflight(root, environment=_env(), branch_reader=lambda _: "main")

    assert result.status == "READY"
    assert result.accepted_trades == 5
    assert json.loads((root / STATE_RELATIVE_PATH).read_text(encoding="utf-8")) == payload


def test_preflight_canonical_absent_and_malformed_legacy_blocks(tmp_path: Path) -> None:
    root = _repo_without_state(tmp_path)
    legacy = root / LEGACY_STATE_RELATIVE_PATH
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps({"campaign_status": "WAITING_FOR_NEXT_RUN"}), encoding="utf-8")

    result = preflight(root, environment=_env(), branch_reader=lambda _: "main")

    assert result.status == "BLOCKED"
    assert result.reason == "CAMPAIGN_ACCEPTED_COUNT_MISSING"


def test_preflight_canonical_malformed_and_valid_legacy_blocks(tmp_path: Path) -> None:
    root = _repo_without_state(tmp_path)
    canonical = root / STATE_RELATIVE_PATH
    canonical.parent.mkdir(parents=True)
    canonical.write_text(json.dumps({"campaign_status": "WAITING_FOR_NEXT_RUN"}), encoding="utf-8")
    legacy = root / LEGACY_STATE_RELATIVE_PATH
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps({"accepted_qualifying_trades": 5, "campaign_status": "WAITING_FOR_NEXT_RUN"}),
        encoding="utf-8",
    )

    result = preflight(root, environment=_env(), branch_reader=lambda _: "main")

    assert result.status == "BLOCKED"
    assert result.reason == "CAMPAIGN_ACCEPTED_COUNT_MISSING"


def test_preflight_specialized_active_campaign_blocks_launch(tmp_path: Path) -> None:
    root = _repo_without_state(tmp_path)
    legacy = root / LEGACY_STATE_RELATIVE_PATH
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps({
            "accepted_qualifying_trades": 5,
            "thirty_trade_campaign_status": "ACTIVE",
            "active_position_status": "NONE",
            "runtime_launch_status": "NOT_LAUNCHED",
        }),
        encoding="utf-8",
    )

    result = preflight(root, environment=_env(), branch_reader=lambda _: "main")

    assert result.status == "BLOCKED"
    assert result.reason == "CAMPAIGN_STATE_ACTIVE"


def test_preflight_specialized_active_position_blocks_launch(tmp_path: Path) -> None:
    root = _repo_without_state(tmp_path)
    legacy = root / LEGACY_STATE_RELATIVE_PATH
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps({
            "accepted_qualifying_trades": 5,
            "thirty_trade_campaign_status": "IN_PROGRESS",
            "active_position_status": "ACTIVE",
            "runtime_launch_status": "NOT_LAUNCHED",
        }),
        encoding="utf-8",
    )

    result = preflight(root, environment=_env(), branch_reader=lambda _: "main")

    assert result.status == "BLOCKED"
    assert result.reason == "CAMPAIGN_STATE_UNRESOLVED_POSITION"


def test_preflight_generic_and_specialized_position_contradiction_blocks(
    tmp_path: Path,
) -> None:
    root = _repo_without_state(tmp_path)
    legacy = root / LEGACY_STATE_RELATIVE_PATH
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps({
            "accepted_qualifying_trades": 5,
            "active_position": {"trade_id": "open-001"},
            "active_position_status": "NONE",
            "thirty_trade_campaign_status": "IN_PROGRESS",
            "runtime_launch_status": "NOT_LAUNCHED",
        }),
        encoding="utf-8",
    )

    result = preflight(root, environment=_env(), branch_reader=lambda _: "main")

    assert result.status == "BLOCKED"
    assert result.reason == "CAMPAIGN_STATE_CONTRADICTION"


@pytest.mark.parametrize("position", [None, "NONE"])
def test_preflight_inactive_position_values_are_ready(
    tmp_path: Path,
    position: object,
) -> None:
    root = _repo_without_state(tmp_path)
    legacy = root / LEGACY_STATE_RELATIVE_PATH
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps({
            "accepted_qualifying_trades": 5,
            "active_position": position,
            "active_position_status": "NONE",
            "thirty_trade_campaign_status": "IN_PROGRESS",
            "runtime_launch_status": "NOT_LAUNCHED",
        }),
        encoding="utf-8",
    )

    result = preflight(root, environment=_env(), branch_reader=lambda _: "main")

    assert result.status == "READY"


def test_preflight_malformed_scalar_position_fails_closed(tmp_path: Path) -> None:
    root = _repo_without_state(tmp_path)
    legacy = root / LEGACY_STATE_RELATIVE_PATH
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps({
            "accepted_qualifying_trades": 5,
            "active_position": 1,
            "active_position_status": "NONE",
            "thirty_trade_campaign_status": "IN_PROGRESS",
            "runtime_launch_status": "NOT_LAUNCHED",
        }),
        encoding="utf-8",
    )

    result = preflight(root, environment=_env(), branch_reader=lambda _: "main")

    assert result.status == "BLOCKED"
    assert result.reason == "CAMPAIGN_STATE_POSITION_INVALID"


def test_preflight_fully_inactive_specialized_state_is_ready(tmp_path: Path) -> None:
    root = _repo_without_state(tmp_path)
    legacy = root / LEGACY_STATE_RELATIVE_PATH
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps({
            "accepted_qualifying_trades": 5,
            "campaign_status": "WAITING_FOR_NEXT_RUN",
            "thirty_trade_campaign_status": "IN_PROGRESS",
            "active_position_status": "NONE",
            "runtime_launch_status": "NOT_LAUNCHED",
        }),
        encoding="utf-8",
    )

    result = preflight(root, environment=_env(), branch_reader=lambda _: "main")

    assert result.status == "READY"
    assert result.accepted_trades == 5


def test_launch_does_not_start_when_legacy_state_is_active(tmp_path: Path) -> None:
    root = _repo_without_state(tmp_path)
    legacy = root / LEGACY_STATE_RELATIVE_PATH
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps({"accepted_qualifying_trades": 5, "campaign_status": "RUNNING"}),
        encoding="utf-8",
    )
    called = []

    def forbidden_run(*args, **kwargs):
        called.append(args)
        raise AssertionError("active campaign must not launch a second runner")

    assert launch(
        root,
        environment=_env(),
        branch_reader=lambda _: "main",
        run=forbidden_run,
    ) == 2
    assert called == []
    assert (root / STATE_RELATIVE_PATH).exists()


def test_preflight_blocks_missing_credentials(tmp_path: Path) -> None:
    result = preflight(
        _repo(tmp_path), environment={}, branch_reader=lambda _: "main"
    )

    assert result.reason == "RUNTIME_CREDENTIALS_MISSING"


def test_preflight_blocks_safety_stop(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    stop = root / ".aios/runtime/forex/kill_switch.active"
    stop.parent.mkdir(parents=True)
    stop.touch()

    result = preflight(root, environment=_env(), branch_reader=lambda _: "main")

    assert result.reason.startswith("SAFETY_STOP_ACTIVE:")


def test_preflight_does_nothing_after_target(tmp_path: Path) -> None:
    result = preflight(
        _repo(tmp_path, 30), environment=_env(), branch_reader=lambda _: "main"
    )

    assert result.status == "NO_ACTION"
    assert result.reason == "TARGET_ALREADY_REACHED"


def test_launch_uses_only_canonical_supertrend_paper_flags(tmp_path: Path) -> None:
    root = _repo(tmp_path, 1)
    observed = {}

    def fake_run(command, **kwargs):
        observed["command"] = list(command)
        return subprocess.CompletedProcess(command, 0)

    assert launch(
        root,
        environment=_env(),
        branch_reader=lambda _: "main",
        run=fake_run,
    ) == 0
    assert "--signal-source" in observed["command"]
    assert "supertrend" in observed["command"]
    assert "--supertrend-paper-demo-only" in observed["command"]
    assert "--owner-local-runtime" in observed["command"]
    output_root_index = observed["command"].index("--output-root") + 1
    assert Path(observed["command"][output_root_index]) == (
        root / PAPER_OUTPUT_ROOT_RELATIVE_PATH
    )
    assert not any(
        str(root / "Reports" / "forex_delivery") in argument
        for argument in observed["command"]
    )
    assert not (root / ".aios/runtime/forex_p1_paper_autostart_v1/launch.lock").exists()


def test_preflight_only_never_starts_runner(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    def forbidden_run(*args, **kwargs):
        raise AssertionError("runner must not start")

    assert launch(
        root,
        environment=_env(),
        preflight_only=True,
        branch_reader=lambda _: "main",
        run=forbidden_run,
    ) == 0


def test_runtime_lock_atomic_exclusive_acquisition_and_duplicate_rejection(tmp_path: Path) -> None:
    path = tmp_path / "launch.lock"
    first = _acquire(path, pid=101)
    assert first is not None
    assert _acquire(path, pid=202) is None
    assert autostart.release_runtime_lock(path, first) is True


def test_runtime_lock_active_owner_is_protected_after_ttl(tmp_path: Path) -> None:
    path = tmp_path / "launch.lock"
    active = _owner(101)
    _write_lock(
        path,
        active,
        acquired=LOCK_NOW - timedelta(hours=2),
        expires=LOCK_NOW - timedelta(hours=1),
    )
    contender = _acquire(
        path,
        pid=202,
        process_start_reader=lambda target: "pid-101" if target == 101 else f"pid-{target}",
    )
    assert contender is None
    assert autostart.read_runtime_lock(
        path,
        schema=LOCK_SCHEMA,
        campaign_identity=LOCK_CAMPAIGN,
        source_fingerprint_value=LOCK_FINGERPRINT,
    )["lock_id"] == active.lock_id


def test_runtime_lock_immediately_recovers_proven_dead_owner(tmp_path: Path) -> None:
    path = tmp_path / "launch.lock"
    dead = _owner(101)
    _write_lock(path, dead, acquired=LOCK_NOW, expires=LOCK_NOW + timedelta(hours=1))

    def missing(_pid: int) -> str:
        raise ProcessLookupError

    recovered = _acquire(path, pid=202, process_start_reader=missing)
    assert recovered is not None
    assert recovered.lock_id != dead.lock_id
    assert autostart.release_runtime_lock(path, recovered) is True


def test_runtime_lock_immediately_recovers_after_same_host_reboot(tmp_path: Path) -> None:
    path = tmp_path / "launch.lock"
    previous_boot = _owner(101, boot="boot-before")
    _write_lock(
        path,
        previous_boot,
        acquired=LOCK_NOW,
        expires=LOCK_NOW + timedelta(hours=1),
    )
    recovered = _acquire(path, pid=202, boot_identity="boot-after")
    assert recovered is not None
    assert autostart.release_runtime_lock(path, recovered) is True


def test_runtime_lock_unknown_owner_blocks_until_ttl(tmp_path: Path) -> None:
    path = tmp_path / "launch.lock"
    unknown = _owner(101, host="other-host")
    _write_lock(path, unknown, acquired=LOCK_NOW, expires=LOCK_NOW + timedelta(minutes=1))
    assert _acquire(path, now=LOCK_NOW, pid=202) is None
    recovered = _acquire(path, now=LOCK_NOW + timedelta(minutes=2), pid=202)
    assert recovered is not None
    assert autostart.release_runtime_lock(path, recovered) is True


def test_runtime_lock_host_mismatch_classifies_unknown() -> None:
    payload = autostart._lock_metadata(
        _owner(101, host="other-host"),
        acquired_at=LOCK_NOW,
        heartbeat_at=LOCK_NOW,
        expires_at=LOCK_NOW + timedelta(minutes=1),
    )
    assert autostart.classify_lock_owner(
        payload,
        current_host_identity="test-host",
        current_boot_identity="boot-a",
        process_start_reader=lambda _pid: "pid-101",
    ) is autostart.LockOwnerState.UNKNOWN


def test_runtime_lock_pid_reuse_is_dead_and_recoverable_immediately(tmp_path: Path) -> None:
    path = tmp_path / "launch.lock"
    reused = _owner(101, start="original-start")
    _write_lock(path, reused, acquired=LOCK_NOW, expires=LOCK_NOW + timedelta(hours=1))
    recovered = _acquire(
        path,
        pid=202,
        process_start_reader=lambda target: "reused-pid-start" if target == 101 else f"pid-{target}",
    )
    assert recovered is not None
    assert autostart.release_runtime_lock(path, recovered) is True


@pytest.mark.parametrize("contents", [b"{", b"{}", b'{"schema":"truncated"'])
def test_runtime_lock_malformed_metadata_fails_closed(tmp_path: Path, contents: bytes) -> None:
    path = tmp_path / "launch.lock"
    path.write_bytes(contents)
    with pytest.raises(ValueError, match="RUNTIME_LOCK_METADATA_INVALID"):
        _acquire(path, pid=202)
    assert path.read_bytes() == contents


def test_runtime_lock_release_is_exact_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "launch.lock"
    owner = _acquire(path)
    assert owner is not None
    assert autostart.release_runtime_lock(path, replace(owner, lock_id=str(uuid.uuid4()))) is False
    assert path.exists()
    assert autostart.release_runtime_lock(path, owner) is True
    assert not path.exists()


def test_runtime_lock_refresh_is_exact_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "launch.lock"
    owner = _acquire(path)
    assert owner is not None
    original = path.read_bytes()
    wrong_owner = replace(owner, lock_id=str(uuid.uuid4()))
    assert autostart.refresh_runtime_lock(
        path,
        wrong_owner,
        ttl_seconds=60,
        now=LOCK_NOW + timedelta(seconds=1),
    ) is False
    assert path.read_bytes() == original
    assert autostart.refresh_runtime_lock(
        path,
        owner,
        ttl_seconds=60,
        now=LOCK_NOW + timedelta(seconds=2),
    ) is True
    refreshed = autostart.read_runtime_lock(
        path,
        schema=LOCK_SCHEMA,
        campaign_identity=LOCK_CAMPAIGN,
        source_fingerprint_value=LOCK_FINGERPRINT,
    )
    assert refreshed is not None
    assert refreshed["lock_id"] == owner.lock_id
    assert refreshed["heartbeat_at_utc"] == autostart._stamp(
        LOCK_NOW + timedelta(seconds=2)
    )
    assert autostart.release_runtime_lock(path, owner) is True


@pytest.mark.parametrize("ttl", [0, -1, True, 1.5])
def test_runtime_lock_refresh_validates_ttl(tmp_path: Path, ttl) -> None:
    path = tmp_path / "launch.lock"
    owner = _acquire(path)
    assert owner is not None
    with pytest.raises(ValueError, match="RUNTIME_LOCK_TTL_INVALID"):
        autostart.refresh_runtime_lock(path, owner, ttl_seconds=ttl)
    assert autostart.release_runtime_lock(path, owner) is True


def test_runtime_lock_refresh_cannot_undo_concurrent_release(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "launch.lock"
    owner = _acquire(path)
    assert owner is not None
    entered = threading.Event()
    proceed = threading.Event()
    original_replace = autostart._atomic_replace_lock

    def pausing_replace(lock_path, payload):
        entered.set()
        assert proceed.wait(5)
        original_replace(lock_path, payload)

    monkeypatch.setattr(autostart, "_atomic_replace_lock", pausing_replace)
    results = {}
    refresher = threading.Thread(
        target=lambda: results.setdefault(
            "refresh",
            autostart.refresh_runtime_lock(
                path,
                owner,
                ttl_seconds=60,
                now=LOCK_NOW + timedelta(seconds=1),
            ),
        )
    )
    releaser = threading.Thread(
        target=lambda: results.setdefault("release", autostart.release_runtime_lock(path, owner))
    )
    refresher.start()
    assert entered.wait(5)
    releaser.start()
    proceed.set()
    refresher.join(5)
    releaser.join(5)
    assert results == {"refresh": True, "release": True}
    assert not path.exists()


def test_runtime_lock_stale_takeover_serializes_against_refresh(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "launch.lock"
    stale = _owner(101)
    _write_lock(
        path,
        stale,
        acquired=LOCK_NOW - timedelta(minutes=2),
        expires=LOCK_NOW - timedelta(minutes=1),
    )
    entered = threading.Event()
    proceed = threading.Event()
    original_receipt = autostart._append_lock_recovery_receipt

    def pausing_receipt(*args, **kwargs):
        entered.set()
        assert proceed.wait(5)
        original_receipt(*args, **kwargs)

    monkeypatch.setattr(autostart, "_append_lock_recovery_receipt", pausing_receipt)
    results = {}
    takeover = threading.Thread(
        target=lambda: results.setdefault(
            "new",
            _acquire(
                path,
                pid=202,
                process_start_reader=lambda target: "pid-reused" if target == 101 else f"pid-{target}",
            ),
        )
    )
    refresh = threading.Thread(
        target=lambda: results.setdefault(
            "refresh",
            autostart.refresh_runtime_lock(
                path,
                stale,
                ttl_seconds=60,
                now=LOCK_NOW + timedelta(seconds=1),
            ),
        )
    )
    takeover.start()
    assert entered.wait(5)
    refresh.start()
    proceed.set()
    takeover.join(5)
    refresh.join(5)
    assert results["new"] is not None
    assert results["refresh"] is False
    assert autostart.release_runtime_lock(path, results["new"]) is True


def test_runtime_lock_stale_refresh_release_race_preserves_replacement_owner(
    tmp_path: Path,
) -> None:
    path = tmp_path / "launch.lock"
    stale_owner = _acquire(path, pid=101)
    assert stale_owner is not None
    assert autostart.release_runtime_lock(path, stale_owner) is True
    replacement_owner = _acquire(path, pid=202)
    assert replacement_owner is not None
    barrier = threading.Barrier(2)
    results = {}

    def stale_refresh() -> None:
        barrier.wait()
        results["refresh"] = autostart.refresh_runtime_lock(
            path,
            stale_owner,
            ttl_seconds=60,
            now=LOCK_NOW + timedelta(seconds=1),
        )

    def stale_release() -> None:
        barrier.wait()
        results["release"] = autostart.release_runtime_lock(path, stale_owner)

    threads = [
        threading.Thread(target=stale_refresh),
        threading.Thread(target=stale_release),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)
        assert not thread.is_alive()
    assert results == {"refresh": False, "release": False}
    record = autostart.read_runtime_lock(
        path,
        schema=LOCK_SCHEMA,
        campaign_identity=LOCK_CAMPAIGN,
        source_fingerprint_value=LOCK_FINGERPRINT,
    )
    assert record is not None
    assert record["lock_id"] == replacement_owner.lock_id
    assert autostart.release_runtime_lock(path, replacement_owner) is True


def test_runtime_lock_two_thread_contenders_produce_one_owner(tmp_path: Path) -> None:
    path = tmp_path / "launch.lock"
    barrier = threading.Barrier(2)
    results = []

    def contend(pid: int) -> None:
        barrier.wait()
        results.append(_acquire(path, pid=pid))

    threads = [threading.Thread(target=contend, args=(pid,)) for pid in (101, 202)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)
    winners = [owner for owner in results if owner is not None]
    assert len(winners) == 1
    assert autostart.release_runtime_lock(path, winners[0]) is True


@pytest.mark.parametrize("preexisting_stale", [False, True])
def test_runtime_lock_two_process_contenders_produce_one_owner(
    tmp_path: Path,
    preexisting_stale: bool,
) -> None:
    path = tmp_path / "launch.lock"
    if preexisting_stale:
        stale = _owner(999999, start="original-owner-start")
        _write_lock(
            path,
            stale,
            acquired=LOCK_NOW - timedelta(minutes=2),
            expires=LOCK_NOW - timedelta(minutes=1),
        )
    context = multiprocessing.get_context("spawn")
    start_event = context.Event()
    release_event = context.Event()
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    processes = [
        context.Process(
            target=_process_lock_contender,
            args=(
                str(path),
                start_event,
                release_event,
                str(results_dir / f"result-{index}.json"),
                LOCK_NOW.isoformat(),
            ),
        )
        for index in range(2)
    ]
    for process in processes:
        process.start()
    start_event.set()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        result_files = sorted(results_dir.glob("result-*.json"))
        if len(result_files) == len(processes):
            break
        time.sleep(0.05)
    result_files = sorted(results_dir.glob("result-*.json"))
    assert len(result_files) == len(processes)
    results = [json.loads(path.read_text(encoding="utf-8")) for path in result_files]
    assert sum(bool(result["won"]) for result in results) == 1
    release_event.set()
    for process in processes:
        process.join(15)
        assert process.exitcode == 0
    assert not path.exists()


def test_runtime_lock_abrupt_termination_is_recoverable_after_ttl(tmp_path: Path) -> None:
    path = tmp_path / "launch.lock"
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    child = context.Process(
        target=_abrupt_lock_owner,
        args=(str(path), ready, LOCK_NOW.isoformat()),
    )
    child.start()
    assert ready.wait(15)
    assert path.exists()
    child.terminate()
    child.join(15)
    assert child.exitcode is not None

    def missing(_pid: int) -> str:
        raise ProcessLookupError

    recovered = _acquire(
        path,
        now=LOCK_NOW + timedelta(seconds=2),
        pid=202,
        process_start_reader=missing,
    )
    assert recovered is not None
    assert autostart.release_runtime_lock(path, recovered) is True


def test_current_shape_lock_with_dead_owner_source_mismatch_recovers_and_records_receipt(
    monkeypatch, tmp_path: Path
) -> None:
    path = tmp_path / "launch.lock"
    stale = _owner(101, fingerprint=LOCK_FINGERPRINT_OLD)
    _write_lock(
        path,
        stale,
        acquired=LOCK_NOW - timedelta(minutes=2),
        expires=LOCK_NOW - timedelta(minutes=1),
    )
    prior_bytes = path.read_bytes()
    monkeypatch.setattr(autostart, "_host_identity", lambda: "test-host")
    monkeypatch.setattr(autostart, "_boot_identity", lambda: "boot-a")

    owner = _acquire(
        path,
        now=LOCK_NOW,
        pid=202,
        fingerprint=LOCK_FINGERPRINT,
        process_start_reader=lambda _pid: (_ for _ in ()).throw(ProcessLookupError),
    )

    assert owner is not None
    receipt = json.loads((tmp_path / "launch.lock.recovery.jsonl").read_text(encoding="utf-8"))
    assert receipt["owner_state"] == "DEAD"
    assert receipt["recovery_reason"] == "DEAD_OWNER_SOURCE_FINGERPRINT_MISMATCH"
    assert receipt["prior_lock_id"] == stale.lock_id
    assert receipt["prior_pid"] == stale.pid
    assert receipt["prior_campaign_identity"] == LOCK_CAMPAIGN
    assert receipt["prior_source_fingerprint"] == LOCK_FINGERPRINT_OLD
    assert receipt["current_source_fingerprint"] == LOCK_FINGERPRINT
    assert receipt["prior_metadata_sha256"] == __import__("hashlib").sha256(prior_bytes).hexdigest()
    assert autostart.release_runtime_lock(path, owner) is True


@pytest.mark.parametrize(
    "process_reader, boot_identity",
    [
        (lambda _pid: "pid-101", lambda: "boot-a"),
        (lambda _pid: (_ for _ in ()).throw(RuntimeError("unknown")), lambda: "boot-a"),
    ],
)
def test_current_shape_lock_source_mismatch_blocks_active_or_unknown_owner(
    monkeypatch,
    tmp_path: Path,
    process_reader,
    boot_identity,
) -> None:
    path = tmp_path / "launch.lock"
    stale = _owner(101, fingerprint=LOCK_FINGERPRINT_OLD)
    _write_lock(
        path,
        stale,
        acquired=LOCK_NOW - timedelta(minutes=2),
        expires=LOCK_NOW - timedelta(minutes=1),
    )
    monkeypatch.setattr(autostart, "_host_identity", lambda: "test-host")
    monkeypatch.setattr(autostart, "_boot_identity", boot_identity)

    with pytest.raises(ValueError, match="RUNTIME_LOCK_METADATA_INVALID"):
        _acquire(
            path,
            now=LOCK_NOW,
            pid=202,
            fingerprint=LOCK_FINGERPRINT,
            process_start_reader=process_reader,
        )


@pytest.mark.parametrize(
    "mutator",
        [
            lambda payload: payload.pop("source_fingerprint"),
            lambda payload: payload.__setitem__("source_fingerprint", "not-a-sha256"),
            lambda payload: payload.__setitem__("campaign_identity", "wrong-campaign"),
            lambda payload: payload.__setitem__("pid", 0),
            lambda payload: payload.__setitem__(
                "expires_at_utc",
                autostart._stamp(LOCK_NOW - timedelta(minutes=2)),
            ),
        ],
    )
def test_current_shape_lock_malformed_metadata_remains_blocked(
    monkeypatch,
    tmp_path: Path,
    mutator,
) -> None:
    path = tmp_path / "launch.lock"
    stale = _owner(101, fingerprint=LOCK_FINGERPRINT_OLD)
    payload = autostart._lock_metadata(
        stale,
        acquired_at=LOCK_NOW - timedelta(minutes=2),
        heartbeat_at=LOCK_NOW - timedelta(minutes=2),
        expires_at=LOCK_NOW + timedelta(minutes=1),
    )
    mutator(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(autostart, "_host_identity", lambda: "test-host")
    monkeypatch.setattr(autostart, "_boot_identity", lambda: "boot-a")

    with pytest.raises(ValueError, match="RUNTIME_LOCK_METADATA_INVALID"):
        _acquire(
            path,
            now=LOCK_NOW,
            pid=202,
            fingerprint=LOCK_FINGERPRINT,
            process_start_reader=lambda _pid: (_ for _ in ()).throw(ProcessLookupError),
        )


def test_windows_process_missing_pid_is_dead(monkeypatch) -> None:
    monkeypatch.setattr(
        autostart.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [], 3, stdout='{"status":"MISSING"}', stderr=""
        ),
    )
    payload = autostart._lock_metadata(
        _owner(101),
        acquired_at=LOCK_NOW,
        heartbeat_at=LOCK_NOW,
        expires_at=LOCK_NOW + timedelta(minutes=1),
    )
    assert autostart.classify_lock_owner(
        payload,
        current_host_identity="test-host",
        current_boot_identity="boot-a",
        process_start_reader=autostart._windows_process_start_identity,
    ) is autostart.LockOwnerState.DEAD


def test_windows_process_matching_pid_start_is_active(monkeypatch) -> None:
    process_start = "2026-08-15T19:59:58Z"
    monkeypatch.setattr(
        autostart.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [],
            0,
            stdout=json.dumps({"status": "FOUND", "start": process_start}),
            stderr="",
        ),
    )
    payload = autostart._lock_metadata(
        _owner(101, start=process_start),
        acquired_at=LOCK_NOW,
        heartbeat_at=LOCK_NOW,
        expires_at=LOCK_NOW + timedelta(minutes=1),
    )
    assert autostart.classify_lock_owner(
        payload,
        current_host_identity="test-host",
        current_boot_identity="boot-a",
        process_start_reader=autostart._windows_process_start_identity,
    ) is autostart.LockOwnerState.ACTIVE


@pytest.mark.parametrize(
    ("behavior", "returncode", "stdout"),
    [
        ("access-denied", 4, '{"status":"UNKNOWN"}'),
        ("unexpected", 1, "unexpected failure"),
        ("invalid-output", 0, "not-json"),
    ],
)
def test_windows_process_unconfirmed_failures_are_unknown(
    monkeypatch,
    behavior: str,
    returncode: int,
    stdout: str,
) -> None:
    del behavior
    monkeypatch.setattr(
        autostart.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [], returncode, stdout=stdout, stderr="sensitive broker body"
        ),
    )
    payload = autostart._lock_metadata(
        _owner(101),
        acquired_at=LOCK_NOW,
        heartbeat_at=LOCK_NOW,
        expires_at=LOCK_NOW + timedelta(minutes=1),
    )
    assert autostart.classify_lock_owner(
        payload,
        current_host_identity="test-host",
        current_boot_identity="boot-a",
        process_start_reader=autostart._windows_process_start_identity,
    ) is autostart.LockOwnerState.UNKNOWN


def test_windows_process_timeout_is_unknown_and_bounded(monkeypatch) -> None:
    observed = {}

    def timeout(*_args, **kwargs):
        observed["timeout"] = kwargs.get("timeout")
        raise subprocess.TimeoutExpired("powershell.exe", kwargs["timeout"])

    monkeypatch.setattr(autostart.subprocess, "run", timeout)
    payload = autostart._lock_metadata(
        _owner(101),
        acquired_at=LOCK_NOW,
        heartbeat_at=LOCK_NOW,
        expires_at=LOCK_NOW + timedelta(minutes=1),
    )
    assert autostart.classify_lock_owner(
        payload,
        current_host_identity="test-host",
        current_boot_identity="boot-a",
        process_start_reader=autostart._windows_process_start_identity,
    ) is autostart.LockOwnerState.UNKNOWN
    assert observed["timeout"] == autostart.LOCK_POWERSHELL_TIMEOUT_SECONDS


def test_windows_boot_identity_timeout_is_bounded(monkeypatch) -> None:
    observed = {}

    def timeout(*_args, **kwargs):
        observed["timeout"] = kwargs.get("timeout")
        raise subprocess.TimeoutExpired("powershell.exe", kwargs["timeout"])

    monkeypatch.setattr(autostart.subprocess, "run", timeout)
    monkeypatch.setattr(autostart, "_BOOT_IDENTITY_CACHE", None, raising=False)
    monkeypatch.setattr(autostart.os, "name", "nt")
    with pytest.raises(RuntimeError, match="RUNTIME_LOCK_BOOT_IDENTITY_UNAVAILABLE"):
        autostart._boot_identity()
    assert observed["timeout"] == autostart.LOCK_POWERSHELL_TIMEOUT_SECONDS


class _PartialWriteFailure:
    def __init__(self, stream) -> None:
        self._stream = stream

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        self._stream.close()

    def write(self, data: bytes) -> int:
        self._stream.write(data[:7])
        self._stream.flush()
        raise OSError("Authorization: Bearer secret-token broker-response-body")

    def flush(self) -> None:
        self._stream.flush()

    def fileno(self) -> int:
        return self._stream.fileno()


def test_runtime_lock_partial_receipt_write_preserves_prior_bytes(monkeypatch, tmp_path: Path) -> None:
    lock_path = tmp_path / "launch.lock"
    receipt_path = tmp_path / "launch.lock.recovery.jsonl"
    previous = b'{"schema":"prior-safe-receipt"}\n'
    receipt_path.write_bytes(previous)
    original_open = Path.open

    def failing_open(path_self, mode="r", *args, **kwargs):
        stream = original_open(path_self, mode, *args, **kwargs)
        if mode == "xb" and path_self.name.startswith(f".{receipt_path.name}."):
            return _PartialWriteFailure(stream)
        return stream

    monkeypatch.setattr(Path, "open", failing_open)
    with pytest.raises(RuntimeError, match="RUNTIME_LOCK_RECOVERY_RECEIPT_PERSISTENCE_FAILED"):
        autostart._append_lock_recovery_receipt(
            lock_path,
            prior_metadata=b"corrupt-input Authorization token account-id broker-response-body",
            owner=_owner(202),
            observed_at=LOCK_NOW,
        )
    assert receipt_path.read_bytes() == previous
    assert not list(tmp_path.glob(f".{receipt_path.name}.*.tmp"))


def test_runtime_lock_receipt_fsync_failure_preserves_prior_bytes(monkeypatch, tmp_path: Path) -> None:
    lock_path = tmp_path / "launch.lock"
    receipt_path = tmp_path / "launch.lock.recovery.jsonl"
    previous = b'{"schema":"prior-safe-receipt"}\n'
    receipt_path.write_bytes(previous)

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("secret-token Authorization broker-response-body")

    monkeypatch.setattr(autostart.os, "fsync", fail_fsync)
    with pytest.raises(RuntimeError, match="RUNTIME_LOCK_RECOVERY_RECEIPT_PERSISTENCE_FAILED"):
        autostart._append_lock_recovery_receipt(
            lock_path,
            prior_metadata=b"invalid secret bytes",
            owner=_owner(202),
            observed_at=LOCK_NOW,
        )
    assert receipt_path.read_bytes() == previous
    assert not list(tmp_path.glob(f".{receipt_path.name}.*.tmp"))


def test_runtime_lock_receipt_replace_failure_creates_no_false_success(
    monkeypatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "launch.lock"
    receipt_path = tmp_path / "launch.lock.recovery.jsonl"
    stale = _owner(101)
    _write_lock(
        path,
        stale,
        acquired=LOCK_NOW - timedelta(minutes=2),
        expires=LOCK_NOW - timedelta(minutes=1),
    )
    original_replace = autostart.os.replace

    def fail_receipt_replace(source, destination) -> None:
        if Path(destination) == receipt_path:
            raise OSError("SANITIZED_RECEIPT_REPLACE_FAILURE")
        original_replace(source, destination)

    monkeypatch.setattr(autostart.os, "replace", fail_receipt_replace)
    with pytest.raises(
        RuntimeError,
        match="RUNTIME_LOCK_RECOVERY_RECEIPT_PERSISTENCE_FAILED",
    ):
        _acquire(
            path,
            pid=202,
            process_start_reader=lambda target: (
                "pid-reused" if target == 101 else f"pid-{target}"
            ),
        )
    assert not path.exists()
    assert not receipt_path.exists()
    assert not list(tmp_path.glob(".*.tmp"))


def test_runtime_lock_receipt_failure_leaves_no_orphan_owner(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "launch.lock"
    stale = _owner(101)
    _write_lock(
        path,
        stale,
        acquired=LOCK_NOW - timedelta(minutes=2),
        expires=LOCK_NOW - timedelta(minutes=1),
    )
    monkeypatch.setattr(
        autostart,
        "_append_lock_recovery_receipt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("RUNTIME_LOCK_RECOVERY_RECEIPT_PERSISTENCE_FAILED")
        ),
    )
    with pytest.raises(RuntimeError, match="RUNTIME_LOCK_RECOVERY_RECEIPT_PERSISTENCE_FAILED"):
        _acquire(
            path,
            pid=202,
            process_start_reader=lambda target: "pid-reused" if target == 101 else f"pid-{target}",
        )
    assert not path.exists()
    assert not list(tmp_path.glob(".*.tmp"))


def test_runtime_lock_failed_first_acquisition_leaves_no_orphan_files(
    monkeypatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "launch.lock"

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("SANITIZED_LOCK_FSYNC_FAILURE")

    monkeypatch.setattr(autostart.os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="SANITIZED_LOCK_FSYNC_FAILURE"):
        _acquire(path, pid=101)
    assert not path.exists()
    assert not list(tmp_path.glob(".*.tmp"))


def test_runtime_lock_global_mutex_is_machine_wide(tmp_path: Path) -> None:
    name = autostart._mutex_name(tmp_path / "launch.lock")
    assert name.startswith("Global\\AIOS_FOREX_RUNTIME_LOCK_")
    assert not name.startswith("Local\\")


def test_runtime_lock_metadata_and_receipts_exclude_sensitive_material(monkeypatch, tmp_path: Path) -> None:
    sensitive_values = (
        "secret-token",
        "account-123",
        "Authorization: Bearer",
        "broker-response-body",
        "--command-line-secret",
    )
    for index, value in enumerate(sensitive_values):
        monkeypatch.setenv(f"AIOS_SENSITIVE_{index}", value)
    path = tmp_path / "launch.lock"
    owner = _acquire(path)
    assert owner is not None
    metadata = path.read_text(encoding="utf-8")
    autostart._append_lock_recovery_receipt(
        path,
        prior_metadata=("|".join(sensitive_values)).encode("utf-8"),
        owner=owner,
        observed_at=LOCK_NOW,
    )
    receipt_text = (tmp_path / "launch.lock.recovery.jsonl").read_text(encoding="utf-8")
    assert set(json.loads(receipt_text)) == autostart.LOCK_RECOVERY_RECEIPT_FIELDS
    assert all(value not in metadata and value not in receipt_text for value in sensitive_values)
    assert autostart.release_runtime_lock(path, owner) is True


def test_outer_launch_exception_releases_runtime_lock(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    def crash(*_args, **_kwargs):
        raise RuntimeError("SANITIZED_RUNNER_FAILURE")

    with pytest.raises(RuntimeError, match="SANITIZED_RUNNER_FAILURE"):
        launch(
            root,
            environment=_env(),
            branch_reader=lambda _: "main",
            run=crash,
    )
    assert not (root / ".aios/runtime/forex_p1_paper_autostart_v1/launch.lock").exists()


def test_outer_launch_exception_cannot_release_replacement_owner(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    lock_path = root / ".aios/runtime/forex_p1_paper_autostart_v1/launch.lock"
    replacement = {}

    def replace_owner_then_crash(*_args, **_kwargs):
        current = json.loads(lock_path.read_text(encoding="utf-8"))
        acquired_at = autostart._parse_lock_utc(current["acquired_at_utc"])
        replacement_owner = autostart.RuntimeLockOwnership(
            schema=current["schema"],
            lock_id=str(uuid.uuid4()),
            pid=current["pid"] + 1,
            process_start_identity="replacement-process-start",
            host_identity=current["host_identity"],
            boot_identity=current["boot_identity"],
            campaign_identity=current["campaign_identity"],
            source_fingerprint=current["source_fingerprint"],
        )
        replacement["owner"] = replacement_owner
        autostart._atomic_replace_lock(
            lock_path,
            autostart._lock_metadata(
                replacement_owner,
                acquired_at=acquired_at,
                heartbeat_at=acquired_at,
                expires_at=acquired_at + timedelta(minutes=5),
            ),
        )
        raise RuntimeError("SANITIZED_RUNNER_FAILURE")

    with pytest.raises(RuntimeError, match="SANITIZED_RUNNER_FAILURE"):
        launch(
            root,
            environment=_env(),
            branch_reader=lambda _: "main",
            run=replace_owner_then_crash,
    )
    assert lock_path.exists()
    assert json.loads(lock_path.read_text(encoding="utf-8"))["lock_id"] == (
        replacement["owner"].lock_id
    )
    assert autostart.release_runtime_lock(lock_path, replacement["owner"]) is True


def test_outer_launch_legacy_replacement_owner_is_preserved(tmp_path: Path) -> None:
    root = _repo(tmp_path, accepted=1)
    lock_path = root / ".aios/runtime/forex_p1_paper_autostart_v1/launch.lock"

    def replace_with_legacy_owner(*_args, **_kwargs):
        current = json.loads(lock_path.read_text(encoding="utf-8"))
        lock_path.write_text(
            json.dumps({
                "schema": current["schema"],
                "status": "ACTIVE",
                "owner": "legacy-owner",
                "pid": current["pid"] + 1,
                "heartbeat_at_utc": current["heartbeat_at_utc"],
            }),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(["python"], 0)

    with pytest.raises(autostart._AutostartLockReplacementUnverifiable):
        launch(
            root,
            environment=_env(),
            branch_reader=lambda _: "main",
            run=replace_with_legacy_owner,
        )
    assert lock_path.exists()
    assert json.loads(lock_path.read_text(encoding="utf-8"))["owner"] == "legacy-owner"


def test_outer_launch_malformed_replacement_lock_is_preserved(tmp_path: Path) -> None:
    root = _repo(tmp_path, accepted=1)
    lock_path = root / ".aios/runtime/forex_p1_paper_autostart_v1/launch.lock"

    def replace_with_malformed_lock(*_args, **_kwargs):
        current = json.loads(lock_path.read_text(encoding="utf-8"))
        lock_path.write_text(json.dumps({"schema": current["schema"]}), encoding="utf-8")
        return subprocess.CompletedProcess(["python"], 0)

    with pytest.raises(ValueError, match="RUNTIME_LOCK_METADATA_INVALID"):
        launch(
            root,
            environment=_env(),
            branch_reader=lambda _: "main",
            run=replace_with_malformed_lock,
        )
    assert lock_path.exists()
    assert json.loads(lock_path.read_text(encoding="utf-8")) == {
        "schema": autostart.OUTER_LOCK_SCHEMA,
    }


def test_outer_launch_exact_current_owner_cleanup_removes_lock(tmp_path: Path) -> None:
    root = _repo(tmp_path, accepted=1)

    def finish(*args, **_kwargs):
        return subprocess.CompletedProcess(args[0], 0)

    assert launch(
        root,
        environment=_env(),
        branch_reader=lambda _: "main",
        run=finish,
    ) == 0
    assert not (root / ".aios/runtime/forex_p1_paper_autostart_v1/launch.lock").exists()


def test_outer_launch_primary_exception_does_not_hide_missing_lock_cleanup_failure(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    lock_path = root / ".aios/runtime/forex_p1_paper_autostart_v1/launch.lock"

    def crash(*_args, **_kwargs):
        lock_path.unlink(missing_ok=True)
        raise RuntimeError("SANITIZED_RUNNER_FAILURE")

    with pytest.raises(FileNotFoundError):
        launch(
            root,
            environment=_env(),
            branch_reader=lambda _: "main",
            run=crash,
        )
    assert not lock_path.exists()


def test_outer_launch_primary_exception_does_not_hide_unrelated_cleanup_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _repo(tmp_path)

    def crash(*_args, **_kwargs):
        raise RuntimeError("SANITIZED_RUNNER_FAILURE")

    monkeypatch.setattr(
        autostart,
        "_release_exact_owner_locked",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("SANITIZED_CLEANUP_FAILURE")
        ),
    )
    with pytest.raises(RuntimeError, match="SANITIZED_CLEANUP_FAILURE"):
        launch(
            root,
            environment=_env(),
            branch_reader=lambda _: "main",
            run=crash,
        )


def test_outer_launch_replacement_rejection_propagates_without_primary_exception(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    lock_path = root / ".aios/runtime/forex_p1_paper_autostart_v1/launch.lock"
    replacement: dict[str, autostart.RuntimeLockOwnership] = {}

    def replace_owner_and_finish(*_args, **_kwargs):
        current = json.loads(lock_path.read_text(encoding="utf-8"))
        acquired_at = autostart._parse_lock_utc(current["acquired_at_utc"])
        replacement_owner = autostart.RuntimeLockOwnership(
            schema=current["schema"],
            lock_id=str(uuid.uuid4()),
            pid=current["pid"] + 1,
            process_start_identity="replacement-process-start",
            host_identity=current["host_identity"],
            boot_identity=current["boot_identity"],
            campaign_identity=current["campaign_identity"],
            source_fingerprint=current["source_fingerprint"],
        )
        replacement["owner"] = replacement_owner
        autostart._atomic_replace_lock(
            lock_path,
            autostart._lock_metadata(
                replacement_owner,
                acquired_at=acquired_at,
                heartbeat_at=acquired_at,
                expires_at=acquired_at + timedelta(minutes=5),
            ),
        )
        return subprocess.CompletedProcess(["python"], 0)

    with pytest.raises(autostart._AutostartLockReplaced) as exc_info:
        launch(
            root,
            environment=_env(),
            branch_reader=lambda _: "main",
            run=replace_owner_and_finish,
        )
    assert exc_info.value.replacement_owner == replacement["owner"]
    assert autostart.release_runtime_lock(lock_path, replacement["owner"]) is True
