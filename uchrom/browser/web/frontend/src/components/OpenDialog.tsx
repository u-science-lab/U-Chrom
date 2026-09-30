import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { filePlaces, listFiles, openDataset } from '../api'
import { addRecent, baseName, breadcrumbs, fmtDate, fmtSize, loadRecent, saveRecent } from '../datasets'
import { useStore } from '../store'
import type { FileEntry, FileListing, FilePlace } from '../types'

/** Last folder the dialog showed (per viewer), to reopen where one left off. */
const LAST_DIR_KEY = 'uchrom.browser.openDir'
const lastDir = () => {
  try {
    return localStorage.getItem(LAST_DIR_KEY)
  } catch {
    return null
  }
}

/**
 * Open a dataset on the server: places (server folder, home, the loaded datasets' folders) and recently
 * opened datasets on the left; breadcrumbs, a path field and a filter above a listing of the folder.
 * Folders open with a click; datasets (.chromdata.zarr, .cdz, .csv) open with a double-click or
 * Open.  Esc or a click outside closes it.
 */
export function OpenDialog({ onClose }: { onClose(): void }) {
  const addDataset = useStore((s) => s.addDataset)
  const [listing, setListing] = useState<FileListing | null>(null)
  const [places, setPlaces] = useState<FilePlace[]>([])
  const [recent, setRecent] = useState<string[]>(loadRecent)
  const [dir, setDir] = useState<string | null>(lastDir())
  const [pathText, setPathText] = useState('')
  const [filter, setFilter] = useState('')
  const [selected, setSelected] = useState<FileEntry | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [hidden, setHidden] = useState(false)
  const filterRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    filePlaces()
      .then(setPlaces)
      .catch(() => {})
  }, [])
  useEffect(() => {
    let live = true
    setError(null)
    listFiles(dir, hidden)
      .then((l) => {
        if (!live) return
        setListing(l)
        setPathText(l.path)
        setSelected(null)
        setFilter('')
        try {
          localStorage.setItem(LAST_DIR_KEY, l.path)
        } catch {
          /* no storage */
        }
      })
      .catch((e: Error) => {
        if (!live) return
        if (dir && dir === lastDir()) setDir(null) // a remembered folder that is gone: start at the server's
        else setError(e.message)
      })
    return () => {
      live = false
    }
  }, [dir, hidden])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
      }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [onClose])

  const open = useCallback(
    async (path: string) => {
      setBusy(path)
      setError(null)
      try {
        addDataset(await openDataset(path))
        const r = addRecent(loadRecent(), path)
        saveRecent(r)
        setRecent(r)
        onClose()
      } catch (e) {
        setError((e as Error).message)
      } finally {
        setBusy(null)
      }
    },
    [addDataset, onClose],
  )
  const activate = (e: FileEntry) => (e.kind === 'dir' ? setDir(e.path) : e.kind === 'dataset' ? void open(e.path) : undefined)
  const shown = useMemo(() => {
    const f = filter.trim().toLowerCase()
    return (listing?.entries ?? []).filter((e) => !f || e.name.toLowerCase().includes(f))
  }, [listing, filter])
  const nData = (listing?.entries ?? []).filter((e) => e.kind === 'dataset').length

  const goPath = () => {
    const t = pathText.trim()
    if (!t) return
    // a dataset path typed / pasted: open it; else list the folder
    if (/\.(chromdata\.zarr|cdz|csv|csv\.gz)\/?$/i.test(t)) void open(t.replace(/\/$/, ''))
    else setDir(t)
  }

  return createPortal(
    <div className="modal-backdrop" onPointerDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="open-dialog" role="dialog" aria-modal="true" aria-label="Open dataset">
        <header className="od-head">
          <h2>Open dataset</h2>
          <button className="od-x" onClick={onClose} aria-label="Close" title="Close (Esc)">
            ×
          </button>
        </header>
        <div className="od-body">
          <nav className="od-side">
            <div className="od-side-title">Places</div>
            {places.map((p) => (
              <button key={p.path} className={`od-place${listing?.path === p.path ? ' current' : ''}`} onClick={() => setDir(p.path)} title={p.path}>
                <FolderIcon />
                <span>{p.label}</span>
              </button>
            ))}
            {recent.length > 0 && (
              <>
                <div className="od-side-title">Recent</div>
                {recent.map((r) => (
                  <button key={r} className="od-place" onClick={() => void open(r)} title={r} disabled={!!busy}>
                    <DataIcon />
                    <span>{baseName(r)}</span>
                  </button>
                ))}
              </>
            )}
          </nav>
          <section className="od-main">
            <div className="od-crumbs">
              <button className="od-up" disabled={!listing?.parent} onClick={() => listing?.parent && setDir(listing.parent)} title="Up one folder">
                ↑
              </button>
              <div className="od-crumb-list">
                {listing &&
                  breadcrumbs(listing.path, listing.sep).map((c, i, all) => (
                    <span key={c.path} className="od-crumb">
                      <button className={i === all.length - 1 ? 'last' : ''} onClick={() => setDir(c.path)} title={c.path}>
                        {c.label}
                      </button>
                      {i < all.length - 1 && c.label !== '/' && <span className="od-sep">›</span>}
                    </span>
                  ))}
              </div>
            </div>
            <div className="od-tools">
              <input
                className="od-path"
                value={pathText}
                onChange={(e) => setPathText(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && goPath()}
                placeholder="Path of a folder or a dataset on the server"
                spellCheck={false}
                title="Type or paste a folder (Enter lists it) or a dataset (Enter opens it)"
              />
              <input ref={filterRef} className="od-filter" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter…" />
              <label className="check small" title="Show hidden files and folders">
                <input type="checkbox" checked={hidden} onChange={(e) => setHidden(e.target.checked)} /> hidden
              </label>
            </div>
            <div className="od-list" role="listbox" aria-label="Folder contents">
              <div className="od-row od-colhead">
                <span />
                <span>Name</span>
                <span>Format</span>
                <span className="num">Size</span>
                <span>Modified</span>
              </div>
              {shown.map((e) => (
                <div
                  key={e.path}
                  role="option"
                  aria-selected={selected?.path === e.path}
                  className={`od-row od-${e.kind}${selected?.path === e.path ? ' selected' : ''}`}
                  onClick={() => (e.kind === 'dir' ? setDir(e.path) : setSelected(e))}
                  onDoubleClick={() => activate(e)}
                  title={e.kind === 'file' ? `${e.name} — not a dataset the browser opens` : e.path}
                >
                  <span className="od-icon">{e.kind === 'dir' ? <FolderIcon /> : e.kind === 'dataset' ? <DataIcon /> : <FileIcon />}</span>
                  <span className="od-name">{e.name}</span>
                  <span className="od-format">{e.format ?? ''}</span>
                  <span className="num">{e.kind === 'dir' ? '' : fmtSize(e.size)}</span>
                  <span className="muted">{fmtDate(e.mtime)}</span>
                </div>
              ))}
              {listing && !shown.length && <div className="od-empty muted">{filter ? 'Nothing matches the filter.' : 'This folder is empty.'}</div>}
              {!listing && !error && <div className="od-empty muted">Loading…</div>}
            </div>
          </section>
        </div>
        <footer className="od-foot">
          {error ? (
            <span className="error od-msg">{error}</span>
          ) : (
            <span className="muted od-msg">
              {selected
                ? selected.kind === 'dataset'
                  ? selected.path
                  : `${selected.name}: not a dataset the browser opens (.chromdata.zarr, .cdz, .csv)`
                : listing
                  ? `${nData} dataset${nData === 1 ? '' : 's'} in this folder${listing.truncated ? ' (listing truncated)' : ''}`
                  : ''}
            </span>
          )}
          <button onClick={onClose}>Cancel</button>
          <button className="primary" disabled={!selected || selected.kind !== 'dataset' || !!busy} onClick={() => selected && void open(selected.path)}>
            {busy ? 'Opening…' : 'Open'}
          </button>
        </footer>
      </div>
    </div>,
    document.body,
  )
}

function FolderIcon() {
  return (
    <svg viewBox="0 0 16 14" width="15" height="13" aria-hidden>
      <path d="M1.5 3.2c0-.7.5-1.2 1.2-1.2h3.6l1.5 1.6h5.5c.7 0 1.2.5 1.2 1.2v6.9c0 .7-.5 1.2-1.2 1.2H2.7c-.7 0-1.2-.5-1.2-1.2z" fill="currentColor" fillOpacity=".25" stroke="currentColor" strokeWidth="1.1" />
    </svg>
  )
}

function DataIcon() {
  return (
    <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.2">
      <ellipse cx="8" cy="3.5" rx="5.5" ry="2" />
      <path d="M2.5 3.5v9c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2v-9" />
      <path d="M2.5 8c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2" />
    </svg>
  )
}

function FileIcon() {
  return (
    <svg viewBox="0 0 14 16" width="13" height="15" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.1">
      <path d="M2 1.5h6.5L12 5v9.5H2z" />
      <path d="M8.5 1.5V5H12" />
    </svg>
  )
}
