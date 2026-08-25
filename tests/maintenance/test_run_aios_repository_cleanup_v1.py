from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).parents[2] / "scripts/maintenance/run_aios_repository_cleanup_v1.py"
SPEC = importlib.util.spec_from_file_location("cleanup", SCRIPT)
assert SPEC and SPEC.loader
cleanup = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cleanup
SPEC.loader.exec_module(cleanup)


def command(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(args), cwd=root, text=True, capture_output=True, check=False)


def repo(tmp_path: Path, branch: str = "work") -> Path:
    command(tmp_path, "git", "init", "-q", "-b", branch)
    command(tmp_path, "git", "config", "user.email", "test@example.invalid")
    command(tmp_path, "git", "config", "user.name", "Test")
    for name, content in {
        "AGENTS.md": "rules\n", "README.md": "readme\n", "SECURITY.md": "security\n",
        "COMPLIANCE_BASELINE.md": "baseline\n", ".gitignore": ".aios/runtime/\n",
        ".github/workflows/ci.yml": "name: CI\n", "source.py": "value = 1\n",
    }.items():
        path = tmp_path / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content, encoding="utf-8")
    command(tmp_path, "git", "add", "AGENTS.md", "README.md", "SECURITY.md", "COMPLIANCE_BASELINE.md", ".gitignore", ".github/workflows/ci.yml", "source.py")
    command(tmp_path, "git", "commit", "-qm", "initial")
    cleanup.BASELINE = command(tmp_path, "git", "rev-parse", "HEAD").stdout.strip()
    return tmp_path


def report(root: Path) -> dict:
    return cleanup.audit_repository(root, generated_at="2026-08-06T00:00:00+00:00")


def plan_for(root: Path, entries: list[dict] | None = None, head: str | None = None) -> Path:
    value = {"schema": "aios.repository_cleanup.plan.v1", "head": head or cleanup.git(root, "rev-parse", "HEAD").strip(), "entries": entries or []}
    path = root / "plan.json"; path.write_text(json.dumps(value), encoding="utf-8"); return path


def test_audit_and_plan_are_read_only_and_ignore_untracked(tmp_path: Path) -> None:
    root = repo(tmp_path); untracked = root / "private.txt"; untracked.write_text("token=valuable-secret\n", encoding="utf-8")
    before = cleanup.git(root, "status", "--porcelain")
    audit = report(root); cleanup.build_plan(audit, root)
    assert cleanup.git(root, "status", "--porcelain") == before
    assert "valuable-secret" not in cleanup.stable_json(audit)
    assert audit["tracked_file_count"] == len(cleanup.tracked_files(root))


def test_symlink_escape_is_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = repo(tmp_path); outside = tmp_path.parent / "outside-cleanup-test"; outside.write_text("outside", encoding="utf-8")
    link = root / "escape.txt"; link.write_text("outside", encoding="utf-8"); command(root, "git", "add", "escape.txt"); command(root, "git", "commit", "-qm", "link")
    original_is_symlink = cleanup.Path.is_symlink
    original_resolve = cleanup.Path.resolve
    monkeypatch.setattr(cleanup.Path, "is_symlink", lambda self: self == link or original_is_symlink(self))
    monkeypatch.setattr(cleanup.Path, "resolve", lambda self, *args, **kwargs: (outside.resolve(strict=False) if self == link else original_resolve(self, *args, **kwargs)))
    assert report(root)["categories"]["A"] == "BLOCKED"


@pytest.mark.parametrize("path", ["../escape", "/tmp/escape", r"C:\escape", "*.py", "dir/../../escape"])
def test_path_traversal_wildcards_and_absolute_forms_are_rejected(tmp_path: Path, path: str) -> None:
    root = repo(tmp_path)
    with pytest.raises(cleanup.ControllerError) as raised: cleanup.safe_path(root, path)
    assert raised.value.code == 5


def test_secret_values_are_redacted() -> None:
    output = cleanup.redact('token = "valuable-secret" password=hunter2')
    assert "valuable-secret" not in output and "hunter2" not in output and output.count("[REDACTED]") == 2


def test_stable_output_and_ordering(tmp_path: Path) -> None:
    root = repo(tmp_path); first = report(root); second = report(root)
    assert cleanup.stable_json(first) == cleanup.stable_json(second)
    assert list(first["categories"]) == list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def test_binary_and_unsupported_encoding_are_skipped(tmp_path: Path) -> None:
    root = repo(tmp_path)
    (root / "binary.dat").write_bytes(b"a\0b"); (root / "latin.txt").write_bytes(b"\xff\xfe")
    command(root, "git", "add", "binary.dat", "latin.txt"); command(root, "git", "commit", "-qm", "data")
    result = report(root)
    assert result["skipped_file_reasons"]["binary"] == 1
    assert result["skipped_file_reasons"]["unsupported_encoding"] == 1


def test_mixed_eol_and_markdown_spaces_are_observed_not_rewritten(tmp_path: Path) -> None:
    root = repo(tmp_path); path = root / "notes.md"; original = b"one  \r\ntwo\n"; path.write_bytes(original)
    command(root, "git", "add", "notes.md"); command(root, "git", "commit", "-qm", "notes")
    assert report(root)["categories"]["M"] == "WARN"
    assert path.read_bytes() == original


def test_generated_runtime_duplicate_and_case_collision_detection(tmp_path: Path) -> None:
    root = repo(tmp_path)
    for name in ("runtime/state.txt", "Same.txt", "same.TXT", "copy.txt"):
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("duplicate\n", encoding="utf-8")
    command(root, "git", "add", "runtime/state.txt", "Same.txt", "same.TXT", "copy.txt"); command(root, "git", "commit", "-qm", "findings")
    result = report(root)
    assert result["categories"]["G"] == result["categories"]["E"] == result["categories"]["N"] == "WARN"


