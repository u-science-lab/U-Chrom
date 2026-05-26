import { useEffect, useState } from 'react'

interface Entry {
  name: string
  type: 'dir' | 'file'
  path: string
  size?: number
}

interface BrowseResult {
  path: string
  parent: string | null
  entries: Entry[]
}

interface Props {
  onSelect: (path: string) => void
  onClose: () => void
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export default function FileBrowser({ onSelect, onClose }: Props) {
  const [result, setResult] = useState<BrowseResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [hovered, setHovered] = useState<string | null>(null)

  function navigate(path: string) {
    setLoading(true)
    setError('')
    fetch(`/api/browse?path=${encodeURIComponent(path)}`)
      .then(r => r.json())
      .then(d => {
        if (d.detail) { setError(d.detail.error ?? 'Error'); setLoading(false); return }
        setResult(d)
        setLoading(false)
      })
      .catch(() => { setError('Network error'); setLoading(false) })
  }

  useEffect(() => {
    fetch('/api/browse')
      .then(r => r.json())
      .then(d => { if (!d.detail) setResult(d) })
      .catch(() => {})
  }, [])

  const s = {
    overlay: {
      position: 'fixed' as const, inset: 0, background: 'rgba(0,0,0,0.6)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    },
    modal: {
      background: '#1e1e2e', border: '1px solid #313244', borderRadius: 8,
      width: 480, maxHeight: '70vh', display: 'flex', flexDirection: 'column' as const,
      boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
    },
    header: {
      padding: '10px 14px', borderBottom: '1px solid #313244',
      display: 'flex', alignItems: 'center', gap: 8,
    },
    title: { color: '#cdd6f4', fontSize: 13, fontWeight: 600, flex: 0 },
    pathBar: {
      color: '#6c7086', fontSize: 11, flex: 1, overflow: 'hidden',
      textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const, marginLeft: 8,
    },
    closeBtn: {
      background: 'none', border: 'none', color: '#6c7086', cursor: 'pointer',
      fontSize: 16, padding: '0 4px', lineHeight: 1,
    },
    body: { flex: 1, overflowY: 'auto' as const, padding: '4px 0' },
    row: (key: string, isDir: boolean) => ({
      display: 'flex', alignItems: 'center', gap: 8, padding: '5px 14px',
      cursor: 'pointer', fontSize: 12,
      color: isDir ? '#cdd6f4' : '#a6e3a1',
      background: hovered === key ? '#313244' : 'transparent',
    }),
    icon: { width: 16, flexShrink: 0 as const, fontSize: 13 },
    size: { marginLeft: 'auto', color: '#6c7086', fontSize: 11 },
    empty: { color: '#6c7086', fontSize: 12, padding: '16px 14px', textAlign: 'center' as const },
    err: { color: '#f38ba8', fontSize: 12, padding: '8px 14px' },
  }

  return (
    <div style={s.overlay} onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div style={s.modal}>
        <div style={s.header}>
          <span style={s.title}>Browse Files</span>
          <span style={s.pathBar}>{result?.path ?? '…'}</span>
          <button style={s.closeBtn} onClick={onClose}>✕</button>
        </div>
        <div style={s.body}>
          {error && <div style={s.err}>{error}</div>}
          {loading && <div style={s.empty}>Loading…</div>}
          {!loading && result && (
            <>
              {result.parent !== null && (
                <div
                  style={s.row('..', true)}
                  onClick={() => navigate(result.parent!)}
                  onMouseEnter={() => setHovered('..')}
                  onMouseLeave={() => setHovered(null)}>
                  <span style={s.icon}>↑</span>
                  <span>..</span>
                </div>
              )}
              {result.entries.length === 0 && <div style={s.empty}>Empty directory</div>}
              {result.entries.map(entry => (
                <div
                  key={entry.path}
                  style={s.row(entry.path, entry.type === 'dir')}
                  onClick={() => entry.type === 'dir' ? navigate(entry.path) : onSelect(entry.path)}
                  onMouseEnter={() => setHovered(entry.path)}
                  onMouseLeave={() => setHovered(null)}>
                  <span style={s.icon}>{entry.type === 'dir' ? '📁' : '📄'}</span>
                  <span>{entry.name}</span>
                  {entry.size !== undefined && <span style={s.size}>{fmtSize(entry.size)}</span>}
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
