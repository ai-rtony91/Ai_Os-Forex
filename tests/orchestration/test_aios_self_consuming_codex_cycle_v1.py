from __future__ import annotations

import json
from pathlib import Path

from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import PROTECTED_FLAGS
from automation.orchestration.relay.aios_self_consuming_codex_cycle_v1 import build_next_pr_lifecycle_packet, run_self_consuming_cycle
from tests.orchestration.test_aios_codex_prompt_consumer_v1 import prompt_text


FLAGS = {name: False for name in PROTECTED_FLAGS}


def prompt(tmp_path: Path, suffix: str = "") -> Path:
    path = tmp_path / f"prompt{suffix}.md"
    path.write_text(prompt_text((f"safe/{suffix or 'one'}.py",)), encoding="utf-8")
    return path


def fake_complete(relay: Path):
    def worker() -> None:
        task = next((relay / "inbox").glob("*.task.json"))
        (relay / "done").mkdir(parents=True, exist_ok=True)
        task.replace(relay / "done" / task.name)
    return worker


def test_unbound_prompt_path_cannot_dispatch_or_complete(tmp_path: Path) -> None:
    result=run_self_consuming_cycle(generate=lambda: str(prompt(tmp_path)),relay_root=tmp_path/"relay",invoke_worker=lambda *a: (_ for _ in ()).throw(AssertionError("unbound dispatch")))
    assert result.status == "BOUND_REQUEST_REQUIRED"


def test_stop_flag_stops_without_generation(tmp_path: Path) -> None:
    relay=tmp_path/"relay";relay.mkdir();(relay/"STOP.flag").touch()
    result=run_self_consuming_cycle(generate=lambda: (_ for _ in ()).throw(AssertionError()),relay_root=relay)
    assert result.status == "STOP_FLAG"


def test_elapsed_bound_is_enforced_before_generation(tmp_path: Path) -> None:
    ticks=iter((0.0,61.0))
    result=run_self_consuming_cycle(generate=lambda: (_ for _ in ()).throw(AssertionError()),relay_root=tmp_path/"relay",monotonic=lambda: next(ticks),max_elapsed_minutes=1)
    assert result.status == "MAX_ELAPSED"


def test_protected_bound_request_never_creates_approvals(tmp_path: Path) -> None:
    request=n05_request(tmp_path);flags=dict(FLAGS);flags["commit"]=True
    result=run_self_consuming_cycle(generate=lambda:request,relay_root=Path(request["relay_root"]),flags=flags)
    assert result.status == "APPROVAL_REQUIRED"
    assert not Path(request["relay_root"]).exists()


def test_next_pr_lifecycle_packet_is_complete_but_dry_run() -> None:
    packet = build_next_pr_lifecycle_packet()
    assert packet.startswith("CODEX-ONLY PROMPT\n")
    assert "AI_OS EXECUTION TOKEN" in packet
    assert "MODE: DRY_RUN" in packet
    assert "Commit, push, PR mutation, merge, and branch deletion require separate approval." in packet



# N03 fixtures execute only AST-selected actual adapter definitions. The accepted
# N02 outer Job owns the harmless harness and all children before its gate opens.
def _n03_fixture(tmp_path: Path, child: str, *, stdin: str | None = None,
                 arguments: list[str] | None = None, timeout: int = 3,
                 executable: str | None = None, extra: dict | None = None,
                 launcher: str | None = None, failure: str | None = None) -> tuple[dict, Path]:
    import base64
    import shutil
    import sys
    import tempfile
    from tests.orchestration.test_aios_validator_path_policy import _n02_owned_harness

    repo = Path(tempfile.mkdtemp(prefix='n3-')) / 'r'
    helper = repo / 'automation/orchestration/timeout/Invoke-AiOsCliWithTimeout.ps1'
    runner = repo / 'automation/orchestration/validator_chain_runner/Invoke-AiOsValidatorChain.DRY_RUN.ps1'
    source = Path(__file__).resolve().parents[2]
    for path in (helper, runner):
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / path.relative_to(repo), path)
    child_path = repo / 'inert child.py'
    child_path.write_text(child, encoding='utf-8')
    if launcher:
        launcher_path = repo / ('launch space 雪.' + launcher)
        if launcher == 'ps1':
            launcher_path.write_text("[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)\n[Console]::Write(($args | ConvertTo-Json -Compress))\n", encoding='utf-8-sig')
        else:
            launcher_path.write_text('@echo off\r\n"' + sys.executable + '" "' + str(child_path) + '" %*\r\n', encoding='ascii')
        executable = str(launcher_path)
    if failure:
        code = runner.read_text(encoding='utf-8')
        if failure == 'writer_join':
            start = code.index('internal sealed class PipeInput')
            end = code.index('public static class ValidatorProcess', start)
            owned = code[start:end]
            old = 'return !started || thread.Join(Math.Max(0, wait));'
            assert owned.count(old) == 1
            owned = owned.replace(old, 'if (started) thread.Join(Math.Max(0, wait)); return false;')
            code = code[:start] + owned + code[end:]
        elif failure == 'writer_close':
            start = code.index('internal sealed class PipeInput')
            end = code.index('public static class ValidatorProcess', start)
            owned = code[start:end]
            assert owned.count('Native.CloseHandle(owned)') == 1
            # Force CloseHandle failure for the owned pipe only. The actual
            # handle remains confined to this fixture process and is released
            # when its accepted outer Job reaps the harness after the result.
            owned = owned.replace('Native.CloseHandle(owned)', 'Native.CloseHandle(new IntPtr(-999))')
            code = code[:start] + owned + code[end:]
        else:
            raise AssertionError(failure)
        runner.write_text(code, encoding='utf-8', newline='')
    request = dict(FilePath=executable or sys.executable,
                   ArgumentList=arguments if arguments is not None else [str(child_path)],
                   TimeoutSec=timeout, StdIn=stdin, WorkingDirectory=str(repo))
    request.update(extra or {})
    encoded = base64.b64encode(json.dumps(request, ensure_ascii=True).encode()).decode()
    quoted = str(helper).replace("'", "''")
    harness = repo / 'n03_harness.ps1'
    harness.write_text(f"""$ErrorActionPreference = 'Stop'
if (-not [string]::Equals([Console]::In.ReadLine(), 'owned-job-ready', [StringComparison]::Ordinal)) {{ exit 125 }}
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile('{quoted}', [ref]$tokens, [ref]$errors)
if ($errors.Count) {{ throw $errors[0] }}
$definitions = $ast.FindAll({{ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] }}, $false)
$definitionFile = Join-Path (Split-Path '{quoted}' -Parent) 'owned-definitions.ps1'
[IO.File]::WriteAllText($definitionFile, (($definitions | ForEach-Object {{ $_.Extent.Text }}) -join [Environment]::NewLine), [Text.UTF8Encoding]::new($false))
. $definitionFile
$request = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded}')) | ConvertFrom-Json
$parameters = @{{}}
foreach ($p in $request.PSObject.Properties) {{ $parameters[$p.Name] = $p.Value }}
$watch = [Diagnostics.Stopwatch]::StartNew()
if (Get-Command Invoke-AiOsCliProcess -ErrorAction SilentlyContinue) {{
    $run = Invoke-AiOsCliProcess @parameters
}} else {{
    # RED-only original entry extraction; executes its exact original Try AST,
    # never the unregistered helper's top-level script or any provider worker.
    foreach ($p in $parameters.GetEnumerator()) {{ Set-Variable -Name $p.Key -Value $p.Value }}
    $started = (Get-Date).ToUniversalTime()
    $entry = $ast.Find({{ param($node) $node -is [Management.Automation.Language.TryStatementAst] }}, $false)
    $run = & ([scriptblock]::Create($entry.Extent.Text))
}}
$run | Add-Member -NotePropertyName elapsed_ms -NotePropertyValue $watch.ElapsedMilliseconds
if ('{failure or ''}' -ne '') {{
    $second = Invoke-AiOsCliProcess -FilePath '{__import__('sys').executable}' -ArgumentList @('-c', 'open("second-sentinel", "w").write("bad")') -WorkingDirectory '{str(repo)}' -StdIn '' -TimeoutSec 1
    $run | Add-Member -NotePropertyName second_run -NotePropertyValue $second
}}
$json = $run | ConvertTo-Json -Depth 12
[Console]::WriteLine('N03_RESULT_BASE64:' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json)))
""", encoding='utf-8')
    output, active = _n02_owned_harness(harness, repo, timeout=14)
    assert active == 0
    encoded_result = output.split('N03_RESULT_BASE64:', 1)[1].strip()
    result = json.loads(base64.b64decode(encoded_result).decode('utf-8'))
    (repo / 'n03-result.json').write_text(json.dumps(dict(result=result, outer_job_active=active), ensure_ascii=True, indent=2), encoding='utf-8')
    return result, repo


def test_n03_simultaneous_input_output_does_not_deadlock(tmp_path: Path) -> None:
    # Writing stdin synchronously before draining stdout makes this child and
    # adapter block each other; the original helper exceeds the outer deadline.
    run, _ = _n03_fixture(tmp_path, """import sys
sys.stdout.buffer.write(b'O' * 262144); sys.stdout.buffer.flush()
sys.stderr.buffer.write(b'E' * 262144); sys.stderr.buffer.flush()
data = sys.stdin.buffer.read()
sys.stdout.write('INPUT_BYTES:' + str(len(data)))
""", stdin='x' * 2097152)
    assert run['exit_code'] == 0 and run['timed_out'] is False
    assert run['cleanup_state'] == 'CONFIRMED'
    assert run['stdin_completed'] is True and run['stdin_bytes_written'] == 2097152
    assert run['stdout'].endswith('INPUT_BYTES:2097152')
    assert len(run['stderr']) == 262144
    assert run['elapsed_ms'] < 8000



def test_n03_never_read_stdin_times_out_and_reaps_writer(tmp_path: Path) -> None:
    run, _ = _n03_fixture(tmp_path, "import time; print('BEFORE_BLOCK', flush=True); time.sleep(30)", stdin='x' * 2097152, timeout=1)
    assert run['exit_code'] == 'TIMEOUT_EXCEEDED' and run['timed_out'] is True
    assert run['cleanup_state'] == 'CONFIRMED' and run['stdin_writer_joined'] is True
    assert run['root_exit_confirmed'] is True and run['tree_exit_confirmed'] is True
    assert 'BEFORE_BLOCK' in run['stdout'] and run['stdin_completed'] is False
    assert run['elapsed_ms'] < 5000


def test_n03_early_child_exit_rejects_incomplete_input(tmp_path: Path) -> None:
    run, _ = _n03_fixture(tmp_path, "print('EARLY_EXIT', flush=True)", stdin='x' * 2097152)
    assert run['exit_code'] == 'INPUT_INCOMPLETE' and run['timed_out'] is False
    assert run['stdin_completed'] is False and run['stdin_writer_joined'] is True
    assert run['cleanup_state'] == 'CONFIRMED' and run['child_exit_code'] == 0
    assert run['elapsed_ms'] < 5000


def test_n03_utf8_input_output_and_working_directory(tmp_path: Path) -> None:
    run, repo = _n03_fixture(tmp_path, """import os, sys
data = sys.stdin.buffer.read()
sys.stdout.buffer.write(data)
sys.stderr.buffer.write(os.getcwd().encode('utf-8'))
""", stdin='café 雪 😀\n')
    assert run['exit_code'] == 0 and run['stdin_completed'] is True
    assert run['stdout'] == 'café 雪 😀\n'
    assert run['stdin_bytes_written'] == 15
    assert run['stderr'] == str(repo)


def test_n03_output_retention_is_bounded_without_blocking_drains(tmp_path: Path) -> None:
    run, _ = _n03_fixture(tmp_path, """import sys
sys.stdout.buffer.write(b'O' * 2097152)
sys.stderr.buffer.write(b'E' * 2097152)
""", extra={'MaximumOutputCharacters': 4096})
    assert run['exit_code'] == 0 and run['cleanup_state'] == 'CONFIRMED'
    assert run['stdout'] == 'O' * 4096 and run['stderr'] == 'E' * 4096
    assert run['stdout_truncated'] is True and run['stderr_truncated'] is True


def test_n03_native_argument_quotes_and_trailing_backslashes(tmp_path: Path) -> None:
    import sys
    args = ['', 'space value', '雪😀', 'embedded"quote', 'C:\\path with spaces\\', 'slashes\\\\"quote']
    run, _ = _n03_fixture(tmp_path, '', executable=sys.executable,
                          arguments=['-c', 'import json,sys; print(json.dumps(sys.argv[1:], ensure_ascii=True))', *args])
    assert run['exit_code'] == 0
    assert json.loads(run['stdout']) == args


def test_n03_descendant_holding_pipes_uses_original_deadline(tmp_path: Path) -> None:
    run, _ = _n03_fixture(tmp_path, """import subprocess, sys
subprocess.Popen([sys.executable, '-c', 'import time; print("DESCENDANT",flush=True); time.sleep(30)'])
print('ROOT_EXIT_FIRST', flush=True)
""", timeout=1)
    assert run['timed_out'] is True and run['cleanup_state'] == 'CONFIRMED'
    assert run['root_exit_confirmed'] is True and run['tree_exit_confirmed'] is True
    assert 'ROOT_EXIT_FIRST' in run['stdout'] and 'DESCENDANT' in run['stdout']
    assert run['elapsed_ms'] < 5000



def test_n03_powershell_launcher_preserves_arguments_under_current_policy(tmp_path: Path) -> None:
    args = ['', 'space value', '雪😀', 'embedded"quote', 'C:\\path with spaces\\']
    run, _ = _n03_fixture(tmp_path, '', launcher='ps1', arguments=args)
    assert run['exit_code'] == 0, run
    assert json.loads(run['stdout']) == args


def test_n03_cmd_launcher_spaces_unicode_and_safe_arguments(tmp_path: Path) -> None:
    run, _ = _n03_fixture(tmp_path, 'import json,sys; print(json.dumps(sys.argv[1:], ensure_ascii=True))',
                          launcher='cmd', arguments=['', 'space value', '雪😀', 'plain', 'C:\\path with spaces\\'])
    assert run['exit_code'] == 0, run
    assert json.loads(run['stdout']) == ['', 'space value', '雪😀', 'plain', 'C:\\path with spaces\\']


def test_n03_cmd_shell_syntax_rejected_without_launch(tmp_path: Path) -> None:
    for index, value in enumerate(['& echo bad', 'embedded"quote', '%TEMP%', '!bad!', 'line\nbreak']):
        run, repo = _n03_fixture(tmp_path / str(index), "from pathlib import Path; Path('bad-sentinel').touch()",
                                 launcher='cmd', arguments=[value])
        assert run['exit_code'] == 'STARTUP_FAILED' and run['root_process_id'] == 0
        assert 'Unsupported CMD shell syntax' in run['stderr']
        assert not (repo / 'bad-sentinel').exists()


def test_n03_writer_join_uncertainty_blocks_retry_and_following_launch(tmp_path: Path) -> None:
    run, repo = _n03_fixture(tmp_path, "import time; print('OWNED',flush=True); time.sleep(30)",
                             stdin='x' * 2097152, timeout=1, failure='writer_join')
    assert run['exit_code'] == 'CLEANUP_UNRESOLVED' and run['cleanup_state'] == 'UNRESOLVED'
    assert run['stdin_writer_joined'] is False and run['retry_allowed'] is False
    assert run['second_run']['exit_code'] == 'CLEANUP_UNRESOLVED'
    assert run['second_run']['retry_allowed'] is False
    assert not (repo / 'second-sentinel').exists()



def test_n03_writer_pipe_close_failure_is_not_confirmed_cleanup(tmp_path: Path) -> None:
    run, repo = _n03_fixture(tmp_path, 'import sys; sys.stdin.buffer.read()',
                             stdin='owned input', timeout=1, failure='writer_close')
    assert run['cleanup_state'] == 'UNRESOLVED' and run['retry_allowed'] is False
    assert run['stdin_close_error_code'] != 0
    assert run['second_run']['exit_code'] == 'CLEANUP_UNRESOLVED'
    assert not (repo / 'second-sentinel').exists()


# N05 exact request/observation contracts. No provider/runtime entry executes.
import hashlib
import pytest
from copy import deepcopy
from automation.orchestration.relay import aios_codex_prompt_consumer_v1 as n05_consumer
from automation.orchestration.relay import aios_self_consuming_codex_cycle_v1 as n05_cycle


def _selected_event_memory_case(monkeypatch, *, native=False):
    """Reuse accepted collector/verifiers; double only owned filesystem/lock APIs."""
    import importlib.util
    import os
    from contextlib import nullcontext

    source = Path(__file__).resolve().with_name('test_aios_resume_state.py')
    spec = importlib.util.spec_from_file_location('selected_event_resume_fixture', source)
    held = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(held)
    if not native:
        root, files = held._p505_memory_files(monkeypatch)
        return held, root, files, n05_request(root)
    case = held._p505_memory_case(monkeypatch)
    files, root = case['memory_files'], case['root']
    def move(source, destination):
        source, destination = Path(source), Path(destination)
        if source not in files or not destination.is_relative_to(root):
            raise AssertionError('Only owned memory replacement permitted')
        files[destination] = files.pop(source)
        return destination
    monkeypatch.setattr(os, 'replace', move)
    monkeypatch.setattr(Path, 'replace', move)
    def unlink(path, missing_ok=False):
        if not path.is_relative_to(root):
            raise AssertionError('No real unlink')
        if path not in files and not missing_ok:
            raise FileNotFoundError(str(path))
        files.pop(path, None)
    monkeypatch.setattr(Path, 'unlink', unlink)
    monkeypatch.setattr(case['owner'], 'publication_lock', lambda *a, **k: nullcontext())
    case['requested']['resume_dir'] = 'Reports/aios_resume'
    # The accepted adapter closes over this owned set. Supply missing fixture
    # data directly, without calling a filesystem API (including mocked mkdir).
    from inspect import getclosurevars
    memory_directories = getclosurevars(Path.mkdir).nonlocals['directories']
    memory_directories.add(root / 'Reports/aios_resume')
    lock_path = root / 'Reports/aios_resume/.publication.lock'
    files[lock_path] = b'\0'
    descriptors = getclosurevars(os.fstat).nonlocals['descriptors']
    def memory_lock(fd, mode, size):
        if fd not in descriptors or descriptors[fd].path != lock_path or size != 1:
            raise AssertionError('Only owned synthetic publication lock descriptor')
    import msvcrt
    monkeypatch.setattr(msvcrt, 'locking', memory_lock)
    def glob(path, pattern):
        from fnmatch import fnmatchcase
        if not path.is_relative_to(root) or not pattern.startswith(('AIOS_RESUME_ATTEMPT_', 'AIOS_RESUME_STATE_')):
            raise AssertionError('Only owned memory publication enumeration')
        return iter(sorted(candidate for candidate in files if candidate.parent == path
                           and fnmatchcase(candidate.name, pattern)))
    monkeypatch.setattr(Path, 'glob', glob)
    held._np_refresh(case)
    return held, case


