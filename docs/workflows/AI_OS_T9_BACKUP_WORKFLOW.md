# AI_OS T9 Backup Workflow

Status: Specification only. No backup automation is implemented by this document.

## Purpose

The Samsung T9 is support infrastructure for AI_OS backups, logs, reports, exports, evidence packets, dashboard assets, and operator recovery material.

This workflow records the approved backup architecture before any script, folder creation, robocopy command, or scheduled task is created.

## Non-Goals

- The T9 is not the canonical repo.
- The T9 does not replace `C:\Dev\Ai.Os`.
- The T9 must not store secrets, credentials, API keys, broker credentials, or live trading material.
- This document does not create scheduled tasks.
- This document does not run robocopy.
- This document does not create folders on the T9.
- This document does not copy, move, delete, rename, stage, commit, push, reset, clean, or stash anything.
- This document does not authorize reusing high-risk reorganization scripts for backup.

## Discovered T9 State

- T9 drive detected at `D:`.
- T9 label: `T9_FOB`.
- Filesystem: `exFAT`.
- Free space: about 931 GB.
- No `AIOS_T9`, `AI_OS_T9`, or `AiOS_T9` folder exists at `C:\` or `D:\`.
- No recursive exact `AIOS_T9` folder was found on `D:\`.
- Existing T9 numbered layout exists:
  - `D:\00_COMMAND_CENTER`
  - `D:\01_ACTIVE_OPERATIONS`
  - `D:\02_AI_WORKERS`
  - `D:\04_REPOS`
  - `D:\05_MEDIA`
  - `D:\06_MODELS`
  - `D:\07_KNOWLEDGE`
  - `D:\08_ARCHIVE`
  - `D:\99_STAGING`
  - `D:\AIOS_TERMINAL`
- No dedicated T9 or robocopy backup helper was found.
- No active Task Scheduler creation script was found.
- `automation/Ai_Os_Reorganize.ps1` is high risk and must not be reused for backup.
- Local `main` was aligned with `origin/main` during discovery.
- Known untracked backlog existed during discovery and must not be touched by backup design or future helper creation unless explicitly approved.

## Approved Root Strategy

Use the existing T9 numbered layout.

Do not create `D:\AIOS_T9` unless separately approved by the operator in a future APPLY lane.

The T9 layout should remain readable as an operator support drive, not as a second canonical repo or a hidden automation target.

## Recommended Folder Mapping

| Purpose | Recommended path |
|---|---|
| Command center / dashboard | `D:\00_COMMAND_CENTER\AI_OS` |
| Active operations | `D:\01_ACTIVE_OPERATIONS\AI_OS` |
| Repo backup mirror | `D:\04_REPOS\AI_OS\Ai_Os\current_mirror` |
| Snapshots | `D:\04_REPOS\AI_OS\Ai_Os\snapshots\YYYY-MM-DD_HHMM` |
| Logs | `D:\04_REPOS\AI_OS\Ai_Os\logs` |
| Archive | `D:\08_ARCHIVE\AI_OS` |
| Staging | `D:\99_STAGING\AI_OS` |

## Backup Source

```text
C:\Dev\Ai.Os
```

## Backup Destination

Primary mirror:

```text
D:\04_REPOS\AI_OS\Ai_Os\current_mirror
```

Snapshot destination:

```text
D:\04_REPOS\AI_OS\Ai_Os\snapshots
```

## Snapshot / Mirror Authority Boundary

GitHub `origin/main` is the canonical current repo truth. The local
`C:\Dev\Ai.Os` worktree is current working state only after `git status`
classification. T9 material is backup and recovery evidence; it does not become
active authority just because it exists on the drive.

Backup source classifications:

- `CURRENT_MAIN`: the current GitHub `origin/main` state, or local `main` after
  it is verified as synced to `origin/main`.
- `LOCAL_WORKTREE`: the current local checkout plus classified dirty or
  untracked state.
- `T9_MIRROR_CURRENT`: a T9 mirror that is explicitly labeled as current and
  matched to the current `HEAD` or approved manifest.
- `T9_SNAPSHOT_ARCHIVE`: a timestamped historical backup snapshot.
- `ARCHIVE_ONLY`: reference or recovery history that must not drive active repo
  state.
- `RESTORE_CANDIDATE`: a specific T9 file or folder that may be reviewed for
  restore after provenance, diff, duplicate-authority, and safety checks.
- `DO_NOT_ADOPT`: secret-bearing, obsolete, runtime-unsafe,
  authority-conflicting, duplicate-governance, superseded, or intentionally
  deleted material.

Authority rules:

- Never scan T9 snapshots as active repo source.
- Never copy from T9 into `C:\Dev\Ai.Os` without exact human-approved restore
  scope.
- Deleted files remain deleted unless a restore packet proves why they should
  return.
- Compare T9 files to current `main` and Git history before restore.
- Restore must be file-by-file or tightly scoped.
- T9 archive/reference files cannot override `AGENTS.md`, `docs/governance/`,
  or `docs/workflows/`.
- If a file exists on T9 but not in current `main`, classify it as
  `ARCHIVE_ONLY` or `RESTORE_CANDIDATE`, never active.
- Secret-bearing, obsolete, runtime-unsafe, authority-conflicting, or duplicate
  governance files must be `DO_NOT_ADOPT`.

Restore Candidate Review checklist:

- exact current target path
- exact T9 source path
- snapshot or mirror label
- reason for restore
- current `main` comparison
- Git history or deletion check if available
- duplicate-authority search
- forbidden path and secret scan
- diff review
- Anthony approval before restore or import

## Log Path

Recommended backup log directory:

```text
D:\04_REPOS\AI_OS\Ai_Os\logs
```

Recommended log naming pattern:

```text
backup_YYYY-MM-DD_HHMM.log
```

## Recommended Exclusions

Future backup helpers should exclude:

- `.git\`
- `.venv\`
- `venv\`
- `node_modules\`
- build, cache, and generated output folders
- `.codex_backups\`
- temporary files
- secrets, credentials, API keys, broker credentials, and live trading material
- known untracked backlog until classified or explicitly approved for backup

The future helper should report excluded categories plainly so the operator knows what was intentionally skipped.

## Recursion Guard

AI_OS backup helpers must never copy their own destination back into future backups. The backup source must not contain the backup root, the backup root must not contain the source repo, and the timestamped snapshot path must never resolve inside `C:\Dev\Ai.Os`.

The T9 backup helper must block the run when recursion is detected. This includes nested backup folders, old snapshot folders, `current_mirror`, `snapshots`, `AIOS_BACKUP*`, `T9_FOB`, or other T9 backup output appearing as candidate copy sources.

Backups must never include old snapshots unless Anthony explicitly approves a separate restore or archival lane. T9 output must never be copied back into `C:\Dev\Ai.Os` without exact human-approved restore scope.

Retention deletion remains separate. Recursion detection can block a run, but it does not approve cleanup, deletion, compression, restore, scheduled tasks, or T9-to-repo copy.

## Recommended Schedule

Schedule creation is not approved by this document.

Owner direction, 2026-10-31: the planned default is twice-weekly backup of changed or newly saved work, with Telegram reminders and a clear alert when the approved backup drive is missing. Preserve needed unique files and compact recovery checkpoints; avoid backing up backups. This documentation update does not install schedules or approve blanket deletion, retention cleanup, or restore.

Planned schedule after an incremental DRY_RUN helper proves safe:

1. Manual DRY_RUN first.
2. Manual APPLY backup second, with explicit operator approval.
3. Wednesday and Sunday at 20:00 `America/New_York`, using timezone rules that follow daylight saving time. Copy only changed or newly saved work within the approved source scope; do not create routine full copies.
4. Send a Telegram reminder and report a missing destination drive; preserve the pending checkpoint and do not silently redirect the backup to another drive. Keep bot credentials and destination identifiers in approved private configuration, outside the public repo and logs.
5. Prevent overlapping runs. Resume only from verified checkpoints, confirm copied files against the approved manifest or hashes, and record completion before advancing the checkpoint. Preserve incomplete work after an interruption. Do not perform automated deletion.

Reported deployment status, 2026-10-31: a cloud reminder has been set. The local incremental backup job and Telegram delivery are **not verified installed or operational**. A cloud reminder is not evidence that files were backed up or that Telegram delivery works.

Existing helper modes below describe current behavior, including `Auto` selecting a daily `Full` backup. They are not proof that this incremental schedule is implemented. Changing those modes, selecting eligible saved files, verifying recovery, and installing local jobs or Telegram delivery require separately scoped implementation and validation. No runtime, credential, or scheduling change is made by this policy update.

No Task Scheduler registration may occur until a future APPLY lane explicitly authorizes:

- exact script path
- exact task name
- exact schedule
- exact source and destination
- exact exclusions
- log path
- rollback/removal plan
- validation steps

## Future Helper Design

The next helper should start as DRY_RUN/report-only.

Approved controlled snapshot script path:

```text
scripts/backup/Start-AiOsT9SnapshotBackup.ps1
```

The first implementation is a manual operator-triggered snapshot helper with
preview support. It must not register scheduled tasks, create a daemon, move
the active repo, change remotes, or perform retention deletion.

Initial preview behavior should:

- confirm `C:\Dev\Ai.Os` exists
- confirm `D:` exists and is labeled `T9_FOB`
- confirm `D:\T9_FOB` exists
- print the planned snapshot path
- print the planned exclusions
- print the planned robocopy command as text only
- refuse to run robocopy
- refuse to create scheduled tasks
- refuse to touch known untracked backlog
- produce console output only

Manual APPLY backup behavior must choose one explicit backup mode:

```text
-BackupMode Auto
-BackupMode Full
-BackupMode Delta
-BackupMode ManifestOnly
-RetentionPreview
```

`Auto` is the default and avoids duplicate full snapshots:

- no prior successful manifest -> `Full`
- first successful backup of the local day -> `Full`
- current commit equals the previous backup commit -> `ManifestOnly`
- small productive git delta -> `Delta`
- large or unsafe delta -> `Full`

`Full` preserves the original timestamped snapshot behavior and is intended for
major checkpoints. `Delta` creates a timestamped delta folder and copies only
git-tracked changed or new files from the previous successful backup commit to
the current commit. It uses `git diff --name-status <previous>..<current>` and
filters copy candidates through `git ls-files`. Deleted files are recorded in
the manifest only. `ManifestOnly` writes a checkpoint manifest without copying
files.

`RetentionPreview` reports cleanup candidates only. It must print
`RETENTION_PREVIEW_ONLY` and must not delete anything.

## Default Post-Packet Savepoint Rule

When a packet or packet batch is fully merged, local `main` is synced, and
`git status --short --branch` is clean, AI_OS should run a ManifestOnly
savepoint directly. Do not re-audit the full backup system every time. Do not
ask about Full backup unless the operator explicitly requests Full backup. Do
not copy the full repo. ManifestOnly is the default closeout savepoint.

Standard compact command pattern:

```powershell
scripts/backup/Start-AiOsT9SnapshotBackup.ps1 -BackupMode ManifestOnly -OutputJson
```

Short operator report format:

```text
APPLIED?:
BACKUP_MODE:
MANIFEST_CREATED?:
MANIFEST_PATH:
COPIED_HUMAN:
FILE_COUNT_COPIED:
ROBOCOPY_RAN?:
HEAD_SHA:
FINAL_GIT_STATUS:
SAFE_NEXT_ACTION:
```

Full backup remains separate and requires explicit operator wording: full
backup.

## Backup-Session Data-Size Telemetry

Every backup run must report data-size telemetry so the operator can confirm
what was measured, what already exists on the T9, and what this run produced.

Required fields:

- **Source data measured** — repo size after exclusions.
- **Current backup size (T9)** — cumulative size of `D:\T9_FOB` after this run.
- **Copied this run** — file count and byte size copied this session.
- **Skipped (already current)** — file count robocopy left unchanged.
- **Produced this backup session** — byte size written by this run.

The same summary must appear in Preview/DRY_RUN where measurable. In Preview,
`Copied this run`, `Skipped`, and `Produced this backup session` read
`pending (preview — robocopy not run)` because robocopy does not execute.

Required readable text (console window and report):

```text
Source data measured:        1.39 GB
Current backup size (T9):    1.42 GB
Copied this run:             18 files / 42.7 MB
Skipped (already current):   1,204 files
Produced this backup session: 248 MB
```

Automation mode (`-OutputJson`) must expose these as machine fields without
dirtying stdout: `source_bytes`, `dest_bytes`, `copied_bytes`, `files_copied`,
`files_skipped`, plus the `_human` formatted variants.

Mode-aware manifests must also expose:

- `backup_mode`
- `requested_backup_mode`
- `selected_backup_mode_reason`
- `base_backup_id`
- `base_backup_commit_hash`
- `changed_files`
- `deleted_files`
- `file_count_copied`
- `delta_source_range`
- `restore_requires_full_backup`
- `retention_class`
- `retention_preview_candidates`

Implemented in `scripts/backup/Start-AiOsT9SnapshotBackup.ps1`. File counts are
parsed from the robocopy summary `Files :` row; when unavailable the script
reports `count unavailable` rather than a misleading zero.

## Robocopy Safety Notes

Robocopy must not run in this specification lane.

Future robocopy use should avoid destructive mirror behavior until proven safe. In particular:

- Do not use `/MIR` until the destination is confirmed to be dedicated to AI_OS backup output.
- Prefer a non-destructive copy preview first.
- Log every run.
- Confirm source and destination before execution.
- Stop if the T9 drive label does not match `T9_FOB`.
- Stop if source is not `C:\Dev\Ai.Os`.
- Stop if destination resolves outside the approved T9 layout.
- Do not run robocopy for `Delta` or `ManifestOnly`.
- Never delete files as part of `RetentionPreview`.

## Retention Preview Policy

Initial retention behavior is report-only:

- keep the last 3 full backups.
- keep the first full backup of each local day.
- keep all manifests.
- keep delta backups tied to retained full backups.
- report older duplicate full snapshots as cleanup candidates.

Deletion, archival movement, or compression requires a separate explicit APPLY
packet naming the exact candidate paths.

## Risk Controls

- The T9 filesystem is `exFAT`; NTFS permissions and some metadata may not preserve exactly.
- The T9 must not become a second source of truth.
- Known untracked backlog must not be copied into authority accidentally.
- High-risk reorganizer scripts must not be reused for backup.
- Backup helpers must not silently delete destination files.
- Task Scheduler must not be created until manual DRY_RUN and APPLY behavior are proven.
- Secrets and credentials must be excluded and must not be logged.

## Next Approved Sequence

1. Commit this specification after review.
2. Create a future DRY_RUN-only backup preview helper.
3. Validate that the helper prints paths, exclusions, and planned commands without mutation.
4. Run a separate APPLY lane only after operator approval.
5. Consider Task Scheduler only after the manual APPLY path is reliable.
