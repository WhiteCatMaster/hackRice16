import { NextResponse } from 'next/server'

import { getActivity } from '@/lib/api'

export const dynamic = 'force-dynamic'

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  const limit = Number(new URL(request.url).searchParams.get('limit') ?? 6)
  return NextResponse.json(await getActivity(id, Number.isFinite(limit) ? limit : 6))
}
