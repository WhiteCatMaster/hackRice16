// Metro, taught to look one directory up.
//
// The app bundles P1's fixtures straight out of `mocks/` at the repository
// root, the same files the web app reads at request time. That is what keeps
// mock mode honest: one set of fixtures, no second copy inside mobile/ to drift
// away from the first. Metro refuses to resolve anything outside the project
// root unless the folder is watched, so `../mocks` is watched here and the
// requires in lib/mocks.ts reach it.
//
// Only the fixtures are shared. This is deliberately not a monorepo config —
// npm installs this app's dependencies nested rather than hoisted, so pinning
// `nodeModulesPaths` or setting `disableHierarchicalLookup` here breaks
// resolution of anything a package keeps in its own node_modules.

const path = require('node:path')

const { getDefaultConfig } = require('expo/metro-config')

const config = getDefaultConfig(__dirname)

config.watchFolders = [path.resolve(__dirname, '..', 'mocks')]

module.exports = config
