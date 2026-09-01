import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useModelRouting, useModels } from '@/lib/hooks/use-models'

import { ModelSelector } from './ModelSelector'

vi.mock('@/lib/hooks/use-models', () => ({
  useModels: vi.fn(),
  useModelRouting: vi.fn(),
}))

vi.mock('@/components/ui/select', () => ({
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectGroup: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
  SelectItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectLabel: ({ children }: { children: React.ReactNode }) => <h3>{children}</h3>,
  SelectSeparator: () => <hr />,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  SelectValue: () => null,
}))

const catalog = {
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
      configuration_source: 'credential' as const,
      configured: true,
      allowed: true,
      selectable: true,
      unavailable_reason: null,
      is_default: false,
    },
  ],
}

describe('common routed ModelSelector', () => {
  it('groups local/cloud models and warns when cloud is selected', () => {
    vi.mocked(useModels).mockReturnValue({ data: [], isLoading: false } as never)
    vi.mocked(useModelRouting).mockReturnValue({ data: catalog, isLoading: false } as never)

    render(
      <ModelSelector
        label="Workflow model"
        modelType="language"
        value="model:cloud"
        onChange={vi.fn()}
      />
    )

    expect(screen.getByRole('heading', { name: 'modelRouting.privateLocal' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'modelRouting.frontierCloud' })).toBeInTheDocument()
    expect(screen.getByText('modelRouting.cloudPrivacyNotice')).toBeInTheDocument()
  })
})
