import { describe, expect, it } from 'vitest'
import {
  convertReferencesToCompactMarkdown,
  parseSourceReferences,
} from './source-references'

describe('source reference citations', () => {
  it('parses exact IDs with hyphens and normalizes insight aliases', () => {
    expect(
      parseSourceReferences(
        'Use [source:source-123] and [insight:insight-456].'
      )
    ).toEqual([
      expect.objectContaining({ type: 'source', id: 'source-123' }),
      expect.objectContaining({ type: 'source_insight', id: 'insight-456' }),
    ])
  })

  it('deduplicates references into compact numbered clickable citations', () => {
    const result = convertReferencesToCompactMarkdown(
      'First [source:abc-123]. Again [source:abc-123]. Then [note:xyz].'
    )

    expect(result).toContain('First [1](#ref-source-abc-123).')
    expect(result).toContain('Again [1](#ref-source-abc-123).')
    expect(result).toContain('Then [2](#ref-note-xyz).')
    expect(result).toContain('[1] - [source:abc-123](#ref-source-abc-123)')
    expect(result).toContain('[2] - [note:xyz](#ref-note-xyz)')
  })
})
