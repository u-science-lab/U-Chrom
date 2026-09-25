import { useEffect } from 'react'
import { fetchGeometry } from './api'
import { useStore } from './store'

/** Fetch geometry for every layer that doesn't have it yet. */
export function useGeometryLoader() {
  const layers = useStore((s) => s.layers)
  useEffect(() => {
    const { setLoading, setGeometry, setLayerError } = useStore.getState()
    for (const l of layers) {
      // Re-read the live layer: the effect may run again before a fetch lands.
      const cur = useStore.getState().layers.find((x) => x.id === l.id)
      if (!cur || cur.geometry || cur.loading || cur.error) continue
      setLoading(l.id)
      fetchGeometry(l.datasetId, l.filter)
        .then((g) => setGeometry(l.id, g))
        .catch((e: Error) => setLayerError(l.id, e.message))
    }
  }, [layers])
}
