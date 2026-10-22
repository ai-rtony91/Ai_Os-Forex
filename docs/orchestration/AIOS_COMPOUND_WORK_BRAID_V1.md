# AI_OS Compound Work-Braid V1

The compound work-braid controller is a deterministic, repository-local planning layer over the canonical orchestration platform. It turns evidenced unfinished obligations (strands) into coherent engineering contexts (braids), then combines compatible braids into complete APPLY workflows (execution cables).

## Safety boundary

The controller reads canonical work-packet evidence and Git state. It does not mutate queues, execute generated packets, launch workers, stage or commit Git changes, use credentials, access a broker, place orders, move money, or approve protected actions. Generated continuation text always stops at Human Owner review.

## Model

- **Strand:** one evidenced repository obligation with completion evidence, dependencies, gates, paths, and validators.
- **Braid:** compatible actionable strands sharing root cause, write boundary, validator context, and milestone.
- **Cable:** one dependency-correct workflow containing discovery, implementation, validation, bounded repair, evidence, checkpoint, continuation, readiness reporting, and handoff stages.
- **Program:** ordered cable planning toward a governed repository or economic checkpoint. Economic programs remain planning-only without broker evidence.

Duplicate strands retain evidence but leave executable selection. Superseded strands name their replacement. Missing dependencies and dependency cycles fail closed. Checkpoint resume requires an unchanged HEAD, branch, allowed-path content, and dependency graph.

## Usage

```bash
python scripts/run_aios_compound_work_braid_v1.py --repo-root . --pretty
```

Resume validation is available with `--resume`. Generation writes only the four declared report artifacts and never executes the emitted Codex packet.