def test_selected_event_actual_main_receives_default_preview(monkeypatch):
    """Removing the actual main-to-notifier connection loses this event output."""
    import io
    import sys
    from contextlib import redirect_stdout

    _, root, files, request = _selected_event_memory_case(monkeypatch)
    path = root / 'selected-request.json'
    path.write_bytes(n05_consumer.canonical_json(request))
    before = dict(files)
    monkeypatch.setattr(sys, 'argv', ['cycle', '--request-json', str(path), '--dry-run'])
    with redirect_stdout(io.StringIO()) as output:
        assert n05_cycle.main() == 0
    result = json.loads(output.getvalue())
    assert result['status'] == 'DRY_RUN' and result['retry_allowed'] is False
    assert result['notification']['effect_scope'] == 'PREVIEW_ONLY'
    assert result['notification']['delivery_accepted'] is False
    assert files == before


def test_selected_event_actual_native_postpublication_receives_canonical_preview(monkeypatch):
    """Removing postpublication receiving must fail while native acceptance stays real."""
    from automation.orchestration.claims.aios_task_claim_control import TaskClaimController

    held, case = _selected_event_memory_case(monkeypatch, native=True)
    attempt = held._np_capture(case)
    recovered = held._np_recover(case, attempt)
    assert recovered['result'] == 'COMPLETE', recovered.get('finalization')
    assert held._np_read(case) is not None
    monkeypatch.setattr(TaskClaimController, 'guard', lambda *a, **k: case['data']['claim'])
    controller = object.__new__(TaskClaimController)
    adapter = case['cycle'].make_native_execution_adapter(case['root'],
        expected_request=case['context'].request, native_admission_reader=case['reader'],
        claim_controller=controller, requested=case['requested'])
    result = adapter(case['data']['original_resolver_packet'])
    assert result['status'] == 'COMPLETE' and result['passed'] is True
    assert result['notification']['effect_scope'] == 'PREVIEW_ONLY'
    assert result['notification']['canonical_integrity'] == 'VERIFIED', result['notification']
    assert result['notification']['delivery_accepted'] is False
    assert result['notification']['selected_event']['transport_request_sha256'] != case['context'].request.request_sha256
    assert result['notification']['selected_event']['requirement_request_sha256'] == case['context'].request.request_sha256
    before = dict(case['memory_files'])
    repeated = adapter(case['data']['original_resolver_packet'])
    assert repeated['status'] == 'COMPLETE'
    assert repeated['notification']['canonical_integrity'] == 'VERIFIED'
    assert case['memory_files'] == before


def test_selected_event_delayed_reader_loss_never_exposes_arbitrary_reason(monkeypatch):
    """The real third admission read may fail with text that only resembles a code."""
    held, case = _selected_event_memory_case(monkeypatch, native=True)
    attempt = held._np_capture(case)
    assert held._np_recover(case, attempt)['result'] == 'COMPLETE'
    assert held._np_read(case) is not None
    request = json.loads(case['data']['request_json'])
    original = {'status': 'COMPLETE', 'detail': 'original task outcome is unchanged'}
    before = dict(case['memory_files'])
    kwargs = dict(expected_request=case['context'].request, admitted_context=case['context'])
    positive = case['cycle']._preview_selected_event(case['root'], request, original,
        native_admission_reader=case['reader'], **kwargs)
    assert positive['canonical_integrity'] == 'VERIFIED' and positive['canonical_current'] is True
    for reason, expected in [('synthetic_provider_secret_marker', 'verification_unavailable'),
                             ('canonical_public_contract_invalid', 'canonical_public_contract_invalid')]:
        calls = []

        def intermittent_reader(value):
            calls.append(value)
            if len(calls) == 3:
                raise ValueError(reason)
            return case['reader'](value)

        result = case['cycle']._preview_selected_event(case['root'], request, original,
            native_admission_reader=intermittent_reader, **kwargs)
        assert len(calls) == 3
        assert result['canonical_integrity'] == 'UNKNOWN' and result['canonical_current'] is False
        assert result['canonical_reason_code'] == expected
        assert result['checkpoint_observation']['reason_code'] == expected
        assert result['effect_scope'] == 'PREVIEW_ONLY' and result['delivery_accepted'] is False
        assert 'synthetic_provider_secret_marker' not in json.dumps(result)
        assert original == {'status': 'COMPLETE', 'detail': 'original task outcome is unchanged'}
        assert case['memory_files'] == before


def test_selected_event_actual_main_preserves_transport_and_notification_errors(monkeypatch):
    import io
    import sys
    from contextlib import redirect_stdout
    from services.python_supervisor import notifier

    statuses = ['EXECUTED_AWAITING_VALIDATION', 'DEFERRED', 'STOP_FLAG', 'EXECUTION_FAILED',
                'FINALIZATION_RECONCILIATION_REQUIRED', 'INTEGRITY_BLOCKED', 'notification-error']
    for status in statuses:
        with pytest.MonkeyPatch.context() as mp:
            _, root, files, request = _selected_event_memory_case(mp)
            path = root / 'selected-request.json'
            path.write_bytes(n05_consumer.canonical_json(request))
            calls = []
            def worker(enqueued):
                calls.append('owned provider boundary')
                if status == 'INTEGRITY_BLOCKED':
                    raise RuntimeError('PRIVATE_PROVIDER_BODY_MUST_NOT_ENTER_NOTIFICATION')
                return n05_observation(enqueued, 'DEFERRED' if status == 'notification-error' else status,
                    reason='PRIVATE_PROVIDER_BODY_MUST_NOT_ENTER_NOTIFICATION')
            mp.setattr(n05_cycle, '_worker', lambda selected: worker)
            if status == 'notification-error':
                mp.setattr(notifier, 'notify_file', lambda *a, **k: (_ for _ in ()).throw(OSError('owned notifier loss')))
            mp.setattr(sys, 'argv', ['cycle', '--request-json', str(path)])
            with redirect_stdout(io.StringIO()) as output:
                code = n05_cycle.main()
            result = json.loads(output.getvalue())
            expected = 'DEFERRED' if status == 'notification-error' else status
            assert result['status'] == expected
            assert result['retry_allowed'] is False and len(calls) == 1
            assert code == (0 if expected in {'DEFERRED', 'EXECUTED_AWAITING_VALIDATION'} else 2)
            assert 'PRIVATE_PROVIDER_BODY_MUST_NOT_ENTER_NOTIFICATION' in result['detail']
            assert 'PRIVATE_PROVIDER_BODY_MUST_NOT_ENTER_NOTIFICATION' not in json.dumps(result['notification'])
            assert result['notification']['effect_scope'] == 'PREVIEW_ONLY'
            assert not any('/SOS_OUTBOX/' in path.as_posix() or '/telemetry/night_supervisor/' in path.as_posix()
                           for path in files)


def test_selected_event_custom_exception_name_is_not_public_diagnostic(monkeypatch):
    from services.python_supervisor import notifier

    _, root, files, request = _selected_event_memory_case(monkeypatch)
    before = dict(files)
    private_error = type('synthetic_provider_secret_class', (Exception,), {})
    monkeypatch.setattr(notifier, 'preview_selected_event',
        lambda *a, **k: (_ for _ in ()).throw(private_error('synthetic error body')))
    original = {'status': 'DEFERRED', 'detail': 'original transport cause'}
    result = n05_cycle._preview_selected_event(root, request, original)
    assert result['reason'] == 'selected_event_preview_unavailable:Exception'
    assert result['canonical_integrity'] == 'UNKNOWN' and result['delivery_accepted'] is False
    assert original == {'status': 'DEFERRED', 'detail': 'original transport cause'}
    assert files == before


def test_selected_event_native_identity_mismatch_rejects_before_effects(monkeypatch):
    from dataclasses import replace

    _, case = _selected_event_memory_case(monkeypatch, native=True)
    request = json.loads(case['data']['request_json'])
    before = dict(case['memory_files'])
    for fault in ('requirement', 'transport', 'task', 'attempt', 'prompt', 'missing_context', 'private_root'):
        supplied = deepcopy(request)
        expected = case['context'].request
        context, reader = case['context'], case['reader']
        result = {'status': 'COMPLETE'}
        if fault == 'requirement': expected = replace(expected, request_sha256='f' * 64)
        elif fault == 'transport': result['request_sha256'] = expected.request_sha256
        elif fault in {'task', 'attempt', 'prompt'}:
            result[{'task': 'task_id', 'attempt': 'attempt_id', 'prompt': 'prompt_sha256'}[fault]] = 'wrong'
        elif fault == 'missing_context': context = None
        else: supplied['repo_root'] += '/.codex/forged'
        outcome = case['cycle']._preview_selected_event(case['root'], supplied, result,
            expected_request=expected, admitted_context=context, native_admission_reader=reader)
        assert outcome['canonical_integrity'] == 'UNKNOWN'
        assert outcome['delivery_accepted'] is False and outcome['effect_scope'] == 'PREVIEW_ONLY'
        assert case['memory_files'] == before


def test_selected_event_native_notification_failure_preserves_committed_outcome(monkeypatch):
    from automation.orchestration.claims.aios_task_claim_control import TaskClaimController
    from services.python_supervisor import notifier

    held, case = _selected_event_memory_case(monkeypatch, native=True)
    attempt = held._np_capture(case)
    assert held._np_recover(case, attempt)['result'] == 'COMPLETE'
    monkeypatch.setattr(TaskClaimController, 'guard', lambda *a, **k: case['data']['claim'])
    monkeypatch.setattr(notifier, 'preview_selected_event', lambda *a, **k: (_ for _ in ()).throw(OSError('owned preview loss')))
    adapter = case['cycle'].make_native_execution_adapter(case['root'], expected_request=case['context'].request,
        native_admission_reader=case['reader'], claim_controller=object.__new__(TaskClaimController), requested=case['requested'])
    result = adapter(case['data']['original_resolver_packet'])
    assert result['status'] == 'COMPLETE' and result['passed'] is True
    assert result['notification']['canonical_integrity'] == 'UNKNOWN'
    assert held._np_read(case) is not None


