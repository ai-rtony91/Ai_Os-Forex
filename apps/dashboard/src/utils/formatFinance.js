export function formatCurrency(value, currency = 'USD') { if (value === null || value === undefined || value === 'UNKNOWN') return 'UNKNOWN'; return new Intl.NumberFormat('en-US', { style: 'currency', currency, maximumFractionDigits: 2 }).format(value) }
export function formatPercent(value) { if (value === null || value === undefined || value === 'UNKNOWN') return 'UNKNOWN'; return `${Number(value).toFixed(2)}%` }
export function formatValue(value) { return value === null || value === undefined || value === '' ? 'UNKNOWN' : String(value) }
