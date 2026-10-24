import { useEffect, useRef, useState } from 'react'
import { withPhase } from './activity'
import { fetchHealth, listDatasets, openDataset } from './api'
import { ActivityBar, ActivityCard } from './components/ActivityCard'
import { addRecent, loadRecent, openParams, openSearch, saveRecent } from './datasets'
import { CellInfoPanel } from './components/CellInfoPanel'
import { CellPanel } from './components/CellPanel'
import { GroupPanel } from './components/GroupPanel'
import { Inspector, useDatasetFacts } from './components/Inspector'
import { OverviewColour } from './components/PropertiesPanel'
import { SideClose } from './components/SideClose'
import { StatusBar } from './components/StatusBar'
import { StorePanel } from './components/StorePanel'
import { TopBar } from './components/TopBar'
import { Welcome } from './components/Welcome'
import { Workspace } from './components/Workspace'
import { leftSections } from './inspector'
import { STALE_SERVER_MESSAGE, isStaleServer, pageBundle } from './serverBundle'
import { useStore } from './store'
import { startControl } from './control'
import { useCellLoader } from './useCellLoader'
import { useGeometryLoader } from './useGeometryLoader'
import { useFocusGeometry } from './useFocusGeometry'
import { useOmicsLoader } from './useOmicsLoader'
import { registerWebMcpTools } from './webmcp'
import { sidebarKey } from './sidebars'

/**
 * The address names the dataset on show (`?open=<store>`, see `openSearch`), so that a reload reopens it and the address
 * is a link to it.  Nothing changes before a dataset is on show: a link whose store did not open (and nothing else
 * open) stays as it is, for a reload to try again.
 */
function useOpenAddress() {
  const path = useStore((s) => s.datasets.find((d) => d.id === s.activeDatasetId)?.path ?? null)
  const shown = useRef(false)
  useEffect(() => {
    if (path === null && !shown.current) return
    shown.current = true
    const search = openSearch(window.location.search, path)
    if (search !== window.location.search)
      window.history.replaceState(window.history.state, '', window.location.pathname + search + window.location.hash)
  }, [path])
}

export function App() {
  const setDatasets = useStore((s) => s.setDatasets)
  const setError = useStore((s) => s.setError)
  const addDataset = useStore((s) => s.addDataset)
  const setActiveDataset = useStore((s) => s.setActiveDataset)
  const agentLease = useStore((s) => s.agentLease)
  // the start page waits until the server has said what is open and a linked dataset has opened (no flash of it)
  const [booted, setBooted] = useState(false)
  const hasData = useStore((s) => s.datasets.length > 0)
  useGeometryLoader()
  useFocusGeometry()
  useCellLoader()
  useOmicsLoader()
  useSystemTheme()
  useEffect(() => {
    // an atlas page links here with ?open=<store url> (read before the address follows the dataset on show)
    const linked = openParams(window.location.search)
    withPhase('boot', 'Connecting to the U-Chrom server…', () => listDatasets())
      .then(async (ds) => {
        setDatasets(ds)
        // already open in this session: show it; otherwise open it
        const open = ds.filter((d) => linked.includes(d.path))
        if (open.length) setActiveDataset(open[open.length - 1].id)
        const wanted = linked.filter((u) => !ds.some((d) => d.path === u))
        for (const u of wanted) {
          try {
            addDataset(await withPhase('open', `Opening ${u.split('/').pop()?.replace('.chromdata.zarr', '')} from the atlas…`, () => openDataset(u), 'Only what is needed is read from the atlas, but the first open of a dataset takes a few seconds.'))
            saveRecent(addRecent(loadRecent(), u))
          } catch (e) {
            setError(`Cannot open ${u}: ${(e as Error).message}`)
          }
        }
      })
      .catch((e: Error) => setError(`Cannot reach the U-Chrom server: ${e.message}`))
      .finally(() => setBooted(true))
    fetchHealth()
      .then((h) => {
        // a server older than the page lacks its newer routes (405 / 404 on use)
        if (isStaleServer(pageBundle(), h.bundle ?? null)) setError(STALE_SERVER_MESSAGE)
      })
      .catch(() => {})
  }, [setDatasets, setError, addDataset, setActiveDataset])
  useOpenAddress()
  // code and agents drive this page through the same actions as the GUI (control channel, WebMCP).  A hosted
  // server (public atlas) has no agent to drive and must be free to sleep: no long-lived connection there.
  useEffect(() => {
    let stop: (() => void) | undefined
    let live = true
    fetchHealth()
      .then((h) => {
        if (live && !h.hosted) stop = startControl()
      })
      .catch(() => {
        if (live) stop = startControl()
      })
    return () => {
      live = false
      stop?.()
    }
  }, [])
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
    <div className="app" aria-busy={agentLease} aria-disabled={agentLease} data-agent-lease={agentLease ? 'active' : 'idle'}>
      <ActivityBar />
      <ActivityCard />
      <TopBar />
      <div className="main">
        {hasData && sidebars.left && <LeftSidebar />}
        {hasData ? <Workspace /> : booted ? <Welcome /> : <div className="workspace" />}
        {hasData && sidebars.right && <Inspector />}
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
        <SideClose side="left" />
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
