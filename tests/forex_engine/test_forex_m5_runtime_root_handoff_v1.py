from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from automation.forex_engine import forex_p1_practice_paper_campaign_runtime_v1 as runtime


REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER_PATH = REPO_ROOT / "scripts/forex_delivery/run_forex_p1_supervised_paper_campaign_v1.py"
SPEC = importlib.util.spec_from_file_location("m5_runtime_root_launcher", LAUNCHER_PATH)
assert SPEC and SPEC.loader
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


def _approved_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "approved" / "forex_p1_supertrend_paper_sessions"
    root.mkdir(parents=True)
    monkeypatch.setattr(runtime, "APPROVED_EXTERNAL_M5_RUNTIME_ROOT", root)
    return root


def test_default_m5_runtime_paths_remain_checkout_local(tmp_path: Path):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    paths = runtime.resolve_m5_runtime_paths(checkout_root=checkout)
    assert paths.mode == "CHECKOUT_LOCAL"
    assert paths.root == checkout / runtime.M5_RUNTIME_ROOT_RELATIVE_PATH
    active, lock, selected = launcher.runtime_paths_for_signal_source(
        runtime.SUPERTREND_SIGNAL_SOURCE, checkout_root=checkout
    )
    assert (active, lock, selected) == (paths.active_session, paths.lock, paths)


def test_exact_approved_external_root_keeps_all_m5_artifacts_coherent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
):
    approved = _approved_root(monkeypatch, tmp_path)
    checkout = tmp_path / "clean-checkout"
    checkout.mkdir()
    paths = runtime.resolve_m5_runtime_paths(
        checkout_root=checkout, external_runtime_root=approved
    )
    assert paths.mode == "APPROVED_EXTERNAL"
    assert paths.root == approved.resolve()
    assert all(path.parent == paths.root for path in (
        paths.active_session, paths.lock, paths.heartbeat,
        paths.campaign_projection, paths.telemetry, paths.recovery_receipt,
    ))
    active, lock, selected = launcher.runtime_paths_for_signal_source(
        runtime.SUPERTREND_SIGNAL_SOURCE,
        checkout_root=checkout,
        external_m5_runtime_root=approved,
    )
    assert selected == paths
    assert active == paths.active_session
    assert lock == paths.lock
    assert paths.root != checkout / runtime.M5_RUNTIME_ROOT_RELATIVE_PATH
    campaign_paths = launcher.campaign_paths_for_signal_source(
        runtime.SUPERTREND_SIGNAL_SOURCE,
        paths.root,
    )
    assert campaign_paths.campaign_state == paths.campaign_projection


def test_missing_allowlisted_external_root_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
):
    missing = tmp_path / "missing-approved-root"
    monkeypatch.setattr(runtime, "APPROVED_EXTERNAL_M5_RUNTIME_ROOT", missing)
    with pytest.raises(ValueError, match="missing"):
        runtime.resolve_m5_runtime_paths(
            checkout_root=tmp_path,
            external_runtime_root=missing,
        )


@pytest.mark.parametrize(
    "candidate, error",
    [
        (Path("relative"), "must_be_absolute"),
        (Path("C:/missing/runtime"), "not_allowlisted"),
        (Path("C:/Dev/Ai.Os"), "not_allowlisted"),
        (Path("C:/Dev/Ai.Os/.aios/runtime"), "not_allowlisted"),
        (Path("C:/Dev/Ai.Os/.aios/runtime/forex_persistent_all_pairs_m1_m2_observer_v1"), "not_allowlisted"),
    ],
)
def test_disallowed_external_runtime_roots_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, candidate: Path, error: str,
):
    approved = _approved_root(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match=error):
        runtime.resolve_m5_runtime_paths(
            checkout_root=tmp_path, external_runtime_root=candidate
        )
    assert approved.exists()


def test_path_traversal_and_symlink_escape_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
):
    approved = _approved_root(monkeypatch, tmp_path)
    traversal = approved.parent / ".." / approved.parent.name / approved.name
    with pytest.raises(ValueError, match="path_traversal_forbidden"):
        runtime.resolve_m5_runtime_paths(
            checkout_root=tmp_path, external_runtime_root=traversal
        )
    escaped = tmp_path / "escaped"
    escaped.mkdir(exist_ok=True)
    original_normalized = runtime._normalized_path_text
    original_resolve = Path.resolve
    monkeypatch.setattr(
        runtime,
        "_normalized_path_text",
        lambda path: original_normalized(approved) if path in {escaped, approved} else original_normalized(path),
    )
    monkeypatch.setattr(
        Path,
        "resolve",
        lambda self, *args, **kwargs: (approved.parent if self == escaped else original_resolve(self, *args, **kwargs)),
    )
    with pytest.raises(ValueError, match="symlink_escape"):
        runtime.resolve_m5_runtime_paths(
            checkout_root=tmp_path, external_runtime_root=escaped
        )


def test_non_supertrend_external_root_is_rejected_before_runtime_construction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
):
    approved = _approved_root(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="requires_supertrend"):
        launcher.runtime_paths_for_signal_source(
            runtime.SPRINT_4_SIGNAL_SOURCE,
            checkout_root=tmp_path,
            external_m5_runtime_root=approved,
        )
