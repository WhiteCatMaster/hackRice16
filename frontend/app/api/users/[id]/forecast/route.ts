import { NextResponse } from 'next/server'

import { getForecast } from '@/lib/api'

export const dynamic = 'force-dynamic'

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  const target = new URL(request.url).searchParams.get('target') ?? undefined
  const data = await getForecast(id, target)
  if (!data) {
    return NextResponse.json({ error: `No forecast for '${id}'` }, { status: 404 })
  }
  return NextResponse.json(data)
}
