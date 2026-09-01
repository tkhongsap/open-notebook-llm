'use client'

import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Cloud, Settings2, ShieldCheck, Sparkles } from 'lucide-react'

import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { useModelRouting } from '@/lib/hooks/use-models'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { ModelUnavailableReason, RoutedModel } from '@/lib/types/models'
import { cn } from '@/lib/utils'

const DEFAULT_MODEL_VALUE = '__system_default__'

interface ModelSelectorProps {
  currentModel?: string
  onModelChange: (model?: string) => void | Promise<void>
  disabled?: boolean
}

export function ModelSelector({
  currentModel,
  onModelChange,
  disabled = false,
}: ModelSelectorProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [selectedModel, setSelectedModel] = useState(currentModel || DEFAULT_MODEL_VALUE)
  const [isSaving, setIsSaving] = useState(false)
  const { data: routing, isLoading } = useModelRouting()

  useEffect(() => {
    setSelectedModel(currentModel || DEFAULT_MODEL_VALUE)
  }, [currentModel])

  const localModels = useMemo(
    () => routing?.models.filter(model => model.location === 'local') ?? [],
    [routing?.models]
  )
  const cloudModels = useMemo(
    () => routing?.models.filter(model => model.location === 'cloud') ?? [],
    [routing?.models]
  )
  const defaultModel = routing?.models.find(model => model.id === routing.default_model_id)
  const effectiveModel = routing?.models.find(
    model => model.id === (currentModel || routing.default_model_id)
  )
  const selectedModelDetails = routing?.models.find(model => model.id === selectedModel)

  const policyLabel = routing?.policy === 'local-only'
    ? t('modelRouting.policyLocalOnly')
    : routing?.policy === 'cloud-only'
      ? t('modelRouting.policyCloudOnly')
      : t('modelRouting.policyHybrid')

  const unavailableLabel = (reason?: ModelUnavailableReason | null) => {
    if (reason === 'policy_local_only') return t('modelRouting.blockedLocalOnly')
    if (reason === 'policy_cloud_only') return t('modelRouting.blockedCloudOnly')
    return t('modelRouting.notConfigured')
  }

  const handleSave = async () => {
    setIsSaving(true)
    try {
      await onModelChange(
        selectedModel === DEFAULT_MODEL_VALUE ? undefined : selectedModel
      )
      setOpen(false)
    } finally {
      setIsSaving(false)
    }
  }

  const renderModel = (model: RoutedModel) => {
    const selected = selectedModel === model.id
    const isLocal = model.location === 'local'
    return (
      <button
        key={model.id}
        type="button"
        disabled={!model.selectable || isSaving}
        aria-pressed={selected}
        onClick={() => setSelectedModel(model.id)}
        className={cn(
          'group flex w-full items-start gap-3 rounded-xl border px-3 py-3 text-left transition-colors',
          selected
            ? isLocal
              ? 'border-teal/45 bg-teal-tint/70'
              : 'border-gold/45 bg-gold-tint/70'
            : 'border-border/80 bg-background hover:border-foreground/20 hover:bg-muted/45',
          !model.selectable && 'cursor-not-allowed opacity-55'
        )}
      >
        <span
          className={cn(
            'mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg',
            isLocal ? 'bg-teal-tint text-teal' : 'bg-gold-tint text-gold'
          )}
        >
          {isLocal ? <ShieldCheck className="h-4 w-4" /> : <Cloud className="h-4 w-4" />}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            <span className="truncate text-sm font-medium text-foreground">{model.name}</span>
            {model.is_default && (
              <Badge variant="secondary" className="h-5 shrink-0 px-1.5 text-[10px]">
                {t('modelRouting.defaultBadge')}
              </Badge>
            )}
            {model.configured && (
              <Badge variant="outline" className="h-5 shrink-0 px-1.5 text-[10px]">
                {t('modelRouting.configured')}
              </Badge>
            )}
          </span>
          <span className="mt-0.5 block truncate text-xs text-muted-foreground">
            {model.provider_display_name}
          </span>
          {!model.selectable && (
            <span className="mt-1 flex items-start gap-1 text-[11px] leading-4 text-warn">
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
              {unavailableLabel(model.unavailable_reason)}
            </span>
          )}
        </span>
        <span
          aria-hidden
          className={cn(
            'mt-2 h-2.5 w-2.5 shrink-0 rounded-full border-2 border-background ring-1',
            selected
              ? isLocal
                ? 'bg-teal ring-teal'
                : 'bg-gold ring-gold'
              : 'bg-transparent ring-border'
          )}
        />
      </button>
    )
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          disabled={disabled}
          aria-label={t('modelRouting.chooseModel')}
          className="max-w-[16rem] gap-2"
        >
          {effectiveModel?.location === 'cloud' ? (
            <Cloud className="h-4 w-4 shrink-0 text-gold" />
          ) : effectiveModel?.location === 'local' ? (
            <ShieldCheck className="h-4 w-4 shrink-0 text-teal" />
          ) : (
            <Settings2 className="h-4 w-4 shrink-0" />
          )}
          <span className="truncate text-xs">
            {effectiveModel?.name || t('modelRouting.defaultModel')}
          </span>
        </Button>
      </DialogTrigger>
      <DialogContent
        aria-label={t('common.model')}
        className="max-h-[88vh] overflow-hidden p-0 sm:max-w-[620px]"
      >
        <DialogHeader className="border-b px-6 pb-5 pt-6">
          <div className="flex items-start justify-between gap-4 pr-7">
            <div>
              <DialogTitle className="flex items-center gap-2 font-display text-xl">
                <Sparkles className="h-5 w-5 text-teal" />
                {t('common.modelConfiguration')}
              </DialogTitle>
              <DialogDescription className="mt-2 max-w-[32rem] leading-5">
                {t('modelRouting.chooseModelDescription')}
                <span className="mt-1 block">{t('transformations.overrideModelDesc')}</span>
              </DialogDescription>
            </div>
            <Badge variant="outline" className="shrink-0 text-[10px] uppercase tracking-[0.1em]">
              {t('modelRouting.routingPolicy', { policy: policyLabel })}
            </Badge>
          </div>
        </DialogHeader>

        <div className="space-y-5 overflow-y-auto px-6 py-5">
          <button
            type="button"
            disabled={!defaultModel?.selectable || isSaving}
            aria-pressed={selectedModel === DEFAULT_MODEL_VALUE}
            onClick={() => setSelectedModel(DEFAULT_MODEL_VALUE)}
            className={cn(
              'flex w-full items-center gap-3 rounded-xl border px-3 py-3 text-left transition-colors',
              selectedModel === DEFAULT_MODEL_VALUE
                ? 'border-foreground/25 bg-muted/60'
                : 'border-border/80 hover:bg-muted/40',
              !defaultModel?.selectable && 'cursor-not-allowed opacity-55'
            )}
          >
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-muted">
              <Settings2 className="h-4 w-4" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-medium">{t('modelRouting.defaultModel')}</span>
              <span className="block truncate text-xs text-muted-foreground">
                {defaultModel?.name || t('common.noResults')}
              </span>
            </span>
          </button>

          {isLoading ? (
            <div className="flex items-center justify-center py-10">
              <LoadingSpinner />
            </div>
          ) : (
            <div className="grid gap-5 md:grid-cols-2">
              <section className="space-y-3">
                <div className="min-h-[3.5rem]">
                  <h3 className="flex items-center gap-2 text-sm font-semibold">
                    <ShieldCheck className="h-4 w-4 text-teal" />
                    {t('modelRouting.privateLocal')}
                  </h3>
                  <p className="mt-1 text-xs leading-4 text-muted-foreground">
                    {t('modelRouting.privateLocalDescription')}
                  </p>
                </div>
                <div className="space-y-2">
                  {localModels.length > 0 ? localModels.map(renderModel) : (
                    <p className="rounded-xl border border-dashed p-3 text-xs text-muted-foreground">
                      {t('modelRouting.noLocalModels')}
                    </p>
                  )}
                </div>
              </section>

              <section className="space-y-3">
                <div className="min-h-[3.5rem]">
                  <h3 className="flex items-center gap-2 text-sm font-semibold">
                    <Cloud className="h-4 w-4 text-gold" />
                    {t('modelRouting.frontierCloud')}
                  </h3>
                  <p className="mt-1 text-xs leading-4 text-muted-foreground">
                    {t('modelRouting.frontierCloudDescription')}
                  </p>
                </div>
                <div className="space-y-2">
                  {cloudModels.length > 0 ? cloudModels.map(renderModel) : (
                    <p className="rounded-xl border border-dashed p-3 text-xs text-muted-foreground">
                      {t('modelRouting.noCloudModels')}
                    </p>
                  )}
                </div>
              </section>
            </div>
          )}

          {selectedModelDetails?.location === 'cloud' && (
            <div className="flex items-start gap-2 rounded-xl border border-gold/30 bg-gold-tint/55 px-3 py-2.5 text-xs leading-5 text-foreground/75">
              <Cloud className="mt-0.5 h-4 w-4 shrink-0 text-gold" />
              {t('modelRouting.cloudPrivacyNotice', {
                provider: selectedModelDetails.provider_display_name,
              })}
            </div>
          )}

          {selectedModelDetails && (
            <p className="text-xs text-muted-foreground">
              {t('transformations.sessionUseReplacement', {
                name: selectedModelDetails.name,
              })}
            </p>
          )}
        </div>

        <DialogFooter className="border-t bg-muted/25 px-6 py-4 sm:justify-between">
          <Button
            variant="ghost"
            onClick={() => setSelectedModel(DEFAULT_MODEL_VALUE)}
            disabled={isSaving || !defaultModel?.selectable}
          >
            {t('common.resetToDefault')}
          </Button>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setOpen(false)} disabled={isSaving}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleSave} disabled={isSaving || isLoading}>
              {isSaving && <LoadingSpinner size="sm" className="mr-2" />}
              {isSaving ? t('modelRouting.savingSelection') : t('common.saveChanges')}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
