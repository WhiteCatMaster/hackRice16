// The small pieces every screen is built from.
//
// The web app gets these from the stylesheet — `.panel`, `.eyebrow`,
// `.primary-button` are classes anything can wear. React Native has no
// cascade, so the same vocabulary has to be components. Same names, so a change
// on one side is findable on the other.

import { forwardRef } from 'react'
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type TextStyle,
  type ViewStyle,
} from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'

import { color, font, lift, radius, space, text, tone, type ToneName } from '../lib/theme'

/* === Type ================================================================= */

export function Eyebrow({ children, style }: { children: React.ReactNode; style?: StyleProp<TextStyle> }) {
  return <Text style={[text.eyebrow, style]}>{children}</Text>
}

export function Body({ children, style }: { children: React.ReactNode; style?: StyleProp<TextStyle> }) {
  return <Text style={[text.body, style]}>{children}</Text>
}

/* === Containers =========================================================== */

export function Panel({
  children,
  style,
}: {
  children: React.ReactNode
  style?: StyleProp<ViewStyle>
}) {
  return <View style={[styles.panel, style]}>{children}</View>
}

/** The eyebrow + title pair that opens every panel on the web. */
export function PanelHead({
  eyebrow,
  title,
  right,
}: {
  eyebrow: string
  title: string
  right?: React.ReactNode
}) {
  return (
    <View style={styles.panelHead}>
      <View style={styles.panelHeadCopy}>
        <Eyebrow>{eyebrow}</Eyebrow>
        <Text style={[text.h2, styles.panelHeadTitle]}>{title}</Text>
      </View>
      {right}
    </View>
  )
}

/**
 * What this screen is for, in one sentence.
 *
 * The web app's `<ViewHeader>` — minus its "back to overview" button, which a
 * tab bar makes redundant.
 */
export function Intro({
  eyebrow,
  title,
  body,
}: {
  eyebrow: string
  title: string
  body: string
}) {
  return (
    <View style={styles.intro}>
      <Eyebrow>{eyebrow}</Eyebrow>
      <Text style={text.h1}>{title}</Text>
      <Text style={text.body}>{body}</Text>
    </View>
  )
}

/**
 * The scrolling body of a tab.
 *
 * Pull-to-refresh is the phone's version of the web app's `router.refresh()`:
 * the same reload, reachable by the gesture people already try. `insets.bottom`
 * keeps the last card clear of the home indicator, which otherwise sits on top
 * of it on every modern iPhone.
 */
export const Screen = forwardRef<ScrollView, {
  children: React.ReactNode
  refreshing?: boolean
  onRefresh?: () => void
}>(function Screen({ children, refreshing, onRefresh }, ref) {
  const insets = useSafeAreaInsets()
  return (
    <ScrollView
      ref={ref}
      style={styles.screen}
      contentContainerStyle={[styles.screenContent, { paddingBottom: insets.bottom + 32 }]}
      keyboardShouldPersistTaps="handled"
      refreshControl={
        onRefresh ? (
          <RefreshControl
            refreshing={!!refreshing}
            onRefresh={onRefresh}
            tintColor={color.inkMute}
            colors={[color.teal]}
          />
        ) : undefined
      }
    >
      {children}
    </ScrollView>
  )
})

/* === Controls ============================================================= */

type ButtonKind = 'primary' | 'secondary' | 'ghost'

export function Button({
  label,
  onPress,
  kind = 'primary',
  disabled,
  busy,
  style,
}: {
  label: string
  onPress: () => void
  kind?: ButtonKind
  disabled?: boolean
  busy?: boolean
  style?: StyleProp<ViewStyle>
}) {
  const off = disabled || busy
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!off, busy: !!busy }}
      disabled={off}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        kind === 'primary' && styles.buttonPrimary,
        kind === 'secondary' && styles.buttonSecondary,
        kind === 'ghost' && styles.buttonGhost,
        off && styles.buttonOff,
        pressed && styles.buttonPressed,
        style,
      ]}
    >
      {busy && <ActivityIndicator size="small" color={kind === 'primary' ? '#fff' : color.teal} />}
      <Text
        style={[
          styles.buttonLabel,
          kind === 'primary' && styles.buttonLabelPrimary,
          kind !== 'primary' && styles.buttonLabelQuiet,
        ]}
      >
        {label}
      </Text>
    </Pressable>
  )
}

