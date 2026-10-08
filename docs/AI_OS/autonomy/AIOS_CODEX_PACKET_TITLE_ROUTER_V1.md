# AIOS Codex Packet Title Router V1

## Owner workflow

Open one new Codex task and enter only this exact text:

**TASK 1 INPUT:**

```text
AIOS-PACKET-RESTORE-PR1379-BRANCH-V1
```

**EXPECTED BEHAVIOR:**

1. Resolve the exact title.
2. Load the registered packet.
3. Verify its SHA-256 digest.
4. Validate the complete packet.
5. Run its preflight.
6. Execute only its authorized actions.
7. Validate the result.
8. Return its receipt.
9. Stop.

Use one title per Codex task. Multiple-title batches are not accepted, and resolution never depends on previous task history. The registry and stored packet must exist in the repository version loaded by that task. A title grants no authority of its own, and all protected actions retain their existing approval gates.

## Fail-closed behavior

Lookup is exact and case-sensitive. Unknown, inactive, superseded, duplicate, malformed, path-escaping, symlink-escaping, digest-mismatched, and invalid packets are rejected. Normal resolution returns metadata, not the complete stored packet body.
