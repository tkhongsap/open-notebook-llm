import { useMutation, useQueryClient } from '@tanstack/react-query'

import { artifactsApi } from '@/lib/api/artifacts'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { useToast } from '@/lib/hooks/use-toast'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { CreateNotebookArtifactRequest } from '@/lib/types/api'
import { getApiErrorKey } from '@/lib/utils/error-handler'

export function useCreateNotebookArtifact(notebookId: string) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (data: CreateNotebookArtifactRequest) =>
      artifactsApi.create(notebookId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notes(notebookId) })
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.notebook(notebookId) })
      toast({
        title: t('common.success'),
        description: t('studio.generateSuccess'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorKey(error, t('studio.generateFailed')),
        variant: 'destructive',
      })
    },
  })
}
