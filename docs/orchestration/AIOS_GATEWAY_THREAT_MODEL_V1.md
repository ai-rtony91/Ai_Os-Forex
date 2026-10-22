# AIOS Gateway Threat Model V1

## 1. Phase identity and purpose

This document defines Phase 3 = Gateway Threat Model for the Owner Cellular Voice Gateway Program. It is a declarative security design only; it implements no gateway or protected capability.

| Field | Value |
|---|---|
| Mission ID | `AIOS-CELLULAR-GATEWAY-PHASE-03` |
| Program ID | `AIOS-OWNER-CELLULAR-VOICE-GATEWAY-V1` |
| Phase | `3` |
| owner_authority | `RISK_ACCEPTANCE` |
| owner_bundle | `OWNER-BUNDLE-1-POLICY` |
| mode | `PREPARE_BEHIND_GATE` |
| protected_transition | `BLOCKED` |

The Human Owner remains final authority. The Approval Broker remains non-authoritative. A validator PASS is evidence only. Threat-model completion neither authorizes a protected transition nor constitutes owner risk acceptance.

## 2. Inputs and trusted evidence

The controlling inputs are the reviewed Phase 1 charter, `AIOS_OWNER_CELLULAR_VOICE_GATEWAY_PROGRAM_CHARTER_V1.md`; the merged Phase 2 archive design, `AIOS_FULL_CONVERSATION_CONTEXT_ARCHIVE_DESIGN_V1.md`; the Phase 2 schema, `aios_conversation_context_archive_v1.schema.json`; and the canonical owner-authority manifest. Their existence is evidence of design constraints, not evidence that mitigations work. Archived conversation content is historical context only. Past approvals, archived approval language, historical commands, old receipts, and previous owner-authored text cannot become current approval.

## 3. Assets requiring protection

The protected assets are: owner identity; owner intent; command integrity; command freshness; conversation context; archive integrity; archive privacy; approval decisions; approval binding; device trust; phone-number control; voice evidence; liveness evidence; passkey/YubiKey authority; secrets/session material; the AIOS receiving boundary; runtime bridge; The_Lab execution boundary; audit evidence; location/privacy data; and availability of the command path.

## 4. Trust boundaries

The boundaries are the Human Owner; future cellular/provider boundary; future phone-number routing boundary; future trusted-device boundary; future voice-recognition boundary; future liveness/replay boundary; future passkey/YubiKey boundary; conversation archive boundary; Approval Broker; trusted owner-verifier boundary; AIOS receiving boundary; runtime bridge boundary; The_Lab execution boundary; vault/secrets boundary; location/privacy boundary; and external systems. All future or external boundaries remain untrusted unless a later phase proves otherwise.

## 5. Adversary assumptions

Adversaries may be remote, local, privileged, opportunistic, or supply-chain actors. They may control a caller identity, carrier account, device, recording, archive input, attachment, dependency, log sink, or timing window. They may combine individually weak signals. No network, device, voice, archive, approval-routing, or external-system claim is trusted merely because it is well formed.

## 6. Attack surfaces

Attack surfaces include cellular signaling and provider administration; number routing; devices and recovery paths; microphones, speech processing, and liveness; archives, imports, attachments, and exports; approval records and verifier responses; parsers and routers; runtime and execution bridges; vault/session interfaces; logs and telemetry; privacy/location flows; external dependencies; resource limits; and error paths. This document introduces none of those runtime surfaces.

## 7. Risk-scoring method

This model uses ordinal prioritization only.

* Likelihood ordinal: `1 = unlikely`, `2 = plausible`, `3 = likely`, `4 = highly exposed`.
* Impact ordinal: `1 = limited`, `2 = material`, `3 = severe`, `4 = critical`.
* `risk_score = likelihood * impact`.
* Severity: `1-3 = LOW`, `4-7 = MEDIUM`, `8-11 = HIGH`, `12-16 = CRITICAL`.

This scoring is deterministic prioritization, not a probability estimate, certification, or guarantee.

