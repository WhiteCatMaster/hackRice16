// The API contract from begin.md §7 ("Shared contracts"), as types.
//
// Copied verbatim from frontend/lib/contract.ts. Both apps answer to the same
// backend, so both must describe it the same way; `npm run contract:check`
// fails if these two files ever drift apart.
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

/**
 * One thing the user can do about being short, with the effect already
 * measured by the engine. The frontend never computes `effect` — it renders it.
 */
export interface Fix {
  id: string
  type: 'cap_category' | 'transfer' | 'cancel_bill' | string
  label: string
  detail?: string
  amount: number
  /** Whether the engine put this one in its recommended plan. */
  in_plan?: boolean
  /**
   * The whole plan's outcome, not this step's — the identical object on every
   * `in_plan` fix. `effect` always measures the fix alone, so a two-step plan
   * has two steps that each say "still short" and a plan that says "closed".
   * Rendering this per row would re-create the bug it was added to fix: one
   * step advertising the work of two.
   */
  effect_with_plan?: FixEffect
  effect?: FixEffect
}

export interface FixEffect {
  runway_date_before?: string | null
  runway_date_after?: string | null
  /** True when the money now lasts past the flight. Says outright what a
   *  null `runway_date_after` means, so nobody has to infer it. */
  lasts_past_target?: boolean
  /** Days the crossing day moves. Legitimately 0 for a fix that shrinks the
   *  gap without moving the date — the crossing day is a big bill day. */
  days_gained?: number
  gap_before?: number
  gap_after?: number
  min_balance_after?: number
  clears_the_gap?: boolean
}

/**
 * A recurring payment the engine spotted that is deliberately NOT in the
 * projection — money she sends her roommate every month, say. Real and
 * repeating, but not a bill we will commit her to, so it is shown apart.
 */
export interface Detected {
  key: string
  kind: string
  label: string
  amount: number
  cadence: string
  confidence: number
  times_seen: number
  last_seen: string
  category?: string | null
  day_of_month?: number
  interval_days?: number
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
  /** Present from the engine; absent in P1's older fixtures. */
  starting_balance?: number
  safety_buffer?: number
  fixes?: Fix[]
  also_detected?: Detected[]
  /** Fix ids already applied to this projection. */
  applied?: string[]
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
  /** From the engine: whether the projection covers it, and by when. */
  covered?: boolean
  days_away?: number
  usual_amount?: number
  cadence?: string
  times_paid?: number
  payments_left?: number
}

export interface Bills {
  user: string
  bills: Bill[]
  monthly_total?: number
  next_30_days?: number
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
  available?: number
  interest_if_carried?: number
  /** Plain-language answers to "why did my balance go up if I paid it?" */
  explanations?: { title: string; body: string }[]
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
  /** The engine's score and the plain-words signals behind it. */
  risk_score?: number
  signals?: string[]
  purchase_ids?: string[]
}

export interface Alerts {
  user: string
  alerts: Alert[]
}

/** POST /api/transfers/check — the scam pause. */
export interface TransferCheck {
  scenario?: string
  user?: string
  amount: number
  risk_score: number
  pause: boolean
  reasons: string[]
  questions: string[]
  /** PAUSE | ALLOW — the engine's own word for the outcome. */
  verdict?: string
  signals?: string[]
  payee?: string | null
  known_payee?: boolean
  /** Where the runway would land if this went through. */
  runway_date_after?: string | null
}

/**
 * POST /api/users/{id}/affordability — "can I afford this?"
 *
 * The honest answer for someone already short is not "no": it is "not yet,
 * and here is what makes it yes". `if_you_fix_first` is that second half.
 */
export interface Affordability {
  user?: string
  amount: number
  when?: string
  affordable: boolean
  already_short?: boolean
  runway_date_before: string | null
  runway_date_after: string | null
  days_lost?: number
  min_balance_after?: number
  min_balance_date_after?: string | null
  /** The safe number, and the date it holds to. Meaningless apart. */
  max_safe_amount: number
  max_safe_through?: string | null
  /** Largest spend that does not move the runway — real, but not a fix. */
  max_without_moving_runway?: number
  safety_buffer?: number
  gap_after?: number
  if_you_fix_first?: {
    plan: string[]
    max_safe_amount: number
    max_safe_through?: string | null
    runway_date_after?: string | null
    closes_the_gap?: boolean
  } | null
  reason: string
}

export interface ProposedAction {
  id: string
  type: 'transfer' | 'bill_payment' | string
  from?: string
  to?: string
  amount: number
  effect?: {
    runway_date_before?: string | null
    /** Null means she never runs short before the flight — good news, not a blank. */
    runway_date_after?: string | null
    gap_before?: number
    gap_after?: number
    min_balance_after?: number
    /** False when the effect could not be computed. Then a null
     *  `runway_date_after` means "we could not work it out", which is the
     *  opposite of what it means when this is true. */
    measured?: boolean
    measured_note?: string
    /** "backend.engine", or "p3-reference" if it fell back. */
    measured_by?: string
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
