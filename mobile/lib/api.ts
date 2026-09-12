// Data access, on a phone. Two modes, one switch — the same rule as the web app.
//
//   EXPO_PUBLIC_TREASURER_API_BASE set    -> call P3's FastAPI, which owns the contract.
//   EXPO_PUBLIC_TREASURER_API_BASE unset  -> read P1's fixtures, bundled by Metro.
//
// begin.md's working agreement is "mocks first: nobody waits for anyone", so the
// screens are built against mocks/ and the backend drops in by setting one
// environment variable. That much is a straight port of frontend/lib/api.ts.
//
// One thing genuinely differs. The web app runs this on the server and puts its
// own routes under /api in front of the browser; a phone has no server of its
// own, so these functions ARE the client and they talk to the backend directly.
// That makes the backend's CORS the thing to get right, not a proxy — see the
// README.

import Constants from 'expo-constants'
import { Platform } from 'react-native'

import type {
  ActionResult,
  Activity,
  ActivityItem,
  Affordability,
  Alerts,
  Bills,
  ChatReply,
  Credit,
  Forecast,
  Profile,
  Summary,
  TransferCheck,
} from './contract'
import { chatFixture, fixture, transferFixture } from './mocks'

/**
 * Where the backend is, as the *phone* can reach it.
 *
 * `127.0.0.1` means the phone itself, so a base pointing at loopback — which is
 * exactly what the README tells you to run uvicorn on — reaches nothing from a
 * real device. Expo already knows the LAN address the bundle was served from,
 * so borrow its host and keep the port. This is why `pnpm dev` on a laptop and
 * `npm start` on a phone can share one .env line.
 */
function resolveBase(raw: string): string {
  const base = raw.replace(/\/$/, '')
  if (!base) return ''
  if (Platform.OS === 'web') return base

  const loopback = /^(https?:\/\/)(localhost|127\.0\.0\.1|\[::1\])(:\d+)?/i
  const match = base.match(loopback)
  if (!match) return base

  // "192.168.1.24:8081" — the machine running Metro, which is also the machine
  // running uvicorn in every setup the README describes.
  const hostUri = Constants.expoConfig?.hostUri ?? Constants.linkingUri ?? ''
  const host = hostUri.replace(/^\w+:\/\//, '').split('/')[0].split(':')[0]
  if (!host || host === 'localhost' || host === '127.0.0.1') return base

  return base.replace(loopback, `${match[1]}${host}${match[3] ?? ''}`)
}

export const API_BASE = resolveBase(process.env.EXPO_PUBLIC_TREASURER_API_BASE ?? '')
export const LIVE = API_BASE !== ''
export const DEFAULT_USER = process.env.EXPO_PUBLIC_TREASURER_USER ?? 'ana'

/** A phone on hotel wifi can hang forever. Fail visibly instead. */
const TIMEOUT_MS = 10_000

async function live<T>(endpoint: string, init?: RequestInit): Promise<T | null> {
  const abort = new AbortController()
  const timer = setTimeout(() => abort.abort(), TIMEOUT_MS)
  try {
    const res = await fetch(`${API_BASE}${endpoint}`, {
      ...init,
      headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) },
      signal: abort.signal,
    })
    if (!res.ok) return null
    return (await res.json()) as T
  } catch {
    return null
  } finally {
    clearTimeout(timer)
  }
}

/** GET endpoints: the live backend if there is one, the fixture otherwise. */
function reader<T>(endpoint: (user: string) => string, kind: 'summary' | 'bills' | 'credit' | 'alerts') {
  return (user: string): Promise<T | null> =>
    LIVE ? live<T>(endpoint(user)) : Promise.resolve(fixture<T>(user, kind))
}

export const getSummary = reader<Summary>((u) => `/api/users/${u}/summary`, 'summary')
export const getBills = reader<Bills>((u) => `/api/users/${u}/bills`, 'bills')
export const getCredit = reader<Credit>((u) => `/api/users/${u}/credit`, 'credit')
export const getAlerts = reader<Alerts>((u) => `/api/users/${u}/alerts`, 'alerts')

export async function getForecast(user: string, target?: string): Promise<Forecast | null> {
  if (LIVE) {
    const qs = target ? `?target=${encodeURIComponent(target)}` : ''
    return live<Forecast>(`/api/users/${user}/forecast${qs}`)
  }
  return fixture<Forecast>(user, 'forecast')
}

/**
 * Recent movements. No endpoint in begin.md §7 returns these, so live mode asks
 * for one and shrugs if P3 has not built it yet; mock mode derives it from the
 * persona snapshot, exactly as the web app does.
 */
