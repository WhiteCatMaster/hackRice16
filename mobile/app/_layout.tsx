// The root: fonts, the data store, and the one stack the tabs live inside.
//
// One modal hangs off that stack: the model-key sheet. The copilot used to be
// the modal and is now a tab — see app/(tabs)/copilot.tsx for why.

import {
  Fraunces_500Medium,
  Fraunces_600SemiBold,
  useFonts,
} from '@expo-google-fonts/fraunces'
import {
  IBMPlexMono_400Regular,
  IBMPlexMono_500Medium,
  IBMPlexMono_600SemiBold,
} from '@expo-google-fonts/ibm-plex-mono'
import {
  IBMPlexSans_400Regular,
  IBMPlexSans_500Medium,
  IBMPlexSans_600SemiBold,
} from '@expo-google-fonts/ibm-plex-sans'
import { Stack } from 'expo-router'
import * as SplashScreen from 'expo-splash-screen'
import { StatusBar } from 'expo-status-bar'
import { useEffect } from 'react'
import { SafeAreaProvider } from 'react-native-safe-area-context'

import { StoreProvider } from '../lib/store'
import { color } from '../lib/theme'

SplashScreen.preventAutoHideAsync().catch(() => {
  // Already hidden, or the module is unavailable on this platform. Not worth a
  // crash on the way into the app.
})

export default function RootLayout() {
  const [fontsReady, fontError] = useFonts({
    Fraunces_500Medium,
    Fraunces_600SemiBold,
    IBMPlexSans_400Regular,
    IBMPlexSans_500Medium,
    IBMPlexSans_600SemiBold,
    IBMPlexMono_400Regular,
    IBMPlexMono_500Medium,
    IBMPlexMono_600SemiBold,
  })

  useEffect(() => {
    // A font that fails to download is a worse-looking app, not a broken one —
    // React Native falls back to the system face. Holding the splash screen
    // over it forever would be the actual failure, so drop it either way.
    if (fontsReady || fontError) SplashScreen.hideAsync().catch(() => {})
  }, [fontsReady, fontError])

  if (!fontsReady && !fontError) return null

  return (
    <SafeAreaProvider>
      <StoreProvider>
        <StatusBar style="light" />
        <Stack
          screenOptions={{
            headerShown: false,
            contentStyle: { backgroundColor: color.paper },
          }}
        >
          <Stack.Screen name="(tabs)" />
          <Stack.Screen
            name="model-key"
            options={{
              presentation: 'modal',
              headerShown: false,
              // iOS sheets show the paper through the rounded corners; matching
              // the colour stops a white seam at the top of the modal.
              contentStyle: { backgroundColor: color.paper },
            }}
          />
        </Stack>
      </StoreProvider>
    </SafeAreaProvider>
  )
}
