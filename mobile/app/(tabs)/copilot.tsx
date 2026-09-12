// The agent, with the confirmation gate in front of every write.
//
// It never does arithmetic here: the reply text and the proposed action both
// come from the backend, which got its numbers from the engine. That is design
// rule 1 in begin.md §6, and it is the answer to "how do you stop the LLM from
// hallucinating a balance".
//
// The web app renders this as a drawer sliding in from the right, opened from a
// button on its dark rail. On a phone it is a tab: the copilot is not a thing
// you summon over the dashboard, it is one of the six places the app goes, and
// a tab is how a phone says that. It was a modal sheet before, which meant the
// one screen you might come back to five times was the one behind a 34px icon.
//
// Which model writes the prose is the user's to choose. `/model-key` holds the
// key on this device, the store hands it over, and `lib/api.ts` sends it with
// each question — see `lib/secrets.ts`, and `backend/agent/keys.py` for what
// the backend does and does not keep.

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

import { Body, Button, Eyebrow, Panel } from '../../components/ui'
import { chat, confirmAction } from '../../lib/api'
import {
  MODEL_PROVIDERS,
  isChatError,
  type ActionResult,
  type ChatReply,
  type ProposedAction,
} from '../../lib/contract'
import { dayMonth, money, runwayLabel } from '../../lib/format'
import { useStore } from '../../lib/store'
import { color, font, radius, space, text } from '../../lib/theme'

interface Message {
  role: 'user' | 'agent'
  text: string
  tools?: string[]
  /** Which brain wrote it, when a model did. */
  provider?: string
  /** Whose key paid for it. */
  keySource?: 'user' | 'server' | null
}

const SUGGESTIONS = [
  '¿Puedo permitirme ir a Chicago este finde?',
  'Why did my card balance go up if I paid it?',
  'What happens if I cancel the gym before I fly home?',
]

function providerLabel(id?: string): string {
  return MODEL_PROVIDERS.find((p) => p.id === id)?.label ?? 'the scripted router'
}

