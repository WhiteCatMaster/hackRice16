// Bills — what each one is, when it leaves, and what will catch you out.

import { Feather } from '@expo/vector-icons'
import { StyleSheet, Text, View } from 'react-native'

import { Body, Dot, Empty, Eyebrow, Intro, Panel, Screen } from '../../components/ui'
import { dayMonth, daysBetween } from '../../lib/format'
import { useLoaded } from '../../lib/store'
import { BILL_TONE, color, font, radius, text } from '../../lib/theme'

export default function Bills() {
  const { summary, bills, fmt, refreshing, reload } = useLoaded()

  const next30 = bills
    .filter((b) => daysBetween(summary.as_of, b.next_date) <= 30)
    .reduce((total, b) => total + b.amount, 0)

  return (
    <Screen refreshing={refreshing} onRefresh={() => void reload()}>
      <Intro
        eyebrow="BILL DECODER"
        title="Stay ahead of every payment"
        body="What each bill is, when it leaves your account, and what US-specific thing about it is likely to catch you out."
      />

      {bills.length > 0 ? (
        <View style={styles.totals}>
          <View style={styles.total}>
            <Eyebrow>ON FILE</Eyebrow>
            <Text style={[text.figure, styles.totalValue]}>{bills.length}</Text>
          </View>
          <View style={styles.total}>
            <Eyebrow>NEXT 30 DAYS</Eyebrow>
            <Text style={[text.figure, styles.totalValue]}>{fmt(next30)}</Text>
          </View>
        </View>
      ) : null}

      {bills.map((bill) => (
        <Panel key={bill.id}>
          <View style={styles.head}>
            <Dot glyph={bill.nickname.charAt(0)} name={BILL_TONE[bill.category] ?? 'teal'} />
            <View style={styles.headCopy}>
              <Text style={text.label} numberOfLines={1}>
                {bill.nickname}
              </Text>
              <Text style={text.small} numberOfLines={1}>
                {bill.payee}
              </Text>
            </View>
            <View style={styles.headAmount}>
              <Text style={[text.figure, styles.amount]}>{fmt(bill.amount)}</Text>
              <Text style={text.small}>{dueLabel(bill.next_date, summary.as_of)}</Text>
            </View>
          </View>

          <Body>{bill.explanation}</Body>

          {bill.heads_up ? (
            <View style={styles.headsUp}>
              <Feather name="alert-circle" size={13} color={color.brass} />
              <Text style={[text.small, styles.headsUpText]}>{bill.heads_up}</Text>
            </View>
          ) : null}
        </Panel>
      ))}

      {bills.length === 0 ? (
        <Panel>
          <Empty title="No bills on file." body="Nothing recurring was detected for this persona." />
        </Panel>
      ) : null}
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
  totals: { flexDirection: 'row', gap: 10 },
  total: {
    flex: 1,
    gap: 4,
    backgroundColor: color.paperCard,
    borderRadius: radius.sm,
    padding: 13,
  },
  totalValue: { fontSize: 17 },

  head: { flexDirection: 'row', alignItems: 'center', gap: 11 },
  headCopy: { flex: 1, gap: 3 },
  headAmount: { alignItems: 'flex-end', gap: 3 },
  amount: { fontSize: 15 },

  headsUp: {
    flexDirection: 'row',
    gap: 9,
    alignItems: 'flex-start',
    backgroundColor: color.brassTint,
    borderRadius: radius.sm,
    padding: 11,
  },
  headsUpText: { flex: 1, color: color.brass, fontFamily: font.sansMed },
})
