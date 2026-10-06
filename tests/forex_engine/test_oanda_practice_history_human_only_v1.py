import json
import subprocess
from pathlib import Path


SCRIPT = Path("scripts/forex_delivery/Acquire-AiOsOandaPracticeHistory.HUMAN_ONLY.ps1")


def _retry_function_block() -> str:
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index("function Get-AiOsPropertyValue")
    end = text.index("function Invoke-AiOsPracticeResponse")
    return text[start:end]


def _run_powershell_json(body: str):
    script = (
        "$ErrorActionPreference = 'Stop'\n"
        "Set-StrictMode -Version Latest\n"
        f"{_retry_function_block()}\n"
        f"{body}\n"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True,
        text=True,
        capture_output=True,
    )
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return json.loads(lines[-1])


def test_practice_history_helper_is_human_only_get_only_and_practice_host():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "Read-Host" in text
    assert "-AsSecureString" in text
    assert "api-fxpractice.oanda.com" in text
    assert "-Method Get" in text
    assert ("-Method " + "Post") not in text
    assert ("-Method " + "Put") not in text
    assert ("-Method " + "Patch") not in text
    assert ("-Method " + "Delete") not in text
    assert "account_mutation = $false" in text
    assert ".aios/runtime/forex_practice_history_human_inbox" in text


def test_practice_history_helper_does_not_print_or_persist_token_markers():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "Write-AiOsManifest -ManifestPath $manifestPath" in text
    assert "Write-AiOsJsonAtomic" in text
    assert "secret_written = $false" in text
    assert "header_written = $false" in text
    assert "ZeroFreeBSTR" in text
    assert "Authorization\" = " not in text
    assert "token CLI" not in text
    assert ("token" + "_hash") not in text


def test_practice_history_helper_paginates_and_promotes_temp_files():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "MaxBatchesPerInstrument" in text
    assert "while ($batchCount -lt $MaxBatchesPerInstrument)" in text
    assert "TOTAL_CANDLES" in text
    assert "Read-AiOsDateTimeOffset -Value $nextStart" in text
    assert "MinimumExclusiveTime" in text
    assert "pagination boundary duplicate or rewind" in text
    assert "Invoke-RestMethod -Uri $Uri -Method Get -Headers $Headers -TimeoutSec $TimeoutSec -ErrorAction Stop" in text


def test_practice_history_helper_retries_transient_504_and_related_statuses():
    text = SCRIPT.read_text(encoding="utf-8")
    for status in ("408", "425", "429", "500", "502", "503", "504"):
        assert status in text
    assert "Test-AiOsTransientFailure" in text
    assert "PRACTICE_RETRY" in text
    assert "MaxAttemptsPerBatch = 5" in text
    assert "Get-AiOsHttpStatusCode -ErrorRecord $_ -Exception $_.Exception" in text
    assert "ErrorDetails.Message" in text
    assert "(?<code>401|403|404|408|425|429|500|502|503|504)" in text
    assert "\\b(408|425|429|500|502|503|504)\\b" in text


def test_practice_history_helper_detects_504_from_powershell_error_record_shape():
    result = _run_powershell_json(
        r"""
        $exception = [System.Net.WebException]::new('Invoke-RestMethod failed')
        $record = [System.Management.Automation.ErrorRecord]::new(
            $exception,
            'WebCmdletWebResponseException',
            [System.Management.Automation.ErrorCategory]::InvalidOperation,
            $null
        )
        $record.ErrorDetails = [System.Management.Automation.ErrorDetails]::new('Invoke-RestMethod : HTTP 504 Gateway Timeout')
        $status = Get-AiOsHttpStatusCode -ErrorRecord $record -Exception $record.Exception
        $transient = Test-AiOsTransientFailure -ErrorRecord $record -Exception $record.Exception -StatusCode $status
        [pscustomobject]@{
            status = $status
            transient = $transient
        } | ConvertTo-Json -Compress
        """
    )
    assert result == {"status": 504, "transient": True}


def test_practice_history_helper_retries_first_504_and_continues():
    result = _run_powershell_json(
        r"""
        $script:attempts = 0
        $script:sleeps = @()
        function Start-Sleep { param([int]$Seconds) $script:sleeps += $Seconds }
        function Invoke-RestMethod {
            $script:attempts += 1
            if ($script:attempts -eq 1) {
                $exception = [System.Net.WebException]::new('Gateway timeout')
                $record = [System.Management.Automation.ErrorRecord]::new(
                    $exception,
                    'WebCmdletWebResponseException',
                    [System.Management.Automation.ErrorCategory]::InvalidOperation,
                    $null
                )
                $record.ErrorDetails = [System.Management.Automation.ErrorDetails]::new('Response status code does not indicate success: 504.')
                throw $record
            }
            return [pscustomobject]@{ candles = @([pscustomobject]@{ complete = $true }) }
        }
        $response = Invoke-AiOsPracticeGetWithRetry -Uri 'https://api-fxpractice.oanda.com/test' -Headers @{} -Instrument 'GBP_CAD' -BatchNumber 2 -TimeoutSec 1 -MaxAttemptsPerBatch 5 -RetryMaxDelaySec 1
        [pscustomobject]@{
            attempts = $script:attempts
            sleep_count = @($script:sleeps).Count
            candles = @($response.candles).Count
        } | ConvertTo-Json -Compress
        """
    )
    assert result == {"attempts": 2, "sleep_count": 1, "candles": 1}


