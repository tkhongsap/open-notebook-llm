export const DEFAULT_INTERNAL_API_PROXY_TIMEOUT_MS = 600_000

/**
 * Resolve the server-side /api rewrite timeout.
 *
 * Next.js treats zero as its 30-second default, so only positive finite values
 * are accepted. Invalid values fall back to the same ten-minute budget used by
 * the browser API client.
 */
export function getInternalApiProxyTimeout(
  rawValue = process.env.INTERNAL_API_PROXY_TIMEOUT_MS
): number {
  if (!rawValue || rawValue.trim() === '') {
    return DEFAULT_INTERNAL_API_PROXY_TIMEOUT_MS
  }

  const parsed = Number(rawValue)
  return Number.isFinite(parsed) && parsed > 0
    ? parsed
    : DEFAULT_INTERNAL_API_PROXY_TIMEOUT_MS
}
