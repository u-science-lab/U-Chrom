import { useEffect } from 'react'
import { listDatasets } from './api'
import { LayerPanel } from './components/LayerPanel'
import { OperationsPanel } from './components/OperationsPanel'
import { PropertiesPanel } from './components/PropertiesPanel'
import { StatusBar } from './components/StatusBar'
import { TopBar } from './components/TopBar'
import { Viewport } from './components/Viewport'
import { useStore } from './store'
import { useGeometryLoader } from './useGeometryLoader'

export function App() {
  const setDatasets = useStore((s) => s.setDatasets)
  const setError = useStore((s) => s.setError)
  useGeometryLoader()
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
          <LayerPanel />
          <OperationsPanel />
        </div>
        <Viewport />
        <PropertiesPanel />
      </div>
      <StatusBar />
    </div>
  )
}
