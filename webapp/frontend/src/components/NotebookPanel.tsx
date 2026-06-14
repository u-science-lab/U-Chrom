import { useState, useEffect } from 'react'
import { useAppStore, type NotebookCell } from '../store'
import { ws } from '../ws'

interface NotebookCellContent {
  code: string
  output?: string
  error?: string
  status: string
  images?: string[]
}

function CellView({ cell }: { cell: NotebookCell }) {
  const { updateCellOutput, setCellRunning } = useAppStore()
  const [code, setCode] = useState(cell.code)

  const runCell = async () => {
    setCellRunning(cell.id, true)
    try {
      const res = await fetch('/api/execute_code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      })
      const data = await res.json()
      const outputs: NotebookCell['outputs'] = []
      if (data.error) {
        outputs.push({ type: 'error', content: String(data.error) })
      } else if (data.output) {
        outputs.push({ type: 'text', content: String(data.output) })
      }
      for (const img of (data.images as string[] | undefined) || []) {
        outputs.push({ type: 'image', content: img })
      }
      updateCellOutput(cell.id, outputs)
    } catch (err) {
      updateCellOutput(cell.id, [{ type: 'error', content: String(err) }])
    }
    setCellRunning(cell.id, false)
  }

  return (
    <div className="border border-border-primary rounded-lg overflow-hidden mb-3">
      <div className="bg-bg-secondary px-3 py-1.5 flex items-center justify-between">
        <span className="text-xs text-text-tertiary font-mono">Python</span>
        <button
          onClick={runCell}
          disabled={cell.running}
          className="text-xs px-3 py-1 bg-accent-blue text-white rounded hover:bg-blue-600 disabled:opacity-50 transition-colors"
        >
          {cell.running ? '...' : '▶ Run'}
        </button>
      </div>
      <textarea
        value={code}
        onChange={(e) => setCode(e.target.value)}
        className="w-full px-3 py-2 text-sm font-mono bg-bg-primary text-text-primary border-0 resize-none focus:outline-none"
        rows={Math.max(3, code.split('\n').length)}
      />
      {cell.outputs.length > 0 && (
        <div className="border-t border-border-primary bg-bg-secondary px-3 py-2 space-y-1">
          {cell.outputs.map((output, idx) => (
            <div key={idx} className={`text-xs font-mono ${output.type === 'error' ? 'text-red-500' : 'text-text-primary'}`}>
              {output.type === 'image' ? (
                <img src={`data:image/png;base64,${output.content}`} className="max-w-full" alt="output" />
              ) : (
                <pre className="whitespace-pre-wrap">{output.content}</pre>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function NotebookPanel() {
  const { notebookCells } = useAppStore()
  const [wsConnected, setWsConnected] = useState(false)

  // WebSocket listener for notebook_cell artifacts (via shared ws singleton)
  useEffect(() => {
    const offStatus = ws.onStatus(setWsConnected)

    const offArtifact = ws.onMessage('artifact', (msg) => {
      if (msg.artifact_type !== 'notebook_cell' || !msg.content) return
      const content = msg.content as NotebookCellContent
      const outputs: NotebookCell['outputs'] = []
      if (content.error) {
        outputs.push({ type: 'error', content: content.error })
      } else if (content.output) {
        outputs.push({ type: 'text', content: content.output })
      }
      for (const img of content.images || []) {
        outputs.push({ type: 'image', content: img })
      }
      useAppStore.getState().addNotebookCell({
        id: `cell_${Date.now()}`,
        code: content.code || '',
        outputs,
        running: content.status === 'running',
      })
    })

    return () => { offStatus(); offArtifact() }
  }, [])

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="px-4 py-2 border-b border-border-primary bg-bg-secondary flex items-center justify-between">
        <h2 className="text-sm font-semibold text-text-primary">Notebook</h2>
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${wsConnected ? 'bg-accent-green' : 'bg-gray-300'}`} />
          <span className="text-xs text-text-tertiary">{wsConnected ? 'Live' : 'Offline'}</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {notebookCells.length === 0 ? (
          <div className="text-center text-text-tertiary text-sm mt-8">
            <p>No cells yet.</p>
            <p className="mt-2">Agent will add analysis results here, or you can add cells manually.</p>
          </div>
        ) : (
          notebookCells.map(cell => <CellView key={cell.id} cell={cell} />)
        )}
      </div>

      <div className="border-t border-border-primary px-4 py-2">
        <button
          onClick={() => useAppStore.getState().addNotebookCell({
            id: `cell_${Date.now()}`,
            code: '',
            outputs: [],
            running: false
          })}
          className="text-sm text-accent-blue hover:text-blue-600 transition-colors"
        >
          + Add cell
        </button>
      </div>
    </div>
  )
}
