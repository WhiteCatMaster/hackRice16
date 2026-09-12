// Overview — the clearest view of the money today.
//
// A straight port of the web app's Overview branch, unstacked. The web grid puts
// balance, runway and safety side by side and the forecast beside the bill list;
// at 390pt wide everything is one column, so the order becomes the hierarchy:
// what is wrong, what you have, where it runs out, who is watching, then the
// picture and the detail.

import { Feather } from '@expo/vector-icons'
import { useRouter } from 'expo-router'
import { useMemo } from 'react'
import { Pressable, StyleSheet, Text, View } from 'react-native'

import { ForecastChart } from '../../components/forecast-chart'
import { Body, Button, Dot, Empty, Eyebrow, Panel, PanelHead, Pill, Screen } from '../../components/ui'
import { dayMonth, daysBetween, longDate, signedMoney, whenLabel } from '../../lib/format'
import { useLoaded } from '../../lib/store'
import { ACTIVITY_TONE, BILL_TONE, color, font, lift, radius, text } from '../../lib/theme'

export default function Overview() {
  const {
    summary,
    forecast,
    bills,
    credit,
    activity,
    profile,
    openAlerts,
    fmt,
    rate,
    currency,
    refreshing,
    reload,
    confirmed,
    setConfirmed,
  } = useLoaded()
  const router = useRouter()

  const checking = summary.accounts.find((a) => a.type === 'Checking')
  const savings = summary.accounts.find((a) => a.type === 'Savings')

  const daysToFlight = daysBetween(summary.as_of, summary.target_date)
  const shortBy = summary.runway_date ? daysBetween(summary.runway_date, summary.target_date) : 0

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
        Math.min(
          100,
          (daysBetween(summary.as_of, summary.runway_date) / Math.max(1, daysToFlight)) * 100,
        ),
      )
    : 100

  return (
    <Screen refreshing={refreshing} onRefresh={() => void reload()}>
      {/* Who this is, and how long they have. */}
      <View style={styles.profile}>
        <Eyebrow>
          FLIGHT HOME · {dayMonth(summary.target_date).toUpperCase()} · {daysToFlight}D
        </Eyebrow>
        <Text style={[text.h1, styles.profileName]}>{summary.name}</Text>
        <Text style={text.small}>
          {profile?.home_city ?? `Home currency ${summary.home_currency}`}
          {profile?.arrival_date ? ` · arrived ${dayMonth(profile.arrival_date)}` : ''}
          {` · 1 ${summary.currency} = ${summary.fx_rate.toFixed(2)} ${summary.home_currency}`}
        </Text>
        {profile?.city ? (
          <View style={styles.stamp}>
            <Text style={styles.stampPlace}>
              {profile.city}, {profile.state}
            </Text>
            <Pill label="verified" name="teal" />
          </View>
        ) : null}
      </View>

      {/* What the copilot just did, if anything. */}
      {confirmed ? (
        <View
          accessibilityLiveRegion="polite"
          style={[styles.strip, confirmed.executed_in_nessie ? styles.stripLive : styles.stripSim]}
        >
          <View style={styles.stripCopy}>
            <Text style={styles.stripTitle}>
              {confirmed.status === 'executed' ? 'Action approved' : 'Action failed'}
            </Text>
            <Text style={text.small}>{confirmed.message}</Text>
            {confirmed.status === 'executed' ? (
              <Text style={[text.small, styles.stripEffect]}>
                {confirmed.runway_date_after
                  ? `New runway date ${dayMonth(confirmed.runway_date_after)}`
                  : 'Your money now lasts past your flight home.'}
              </Text>
            ) : null}
          </View>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Dismiss"
            onPress={() => setConfirmed(null)}
            hitSlop={10}
          >
            <Feather name="x" size={16} color={color.inkMute} />
          </Pressable>
        </View>
      ) : null}

      {/* The headline state of the money, good or bad. */}
      {summary.runway_date ? (
        <View style={[styles.banner, styles.bannerShort]}>
          <View style={[styles.bannerMark, styles.bannerMarkShort]}>
            <Feather name="alert-triangle" size={14} color="#ffffff" />
          </View>
          <View style={styles.bannerCopy}>
            <Text style={[text.h3, styles.bannerTitleShort]}>Runway alert · deficit detected</Text>
            <Text style={[text.small, styles.bannerBodyShort]}>
              Funds deplete {longDate(summary.runway_date).replace(/^\w+, /, '')} ({shortBy} days
              before the flight home)
            </Text>
            <View style={styles.bannerFigures}>
              <View style={styles.bannerFigure}>
                <Eyebrow style={styles.bannerLabelShort}>DAILY BURN</Eyebrow>
                <Text style={[text.figure, styles.bannerValueShort]}>
                  {fmt(summary.daily_burn)} / day
                </Text>
              </View>
              <View style={styles.bannerFigure}>
                <Eyebrow style={styles.bannerLabelShort}>SHORT BY</Eyebrow>
                <Text style={[text.figure, styles.bannerValueShort]}>{fmt(summary.gap)}</Text>
              </View>
            </View>
          </View>
        </View>
      ) : (
        <View style={[styles.banner, styles.bannerClear]}>
          <View style={[styles.bannerMark, styles.bannerMarkClear]}>
            <Feather name="check" size={14} color="#ffffff" />
          </View>
          <View style={styles.bannerCopy}>
            <Text style={[text.h3, styles.bannerTitleClear]}>Runway clear</Text>
            <Text style={[text.small, styles.bannerBodyClear]}>
              The projection stays above the {fmt(summary.safety_buffer)} buffer all the way to{' '}
              {dayMonth(summary.target_date)}.
            </Text>
            <View style={styles.bannerFigure}>
              <Eyebrow style={styles.bannerLabelClear}>DAILY BURN</Eyebrow>
              <Text style={[text.figure, styles.bannerValueClear]}>
                {fmt(summary.daily_burn)} / day
              </Text>
            </View>
          </View>
        </View>
      )}

      <Text style={[text.h1, styles.greeting]}>
        Good morning, {summary.name.split(' ')[0]}.
      </Text>
      <Text style={[text.small, styles.greetingDate]}>
        {longDate(summary.as_of).toUpperCase()}
      </Text>

      {/* Available now. */}
      <Panel style={styles.balancePanel}>
        <View style={styles.balanceTop}>
          <Eyebrow>AVAILABLE NOW</Eyebrow>
          <Feather name="check-circle" size={12} color={color.teal} />
        </View>
        <Text style={styles.account}>
          {(checking?.nickname ?? 'CHECKING').toUpperCase()} ···{(checking?.id ?? '0000').slice(-4)}
        </Text>
        <Text style={[text.figureBig, styles.balance]}>{fmt(checking?.balance ?? 0)}</Text>
        {depositedThisMonth > 0 ? (
          <View style={styles.balanceNote}>
            <Feather name="arrow-up-right" size={12} color={color.teal} />
            <Text style={[text.small, styles.balanceNoteText]}>
              {fmt(depositedThisMonth)} in this month
            </Text>
          </View>
        ) : null}
        <View style={styles.balanceFoot}>
          <Eyebrow>SAVINGS RESERVE</Eyebrow>
          <Text style={text.figure}>{fmt(savings?.balance ?? 0)}</Text>
        </View>
      </Panel>

      {/* Your runway. */}
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Open the runway planner"
        onPress={() => router.push('/runway')}
      >
        <Panel style={styles.runwayPanel}>
          <View style={styles.balanceTop}>
            <Eyebrow>YOUR RUNWAY</Eyebrow>
            <Pill
              label={summary.runway_date ? 'Short' : 'Healthy'}
              name={summary.runway_date ? 'flag' : 'teal'}
            />
          </View>
          <Text style={[text.h2, styles.runwayDate]}>
            {summary.runway_date
              ? `${dayMonth(summary.runway_date)} → ${dayMonth(summary.target_date)}`
              : // Null is the healthy case, which "Past" read as a warning about
                // something overdue rather than as good news.
                `Lasts past ${dayMonth(summary.target_date)}`}
          </Text>
          <Body>
            {summary.runway_date
              ? `You're projected to be short ${fmt(summary.gap)} before your flight home.`
              : 'Your money lasts past the flight home.'}
          </Body>
          <View style={styles.track}>
            <View style={[styles.trackFill, { width: `${runwayProgress}%` }]} />
          </View>
          <View style={styles.trackLabels}>
            <Eyebrow>TODAY</Eyebrow>
            <Eyebrow>FLIGHT HOME</Eyebrow>
          </View>
        </Panel>
      </Pressable>

      {/* Safety check. */}
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Open the safety center"
        onPress={() => router.push('/safety')}
      >
        <Panel style={styles.safetyPanel}>
          <View style={styles.safetyIcon}>
            <Feather
              name={openAlerts.length > 0 ? 'alert-circle' : 'shield'}
              size={16}
              color={openAlerts.length > 0 ? color.flagDeep : color.teal}
            />
          </View>
          <View style={styles.safetyCopy}>
            <Eyebrow>SAFETY CHECK</Eyebrow>
            <Text style={text.h3}>
              {openAlerts.length > 0 ? `${openAlerts.length} to review` : "You're all clear"}
            </Text>
            <Text style={text.small} numberOfLines={2}>
              {openAlerts.length > 0
                ? openAlerts[0].reason
                : 'No unusual activity on this account.'}
            </Text>
          </View>
          <Feather name="arrow-up-right" size={16} color={color.inkMute} />
        </Panel>
      </Pressable>

      {/* The big picture. */}
      <Panel>
        <PanelHead eyebrow="THE BIG PICTURE" title={`Through ${dayMonth(summary.target_date)}`} />
        {forecast ? (
          <ForecastChart forecast={forecast} rate={rate} currency={currency} />
        ) : (
          <Empty title="No forecast available for this persona." />
        )}
        <View style={styles.insight}>
          <Feather name="zap" size={13} color={color.teal} />
          <Text style={[text.small, styles.insightText]}>
            {summary.runway_date
              ? `One move does not close this. The gap is ${fmt(summary.gap)} — open the runway planner for the options the engine measured.`
              : 'Nothing to fix. Spending stays under the buffer all the way to the flight home.'}
          </Text>
        </View>
        <Button label="Ask the copilot" onPress={() => router.push('/copilot')} />
      </Panel>

      {/* Coming up. */}
      <Panel>
        <PanelHead eyebrow="COMING UP" title="Upcoming bills" />
        <View style={styles.list}>
          {bills.slice(0, 3).map((bill) => (
            <View style={styles.row} key={bill.id}>
              <Dot glyph={bill.nickname.charAt(0)} name={BILL_TONE[bill.category] ?? 'teal'} />
              <View style={styles.rowCopy}>
                <Text style={text.label} numberOfLines={1}>
                  {bill.nickname}
                </Text>
                <Text style={text.small}>{dueLabel(bill.next_date, summary.as_of)}</Text>
              </View>
              <Text style={text.figure}>{fmt(bill.amount)}</Text>
            </View>
          ))}
          {bills.length === 0 ? <Empty title="No bills on file." /> : null}
        </View>
        <Button label="View all bills" kind="secondary" onPress={() => router.push('/bills')} />
      </Panel>

      {/* Recently. */}
      <Panel>
        <PanelHead eyebrow="RECENTLY" title="Activity" />
        <View style={styles.list}>
          {activity.slice(0, 5).map((item) => (
            <View style={styles.row} key={item.id}>
              <Dot
                glyph={item.amount > 0 ? '↗' : item.label.charAt(0)}
                name={ACTIVITY_TONE[item.category] ?? 'teal'}
              />
              <View style={styles.rowCopy}>
                <Text style={text.label} numberOfLines={1}>
                  {item.label}
                </Text>
                <Text style={text.small} numberOfLines={1}>
                  {item.category} · {whenLabel(item.occurred_at, summary.as_of)}
                </Text>
              </View>
              <Text style={[text.figure, item.amount > 0 && styles.positive]}>
                {signedMoney(item.amount * rate, currency)}
              </Text>
            </View>
          ))}
          {activity.length === 0 ? (
            <Empty title="No movements cached for this persona." />
          ) : null}
        </View>
      </Panel>

      {/* Building credit. */}
      {credit ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Understand your credit"
          onPress={() => router.push('/credit')}
        >
          <Panel>
            <PanelHead
              eyebrow="BUILDING CREDIT"
              title="Your student card"
              right={<Feather name="arrow-up-right" size={16} color={color.inkMute} />}
            />
            <Body>{credit.tip}</Body>
          </Panel>
        </Pressable>
      ) : null}

      {/* Know before you send. */}
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Know before you send"
        onPress={() => router.push('/safety')}
        style={({ pressed }) => [styles.scamBanner, pressed && styles.pressed]}
      >
        <View style={styles.scamShield}>
          <Feather name="shield" size={15} color={color.flagDeep} />
        </View>
        <View style={styles.safetyCopy}>
          <Text style={[text.h3, styles.scamTitle]}>Know before you send</Text>
          <Text style={[text.small, styles.scamBody]}>
            We pause unusual transfers and tell you, in plain words, what looked wrong.
          </Text>
        </View>
        <Feather name="arrow-right" size={16} color={color.flagDeep} />
      </Pressable>
    </Screen>
  )
}

