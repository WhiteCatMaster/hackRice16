// The fixtures, bundled.
//
// The web app reads `mocks/` off disk at request time. A phone has no
// repository to read, so Metro bundles the same files into the app instead —
// see metro.config.js, which watches `../mocks` so these requires resolve.
//
// Every path is a literal on purpose. Metro resolves `require` at build time,
// so `require(\`../../mocks/api_users_${user}_summary.json\`)` bundles nothing
// and fails at runtime. The map is the price of static bundling.

/* eslint-disable @typescript-eslint/no-var-requires */

type Json = Record<string, unknown>

const BY_USER: Record<string, Record<string, Json>> = {
  ana: {
    summary: require('../../mocks/api_users_ana_summary.json'),
    bills: require('../../mocks/api_users_ana_bills.json'),
    credit: require('../../mocks/api_users_ana_credit.json'),
    alerts: require('../../mocks/api_users_ana_alerts.json'),
    forecast: require('../../mocks/api_users_ana_forecast.json'),
    snapshot: require('../../mocks/ana_snapshot.json'),
  },
  raj: {
    summary: require('../../mocks/api_users_raj_summary.json'),
    bills: require('../../mocks/api_users_raj_bills.json'),
    credit: require('../../mocks/api_users_raj_credit.json'),
    alerts: require('../../mocks/api_users_raj_alerts.json'),
    forecast: require('../../mocks/api_users_raj_forecast.json'),
    snapshot: require('../../mocks/raj_snapshot.json'),
  },
  lucia: {
    summary: require('../../mocks/api_users_lucia_summary.json'),
    bills: require('../../mocks/api_users_lucia_bills.json'),
    credit: require('../../mocks/api_users_lucia_credit.json'),
    alerts: require('../../mocks/api_users_lucia_alerts.json'),
    forecast: require('../../mocks/api_users_lucia_forecast.json'),
    snapshot: require('../../mocks/lucia_snapshot.json'),
  },
}

const TRANSFER_CHECKS: Record<string, Json> = {
  fake_landlord: require('../../mocks/api_transfers_check_fake_landlord.json'),
  immigration_fine: require('../../mocks/api_transfers_check_immigration_fine.json'),
  legit_roommate: require('../../mocks/api_transfers_check_legit_roommate.json'),
}

const CHAT: Json = require('../../mocks/api_chat_response.json')

/** One persona's fixture, or null if the persona is not one of the three. */
export function fixture<T>(user: string, kind: keyof (typeof BY_USER)['ana']): T | null {
  return (BY_USER[user]?.[kind] as T | undefined) ?? null
}

export function transferFixture<T>(scenario: string): T | null {
  return (TRANSFER_CHECKS[scenario] as T | undefined) ?? null
}

export function chatFixture<T>(): T {
  return CHAT as T
}
