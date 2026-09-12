// Safety — a pause before you pay.

import { Feather } from '@expo/vector-icons'
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native'

import {
  AlertList,
  ScamSheet,
  TRANSFER_SCENARIOS,
  useTransferCheck,
} from '../../components/safety'
import { Body, Eyebrow, Intro, Panel, PanelHead, Pill, Screen } from '../../components/ui'
import { useLoaded } from '../../lib/store'
import { color, radius, text } from '../../lib/theme'

export default function Safety() {
  const { summary, user, openAlerts, fmt, refreshing, reload } = useLoaded()
  const check = useTransferCheck(user)

  return (
    <>
      <Screen refreshing={refreshing} onRefresh={() => void reload()}>
        <Intro
          eyebrow="SAFETY CENTER"
          title="A pause before you pay"
          body="Every transfer is scored before it leaves. Above the threshold we stop it and tell you exactly what looked wrong."
        />

        <Panel>
          <PanelHead
            eyebrow="OPEN ALERTS"
            title="What we noticed"
            right={
              openAlerts.length > 0 ? (
                <Pill label={`${openAlerts.length} open`} name="flag" />
              ) : (
                <Pill label="all clear" name="teal" />
              )
            }
          />
          <AlertList alerts={openAlerts} asOf={summary.as_of} />
        </Panel>

        <Panel>
          <PanelHead eyebrow="TRY IT" title="Send money" />
          <Body>
            Three transfers, scored by the risk engine before anything moves. The last one has to
            go through — a check that stops everything is not a feature.
          </Body>

          <View style={styles.scenarios}>
            {TRANSFER_SCENARIOS.map((scenario) => {
              const busy = check.busy === scenario.key
              return (
                <Pressable
                  key={scenario.key}
                  accessibilityRole="button"
                  accessibilityLabel={`Send ${fmt(scenario.amount)} to ${scenario.payee}`}
                  accessibilityState={{ busy, disabled: !!check.busy }}
                  disabled={!!check.busy}
                  onPress={() => void check.run(scenario)}
                  style={({ pressed }) => [
                    styles.scenario,
                    pressed && styles.pressed,
                    check.busy && !busy && styles.dimmed,
                  ]}
                >
                  <View style={styles.scenarioCopy}>
                    <Text style={text.label}>{scenario.payee}</Text>
                    <Text style={text.small} numberOfLines={2}>
                      “{scenario.note}”
                    </Text>
                    <Eyebrow style={styles.expect}>{scenario.expect.toUpperCase()}</Eyebrow>
                  </View>
                  <View style={styles.scenarioRight}>
                    <Text style={[text.figure, styles.amount]}>{fmt(scenario.amount)}</Text>
                    {busy ? (
                      <ActivityIndicator size="small" color={color.teal} />
                    ) : (
                      <Feather name="arrow-right" size={15} color={color.inkMute} />
                    )}
                  </View>
                </Pressable>
              )
            })}
          </View>

          {check.status ? (
            <Text accessibilityLiveRegion="polite" style={[text.small, styles.status]}>
              {check.status}
            </Text>
          ) : null}
        </Panel>
      </Screen>

      <ScamSheet check={check.check} onClose={check.clear} />
    </>
  )
}

const styles = StyleSheet.create({
  scenarios: { gap: 10 },
  scenario: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    borderWidth: 1,
    borderColor: color.lineSoft,
    borderRadius: radius.sm,
    padding: 13,
    backgroundColor: color.surface2,
  },
  scenarioCopy: { flex: 1, gap: 4 },
  scenarioRight: { alignItems: 'flex-end', gap: 6 },
  expect: { color: color.inkFaint },
  amount: { fontSize: 14 },
  status: { color: color.inkSoft },
  pressed: { opacity: 0.75 },
  dimmed: { opacity: 0.5 },
})
