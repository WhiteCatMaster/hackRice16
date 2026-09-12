'use client'

import { useState } from 'react'

import type { ActionResult, ChatReply, ProposedAction } from '@/lib/contract'
import { dayMonth, money, runwayLabel } from '@/lib/format'

interface Message {
  role: 'user' | 'agent'
  text: string
  tools?: string[]
}

const SUGGESTIONS = [
  '¿Puedo permitirme ir a Chicago este finde?',
  'Why did my card balance go up if I paid it?',
  'What happens if I cancel the gym before I fly home?',
]

interface Props {
  user: string
  open: boolean
  onClose: () => void
  onActionConfirmed: (result: ActionResult) => void
}

/**
 * The agent, with the confirmation gate in front of every write.
 *
 * It never does arithmetic here: the reply text and the proposed action both
 * come from the backend, which got its numbers from the engine. That is design
 * rule 1 in begin.md §6, and it is the answer to "how do you stop the LLM from
 * hallucinating a balance".
 */
export function Copilot({ user, open, onClose, onActionConfirmed }: Props) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [action, setAction] = useState<ProposedAction | null>(null)
  const [result, setResult] = useState<ActionResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function ask(message: string) {
    if (!message.trim() || busy) return
    setMessages((m) => [...m, { role: 'user', text: message }])
    setInput('')
    setBusy(true)
    setError(null)
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ user, message }),
      })
      if (!res.ok) throw new Error(await res.text())
      const data: ChatReply = await res.json()
      setMessages((m) => [...m, { role: 'agent', text: data.reply, tools: data.used_tools }])
      if (data.proposed_action) {
        setAction(data.proposed_action)
        setResult(null)
      }
    } catch {
      setError('The agent did not answer. Is the backend running?')
    } finally {
      setBusy(false)
    }
  }

  async function approve() {
    if (!action) return
    setBusy(true)
    try {
      const res = await fetch(`/api/actions/${action.id}/confirm`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ user, action }),
      })
      const data: ActionResult = await res.json()
      setResult(data)
      onActionConfirmed(data)
    } catch {
      setError('The action could not be confirmed.')
    } finally {
      setBusy(false)
    }
  }

  if (!open) return null

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside
        className="copilot-drawer"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Financial copilot"
      >
        <header className="copilot-head">
          <div>
            <p className="eyebrow">FINANCIAL COPILOT</p>
            <h2>Ask about your money</h2>
          </div>
          <button className="modal-close" onClick={onClose} aria-label="Close copilot">
            ×
          </button>
        </header>

        <div className="copilot-body">
          {messages.length === 0 && (
            <div className="copilot-empty">
              <p>
                Every number in an answer comes from the forecast engine. The
                assistant picks the tools and explains the result — it does not
                do the arithmetic.
              </p>
              <div className="suggestions">
                {SUGGESTIONS.map((s) => (
                  <button key={s} onClick={() => ask(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <div key={i} className={`bubble ${m.role}`}>
              <p>{m.text}</p>
              {m.tools && m.tools.length > 0 && (
                <span className="tool-trace">via {m.tools.join(' · ')}</span>
              )}
            </div>
          ))}

          {busy && <div className="bubble agent pending">…</div>}
          {error && <p className="copilot-error">{error}</p>}

          {action && (
            <div className="action-card">
              <p className="eyebrow">PROPOSED ACTION · NEEDS YOUR APPROVAL</p>
              <h3>
                Move {money(action.amount)} from {action.from} to {action.to}
              </h3>
              {action.effect &&
                (action.effect.measured === false ? (
                  // A null date here means "we could not work it out", which is
                  // the opposite of what it means when the effect was measured.
                  // Saying so is better than implying the best outcome.
                  <p className="action-effect unmeasured">
                    {action.effect.measured_note ??
                      'We could not measure what this would do to your runway.'}
                  </p>
                ) : (
                  <p className="action-effect">
                    Runway{' '}
                    {action.effect.runway_date_before && (
                      <>
                        <s>{dayMonth(action.effect.runway_date_before)}</s>{' '}
                        <span aria-hidden>→</span>{' '}
                      </>
                    )}
                    {/* Never hidden: null is the best outcome there is, and
                        dropping the line loses the payoff of the whole beat. */}
                    <strong>{runwayLabel(action.effect.runway_date_after)}</strong>
                  </p>
                ))}
              {result ? (
                <p className={`action-result ${result.executed_in_nessie ? 'live' : 'simulated'}`}>
                  {result.message}
                </p>
              ) : (
                <div className="action-buttons">
                  <button className="primary-button" onClick={approve} disabled={busy}>
                    Approve
                  </button>
                  <button className="ghost-button" onClick={() => setAction(null)}>
                    Not now
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        <form
          className="copilot-input"
          onSubmit={(e) => {
            e.preventDefault()
            ask(input)
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask in English or Spanish…"
            aria-label="Message the copilot"
          />
          <button className="primary-button" type="submit" disabled={busy || !input.trim()}>
            Send
          </button>
        </form>
      </aside>
    </div>
  )
}
