const RULES = Object.freeze({
  pair: { type: 'string', max: 30 },
  timeframe: { type: 'string', max: 20 },
  strategy: { type: 'string', max: 80 },
  atr_period: { type: 'integer', min: 1, max: 100 },
  supertrend_multiplier: { type: 'number', min: 0.5, max: 10 },
  minimum_rr: { type: 'number', min: 1, max: 10 },
  maximum_spread: { type: 'number', minExclusive: 0, max: 100 },
  maximum_slippage: { type: 'number', min: 0, max: 100 },
  maximum_concurrent_positions: { type: 'integer', min: 1, max: 10 },
  consecutive_loss_pause: { type: 'integer', min: 1, max: 20 },
  cooldown_minutes: { type: 'integer', min: 0, max: 1440 },
  maximum_holding_minutes: { type: 'integer', min: 1, max: 10080 },
  session: { type: 'string', max: 40 },
  notes: { type: 'string', max: 2000 },
})

function validateField(name, value, rule) {
  if (rule.type === 'string') {
    if (typeof value !== 'string') return `${name} must be a string.`
    if (value.length > rule.max) return `${name} exceeds ${rule.max} characters.`
    return null
  }
  if (typeof value !== 'number' || !Number.isFinite(value)) return `${name} must be a finite number.`
  if (rule.type === 'integer' && !Number.isInteger(value)) return `${name} must be an integer.`
  if (rule.min !== undefined && value < rule.min) return `${name} must be at least ${rule.min}.`
  if (rule.minExclusive !== undefined && value <= rule.minExclusive) return `${name} must be greater than ${rule.minExclusive}.`
  if (rule.max !== undefined && value > rule.max) return `${name} must be no greater than ${rule.max}.`
  return null
}

export function validateStrategyDraft(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) {
    return { status: 'INVALID', errors: ['Draft must be a JSON object.'], draft: {} }
  }
  const errors = []
  const draft = {}
  for (const [name, value] of Object.entries(input)) {
    const rule = RULES[name]
    if (!rule) {
      errors.push(`Unknown field: ${name}`)
      continue
    }
    const error = validateField(name, value, rule)
    if (error) errors.push(error)
    else draft[name] = typeof value === 'string' ? value.trim() : value
  }
  return { status: errors.length ? 'INVALID' : 'VALID', errors, draft }
}

export const STRATEGY_DRAFT_FIELDS = Object.freeze(Object.keys(RULES))
