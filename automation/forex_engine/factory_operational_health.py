"""Synchronous, read-only native factory measurements; never launch authority.

This inspects an already-open native controller/store. It never opens another
SQLite database, reclaims a lease, repairs a receipt, resumes, retries, kills,
creates a controller, publishes an observation, or starts a monitoring loop.
Engineering measurements remain engineering evidence even when every measured
property passes. Process and kernel evidence are sampled, never inferred from
an owner heartbeat or a PID alone. Missing attribution remains unknown.
"""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import threading
import time
from types import CodeType
from typing import Mapping


RESEARCH_DEADLINE_EPOCH = 1792348454.0
CLOSURE_DEADLINE_EPOCH = 1792362854.0
CPU_HARD_CAP_PERCENT = 70
RAM_HARD_CAP_BYTES = 24 * 1024 ** 3
MAX_OWNED_WINDOWS_JOBS = 1
HEARTBEAT_MAX_AGE_SECONDS = 60
PROGRESS_MAX_AGE_SECONDS = 300
RESOURCE_MAX_AGE_SECONDS = 60
FUTURE_TOLERANCE_SECONDS = 2
_CONTROLLER_OBSERVATIONS = {}
_OBSERVATION_SEAL = object()


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _fresh(value, now, maximum):
    return _finite(value) and -FUTURE_TOLERANCE_SECONDS <= now - value <= maximum


def _pins(source_pins):
    if not isinstance(source_pins, Mapping):
        raise ValueError("SOURCE_PINS_REQUIRED")
    return {str(Path(path).resolve()): pin for path, pin in source_pins.items()}


def native_scope_identity(supervisor, source_pins, manifest_path, expected_specs):
    """Digest exact sources, manifest bytes, native run and full supplied catalog."""
    return _digest({"source_pins": _pins(source_pins), "manifest_sha256": _sha(manifest_path),
        "run_id": supervisor.run_id, "specs_sha256": _digest(expected_specs)})


def capture_process_identity(pid):
    """Read current OS creation identity and image identity, without command text.

    Linux adds the boot identity and hashes command bytes. Windows retains a
    query handle for this sample and compares creation times. No signal or
    process mutation occurs. Failure is static and contains no command/secret.
    """
    if type(pid) is not int or pid <= 0:
        return {"verified": False, "code": "PROCESS_IDENTITY_UNAVAILABLE"}
    try:
        if sys.platform.startswith("linux"):
            root = Path("/proc") / str(pid)
            raw = (root / "stat").read_text(encoding="utf-8")
            # comm is parenthesized and may contain spaces or closing parens.
            fields = raw[raw.rfind(")") + 2:].split()
            if fields[0] in {"Z", "X"}:
                raise ValueError("dead")
            creation = fields[19]  # field 22, after pid and comm
            boot = _sha("/proc/sys/kernel/random/boot_id")
            image = hashlib.sha256(os.readlink(root / "exe").encode()).hexdigest()
            command = _sha(root / "cmdline")
            again = (root / "stat").read_text(encoding="utf-8")
            if again[again.rfind(")") + 2:].split()[19] != creation:
                raise ValueError("generation changed")
            return {"verified": True, "pid": pid, "creation_identity": creation,
                "boot_identity_sha256": boot, "image_identity_sha256": image,
                "command_identity_sha256": command, "measurement_kind": "LINUX_PROC_PROCESS"}
        if os.name == "nt":
            import ctypes as c
            from ctypes import wintypes as w
            kernel = c.WinDLL("kernel32", use_last_error=True)
            signatures = {
                "OpenProcess": ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
                "CloseHandle": ([w.HANDLE], w.BOOL),
                "WaitForSingleObject": ([w.HANDLE, w.DWORD], w.DWORD),
                "GetProcessTimes": ([w.HANDLE] + [c.POINTER(w.FILETIME)] * 4, w.BOOL),
                "QueryFullProcessImageNameW": ([w.HANDLE, w.DWORD, w.LPWSTR, c.POINTER(w.DWORD)], w.BOOL)}
            for name, (args, result) in signatures.items():
                fn = getattr(kernel, name)
                fn.argtypes, fn.restype = args, result
            handle = kernel.OpenProcess(0x1000 | 0x100000, False, pid)
            if not handle:
                raise OSError("query unavailable")
            try:
                values = [w.FILETIME() for _ in range(4)]
                buffer, length = c.create_unicode_buffer(32768), w.DWORD(32768)
                if (kernel.WaitForSingleObject(handle, 0) != 258 or
                        not kernel.GetProcessTimes(handle, *[c.byref(item) for item in values]) or
                        not kernel.QueryFullProcessImageNameW(handle, 0, buffer, c.byref(length))):
                    raise OSError("query unavailable")
                creation = str((values[0].dwHighDateTime << 32) | values[0].dwLowDateTime)
                return {"verified": True, "pid": pid, "creation_identity": creation,
                    "image_identity_sha256": hashlib.sha256(buffer.value.casefold().encode()).hexdigest(),
                    "measurement_kind": "WINDOWS_RETAINED_PROCESS_QUERY"}
            finally:
                kernel.CloseHandle(handle)
    except (OSError, ValueError, IndexError):
        pass
    return {"verified": False, "pid": pid, "code": "PROCESS_IDENTITY_UNAVAILABLE"}


