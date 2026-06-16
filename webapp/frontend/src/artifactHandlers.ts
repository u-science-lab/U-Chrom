import { useAppStore, type GoslingArtifact, nextCellId } from './store'
import { type Operation } from 'fast-json-patch'

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
    const id = (msg.artifact_id as string) || `viz_${Date.now()}`
    const artifact: GoslingArtifact = {
      id,
      title: (msg.title as string) || 'Genomic Visualization',
      spec: msg.spec as object,
      createdAt: Date.now(),
      active: false,
    }
    store.addGoslingArtifact(artifact)
    store.setActiveGoslingSpec(artifact.spec, artifact.id)
    // Seed this view's local revision so later patch base_revision checks align.
    if (typeof msg.revision === 'number') {
      useAppStore.setState(s => ({
        viewRevisions: { ...s.viewRevisions, [id]: msg.revision as number },
      }))
    }
    ctx.pushAssistant(`[Visualization: ${artifact.title}]`)
  },

  // Standard RFC 6902 JSON-Patch delta (AG-UI STATE_DELTA). The op array is
  // applied to the target view's state via fast-json-patch; base_revision lets
  // the store detect a gap and re-pull a full snapshot instead of mis-applying.
  gosling_patch: (msg) => {
    if (!msg.target_id) return
    // Accept the standard `ops` array; fall back to a legacy single `patch`
    // object so an in-flight older backend message still applies.
    let ops: Operation[] | null = null
    if (Array.isArray(msg.ops)) {
      ops = msg.ops as Operation[]
    } else if (msg.patch && typeof msg.patch === 'object') {
      ops = [msg.patch as Operation]
    }
    if (!ops || ops.length === 0) return
    useAppStore.getState().applyPatch(
      msg.target_id as string,
      ops,
      (msg.base_revision as number | null) ?? null,
      (msg.new_revision as number | null) ?? null,
    )
  },

  select_cells: (msg, ctx) => {
    const ids = (msg.cell_ids as string[]) || []
    useAppStore.getState().highlightCells(ids)
    useAppStore.getState().setActiveTab('embedding')
    ctx.pushAssistant(`[Selected ${ids.length} cell(s)]`)
  },

  color_embedding: (msg, ctx) => {
    const colorBy = (msg.color_by as string) || null
    useAppStore.getState().setEmbeddingColorBy(colorBy)
    useAppStore.getState().setActiveTab('embedding')
    ctx.pushAssistant(`[Colored embedding by ${colorBy ?? 'default'}]`)
  },

  // A cell-level UMAP was just computed (compute_embedding). Switch to the
  // Embedding tab and bump dataVersion so EmbeddingPanel re-fetches /api/umap.
  embedding_computed: (msg, ctx) => {
    useAppStore.getState().bumpDataVersion()
    useAppStore.getState().setActiveTab('embedding')
    const n = msg.n_cells as number | undefined
    const method = msg.method as string | undefined
    ctx.pushAssistant(
      `[Embedding computed${n != null ? ` for ${n} cells` : ''}` +
      `${method ? ` (method: ${method})` : ''}]`,
    )
  },

  show_structure: (msg, ctx) => {
    const cellId = (msg.cell_id as string) || null
    const chrom = (msg.chrom as string) || null
    // Restrict the 3D view to this cell (+ optional chrom) and highlight it.
    useAppStore.getState().setStructureSelection(cellId, chrom)
    if (cellId) useAppStore.getState().highlightCells([cellId])
    useAppStore.getState().setActiveTab('structure3d')
    ctx.pushAssistant(
      `[Showing 3D structure for ${cellId ?? 'all cells'}${chrom ? `, ${chrom}` : ''}]`,
    )
  },

  color_structure: (msg, ctx) => {
    const colorBy = (msg.color_by as string) || null
    useAppStore.getState().setStructureColorBy(colorBy)
    useAppStore.getState().setActiveTab('structure3d')
    ctx.pushAssistant(`[Colored 3D structure by ${colorBy ?? 'default'}]`)
  },

  export_view: (msg, ctx) => {
    const fmt = (msg.format as 'png' | 'pdf') || 'png'
    useAppStore.getState().requestExport(fmt)
    ctx.pushAssistant(`[Exporting current view as ${fmt.toUpperCase()}]`)
  },

  analysis_result: (msg, ctx) => {
    // Bump dataVersion so panels re-fetch derived data (TAD/loop/compartment).
    useAppStore.getState().bumpDataVersion()
    const analysisType = msg.analysis_type as string
    const chrom = msg.chrom as string
    useAppStore.getState().setAnalysisResult(`${analysisType}:${chrom}`, {
      analysis_type: analysisType,
      chrom,
      data_url: msg.data_url as string | undefined,
      record_count: msg.record_count as number | undefined,
      chromosome_field: msg.chromosome_field as string | undefined,
      genomic_fields: msg.genomic_fields as string[] | undefined,
      suggested_mark: msg.suggested_mark as string | undefined,
    })
    const at = msg.analysis_type as string
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
      images?: string[]
    }) || {}
    const outputs: Array<{ type: 'text' | 'image' | 'error'; content: string }> = []
    if (c.error) {
      outputs.push({ type: 'error', content: c.error })
    } else if (c.output) {
      outputs.push({ type: 'text', content: c.output })
    }
    for (const img of c.images || []) {
      outputs.push({ type: 'image', content: img })
    }
    useAppStore.getState().addNotebookCell({
      id: nextCellId(),
      code: c.code || '',
      outputs,
      running: false,
    })
    useAppStore.getState().setActiveTab('notebook')
    const nImg = (c.images || []).length
    const preview = c.error
      ? `error: ${c.error.slice(0, 80)}`
      : (c.output || '').slice(0, 80) || (nImg ? `${nImg} figure(s)` : '')
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
