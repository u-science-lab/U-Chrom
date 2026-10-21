import { useCallback } from 'react'
import { withPhase } from './activity'
import { openDataset } from './api'
import { addRecent, baseName, loadRecent, saveRecent } from './datasets'
import { useStore } from './store'

/**
 * Open a dataset on the server (the activity card shows it opening), make it the one on show and put it first in the
 * recent list; resolves to the new recent list.  Errors are thrown to the caller.
 */
export function useOpenDataset(): (path: string) => Promise<string[]> {
  const addDataset = useStore((s) => s.addDataset)
  return useCallback(
    async (path: string) => {
      addDataset(
        await withPhase('open', `Opening ${baseName(path).replace('.chromdata.zarr', '')}…`, () => openDataset(path),
          'A dataset on a remote atlas is read over the network: the first open takes a few seconds.'),
      )
      const recent = addRecent(loadRecent(), path)
      saveRecent(recent)
      return recent
    },
    [addDataset],
  )
}
