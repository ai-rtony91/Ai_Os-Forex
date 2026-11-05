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

Owner direction, 2026-10-31: twice-weekly backup covers changed or newly saved work, with a clear alert when the approved backup drive is missing. The current alert choice is Threema; live delivery awaits vendor approval and separately authorized private configuration. Preserve needed unique files and compact recovery checkpoints; avoid backing up backups. This documentation update does not install schedules or approve blanket deletion, retention cleanup, or restore.

Planned schedule after an incremental DRY_RUN helper proves safe:

1. Manual DRY_RUN first.
2. Manual APPLY backup second, with explicit operator approval.
3. Wednesday and Sunday at 20:00 `America/New_York`, using timezone rules that follow daylight saving time. Copy only changed or newly saved work within the approved source scope; do not create routine full copies.
4. Preserve a missing-drive pending checkpoint and report the missing destination. Once Threema delivery is approved and verified, use the existing notifier for a deduplicated connection reminder. Until then, retain local pending status without claiming delivery or silently falling back to another channel/drive. Keep private keys, API secrets and destination identifiers outside the public repo and logs.
5. Prevent overlapping runs. Resume only from verified checkpoints, confirm copied files against the approved manifest or hashes, and record completion before advancing the checkpoint. Preserve incomplete work after an interruption. Do not perform automated deletion.

Milestone events supplement the twice-weekly schedule within the same backup workflow:

- The current canonical milestone record must provide a stable ID, version, finish criteria, accepted completion proof, and the identity of changed/unbacked saved work. Verified milestone acceptance plus meaningful unbacked saved work makes an incremental backup eligible. Use that evidence and the difference from the last verified backup checkpoint, not raw line/file counts or invented investment or cost figures.
- Future milestones use the same existing record and completion-event mechanism when registered; no separate milestone subsystem or advance enumeration of every future milestone is needed. Reconcile current remaining autonomy milestones and their acceptance proof before marking any complete. This policy update marks no milestone complete.
- Reuse the existing backup checkpoint to coalesce milestone and scheduled events into one pending capture. If the approved T9 is absent, persist that event; the verified private notifier may send a deduplicated Threema connection reminder when available. Repeated checks must not create duplicate events or alerts.
- On reconnection, validate the approved drive identity and run only an authorized incremental capture of new or changed saved files. Verify the capture, record success, and then clear the pending event. Reconnection alone grants no execution authority. Retain failed or pending state and preserve original files after any failure.
- Serialize captures and coalesce overlapping triggers so a milestone and scheduled event do not back up the same work twice. Keep backup outputs excluded as sources and perform no automated deletion.

The milestone "bin" is staging-only: a manifest of eligible saved work and restore references within this workflow, not another full project copy or subsystem. A staging cleanup proposal must identify exact staging objects, a verified destination receipt and the retained restore manifest. It cannot remove live source, unique backup versions, credentials or recovery evidence. No automatic permanent deletion or staging cleanup implementation is authorized here.

Installation evidence, 2026-10-31 at 20:43 UTC: the owner-run receipt reports INSTALLED_NOT_RUN, task AIOS-T9-Saved-Work-Incremental, enabled and Ready. Readback shows floating local 20:00:00 with no offset/Z, Wednesday/Sunday day mask 9, weekly interval 1, IgnoreNew, a 65-minute limit and Interactive/Limited owner execution. Owner login is required; battery start is blocked, switching to battery stops the task, missed-run catch-up is disabled and a changed system timezone refuses runs. This proves installation/readback, not a completed backup or permanent live health.

The local invocation selects explicit saved-work Delta with verified scope/archive baseline and drive identity; it must not use legacy Auto selecting daily Full. Synthetic helper/recovery checks and local Preview passed, but no real scheduled capture is proven. The installed job/private configuration are local; source publication and installed-helper identity must be verified separately. Reuse accepted checks only while exact source/configuration identities and acceptance scope match.

