import { useId } from 'react'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import { useModelRouting, useModels } from '@/lib/hooks/use-models'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { useTranslation } from '@/lib/hooks/use-translation'
import { Cloud, ShieldCheck } from 'lucide-react'
import type { ModelUnavailableReason, RoutedModel } from '@/lib/types/models'

const DEFAULT_MODEL_VALUE = '__system_default__'

interface ModelSelectorProps {
  id?: string
  name?: string
  label?: string
  modelType: 'language' | 'embedding' | 'speech_to_text' | 'text_to_speech'
  value: string
  onChange: (value: string) => void
  placeholder?: string
  disabled?: boolean
  allowDefault?: boolean
}

export function ModelSelector({
  id,
  name,
  label,
  modelType,
  value,
  onChange,
  placeholder,
  disabled = false,
  allowDefault = false,
}: ModelSelectorProps) {
  const { t } = useTranslation()
  const { data: models, isLoading: modelsLoading } = useModels()
  const { data: routing, isLoading: routingLoading } = useModelRouting()
  const derivedId = useId()
  const selectId = id || derivedId
  const usesRouting = modelType === 'language'
  const isLoading = usesRouting ? routingLoading : modelsLoading

  const filteredModels = models?.filter(model => model.type === modelType) || []
  const routedModels = routing?.models ?? []
  const localModels = routedModels.filter(model => model.location === 'local')
  const cloudModels = routedModels.filter(model => model.location === 'cloud')
  const defaultModel = routedModels.find(model => model.id === routing?.default_model_id)
  const selectedRoutedModel = routedModels.find(
    model => model.id === (value || routing?.default_model_id)
  )
  const selectValue = allowDefault && !value ? DEFAULT_MODEL_VALUE : value

  const unavailableLabel = (reason?: ModelUnavailableReason | null) => {
    if (reason === 'policy_local_only') return t('modelRouting.blockedLocalOnly')
    if (reason === 'policy_cloud_only') return t('modelRouting.blockedCloudOnly')
    return t('modelRouting.notConfigured')
  }

  const renderRoutedModel = (model: RoutedModel) => (
    <SelectItem key={model.id} value={model.id} disabled={!model.selectable}>
      <div className="flex min-w-0 flex-1 items-center gap-2">
        {model.location === 'local' ? (
          <ShieldCheck className="h-3.5 w-3.5 text-teal" />
        ) : (
          <Cloud className="h-3.5 w-3.5 text-gold" />
        )}
        <span className="truncate">{model.name}</span>
        <span className="ml-auto truncate text-[11px] text-muted-foreground">
          {model.selectable ? model.provider_display_name : unavailableLabel(model.unavailable_reason)}
        </span>
      </div>
    </SelectItem>
  )

  return (
    <div className="space-y-2">
      {label && <Label htmlFor={selectId}>{label}</Label>}
      <Select
        name={name}
        value={selectValue}
        onValueChange={(nextValue) => onChange(nextValue === DEFAULT_MODEL_VALUE ? '' : nextValue)}
        disabled={disabled || isLoading}
      >
        <SelectTrigger id={selectId} className="w-full">
          <SelectValue placeholder={placeholder || t('settings.embeddingOptionPlaceholder')} />
        </SelectTrigger>
        <SelectContent className="min-w-[var(--radix-select-trigger-width)] max-w-[32rem]">
          {isLoading ? (
            <div className="flex items-center justify-center py-2">
              <LoadingSpinner size="sm" />
            </div>
          ) : usesRouting ? (
            routedModels.length === 0 ? (
              <div className="px-2 py-2 text-sm text-muted-foreground">
                {t('common.noResults')}
              </div>
            ) : (
              <>
                {allowDefault && (
                  <>
                    <SelectItem
                      value={DEFAULT_MODEL_VALUE}
                      disabled={!defaultModel?.selectable}
                    >
                      <div className="flex min-w-0 flex-1 items-center gap-2">
                        <span>{t('modelRouting.defaultModel')}</span>
                        {defaultModel && (
                          <span className="truncate text-[11px] text-muted-foreground">
                            {defaultModel.name}
                          </span>
                        )}
                      </div>
                    </SelectItem>
                    <SelectSeparator />
                  </>
                )}
                {localModels.length > 0 && (
                  <SelectGroup>
                    <SelectLabel className="flex items-center gap-2 font-semibold uppercase tracking-[0.12em]">
                      <ShieldCheck className="h-3.5 w-3.5 text-teal" />
                      {t('modelRouting.privateLocal')}
                    </SelectLabel>
                    {localModels.map(renderRoutedModel)}
                  </SelectGroup>
                )}
                {localModels.length > 0 && cloudModels.length > 0 && <SelectSeparator />}
                {cloudModels.length > 0 && (
                  <SelectGroup>
                    <SelectLabel className="flex items-center gap-2 font-semibold uppercase tracking-[0.12em]">
                      <Cloud className="h-3.5 w-3.5 text-gold" />
                      {t('modelRouting.frontierCloud')}
                    </SelectLabel>
                    {cloudModels.map(renderRoutedModel)}
                  </SelectGroup>
                )}
              </>
            )
          ) : filteredModels.length === 0 ? (
            <div className="text-sm text-muted-foreground py-2 px-2">
              {t('common.noResults')}
            </div>
          ) : (
            filteredModels.map((model) => (
              <SelectItem key={model.id} value={model.id}>
                <div className="flex items-center justify-between w-full">
                  <span>{model.name}</span>
                  <span className="text-xs text-muted-foreground ml-2">{model.provider}</span>
                </div>
              </SelectItem>
            ))
          )}
        </SelectContent>
      </Select>
      {usesRouting && selectedRoutedModel?.location === 'cloud' && (
        <p className="flex items-start gap-1.5 text-xs leading-5 text-muted-foreground">
          <Cloud className="mt-0.5 h-3.5 w-3.5 shrink-0 text-gold" />
          {t('modelRouting.cloudPrivacyNotice', {
            provider: selectedRoutedModel.provider_display_name,
          })}
        </p>
      )}
    </div>
  )
}