def test_invalid_and_duplicate_json_and_invalid_python(tmp_path: Path) -> None:
    root = repo(tmp_path)
    (root / "bad.json").write_text('{"a": 1, "a": 2}', encoding="utf-8")
    (root / "bad.py").write_text("def nope(:\n", encoding="utf-8")
    command(root, "git", "add", "bad.json", "bad.py"); command(root, "git", "commit", "-qm", "bad")
    result = report(root)
    assert result["categories"]["J"] == "WARN" and result["categories"]["I"] == "BLOCKED"


def test_missing_optional_tools_have_not_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = repo(tmp_path); monkeypatch.setattr(cleanup.shutil, "which", lambda _name: None)
    result = report(root)
    assert result["categories"]["P"] == result["categories"]["Q"] == result["categories"]["Y"] == "NOT_AVAILABLE"


@pytest.mark.parametrize("branch,confirmed,message", [("main", True, "non-main"), ("work", False, "confirm")])
def test_apply_rejects_main_and_missing_confirmation(tmp_path: Path, branch: str, confirmed: bool, message: str) -> None:
    root = repo(tmp_path, branch); path = plan_for(root)
    with pytest.raises(cleanup.ControllerError, match=message): cleanup.apply_plan(root, path, confirmed)


def test_apply_rejects_detached_and_dirty_state(tmp_path: Path) -> None:
    root = repo(tmp_path); plan = plan_for(root); command(root, "git", "checkout", "--detach", "-q")
    with pytest.raises(cleanup.ControllerError, match="attached"): cleanup.apply_plan(root, plan, True)
    command(root, "git", "switch", "-q", "work"); (root / "source.py").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(cleanup.ControllerError, match="clean"): cleanup.apply_plan(root, plan, True)


def test_apply_rejects_stale_head_and_hash(tmp_path: Path) -> None:
    root = repo(tmp_path); stale = plan_for(root, head="0" * 40)
    with pytest.raises(cleanup.ControllerError) as raised: cleanup.apply_plan(root, stale, True)
    assert raised.value.code == 4
    entry = eligible(root, [sys.executable, "-c", "pass"]); entry["original_sha256"] = "0" * 64
    with pytest.raises(cleanup.ControllerError, match="Stale file hash"): cleanup.apply_plan(root, plan_for(root, [entry]), True)


def eligible(root: Path, args: list[str], validators: list[list[str]] | None = None) -> dict:
    return {"classification": "EXISTING_TOOL_SAFE_FIX", "automatic_eligibility": True, "path": "source.py",
            "expected_changed_paths": ["source.py"], "configured_tool_name": args[0], "exact_command_arguments": args,
            "original_sha256": cleanup.sha256((root / "source.py").read_bytes()), "post_fix_validators": validators or []}


def test_apply_rejects_wildcard_and_protected_path(tmp_path: Path) -> None:
    root = repo(tmp_path); entry = eligible(root, [sys.executable, "*.py"])
    with pytest.raises(cleanup.ControllerError) as raised: cleanup.apply_plan(root, plan_for(root, [entry]), True)
    assert raised.value.code == 5
    entry.update(path="AGENTS.md", expected_changed_paths=["AGENTS.md"])
    with pytest.raises(cleanup.ControllerError) as raised: cleanup.apply_plan(root, plan_for(root, [entry]), True)
    assert raised.value.code == 5


def test_unexpected_change_stops_apply_and_failed_validator_restores_bytes(tmp_path: Path) -> None:
    root = repo(tmp_path); original = (root / "source.py").read_bytes()
    mutate = [sys.executable, "-c", "from pathlib import Path; Path('source.py').write_text('changed'); Path('README.md').write_text('surprise')"]
    with pytest.raises(cleanup.ControllerError, match="Unexpected"): cleanup.apply_plan(root, plan_for(root, [eligible(root, mutate)]), True)
    assert (root / "source.py").read_bytes() == original
    command(root, "git", "restore", "README.md")
    mutate_one = [sys.executable, "-c", "from pathlib import Path; Path('source.py').write_text('changed')"]
    validator = [[sys.executable, "-c", "raise SystemExit(1)"]]
    with pytest.raises(cleanup.ControllerError, match="Validator"): cleanup.apply_plan(root, plan_for(root, [eligible(root, mutate_one, validator)]), True)
    assert (root / "source.py").read_bytes() == original
    assert not cleanup.git(root, "diff", "--cached").strip()


def test_subprocess_wrapper_does_not_offer_shell_argument() -> None:
    assert "shell" not in cleanup.run.__annotations__


def test_cli_exit_codes(tmp_path: Path) -> None:
    root = repo(tmp_path)
    assert cleanup.execute("audit", root) in {0, 1}
    assert cleanup.main(["apply", "--repo-root", str(root), "--plan", "missing.json"]) == 2


def test_runtime_reports_do_not_contain_credential_values(tmp_path: Path) -> None:
    root = repo(tmp_path); (root / "source.py").write_text('token = "valuable-secret"\n', encoding="utf-8")
    command(root, "git", "add", "source.py"); command(root, "git", "commit", "-qm", "secretlike")
    cleanup.execute("audit", root)
    assert "valuable-secret" not in (root / cleanup.RUNTIME / cleanup.AUDIT_JSON).read_text(encoding="utf-8")
