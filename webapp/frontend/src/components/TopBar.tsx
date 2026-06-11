import { useState, useEffect, useRef } from 'react'
import { useAppStore } from '../store'
import { ws } from '../ws'

export default function TopBar() {
  const dataVersion = useAppStore(s => s.dataVersion)
  const bumpDataVersion = useAppStore(s => s.bumpDataVersion)

  const [showModal, setShowModal] = useState(false)
  const [filePath, setFilePath] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loadedFile, setLoadedFile] = useState<string | null>(null)
  const pendingPath = useRef<string | null>(null)

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

  const handleOpen = () => {
    const path = filePath.trim()
    if (!path) return
    if (!ws.connected) {
      setLoadError('Not connected to backend')
      return
    }
    setLoading(true)
    setLoadError(null)
    pendingPath.current = path
    ws.send('load_data', { path })
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
          onClick={() => { setLoadError(null); setShowModal(true) }}
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
          <div className="bg-white rounded-lg shadow-xl p-6 w-[480px] max-w-[90vw]">
            <h3 className="text-base font-medium text-gray-800 mb-4">Open ChromData File</h3>
            <input
              type="text"
              value={filePath}
              onChange={e => setFilePath(e.target.value)}
              placeholder="/path/to/data.h5cd"
              className="w-full border border-gray-200 rounded px-3 py-2 text-sm font-mono focus:outline-none focus:border-blue-400"
              onKeyDown={e => e.key === 'Enter' && handleOpen()}
              autoFocus
            />
            {loadError && <p className="text-xs text-red-500 mt-2">{loadError}</p>}
            <div className="flex justify-end gap-2 mt-4">
              <button
                onClick={() => setShowModal(false)}
                className="px-4 py-1.5 text-sm text-gray-600 hover:text-gray-800"
              >
                Cancel
              </button>
              <button
                onClick={handleOpen}
                disabled={loading || !filePath.trim()}
                className="px-4 py-1.5 text-sm bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50"
              >
                {loading ? 'Loading...' : 'Open'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
