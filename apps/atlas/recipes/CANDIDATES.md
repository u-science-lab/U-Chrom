# Candidate datasets for the atlas (review draft, 2026-11-03)

A list of public chromatin 3-D datasets that the atlas and the dataset registry do not hold yet, for the
collaborators to decide which are worth adding.  **Nothing here is registered or built**: no entry is in
`_sources.py`, `datasets.json` or the recipes README.  An accepted dataset follows the rules of `CLAUDE.md`
(*Data*): a registered source, a recipe, an entry in `apps/atlas/recipes/README.md` with size, citation,
accession, licence and users, and a check on the real data against the authors' numbers.

## How the list was made, and how far it can be trusted

- Searched on 2026-11-03: Europe PMC (papers and preprints), NCBI GEO, Zenodo, IDR and web search, for 2024-2026
  and for older classics.  Eligible: chromatin tracing / DNA FISH coordinates, single-cell Hi-C family
  (including with RNA, ATAC or methylation of the same cell), spatial Hi-C with positions, published per-cell
  3-D structures.  Not eligible: bulk Hi-C only, RNA-only or spatial-transcriptomics-only data (for example GEO
  GSE317379), ChIP / ATAC only.
- **Checked by hand on 2026-11-03**: every GEO accession in the table resolves, and its title, release date and
  number of listed samples are as given.  Whether a candidate is already in the repository was checked by
  accession in `datasets.json`, `_sources.py` and the recipes README.
- **Taken from the literature search and not checked**: numbers of nuclei or cells, file formats, whether the
  contacts are public per cell or only per group, journal and year of a preprint, licences.  They are marked
  "reported" below.  The 4DN portal could not be reached from the search environment, so no 4DN accession was
  checked.
- A GEO SuperSeries lists no samples of its own (marked "super"): the data sit in its sub-series, and the
  processed contacts may be at another archive (NeMO).

## Already in the repository (not candidates)

| Study | Where |
|---|---|
| Lee et al. 2019, snm3C-seq of human prefrontal cortex, GSE130711 | `lee2019_snm3c` in `_sources.py`; `build_schic_pairs.py` |
| Tian et al. 2023, snm3C-seq of the adult human brain, GSE215353 / NeMO | `tian2023_snm3c` in `_sources.py` |
| Yuan et al. 2026, snm3C-seq of the human retina, GSE277361 | `yuan2026_retina` in `_sources.py` |
| Wu et al. 2025, scMicro-C, GSE281150 | `wu2025_scmicroc`: the 12 deepest GM12878 cells only (the superseries has 829 samples) |

The snm3C-seq contacts, then, can already be read: the open question for them is publication in the atlas, not
a reader.  Only the contacts are fetched; DNA methylation is not stored in a ChromData (cell-level summaries
can go to `cells`, a full matrix can be linked as AnnData).

## Candidates

Priority is a first guess for discussion.  "Reported" = from the literature search, not checked.

