'use client'

import { useEffect, useRef, useState } from 'react'
import { Download, Loader2 } from 'lucide-react'

import apiClient from '@/lib/api/client'
import { resolvePodcastAssetUrl } from '@/lib/api/podcasts'
import type { PodcastEpisode } from '@/lib/types/podcasts'
import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'

const PLAYBACK_RATES = [0.75, 1, 1.25, 1.5, 2] as const

function downloadName(name: string, sourcePath?: string | null): string {
  const safe = name
    .trim()
    .replace(/[^a-z0-9._-]+/gi, '-')
    .replace(/^-+|-+$/g, '')
  const extension = sourcePath?.match(/\.(mp3|m4a|wav|ogg|aac)(?:$|[?#])/i)?.[1]
  return `${safe || 'audio-overview'}.${extension?.toLowerCase() || 'mp3'}`
}

interface PodcastAudioPlayerProps {
  episode: PodcastEpisode
}

export function PodcastAudioPlayer({ episode }: PodcastAudioPlayerProps) {
  const { t } = useTranslation()
  const audioRef = useRef<HTMLAudioElement>(null)
  const [audioSrc, setAudioSrc] = useState<string>()
  const [audioError, setAudioError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [rateIndex, setRateIndex] = useState(1)
  const audioUnavailableLabel = t('podcasts.audioUnavailable')

  useEffect(() => {
    let revokeUrl: string | undefined
    let cancelled = false
    setAudioError(null)
    setAudioSrc(undefined)

    const loadAudio = async () => {
      const resolved = await resolvePodcastAssetUrl(
        episode.audio_url ?? episode.audio_file
      )

      if (!resolved || cancelled) {
        return
      }

      // The API audio endpoint can be protected. Fetch it through the shared
      // client so auth headers are included, then let the browser play and
      // download the resulting object URL.
      if (episode.audio_url) {
        setLoading(true)
        try {
          const response = await apiClient.get<Blob>(resolved, {
            responseType: 'blob',
          })
          if (cancelled) {
            return
          }
          revokeUrl = URL.createObjectURL(response.data)
          setAudioSrc(revokeUrl)
        } catch (error) {
          console.error('Unable to load podcast audio', error)
          if (!cancelled) {
            setAudioError(audioUnavailableLabel)
          }
        } finally {
          if (!cancelled) {
            setLoading(false)
          }
        }
        return
      }

      setAudioSrc(resolved)
    }

    void loadAudio()

    return () => {
      cancelled = true
      if (revokeUrl) {
        URL.revokeObjectURL(revokeUrl)
      }
    }
  }, [audioUnavailableLabel, episode.audio_file, episode.audio_url])

  const cyclePlaybackRate = () => {
    const nextIndex = (rateIndex + 1) % PLAYBACK_RATES.length
    const nextRate = PLAYBACK_RATES[nextIndex]
    setRateIndex(nextIndex)
    if (audioRef.current) {
      audioRef.current.playbackRate = nextRate
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 rounded-lg border bg-card p-3 text-xs text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        {t('podcasts.loadingAudio')}
      </div>
    )
  }

  if (audioError) {
    return <p className="text-sm text-destructive">{audioError}</p>
  }

  if (!audioSrc) {
    return null
  }

  const playbackRate = PLAYBACK_RATES[rateIndex]

  return (
    <div className="space-y-2 rounded-xl border bg-card/80 p-2.5">
      <audio
        ref={audioRef}
        controls
        preload="metadata"
        src={audioSrc}
        className="h-9 w-full"
        aria-label={t('podcasts.playAudioOverview', { name: episode.name })}
        onLoadedMetadata={(event) => {
          event.currentTarget.playbackRate = playbackRate
        }}
      />
      <div className="flex items-center justify-end gap-2">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={cyclePlaybackRate}
          aria-label={t('podcasts.changePlaybackSpeed')}
          className="h-7 px-2 text-xs tabular-nums"
        >
          {playbackRate}×
        </Button>
        <Button asChild variant="ghost" size="sm" className="h-7 px-2 text-xs">
          <a
            href={audioSrc}
            download={downloadName(episode.name, episode.audio_file ?? episode.audio_url)}
          >
            <Download className="mr-1.5 h-3.5 w-3.5" />
            {t('podcasts.downloadAudio')}
          </a>
        </Button>
      </div>
    </div>
  )
}
