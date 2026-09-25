import type { Layer, LayerStyle } from './types'

export const DEFAULT_STYLE: LayerStyle = {
  mode: 'line',
  colorMode: 'rainbow',
  color: '#4fc3f7',
  opacity: 1,
  lineWidth: 1,
  tubeRadius: null,
  pointSize: 4,
  highQuality: false,
}

/** Ids of `id` and all its descendants. */
export function descendantIds(layers: Layer[], id: string): Set<string> {
  const out = new Set<string>([id])
  let grew = true
  while (grew) {
    grew = false
    for (const l of layers) {
      if (l.parentId && out.has(l.parentId) && !out.has(l.id)) {
        out.add(l.id)
        grew = true
      }
    }
  }
  return out
}

/** Remove a layer together with its whole subtree. */
export function removeCascade(layers: Layer[], id: string): Layer[] {
  const gone = descendantIds(layers, id)
  return layers.filter((l) => !gone.has(l.id))
}

/**
 * Depth-first order (parents before children, siblings in insertion order)
 * with depth, for rendering the layer tree.
 */
export function treeOrder(layers: Layer[]): { layer: Layer; depth: number }[] {
  const byParent = new Map<string | null, Layer[]>()
  const ids = new Set(layers.map((l) => l.id))
  for (const l of layers) {
    const key = l.parentId && ids.has(l.parentId) ? l.parentId : null
    if (!byParent.has(key)) byParent.set(key, [])
    byParent.get(key)!.push(l)
  }
  const out: { layer: Layer; depth: number }[] = []
  const walk = (parent: string | null, depth: number) => {
    for (const l of byParent.get(parent) ?? []) {
      out.push({ layer: l, depth })
      walk(l.id, depth + 1)
    }
  }
  walk(null, 0)
  return out
}

/** Unique name among siblings: "chr1", "chr1 (2)", … */
export function uniqueName(layers: Layer[], base: string): string {
  const names = new Set(layers.map((l) => l.name))
  if (!names.has(base)) return base
  for (let i = 2; ; i++) {
    const cand = `${base} (${i})`
    if (!names.has(cand)) return cand
  }
}