| # | Study | Data | Accession (checked) | Scale | What it adds | Priority |
|---|---|---|---|---|---|---|
| 1 | Zhou et al. 2026, *Science*: human body atlas of 3-D genome and DNA methylation | snm3C-seq, 16 human tissues | GSE326618: "Human body single-cell atlas of three-dimensional genome organization and DNA methylation", public 2026-07-31, 256 samples | reported ~86,700 nuclei | first multi-tissue human single-cell 3-D genome set | high |
| 2 | Liu et al. 2023, *Nature*: DNA methylome and 3-D chromatin of the mouse brain | snm3C-seq, mouse, 117 brain regions | GSE213262: "DNA Methylome and 3D Chromatin Landscape of Cell Types Across the Mouse Brain", public 2023-04-13, super | reported hundreds of thousands of nuclei | largest mouse snm3C reference; cross-check against the Liu 2025 brain imaging already in the atlas | high |
| 3 | Chen et al. 2026, *Nature* (reported): CHARM, four-omics of single cells | Hi-C, chromatin accessibility, histone marks and RNA of the same cell; mouse ESC and cortex | GSE303006: "Gene regulatory landscape dissected by single-cell four-omics sequencing", public 2026-01-18, 16 samples | not checked | a new modality; the GEO text says 3-D structures were made with hickit, so a ChromData needs little reconstruction | high |
| 4 | Zhang et al. 2026, *Science* (reported): Alzheimer's disease brain, 3-D genome and transcriptome | snm3C-seq, human VC / TC / PFC, 11 cases and 9 controls (reported) | GSE308132: "Single-cell multi-omic and multi-region atlas of the Human Alzheimer's Disease Brain", public 2025-12-04, super | not checked | disease cohort; the atlas has no neurodegeneration | medium |
| 5 | Aging male mouse brain atlas (reported: *Cell* 2026) | snm3C, several brain regions and ages | GSE313770: "Single-cell multi-omic and multi-region atlas of the Aging Male Mouse Brain", public 2025-12-18, 108 samples | not checked | an ageing axis, next to Tan 2023 (cerebellum) | medium |
| 6 | Developing human basal ganglia (reported: bioRxiv 2026) | snm3C plus imaging of chromatin and RNA, spatial | GSE322468: "A Single-Cell and Spatial 3D-Epigenomic Atlas of Developing Human Basal Ganglia ...", public 2026-03-02, 9 samples | not checked | human development with spatial data | medium |
| 7 | Human subcutaneous adipose tissue (reported: *Nat Genet* 2025) | snm3C-seq | GSE297267: "Single-cell DNA methylome and 3D genome atlas of human subcutaneous adipose tissue", public 2025-07-14, super (16 sub-series samples) | not checked | a metabolic tissue; none in the atlas | medium |
| 8 | AML patient cells, HiRES (reported) | Hi-C with RNA of the same cells, human CD34+ leukaemia cells, `.pairs` | GSE302267: "Single-cell transcriptomic and 3D genome atlas of leukemia cells from patients with acute myeloid ...", public 2025-07-14, 381 samples | reported ~381 cells | cancer; same method as Liu 2023 HiRES already in the atlas | medium |
| 9 | Parasar et al. 2026, bioRxiv (reported): Plate-C / Easy Dip-C, chemical screen | Dip-C-family, human NGN2 neurons and neonatal mouse brain | Zenodo 10.5281/zenodo.15021657 (reported; the record was not rechecked) | reported 6,081 cells | drug perturbation; the Zenodo copy may be per cluster, not per cell | medium |
| 10 | Fiche / Messina and colleagues 2024, bioRxiv (reported): single-allele folding motifs in tissues | chromatin tracing of the mouse Pdx1 locus in pancreas and other tissues | not found (the preprint's data statement was not located) | reported 82,754 traces | tissue tracing in pancreas; none in the atlas | medium once the data location is known |
| 11 | Patel et al. 2026, bioRxiv (reported): *Drosophila* brain ORCA | tracing in brain sections | not found (the preprint points to a probe-library repository only) | reported 79,732 cells | tissue tracing in *Drosophila* brain | medium once the data location is known |
| 12 | Wang et al. 2016, *Science*: chromosome 21 folding in IMR90 | chromatin tracing | 4DN (not checked) | reported a handful of 4DN sets | the earliest tracing data; may overlap with the Bintu 2018 and Su 2020 chr21 entries already in the atlas | low: check overlap first |

## Gaps in the current atlas (modalities, tissues)

- Multi-tissue and disease single-cell 3-D genome: human body, Alzheimer's disease, ageing mouse brain,
  adipose, AML.  The snm3C-seq contacts of three studies are registered but the atlas page lists none yet.
- Four-omics in one cell (CHARM).
- Tracing in tissue: pancreas, *Drosophila* brain; the 4DN portal lists far more FOF-CT sets than the atlas holds
  (the search could not enumerate them).

## Left out

- GEO GSE320293 (adult basal ganglia snm3C, reported 261,331 nuclei): not found in GEO, possibly not released.
- Jones 2026 (human embryonic cortical glia): controlled access and pooled by cell type.
- Itoh 2026 bioRxiv: its "chromatin traces" are reconstructed from ATAC, not imaging.
- Lu 2026 *Cell Discov* (dscNanoATAC / CUT): no 3-D genome.
- Jay 2026 *Immunity* and Le 2026 *Cell Genomics*: the published versions of Jay 2025 and Le 2024, which the atlas holds.
- sci-Hi-C (GSE84920, 6 samples) and HiChew (GSE284602, 8 samples): proofs of concept.
- iFISH (idr0123), Cheng 2021 X chromosome, *C. elegans* domain tracing: little beyond what the atlas has.
- Several 2025-2026 bulk Hi-C papers (rice, schizophrenia, others): not single-cell, not looked at.

## Questions for the reviewers of this PR

1. Which of 1-9 do we want, and in what order?  A suggestion: 3 (CHARM) first, as it needs no reconstruction
   and adds a modality; then 1 and 2 as the large snm3C references.
2. For the snm3C sets: should the atlas publish the three already registered (Lee 2019, Tian 2023, Yuan 2026)
   before adding more?
3. Scale: Tian 2023 is 145,070 nuclei (556 GB of contacts) and Zhou 2026 about 86,700.  Do we embed all cells in
   a store, or a subset by cell type (and reconstruct structures for a subset only)?
4. Licences were not found for most of these.  Who checks them before a store is published?
5. Does anyone have access to the 4DN portal from a machine that can reach it, to complete the tracing list?