function dueLabel(next: string, asOf: string): string {
  const days = daysBetween(asOf, next)
  if (days <= 0) return `Due today · ${dayMonth(next)}`
  if (days === 1) return `Due tomorrow · ${dayMonth(next)}`
  return `Due in ${days} days · ${dayMonth(next)}`
}

const styles = StyleSheet.create({
  profile: { gap: 5, paddingBottom: 14, borderBottomWidth: 1, borderBottomColor: color.line },
  profileName: { marginTop: 2 },
  stamp: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 4 },
  stampPlace: { ...text.eyebrow, color: color.inkSoft },

  strip: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
    borderRadius: radius.md,
    borderWidth: 1,
    padding: 14,
  },
  stripLive: { backgroundColor: color.tealTint, borderColor: color.tealLine },
  stripSim: { backgroundColor: color.brassTint, borderColor: color.brassLine },
  stripCopy: { flex: 1, gap: 3 },
  stripTitle: { fontFamily: font.sansSemi, fontSize: 13, color: color.ink },
  stripEffect: { color: color.ink, fontFamily: font.sansMed },

  banner: { flexDirection: 'row', gap: 12, borderRadius: radius.md, borderWidth: 1, padding: 15 },
  bannerShort: { backgroundColor: color.flagTint, borderColor: color.flagLine },
  bannerClear: { backgroundColor: color.tealTint, borderColor: color.tealLine },
  bannerMark: { width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  bannerMarkShort: { backgroundColor: color.flag },
  bannerMarkClear: { backgroundColor: color.teal },
  bannerCopy: { flex: 1, gap: 4 },
  bannerTitleShort: { color: color.flagDeep, fontSize: 16 },
  bannerTitleClear: { color: color.tealDeep, fontSize: 16 },
  bannerBodyShort: { color: color.flagDeep },
  bannerBodyClear: { color: color.tealDeep },
  bannerFigures: { flexDirection: 'row', gap: 24, marginTop: 6 },
  bannerFigure: { gap: 3, marginTop: 6 },
  bannerLabelShort: { color: color.flagDeep, opacity: 0.75 },
  bannerLabelClear: { color: color.tealDeep, opacity: 0.75 },
  bannerValueShort: { color: color.flagDeep, fontSize: 12 },
  bannerValueClear: { color: color.tealDeep, fontSize: 12 },

  greeting: { marginTop: 8, fontSize: 34, lineHeight: 38 },
  greetingDate: { marginTop: -6, marginBottom: 2 },

  balancePanel: { backgroundColor: color.tealTint, borderColor: color.tealLine },
  balanceTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  account: { ...text.eyebrow, color: color.tealDeep, marginTop: -4 },
  balance: { color: color.tealDeep, marginTop: 2 },
  balanceNote: { flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: -6 },
  balanceNoteText: { color: color.tealDeep },
  balanceFoot: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderTopWidth: 1,
    borderTopColor: color.tealLine,
    paddingTop: 12,
  },

  runwayPanel: { backgroundColor: color.paperCard, borderColor: color.line },
  runwayDate: { color: color.ink, marginTop: 2 },
  track: { height: 5, borderRadius: 3, backgroundColor: color.surface, overflow: 'hidden' },
  trackFill: { height: '100%', backgroundColor: color.flag },
  trackLabels: { flexDirection: 'row', justifyContent: 'space-between', marginTop: -6 },

  safetyPanel: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  safetyIcon: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: color.surface2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  safetyCopy: { flex: 1, gap: 3 },

  insight: {
    flexDirection: 'row',
    gap: 10,
    alignItems: 'flex-start',
    backgroundColor: color.surface2,
    borderRadius: radius.sm,
    padding: 13,
  },
  insightText: { flex: 1, color: color.inkSoft },

  list: { gap: 14 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 11 },
  rowCopy: { flex: 1, gap: 3 },
  positive: { color: color.teal },

  scamBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: color.flagTint,
    borderWidth: 1,
    borderColor: color.flagLine,
    borderRadius: radius.md,
    padding: 16,
    ...lift(1),
  },
  scamShield: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: color.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  scamTitle: { color: color.flagDeep, fontSize: 16 },
  scamBody: { color: color.flagDeep, opacity: 0.85 },
  pressed: { opacity: 0.8 },
})
