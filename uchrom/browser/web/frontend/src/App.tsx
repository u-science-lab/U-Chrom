import { useEffect } from 'react'
import { fetchHealth, listDatasets } from './api'
import { CellInfoPanel } from './components/CellInfoPanel'
import { CellPanel } from './components/CellPanel'
import { GroupPanel } from './components/GroupPanel'
import { Inspector, useDatasetFacts } from './components/Inspector'
import { OverviewColour } from './components/PropertiesPanel'
import { StatusBar } from './components/StatusBar'
import { TopBar } from './components/TopBar'
import { Workspace } from './components/Workspace'
import { leftSections } from './inspector'
import { STALE_SERVER_MESSAGE, isStaleServer, pageBundle } from './serverBundle'
import { useStore } from './store'
import { startControl } from './control'
import { useCellLoader } from './useCellLoader'
import { useGeometryLoader } from './useGeometryLoader'
import { useOmicsLoader } from './useOmicsLoader'
import { registerWebMcpTools } from './webmcp'
import { sidebarKey } from './sidebars'

export function App() {
  const setDatasets = useStore((s) => s.setDatasets)
  const setError = useStore((s) => s.setError)
  useGeometryLoader()
  useCellLoader()
  useOmicsLoader()
  useSystemTheme()
  useEffect(() => {
    listDatasets()
      .then(setDatasets)
      .catch((e: Error) => setError(`Cannot reach the U-Chrom server: ${e.message}`))
    fetchHealth()
      .then((h) => {
        // a server older than the page lacks its newer routes (405 / 404 on use)
        if (isStaleServer(pageBundle(), h.bundle ?? null)) setError(STALE_SERVER_MESSAGE)
      })
      .catch(() => {})
  }, [setDatasets, setError])
  // code and agents drive this page through the same actions as the GUI (control channel, WebMCP)
  useEffect(() => startControl(), [])
  useEffect(() => {
    registerWebMcpTools()
  }, [])
  const sidebars = useStore((s) => s.sidebars)
  const toggleSidebar = useStore((s) => s.toggleSidebar)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const side = sidebarKey(e)
      if (!side) return
      e.preventDefault()
      toggleSidebar(side)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toggleSidebar])

  return (
    <div className="app">
      <TopBar />
      <div className="main">
        {sidebars.left && <LeftSidebar />}
        <Workspace />
        {sidebars.right && <Inspector />}
      </div>
      <StatusBar />
    </div>
  )
}

/** Left side bar: shared by every open view (never depends on the active pane). */
function LeftSidebar() {
  const sections = new Set(leftSections(useDatasetFacts()))
  return (
    <div className="left">
      {sections.has('cells') && <CellPanel />}
      {sections.has('groups') && <GroupPanel />}
      {sections.has('cellInfo') && (
        <div className="panel left-info">
          <CellInfoPanel />
        </div>
      )}
      {sections.has('colour') && (
        <div className="panel left-colour">
          <OverviewColour />
        </div>
      )}
    </div>
  )
}

/** Follow the system light / dark preference while the choice is "System". */
function useSystemTheme() {
  const choice = useStore((s) => s.themeChoice)
  const refresh = useStore((s) => s.refreshTheme)
  useEffect(() => {
    if (choice !== 'system' || typeof matchMedia === 'undefined') return
    const mq = matchMedia('(prefers-color-scheme: light)')
    mq.addEventListener('change', refresh)
    return () => mq.removeEventListener('change', refresh)
  }, [choice, refresh])
}
