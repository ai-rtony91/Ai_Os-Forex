# AIOS Full Conversation Context Archive Design V1

## Phase identity and purpose

This is Phase 2, **Full Conversation Context Archive Design**, of the Owner
Cellular Voice Gateway program. It defines a bounded, deterministic contract by
which later phases may represent and validate conversation history without
activating an archive or storing real owner conversations. The design supports
traceable context while preventing historical text from silently becoming
current execution or approval authority.

Phase 2 maps to `OWNER-BUNDLE-1-POLICY`. Declarative design and preparation may
complete autonomously, but its protected transition is **BLOCKED**.

## Data classes

An archive record separates these explicit classes:

| Class | Bounded representation |
|---|---|
| Conversation metadata | Opaque conversation, session, and message identifiers plus archive version |
| Message ordering | Positive integer `sequence`, unique within one conversation/session |
| Roles | Controlled `owner`, `assistant`, `system`, `tool`, or `unknown` label |
| Timestamps | Timezone-aware RFC 3339 event time; never used alone as ordering authority |
| Source/session identity | Controlled source label and opaque session identifier, not an authentication claim |
| References/attachments metadata | Identifier, media type, size, digest, and sanitized display name only |
| Authority-bearing content | Explicit authority classification; content remains historical evidence only |
| Sensitive/private content | Sensitivity classification drives quarantine, redaction, and access policy |
| Executional instructions | Classified as historical instructions and never dispatched from the archive |
| Sanitized evidence | Redacted, metadata-bounded evidence carrying its sanitization state |

## Archive record contract

The canonical machine-readable contract is
`schemas/orchestration/aios_conversation_context_archive_v1.schema.json`. A
record has exactly one message and includes at minimum:

- `archive_version`, `conversation_id`, `session_id`, `message_id`, and positive
  integer `sequence`;
- `role`, timezone-aware `timestamp`, and `source`;
- `content` plus `content_classification`, `authority_classification`,
  `sensitivity_classification`, and `retention_classification`;
- structured `provenance`, an `integrity_reference`, and `sanitization_state`;
- optional metadata-only `references`.

Identifiers are opaque and must not embed phone numbers, account identifiers,
credentials, exact locations, or other private payloads. `content` is present to
define the future contract; this phase supplies no real conversation content.
Secrets, passwords, tokens, private keys, credential values, recovery codes,
raw authentication payloads, and exact location data are prohibited from the
archive. A producer must reject or redact them before a record can be eligible
for downstream use.

## Ordering and integrity

Records are deterministically ordered by the tuple `(conversation_id,
session_id, sequence, message_id)`. Sequence starts at 1 and is contiguous per
conversation/session. Timestamps are descriptive and cannot repair or override
sequence.

- An exact replay with the same message ID, sequence, canonical record bytes,
  and integrity reference is a duplicate and may be idempotently ignored.
- Reuse of a message ID with different content, sequence, provenance, or digest
  is a conflict and fails closed.
- Reuse of a sequence by different message IDs is a conflict and fails closed.
- A missing sequence, non-positive sequence, or gap quarantines the affected
  session and all later records until independently reconciled.
- A conversation/session identifier conflict, or a record that changes identity
  after ingestion, quarantines the record; timestamps must not break the tie.

`integrity_reference` identifies the digest algorithm and digest of the
canonical serialized record payload excluding the integrity reference itself.
Canonical serialization uses UTF-8 JSON, lexicographically sorted object keys,
no insignificant whitespace, and the schema-defined value forms. Integrity
verification detects alteration only: it does not authenticate the owner, prove
freshness, approve a command, or grant execution authority.

## Authority separation

The archive is context, not an authority channel. `authority_classification`
can describe `owner_authored_historical`, `approval_claim_historical`,
`execution_instruction_historical`, `non_authoritative`, or `unknown`; every
value remains non-authoritative. No archive record grants approval authority.

The Approval Broker remains non-authoritative. Owner-authored text, archived
commands, approval language, receipts, or past decisions are historical context
only. They must never be replayed, promoted, or accepted as a current decision.
Every protected transition still requires current trusted owner approval through
the existing verifier boundary, with current binding and expiry checks. Stale or
replayed approvals from archive history fail closed.

## Privacy boundary

- **Minimization:** collect only fields required for a declared downstream use;
  omit redundant message bodies and private identifiers.
