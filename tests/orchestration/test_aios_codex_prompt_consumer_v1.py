from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import (
    PROTECTED_FLAGS,
    PromptValidationError,
    enqueue_prompt,
    validate_prompt,
)


def prompt_text(allowed: tuple[str, ...] = ("safe/file.py",)) -> str:
    paths = "\n".join(f"- {path}" for path in allowed)
    return f"""CODEX-ONLY PROMPT

AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED
IDENTITY MARKER: AI_OS
SUPERVISOR IDENTITY: OWNER
WORKER IDENTITY: CODEX
PACKET ID: PACKET-1
MODE: APPLY
ZONE: LOCAL
LANE: TEST

ALLOWED PATHS
{paths}

FORBIDDEN PATHS
- AGENTS.md

APPROVAL AUTHORITY
Local edits only.

VALIDATOR CHAIN
python -m pytest

STOP POINT
Stop after validation.

MISSION
Perform bounded local work.

PREFLIGHT
git status --short

FINAL REPORT FORMAT
STATUS:
END OF PACKET
"""


@pytest.fixture
def flags() -> dict[str, bool]:
    return {name: False for name in PROTECTED_FLAGS}


def write_prompt(tmp_path: Path, text: str | None = None) -> Path:
    path = tmp_path / "next.md"
    path.write_text(text or prompt_text(), encoding="utf-8")
    return path


def test_valid_prompt_becomes_one_task_and_preserves_content(tmp_path: Path, flags: dict[str, bool]) -> None:
    prompt = write_prompt(tmp_path)
    relay = tmp_path / "relay"
    result = enqueue_prompt(prompt, relay, flags)
    task = json.loads(Path(result["target"]).read_text(encoding="utf-8"))
    assert result["status"] == "ENQUEUED"
    assert list((relay / "inbox").glob("*.task.json")) == [Path(result["target"])]
    assert task["prompt_text"] == prompt.read_text(encoding="utf-8")
    assert task["prompt_sha256"] == hashlib.sha256(prompt.read_bytes()).hexdigest()
    assert task["worker"] == task["provider"] == "codex"


def test_missing_required_field_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(PromptValidationError, match="missing required"):
        validate_prompt(write_prompt(tmp_path, prompt_text().replace("PREFLIGHT", "CHECKS")))


def test_placeholder_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(PromptValidationError, match="placeholder"):
        validate_prompt(write_prompt(tmp_path, prompt_text() + "\nTODO\n"))


def test_duplicate_digest_is_not_requeued(tmp_path: Path, flags: dict[str, bool]) -> None:
    prompt = write_prompt(tmp_path)
    relay = tmp_path / "relay"
    enqueue_prompt(prompt, relay, flags)
    duplicate = enqueue_prompt(prompt, relay, flags)
    assert duplicate["status"] == "DUPLICATE"
    assert len(list((relay / "inbox").glob("*.task.json"))) == 1


def test_negative_declarations_do_not_trigger_approval(tmp_path: Path, flags: dict[str, bool]) -> None:
    prompt = write_prompt(tmp_path, prompt_text() + "\nDo not commit, merge, contact OANDA, or trade live.\n")
    result = enqueue_prompt(prompt, tmp_path / "relay", flags)
    assert result["status"] == "ENQUEUED"


def test_positive_flag_routes_to_approvals(tmp_path: Path, flags: dict[str, bool]) -> None:
    flags["commit"] = True
    result = enqueue_prompt(write_prompt(tmp_path), tmp_path / "relay", flags)
    assert result["status"] == "APPROVAL_REQUIRED"
    assert "/approvals/" in str(result["target"])


def test_missing_or_malformed_flags_fail_closed(tmp_path: Path, flags: dict[str, bool]) -> None:
    flags.pop("commit")
    with pytest.raises(PromptValidationError, match="flags mismatch"):
        enqueue_prompt(write_prompt(tmp_path), tmp_path / "relay", flags)
    flags["commit"] = "false"  # type: ignore[assignment]
    with pytest.raises(PromptValidationError, match="boolean"):
        enqueue_prompt(write_prompt(tmp_path), tmp_path / "other", flags)


def test_dry_run_does_not_write_task(tmp_path: Path, flags: dict[str, bool]) -> None:
    result = enqueue_prompt(write_prompt(tmp_path), tmp_path / "relay", flags, dry_run=True)
    assert result["status"] == "DRY_RUN"
    assert not Path(result["target"]).exists()


