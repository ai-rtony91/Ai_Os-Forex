"""Local pytest fixtures for service-level tests.

This subtree is not covered by the repository-level tests/conftest.py, so we
mirror the workspace-safe tmp_path behavior here to avoid the default pytest
temp root on this machine.
"""
from __future__ import annotations

import secrets
import shutil
import tempfile
from pathlib import Path

import pytest


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
