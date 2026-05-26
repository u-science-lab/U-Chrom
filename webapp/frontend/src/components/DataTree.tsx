import { useEffect, useRef, useState } from 'react'
import { ws } from '../ws'
import { useAppStore } from '../store'
import FileBrowser from './FileBrowser'

interface DataInfo {
  cell_count: number
  chroms: string[]
  umap_url: string | null
}

export default function DataTree() {
  const [path, setPath] = useState('')
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<DataInfo | null>(null)
  const [error, setError] = useState('')
  const [showBrowser, setShowBrowser] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const bumpDataVersion = useAppStore(s => s.bumpDataVersion)

  useEffect(() => {
    const off = ws.onMessage('data_loaded', (p: any) => {
      setData(p)
      setLoading(false)
      setError('')
      bumpDataVersion()
    })
    return () => { off() }
  }, [])

  useEffect(() => {
    const off = ws.onMessage('error', (p: any) => {
      setError(p.message ?? 'Error')
      setLoading(false)
    })
    return () => { off() }
  }, [])

  function load(filePath: string) {
    setLoading(true)
    setError('')
    ws.send('load_data', { path: filePath, format: 'h5cd' })
  }

  async function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setLoading(true)
    setError('')
    const form = new FormData()
    form.append('file', file)
    const r = await fetch('/api/upload', { method: 'POST', body: form })
    if (!r.ok) { setError('Upload failed'); setLoading(false); return }
    const { path: uploaded } = await r.json()
    load(uploaded)
  }

  const s = {
    root: { width: 240, flexShrink: 0 as const, background: '#1e1e2e',
            borderRight: '1px solid #313244', display: 'flex', flexDirection: 'column' as const },
    header: { padding: '8px 10px', borderBottom: '1px solid #313244',
              color: '#cdd6f4', fontSize: 13, fontWeight: 600 },
    body: { flex: 1, padding: 8, overflowY: 'auto' as const },
    input: { width: '100%', background: '#313244', border: 'none', borderRadius: 4,
             padding: '5px 7px', color: '#cdd6f4', fontSize: 11, outline: 'none',
             boxSizing: 'border-box' as const },
    btn: { width: '100%', marginTop: 4, background: '#89b4fa', border: 'none',
           borderRadius: 4, padding: '5px 0', color: '#1e1e2e', fontSize: 11,
           cursor: 'pointer', fontWeight: 600 },
    row: { display: 'flex', alignItems: 'center', gap: 4, color: '#a6e3a1', fontSize: 11, marginTop: 2 },
    err: { color: '#f38ba8', fontSize: 11, marginTop: 4 },
  }

  return (
    <>
      <div style={s.root}>
      <div style={s.header}>Data</div>
      <div style={s.body}>
        {!data ? (
          <>
            <button style={s.btn} disabled={loading} onClick={() => setShowBrowser(true)}>
              Browse…
            </button>
            <div style={{ textAlign: 'center', color: '#6c7086', fontSize: 11, margin: '6px 0' }}>or enter path</div>
            <input style={s.input} value={path} onChange={e => setPath(e.target.value)}
              placeholder="/path/to/data.h5cd"
              onKeyDown={e => e.key === 'Enter' && path && load(path)} />
            <button style={{ ...s.btn, background: '#313244', color: '#cdd6f4' }}
              disabled={loading || !path} onClick={() => load(path)}>
              {loading ? 'Loading…' : 'Load path'}
            </button>
            <div style={{ textAlign: 'center', color: '#6c7086', fontSize: 11, margin: '6px 0' }}>or</div>
            <button style={{ ...s.btn, background: '#313244', color: '#cdd6f4' }}
              onClick={() => fileRef.current?.click()}>
              {loading ? 'Uploading…' : 'Upload file'}
            </button>
            <input ref={fileRef} type="file" accept=".h5cd,.csv" style={{ display: 'none' }}
              onChange={onFileChange} />
            {error && <div style={s.err}>{error}</div>}
          </>
        ) : (
          <>
            <div style={{ color: '#cdd6f4', fontSize: 12, fontWeight: 600, marginBottom: 6 }}>
              Loaded
            </div>
            <div style={s.row}>▸ {data.cell_count} cells</div>
            <div style={{ color: '#6c7086', fontSize: 11, marginTop: 6, marginBottom: 2 }}>Chromosomes:</div>
            {data.chroms.slice(0, 8).map(c => (
              <div key={c} style={{ ...s.row, color: '#89b4fa' }}>  {c}</div>
            ))}
            {data.chroms.length > 8 && (
              <div style={{ color: '#6c7086', fontSize: 11 }}>  +{data.chroms.length - 8} more</div>
            )}
            {data.umap_url && <div style={{ ...s.row, marginTop: 6 }}>▸ UMAP ✓</div>}
            <button style={{ ...s.btn, marginTop: 12, background: '#313244', color: '#cdd6f4' }}
              onClick={() => { setData(null); setPath('') }}>
              Unload
            </button>
          </>
        )}
      </div>
      </div>
      {showBrowser && (
        <FileBrowser
          onSelect={p => { setShowBrowser(false); load(p) }}
          onClose={() => setShowBrowser(false)}
        />
      )}
    </>
  )
}
