# AIOS Repository Cleanup Controller V1

## Purpose and authority boundary

The controller provides a deterministic inventory for repository-maintenance decisions. It reads Git-tracked files, records findings, and prepares a reviewable plan. It does not grant authority to change application, governance, trading, broker, risk, credential, deployment, workflow, or generated-evidence files. Runtime reports are local evidence, not repository authority.

Blind repository-wide formatting is unsafe because formatting can alter meaningful Markdown whitespace, snapshots, generated evidence, encodings, line endings, schemas, and code behavior. V1 therefore makes no heuristic edits and marks every audit-generated plan entry ineligible for automatic application.

## Modes

```bash
python scripts/maintenance/run_aios_repository_cleanup_v1.py audit --repo-root /workspace/Ai_Os
python scripts/maintenance/run_aios_repository_cleanup_v1.py plan --repo-root /workspace/Ai_Os
python scripts/maintenance/run_aios_repository_cleanup_v1.py apply --repo-root /workspace/Ai_Os --plan .aios/runtime/repository_cleanup/AIOS_REPOSITORY_CLEANUP_PLAN_V1.json --confirm-safe-apply
python scripts/maintenance/run_aios_repository_cleanup_v1.py verify --repo-root /workspace/Ai_Os
```

- **AUDIT** inspects the `git ls-files -z` inventory and writes JSON and Markdown evidence.
- **PLAN** repeats the audit and classifies findings without changing tracked files.
- **APPLY** accepts only exact, eligible entries produced for an already configured and installed tool. It is not blanket cleanup authority.
- **VERIFY** repeats the audit so an operator can compare current evidence with the earlier audit and plan.

The default runtime directory is `.aios/runtime/repository_cleanup/`. The controller writes there only when Git confirms that directory is ignored; otherwise it prints JSON to standard output. It never recursively inspects untracked files.

## Reports and schema

The audit files are `AIOS_REPOSITORY_CLEANUP_AUDIT_V1.json` and `AIOS_REPOSITORY_CLEANUP_AUDIT_V1.md`. The plan is `AIOS_REPOSITORY_CLEANUP_PLAN_V1.json`; an authorized apply writes `AIOS_REPOSITORY_CLEANUP_APPLY_RECEIPT_V1.json`.

Audit schema `aios.repository_cleanup.audit.v1` records UTC generation time, root, branch, HEAD, clean state, baseline ancestry, tracked/inspected/skipped counts, skip reasons, installed-tool versions, A–Z statuses, and severity-grouped redacted findings. Plan schema `aios.repository_cleanup.plan.v1` records the same HEAD and exact entries, including path, original SHA-256, classification, tool and arguments, expected changed paths, validators, rollback evidence, and semantics-preservation reason. JSON keys and findings use stable ordering.

Statuses are `PASS`, `WARN`, `BLOCKED`, and `NOT_AVAILABLE`. Exit codes are:

| Code | Meaning |
|---:|---|
| 0 | Completed with no blocking findings |
| 1 | Completed with warnings |
| 2 | Unsafe repository state or missing authorization |
| 3 | Validator or configured-tool failure |
| 4 | Malformed or stale plan |
| 5 | Path escape, forbidden path, or protected action |

## Files, tools, and protections

The content checks support Python, JSON, Markdown, YAML, PowerShell, TOML, INI/CFG, shell, and plain text. Binary and unsupported-encoding files are counted and skipped safely. UTF-8 byte-order marks, line endings, final newlines, and Markdown trailing spaces are observed but never normalized.

APPLY may invoke only an existing installed tool named by an exact eligible plan entry. The controller does not install tools, add configuration, use a shell, accept wildcard mutation, or infer a formatter. Missing optional tools are `NOT_AVAILABLE`.

Protected paths include root authority, `.git`, GitHub and hook configuration, governance/security documentation, automation, applications, services, Forex delivery and engine tests, reports, and runtime/evidence paths. Symlinks and traversal cannot escape the repository. Secret-like assignment evidence is redacted; raw values are not included in reports.

## APPLY gates and rollback

APPLY requires an attached non-`main` branch, clean tracked state, `--confirm-safe-apply`, an exact plan, matching plan HEAD, matching original SHA-256, one exact expected path, and an existing configured tool. It rejects stale plans, protected/generated paths, wildcards, and unexpected changes. Validators use bounded subprocess execution without `shell=True`.

Before invoking a tool, original bytes are retained. A tool failure, unexpected path, or failed validator stops execution and atomically restores every touched planned file. The controller neither stages nor commits.

## Future cleanup packets

A future subsystem packet should review the report-only plan, select one bounded subsystem, independently authorize exact files and validators, and create a new plan whose safe-fix entries name only repository-configured tools. Review the HEAD and hashes immediately before execution. Never convert the A–Z report into repository-wide mutation authority.

Controller completion does not prove the repository is defect-free. It is also separate from production readiness, broker readiness, live-trading approval, performance, or profitability readiness.
