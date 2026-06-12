import { lazy, Suspense } from 'react'
import { useAppStore } from '../store'
import { LOCAL_CONTACT_MAP_SPEC } from '../specs/localContactMapSpec'

const GoslingRenderer = lazy(() => import('./GoslingRenderer'))

// Remote demo spec (CpG Islands) for comparison/testing
export const REMOTE_DEMO_SPEC = {
  assembly: 'hg19',
  layout: 'linear',
  arrangement: 'vertical',
  views: [
    {
      xDomain: { chromosome: 'chr1', interval: [1, 3000000] },
      tracks: [
        {
          id: 'demo-track',
          title: 'CpG Islands (Remote Demo)',
          data: {
            url: 'https://server.gosling-lang.org/api/v1/tileset_info/?d=gene-annotation',
            type: 'beddb',
            genomicFields: [{ index: 1, name: 'start' }, { index: 2, name: 'end' }],
            valueFields: [{ index: 5, name: 'strand', type: 'nominal' }],
            exonIntervalFields: [{ index: 12, name: 'start' }, { index: 13, name: 'end' }],
          },
          mark: 'triangleRight',
          x: { field: 'start', type: 'genomic', axis: 'top' },
          xe: { field: 'end', type: 'genomic' },
          size: { value: 10 },
          color: { value: '#3b82f6' },
          width: 800,
          height: 60,
        }
      ]
    }
  ]
}

export default function GenomicPanel() {
  const activeSpec = useAppStore(s => s.activeGoslingSpec)
  const activeSpecId = useAppStore(s => s.activeGoslingSpecId)
  const goslingArtifacts = useAppStore(s => s.goslingArtifacts)
  const setActiveGoslingSpec = useAppStore(s => s.setActiveGoslingSpec)
  const viewport = useAppStore(s => s.viewport)
  const requestExport = useAppStore(s => s.requestExport)
  const dataVersion = useAppStore(s => s.dataVersion)

  // The local contact map pulls from the backend tileset/strc endpoints, which
  // 404 until a ChromData file is loaded. Only mount it once data exists —
  // otherwise Gosling fires requests against an empty session and its CSV
  // fetcher crashes on the undefined response
  // (`Cannot read properties of undefined (reading 'filter')`).
  const hasData = dataVersion > 0

  // Priority: agent-generated spec > local contact map (only once data loaded).
  const specToRender = activeSpec ?? (hasData ? LOCAL_CONTACT_MAP_SPEC : null)

  const isLocalDefault = !activeSpec

  return (
    <div className="h-full flex flex-col bg-white overflow-hidden">
      {/* Control bar - manual view selection */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border-subtle text-xs">
        <span className="text-gray-500">View:</span>
        <button
          onClick={() => setActiveGoslingSpec(undefined, undefined)}
          className={`px-2 py-1 rounded transition-colors ${
            isLocalDefault
              ? 'bg-blue-500 text-white'
              : 'bg-white border border-gray-200 text-gray-600 hover:border-blue-400'
          }`}
        >
          Local Contact Map
        </button>
        <button
          onClick={() => setActiveGoslingSpec(REMOTE_DEMO_SPEC, 'remote-demo')}
          className={`px-2 py-1 rounded transition-colors ${
            activeSpecId === 'remote-demo'
              ? 'bg-blue-500 text-white'
              : 'bg-white border border-gray-200 text-gray-600 hover:border-blue-400'
          }`}
        >
          Remote Demo
        </button>

        {/* Viewport display */}
        {viewport && (
          <span className="ml-auto text-gray-500 font-mono">
            {viewport.chrom}:{viewport.start?.toLocaleString()}-{viewport.end?.toLocaleString()}
          </span>
        )}

        {/* Manual export — same path the agent's export_view tool triggers */}
        <button
          onClick={() => requestExport('png')}
          className={`px-2 py-1 rounded border border-gray-200 text-gray-600 hover:border-blue-400 transition-colors ${viewport ? '' : 'ml-auto'}`}
          title="Export current view as PNG"
        >
          Export PNG
        </button>
      </div>

      {/* Sub-toolbar: artifact list */}
      {goslingArtifacts.length > 0 && (
        <div className="flex items-center gap-2 px-4 py-2 border-b border-gray-100 bg-yellow-50 overflow-x-auto">
          <span className="text-xs text-gray-400 whitespace-nowrap">Agent specs:</span>
          {goslingArtifacts.map(a => (
            <button
              key={a.id}
              onClick={() => setActiveGoslingSpec(a.spec, a.id)}
              className={`text-xs px-2 py-1 rounded whitespace-nowrap transition-colors ${
                a.id === activeSpecId
                  ? 'bg-blue-500 text-white'
                  : 'bg-white border border-gray-200 text-gray-600 hover:border-blue-400'
              }`}
            >
              {a.title}
            </button>
          ))}
        </div>
      )}

      {/* Main Gosling renderer */}
      <div className="flex-1 overflow-auto">
        {specToRender ? (
          <Suspense fallback={
            <div className="h-full flex items-center justify-center text-gray-400 text-sm">
              Loading Gosling...
            </div>
          }>
            <GoslingRenderer spec={specToRender} />
          </Suspense>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-center px-6 text-gray-400">
            <div className="text-sm font-medium text-gray-500 mb-1">No data loaded</div>
            <div className="text-xs max-w-xs">
              Open a ChromData file (top-right) to view the contact map, or pick
              "Remote Demo" to preview a sample track.
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
