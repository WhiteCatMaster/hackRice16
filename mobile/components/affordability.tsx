// "Can I afford this?" as a screen rather than only a chat turn.
//
// Nothing here is computed on the phone. The engine answers with the number
// *and* the date it holds to — `$47.34 safe` says much less than `$47.34 safe
// through 31 Oct` — and, when she is already short, with the plan that turns a
// no into a yes. Rendering one without the other is what makes the answer
// ambiguous, so this card always shows both halves.

import { useState } from 'react'
import { StyleSheet, Text, TextInput, View } from 'react-native'

import { checkAffordability } from '../lib/api'
import type { Affordability } from '../lib/contract'
import { dayMonth } from '../lib/format'
import { color, font, radius, text } from '../lib/theme'
import { Body, Button, Empty, Eyebrow, Panel, PanelHead, Pill } from './ui'

interface Props {
  user: string
  /** Converts a USD figure into whatever the header is currently showing. */
  fmt: (amount: number) => string
  live: boolean
}

export function AffordabilityCard({ user, fmt, live }: Props) {
  const [amount, setAmount] = useState('')
  const [answer, setAnswer] = useState<Affordability | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function ask() {
    const value = Number(amount)
    // `live` is checked here as well as on the button, because the keyboard's
    // "done" key submits too. Without a backend `checkAffordability` returns
    // null by design, and reporting that as "the engine did not answer"
    // contradicts the card right below, which says why there is no answer.
    if (!live || !Number.isFinite(value) || value <= 0 || busy) return
    setBusy(true)
    setError(null)
    try {
      const got = await checkAffordability(user, value)
      if (!got) throw new Error('The engine did not answer.')
      setAnswer(got)
    } catch (err) {
      setAnswer(null)
      setError(err instanceof Error ? err.message : 'The engine did not answer.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Panel>
      <PanelHead eyebrow="BEFORE YOU SPEND" title="Can I afford it?" />

      <View style={styles.form}>
        <View style={[styles.input, !live && styles.inputOff]}>
          <Text style={styles.currency}>$</Text>
          <TextInput
            value={amount}
            onChangeText={setAmount}
            editable={live}
            keyboardType="decimal-pad"
            returnKeyType="done"
            onSubmitEditing={() => void ask()}
            placeholder="47.34"
            placeholderTextColor={color.inkFaint}
            accessibilityLabel="Amount you want to spend, in dollars"
            style={styles.inputField}
          />
        </View>
        <Button
          label={busy ? 'Checking…' : 'Check'}
          onPress={() => void ask()}
          busy={busy}
          disabled={!live || !amount.trim()}
          style={styles.submit}
        />
      </View>

      {!live ? (
        <Empty
          title="This one needs the engine."
          body="The answer depends on the amount you type, so there is no fixture for it. Start the backend and set EXPO_PUBLIC_TREASURER_API_BASE."
        />
      ) : null}

      {error ? <Text style={styles.error}>{error}</Text> : null}

      {answer ? (
        <View
          accessibilityLiveRegion="polite"
          style={[styles.answer, answer.affordable ? styles.answerYes : styles.answerNo]}
        >
          <Pill
            label={answer.affordable ? 'Yes' : answer.if_you_fix_first ? 'Not yet' : 'No'}
            name={answer.affordable ? 'teal' : 'flag'}
          />

          {/* The engine's own sentence. We quote it; we do not re-template it. */}
          <Body style={styles.reason}>{answer.reason}</Body>

          <View style={styles.figures}>
            <View style={styles.figure}>
              <Eyebrow>SAFE TO SPEND</Eyebrow>
              <Text style={[text.figure, styles.figureValue]}>{fmt(answer.max_safe_amount)}</Text>
              {answer.max_safe_through ? (
                <Text style={text.small}>through {dayMonth(answer.max_safe_through)}</Text>
              ) : null}
            </View>

            {typeof answer.max_without_moving_runway === 'number' &&
            answer.max_without_moving_runway > answer.max_safe_amount ? (
              <View style={styles.figure}>
                <Eyebrow>WITHOUT MOVING YOUR RUNWAY</Eyebrow>
                <Text style={[text.figure, styles.figureValue]}>
                  {fmt(answer.max_without_moving_runway)}
                </Text>
                <Text style={text.small}>does not fix being short</Text>
              </View>
            ) : null}

            <View style={styles.figure}>
              <Eyebrow>RUNWAY</Eyebrow>
              <Text style={[text.figure, styles.figureValue]}>
                {answer.runway_date_before
                  ? dayMonth(answer.runway_date_before)
                  : 'past the flight'}
                {answer.runway_date_after !== answer.runway_date_before
                  ? ` → ${
                      answer.runway_date_after
                        ? dayMonth(answer.runway_date_after)
                        : 'past the flight'
                    }`
                  : ''}
              </Text>
              {typeof answer.days_lost === 'number' && answer.days_lost > 0 ? (
                <Text style={text.small}>
                  {answer.days_lost} day{answer.days_lost === 1 ? '' : 's'} closer
                </Text>
              ) : null}
            </View>
          </View>

          {answer.if_you_fix_first ? (
            <View style={styles.plan}>
              <Eyebrow>IF YOU FIX IT FIRST</Eyebrow>
              {answer.if_you_fix_first.plan.map((step) => (
                <View key={step} style={styles.step}>
                  <Text style={styles.bullet}>—</Text>
                  <Text style={[text.small, styles.stepText]}>{step}</Text>
                </View>
              ))}
              <Text style={[text.small, styles.planEffect]}>
                Then {fmt(answer.if_you_fix_first.max_safe_amount)} is safe
                {answer.if_you_fix_first.max_safe_through
                  ? ` through ${dayMonth(answer.if_you_fix_first.max_safe_through)}`
                  : ''}
                {answer.if_you_fix_first.closes_the_gap ? ' — and the gap is closed.' : '.'}
              </Text>
            </View>
          ) : null}
        </View>
      ) : null}
    </Panel>
  )
}

const styles = StyleSheet.create({
  form: { flexDirection: 'row', gap: 10, alignItems: 'stretch' },
  input: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderWidth: 1,
    borderColor: color.line,
    borderRadius: radius.sm,
    paddingHorizontal: 12,
    backgroundColor: color.surface2,
  },
  inputOff: { opacity: 0.5 },
  currency: { fontFamily: font.figureMed, fontSize: 14, color: color.inkMute },
  inputField: {
    flex: 1,
    paddingVertical: 12,
    fontFamily: font.figureMed,
    fontSize: 15,
    color: color.ink,
  },
  submit: { minWidth: 104 },

  error: { ...text.small, color: color.flagDeep },

  answer: { borderRadius: radius.sm, borderWidth: 1, padding: 14, gap: 12, alignItems: 'flex-start' },
  answerYes: { backgroundColor: color.tealTint, borderColor: color.tealLine },
  answerNo: { backgroundColor: color.flagTint, borderColor: color.flagLine },
  reason: { color: color.ink },

  figures: { gap: 12, alignSelf: 'stretch' },
  figure: { gap: 3 },
  figureValue: { fontSize: 15 },

  plan: {
    alignSelf: 'stretch',
    gap: 6,
    borderTopWidth: 1,
    borderTopColor: color.line,
    paddingTop: 12,
  },
  step: { flexDirection: 'row', gap: 8 },
  bullet: { ...text.small, color: color.inkFaint },
  stepText: { flex: 1, color: color.inkSoft },
  planEffect: { color: color.ink, fontFamily: font.sansMed, marginTop: 4 },
})
