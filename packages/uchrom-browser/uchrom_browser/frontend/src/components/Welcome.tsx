import { useEffect, useMemo, useState } from 'react'
import { fetchAtlas, fetchHealth } from '../api'
import { baseName, loadRecent } from '../datasets'
import { useStore } from '../store'
import type { AtlasDataset, AtlasResponse, AtlasStudy } from '../types'
import { useOpenDataset } from '../useOpenDataset'
import { datasetFacts, featuredDatasets, modalityLabels, studyIndex, thumbnailUrl } from '../welcome'
import { OpenDialog } from './OpenDialog'

/**
 * The start page, in place of the views while no dataset is open: example datasets of the atlas (a click opens one),
 * the whole atlas and — on a local server — the server's folders in the Open dialog, and the datasets opened before.
 */
export function Welcome() {
  const setError = useStore((s) => s.setError)
  const open = useOpenDataset()
  const [atlas, setAtlas] = useState<AtlasResponse | null>(null)
  const [atlasError, setAtlasError] = useState<string | null>(null)
  const [hosted, setHosted] = useState<boolean | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [dialog, setDialog] = useState<'atlas' | 'files' | null>(null)
  const [recent] = useState(loadRecent)
  useEffect(() => {
    fetchAtlas()
      .then(setAtlas)
      .catch((e: Error) => setAtlasError(e.message))
    fetchHealth()
      .then((h) => setHosted(!!h.hosted))
      .catch(() => setHosted(false))
  }, [])

  const catalog = atlas?.catalog ?? null
  const examples = useMemo(() => featuredDatasets(catalog), [catalog])
  const studies = useMemo(() => studyIndex(catalog?.studies), [catalog])
  const names = useMemo(() => new Map((catalog?.datasets ?? []).map((d) => [d.url, d.name ?? d.title])), [catalog])
  const nAtlas = catalog?.datasets.length ?? 0

  const openPath = async (path: string) => {
    setBusy(path)
    try {
      await open(path)
    } catch (e) {
      setError(`Cannot open ${baseName(path)}: ${(e as Error).message}`)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="workspace welcome">
      <div className="welcome-inner">
        <header className="welcome-head">
          <img src={`${import.meta.env.BASE_URL}favicon.svg`} alt="" width={44} height={44} />
          <div>
            <h1>U-Chrom Browser</h1>
            <p className="muted">
              Chromatin tracing, single-cell and spatial Hi-C in linked views: 3-D structures, contact maps, tissue
              sections and embeddings, cell by cell.
            </p>
          </div>
        </header>

        {atlas?.root !== null && (
          <section className="welcome-section">
            <div className="welcome-section-head">
              <h2>Start with an example</h2>
              <span className="muted small">Read from the atlas over the network: only what a view shows is fetched.</span>
            </div>
            {examples.length > 0 && (
              <div className="welcome-grid">
                {examples.map((d) => (
                  <ExampleCard key={d.id} d={d} study={studies.get(d.study ?? '')} figures={atlas?.figures} busy={busy} onOpen={() => void openPath(d.url)} />
                ))}
              </div>
            )}
            {atlasError && <p className="error small">The atlas could not be read: {atlasError}</p>}
            {!atlas && !atlasError && <p className="muted small">Loading the atlas…</p>}
          </section>
        )}

        <div className="welcome-actions">
          {nAtlas > 0 && (
            <button className={hosted ? 'primary' : ''} onClick={() => setDialog('atlas')}>
              Browse all {nAtlas} datasets of the atlas…
            </button>
          )}
          {hosted === false && (
            <button className="primary" onClick={() => setDialog('files')} title="A .chromdata.zarr, .cdz or .csv on the server's disk">
              Open a dataset on this server…
            </button>
          )}
        </div>

        {recent.length > 0 && (
          <section className="welcome-section">
            <div className="welcome-section-head">
              <h2>Opened before</h2>
            </div>
            <div className="welcome-recent">
              {recent.map((r) => (
                <button key={r} onClick={() => void openPath(r)} disabled={!!busy} title={r}>
                  {busy === r ? 'Opening…' : (names.get(r) ?? baseName(r).replace(/\.chromdata\.zarr$/, ''))}
                </button>
              ))}
            </div>
          </section>
        )}

        <footer className="welcome-links muted small">
          <a href="https://u-chrom-docs.u-science.org/viz/browser" target="_blank" rel="noreferrer">
            Guide to the browser
          </a>
          <a href="https://uchrom-atlas.u-science.org" target="_blank" rel="noreferrer">
            The atlas
          </a>
          <a href="https://github.com/u-science-lab/U-Chrom" target="_blank" rel="noreferrer">
            U-Chrom on GitHub
          </a>
        </footer>
      </div>
      {dialog && <OpenDialog panel={dialog} onClose={() => setDialog(null)} />}
    </div>
  )
}

/** One example: its thumbnail, the assay, name, size and data; a click opens it. */
function ExampleCard({ d, study, figures, busy, onOpen }: { d: AtlasDataset; study?: AtlasStudy; figures?: string | null; busy: string | null; onOpen(): void }) {
  const [thumb, setThumb] = useState(() => thumbnailUrl(figures, d))
  return (
    <button className="welcome-card" onClick={onOpen} disabled={!!busy} title={d.description ?? d.title}>
      {thumb && (
        <span className="welcome-thumb">
          <img src={thumb} alt="" loading="lazy" onError={() => setThumb(null)} />
        </span>
      )}
      <span className="welcome-card-body">
        {study?.kind && <span className="welcome-kind">{study.kind}</span>}
        <span className="welcome-name">{d.name ?? d.title}</span>
        <span className="muted small">{[datasetFacts(d, study), d.organism?.replace(/ /g, '\u00a0')].filter(Boolean).join(' · ')}</span>
        <span className="atlas-chips">
          {modalityLabels(d).map((m) => (
            <span key={m} className="atlas-chip">
              {m}
            </span>
          ))}
        </span>
        {d.paper && <span className="muted small welcome-paper">{d.paper}</span>}
      </span>
      {busy === d.url && <span className="welcome-busy">Opening…</span>}
    </button>
  )
}
