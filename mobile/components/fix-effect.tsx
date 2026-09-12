// What one fix actually buys you.
//
// Ported line for line from the web app, including the branch order, because
// the order is the correctness argument. Two things read as bugs on screen
// unless the engine is explicit, and it is: `days_gained: 0` means a fix shrinks
// the gap without moving the day she runs out (the crossing day is a big bill
// day), so those show the gap closing rather than "Oct 10 → Oct 10"; and
// `lasts_past_target` states the best outcome there is, instead of leaving it to
// be inferred from a null date.

import { StyleSheet, Text, View } from 'react-native'

import type { Fix } from '../lib/contract'
import { dayMonth } from '../lib/format'
import { color, font, text } from '../lib/theme'

export function FixEffect({
  fix,
  gapBefore,
  fmt,
}: {
  fix: Fix
  gapBefore: number
  fmt: (amount: number) => string
}) {
  const effect = fix.effect
  if (!effect || !('runway_date_after' in effect)) {
    return <Text style={text.figure}>{fmt(fix.amount)}</Text>
  }

  const before = effect.runway_date_before ?? null
  const after = effect.runway_date_after ?? null
  const lastsPast = effect.lasts_past_target ?? after === null
  const gained = effect.days_gained ?? (before === after ? 0 : null)

  // The engine's documented branch order: lasts_past_target, then
  // clears_the_gap, then days_gained, then the gap. Order matters because a fix
  // can gain no days and still be the best outcome there is — that is what
  // happens once the runway already reaches the flight, which is the state this
  // demo is in right after the transfer is approved. Reading days_gained first
  // there inverts the headline, reporting "still short" about a fix that closes
  // it. The two flags coincide in every state we can produce today; following
  // the order anyway costs nothing and does not depend on that.
  const bestOutcome = lastsPast || effect.clears_the_gap === true

  if (!bestOutcome && gained === 0) {
    // The date does not move. Say what does change: how short she still is.
    const from = effect.gap_before ?? gapBefore
    const to = effect.gap_after
    return (
      <View style={styles.wrap}>
        <Text style={text.eyebrow}>STILL SHORT</Text>
        {typeof to === 'number' ? (
          <View style={styles.line}>
            <Text style={[text.figure, styles.struck]}>{fmt(from)}</Text>
            <Text style={[text.figure, styles.value]}>{fmt(to)}</Text>
          </View>
        ) : (
          <Text style={[text.figure, styles.value]}>{fmt(fix.amount)}</Text>
        )}
      </View>
    )
  }

  return (
    <View style={styles.wrap}>
      <Text style={text.eyebrow}>RUNWAY</Text>
      <View style={styles.line}>
        {before ? <Text style={[text.figure, styles.struck]}>{dayMonth(before)}</Text> : null}
        <Text style={[text.figure, styles.value]}>
          {lastsPast || !after ? 'past the flight' : dayMonth(after)}
        </Text>
      </View>
      {typeof gained === 'number' && gained > 0 ? (
        <Text style={styles.gained}>
          +{gained} day{gained === 1 ? '' : 's'}
        </Text>
      ) : null}
    </View>
  )
}

const styles = StyleSheet.create({
  wrap: { alignItems: 'flex-end', gap: 3 },
  line: { flexDirection: 'row', alignItems: 'baseline', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' },
  struck: { color: color.inkFaint, textDecorationLine: 'line-through', fontSize: 11 },
  value: { color: color.ink, fontSize: 12 },
  gained: { fontFamily: font.figureMed, fontSize: 9, letterSpacing: 0.8, color: color.teal },
})
