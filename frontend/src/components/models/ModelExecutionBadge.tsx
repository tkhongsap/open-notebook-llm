import { Cloud, ShieldCheck } from 'lucide-react'

import type { ModelExecutionInfo } from '@/lib/types/api'
import { useTranslation } from '@/lib/hooks/use-translation'

interface ModelExecutionBadgeProps {
  model: ModelExecutionInfo
  generated?: boolean
}

export function ModelExecutionBadge({ model, generated = false }: ModelExecutionBadgeProps) {
  const { t } = useTranslation()
  const isLocal = model.location === 'local'

  return (
    <div
      className="inline-flex max-w-full items-center gap-1.5 rounded-full border bg-background/70 px-2 py-1 text-[11px] text-muted-foreground"
      title={`${model.provider_display_name} · ${model.selection_reason}`}
    >
      {isLocal ? (
        <ShieldCheck className="h-3 w-3 text-teal" />
      ) : (
        <Cloud className="h-3 w-3 text-gold" />
      )}
      <span className="truncate">
        {t(generated ? 'modelRouting.generatedWith' : 'modelRouting.usedModel', { name: model.name })}
      </span>
      <span className="font-semibold uppercase tracking-[0.08em] text-foreground/65">
        {t(isLocal ? 'modelRouting.localBadge' : 'modelRouting.cloudBadge')}
      </span>
    </div>
  )
}
