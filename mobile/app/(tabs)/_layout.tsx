// The five screens, and the navy that frames them.
//
// The web app puts a dark rail down the left: brand at the top, the same five
// destinations, the copilot at the bottom. A phone has no room for a rail, so
// the navy splits in two — a header carrying the brand, the live/fixture status
// and the copilot, and a tab bar carrying the destinations. Same weight in the
// layout, same job of framing the paper.

import { Feather } from '@expo/vector-icons'
import { Tabs, useRouter } from 'expo-router'
import { ActivityIndicator, Pressable, StyleSheet, Text, View, type ColorValue } from 'react-native'
import { useSafeAreaInsets } from 'react-native-safe-area-context'

import { PersonaSwitch } from '../../components/persona-switch'
import { useStore } from '../../lib/store'
import { color, font, radius, text } from '../../lib/theme'

type IconName = React.ComponentProps<typeof Feather>['name']

export default function TabLayout() {
  const { summary, loading, openAlerts } = useStore()
  const insets = useSafeAreaInsets()

  if (loading || !summary) return <Gate loading={loading} />

  return (
    <View style={styles.root}>
      <Header />
      <Tabs
        screenOptions={{
          headerShown: false,
          tabBarActiveTintColor: '#ffffff',
          tabBarInactiveTintColor: color.vaultMute,
          // 64 is the floor an icon plus a label fits in. At 56 the label
          // rendered past the bar's own bottom edge and got clipped.
          tabBarStyle: [styles.tabBar, { height: 64 + insets.bottom, paddingBottom: insets.bottom }],
          tabBarLabelStyle: styles.tabLabel,
          tabBarItemStyle: styles.tabItem,
          sceneStyle: { backgroundColor: color.paper },
        }}
      >
        <Tabs.Screen name="index" options={tab('Overview', 'home')} />
        <Tabs.Screen name="runway" options={tab('Runway', 'trending-up')} />
        <Tabs.Screen name="bills" options={tab('Bills', 'file-text')} />
        <Tabs.Screen name="credit" options={tab('Credit', 'credit-card')} />
        <Tabs.Screen
          name="safety"
          options={{
            ...tab('Safety', 'shield'),
            // The count, not a bare dot: "2 to review" is the sentence the
            // overview card makes, and the badge should agree with it.
            tabBarBadge: openAlerts.length > 0 ? openAlerts.length : undefined,
            tabBarBadgeStyle: styles.badge,
          }}
        />
      </Tabs>
    </View>
  )
}

function tab(title: string, icon: IconName) {
  return {
    title,
    tabBarIcon: ({ color: tint, size }: { color: ColorValue; size: number }) => (
      <Feather name={icon} size={size - 3} color={tint} />
    ),
  }
}

/**
 * The brand bar. Carries the one thing the web top bar exists to say: whether
 * these numbers came from the engine or from `mocks/`.
 */
function Header() {
  const { summary, live, home, setHome, refreshing } = useStore()
  const insets = useSafeAreaInsets()
  const router = useRouter()

  return (
    <View style={[styles.header, { paddingTop: insets.top + 10 }]}>
      <View style={styles.headerTop}>
        <View style={styles.brand}>
          <View style={styles.brandMark}>
            <Text style={styles.brandMarkText}>ET</Text>
          </View>
          <View>
            <Text style={styles.brandName}>exchangetreasurer</Text>
            <Text style={styles.brandSub}>TREASURY DESK</Text>
          </View>
        </View>

        <View style={styles.headerActions}>
          <PersonaSwitch />
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Open the financial copilot"
            onPress={() => router.push('/copilot')}
            style={({ pressed }) => [styles.copilotButton, pressed && styles.pressed]}
          >
            <Feather name="message-circle" size={15} color="#ffffff" />
          </Pressable>
        </View>
      </View>

      <View style={styles.headerBottom}>
        <View style={styles.status}>
          <View style={[styles.statusDot, !live && styles.statusDotFixture]} />
          <Text style={styles.statusText} numberOfLines={1}>
            {live ? 'LIVE BACKEND · NESSIE-BACKED' : `FIXTURES · AS OF ${summary?.as_of ?? ''}`}
          </Text>
          {refreshing && <ActivityIndicator size="small" color={color.vaultMute} />}
        </View>

        {summary && (
          <Pressable
            accessibilityRole="switch"
            accessibilityState={{ checked: home }}
            accessibilityLabel={`Show figures in ${home ? summary.currency : summary.home_currency}`}
            onPress={() => setHome(!home)}
            style={({ pressed }) => [styles.currency, pressed && styles.pressed]}
          >
            <Text style={[styles.currencyCode, !home && styles.currencyOn]}>{summary.currency}</Text>
            <Feather name="repeat" size={10} color={color.vaultMute} />
            <Text style={[styles.currencyCode, home && styles.currencyOn]}>
              {summary.home_currency}
            </Text>
          </Pressable>
        )}
      </View>
    </View>
  )
}

