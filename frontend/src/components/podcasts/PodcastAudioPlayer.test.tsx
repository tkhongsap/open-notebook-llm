import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { PodcastAudioPlayer } from './PodcastAudioPlayer'
import type { PodcastEpisode } from '@/lib/types/podcasts'

vi.mock('@/lib/api/podcasts', () => ({
  resolvePodcastAssetUrl: vi.fn(async () => 'http://localhost/audio/overview.mp3'),
}))

vi.mock('@/lib/api/client', () => ({
  default: { get: vi.fn() },
}))

const episode: PodcastEpisode = {
  id: 'episode:1',
  name: 'Evidence & Strategy',
  episode_profile: {
    id: 'episode_profile:1',
    name: 'overview',
    description: '',
    speaker_config: null,
    default_briefing: '',
    num_segments: 4,
  },
  speaker_profile: {
    id: 'speaker_profile:1',
    name: 'hosts',
    description: '',
    speakers: [],
  },
  briefing: 'Explain the evidence',
  audio_file: 'episodes/one/overview.mp3',
  notebook_ids: ['notebook:one'],
  job_status: 'completed',
}

describe('PodcastAudioPlayer', () => {
  it('provides playback, speed control, and a safe MP3 download', async () => {
    render(<PodcastAudioPlayer episode={episode} />)

    const player = await screen.findByLabelText('podcasts.playAudioOverview')
    expect(player).toHaveAttribute('src', 'http://localhost/audio/overview.mp3')

    const speed = screen.getByRole('button', { name: 'podcasts.changePlaybackSpeed' })
    expect(speed).toHaveTextContent('1×')
    fireEvent.click(speed)
    expect(speed).toHaveTextContent('1.25×')

    const download = screen.getByRole('link', { name: /podcasts.downloadAudio/ })
    expect(download).toHaveAttribute('download', 'Evidence-Strategy.mp3')
    expect(download).toHaveAttribute('href', 'http://localhost/audio/overview.mp3')

    fireEvent.loadedMetadata(player)
    await waitFor(() => expect((player as HTMLAudioElement).playbackRate).toBe(1.25))
  })
})
