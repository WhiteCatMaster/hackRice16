import { NextResponse } from 'next/server'

import { confirmAction } from '@/lib/api'

export const dynamic = 'force-dynamic'

// begin.md design rule 2: the agent proposes, the user approves, and only then
// does anything reach Nessie. This route is the gate.
export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  const body = await request.json().catch(() => ({}))
  return NextResponse.json(await confirmAction(id, body))
}
