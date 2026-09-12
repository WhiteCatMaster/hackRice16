import { NextResponse } from 'next/server'

import { chat } from '@/lib/api'

export const dynamic = 'force-dynamic'

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}))
  if (!body.message) {
    return NextResponse.json({ error: 'message is required' }, { status: 400 })
  }
  const data = await chat(body)
  if (!data) {
    return NextResponse.json({ error: 'The agent is not available' }, { status: 502 })
  }
  return NextResponse.json(data)
}
