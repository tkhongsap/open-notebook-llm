import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useNotebookChat } from './use-notebook-chat'
import { chatApi } from '@/lib/api/chat'
import { QUERY_KEYS } from '@/lib/api/query-client'

vi.mock('@/lib/api/chat', () => ({
  chatApi: {
    listSessions: vi.fn(),
    getSession: vi.fn(),
    createSession: vi.fn(),
    updateSession: vi.fn(),
    deleteSession: vi.fn(),
    buildContext: vi.fn(),
    sendMessage: vi.fn(),
  },
}))

const localSession = {
  id: 'chat_session:one',
  title: 'Research',
  notebook_id: 'notebook:one',
  created: '2026-09-01T00:00:00Z',
  updated: '2026-09-01T00:00:00Z',
  model_override: 'model:local',
  messages: [],
}

describe('useNotebookChat model selection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(chatApi.listSessions).mockResolvedValue([localSession])
    vi.mocked(chatApi.getSession).mockResolvedValue(localSession)
    vi.mocked(chatApi.buildContext).mockResolvedValue({
      context: { sources: [], notes: [] },
      token_count: 0,
      char_count: 0,
    })
  })

  it('awaits and caches the session override before the next message can send', async () => {
    const cloudSession = { ...localSession, model_override: 'model:cloud' }
    vi.mocked(chatApi.updateSession).mockResolvedValue(cloudSession)
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )

    const { result } = renderHook(() => useNotebookChat({
      notebookId: 'notebook:one',
      sources: [],
      notes: [],
      contextSelections: { sources: {}, notes: {} },
    }), { wrapper })

    await waitFor(() => {
      expect(result.current.currentSessionId).toBe('chat_session:one')
      expect(result.current.currentSession?.model_override).toBe('model:local')
    })

    await act(async () => {
      await result.current.setModelOverride('model:cloud')
    })

    expect(chatApi.updateSession).toHaveBeenCalledWith(
      'chat_session:one',
      { model_override: 'model:cloud' }
    )
    expect(
      queryClient.getQueryData<{ model_override?: string }>(
        QUERY_KEYS.notebookChatSession('chat_session:one')
      )?.model_override
    ).toBe('model:cloud')
    await waitFor(() => {
      expect(result.current.currentSession?.model_override).toBe('model:cloud')
    })
  })
})
