import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { NextRequest } from 'next/server'
import { GET } from './route'

describe('GET /config', () => {
  const originalEnv = process.env

  beforeEach(() => {
    process.env = { ...originalEnv }
    delete process.env.API_URL
    delete process.env.NEXT_PUBLIC_API_URL
  })

  afterEach(() => {
    process.env = originalEnv
  })

  function makeRequest(headers: Record<string, string> = {}) {
    return new NextRequest('http://ignored.example/config', { headers })
  }

  it('uses same-origin API proxying by default', async () => {
    const response = await GET(
      makeRequest({ host: 'notebook.example.com', 'x-forwarded-proto': 'https' })
    )

    expect(await response.json()).toEqual({ apiUrl: '' })
  })

  it('uses API_URL when the API is deliberately exposed separately', async () => {
    process.env.API_URL = 'https://api.notebook.example.com'

    const response = await GET(makeRequest({ host: 'notebook.example.com' }))

    expect(await response.json()).toEqual({
      apiUrl: 'https://api.notebook.example.com',
    })
  })

  it('supports the legacy build-time override when API_URL is absent', async () => {
    process.env.NEXT_PUBLIC_API_URL = 'https://legacy-api.example.com'

    const response = await GET(makeRequest())

    expect(await response.json()).toEqual({
      apiUrl: 'https://legacy-api.example.com',
    })
  })

  it('does not derive a credential destination from untrusted Host headers', async () => {
    const response = await GET(
      makeRequest({ host: 'legit.example.com@evil.example.com' })
    )

    expect(await response.json()).toEqual({ apiUrl: '' })
  })
})
