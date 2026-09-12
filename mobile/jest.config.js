// Jest, for the phone app.
//
// `jest-expo/ios` rather than the bare `jest-expo` preset: the universal one
// runs every suite four times over (ios, android, web, node), and nothing here
// branches on the platform except `resolveBase`, which picks its own
// `Platform.OS` in the one test that cares.

module.exports = {
  preset: 'jest-expo/ios',
  setupFilesAfterEnv: ['<rootDir>/jest.setup.tsx'],
  testPathIgnorePatterns: ['/node_modules/', '/.expo/', '/dist/'],
  collectCoverageFrom: [
    'app/**/*.{ts,tsx}',
    'components/**/*.{ts,tsx}',
    'lib/**/*.{ts,tsx}',
    '!**/*.d.ts',
  ],
}
