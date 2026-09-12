'use client'

import { useMemo, useState } from 'react'

import { ForecastChart } from './forecast-chart'
import { Copilot } from './copilot'
import { AlertList, ScamModal, TRANSFER_SCENARIOS, useTransferCheck } from './safety'
import type {
  ActionResult,
  ActivityItem,
  Alert,
  Bill,
  Credit,
  Forecast,
  Profile,
  Summary,
} from '@/lib/contract'
import {
  dayMonth,
  daysBetween,
  longDate,
  money,
  moneyRound,
  percent,
  signedMoney,
  whenLabel,
} from '@/lib/format'

type View = 'Overview' | 'Runway' | 'Bills' | 'Credit' | 'Safety'

const NAV: { view: View; icon: string }[] = [
  { view: 'Overview', icon: '◌' },
  { view: 'Runway', icon: '↗' },
  { view: 'Bills', icon: '▣' },
  { view: 'Credit', icon: '◒' },
]

const BILL_TONE: Record<string, string> = {
  housing: 'lavender',
  insurance: 'peach',
  phone: 'mint',
  fitness: 'mint',
  subscription: 'lavender',
  credit_card: 'peach',
}

const ACTIVITY_TONE: Record<string, string> = {
  groceries: 'green',
  dining: 'orange',
  coffee: 'orange',
  deposit: 'blue',
  family: 'blue',
  transfer: 'blue',
}

interface Props {
  user: string
  live: boolean
  summary: Summary
  forecast: Forecast | null
  bills: Bill[]
  credit: Credit | null
  alerts: Alert[]
  activity: ActivityItem[]
  profile: Profile | null
}

