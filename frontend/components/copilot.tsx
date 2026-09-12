'use client'

import { useState } from 'react'

import { ModelKeyPanel } from './model-key'
import type { ActionResult, ChatError, ChatReply, ProposedAction } from '@/lib/contract'
import { MODEL_PROVIDERS, isChatError, modelKeyHeaders } from '@/lib/contract'
import { dayMonth, money, runwayLabel } from '@/lib/format'
import { useModelKey } from '@/lib/model-key'

interface Message {
  role: 'user' | 'agent'
  text: string
  tools?: string[]
  /** Which brain wrote it, when a model did. */
  provider?: string
  /** Whose key paid for it. */
  keySource?: 'user' | 'server' | null
}

const SUGGESTIONS = [
  '¿Puedo permitirme ir a Chicago este finde?',
  'Why did my card balance go up if I paid it?',
  'What happens if I cancel the gym before I fly home?',
]

interface Props {
  user: string
  open: boolean
  /** False in fixture mode: no backend, so one canned reply and no key to spend. */
  live: boolean
  onClose: () => void
  onActionConfirmed: (result: ActionResult) => void
}

function providerLabel(id?: string): string {
  return MODEL_PROVIDERS.find((p) => p.id === id)?.label ?? 'the scripted router'
}

/**
 * The agent, with the confirmation gate in front of every write.
 *
 * It never does arithmetic here: the reply text and the proposed action both
 * come from the backend, which got its numbers from the engine. That is design
 * rule 1 in begin.md §6, and it is the answer to "how do you stop the LLM from
 * hallucinating a balance".
 *
 * Which model writes the prose is the user's to choose. A key pasted into the
 * panel below is kept in this browser, sent with each question, and spent on
 * that one turn — see `lib/model-key.ts`. With no key the backend answers with
 * its own, or with the scripted router, exactly as before.
 */
export function Copilot({ user, open, live, onClose, onActionConfirmed }: Props) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [action, setAction] = useState<ProposedAction | null>(null)
  const [result, setResult] = useState<ActionResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [keyTrouble, setKeyTrouble] = useState<string | null>(null)
  const [editingKey, setEditingKey] = useState(false)

  const { key: modelKey, setKey, forget, ready } = useModelKey()

  async function ask(message: string) {
    if (!message.trim() || busy) return
    setMessages((m) => [...m, { role: 'user', text: message }])
    setInput('')
    setBusy(true)
    setError(null)
    setKeyTrouble(null)
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'content-type': 'application/json', ...modelKeyHeaders(modelKey) },
        body: JSON.stringify({ user, message }),
      })
      const data: ChatReply | ChatError = await res.json()
      if (isChatError(data)) {
        // `bad_model_key` is the one refusal the user can act on, and its
        // message says which way the key is unreadable. Every other error is
        // ours, not theirs, and reads as the backend being down — which it
        // probably is.
        if (data.error === 'bad_model_key') setKeyTrouble(data.message ?? data.error)
        else throw new Error(data.error)
        return
      }
      if (!res.ok) throw new Error('bad status')
      setMessages((m) => [
        ...m,
        {
          role: 'agent',
          text: data.reply,
          tools: data.used_tools,
          provider: data._provider,
          keySource: data._key_source,
        },
      ])
      // A key of the user's that did not work is the user's to fix — a typo, an
      // empty quota, a model name that does not exist. The answer still landed
      // (the scripted router composed it), so this is a note, not an error.
      if (data._key_rejected) {
        setKeyTrouble(
          `Your key did not answer${data._fell_back ? ` — ${data._fell_back}` : ''}. ` +
            'The reply below came from the scripted router instead.',
        )
      }
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
          <div className="copilot-head-actions">
            {/* `ready` is false until localStorage has been read, and a button
                that says "use your own model" for a frame before correcting
                itself to "your Gemini key" reads as a bug. */}
            <button
              className={`key-button${modelKey ? ' on' : ''}`}
              onClick={() => setEditingKey((was) => !was)}
              aria-expanded={editingKey}
              title="Use your own model key"
            >
              {ready && modelKey ? `${providerLabel(modelKey.provider)} key` : 'Use your own key'}
            </button>
            <button className="modal-close" onClick={onClose} aria-label="Close copilot">
              ×
            </button>
          </div>
        </header>

        <div className="copilot-body">
          {editingKey && (
            <ModelKeyPanel
              current={modelKey}
              live={live}
              onSave={(next) => {
                setKey(next)
                setEditingKey(false)
                setKeyTrouble(null)
              }}
              onForget={() => {
                forget()
                setEditingKey(false)
                setKeyTrouble(null)
              }}
              onClose={() => setEditingKey(false)}
            />
          )}

          {messages.length === 0 && (
            <div className="copilot-empty">
              <p>
                Every number in an answer comes from the forecast engine. The
                assistant picks the tools and explains the result — it does not
                do the arithmetic.
              </p>
              {!live && (
                <p>
                  Running on fixtures, so this is one canned reply from
                  <code> mocks/api_chat_response.json</code>. Point
                  <code> TREASURER_API_BASE</code> at the API for a real
                  conversation.
                </p>
              )}
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
              {m.role === 'agent' && m.keySource === 'user' && (
                <span className="tool-trace">written by your {providerLabel(m.provider)} key</span>
              )}
            </div>
          ))}

          {busy && <div className="bubble agent pending">…</div>}
          {keyTrouble && (
            <p className="model-key-warn" role="status">
              {keyTrouble}{' '}
              <button className="link-button" onClick={() => setEditingKey(true)}>
                Check the key
              </button>
            </p>
          )}
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
