"""Process-local path ownership, held outside the existing OS file lock."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
from threading import Lock
from typing import Iterator
from weakref import WeakValueDictionary


class ProcessPathBusy(RuntimeError):
    """Another entry in this process already owns the resolved path."""


_registry_guard = Lock()
_path_locks: WeakValueDictionary = WeakValueDictionary()


def _after_fork_child() -> None:
    # A child must not inherit a mutex held by a thread that no longer exists.
    global _registry_guard, _path_locks
    _registry_guard = Lock()
    _path_locks = WeakValueDictionary()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork_child)


@contextmanager
def process_path_lock(path: Path) -> Iterator[None]:
    key = os.path.normcase(str(path.resolve(strict=False)))
    with _registry_guard:
        guard = _path_locks.get(key)
        if guard is None:
            guard = Lock()
            _path_locks[key] = guard
    # Non-reentrant: nested use is a second owner, even on the same thread.
    if not guard.acquire(blocking=False):
        raise ProcessPathBusy("path already owned in this process")
    try:
        yield
    finally:
        guard.release()
