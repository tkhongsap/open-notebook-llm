import { NextResponse } from 'next/server'

const READY_TIMEOUT_MS = 3000

export async function GET() {
  const internalApiUrl = (
    process.env.INTERNAL_API_URL || 'http://localhost:5055'
  ).replace(/\/$/, '')

  try {
    const response = await fetch(`${internalApiUrl}/ready`, {
      cache: 'no-store',
      signal: AbortSignal.timeout(READY_TIMEOUT_MS),
    })

    if (!response.ok) {
      return NextResponse.json(
        { status: 'not_ready', apiStatus: response.status },
        { status: 503 }
      )
    }

    return NextResponse.json({ status: 'ready' })
  } catch {
    return NextResponse.json(
      { status: 'not_ready', apiStatus: null },
      { status: 503 }
    )
  }
}
