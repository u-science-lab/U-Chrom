import { lazy, Suspense, type ReactNode } from 'react'
import { useAppStore } from '../store'
import EmbeddingPanel from './EmbeddingPanel'
import Structure3DPanel from './Structure3DPanel'

// GoslingRenderer is the heavy chunk (~5MB) — keep it lazy, like GenomicPanel.
const GoslingRenderer = lazy(() => import('./GoslingRenderer'))

/**
 * Tier-2 generative UI: render an agent-composed tree of WHITELISTED components.
 *
 * The agent never ships code or markup — it ships a declarative node tree
 * ({component, props, children}). Every `component` name must resolve in
 * COMPONENT_REGISTRY; an unknown name renders a visible error instead of
 * anything dangerous. props are literal values or {$dataPath} references that
 * we resolve against the store — there is no expression evaluation.
 */
export interface ComponentNode {
  component: string
  props?: Record<string, unknown>
  children?: ComponentNode[]
}

// Resolve a {$dataPath: "a.b.c"} prop against the store, else pass through.
function resolveProp(value: unknown): unknown {
  if (value && typeof value === 'object' && '$dataPath' in (value as object)) {
    const path = (value as { $dataPath: string }).$dataPath
    const root = useAppStore.getState() as unknown as Record<string, unknown>
    return path.split('.').reduce<unknown>(
      (acc, key) => (acc && typeof acc === 'object'
        ? (acc as Record<string, unknown>)[key]
        : undefined),
      root,
    )
  }
  return value
}

function resolveProps(props?: Record<string, unknown>): Record<string, unknown> {
  if (!props) return {}
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(props)) out[k] = resolveProp(v)
  return out
}

type LeafProps = { props: Record<string, unknown>; children: ReactNode }

const COMPONENT_REGISTRY: Record<string, (p: LeafProps) => ReactNode> = {
  Panel: ({ props, children }) => (
    <div className="border border-border-primary rounded-lg overflow-hidden flex flex-col min-h-0">
      {props.title ? (
        <div className="px-3 py-1.5 bg-bg-secondary border-b border-border-primary text-xs font-medium text-text-secondary">
          {String(props.title)}
        </div>
      ) : null}
      <div className="flex-1 min-h-0 p-2">{children}</div>
    </div>
  ),
  Row: ({ children }) => <div className="flex flex-row gap-3 min-h-0">{children}</div>,
  Column: ({ children }) => <div className="flex flex-col gap-3 min-h-0">{children}</div>,
  Text: ({ props }) => <p className="text-sm text-text-primary">{String(props.value ?? props.text ?? '')}</p>,
  Table: ({ props }) => {
    const rows = Array.isArray(props.rows) ? (props.rows as unknown[][]) : []
    const headers = Array.isArray(props.headers) ? (props.headers as string[]) : []
    return (
      <table className="text-xs border-collapse w-full">
        {headers.length > 0 && (
          <thead>
            <tr>{headers.map((h, i) => <th key={i} className="border border-border-primary px-2 py-1 text-left">{h}</th>)}</tr>
          </thead>
        )}
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>{r.map((c, j) => <td key={j} className="border border-border-primary px-2 py-1">{String(c)}</td>)}</tr>
          ))}
        </tbody>
      </table>
    )
  },
  Button: ({ props }) => (
    <button className="px-3 py-1.5 bg-accent-blue text-white text-sm rounded hover:bg-blue-600">
      {String(props.label ?? 'Button')}
    </button>
  ),
  Slider: ({ props }) => (
    <label className="flex items-center gap-2 text-xs text-text-secondary">
      {props.label ? <span>{String(props.label)}</span> : null}
      <input
        type="range"
        min={Number(props.min ?? 0)}
        max={Number(props.max ?? 100)}
        defaultValue={Number(props.value ?? 50)}
        readOnly
      />
    </label>
  ),
  Select: ({ props }) => {
    const options = Array.isArray(props.options) ? (props.options as string[]) : []
    return (
      <select className="text-sm border border-border-primary rounded px-2 py-1" defaultValue={String(props.value ?? '')}>
        {options.map((o, i) => <option key={i} value={o}>{o}</option>)}
      </select>
    )
  },
  GoslingView: ({ props }) => {
    // Render an existing gosling view by id, else the active spec.
    const viewId = props.view_id as string | undefined
    const artifact = useAppStore(s =>
      viewId ? s.goslingArtifacts.find(a => a.id === viewId) : undefined,
    )
    const activeSpec = useAppStore(s => s.activeGoslingSpec)
    const spec = artifact?.spec ?? activeSpec
    if (!spec) return <div className="text-xs text-text-secondary p-2">No visualization yet.</div>
    return (
      <Suspense fallback={<div className="text-xs p-2">Loading…</div>}>
        <div className="min-h-[200px]"><GoslingRenderer spec={spec} /></div>
      </Suspense>
    )
  },
  EmbeddingView: () => (
    <div className="min-h-[200px]"><EmbeddingPanel /></div>
  ),
  StructureView: () => (
    <div className="min-h-[200px]"><Structure3DPanel /></div>
  ),
}

export function ComponentRenderer({ node }: { node: ComponentNode }): ReactNode {
  if (!node || typeof node !== 'object' || !node.component) {
    return <div className="text-xs text-accent-red">Invalid component node</div>
  }
  const impl = COMPONENT_REGISTRY[node.component]
  if (!impl) {
    // Whitelist boundary: never render an unknown component.
    return (
      <div className="text-xs text-accent-red border border-accent-red rounded px-2 py-1">
        Unknown component: {node.component}
      </div>
    )
  }
  const children = (node.children ?? []).map((child, i) => (
    <ComponentRenderer key={i} node={child} />
  ))
  return impl({ props: resolveProps(node.props), children })
}

export default ComponentRenderer
