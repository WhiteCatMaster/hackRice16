import Dashboard from '@/components/dashboard'
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
} from '@/lib/api'

// Balances change; nothing here should ever be served from a build-time cache.
export const dynamic = 'force-dynamic'

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ user?: string }>
}) {
  const { user = DEFAULT_USER } = await searchParams

  const [summary, forecast, bills, credit, alerts, activity, profile] = await Promise.all([
    getSummary(user),
    getForecast(user),
    getBills(user),
    getCredit(user),
    getAlerts(user),
    getActivity(user, 8),
    getProfile(user),
  ])

  if (!summary) return <NoData user={user} />

  return (
    <Dashboard
      user={user}
      live={LIVE}
      summary={summary}
      forecast={forecast}
      bills={bills?.bills ?? []}
      credit={credit}
      alerts={alerts?.alerts ?? []}
      activity={activity.items}
      profile={profile}
    />
  )
}

function NoData({ user }: { user: string }) {
  return (
    <main className="setup-notice">
      <p className="eyebrow">NO DATA FOR &ldquo;{user.toUpperCase()}&rdquo;</p>
      <h1>Nothing to show yet.</h1>
      <p>
        {LIVE ? (
          <>
            The backend at <code>{process.env.LANDED_API_BASE}</code> did not answer with a summary
            for this persona.
          </>
        ) : (
          <>
            This screen reads <code>mocks/</code> from the repository root. Generate it once and
            reload:
          </>
        )}
      </p>
      {!LIVE && <pre>python -m seed.reset_demo</pre>}
      <p className="setup-hint">
        Personas: <a href="/?user=ana">ana</a> · <a href="/?user=raj">raj</a> ·{' '}
        <a href="/?user=lucia">lucia</a>
      </p>
    </main>
  )
}
