import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { NotebookAudioOverviews } from './NotebookAudioOverviews'
import {
  useDeletePodcastEpisode,
  usePodcastEpisodes,
  useRetryPodcastEpisode,
} from '@/lib/hooks/use-podcasts'

vi.mock('@/lib/hooks/use-podcasts', () => ({
  usePodcastEpisodes: vi.fn(),
  useDeletePodcastEpisode: vi.fn(),
  useRetryPodcastEpisode: vi.fn(),
}))

vi.mock('@/components/podcasts/EpisodeCard', () => ({
  EpisodeCard: ({ episode }: { episode: { name: string } }) => <div>{episode.name}</div>,
}))

describe('NotebookAudioOverviews', () => {
  beforeEach(() => {
    vi.mocked(useDeletePodcastEpisode).mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
    } as never)
    vi.mocked(useRetryPodcastEpisode).mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
    } as never)
  })

  it('requests and renders only the current notebook episodes', () => {
    vi.mocked(usePodcastEpisodes).mockReturnValue({
      episodes: [
        { id: 'episode:1', name: 'Notebook One Overview' },
      ],
      isLoading: false,
      isError: false,
    } as never)

    render(<NotebookAudioOverviews notebookId="notebook:one" />)

    expect(usePodcastEpisodes).toHaveBeenCalledWith({ notebookId: 'notebook:one' })
    expect(screen.getByText('Notebook One Overview')).toBeInTheDocument()
    expect(screen.getByText('podcasts.audioOverviews')).toBeInTheDocument()
  })

  it('stays out of the Studio when a notebook has no episodes', () => {
    vi.mocked(usePodcastEpisodes).mockReturnValue({
      episodes: [],
      isLoading: false,
      isError: false,
    } as never)

    const { container } = render(<NotebookAudioOverviews notebookId="notebook:empty" />)
    expect(container).toBeEmptyDOMElement()
  })
})