def test_allowed_path_mismatch_contract_is_present_in_worker() -> None:
    worker = Path("automation/orchestration/relay/Invoke-AiOsRelayWorker.ps1").read_text(encoding="utf-8")
    assert "ALLOWED_PATH_MISMATCH" in worker
    assert "Task allowed paths do not match the validated prompt." in worker


def _n04_read_actual_packet(tmp_path: Path, task_path: Path) -> dict:
    """Run actual pure reader definitions inside the verified private Job harness."""
    import base64
    import os

    if os.name != "nt":
        pytest.skip("Native Windows PowerShell reader qualification requires its host")
    from tests.orchestration.test_aios_validator_path_policy import _n02_owned_harness

    worker = Path(__file__).resolve().parents[2] / "automation/orchestration/relay/Invoke-AiOsRelayWorker.ps1"
    wrapper = tmp_path / "n04-reader.ps1"
    source_path = base64.b64encode(str(worker).encode("utf-8")).decode("ascii")
    packet_path = base64.b64encode(str(task_path).encode("utf-8")).decode("ascii")
    bootstrap = (
        "$ErrorActionPreference = 'Stop'\n"
        "if (-not [string]::Equals([Console]::In.ReadLine(), 'owned-job-ready', [StringComparison]::Ordinal)) { exit 125 }\n"
        f"$SourcePath = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{source_path}'))\n"
        f"$TaskPath = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{packet_path}'))\n"
    )
    wrapper.write_text(bootstrap + r'''
Set-StrictMode -Version Latest
$env:PSModulePath = Join-Path $PSHOME 'Modules'
# Load only the host's observed Get-FileHash function dependency for old-source
# characterization. Do not import an entire module or run worker top-level.
$hashText = [IO.File]::ReadAllText((Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Utility/Microsoft.PowerShell.Utility.psm1'))
$hashTokens = $null; $hashErrors = $null
$hashAst = [System.Management.Automation.Language.Parser]::ParseInput($hashText, [ref]$hashTokens, [ref]$hashErrors)
$hashDefinition = @($hashAst.FindAll({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-FileHash' }, $true))
if ($hashErrors.Count -ne 0 -or $hashDefinition.Count -ne 1) { throw 'Host hash dependency could not be loaded' }
. ([scriptblock]::Create($hashDefinition[0].Extent.Text))
$sourceText = [System.IO.File]::ReadAllText($SourcePath, (New-Object System.Text.UTF8Encoding($false, $true)))
$sourceTokens = $null; $sourceErrors = $null
$sourceAst = [System.Management.Automation.Language.Parser]::ParseInput($sourceText, [ref]$sourceTokens, [ref]$sourceErrors)
if ($sourceErrors.Count -ne 0) { throw 'Actual worker source does not parse' }
$functionNames = @('Get-AiOsTaskIdFromFile', 'Get-AiOsStringArray', 'Resolve-AiOsProviderSpec', 'Read-AiOsTaskPacket')
foreach ($functionName in $functionNames) {
    $definitions = @($sourceAst.FindAll({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $functionName }, $true))
    if ($definitions.Count -ne 1) { throw "Expected exactly one pure definition: $functionName" }
    . ([scriptblock]::Create($definitions[0].Extent.Text))
}
$parsed = Read-AiOsTaskPacket -File (Get-Item -LiteralPath $TaskPath)
# Preserve only actual returned contract scalars for fixture transport.
# PowerShell5 Get-Content strings carry PSDrive/PSProvider ETS properties;
# serializing the complete object at depth20 traverses that unrelated graph.
if ($parsed.ok -isnot [bool]) { throw 'Reader ok must remain a real boolean' }
$transport = [ordered]@{ ok = $parsed.ok }
foreach ($name in @('id', 'reason', 'detail', 'prompt_text')) {
    if ($parsed.PSObject.Properties[$name]) {
        $value = $parsed.$name
        if ($value -isnot [string]) { throw "Reader field must remain a real string: $name" }
        $transport[$name] = [string]::new($value.ToCharArray())
    }
}
$resultJson = [pscustomobject]$transport | ConvertTo-Json -Depth 4 -Compress
[Console]::WriteLine([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($resultJson)))
''', encoding="ascii")
    stdout, remaining = _n02_owned_harness(wrapper, tmp_path, timeout=10)
    assert remaining == 0
    return json.loads(base64.b64decode(stdout.strip()).decode("utf-8"))


