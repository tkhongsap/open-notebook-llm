'use client'

import { createContext, useContext, useState, useCallback, ReactNode } from 'react'
import { AddSourceDialog } from '@/components/sources/AddSourceDialog'
import { CreateNotebookDialog } from '@/components/notebooks/CreateNotebookDialog'
import { GeneratePodcastDialog } from '@/components/podcasts/GeneratePodcastDialog'

export interface PodcastDialogOptions {
  notebookId?: string
  notebookName?: string
}

interface CreateDialogsContextType {
  openSourceDialog: () => void
  openNotebookDialog: () => void
  openPodcastDialog: (options?: PodcastDialogOptions) => void
}

const CreateDialogsContext = createContext<CreateDialogsContextType | null>(null)

export function CreateDialogsProvider({ children }: { children: ReactNode }) {
  const [sourceDialogOpen, setSourceDialogOpen] = useState(false)
  const [notebookDialogOpen, setNotebookDialogOpen] = useState(false)
  const [podcastDialogOpen, setPodcastDialogOpen] = useState(false)
  const [podcastDialogOptions, setPodcastDialogOptions] = useState<PodcastDialogOptions>({})

  const openSourceDialog = useCallback(() => setSourceDialogOpen(true), [])
  const openNotebookDialog = useCallback(() => setNotebookDialogOpen(true), [])
  const openPodcastDialog = useCallback((options: PodcastDialogOptions = {}) => {
    setPodcastDialogOptions(options)
    setPodcastDialogOpen(true)
  }, [])

  const setPodcastOpen = useCallback((value: boolean) => {
    setPodcastDialogOpen(value)
    if (!value) {
      setPodcastDialogOptions({})
    }
  }, [])

  return (
    <CreateDialogsContext.Provider
      value={{
        openSourceDialog,
        openNotebookDialog,
        openPodcastDialog,
      }}
    >
      {children}
      <AddSourceDialog open={sourceDialogOpen} onOpenChange={setSourceDialogOpen} />
      <CreateNotebookDialog open={notebookDialogOpen} onOpenChange={setNotebookDialogOpen} />
      <GeneratePodcastDialog
        open={podcastDialogOpen}
        onOpenChange={setPodcastOpen}
        initialNotebookId={podcastDialogOptions.notebookId}
        initialNotebookName={podcastDialogOptions.notebookName}
      />
    </CreateDialogsContext.Provider>
  )
}

export function useCreateDialogs() {
  const context = useContext(CreateDialogsContext)
  if (!context) {
    throw new Error('useCreateDialogs must be used within a CreateDialogsProvider')
  }
  return context
}
