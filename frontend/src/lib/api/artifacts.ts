import apiClient from './client'
import type {
  CreateNotebookArtifactRequest,
  NotebookArtifactResponse,
} from '@/lib/types/api'

export const artifactsApi = {
  create: async (notebookId: string, data: CreateNotebookArtifactRequest) => {
    const response = await apiClient.post<NotebookArtifactResponse>(
      `/notebooks/${notebookId}/artifacts`,
      data
    )
    return response.data
  },
}
