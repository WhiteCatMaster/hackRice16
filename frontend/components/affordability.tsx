'use client'

import { useState } from 'react'

import type { Affordability } from '@/lib/contract'
import { dayMonth } from '@/lib/format'

interface Props {
  user: string
  /** Converts a USD figure into whatever the header is currently showing. */
  fmt: (amount: number) => string
  live: boolean
}

/**
 * "Can I afford this?" as a screen rather than only a chat turn.
 *
 * Nothing here is computed in the browser. The engine answers with the number
 * *and* the date it holds to — `$47.34 safe` says much less than `$47.34 safe
 * through 31 Oct` — and, when she is already short, with the plan that turns a
 * no into a yes. Rendering one without the other is what makes the answer
 * ambiguous, so this card always shows both halves.
 */
export function AffordabilityCard({ user, fmt, live }: Props) {
  const [amount, setAmount] = useState('')
  const [answer, setAnswer] = useState<Affordability | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function ask(e: React.FormEvent) {
    e.preventDefault()
    const value = Number(amount)
    if (!Number.isFinite(value) || value <= 0 || busy) return
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(`/api/users/${user}/affordability`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ amount: value }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body?.error ?? 'The engine did not answer.')
      }
      setAnswer((await res.json()) as Affordability)
    } catch (err) {
      setAnswer(null)
      setError(err instanceof Error ? err.message : 'The engine did not answer.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel afford-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">BEFORE YOU SPEND</p>
          <h2>Can I afford it?</h2>
        </div>
      </div>

      <form className="afford-form" onSubmit={ask}>
        <div className="afford-input">
          <span aria-hidden>$</span>
          <input
            inputMode="decimal"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="47.34"
            aria-label="Amount you want to spend, in dollars"
          />
        </div>
        <button className="primary-button" type="submit" disabled={busy || !amount.trim()}>
          {busy ? 'Checking…' : 'Check'}
        </button>
      </form>

      {!live && (
        <p className="afford-note">
          This one needs the engine — it depends on the amount you type, so there is no
          fixture for it. Start the backend and set <code>TREASURER_API_BASE</code>.
        </p>
      )}

      {error && <p className="copilot-error">{error}</p>}

      {answer && (
        <div className={`afford-answer ${answer.affordable ? 'yes' : 'no'}`}>
          <p className="afford-verdict">
            {answer.affordable ? 'Yes' : answer.if_you_fix_first ? 'Not yet' : 'No'}
          </p>

          {/* The engine's own sentence. We quote it; we do not re-template it. */}
          <p className="afford-reason">{answer.reason}</p>

          <dl className="afford-figures">
            <div>
              <dt>Safe to spend</dt>
              <dd>
                {fmt(answer.max_safe_amount)}
                {answer.max_safe_through && (
                  <small> through {dayMonth(answer.max_safe_through)}</small>
                )}
              </dd>
            </div>

            {typeof answer.max_without_moving_runway === 'number' &&
              answer.max_without_moving_runway > answer.max_safe_amount && (
                <div>
                  <dt>Without moving your runway</dt>
                  <dd>
                    {fmt(answer.max_without_moving_runway)}
                    <small>does not fix being short</small>
                  </dd>
                </div>
              )}

            <div>
              <dt>Runway</dt>
              <dd>
                {answer.runway_date_before ? dayMonth(answer.runway_date_before) : 'past the flight'}
                {answer.runway_date_after !== answer.runway_date_before && (
                  <>
                    {' '}
                    <span aria-hidden>→</span>{' '}
                    {answer.runway_date_after ? dayMonth(answer.runway_date_after) : 'past the flight'}
                  </>
                )}
                {typeof answer.days_lost === 'number' && answer.days_lost > 0 && (
                  <small>
                    {answer.days_lost} day{answer.days_lost === 1 ? '' : 's'} closer
                  </small>
                )}
              </dd>
            </div>
          </dl>

          {answer.if_you_fix_first && (
            <div className="afford-fix">
              <p className="eyebrow">IF YOU FIX IT FIRST</p>
              <ul>
                {answer.if_you_fix_first.plan.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ul>
              <p className="afford-fix-effect">
                Then <strong>{fmt(answer.if_you_fix_first.max_safe_amount)}</strong> is safe
                {answer.if_you_fix_first.max_safe_through && (
                  <> through {dayMonth(answer.if_you_fix_first.max_safe_through)}</>
                )}
                {answer.if_you_fix_first.closes_the_gap && <> — and the gap is closed.</>}
              </p>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
