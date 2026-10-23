"""Selected cycle preview cannot write, notify, or turn a value into authority."""
import builtins
import json
import os
from pathlib import Path

import pytest

from services.python_supervisor import notifier


class Untouchable:
    def __bool__(self):
        raise AssertionError("Boolean conversion is forbidden")

    def __fspath__(self):
        raise AssertionError("The preview must not touch its root")

    def get(self, *args, **kwargs):
        raise AssertionError("Invalid apply choice must be refused before reading state")


@pytest.mark.parametrize("apply", [True, 0, 1, None, "", "false", [], {}, Untouchable()])
def test_preview_rejects_every_apply_choice_except_real_false(apply):
    def forbidden(*args, **kwargs):
        raise AssertionError("A preview cannot call an effect callback")

    with pytest.raises(ValueError, match="PREVIEW_APPLY_FORBIDDEN"):
        notifier.notify_file(Untouchable(), Untouchable(), apply=apply,
            read_receipt=forbidden, save_receipt=forbidden, dispatch=forbidden, lock=forbidden)


@pytest.mark.parametrize("status,expected", [
    ("BLOCKED", "DRY_RUN_WOULD_NOTIFY"),
    ("NEEDS_APPROVAL", "DISPLAY_ALERT_ONLY"),
    ("READY", "NO_BLOCKER"),
    ("UNKNOWN", "NO_BLOCKER"),
])
@pytest.mark.parametrize("explicit", [False, True])
def test_preview_has_no_io_callbacks_or_state_changes(monkeypatch, status, expected, explicit):
    state = {"status": status, "plain_summary": "test-owned event"}
    before = json.dumps(state, sort_keys=True)
    calls = []

    def forbidden(*args, **kwargs):
        calls.append("forbidden effect")
        raise AssertionError("Preview attempted a file, process, or callback effect")

    options = dict(read_receipt=forbidden, save_receipt=forbidden, dispatch=forbidden, lock=forbidden)
    if explicit:
        options["apply"] = False
    with monkeypatch.context() as patch:
        for name in ("open", "read_bytes", "read_text", "write_bytes", "write_text", "mkdir", "rename", "replace"):
            patch.setattr(Path, name, forbidden)
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(os, "open", forbidden)
        patch.setattr(notifier.subprocess, "run", forbidden)
        patch.setattr(notifier, "write_file_channel", forbidden)
        result = notifier.notify_file(Untouchable(), state, **options)
    assert result == {"status": expected, "delivery_accepted": False}
    assert calls == [] and json.dumps(state, sort_keys=True) == before


@pytest.mark.parametrize("status,wake,display", [
    ("READY", "NO_WAKE", False), ("UNKNOWN", "NO_WAKE", False),
    ("NEEDS_APPROVAL", "REVIEW_ONLY", True), ("BLOCKED", "SOS", True),
])
def test_existing_plain_status_and_key_behavior_is_preserved(status, wake, display):
    state = {"status": status, "generated_at": "2026-10-22", "plain_summary": "same text"}
    assert notifier.status_from_state(state) == status
    assert notifier.wake_class(status) == wake
    assert notifier.display_alert_required(status) is display
    assert notifier.notification_key(state) == status + "|2026-10-22|same text"


@pytest.mark.parametrize("integrity,current,expected", [
    ("VERIFIED", True, "READY"), ("UNKNOWN", True, "UNKNOWN"),
    ("VERIFIED", False, "UNKNOWN"),
])
def test_canonical_status_requires_current_verified_evidence(integrity, current, expected):
    state = {"status": "UNKNOWN", "canonical_resume": {
        "integrity": integrity, "freshness": {"current": current},
        "result": "COMPLETE", "resume_ready": True,
    }}
    assert notifier.status_from_state(state) == expected