def capture_current_process_identity():
    """Measure this process through /proc/self, including namespace identity.

    A mismounted proc tree must never turn a local PID into an unrelated host
    process. The self link, stat creation field, executable/command hashes and
    namespace PID must all agree with a second direct process query.
    """
    if not sys.platform.startswith("linux"):
        return capture_process_identity(os.getpid())
    try:
        root = Path("/proc/self")
        stat = (root / "stat").read_text(encoding="utf-8")
        pid = int(stat.split(" ", 1)[0])
        fields = stat[stat.rfind(")") + 2:].split()
        status = (root / "status").read_text(encoding="utf-8").splitlines()
        local = next((row.split()[1:] for row in status if row.startswith("NSpid:")), [])
        observed = capture_process_identity(pid)
        valid = (local and int(local[-1]) == os.getpid() and observed.get("verified") is True
            and observed["creation_identity"] == fields[19]
            and observed["image_identity_sha256"] == hashlib.sha256(os.readlink(root / "exe").encode()).hexdigest()
            and observed["command_identity_sha256"] == _sha(root / "cmdline"))
        if valid:
            return observed
    except (OSError, ValueError, KeyError, IndexError):
        pass
    return {"verified": False, "code": "CURRENT_PROCESS_IDENTITY_UNAVAILABLE"}


def _exact_native_method_bytes(cls, name):
    """Compare loaded method code to compilation of its exact public source.

    This compiles for byte identity only: it never executes a replacement core,
    extracts an AST, substitutes a method, or manufactures a fixture controller.
    Code equality checks constants/instructions/nested code; origin is checked
    separately because Python's code equality can ignore a filename.
    """
    path = Path(sys.modules[cls.__module__].__file__).resolve()
    loaded = getattr(cls, name).__code__
    if Path(loaded.co_filename).resolve() != path:
        return False
    module_code = compile(path.read_bytes(), str(path), "exec", dont_inherit=True)
    class_code = next((code for code in module_code.co_consts if isinstance(code, CodeType) and code.co_name == cls.__name__), None)
    if class_code is None:
        return False
    method_code = next((code for code in class_code.co_consts if isinstance(code, CodeType) and code.co_name == name), None)
    return method_code is not None and method_code == loaded and method_code.co_firstlineno == loaded.co_firstlineno


@contextmanager
def native_controller_observation(supervisor, *, source_pins, manifest_path, expected_specs):
    """Observe acquisition by one unchanged, public native Supervisor.run call.

    The short current-thread profile hook captures only a successful return of
    the exact pinned ProcessLease.__enter__ directly called by the exact native
    run code for this supervisor and controller.lock. It immediately restores
    the previous hook after acquisition; no replay work is profiled. The opaque
    registry keeps the actual native object/stream, never a caller 'held' flag.
    Querying after native exit finds its stream released and cannot prove health.
    This wrapper creates no lease, worker, authority, file, thread or watchdog.
    Use a fresh context for each inherited public run invocation.
    """
    prior_profile = sys.getprofile()
    try:
        pins = _pins(source_pins)
        required = _native_sources(supervisor)
        if any(path not in pins or _sha(path) != pins[path] for path in required):
            raise ValueError("changed source")
        native_class = next(cls for cls in type(supervisor).__mro__ if cls.__name__ == "AdaptiveWorkforceSupervisor")
        run_method = native_class.run
        lease_class = run_method.__globals__["ProcessLease"]
        lease_path = str(Path(sys.modules[lease_class.__module__].__file__).resolve())
        if (lease_class.__name__ != "ProcessLease" or lease_path not in pins or _sha(lease_path) != pins[lease_path]
                or Path(lease_class.__enter__.__code__.co_filename).resolve() != Path(lease_path)
                or Path(run_method.__code__.co_filename).resolve() != Path(sys.modules[native_class.__module__].__file__).resolve()
                or not _exact_native_method_bytes(lease_class, "__enter__") or not _exact_native_method_bytes(lease_class, "__exit__")
                or not _exact_native_method_bytes(native_class, "run")
                or Path(manifest_path).resolve() != supervisor.manifest_path.resolve()):
            raise ValueError("exact native code required")
        scope = native_scope_identity(supervisor, pins, manifest_path, expected_specs)
        current = capture_current_process_identity()
        if current.get("verified") is not True or id(supervisor) in _CONTROLLER_OBSERVATIONS:
            raise ValueError("bound current process required")
    except (OSError, ValueError, TypeError, AttributeError, KeyError, StopIteration, SyntaxError):
        raise ValueError("SOURCE_BOUND_NATIVE_OBSERVATION_REQUIRED") from None
    owner_thread = threading.get_ident()
    record = {"seal": _OBSERVATION_SEAL, "supervisor": supervisor, "scope_sha256": scope,
        "controller_identity": current, "owner_thread": owner_thread, "lease_class": lease_class,
        "lease": None, "stream": None, "acquired": False}
    _CONTROLLER_OBSERVATIONS[id(supervisor)] = record
    def profile(frame, event, arg):
        if prior_profile is not None:
            prior_profile(frame, event, arg)
        if event != "return" or frame.f_code is not lease_class.__enter__.__code__:
            return
        caller = frame.f_back
        lease = frame.f_locals.get("self")
        if (threading.get_ident() != owner_thread or caller is None or caller.f_code is not run_method.__code__
                or caller.f_locals.get("self") is not supervisor or type(lease) is not lease_class
                or arg is not lease or getattr(lease, "stream", None) is None
                or lease.path.resolve() != (supervisor.state_root / "controller.lock").resolve()):
            return
        stream = lease.stream
        if stream.closed:
            return
        record.update(lease=lease, stream=stream, fd=stream.fileno(), acquired=True)
        # No ongoing profiler cost or extra execution path during the workload.
        sys.setprofile(prior_profile)
    sys.setprofile(profile)
    try:
        yield
    finally:
        if sys.getprofile() is profile:
            sys.setprofile(prior_profile)
        _CONTROLLER_OBSERVATIONS.pop(id(supervisor), None)


