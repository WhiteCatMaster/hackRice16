'use client'

// "Use your own model" — the form, on a laptop.
//
// The copilot normally answers with whatever key the backend's .env has. That
// is one key, on one machine, belonging to one of us; anybody else looking at
// this app has their own and no way to use it. This is that way.
//
// The phone has the same form in `mobile/app/model-key.tsx`, over the same
// headers. Nothing about the key reaches the server's disk — see
// `backend/agent/keys.py`.

import { useState } from 'react'

import {
  MODEL_PROVIDERS,
  type ModelKey,
  type ModelProvider,
  inferProvider,
  redactKey,
} from '@/lib/contract'

interface Props {
  current: ModelKey | null
  /** False in fixture mode, where a key has no backend to be spent by. */
  live: boolean
  onSave: (key: ModelKey) => void
  onForget: () => void
  onClose: () => void
}

/** The same rules `backend/agent/keys.py` applies, so a paste fails here first. */
function complain(key: string): string | null {
  const trimmed = key.trim()
  if (!trimmed) return 'Paste a key first.'
  if (/\s/.test(trimmed)) return 'A key has no spaces or line breaks in it. Check the paste.'
  if (trimmed.length > 400) return 'That is longer than a key. Did a whole file come along?'
  return null
}

export function ModelKeyPanel({ current, live, onSave, onForget, onClose }: Props) {
  const [provider, setProvider] = useState<ModelProvider>(current?.provider ?? 'gemini')
  const [key, setKey] = useState(current?.key ?? '')
  const [model, setModel] = useState(current?.model ?? '')
  const [baseUrl, setBaseUrl] = useState(current?.baseUrl ?? '')
  const [error, setError] = useState<string | null>(null)

  const meta = MODEL_PROVIDERS.find((p) => p.id === provider)!
  // A key whose shape says "Claude" sitting in the Gemini field is the mistake
  // this form exists to catch. It is a note rather than a block: an
  // OpenAI-compatible proxy hands out keys in every shape there is.
  const looksLike = inferProvider(key)
  const mismatch = key.trim() !== '' && looksLike !== null && looksLike !== provider

  function submit(event: React.FormEvent) {
    event.preventDefault()
    const wrong = complain(key)
    if (wrong) return setError(wrong)
    setError(null)
    onSave({
      provider,
      key: key.trim(),
      model: model.trim() || undefined,
      baseUrl: provider === 'openai' && baseUrl.trim() ? baseUrl.trim() : undefined,
    })
  }

  return (
    <form className="model-key" onSubmit={submit}>
      <div className="model-key-head">
        <div>
          <p className="eyebrow">YOUR OWN MODEL</p>
          <h3>Answer with your key</h3>
        </div>
        <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
          ×
        </button>
      </div>

      <p className="model-key-note">
        Sent with each question, used for that one answer, and never written down
        on the server. It stays in this browser.
        {!live && ' This app is on fixtures right now, so a key has no backend to spend it — point TREASURER_API_BASE at the API first.'}
      </p>

      <div className="model-key-providers" role="radiogroup" aria-label="Provider">
        {MODEL_PROVIDERS.map((p) => (
          <button
            key={p.id}
            type="button"
            role="radio"
            aria-checked={provider === p.id}
            className={provider === p.id ? 'on' : undefined}
            onClick={() => setProvider(p.id)}
          >
            {p.label}
          </button>
        ))}
      </div>

      <label className="model-key-field">
        <span>API KEY</span>
        <input
          type="password"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          placeholder={meta.prefix}
          autoComplete="off"
          spellCheck={false}
          aria-label="API key"
        />
        <small>From {meta.source}</small>
      </label>

      <label className="model-key-field">
        <span>MODEL (OPTIONAL)</span>
        <input
          value={model}
          onChange={(e) => setModel(e.target.value)}
          placeholder={meta.defaultModel}
          autoComplete="off"
          spellCheck={false}
          aria-label="Model name"
        />
      </label>

      {meta.endpoint && (
        <label className="model-key-field">
          <span>ENDPOINT (OPTIONAL)</span>
          <input
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://openrouter.ai/api/v1"
            autoComplete="off"
            spellCheck={false}
            aria-label="Model endpoint"
          />
          <small>
            Anything that speaks OpenAI&rsquo;s shape — OpenRouter, Groq, or a model on
            this machine. http is only allowed for localhost.
          </small>
        </label>
      )}

      {mismatch && (
        <p className="model-key-warn">
          That key looks like {MODEL_PROVIDERS.find((p) => p.id === looksLike)?.label}
          &rsquo;s. Switch provider, or send it anyway if your endpoint expects it.
        </p>
      )}
      {error && <p className="model-key-error">{error}</p>}

      <div className="action-buttons">
        <button className="primary-button" type="submit">
          {current ? 'Replace key' : 'Use this key'}
        </button>
        {current && (
          <button type="button" className="ghost-button" onClick={onForget}>
            Forget {redactKey(current.key)}
          </button>
        )}
      </div>
    </form>
  )
}
