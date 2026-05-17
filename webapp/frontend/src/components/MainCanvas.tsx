import CellEmbedding from './CellEmbedding'

export default function MainCanvas() {
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%' }}>
      <CellEmbedding />
    </div>
  )
}
