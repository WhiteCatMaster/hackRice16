// "Use your own model" — the form, on a phone.
//
// The copilot normally answers with whatever key the backend's .env holds. That
// is one key, on one laptop, belonging to one of us. Anybody else holding this
// phone has their own key and, until this screen existed, no way to use it.
//
// A modal route rather than a tab: it is something you do once and leave, so
// the OS sheet gesture and the back button are exactly right, and it keeps the
// tab bar for the six places the app actually goes.
//
// Where the key ends up: `lib/secrets.ts` (the phone's keystore), never this
// repository and never the server's disk — see `backend/agent/keys.py`.

import { Feather } from '@expo/vector-icons'
import { useRouter } from 'expo-router'
import { useState } from 'react'
import {
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

import { Body, Button, Eyebrow } from '../components/ui'
import {
  MODEL_PROVIDERS,
  inferProvider,
  redactKey,
  type ModelProvider,
} from '../lib/contract'
import { useStore } from '../lib/store'
import { color, font, radius, text } from '../lib/theme'

/** The same rules `backend/agent/keys.py` applies, so a bad paste fails here first. */
function complain(key: string): string | null {
  const trimmed = key.trim()
  if (!trimmed) return 'Paste a key first.'
  if (/\s/.test(trimmed)) return 'A key has no spaces or line breaks in it. Check the paste.'
  if (trimmed.length > 400) return 'That is longer than a key. Did a whole file come along?'
  return null
}

const WHERE_IT_LIVES: Record<string, string> = {
  keychain: 'Kept in this phone’s keystore, so it survives a restart.',
  browser: 'Kept in this browser’s storage.',
  session: 'This device would not let us store it, so it lasts until the app closes.',
}

export default function ModelKeyScreen() {
  const { live, modelKey, modelKeyStore, setModelKey } = useStore()
  const router = useRouter()
  const insets = useSafeAreaInsets()

  const [provider, setProvider] = useState<ModelProvider>(modelKey?.provider ?? 'gemini')
  const [key, setKey] = useState(modelKey?.key ?? '')
  const [model, setModel] = useState(modelKey?.model ?? '')
  const [baseUrl, setBaseUrl] = useState(modelKey?.baseUrl ?? '')
  const [error, setError] = useState<string | null>(null)

  const meta = MODEL_PROVIDERS.find((p) => p.id === provider)!
  // A key whose shape says "Claude" sitting in the Gemini field is the mistake
  // this screen exists to catch. A note rather than a block: an
  // OpenAI-compatible proxy hands out keys in every shape there is.
  const looksLike = inferProvider(key)
  const mismatch = key.trim() !== '' && looksLike !== null && looksLike !== provider

  function save() {
    const wrong = complain(key)
    if (wrong) return setError(wrong)
    setError(null)
    setModelKey({
      provider,
      key: key.trim(),
      model: model.trim() || undefined,
      baseUrl: provider === 'openai' && baseUrl.trim() ? baseUrl.trim() : undefined,
    })
    router.back()
  }

  function forget() {
    setModelKey(null)
    router.back()
  }

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={styles.head}>
        <View style={styles.headCopy}>
          <Eyebrow>YOUR OWN MODEL</Eyebrow>
          <Text style={text.h2}>Answer with your key</Text>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Close"
          onPress={() => router.back()}
          hitSlop={12}
          style={({ pressed }) => [styles.close, pressed && styles.pressed]}
        >
          <Feather name="x" size={17} color={color.inkSoft} />
        </Pressable>
      </View>

      <ScrollView
        style={styles.body}
        contentContainerStyle={[styles.bodyContent, { paddingBottom: insets.bottom + 28 }]}
        keyboardShouldPersistTaps="handled"
      >
        <Body>
          Sent with each question, used for that one answer, and never written down on the server.
          {' '}
          {WHERE_IT_LIVES[modelKeyStore]}
        </Body>

        {/* Fixture mode has no backend, and the tools that produce the numbers
            live in the backend — so a key stored now is stored for later, not
            used today. Better said here than discovered by a key that seems to
            do nothing. */}
        {!live ? (
          <Text style={[text.small, styles.warn]}>
            This app is reading bundled fixtures, so there is no backend to spend a key. Set
            EXPO_PUBLIC_TREASURER_API_BASE first; the key will be waiting.
          </Text>
        ) : null}

        <View style={styles.providers} accessibilityRole="radiogroup">
          {MODEL_PROVIDERS.map((p) => (
            <Pressable
              key={p.id}
              accessibilityRole="radio"
              accessibilityState={{ checked: provider === p.id }}
              onPress={() => setProvider(p.id)}
              style={({ pressed }) => [
                styles.provider,
                provider === p.id && styles.providerOn,
                pressed && styles.pressed,
              ]}
            >
              <Text style={[styles.providerLabel, provider === p.id && styles.providerLabelOn]}>
                {p.label}
              </Text>
            </Pressable>
          ))}
        </View>

        <View style={styles.field}>
          <Eyebrow>API KEY</Eyebrow>
          <TextInput
            value={key}
            onChangeText={setKey}
            placeholder={meta.prefix}
            placeholderTextColor={color.inkFaint}
            accessibilityLabel="API key"
            autoCapitalize="none"
            autoCorrect={false}
            secureTextEntry
            style={styles.input}
          />
          <Text style={styles.hint}>From {meta.source}</Text>
        </View>

        <View style={styles.field}>
          <Eyebrow>MODEL (OPTIONAL)</Eyebrow>
          <TextInput
            value={model}
            onChangeText={setModel}
            placeholder={meta.defaultModel}
            placeholderTextColor={color.inkFaint}
            accessibilityLabel="Model name"
            autoCapitalize="none"
            autoCorrect={false}
            style={styles.input}
          />
        </View>

        {meta.endpoint ? (
          <View style={styles.field}>
            <Eyebrow>ENDPOINT (OPTIONAL)</Eyebrow>
            <TextInput
              value={baseUrl}
              onChangeText={setBaseUrl}
              placeholder="https://openrouter.ai/api/v1"
              placeholderTextColor={color.inkFaint}
              accessibilityLabel="Model endpoint"
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
              style={styles.input}
            />
            <Text style={styles.hint}>
              Anything that speaks OpenAI’s shape — OpenRouter, Groq, or a model on the machine
              running the backend. http is only allowed for localhost.
            </Text>
          </View>
        ) : null}

        {mismatch ? (
          <Text style={[text.small, styles.warn]}>
            That key looks like {MODEL_PROVIDERS.find((p) => p.id === looksLike)?.label}’s. Switch
            provider, or save it anyway if your endpoint expects it.
          </Text>
        ) : null}
        {error ? <Text style={styles.error}>{error}</Text> : null}

        <Button label={modelKey ? 'Replace key' : 'Use this key'} onPress={save} />
        {modelKey ? (
          <Button
            label={`Forget ${redactKey(modelKey.key)}`}
            kind="secondary"
            onPress={forget}
          />
        ) : null}
      </ScrollView>
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
  bodyContent: { padding: 18, gap: 16 },

  providers: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  provider: {
    paddingHorizontal: 12,
    paddingVertical: 9,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: color.line,
    backgroundColor: color.surface,
  },
  providerOn: { backgroundColor: color.vault, borderColor: color.vault },
  providerLabel: { fontFamily: font.sansMed, fontSize: 12, color: color.inkSoft },
  providerLabelOn: { color: '#ffffff' },

  field: { gap: 6 },
  input: {
    borderWidth: 1,
    borderColor: color.line,
    borderRadius: radius.sm,
    paddingHorizontal: 12,
    paddingVertical: 11,
    fontFamily: font.figure,
    fontSize: 13,
    color: color.ink,
    backgroundColor: color.surface,
  },
  hint: { fontFamily: font.sans, fontSize: 11, lineHeight: 16, color: color.inkMute },

  warn: {
    backgroundColor: color.brassTint,
    borderRadius: radius.sm,
    padding: 11,
    color: color.brass,
    overflow: 'hidden',
  },
  error: { ...text.small, color: color.flagDeep },
  pressed: { opacity: 0.75 },
})
