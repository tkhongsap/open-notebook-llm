import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { GET } from './route'

describe('GET /healthz', () => {
  const originalEnv = process.env
  const originalFetch = global.fetch
  const fetchMock = vi.fn()

  beforeEach(() => {
    process.env = { ...originalEnv }
    delete process.env.INTERNAL_API_URL
    fetchMock.mockReset()
    global.fetch = fetchMock
  })

  afterEach(() => {
    process.env = originalEnv
    global.fetch = originalFetch
  })

  it('returns ready only when the internal API readiness check passes', async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200 } as Response)

    const response = await GET()

    expect(response.status).toBe(200)
    expect(await response.json()).toEqual({ status: 'ready' })
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:5055/ready',
      expect.objectContaining({ cache: 'no-store' })
    )
  })

  it('uses the configured internal API URL without a duplicate slash', async () => {
    process.env.INTERNAL_API_URL = 'http://open-notebook-api:5055/'
    fetchMock.mockResolvedValue({ ok: true, status: 200 } as Response)

    await GET()

    expect(fetchMock).toHaveBeenCalledWith(
      'http://open-notebook-api:5055/ready',
      expect.any(Object)
    )
  })

  it('returns 503 when the API reports not ready', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 503 } as Response)

    const response = await GET()

    expect(response.status).toBe(503)
    expect(await response.json()).toEqual({
      status: 'not_ready',
      apiStatus: 503,
    })
  })

  it('returns 503 when the API cannot be reached', async () => {
    fetchMock.mockRejectedValue(new Error('connection refused'))

    const response = await GET()

    expect(response.status).toBe(503)
    expect(await response.json()).toEqual({
      status: 'not_ready',
      apiStatus: null,
    })
  })
})
