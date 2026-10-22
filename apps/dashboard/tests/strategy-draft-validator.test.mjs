import assert from 'node:assert/strict'
import test from 'node:test'
import { validateStrategyDraft } from '../server/strategyDraftValidator.js'

const validDraft = { pair: 'EUR/USD', timeframe: 'H1', strategy: 'supertrend_research', atr_period: 14, supertrend_multiplier: 3, minimum_rr: 2, maximum_spread: 3, maximum_slippage: 1, maximum_concurrent_positions: 2, consecutive_loss_pause: 3, cooldown_minutes: 60, maximum_holding_minutes: 480, session: 'London', notes: 'Review only.' }

test('strategy validator accepts a bounded draft without persistence', () => {
  const before = JSON.stringify(validDraft)
  const result = validateStrategyDraft(validDraft)
  assert.equal(result.status, 'VALID')
  assert.equal(JSON.stringify(validDraft), before)
  assert.equal(result.draft.pair, 'EUR/USD')
})

test('strategy validator rejects unknown keys', () => {
  const result = validateStrategyDraft({ ...validDraft, execute: true })
  assert.equal(result.status, 'INVALID')
  assert.match(result.errors.join(' '), /Unknown field: execute/)
})

test('strategy validator enforces every numeric boundary', () => {
  const invalid = validateStrategyDraft({ atr_period: 0, supertrend_multiplier: 10.1, minimum_rr: .5, maximum_spread: 0, maximum_slippage: 101, maximum_concurrent_positions: 11, consecutive_loss_pause: 21, cooldown_minutes: 1441, maximum_holding_minutes: 10081 })
  assert.equal(invalid.status, 'INVALID')
  assert.equal(invalid.errors.length, 9)
})

test('strategy validator limits notes to 2000 characters', () => {
  const result = validateStrategyDraft({ notes: 'x'.repeat(2001) })
  assert.equal(result.status, 'INVALID')
})