export default function Dashboard({
  user,
  live,
  summary,
  forecast,
  bills,
  credit,
  alerts,
  activity,
  profile,
}: Props) {
  const [view, setView] = useState<View>('Overview')
  const [home, setHome] = useState(false)
  const [copilot, setCopilot] = useState(false)
  const [confirmed, setConfirmed] = useState<ActionResult | null>(null)
  const check = useTransferCheck(user)

  // Every dollar figure on screen goes through these two.
  const rate = home ? summary.fx_rate : 1
  const code = home ? summary.home_currency : summary.currency
  const fmt = (amount: number) => money(amount * rate, code)

  const checking = summary.accounts.find((a) => a.type === 'Checking')
  const savings = summary.accounts.find((a) => a.type === 'Savings')
  const card = summary.accounts.find((a) => a.type === 'Credit Card')

  const daysToFlight = daysBetween(summary.as_of, summary.target_date)
  const shortBy = summary.runway_date ? daysBetween(summary.runway_date, summary.target_date) : 0
  const openAlerts = alerts.filter((a) => a.status !== 'resolved')

  const depositedThisMonth = useMemo(
    () =>
      activity
        .filter((i) => i.amount > 0 && i.occurred_at.slice(0, 7) === summary.as_of.slice(0, 7))
        .reduce((total, i) => total + i.amount, 0),
    [activity, summary.as_of],
  )

  // How far through the run to the flight home we are. Drives the little bar on
  // the runway card.
  const runwayProgress = summary.runway_date
    ? Math.max(
        0,
        Math.min(100, (daysBetween(summary.as_of, summary.runway_date) / Math.max(1, daysToFlight)) * 100),
      )
    : 100

  const upcoming = bills.slice(0, 3)

  return (
    <main className="landed-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">L</span>
          <span>landed</span>
        </div>
        <div className="workspace-label">YOUR MONEY, MADE CLEAR</div>
        <nav className="side-nav" aria-label="Main navigation">
          {NAV.map(({ view: item, icon }) => (
            <button
              key={item}
              className={view === item ? 'nav-item active' : 'nav-item'}
              onClick={() => setView(item)}
            >
              <span className="nav-icon">{icon}</span>
              {item}
            </button>
          ))}
        </nav>
        <div className="sidebar-rule" />
        <button
          className={view === 'Safety' ? 'nav-item active' : 'nav-item'}
          onClick={() => setView('Safety')}
        >
          <span className="nav-icon">!</span>Safety center
          {openAlerts.length > 0 && <span className="nav-dot" />}
        </button>

        <div className="sidebar-bottom">
          <div className="support-card">
            <div className="support-kicker">NEED A HAND?</div>
            <p>Ask your financial copilot anything.</p>
            <button onClick={() => setCopilot(true)}>
              Open assistant <span>↗</span>
            </button>
          </div>
          <div className="profile">
            <div className="avatar">{initials(summary.name)}</div>
            <div>
              <strong>{summary.name}</strong>
              <span>{profile?.home_city ?? summary.home_currency}</span>
            </div>
            <PersonaSwitch current={user} />
          </div>
        </div>
      </aside>

      <section className="main-content">
        <header className="topbar">
          <div className="ledger-brand">
            LANDED <span>· FIELD LEDGER</span>
          </div>
          <div className="nessie-status">
            <span className={`status-dot ${live ? '' : 'fixture'}`} />
            {live ? (
              <>
                LIVE BACKEND <strong>NESSIE-BACKED</strong>
              </>
            ) : (
              <>
                RUNNING ON FIXTURES <strong>mocks/ · as of {summary.as_of}</strong>
              </>
            )}
          </div>
          <div className="top-actions">
            <button className="currency-link" onClick={() => setHome(!home)}>
              {summary.currency} <span>↔</span> {summary.home_currency}
            </button>
            <button
              className="icon-button"
              aria-label={`Alerts (${openAlerts.length})`}
              onClick={() => setView('Safety')}
            >
              ♧{openAlerts.length > 0 && <i />}
            </button>
            <button className="help-button" onClick={() => setCopilot(true)}>
              Copilot <span>↗</span>
            </button>
          </div>
        </header>

        <div className="content-inner">
          <div className="reference-profile">
            <div>
              <span className="eyebrow">
                FLIGHT HOME · {dayMonth(summary.target_date).toUpperCase()} · {daysToFlight}D
              </span>
              <h2>{summary.name}</h2>
              <p>
                {profile?.home_city ?? `Home currency ${summary.home_currency}`}
                {profile?.arrival_date && <> · arrived {dayMonth(profile.arrival_date)}</>}
                {' · '}1 {summary.currency} = {(summary.fx_rate).toFixed(2)} {summary.home_currency}
              </p>
            </div>
            {profile?.city && (
              <div className="location-stamp">
                {profile.city}, {profile.state} <span>verified</span>
              </div>
            )}
          </div>

          {summary.runway_date ? (
            <div className="runway-alert">
              <span className="alert-mark">!</span>
              <div>
                <strong>Runway Alert · Deficit Detected</strong>
                <p>
                  Funds deplete {longDate(summary.runway_date).replace(/^\w+, /, '')}{' '}
                  <em>({shortBy} days before the flight home)</em>
                </p>
              </div>
              <div className="burn-rate">
                <span>Daily burn</span>
                <strong>{fmt(summary.daily_burn)} / day</strong>
              </div>
              <div className="critical-status">
                SHORT BY
                <strong>{fmt(summary.gap)}</strong>
              </div>
            </div>
          ) : (
            <div className="runway-alert healthy">
              <span className="alert-mark">✓</span>
              <div>
                <strong>Runway clear</strong>
                <p>
                  The projection stays above the {fmt(summary.safety_buffer)} buffer all the way to{' '}
                  {dayMonth(summary.target_date)}.
                </p>
              </div>
              <div className="burn-rate">
                <span>Daily burn</span>
                <strong>{fmt(summary.daily_burn)} / day</strong>
              </div>
            </div>
          )}

          <div className="page-intro">
            <div>
              <p className="eyebrow">{longDate(summary.as_of).toUpperCase()}</p>
              <h1>Good morning, {summary.name.split(' ')[0]}.</h1>
              <p className="intro-copy">Here&apos;s the clearest view of your money today.</p>
            </div>
            <div className="currency-toggle" role="group" aria-label="Currency">
              <button className={!home ? 'selected' : ''} onClick={() => setHome(false)}>
                {summary.currency}
              </button>
              <button className={home ? 'selected' : ''} onClick={() => setHome(true)}>
                {summary.home_currency}
              </button>
            </div>
          </div>

          {confirmed && (
            <div className={`confirm-strip ${confirmed.executed_in_nessie ? 'live' : 'simulated'}`}>
              <strong>{confirmed.status === 'executed' ? 'Action approved' : 'Action failed'}</strong>
              <span>{confirmed.message}</span>
              {confirmed.runway_date_after && (
                <span>
                  New runway date <strong>{dayMonth(confirmed.runway_date_after)}</strong>
                </span>
              )}
              <button className="ghost-button" onClick={() => setConfirmed(null)}>
                Dismiss
              </button>
            </div>
          )}

          {view === 'Overview' && (
            <>
              <div className="summary-grid">
                <article className="balance-card">
                  <div className="card-label">
                    AVAILABLE NOW <span className="verified-check">✓</span>
                  </div>
                  <div className="reference-account">
                    {(checking?.nickname ?? 'CHECKING').toUpperCase()} ···
                    {(checking?.id ?? '0000').slice(-4)}
                  </div>
                  <div className="balance">{fmt(checking?.balance ?? 0)}</div>
                  {depositedThisMonth > 0 && (
                    <div className="balance-note">
                      <span className="up-arrow">↗</span> {fmt(depositedThisMonth)} in this month
                    </div>
                  )}
                  <div className="balance-footer">
                    <span>Savings reserve</span>
                    <span className="card-number">{fmt(savings?.balance ?? 0)}</span>
                  </div>
                </article>

                <article className="runway-card">
                  <div className="card-topline">
                    <div className="card-label">YOUR RUNWAY</div>
                    <span className={`healthy-pill ${summary.runway_date ? 'short' : ''}`}>
                      {summary.runway_date ? 'Short' : 'Healthy'}
                    </span>
                  </div>
                  <div className="runway-date">
                    {summary.runway_date ? dayMonth(summary.runway_date) : 'Past'} <span>→</span>{' '}
                    {dayMonth(summary.target_date)}
                  </div>
                  <p>
                    {summary.runway_date ? (
                      <>
                        You&apos;re projected to be short <strong>{fmt(summary.gap)}</strong> before your
                        flight home.
                      </>
                    ) : (
                      <>Your money lasts past the flight home.</>
                    )}
                  </p>
                  <div className="runway-progress">
                    <span style={{ width: `${runwayProgress}%` }} />
                  </div>
                  <div className="progress-labels">
                    <span>Today</span>
                    <span>Flight home</span>
                  </div>
                </article>

                <article className="safety-card">
                  <div className="safety-icon">{openAlerts.length > 0 ? '!' : '✦'}</div>
                  <div>
                    <div className="card-label">SAFETY CHECK</div>
                    <div className="safety-title">
                      {openAlerts.length > 0 ? `${openAlerts.length} to review` : "You're all clear"}
                    </div>
                    <p>
                      {openAlerts.length > 0
                        ? openAlerts[0].reason
                        : 'No unusual activity on this account.'}
                    </p>
                  </div>
                  <button className="arrow-button" onClick={() => setView('Safety')} aria-label="Safety center">
                    ↗
                  </button>
                </article>
              </div>

              <div className="main-grid">
                <section className="forecast-panel panel">
                  <div className="panel-header">
                    <div>
                      <p className="eyebrow">THE BIG PICTURE</p>
                      <h2>Your money, through {dayMonth(summary.target_date)}</h2>
                    </div>
                    <button className="text-button" onClick={() => setView('Runway')}>
                      View full forecast <span>↗</span>
                    </button>
                  </div>
                  {forecast ? (
                    <ForecastChart forecast={forecast} rate={rate} currency={code} />
                  ) : (
                    <p className="empty-note">No forecast available for this persona.</p>
                  )}
                  <div className="forecast-insight">
                    <span className="insight-spark">✦</span>
                    <p>
                      {summary.runway_date ? (
                        <>
                          <strong>One move does not close this.</strong> The gap is{' '}
                          {fmt(summary.gap)}: moving {moneyRound(300 * rate, code)} from savings gets
                          you most of the way, and a weekly dining cap covers the rest.
                        </>
                      ) : (
                        <>
                          <strong>Nothing to fix.</strong> Spending stays under the buffer all the way
                          to the flight home.
                        </>
                      )}
                    </p>
                    <button className="primary-button" onClick={() => setCopilot(true)}>
                      Ask the copilot <span>→</span>
                    </button>
                  </div>
                </section>

                <aside className="right-column">
                  <section className="panel upcoming-panel">
                    <div className="panel-header">
                      <div>
                        <p className="eyebrow">COMING UP</p>
                        <h2>Upcoming bills</h2>
                      </div>
                      <button className="more-button" onClick={() => setView('Bills')} aria-label="All bills">
                        ···
                      </button>
                    </div>
                    <div className="bill-list">
                      {upcoming.map((bill) => (
                        <div className="bill-row" key={bill.id}>
                          <div className={`bill-icon ${BILL_TONE[bill.category] ?? 'mint'}`}>
                            {bill.nickname.charAt(0)}
                          </div>
                          <div className="bill-info">
                            <strong>{bill.nickname}</strong>
                            <span>{dueLabel(bill.next_date, summary.as_of)}</span>
                          </div>
                          <strong className="bill-amount">{fmt(bill.amount)}</strong>
                        </div>
                      ))}
                    </div>
                    <button className="secondary-button" onClick={() => setView('Bills')}>
                      View all bills <span>→</span>
                    </button>
                  </section>

                  <section className="panel activity-panel">
                    <div className="panel-header">
                      <div>
                        <p className="eyebrow">RECENTLY</p>
                        <h2>Activity</h2>
                      </div>
                    </div>
                    <div className="activity-list">
                      {activity.slice(0, 4).map((item) => (
                        <div className="activity-row" key={item.id}>
                          <div className={`activity-icon ${ACTIVITY_TONE[item.category] ?? 'green'}`}>
                            {item.amount > 0 ? '↗' : item.label.charAt(0)}
                          </div>
                          <div className="activity-info">
                            <strong>{item.label}</strong>
                            <span>
                              {item.category} · {whenLabel(item.occurred_at, summary.as_of)}
                            </span>
                          </div>
                          <strong className={item.amount > 0 ? 'positive' : ''}>
                            {signedMoney(item.amount * rate, code)}
                          </strong>
                        </div>
                      ))}
                      {activity.length === 0 && (
                        <p className="empty-note">No movements cached for this persona.</p>
                      )}
                    </div>
                  </section>
                </aside>
              </div>

              <section className="bottom-row">
                {credit && (
                  <div className="credit-card panel">
                    <div>
                      <p className="eyebrow">BUILDING CREDIT</p>
                      <h2>Your student card</h2>
                      <p className="credit-copy">{credit.tip}</p>
                      <button className="text-button" onClick={() => setView('Credit')}>
                        Understand your credit <span>↗</span>
                      </button>
                    </div>
                    <UtilizationRing utilization={credit.utilization} />
                  </div>
                )}
                <button className="scam-banner" onClick={() => setView('Safety')}>
                  <span className="shield">!</span>
                  <span>
                    <strong>Know before you send</strong>
                    <small>
                      We pause unusual transfers and tell you, in plain words, what looked wrong.
                    </small>
                  </span>
                  <span className="banner-arrow">→</span>
                </button>
              </section>
            </>
          )}

          {view === 'Runway' && forecast && (
            <>
              <ViewHeader
                eyebrow="RUNWAY PLANNER"
                title={
                  summary.runway_date
                    ? `Make it to ${dayMonth(summary.target_date)} with confidence`
                    : `You are covered through ${dayMonth(summary.target_date)}`
                }
                body={`Projected day by day from ${fmt(checking?.balance ?? 0)} in checking, ${fmt(
                  summary.daily_burn,
                )} a day of variable spending, and every bill and deposit we know about.`}
                onBack={() => setView('Overview')}
              />
              <section className="panel forecast-panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">PROJECTED BALANCE</p>
                    <h2>
                      {summary.as_of} → {forecast.target}
                    </h2>
                  </div>
                  <div className="stat-inline">
                    <span>Lowest point</span>
                    <strong>
                      {fmt(forecast.min_balance)} on {dayMonth(forecast.min_balance_date)}
                    </strong>
                  </div>
                </div>
                <ForecastChart forecast={forecast} rate={rate} currency={code} labelCount={6} />
              </section>

              <section className="panel event-panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">WHAT THE PROJECTION KNOWS ABOUT</p>
                    <h2>Scheduled events</h2>
                  </div>
                </div>
                <div className="event-list">
                  {forecast.events.map((event, i) => (
                    <div className="event-row" key={`${event.date}-${event.label}-${i}`}>
                      <span className="event-date">{dayMonth(event.date)}</span>
                      <strong>{event.label}</strong>
                      <span className={event.amount > 0 ? 'positive' : 'event-amount'}>
                        {signedMoney(event.amount * rate, code)}
                      </span>
                    </div>
                  ))}
                </div>
              </section>
            </>
          )}

          {view === 'Bills' && (
            <>
              <ViewHeader
                eyebrow="BILL DECODER"
                title="Stay ahead of every payment"
                body="What each bill is, when it leaves your account, and what US-specific thing about it is likely to catch you out."
                onBack={() => setView('Overview')}
              />
              <div className="bill-cards">
                {bills.map((bill) => (
                  <article className="panel bill-card" key={bill.id}>
                    <header>
                      <div className={`bill-icon ${BILL_TONE[bill.category] ?? 'mint'}`}>
                        {bill.nickname.charAt(0)}
                      </div>
                      <div>
                        <strong>{bill.nickname}</strong>
                        <span>{bill.payee}</span>
                      </div>
                      <div className="bill-amount-block">
                        <strong>{fmt(bill.amount)}</strong>
                        <span>{dueLabel(bill.next_date, summary.as_of)}</span>
                      </div>
                    </header>
                    <p>{bill.explanation}</p>
                    {bill.heads_up && (
                      <p className="heads-up">
                        <span>!</span> {bill.heads_up}
                      </p>
                    )}
                  </article>
                ))}
                {bills.length === 0 && <p className="empty-note">No bills on file.</p>}
              </div>
            </>
          )}

          {view === 'Credit' && credit && (
            <>
              <ViewHeader
                eyebrow="CREDIT BUILDER"
                title="Build your US credit history"
                body="Your student card, explained with your own numbers. No jargon, no score you cannot check."
                onBack={() => setView('Overview')}
              />
              <section className="panel credit-detail">
                <div className="credit-figures">
                  <div>
                    <p className="eyebrow">BALANCE</p>
                    <strong>{fmt(credit.balance)}</strong>
                  </div>
                  <div>
                    <p className="eyebrow">LIMIT</p>
                    <strong>{fmt(credit.limit)}</strong>
                  </div>
                  <div>
                    <p className="eyebrow">UTILIZATION</p>
                    <strong>{percent(credit.utilization)}</strong>
                  </div>
                  <div>
                    <p className="eyebrow">APR</p>
                    <strong>{credit.apr}%</strong>
                  </div>
                  <div>
                    <p className="eyebrow">STATEMENT DAY</p>
                    <strong>{credit.statement_day}</strong>
                  </div>
                  <div>
                    <p className="eyebrow">SUGGESTED PAYMENT</p>
                    <strong>{fmt(credit.suggested_payment)}</strong>
                  </div>
                </div>
                <UtilizationRing utilization={credit.utilization} />
              </section>
              <p className="credit-copy">{credit.tip}</p>
              {credit._simulated && credit._simulated.length > 0 && (
                <p className="simulated-note">
                  <strong>Simulated:</strong> {credit._simulated.join(', ')}.{' '}
                  {credit._note ?? 'Nessie has no credit limit or credit score. These are ours.'}
                </p>
              )}
            </>
          )}

          {view === 'Safety' && (
            <>
              <ViewHeader
                eyebrow="SAFETY CENTER"
                title="A pause before you pay"
                body="Every transfer is scored before it leaves. Above the threshold we stop it and tell you exactly what looked wrong."
                onBack={() => setView('Overview')}
              />
              <section className="panel safety-panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">OPEN ALERTS</p>
                    <h2>What we noticed</h2>
                  </div>
                </div>
                <AlertList alerts={openAlerts} asOf={summary.as_of} />
              </section>

              <section className="panel safety-panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">TRY IT</p>
                    <h2>Send money</h2>
                  </div>
                </div>
                <p className="panel-copy">
                  Three transfers, scored by the risk engine before anything moves. The last one has
                  to go through — a check that stops everything is not a feature.
                </p>
                <div className="scenario-list">
                  {TRANSFER_SCENARIOS.map((scenario) => (
                    <button
                      key={scenario.key}
                      className="scenario-row"
                      onClick={() => check.run(scenario)}
                      disabled={check.busy}
                    >
                      <div className="scenario-info">
                        <strong>{scenario.payee}</strong>
                        <span>&ldquo;{scenario.note}&rdquo;</span>
                      </div>
                      <span className="scenario-expect">{scenario.expect}</span>
                      <strong className="scenario-amount">{fmt(scenario.amount)}</strong>
                    </button>
                  ))}
                </div>
              </section>
            </>
          )}
        </div>
      </section>

      {check.check && <ScamModal check={check.check} onClose={check.clear} />}
      <Copilot
        user={user}
        open={copilot}
        onClose={() => setCopilot(false)}
        onActionConfirmed={(result) => {
          setConfirmed(result)
          setCopilot(false)
        }}
      />
    </main>
  )
}

