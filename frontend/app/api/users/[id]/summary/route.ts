import { NextResponse } from 'next/server'

import { getSummary } from '@/lib/api'

export const dynamic = 'force-dynamic'

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  const data = await getSummary(id)
  if (!data) {
    return NextResponse.json({ error: `No summary for '${id}'` }, { status: 404 })
  }
  return NextResponse.json(data)
}
