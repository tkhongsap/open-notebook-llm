import { describe, expect, it } from 'vitest'

import {
  DEFAULT_INTERNAL_API_PROXY_TIMEOUT_MS,
  getInternalApiProxyTimeout,
} from './api-proxy-timeout'

describe('getInternalApiProxyTimeout', () => {
  it('uses ten minutes by default for slow local inference', () => {
    expect(getInternalApiProxyTimeout(undefined)).toBe(
      DEFAULT_INTERNAL_API_PROXY_TIMEOUT_MS
    )
  })

  it('accepts a positive finite override', () => {
    expect(getInternalApiProxyTimeout('900000')).toBe(900_000)
  })

  it.each(['', '0', '-1', 'not-a-number', 'Infinity'])(
    'rejects an unsafe override: %s',
    (value) => {
      expect(getInternalApiProxyTimeout(value)).toBe(
        DEFAULT_INTERNAL_API_PROXY_TIMEOUT_MS
      )
    }
  )
})