## 8. Threat register

Each row supplies every mandatory field. `UNASSESSED` means that this packet contains no validated mitigation evidence and makes no risk-acceptance claim.

| Threat ID | Threat name | Asset or trust boundary | Threat scenario | Required preconditions | Affected phases | Likelihood ordinal | Impact ordinal | Inherent risk score | Inherent severity | Required mitigation | Mitigation-owning phase or phases | Validation evidence required | Residual risk | Fail-closed response | Owner decision requirement |
|---|---|---|---|---|---|---:|---:|---:|---|---|---|---|---|---|---|
| GW-T001 | Caller/source spoofing | owner identity; phone routing | An attacker presents a forged caller/source identity. | Access to signaling or caller metadata | 3,4,11,13 | 4 | 4 | 16 | CRITICAL | Bind source to independently verified owner factors; never trust caller ID alone. | Phase 4, Phase 11, Phase 13 | Spoof-rejection and binding tests | UNASSESSED | BLOCKED on absent or conflicting binding | Owner later accepts/rejects residual risk after evidence |
| GW-T002 | SIM swap or phone-number takeover | phone-number control | An attacker transfers or takes control of the owner number. | Carrier social engineering or account access | 3,4,9 | 3 | 4 | 12 | CRITICAL | Detect number/account changes and require an independent possession factor. | Phase 4, Phase 9 | Provider-control and takeover drill evidence | UNASSESSED | BLOCKED until control is re-established | Owner later accepts/rejects residual risk after evidence |
| GW-T003 | Carrier/provider account compromise | cellular/provider boundary | Provider administration is used to reroute or inspect traffic. | Compromised provider account | 3,4,16 | 3 | 4 | 12 | CRITICAL | Strong external account controls, least privilege, and change alerts. | Phase 4, Phase 16 | Sanitized provider security-control evidence | UNASSESSED | BLOCKED on account anomaly | Owner later accepts/rejects residual risk after evidence |
| GW-T004 | Carrier/provider infrastructure compromise | external systems | Compromised carrier infrastructure alters or observes messages. | Provider or signaling compromise | 3,4,8 | 2 | 4 | 8 | HIGH | Treat carrier transport as untrusted; use end-to-end freshness and identity checks. | Phase 4, Phase 8 | Adversarial transport tests | UNASSESSED | BLOCKED when end-to-end checks fail | Owner later accepts/rejects residual risk after evidence |
| GW-T005 | Voice cloning or deepfake impersonation | voice evidence | Synthesized owner-like audio passes voice checks. | Owner voice samples and synthesis capability | 3,6,8 | 4 | 4 | 16 | CRITICAL | Voice is never sole authority; calibrated confidence plus liveness and stronger factors. | Phase 6, Phase 8, Phase 9 | Deepfake corpus false-accept evidence | UNASSESSED | BLOCKED below verified multi-factor threshold | Owner later accepts/rejects residual risk after evidence |
| GW-T006 | Recorded voice replay | liveness evidence | A captured valid utterance is replayed promptly. | Access to owner recording | 3,8 | 4 | 4 | 16 | CRITICAL | Nonce-bound, time-bound liveness challenge and replay cache. | Phase 8 | Recorded-replay rejection tests | UNASSESSED | BLOCKED on nonce reuse or missing liveness | Owner later accepts/rejects residual risk after evidence |
| GW-T007 | Delayed replay | command freshness | An old genuine command is submitted after its intended window. | Captured prior command | 3,8,11 | 3 | 4 | 12 | CRITICAL | Signed freshness window, expiry, nonce, and contextual rebinding. | Phase 8, Phase 11 | Expiry-boundary and delayed-replay tests | UNASSESSED | BLOCKED on expired or stale evidence | Owner later accepts/rejects residual risk after evidence |
| GW-T008 | Liveness bypass | liveness/replay boundary | Crafted input tricks or skips the liveness decision. | Parser, sensor, or policy weakness | 3,7,8 | 3 | 4 | 12 | CRITICAL | Explicit liveness state machine; no bypass or permissive fallback. | Phase 7, Phase 8 | Bypass and negative-path tests | UNASSESSED | BLOCKED on missing, unknown, or unverifiable liveness | Owner later accepts/rejects residual risk after evidence |
| GW-T009 | Transcript tampering | command integrity | Transcript content changes after recognition. | Access between recognition and receiver | 3,6,12 | 3 | 4 | 12 | CRITICAL | Bind transcript, source evidence, timestamps, and digest end to end. | Phase 6, Phase 12 | Mutation and binding verification tests | UNASSESSED | BLOCKED on integrity mismatch | Owner later accepts/rejects residual risk after evidence |
| GW-T010 | Speech-to-text command substitution | owner intent | Recognition changes meaning or inserts an action. | Ambiguous audio or compromised recognizer | 3,6,12 | 4 | 4 | 16 | CRITICAL | Confidence thresholds, constrained grammar, semantic confirmation for protected intent. | Phase 6, Phase 12 | Substitution corpus and intent-diff tests | UNASSESSED | BLOCKED on ambiguity or material mismatch | Owner later accepts/rejects residual risk after evidence |
| GW-T011 | Prompt or instruction injection | AIOS receiving boundary | Spoken or archived content instructs a model to bypass policy. | Untrusted natural-language content reaches parser/model | 3,10,12,13 | 4 | 4 | 16 | CRITICAL | Separate data from authority; constrained parser and policy-enforced routing. | Phase 10, Phase 12, Phase 13 | Injection suite proving authority isolation | UNASSESSED | BLOCKED on unclassified or policy-altering content | Owner later accepts/rejects residual risk after evidence |
| GW-T012 | Conversation archive poisoning | conversation archive boundary | Crafted historical records bias current context or decisions. | Ability to submit/import archive records | 2,3,10,12 | 3 | 4 | 12 | CRITICAL | Provenance, quarantine, sanitization revalidation, and non-authoritative consumption. | Phase 2, Phase 10, Phase 12 | Poisoned-record quarantine tests | UNASSESSED | BLOCKED on unknown critical classification | Owner later accepts/rejects residual risk after evidence |
| GW-T013 | Historical approval replay | approval binding | Archived approval language is presented as current approval. | Access to old approval or archive content | 2,3,10,11 | 4 | 4 | 16 | CRITICAL | Current trusted-verifier receipt bound to exact action, scope, and freshness. | Phase 10, Phase 11 | Historical-language rejection tests | UNASSESSED | BLOCKED without current bound owner decision | Owner later accepts/rejects residual risk after evidence |
| GW-T014 | Stale-context promotion | command freshness | Old context is silently promoted into the active decision. | Stale archive or cache available | 2,3,10,12 | 3 | 4 | 12 | CRITICAL | Explicit context age, provenance, revalidation, and no silent promotion. | Phase 10, Phase 12 | Stale-context rejection tests | UNASSESSED | BLOCKED on stale or unverifiable context | Owner later accepts/rejects residual risk after evidence |
| GW-T015 | Archive integrity tampering | archive integrity | Stored content or metadata is altered. | Archive write access | 2,3,10 | 3 | 3 | 9 | HIGH | Canonical digest verification plus independent authority authentication. | Phase 2, Phase 10 | Digest mutation tests; proof that integrity does not authenticate owner | UNASSESSED | QUARANTINED and BLOCKED on mismatch | Owner later accepts/rejects residual risk after evidence |
| GW-T016 | Message ordering or sequence manipulation | conversation context | Reordering, gaps, or conflicts change meaning. | Ability to alter sequence or identifiers | 2,3,10 | 3 | 3 | 9 | HIGH | Sequence-based ordering; duplicate, gap, and conflict rules fail closed. | Phase 2, Phase 10 | Duplicate/conflict/gap test evidence | UNASSESSED | QUARANTINED and BLOCKED on sequence anomaly | Owner later accepts/rejects residual risk after evidence |
| GW-T017 | Identity/session confusion | owner identity; session material | Evidence from different owners or sessions is combined. | Weak binding or concurrent sessions | 3,9,11,16 | 3 | 4 | 12 | CRITICAL | Bind identity, session, factor, command, and expiry atomically. | Phase 9, Phase 11, Phase 16 | Cross-session substitution tests | UNASSESSED | BLOCKED on binding conflict | Owner later accepts/rejects residual risk after evidence |
| GW-T018 | Confused-deputy behavior | Approval Broker; router | A component uses its access to perform an unauthorized action for untrusted input. | Over-broad component capability | 3,11,13,14 | 3 | 4 | 12 | CRITICAL | Capability minimization and receiving-boundary reauthorization. | Phase 11, Phase 13, Phase 14 | Negative authorization and capability tests | UNASSESSED | BLOCKED unless exact receiving policy authorizes | Owner later accepts/rejects residual risk after evidence |
| GW-T019 | Cross-phase authority escalation | phase governance | Completion or evidence from one phase is treated as authority for another. | Incorrect workflow binding | 3,10,11 | 3 | 4 | 12 | CRITICAL | Phase-scoped receipts and explicit protected-transition gates. | Phase 10, Phase 11 | Cross-phase replay rejection tests | UNASSESSED | BLOCKED on phase mismatch | Owner later accepts/rejects residual risk after evidence |
| GW-T020 | Forged approval/verifier result | trusted owner-verifier boundary | A fake PASS or approval record claims owner authorization. | Verifier channel compromise or forged record | 3,9,11 | 3 | 4 | 12 | CRITICAL | Authenticated verifier, action binding, expiry, replay protection, independent receiving validation. | Phase 9, Phase 11 | Forgery and receipt-binding tests | UNASSESSED | BLOCKED on unverifiable verifier result | Owner later accepts/rejects residual risk after evidence |
| GW-T021 | Approval Broker misuse | Approval Broker | Broker routing output is mistaken for authority or execution permission. | Consumer trusts broker status as approval | 3,10,11,13 | 3 | 4 | 12 | CRITICAL | Preserve non-authoritative broker contract; receiving component validates authority. | Phase 10, Phase 11, Phase 13 | Broker misuse negative tests | UNASSESSED | BLOCKED without trusted current receipt | Owner later accepts/rejects residual risk after evidence |
| GW-T022 | Unsafe fallback or downgrade path | fallback boundary | Failure silently downgrades to a weaker identity or command path. | Primary factor unavailable | 3,7,8,9 | 4 | 4 | 16 | CRITICAL | Explicit lockout and equal-or-stronger recovery; prohibit permissive downgrade. | Phase 7, Phase 8, Phase 9 | Downgrade and lockout tests | UNASSESSED | BLOCKED when required factor unavailable | Owner later accepts/rejects residual risk after evidence |
| GW-T023 | Trusted-device compromise | trusted-device boundary | Malware or theft uses an enrolled device. | Device access or compromise | 3,5,9,16 | 3 | 4 | 12 | CRITICAL | Hardware-backed device state, revocation, attestation, and step-up authority. | Phase 5, Phase 9, Phase 16 | Compromise/revocation drill evidence | UNASSESSED | BLOCKED on invalid or revoked device state | Owner later accepts/rejects residual risk after evidence |
| GW-T024 | Passkey or YubiKey possession compromise | passkey/YubiKey boundary | Stolen factor is used without valid owner intent. | Factor theft and usable session | 3,9,11 | 2 | 4 | 8 | HIGH | User verification, intent binding, revocation, and no repository key material. | Phase 9, Phase 11 | Lost-factor and intent-binding tests | UNASSESSED | BLOCKED on possession-only evidence | Owner later accepts/rejects residual risk after evidence |
| GW-T025 | Secret/session leakage | vault/secrets boundary | Tokens or session material leak through storage, process, or logs. | Sensitive material exists at runtime | 3,14,16 | 3 | 4 | 12 | CRITICAL | Runtime-only least-privilege material, redaction, rotation, and expiry. | Phase 14, Phase 16 | Secret scanning and session-expiry evidence | UNASSESSED | BLOCKED and revoke on suspected exposure | Owner later accepts/rejects residual risk after evidence |
| GW-T026 | Privacy leakage | archive privacy | Conversation or identity data is disclosed beyond purpose. | Excess collection, access, or export | 2,3,10,17 | 3 | 3 | 9 | HIGH | Minimize, classify, authorize access, redact, and enforce retention. | Phase 2, Phase 10, Phase 17 | Privacy access and minimization tests | UNASSESSED | BLOCKED on unknown privacy classification | Owner later accepts/rejects residual risk after evidence |
| GW-T027 | Location leakage | location/privacy boundary | Exact or inferred location is exposed. | Location metadata or correlated signals | 3,17 | 3 | 4 | 12 | CRITICAL | Separate consent gate, minimization, coarse data by default, protected vault. | Phase 17 | Consent, minimization, and inference review | UNASSESSED | BLOCKED without current explicit privacy consent | Owner later accepts/rejects residual risk after evidence |
| GW-T028 | Logging or telemetry exfiltration | audit evidence; privacy data | Logs export sensitive commands, identifiers, or factors. | Verbose telemetry or compromised sink | 3,10,16,17 | 3 | 3 | 9 | HIGH | Structured allowlist logging, redaction, access limits, and export controls. | Phase 10, Phase 16, Phase 17 | Sanitized-log and exfiltration tests | UNASSESSED | BLOCKED logging/export on classification failure | Owner later accepts/rejects residual risk after evidence |
| GW-T029 | Unauthorized archive export | archive privacy | An actor exports conversation history without authority. | Archive access or export path | 2,3,10,17 | 3 | 3 | 9 | HIGH | Explicit export authorization, minimization, audit, and encrypted destination. | Phase 2, Phase 10, Phase 17 | Export authorization negative tests | UNASSESSED | BLOCKED on missing export authority | Owner later accepts/rejects residual risk after evidence |
| GW-T030 | Attachment/reference abuse | conversation archive boundary | Malicious attachments, references, or locators trigger fetch, parsing, or authority confusion. | Untrusted reference enters context | 2,3,12 | 3 | 4 | 12 | CRITICAL | No implicit fetch; allowlisted types, sandboxed parsing, opaque reference treatment. | Phase 2, Phase 12 | Malformed attachment and no-fetch tests | UNASSESSED | QUARANTINED and BLOCKED on unknown reference | Owner later accepts/rejects residual risk after evidence |
| GW-T031 | Denial of service | command-path availability | Flooding prevents legitimate owner commands. | Reachability of an input surface | 3,4,13 | 4 | 3 | 12 | CRITICAL | Rate limits, admission control, bounded queues, and safe recovery. | Phase 4, Phase 13 | Load and recovery evidence | UNASSESSED | Reject excess work while protected actions remain BLOCKED | Owner later accepts/rejects residual risk after evidence |
| GW-T032 | Resource exhaustion | AIOS receiving boundary | Oversized audio, context, attachments, or requests exhaust resources. | Unbounded input or processing | 2,3,12,13 | 4 | 3 | 12 | CRITICAL | Strict size/time/work limits and bounded parsing. | Phase 12, Phase 13 | Boundary and exhaustion tests | UNASSESSED | BLOCKED before allocation beyond limits | Owner later accepts/rejects residual risk after evidence |
| GW-T033 | Race or TOCTOU error | approval binding | Trust or approval changes between check and use. | Concurrent state change | 3,11,13,14 | 3 | 4 | 12 | CRITICAL | Atomic consume-once receipts bound to immutable command state. | Phase 11, Phase 13, Phase 14 | Concurrency and time-of-check/time-of-use tests | UNASSESSED | BLOCKED and restart verification on state change | Owner later accepts/rejects residual risk after evidence |
| GW-T034 | Runtime bridge compromise | runtime bridge boundary | Bridge code or host alters or executes unauthorized commands. | Phase 14 runtime exists and is compromised | 3,14,16 | 3 | 4 | 12 | CRITICAL | Minimal bridge, authenticated messages, allowlists, isolation, and kill switch. | Phase 14, Phase 16 | Tamper, isolation, and kill-switch tests | UNASSESSED | BLOCKED; bridge cannot execute on failed validation | Owner later accepts/rejects residual risk after evidence |
| GW-T035 | The_Lab execution-boundary bypass | The_Lab execution boundary | A command bypasses final execution policy. | Route to execution boundary exists | 3,13,14,15 | 3 | 4 | 12 | CRITICAL | Independent final authorization, strict command allowlist, and deny-by-default route. | Phase 13, Phase 14, Phase 15 | Boundary-bypass negative tests | UNASSESSED | BLOCKED at The_Lab boundary | Owner later accepts/rejects residual risk after evidence |
| GW-T036 | Fail-open error handling | all trust boundaries | Exception, timeout, or unknown state permits continued processing. | Error path is reached | 3,7,11,13,14,15 | 3 | 4 | 12 | CRITICAL | Exhaustive deny-by-default state handling and tested error paths. | Phase 7, Phase 11, Phase 13, Phase 14, Phase 15 | Fault-injection and unknown-state tests | UNASSESSED | BLOCKED on every error or unknown state | Owner later accepts/rejects residual risk after evidence |
| GW-T037 | Audit/repudiation ambiguity | audit evidence | Evidence cannot prove which input, decision, and action were bound. | Incomplete or mutable audit chain | 3,10,11,14,15 | 3 | 3 | 9 | HIGH | Tamper-evident, privacy-bounded event correlation and receipt binding. | Phase 10, Phase 11, Phase 14, Phase 15 | Correlation, mutation, and repudiation tests | UNASSESSED | BLOCKED when required audit binding is absent | Owner later accepts/rejects residual risk after evidence |
| GW-T038 | Retention or deletion failure | archive privacy | Expired or prohibited data persists or deletion is unverifiable. | Archive or backup retains records | 2,3,10,17 | 3 | 3 | 9 | HIGH | Enforce retention class, deletion/expiry evidence, and backup handling. | Phase 2, Phase 10, Phase 17 | Retention clock and deletion evidence | UNASSESSED | QUARANTINED; prevent use/export until resolved | Owner later accepts/rejects residual risk after evidence |
| GW-T039 | Malicious or compromised external dependency | external systems | A provider, model, library, or service returns hostile or false results. | Later phase integrates dependency | 3,4,6,12,13,14 | 3 | 4 | 12 | CRITICAL | Pin and verify dependencies; validate all outputs; isolate and provide safe denial. | Phase 4, Phase 6, Phase 12, Phase 13, Phase 14 | Supply-chain, provenance, and hostile-output tests | UNASSESSED | BLOCKED on unverified dependency or output | Owner later accepts/rejects residual risk after evidence |

