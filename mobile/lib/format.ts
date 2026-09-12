// Formatting helpers. Copied verbatim from frontend/lib/format.ts — no imports
// beyond the standard library, so it runs unchanged on Hermes.
//
// `Intl` is the one thing worth naming: Hermes ships with full ICU on both
// platforms from RN 0.73, so `Intl.NumberFormat` here formats the same way the
// browser does. Nothing below needs a polyfill.

/**
 * Parse a YYYY-MM-DD (or YYYY-MM-DDTHH:MM) string as a *local* date.
 *
 * `new Date('2026-10-10')` is UTC midnight, which renders as October 9th for
 * anyone west of Greenwich. The demo is in Omaha. Every date in the fixtures
 * goes through here.
 */
export function parseDate(value: string): Date {
  const [date, time] = value.split('T')
  const [y, m, d] = date.split('-').map(Number)
  const [hh, mm] = (time ?? '').split(':').map(Number)
  return new Date(y, (m ?? 1) - 1, d ?? 1, hh || 0, mm || 0)
}

export function money(amount: number, currency = 'USD'): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount)
}

/** Whole dollars, for places where the cents are noise. */
export function moneyRound(amount: number, currency = 'USD'): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
  }).format(amount)
}

export function signedMoney(amount: number, currency = 'USD'): string {
  const formatted = money(Math.abs(amount), currency)
  return `${amount < 0 ? '-' : '+'}${formatted}`
}

export function dayMonth(value: string): string {
  return parseDate(value).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  })
}

export function longDate(value: string): string {
  return parseDate(value).toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  })
}

export function daysBetween(from: string, to: string): number {
  const ms = parseDate(to).getTime() - parseDate(from).getTime()
  return Math.round(ms / 86_400_000)
}

/** "Today, 12:42 PM" / "Yesterday, 9:18 AM" / "Sep 04, 8:00 AM". */
export function whenLabel(value: string, asOf: string): string {
  const at = parseDate(value)
  const days = daysBetween(value.split('T')[0], asOf)
  const time = at.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  })
  if (days === 0) return `Today, ${time}`
  if (days === 1) return `Yesterday, ${time}`
  return `${dayMonth(value)}, ${time}`
}

export function percent(fraction: number): string {
  return `${Math.round(fraction * 100)}%`
}

/**
 * A runway date, where null is good news rather than a missing value.
 *
 * The engine returns `null` for "never runs short inside the horizon" — the
 * best outcome there is, and what both healthy personas report all the time.
 * Printing it raw puts "null" on screen; guarding it with `&&` is the quieter
 * version of the same bug, because it hides the effect exactly when the effect
 * is best. Both go through here instead.
 *
 * `measured: false` is the genuinely unknown case and must not borrow this
 * wording — see `runwayEffect` callers, which check that first.
 */
export function runwayLabel(
  value: string | null | undefined,
  lastsPast = 'past your flight home',
): string {
  return value ? dayMonth(value) : lastsPast
}