/** A round category badge: the first letter of a bill, or an arrow for money in. */
export function Dot({ glyph, name }: { glyph: string; name: ToneName }) {
  return (
    <View style={[styles.dot, { backgroundColor: tone[name].bg }]}>
      <Text style={[styles.dotGlyph, { color: tone[name].ink }]}>{glyph}</Text>
    </View>
  )
}

export function Pill({
  label,
  name = 'teal',
}: {
  label: string
  name?: ToneName | 'flag' | 'brass'
}) {
  const skin =
    name === 'flag'
      ? { bg: color.flagTint, ink: color.flagDeep }
      : name === 'brass'
        ? { bg: color.brassTint, ink: color.brass }
        : tone[name]
  return (
    <View style={[styles.pill, { backgroundColor: skin.bg }]}>
      <Text style={[styles.pillLabel, { color: skin.ink }]}>{label}</Text>
    </View>
  )
}

/** A row of figures under small-caps labels — the credit screen's spine. */
export function Figures({ items }: { items: { label: string; value: string }[] }) {
  return (
    <View style={styles.figures}>
      {items.map((item) => (
        <View key={item.label} style={styles.figuresCell}>
          <Eyebrow>{item.label}</Eyebrow>
          <Text style={[text.figure, styles.figuresValue]}>{item.value}</Text>
        </View>
      ))}
    </View>
  )
}

export function Empty({ title, body }: { title: string; body?: string }) {
  return (
    <View accessibilityRole="text" style={styles.empty}>
      <Text style={[text.label, styles.emptyTitle]}>{title}</Text>
      {body ? <Text style={text.small}>{body}</Text> : null}
    </View>
  )
}

/** A horizontal rule with the same weight as the web app's borders. */
export function Rule({ style }: { style?: StyleProp<ViewStyle> }) {
  return <View style={[styles.rule, style]} />
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: color.paper },
  screenContent: { padding: space.gutter, gap: space.gap },

  panel: {
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.line,
    borderRadius: radius.md,
    padding: space.card,
    gap: 12,
    ...lift(1),
  },
  intro: { gap: 7, paddingBottom: 14, borderBottomWidth: 1, borderBottomColor: color.line },
  panelHead: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  panelHeadCopy: { flex: 1, gap: 4 },
  panelHeadTitle: { marginTop: 2 },

  button: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    borderRadius: radius.sm,
    paddingVertical: 13,
    paddingHorizontal: 16,
    borderWidth: 1,
  },
  buttonPrimary: { backgroundColor: color.teal, borderColor: color.teal },
  buttonSecondary: { backgroundColor: 'transparent', borderColor: color.line },
  buttonGhost: { backgroundColor: 'transparent', borderColor: 'transparent' },
  buttonOff: { opacity: 0.45 },
  buttonPressed: { opacity: 0.75 },
  buttonLabel: { fontFamily: font.sansSemi, fontSize: 13, letterSpacing: 0.2 },
  buttonLabelPrimary: { color: '#ffffff' },
  buttonLabelQuiet: { color: color.inkSoft },

  dot: { width: 34, height: 34, borderRadius: radius.pill, alignItems: 'center', justifyContent: 'center' },
  dotGlyph: { fontFamily: font.display, fontSize: 15 },

  pill: { paddingHorizontal: 9, paddingVertical: 4, borderRadius: radius.pill },
  pillLabel: { fontFamily: font.figureMed, fontSize: 9, letterSpacing: 0.9, textTransform: 'uppercase' },

  figures: { flexDirection: 'row', flexWrap: 'wrap', rowGap: 16, columnGap: 12 },
  figuresCell: { minWidth: '30%', flexGrow: 1, gap: 5 },
  figuresValue: { fontSize: 16 },

  empty: {
    backgroundColor: color.surface2,
    borderRadius: radius.sm,
    padding: 16,
    gap: 4,
  },
  emptyTitle: { fontFamily: font.sansSemi },

  rule: { height: 1, backgroundColor: color.lineSoft },
})
