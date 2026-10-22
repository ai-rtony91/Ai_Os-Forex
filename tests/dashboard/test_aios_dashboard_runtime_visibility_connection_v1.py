from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "apps" / "dashboard" / "server.js"
DASHBOARD = ROOT / "apps" / "dashboard" / "src" / "MinimalOperatorDashboard.jsx"
HOOK = ROOT / "apps" / "dashboard" / "src" / "hooks" / "useRuntimeVisibility.js"
CLIENT = ROOT / "apps" / "dashboard" / "src" / "runtimeVisibilityClient.js"
ADAPTER = ROOT / "apps" / "dashboard" / "src" / "runtimeVisibilityAdapter.js"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_dashboard_server_exposes_read_only_runtime_visibility_route():
    source = read(SERVER)
    assert "/api/runtime/visibility" in source
    assert "getVisibilitySnapshot" in source
    assert "READ_ONLY" in source
    assert "cache-control" in source
    assert "Runtime visibility unavailable" in source


def test_active_react_dashboard_consumes_canonical_runtime_visibility_hook():
    source = read(DASHBOARD)
    assert "useRuntimeVisibility" in source
    assert "data-runtime-state" in source
    assert "runtimeVisibility={runtimeVisibility}" in source
    assert "<span>Runtime</span>" in source


def test_runtime_hook_reuses_existing_client_and_adapter():
    hook = read(HOOK)
    client = read(CLIENT)
    adapter = read(ADAPTER)
    assert "fetchRuntimeVisibilityReadOnly" in hook
    assert "mapRuntimeVisibilityDisplayModel" in hook
    assert "aios.runtime_visibility_api.v1" in client
    assert "LOCAL_API_READ_ONLY" in adapter


def test_forex_surface_remains_display_only_and_broker_locked():
    source = read(DASHBOARD)
    assert "Display only" in source
    assert "Execution off" in source
    assert "Broker" in source
    assert "Locked" in source
    forbidden_controls = ("Place order", "Submit order", "Execute trade", "Buy now", "Sell now")
    for control in forbidden_controls:
        assert control not in source
