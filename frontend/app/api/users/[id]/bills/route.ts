import { NextResponse } from 'next/server'

import { getBills } from '@/lib/api'

export const dynamic = 'force-dynamic'

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  const data = await getBills(id)
  if (!data) {
    return NextResponse.json({ error: `No bills for '${id}'` }, { status: 404 })
  }
  return NextResponse.json(data)
}
