import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ModelSelector } from './ModelSelector'
import { useModelRouting } from '@/lib/hooks/use-models'

vi.mock('@/lib/hooks/use-models', () => ({
  useModelRouting: vi.fn(),
}))

vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

const routingCatalog = {
  policy: 'hybrid' as const,
  default_model_id: 'model:local',
  models: [
    {
      id: 'model:local',
      name: 'sandbox/qwen',
      provider: 'openai_compatible',
      provider_display_name: 'Local AI / OpenAI Compatible',
      location: 'local' as const,
      configuration_source: 'credential' as const,
      configured: true,
      allowed: true,
      selectable: true,
      unavailable_reason: null,
      is_default: true,
    },
    {
      id: 'model:cloud',
      name: 'openai/gpt-4.1-mini',
      provider: 'openrouter',
      provider_display_name: 'OpenRouter',
      location: 'cloud' as const,
      configuration_source: 'environment' as const,
      configured: true,
      allowed: true,
      selectable: true,
      unavailable_reason: null,
      is_default: false,
    },
  ],
}

describe('hybrid model selector', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useModelRouting).mockReturnValue({
      data: routingCatalog,
      isLoading: false,
    } as never)
  })

  it('groups local and frontier models and saves the explicit cloud choice', async () => {
    const onModelChange = vi.fn(async () => undefined)
    render(
      <ModelSelector
        currentModel="model:local"
        onModelChange={onModelChange}
      />
    )

    expect(screen.getByText('modelRouting.privateLocal')).toBeInTheDocument()
    expect(screen.getByText('modelRouting.frontierCloud')).toBeInTheDocument()
    expect(screen.getAllByText('sandbox/qwen').length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('button', { name: /openai\/gpt-4\.1-mini/ }))
    expect(screen.getByText('modelRouting.cloudPrivacyNotice')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'common.saveChanges' }))

    await waitFor(() => {
      expect(onModelChange).toHaveBeenCalledWith('model:cloud')
    })
  })

  it('disables policy-blocked cloud models with an actionable reason', () => {
    vi.mocked(useModelRouting).mockReturnValue({
      data: {
        ...routingCatalog,
        policy: 'local-only',
        models: routingCatalog.models.map(model => model.id === 'model:cloud'
          ? {
              ...model,
              allowed: false,
              selectable: false,
              unavailable_reason: 'policy_local_only' as const,
            }
          : model),
      },
      isLoading: false,
    } as never)

    render(<ModelSelector onModelChange={vi.fn()} />)

    expect(
      screen.getByRole('button', { name: /openai\/gpt-4\.1-mini/ })
    ).toBeDisabled()
    expect(screen.getByText('modelRouting.blockedLocalOnly')).toBeInTheDocument()
  })
})