/**
 * Before the first load lands, and after it lands with nothing.
 *
 * The web app's equivalent prints the `python -m seed.reset_demo` line, because
 * on a laptop that is the fix. On a phone the fixtures are already bundled, so
 * an empty result means the live backend answered with nothing — which is a
 * different problem and gets a different sentence.
 */
function Gate({ loading }: { loading: boolean }) {
  const { user, live, reload } = useStore()
  const insets = useSafeAreaInsets()

  return (
    <View style={[styles.gate, { paddingTop: insets.top + 40, paddingBottom: insets.bottom + 40 }]}>
      {loading ? (
        <>
          <ActivityIndicator color={color.teal} />
          <Text style={text.small}>Reading your accounts…</Text>
        </>
      ) : (
        <>
          <Text style={text.eyebrow}>NO DATA FOR “{user.toUpperCase()}”</Text>
          <Text style={[text.h1, styles.gateTitle]}>Nothing to show yet.</Text>
          <Text style={[text.body, styles.gateBody]}>
            {live
              ? 'The backend is set, but it did not return a summary for this profile. Check that the API is running and that the persona exists.'
              : 'The bundled fixtures have no summary for this profile. Try ana, raj or lucia.'}
          </Text>
          <Pressable
            accessibilityRole="button"
            onPress={() => void reload()}
            style={({ pressed }) => [styles.retry, pressed && styles.pressed]}
          >
            <Text style={styles.retryLabel}>Try again</Text>
          </Pressable>
          <PersonaSwitch dark={false} />
        </>
      )}
    </View>
  )
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: color.paper },

  header: { backgroundColor: color.vault, paddingHorizontal: 16, paddingBottom: 10, gap: 10 },
  headerTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  brand: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  brandMark: {
    width: 30,
    height: 30,
    borderRadius: radius.sm,
    backgroundColor: color.teal,
    alignItems: 'center',
    justifyContent: 'center',
  },
  brandMarkText: { fontFamily: font.displaySemi, fontSize: 13, color: '#ffffff', letterSpacing: 0.5 },
  brandName: { fontFamily: font.display, fontSize: 17, color: '#ffffff', letterSpacing: -0.5 },
  brandSub: { fontFamily: font.figureMed, fontSize: 8, letterSpacing: 1.4, color: color.vaultMute },
  headerActions: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  copilotButton: {
    width: 34,
    height: 34,
    borderRadius: radius.sm,
    backgroundColor: color.vault2,
    borderWidth: 1,
    borderColor: color.vaultLine,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pressed: { opacity: 0.7 },

  headerBottom: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    borderTopWidth: 1,
    borderTopColor: color.vaultLine,
    paddingTop: 9,
  },
  status: { flexDirection: 'row', alignItems: 'center', gap: 7, flex: 1 },
  statusDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: color.teal },
  statusDotFixture: { backgroundColor: color.brass },
  statusText: {
    fontFamily: font.figureMed,
    fontSize: 9,
    letterSpacing: 1,
    color: color.vaultInk,
    flexShrink: 1,
  },
  currency: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 4,
    paddingHorizontal: 8,
    borderRadius: radius.sm,
    backgroundColor: color.vault2,
  },
  currencyCode: { fontFamily: font.figureMed, fontSize: 9, letterSpacing: 0.8, color: color.vaultMute },
  currencyOn: { color: '#ffffff' },

  tabBar: {
    backgroundColor: color.vault,
    borderTopWidth: 1,
    borderTopColor: color.vaultLine,
    paddingTop: 6,
  },
  tabItem: { paddingVertical: 2 },
  tabLabel: { fontFamily: font.figureMed, fontSize: 9, letterSpacing: 0.6, marginTop: 2, marginBottom: 4 },
  badge: {
    backgroundColor: color.flag,
    color: '#ffffff',
    fontFamily: font.figureSemi,
    fontSize: 10,
  },

  gate: { flex: 1, backgroundColor: color.paper, padding: 28, gap: 12, justifyContent: 'center' },
  gateTitle: { marginTop: 4 },
  gateBody: { marginBottom: 8 },
  retry: {
    alignSelf: 'flex-start',
    backgroundColor: color.teal,
    paddingVertical: 11,
    paddingHorizontal: 18,
    borderRadius: radius.sm,
  },
  retryLabel: { fontFamily: font.sansSemi, fontSize: 13, color: '#ffffff' },
})
