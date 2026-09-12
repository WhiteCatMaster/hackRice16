import { NextResponse } from 'next/server'

import { chat } from '@/lib/api'
import { MODEL_KEY_HEADERS, isChatError } from '@/lib/contract'

export const dynamic = 'force-dynamic'

/**
 * The browser holds the user's model key; this route only passes it on.
 *
 * Nothing here reads the key, logs it or keeps it — it is copied from the
 * incoming request to the outgoing one and forgotten, the same contract the
 * backend keeps in `backend/agent/keys.py`. A phone skips this hop entirely and
 * sends the headers to the backend itself.
 */
function forwarded(request: Request): Record<string, string> {
  const out: Record<string, string> = {}
  for (const name of Object.values(MODEL_KEY_HEADERS)) {
    const value = request.headers.get(name)
    if (value) out[name] = value
  }
  return out
}

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}))
  if (!body.message) {
    return NextResponse.json({ error: 'message is required' }, { status: 400 })
  }
  const data = await chat(body, forwarded(request))
  if (!data) {
    return NextResponse.json({ error: 'The agent is not available' }, { status: 502 })
  }
  // A refused key comes back as the backend's own explanation, with its status,
  // because the person who can fix it is the one reading the screen.
  if (isChatError(data)) return NextResponse.json(data, { status: 400 })
  return NextResponse.json(data)
}
