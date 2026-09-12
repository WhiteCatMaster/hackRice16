// Runway — the projection, what is in it, and what would actually fix it.

import { StyleSheet, Text, View } from 'react-native'

import { AffordabilityCard } from '../../components/affordability'
import { FixEffect } from '../../components/fix-effect'
import { ForecastChart } from '../../components/forecast-chart'
import { Body, Empty, Eyebrow, Intro, Panel, PanelHead, Pill, Screen } from '../../components/ui'
import { dayMonth, runwayLabel, signedMoney } from '../../lib/format'
import { useLoaded } from '../../lib/store'
import { color, font, radius, text } from '../../lib/theme'

export default function Runway() {
  const { summary, forecast, user, live, fmt, rate, currency, refreshing, reload } = useLoaded()

  const checking = summary.accounts.find((a) => a.type === 'Checking')

  return (
    <Screen refreshing={refreshing} onRefresh={() => void reload()}>
      <Intro
        eyebrow="RUNWAY PLANNER"
        title={
          summary.runway_date
            ? `Make it to ${dayMonth(summary.target_date)} with confidence`
            : `You are covered through ${dayMonth(summary.target_date)}`
        }
        body={`Projected day by day from ${fmt(
          checking?.balance ?? 0,
        )} in checking, ${fmt(summary.daily_burn)} a day of variable spending, and every bill and deposit we know about.`}
      />

      {forecast ? (
        <>
          <Panel>
            <PanelHead
              eyebrow="PROJECTED BALANCE"
              title={`${summary.as_of} → ${forecast.target}`}
            />
            <View style={styles.lowest}>
              <Eyebrow>LOWEST POINT</Eyebrow>
              <Text style={text.figure}>
                {fmt(forecast.min_balance)} on {dayMonth(forecast.min_balance_date)}
              </Text>
            </View>
            <ForecastChart forecast={forecast} rate={rate} currency={currency} labelCount={4} />
          </Panel>

          <Panel>
            <PanelHead eyebrow="WHAT THE PROJECTION KNOWS ABOUT" title="Scheduled events" />
            <View style={styles.events}>
              {forecast.events.map((event, i) => (
                <View style={styles.event} key={`${event.date}-${event.label}-${i}`}>
                  <Text style={styles.eventDate}>{dayMonth(event.date)}</Text>
                  <Text style={[text.label, styles.eventLabel]} numberOfLines={2}>
                    {event.label}
                  </Text>
                  <Text style={[text.figure, event.amount > 0 && styles.positive]}>
                    {signedMoney(event.amount * rate, currency)}
                  </Text>
                </View>
              ))}
              {forecast.events.length === 0 ? (
                <Empty title="Nothing scheduled in this window." />
              ) : null}
            </View>
          </Panel>

          {forecast.fixes && forecast.fixes.length > 0 ? (
            <Panel>
              <PanelHead
                eyebrow="WHAT WOULD ACTUALLY FIX IT"
                title="Your options"
                right={
                  <View style={styles.gap}>
                    <Eyebrow>SHORT BY</Eyebrow>
                    <Text style={text.figure}>{fmt(summary.gap)}</Text>
                  </View>
                }
              />

              <PlanBanner forecast={forecast} fmt={fmt} />

              <View style={styles.fixes}>
                {forecast.fixes.map((fix) => (
                  <View
                    key={fix.id}
                    style={[styles.fix, fix.in_plan ? styles.fixRecommended : null]}
                  >
                    <View style={styles.fixCopy}>
                      {fix.in_plan ? <Pill label="in the plan" name="teal" /> : null}
                      <Text style={text.label}>{fix.label}</Text>
                      {fix.detail ? <Text style={text.small}>{fix.detail}</Text> : null}
                    </View>
                    <View style={styles.fixEffect}>
                      <FixEffect fix={fix} gapBefore={summary.gap} fmt={fmt} />
                      {fix.effect?.clears_the_gap ? (
                        <Text style={styles.clears}>closes the gap</Text>
                      ) : null}
                    </View>
                  </View>
                ))}
              </View>
            </Panel>
          ) : null}
        </>
      ) : (
        <Panel>
          <Empty title="No forecast available for this persona." />
        </Panel>
      )}

      <AffordabilityCard user={user} fmt={fmt} live={live} />

      {forecast?.also_detected && forecast.also_detected.length > 0 ? (
        <Panel>
          <PanelHead
            eyebrow="SPOTTED, BUT NOT PROJECTED"
            title="Recurring, and yours to decide"
          />
          <Body>
            These repeat like bills but we have not committed you to them, so they are not in the
            projection above.
          </Body>
          <View style={styles.events}>
            {forecast.also_detected.map((item) => (
              <View style={styles.event} key={item.key}>
                <Text style={styles.eventDate}>{item.cadence}</Text>
                <Text style={[text.label, styles.eventLabel]} numberOfLines={2}>
                  {item.label}
                </Text>
                <Text style={text.figure}>{fmt(item.amount)}</Text>
              </View>
            ))}
          </View>
        </Panel>
      ) : null}
    </Screen>
  )
}

/**
 * The plan's outcome, stated once.
 *
 * Every `in_plan` fix carries the same `effect_with_plan`. A step that claimed
 * it alone would be the exact false claim the field was added to remove — one
 * step advertising the work of two — so it is rendered here, above the list,
 * and nowhere inside it.
 */
function PlanBanner({
  forecast,
  fmt,
}: {
  forecast: NonNullable<ReturnType<typeof useLoaded>['forecast']>
  fmt: (amount: number) => string
}) {
  const plan = (forecast.fixes ?? []).filter((f) => f.in_plan)
  const combined = plan.find((f) => f.effect_with_plan)?.effect_with_plan
  if (plan.length < 2 || !combined) return null

  return (
    <View style={styles.plan}>
      <Eyebrow style={styles.planEyebrow}>THE RECOMMENDED PLAN · {plan.length} STEPS</Eyebrow>
      <Text style={[text.body, styles.planBody]}>
        {combined.clears_the_gap
          ? `Neither step closes the gap by itself. Together they close it, and your money ${runwayLabel(
              combined.runway_date_after,
              'lasts past your flight home',
            )}.`
          : `Neither step closes the gap by itself. Together they bring you to ${fmt(
              combined.gap_after ?? 0,
            )} short.`}
      </Text>
    </View>
  )
}

const styles = StyleSheet.create({
  lowest: { gap: 3, marginTop: -4 },
  gap: { alignItems: 'flex-end', gap: 3 },

  events: { gap: 12 },
  event: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  eventDate: {
    ...text.eyebrow,
    width: 62,
  },
  eventLabel: { flex: 1 },
  positive: { color: color.teal },

  plan: {
    backgroundColor: color.tealTint,
    borderWidth: 1,
    borderColor: color.tealLine,
    borderRadius: radius.sm,
    padding: 14,
    gap: 5,
  },
  planEyebrow: { color: color.tealDeep },
  planBody: { color: color.tealDeep },

  fixes: { gap: 10 },
  fix: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
    borderWidth: 1,
    borderColor: color.lineSoft,
    borderRadius: radius.sm,
    padding: 13,
  },
  fixRecommended: { borderColor: color.tealLine, backgroundColor: color.surface2 },
  fixCopy: { flex: 1, gap: 4, alignItems: 'flex-start' },
  fixEffect: { alignItems: 'flex-end', gap: 4 },
  clears: { fontFamily: font.figureMed, fontSize: 9, letterSpacing: 0.8, color: color.teal },
})
