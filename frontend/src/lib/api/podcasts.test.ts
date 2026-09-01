import { beforeEach, describe, expect, it, vi } from 'vitest'

import { resolvePodcastAssetUrl } from './podcasts'
import { getApiUrl } from '@/lib/config'

vi.mock('@/lib/config', () => ({ getApiUrl: vi.fn() }))

describe('resolvePodcastAssetUrl', () => {
  beforeEach(() => {
    vi.mocked(getApiUrl).mockReset()
  })

  it('makes protected API paths absolute in same-origin mode', async () => {
    vi.mocked(getApiUrl).mockResolvedValue('')

    await expect(
      resolvePodcastAssetUrl('/api/podcasts/episodes/episode:one/audio')
    ).resolves.toBe(
      `${window.location.origin}/api/podcasts/episodes/episode:one/audio`
    )
  })

  it('preserves the configured remote API origin without duplicating api', async () => {
    vi.mocked(getApiUrl).mockResolvedValue('https://notebook-api.example.com/')

    await expect(
      resolvePodcastAssetUrl('/api/podcasts/episodes/episode:one/audio')
    ).resolves.toBe(
      'https://notebook-api.example.com/api/podcasts/episodes/episode:one/audio'
    )
  })

  it('does not rewrite an already absolute asset URL', async () => {
    await expect(
      resolvePodcastAssetUrl('https://cdn.example.com/overview.mp3')
    ).resolves.toBe('https://cdn.example.com/overview.mp3')
    expect(getApiUrl).not.toHaveBeenCalled()
  })
})
