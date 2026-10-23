Set-StrictMode -Version Latest

function Get-AiOsCodexPacketContract {
    [CmdletBinding()]
    param()

    [ordered]@{
        schema = "AIOS_CODEX_PACKET_CONTRACT.v2"
        exact_first_line = "CODEX-ONLY PROMPT"
        required_markers = @("AI_OS EXECUTION TOKEN", "AI_OS BOOTSTRAP REQUIRED")
        required_scalar_fields = @(
            "MISSION ID", "MISSION NAME", "PROGRAM ID", "PROGRAM NAME",
            "EPIC ID", "EPIC NAME", "BUCKET ID", "BUCKET NAME",
            "PACKET ID", "PACKET NAME", "IDENTITY MARKER",
            "SUPERVISOR IDENTITY", "WORKER IDENTITY", "LOCK IDENTITY",
            "MODE", "ZONE", "LANE", "WORKTREE", "BRANCH",
            "APPROVAL AUTHORITY", "STOP POINT"
        )
        list_valued_fields = @(
            "ALLOWED PATHS", "FORBIDDEN PATHS", "PREFLIGHT",
            "VALIDATOR CHAIN", "FINAL REPORT FORMAT"
        )
        protected_action_fields = @(
            "STAGING AUTHORITY", "COMMIT AUTHORITY", "PUSH AUTHORITY",
            "PULL REQUEST AUTHORITY", "MERGE AUTHORITY"
        )
        protected_authority_pattern = "^(AUTHORIZED|NOT AUTHORIZED|PREPARE ONLY)(?:\b|\.)"
        required_repository_state_commands = @(
            "pwd", "git status --short --branch", "git branch --show-current",
            "git remote -v", "git rev-parse HEAD", "git diff --name-only"
        )
        unresolved_placeholder_patterns = @(
            "(?i)\bTODO\b", "(?i)\bTBD\b", "(?i)@filename\b",
            "(?i)path/to/file", "(?i)\[REAL-FILENAME\]", "\{[^{}]+\}",
            "(?i)<(?:placeholder|insert|replace)[^>]*>", "(?i)\bplaceholder(?:s|_token)?\b"
        )
        required_bootstrap_lines = @(
            "Read AGENTS.md first."
            "Read README.md second."
            "Use AGENTS.md as operating authority."
            "Use README.md as AI_OS front-door/context authority."
            "If task context conflicts with either file:"
            "STOP."
            "Report the conflict before continuing."
            "Read docs/governance/AI_OS_REPO_MEMORY.md."
            "Read docs/governance/aios-identity-and-lane-governance.md."
            "Read assigned lane instructions and the current operator instruction."
            "If unavailable, stop and report missing AI_OS context."
        )
        safety_flags = @("execution_allowed", "can_continue_without_anthony", "writes_files")
        operator_delivery = [ordered]@{
            target_operator_pastes = 1
            emit_one_complete_prompt_once = $true
            do_not_repeat_full_prompt_after_delivery = $true
            recovery_uses_smallest_safe_delta = $true
            regenerate_full_prompt_only_when_required_for_safe_execution = $true
            do_not_emit_prompt_and_duplicate_download_copy_unless_requested = $true
            resolve_mutable_repo_state_during_preflight_when_unknown = $true
            inspect_canonical_ownership_before_proposing_new_authority = $true
        }
        terminology = [ordered]@{
            preferred = [ordered]@{
                work_item = "engineering work packet"
                change_action = "apply"
                validation_result = "validation evidence"
            }
            drift_terms = @("workload pack", "task pack")
        }
    }
}

function Test-AiOsCodexPacketReport {
    param([AllowNull()]$Report, [string]$ExpectedSchema)
    if ($null -eq $Report -or $Report -isnot [pscustomobject]) { return $false }
    $names = @($Report.PSObject.Properties.Name)
    foreach ($name in @("schema", "packet_valid", "missing_required_fields", "validation_defects", "writes_files", "execution_allowed", "can_continue_without_anthony")) {
        if ($names -notcontains $name) { return $false }
    }
    if ($Report.schema -isnot [string] -or $Report.schema -cne $ExpectedSchema) { return $false }
    if ($Report.packet_valid -isnot [bool] -or $Report.packet_valid -ne $true) { return $false }
    foreach ($name in @("missing_required_fields", "validation_defects")) {
        if ($Report.$name -isnot [array] -or $Report.$name.Count -ne 0) { return $false }
    }
    foreach ($name in @("writes_files", "execution_allowed", "can_continue_without_anthony")) {
        if ($Report.$name -isnot [bool] -or $Report.$name -ne $false) { return $false }
    }
    return $true
}
