import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GeneratePodcastDialog } from './GeneratePodcastDialog'
import { useNotebooks } from '@/lib/hooks/use-notebooks'
import {
  useEpisodeProfiles,
  useGeneratePodcast,
  useSpeakerProfiles,
} from '@/lib/hooks/use-podcasts'
import { useQueries } from '@tanstack/react-query'
import { chatApi } from '@/lib/api/chat'

vi.mock('@/lib/hooks/use-notebooks', () => ({ useNotebooks: vi.fn() }))
vi.mock('@/lib/hooks/use-podcasts', () => ({
  useEpisodeProfiles: vi.fn(),
  useSpeakerProfiles: vi.fn(),
  useGeneratePodcast: vi.fn(),
}))
vi.mock('@tanstack/react-query', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@tanstack/react-query')>()),
  useQueries: vi.fn(),
}))
vi.mock('@/lib/api/chat', () => ({
  chatApi: { buildContext: vi.fn() },
}))
vi.mock('@/lib/api/sources', () => ({ sourcesApi: { list: vi.fn() } }))
vi.mock('@/lib/api/notes', () => ({ notesApi: { list: vi.fn() } }))
vi.mock('@/lib/hooks/use-toast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}))
vi.mock('./ContentSelectionPanel', () => ({
  ContentSelectionPanel: () => <div data-testid="content-selection" />,
}))

const readyEpisodeProfile = {
  id: 'episode_profile:overview',
  name: 'overview',
  description: '',
  speaker_config: 'speaker_profile:hosts',
  speaker_config_name: 'hosts',
  outline_llm: 'model:language',
  transcript_llm: 'model:language',
  default_briefing: 'Explain',
  num_segments: 4,
}

const readySpeakerProfile = {
  id: 'speaker_profile:hosts',
  name: 'hosts',
  description: '',
  voice_model: 'model:voice',
  speakers: [],
}

describe('GeneratePodcastDialog notebook workflow', () => {
  const mutateAsync = vi.fn(async () => ({ job_id: 'command:one' }))

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useNotebooks).mockReturnValue({
      data: [{ id: 'notebook:one', name: 'Research', description: '' }],
      isLoading: false,
    } as never)
    vi.mocked(useEpisodeProfiles).mockReturnValue({
      episodeProfiles: [readyEpisodeProfile],
      isLoading: false,
    } as never)
    vi.mocked(useSpeakerProfiles).mockReturnValue({
      speakerProfiles: [readySpeakerProfile],
      isLoading: false,
    } as never)
    vi.mocked(useGeneratePodcast).mockReturnValue({
      mutateAsync,
      isPending: false,
    } as never)
    vi.mocked(useQueries).mockImplementation((options: never) => {
      const queryKey = (options as { queries: Array<{ queryKey: string[] }> }).queries[0]?.queryKey
      if (queryKey?.[0] === 'sources') {
        return [{
          data: [{
            id: 'source:one',
            title: 'Evidence',
            asset: null,
            embedded: true,
            embedded_chunks: 1,
            insights_count: 0,
            created: '2026-01-01',
            updated: '2026-01-01',
          }],
          isFetching: false,
        }] as never
      }
      return [{ data: [], isFetching: false }] as never
    })
    vi.mocked(chatApi.buildContext).mockResolvedValue({
      context: { sources: [{ id: 'source:one', content: 'Evidence' }] },
      token_count: 12,
      char_count: 80,
    } as never)
  })

  it('prefills, scopes, and submits an Audio Overview for the current notebook', async () => {
    render(
      <GeneratePodcastDialog
        open
        onOpenChange={vi.fn()}
        initialNotebookId="notebook:one"
        initialNotebookName="Research"
      />
    )

    await waitFor(() => {
      expect(screen.getByLabelText('podcasts.episodeName')).toHaveValue(
        'podcasts.defaultEpisodeName'
      )
    })

    fireEvent.click(screen.getByRole('button', { name: 'podcasts.generate' }))

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledOnce())
    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        episode_profile: 'overview',
        speaker_profile: 'speaker_profile:hosts',
        episode_name: 'podcasts.defaultEpisodeName',
        notebook_ids: ['notebook:one'],
      })
    )
  })

  it('blocks generation and links to setup when no profile has language and TTS models', () => {
    vi.mocked(useEpisodeProfiles).mockReturnValue({
      episodeProfiles: [{
        ...readyEpisodeProfile,
        outline_llm: null,
        transcript_llm: null,
      }],
      isLoading: false,
    } as never)
    vi.mocked(useSpeakerProfiles).mockReturnValue({
      speakerProfiles: [{ ...readySpeakerProfile, voice_model: null }],
      isLoading: false,
    } as never)

    render(<GeneratePodcastDialog open onOpenChange={vi.fn()} />)

    expect(screen.getByText('podcasts.audioSetupRequired')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /podcasts.configureAudio/ })).toHaveAttribute(
      'href',
      '/podcasts?tab=templates'
    )
    expect(screen.getByRole('button', { name: 'podcasts.generate' })).toBeDisabled()
  })
})
