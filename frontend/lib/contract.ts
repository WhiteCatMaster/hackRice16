// The API contract from begin.md §7 ("Shared contracts"), as types.
//
// Every shape here is taken from a file in mocks/, which P1 generates from the
// real dataset. When P3's backend is up it must answer with these same shapes —
// that is the whole point of the contract.

export type PersonaId = 'ana' | 'raj' | 'lucia'

export interface Account {
  id: string
  type: 'Checking' | 'Savings' | 'Credit Card'
  nickname: string
  balance: number
  /** Ours, not Nessie's. Only on the credit card. */
  limit?: number
  utilization?: number
}

export interface Summary {
  user: string
  name: string
  accounts: Account[]
  as_of: string
  /** First day the projected balance falls below the safety buffer. Null = never. */
  runway_date: string | null
  /** The flight home. */
  target_date: string
  gap: number
  safety_buffer: number
  daily_burn: number
  currency: string
  home_currency: string
  fx_rate: number
  /** Fields we simulate because Nessie has no equivalent. */
  _simulated?: string[]
}

export interface ForecastPoint {
  date: string
  balance: number
  events: ForecastEvent[]
}

export interface ForecastEvent {
  date: string
  amount: number
  label: string
}

export interface Forecast {
  user: string
  target: string
  runway_date: string | null
  gap: number
  min_balance: number
  min_balance_date: string
  daily_burn: number
  series: ForecastPoint[]
  events: ForecastEvent[]
}

export interface Bill {
  id: string
  nickname: string
  payee: string
  amount: number
  next_date: string
  recurring_day: number
  category: string
  explanation: string
  /** Set when something is about to change, e.g. a trial converting to paid. */
  heads_up?: string
}

export interface Bills {
  user: string
  bills: Bill[]
}

export interface Credit {
  user: string
  balance: number
  limit: number
  utilization: number
  apr: number
  statement_day: number
  suggested_payment: number
  tip: string
  _simulated?: string[]
  _note?: string
}

export interface Alert {
  id: string
  type: 'scam_transfer' | 'card_anomaly' | string
  severity: 'high' | 'medium' | 'low' | string
  title: string
  amount: number
  reason: string
  created_at: string
  status: 'open' | 'resolved' | string
}

export interface Alerts {
  user: string
  alerts: Alert[]
}

/** POST /api/transfers/check — the scam pause. */
export interface TransferCheck {
  scenario?: string
  amount: number
  risk_score: number
  pause: boolean
  reasons: string[]
  questions: string[]
}

export interface ProposedAction {
  id: string
  type: 'transfer' | 'bill_payment' | string
  from?: string
  to?: string
  amount: number
  effect?: {
    runway_date_before?: string | null
    runway_date_after?: string | null
  }
}

/** POST /api/chat */
export interface ChatReply {
  reply: string
  language?: string
  used_tools?: string[]
  proposed_action?: ProposedAction | null
}

/** POST /api/actions/{id}/confirm */
export interface ActionResult {
  id: string
  status: 'executed' | 'failed' | string
  message: string
  runway_date_after?: string | null
  /** False when the action was simulated locally instead of written to Nessie. */
  executed_in_nessie: boolean
}

/**
 * Recent movements on the account. Not in the begin.md contract — the design
 * needs an "Activity" panel and nothing in §7 returns one. In mock mode we read
 * it out of P1's snapshot; when P3 adds the endpoint this starts using it.
 */
export interface ActivityItem {
  id: string
  label: string
  category: string
  occurred_at: string
  /** Negative for money out, positive for money in. */
  amount: number
  kind: 'purchase' | 'deposit' | 'withdrawal' | 'transfer'
}

export interface Activity {
  user: string
  items: ActivityItem[]
}

/**
 * Persona details for the header. Also not in the §7 contract — it comes off
 * Nessie's Customer record, which P1 already stores.
 */
export interface Profile {
  name: string
  home_city: string | null
  city: string | null
  state: string | null
  language: string | null
  arrival_date: string | null
  flight_home_date: string | null
}
