// The icon set, stubbed.
//
// `@expo/vector-icons` pulls in `expo-font` → `expo-asset`, which npm left
// nested under `expo/` rather than hoisted; Metro resolves it, Jest's plain
// node resolution does not. Mocking the glyphs is the better answer anyway:
// a font glyph is not something a test can assert on, and a `testID` is.
//
// Jest picks this up automatically — a `__mocks__` folder next to
// `node_modules` mocks a package with no `jest.mock()` call at the test site.

import { View } from 'react-native'

type Props = { name: string; size?: number; color?: string }

function iconSet(family: string) {
  return function Icon({ name }: Props) {
    return <View testID={`icon-${name}`} accessibilityElementsHidden data-family={family} />
  }
}

export const Feather = iconSet('Feather')
export const AntDesign = iconSet('AntDesign')
export const Entypo = iconSet('Entypo')
export const EvilIcons = iconSet('EvilIcons')
export const FontAwesome = iconSet('FontAwesome')
export const FontAwesome5 = iconSet('FontAwesome5')
export const FontAwesome6 = iconSet('FontAwesome6')
export const Fontisto = iconSet('Fontisto')
export const Foundation = iconSet('Foundation')
export const Ionicons = iconSet('Ionicons')
export const MaterialCommunityIcons = iconSet('MaterialCommunityIcons')
export const MaterialIcons = iconSet('MaterialIcons')
export const Octicons = iconSet('Octicons')
export const SimpleLineIcons = iconSet('SimpleLineIcons')
export const Zocial = iconSet('Zocial')
export const createIconSet = () => iconSet('custom')
