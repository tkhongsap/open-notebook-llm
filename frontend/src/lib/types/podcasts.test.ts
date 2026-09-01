import { describe, expect, it } from 'vitest'

import {
  isEpisodeProfileReady,
  type EpisodeProfile,
  type SpeakerProfile,
} from './podcasts'

const episodeProfile: EpisodeProfile = {
  id: 'episode_profile:one',
  name: 'overview',
  description: '',
  speaker_config: 'speaker_profile:one',
  outline_llm: 'model:language',
  transcript_llm: 'model:language',
  default_briefing: 'Explain',
  num_segments: 4,
}

const speakerProfile: SpeakerProfile = {
  id: 'speaker_profile:one',
  name: 'hosts',
  description: '',
  voice_model: 'model:voice',
  speakers: [],
}

describe('isEpisodeProfileReady', () => {
  it('requires both language stages and the linked TTS voice model', () => {
    expect(isEpisodeProfileReady(episodeProfile, [speakerProfile])).toBe(true)
    expect(
      isEpisodeProfileReady(
        { ...episodeProfile, transcript_llm: null },
        [speakerProfile]
      )
    ).toBe(false)
    expect(
      isEpisodeProfileReady(episodeProfile, [
        { ...speakerProfile, voice_model: null },
      ])
    ).toBe(false)
    expect(isEpisodeProfileReady(episodeProfile, [])).toBe(false)
  })
})