def _n04_enqueue_raw(tmp_path: Path, raw: bytes, flags: dict[str, bool]) -> tuple[Path, dict]:
    path = tmp_path / "source-prompt.md"
    path.write_bytes(raw)
    result = enqueue_prompt(path, tmp_path / "owned-relay", flags)
    return Path(result["target"]), result["task"]


@pytest.mark.parametrize("newlines", ["\n", "\r\n", "\r"], ids=["lf", "crlf", "cr"])
@pytest.mark.parametrize("final_newline", [False, True], ids=["no-final-newline", "final-newline"])
@pytest.mark.parametrize("unicode_body", [False, True], ids=["ascii", "unicode"])
def test_n04_python_producer_to_actual_ps_reader(
    tmp_path: Path, flags: dict[str, bool], newlines: str, final_newline: bool, unicode_body: bool,
) -> None:
    content = prompt_text(("safe/caf\u00e9_\u6771.py",)) if unicode_body else prompt_text()
    if unicode_body:
        content += "\nDescription: caf\u00e9 \u6771 \U0001f680\n"
    canonical = content.rstrip("\n") + ("\n" if final_newline else "")
    raw = canonical.replace("\n", newlines).encode("utf-8")
    task_path, task = _n04_enqueue_raw(tmp_path, raw, flags)
    parsed = _n04_read_actual_packet(tmp_path, task_path)
    assert parsed["ok"] is True, parsed
    assert parsed["prompt_text"] == canonical
    assert task["prompt_sha256"] == hashlib.sha256(raw).hexdigest()
    assert task["prompt_text"] == canonical


def test_n04_contract_is_declared_and_raw_newlines_have_distinct_identity(tmp_path: Path, flags: dict[str, bool]) -> None:
    text = prompt_text()
    observed = []
    for index, newline in enumerate(("\n", "\r\n", "\r")):
        owned = tmp_path / str(index)
        owned.mkdir()
        _, task = _n04_enqueue_raw(owned, text.replace("\n", newline).encode("utf-8"), flags)
        assert task["prompt_text_contract"] == "AIOS_PROMPT_TEXT_UTF8_LF.v1"
        assert task["prompt_encoding"] == "utf-8"
        assert task["prompt_newlines"] == "lf"
        observed.append(task)
    assert len({task["prompt_sha256"] for task in observed}) == 3
    assert len({task["prompt_text"] for task in observed}) == 1


def test_n04_source_newline_change_after_enqueue_rejects(tmp_path: Path, flags: dict[str, bool]) -> None:
    task_path, _ = _n04_enqueue_raw(tmp_path, prompt_text().encode("utf-8"), flags)
    source = tmp_path / "source-prompt.md"
    source.write_bytes(source.read_bytes().replace(b"\n", b"\r\n"))
    before = source.read_bytes()
    parsed = _n04_read_actual_packet(tmp_path, task_path)
    assert parsed["ok"] is False and parsed["reason"] == "PROMPT_SHA256_MISMATCH"
    assert source.read_bytes() == before


@pytest.mark.parametrize("field,value", [
    ("prompt_text_contract", "unknown.v2"), ("prompt_encoding", "latin-1"), ("prompt_newlines", "crlf"),
    ("prompt_text_contract", None), ("prompt_encoding", False), ("prompt_newlines", []),
])
def test_n04_unknown_text_contract_rejects(tmp_path: Path, flags: dict[str, bool], field: str, value: object) -> None:
    task_path, task = _n04_enqueue_raw(tmp_path, prompt_text().encode("utf-8"), flags)
    task[field] = value
    task_path.write_text(json.dumps(task), encoding="utf-8")
    parsed = _n04_read_actual_packet(tmp_path, task_path)
    assert parsed["ok"] is False and parsed["reason"] == "PROMPT_CONTRACT_UNSUPPORTED", parsed


@pytest.mark.parametrize("field", ["prompt_text_contract", "prompt_encoding", "prompt_newlines"])
def test_n04_missing_text_contract_rejects(tmp_path: Path, flags: dict[str, bool], field: str) -> None:
    task_path, task = _n04_enqueue_raw(tmp_path, prompt_text().encode("utf-8"), flags)
    task.pop(field, None)
    task_path.write_text(json.dumps(task), encoding="utf-8")
    parsed = _n04_read_actual_packet(tmp_path, task_path)
    assert parsed["ok"] is False and parsed["reason"] == "PACKET_INCOMPLETE", parsed