def capture_bound_controller_lease(supervisor, scope_sha256):
    """Read the opaque source/scope-bound native acquired stream registration."""
    failure = {"verified": False, "source_bound_native_context": False,
        "measurement_kind": "SOURCE_BOUND_NATIVE_ACQUIRED_LEASE",
        "code": "SOURCE_BOUND_NATIVE_CONTROLLER_LEASE_UNAVAILABLE"}
    record = _CONTROLLER_OBSERVATIONS.get(id(supervisor))
    if (not record or record.get("seal") is not _OBSERVATION_SEAL or record.get("supervisor") is not supervisor
            or record.get("scope_sha256") != scope_sha256 or record.get("acquired") is not True):
        return failure
    try:
        lease, stream = record["lease"], record["stream"]
        path = (supervisor.state_root / "controller.lock").resolve()
        if (type(lease) is not record["lease_class"] or lease.stream is not stream or stream.closed
                or stream.fileno() != record["fd"] or lease.path.resolve() != path
                or not _same_process(record["controller_identity"], capture_current_process_identity())):
            return failure
        actual, expected = os.fstat(stream.fileno()), path.stat()
        if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
            return failure
        if os.name == "nt":
            import ctypes as c
            from ctypes import wintypes as w
            import msvcrt
            kernel = c.WinDLL("kernel32", use_last_error=True)
            api = kernel.GetFinalPathNameByHandleW
            api.argtypes, api.restype = [w.HANDLE, w.LPWSTR, w.DWORD, w.DWORD], w.DWORD
            buffer = c.create_unicode_buffer(32768)
            length = api(msvcrt.get_osfhandle(stream.fileno()), buffer, len(buffer), 0)
            if not 0 < length < len(buffer):
                return failure
            handle_path = buffer.value
            if handle_path.startswith("\\\\?\\UNC\\"):
                handle_path = "\\\\" + handle_path[8:]
            elif handle_path.startswith("\\\\?\\"):
                handle_path = handle_path[4:]
            if os.path.normcase(os.path.abspath(handle_path)) != os.path.normcase(os.path.abspath(path)):
                return failure
        return {"verified": True, "source_bound_native_context": True,
            "measurement_kind": "SOURCE_BOUND_NATIVE_ACQUIRED_LEASE", "controller_identity": record["controller_identity"],
            "scope_sha256": scope_sha256, "native_enter_return_observed": True, "stream_open": True,
            "file_identity_checked": True, "native_run_caller_checked": True, "code": None}
    except (OSError, ValueError, KeyError, AttributeError):
        return failure


def _same_process(expected, observed):
    if not isinstance(expected, Mapping) or not isinstance(observed, Mapping) or expected.get("verified") is not True or observed.get("verified") is not True:
        return False
    fields = ("pid", "creation_identity", "image_identity_sha256", "measurement_kind")
    if observed.get("measurement_kind") == "LINUX_PROC_PROCESS":
        fields += ("boot_identity_sha256", "command_identity_sha256")
    return all(expected.get(field) == observed.get(field) and observed.get(field) is not None for field in fields)


def capture_controller_lease(path, controller_identity):
    """Associate the existing Linux flock inode with its kernel owner PID.

    The native Windows byte-range lease exposes neither a retained handle nor
    owner identity. A conflict alone cannot attribute it; report unknown there.
    This API does not acquire a lock, create a file, or treat age as exit proof.
    """
    result = {"verified": False, "measurement_kind": "KERNEL_LOCK_OWNER_QUERY"}
    if not sys.platform.startswith("linux"):
        return {**result, "code": "CONTROLLER_LOCK_OWNER_UNAVAILABLE"}
    try:
        stat = Path(path).stat()
        key = (os.major(stat.st_dev), os.minor(stat.st_dev), stat.st_ino)
        owners = []
        for line in Path("/proc/locks").read_text(encoding="utf-8").splitlines():
            fields = line.split()
            if len(fields) < 8 or fields[1:4] != ["FLOCK", "ADVISORY", "WRITE"]:
                continue
            device = fields[5].split(":")
            if len(device) == 3 and (int(device[0], 16), int(device[1], 16), int(device[2])) == key:
                owners.append(int(fields[4]))
        pid = controller_identity.get("pid") if isinstance(controller_identity, Mapping) else None
        observed = capture_process_identity(pid)
        return {**result, "verified": owners == [pid] and _same_process(controller_identity, observed),
            "owner_pids": owners, "inode": stat.st_ino,
            "code": None if owners == [pid] and _same_process(controller_identity, observed) else "CONTROLLER_LOCK_OWNER_MISMATCH"}
    except (OSError, ValueError):
        return {**result, "code": "CONTROLLER_LOCK_OWNER_UNAVAILABLE"}


