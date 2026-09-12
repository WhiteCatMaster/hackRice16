import { NextResponse } from 'next/server'

import { checkAffordability } from '@/lib/api'

export const dynamic = 'force-dynamic'

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  const body = await request.json().catch(() => ({}))
  const amount = Number(body?.amount)
  if (!Number.isFinite(amount) || amount <= 0) {
    return NextResponse.json({ error: 'amount must be a positive number' }, { status: 400 })
  }

  const data = await checkAffordability(id, amount, body?.description)
  if (!data) {
    // Mock mode, or the backend is down. The honest answer is "ask the backend",
    // not a number we made up here.
    return NextResponse.json(
      { error: 'Affordability needs the live engine. Set LANDED_API_BASE.' },
      { status: 503 },
    )
  }
  return NextResponse.json(data)
}