def test_selected_event_native_public_reader_requires_exact_current_publication(monkeypatch):
    from dataclasses import replace
    from datetime import datetime, timedelta, timezone
    from services.python_supervisor import notifier

    held, case = _selected_event_memory_case(monkeypatch, native=True)
    attempt = held._np_capture(case)
    assert held._np_recover(case, attempt)['result'] == 'COMPLETE'
    state = held._np_read(case)
    reader = notifier.public_reader(case['root'])
    args = {'expected_request': case['context'].request, 'admitted_context': case['context'],
            'native_admission_reader': case['reader']}
    accepted = reader.read_public_resume(case['root'], **args)
    assert accepted['integrity'] == 'VERIFIED' and accepted['freshness']['current'] is True
    assert accepted['goal'] == accepted['selected_action'] == accepted['reason_code'] == 'UNKNOWN'
    assert reader.read_public_resume(case['root'])['integrity'] == 'UNKNOWN'
    for fault in ('request', 'context', 'claim', 'latest', 'archive', 'completion', 'source'):
        with pytest.MonkeyPatch.context() as mp:
            supplied = dict(args)
            if fault == 'request': supplied['expected_request'] = replace(args['expected_request'], request_sha256='f' * 64)
            elif fault == 'context': supplied['admitted_context'] = None
            elif fault == 'claim':
                changed, changed_reader = held._np_admit_mutation(case, lambda value: value['claim'].update(attempt_id='other'))
                supplied.update(admitted_context=changed, native_admission_reader=changed_reader)
            else:
                latest = case['root'] / 'Reports/aios_resume' / case['owner'].LATEST_FILENAME
                archive = case['root'] / state['resume_state_paths']['timestamped']
                path = {'latest': latest, 'archive': archive,
                        'completion': archive.with_name(archive.stem + '.completion.json'),
                        'source': case['root'] / 'services/python_supervisor/notifier.py'}[fault]
                mp.setitem(case['memory_files'], path, b'{}')
            value = reader.read_public_resume(case['root'], **supplied)
            assert value['integrity'] == 'UNKNOWN' and value['execution_allowed'] is False
    accepted_at = datetime.strptime(accepted['accepted_at'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    for delta in (-1, 61):
        historical = reader.read_public_resume(case['root'], now=accepted_at + timedelta(seconds=delta), **args)
        assert historical['integrity'] == 'VERIFIED' and historical['freshness']['current'] is False
        assert notifier.status_from_state({'canonical_resume': historical}) == 'UNKNOWN'
        assert historical['accepted_at'] == accepted['accepted_at']


def n05_request(root, *, task="task-one", attempt="attempt-one"):
    root = root.resolve(); root.mkdir(parents=True, exist_ok=True)
    source = root / "safe/file.py"; source.parent.mkdir(exist_ok=True); source.write_text("before\n", encoding="utf-8")
    provider = root / "bin/codex.exe"; provider.parent.mkdir(exist_ok=True); provider.write_bytes(b"inert provider fixture - never executed")
    prompt_path = root / "prompt.md"; prompt_path.write_text(prompt_text()+"\n# café 雪 😀\n", encoding="utf-8")
    import shutil
    implementation_paths = list(n05_consumer.BOUND_IMPLEMENTATIONS)
    implementation_paths += ["automation/orchestration/cost/Test-AiOsCostCeiling.ps1", "automation/orchestration/lock/Test-AiOsFileLock.ps1"]
    for relative in implementation_paths:
        target=root/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(Path(__file__).resolve().parents[2]/relative,target)
    manifest = {relative: hashlib.sha256((root/relative).read_bytes()).hexdigest() for relative in implementation_paths}
    (root / "owned-policy.json").write_text('{"cost_ceiling_per_cycle_usd":1,"cost_ceiling_per_day_usd":10}',encoding="utf-8")
    digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    request = {"schema": "AIOS_RELAY_REQUEST.v1", "campaign_id": "campaign-fixture",
        "repository": "ai-rtony91/Ai_Os-Forex", "repository_id": "1227385337", "repo_root": str(root),
        "relay_root": str(root / "relay/owned-campaign"), "repository_identity": {"resolved": True,
            "repo_root": str(root), "git_dir": str(root / ".git"), "branch": "codex/fixture", "commit": "a" * 40},
        "task_id": task, "packet_id": "PACKET-1", "priority": "P1", "depends_on": [],
        "attempt_id": attempt, "attempt_number": 0, "max_attempts": 3,
        "claim_ref": {"owner": "TaskClaimController", "task_id": task, "acquired_at": "2026-10-17T14:00:00+00:00", "identity_sha256": "c" * 64},
        "prompt_path": str(prompt_path), "prompt_sha256": hashlib.sha256(prompt_path.read_bytes()).hexdigest(),
        "allowed_paths": ["safe/file.py"], "source_paths": ["safe/file.py", *manifest], "controller_metadata_paths": ["owned-policy.json"],
        "source_manifest": manifest, "source_manifest_sha256": digest(manifest), "validator_spec_sha256": "d" * 64,
        "provider": "codex", "provider_executable": str(provider), "provider_sha256": hashlib.sha256(provider.read_bytes()).hexdigest(),
        "provider_args": ["--no-daemon", "exec", "--sandbox", "workspace-write", "-"], "python_executable": __import__("sys").executable,
        "timeout_sec": 5, "cycle_id": "campaign-fixture", "policy_path": str(root / "owned-policy.json")}
    request['preservation_contract'] = n05_consumer.build_preservation_contract(request)
    return request


def n05_enqueue(request, *, dry_run=False):
    return n05_consumer.enqueue_prompt(Path(request["prompt_path"]), Path(request["relay_root"]), FLAGS,
        dry_run=dry_run, bound_request=request)


def n05_observation(enqueued, status="EXECUTED_AWAITING_VALIDATION", **extra):
    binding = enqueued["task"]["request_sha256"]
    request = json.loads(enqueued["task"]["request_json"])
    result = {**n05_consumer.request_binding(request,binding), "repo_root":request["repo_root"], "relay_root":request["relay_root"], "schema": "AIOS_RELAY_OBSERVATION.v1", "request_sha256": binding,
        "task_id": enqueued["task"]["task_id"], "packet_id": "PACKET-1", "attempt_id": enqueued["task"]["attempt_id"],
        "status": status, "reason": "", "authority_granted": False, **extra}
    outbox = Path(enqueued["task"]["relay_root"]) / "outbox"; outbox.mkdir(parents=True, exist_ok=True)
    process = dict(exit_code=0,child_exit_code=0,cleanup_state="CONFIRMED",root_exit_confirmed=True,tree_exit_confirmed=True,
        drains_completed=True,stdin_writer_joined=True,stdin_completed=True,timed_out=False,startup_failed=False,
        process_error_present=False,shape_valid=True,working_directory=request["repo_root"],stdin_bytes_written=len(enqueued["task"]["prompt_text"].encode("utf-8")),
        stdin_error_code=0,stdin_close_error_code=0,cleanup_error_code=0,cancellation_error_code=0)
    capture = {"schema":"AIOS_RELAY_EXECUTION.v1","binding":n05_consumer.request_binding(request,binding),
        "request_json":enqueued["task"]["request_json"],"packet_sha256":enqueued["packet_sha256"],"process":process,"authority_granted":False,"retry_allowed":False}
    capture_data=json.dumps(capture,sort_keys=True).encode();capture_path=outbox/(enqueued["task"]["id"]+".execution.json")
    capture_path.write_bytes(capture_data)
    result.update(execution_path=str(capture_path),execution_sha256=hashlib.sha256(capture_data).hexdigest(),retry_allowed=False)
    data = (json.dumps(result, sort_keys=True) + "\n").encode()
    path = outbox / (enqueued["task"]["id"] + ".result." + hashlib.sha256(data).hexdigest() + ".json")
    path.write_bytes(data)
    return {**result, "observation_path": str(path), "observation_sha256": hashlib.sha256(data).hexdigest()}


def test_n05_same_text_different_obligation_and_attempt_are_distinct(tmp_path):
    one = n05_request(tmp_path); two = deepcopy(one); two["task_id"] = two["claim_ref"]["task_id"] = "task-two"
    three = deepcopy(one); three["attempt_id"] = "attempt-two"; three["attempt_number"] = 1
    results = [n05_enqueue(value) for value in (one, two, three)]
    assert len({result["task"]["id"] for result in results}) == 3
    assert {result["task"]["task_id"] for result in results} == {"task-one", "task-two"}
    assert all(result["task"]["prompt_sha256"] == one["prompt_sha256"] for result in results)


def test_n05_same_pending_request_reconciles_and_conflict_preserves_bytes(tmp_path):
    request = n05_request(tmp_path); first = n05_enqueue(request)
    repeated = n05_enqueue(request)
    assert repeated["status"] == "EXISTING_REQUEST"
    path = Path(first["target"]); value = json.loads(path.read_bytes()); value["task_id"] = "forged"
    path.write_text(json.dumps(value), encoding="utf-8"); original = path.read_bytes()
    with pytest.raises(ValueError): n05_enqueue(request)
    assert path.read_bytes() == original


@pytest.mark.parametrize("slot,value", [("repo_root", "relative"), ("relay_root", "C:relative"),
    ("attempt_number", True), ("attempt_id", ""), ("source_manifest_sha256", "wrong"),
    ("provider", "custom"), ("provider_args", ["exec", "--dangerously-bypass-approvals-and-sandbox"]), ("validator_spec_sha256", None)])
def test_n05_invalid_request_rejects_before_writes(tmp_path, slot, value):
    request = n05_request(tmp_path); request[slot] = value
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    with pytest.raises(ValueError): n05_enqueue(request)
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_n05_bound_cycle_passes_request_and_never_completes_from_exit_or_done(tmp_path):
    request = n05_request(tmp_path); seen = []
    def worker(enqueued):
        seen.append(enqueued)
        # Even an exact transport done file is no requirement acceptance.
        target = Path(enqueued["target"]); done = Path(request["relay_root"]) / "done"; done.mkdir()
        target.replace(done / target.name)
        return n05_observation(enqueued)
    result = n05_cycle.run_self_consuming_cycle(generate=lambda: request, relay_root=Path(request["relay_root"]), invoke_worker=worker)
    assert len(seen) == 1 and seen[0]["task"]["task_id"] == request["task_id"]
    assert result.status == "EXECUTED_AWAITING_VALIDATION"
    assert result.task_id == request["task_id"] and result.attempt_id == request["attempt_id"]


@pytest.mark.parametrize("corruption", ["wrong_attempt", "wrong_request", "missing_readback", "complete_claim"])
def test_n05_cycle_rejects_unbound_or_false_completion_response(tmp_path, corruption):
    request = n05_request(tmp_path)
    def worker(enqueued):
        response = n05_observation(enqueued)
        if corruption == "wrong_attempt": response["attempt_id"] = "other"
        elif corruption == "wrong_request": response["request_sha256"] = "f" * 64
        elif corruption == "missing_readback": Path(response["observation_path"]).unlink()
        else: response["status"] = "COMPLETE"
        return response
    result = n05_cycle.run_self_consuming_cycle(generate=lambda: request, relay_root=Path(request["relay_root"]), invoke_worker=worker)
    assert result.status == "INTEGRITY_BLOCKED"


def test_n05_no_admitted_request_is_not_workflow_completion(tmp_path):
    result = n05_cycle.run_self_consuming_cycle(generate=lambda: None, relay_root=tmp_path / "relay")
    assert result.status == "NO_ADMITTED_WORK"


def test_n05_bound_dry_run_creates_no_transport_or_helper_output(tmp_path):
    request = n05_request(tmp_path)
    result = n05_cycle.run_self_consuming_cycle(generate=lambda: request, relay_root=Path(request["relay_root"]), dry_run=True,
        invoke_worker=lambda *a: (_ for _ in ()).throw(AssertionError("no dispatch")))
    assert result.status == "DRY_RUN"
    assert not Path(request["relay_root"]).exists()


def _n05_native(tmp_path, case, *, first_choice=True, second_choice=True):
    """Actual bound receiver/functions; inert process-result seam, private Job."""
    import base64
    import shutil
    from tests.orchestration.test_aios_validator_path_policy import _n02_owned_harness
    repo = Path(__import__('tempfile').mkdtemp(prefix='n5-')) / 'r'; request = n05_request(repo)
    helper = repo / 'automation/orchestration/relay/Invoke-AiOsRelayWorker.ps1'
    unrelated = repo / 'unrelated.task.json'; unrelated.write_bytes(b'UNTOUCHED unrelated packet')
    # Fixture inventory is explicit. No private queue payload is parsed.
    request['source_paths'].append('unrelated.task.json')
    if case == 'unknown_before': request['fixture_unknown_before'] = True
    if case.startswith('log_failure'):
        log=Path(request['relay_root'])/'logs/output_validator.log'
        log.parent.mkdir(parents=True,exist_ok=True); log.write_text('owned original log\n',encoding='utf-8')
    # Recreate exact request after adding only owned fixture inventory.
    enqueued = n05_enqueue(request)
    encoded = base64.b64encode(json.dumps(dict(request=request, enqueued=enqueued, case=case, first_choice=first_choice, second_choice=second_choice)).encode()).decode()
    harness = repo / 'owned_n05.ps1'
    harness.write_text(r'''$ErrorActionPreference='Stop'; Set-StrictMode -Version Latest
if (-not [string]::Equals([Console]::In.ReadLine(),'owned-job-ready',[StringComparison]::Ordinal)) { exit 125 }
$inputData=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('ENCODED')) | ConvertFrom-Json
$worker='WORKER'
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($worker,[ref]$tokens,[ref]$errors)
if($errors.Count){throw $errors[0]}
foreach($def in $ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst]},$false)) {
    Set-Item -Path ('Function:'+ $def.Name) -Value $def.Body.GetScriptBlock()
}
if(-not(Get-Command Invoke-AiOsBoundRelayRequest -ErrorAction SilentlyContinue)) {
    [Console]::WriteLine('N05_RESULT_BASE64:'+ [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes('{"missing_bound_entry":true}')));exit 0
}
$script:priorObservation=''; $script:calls=0; $script:metadataCalls=0; $script:fixtureRequest=$inputData.request; $script:case=$inputData.case
function Get-AiOsBoundRepositoryEvidence {
    param($Request)
    $script:metadataCalls++
    $paths=@();if($script:priorObservation){$paths=@($script:priorObservation)}
    if($script:case -eq 'unknown_before'){$paths=@('uninspectable/private-unlisted.bin')}
    return [pscustomobject]@{identity=$Request.repository_identity;paths=$paths;complete=$true;errors=@()}
}
function Test-AiOsBoundPreflight {param($Request,$Binding,$LogPath)
    if($script:case -eq 'preflight') {return [pscustomobject]@{ok=$false;reason='MISSING_SELECTED_TOOL'}}
    return [pscustomobject]@{ok=$true;reason='';binding=$Binding;authority_granted=$false}
}
function Test-AiOsBoundCostAndLock {param($Request,$LedgerPath)
    if($script:case -eq 'cost'){return [pscustomobject]@{ok=$false;defer=$false;reason='COST_LIMIT'}}
    return [pscustomobject]@{ok=$true;defer=($script:case -in @('defer','defer_resume'));reason='RECENT_EXTERNAL_WRITE'}
}
function Invoke-AiOsBoundProvider {param($Request,$PromptText)
    $script:calls++
    if($script:case -eq 'metadata_delta'){[IO.File]::WriteAllText($Request.policy_path,'provider changed controller metadata')}
    if($script:case -eq 'source_delta'){[IO.File]::WriteAllText((Join-Path $Request.repo_root 'safe/file.py'),'allowed change')}
    if($script:case -eq 'log_failure_scope'){[IO.File]::WriteAllText($Request.policy_path,'provider changed controller metadata')}
    if($script:case.StartsWith('log_failure')){
        $log=Join-Path $Request.relay_root 'logs/output_validator.log'
        [IO.File]::SetAttributes($log,([IO.File]::GetAttributes($log) -bor [IO.FileAttributes]::ReadOnly))
    }
    $result=[pscustomobject]@{exit_code=0;child_exit_code=0;stdout='PRIVATE_CHILD_OUTPUT_NOT_PERSISTED';stderr='';duration_sec=0.1;
        executable=$Request.provider_executable;arguments=$Request.provider_args;command_line_arguments='exec --sandbox workspace-write -';working_directory=$Request.repo_root;
        timed_out=$false;startup_failed=$false;root_process_id=123;cleanup_state='CONFIRMED';root_exit_confirmed=$true;tree_exit_confirmed=$true;drains_completed=$true;
        retry_allowed=$false;stdin_completed=$true;stdin_writer_joined=$true;stdin_bytes_written=([Text.Encoding]::UTF8.GetByteCount($PromptText));stdin_error_code=0;stdin_close_error_code=0;
        stdout_truncated=$false;stderr_truncated=$false;cleanup_error_code=0;cancellation_error_code=0;process_error=$null}
    if($script:case -in @('incomplete','log_failure_process')){$result.exit_code='INPUT_INCOMPLETE';$result.stdin_completed=$false}
    if($script:case -eq 'cleanup'){$result.cleanup_state='UNRESOLVED';$result.tree_exit_confirmed=$false}
    if($script:case -eq 'wrong_bool'){$result.stdin_writer_joined='true'}
    return $result
}
function Add-AiOsBoundCost {param($Request,$Binding,$LedgerPath,$ProviderResult)
    if($script:case -eq 'finalizer'){throw 'owned finalizer fault'}
    return [pscustomobject]@{ok=$true;binding=$Binding;authority_granted=$false}
}
$argsBound=@{RepoRoot=$inputData.request.repo_root;RelayRoot=$inputData.request.relay_root;RequestPath=$inputData.enqueued.target;
    ExpectedPacketSha256=$inputData.enqueued.packet_sha256;PythonExecutable=$inputData.request.python_executable;ExplicitApplyChoice=$inputData.first_choice}
if($inputData.first_choice -is [string] -and $inputData.first_choice -ceq '__omit_fixture_only__'){$argsBound.Remove('ExplicitApplyChoice')}
$first=Invoke-AiOsBoundRelayRequest @argsBound
if($script:case -eq 'defer_resume'){$script:case='success';$script:priorObservation=$first.observation_path.Substring($inputData.request.repo_root.Length+1).Replace('\','/')}
# Recovery uses the exact selected running path, never scans a queue.
$running=Join-Path (Join-Path $inputData.request.relay_root 'running') (Split-Path $inputData.enqueued.target -Leaf)
if(Test-Path -LiteralPath $running){$argsBound.RequestPath=$running}
$capturePath=Join-Path $inputData.request.relay_root ('outbox/'+$inputData.enqueued.task.id+'.execution.json')
$captureBefore=if([IO.File]::Exists($capturePath)){[Convert]::ToBase64String([IO.File]::ReadAllBytes($capturePath))}else{''}
$argsBound.ExplicitApplyChoice=$inputData.second_choice
$second=Invoke-AiOsBoundRelayRequest @argsBound
$captureAfter=if([IO.File]::Exists($capturePath)){[Convert]::ToBase64String([IO.File]::ReadAllBytes($capturePath))}else{''}
$answer=[ordered]@{first=$first;second=$second;calls=$script:calls;metadata_calls=$script:metadataCalls;capture_before=$captureBefore;capture_after=$captureAfter}
$json=$answer|ConvertTo-Json -Depth 25 -Compress
[Console]::WriteLine('N05_RESULT_BASE64:'+ [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json)))
'''.replace('ENCODED', encoded).replace('WORKER', str(helper).replace("'", "''")), encoding='utf-8')
    output, active = _n02_owned_harness(harness, repo, timeout=35)
    assert active == 0
    result = json.loads(base64.b64decode(output.split('N05_RESULT_BASE64:', 1)[1].strip()))
    assert 'missing_bound_entry' not in result, 'actual worker has no exact bound request entry'
    assert unrelated.read_bytes() == b'UNTOUCHED unrelated packet'
    assert not (Path(request['relay_root']) / 'approvals').exists()
    return result, request


@pytest.mark.parametrize('case,status,launches', [('success','EXECUTED_AWAITING_VALIDATION',1),
    ('source_delta','EXECUTED_AWAITING_VALIDATION',1),('metadata_delta','SAFETY_INTEGRITY_BLOCK',1),
    ('incomplete','EXECUTION_FAILED',1),('cleanup','SAFETY_INTEGRITY_BLOCK',1),('wrong_bool','SAFETY_INTEGRITY_BLOCK',1),
    ('finalizer','FINALIZATION_RECONCILIATION_REQUIRED',1),('preflight','DEFERRED',0),('cost','DEFERRED',0),
    ('defer','DEFERRED',0),('unknown_before','REQUEST_REJECTED',0)])
def test_n05_native_exact_receiver_and_no_replay(tmp_path, case, status, launches):
    result, request = _n05_native(tmp_path, case)
    assert result['first']['status'] == status, result
    assert result['calls'] == launches
    assert result['first']['authority_granted'] is False
    assert result['first']['attempt_id'] == request['attempt_id']
    if launches:
        assert result['second']['status'] == 'FINALIZATION_RECONCILIATION_REQUIRED', result
        capture = Path(result['first']['execution_path'])
        saved = json.loads(capture.read_bytes())
        assert saved['binding']['claim_identity_sha256'] == request['claim_ref']['identity_sha256']
        assert saved['binding']['attempt_number'] == request['attempt_number']
        assert 'PRIVATE_CHILD_OUTPUT' not in capture.read_text()


@pytest.mark.parametrize("corruption",["cleanup","missing_bool","string_bool","input","drains","byte_count","cwd","missing_capture"])
def test_n05_cycle_checks_capture_process_not_status_only(tmp_path,corruption):
    request=n05_request(tmp_path)
    def worker(enqueued):
        response=n05_observation(enqueued)
        capture_path=Path(response["execution_path"]);capture=json.loads(capture_path.read_bytes());process=capture["process"]
        if corruption=="cleanup":process["cleanup_state"]="UNRESOLVED"
        elif corruption=="missing_bool":process.pop("tree_exit_confirmed")
        elif corruption=="string_bool":process["tree_exit_confirmed"]="false"
        elif corruption=="input":process["stdin_completed"]=False
        elif corruption=="drains":process["drains_completed"]=False
        elif corruption=="byte_count":process["stdin_bytes_written"]=1
        elif corruption=="cwd":process["working_directory"]=str(tmp_path/"foreign")
        else:response["execution_path"]=str(tmp_path/"missing.json")
        if corruption!="missing_capture":
            data=json.dumps(capture).encode();capture_path.write_bytes(data);response["execution_sha256"]=hashlib.sha256(data).hexdigest()
        saved={k:v for k,v in response.items() if k not in {"observation_path","observation_sha256"}}
        data=json.dumps(saved).encode();Path(response["observation_path"]).write_bytes(data);response["observation_sha256"]=hashlib.sha256(data).hexdigest()
        return response
    result=n05_cycle.run_self_consuming_cycle(generate=lambda:request,relay_root=Path(request["relay_root"]),invoke_worker=worker)
    assert result.status=="INTEGRITY_BLOCKED",result


@pytest.mark.parametrize('kind',['private_prompt','private_manifest','approval_transport'])
def test_n05_private_paths_reject_before_open(tmp_path,monkeypatch,kind):
    request=n05_request(tmp_path); original_read=Path.read_bytes
    if kind=='private_prompt':
        target=tmp_path/'.env';target.write_bytes(Path(request['prompt_path']).read_bytes());request['prompt_path']=str(target)
    elif kind=='private_manifest':
        target=tmp_path/'.aws/mock';target.parent.mkdir();target.write_bytes(b'owned private-shaped fixture')
        request['source_manifest']['.aws/mock']=hashlib.sha256(target.read_bytes()).hexdigest()
        request['source_manifest_sha256']=hashlib.sha256(n05_consumer.canonical_json(request['source_manifest'])).hexdigest()
    else:
        enqueued=n05_enqueue(request);target=Path(request['relay_root'])/'approvals'/Path(enqueued['target']).name
        target.parent.mkdir();target.write_bytes(Path(enqueued['target']).read_bytes())
    reads=[]
    def guarded(path):
        if path==target:reads.append(str(path))
        return original_read(path)
    monkeypatch.setattr(Path,'read_bytes',guarded)
    with pytest.raises(ValueError):
        if kind=='approval_transport':n05_consumer.read_bound_packet(str(target),enqueued['packet_sha256'],request['repo_root'],request['relay_root'])
        else:n05_enqueue(request)
    assert reads==[]


def test_n05_worker_host_uses_owned_adapter_and_typed_host_evidence(tmp_path,monkeypatch):
    from types import SimpleNamespace
    source=Path(__file__).resolve().parents[2]
    request={'repo_root':str(source),'relay_root':str(source/'relay/not-activated'), 'python_executable':__import__('sys').executable,'timeout_sec':5}
    task={'request_json':json.dumps(request)}
    observed={'status':'DEFERRED','authority_granted':False};seen=[]
    host=dict(exit_code=0,child_exit_code=0,cleanup_state='CONFIRMED',root_exit_confirmed=True,tree_exit_confirmed=True,
        drains_completed=True,stdin_writer_joined=True,stdin_completed=True,timed_out=False,startup_failed=False,process_error_present=False,
        shape_valid=True,working_directory=str(source),stdin_bytes_written=0,stdin_error_code=0,stdin_close_error_code=0,cleanup_error_code=0,cancellation_error_code=0)
    def run(argv,**kwargs):
        seen.append(argv)
        return SimpleNamespace(returncode=0,stdout=json.dumps({'host_process':host,'observation_json':json.dumps(observed)}))
    monkeypatch.setattr(n05_cycle,'validate_bound_request',lambda value:value)
    monkeypatch.setattr(n05_cycle.shutil,'which',lambda name:r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe')
    monkeypatch.setattr(n05_cycle.subprocess,'run',run)
    callback=n05_cycle._worker(source)
    assert callback({'task':task,'target':str(tmp_path/'selected.task.json'),'packet_sha256':'e'*64})==observed
    command=seen[0]
    assert '-EncodedCommand' in command
    code=__import__('base64').b64decode(command[-1]).decode('utf-16-le')
    assert 'Invoke-AiOsCliProcess' in code and 'GetScriptBlock' in code
    host['tree_exit_confirmed']='true'
    with pytest.raises(ValueError):callback({'task':task,'target':str(tmp_path/'selected.task.json'),'packet_sha256':'e'*64})


def test_n05_same_attempt_resumes_after_defer_with_prior_observation(tmp_path):
    result,request=_n05_native(tmp_path,"defer_resume")
    assert result["first"]["status"]=="DEFERRED",result
    assert result["second"]["status"]=="EXECUTED_AWAITING_VALIDATION",result
    assert result["calls"]==1
    assert result["second"]["attempt_id"]==request["attempt_id"]

import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import pytest

N05_HELPER_SOURCE_REPO = Path(__file__).resolve().parents[2]
def _n02_owned_harness(*args, **kwargs):
    # Native companion fixtures require their actual helper only when called.
    # Offline fake-only cases must still collect without that separate fixture.
    from tests.orchestration.test_aios_validator_path_policy import _n02_owned_harness as owned_harness
    return owned_harness(*args, **kwargs)

N05_HELPER_DEFINITIONS = {
 'preflight': ('automation/orchestration/preflight/Test-AiOsToolPreflight.ps1', 'Test-AiOsToolPreflight'),
 'cost': ('automation/orchestration/cost/Add-AiOsCostLedgerEntry.ps1', 'Add-AiOsCostLedgerEntry'),
 'output': ('automation/orchestration/validators/output/Test-AiOsWorkerOutput.DRY_RUN.ps1', 'Test-AiOsWorkerOutput'),
}

def _n05_helper_binding():
    return dict(request_sha256='a'*64, task_id='task-one', packet_id='packet-one', attempt_id='attempt-one',
                attempt_number=0, claim_task_id='task-one', claim_acquired_at='2026-10-17T00:00:00Z',
                claim_identity_sha256='b'*64, campaign_id='campaign-one')

def _n05_run_helper(kind: str, prepare=None, *, evidence_as_hashtable=False, fixture_setup='', entry_mode='named', source_transform=None):
    parent = Path(tempfile.gettempdir()) / 'n05h'
    parent.mkdir(exist_ok=True)
    repo = Path(tempfile.mkdtemp(prefix='n5-', dir=parent)) / 'r'
    relay = repo/'relay/campaign-one'
    relay.mkdir(parents=True)
    relative, function = N05_HELPER_DEFINITIONS[kind]
    helper = repo/relative
    helper.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(N05_HELPER_SOURCE_REPO/relative, helper)
    if source_transform: helper.write_text(source_transform(helper.read_text(encoding='utf-8')),encoding='utf-8')
    if kind == 'preflight':
        for child in ('timeout/Invoke-AiOsCliWithTimeout.ps1', 'validator_chain_runner/Invoke-AiOsValidatorChain.DRY_RUN.ps1'):
            target=repo/'automation/orchestration'/child
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(N05_HELPER_SOURCE_REPO/'automation/orchestration'/child, target)
    common=dict(RepoRoot=str(repo), RelayRoot=str(relay), CampaignBinding=_n05_helper_binding())
    if kind == 'preflight':
        params=dict(common, Tools=[], VersionTimeoutSec=1, LogPath=str(relay/'logs/preflight.log'))
    elif kind == 'cost':
        params=dict(common, LedgerPath=str(relay/'logs/cost.jsonl'), CycleId='cycle-one', Cost=0.1,
                    PacketId='packet-one', Worker='codex', Estimated=True, EstimateReason='Bounded estimate', InputTokens=0, OutputTokens=0)
    else:
        safe=repo/'safe/file.py'; safe.parent.mkdir(); safe.write_bytes(b'original')
        params=dict(common, LogPath=str(relay/'logs/output.log'), PacketId='packet-one',
                    AllowedPaths=['safe/file.py'], RunStartUtc='2099-01-01T00:00:00Z',
                    BeforeManifest={'safe/file.py':hashlib.sha256(b'original').hexdigest()}, ControllerMetadataPaths=[],
                    ExpectedStatusParserSha256='c'*64,
                    ChangedPathsEvidence=dict(complete=True, repo_root=str(repo), parser_source_sha256='c'*64,
                                              before_paths=['safe/file.py'], after_paths=['safe/file.py'], errors=[]))
    if prepare:
        prepare(repo, relay, params)
    encoded=base64.b64encode(json.dumps(params).encode()).decode()
    wrapper=helper.parent/'owned-probe.ps1'
    quoted=str(helper).replace("'", "''")
    evidence_conversion = "$copy=@{}; foreach($p in $parameters['ChangedPathsEvidence'].PSObject.Properties) { $copy[$p.Name]=$p.Value }; $parameters['ChangedPathsEvidence']=$copy" if evidence_as_hashtable else ''
    wrapper.write_text(f"""$ErrorActionPreference='Stop'
if (-not [string]::Equals([Console]::In.ReadLine(),'owned-job-ready',[StringComparison]::Ordinal)) {{ exit 125 }}
Set-StrictMode -Version Latest
$tokens=$null; $errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile('{quoted}',[ref]$tokens,[ref]$errors)
if ($errors.Count) {{ throw $errors[0] }}
$definitions=@($ast.EndBlock.Statements | Where-Object {{ $_ -is [Management.Automation.Language.FunctionDefinitionAst] }})
foreach($definition in $definitions) {{
    Set-Item -Path ('Function:'+ $definition.Name) -Value $definition.Body.GetScriptBlock()
}}
$request=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded}')) | ConvertFrom-Json
$parameters=@{{}}
foreach($property in $request.PSObject.Properties) {{ $parameters[$property.Name]=$property.Value }}
if ($parameters.ContainsKey('RunStartUtc')) {{ $parameters['RunStartUtc']=[datetime]$parameters['RunStartUtc'] }}
{evidence_conversion}
{fixture_setup}
if ('{entry_mode}' -ceq 'direct') {{
    $run= & '{quoted}' @parameters
}} elseif (Get-Command '{function}' -CommandType Function -ErrorAction SilentlyContinue) {{
    $run={function} @parameters
}} else {{
    foreach($p in $parameters.GetEnumerator()) {{ Set-Variable -Name $p.Key -Value $p.Value }}
    $body=($ast.EndBlock.Statements | Where-Object {{ $_ -isnot [Management.Automation.Language.FunctionDefinitionAst] }} | ForEach-Object {{ $_.Extent.Text }}) -join [Environment]::NewLine
    $bodyFile=Join-Path $PSScriptRoot 'owned-original-body.ps1'
    [IO.File]::WriteAllText($bodyFile,$body,[Text.UTF8Encoding]::new($false))
    $run= & $bodyFile
}}
[Console]::WriteLine([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($run | ConvertTo-Json -Depth 8 -Compress))))
""", encoding='ascii')
    stdout,active=_n02_owned_harness(wrapper, repo, timeout=15)
    assert active == 0
    result=json.loads(base64.b64decode(stdout.strip()).decode())
    (repo/'result.json').write_text(json.dumps(dict(result=result,outer_job_active=active), indent=2), encoding='utf-8')
    return result,repo,relay

def test_n05_cost_uses_only_explicit_bound_ledger():
    result,repo,relay=_n05_run_helper('cost')
    assert (relay/'logs/cost.jsonl').exists()
    assert not (repo/'control/mode/cost_ledger.jsonl').exists()
    entry=json.loads((relay/'logs/cost.jsonl').read_text(encoding='utf-8'))
    assert entry['binding'] == _n05_helper_binding() and entry['cost_usd'] == 0.1
    assert result['ok'] is True and result['authority_granted'] is False

def test_n05_preflight_invalid_selection_writes_no_global_log():
    result,repo,_=_n05_run_helper('preflight')
    assert result['ok'] is False
    assert not (repo/'relay/logs/preflight.log').exists()

def test_n05_output_detects_same_mtime_outside_scope_byte_delta():
    def prepare(repo,relay,params):
        params['AllowedPaths']=['safe/other.py']
        params['BeforeManifest']['safe/other.py']=None
        target=repo/'safe/file.py'; target.write_bytes(b'changed')
        os.utime(target, (1000000000,1000000000))
    result,_,_=_n05_run_helper('output',prepare)
    assert result['pass'] is False and 'safe/file.py' in result['violations']

def test_n05_selected_inert_version_and_bound_log():
    result,repo,relay=_n05_run_helper('preflight',lambda r,i,p:p.update(Tools=[sys.executable],VersionTimeoutSec=3))
    assert result['ok'] is True and result['authentication_checked'] is False
    assert result['binding'] == _n05_helper_binding() and result['checks'][0]['cleanup_state']=='CONFIRMED'
    assert (relay/'logs/preflight.log').exists() and not (repo/'relay/logs/preflight.log').exists()

def test_n05_provider_metadata_delta_is_not_exempted():
    def prepare(repo,relay,params):
        path=relay/'logs/controller.json'; path.parent.mkdir(); path.write_text('changed')
        rel=path.relative_to(repo).as_posix()
        params['BeforeManifest'][rel]=hashlib.sha256(b'original').hexdigest()
        params['ControllerMetadataPaths']=[rel]
        params['ChangedPathsEvidence']['after_paths'].append(rel)
    result,_,_=_n05_run_helper('output',prepare)
    assert result['pass'] is False and result['violation_reason']=='CONTROLLER_METADATA_CHANGED_BY_PROVIDER'

def test_n05_output_accepts_native_hashtable_evidence_without_mutation():
    result,_,_=_n05_run_helper('output',evidence_as_hashtable=True)
    assert result['pass'] is True and result['authority_granted'] is False

@pytest.mark.parametrize('mutation', ['coverage','parser','incomplete','private','root'])
def test_n05_output_requires_complete_raw_parser_coverage(mutation):
    def prepare(repo,relay,params):
        evidence=params['ChangedPathsEvidence']
        if mutation=='coverage': evidence['after_paths'].append('outside/new.py')
        elif mutation=='private': evidence['after_paths'].append('approvals/do-not-open.json')
        elif mutation=='parser': evidence['parser_source_sha256']='d'*64
        elif mutation=='incomplete': evidence['complete']=False
        else: evidence['repo_root']=str(repo/'wrong')
    result,_,_=_n05_run_helper('output',prepare)
    assert result['pass'] is False

@pytest.mark.parametrize('destination',['outside','traversal','unc','drive_relative'])
def test_n05_cost_rejects_escaping_destination_before_writes(destination):
    def prepare(repo,relay,params):
        params['LedgerPath']={'outside':str(repo/'outside.jsonl'),'traversal':str(relay/'..'/'escape.jsonl'),
                              'unc':r'\\localhost\fake\cost.jsonl','drive_relative':'C:cost.jsonl'}[destination]
    result,repo,relay=_n05_run_helper('cost',prepare)
    assert result['ok'] is False
    assert not list(relay.rglob('*.jsonl')) and not (repo/'outside.jsonl').exists()

@pytest.mark.parametrize('operation', ['allowed_change','create','delete','rename','copy'])
def test_n05_output_tracks_actual_byte_manifest_file_lifecycle(operation):
    def prepare(repo,relay,params):
        target=repo/'safe/file.py'
        if operation=='allowed_change': target.write_bytes(b'changed')
        elif operation=='create':
            params['BeforeManifest']['safe/new.py']=None
            params['AllowedPaths'].append('safe/new.py')
            params['ChangedPathsEvidence']['after_paths'].append('safe/new.py')
            (repo/'safe/new.py').write_bytes(b'new')
        elif operation=='delete': target.unlink()
        else:
            params['BeforeManifest']['safe/new.py']=None
            params['AllowedPaths'].append('safe/new.py')
            params['ChangedPathsEvidence']['after_paths'].append('safe/new.py')
            if operation=='rename': target.rename(repo/'safe/new.py')
            else: shutil.copyfile(target,repo/'safe/new.py')
    result,_,_=_n05_run_helper('output',prepare)
    assert result['pass'] is True and result['requirement_acceptance'] is False
    expected={'allowed_change':['safe/file.py'],'create':['safe/new.py'],'delete':['safe/file.py'],
              'rename':['safe/file.py','safe/new.py'],'copy':['safe/new.py']}[operation]
    assert sorted(result['touched']) == expected

@pytest.mark.parametrize('kind',['preflight','cost','output'])
def test_n05_malformed_binding_cannot_write_or_grant_authority(kind):
    def prepare(repo,relay,params): params['CampaignBinding']['attempt_number']=True
    result,repo,relay=_n05_run_helper(kind,prepare)
    assert result.get('ok',result.get('pass')) is False and result['authority_granted'] is False
    assert not (relay/'logs').exists() and not (repo/'control').exists() and not (repo/'relay/logs').exists()

def test_n05_preflight_missing_selected_tool_is_local_version_failure():
    result,repo,relay=_n05_run_helper('preflight',lambda r,i,p:p.update(Tools=['n05-absent-owned-tool']))
    assert result['ok'] is False and result['missing']==['n05-absent-owned-tool']
    assert result['authentication_checked'] is False and result['unauth']==[]
    assert (relay/'logs/preflight.log').exists() and not (repo/'relay/logs/preflight.log').exists()

def test_n05_reparse_destination_is_rejected_before_ledger_creation():
    def prepare(repo,relay,params): params['LedgerPath']=str(relay/'jump/escaped.jsonl')
    setup="""$outside=Join-Path $parameters['RepoRoot'] 'outside'
[void][IO.Directory]::CreateDirectory($outside)
New-Item -ItemType Junction -Path (Join-Path $parameters['RelayRoot'] 'jump') -Target $outside | Out-Null"""
    result,repo,relay=_n05_run_helper('cost',prepare,fixture_setup=setup)
    assert result['ok'] is False and 'Reparse path rejected' in result['detail']
    assert not (repo/'outside/escaped.jsonl').exists()

@pytest.mark.parametrize('kind',['preflight','cost','output'])
def test_n05_legacy_profile_retains_its_existing_owned_fixture_behavior(kind):
    def prepare(repo,relay,params):
        for key in ['CampaignBinding','RelayRoot','LogPath','LedgerPath','BeforeManifest','ControllerMetadataPaths','ChangedPathsEvidence','ExpectedStatusParserSha256']:
            params.pop(key,None)
        if kind!='output': params.pop('RepoRoot',None)
    result,repo,_=_n05_run_helper(kind,prepare)
    if kind=='preflight':
        assert result['ok'] is True and (repo/'relay/logs/preflight.log').exists()
    elif kind=='cost':
        assert result['cost_usd']==0.1 and (repo/'control/mode/cost_ledger.jsonl').exists()
    else:
        assert result['pass'] is True and not (repo/'relay/logs/output_validator.log').exists()
        assert result['diagnostic_write_requested'] is False

def test_n05_preflight_version_timeout_confirms_owned_cleanup():
    def prepare(repo,relay,params):
        tool=repo/'inert-version.ps1'
        tool.write_text("[Console]::WriteLine('INERT_VERSION'); Start-Sleep -Seconds 30\n",encoding='ascii')
        params.update(Tools=[str(tool)],VersionTimeoutSec=1)
    result,_,_=_n05_run_helper('preflight',prepare)
    assert result['ok'] is False and result['authentication_checked'] is False
    assert result['checks'][0]['exit_code']=='TIMEOUT_EXCEEDED'
    assert result['checks'][0]['cleanup_state']=='CONFIRMED'
    assert result['checks'][0]['root_exit_confirmed'] is True and result['checks'][0]['tree_exit_confirmed'] is True

@pytest.mark.parametrize('kind',['preflight','cost','output'])
def test_n05_actual_owner_utc_claim_timestamp_round_trips_exactly(kind):
    admitted='2026-10-17T00:00:00.123456+00:00'
    def prepare(repo,relay,params):
        params['CampaignBinding']['claim_acquired_at']=admitted
        if kind=='preflight': params.update(Tools=[sys.executable],VersionTimeoutSec=3)
    result,_,_=_n05_run_helper(kind,prepare)
    assert result.get('ok',result.get('pass')) is True
    assert result['binding']['claim_acquired_at']==admitted

@pytest.mark.parametrize('kind',['preflight','cost','output'])
def test_n05_noncanonical_nonzero_offset_binding_is_rejected_before_writes(kind):
    def prepare(repo,relay,params): params['CampaignBinding']['claim_acquired_at']='2026-10-17T01:00:00+01:00'
    result,repo,relay=_n05_run_helper(kind,prepare)
    assert result.get('ok',result.get('pass')) is False
    assert not (relay/'logs').exists() and not (repo/'control').exists()


def _n05_c4_resave(response, saved=None):
    value=saved if saved is not None else {k:v for k,v in response.items() if k not in {'observation_path','observation_sha256'}}
    raw=json.dumps(value,sort_keys=True).encode();Path(response['observation_path']).write_bytes(raw)
    response['observation_sha256']=hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize('location',['returned','saved','capture'])
def test_n05_readback_preserves_raw_binding_and_flag_types(tmp_path,location):
    fields={'request_sha256':'a'*64,'task_id':'task-one','packet_id':'PACKET-1','attempt_id':'attempt-one',
        'attempt_number':0,'claim_task_id':'task-one','claim_acquired_at':'2026-10-17T14:00:00+00:00',
        'claim_identity_sha256':'c'*64,'campaign_id':'campaign-fixture','authority_granted':False,'retry_allowed':False}
    for field,example in fields.items():
        aliases=[[],[example],{'value':example},None]
        aliases += [False,0.0,'0'] if field=='attempt_number' else ([0,0.0,'false',True] if field.endswith('granted') or field=='retry_allowed' else [False,0.0])
        for index,value in enumerate(aliases):
            request=n05_request(tmp_path/(field+'-'+str(index)));enqueued=n05_enqueue(request);response=n05_observation(enqueued)
            if location=='returned':response[field]=value
            elif location=='saved':
                saved={k:v for k,v in response.items() if k not in {'observation_path','observation_sha256'}};saved[field]=value;_n05_c4_resave(response,saved)
            else:
                path=Path(response['execution_path']);capture=json.loads(path.read_bytes())
                target=capture if field in {'authority_granted','retry_allowed'} else capture['binding']
                target[field]=value;raw=json.dumps(capture).encode();path.write_bytes(raw)
                response['execution_sha256']=hashlib.sha256(raw).hexdigest();_n05_c4_resave(response)
            with pytest.raises((ValueError,TypeError,KeyError)):n05_cycle.verify_observation(enqueued,response)


@pytest.mark.parametrize('slot',['manifest','prompt','policy'])
@pytest.mark.parametrize('relative',['config/.env','config/.env.local','.aws/credentials','.codex/private.json'])
def test_n05_every_private_input_rejects_before_payload_read(tmp_path,monkeypatch,slot,relative):
    request=n05_request(tmp_path);path=tmp_path/relative;path.parent.mkdir(parents=True,exist_ok=True)
    original=Path.read_bytes;path.write_bytes(original(Path(request['prompt_path'])) if slot=='prompt' else b'owned dummy data')
    if slot=='manifest':
        request['source_manifest'][relative]=hashlib.sha256(original(path)).hexdigest();request['source_manifest_sha256']=hashlib.sha256(n05_consumer.canonical_json(request['source_manifest'])).hexdigest()
    else:request['prompt_path' if slot=='prompt' else 'policy_path']=str(path)
    reads=[]
    def guarded(candidate):
        if candidate==path:reads.append(str(candidate));raise AssertionError('private-shaped bytes must stay unopened')
        return original(candidate)
    monkeypatch.setattr(Path,'read_bytes',guarded)
    with pytest.raises(ValueError):n05_consumer.validate_bound_request(request)
    assert reads==[]


def test_n05_double_capture_save_failure_preserves_both_causes_and_pending_evidence(tmp_path):
    import inspect
    source=inspect.getsource(_n05_native);marker='$first=Invoke-AiOsBoundRelayRequest @argsBound';assert source.count(marker)==1
    inject=r'''
$script:originalWriter=${function:Write-AiOsBoundBytes}
function Write-AiOsBoundBytes {
 param([string]$Path,[string]$Under,[byte[]]$Bytes,[switch]$AllowIdentical)
 if($Path.EndsWith('.execution.json',[StringComparison]::Ordinal)){throw 'C4_PRIMARY_CAPTURE_SAVE'}
 if($Path.Contains('.execution-recovery.')){throw 'C4_SECONDARY_RECOVERY_SAVE'}
 & $script:originalWriter -Path $Path -Under $Under -Bytes $Bytes -AllowIdentical:$AllowIdentical
}
'''
    namespace=dict(globals());exec(compile(source.replace(marker,inject+'\n'+marker),str(tmp_path/'owned-double-save-fixture.py'),'exec'),namespace)
    result,request=namespace['_n05_native'](tmp_path,'success');first=result['first']
    assert first['status']=='FINALIZATION_RECONCILIATION_REQUIRED'
    text=json.dumps(first);assert 'C4_PRIMARY_CAPTURE_SAVE' in text and 'C4_SECONDARY_RECOVERY_SAVE' in text
    assert first['pending_capture']['binding']['attempt_id']==request['attempt_id']
    assert first['pending_capture']['process']['stdin_completed'] is True
    assert 'PRIVATE_CHILD_OUTPUT' not in text
    durable=json.loads(Path(first['observation_path']).read_bytes())
    assert durable['pending_capture']==first['pending_capture']
    assert result['calls']==1 and result['second']['status']=='SAFETY_INTEGRITY_BLOCK'


def test_n05_actual_ps_readback_strict_boundary_all_fields_and_flags(tmp_path):
    from tests.orchestration.test_aios_validator_path_policy import _n02_owned_harness
    import tempfile
    root=Path(tempfile.mkdtemp(prefix='n5typed-'));worker=Path(__file__).resolve().parents[2]/'automation/orchestration/relay/Invoke-AiOsRelayWorker.ps1'
    binding=dict(request_sha256='a'*64,task_id='task-one',packet_id='PACKET-1',attempt_id='attempt-one',attempt_number=0,
        claim_task_id='task-one',claim_acquired_at='2026-10-17T14:00:00+00:00',claim_identity_sha256='c'*64,campaign_id='campaign-fixture')
    probes=[]
    for field,example in binding.items():
        for raw in [[],[example],{'value':example},None,False,0.0,'0']:
            probes.append(dict(field=field,value=raw,target='binding'))
    for field in ['authority_granted','retry_allowed']:
        for raw in [0,0.0,'false',[False],[],None,True]:probes.append(dict(field=field,value=raw,target='flag'))
    payload=dict(binding=binding,probes=probes,root=str(root),relay=str(root/'relay'))
    encoded=base64.b64encode(json.dumps(payload).encode()).decode();harness=root/'typed.ps1'
    harness.write_text(r'''$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
if(-not [string]::Equals([Console]::In.ReadLine(),'owned-job-ready',[StringComparison]::Ordinal)){exit 125}
$data=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('ENCODED'))|ConvertFrom-Json
$t=$null;$e=$null;$a=[Management.Automation.Language.Parser]::ParseFile('WORKER',[ref]$t,[ref]$e);if($e.Count){throw $e[0]}
foreach($d in $a.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst]},$false)){Set-Item -Path ('Function:'+$d.Name) -Value $d.Body.GetScriptBlock()}
$binding=@{};foreach($p in $data.binding.PSObject.Properties){$binding[$p.Name]=$p.Value}
$rows=@();$valid=0
foreach($kind in @('Observation','Capture')){
 foreach($case in @($data.probes)+@([pscustomobject]@{target='valid';field='';value=$null})){
  $copy=@{};foreach($name in $binding.Keys){$copy[$name]=$binding[$name]}
  $saved=@{schema=$(if($kind -eq 'Capture'){'AIOS_RELAY_EXECUTION.v1'}else{'AIOS_RELAY_OBSERVATION.v1'});authority_granted=$false;retry_allowed=$false}
  if($kind -eq 'Capture'){$saved.binding=[pscustomobject]$copy;$saved.request_json='{}';$saved.packet_sha256=('e'*64)}
  else{foreach($name in $copy.Keys){$saved[$name]=$copy[$name]};$saved.repo_root=$data.root;$saved.relay_root=$data.relay;$saved.status='DEFERRED';$saved.reason='owned'}
  if($case.target -eq 'binding'){if($kind -eq 'Capture'){$saved.binding.PSObject.Properties[$case.field].Value=$case.value}else{$saved[$case.field]=$case.value}}
  elseif($case.target -eq 'flag'){$saved[$case.field]=$case.value}
  $rejected=$false
  try{Assert-AiOsBoundReadback -Value ([pscustomobject]$saved) -Binding $binding -Kind $kind -RepoRoot $data.root -RelayRoot $data.relay -RequestJson '{}' -PacketSha256 ('e'*64)}catch{$rejected=$true}
  if($case.target -eq 'valid'){if(-not $rejected){$valid++}}
  else{$rows+=[pscustomobject]@{kind=$kind;field=[string]$case.field;rejected=$rejected}}
 }
}
[Console]::WriteLine('C4_TYPES:'+ [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes((@{rows=$rows;valid=$valid}|ConvertTo-Json -Depth 8 -Compress))))
'''.replace('ENCODED',encoded).replace('WORKER',str(worker).replace("'","''")),encoding='utf-8')
    output,active=_n02_owned_harness(harness,root,timeout=15);assert active==0
    result=json.loads(base64.b64decode(output.split('C4_TYPES:',1)[1].strip()))
    assert result['valid']==2 and len(result['rows'])==154
    assert all(row['rejected'] is True for row in result['rows'])

# Serial integration into the existing cycle test file, after the helper35 block.
@pytest.mark.parametrize('kind',['preflight','cost','output'])
@pytest.mark.parametrize('dictionary',[False,True],ids=['psobject','dictionary'])
def test_n05_raw_binding_members_do_not_alias_scalars_or_start_helpers(kind,dictionary):
    original=_n05_helper_binding()
    probes=[]
    for field,value in original.items():
        for shape,raw in [('empty',[]),('singleton',[value]),('multiple',[value,value]),('nested',[[value]]),
                          ('wrong_scalar','0' if field=='attempt_number' else 7),('object',{'value':value})]:
            probes.append(dict(field=field,shape=shape,value=raw))
    encoded=base64.b64encode(json.dumps(probes).encode()).decode()
    native='$true' if dictionary else '$false'
    function=N05_HELPER_DEFINITIONS[kind][1]
    setup=f'''
$originalBinding=$parameters['CampaignBinding']
$probes=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded}')) | ConvertFrom-Json
$rows=New-Object System.Collections.Generic.List[object]
foreach($case in $probes) {{
    $candidate=@{{}}
    foreach($property in $originalBinding.PSObject.Properties) {{ $candidate[$property.Name]=$property.Value }}
    $candidate[$case.field]=$case.value
    if({native}) {{ $parameters['CampaignBinding']=$candidate }} else {{ $parameters['CampaignBinding']=[pscustomobject]$candidate }}
    $response={function} @parameters
    $sideEffects=([IO.Directory]::Exists((Join-Path $parameters['RelayRoot'] 'logs')) -or [IO.Directory]::Exists((Join-Path $parameters['RepoRoot'] 'control')) -or [IO.File]::Exists((Join-Path $parameters['RepoRoot'] 'version-invoked')))
    $rows.Add([pscustomobject]@{{rejected=($response.ok -is [bool] -and -not $response.ok);authority_granted=$response.authority_granted;side_effects=$sideEffects}})
}}
$parameters['CampaignBinding']=$originalBinding
$parameters['CampaignBinding'].attempt_number=[long]7
$parameters['CampaignBinding'].claim_acquired_at='2026-10-17T00:00:00.123456+00:00'
[IO.File]::WriteAllText((Join-Path $parameters['RepoRoot'] 'pipeline-rows.json'),(ConvertTo-Json -InputObject @($rows.ToArray()) -Depth 4 -Compress),[Text.UTF8Encoding]::new($false))
'''
    def prepare(repo,relay,params):
        if kind=='preflight':
            tool=repo/'version-probe.ps1'
            marker=base64.b64encode(str(repo/'version-invoked').encode()).decode()
            tool.write_text("[IO.File]::WriteAllText([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('"+marker+"')),'invoked')\n",encoding='ascii')
            params.update(Tools=[str(tool)],VersionTimeoutSec=3)
        if kind=='output':
            params['BeforeManifest']['safe/legit-null.py']=None
            params['AllowedPaths'].append('safe/legit-null.py')
    result,repo,_=_n05_run_helper(kind,prepare,fixture_setup=setup)
    rows=json.loads((repo/'pipeline-rows.json').read_text())
    assert len(rows)==54
    assert all(row['rejected'] and row['authority_granted'] is False and not row['side_effects'] for row in rows)
    assert result['ok'] is True and result['binding']['attempt_number']==7
    assert result['binding']['claim_acquired_at']=='2026-10-17T00:00:00.123456+00:00'


@pytest.mark.parametrize('dictionary',[False,True],ids=['psobject','dictionary'])
def test_n05_raw_manifest_members_do_not_invent_null_or_digest(dictionary):
    digest=hashlib.sha256(b'original').hexdigest()
    probes=[dict(value=value) for value in [[],[digest],[digest,digest],[[digest]],True,7,{'hash':digest}]]
    encoded=base64.b64encode(json.dumps(probes).encode()).decode()
    native='$true' if dictionary else '$false'
    setup=f'''
$originalManifest=$parameters['BeforeManifest']
$probes=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded}')) | ConvertFrom-Json
$rows=New-Object System.Collections.Generic.List[object]
foreach($case in $probes) {{
    $candidate=@{{'safe/file.py'=$case.value}}
    if({native}) {{ $parameters['BeforeManifest']=$candidate }} else {{ $parameters['BeforeManifest']=[pscustomobject]$candidate }}
    $response=Test-AiOsWorkerOutput @parameters
    $rows.Add([pscustomobject]@{{rejected=($response.pass -is [bool] -and -not $response.pass);authority_granted=$response.authority_granted;side_effects=[IO.Directory]::Exists((Join-Path $parameters['RelayRoot'] 'logs'))}})
}}
$parameters['BeforeManifest']=$originalManifest
[IO.File]::WriteAllText((Join-Path $parameters['RepoRoot'] 'pipeline-rows.json'),(ConvertTo-Json -InputObject @($rows.ToArray()) -Depth 4 -Compress),[Text.UTF8Encoding]::new($false))
'''
    result,repo,_=_n05_run_helper('output',fixture_setup=setup)
    rows=json.loads((repo/'pipeline-rows.json').read_text())
    assert len(rows)==7
    assert all(row['rejected'] and row['authority_granted'] is False and not row['side_effects'] for row in rows)
    assert result['pass'] is True


# Output-helper source admission: explicit diagnostic intent is never approval.
@pytest.mark.parametrize('entry_mode',['named','direct'])
@pytest.mark.parametrize('ambient',[False,True])
def test_output_admission_default_never_writes(entry_mode,ambient):
    result,repo,relay=_n05_run_helper('output',entry_mode=entry_mode,
        fixture_setup='$Apply=$true' if ambient else '')
    assert result['pass'] is True and result['authority_granted'] is False
    assert not (relay/'logs').exists() and not (repo/'relay/logs').exists()
    assert result['diagnostic_write_requested'] is False
    assert result['diagnostic_write_completed'] is False


@pytest.mark.parametrize('entry_mode',['named','direct'])
def test_output_admission_explicit_false_still_never_writes(entry_mode):
    def prepare(repo,relay,params):params['Apply' if entry_mode=='direct' else 'DiagnosticWriteChoice']=False
    result,repo,relay=_n05_run_helper('output',prepare,entry_mode=entry_mode,fixture_setup='$Apply=$true')
    assert result['pass'] is True and result['diagnostic_write_requested'] is False
    assert not (relay/'logs').exists() and not (repo/'relay/logs').exists()


@pytest.mark.parametrize('entry_mode',['named','direct'])
@pytest.mark.parametrize('legacy',[False,True])
def test_output_admission_explicit_selected_write(entry_mode,legacy):
    def prepare(repo,relay,params):
        if legacy:
            for key in ['CampaignBinding','RelayRoot','LogPath','BeforeManifest','ControllerMetadataPaths','ChangedPathsEvidence','ExpectedStatusParserSha256']:params.pop(key,None)
        params['Apply' if entry_mode=='direct' else 'DiagnosticWriteChoice']=True
    result,repo,relay=_n05_run_helper('output',prepare,entry_mode=entry_mode)
    target=repo/'relay/logs/output_validator.log' if legacy else relay/'logs/output.log'
    assert result['pass'] is True and target.exists()
    assert result['diagnostic_write_requested'] is True and result['diagnostic_write_completed'] is True
    assert result['diagnostic_write_error']=='' and len(target.read_text(encoding='utf-8-sig').splitlines())==1
    if not legacy:assert not (repo/'relay/logs').exists()


@pytest.mark.parametrize('raw',[None,'true',1,[],[True],[False,True],[[True]],{'value':True}])
def test_output_admission_raw_choice_rejects_before_io(raw):
    result,repo,relay=_n05_run_helper('output',lambda r,i,p:p.update(DiagnosticWriteChoice=raw))
    assert result['pass'] is False and result['violation_reason']=='DIAGNOSTIC_WRITE_CHOICE_REJECTED'
    assert result['authority_granted'] is False and not (relay/'logs').exists() and not (repo/'relay/logs').exists()


@pytest.mark.parametrize('primary_pass',[True,False])
def test_output_admission_real_log_io_failure_preserves_primary_scope(primary_pass):
    def prepare(repo,relay,params):
        params['DiagnosticWriteChoice']=True
        target=relay/'log-directory';target.mkdir();params['LogPath']=str(target)
        if not primary_pass:
            (repo/'safe/other.py').write_bytes(b'provider delta')
            params['BeforeManifest']['safe/other.py']=None
            params['ChangedPathsEvidence']['after_paths'].append('safe/other.py')
    result,repo,relay=_n05_run_helper('output',prepare)
    assert result['pass'] is primary_pass and result['ok'] is primary_pass
    assert result['violation_reason']==('' if primary_pass else 'OUTPUT_OUTSIDE_ALLOWED_PATHS')
    assert result['diagnostic_write_requested'] is True and result['diagnostic_write_completed'] is False
    assert isinstance(result['diagnostic_write_error'],str) and result['diagnostic_write_error']
    assert result['authority_granted'] is False and not (repo/'relay/logs').exists()


@pytest.mark.parametrize('raw',[False,None,'true',1,[],[True],[False,True],{'value':True}])
def test_output_admission_bound_choice_rejects_before_effects(tmp_path,raw):
    result,request=_n05_native(tmp_path,'success',first_choice=raw,second_choice=raw)
    assert result['calls']==0 and result['metadata_calls']==0
    assert result['first']['status']=='REQUEST_REJECTED' and result['first']['reason']=='EXACT_APPLY_REQUEST_REQUIRED'
    relay=Path(request['relay_root'])
    assert not (relay/'running').exists() and not (relay/'outbox').exists() and not (relay/'logs').exists()


@pytest.mark.parametrize('raw',[False,'true',[True],None])
def test_output_admission_rejected_choice_preserves_existing_capture_no_replay(tmp_path,raw):
    result,request=_n05_native(tmp_path,'incomplete',second_choice=raw)
    assert result['first']['status']=='EXECUTION_FAILED' and result['calls']==1
    assert result['second']['status']=='REQUEST_REJECTED' and result['second']['reason']=='EXACT_APPLY_REQUEST_REQUIRED'
    assert result['capture_before'] and result['capture_after']==result['capture_before']
    capture=Path(result['first']['execution_path'])
    assert hashlib.sha256(capture.read_bytes()).hexdigest()==result['first']['execution_sha256']


@pytest.mark.parametrize('case,status,primary_pass',[
    ('log_failure','FINALIZATION_RECONCILIATION_REQUIRED',True),
    ('log_failure_scope','SAFETY_INTEGRITY_BLOCK',False),
    ('log_failure_process','EXECUTION_FAILED',True)])
def test_output_admission_worker_log_failure_retains_capture_and_primary(tmp_path,case,status,primary_pass):
    result,request=_n05_native(tmp_path,case)
    first=result['first'];assert first['status']==status and result['calls']==1
    assert result['second']['status']=='FINALIZATION_RECONCILIATION_REQUIRED'
    assert result['capture_before'] and result['capture_before']==result['capture_after']
    scope=first['output_scope'];assert scope['pass'] is primary_pass
    assert scope['diagnostic_write_requested'] is True and scope['diagnostic_write_completed'] is False and scope['diagnostic_write_error']
    assert scope['authority_granted'] is False and first['authority_granted'] is False
    capture=Path(first['execution_path']);assert hashlib.sha256(capture.read_bytes()).hexdigest()==first['execution_sha256']
    assert 'PRIVATE_CHILD_OUTPUT' not in capture.read_text() and not (Path(request['relay_root'])/'done').exists()


@pytest.mark.parametrize('raw_switch',[True,False])
def test_output_admission_switch_object_is_not_raw_bool(raw_switch):
    setup="$parameters['DiagnosticWriteChoice']=[switch]$"+str(raw_switch).lower()
    result,_,relay=_n05_run_helper('output',fixture_setup=setup)
    assert result['violation_reason']=='DIAGNOSTIC_WRITE_CHOICE_REJECTED' and not (relay/'logs').exists()


def test_output_admission_named_writers_deny_direct_unready_calls():
    setup=r"""
foreach($writer in @('Write-AiOsOutputBoundLine','Write-AiOsOutputLegacyLine')) {
 foreach($case in @('absent','false','string','unready','array_state')) {
  $argsWrite=@{Path=(Join-Path $parameters['RelayRoot'] 'logs/forbidden.log');Line='forbidden'}
  if($writer -ceq 'Write-AiOsOutputBoundLine'){$argsWrite.RelayRoot=$parameters['RelayRoot']}else{$argsWrite.RepoRoot=$parameters['RepoRoot']}
  if($case -eq 'false'){$argsWrite.DiagnosticWriteChoice=$false;$argsWrite.OutputWriteState='READY_TO_WRITE_DIAGNOSTIC'}
  elseif($case -eq 'string'){$argsWrite.DiagnosticWriteChoice='true';$argsWrite.OutputWriteState='READY_TO_WRITE_DIAGNOSTIC'}
  elseif($case -eq 'unready'){$argsWrite.DiagnosticWriteChoice=$true;$argsWrite.OutputWriteState='NOT_READY'}
  elseif($case -eq 'array_state'){$argsWrite.DiagnosticWriteChoice=$true;$argsWrite.OutputWriteState=@('READY_TO_WRITE_DIAGNOSTIC')}
  $rejected=$false;try{& $writer @argsWrite}catch{$rejected=$_.Exception.Message -ceq 'DIAGNOSTIC_WRITE_GATE_REQUIRED'}
  if(-not $rejected){throw ('Owned direct writer gate did not reject '+$writer+':'+$case)}
 }
}
"""
    result,repo,relay=_n05_run_helper('output',fixture_setup=setup)
    assert result['pass'] is True and not (relay/'logs').exists() and not (repo/'relay/logs').exists()


def test_output_admission_bound_named_default_rejects_before_effects(tmp_path):
    result,request=_n05_native(tmp_path,'success',first_choice='__omit_fixture_only__',second_choice=False)
    assert result['first']['reason']=='EXACT_APPLY_REQUEST_REQUIRED' and result['calls']==0 and result['metadata_calls']==0
    assert not (Path(request['relay_root'])/'running').exists() and not (Path(request['relay_root'])/'outbox').exists()


@pytest.mark.parametrize('explicit_false',[False,True])
def test_output_admission_owned_worker_direct_default_rejects_without_effects(explicit_false):
    root=Path(tempfile.mkdtemp(prefix='n5entry-'))/'r'
    relative='automation/orchestration/relay/Invoke-AiOsRelayWorker.ps1'
    worker=root/relative;worker.parent.mkdir(parents=True);shutil.copy2(N05_HELPER_SOURCE_REPO/relative,worker)
    harness=root/'owned-entry.ps1';relay=root/'relay/selected'
    harness.write_text("$ErrorActionPreference='Stop'\n"
        "if(-not [string]::Equals([Console]::In.ReadLine(),'owned-job-ready',[StringComparison]::Ordinal)){exit 125}\n"
        f"& '{str(worker).replace(chr(39),chr(39)*2)}' -RepoRoot '{root}' -RelayRoot '{relay}' -RequestPath '{relay/'inbox/selected.task.json'}' -ExpectedPacketSha256 '{'e'*64}' -PythonExecutable '{sys.executable}' "
        +( '-Apply:$false' if explicit_false else '')+"\nexit $LASTEXITCODE\n",encoding='utf-8')
    output,active=_n02_owned_harness(harness,root,timeout=10,expected_exit=2)
    assert active==0 and json.loads(output)['reason']=='EXACT_APPLY_REQUEST_REQUIRED' and not relay.exists()


def _output_admission_guard(mutation='none', *, canonical=False):
    root=Path(tempfile.mkdtemp(prefix='n5guard-'))/'r';root.mkdir()
    helper_relative=N05_HELPER_DEFINITIONS['output'][0]
    guard_relative='automation/orchestration/validators/Invoke-AiOsExecutionRegistryGuard.ps1'
    registry_relative='automation/orchestration/execution_registry/AIOS_EXECUTION_CLASSIFICATION_REGISTRY.json'
    for relative in ['AGENTS.md','README.md',helper_relative,guard_relative,registry_relative]:
        target=root/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(N05_HELPER_SOURCE_REPO/relative,target)
    registry=json.loads((root/registry_relative).read_text(encoding='utf-8-sig'))
    original_entries=deepcopy(registry['scripts'])
    if not canonical:
        entry=deepcopy(next(item for item in registry['scripts'] if item.get('gated_mutation_contract')))
        entry.update(path=helper_relative,purpose='UNAPPROVED owned source-gate test',owner_area='automation/orchestration/validators/output',
            allowed_callers=['automation/orchestration/relay/Invoke-AiOsRelayWorker.ps1','operator'],review_status='UNAPPROVED_OWNED_TEST_ONLY',launches_process=False,runs_git=False)
        entry['gated_mutation_contract'].update(explicit_apply_parameter='Apply',gated_write_functions=['Write-AiOsOutputBoundLine','Write-AiOsOutputLegacyLine'],
            required_apply_gate_terms=['$Apply','$OutputWriteState','READY_TO_WRITE_DIAGNOSTIC'])
        registry['scripts'].append(entry)
        (root/registry_relative).write_text(json.dumps(registry,indent=2),encoding='utf-8')
    assert registry['scripts'][:len(original_entries)]==original_entries
    helper=root/helper_relative;source=helper.read_text(encoding='utf-8')
    if mutation=='duplicate_switch':source+='\nfunction OwnedWrongDuplicate { param([switch]$Apply) }\n'
    elif mutation=='outside_writer':source+='\nNew-Item -ItemType Directory -Path owned-forbidden\n'
    elif mutation=='outside_gate':source=source.replace("if ($Apply -and $OutputWriteState -ceq 'READY_TO_WRITE_DIAGNOSTIC')",'if ($true)')
    elif mutation=='wrong_branch':source=source.replace("if ($Apply -and $OutputWriteState -ceq 'READY_TO_WRITE_DIAGNOSTIC')","if ($Apply -and $OutputWriteState -ceq 'READY_TO_WRITE_DIAGNOSTIC' -and $false)")
    helper.write_text(source,encoding='utf-8')
    harness=root/'owned-guard.ps1';guard=root/guard_relative
    harness.write_text("$ErrorActionPreference='Stop'\n"
        "if(-not [string]::Equals([Console]::In.ReadLine(),'owned-job-ready',[StringComparison]::Ordinal)){exit 125}\n"
        f"& '{guard}' -ScanFiles '{helper_relative}'\nexit $LASTEXITCODE\n",encoding='utf-8')
    expected=1 if canonical or mutation in {'duplicate_switch','outside_writer','outside_gate'} else 0
    output,active=_n02_owned_harness(harness,root,timeout=10,expected_exit=expected)
    assert active==0
    assert hashlib.sha256(guard.read_bytes()).digest()==hashlib.sha256((N05_HELPER_SOURCE_REPO/guard_relative).read_bytes()).digest()
    return output


def test_output_admission_actual_guard_still_blocks_canonical_registry():
    assert 'unregistered_executable_script' in _output_admission_guard(canonical=True)


@pytest.mark.parametrize('mutation',['none','duplicate_switch','outside_writer','outside_gate'])
def test_output_admission_actual_unchanged_guard_contract_controls(mutation):
    output=_output_admission_guard(mutation)
    assert ('AI_OS EXECUTION REGISTRY GUARD: PASS' in output) is (mutation=='none')
    if mutation!='none':assert 'dry_run_script_writes_files' in output


def test_output_admission_text_guard_cannot_confirm_wrong_branch_behavior():
    assert 'AI_OS EXECUTION REGISTRY GUARD: PASS' in _output_admission_guard('wrong_branch')
    transform=lambda source:source.replace("if ($Apply -and $OutputWriteState -ceq 'READY_TO_WRITE_DIAGNOSTIC')", "if ($Apply -and $OutputWriteState -ceq 'READY_TO_WRITE_DIAGNOSTIC' -and $false)")
    result,_,relay=_n05_run_helper('output',lambda r,i,p:p.update(DiagnosticWriteChoice=True),source_transform=transform)
    assert result['pass'] is True and result['diagnostic_write_requested'] is True
    assert result['diagnostic_write_completed'] is False and not (relay/'logs').exists()


@pytest.mark.parametrize('primary_pass',[True,False])
def test_output_admission_legacy_real_io_failure_keeps_primary(primary_pass):
    def prepare(repo,relay,params):
        for key in ['CampaignBinding','RelayRoot','LogPath','BeforeManifest','ControllerMetadataPaths','ChangedPathsEvidence','ExpectedStatusParserSha256']:params.pop(key,None)
        params['DiagnosticWriteChoice']=True
        if not primary_pass:params['AllowedPaths']=['AGENTS.md']
        (repo/'relay/logs/output_validator.log').mkdir(parents=True)
    result,repo,_=_n05_run_helper('output',prepare)
    assert result['pass'] is primary_pass and result['authority_granted'] is False
    assert result['violation_reason']==('' if primary_pass else 'PROTECTED_PATH_TOUCHED')
    assert result['diagnostic_write_requested'] is True and result['diagnostic_write_completed'] is False and result['diagnostic_write_error']
    assert (repo/'relay/logs/output_validator.log').is_dir()


@pytest.mark.parametrize('mutation',['binding','manifest','coverage','destination'])
def test_output_admission_positive_choice_still_rejects_before_io(mutation):
    def prepare(repo,relay,params):
        params['DiagnosticWriteChoice']=True
        if mutation=='binding':params['CampaignBinding']['attempt_number']=[0]
        elif mutation=='manifest':params['BeforeManifest']['safe/file.py']=[]
        elif mutation=='coverage':params['ChangedPathsEvidence']['complete']=1
        else:params['LogPath']=str(repo/'outside.log')
    result,repo,relay=_n05_run_helper('output',prepare)
    assert result['pass'] is False and result['authority_granted'] is False
    assert result['diagnostic_write_completed'] is False and not (relay/'logs').exists() and not (repo/'relay/logs').exists() and not (repo/'outside.log').exists()


@pytest.mark.parametrize('junction',[False,True])
@pytest.mark.parametrize('primary_pass',[False,True])
@pytest.mark.parametrize('choice',[False,True])
def test_output_admission_legacy_log_path_failure_preserves_scope(junction,primary_pass,choice):
    def prepare(repo,relay,params):
        for key in ['CampaignBinding','RelayRoot','LogPath','BeforeManifest','ControllerMetadataPaths','ChangedPathsEvidence','ExpectedStatusParserSha256']:params.pop(key,None)
        params['DiagnosticWriteChoice']=choice
        if not primary_pass:params['AllowedPaths']=['AGENTS.md']
    setup=r"""
$target=Join-Path $parameters['RepoRoot'] 'owned-log-junction-target'
[void][IO.Directory]::CreateDirectory($target)
[IO.File]::WriteAllText((Join-Path $target 'sentinel.txt'),'OWNED_SENTINEL_UNCHANGED')
$null=New-Item -ItemType Junction -Path (Join-Path $parameters['RepoRoot'] 'relay/logs') -Target $target -ErrorAction Stop
""" if junction else ''
    result,repo,_=_n05_run_helper('output',prepare,fixture_setup=setup)
    assert result['pass'] is primary_pass and result['authority_granted'] is False
    assert result['violation_reason']==('' if primary_pass else 'PROTECTED_PATH_TOUCHED')
    assert result['diagnostic_write_requested'] is choice
    assert result['diagnostic_write_completed'] is (choice and not junction)
    if choice and junction:assert 'Reparse path rejected' in result['diagnostic_write_error']
    else:assert result['diagnostic_write_error']==''
    if junction:
        target=repo/'owned-log-junction-target'
        assert (target/'sentinel.txt').read_text()=='OWNED_SENTINEL_UNCHANGED'
        assert not (target/'output_validator.log').exists()
    else:assert (repo/'relay/logs/output_validator.log').exists() is choice


@pytest.mark.parametrize('primary_pass',[False,True])
@pytest.mark.parametrize('choice',[False,True])
def test_output_admission_legacy_caller_keeps_typed_diagnostic_evidence(primary_pass,choice):
    root=Path(tempfile.mkdtemp(prefix='n5legacy-'))/'r';root.mkdir()
    worker_relative='automation/orchestration/relay/Invoke-AiOsRelayWorker.ps1'
    for relative in (worker_relative,N05_HELPER_DEFINITIONS['output'][0]):
        target=root/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(N05_HELPER_SOURCE_REPO/relative,target)
    for relative,body in {
        'cost/Test-AiOsCostCeiling.ps1':"param($CycleId) [pscustomobject]@{ok=$true;reason='';cycle_spend=0;day_spend=0}",
        'lock/Test-AiOsFileLock.ps1':"param($AllowedPaths,$RepoRoot) [pscustomobject]@{defer=$false}",
        'cost/Add-AiOsCostLedgerEntry.ps1':"param($CycleId,$Cost,$InputTokens,$OutputTokens,$PacketId,$Worker,$Estimated,$EstimateReason) [pscustomobject]@{ok=$true}",
    }.items():
        target=root/'automation/orchestration'/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(body,encoding='ascii')
    packet=root/'inert.task.json';packet.write_bytes(b'owned inert packet, never dispatched')
    log=root/'relay/logs/output_validator.log';log.parent.mkdir(parents=True);log.write_bytes(b'OWNED_ORIGINAL_LOG\n')
    error=root/'relay/error/owned-legacy.error.txt';error.parent.mkdir()
    report=root/'retained-report.txt';report.write_bytes(b'OWNED_EXISTING_EXECUTION_REPORT\n');report_sha=hashlib.sha256(report.read_bytes()).hexdigest()
    payload=base64.b64encode(json.dumps(dict(root=str(root),worker=str(root/worker_relative),packet=str(packet),log=str(log),report=str(report),primary=primary_pass,choice=choice)).encode()).decode()
    harness=root/'owned-legacy.ps1'
    harness.write_text(r'''$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
if(-not [string]::Equals([Console]::In.ReadLine(),'owned-job-ready',[StringComparison]::Ordinal)){exit 125}
$inputData=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('PAYLOAD'))|ConvertFrom-Json
$tokens=$null;$errors=$null;$ast=[Management.Automation.Language.Parser]::ParseFile($inputData.worker,[ref]$tokens,[ref]$errors);if($errors.Count){throw $errors[0]}
foreach($def in @($ast.EndBlock.Statements|Where-Object{$_ -is [Management.Automation.Language.FunctionDefinitionAst]})){Set-Item -Path ('Function:'+$def.Name) -Value $def.Body.GetScriptBlock()}
$RepoRoot=$inputData.root;$Apply=[switch]$inputData.choice;$DefaultEstimateUsd=0;$script:moves=@();$script:providerCalls=0
$RelayPaths=@{error=(Join-Path $RepoRoot 'relay/error');running=(Join-Path $RepoRoot 'relay/running');done=(Join-Path $RepoRoot 'relay/done')}
$script:ownedAllowed=if($inputData.primary){@('safe/file.py')}else{@('AGENTS.md')}
function Test-AiOsStableFile {param($File) return $true}
function Read-AiOsTaskPacket {param($File) return [pscustomobject]@{ok=$true;id='owned-legacy';mission='inert';tier='TIER_1_BOUNDED_APPLY';worker='codex';provider='codex';provider_command='owned-never-executed';provider_args=@();allowed_paths=$script:ownedAllowed;prompt_text='owned';packet=[pscustomobject]@{timeout_sec=1}}}
function Get-AiOsRelayTier {param($Text) return 'TIER_1_BOUNDED_APPLY'}
function Test-AiOsProtectedRelayText {param($Text) return $false}
function Move-AiOsRelayPacket {param($SourcePath,$TargetFolder) $script:moves+=([string]$TargetFolder);return (Join-Path $TargetFolder 'owned.task.json')}
function Write-AiOsRelayLog {param($Message)}
function Write-AiOsWorkerReport {param($Id,$Worker,$Provider,$ProviderCommand,$Tier,$StartedAt,$EndedAt,$ExitCode,$AllowedPaths,$Body) return $inputData.report}
function Invoke-AiOsProviderWorker {param($Worker,$Provider,$ProviderCommand,$ProviderArgs,$Tier,$Mission,$AllowedPaths,$PromptText) $script:providerCalls++;return [pscustomobject]@{exit_code=0;command='owned-no-provider';output=@()}}
function Resolve-AiOsWorkerCostRecord {param($ProviderResult,$DefaultEstimateUsd) return [pscustomobject]@{cost_usd=0;input_tokens=0;output_tokens=0;estimated=$true;estimate_reason='owned'}}
[IO.File]::SetAttributes($inputData.log,([IO.File]::GetAttributes($inputData.log) -bor [IO.FileAttributes]::ReadOnly))
$result=Complete-AiOsRelayWorkerPacket -File ([IO.FileInfo]$inputData.packet)
$value=@{result=$result;moves=$script:moves;provider_seam_calls=$script:providerCalls;log_bytes=[Convert]::ToBase64String([IO.File]::ReadAllBytes($inputData.log))}
[Console]::WriteLine([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($value|ConvertTo-Json -Depth 5 -Compress))))
'''.replace('PAYLOAD',payload),encoding='utf-8')
    output,active=_n02_owned_harness(harness,root,timeout=15);assert active==0
    result=json.loads(base64.b64decode(output.strip()))
    assert result['provider_seam_calls']==int(choice) and result['log_bytes']==base64.b64encode(b'OWNED_ORIGINAL_LOG\n').decode()
    assert hashlib.sha256(report.read_bytes()).hexdigest()==report_sha
    done=str(root/'relay/done')
    if primary_pass and not choice:
        assert not error.exists() and done in result['moves']
    else:
        assert done not in result['moves']
        text=error.read_text(encoding='utf-8-sig')
        assert ('reason: OUTPUT_OUTSIDE_ALLOWED_PATHS' if not primary_pass else 'reason: OUTPUT_DIAGNOSTIC_WRITE_UNCONFIRMED') in text
        if not primary_pass:assert 'PROTECTED_PATH_TOUCHED' in text
        diagnostic=json.loads(next(line.removeprefix('output_diagnostic: ') for line in text.splitlines() if line.startswith('output_diagnostic: ')))
        assert diagnostic['evidence_shape_valid'] is True and diagnostic['primary_scope_pass'] is primary_pass
        assert diagnostic['diagnostic_write_requested'] is choice and diagnostic['diagnostic_write_completed'] is False
        assert isinstance(diagnostic['diagnostic_write_error'],str)
        if choice:assert 'denied' in diagnostic['diagnostic_write_error']
        else:assert diagnostic['diagnostic_write_error']==''


# Native aggregate controls are pure or use owned receipt files only. No fixture
# here invokes the actual nv02 descriptor, a validator process or a provider.
def _native_aggregate_cycle():
    from automation.orchestration.relay import aios_self_consuming_codex_cycle_v1
    return aios_self_consuming_codex_cycle_v1


def _native_aggregate_descriptor(tmp_path: Path) -> dict:
    root=tmp_path/'owned';root.mkdir()
    (root/'results').mkdir()
    config=root/'pytest.ini';config.write_bytes(b'[pytest]\njunit_family=xunit2\n')
    source=root/'test_requirement_contract.py';source.write_bytes(b'# inert pure metadata fixture\n')
    cases=[{'node_id':'test_requirement_contract.py::test_owned_binding_projection','classname':'test_requirement_contract','name':'test_owned_binding_projection'},
           {'node_id':'test_requirement_contract.py::test_owned_result_projection','classname':'test_requirement_contract','name':'test_owned_result_projection'}]
    receipt=root/'results/pytest.xml'
    return {'schema':'AIOS_PYTEST_JUNIT_REQUIREMENT.v1','validator_id':'owned-component-contract',
            'executable':str(root/'python.exe'),'executable_sha256':'a'*64,'cwd':str(root),
            'argv':['-B','-m','pytest','-c',str(config),'--noconftest','-p','no:cacheprovider','--import-mode=importlib','--junitxml='+str(receipt),*[case['node_id'] for case in cases]],
            'environment':{'PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTHONPATH':str(root),'SYSTEMROOT':r'C:\Windows','WINDIR':r'C:\Windows','TEMP':str(root/'tmp'),'TMP':str(root/'tmp')},
            'stdin_utf8':'','stdin_byte_count':0,'receipt_path':str(receipt),'receipt_max_bytes':1048576,
            'required_cases':cases,'input_manifest':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in (config,source)},
            'observed_producer_sources':{},'required_counts':{'tests':2,'failures':0,'errors':0,'skipped':0},'result_contract':'exact-case-set-and-all-pass'}


def _native_aggregate_xml() -> bytes:
    return (b'<?xml version="1.0" encoding="utf-8"?><testsuites>'
            b'<testsuite name="pytest" errors="0" failures="0" skipped="0" tests="2" time="0.001" timestamp="2026-10-17T00:00:00" hostname="owned">'
            b'<testcase classname="test_requirement_contract" name="test_owned_binding_projection" time="0.001" />'
            b'<testcase classname="test_requirement_contract" name="test_owned_result_projection" time="0.000" />'
            b'</testsuite></testsuites>')


def test_native_aggregate_exact_junit_control(tmp_path: Path) -> None:
    descriptor=_native_aggregate_descriptor(tmp_path)
    summary=_native_aggregate_cycle()._parse_native_junit(descriptor,_native_aggregate_xml())
    assert type(summary) is dict
    for name,want in descriptor['required_counts'].items():
        assert type(summary[name]) is int and summary[name]==want
    assert len(summary['cases'])==2
    assert {(case['classname'],case['name']) for case in summary['cases']}=={(case['classname'],case['name']) for case in descriptor['required_cases']}


@pytest.mark.parametrize('case',[
    'missing','extra','duplicate','wrong_identity','skip','failure','error','warning',
    'test_output','suite_output','properties','unknown_child','root_namespace',
    'malformed','duplicate_attribute','dtd','entity','wrong_counter','counter_bool',
    'counter_float','counter_negative','root_counter','two_suites','empty_suite',
])
def test_native_aggregate_junit_rejects_incomplete_or_extended_results(tmp_path: Path,case: str) -> None:
    descriptor=_native_aggregate_descriptor(tmp_path);raw=_native_aggregate_xml()
    first=b'<testcase classname="test_requirement_contract" name="test_owned_binding_projection" time="0.001" />'
    second=b'<testcase classname="test_requirement_contract" name="test_owned_result_projection" time="0.000" />'
    mutations={
        'missing':lambda:raw.replace(second,b''),
        'extra':lambda:raw.replace(b'</testsuite>',b'<testcase classname="extra" name="unrequested" /></testsuite>').replace(b'tests="2"',b'tests="3"'),
        'duplicate':lambda:raw.replace(second,first),
        'wrong_identity':lambda:raw.replace(b'name="test_owned_result_projection"',b'name="unrequested"'),
        'skip':lambda:raw.replace(second,second[:-3]+b'><skipped message="xfail" /></testcase>').replace(b'skipped="0"',b'skipped="1"'),
        'failure':lambda:raw.replace(second,second[:-3]+b'><failure message="assertion" /></testcase>').replace(b'failures="0"',b'failures="1"'),
        'error':lambda:raw.replace(second,second[:-3]+b'><error message="setup" /></testcase>').replace(b'errors="0"',b'errors="1"'),
        'warning':lambda:raw.replace(second,second[:-3]+b'><warning message="not acceptance" /></testcase>'),
        'test_output':lambda:raw.replace(second,second[:-3]+b'><system-out>untrusted output</system-out></testcase>'),
        'suite_output':lambda:raw.replace(b'</testsuite>',b'<system-err>untrusted output</system-err></testsuite>'),
        'properties':lambda:raw.replace(b'</testsuite>',b'<properties><property name="passed" value="true" /></properties></testsuite>'),
        'unknown_child':lambda:raw.replace(b'</testsuite>',b'<result passed="true" /></testsuite>'),
        'root_namespace':lambda:raw.replace(b'<testsuites>',b'<testsuites xmlns="urn:unadmitted">'),
        'malformed':lambda:raw[:-8],
        'duplicate_attribute':lambda:raw.replace(b'tests="2"',b'tests="2" tests="2"'),
        'dtd':lambda:raw.replace(b'<testsuites>',b'<!DOCTYPE testsuites [<!ELEMENT testsuites ANY>]><testsuites>'),
        'entity':lambda:raw.replace(b'<testsuites>',b'<!DOCTYPE testsuites [<!ENTITY owned "no expansion">]><testsuites>'),
        'wrong_counter':lambda:raw.replace(b'tests="2"',b'tests="1"'),
        'counter_bool':lambda:raw.replace(b'tests="2"',b'tests="true"'),
        'counter_float':lambda:raw.replace(b'tests="2"',b'tests="2.0"'),
        'counter_negative':lambda:raw.replace(b'errors="0"',b'errors="-1"'),
        'root_counter':lambda:raw.replace(b'<testsuites>',b'<testsuites tests="3">'),
        'two_suites':lambda:raw.replace(b'</testsuites>',b'<testsuite name="extra" tests="0" errors="0" failures="0" skipped="0" /></testsuites>'),
        'empty_suite':lambda:raw.replace(first,b'').replace(second,b'').replace(b'tests="2"',b'tests="0"'),
    }
    with pytest.raises((ValueError,TypeError)):
        _native_aggregate_cycle()._parse_native_junit(descriptor,mutations[case]())


@pytest.mark.parametrize('value',[None,'<testsuites />',bytearray(b'<testsuites />'),True])
def test_native_aggregate_junit_raw_bytes_required(tmp_path: Path,value) -> None:
    with pytest.raises((ValueError,TypeError)):
        _native_aggregate_cycle()._parse_native_junit(_native_aggregate_descriptor(tmp_path),value)


def test_native_aggregate_junit_bound_and_required_identity_uniqueness(tmp_path: Path) -> None:
    import copy
    descriptor=_native_aggregate_descriptor(tmp_path)
    oversized=copy.deepcopy(descriptor);oversized['receipt_max_bytes']=64
    with pytest.raises((ValueError,TypeError)):
        _native_aggregate_cycle()._parse_native_junit(oversized,_native_aggregate_xml())
    duplicate=copy.deepcopy(descriptor);duplicate['required_cases'][1]=duplicate['required_cases'][0].copy()
    with pytest.raises((ValueError,TypeError)):
        _native_aggregate_cycle()._parse_native_junit(duplicate,_native_aggregate_xml())
    empty=copy.deepcopy(descriptor);empty['required_cases']=[]
    with pytest.raises((ValueError,TypeError)):
        _native_aggregate_cycle()._parse_native_junit(empty,_native_aggregate_xml())


def _native_aggregate_process() -> dict:
    return {'shape_valid':True,'root_exit_confirmed':True,'tree_exit_confirmed':True,'drains_completed':True,
            'stdin_completed':True,'stdin_writer_joined':True,'timed_out':False,'startup_failed':False,
            'process_error_present':False,'stdout_truncated':False,'stderr_truncated':False,'retry_allowed':True,
            'exit_code':0,'child_exit_code':0,'stdin_error_code':0,'stdin_close_error_code':0,'cleanup_error_code':0,
            'cancellation_error_code':0,'root_process_id':471,'stdin_bytes_written':len('owned雪\n'.encode('utf-8')),
            'duration_sec':0.01,'cleanup_state':'CONFIRMED','executable':r'C:\owned\python.exe',
            'arguments':['-B','owned.py','雪'],'command_line_arguments':'"-B" "owned.py" "雪"','working_directory':r'C:\owned'}


def _native_aggregate_check_process(process) -> None:
    _native_aggregate_cycle()._verify_native_process(process,executable=r'C:\owned\python.exe',
        argv=['-B','owned.py','雪'],cwd=r'C:\owned',stdin_utf8='owned雪\n')


def test_native_aggregate_exact_process_control() -> None:
    import copy
    process=_native_aggregate_process();before=copy.deepcopy(process)
    assert _native_aggregate_check_process(process) is None
    assert process==before


@pytest.mark.parametrize(('field','bad'),[
    ('shape_valid',1),('root_exit_confirmed','true'),('tree_exit_confirmed',[True]),
    ('drains_completed',1.0),('stdin_completed',None),('stdin_writer_joined',False),
    ('timed_out',0),('startup_failed','false'),('process_error_present',[]),
    ('stdout_truncated',True),('stderr_truncated',True),('retry_allowed','true'),
    ('exit_code',False),('exit_code','0'),('exit_code',0.0),('exit_code',[0]),
    ('child_exit_code',True),('stdin_error_code',False),('stdin_close_error_code',1),
    ('cleanup_error_code',None),('cancellation_error_code',0.0),
    ('root_process_id',0),('root_process_id',True),('stdin_bytes_written',True),('stdin_bytes_written',0),
    ('duration_sec',True),('duration_sec',float('nan')),('duration_sec',float('inf')),('duration_sec',-1),
    ('cleanup_state','UNRESOLVED'),('executable',r'C:\other\python.exe'),
    ('arguments',['-B','other.py','雪']),('arguments','-B owned.py 雪'),
    ('arguments',['-B',['owned.py'],'雪']),('command_line_arguments','-B other.py 雪'),
    ('working_directory',r'C:\other'),
])
def test_native_aggregate_process_rejects_aliases_or_wrong_execution(field: str,bad) -> None:
    process=_native_aggregate_process();process[field]=bad
    with pytest.raises((ValueError,TypeError)):
        _native_aggregate_check_process(process)


@pytest.mark.parametrize('field',list(_native_aggregate_process()))
def test_native_aggregate_process_missing_fields_are_unknown(field: str) -> None:
    process=_native_aggregate_process();del process[field]
    with pytest.raises((ValueError,TypeError)):
        _native_aggregate_check_process(process)


def test_native_aggregate_receipt_live_creator_writes_exact_marker(tmp_path: Path) -> None:
    descriptor=_native_aggregate_descriptor(tmp_path);path=Path(descriptor['receipt_path'])
    assert not path.exists()
    assert _native_aggregate_cycle()._reserve_native_receipt(descriptor) is None
    assert path.read_bytes()==b'AIOS aggregate validator reserved; result unavailable\n'
    with pytest.raises((OSError,ValueError)):
        _native_aggregate_cycle()._reserve_native_receipt(descriptor)
    assert path.read_bytes()==b'AIOS aggregate validator reserved; result unavailable\n'


@pytest.mark.parametrize('existing',[b'',b'AIOS aggregate validator reserved; result unavailable\n',b'<testsuites>',_native_aggregate_xml(),b'foreign'])
def test_native_aggregate_existing_receipt_never_becomes_launch_ownership(tmp_path: Path,existing: bytes) -> None:
    descriptor=_native_aggregate_descriptor(tmp_path);path=Path(descriptor['receipt_path']);path.write_bytes(existing)
    with pytest.raises((OSError,ValueError)):
        _native_aggregate_cycle()._reserve_native_receipt(descriptor)
    assert path.read_bytes()==existing


def test_native_aggregate_concurrent_reservation_has_one_live_creator(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    descriptor=_native_aggregate_descriptor(tmp_path);ready=Barrier(2)
    def reserve():
        ready.wait(timeout=5)
        try:_native_aggregate_cycle()._reserve_native_receipt(descriptor)
        except (OSError,ValueError):return 'blocked'
        return 'creator'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:reserve(),range(2)))
    assert sorted(results)==['blocked','creator']
    assert Path(descriptor['receipt_path']).read_bytes()==b'AIOS aggregate validator reserved; result unavailable\n'


def test_native_aggregate_fsync_failure_retains_barrier_and_blocks_retry(tmp_path: Path,monkeypatch) -> None:
    import os
    descriptor=_native_aggregate_descriptor(tmp_path);path=Path(descriptor['receipt_path'])
    def fail_fsync(fd):raise OSError('owned fsync fault')
    with monkeypatch.context() as patch:
        patch.setattr(os,'fsync',fail_fsync)
        with pytest.raises((OSError,ValueError)):
            _native_aggregate_cycle()._reserve_native_receipt(descriptor)
    assert path.exists();before=path.read_bytes()
    with pytest.raises((OSError,ValueError)):
        _native_aggregate_cycle()._reserve_native_receipt(descriptor)
    assert path.read_bytes()==before


def test_native_aggregate_changed_marker_readback_cannot_claim_creator(tmp_path: Path,monkeypatch) -> None:
    import os
    descriptor=_native_aggregate_descriptor(tmp_path);path=Path(descriptor['receipt_path']);actual_fsync=os.fsync
    def change_after_flush(fd):
        actual_fsync(fd)
        path.write_bytes(b'OWNED_READBACK_CHANGED')
    with monkeypatch.context() as patch:
        patch.setattr(os,'fsync',change_after_flush)
        with pytest.raises((OSError,ValueError)):
            _native_aggregate_cycle()._reserve_native_receipt(descriptor)
    assert path.read_bytes()==b'OWNED_READBACK_CHANGED'
    with pytest.raises((OSError,ValueError)):
        _native_aggregate_cycle()._reserve_native_receipt(descriptor)
    assert path.read_bytes()==b'OWNED_READBACK_CHANGED'


@pytest.mark.parametrize("encoding", ["utf-16-le", "utf-16-be"])
def test_native_aggregate_no_bom_utf16_declarations_reject(tmp_path, encoding):
    descriptor = _native_aggregate_descriptor(tmp_path)
    xml = '<!DOCTYPE testsuites [<!ENTITY result "untrusted">]>' + _native_aggregate_xml().decode().split('?>', 1)[1]
    with pytest.raises(ValueError):
        _native_aggregate_cycle()._parse_native_junit(descriptor, xml.encode(encoding))


@pytest.mark.parametrize("insertion", ["prefix", "suite", "tail", "processing"])
def test_native_aggregate_text_tails_and_processing_reject(tmp_path, insertion):
    raw = _native_aggregate_xml()
    if insertion == "prefix":
        raw = raw.replace(b'<testsuites>', b'<testsuites>untrusted')
    elif insertion == "suite":
        raw = raw.replace(b'<testcase ', b'untrusted<testcase ', 1)
    elif insertion == "tail":
        raw = raw.replace(b'</testsuite>', b'untrusted</testsuite>')
    else:
        raw = b'<?untrusted result="pass"?>' + raw
    with pytest.raises(ValueError):
        _native_aggregate_cycle()._parse_native_junit(_native_aggregate_descriptor(tmp_path), raw)


def test_native_aggregate_host_transport_is_bounded_and_does_not_overlay_environment(tmp_path, monkeypatch):
    from types import SimpleNamespace
    cycle = _native_aggregate_cycle()
    descriptor = _native_aggregate_descriptor(tmp_path)
    data = {"descriptor": descriptor, "host": {"executable": r"C:\owned\powershell.exe", "timeout_sec": 5,
        "maximum_output_characters": 1024}, "implementation_manifest": {
            "automation/orchestration/" + ("long_source_" * 8) + str(index) + ".py": "a" * 64 for index in range(100)}}
    calls = []
    def transport(command, **options):
        calls.append((command, options))
        return SimpleNamespace(returncode=0, stdout=json.dumps({"process": {"owned": True}, "environment": descriptor["environment"]}))
    monkeypatch.setattr(cycle.subprocess, "run", transport)
    before = dict(__import__("os").environ)
    assert cycle._invoke_native_aggregate_host(tmp_path, data) == {"owned": True}
    command, options = calls[0]
    assert len(__import__("subprocess").list2cmdline(command)) < 32767
    assert options["env"] == descriptor["environment"] and __import__("os").environ == before
    payload = json.loads(options["input"])
    assert payload["environment"] == descriptor["environment"]
    assert payload["parameters"]["StdIn"] == "" and payload["parameters"]["ArgumentList"] == descriptor["argv"]
    assert len(payload["pins"]) >= 100


@pytest.mark.parametrize("value", [False, 0, 1, "true", [True], {"value": True}])
def test_native_confirmed_process_requires_actual_retry_value(value):
    process = _native_aggregate_process()
    process["retry_allowed"] = value
    with pytest.raises(ValueError):
        _native_aggregate_check_process(process)


@pytest.mark.parametrize("value", [0, 4294967296, True, 123.0, "123", [123]])
def test_native_process_id_preserves_source_uint32_boundary(value):
    process = _native_aggregate_process()
    process["root_process_id"] = value
    with pytest.raises(ValueError):
        _native_aggregate_check_process(process)


def test_native_process_uint32_maximum_is_valid_projection():
    process = _native_aggregate_process()
    process["root_process_id"] = 4294967295
    _native_aggregate_check_process(process)


def test_native_rejected_projection_retains_only_known_bounded_evidence(tmp_path):
    cycle = _native_aggregate_cycle()
    descriptor = _native_aggregate_descriptor(tmp_path)
    process = _native_aggregate_process()
    process.update(stdout="private sentinel output", stderr="private sentinel error", unknown={"secret": "sentinel"})
    process["root_process_id"] = False
    process["executable"] = "unadmitted sentinel executable"
    evidence = cycle._native_rejected_process_evidence(process, descriptor)
    assert evidence["available"] is True
    assert evidence["projection"]["root_process_id"] is False
    assert evidence["field_types"]["root_process_id"] == "bool"
    assert "executable" not in evidence["projection"]
    encoded = json.dumps(evidence)
    assert "sentinel" not in encoded
    assert not {"stdout", "stderr", "unknown"} & (evidence["projection"].keys() | evidence["field_types"].keys())
    assert evidence["projection_sha256"] == cycle._native_hash(process)
    assert cycle._native_rejected_process_evidence(None, descriptor) == {
        "available": False, "projection": None, "field_types": {}, "projection_sha256": None}


def test_native_host_bridge_rejection_keeps_returned_projection_for_diagnosis(tmp_path, monkeypatch):
    from types import SimpleNamespace
    cycle = _native_aggregate_cycle()
    descriptor = _native_aggregate_descriptor(tmp_path)
    projection = _native_aggregate_process()
    projection.update(shape_valid=False, root_process_id=None)
    data = {"descriptor": descriptor, "host": {"executable": r"C:\owned\powershell.exe", "timeout_sec": 5,
        "maximum_output_characters": 1024}, "implementation_manifest": {}}
    result = {"process": projection, "environment": descriptor["environment"],
        "bridge_error": "NATIVE_PROCESS_RAW_TYPES_REJECTED", "raw_field_types": {"root_process_id": "System.UInt32"}}
    monkeypatch.setattr(cycle.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(result)))
    with pytest.raises(ValueError) as caught:
        cycle._invoke_native_aggregate_host(tmp_path, data)
    assert caught.value.native_process_projection == projection
    assert caught.value.native_raw_process_field_types == result["raw_field_types"]
