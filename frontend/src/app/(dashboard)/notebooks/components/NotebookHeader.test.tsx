import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { NotebookHeader } from './NotebookHeader'

vi.mock('@/lib/hooks/use-notebooks', () => ({
  useUpdateNotebook: () => ({ mutate: vi.fn(), mutateAsync: vi.fn() }),
}))

vi.mock('./NotebookDeleteDialog', () => ({
  NotebookDeleteDialog: () => null,
}))

vi.mock('@/components/common/InlineEdit', () => ({
  InlineEdit: ({ value }: { value: string }) => <span>{value}</span>,
}))

describe('NotebookHeader', () => {
  it('stacks notebook actions below the title on narrow screens', () => {
    render(
      <NotebookHeader
        notebook={{
          id: 'notebook:local',
          name: 'Local Model Verification',
          description: 'End-to-end local inference validation',
          archived: false,
          created: '2026-08-31T00:00:00.000Z',
          updated: '2026-08-31T00:00:00.000Z',
          source_count: 1,
          note_count: 1,
        }}
      />
    )

    const headingRow = screen.getByTestId('notebook-heading-row')
    expect(headingRow.className).toContain('flex-col')
    expect(headingRow.className).toContain('sm:flex-row')
    expect(screen.getByText('Local Model Verification')).toBeDefined()
  })
})