- **Sensitivity labels:** every record is `public`, `internal`, `private`,
  `restricted`, or `unknown`; `unknown` is quarantined.
- **Redaction and sanitization:** states are `raw_prohibited`, `pending`,
  `sanitized`, `redacted`, or `quarantined`. Only `sanitized` or `redacted`
  records may be considered for bounded downstream evidence.
- **Access boundary:** least-privilege, purpose-bound readers only; archive
  visibility conveys neither owner identity nor command authority.
- **Export boundary:** exports must be schema validated, minimized, sanitized,
  access approved, integrity checked, and stripped of prohibited data. Arbitrary
  external transfer is forbidden.
- **Deletion/expiry:** policy records a disposition due time; a later approved
  storage phase must delete or cryptographically render inaccessible expired
  material and preserve only sanitized deletion evidence where required.

Phase 17 owns any location capability. This design neither collects nor stores
location data and does not implement Phase 17 location storage.

## Retention model

Retention is classification only; this phase creates no storage job or timer.

| Classification | Intended policy |
|---|---|
| `ephemeral` | Processing-window context, then expire |
| `short_term_operational` | Bounded troubleshooting or session continuity with an explicit expiry |
| `long_term_governance` | Minimized, sanitized governance evidence retained under approved policy |
| `prohibited_from_archive` | Reject, redact, or quarantine; never persist as archive content |
| `unknown` | Fail closed and quarantine pending explicit classification |

## Attachment and reference model

References are metadata only: opaque reference ID, sanitized display name,
declared media type, byte size, integrity digest, source classification, and
optional safe locator classification. The archive does not fetch URLs, ingest
arbitrary binaries, follow links, call external services, or embed attachment
contents. A later explicitly authorized phase must own any such capability.

## Fail-closed rules

Undefined or `unknown` authority, sensitivity, provenance, sequence, retention,
or integrity prevents downstream eligibility and quarantines the record. Missing
required fields and values outside the schema are rejected. Conflicts, integrity
mismatches, prohibited content, non-sanitized evidence, and historical approval
claims cannot be repaired by inference. Quarantine is not approval and cannot be
bypassed by a downstream consumer.

No live persistence, runtime activation, ingestion process, external storage,
network integration, credential handling, or owner approval receipt creation is
introduced by this design.

## Phase 2 handoff

Phase 3 and later phases may rely only on: this reviewed design; the validated
schema shape and enumerations; deterministic ordering/conflict rules; explicit
privacy and retention classifications; integrity-verification semantics; and
sanitized test evidence. They may not rely on real conversation data, archive
availability, an operational store, owner authentication, or approval state.
Each consumer must revalidate schema, classification, sanitization, sequence,
provenance, and integrity and preserve its own authority gates.

## Acceptance matrix

| Requirement | Evidence | Pass condition | Downstream consumer |
|---|---|---|---|
| Purpose and phase identity | Phase identity section | Exact Phase 2 name and policy bundle are present | Program coordinator |
| Data classes | Data classes table | All required classes have bounded representations | Phase 3 threat model |
| Archive record | JSON Schema and contract section | All required fields and closed enumerations validate | Future archive adapter |
| Ordering and integrity | Ordering section | Deterministic order, duplicate, gap, conflict, and digest rules are explicit | Phase 3 and future validator |
| Authority separation | Authority section | Archive content and broker cannot grant approval or execution | Phases 10-15 |
| Privacy boundary | Privacy section | Minimization, labels, sanitization, access, export, and expiry are defined | Phases 3 and 10 |
| Retention model | Retention table | Four bounded categories plus fail-closed unknown exist; no jobs run | Phase 10 governance memory |
| References | Attachment section | Metadata-only boundary and no fetching/ingestion are explicit | Future input adapters |
| Fail-closed behavior | Fail-closed section | Undefined critical classifications are quarantined | Every downstream consumer |
| Handoff | Phase 2 handoff | Reliance evidence and non-evidence are explicit | Phase 3 and later phases |
| Owner gate | Owner gate section | Protected transition remains blocked | Approval Broker consumer |

## Owner gate

Phase 2 design/preparation may complete autonomously. Any protected transition
that activates, persists, exposes, or operationalizes owner conversation
archives remains **BLOCKED** until valid `OWNER-BUNDLE-1-POLICY` authority is
verified through the current trusted owner-approval path.
