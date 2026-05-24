import { Fragment } from 'react'
import { Group as PanelGroup, Panel, Separator as PanelResizeHandle } from 'react-resizable-panels'
import { useAppStore, PanelType, PanelDef } from '../store'
import CellEmbedding from './CellEmbedding'
import StructureViewer from './StructureViewer'
import ContactMap from './ContactMap'
import TrackPlot from './TrackPlot'
import PanelContainer from './PanelContainer'

const PANEL_TYPES: PanelType[] = ['umap', 'structure3d', 'contact_map', 'track_plot']
const PANEL_LABELS: Record<PanelType, string> = {
  umap: 'Cell Embedding', structure3d: '3D Structure',
  contact_map: 'Contact Map', track_plot: 'Track Plot',
}

function PanelContent({ type }: { type: PanelType }) {
  if (type === 'umap') return <CellEmbedding />
  if (type === 'structure3d') return <StructureViewer />
  if (type === 'contact_map') return <ContactMap />
  return <TrackPlot />
}

function AddPanelMenu() {
  const addPanel = useAppStore(s => s.addPanel)
  const panels = useAppStore(s => s.panels)
  const existing = new Set(panels.map(p => p.type))
  const available = PANEL_TYPES.filter(t => !existing.has(t))
  if (!available.length) return null
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: 8,
                  background: '#1e1e2e', borderLeft: '1px solid #313244', width: 140, flexShrink: 0 }}>
      <div style={{ color: '#6c7086', fontSize: 11, marginBottom: 2 }}>Add panel</div>
      {available.map(t => (
        <button key={t} onClick={() => addPanel(t)}
          style={{ background: '#313244', border: 'none', borderRadius: 4, padding: '5px 8px',
                   color: '#cdd6f4', fontSize: 11, cursor: 'pointer', textAlign: 'left' }}>
          + {PANEL_LABELS[t]}
        </button>
      ))}
    </div>
  )
}

export default function MainCanvas() {
  const panels = useAppStore(s => s.panels)
  const removePanel = useAppStore(s => s.removePanel)

  if (!panels.length) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: '#181825', color: '#6c7086', fontSize: 13 }}>
        <AddPanelMenu />
      </div>
    )
  }

  return (
    <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
      <PanelGroup orientation="horizontal" style={{ flex: 1 }}>
        {panels.map((p: PanelDef, i: number) => (
          <Fragment key={p.id}>
            {i > 0 && (
              <PanelResizeHandle
                style={{ width: 4, background: '#313244', cursor: 'col-resize' }} />
            )}
            <Panel minSize={15}>
              <PanelContainer title={p.label} onClose={() => removePanel(p.id)}>
                <PanelContent type={p.type} />
              </PanelContainer>
            </Panel>
          </Fragment>
        ))}
      </PanelGroup>
      <AddPanelMenu />
    </div>
  )
}
