// One load, five tabs.
//
// The web app is a single server-rendered page: every screen is a branch of the
// same component, so one `Promise.all` at the top feeds all of them, and
// `router.refresh()` re-runs it after money moves. Tabs are not branches of one
// render, so that job moves here — fetch once, share through context, and give
// the copilot a `reload()` to call when an action is approved.
//
// The currency toggle lives here for the same reason. On the web it is one
// `useState` in the page component because every figure is inside that
// component; on a phone the figures are spread across five screens, and a
// toggle on the overview that the bills screen ignores is a bug.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

import {
  DEFAULT_USER,
  LIVE,
  getActivity,
  getAlerts,
  getBills,
  getCredit,
  getForecast,
  getProfile,
  getSummary,
} from './api'
import type {
  ActionResult,
  ActivityItem,
  Alert,
  Bill,
  Credit,
  Forecast,
  Profile,
  Summary,
} from './contract'
import { money } from './format'

export const PERSONAS = ['ana', 'raj', 'lucia'] as const

interface Data {
  summary: Summary | null
  forecast: Forecast | null
  bills: Bill[]
  credit: Credit | null
  alerts: Alert[]
  activity: ActivityItem[]
  profile: Profile | null
}

const EMPTY: Data = {
  summary: null,
  forecast: null,
  bills: [],
  credit: null,
  alerts: [],
  activity: [],
  profile: null,
}

interface Store extends Data {
  user: string
  setUser: (user: string) => void
  live: boolean
  loading: boolean
  /** True while a reload runs over data already on screen. */
  refreshing: boolean
  reload: () => Promise<void>

  /** Showing the home currency rather than USD. */
  home: boolean
  setHome: (home: boolean) => void
  /** Every dollar figure on every screen goes through this one. */
  fmt: (amount: number) => string
  rate: number
  currency: string

  /** Open alerts — the badge on the safety tab and the overview card. */
  openAlerts: Alert[]

  /**
   * The last action the user approved in the copilot.
   *
   * It lives up here rather than in the copilot because the copilot closes when
   * the action lands, and the strip announcing what happened belongs on the
   * overview — the screen carrying the runway date that just changed.
   */
  confirmed: ActionResult | null
  setConfirmed: (result: ActionResult | null) => void
}

const StoreContext = createContext<Store | null>(null)

export function StoreProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState(DEFAULT_USER)
  const [data, setData] = useState<Data>(EMPTY)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [home, setHome] = useState(false)
  const [confirmed, setConfirmed] = useState<ActionResult | null>(null)

  // Every load takes a ticket, and only the newest one is allowed to write.
  // Two are in flight whenever someone switches persona while the first is
  // still loading, or pulls to refresh over a switch, and on a phone's network
  // the older request can easily land last: Ana's balances arriving after Raj's
  // and sitting under Raj's name. The seven requests inside one load cannot
  // disagree with each other — they are one `Promise.all` — but two loads can.
  const ticket = useRef(0)

  const load = useCallback(
    async (id: string, quiet: boolean) => {
      const mine = ++ticket.current
      if (quiet) setRefreshing(true)
      else setLoading(true)
      try {
        const [summary, forecast, bills, credit, alerts, activity, profile] = await Promise.all([
          getSummary(id),
          getForecast(id),
          getBills(id),
          getCredit(id),
          getAlerts(id),
          getActivity(id, 8),
          getProfile(id),
        ])
        if (mine !== ticket.current) return
        setData({
          summary,
          forecast,
          bills: bills?.bills ?? [],
          credit,
          alerts: alerts?.alerts ?? [],
          activity: activity.items,
          profile,
        })
      } finally {
        // A superseded load must not clear the flags either: the load that
        // overtook it is still running, and the spinner belongs to that one.
        if (mine === ticket.current) {
          setLoading(false)
          setRefreshing(false)
        }
      }
    },
    [],
  )

  useEffect(() => {
    // A persona switch replaces every figure on screen. Clearing first means the
    // spinner shows instead of Ana's numbers under Raj's name, and the strip
    // about Ana's approved transfer does not survive into Raj's overview.
    setData(EMPTY)
    setConfirmed(null)
    void load(user, false)
  }, [user, load])

  const reload = useCallback(() => load(user, true), [load, user])

  const value = useMemo<Store>(() => {
    const summary = data.summary
    const rate = home && summary ? summary.fx_rate : 1
    const currency = home && summary ? summary.home_currency : (summary?.currency ?? 'USD')
    return {
      ...data,
      user,
      setUser,
      live: LIVE,
      loading,
      refreshing,
      reload,
      home,
      setHome,
      rate,
      currency,
      fmt: (amount: number) => money(amount * rate, currency),
      openAlerts: data.alerts.filter((a) => a.status !== 'resolved'),
      confirmed,
      setConfirmed,
    }
  }, [confirmed, data, home, loading, refreshing, reload, user])

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>
}

export function useStore(): Store {
  const store = useContext(StoreContext)
  if (!store) throw new Error('useStore must be used inside <StoreProvider>')
  return store
}

/**
 * The same, for the screens that cannot render without a summary.
 *
 * Every tab is behind the loading gate in app/(tabs)/_layout.tsx, so by the time
 * a screen renders the summary is there. This narrows the type to say so
 * instead of scattering `summary!` through five files.
 */
export function useLoaded(): Store & { summary: Summary } {
  const store = useStore()
  return store as Store & { summary: Summary }
}
