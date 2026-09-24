import { useRef } from 'react'
import { activeView, useStore } from '../store'
import { EmbeddingPanel } from './EmbeddingPanel'
import { Viewport } from './Viewport'

/**
 * Centre area: the 3-D viewport plus, when open, the embedding view in the
 * layout the user picked — floating (inside the viewport), a tab, or a split
 * pane.  The viewport keeps the same position in the tree in every layout so
 * switching never re-creates the 3-D scene (camera, built geometry).
 */
export function Workspace() {
  const ui = useStore((s) => s.ui)
  const setUi = useStore((s) => s.setUi)
  const view = useStore(activeView)
  const hasEmbeddings = useStore((s) => (s.datasets.find((d) => d.id === s.activeDatasetId)?.embeddings?.length ?? 0) > 0)
  const rootRef = useRef<HTMLDivElement>(null)

  const docked = view.embeddingOpen && hasEmbeddings && ui.embeddingLayout !== 'float'
  const mode = docked ? ui.embeddingLayout : 'single'
  const tab = mode === 'tab' ? ui.activeTab : '3d'

  const onSplitStart = (e: React.PointerEvent) => {
    e.preventDefault()
    const root = rootRef.current
    if (!root) return
    const rect = root.getBoundingClientRect()
    const move = (ev: PointerEvent) => setUi({ splitFrac: (ev.clientX - rect.left) / rect.width })
    const up = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      document.body.classList.remove('resizing')
    }
    document.body.classList.add('resizing')
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  return (
    <div className={`workspace mode-${mode}`} ref={rootRef}>
      {mode === 'tab' && (
        <div className="ws-tabs">
          <button className={tab === '3d' ? 'active' : ''} onClick={() => setUi({ activeTab: '3d' })}>
            3D
          </button>
          <button className={tab === 'embedding' ? 'active' : ''} onClick={() => setUi({ activeTab: 'embedding' })}>
            Embedding
          </button>
        </div>
      )}
      <div className="ws-row">
        <div
          className={`ws-main ${mode === 'tab' && tab !== '3d' ? 'hidden' : ''}`}
          style={mode === 'split' ? { flex: `0 0 ${(ui.splitFrac * 100).toFixed(2)}%` } : undefined}
        >
          <Viewport />
        </div>
        {mode === 'split' && <div className="ws-splitter" onPointerDown={onSplitStart} title="Drag to resize" />}
        {docked && (
          <div className={`ws-side ${mode === 'tab' && tab !== 'embedding' ? 'hidden' : ''}`}>
            <EmbeddingPanel docked />
          </div>
        )}
      </div>
    </div>
  )
}
