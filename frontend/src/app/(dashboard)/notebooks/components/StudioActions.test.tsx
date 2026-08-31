import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { StudioActions } from './StudioActions'


describe('StudioActions', () => {
  it('exposes every grounded text artifact and audio overview', () => {
    render(
      <StudioActions
        onGenerate={vi.fn()}
        onAudio={vi.fn()}
      />
    )

    expect(screen.getByText('studio.briefingDoc')).toBeInTheDocument()
    expect(screen.getByText('studio.studyGuide')).toBeInTheDocument()
    expect(screen.getByText('studio.faq')).toBeInTheDocument()
    expect(screen.getByText('studio.timeline')).toBeInTheDocument()
    expect(screen.getByText('studio.mindMap')).toBeInTheDocument()
    expect(screen.getByText('studio.flashcards')).toBeInTheDocument()
    expect(screen.getByText('studio.quiz')).toBeInTheDocument()
    expect(screen.getByText('studio.audioOverview')).toBeInTheDocument()
  })

  it('dispatches the selected artifact kind', () => {
    const onGenerate = vi.fn()
    render(<StudioActions onGenerate={onGenerate} onAudio={vi.fn()} />)

    fireEvent.click(screen.getByText('studio.studyGuide'))

    expect(onGenerate).toHaveBeenCalledWith('study_guide')
  })

  it('opens the audio workflow separately', () => {
    const onAudio = vi.fn()
    render(<StudioActions onGenerate={vi.fn()} onAudio={onAudio} />)

    fireEvent.click(screen.getByText('studio.audioOverview'))

    expect(onAudio).toHaveBeenCalledOnce()
  })

  it('prevents duplicate work while an artifact is pending', () => {
    render(
      <StudioActions
        pendingKind="quiz"
        onGenerate={vi.fn()}
        onAudio={vi.fn()}
      />
    )

    expect(screen.getByText('studio.generating')).toBeInTheDocument()
    for (const button of screen.getAllByRole('button')) {
      expect(button).toBeDisabled()
    }
  })
})