def test_p505_selected_snapshot_private_refusal_fails_before_provider(monkeypatch):
    from tests.orchestration.test_aios_resume_state import (
        _p505_memory_case,
        _p505_ordinary_reader,
    )
    case = _p505_memory_case(monkeypatch)
    request, packet, launch, *_ = case['proof_inputs']
    # The actual collector sees the private name but refuses its contents.
    payloads = {'safe/file.py': b'owned', '.git': b'must never be read'}
    _p505_ordinary_reader(monkeypatch, payloads)
    with pytest.raises(ValueError):
        n05_cycle.capture_provider_preservation(request, packet, launch, 'before')


def test_p505_selected_actual_interval_binds_process_not_caller_pass(monkeypatch):
    from tests.orchestration.test_aios_resume_state import _p505_memory_case
    case = _p505_memory_case(monkeypatch)
    request, packet, launch, capture, before, after, started = case['proof_inputs']
    original = n05_cycle.complete_provider_preservation(request, packet, launch, capture, before, after, started)
    capture['provider_interval'] = original
    capture['process']['duration_sec'] += 1
    with pytest.raises(ValueError, match='preservation_execution_mismatch'):
        n05_cycle.verify_provider_preservation(request, packet, launch, capture)

_P505_PS_MEMORY_SEAM_HARNESS = r'''
param([string]$SourcePath)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
# Explicit stock host modules, never a profile or repository bootstrap.
Import-Module ([IO.Path]::Combine($PSHOME,'Modules/Microsoft.PowerShell.Utility/Microsoft.PowerShell.Utility.psd1'))
Import-Module ([IO.Path]::Combine($PSHOME,'Modules/Microsoft.PowerShell.Management/Microsoft.PowerShell.Management.psd1'))
class P505MemoryFile {
    static [hashtable]$Files=@{}
    static [bool] Exists([string]$path){return [P505MemoryFile]::Files.ContainsKey($path)}
    static [byte[]] ReadAllBytes([string]$path){
        if(-not [P505MemoryFile]::Exists($path)){throw 'OWNED_MEMORY_FILE_ABSENT'}
        return [P505MemoryFile]::Files[$path]
    }
    static [void] Move([string]$source,[string]$target){
        if([P505MemoryFile]::Exists($target)){throw 'OWNED_MEMORY_TARGET_EXISTS'}
        [P505MemoryFile]::Files[$target]=[P505MemoryFile]::ReadAllBytes($source)
        [P505MemoryFile]::Files.Remove($source)
    }
}
class P505MemoryDirectory {static [string] CreateDirectory([string]$path){return $path}}
function Start-Process {throw 'P505_FORBIDDEN_PROCESS'}
function Invoke-WebRequest {throw 'P505_FORBIDDEN_NETWORK'}
function Invoke-RestMethod {throw 'P505_FORBIDDEN_NETWORK'}
function Invoke-Expression {throw 'P505_FORBIDDEN_EVAL'}
$tokens=$null;$errors=$null
$text=[IO.File]::ReadAllText($SourcePath)
$ast=[Management.Automation.Language.Parser]::ParseInput($text,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'P505_SOURCE_PARSE_FAILED'}
$names=@('Get-AiOsBoundHash','Get-AiOsBoundPreservationSnapshot','Complete-AiOsBoundPreservationInterval','Invoke-AiOsBoundRelayRequest')
$allowed=@('Get-AiOsBoundHash','Invoke-AiOsBoundPython','Resolve-AiOsBoundPath','Import-AiOsBoundFunctions',
    'ConvertFrom-Json','ConvertTo-Json','Join-Path','Get-AiOsBoundRepositoryEvidence','Get-AiOsBoundCoveredMetadata',
    'Assert-AiOsBoundReadback','Write-AiOsBoundObservation','Test-AiOsBoundPreflight','Test-AiOsBoundCostAndLock',
    'Select-Object','Get-AiOsWorkerOutputManifest','Write-AiOsBoundBytes','Get-AiOsBoundPreservationSnapshot',
    'Invoke-AiOsBoundProvider','Get-AiOsBoundProcessProjection','Complete-AiOsBoundPreservationInterval',
    'Test-AiOsWorkerOutput','Add-AiOsBoundCost')
foreach($name in $names){
    $definitions=@($ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -ceq $name},$true))
    if($definitions.Count -ne 1){throw 'P505_EXPECTED_EXACT_FUNCTION'}
    foreach($call in $definitions[0].FindAll({param($node) $node -is [Management.Automation.Language.CommandAst]},$true)){
        if($call.GetCommandName() -cnotin $allowed){throw ('P505_UNAUDITED_COMMAND:'+ $call.GetCommandName())}
    }
    foreach($type in $definitions[0].FindAll({param($node) $node -is [Management.Automation.Language.TypeExpressionAst]},$true)){
        if($type.TypeName.FullName -cnotin @('IO.File','IO.Directory','IO.Path','Text.UTF8Encoding','Text.Encoding',
            'DateTime','StringComparison','Security.Cryptography.SHA256','BitConverter','bool','int','string')){
            throw ('P505_UNAUDITED_STATIC_TYPE:'+ $type.TypeName.FullName)
        }
    }
    # Only direct filesystem boundaries are adapted. The worker's control flow,
    # catch paths and before/provider/after helper invocations remain actual.
    $definition=$definitions[0].Extent.Text.Replace('[IO.File]','[P505MemoryFile]').Replace('[IO.Directory]','[P505MemoryDirectory]').Replace('$PSScriptRoot','$script:P505OwnedScriptRoot')
    . ([scriptblock]::Create($definition))
}
function Resolve-AiOsBoundPath {param($Path,$Under) return $Path}
function Import-AiOsBoundFunctions {param($Path)}
function Get-AiOsBoundCoveredMetadata {param($Request,$Task,$Binding,$Evidence,$Metadata) return $Metadata}
function Assert-AiOsBoundReadback {param($Value,$Binding,$Kind,$RepoRoot,$RelayRoot,$RequestJson,$PacketSha256)}
function Get-AiOsBoundRepositoryEvidence {param($Request) return [pscustomobject]@{identity=$Request.repository_identity;paths=@();complete=$true;errors=@()}}
function Test-AiOsBoundPreflight {param($Request,$Binding,$LogPath) return @{ok=$true}}
function Test-AiOsBoundCostAndLock {param($Request,$LedgerPath) return @{ok=$true;defer=$false}}
function Get-AiOsWorkerOutputManifest {param($RepoRoot,$SourcePaths) $value=@{};foreach($path in $SourcePaths){$value[$path]=$null};return $value}
function Invoke-AiOsBoundPython {
    param($PythonExecutable,$RepoRoot,$Code,$InputObject)
    if($Code.Contains('capture_provider_preservation')){
        $script:Events.Add([string]$InputObject.phase)
        if($script:Mode -ceq ($InputObject.phase+'-loss')){throw ('OWNED_'+$InputObject.phase+'_LOSS')}
        return @{utf8=('DECLARED_MEMORY_'+$InputObject.phase);sha256=('b'*64)}
    }
    if($Code.Contains('complete_provider_preservation')){
        $script:Events.Add('proof')
        if($script:Mode -ceq 'proof-loss'){throw 'OWNED_PROOF_LOSS'}
        return @{schema='DECLARED_MEMORY_PROTOCOL_ONLY';before=$InputObject.before;after=$InputObject.after}
    }
    return [pscustomobject]@{request=$script:Request;task=$script:Task;binding=[pscustomobject]$script:Binding}
}
function Write-AiOsBoundBytes {
    param($Path,$Under,[byte[]]$Bytes,[switch]$AllowIdentical)
    $role=if($Path.EndsWith('.launch.json')){'launch-write'}elseif($Path.Contains('.execution-recovery.')){'recovery-write'}else{'execution-write'}
    $script:Events.Add($role)
    if($role -ceq 'execution-write' -and $script:Mode -in @('primary-save-loss','both-save-loss')){throw 'OWNED_PRIMARY_SAVE_LOSS'}
    if($role -ceq 'recovery-write' -and $script:Mode -ceq 'both-save-loss'){throw 'OWNED_RECOVERY_SAVE_LOSS'}
    if([P505MemoryFile]::Exists($Path)){throw 'OWNED_CREATE_NEW_COLLISION'}
    [P505MemoryFile]::Files[$Path]=$Bytes
    if($role -ceq 'launch-write' -and $script:Mode -ceq 'launch-flush-loss'){throw 'OWNED_LAUNCH_FLUSH_LOSS'}
}
function Invoke-AiOsBoundProvider {param($Request,$PromptText) $script:Events.Add('provider');$script:ProviderCalls++;return $script:Projection}
function Get-AiOsBoundProcessProjection {param($Value) return $Value}
function Test-AiOsWorkerOutput {
    param($PacketId,$AllowedPaths,$RepoRoot,$RelayRoot,$LogPath,$CampaignBinding,$BeforeManifest,$ControllerMetadataPaths,$ChangedPathsEvidence,$ExpectedStatusParserSha256,$DiagnosticWriteChoice)
    $script:Events.Add('scope')
    return [pscustomobject]@{pass=$true;diagnostic_write_requested=$true;diagnostic_write_completed=$true;diagnostic_write_error=''}
}
function Add-AiOsBoundCost {param($Request,$Binding,$Ledger,$ProviderRun) $script:Events.Add('cost')}
function Write-AiOsBoundObservation {
    param($Request,$Binding,$TaskId,$Status,$Reason,$ExecutionPath,$ExecutionSha,$PendingCapture,$PrimaryError,$SecondaryError,$PendingAction,$OutputEvidence)
    $script:Events.Add('observation')
    return [pscustomobject]@{status=$Status;reason=$Reason;retry_allowed=$false;authority_granted=$false;
        primary=$PrimaryError;secondary=$SecondaryError;pending_capture=$PendingCapture;pending_action=$PendingAction}
}
$Root='C:\P505_SELECTED_MEMORY_ONLY';$Relay=$Root+'\relay\selected'
$script:P505OwnedScriptRoot=$Root+'\automation\orchestration\relay'
$utf8=[Text.UTF8Encoding]::new($false)
$script:Request=[pscustomobject]@{python_executable='C:\P505_MEMORY_RUNTIME\python.exe';repo_root=$Root;relay_root=$Relay;
    policy_path=$Root+'\owned-policy.json';controller_metadata_paths=@();source_paths=@('safe/task.py');allowed_paths=@('safe/task.py');packet_id='PACKET';
    source_manifest=[pscustomobject]@{'automation/orchestration/aios_repo_state_evidence.py'=('c'*64)};
    repository_identity=[pscustomobject]@{repo_root=$Root;git_dir=$Root+'\.git';branch='owned';commit=('a'*40);resolved=$true}}
$script:Binding=@{request_sha256=('a'*64);task_id='owned';packet_id='PACKET';attempt_id='attempt';attempt_number=0;claim_task_id='owned';claim_acquired_at='owned';claim_identity_sha256=('b'*64);campaign_id='owned'}
$script:Task=[pscustomobject]@{id=('bound-'+('a'*64));request_json=($Request|ConvertTo-Json -Depth 20 -Compress);prompt_text='owned'}
$packetBytes=$utf8.GetBytes(($Task|ConvertTo-Json -Depth 30 -Compress));$packetHash=Get-AiOsBoundHash $packetBytes
$inbox=$Relay+'\inbox\'+$Task.id+'.task.json';$running=$Relay+'\running\'+$Task.id+'.task.json';$launch=$Relay+'\outbox\'+$Task.id+'.launch.json'
$script:Projection=[pscustomobject]@{working_directory=$Root;stdin_bytes_written=5;shape_valid=$true;cleanup_state='CONFIRMED';root_exit_confirmed=$true;tree_exit_confirmed=$true;drains_completed=$true;stdin_writer_joined=$true;exit_code=0;child_exit_code=0;stdin_completed=$true;timed_out=$false;startup_failed=$false;process_error_present=$false}
$results=[Collections.Generic.List[object]]::new()
foreach($script:Mode in @('valid','before-loss','after-loss','proof-loss','primary-save-loss','both-save-loss','launch-flush-loss')){
    [P505MemoryFile]::Files=@{};[P505MemoryFile]::Files[$inbox]=$packetBytes
    $script:Events=[Collections.Generic.List[string]]::new();$script:ProviderCalls=0
    $first=Invoke-AiOsBoundRelayRequest $Root $Relay $inbox $packetHash $Request.python_executable $true
    $initial=@($Events);$count=$ProviderCalls
    if($Mode -ceq 'valid'){
        if($first.status -cne 'EXECUTED_AWAITING_VALIDATION' -or ($initial -join ',') -cne 'launch-write,before,provider,after,proof,execution-write,scope,cost,observation'){throw ('P505_VALID_ORDER:'+($initial -join ',')+':'+($first|ConvertTo-Json -Depth 6 -Compress)+':'+$Error[0])}
    }else{
        if($first.status -cne 'FINALIZATION_RECONCILIATION_REQUIRED'){throw ('P505_UNCERTAINTY_NOT_STICKY:'+ $Mode+':'+$first.status+':'+$first.reason)}
        if($Mode -ceq 'both-save-loss' -and ($first.primary -cne 'OWNED_PRIMARY_SAVE_LOSS' -or $first.secondary -cne 'OWNED_RECOVERY_SAVE_LOSS' -or $null -eq $first.pending_capture)){throw 'P505_CAPTURE_CAUSES_LOST'}
    }
    if(-not [P505MemoryFile]::Exists($launch)){throw 'P505_LAUNCH_INTENT_LOST'}
    $second=Invoke-AiOsBoundRelayRequest $Root $Relay $running $packetHash $Request.python_executable $true
    if($ProviderCalls -ne $count -or $first.retry_allowed -or $second.retry_allowed -or $first.authority_granted -or $second.authority_granted){throw 'P505_REPLAY_OR_AUTHORITY'}
    $results.Add(@{mode=$Mode;first=$first.status;reason=$first.reason;second=$second.status;provider_calls=$count;initial_order=$initial;launch_retained=$true})
}
[Console]::WriteLine((@{tier='ACTUAL_EXTRACTED_PS_CONTROL_FLOW_MEMORY_BOUNDARIES_ONLY';host=$PSVersionTable.PSVersion.ToString();argv=[Environment]::GetCommandLineArgs();results=$results;disk_fixture_writes=0;provider_native_calls=0}|ConvertTo-Json -Depth 30 -Compress))
'''


