// The pause, and the alerts behind it.
//
// The pause happens *before* the transfer, which is the whole difference
// between this and a fraud alert that arrives after the money is gone. On a
// phone that reads even more strongly than on the web: the sheet slides up over
// the thing you were about to do.

import { Feather } from '@expo/vector-icons'
import * as Haptics from 'expo-haptics'
import { useCallback, useEffect, useState } from 'react'
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'

import { checkTransfer } from '../lib/api'
import type { Alert, TransferCheck } from '../lib/contract'
import { money, whenLabel } from '../lib/format'
import { color, font, radius, text } from '../lib/theme'
import { Body, Button, Empty, Eyebrow } from './ui'

/** The three transfer cases P1 stages with `python -m seed.scenarios`. */
export const TRANSFER_SCENARIOS = [
  {
    key: 'fake_landlord',
    payee: 'Omaha Property Holdings',
    amount: 800,
    note: 'URGENT apartment deposit - pay today or you lose the place',
    expect: 'Should pause',
  },
  {
    key: 'immigration_fine',
    payee: 'USCIS Processing Center',
    amount: 1200,
    note: 'USCIS processing fine - immediate payment required',
    expect: 'Should pause',
  },
  {
    key: 'legit_roommate',
    payee: 'Marta Aguirre',
    amount: 60,
    note: 'internet share',
    expect: 'Should go through',
  },
] as const

type Scenario = (typeof TRANSFER_SCENARIOS)[number]

export function useTransferCheck(user: string) {
  const [check, setCheck] = useState<(TransferCheck & { payee?: string }) | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [status, setStatus] = useState('')

  const run = useCallback(
    async (scenario: Scenario) => {
      setBusy(scenario.key)
      setStatus(`Checking ${scenario.payee}…`)
      try {
        const data = await checkTransfer({
          user,
          scenario: scenario.key,
          amount: scenario.amount,
          description: scenario.note,
        })
        if (!data) {
          setStatus('Could not verify this transfer right now.')
          return
        }
        setCheck({ ...data, payee: scenario.payee })
        setStatus(
          data.pause
            ? 'Transfer paused before sending — we found a risk signal.'
            : 'This transfer looks normal and can continue.',
        )
        // The stop is the product. Let the phone say so before the sheet does.
        void Haptics.notificationAsync(
          data.pause
            ? Haptics.NotificationFeedbackType.Warning
            : Haptics.NotificationFeedbackType.Success,
        ).catch(() => {})
      } catch {
        setStatus('The risk check failed. Please try again.')
      } finally {
        setBusy(null)
      }
    },
    [user],
  )

  return {
    check,
    busy,
    status,
    run,
    clear: () => {
      setCheck(null)
      setStatus('')
    },
  }
}

export function ScamSheet({
  check,
  onClose,
}: {
  check: (TransferCheck & { payee?: string }) | null
  onClose: () => void
}) {
  const insets = useSafeAreaInsets()
  const [answered, setAnswered] = useState<Record<string, boolean>>({})
  const paused = check?.pause ?? false

  // A new check is a new set of questions. These are things like "were you
  // asked to keep this payment private?", so carrying a tick over from the
  // previous transfer — the two scam scenarios ask two of the same three — is
  // worse than showing no box at all.
  useEffect(() => setAnswered({}), [check])

  return (
    <Modal
      visible={!!check}
      animationType="slide"
      transparent
      onRequestClose={onClose}
      // Announced by the OS when the sheet opens.
      accessibilityViewIsModal
    >
      <Pressable style={styles.backdrop} onPress={onClose} accessibilityLabel="Close" />
      <View style={[styles.sheet, { paddingBottom: insets.bottom + 18 }]}>
        <View style={styles.grabber} />
        {check ? (
          <ScrollView
            contentContainerStyle={styles.sheetBody}
            showsVerticalScrollIndicator={false}
          >
            <View style={[styles.shield, paused ? styles.shieldPaused : styles.shieldClear]}>
              <Feather
                name={paused ? 'alert-triangle' : 'check'}
                size={18}
                color={paused ? color.flagDeep : color.tealDeep}
              />
            </View>

            <Eyebrow>{paused ? 'TRANSFER PAUSED' : 'TRANSFER LOOKS NORMAL'}</Eyebrow>
            <Text style={text.h1}>
              {paused ? 'A pause before you pay' : 'This one looks like you'}
            </Text>
            <Body>
              {money(check.amount)} to {check.payee ?? 'this payee'}.{' '}
              {paused
                ? 'Nothing has left your account. We stopped it before the payment went out.'
                : 'We found nothing unusual, so we are not going to get in your way.'}
            </Body>

            <View style={styles.meter} accessibilityLiveRegion="polite">
              <View style={styles.meterTrack}>
                <View
                  style={[
                    styles.meterFill,
                    { width: `${Math.min(100, Math.max(4, check.risk_score))}%` },
                    paused ? styles.meterHigh : styles.meterLow,
                  ]}
                />
              </View>
              <Text style={text.figure}>{check.risk_score}/100</Text>
            </View>

            <View style={[styles.note, paused ? styles.notePaused : styles.noteClear]}>
              <Text style={[text.small, paused ? styles.noteInkPaused : styles.noteInkClear]}>
                {paused
                  ? 'We recommend cancelling this transfer and confirming the recipient directly.'
                  : 'This payment matches the normal pattern for this account.'}
              </Text>
            </View>

            {check.reasons.map((reason) => (
              <View style={styles.reason} key={reason}>
                <Feather
                  name={paused ? 'alert-circle' : 'check'}
                  size={13}
                  color={paused ? color.flag : color.teal}
                />
                <Text style={[text.label, styles.reasonText]}>{reason}</Text>
              </View>
            ))}

            {check.questions.length > 0 ? (
              <View style={styles.questions}>
                <Eyebrow>BEFORE YOU CONTINUE</Eyebrow>
                {check.questions.map((q) => (
                  <Pressable
                    key={q}
                    accessibilityRole="checkbox"
                    accessibilityState={{ checked: !!answered[q] }}
                    onPress={() => setAnswered((a) => ({ ...a, [q]: !a[q] }))}
                    style={styles.question}
                  >
                    <View style={[styles.box, answered[q] && styles.boxOn]}>
                      {answered[q] ? <Feather name="check" size={11} color="#ffffff" /> : null}
                    </View>
                    <Text style={[text.body, styles.questionText]}>{q}</Text>
                  </Pressable>
                ))}
              </View>
            ) : null}

            <View style={styles.actions}>
              <Button label={paused ? 'Cancel the transfer' : 'Send it'} onPress={onClose} />
              {paused ? (
                <Button
                  label="I verified this myself, send anyway"
                  kind="ghost"
                  onPress={onClose}
                />
              ) : null}
            </View>
          </ScrollView>
        ) : null}
      </View>
    </Modal>
  )
}

