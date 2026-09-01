import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { NotesColumn } from './NotesColumn'

const { createArtifactMutate } = vi.hoisted(() => ({
  createArtifactMutate: vi.fn(),
}))

vi.mock('@/lib/hooks/use-translation', () => ({
  useTranslation: () => ({ t: (key: string) => key, language: 'en-US' }),
}))
vi.mock('@/lib/hooks/use-artifacts', () => ({
  useCreateNotebookArtifact: () => ({
    mutate: createArtifactMutate,
    isPending: false,
    variables: undefined,
  }),
}))
vi.mock('@/lib/hooks/use-notes', () => ({
  useDeleteNote: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('@/lib/hooks/use-create-dialogs', () => ({
  useCreateDialogs: () => ({ openPodcastDialog: vi.fn() }),
}))
vi.mock('@/lib/stores/notebook-columns-store', () => ({
  useNotebookColumnsStore: () => ({ notesCollapsed: false, toggleNotes: vi.fn() }),
}))
vi.mock('@/components/notebooks/CollapsibleColumn', () => ({
  CollapsibleColumn: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  createCollapseButton: () => null,
}))
vi.mock('@/components/common/ModelSelector', () => ({
  ModelSelector: ({ onChange }: { onChange: (value: string) => void }) => (
    <button type="button" onClick={() => onChange('model:cloud')}>
      choose-cloud-model
    </button>
  ),
}))
vi.mock('./StudioActions', () => ({
  StudioActions: ({ onGenerate }: { onGenerate: (kind: 'briefing_doc') => void }) => (
    <button type="button" onClick={() => onGenerate('briefing_doc')}>
      generate-briefing
    </button>
  ),
}))
vi.mock('./NotebookAudioOverviews', () => ({ NotebookAudioOverviews: () => null }))
vi.mock('./NoteEditorDialog', () => ({ NoteEditorDialog: () => null }))
vi.mock('@/components/common/ConfirmDialog', () => ({ ConfirmDialog: () => null }))

describe('NotesColumn Studio model routing', () => {
  beforeEach(() => {
    createArtifactMutate.mockClear()
  })

  it('sends the explicitly selected model with an artifact request', () => {
    render(
      <NotesColumn
        notes={[]}
        isLoading={false}
        notebookId="notebook:one"
        notebookName="Research"
        hasContext
      />
    )

    fireEvent.click(screen.getByRole('button', { name: 'choose-cloud-model' }))
    fireEvent.click(screen.getByRole('button', { name: 'generate-briefing' }))

    expect(createArtifactMutate).toHaveBeenCalledWith({
      artifact_kind: 'briefing_doc',
      model_id: 'model:cloud',
    })
  })
})
