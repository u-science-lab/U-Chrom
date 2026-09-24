import { useEffect } from 'react'
import { listDatasets } from './api'
import { CellPanel } from './components/CellPanel'
import { LayerPanel } from './components/LayerPanel'
import { OperationsPanel } from './components/OperationsPanel'
import { PropertiesPanel } from './components/PropertiesPanel'
import { StatusBar } from './components/StatusBar'
import { TopBar } from './components/TopBar'
import { Workspace } from './components/Workspace'
import { hasCoords, useStore } from './store'
import { useCellLoader } from './useCellLoader'
import { useGeometryLoader } from './useGeometryLoader'
import { useOmicsLoader } from './useOmicsLoader'

export function App() {
  const setDatasets = useStore((s) => s.setDatasets)
  const setError = useStore((s) => s.setError)
  // layers / subsets are 3-D geometry: nothing to show without coordinates
  const coords = useStore((s) => hasCoords(s.datasets.find((d) => d.id === s.activeDatasetId)) || !s.activeDatasetId)
  useGeometryLoader()
  useCellLoader()
  useOmicsLoader()
  useEffect(() => {
    listDatasets()
      .then(setDatasets)
      .catch((e: Error) => setError(`Cannot reach the U-Chrom server: ${e.message}`))
  }, [setDatasets, setError])

  return (
    <div className="app">
      <TopBar />
      <div className="main">
        <div className="left">
          <CellPanel />
          {coords && <LayerPanel />}
          {coords && <OperationsPanel />}
        </div>
        <Workspace />
        <PropertiesPanel />
      </div>
      <StatusBar />
    </div>
  )
}