## 9. Cross-phase threat ownership

Phase 3 records threats but implements no later phase. Phase 4 owns phone-number/provider routing risks; Phase 5 trusted Z Fold device risks; Phase 6 voice-confidence risks; Phase 7 fallback/lockout risks; Phase 8 replay/liveness risks; Phase 9 YubiKey/passkey risks; Phase 10 governance-memory risks; Phase 11 risk-scored command-gating risks; Phase 12 intent-parser risks; Phase 13 gateway-router risks; Phase 14 runtime-bridge risks; Phase 15 The_Lab execution-boundary risks; Phase 16 vault/secrets/session risks; and Phase 17 location/privacy risks.

## 10. Archive-specific threats inherited from Phase 2

Phase 3 preserves and attacks-tests every Phase 2 invariant: historical archive content is non-authoritative (GW-T013); unknown critical classifications quarantine (GW-T012); message order is sequence-based (GW-T016); duplicate/conflict rules fail closed (GW-T016); integrity verification detects alteration but does not authenticate owner (GW-T015); sanitization and sensitivity classifications must be revalidated (GW-T012, GW-T026); prohibited/private data may not be silently promoted (GW-T014, GW-T026); archive availability cannot be assumed (GW-T031); real conversation data cannot be assumed (GW-T012); and archive history cannot produce current owner approval (GW-T013). Phase 2 provides no real conversation data.

