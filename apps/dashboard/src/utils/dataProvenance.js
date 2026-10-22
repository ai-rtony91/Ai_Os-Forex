export function provenanceFrom(envelope, overrides = {}) { return { source: envelope?.source ?? 'unavailable', mode: envelope?.mode ?? 'UNKNOWN', asOf: envelope?.as_of ?? 'UNKNOWN', freshness: envelope?.freshness ?? 'UNKNOWN', ...overrides } }
export function provenanceLabel(provenance) { return `${String(provenance.source).toUpperCase()} · ${provenance.mode} · ${provenance.freshness}` }
