/** Detect a server started before the page was rebuilt (it may lack new routes). */

/** Bundle file name (`index-<hash>.js`) of a script URL, or null (e.g. the Vite dev server). */
export function bundleOf(src: string | null | undefined): string | null {
  const m = src?.match(/assets\/(index-[^/?#]+\.js)/)
  return m ? m[1] : null
}

/** The page's own bundle, from its module script tag. */
export function pageBundle(doc: Document = document): string | null {
  for (const s of Array.from(doc.querySelectorAll('script[src]'))) {
    const b = bundleOf(s.getAttribute('src'))
    if (b) return b
  }
  return null
}

/** True only when both sides are known and differ. */
export function isStaleServer(page: string | null, server: string | null | undefined): boolean {
  return !!page && !!server && page !== server
}

export const STALE_SERVER_MESSAGE =
  'The server was started before this page was rebuilt and may lack newer features — ' +
  'restart `python -m uchrom.browser --web …` and reload.'
