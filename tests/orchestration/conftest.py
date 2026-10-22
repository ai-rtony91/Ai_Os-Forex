from __future__ import annotations

import shutil
from pathlib import Path

import pytest


POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")
POWERSHELL_MARKERS = ("powershell", "pwsh", ".ps1")


def pytest_collection_modifyitems(config, items):
    if POWERSHELL is not None:
        return

    skip_powershell = pytest.mark.skip(
        reason="PowerShell-dependent orchestration test requires pwsh or Windows PowerShell on PATH."
    )
    for item in items:
        try:
            source = Path(str(item.fspath)).read_text(encoding="utf-8").lower()
        except OSError:
            continue
        if any(marker in source for marker in POWERSHELL_MARKERS):
            item.add_marker(skip_powershell)
