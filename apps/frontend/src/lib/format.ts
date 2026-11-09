export const nf = new Intl.NumberFormat('en-US')

const cf = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
})

export function formatCurrency(n: number): string {
  return cf.format(n)
}

export function maskCardNumber(n: string): string {
  return `•••• ${n.slice(-4)}`
}

/** Format a backend-measured query duration (milliseconds) for display. */
export function formatMs(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)} s`
  if (ms >= 10) return `${Math.round(ms)} ms`
  return `${ms.toFixed(1)} ms`
}
