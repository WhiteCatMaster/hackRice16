'use client'

import { useState } from 'react'

import type { Alert, TransferCheck } from '@/lib/contract'
import { money, whenLabel } from '@/lib/format'

/** The three transfer cases P1 stages with `python -m seed.scenarios`. */
export const TRANSFER_SCENARIOS = [
  {
    key: 'fake_landlord',
    payee: 'Omaha Property Holdings',
    amount: 800,
    note: 'URGENT apartment deposit - pay today or you lose the place',
    expect: 'Should pause',
  },
  {
    key: 'immigration_fine',
    payee: 'USCIS Processing Center',
    amount: 1200,
    note: 'USCIS processing fine - immediate payment required',
    expect: 'Should pause',
  },
  {
    key: 'legit_roommate',
    payee: 'Marta Aguirre',
    amount: 60,
    note: 'internet share',
    expect: 'Should go through',
  },
] as const

export function useTransferCheck(user: string) {
  const [check, setCheck] = useState<(TransferCheck & { payee?: string }) | null>(null)
  const [busy, setBusy] = useState(false)

  async function run(scenario: (typeof TRANSFER_SCENARIOS)[number]) {
    setBusy(true)
    try {
      const res = await fetch('/api/transfers/check', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          user,
          scenario: scenario.key,
          amount: scenario.amount,
          description: scenario.note,
        }),
      })
      if (!res.ok) return
      const data: TransferCheck = await res.json()
      setCheck({ ...data, payee: scenario.payee })
    } finally {
      setBusy(false)
    }
  }

  return { check, busy, run, clear: () => setCheck(null) }
}

/**
 * The pause. It happens *before* the transfer, which is the whole difference
 * between this and a fraud alert that arrives after the money is gone.
 */
export function ScamModal({
  check,
  onClose,
}: {
  check: TransferCheck & { payee?: string }
  onClose: () => void
}) {
  const paused = check.pause
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="scam-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <button className="modal-close" onClick={onClose} aria-label="Close">
          ×
        </button>
        <div className={`modal-shield ${paused ? '' : 'clear'}`}>{paused ? '!' : '✓'}</div>
        <p className="eyebrow">{paused ? 'TRANSFER PAUSED' : 'TRANSFER LOOKS NORMAL'}</p>
        <h2>
          {paused ? 'A pause before you pay' : 'This one looks like you'}
        </h2>
        <p>
          {money(check.amount)} to {check.payee ?? 'this payee'}.{' '}
          {paused
            ? 'Nothing has left your account. Here is what we noticed.'
            : 'We found nothing unusual, so we are not going to get in your way.'}
        </p>

        <div className="risk-meter">
          <div className="risk-bar">
            <span
              className={paused ? 'high' : 'low'}
              style={{ width: `${Math.min(100, Math.max(4, check.risk_score))}%` }}
            />
          </div>
          <strong>{check.risk_score}/100</strong>
        </div>

        {check.reasons.map((reason) => (
          <div className="modal-check" key={reason}>
            <span>{paused ? '!' : '✓'}</span>
            <div>
              <strong>{reason}</strong>
            </div>
          </div>
        ))}

        {check.questions.length > 0 && (
          <div className="questions">
            <p className="eyebrow">BEFORE YOU CONTINUE</p>
            {check.questions.map((q) => (
              <label key={q}>
                <input type="checkbox" /> {q}
              </label>
            ))}
          </div>
        )}

        <div className="action-buttons">
          <button className="primary-button full" onClick={onClose}>
            {paused ? 'Cancel the transfer' : 'Send it'}
          </button>
          {paused && (
            <button className="ghost-button" onClick={onClose}>
              I verified this myself, send anyway
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export function AlertList({ alerts, asOf }: { alerts: Alert[]; asOf: string }) {
  if (alerts.length === 0) {
    return (
      <div className="empty-note">
        <strong>Nothing to look at.</strong>
        <span>No unusual activity on this account.</span>
      </div>
    )
  }
  return (
    <div className="alerts-list">
      {alerts.map((alert) => (
        <article className={`alert-row ${alert.severity}`} key={alert.id}>
          <span className="alert-mark">!</span>
          <div className="alert-copy">
            <strong>{alert.title}</strong>
            <span>{alert.reason}</span>
            <small>{whenLabel(alert.created_at, asOf)}</small>
          </div>
          <strong className="alert-amount">{money(alert.amount)}</strong>
        </article>
      ))}
    </div>
  )
}
