import { NextRequest, NextResponse } from 'next/server'

/**
 * Runtime configuration endpoint.
 *
 * The default is same-origin: browser API calls use `/api/*`, and Next.js
 * proxies them to `INTERNAL_API_URL`. This works behind one HTTPS ingress on
 * Docker, Fly.io, Railway, and Render without publishing port 5055.
 *
 * Set `API_URL` only when the browser must call a separately exposed API.
 */
export async function GET(request: NextRequest) {
  void request
  const explicitApiUrl = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL

  return NextResponse.json({
    apiUrl: explicitApiUrl || '',
  })
}
