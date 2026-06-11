import { useAppStore, type TabType } from '../store'
import GenomicPanel from './GenomicPanel'
import EmbeddingPanel from './EmbeddingPanel'
import Structure3DPanel from './Structure3DPanel'
import NotebookPanel from './NotebookPanel'
import { ComponentRenderer, type ComponentNode } from './ComponentRenderer'

const TAB_LABELS: Record<TabType, string> = {
  genomic: 'Genomic',
  embedding: 'Embedding',
  structure3d: '3D Structure',
  notebook: 'Code',
  custom: 'Custom',
}

function CustomPanel() {
  const tree = useAppStore(s => s.activeComponentTree)
  if (!tree) {
    return <div className="p-4 text-sm text-text-secondary">No custom view composed yet.</div>
  }
  return (
    <div className="h-full overflow-auto p-3">
      <ComponentRenderer node={tree.tree as ComponentNode} />
    </div>
  )
}

export default function TabContainer() {
  const activeTab = useAppStore(s => s.activeTab)
  const setActiveTab = useAppStore(s => s.setActiveTab)
  const hasCustom = useAppStore(s => s.activeComponentTree !== null)
  // The 'custom' tab only appears once the agent has composed a component tree.
  const tabs: TabType[] = ['genomic', 'embedding', 'structure3d', 'notebook']
  if (hasCustom) tabs.push('custom')

  return (
    <div className="h-full flex flex-col bg-bg-primary">
      <div className="flex border-b border-border-primary bg-bg-secondary">
        {tabs.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-6 py-3 text-sm font-medium transition-colors ${
              activeTab === tab
                ? 'text-accent-blue border-b-2 border-accent-blue bg-bg-primary'
                : 'text-text-secondary hover:text-text-primary'
            }`}
          >
            {TAB_LABELS[tab]}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-hidden">
        {activeTab === 'genomic' && <GenomicPanel />}
        {activeTab === 'embedding' && <EmbeddingPanel />}
        {activeTab === 'structure3d' && <Structure3DPanel />}
        {activeTab === 'notebook' && <NotebookPanel />}
        {activeTab === 'custom' && <CustomPanel />}
      </div>
    </div>
  )
}
