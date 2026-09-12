// The agent, with the confirmation gate in front of every write.
//
// It never does arithmetic here: the reply text and the proposed action both
// come from the backend, which got its numbers from the engine. That is design
// rule 1 in begin.md §6, and it is the answer to "how do you stop the LLM from
// hallucinating a balance".
//
// The web app renders this as a drawer sliding in from the right. On a phone it
// is a modal route, so the OS gives it the sheet gesture and the back button for
// free — and the keyboard, which is the part a drawer would have fought.

import { Feather } from '@expo/vector-icons'
import { useRouter } from 'expo-router'
import { useRef, useState } from 'react'
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'

import { Body, Button, Eyebrow, Panel } from '../components/ui'
import { chat, confirmAction } from '../lib/api'
import type { ActionResult, ChatReply, ProposedAction } from '../lib/contract'
import { dayMonth, money, runwayLabel } from '../lib/format'
import { useStore } from '../lib/store'
import { color, font, radius, text } from '../lib/theme'

interface Message {
  role: 'user' | 'agent'
  text: string
  tools?: string[]
}

const SUGGESTIONS = [
  '¿Puedo permitirme ir a Chicago este finde?',
  'Why did my card balance go up if I paid it?',
  'What happens if I cancel the gym before I fly home?',
]

export default function Copilot() {
  const { user, reload, setConfirmed } = useStore()
  const router = useRouter()
  const insets = useSafeAreaInsets()
  const scroller = useRef<ScrollView>(null)

  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [action, setAction] = useState<ProposedAction | null>(null)
  const [result, setResult] = useState<ActionResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function ask(message: string) {
    if (!message.trim() || busy) return
    setMessages((m) => [...m, { role: 'user', text: message }])
    setInput('')
    setBusy(true)
    setError(null)
    try {
      const data: ChatReply | null = await chat({ user, message })
      if (!data) throw new Error('no reply')
      setMessages((m) => [...m, { role: 'agent', text: data.reply, tools: data.used_tools }])
      if (data.proposed_action) {
        setAction(data.proposed_action)
        setResult(null)
      }
    } catch {
      setError('The agent did not answer. Is the backend running?')
    } finally {
      setBusy(false)
      requestAnimationFrame(() => scroller.current?.scrollToEnd({ animated: true }))
    }
  }

  async function approve() {
    if (!action) return
    setBusy(true)
    try {
      const data = await confirmAction(action.id, { user, action })
      setResult(data)
      setConfirmed(data)
      if (data.status === 'executed') {
        // The money actually moved. Every figure on the tabs behind this sheet
        // was read before that happened, so without this the strip would
        // announce a new runway date while the card under it still shows the
        // old one. This is the web app's `router.refresh()`.
        await reload()
      }
      router.back()
    } catch {
      setError('The action could not be confirmed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 8 : 0}
    >
      <View style={styles.head}>
        <View style={styles.headCopy}>
          <Eyebrow>FINANCIAL COPILOT</Eyebrow>
          <Text style={text.h2}>Ask about your money</Text>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Close the copilot"
          onPress={() => router.back()}
          hitSlop={12}
          style={({ pressed }) => [styles.close, pressed && styles.pressed]}
        >
          <Feather name="x" size={17} color={color.inkSoft} />
        </Pressable>
      </View>

      <ScrollView
        ref={scroller}
        style={styles.body}
        contentContainerStyle={styles.bodyContent}
        keyboardShouldPersistTaps="handled"
        onContentSizeChange={() => scroller.current?.scrollToEnd({ animated: true })}
      >
        {messages.length === 0 ? (
          <View style={styles.empty}>
            <Body>
              Every number in an answer comes from the forecast engine. The assistant picks the
              tools and explains the result — it does not do the arithmetic.
            </Body>
            <View style={styles.suggestions}>
              {SUGGESTIONS.map((s) => (
                <Pressable
                  key={s}
                  accessibilityRole="button"
                  onPress={() => void ask(s)}
                  style={({ pressed }) => [styles.suggestion, pressed && styles.pressed]}
                >
                  <Text style={[text.small, styles.suggestionText]}>{s}</Text>
                  <Feather name="arrow-up-right" size={13} color={color.inkMute} />
                </Pressable>
              ))}
            </View>
          </View>
        ) : null}

        {messages.map((m, i) => (
          <View
            key={i}
            style={[styles.bubble, m.role === 'user' ? styles.bubbleUser : styles.bubbleAgent]}
          >
            <Text style={[text.body, m.role === 'user' ? styles.bubbleInkUser : styles.bubbleInk]}>
              {m.text}
            </Text>
            {m.tools && m.tools.length > 0 ? (
              <Text style={styles.trace}>via {m.tools.join(' · ')}</Text>
            ) : null}
          </View>
        ))}

        {busy ? (
          <View style={[styles.bubble, styles.bubbleAgent, styles.pending]}>
            <ActivityIndicator size="small" color={color.inkMute} />
            <Text style={text.small}>thinking…</Text>
          </View>
        ) : null}

        {error ? <Text style={styles.error}>{error}</Text> : null}

        {action ? (
          <Panel style={styles.action}>
            <Eyebrow>PROPOSED ACTION · NEEDS YOUR APPROVAL</Eyebrow>
            <Text style={text.h3}>
              Move {money(action.amount)} from {action.from} to {action.to}
            </Text>

            {action.effect ? (
              action.effect.measured === false ? (
                // A null date here means "we could not work it out", which is
                // the opposite of what it means when the effect was measured.
                // Saying so is better than implying the best outcome.
                <Text style={[text.small, styles.unmeasured]}>
                  {action.effect.measured_note ??
                    'We could not measure what this would do to your runway.'}
                </Text>
              ) : (
                <View style={styles.effect}>
                  <Eyebrow>RUNWAY</Eyebrow>
                  <View style={styles.effectLine}>
                    {action.effect.runway_date_before ? (
                      <Text style={[text.figure, styles.struck]}>
                        {dayMonth(action.effect.runway_date_before)}
                      </Text>
                    ) : null}
                    {/* Never hidden: null is the best outcome there is, and
                        dropping the line loses the payoff of the whole beat. */}
                    <Text style={[text.figure, styles.effectValue]}>
                      {runwayLabel(action.effect.runway_date_after)}
                    </Text>
                  </View>
                </View>
              )
            ) : null}

            {result ? (
              <Text
                style={[
                  text.small,
                  styles.result,
                  result.executed_in_nessie ? styles.resultLive : styles.resultSim,
                ]}
              >
                {result.message}
              </Text>
            ) : (
              <View style={styles.actionButtons}>
                <Button label="Approve" onPress={() => void approve()} busy={busy} style={styles.grow} />
                <Button label="Not now" kind="secondary" onPress={() => setAction(null)} />
              </View>
            )}
          </Panel>
        ) : null}
      </ScrollView>

      <View style={[styles.composer, { paddingBottom: insets.bottom + 10 }]}>
        <TextInput
          value={input}
          onChangeText={setInput}
          onSubmitEditing={() => void ask(input)}
          placeholder="Ask in English or Spanish…"
          placeholderTextColor={color.inkFaint}
          accessibilityLabel="Message the copilot"
          returnKeyType="send"
          style={styles.input}
          multiline
        />
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Send"
          accessibilityState={{ disabled: busy || !input.trim() }}
          disabled={busy || !input.trim()}
          onPress={() => void ask(input)}
          style={({ pressed }) => [
            styles.send,
            (busy || !input.trim()) && styles.sendOff,
            pressed && styles.pressed,
          ]}
        >
          <Feather name="arrow-up" size={17} color="#ffffff" />
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  )
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.paper },

  head: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
    paddingHorizontal: 18,
    paddingTop: 18,
    paddingBottom: 14,
    borderBottomWidth: 1,
    borderBottomColor: color.line,
  },
  headCopy: { flex: 1, gap: 4 },
  close: {
    width: 32,
    height: 32,
    borderRadius: radius.sm,
    backgroundColor: color.surface2,
    alignItems: 'center',
    justifyContent: 'center',
  },

  body: { flex: 1 },
  bodyContent: { padding: 18, gap: 12 },

  empty: { gap: 14 },
  suggestions: { gap: 8 },
  suggestion: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.line,
    borderRadius: radius.sm,
    padding: 13,
  },
  suggestionText: { flex: 1, color: color.inkSoft },

  bubble: { borderRadius: radius.md, paddingHorizontal: 14, paddingVertical: 11, maxWidth: '92%', gap: 5 },
  bubbleUser: { alignSelf: 'flex-end', backgroundColor: color.vault },
  bubbleAgent: { alignSelf: 'flex-start', backgroundColor: color.surface, borderWidth: 1, borderColor: color.line },
  bubbleInk: { color: color.ink },
  bubbleInkUser: { color: '#ffffff' },
  pending: { flexDirection: 'row', alignItems: 'center', gap: 9 },
  trace: { fontFamily: font.figure, fontSize: 9, letterSpacing: 0.7, color: color.inkFaint },

  error: { ...text.small, color: color.flagDeep },

  action: { borderColor: color.tealLine, backgroundColor: color.tealTint },
  effect: { gap: 4 },
  effectLine: { flexDirection: 'row', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' },
  struck: { color: color.inkFaint, textDecorationLine: 'line-through' },
  effectValue: { color: color.tealDeep, fontSize: 14 },
  unmeasured: { color: color.brass },
  actionButtons: { flexDirection: 'row', gap: 8 },
  grow: { flex: 1 },
  result: { borderRadius: radius.sm, padding: 11, overflow: 'hidden' },
  resultLive: { backgroundColor: color.surface, color: color.tealDeep },
  resultSim: { backgroundColor: color.brassTint, color: color.brass },

  composer: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 9,
    paddingHorizontal: 14,
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: color.line,
    backgroundColor: color.surface,
  },
  input: {
    flex: 1,
    maxHeight: 110,
    minHeight: 42,
    borderWidth: 1,
    borderColor: color.line,
    borderRadius: radius.md,
    paddingHorizontal: 13,
    paddingTop: 11,
    paddingBottom: 11,
    fontFamily: font.sans,
    fontSize: 14,
    color: color.ink,
    backgroundColor: color.surface2,
  },
  send: {
    width: 42,
    height: 42,
    borderRadius: radius.md,
    backgroundColor: color.teal,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendOff: { opacity: 0.4 },
  pressed: { opacity: 0.75 },
})
