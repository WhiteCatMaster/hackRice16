'use client'

// Where a brought-along model key lives in the browser.
//
// The backend deliberately does not keep it (`backend/agent/keys.py`): a key
// pasted into the copilot is spent on that turn and forgotten. Something has to
// remember it between turns, and the only honest place is the machine it was
// typed on — so, `localStorage`, on the user's own origin, read back into the
// request headers on every ask.
//
// The phone does the same job in `mobile/lib/secrets.ts`, against the keychain.
// Both read the shape and the header names out of `contract.ts`, which is the
// copy the backend agrees with.

import { useCallback, useEffect, useState } from 'react'

import { type ModelKey, type ModelProvider, MODEL_PROVIDERS } from './contract'

const STORAGE_KEY = 'extreasurer.model-key'

/**
 * The stored key, or null.
 *
 * Every access is guarded: `localStorage` throws outright in a Safari private
 * window and in an iframe with third-party storage blocked, and a copilot that
 * cannot open is a worse failure than one with no key in it.
 */
export function load(): ModelKey | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<ModelKey>
    if (!parsed?.key || !parsed?.provider) return null
    if (!MODEL_PROVIDERS.some((p) => p.id === parsed.provider)) return null
    return {
      provider: parsed.provider as ModelProvider,
      key: parsed.key,
      model: parsed.model || undefined,
      baseUrl: parsed.baseUrl || undefined,
    }
  } catch {
    return null
  }
}

export function save(key: ModelKey): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(key))
  } catch {
    // Storage is full or blocked. The key still works for this session — the
    // caller holds it in state — so this is not worth interrupting anyone over.
  }
}

export function clear(): void {
  try {
    window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Nothing to do about it, and nothing to tell the user.
  }
}

/**
 * The key, as component state.
 *
 * `ready` is there because the first render happens on the server, where there
 * is no `localStorage`: without it the copilot would open claiming no key is
 * set, then correct itself a frame later.
 */
export function useModelKey() {
  const [key, setKeyState] = useState<ModelKey | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    setKeyState(load())
    setReady(true)
  }, [])

  const setKey = useCallback((next: ModelKey) => {
    setKeyState(next)
    save(next)
  }, [])

  const forget = useCallback(() => {
    setKeyState(null)
    clear()
  }, [])

  return { key, setKey, forget, ready }
}
