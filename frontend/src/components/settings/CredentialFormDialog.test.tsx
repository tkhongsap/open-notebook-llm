import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  CredentialFormDialog,
  LOCAL_AI_DEFAULT_BASE_URL,
} from './CredentialFormDialog'


const createMutate = vi.fn()
const updateMutate = vi.fn()
const providerQuery = vi.hoisted(() => ({
  data: [
    {
      name: 'openai_compatible',
      display_name: 'Local AI / OpenAI Compatible',
      modalities: ['language', 'embedding', 'speech_to_text', 'text_to_speech'],
      docs_url: null,
    },
  ],
}))

vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))

vi.mock('@/lib/hooks/use-credentials', () => ({
  useCreateCredential: () => ({ isPending: false, mutate: createMutate }),
  useUpdateCredential: () => ({ isPending: false, mutate: updateMutate }),
}))

vi.mock('@/lib/hooks/use-providers', () => ({
  useProviders: () => providerQuery,
}))

describe('CredentialFormDialog local gateway preset', () => {
  beforeEach(() => {
    createMutate.mockReset()
    updateMutate.mockReset()
  })

  it('prefills the loopback-only LocalAISandbox endpoint', async () => {
    render(
      <CredentialFormDialog
        open
        onOpenChange={vi.fn()}
        provider="openai_compatible"
      />
    )

    fireEvent.click(screen.getByRole('button', { name: 'apiKeys.useLocalGateway' }))

    expect(screen.getByLabelText('apiKeys.configName')).toHaveValue('LocalAISandbox')
    expect(screen.getByLabelText('apiKeys.baseUrl')).toHaveValue(LOCAL_AI_DEFAULT_BASE_URL)

    fireEvent.change(screen.getByLabelText(/models\.apiKey/), {
      target: { value: 'test-gateway-key' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'apiKeys.addConfig' }))

    await waitFor(() => {
      expect(createMutate).toHaveBeenCalledWith(
        {
          name: 'LocalAISandbox',
          provider: 'openai_compatible',
          modalities: ['language', 'embedding', 'speech_to_text', 'text_to_speech'],
          api_key: 'test-gateway-key',
          base_url: LOCAL_AI_DEFAULT_BASE_URL,
        },
        expect.objectContaining({ onSuccess: expect.any(Function) })
      )
    })
  })

  it('requires an endpoint for a generic OpenAI-compatible provider', () => {
    render(
      <CredentialFormDialog
        open
        onOpenChange={vi.fn()}
        provider="openai_compatible"
      />
    )

    fireEvent.change(screen.getByLabelText('apiKeys.configName'), {
      target: { value: 'Custom server' },
    })

    expect(screen.getByRole('button', { name: 'apiKeys.addConfig' })).toBeDisabled()
  })
})