export function AlertList({ alerts, asOf }: { alerts: Alert[]; asOf: string }) {
  if (alerts.length === 0) {
    return (
      <Empty
        title="Nothing unusual right now."
        body="No open alerts on this account. We will flag anything suspicious as soon as it appears."
      />
    )
  }
  return (
    <View style={styles.alerts} accessibilityLiveRegion="polite">
      {alerts.map((alert) => (
        <View style={styles.alert} key={alert.id}>
          <View style={styles.alertMark}>
            <Feather name="alert-triangle" size={13} color="#ffffff" />
          </View>
          <View style={styles.alertCopy}>
            <Text style={text.label}>{alert.title}</Text>
            {/* `reason` is already the signals, joined into a sentence. An
                engine-signal chip row under it repeated every word of it and
                ran off the side of the card, so the sentence stands alone —
                the same thing the web app renders. */}
            <Text style={text.small}>{alert.reason}</Text>
            <Text style={[text.small, styles.alertWhen]}>
              {whenLabel(alert.created_at, asOf)}
              {typeof alert.risk_score === 'number' ? ` · risk ${alert.risk_score}/100` : ''}
            </Text>
          </View>
          <Text style={[text.figure, styles.alertAmount]}>{money(alert.amount)}</Text>
        </View>
      ))}
    </View>
  )
}

const styles = StyleSheet.create({
  backdrop: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(15, 27, 40, 0.45)',
  },
  sheet: {
    marginTop: 'auto',
    maxHeight: '90%',
    backgroundColor: color.surface,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    paddingHorizontal: 20,
    paddingTop: 10,
  },
  grabber: {
    alignSelf: 'center',
    width: 38,
    height: 4,
    borderRadius: 2,
    backgroundColor: color.line,
    marginBottom: 14,
  },
  sheetBody: { gap: 11, paddingBottom: 8 },

  shield: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  shieldPaused: { backgroundColor: color.flagTint },
  shieldClear: { backgroundColor: color.tealTint },

  meter: { flexDirection: 'row', alignItems: 'center', gap: 11, marginTop: 4 },
  meterTrack: {
    flex: 1,
    height: 6,
    borderRadius: 3,
    backgroundColor: color.surface2,
    overflow: 'hidden',
  },
  meterFill: { height: '100%', borderRadius: 3 },
  meterHigh: { backgroundColor: color.flag },
  meterLow: { backgroundColor: color.teal },

  note: { borderRadius: radius.sm, padding: 12 },
  notePaused: { backgroundColor: color.flagTint },
  noteClear: { backgroundColor: color.tealTint },
  noteInkPaused: { color: color.flagDeep },
  noteInkClear: { color: color.tealDeep },

  reason: {
    flexDirection: 'row',
    gap: 10,
    alignItems: 'flex-start',
    borderTopWidth: 1,
    borderTopColor: color.lineSoft,
    paddingTop: 11,
  },
  reasonText: { flex: 1, fontFamily: font.sans, lineHeight: 18 },

  questions: { gap: 9, marginTop: 6 },
  question: { flexDirection: 'row', gap: 10, alignItems: 'flex-start' },
  box: {
    width: 18,
    height: 18,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: color.line,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 1,
  },
  boxOn: { backgroundColor: color.teal, borderColor: color.teal },
  questionText: { flex: 1 },

  actions: { gap: 8, marginTop: 10 },

  alerts: { gap: 12 },
  alert: { flexDirection: 'row', gap: 11, alignItems: 'flex-start' },
  alertMark: {
    width: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: color.flag,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 2,
  },
  alertCopy: { flex: 1, gap: 4 },
  alertWhen: { color: color.inkFaint },
  alertAmount: { color: color.flagDeep },
})
