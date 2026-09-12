// Where a brought-along model key lives on a phone.
//
// The backend spends the key on one turn and forgets it
// (`backend/agent/keys.py`), so something on this side has to remember it
// between questions. On a phone that place is the OS keystore — the iOS
// keychain, Android's EncryptedSharedPreferences — which is what
// `expo-secure-store` wraps. Not AsyncStorage: that is a plain file in the app
// sandbox, and this is somebody's billable credential.
//
// Three places, in order of preference, because one app runs on three platforms:
//
//   native  -> expo-secure-store, survives a restart and a reboot
//   web     -> localStorage, same as the web app's lib/model-key.ts
//   neither -> memory, for this session only, and the UI says so
//
// The web app's equivalent is `frontend/lib/model-key.ts`. Both read the shape
// and the header names out of `contract.ts`.

import * as SecureStore from 'expo-secure-store'
import { Platform } from 'react-native'

import { MODEL_PROVIDERS, type ModelKey, type ModelProvider } from './contract'

// SecureStore keys are alphanumerics, '.', '-' and '_' only, so this is not the
// dotted name the browser uses.
const STORE_KEY = 'extreasurer_model_key'
const WEB_KEY = 'extreasurer.model-key'

/** Which of the three actually answered last. The UI says which. */
export type KeyStore = 'keychain' | 'browser' | 'session'

let fallback: ModelKey | null = null
let store: KeyStore = Platform.OS === 'web' ? 'browser' : 'keychain'

export function keyStore(): KeyStore {
  return store
}

/** Only what `contract.ts` describes, and only if it is all there. */
function parse(raw: string | null): ModelKey | null {
  if (!raw) return null
  try {
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

export async function load(): Promise<ModelKey | null> {
  if (Platform.OS === 'web') {
    try {
      return parse(window.localStorage.getItem(WEB_KEY))
    } catch {
      // A private window, or storage blocked. Nothing stored, nothing to say.
      store = 'session'
      return fallback
    }
  }
  try {
    return parse(await SecureStore.getItemAsync(STORE_KEY))
  } catch {
    // A device with no keystore available — a simulator with a broken keychain
    // is the one that actually happens. The key still works this session.
    store = 'session'
    return fallback
  }
}

export async function save(key: ModelKey): Promise<void> {
  fallback = key
  const raw = JSON.stringify(key)
  if (Platform.OS === 'web') {
    try {
      window.localStorage.setItem(WEB_KEY, raw)
      store = 'browser'
    } catch {
      store = 'session'
    }
    return
  }
  try {
    await SecureStore.setItemAsync(STORE_KEY, raw)
    store = 'keychain'
  } catch {
    // Worth knowing, not worth blocking on: the caller holds the key in state,
    // so the copilot works either way — it just will not on the next launch.
    store = 'session'
  }
}

export async function clear(): Promise<void> {
  fallback = null
  if (Platform.OS === 'web') {
    try {
      window.localStorage.removeItem(WEB_KEY)
    } catch {
      // Nothing stored to remove.
    }
    return
  }
  try {
    await SecureStore.deleteItemAsync(STORE_KEY)
  } catch {
    // Same.
  }
}
