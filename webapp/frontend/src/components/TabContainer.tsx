import { useAppStore, type TabType } from '../store'
import GenomicPanel from './GenomicPanel'
import EmbeddingPanel from './EmbeddingPanel'
import Structure3DPanel from './Structure3DPanel'
import NotebookPanel from './NotebookPanel'

const TAB_LABELS: Record<TabType, string> = {
  genomic: 'Genomic',
  embedding: 'Embedding',
  structure3d: '3D Structure',
  notebook: 'Code',
}

export default function TabContainer() {
  const activeTab = useAppStore(s => s.activeTab)
  const setActiveTab = useAppStore(s => s.setActiveTab)
  const tabs: TabType[] = ['genomic', 'embedding', 'structure3d', 'notebook']

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
      </div>
    </div>
  )
}