def test_practice_history_helper_retry_exhaustion_fails_closed_without_extra_attempts():
    result = _run_powershell_json(
        r"""
        $script:attempts = 0
        function Start-Sleep { param([int]$Seconds) }
        function Invoke-RestMethod {
            $script:attempts += 1
            $exception = [System.Net.WebException]::new('Gateway timeout')
            $record = [System.Management.Automation.ErrorRecord]::new(
                $exception,
                'WebCmdletWebResponseException',
                [System.Management.Automation.ErrorCategory]::InvalidOperation,
                $null
            )
            $record.ErrorDetails = [System.Management.Automation.ErrorDetails]::new('HTTP 504 Gateway Timeout')
            throw $record
        }
        $message = ''
        try {
            Invoke-AiOsPracticeGetWithRetry -Uri 'https://api-fxpractice.oanda.com/test' -Headers @{} -Instrument 'GBP_CAD' -BatchNumber 2 -TimeoutSec 1 -MaxAttemptsPerBatch 2 -RetryMaxDelaySec 1 | Out-Null
        }
        catch {
            $message = $_.Exception.Message
        }
        [pscustomobject]@{
            attempts = $script:attempts
            failed_closed = ($message -match 'request failed closed')
        } | ConvertTo-Json -Compress
        """
    )
    assert result == {"attempts": 2, "failed_closed": True}


def test_practice_history_helper_401_403_fail_closed_without_retry():
    for status in (401, 403):
        result = _run_powershell_json(
            rf"""
            $script:attempts = 0
            function Start-Sleep {{ param([int]$Seconds) }}
            function Invoke-RestMethod {{
                $script:attempts += 1
                $exception = [System.Net.WebException]::new('HTTP {status}')
                $record = [System.Management.Automation.ErrorRecord]::new(
                    $exception,
                    'WebCmdletWebResponseException',
                    [System.Management.Automation.ErrorCategory]::InvalidOperation,
                    $null
                )
                $record.ErrorDetails = [System.Management.Automation.ErrorDetails]::new('HTTP {status}')
                throw $record
            }}
            $message = ''
            try {{
                Invoke-AiOsPracticeGetWithRetry -Uri 'https://api-fxpractice.oanda.com/test' -Headers @{{}} -Instrument 'GBP_CAD' -BatchNumber 2 -TimeoutSec 1 -MaxAttemptsPerBatch 5 -RetryMaxDelaySec 1 | Out-Null
            }}
            catch {{
                $message = $_.Exception.Message
            }}
            [pscustomobject]@{{
                attempts = $script:attempts
                failed_closed = ($message -match 'credential/authorization failure')
            }} | ConvertTo-Json -Compress
            """
        )
        assert result == {"attempts": 1, "failed_closed": True}


def test_practice_history_helper_uses_bounded_backoff_and_retry_after():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "Get-AiOsRetryAfterSeconds" in text
    assert "Retry-After" in text
    assert "$base = @(2, 5, 10, 20, 30)" in text
    assert "Get-Random -Minimum 80 -Maximum 121" in text
    assert "RetryMaxDelaySec -gt 30" in text


def test_practice_history_helper_fails_closed_for_exhausted_and_permanent_failures():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "credential/authorization failure" in text
    assert "request/instrument contract failure" in text
    assert "request failed closed" in text
    assert "$attempt -ge $MaxAttemptsPerBatch" in text
    assert "malformed response failed closed" in text


def test_practice_history_helper_reuses_completed_instruments_and_resumes_partial():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "Test-AiOsExistingArtifactCompleted" in text
    assert "STATUS=REUSED_COMPLETED" in text
    assert "continue" in text
    assert "STATUS=RESUME_FROM_PARTIAL" in text
    assert "EXISTING_CANDLES" in text
    assert "NEXT_START" in text


def test_practice_history_helper_writes_sanitized_checkpoints_before_next_batch():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "AIOS_OANDA_PRACTICE_HISTORY_CHECKPOINT_V1" in text
    for field in (
        "batch_number",
        "request_start_time",
        "request_end_time",
        "first_candle_time",
        "last_candle_time",
        "candle_count",
        "cumulative_candle_count",
        "artifact_hash",
        "completed",
        "next_start_time",
    ):
        assert field in text
    assert "CHECKPOINT_WRITTEN=TRUE" in text


def test_practice_history_helper_does_not_restart_from_first_instrument_after_validation():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "STATUS=REUSED_COMPLETED" in text
    assert "Write-AiOsManifest -ManifestPath $manifestPath" in text
    assert "Test-AiOsExistingArtifactCompleted" in text
    assert "continue" in text


def test_practice_history_helper_atomicity_protects_promoted_data_and_manifest():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "Write-AiOsJsonAtomic" in text
    assert "$tempPath = \"$Path.tmp.$PID\"" in text
    assert "Move-Item -LiteralPath $tempPath -Destination $Path -Force" in text
    assert "Write-AiOsPracticeArtifact" in text
    assert "Write-AiOsManifest" in text
    assert "temporary file was empty" in text


def test_practice_history_helper_validates_completed_mba_candle_contract():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "Assert-AiOsCandlePriceContract" in text
    assert "incomplete candle encountered" in text
    for side in ("bid", "ask", "mid"):
        assert f'"{side}"' in text
    for key in ("o", "h", "l", "c"):
        assert f'"{key}"' in text
