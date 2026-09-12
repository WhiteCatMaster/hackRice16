// Server-side data access. Two modes, one switch.
//
//   LANDED_API_BASE set    -> call P3's FastAPI, which owns the contract.
//   LANDED_API_BASE unset  -> read P1's fixtures out of mocks/.
//
// begin.md's working agreement is "mocks first: nobody waits for anyone". This
// is that rule in code — the screens are built against mocks/ and the backend
// drops in later by setting one environment variable. Nothing else changes.

import { readFile } from 'node:fs/promises'
import path from 'node:path'

import type {
  Activity,
  ActivityItem,
  Affordability,
  Alerts,
  Bills,
  ChatReply,
  Credit,
  Forecast,
  ActionResult,
  Profile,
  Summary,
  TransferCheck,
} from './contract'

export const API_BASE = process.env.LANDED_API_BASE?.replace(/\/$/, '') ?? ''
export const LIVE = API_BASE !== ''

const MOCKS_DIR =
  process.env.LANDED_MOCKS_DIR ?? path.join(process.cwd(), '..', 'mocks')

export const DEFAULT_USER = process.env.LANDED_USER ?? 'ana'

async function mock<T>(file: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(path.join(MOCKS_DIR, file), 'utf8')) as T
  } catch {
    return null
  }
}

async function live<T>(
  endpoint: string,
  init?: RequestInit,
): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${endpoint}`, {
      ...init,
      headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) },
      cache: 'no-store',
    })
    if (!res.ok) return null
    return (await res.json()) as T
  } catch {
    return null
  }
}

/** GET endpoints: the live backend if there is one, the fixture otherwise. */
function reader<T>(endpoint: (user: string) => string, file: (user: string) => string) {
  return (user: string): Promise<T | null> =>
    LIVE ? live<T>(endpoint(user)) : mock<T>(file(user))
}

export const getSummary = reader<Summary>(
  (u) => `/api/users/${u}/summary`,
  (u) => `api_users_${u}_summary.json`,
)

export const getBills = reader<Bills>(
  (u) => `/api/users/${u}/bills`,
  (u) => `api_users_${u}_bills.json`,
)

export const getCredit = reader<Credit>(
  (u) => `/api/users/${u}/credit`,
  (u) => `api_users_${u}_credit.json`,
)

export const getAlerts = reader<Alerts>(
  (u) => `/api/users/${u}/alerts`,
  (u) => `api_users_${u}_alerts.json`,
)

export async function getForecast(
  user: string,
  target?: string,
): Promise<Forecast | null> {
  if (LIVE) {
    const qs = target ? `?target=${encodeURIComponent(target)}` : ''
    return live<Forecast>(`/api/users/${user}/forecast${qs}`)
  }
  return mock<Forecast>(`api_users_${user}_forecast.json`)
}

/**
 * Recent movements. No endpoint in begin.md §7 returns these, so live mode asks
 * for one and shrugs if P3 has not built it yet; mock mode derives it from the
 * persona snapshot P1 exports.
 */
export async function getActivity(user: string, limit = 6): Promise<Activity> {
  if (LIVE) {
    const got = await live<Activity>(`/api/users/${user}/activity?limit=${limit}`)
    if (got) return got
    return { user, items: [] }
  }

  const snap = await mock<Record<string, any>>(`${user}_snapshot.json`)
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
  const scenario = body.scenario ?? 'fake_landlord'
  return mock<TransferCheck>(`api_transfers_check_${scenario}.json`)
}

/**
 * "Can I afford this?" — the §9 chat beat, as a screen.
 *
 * Every number comes back measured by the engine, including the two that make
 * the answer useful: `max_safe_through` (the date the safe number holds to) and
 * `if_you_fix_first` (what becomes safe once the recommended plan is approved).
 *
 * There is no fixture for this: the answer depends on the amount the user types,
 * so it cannot be pre-exported. Without a backend the card says so rather than
 * inventing a number.
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
    return live<ChatReply>('/api/chat', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  }
  return mock<ChatReply>('api_chat_response.json')
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

  const chatFixture = await mock<ChatReply>('api_chat_response.json')
  const after = chatFixture?.proposed_action?.effect?.runway_date_after ?? null
  return {
    id,
    status: 'executed',
    message: 'Approved. Running on fixtures, so nothing was written to Nessie.',
    runway_date_after: after,
    executed_in_nessie: false,
  }
}

/**
 * Who the persona is: home city, address, arrival, flight home.
 *
 * Also outside begin.md §7. Nessie has all of it on the Customer record and P1
 * exports it in the snapshot, so mock mode reads it from there. Live mode asks
 * P3 for it and renders without it if the endpoint is not there yet.
 */
export async function getProfile(user: string): Promise<Profile | null> {
  if (LIVE) return live<Profile>(`/api/users/${user}/profile`)

  const snap = await mock<Record<string, any>>(`${user}_snapshot.json`)
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
