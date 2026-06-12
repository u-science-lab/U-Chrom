import { useState, useEffect, useRef, useCallback } from 'react'
import { useAppStore } from '../store'
import { ws } from '../ws'

// One entry returned by GET /api/browse.
interface BrowseEntry {
  name: string
  type: 'dir' | 'file'
  path: string
  size?: number
}

interface BrowseResult {
  path: string
  parent: string | null
  entries: BrowseEntry[]
}

function formatSize(bytes?: number): string {
  if (bytes == null) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function TopBar() {
  const dataVersion = useAppStore(s => s.dataVersion)
  const bumpDataVersion = useAppStore(s => s.bumpDataVersion)

  const [showModal, setShowModal] = useState(false)
  const [filePath, setFilePath] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loadedFile, setLoadedFile] = useState<string | null>(null)
  const pendingPath = useRef<string | null>(null)

  // File-browser state.
  const [browse, setBrowse] = useState<BrowseResult | null>(null)
  const [browseLoading, setBrowseLoading] = useState(false)
  const [browseError, setBrowseError] = useState<string | null>(null)

  // Listen for load_data results from the backend over the shared WS.
  useEffect(() => {
    const offLoaded = ws.onMessage('data_loaded', (msg) => {
      const p = (msg.path as string) || pendingPath.current || ''
      setLoadedFile(p.split('/').pop() ?? p)
      bumpDataVersion()
      setLoading(false)
      setShowModal(false)
      setFilePath('')
      pendingPath.current = null
    })
    const offError = ws.onMessage('error', (msg) => {
      // Only surface errors while a load is in flight.
      if (!pendingPath.current) return
      setLoadError((msg.message as string) || 'Failed to load file')
      setLoading(false)
      pendingPath.current = null
    })
    return () => { offLoaded(); offError() }
  }, [bumpDataVersion])

  // Fetch a directory listing from the backend. An empty path lets the backend
  // default to the user's home directory.
  const fetchDir = useCallback(async (path: string) => {
    setBrowseLoading(true)
    setBrowseError(null)
    try {
      const res = await fetch(`/api/browse?path=${encodeURIComponent(path)}`)
      if (!res.ok) {
        const body = await res.json().catch(() => null)
        throw new Error(body?.detail?.error || `Browse failed (${res.status})`)
      }
      const data: BrowseResult = await res.json()
      setBrowse(data)
    } catch (e) {
      setBrowseError(e instanceof Error ? e.message : 'Failed to list directory')
    } finally {
      setBrowseLoading(false)
    }
  }, [])

  // Open the modal and list the home directory.
  const openModal = () => {
    setLoadError(null)
    setShowModal(true)
    fetchDir('')
  }

  // Load the given file path via the WebSocket (same path the manual input uses).
  const loadPath = (path: string) => {
    const p = path.trim()
    if (!p) return
    if (!ws.connected) {
      setLoadError('Not connected to backend')
      return
    }
    setLoading(true)
    setLoadError(null)
    pendingPath.current = p
    ws.send('load_data', { path: p })
  }

  const onEntryClick = (entry: BrowseEntry) => {
    if (entry.type === 'dir') {
      fetchDir(entry.path)
    } else {
      setFilePath(entry.path)
      loadPath(entry.path)
    }
  }

  return (
    <div className="h-[60px] flex items-center justify-between px-6 border-b border-border-primary bg-bg-primary">
      <div className="flex items-center gap-3">
        <div className="text-2xl font-bold text-accent-blue">U-Chrom</div>
        <div className="text-sm text-text-secondary">Data Portal</div>
      </div>

      <div className="flex items-center gap-4">
        {(dataVersion > 0 || loadedFile) && (
          <div className="text-sm text-text-secondary">
            {loadedFile ? loadedFile : 'Data loaded'}{' '}
            <span className="text-accent-green">●</span>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={openModal}
          className="border border-accent-blue text-accent-blue px-3 py-1.5 rounded text-sm hover:bg-blue-50"
        >
          Open File
        </button>
        <button className="px-4 py-2 text-sm text-text-secondary hover:text-text-primary transition-colors">
          Settings
        </button>
      </div>

      {showModal && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl w-[640px] max-w-[92vw] flex flex-col max-h-[80vh]">
            {/* Header */}
            <div className="px-6 pt-6 pb-3">
              <h3 className="text-base font-medium text-gray-800">Open ChromData File</h3>
              <p className="text-xs text-gray-400 mt-1">
                Browse for a <code>.h5cd</code> or <code>.csv</code> file, or type a path below.
              </p>
            </div>

            {/* Current path breadcrumb */}
            <div className="px-6 pb-2 flex items-center gap-2">
              <button
                onClick={() => browse?.parent != null && fetchDir(browse.parent)}
                disabled={!browse?.parent}
                className="px-2 py-1 text-xs rounded border border-gray-200 text-gray-600 hover:border-blue-400 disabled:opacity-40 disabled:hover:border-gray-200"
                title="Up one level"
              >
                ↑ Up
              </button>
              <div className="flex-1 text-xs font-mono text-gray-500 truncate" title={browse?.path}>
                {browse?.path ?? '…'}
              </div>
              <button
                onClick={() => browse && fetchDir(browse.path)}
                className="px-2 py-1 text-xs rounded border border-gray-200 text-gray-600 hover:border-blue-400"
                title="Refresh"
              >
                ⟳
              </button>
            </div>

            {/* Directory listing */}
            <div className="flex-1 overflow-auto border-y border-gray-100 mx-6 min-h-[200px]">
              {browseLoading ? (
                <div className="h-full flex items-center justify-center text-sm text-gray-400 py-12">
                  Loading…
                </div>
              ) : browseError ? (
                <div className="h-full flex items-center justify-center text-sm text-red-500 py-12 px-4 text-center">
                  {browseError}
                </div>
              ) : browse && browse.entries.length === 0 ? (
                <div className="h-full flex items-center justify-center text-sm text-gray-400 py-12">
                  No folders or data files here.
                </div>
              ) : (
                <ul className="divide-y divide-gray-50">
                  {browse?.entries.map(entry => (
                    <li key={entry.path}>
                      <button
                        onClick={() => onEntryClick(entry)}
                        disabled={loading}
                        className="w-full flex items-center gap-3 px-3 py-2 text-left text-sm hover:bg-blue-50 disabled:opacity-50 transition-colors"
                      >
                        <span className="text-base leading-none w-5 text-center">
                          {entry.type === 'dir' ? '📁' : '📄'}
                        </span>
                        <span className={`flex-1 truncate ${entry.type === 'dir' ? 'text-gray-700' : 'text-blue-600'}`}>
                          {entry.name}
                        </span>
                        {entry.type === 'file' && (
                          <span className="text-xs text-gray-400 font-mono">{formatSize(entry.size)}</span>
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Manual path input (fallback) */}
            <div className="px-6 pt-3">
              <input
                type="text"
                value={filePath}
                onChange={e => setFilePath(e.target.value)}
                placeholder="/path/to/data.h5cd"
                className="w-full border border-gray-200 rounded px-3 py-2 text-sm font-mono focus:outline-none focus:border-blue-400"
                onKeyDown={e => e.key === 'Enter' && loadPath(filePath)}
              />
              {loadError && <p className="text-xs text-red-500 mt-2">{loadError}</p>}
            </div>

            {/* Footer */}
            <div className="flex justify-end gap-2 px-6 py-4">
              <button
                onClick={() => setShowModal(false)}
                className="px-4 py-1.5 text-sm text-gray-600 hover:text-gray-800"
              >
                Cancel
              </button>
              <button
                onClick={() => loadPath(filePath)}
                disabled={loading || !filePath.trim()}
                className="px-4 py-1.5 text-sm bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50"
              >
                {loading ? 'Loading…' : 'Open'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
