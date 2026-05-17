import CellEmbedding from './CellEmbedding'
import StructureViewer from './StructureViewer'
import ContactMap from './ContactMap'

export default function MainCanvas() {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'row', height: '100%' }}>
      <div style={{ flex: 1, minWidth: 0 }}><CellEmbedding /></div>
      <div style={{ flex: 1, minWidth: 0 }}><StructureViewer /></div>
      <div style={{ flex: 1, minWidth: 0 }}><ContactMap /></div>
    </div>
  )
}
