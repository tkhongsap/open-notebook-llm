'use client'

import type { LucideIcon } from 'lucide-react'
import {
  BookOpenCheck,
  BrainCircuit,
  Clock3,
  FileText,
  GraduationCap,
  Headphones,
  HelpCircle,
  ListChecks,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { NotebookArtifactKind } from '@/lib/types/api'
import { cn } from '@/lib/utils'

interface StudioAction {
  kind: NotebookArtifactKind
  labelKey: string
  icon: LucideIcon
  accent: string
}

const STUDIO_ACTIONS: StudioAction[] = [
  { kind: 'briefing_doc', labelKey: 'studio.briefingDoc', icon: FileText, accent: 'text-teal' },
  { kind: 'study_guide', labelKey: 'studio.studyGuide', icon: GraduationCap, accent: 'text-fern' },
  { kind: 'faq', labelKey: 'studio.faq', icon: HelpCircle, accent: 'text-mauve' },
  { kind: 'timeline', labelKey: 'studio.timeline', icon: Clock3, accent: 'text-gold' },
  { kind: 'mind_map', labelKey: 'studio.mindMap', icon: BrainCircuit, accent: 'text-teal' },
  { kind: 'flashcards', labelKey: 'studio.flashcards', icon: BookOpenCheck, accent: 'text-fern' },
  { kind: 'quiz', labelKey: 'studio.quiz', icon: ListChecks, accent: 'text-mauve' },
]

interface StudioActionsProps {
  disabled?: boolean
  pendingKind?: NotebookArtifactKind | null
  onGenerate: (kind: NotebookArtifactKind) => void
  onAudio: () => void
}

export function StudioActions({
  disabled = false,
  pendingKind,
  onGenerate,
  onAudio,
}: StudioActionsProps) {
  const { t } = useTranslation()

  return (
    <div className="grid grid-cols-2 gap-2" aria-label={t('studio.create')}>
      {STUDIO_ACTIONS.map(({ kind, labelKey, icon: Icon, accent }) => {
        const isPending = pendingKind === kind
        return (
          <Button
            key={kind}
            type="button"
            variant="outline"
            disabled={disabled || Boolean(pendingKind)}
            onClick={() => onGenerate(kind)}
            className={cn(
              'h-auto min-h-16 items-start justify-start gap-2.5 rounded-xl p-3 text-left',
              'border-border/70 bg-background/65 hover:-translate-y-0.5 hover:bg-accent/55',
              'transition-all duration-200'
            )}
          >
            <Icon className={cn('mt-0.5 h-4 w-4 shrink-0', accent)} />
            <span className="min-w-0 text-xs font-semibold leading-4">
              {isPending ? t('studio.generating') : t(labelKey)}
            </span>
          </Button>
        )
      })}
      <Button
        type="button"
        variant="outline"
        disabled={disabled || Boolean(pendingKind)}
        onClick={onAudio}
        className="h-auto min-h-16 items-start justify-start gap-2.5 rounded-xl border-border/70 bg-background/65 p-3 text-left transition-all duration-200 hover:-translate-y-0.5 hover:bg-accent/55"
      >
        <Headphones className="mt-0.5 h-4 w-4 shrink-0 text-gold" />
        <span className="text-xs font-semibold leading-4">{t('studio.audioOverview')}</span>
      </Button>
    </div>
  )
}
