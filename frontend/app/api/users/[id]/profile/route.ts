import { NextResponse } from 'next/server'

import { getProfile } from '@/lib/api'

export const dynamic = 'force-dynamic'

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  const data = await getProfile(id)
  if (!data) {
    return NextResponse.json({ error: `No profile for '${id}'` }, { status: 404 })
  }
  return NextResponse.json(data)
}