@pytest.mark.parametrize("raw", [b"\xef\xbb\xbf", b"\xff"])
def test_n04_producer_rejects_bom_and_invalid_utf8(tmp_path: Path, raw: bytes) -> None:
    path = tmp_path / "invalid.md"
    path.write_bytes(raw + prompt_text().encode("utf-8"))
    with pytest.raises(PromptValidationError, match="UTF-8"):
        validate_prompt(path)


@pytest.mark.parametrize("raw", [b"\xef\xbb\xbf", b"\xff"])
def test_n04_actual_reader_rejects_bad_encoding_before_content_compare(tmp_path: Path, flags: dict[str, bool], raw: bytes) -> None:
    task_path, task = _n04_enqueue_raw(tmp_path, prompt_text().encode("utf-8"), flags)
    source = tmp_path / "source-prompt.md"
    invalid = raw + source.read_bytes()
    source.write_bytes(invalid)
    task["prompt_sha256"] = hashlib.sha256(invalid).hexdigest()
    task_path.write_text(json.dumps(task), encoding="utf-8")
    parsed = _n04_read_actual_packet(tmp_path, task_path)
    assert parsed["ok"] is False and parsed["reason"] == "PROMPT_ENCODING_INVALID", parsed
    assert source.read_bytes() == invalid


def test_n04_stored_canonical_text_tamper_rejects(tmp_path: Path, flags: dict[str, bool]) -> None:
    task_path, task = _n04_enqueue_raw(tmp_path, prompt_text().encode("utf-8"), flags)
    task["prompt_text"] += "tampered"
    task_path.write_text(json.dumps(task), encoding="utf-8")
    parsed = _n04_read_actual_packet(tmp_path, task_path)
    assert parsed["ok"] is False and parsed["reason"] == "PROMPT_CONTENT_MISMATCH", parsed
@pytest.mark.parametrize('kind', ['missing', 'rules', 'runtime', 'maximum-bool', 'maximum-excess', 'unknown', 'old-claim-source'])
def test_p505_selected_request_contract_rejects_before_packet_write(monkeypatch, kind):
    from automation.orchestration.relay import aios_codex_prompt_consumer_v1 as consumer
    from tests.orchestration.test_aios_resume_state import _p505_memory_files
    from tests.orchestration.test_aios_self_consuming_codex_cycle_v1 import n05_request
    root, files = _p505_memory_files(monkeypatch)
    request = n05_request(root)
    if kind == 'missing': del request['preservation_contract']
    elif kind == 'rules': request['preservation_contract']['rules_sha256'] = '0' * 64
    elif kind == 'runtime': request['preservation_contract']['python_sha256'] = '0' * 64
    elif kind == 'maximum-bool': request['preservation_contract']['max_files_changed'] = True
    elif kind == 'maximum-excess': request['preservation_contract']['max_files_changed'] = 2
    elif kind == 'unknown': request['preservation_contract']['caller_pass'] = True
    else:
        request['source_manifest']['automation/orchestration/claims/aios_task_claim_control.py'] = '0' * 64
        request['source_manifest_sha256'] = hashlib.sha256(consumer.canonical_json(request['source_manifest'])).hexdigest()
    before = dict(files)
    with pytest.raises(ValueError):
        consumer.enqueue_prompt(Path(request['prompt_path']), Path(request['relay_root']),
            {key: False for key in PROTECTED_FLAGS}, bound_request=request)
    assert files == before


def test_p505_selected_new_request_pins_current_claim_comparator_and_runtime(monkeypatch):
    from automation.orchestration.relay import aios_codex_prompt_consumer_v1 as consumer
    from tests.orchestration.test_aios_resume_state import _p505_memory_files
    from tests.orchestration.test_aios_self_consuming_codex_cycle_v1 import n05_request
    root, _ = _p505_memory_files(monkeypatch)
    request = n05_request(root)
    validated = consumer.validate_bound_request(request)
    assert validated['preservation_contract']['action_id'] == request['task_id']
    for relative in ('automation/orchestration/claims/aios_task_claim_control.py',
                     'automation/orchestration/aios_self_build_apply_result_verifier.py'):
        assert validated['source_manifest'][relative] == hashlib.sha256((Path(__file__).resolve().parents[2] / relative).read_bytes()).hexdigest()
