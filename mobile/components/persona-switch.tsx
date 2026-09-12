// The other two personas are there to show the forecast is not hard-coded.
//
// On the web they are links in the sidebar footer. Here they are initials in the
// header, because switching persona mid-demo is the fastest way to prove that
// Ana's deficit and Raj's clear runway come out of the same code.

import { Pressable, StyleSheet, Text, View } from 'react-native'

import { PERSONAS, useStore } from '../lib/store'
import { color, font, radius } from '../lib/theme'

export function PersonaSwitch({ dark = true }: { dark?: boolean }) {
  const { user, setUser, loading } = useStore()

  return (
    <View style={styles.row} accessibilityRole="radiogroup" accessibilityLabel="Persona">
      {PERSONAS.map((id) => {
        const on = id === user
        return (
          <Pressable
            key={id}
            accessibilityRole="radio"
            accessibilityState={{ selected: on, disabled: loading }}
            accessibilityLabel={`Show ${id}`}
            disabled={loading}
            onPress={() => setUser(id)}
            style={({ pressed }) => [
              styles.chip,
              dark ? styles.chipDark : styles.chipLight,
              on && (dark ? styles.chipDarkOn : styles.chipLightOn),
              pressed && styles.pressed,
            ]}
          >
            <Text
              style={[
                styles.label,
                dark ? styles.labelDark : styles.labelLight,
                on && styles.labelOn,
              ]}
            >
              {id.charAt(0).toUpperCase()}
            </Text>
          </Pressable>
        )
      })}
    </View>
  )
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', gap: 5 },
  chip: {
    width: 28,
    height: 28,
    borderRadius: radius.sm,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
  },
  chipDark: { backgroundColor: 'transparent', borderColor: color.vaultLine },
  chipDarkOn: { backgroundColor: color.teal, borderColor: color.teal },
  chipLight: { backgroundColor: color.surface, borderColor: color.line },
  chipLightOn: { backgroundColor: color.teal, borderColor: color.teal },
  label: { fontFamily: font.figureSemi, fontSize: 11 },
  labelDark: { color: color.vaultMute },
  labelLight: { color: color.inkMute },
  labelOn: { color: '#ffffff' },
  pressed: { opacity: 0.7 },
})