export async function getActivity(user: string, limit = 8): Promise<Activity> {
  if (LIVE) {
    const got = await live<Activity>(`/api/users/${user}/activity?limit=${limit}`)
    if (got) return got
    return { user, items: [] }
  }

  const snap = fixture<Record<string, any>>(user, 'snapshot')
  if (!snap) return { user, items: [] }

  const items: ActivityItem[] = [
    ...(snap.purchases ?? []).map((p: any) => ({
      id: p.local_id ?? p.id,
      label: p.merchant_name ?? p.description ?? 'Purchase',
      category: p.category ?? p.merchant_category ?? 'spending',
      occurred_at: p.occurred_at ?? p.purchase_date,
      amount: -Math.abs(p.amount),
      kind: 'purchase' as const,
    })),
    ...(snap.deposits ?? []).map((d: any) => ({
      id: d.local_id ?? d.id,
      label: d.description ?? 'Deposit',
      category: d.category ?? 'deposit',
      occurred_at: d.occurred_at ?? d.transaction_date,
      amount: Math.abs(d.amount),
      kind: 'deposit' as const,
    })),
    ...(snap.withdrawals ?? []).map((w: any) => ({
      id: w.local_id ?? w.id,
      label: w.description ?? 'Withdrawal',
      category: w.category ?? 'bill',
      occurred_at: w.occurred_at ?? w.transaction_date,
      amount: -Math.abs(w.amount),
      kind: 'withdrawal' as const,
    })),
    ...(snap.transfers ?? []).map((t: any) => ({
      id: t.local_id ?? t.id,
      label: t.payee_name ?? t.description ?? 'Transfer',
      category: 'transfer',
      occurred_at: t.occurred_at ?? t.transaction_date,
      amount: -Math.abs(t.amount),
      kind: 'transfer' as const,
    })),
  ]

  items.sort((a, b) => (a.occurred_at < b.occurred_at ? 1 : -1))
  return { user, items: items.slice(0, limit) }
}

/**
 * Who the persona is: home city, address, arrival, flight home.
 *
 * Outside begin.md §7. Nessie has all of it on the Customer record and P1
 * exports it in the snapshot, so mock mode reads it from there. Live mode asks
 * P3 for it and renders without it if the endpoint is not there yet.
 */
export async function getProfile(user: string): Promise<Profile | null> {
  if (LIVE) return live<Profile>(`/api/users/${user}/profile`)

  const snap = fixture<Record<string, any>>(user, 'snapshot')
  const customer = snap?.customer
  if (!customer) return null

  let address: Record<string, string> = {}
  try {
    address =
      typeof customer.address === 'string' ? JSON.parse(customer.address) : customer.address ?? {}
  } catch {
    address = {}
  }

  return {
    name: [customer.first_name, customer.last_name].filter(Boolean).join(' '),
    home_city: customer.home_city ?? null,
    city: address.city ?? null,
    state: address.state ?? null,
    language: customer.language ?? null,
    arrival_date: customer.arrival_date ?? null,
    flight_home_date: customer.flight_home_date ?? snap?.flight_home_date ?? null,
  }
}

/**
 * The scam pause, before any money moves.
 *
 * Mock mode answers from the scenario fixtures P1 exported, keyed the same way
 * as `python -m seed.scenarios --list`. legit_roommate is the one that must come
 * back `pause: false` — an engine that stops everything is not a feature.
 */
export async function checkTransfer(body: {
  user?: string
  scenario?: string
  payee_id?: string
  amount?: number
  description?: string
}): Promise<TransferCheck | null> {
  if (LIVE) {
    return live<TransferCheck>('/api/transfers/check', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  }
  return transferFixture<TransferCheck>(body.scenario ?? 'fake_landlord')
}

/**
 * "Can I afford this?"
 *
 * There is no fixture for this: the answer depends on the amount the user types,
 * so it cannot be pre-exported. Without a backend the card says so rather than
 * inventing a number — the same call the web app makes.
 */
export async function checkAffordability(
  user: string,
  amount: number,
  description?: string,
): Promise<Affordability | null> {
  if (!LIVE) return null
  return live<Affordability>(`/api/users/${user}/affordability`, {
    method: 'POST',
    body: JSON.stringify({ amount, description }),
  })
}

export async function chat(body: {
  user?: string
  message: string
  language?: string
}): Promise<ChatReply | null> {
  if (LIVE) {
    return live<ChatReply>('/api/chat', { method: 'POST', body: JSON.stringify(body) })
  }
  return chatFixture<ChatReply>()
}

/**
 * The confirmation gate. begin.md design rule 2: the agent proposes, the user
 * approves, and only then does anything get written to Nessie. Without a
 * backend there is nothing to write to, so mock mode says so rather than
 * pretending the transfer happened.
 */
export async function confirmAction(
  id: string,
  body: Record<string, unknown> = {},
): Promise<ActionResult> {
  if (LIVE) {
    const got = await live<ActionResult>(`/api/actions/${id}/confirm`, {
      method: 'POST',
      body: JSON.stringify(body),
    })
    if (got) return got
    return {
      id,
      status: 'failed',
      message: 'The backend did not accept the action.',
      executed_in_nessie: false,
    }
  }

  const after = chatFixture<ChatReply>()?.proposed_action?.effect?.runway_date_after ?? null
  return {
    id,
    status: 'executed',
    message: 'Approved. Running on fixtures, so nothing was written to Nessie.',
    runway_date_after: after,
    executed_in_nessie: false,
  }
}
