import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { sourceChatApi } from '@/lib/api/source-chat'

import { useSourceChat } from './use-source-chat'

vi.mock('@/lib/api/source-chat', () => ({
  sourceChatApi: {
    listSessions: vi.fn(),
    getSession: vi.fn(),
    createSession: vi.fn(),
    updateSession: vi.fn(),
    deleteSession: vi.fn(),
    sendMessage: vi.fn(),
  },
}))

const localSession = {
  id: 'source_chat_session:one',
  title: 'Research',
  source_id: 'source:one',
  created: '2026-09-01T00:00:00Z',
  updated: '2026-09-01T00:00:00Z',
  model_override: 'model:local',
  messages: [],
}

describe('useSourceChat model selection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(sourceChatApi.listSessions).mockResolvedValue([localSession])
    vi.mocked(sourceChatApi.getSession).mockResolvedValue(localSession)
  })

  it('persists and caches a model switch before the selector resolves', async () => {
    const cloudSession = { ...localSession, model_override: 'model:cloud' }
    vi.mocked(sourceChatApi.updateSession).mockResolvedValue(cloudSession)
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )

    const { result } = renderHook(() => useSourceChat('source:one'), { wrapper })

    await waitFor(() => {
      expect(result.current.currentSessionId).toBe('source_chat_session:one')
      expect(result.current.currentSession?.model_override).toBe('model:local')
    })

    await act(async () => {
      await result.current.setModelOverride('model:cloud')
    })

    expect(sourceChatApi.updateSession).toHaveBeenCalledWith(
      'source:one',
      'source_chat_session:one',
      { model_override: 'model:cloud' }
    )
    expect(
      queryClient.getQueryData<{ model_override?: string }>([
        'sourceChatSession',
        'source:one',
        'source_chat_session:one',
      ])?.model_override
    ).toBe('model:cloud')
  })
})
