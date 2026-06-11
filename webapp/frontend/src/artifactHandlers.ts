import { useAppStore, type GoslingArtifact, nextCellId } from './store'

/**
 * Registry of `agent_artifact` handlers, keyed by `artifact_type`.
 *
 * Replaces the if/elif ladder that used to live inline in ChatPanel. To add a
 * new agent-driven UI effect: register a handler here and emit the matching
 * `artifact_type` from the backend tool executor. ChatPanel stays generic.
 *
 * Each handler receives the raw message plus a small context object:
 *   - pushAssistant(text): append an assistant chat bubble
 * Store mutations go through useAppStore.getState() directly.
 */
export interface ArtifactContext {
  pushAssistant: (content: string) => void
}

export type ArtifactHandler = (msg: Record<string, unknown>, ctx: ArtifactContext) => void

export const ARTIFACT_HANDLERS: Record<string, ArtifactHandler> = {
  gosling_spec: (msg, ctx) => {
    if (!msg.spec) return
    const store = useAppStore.getState()
    const artifact: GoslingArtifact = {
      id: (msg.artifact_id as string) || `viz_${Date.now()}`,
      title: (msg.title as string) || 'Genomic Visualization',
      spec: msg.spec as object,
      createdAt: Date.now(),
      active: false,
    }
    store.addGoslingArtifact(artifact)
    store.setActiveGoslingSpec(artifact.spec, artifact.id)
    ctx.pushAssistant(`[Visualization: ${artifact.title}]`)
  },

  gosling_patch: (msg) => {
    if (!msg.target_id || !msg.patch) return
    useAppStore.getState().applyGoslingPatch(
      msg.target_id as string,
      msg.patch as { op: string; path: string; value: unknown },
    )
  },

  select_cells: (msg, ctx) => {
    const ids = (msg.cell_ids as string[]) || []
    useAppStore.getState().highlightCells(ids)
    useAppStore.getState().setActiveTab('embedding')
    ctx.pushAssistant(`[Selected ${ids.length} cell(s)]`)
  },

  color_embedding: (msg, ctx) => {
    useAppStore.getState().setActiveTab('embedding')
    ctx.pushAssistant(`[Colored embedding by ${msg.color_by as string}]`)
  },

  show_structure: (msg, ctx) => {
    const cellId = msg.cell_id as string
    if (cellId) useAppStore.getState().highlightCells([cellId])
    useAppStore.getState().setActiveTab('structure3d')
    ctx.pushAssistant(`[Showing 3D structure for ${cellId}]`)
  },

  color_structure: (msg, ctx) => {
    useAppStore.getState().setActiveTab('structure3d')
    ctx.pushAssistant(`[Colored 3D structure by ${msg.color_by as string}]`)
  },

  export_view: (msg, ctx) => {
    const fmt = (msg.format as 'png' | 'pdf') || 'png'
    useAppStore.getState().requestExport(fmt)
    ctx.pushAssistant(`[Exporting current view as ${fmt.toUpperCase()}]`)
  },

  analysis_result: (msg, ctx) => {
    // Bump dataVersion so panels re-fetch derived data (TAD/loop/compartment).
    useAppStore.getState().bumpDataVersion()
    const at = msg.analysis_type as string
    const chrom = msg.chrom as string
    ctx.pushAssistant(`[${at} analysis complete on ${chrom}]`)
  },

  // A custom agent-authored analysis was compiled + deployed as a live endpoint.
  // The agent will follow up with render_gosling pointing at data_url; here we
  // just surface that the endpoint is live so the user sees the deploy happened.
  custom_analysis_deployed: (msg, ctx) => {
    const id = msg.analysis_id as string
    const url = msg.data_url as string
    ctx.pushAssistant(`[Custom analysis "${id}" deployed → ${url}]`)
  },

  // Agent ran code in the analysis kernel. Surface the cell (code + output) in
  // the notebook tab so the user sees what the agent executed and its result.
  notebook_cell: (msg, ctx) => {
    const c = (msg.content as {
      code?: string
      output?: string
      error?: string | null
      status?: string
    }) || {}
    const outputs: Array<{ type: 'text' | 'image' | 'error'; content: string }> = []
    if (c.error) {
      outputs.push({ type: 'error', content: c.error })
    } else if (c.output) {
      outputs.push({ type: 'text', content: c.output })
    }
    useAppStore.getState().addNotebookCell({
      id: nextCellId(),
      code: c.code || '',
      outputs,
      running: false,
    })
    useAppStore.getState().setActiveTab('notebook')
    const preview = c.error
      ? `error: ${c.error.slice(0, 80)}`
      : (c.output || '').slice(0, 80)
    ctx.pushAssistant(`[Notebook cell executed${preview ? ` — ${preview}` : ''}]`)
  },

  // Tier-2 generative UI: the agent composed a layout from whitelisted
  // components. Store the tree; ComponentRenderer resolves each node against
  // the COMPONENT_REGISTRY (unknown names render a visible error, never code).
  component_tree: (msg, ctx) => {
    const id = (msg.artifact_id as string) || `cmp_${Date.now()}`
    const title = (msg.title as string) || 'Custom View'
    if (!msg.tree) return
    useAppStore.getState().setComponentTree(id, title, msg.tree)
    useAppStore.getState().setActiveTab('custom')
    ctx.pushAssistant(`[Custom view: ${title}]`)
  },
}