## 11. Approval and authority threats

GW-T013 and GW-T017 through GW-T021 cover historical approval replay, session confusion, confused-deputy behavior, cross-phase escalation, forged verifier results, and Approval Broker misuse. Only a current, trusted, action-bound owner decision can satisfy a protected gate. Broker routing and validator results are evidence only.

## 12. Privacy and data-exposure threats

GW-T025 through GW-T030 and GW-T038 cover secrets/session leakage, privacy leakage, location leakage, telemetry exfiltration, unauthorized export, reference abuse, and retention/deletion failure. This design contains no real phone number, real conversation data, credential or secret value, biometric sample, or exact location data.

## 13. Availability and denial-of-service threats

GW-T031 and GW-T032 cover denial of service and resource exhaustion. Availability loss must never trigger weaker authentication, bypass freshness, or permit queued protected work to execute later without complete revalidation.

## 14. Fail-closed requirements

The system must remain `BLOCKED` when any required trust, identity, freshness, liveness, authority, integrity, privacy, classification, mitigation evidence, or risk state is missing, unknown, conflicting, expired, stale, or unverifiable. No risk becomes accepted because a test passed, a document exists, a previous phase merged, a model assigns LOW severity, an archive contains approval language, the Approval Broker routes it, a future phase is planned, or the owner previously approved something else.