@pytest.mark.parametrize('entry', ['build', 'validate', 'admitted'])
@pytest.mark.parametrize('shape', ['runtime-prefix', 'root-prefix', 'control', 'runtime', 'secrets', 'approvals', '.env.local', '.aws', '.git'])
def test_p505_ir01_private_runtime_rejects_before_payload_read(monkeypatch, entry, shape):
    from automation.orchestration.relay import aios_codex_prompt_consumer_v1 as consumer
    from tests.orchestration.test_aios_resume_state import (
        _np_json,
        _np_refresh,
        _p505_memory_case,
    )
    case = _p505_memory_case(monkeypatch)
    request = json.loads(case['data']['request_json'])
    runtime = case['root'] / '.codex' / 'owned-runtime.json'
    if shape not in {'runtime-prefix', 'root-prefix'}:
        runtime = case['root'] / shape / 'public-runtime.exe'
    if shape == 'root-prefix':
        request['repo_root'] = str(case['root'] / '.codex' / 'owned-subtree')
        runtime = Path(request['repo_root']) / 'public-runtime.exe'
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_bytes(b'inert memory private sentinel; never read')
    request['python_executable'] = str(runtime)
    request['preservation_contract']['python_sha256'] = hashlib.sha256(b'inert memory private sentinel; never read').hexdigest()
    original = Path.read_bytes
    reads = []
    def refuse_private_payload(path):
        if path == runtime:
            reads.append(str(path))
            raise AssertionError('P505_PRIVATE_PAYLOAD_READ')
        return original(path)
    monkeypatch.setattr(Path, 'read_bytes', refuse_private_payload)
    before = dict(case['memory_files'])
    with pytest.raises(ValueError, match='private|root'):
        if entry == 'build': consumer.build_preservation_contract(request)
        elif entry == 'validate': consumer.validate_preservation_contract(request)
        else:
            case['data']['request_json'] = _np_json(request).decode('ascii')
            _np_refresh(case)
            case['cycle']._native_admitted(case['context'], case['reader'])
    assert reads == []
    assert case['memory_files'] == before


def test_p505_ir01_forged_public_anchor_rejects_before_payload_read(monkeypatch):
    from tests.orchestration.test_aios_resume_state import (
        _np_json,
        _np_refresh,
        _p505_memory_case,
    )
    case = _p505_memory_case(monkeypatch)
    request = json.loads(case['data']['request_json'])
    runtime = case['root'] / 'control' / 'public-runtime.exe'
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_bytes(b'owned inert sentinel')
    request['repo_root'] = str(runtime.parent)
    request['repository_identity']['repo_root'] = str(runtime.parent)
    request['python_executable'] = str(runtime)
    original = Path.read_bytes
    reads = []
    def refuse_private(path):
        if path == runtime:
            reads.append(str(path))
            raise AssertionError('P505_PRIVATE_PAYLOAD_READ')
        return original(path)
    monkeypatch.setattr(Path, 'read_bytes', refuse_private)
    case['data']['request_json'] = _np_json(request).decode('ascii')
    _np_refresh(case)
    with pytest.raises(ValueError, match='root|private'):
        case['cycle']._native_admitted(case['context'], case['reader'])
    assert reads == []
@pytest.mark.parametrize('missing', ['claim', 'dispatch_item', 'repo_root', 'selection'])
def test_p505_ir01_incomplete_admission_rejects_before_runtime_read(monkeypatch, missing):
    from automation.orchestration.claims.aios_task_claim_control import ClaimError
    from tests.orchestration.test_aios_resume_state import (
        _np_json,
        _np_refresh,
        _p505_memory_case,
    )
    case = _p505_memory_case(monkeypatch)
    request = json.loads(case['data']['request_json'])
    runtime = Path(request['python_executable'])
    if missing == 'repo_root':
        del request['repo_root']
        case['data']['request_json'] = _np_json(request).decode('ascii')
    elif missing == 'selection': case['data']['queue_item']['packet_id'] = 'OTHER'
    else: del case['data'][missing]
    _np_refresh(case)
    original = Path.read_bytes
    reads = []
    def refuse_runtime(path):
        if path == runtime:
            reads.append(str(path))
            raise AssertionError('P505_RUNTIME_READ_BEFORE_ADMISSION')
        return original(path)
    monkeypatch.setattr(Path, 'read_bytes', refuse_runtime)
    with pytest.raises((ValueError, ClaimError)):
        case['cycle']._native_admitted(case['context'], case['reader'])
    assert reads == []
