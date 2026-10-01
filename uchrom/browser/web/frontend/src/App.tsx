import { useEffect, useState } from 'react'
import { fetchHealth, listDatasets } from './api'
import { CellInfoPanel } from './components/CellInfoPanel'
import { CellPanel } from './components/CellPanel'
import { GroupPanel } from './components/GroupPanel'
import { Inspector, useDatasetFacts } from './components/Inspector'
import { OverviewColour } from './components/PropertiesPanel'
import { SideClose } from './components/SideClose'
import { StatusBar } from './components/StatusBar'
import { StorePanel } from './components/StorePanel'
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

type LeftTab = 'cells' | 'store'
const LEFT_TAB_KEY = 'uchrom.browser.leftTab'

/**
 * Left side bar: shared by every open view (never depends on the active pane).  Two tabs:
 * the cells (list, groups, info, colouring) and the store's on-disk structure.
 */
function LeftSidebar() {
  const sections = new Set(leftSections(useDatasetFacts()))
  const [tab, setTab] = useState<LeftTab>(() => {
    try {
      return localStorage.getItem(LEFT_TAB_KEY) === 'store' ? 'store' : 'cells'
    } catch {
      return 'cells'
    }
  })
  const pick = (t: LeftTab) => {
    setTab(t)
    try {
      localStorage.setItem(LEFT_TAB_KEY, t)
    } catch {
      /* no storage */
    }
  }
  return (
    <div className="left">
      <div className="left-tabs" role="tablist">
        <SideClose side="left" />
        {(
          [
            ['cells', 'Cells'],
            ['store', 'Store'],
          ] as [LeftTab, string][]
        ).map(([t, label]) => (
          <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? 'active' : ''} onClick={() => pick(t)} title={t === 'store' ? 'How the dataset is stored on disk' : 'Cells, groups and colouring'}>
            {label}
          </button>
        ))}
      </div>
      {tab === 'store' && <StorePanel />}
      {tab === 'cells' && sections.has('cells') && <CellPanel />}
      {tab === 'cells' && sections.has('groups') && <GroupPanel />}
      {tab === 'cells' && sections.has('cellInfo') && (
        <div className="panel left-info">
          <CellInfoPanel />
        </div>
      )}
      {tab === 'cells' && sections.has('colour') && (
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