## 15. Mitigation evidence requirements

Evidence must be reproducible, sanitized, phase-scoped, tied to the exact mitigation and version, include negative and error-path results, and be reviewed at the receiving boundary. Planned work, prose, a PASS label, or a future test name is not mitigation evidence. Evidence must contain no credentials, secrets, real conversation data, real phone numbers, exact location, or unnecessary personal data.

## 16. Residual-risk treatment

Every threat remains `UNASSESSED`. Phase 3 has no actual validated mitigation evidence sufficient to assert a reduced state. `LOW` inherent severity would still not mean accepted. Residual risk may change only after the mitigation-owning phases produce validated evidence and the Human Owner makes the later required decision.

## 17. Phase 3 handoff

Phase 4 may consume this reviewed threat model only as a design constraint. Phase 3 completion is not permission to provision a number, access a provider account, store credentials, configure telephony, activate network behavior, enroll a device, deploy, connect a broker, trade, place orders, or move money. Phase 4 remains non-activated and not authorized.

## 18. Acceptance matrix

| Requirement | Evidence | Pass condition | Result |
|---|---|---|---|
| Canonical identity | Section 1 and manifest | Exact Phase 3 name, authority, bundle, mode, and blocked transition | Design evidence only |
| Complete register | Section 8 | At least 24 unique stable IDs and all required fields | Design evidence only |
| Required coverage | GW-T001 through GW-T039 | Every required attack concept is explicit | Design evidence only |
| Phase 2 invariants | Section 10 | Every inherited invariant has a threat mapping | Design evidence only |
| Mitigation ownership | Register and Section 9 | Every threat names owning phases and evidence | Design evidence only |
| Safety boundary | Sections 14 and 17 | No runtime or protected capability introduced | Design evidence only |
| Residual risk | Section 16 | All entries remain UNASSESSED pending evidence | Owner gate pending |

## 19. Owner gate

Phase 3 preparation may complete autonomously, but the protected transition remains `BLOCKED`. Anthony is not asked to accept risk during implementation. The later owner decision is: **Accept or reject documented residual gateway risks after validated mitigations are presented.** Until mitigations are proven, residual risk remains `UNASSESSED` and the owner gate remains pending.