Milestone-event wiring, automatic staging-bin population, immediate reconnect capture, live Threema reminders and secure owner-decision routing remain unproved. Local ready-bin metadata is a proposal, not an accepted milestone or cleanup permission. Follow the existing [role acceptance requirements](../governance/aios-identity-and-lane-governance.md#operational-proof-and-single-dispatch-owner); preserve MAIN/M9 ownership and pending-drive state. This documentation update changes no runtime, credentials, security, schedules or deletion behavior.

## Review and Safety Requirements, 2026-11-05

The October 31 owner instruction selected Threema instead of Telegram. That supports the preferred channel change; it does not establish a working backup alert. No silent fallback is authorized by this review. The existing PowerShell notifier supports file, webhook and Telegram channels, with no Threema sender in the inspected source. The missing-drive branch records pending work but does not call a verified delivery provider. Local pending status, provider acceptance, delivery and owner acknowledgement remain separate facts.

| Evidence checked on the laptop | Result and limit |
|---|---|
| Existing scheduled task | Enabled/Ready; last run November 4 at 20:00 America/New_York, result 2; next run November 8 at 20:00. Its last result is PENDING_DRIVE, not backup success. No task was replaced or started by this review. |
| Missing-drive record | Pending since November 1 at 20:00 America/New_York; delivery_confirmed remains false. No functioning phone delivery path is verified. |
| Interrupted capture | November 3 attempt stopped on source enumeration access denial. Checkpoint remains STARTED with no completed root; verified journal data is retained. No access rule was changed or denied source silently omitted. |
| Installed source identity | Installed PowerShell payloads match their existing package pins. Source publication does not update that package or the task action. |
| Focused Windows PowerShell checks | Original PR fixtures passed; expanded checks cover exact identity on both roots, refusal of the unsupported finite-file entry, journal loss/truncation, and real helper-entry refusal without advancing checkpoint or clearing pending. Physical volume/archive observations in the entry fixture are synthetic. |
| Newer storage/bin source | Separate uncommitted successor remains uninstalled; its November 4 review rejected storage-stop reporting/checkpoint claims. Those changes and their ownership are preserved, not included in this correction. |

The reviewed source now requires the exact approved volume identity for both approved roots, including D:. The finite SavedWorkFiles CLI route refuses with SAVED_WORK_ARCHIVE_CHECKPOINT_REQUIRED: its latest-manifest-only state could duplicate work across changing scopes or interrupted attempts. Use the existing explicit verified-archive Delta route and persistent journal; never substitute legacy Auto or a new backup system.

Archive root progress now records minimum journal byte boundaries. A persisted checkpoint cannot skip completed roots if any referenced journal is missing or shorter than its recorded boundary. Fresh and rotated segments are created and flushed before checkpoints reference them; complete extra appends after a checkpoint remain eligible for recovery. Legacy interrupted progress without boundaries requires reconciliation, not fabricated proof, journal recreation or a silent reset. Refusal retains source, copies, pending work and checkpoint evidence.

Passing fixtures do not prove a completed scheduled capture, crash/power-loss durability, portable restoration, historical version integrity, storage reserve enforcement, milestone wiring or mobile delivery. Existing archive references remain restore dependencies; do not delete baseline archives. Retained partial copies can consume space; this source does not claim automatic cleanup or global content deduplication. Owner login, battery conditions, disabled missed-run catch-up and no reconnect watcher can delay a missed capture until another eligible run.

The next runtime gate is to resolve the denied source's coverage within the approved scope and qualify the existing package/checkpoint against reviewed source and real storage limits before any separately approved installed-helper change or capture. Keep the installed package pinned meanwhile. Threema vendor/configuration dependencies and an explicitly approved harmless delivery with provider evidence plus owner acknowledgement remain necessary before claiming phone alerts. This review sends no message, accesses no private credential, changes no protected setting, installs no task and deletes no backup.

Any future Task Scheduler registration, replacement or configuration change requires a separately scoped APPLY lane explicitly authorizing:

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
