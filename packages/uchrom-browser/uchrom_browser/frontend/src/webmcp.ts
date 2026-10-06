/**
 * WebMCP (W3C Web Machine Learning CG draft): register the browser actions as tools of this page,
 * so an agent running in the browser can use them with no setup.  Feature-detected — a no-op in
 * browsers without `document.modelContext` (or the older `navigator.modelContext`).  Experimental.
 */

import { runAction, TOOLS } from './actions'

interface ModelContext {
  registerTool(tool: {
    name: string
    description: string
    inputSchema: Record<string, unknown>
    annotations?: Record<string, unknown>
    execute: (input: Record<string, unknown>) => Promise<unknown>
  }): unknown
}

export function modelContext(): ModelContext | null {
  const d = (typeof document !== 'undefined' ? document : undefined) as unknown as { modelContext?: ModelContext } | undefined
  const n = (typeof navigator !== 'undefined' ? navigator : undefined) as unknown as { modelContext?: ModelContext } | undefined
  return d?.modelContext ?? n?.modelContext ?? null
}

/** Returns the names of the tools registered (empty when WebMCP is unavailable). */
export function registerWebMcpTools(mc: ModelContext | null = modelContext()): string[] {
  if (!mc || typeof mc.registerTool !== 'function') return []
  const done: string[] = []
  for (const t of TOOLS) {
    try {
      mc.registerTool({
        name: `uchrom_${t.name}`,
        description: t.description,
        inputSchema: t.inputSchema,
        annotations: t.annotations,
        execute: async (input) => {
          const result = await runAction(t.name, input ?? {})
          return { content: [{ type: 'text', text: JSON.stringify(result) }] }
        },
      })
      done.push(t.name)
    } catch {
      /* a tool the page cannot register (e.g. a duplicate after hot reload) is skipped */
    }
  }
  return done
}
