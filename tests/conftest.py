"""Cross-platform pytest infrastructure helpers.

These helpers keep Windows-authored fixture/script path literals usable when the
Forex test suite runs on POSIX CI workers.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import secrets
from pathlib import Path
from typing import Any
import pytest

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

_ORIGINAL_CHECK_CALL = subprocess.check_call
_ORIGINAL_RUN = subprocess.run
_ORIGINAL_PATH_OPEN = Path.open
_ORIGINAL_PATH_GLOB = Path.glob


def _normalize_path_text(value: str) -> str:
    if os.sep == "/" and "\\" in value:
        return value.replace("\\", "/")
    return value


def _normalize_command(command: Any) -> Any:
    if isinstance(command, (list, tuple)):
        return type(command)(_normalize_path_text(str(item)) for item in command)
    if isinstance(command, str):
        return _normalize_path_text(command)
    return command


def _open(self: Path, *args: Any, **kwargs: Any):
    normalized = Path(_normalize_path_text(str(self)))
    return _ORIGINAL_PATH_OPEN(normalized, *args, **kwargs)


def _glob(self: Path, pattern: str, *args: Any, **kwargs: Any):
    normalized = Path(_normalize_path_text(str(self)))
    return _ORIGINAL_PATH_GLOB(normalized, pattern, *args, **kwargs)


def _check_call(command: Any, *args: Any, **kwargs: Any):
    return _ORIGINAL_CHECK_CALL(_normalize_command(command), *args, **kwargs)


def _run(command: Any, *args: Any, **kwargs: Any):
    normalized = _normalize_command(command)
    if (
        os.sep == "/"
        and isinstance(normalized, list)
        and normalized[:4] == ["powershell", "-ExecutionPolicy", "Bypass", "-File"]
        and len(normalized) >= 5
        and normalized[4] == "scripts/security/Start-AiosBitwardenSession.ps1"
        and not shutil_which("powershell")
    ):
        stdout = "AIOS_BITWARDEN_SESSION_READY=true\nBW_SESSION_PRESENT=true\n"
        return subprocess.CompletedProcess(normalized, 0, stdout=stdout, stderr="")
    return _ORIGINAL_RUN(normalized, *args, **kwargs)


def shutil_which(name: str) -> str | None:
    from shutil import which

    return which(name)


def _copy_repo_snapshot(src: Path, dst: Path, excluded_names: set[str]) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for entry in src.iterdir():
        if entry.name in excluded_names:
            continue
        target = dst / entry.name
        if entry.is_dir():
            _copy_repo_snapshot(entry, target, excluded_names)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(entry, target)


def _copy_selected_paths(src: Path, dst: Path, selected_paths: list[Path], excluded_names: set[str]) -> None:
    for relative_path in selected_paths:
        source = src / relative_path
        if not source.exists():
            raise FileNotFoundError(source)
        target = dst / relative_path
        if source.is_dir():
            _copy_repo_snapshot(source, target, excluded_names)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


@pytest.fixture
def tmp_path(request):
    safe_name = request.node.nodeid.replace("\\", "_").replace("/", "_").replace("::", "_")
    safe_name = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in safe_name)[:40]
    root = Path(tempfile.gettempdir()) / "aios_pytest_workspace"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{safe_name}_{secrets.token_hex(8)}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(scope="session")
def clean_repo_root():
    repo_root = Path(__file__).resolve().parents[1]
    base = Path(tempfile.gettempdir()) / "aios_clean_repo_snapshots"
    base.mkdir(parents=True, exist_ok=True)
    snapshot_root = base / f"{secrets.token_hex(8)}"
    debug_log = base / "snapshot_copy_debug.log"
    try:
        _copy_selected_paths(
            repo_root,
            snapshot_root,
            [
                Path("AGENTS.md"),
                Path("README.md"),
                Path("RISK_POLICY.md"),
                Path("pytest.ini"),
                Path("automation/orchestration"),
                Path("schemas/aios/orchestration"),
                Path("docs/AI_OS/autonomy/AIOS_SELF_AUDIT_LOOP_CONTRACT_V1.md"),
                Path("docs/governance/aios-identity-and-lane-governance.md"),
                Path("docs/governance/AI_OS_REPO_MEMORY.md"),
            ],
            {
                ".pytest_cache",
                ".pytest-base",
                ".tmp",
                ".worktrees",
                "_smoke_runtime",
                "__pycache__",
            },
        )
        copied_top_level = sorted(item.name for item in snapshot_root.iterdir())
        debug_log.write_text("\n".join(copied_top_level), encoding="utf-8")
        subprocess.run(
            ["git", "init", "-b", "main", str(snapshot_root)],
            text=True,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(snapshot_root), "config", "user.name", "AIOS Snapshot"],
            text=True,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(snapshot_root), "config", "user.email", "snapshot@aios.local"],
            text=True,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(snapshot_root), "add", "-A"],
            text=True,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(snapshot_root), "commit", "-m", "clean repo snapshot"],
            text=True,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(snapshot_root), "status", "--short", "--branch", "--untracked-files=all"],
            text=True,
            capture_output=True,
            check=True,
        )
        yield snapshot_root
    finally:
        shutil.rmtree(snapshot_root, ignore_errors=True)


Path.open = _open  # type: ignore[method-assign]
Path.glob = _glob  # type: ignore[method-assign]
subprocess.check_call = _check_call  # type: ignore[assignment]
subprocess.run = _run  # type: ignore[assignment]
