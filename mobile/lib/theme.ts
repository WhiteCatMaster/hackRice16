// The "treasury desk" design system, as React Native values.
//
// These are the same tokens as the `:root` block in frontend/app/globals.css,
// transcribed rather than reinvented — the two apps are the same product, and a
// second palette invented here is a second product. Three semantic families
// carry every state, and nothing else gets a colour of its own:
//
//   teal   money is fine, this is on track, we checked and it is clean
//   brass  simulated, cached, not the live thing — believe it, but softly
//   clay   we stopped something, or something is about to run out
//
// The web build has a navy rail down the left. A phone has no room for a rail,
// so the navy goes to the tab bar and the header instead: same weight in the
// layout, same job of framing the paper.

import { Platform, StyleSheet } from 'react-native'

export const color = {
  /* Ground */
  paper: '#eef1f5',
  paperLow: '#e5ebf1',
  paperCard: '#dbe3ec',
  surface: '#fbfcfd',
  surface2: '#f3f6f9',

  /* Ink */
  ink: '#0f1b28',
  inkSoft: '#45566a',
  inkMute: '#78899c',
  inkFaint: '#a2b0bf',

  /* Rules */
  line: '#ccd7e2',
  lineSoft: '#e1e8ef',

  /* The navy rail — here, the header and the tab bar */
  vault: '#10202f',
  vault2: '#17304a',
  vaultLine: '#27415d',
  vaultInk: '#ccdbe9',
  vaultMute: '#7e94aa',

  /* Bank-note teal */
  teal: '#0e6f62',
  tealDeep: '#07463d',
  tealTint: '#d4ece7',
  tealLine: '#a5d6ce',

  /* Brass */
  brass: '#8a6112',
  brassTint: '#f7e7c6',
  brassLine: '#e2cb96',

  /* Clay */
  flag: '#a83a22',
  flagDeep: '#7b2814',
  flagTint: '#fadfd6',
  flagLine: '#f0b8a7',
} as const

/** Category chips. Keyed the way the fixtures categorise things. */
export const tone = {
  indigo: { bg: '#e2e4f4', ink: '#4b52a0' },
  clay: { bg: '#f8e3da', ink: '#9a5237' },
  teal: { bg: '#d9eeea', ink: '#106558' },
  slate: { bg: '#dee7f1', ink: '#3f5f80' },
} as const

export type ToneName = keyof typeof tone

export const BILL_TONE: Record<string, ToneName> = {
  housing: 'indigo',
  insurance: 'clay',
  phone: 'teal',
  fitness: 'teal',
  subscription: 'indigo',
  credit_card: 'clay',
}

export const ACTIVITY_TONE: Record<string, ToneName> = {
  groceries: 'teal',
  dining: 'clay',
  coffee: 'clay',
  deposit: 'slate',
  family: 'slate',
  transfer: 'slate',
}

/**
 * Three faces, three jobs — the split the web stylesheet makes.
 *
 * `display` for anything you read as a sentence or a headline figure,
 * `sans` for the interface, `figure` for anything that has to line up in a
 * column. The names on the right are the keys `useFonts` registers in
 * app/_layout.tsx; if a face fails to load, RN falls back to the system font
 * rather than crashing, so the app still renders.
 */
export const font = {
  display: 'Fraunces_500Medium',
  displaySemi: 'Fraunces_600SemiBold',
  sans: 'IBMPlexSans_400Regular',
  sansMed: 'IBMPlexSans_500Medium',
  sansSemi: 'IBMPlexSans_600SemiBold',
  figure: 'IBMPlexMono_400Regular',
  figureMed: 'IBMPlexMono_500Medium',
  figureSemi: 'IBMPlexMono_600SemiBold',
} as const

export const radius = { sm: 4, md: 8, lg: 12, pill: 999 } as const

export const space = {
  gutter: 18,
  card: 18,
  gap: 12,
} as const

/**
 * Elevation, once.
 *
 * iOS wants shadow*, Android wants elevation, and getting one without the other
 * is how a card ends up flat on half the devices in the room.
 */
export function lift(level: 1 | 2 = 1) {
  return Platform.select({
    ios: {
      shadowColor: '#0f1b28',
      shadowOpacity: level === 1 ? 0.06 : 0.18,
      shadowRadius: level === 1 ? 3 : 24,
      shadowOffset: { width: 0, height: level === 1 ? 1 : 12 },
    },
    android: { elevation: level === 1 ? 1 : 12 },
    default: {},
  })!
}

/** The shared voices. Anything used on more than one screen lives here. */
export const text = StyleSheet.create({
  /** The small caps running above every block. */
  eyebrow: {
    fontFamily: font.figureMed,
    fontSize: 9,
    letterSpacing: 1.3,
    textTransform: 'uppercase',
    color: color.inkMute,
  },
  /** Headline. */
  h1: {
    fontFamily: font.display,
    fontSize: 30,
    lineHeight: 34,
    letterSpacing: -0.7,
    color: color.ink,
  },
  h2: {
    fontFamily: font.display,
    fontSize: 21,
    lineHeight: 26,
    letterSpacing: -0.4,
    color: color.ink,
  },
  h3: {
    fontFamily: font.display,
    fontSize: 17,
    lineHeight: 22,
    letterSpacing: -0.2,
    color: color.ink,
  },
  /** Running prose. */
  body: {
    fontFamily: font.sans,
    fontSize: 13,
    lineHeight: 19,
    color: color.inkSoft,
  },
  small: {
    fontFamily: font.sans,
    fontSize: 11,
    lineHeight: 16,
    color: color.inkMute,
  },
  label: {
    fontFamily: font.sansMed,
    fontSize: 12,
    color: color.ink,
  },
  /** Anything that has to line up in a column. */
  figure: {
    fontFamily: font.figureMed,
    fontSize: 13,
    color: color.ink,
    fontVariant: ['tabular-nums'] as const,
  },
  figureBig: {
    fontFamily: font.figure,
    fontSize: 32,
    letterSpacing: -1,
    color: color.ink,
    fontVariant: ['tabular-nums'] as const,
  },
})