def capture_windows_job_health(jobs, *, controller_identity):
    """Query supplied already-retained native Windows Job handles, never assign.

    Read back CPU/memory/process hard limits, KILL_ON_JOB_CLOSE, active process
    count and controller membership. A boolean containment report is ignored.
    Passing multiple owned jobs fails the frozen max-one-job contract.
    """
    if not isinstance(jobs, (tuple, list)):
        return {"verified": False, "measurement_kind": "WINDOWS_QUERY_JOB_OBJECT", "owned_job_count": None,
            "kill_on_close": False, "code": "WINDOWS_JOB_MEASUREMENT_UNAVAILABLE"}
    result = {"verified": False, "measurement_kind": "WINDOWS_QUERY_JOB_OBJECT",
        "owned_job_count": len(jobs), "kill_on_close": False}
    if os.name != "nt" or len(jobs) != MAX_OWNED_WINDOWS_JOBS:
        return {**result, "code": "WINDOWS_JOB_MEASUREMENT_UNAVAILABLE"}
    import ctypes as c
    from ctypes import wintypes as w
    class Basic(c.Structure):
        _fields_ = [("process_time", c.c_longlong), ("job_time", c.c_longlong), ("flags", w.DWORD),
            ("min_ws", c.c_size_t), ("max_ws", c.c_size_t), ("processes", w.DWORD),
            ("affinity", c.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]
    class IO(c.Structure):
        _fields_ = [(name, c.c_ulonglong) for name in ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]
    class Extended(c.Structure):
        _fields_ = [("basic", Basic), ("io", IO)] + [(name, c.c_size_t) for name in ("process_memory", "job_memory", "peak_process", "peak_job")]
    class Rate(c.Structure):
        _fields_ = [("flags", w.DWORD), ("rate", w.DWORD)]
    try:
        kernel = c.WinDLL("kernel32", use_last_error=True)
        for name, args, returns in (
                ("QueryInformationJobObject", [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.c_void_p], w.BOOL),
                ("OpenProcess", [w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
                ("CloseHandle", [w.HANDLE], w.BOOL),
                ("IsProcessInJob", [w.HANDLE, w.HANDLE, c.POINTER(w.BOOL)], w.BOOL)):
            fn = getattr(kernel, name)
            fn.argtypes, fn.restype = args, returns
        job = jobs[0].handle
        if not job:
            raise ValueError("retained job required")
        limits, rate, accounting = Extended(), Rate(), (c.c_byte * 48)()
        for kind, value in ((9, limits), (15, rate), (1, accounting)):
            if not kernel.QueryInformationJobObject(job, kind, c.byref(value), c.sizeof(value), None):
                raise OSError("job query failed")
        process = kernel.OpenProcess(0x1000, False, controller_identity["pid"])
        if not process:
            raise OSError("process query failed")
        try:
            member = w.BOOL()
            if not kernel.IsProcessInJob(process, job, c.byref(member)):
                raise OSError("membership query failed")
        finally:
            kernel.CloseHandle(process)
        active = w.DWORD.from_buffer(accounting, 40).value
        result.update(cpu_hard_cap_percent=rate.rate / 100, ram_bytes=limits.job_memory,
            active_process_limit=limits.basic.processes, active_processes=active,
            kill_on_close=bool(limits.basic.flags & 0x2000), controller_in_job=bool(member.value))
        result["verified"] = (limits.basic.flags & (0x2000 | 0x200 | 0x8) == (0x2000 | 0x200 | 0x8)
            and rate.flags & 5 == 5 and 0 < rate.rate <= CPU_HARD_CAP_PERCENT * 100
            and 0 < limits.job_memory <= RAM_HARD_CAP_BYTES and limits.basic.processes == 1
            and active == 1 and bool(member.value)
            and _same_process(controller_identity, capture_process_identity(controller_identity["pid"])))
        result["code"] = None if result["verified"] else "WINDOWS_JOB_GUARD_MISMATCH"
    except (OSError, ValueError, AttributeError, KeyError, TypeError):
        result["code"] = "WINDOWS_JOB_MEASUREMENT_UNAVAILABLE"
    return result


def _native_sources(supervisor):
    classes = [type(supervisor.store), *type(supervisor).__mro__]
    result = set()
    for cls in classes:
        if cls is object:
            continue
        module = sys.modules.get(cls.__module__)
        if module is None or not getattr(module, "__file__", None):
            raise ValueError("NATIVE_SOURCE_MODULE_REQUIRED")
        result.add(str(Path(module.__file__).resolve()))
    store_module = sys.modules[type(supervisor.store).__module__]
    package = store_module.__name__.rsplit(".", 1)[0]
    for name, module in tuple(sys.modules.items()):
        if name.startswith(package + ".") and getattr(module, "__file__", "").endswith(".py"):
            result.add(str(Path(module.__file__).resolve()))
    if type(supervisor.store).__name__ != "WorkloadStore" or not any(cls.__name__ == "AdaptiveWorkforceSupervisor" for cls in classes):
        raise ValueError("ACTUAL_NATIVE_CONTROLLER_AND_STORE_REQUIRED")
    return result


def _resource_issues(resources, scope, identity, now):
    problems = []
    if (resources.get("scope_sha256") != scope or
            not _same_process(identity, resources.get("controller_identity", {})) or
            not _fresh(resources.get("observed_at"), now, RESOURCE_MAX_AGE_SECONDS)):
        problems.append("RESOURCE_MEASUREMENT_STALE_OR_FOREIGN")
    limits = resources.get("limits", {})
    exact = {"cpu_hard_cap_percent": CPU_HARD_CAP_PERCENT, "ram_bytes": RAM_HARD_CAP_BYTES,
        "workers": 1, "compute_workers": 1, "research_deadline_epoch": RESEARCH_DEADLINE_EPOCH,
        "closure_deadline_epoch": CLOSURE_DEADLINE_EPOCH, "output_bytes": 64 * 1024 ** 3,
        "free_disk_bytes": 10 * 1024 ** 3, "ram_reserve_fraction": .2, "ram_reserve_min_bytes": 4 * 1024 ** 3}
    if not isinstance(limits, Mapping) or any(type(limits.get(key)) is bool or limits.get(key) != value for key, value in exact.items()):
        problems.append("RESOURCE_CONTRACT_CHANGED")
    required = ("cpu_percent", "owned_tree_bytes", "campaign_output_bytes", "free_disk_bytes", "available_ram_bytes", "total_ram_bytes")
    if any(not _finite(resources.get(key)) or resources[key] < 0 for key in required) or resources.get("total_ram_bytes", 0) == 0:
        problems.append("RESOURCE_MEASUREMENT_INVALID")
        return problems
    for failed, code in (
            (resources["cpu_percent"] > CPU_HARD_CAP_PERCENT, "CPU_LIMIT"),
            (resources["owned_tree_bytes"] > RAM_HARD_CAP_BYTES, "RAM_LIMIT"),
            (resources.get("ac") is not True, "AC_POWER_REQUIRED"),
            (resources["campaign_output_bytes"] > exact["output_bytes"], "OUTPUT_LIMIT"),
            (resources["free_disk_bytes"] < exact["free_disk_bytes"], "DISK_FLOOR"),
            (resources["available_ram_bytes"] < max(exact["ram_reserve_min_bytes"], math.ceil(resources["total_ram_bytes"] * .2)), "RAM_RESERVE"),
            (now >= RESEARCH_DEADLINE_EPOCH, "RESEARCH_DEADLINE"),
            (now >= CLOSURE_DEADLINE_EPOCH, "CLOSURE_DEADLINE")):
        if failed:
            problems.append(code)
    return problems


def inspect_native_health(supervisor, *, source_pins, manifest_path, expected_specs,
                          resources, now=None, controller_identity=None, monitoring=None,
                          previous=None, engineering=False):
    """Measure an existing native session without changing its admission/dispatch.

    resources carries the fresh source/scope/process-bound native sample and
    its frozen limits. Optional resources['windows_jobs'] holds existing Job
    objects solely for direct kernel query. The returned record contains no
    handles, command lines, raw input data, exception strings or credentials.
    A previous record is needed to prove receipt growth/preservation; a single
    snapshot cannot demonstrate progress or successful recovery.
    """
    now = time.time() if now is None else now
    if not _finite(now):
        raise ValueError("FINITE_HEALTH_SAMPLE_TIME_REQUIRED")
    criteria, blockers = {}, []
    def criterion(name, passed, codes=(), **evidence):
        codes = list(dict.fromkeys(codes))
        criteria[name] = {"passed": bool(passed), "codes": codes, **evidence}
        if not passed:
            blockers.extend(codes)
    scope = None
    try:
        pins = _pins(source_pins)
        required = _native_sources(supervisor)
        changed = [path for path, pin in pins.items() if not isinstance(pin, str) or _sha(path) != pin]
        missing = sorted(required - pins.keys())
        criterion("source_binding", bool(pins) and not changed and not missing,
            ["NATIVE_SOURCE_BINDING_CHANGED"] if changed or missing or not pins else (),
            required_native_source_count=len(required), missing_source_count=len(missing), changed_source_count=len(changed))
        scope = native_scope_identity(supervisor, pins, manifest_path, expected_specs)
        captured = {}
        for cls in [type(supervisor.store), *type(supervisor).__mro__]:
            if cls is object:
                continue
            module = sys.modules[cls.__module__]
            captured_source = getattr(module, "_LOADED_SOURCE_SHA", None)
            if captured_source:
                captured[str(Path(module.__file__).resolve())] = captured_source
        package = type(supervisor.store).__module__.rsplit(".", 1)[0]
        source_capture = sys.modules.get(package + ".source_identity")
        captured.update(getattr(source_capture, "CAPTURED", {}))
        loaded_ok = all(captured.get(path) == pins.get(path) for path in required)
        criterion("loaded_source_binding", loaded_ok, [] if loaded_ok else ["COMPILED_NATIVE_SOURCE_IDENTITY_UNVERIFIED"],
            compiled_native_source_count=sum(captured.get(path) == pins.get(path) for path in required))
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        criterion("source_binding", False, ["NATIVE_SOURCE_BINDING_UNVERIFIABLE"])
    result = {"schema": "AIOS_NATIVE_FACTORY_OPERATIONAL_HEALTH_V1", "observed_at": now,
        "scope_sha256": scope, "engineering_only": bool(engineering), "execution_allowed": False,
        "operational_health_observed": False, "restart_without_replay_observed": False,
        "receipt_growth_observed": False, "criteria": criteria, "blockers": blockers,
        "receipt_fingerprints": {}, "accepted_attempt_fingerprints": {}, "uncertain_unit_ids": [],
        "accepted_receipts": 0, "pending_units": 0, "running_units": 0, "new_market_calls": 0}
    # Select on the already-open core in one read snapshot. Never call repair,
    # bootstrap, reconcile, reclaim, status/run, or another database connection.
    try:
        store = supervisor.store
        with store._db_lock:
            if store.conn.in_transaction:
                raise ValueError("native transaction in progress")
            store.conn.execute("BEGIN")
            try:
                runs = [dict(row) for row in store.conn.execute("SELECT * FROM runs")]
                units = [dict(row) for row in store.conn.execute("SELECT * FROM units WHERE run_id=?", (supervisor.run_id,))]
                receipts = [dict(row) for row in store.conn.execute("SELECT * FROM receipts WHERE run_id=?", (supervisor.run_id,))]
                attempts = [dict(row) for row in store.conn.execute(
                    "SELECT a.* FROM attempts a JOIN units u ON a.unit_id=u.unit_id WHERE u.run_id=?", (supervisor.run_id,))]
                counters = dict(store.conn.execute("SELECT status,count FROM unit_totals WHERE run_id=?", (supervisor.run_id,)))
                databases = [tuple(row) for row in store.conn.execute("PRAGMA database_list")]
                execution_binding = store.conn.execute("SELECT fingerprint FROM execution_binding WHERE run_id=?", (supervisor.run_id,)).fetchone()
            finally:
                store.conn.rollback()
        manifest = supervisor.manifest
        canonical = manifest.canonical_id()
        manifest_bytes = json.loads(Path(manifest_path).read_bytes())
        disk_manifest = type(manifest).from_dict(manifest_bytes)
        fixture = any(spec.get("fixture_only") is True for spec in expected_specs) or "FIXTURE" in str(manifest_bytes.get("owner_authority", ""))
        result["engineering_only"] = bool(engineering or fixture)
        stages = {spec["candidate_id"] for spec in expected_specs}
        actual_stages = {stage.stage_id for stage in manifest.stages}
        counts = Counter(row["status"] for row in units)
        run = next((row for row in runs if row["run_id"] == supervisor.run_id), {})
        expected_members = {(hashlib.sha256(f"{manifest.workload_id}|{stage.stage_id}|{shard.shard_id}|{i}|{canonical}".encode()).hexdigest(), stage.stage_id, shard.shard_id)
            for stage in manifest.stages for i, shard in enumerate(manifest.inputs)}
        actual_members = {(row["unit_id"], row["stage_id"], row["shard_id"]) for row in units}
        scope_issues = []
        if stages != actual_stages or len(stages) != len(expected_specs):
            scope_issues.append("NATIVE_STAGE_SCOPE_MISMATCH")
        if (Path(manifest_path).resolve() != supervisor.manifest_path.resolve() or
                store.run_id != supervisor.run_id or Path(store.state_root).resolve() != supervisor.state_root.resolve() or
                run.get("manifest_hash") != canonical or run.get("workload_fingerprint") != canonical or
                disk_manifest.canonical_id() != canonical or disk_manifest.execution_fingerprint() != manifest.execution_fingerprint() or
                not execution_binding or execution_binding[0] != manifest.execution_fingerprint() or
                Path(store.sqlite_path).resolve() != (supervisor.state_root / "state.db").resolve() or
                not any(row[1] == "main" and Path(row[2]).resolve() == Path(store.sqlite_path).resolve() for row in databases) or
                run.get("workload_id") != manifest.workload_id or len(runs) != 1 or actual_members != expected_members or
                run.get("expected") != len(expected_members) or
                {key: value for key, value in counters.items() if value} != dict(counts)):
            scope_issues.append("NATIVE_RUN_SCOPE_MISMATCH")
        if not result["engineering_only"] and getattr(supervisor, "deadline", None) != RESEARCH_DEADLINE_EPOCH:
            scope_issues.append("NATIVE_DEADLINE_CHANGED")
        criterion("scope_binding", not scope_issues, scope_issues, run_id=supervisor.run_id,
            expected_units=len(expected_members), observed_units=len(units))
        result.update(pending_units=counts["PENDING"] + counts["RETRY_READY"], running_units=counts["RUNNING"],
            native_state=run.get("state"), native_mode=run.get("mode"))
    except (OSError, ValueError, KeyError, AttributeError, TypeError, sqlite3.Error):
        criterion("scope_binding", False, ["NATIVE_STATE_UNVERIFIABLE"])
        result["status"] = "UNHEALTHY"
        return result
    registered = capture_bound_controller_lease(supervisor, scope)
    if controller_identity is None and registered.get("verified") is True:
        controller_identity = registered["controller_identity"]
    observed_process = capture_process_identity(controller_identity.get("pid") if isinstance(controller_identity, Mapping) else None)
    process_ok = _same_process(controller_identity, observed_process)
    result["controller_identity"] = observed_process
    criterion("process_identity", process_ok, [] if process_ok else ["CONTROLLER_PROCESS_UNVERIFIED"], process=observed_process)
    lease = capture_controller_lease(supervisor.state_root / "controller.lock", controller_identity)
    if registered.get("verified") is True and _same_process(controller_identity, registered["controller_identity"]):
        if os.name == "nt":
            lease = registered
        else:
            lease = {**lease, "source_bound_native_context": True, "controller_identity": registered["controller_identity"],
                "native_enter_return_observed": True, "file_identity_checked": True, "native_run_caller_checked": True}
    criterion("controller_lease", lease["verified"], [] if lease["verified"] else [lease["code"]], measurement=lease)
    lease_issues, uncertain = [], []
    for unit in units:
        if unit["status"] == "RUNNING":
            lease_valid = (_finite(unit.get("lease_expires_at")) and unit["lease_expires_at"] > now and
                bool(unit.get("lease_token")) and unit.get("lease_generation", 0) > 0 and
                str(unit.get("lease_owner", "")).startswith(supervisor.controller_id + ":"))
            if not lease_valid:
                lease_issues.append("EXPIRED_JOB_LEASE" if _finite(unit.get("lease_expires_at")) and unit["lease_expires_at"] <= now else "JOB_LEASE_SCOPE_MISMATCH")
            if not lease_valid or not process_ok or not lease["verified"]:
                uncertain.append(unit["unit_id"])
        elif unit["status"] == "RETRY_READY" and unit.get("lease_generation", 0) > 0:
            uncertain.append(unit["unit_id"])
    if uncertain:
        lease_issues.append("UNCERTAIN_MARKET_ATTEMPT_REQUIRES_CLASSIFICATION")
    result["uncertain_unit_ids"] = sorted(uncertain)
    criterion("job_leases", not lease_issues, lease_issues, running_units=counts["RUNNING"], uncertain_units=len(uncertain))
    by_unit = {row["unit_id"]: row for row in units}
    by_attempt = {row["attempt_id"]: row for row in attempts}
    accepted = [row for row in receipts if row["status"] == "ACCEPTED"]
    receipt_issues = []
    per_unit = Counter(row["unit_id"] for row in accepted)
    for receipt in accepted:
        unit, attempt = by_unit.get(receipt["unit_id"], {}), by_attempt.get(receipt["attempt_id"], {})
        try:
            path = Path(receipt["output_path"])
            output_root = Path(manifest.work_root or supervisor.state_root).resolve()
            valid = (per_unit[receipt["unit_id"]] == 1 and unit.get("status") == "COMPLETED" and attempt.get("status") == "SUCCESS"
                and attempt.get("unit_id") == receipt["unit_id"] and receipt["run_id"] == supervisor.run_id
                and all(receipt[field] == attempt.get(field) for field in ("worker_token", "output_hash", "lease_generation"))
                and receipt["output_hash"] == unit.get("output_hash") and receipt["lease_generation"] == unit.get("lease_generation")
                and path.resolve() == Path(unit["output_path"]).resolve() == Path(unit["output_path_published"]).resolve()
                and path.resolve().is_relative_to(output_root) and not path.is_symlink() and _sha(path) == receipt["output_hash"])
            if not valid:
                receipt_issues.append("NATIVE_RECEIPT_OUTPUT_INTEGRITY")
            result["receipt_fingerprints"][receipt["receipt_id"]] = _digest(receipt)
            result["accepted_attempt_fingerprints"][receipt["unit_id"]] = _digest(sorted(
                [_digest(row) for row in attempts if row["unit_id"] == receipt["unit_id"]]))
        except (OSError, KeyError, TypeError, ValueError):
            receipt_issues.append("NATIVE_RECEIPT_OUTPUT_INTEGRITY")
    if len(accepted) != counts["COMPLETED"] or len(receipts) != len(accepted):
        receipt_issues.append("NATIVE_RECEIPT_COMPLETION_MISMATCH")
    result["accepted_receipts"] = len(accepted)
    criterion("native_receipts", not receipt_issues, receipt_issues, accepted=len(accepted), completed=counts["COMPLETED"])
    previous_ok = (isinstance(previous, Mapping) and previous.get("schema") == result["schema"] and previous.get("scope_sha256") == scope and
        _finite(previous.get("observed_at")) and previous["observed_at"] <= now and
        isinstance(previous.get("receipt_fingerprints"), Mapping) and isinstance(previous.get("accepted_attempt_fingerprints"), Mapping)
        and previous.get("accepted_receipts") == len(previous["receipt_fingerprints"])
        and isinstance(previous.get("criteria"), Mapping)
        and isinstance(previous["criteria"].get("scope_binding"), Mapping)
        and previous["criteria"]["scope_binding"].get("passed") is True
        and isinstance(previous["criteria"].get("source_binding"), Mapping)
        and previous["criteria"]["source_binding"].get("passed") is True)
    monotonic = previous_ok and all(result["receipt_fingerprints"].get(key) == value for key, value in previous["receipt_fingerprints"].items())
    no_replay = previous_ok and all(result["accepted_attempt_fingerprints"].get(key) == value for key, value in previous["accepted_attempt_fingerprints"].items())
    criterion("receipt_monotonicity", monotonic, [] if monotonic else ["ACCEPTED_RECEIPT_CHANGED_OR_BASELINE_MISSING"])
    criterion("accepted_no_replay", no_replay, [] if no_replay else ["ACCEPTED_UNIT_REPLAYED_OR_BASELINE_MISSING"])
    new_receipts = [row for row in accepted if previous_ok and row["receipt_id"] not in previous["receipt_fingerprints"]]
    growth = monotonic and bool(new_receipts) and all(_finite(row.get("created_at"))
        and previous["observed_at"] - FUTURE_TOLERANCE_SECONDS <= row["created_at"] <= now + FUTURE_TOLERANCE_SECONDS for row in new_receipts)
    result["receipt_growth_observed"] = bool(growth)
    criterion("accepted_receipt_growth", growth, [] if growth else ["ACCEPTED_RECEIPT_GROWTH_NOT_OBSERVED"])
    monitoring = monitoring if isinstance(monitoring, Mapping) else {}
    monitor_ok = (monitoring.get("scope_sha256") == scope and _same_process(controller_identity, monitoring.get("controller_identity", {}))
        and monitoring.get("source_pins_checked") is True
        and all(_fresh(monitoring.get(field), now, maximum) for field, maximum in
            (("heartbeat_at", HEARTBEAT_MAX_AGE_SECONDS), ("metadata_saved_at", HEARTBEAT_MAX_AGE_SECONDS), ("useful_progress_at", PROGRESS_MAX_AGE_SECONDS))))
    criterion("monitoring_freshness", monitor_ok, [] if monitor_ok else ["MONITORING_STALE_STALLED_OR_FOREIGN"])
    resources = resources if isinstance(resources, Mapping) else {}
    resource_issues = _resource_issues(resources, scope, controller_identity, now)
    criterion("resource_guards", not resource_issues, resource_issues)
    containment = capture_windows_job_health(resources.get("windows_jobs", ()), controller_identity=controller_identity)
    criterion("containment", containment["verified"], [] if containment["verified"] else [containment["code"]], measurement=containment)
    kill_ok = (containment["verified"] and containment["kill_on_close"] and
        callable(getattr(supervisor, "stop", None)) and callable(getattr(store, "request_drain", None)))
    criterion("kill_guard", kill_ok, [] if kill_ok else ["KERNEL_KILL_AND_NATIVE_STOP_GUARD_UNVERIFIED"])
    saved_stop = getattr(supervisor, "stop_reason", None)
    try:
        if supervisor.state_file.is_file():
            saved = json.loads(supervisor.state_file.read_bytes())
            saved_stop = saved.get("stop_reason") or saved_stop
    except (OSError, ValueError, AttributeError):
        saved_stop = {"class": "SAFETY_INTEGRITY_BLOCK"}
    integrity_stop = run.get("mode") in {"SAFETY_STOP", "BLOCKED_INTEGRITY"} or isinstance(saved_stop, Mapping) and saved_stop.get("class") == "SAFETY_INTEGRITY_BLOCK"
    criterion("persisted_stop", not integrity_stop, ["PERSISTED_INTEGRITY_STOP_REQUIRES_REVIEW"] if integrity_stop else [])
    active = counts["RUNNING"] > 0 and run.get("state") == "RUNNING" and process_ok and lease["verified"]
    criterion("active_native_work", active, [] if active else ["NO_ACTIVE_NATIVE_RESEARCH_WORK"])
    result["restart_without_replay_observed"] = bool(previous_ok and monotonic and no_replay and not uncertain
        and not integrity_stop and counts["RUNNING"] == 0 and run.get("state") == "COMPLETE"
        and previous.get("native_state") == "RUNNING" and previous.get("running_units", 0) > 0
        and previous.get("criteria", {}).get("process_identity", {}).get("passed") is True
        and previous.get("criteria", {}).get("controller_lease", {}).get("passed") is True
        and not _same_process(previous.get("controller_identity"), observed_process))
    result["blockers"] = sorted(set(blockers))
    result["operational_health_observed"] = not result["engineering_only"] and all(row["passed"] for row in criteria.values())
    result["status"] = "HEALTHY_OBSERVED" if result["operational_health_observed"] else "ENGINEERING_MEASUREMENT_ONLY" if result["engineering_only"] else "UNHEALTHY_OR_UNPROVEN"
    return result