# Owner-approved compatibility repair: preview is separate from real work.
def _forbid_active_use_preview_effects(monkeypatch):
    from automation.orchestration.relay import aios_self_consuming_codex_cycle_v1 as cycle

    def forbidden(*args, **kwargs):
        raise AssertionError("packet preview must not read requests, enqueue, or start work")

    for name in ("validate_bound_request", "enqueue_prompt", "run_self_consuming_cycle", "_worker", "_preview_selected_event"):
        monkeypatch.setattr(cycle, name, forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    return cycle


def test_active_use_preview_prints_existing_packet_without_work(monkeypatch, capsys, tmp_path):
    import sys

    cycle = _forbid_active_use_preview_effects(monkeypatch)
    expected = cycle.build_next_pr_lifecycle_packet()
    monkeypatch.setattr(sys, "argv", ["cycle", "--print-next-packet"])
    assert cycle.main() == 0
    captured = capsys.readouterr()
    assert captured.out == expected + "\n"
    assert captured.err == ""
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("extra", [["--request-json", "unused.json"], ["--dry-run"]])
def test_active_use_preview_rejects_mixed_work_options(monkeypatch, capsys, extra):
    import sys

    cycle = _forbid_active_use_preview_effects(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["cycle", "--print-next-packet", *extra])
    with pytest.raises(SystemExit) as stopped:
        cycle.main()
    assert stopped.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "--print-next-packet cannot be combined" in captured.err


def test_active_use_preview_requires_explicit_mode(monkeypatch, capsys):
    import sys

    cycle = _forbid_active_use_preview_effects(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["cycle"])
    with pytest.raises(SystemExit) as stopped:
        cycle.main()
    assert stopped.value.code == 2
    assert "one of --request-json or --print-next-packet is required" in capsys.readouterr().err