export default function Copilot() {
  const { user, live, reload, setConfirmed, modelKey, modelKeyReady } = useStore()
  const router = useRouter()
  const insets = useSafeAreaInsets()
  const scroller = useRef<ScrollView>(null)

  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [action, setAction] = useState<ProposedAction | null>(null)
  const [result, setResult] = useState<ActionResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [keyTrouble, setKeyTrouble] = useState<string | null>(null)

  async function ask(message: string) {
    if (!message.trim() || busy) return
    setMessages((m) => [...m, { role: 'user', text: message }])
    setInput('')
    setBusy(true)
    setError(null)
    setKeyTrouble(null)
    try {
      const data = await chat({ user, message }, modelKey)
      if (!data) throw new Error('no reply')
      if (isChatError(data)) {
        // `bad_model_key` is the one refusal the user can act on, and its
        // message says which way the key is unreadable. Every other error is
        // ours, not theirs, and reads as the backend being unreachable — which
        // it probably is.
        if (data.error !== 'bad_model_key') throw new Error(data.error)
        setKeyTrouble(data.message ?? data.error)
        return
      }
      const reply = data as ChatReply
      setMessages((m) => [
        ...m,
        {
          role: 'agent',
          text: reply.reply,
          tools: reply.used_tools,
          provider: reply._provider,
          keySource: reply._key_source,
        },
      ])
      // A key of the user's that did not work is the user's to fix — a typo, an
      // empty quota, a model name that does not exist. The answer still landed,
      // composed by the scripted router from the same tools, so this is a note
      // rather than an error.
      if (reply._key_rejected) {
        setKeyTrouble(
          `Your key did not answer${reply._fell_back ? ` — ${reply._fell_back}` : ''}. ` +
            'The reply above came from the scripted router instead.',
        )
      }
      if (reply.proposed_action) {
        setAction(reply.proposed_action)
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
        // The money actually moved. Every figure on the other tabs was read
        // before that happened, so without this the overview strip would
        // announce a new runway date while the card under it still shows the
        // old one. This is the web app's `router.refresh()`.
        await reload()
        // And then go to the screen that says so. As a modal this closed itself
        // onto whatever was behind it; a tab has to walk over deliberately, and
        // the overview is where the strip and the new runway date are.
        router.navigate('/')
      }
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
      // The composer sits above the tab bar, so on iOS the keyboard has to be
      // told the bar is there or it lifts the input by exactly one tab bar too
      // little and covers what you are typing.
      keyboardVerticalOffset={Platform.OS === 'ios' ? space.tabBar + insets.bottom : 0}
    >
      <View style={styles.head}>
        <View style={styles.headCopy}>
          <Eyebrow>FINANCIAL COPILOT</Eyebrow>
          <Text style={text.h2}>Ask about your money</Text>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={
            modelKey ? 'Change the model key this app uses' : 'Use your own model key'
          }
          onPress={() => router.push('/model-key')}
          hitSlop={8}
          style={({ pressed }) => [
            styles.keyButton,
            modelKey && styles.keyButtonOn,
            pressed && styles.pressed,
          ]}
        >
          <Feather name="key" size={12} color={modelKey ? color.tealDeep : color.inkMute} />
          <Text style={[styles.keyLabel, modelKey && styles.keyLabelOn]}>
            {modelKeyReady && modelKey ? providerLabel(modelKey.provider) : 'YOUR KEY'}
          </Text>
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
            {/* Fixture mode has no backend, so it has no tools and no model —
                just one exported reply. Letting the same answer come back to
                three different questions looks like a broken agent rather than
                a missing backend. */}
            {!live ? (
              <Text style={[text.small, styles.fixtureNote]}>
                Running on bundled fixtures, so this is one canned reply. Set
                EXPO_PUBLIC_TREASURER_API_BASE to talk to the API — then your own key, if you add
                one, writes the answers.
              </Text>
            ) : null}
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
            {m.role === 'agent' && m.keySource === 'user' ? (
              <Text style={styles.trace}>written by your {providerLabel(m.provider)} key</Text>
            ) : null}
          </View>
        ))}

        {busy ? (
          <View style={[styles.bubble, styles.bubbleAgent, styles.pending]}>
            <ActivityIndicator size="small" color={color.inkMute} />
            <Text style={text.small}>thinking…</Text>
          </View>
        ) : null}

        {keyTrouble ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Check the model key"
            onPress={() => router.push('/model-key')}
            style={styles.keyTrouble}
          >
            <Text style={[text.small, styles.keyTroubleText]}>{keyTrouble}</Text>
            <Text style={[text.small, styles.keyTroubleLink]}>Check the key →</Text>
          </Pressable>
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

      <View style={styles.composer}>
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

  keyButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 7,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: color.line,
    backgroundColor: color.surface2,
  },
  // A key is set: the button is a statement of fact now, not an invitation.
  keyButtonOn: { borderColor: color.tealLine, backgroundColor: color.tealTint },
  keyLabel: { fontFamily: font.figureMed, fontSize: 9, letterSpacing: 0.9, color: color.inkMute },
  keyLabelOn: { color: color.tealDeep },

  body: { flex: 1 },
  bodyContent: { padding: 18, gap: 12 },

  empty: { gap: 14 },
  fixtureNote: {
    backgroundColor: color.brassTint,
    borderRadius: radius.sm,
    padding: 11,
    color: color.brass,
    overflow: 'hidden',
  },
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

  keyTrouble: {
    gap: 6,
    backgroundColor: color.brassTint,
    borderWidth: 1,
    borderColor: color.brassLine,
    borderRadius: radius.sm,
    padding: 12,
  },
  keyTroubleText: { color: color.brass },
  keyTroubleLink: { color: color.brass, fontFamily: font.sansSemi },

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
    paddingVertical: 10,
    borderTopWidth: 1,
    borderTopColor: color.line,
    backgroundColor: color.surface,
    // No safe-area padding here: the tab bar below already owns that space.
    // As a modal this screen had to add it itself.
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