function ViewHeader({
  eyebrow,
  title,
  body,
  onBack,
}: {
  eyebrow: string
  title: string
  body: string
  onBack: () => void
}) {
  return (
    <section className="section-switcher panel">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h2>{title}</h2>
        <p>{body}</p>
      </div>
      <button className="secondary-button" onClick={onBack}>
        Back to overview <span>→</span>
      </button>
    </section>
  )
}

function UtilizationRing({ utilization }: { utilization: number }) {
  const radius = 39
  const circumference = 2 * Math.PI * radius
  const filled = Math.min(1, Math.max(0, utilization)) * circumference
  return (
    <div className="credit-ring">
      <svg viewBox="0 0 100 100">
        <circle cx="50" cy="50" r={radius} fill="none" stroke="#e8d6cd" strokeWidth="8" />
        <circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          stroke={utilization > 0.3 ? '#9f3c16' : '#3a674f'}
          strokeWidth="8"
          strokeDasharray={`${filled.toFixed(1)} ${circumference.toFixed(1)}`}
          strokeLinecap="round"
          transform="rotate(-90 50 50)"
        />
      </svg>
      <div>
        <strong>{percent(utilization)}</strong>
        <span>utilized</span>
      </div>
    </div>
  )
}

/** The other two personas are there to show the forecast is not hard-coded. */
function PersonaSwitch({ current }: { current: string }) {
  const others = ['ana', 'raj', 'lucia'].filter((p) => p !== current)
  return (
    <div className="persona-switch">
      {others.map((p) => (
        <a key={p} href={`/?user=${p}`} title={`Open ${p}`}>
          {p.charAt(0).toUpperCase()}
        </a>
      ))}
    </div>
  )
}

function initials(name: string): string {
  return name
    .split(' ')
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join('')
}

function dueLabel(next: string, asOf: string): string {
  const days = daysBetween(asOf, next)
  if (days <= 0) return `Due today · ${dayMonth(next)}`
  if (days === 1) return `Due tomorrow · ${dayMonth(next)}`
  return `Due in ${days} days · ${dayMonth(next)}`
}
