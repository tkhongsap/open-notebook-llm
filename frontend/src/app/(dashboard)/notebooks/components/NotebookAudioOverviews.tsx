'use client'

import { AlertCircle, Headphones, Loader2 } from 'lucide-react'

import { EpisodeCard } from '@/components/podcasts/EpisodeCard'
import {
  useDeletePodcastEpisode,
  usePodcastEpisodes,
  useRetryPodcastEpisode,
} from '@/lib/hooks/use-podcasts'
import { useTranslation } from '@/lib/hooks/use-translation'

interface NotebookAudioOverviewsProps {
  notebookId: string
}

export function NotebookAudioOverviews({ notebookId }: NotebookAudioOverviewsProps) {
  const { t } = useTranslation()
  const { episodes, isLoading, isError } = usePodcastEpisodes({ notebookId })
  const deleteEpisode = useDeletePodcastEpisode()
  const retryEpisode = useRetryPodcastEpisode()

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-2 text-xs text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        {t('podcasts.loadingAudioOverviews')}
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive-tint p-3 text-xs text-destructive">
        <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        {t('podcasts.loadErrorDesc')}
      </div>
    )
  }

  if (episodes.length === 0) {
    return null
  }

  return (
    <section className="space-y-3" aria-label={t('podcasts.audioOverviews')}>
      <div className="flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <Headphones className="h-4 w-4 text-gold" />
          {t('podcasts.audioOverviews')}
        </h3>
        <span className="text-xs tabular-nums text-muted-foreground">
          {episodes.length}
        </span>
      </div>
      <div className="space-y-3">
        {episodes.slice(0, 3).map((episode) => (
          <EpisodeCard
            key={episode.id}
            episode={episode}
            onDelete={(episodeId) => deleteEpisode.mutateAsync(episodeId)}
            deleting={deleteEpisode.isPending}
            onRetry={async (episodeId) => {
              await retryEpisode.mutateAsync(episodeId)
            }}
            retrying={retryEpisode.isPending}
          />
        ))}
      </div>
    </section>
  )
}
