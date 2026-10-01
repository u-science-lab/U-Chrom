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
        <div className="seg left-tab-seg">
          {(
            [
              ['cells', 'Cells — list, groups and colouring', <CellsIcon key="c" />],
              ['store', 'Store — how the dataset is stored on disk', <StoreIcon key="s" />],
            ] as [LeftTab, string, JSX.Element][]
          ).map(([t, title, icon]) => (
            <button key={t} role="tab" aria-selected={tab === t} aria-label={title} className={tab === t ? 'active' : ''} onClick={() => pick(t)} title={title}>
              {icon}
            </button>
          ))}
        </div>
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

function CellsIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round">
      <circle cx="3" cy="4" r="1.2" fill="currentColor" stroke="none" />
      <circle cx="3" cy="8" r="1.2" fill="currentColor" stroke="none" />
      <circle cx="3" cy="12" r="1.2" fill="currentColor" stroke="none" />
      <path d="M6.5 4h7M6.5 8h7M6.5 12h7" />
    </svg>
  )
}

function StoreIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round">
      <path d="M1.8 3.2h4l1.2 1.4h7.2v8.6H1.8z" />
      <path d="M5 8.2h6M5 10.6h4" strokeLinecap="round" />
    </svg>
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
