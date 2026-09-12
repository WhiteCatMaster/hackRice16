// Babel, for Jest only.
//
// Metro ships its own default preset, so `expo start` never needed a config
// here. `babel-jest` does: the React Native packages it pulls in are written in
// Flow, and without `babel-preset-expo` the first `value(id: TimeoutID)` in
// @react-native/jest-preset is a syntax error.

module.exports = function babel(api) {
  api.cache(true)
  return { presets: ['babel-preset-expo'] }
}
