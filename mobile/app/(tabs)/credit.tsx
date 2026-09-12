// Credit — the student card, explained with her own numbers.

import { StyleSheet, Text, View } from 'react-native'
import Svg, { Circle } from 'react-native-svg'

import { Body, Empty, Eyebrow, Figures, Intro, Panel, PanelHead, Screen } from '../../components/ui'
import { percent } from '../../lib/format'
import { useLoaded } from '../../lib/store'
import { color, font, radius, text } from '../../lib/theme'

export default function CreditScreen() {
  const { credit, fmt, refreshing, reload } = useLoaded()

  return (
    <Screen refreshing={refreshing} onRefresh={() => void reload()}>
      <Intro
        eyebrow="CREDIT BUILDER"
        title="Build your US credit history"
        body="Your student card, explained with your own numbers. No jargon, no score you cannot check."
      />

      {credit ? (
        <>
          <Panel style={styles.ringPanel}>
            <UtilizationRing utilization={credit.utilization} />
            <View style={styles.ringCopy}>
              <Eyebrow>UTILIZATION</Eyebrow>
              <Body>
                {credit.utilization > 0.3
                  ? 'Above 30% is where US scoring models start counting it against you.'
                  : 'Under 30%, which is where US scoring models want it.'}
              </Body>
            </View>
          </Panel>

          <Panel>
            <PanelHead eyebrow="THE NUMBERS" title="Your card, in full" />
            <Figures
              items={[
                { label: 'BALANCE', value: fmt(credit.balance) },
                { label: 'LIMIT', value: fmt(credit.limit) },
                { label: 'UTILIZATION', value: percent(credit.utilization) },
                { label: 'APR', value: `${credit.apr}%` },
                { label: 'STATEMENT DAY', value: String(credit.statement_day) },
                { label: 'SUGGESTED PAYMENT', value: fmt(credit.suggested_payment) },
                ...(typeof credit.available === 'number'
                  ? [{ label: 'AVAILABLE', value: fmt(credit.available) }]
                  : []),
                ...(typeof credit.interest_if_carried === 'number'
                  ? [{ label: 'IF YOU CARRY IT', value: fmt(credit.interest_if_carried) }]
                  : []),
              ]}
            />
          </Panel>

          <Panel>
            <PanelHead eyebrow="WHAT TO DO" title="The one move that matters" />
            <Body>{credit.tip}</Body>
          </Panel>

          {credit.explanations && credit.explanations.length > 0 ? (
            <Panel>
              <PanelHead
                eyebrow="WHY DID THAT HAPPEN?"
                title="The things nobody explains"
              />
              {credit.explanations.map((item) => (
                <View key={item.title} style={styles.explanation}>
                  <Text style={text.h3}>{item.title}</Text>
                  <Body>{item.body}</Body>
                </View>
              ))}
            </Panel>
          ) : null}

          {credit._simulated && credit._simulated.length > 0 ? (
            <View style={styles.simulated}>
              <Eyebrow style={styles.simulatedLabel}>SIMULATED</Eyebrow>
              <Text style={[text.small, styles.simulatedText]}>
                {credit._simulated.join(', ')}.{' '}
                {credit._note ??
                  'Nessie has no credit limit or credit score. These are ours.'}
              </Text>
            </View>
          ) : null}
        </>
      ) : (
        <Panel>
          <Empty
            title="No card on file."
            body="This persona has no credit card in the dataset."
          />
        </Panel>
      )}
    </Screen>
  )
}

/**
 * The ring. Same geometry as the web SVG: a 39-unit radius on a 100-unit box,
 * rotated a quarter turn so it fills clockwise from twelve o'clock.
 */
function UtilizationRing({ utilization }: { utilization: number }) {
  const size = 118
  const radius = 39
  const circumference = 2 * Math.PI * radius
  const filled = Math.min(1, Math.max(0, utilization)) * circumference
  const high = utilization > 0.3

  return (
    <View
      style={[styles.ring, { width: size, height: size }]}
      accessibilityRole="image"
      accessibilityLabel={`${percent(utilization)} of the limit used`}
    >
      <Svg width={size} height={size} viewBox="0 0 100 100">
        <Circle cx="50" cy="50" r={radius} fill="none" stroke={color.lineSoft} strokeWidth="8" />
        <Circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          stroke={high ? color.flag : color.teal}
          strokeWidth="8"
          strokeDasharray={`${filled.toFixed(1)} ${circumference.toFixed(1)}`}
          strokeLinecap="round"
          transform="rotate(-90 50 50)"
        />
      </Svg>
      <View style={styles.ringCentre}>
        <Text style={[text.figure, styles.ringValue, high && styles.ringValueHigh]}>
          {percent(utilization)}
        </Text>
        <Text style={styles.ringUnit}>utilized</Text>
      </View>
    </View>
  )
}

const styles = StyleSheet.create({
  ringPanel: { flexDirection: 'row', alignItems: 'center', gap: 16 },
  ring: { alignItems: 'center', justifyContent: 'center' },
  ringCentre: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    alignItems: 'center',
    justifyContent: 'center',
  },
  ringValue: { fontSize: 22, color: color.teal },
  ringValueHigh: { color: color.flag },
  ringUnit: { fontFamily: font.figure, fontSize: 9, letterSpacing: 0.6, color: color.inkMute },
  ringCopy: { flex: 1, gap: 5 },

  explanation: { gap: 5 },

  simulated: {
    backgroundColor: color.brassTint,
    borderWidth: 1,
    borderColor: color.brassLine,
    borderRadius: radius.sm,
    padding: 13,
    gap: 4,
  },
  simulatedLabel: { color: color.brass },
  simulatedText: { color: color.brass },
})
