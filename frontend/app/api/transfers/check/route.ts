import { NextResponse } from 'next/server'

import { checkTransfer } from '@/lib/api'

export const dynamic = 'force-dynamic'

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}))
  const data = await checkTransfer(body)
  if (!data) {
    return NextResponse.json(
      { error: `No risk check available for scenario '${body.scenario}'` },
      { status: 404 },
    )
  }
  return NextResponse.json(data)
}
