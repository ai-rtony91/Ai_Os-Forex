import { provenanceLabel } from '../utils/dataProvenance.js'
export default function LiveMetric({ icon, label, value, rawValue = value, previousValue, detail, provenance, stale = false, emphasis = 'number' }) {
  const pulse = !stale && typeof rawValue === 'number' && typeof previousValue === 'number' && rawValue !== previousValue ? (rawValue > previousValue ? 'pulse-up' : 'pulse-down') : ''
  const unavailable = ['UNKNOWN', 'UNAVAILABLE', 'NO DATA', 'NO EVIDENCE', 'NOT CONNECTED'].includes(String(value))
  return <article className={`liveMetric metric-${emphasis} ${unavailable ? 'isUnavailable' : ''} ${pulse}`.trim()}><span>{icon && <i aria-hidden="true">{icon}</i>}{label}</span><strong>{value}</strong>{detail && <small>{detail}</small>}{provenance && <small>{provenanceLabel(provenance)}</small>}</article>
}
