# PGS / IGM (Alber lab) — reference algorithm specification

Population-based genome structure modelling of bulk Hi-C: a population of `S` diploid
genome structures is fitted jointly to a contact-probability matrix by alternating an
**A-step** (assignment: decide which structures carry which contact restraint) and an
**M-step** (modelling: optimise each structure independently under its restraints).
This document specifies what the **original code** does, line by line, as the correctness
target for a native U-Chrom protocol (`benchmarks/bulk/design.md`). It follows the style of
`benchmarks/fig3/nucdyn_spec.md`: every item cites `file:function`; quirks are recorded as
found; paper statements that the code does not show are marked **[paper]**, anything
inferred but not verified is marked **[unverified]**, and conflicts are listed in §12.

There are two code generations with the same A/M idea but different kernels and constants:

* **PGS** (2016–2018): Python 2 + IMP. Tjong et al. 2016 PNAS 113:E1663
  (doi:10.1073/pnas.1512577113); Hua et al. 2018 Nat Protoc 13:915 (doi:10.1038/nprot.2018.008).
* **IGM** (2019–2022): Python 3 + a modified LAMMPS. Boninsegna et al. 2022 Nat Methods
  19:938 (doi:10.1038/s41592-022-01527-x). IGM is the current code; U-Chrom's faithful mode
  targets IGM (§13 says why), with PGS as the documented predecessor.

## 0. Sources (all read in full for the parts cited; cloned 2026-09-29)

| repository | commit (HEAD) | date | licence | role |
|---|---|---|---|---|
| github.com/alberlab/pgs | `98cee2ef0da69d8ac237fdda130016ac0e60a2de` | 2018-04-09 | GPL-3.0-or-later (file headers; `pgs.py`: `__license__ = "GPL"`; no LICENSE file in the repo) | PGS pipeline (`pgs.py`, `pgsflows/`), modelling kernel wrapper on IMP (`alab/modeling.py`), matrix preprocessing (`alab/matrix.py`) |
| github.com/alberlab/igm | `edbb33135260443b8b41eb09d7ca4c37b19e330d` | 2022-11-10 | GPL-3.0 (`LICENSE`) | IGM pipeline (`bin/igm-run`), steps (`igm/steps/*`), restraints (`igm/restraints/*`), LAMMPS interface (`igm/model/kernel/*`) |
| github.com/alberlab/alabtools | `2daab4710845674a224f524e0b50e893bf030e35` | 2026-02-04 | GPL-3.0 (`LICENSE`) | `.hcs` / `.hss` formats, genome index, diploid index (`utils.py:make_diploid`), `HssFile` (`analysis.py`), Hi-C scaling helpers (`api.py`), C++ summary matrix (`cmtools/cmtools.cpp`) |
| github.com/alberlab/lammpgen | `8a1a4cbb4d0bffda516c7f51cd3cf2f706ec3cb9` (shallow clone, last 50 commits) | 2025-08-07 | GPL-2.0 (`LICENSE`, as LAMMPS) | IGM's MD kernel: LAMMPS + package `src/USER-GENOME` (bond styles, envelope fixes) |
| github.com/salilab/imp (branch `develop`, individual files fetched) | — | 2026 | LGPL/GPL (IMP) | PGS's MD / CG kernel. **PGS was written for IMP 2.5 (`alab/modeling.py` header "IMP 2.5 is required"); the files read here are from `develop`; the parts used (velocity Verlet, velocity rescaling, harmonic bounds, CG) are long-stable but not verified against 2.5 [unverified]** |

md5 of the key files: `pgs/alab/modeling.py` 9fa984ce…, `pgs/pgsflows/script/Astep.py`
0ddae1ff…, `pgs/pgsflows/script/Mstep.py` 484e035f…, `igm/igm/steps/ActivationDistanceStep.py`
b25c10a8…, `igm/igm/model/kernel/lammps.py` a4b436f3…, `igm/bin/igm-run` f2f21290….

Nothing was run: PGS needs Python 2.7 + IMP, IGM needs a compiled alabtools + the lammpgen
binary; both are HPC-only codes (§11). The only data inspected locally is IGM's demo input
`igm/demo/WTC11_HiC_2Mb.hcs` (read with h5py; §1.3).

---

## 1. Input: Hi-C → contact-probability matrix

### 1.1 PGS — `pgsflows/script/buildTADMap.py:main` (+ `alab/matrix.py:contactmatrix`)

Input: a raw genome-wide matrix (`.hic`, `.cool`, or text) at a fixed bin size (test configs:
100 kb, hg19, chr1–22 + X: `alab/utils.py:genome`, `usechr=['#','X']`) and a **domain file**
(BED: chrom, start, end, flag; flags `domain`, `gap`, `CEN`). Steps, in order:

1. `removeDiagonal()` — main diagonal set to 0.
2. `removePoorRegions(cutoff=1, usepvalue=0.1)` — candidate bins = rowsum below the 1st
   percentile of non-zero rowsums; for each, the row is binomially split into two halves
   (`alab/utils.py:binomialSplit`) and a bin is removed (row/column zeroed, flag `Removed`)
   when the Pearson p-value of the two halves is > 0.1.
3. `identifyInterOutliersCutoff(N=100)` — on the raw inter-chromosomal counts: histogram of
   counts vs 100 bootstrap resamples; `cutoff` = first count (scanning from the top) where two
   consecutive counts have bootstrap std < half their frequency.
4. `smoothInterContactByCutoff(cutoff, w=3, s=3, p=3)` — every inter count > cutoff is replaced
   by a power-law weighted average of its (2w+1)² neighbourhood (`alab/utils.py:powerLawSmooth`).
5. `krnorm()` — Knight–Ruiz balancing (`alab/norm.py:bnewt`), matrix multiplied by `x xᵀ`
   with `x = bnewt(...) · 100`.
6. `smoothGenomeWideHighValue(w=5, s=1, p=1, z=5)` — per chromosome-pair block, spikes > z SD
   smoothed (`alab/utils.py:smoothSpikesInBlock`); if the diagonal sums < 1 it is first
   filled with the sum of the two first off-diagonals.
7. `assignDomain(domain, pattern="")` — all domains kept.
8. `iterativeFmaxScaling(domainAverageContacts=25)` (the test script `assignDomain_makeTADMatrix.py`
   uses 23.4; the default argument is 23.2): start with `fmax = getfmax()` = median of all
   intra-domain bin-pair values (offdiag ≥ 1, domains 1…2000 bins); loop:
   `P = min(F / fmax, 1)` (`fmaxScaling`), domain-level matrix `D = makeDomainLevelMatrix()`
   (see below), `domainMean = mean rowsum(D)`, `fmax ← fmax · domainMean / 25`, until
   `|domainMean − 25| / 25 ≤ 0.01`.
   * `makeDomainLevelMatrix(method='topmean', top=10, removeOutlier=True)`: for every domain pair
     (I, J) the bin-level probabilities of the block (removed bins = NaN, dropped) are trimmed
     to the 1.5·IQR box-plot fences and **D[I,J] = mean of the top 10 %** of the remaining
     values (`_generateTopMeanSummaryMatrix`). Diagonal blocks included.
   * So the final input is a **TAD-level probability matrix** whose average row sum (expected
     number of contacts of a domain, haploid indexing) is 25, entries clipped at 1.

Alternatives: `prob_matrix_file_txt` (a user probability matrix, converted by
`hdf5_converter.py`) or `prob_matrix_file_hdf5` (used as is) — `pgs.py:workflow`.

The matrix is **haploid-indexed** (one row per domain); diploidy is introduced only in the
model (§2.1). Tjong 2016 used GM12878 (female) with chrX modelled as two copies; the shipped
Rao 2014 domain file has 2,320 domains (2,273 `domain`, 24 `gap`, 23 `CEN`; mean 1.31 Mb),
i.e. 4,640 beads (`Astep.py` comment "10000 * 4640 * 3"). **[paper]** Tjong 2016 main text
reports 1,332 domains for the diploid genome at ~3.5 Mb for its TCC data set.

### 1.2 IGM — no preprocessing in the code

`igm/README.md` ("Generate '.hcs' file from '.mcool' raw data"): IGM reads a ready
probability matrix (`.hcs`, alabtools `Contactmatrix`, stored upper-triangular symmetric
sparse `matrix/{data,indices,indptr,diagonal}`); "Our own preprocessing pipeline is peculiar
to the lab and detailed in the Supporting Information … any preprocessing … that generate[s] a
balanced/filtered/appropriate matrix of contact probabilities … can be used".
`IGM_documentation.pdf` §Hi-C: "a (haploid) contact probability matrix … The A(i,j) entry
indicates the probability that a contact is formed between i and j loci". Fixed-size bins
(`genome.segmentation` = integer bin size, or a BED segmentation) — `igm/_preprocess.py:PrepareGenomeIndex`.

alabtools still ships PGS-style helpers (`api.py:Contactmatrix.fmaxScaling` = divide by fmax and
clip at 1; `iterativeScaling(domain, averageContact=24, theta=0.001, tol=0.01)` = bisection on
`fmax` so that the mean non-zero rowsum of the top-mean summary matrix, after zeroing entries
< θ, equals 24; summary by `cmtools.cpp:TopmeanSummaryMatrix`, top 10 % below the upper fence).
Whether the 2022 populations used these is **[unverified]** (SI not accessible from here).

### 1.3 What an IGM input looks like (verified on `igm/demo/WTC11_HiC_2Mb.hcs`)

1,558 bins (hg38, 2 Mb, chr1–22, X, Y), haploid index (`index/copy` all 0), diagonal = 1,
first off-diagonal median 1.0, max 1.0, intra median 0.0245 (99th pct 1.0), inter median
0.0099 (max 0.17). Pairs ≥ σ: 1,702 at σ = 1; 2,824 at 0.2; 6,307 at 0.1; 14,994 at 0.05;
44,944 at 0.02; **614,140 at 0.01** (the inter-chromosomal block crosses the last threshold).
Mean restrained probability mass per haploid bin at σ = 0.01: 5.2 intra + 8.7 inter. So
entries are per-haploid-locus-pair contact probabilities (0…1), with sequence neighbours at 1.

---

## 2. Particle model

### 2.1 Beads and diploid layout

* **PGS** `alab/modeling.py:tadmodel.__init__`: one bead per domain, **two copies**:
  bead `i` (copy A) and `i + nbead` (copy B); `beadRadius = r + r` (list concatenation). No
  sex-chromosome special case (chrX always two copies; chrY not modelled).
* **IGM** `igm/_preprocess.py:PrepareGenomeIndex`: `ploidy` = `diploid` (`alabtools.utils.make_diploid`:
  the whole haploid index concatenated twice, copy 0 then copy 1), `haploid`, `male`
  (`{'#': 2, 'X': 1, 'Y': 1}` → `make_multiploid`), or a dict. The mapping haploid locus → its
  copies is `Index.copy_index` (`alabtools/utils.py:_compute_copy_index`: key = first bead id of
  a locus, value = all bead ids with the same (chrom, start, end)).

### 2.2 Radii from volume occupancy

* **PGS**: `rho = occupancy · R_nuc³ / (2 · Σ_chrom length)`, `r_i = (rho · (end_i − start_i))^{1/3}`
  (nm). Defaults `R_nuc = 5000 nm`, `occupancy = 0.2` (`Mstep.py:main`, overridable by
  `nucleus_radius`, `chr_occupancy`). Hence Σ over both copies of (4/3)π r³ = occupancy × nuclear volume.
* **IGM** `igm/_preprocess.py:Preprocess`: `rho = occupancy · V_nuc / Σ_index (end − start)`
  (index already diploid), `r_i = (rho · size_i / (4π/3))^{1/3}`; `V_nuc` = sphere 4/3πR³ or
  ellipsoid 4/3πabc (`exp_map`: sphere of R = 5200). Schema defaults occupancy 0.2, R = 5000
  (`core/defaults/config_schema.json`); demo 0.4, R = 5500; Boninsegna 2022 **[paper]** HFF:
  200 kb, 29,838 beads, r₀ = 118 nm, 40 % occupancy, prolate ellipsoid (7,840, 6,470, 2,450) nm.
  Bins are fixed size except the last bin of each chromosome (shorter → smaller radius).

### 2.3 Contact definition (both codes)

Two beads are "in contact" when the **centre distance ≤ 2 (r_i + r_j)**:
PGS: surface distance ≤ `contactRange·(r_i + r_j)` with `contactRange = 1`
(`tadmodel(contactRange=1)`, `Astep.py:calcActdist` `existingPortion(sortdist, r[i]+r[j])`);
IGM: `contact_range = 2.0` on centre distance (`ActivationDistanceStep.py:get_actdist`, `rcutsq`).

---

## 3. Restraints — functional forms and constants

Notation: `d` = centre distance, `s = d − r_i − r_j` = surface distance.

### 3.1 PGS (IMP; `alab/modeling.py`)

IMP `HarmonicUpperBound(mean, k)`: `U = ½ k (x − mean)²` for `x > mean`, else 0
(`imp/modules/core/include/Harmonic.h`, `HarmonicUpperBound.h`).
`SphereDistancePairScore(f)`: `x = s` (surface distance).

| restraint | code | form |
|---|---|---|
| excluded volume | `set_excludedVolume(ksping=1, slack=10)` → `IMP.core.ExcludedVolumeRestraint(chain, 1, 10)` | `U = ½·1·(r_i + r_j − d)²` for overlapping pairs (`SoftSpherePairScore`; IMP docs "k·D²/2 … D the depth of overlap"); **all pairs, including sequence neighbours and homologs**; slack 10 is a neighbour-list parameter |
| nuclear envelope | `set_nucleusEnvelope(kspring=1)` → `DistanceToSingletonScore(HarmonicUpperBound(R_nuc, 1), centre)` | `U = ½ (d_c − R_nuc)²` for bead **centre** distance to origin `d_c > R_nuc` (radius not subtracted) |
| consecutive beads | `set_consecutiveBeads(lowprob=0.6)` → `_get_consecutiveBeadRestraints(kspring=10)` | for `(i, i+1)` on the same chromosome, both copies: `p = max(P[i,i+1], 0.6)`, surface upper bound `s₀ = (r_i + r_j)(1 + (x_c³ − 1)/p)^{1/3} − r_i − r_j` with `x_c = contactRange + 1 = 2` (`consecutiveDistanceByProbability`), `k = 10`. **Plus** `(i−1, i+1)` with `p = max(P[i−1,i+1], 0.6)` whenever `flag[i] != "domain"` (the second guard `idx[i-1] != "gap"` compares a whole record to a string and is always true — quirk), i.e. a `gap`/`CEN` bead is bridged. The form comes from requiring the volume-averaged contact probability of a bead uniformly placed in a shell to equal p (Tjong 2016 SI [paper]) |
| Hi-C contact (single) | `_get_beadDistanceRestraint(i, j, contactRange·(r_i + r_j), k=1)` | `U = ½ (s − (r_i + r_j))²` for `s > r_i + r_j` (i.e. d > 2(r_i + r_j)) |
| Hi-C contact (ambiguous) | `_get_minPairRestraints(bpair, dist, minnum)` → `IMP.container.MinimumPairRestraint(score, pairs, minnum)` | sum of the **`minnum` lowest** single-pair scores among the listed copy pairs (hard minimum, re-selected at every evaluation) |
| chromosome territory (initial phase only) | `mdstep_withChromosomeTerritory(t, step)` | every 10 MD steps, per chromosome copy: `U = ½·0.2·(d_com − R_chr)²` for beads farther than `R_chr` from that copy's current centre of mass (recomputed each 10 steps), `R_chr = ((V_nuc · L_c/L_tot / 2)·3/(4π))^{1/3}` |

Masses 1 (`IMP.atom.Mass.setup_particle(p, 1)`). Units: IMP interprets lengths as Å, energies
kcal/mol, time fs; PGS feeds nm-valued coordinates, so temperatures are nominal (hence 8×10⁶ "K").

### 3.2 IGM (LAMMPS `units lj`; `igm/model/kernel/lammps.py:create_lammps_script`)

`bond_style hybrid harmonic_upper_bound harmonic_lower_bound`; lammpgen
`src/USER-GENOME/bond_harmonic_upper_bound.cpp:compute`: for `d > r₀`: `U = k (d − r₀)²`,
`F = −2k (d − r₀)` (LAMMPS convention, **no ½**; the Python classes `igm/model/forces.py` and
`kernel/lammps_model.py` document "½k" / "−k(x−x₀)" — only the C++ is executed).
`special_bonds lj/coul 1.0 1.0 1.0`: bonded pairs keep the pair (excluded-volume) interaction.

| restraint | code | form, constants |
|---|---|---|
| excluded volume | `pair_style soft 2·r_max`; `PairIJ Coeffs`: per bead-type pair `A = evfactor·((r_i + r_j)/π)²`, cutoff `r_c = r_i + r_j` (`create_lammps_data`) | LAMMPS `pair soft`: `U = A (1 + cos(π d / r_c))` for `d < r_c`; force magnitude `A π/r_c sin(π d/r_c)` (max `evfactor·(r_i + r_j)/π` at d = r_c/2). All bead pairs incl. neighbours and homologs. `fix adapt … pair soft a * * v_evprefactor scale yes` multiplies A by the per-stage `evfactors` (§6.2). `evfactor` default 1.0 (schema; `config_default.json` 0.05) |
| nuclear envelope | `restraints/envelope.py:Envelope` → `forces.py:EllipticEnvelope` → `fix … ellipsoidalenvelope a b c k` (`USER-GENOME/fix_ellipsoidal_envelope.cpp:post_force`) | `k² = Σ x_α² / (a_α − r_i)²`; if `k² > 1`: `t = (1 − 1/√k²)·|x|`, `U = ½ k t²`, force `k t` along `−(x/(a−r)², y/(b−r)², z/(c−r)²)` normalised. Bead **surface** kept inside (semi-axes reduced by r_i). Sphere = a = b = c. `nucleus_kspring` default 1; semi-axes scaled by the per-stage `envelope_factors` |
| polymer (consecutive) | `restraints/polymer.py:Polymer._apply` | `(i, i+1)` same chrom and same copy: upper bound `d₀ = contact_range·(r_i + r_{i+1})` = 2(r_i + r_{i+1}), `k = polymer_kspring` (1.0), style `simple` (default). With `polymer_bonds_style = hic` (`_preprocess.py`): `f = P[i,i+1]` (clamped to 0.5 if < 0.5 or > 1), `d₀ = ((d₁³ + (f − 1) d₀'³)/f)^{1/3}` with `d₀' = r_i + r_j`, `d₁ = 2 d₀'` (same shell-volume logic as PGS) |
| Hi-C | `restraints/intra_hic.py:intraHiC._apply`, `inter_hic.py:interHiC._apply` | for every line (i, j, d_act) of the activation-distance file with **this structure's current** `d_ij ≤ d_act` (and same / different chromosome respectively): upper bound `d₀ = contact_range·(r_i + r_j)` = 2(r_i + r_j), `k = contact_kspring` (schema 1.0; code fallback 0.05 in `ModelingStep.task`). **Every copy pair is an independent single restraint — IGM has no ambiguous / minimum restraint**; ambiguity is resolved per structure by the distance test (§4.2) |
| lamina DamID | `restraints/damid.py:Damid._apply_envelope` | beads listed in the DamID activation file whose `x²/(a'−r)² + … ≥ d_act²` (`a' = (1 − contact_range)·a`, contact_range 0.05) get an **inverted** ellipsoidal envelope (`EllipticEnvelope(k = −k)`, `fix ellipsoidalenvelope` with negative k): harmonic penalty while the bead is *inside* the shell at 0.95 R → pushes it to the lamina |
| FISH | `restraints/fish.py:Fish._apply` | per structure a target distance from `fish_assignment` (radial to a dummy centre particle, or pairwise), with tolerance `tol`: `HarmonicLowerBound(d ≥ max(0, target − tol))` + `HarmonicUpperBound(d ≤ target + tol)` on the min (`r`, `p`) or max (`R`, `P`) copy, and a one-sided bound on the other copy (radial: 3 restraints, pairs: up to 5); `tol_list` default [50, 25, 0] nm |
| SPRITE | `restraints/sprite.py:Sprite._apply` | for each cluster assigned to this structure: a massless dynamic centroid particle at the beads' mean, no excluded volume; `HarmonicUpperBound(bead–centroid ≤ R_c − r_b)`, `R_c = (Σ r³ / volume_fraction)^{1/3}`; assignment by a Gibbs weight (`steps/SpriteAssignmentStep.py`, `radius_kt`) |
| nucleolus / volume map | `restraints/nucleolus.py`, `genenvelope.py`, `fix volumetricrestraint` | voxel-map envelopes (not needed here) |

---

## 4. A-step (assignment) — the activation-distance rule

Both codes compute, for every haploid pair (i, j) with input probability `f_ij ≥ σ`
(the current threshold), an **activation distance** `d_act(i,j)` from the current population,
then each structure independently decides whether it receives the restraint.

### 4.1 PGS — `pgsflows/script/Astep.py:calcActdist`

Inputs: probability matrix `P` (TAD level, haploid), all `S` structures of the last M-step
(`copy<k>.hms`, group = last θ label), the previous A-step file (column 4 → `p_last`).
For every pair `i < j` with `P[i,j] ≥ θ` (`targetfreq` = digits of the θ label, so "0.05b" → 0.05):

1. surface distances over the population (`Astep.py` lines 67–75), `r = r_i + r_j`:
   * intra (same chromosome): `d₁ = |x_i − x_j| − r` (copy A) and `d₂ = |x_{i'} − x_{j'}| − r`
     (copy B); `dists = concat(d₁, d₂)` (2S values);
   * inter: the four combinations `(i,j), (i',j'), (i,j'), (i',j)`; per structure the **two
     smallest**; `dists` = 2S values.
2. `sortdist = sort(dists)`; `p_now = fraction of dists ≤ r` (i.e. centre distance ≤ 2r).
3. `t = clean(p_now, p_last)`, `p = clean(P[i,j], t)` with
   `clean(a, b) = max(0, (a − b)/(1 − b))` if `b < 1` else `a`.
   Interpretation (Tjong 2016 SI [paper]): `t` is the contact frequency among the pairs **not**
   already restrained, `p` the fraction of the not-yet-in-contact structures that must be
   pulled in. Note `p_last` is the previous step's *cleaned* p (column 4), not the previous
   `p_now`.
4. if `p > 0`: `o = min(2S − 1, round(2 p S))`, `d_act = sortdist[o]` (a surface distance);
   output line `i j P[i,j] d_act p p_now`. Pairs with `p = 0` produce no line (no restraint).

Per-structure assignment (`alab/modeling.py:tadmodel._get_contactRestraints`, in the
**next M-step**, on that structure's own last coordinates):

* intra: `s_A, s_B` surface distances of the two copies; if `max(s_A, s_B) ≤ d_act` → two single
  restraints (both copies); elif `min ≤ d_act` → one `MinimumPairRestraint([(i,j),(i',j')], minnum=1)`;
  else none.
* inter: the four copy pairs sorted; if the 2nd smallest ≤ d_act → `MinimumPairRestraint`
  over the 4 pairs with `minnum = 2`; elif the smallest ≤ d_act → `minnum = 1`; else none.

The first θ (= 1 in every config) has **no A-step**: `Mstep.py` with no activation file uses
`_get_fmaxRestraints`: every pair with `P > 0.999` is restrained in **every** structure —
intra (`j − i > 1` only) as two single restraints (both copies), inter as `MinimumPairRestraint`
over the 4 copy pairs with `minnum = 2`.

### 4.2 IGM — `igm/steps/ActivationDistanceStep.py:get_actdist` (LB version, 2021-04-16)

`setup`: candidate pairs are the upper-triangle non-zeros of the `.hcs` matrix with
`f_ij ≥ intra_sigma` (same chromosome) or `≥ inter_sigma` (different); `p_last[i,j]` = `prob`
column of the previous activation file (sparse, 0 if absent). Batches of 1,000 pairs, one
task per batch. For each pair (`i ≠ j`; `ii = copy_index[i]`, `jj = copy_index[j]`, radii of
the first copies, `rc = 2 (r_i + r_j)`):

1. squared centre distances over the population (`hss.get_bead_crd` = all S structures):
   * **intra**: the `len(ii)` "same-copy" combinations `(ii[k], jj[k])` (diploid: (i,j), (i',j'));
     `n_possible = min(len(ii), len(jj))` (2);
   * **inter**: all `len(ii)·len(jj)` combinations (diploid 4); `n_possible = len(ii)·len(jj)` (4).
2. `d_sq.sort(axis=0)` (per structure, over combinations — a no-op for the pooled count below
   since all rows are kept), `p_now = #(d² ≤ rc²) / (n_possible · S)`;
   `sortdist = sort(all n_possible·S values)`.
3. `t = clean(p_now, p_last)`, `p = clean(f_ij, t)` (same `clean` as PGS).
4. if `p > 0`: `o = min(n_possible·S − 1, round(n_possible · p · S))`,
   `d_act = sqrt(sortdist[o])` (centre distance); one output row **per copy combination**
   (intra with `option = 0`: `(ii[k], jj[k])` only; inter: all 4), each `(bead_a, bead_b, d_act, p)`.

Per-structure assignment (`intraHiC._apply` / `interHiC._apply` in `ModelingStep.task`): for
each row, restraint iff the structure's **current** centre distance `≤ d_act`. No minimum /
ambiguity: e.g. an inter pair can receive 0–4 restraints in a structure.

Differences PGS → IGM worth noting: IGM pools all 4 inter combinations (`n_possible = 4`, so
`f_ij` is read as a per-copy-pair probability) where PGS used 2 per structure (the 2 closest);
IGM uses centre distances and per-copy single restraints; IGM has separate intra / inter
thresholds. The older helper `igm/utils/actdist.py:get_actdist` (not called by the pipeline)
keeps the PGS inter convention (`n_possible = min(len(ii), len(jj)) = 2` of the per-structure
sorted 4) — see §12.

### 4.3 Threshold schedules and iteration control

**PGS** (`pgsflows/modeling_structure_flow.py:ModelingStructureFlow.workflow`):
`theta_list` from the config — shipped: `["1","0.2","0.1","0.05","0.02"]` (tests),
`["1","0.2","0.1","0.05","0.02","0.01","0.008"]` (`test/runmode_example`, 10,000 structures);
Tjong 2016 **[paper]** stops at 0.01. For each θ: up to `max_iter_per_theta` (3 or 5) A/M
rounds; after each M-step `compute_violation.py` computes
`violation = mean_s(consecutive + contact violations) / mean_s(intra + inter contact restraints)`
(numerator includes consecutive-bead violations, denominator does not — quirk; parsed from each
structure's log by `alab/files.py:modelstructures`); stop iterating this θ when
`violation ≤ violation_cutoff` (0.05). If `max_iter_per_theta` is exhausted, the whole pipeline
**stops** (`while … else: print "Process Stopped"; break`). Repeated rounds at the same θ are
labelled `θa, θb, …`; each re-runs the A-step from the latest structures (p_last from the
previous activation file).

**IGM** (`bin/igm-run:run_pipeline`): `intra_sigma_list`, `inter_sigma_list` (schema default
both `[1.0, 0.2, 0.1, 0.05, 0.02, 0.01]`; documentation example intra down to 0.008, inter down
to 0.001), popped in lockstep. Per σ, iteration `opt_iter = 0, 1, …`: A-step(s) → M-step →
`violation_score = Σ n_violations / Σ n_imposed` over all monitored restraints of all
structures (`ModelingStep.teardown_poller`). Accept when `violation_score < max_violations`
(schema 0.01) **and** not forced; forced when `0 < opt_iter < min_iterations − 1` (default
min 5) — i.e. if the first iteration at a σ is acceptable, move on at once; otherwise run at
least `min_iterations − 1` iterations; also forced once after iteration 0 when all data are
included and `force_last_iteration`, or when `intra_sigma ≤ force_minimum_iterations_hic_cutoff`.
`max_iterations` (schema 10, script fallback 12): the run stops (logged "Maximum number of
iterations reached") — the population produced so far is the output.

---

## 5. Violation definitions

* **PGS** `alab/modeling.py:tadmodel.evaluateRestraints(tolerance=0.05)`: restraint violated if
  `sqrt(2 U / k) > 0.05 · s₀` (upper-bound excess > 5 % of the surface-distance bound; for a
  `MinimumPairRestraint` U is the summed score of the chosen pairs).
* **IGM** `ModelingStep.task`: per force `getViolationRatio`: Hi-C / polymer / FISH:
  `(d − d₀)/d₀` (upper) — note `forces.py:HarmonicUpperBound.getScore` returns `k(d − d₀)` and
  the ratio divides by `k d₀`; envelope: `t / (k · 0.1 R̄)`; violated if ratio `> violation_tolerance`
  (schema 0.05, `config_default.json` 0.01). Excluded volume is **not** monitored.

---

## 6. M-step (modelling) — per-structure protocol

All structures are optimised independently and in parallel; each starts from its own coordinates
of the previous iteration (PGS: `readCoordinates(output_file, last_theta)`; IGM:
`hss.get_struct_crd(struct_id)`, or a fresh random sphere if `optimization/random_shuffling`).

### 6.1 PGS — `pgsflows/script/Mstep.py:main` (IMP)

Integrator: `IMP.atom.MolecularDynamics` = velocity Verlet, `max_time_step = 4.0` (fs;
`MolecularDynamics.cpp:initialize`), `optimize(n)` = n steps; thermostat
`VelocityScalingOptimizerState(T)`: after **every** step all velocities are rescaled to
instantaneous temperature T (`2 E_kin / (3N k_B)`, k_B = 8.31441/4186.8 kcal/mol/K; skipped
while T_kin ≤ 1e-8). Velocities persist between calls (initially 0). Each `mdstep(t, n)`
creates a new optimizer. CG: `IMP.core.ConjugateGradients.optimize(n)` (n = max evaluations).
`SimulatedAnnealing(hot, cold, nc, nstep)`: `nc` MD blocks at `T = hot − i (hot − cold)/nc`,
`i = 0…nc−1`, then one block at `cold`, each `nstep` steps; then CG 100.
`SimulatedAnnealing_Scored(hot, cold, nc, nstep, lowscore)`: same, but CG 100 after every block
and **early return when score < lowscore**; finally MD 300 at `cold` + CG 100.

Restraints always present: excluded volume, envelope (k = 1), consecutive beads (k = 10).

**First θ (no activation file; random start)**:
1. `set_coordinates(None)`: every bead uniform in a ball of radius 1.5 R_nuc
   (`IMP.algebra.get_random_vector_in(Sphere3D(0, 1.5 R))`).
2. `CondenseChromosome(rrange=0.5)`: every bead of a chromosome copy moved near that copy's `CEN`
   bead (uniform ±0.5 R_chr per axis; the offsets **accumulate** because `randA` aliases the
   centromere coordinate vector — quirk).
3. fmax restraints (§4.1), then `SimulatedAnnealing(50000, 1000, nc=2, nstep=1000)`,
   `mdstep_withChromosomeTerritory(500, 2000)`, `cgstep(1000)`.
4. Optimisation: `SimulatedAnnealing_Scored(100000, 10000, nc=2, lowscore=nbead)` (nstep 500);
   if score > `10·nbead` repeat with `lowscore = 10·nbead`.

**Later rounds (activation file present; start from last coordinates)**:
1. contact restraints (§4.1), `SimulatedAnnealing(8e6, 5e4, nc=5, nstep=1000)` + CG 2000;
   `SimulatedAnnealing(5e5, 5e3, nc=8, nstep=1000)` + CG 2000; `SimulatedAnnealing(1e5, 1e3, nc=5,
   nstep=1000)` + CG 1000.
2. `shrinkingOptimization(drange=0.2, shrinkScore=20, minscore=10·nbead, interScale=0.1)`: the
   envelope is replaced by temporary spheres of radius 1.2 R, 1.1 R, …, 0.8 R (decreasing); at
   each: `SimulatedAnnealing_Scored(2000, 300, nc=2, lowscore=20)` + CG 500; if score > minscore:
   first time → expand to a sphere of 1.5 R (`nucExpand = drange + 1.3`) and
   `SimulatedAnnealing_Scored(75000, 500, nc=2, nstep=1000, lowscore=20)`, second time → stop
   shrinking. Then restore R and `SimulatedAnnealing_Scored(2000, 300, nc=2, nstep=1000, lowscore=1)`.

**Both** then: `SimulatedAnnealing(1e5, 5e3, nc=4, nstep=1500)`, `(1e4, 500, 4, 1500)`,
`(5000, 500, 5, 2500)`; relax `SimulatedAnnealing_Scored(5000, 700, nc=4, nstep=1500, lowscore=10)`;
then MD 500 K × 1500 + CG 500, MD 300 × 1000 + CG 500, MD 298 × 500 + CG 5000 (first θ: the
same MD blocks with the chromosome-territory term). Output: `saveCoordinates(output_file, θ)`
(an HDF5 group per θ label in the per-structure `copy<k>.hms`). A NaN final score writes a
marker file (`copyname` is undefined there — would raise; quirk).

Order of magnitude: a later-round M-step is ≈ 6·10⁴–7·10⁴ MD steps + ≈ 10⁴ CG evaluations
(counted from the schedule above; early returns shorten it).

### 6.2 IGM — `igm/steps/ModelingStep.py:task` → `igm/model/kernel/lammps.py`

Model per structure: particles (radii from the `.hss`), `Steric(evfactor)`, `Envelope`,
`Polymer`, Hi-C (`interHiC`, then `intraHiC`), optional DamID / SPRITE / FISH / nucleolus.
`LammpsModel.from_model` turns upper / lower bounds into bonds (bond types deduplicated by
(k, r₀)); a static dummy particle at the origin (`FrozenPhantomBead`, ≤ 20 bonds each) carries
radial restraints.

LAMMPS script (`create_lammps_script`), `units lj`, masses 1, `boundary s s s`:
* `neighbor r_max bin`, `neigh_modify every 1 check yes`, `one max_neigh` (schema 2000, demo 6000);
* integrator `fix nve/limit max_velocity` (velocity Verlet with a per-step displacement cap:
  |v| ≤ max_velocity / dt; lammpgen `fix_nve_limit.cpp`), `timestep` 0.25;
* per annealing stage k of `custom_annealing_protocol` (default: one stage `mdsteps`
  tstart → tstop): `fix adapt` excluded-volume prefactor `evfactors[k]`; envelope semi-axes
  × `envelope_factors[k]`; optional `relax` block (only if the protocol has `relax`: velocities
  created at `relax.temperature`, `temp/rescale 1 T T 0.1 1`, `nve/limit relax.max_velocity`,
  `run relax.mdsteps`); then `velocity nonfixed create t0 seed`,
  `fix temp/rescale 1 t0 t1 0.1 1` (every step: target T ramps linearly t0 → t1 over the run;
  if |T − T_target| > 0.1 the velocities are rescaled fully to T_target — `fix_temp_rescale.cpp:end_of_step`),
  `run mdsteps[k]`.
* after all stages: `min_style cg`, `minimize etol ftol max_cg_iter max_cg_eval`.

Schema defaults (`core/defaults/config_schema.json`) / demo (`demo/config_file.json`):

| parameter | schema default | demo (2 Mb WTC11) |
|---|---|---|
| protocol stages (mdsteps) | 5000, 15000, 15000, 10000 | same |
| tstarts / tstops | 5000→5000, 500→50, 50→1, 1→0 | 5000→500, 500→50, 50→1, 1→0 |
| evfactors | 0.5, 1, 1, 1 | same |
| envelope_factors | 1.2, 1, 1, 1 | same |
| relax | 200 steps at T = 1, max_velocity 10 | 500 steps |
| timestep | 0.25 | 0.25 |
| max_velocity | 1000 | 1000 |
| CG | etol 1e-4, ftol 1e-6, 500 iterations, 500 evaluations | same |
| kernel seed | random | 6535 |

(With `relax` present it runs before **every** stage.) Total ≈ 45,000 MD steps + ≤ 500 CG
iterations per structure per M-step. The seed of each run is
`((seed · struct_id · (step_no + 2)) mod 9190037) + 1` (`create_lammps_script`; `step_no`
is read with `cfg.get('runtime/step_no', 1)` — so effectively constant [unverified whether
the key is ever set]).

`RandomInit` / `RelaxInit` (`igm/steps/RandomInit.py`, `RelaxInit.py`): each chromosome copy
gets a random centre uniform in a ball of radius `init_radius − r̄_chr`
(`r̄_chr` = mean of `0.75 · init_radius · (n_c / n_tot)^{1/3}`), its beads uniform in a ball of
radius `r̄_chr` around it; then one LAMMPS run with excluded volume, envelope and polymer
only (same optimizer options). Nucleus defaults `init_radius = 5000`.

---

## 7. Population, randomness, parallelism

* Population size: PGS `num_of_structures` (FAQ: "we need around 10,000 structures" to reproduce
  a Hi-C map; 1,000 are enough for radial positions); IGM `population_size` (schema 10,000;
  Boninsegna 2022 **[paper]**: 1,000 structures at 200 kb). Rule of thumb in both READMEs:
  S structures resolve probabilities down to ~1/S.
* Structures are **independent within an M-step**; coupling is only through the A-step.
* PGS: one pyflow task per structure (`Mstep_flow.py`: `copy0 … copy{S−1}`, 1 core each), the
  A-step as one multi-process job (`pids = max_core`, all coordinates in shared memory:
  `S × 2N × 3` doubles).
* IGM: ipyparallel / SLURM / serial controllers; one task per structure (M-step) or per batch
  of 1,000 pairs (A-step); coordinates exchanged through the `.hss` file (`igm-model.hss.T` is
  the struct-major working copy).

## 8. Output

* **PGS** per structure `copy<k>.hms` (HDF5: `genome`, `idx`, one group per θ label with `xyz`
  (2N × 3), `r`, `log`, `pym`); `alab/analysis.py:structuresummary` collects them into a
  summary file (~1.2 GB for 10,000 structures, FAQ).
* **IGM** `.hss` (alabtools `HssFile`, version 2.0): attributes `nbead`, `nstruct`, `violation`;
  datasets `genome/*`, `index/*` (chrom, start, end, copy, label, `copy_index` JSON),
  `radii` (N, f32), **`coordinates` (N_bead, S, 3) float32, bead-major** (chunked
  `pack_beads × S × 3` after `h5repack` in `ModelingStep.reduce`), `envelope/{shape,volume,params}`,
  `summary` (violation statistics JSON), `config_data`. Intermediate populations per (σ, iteration)
  are kept as `igm-model.hss.inter_sigma_…intra_sigma_…iter_…<hash>.hss`.

## 9. Validation metrics the papers / code report

* Reproduced contact map: `HssFile.buildContactMap(contact_range)` (diploid map, contact if
  `d ≤ contact_range·(r_i + r_j)`, averaged over S), `sumCopies` to haploid, clipped to 1;
  `igm/report/hic.py:report_hic`: Pearson r of input vs output, intra per chromosome and inter,
  split into restrained (f ≥ σ) and non-restrained pairs; `HicEvaluationStep` also histograms
  absolute / relative differences for pairs ≥ σ. Tjong 2016 **[paper]**: row-based Pearson
  r = 0.956 vs the input TCC map, inter r = 0.75; Boninsegna 2022 **[paper, preprint]**: Hi-C
  r = 0.98 (HFF, 200 kb).
* Radial positions (`igm/report/radials.py`, `alab/analysis.py:getBeadRadialPosition`) vs
  imaging; Tjong 2016 **[paper]**: chromosome radial positions vs FISH r = 0.75.
* Lamina DamID / LAF (0.93 / 0.84), TSA-seq, speckle association, FISH distance distributions
  **[paper, preprint]** — IGM integrates some of these as restraints, so only held-out ones
  are independent validation.

## 10. Cost reported

| source | job | cost |
|---|---|---|
| PGS FAQ (pgs.readthedocs.io) | M-step of one structure, 2 × 2,320 TADs | "around 45 minutes on our HPC cluster (2.6 GHz)" |
| PGS FAQ | 10,000 structures, ~10 A/M cycles, 1,000 CPUs | "~8 hours" (≈ 8,000 CPU-h) |
| IGM README | 1,000 structures, 200 kb (≈ 30,000 beads), Hi-C + other data | "250 independent cores … 10–15 hour computing time" (≈ 2,500–3,750 CPU-h) |
| IGM README | demo, 100 structures, 2 Mb, Hi-C only, serial | "a few hours" |

## 11. Not run here

No PGS / IGM run was attempted on the laptop (instructions). A reference run belongs on
Sherlock (design.md §7(d)); PGS needs a Python 2.7 + IMP 2.x conda environment and the pyflow
scheduler, IGM needs Python 3.6-era conda (cgal 4.14), alabtools, and lammpgen built with
`make yes-user-genome yes-molecule serial`.

## 12. Ambiguities and conflicts

| item | code | paper / docs | note |
|---|---|---|---|
| IGM inter-pair pooling | `ActivationDistanceStep.get_actdist`: all 4 combinations, `n_possible = 4` | PNAS SI (PGS): 2 per structure | changes the meaning of `f_ij` for inter pairs by a factor ~2; the `.hcs` normalisation used with it is [unverified] |
| `contact_kspring` | fallback 0.05 in `ModelingStep.task` | schema 1.0, demo 1.0 | configs always set it |
| bond energy | C++: `k(d − r₀)²` | Python docstrings: `½k(d − r₀)²` | only the C++ runs |
| `evfactor` default | schema 1.0 | `config_default.json` 0.05 | schema wins (merged defaults) [unverified] |
| `violation_tolerance` | schema 0.05 | `config_default.json` 0.01, `ModelingStep` fallback 0.01 | |
| PGS violation ratio | numerator includes consecutive-bead violations, denominator contact restraints only | — | quirk |
| PGS `domainAverageContacts` | 25 (`buildTADMap.py`) | 23.2 (default arg), 23.4 (test script) | |
| PGS CondenseChromosome | offsets accumulate (aliasing) | "collapse around centromere" | quirk; affects only initial condition |
| IMP version | `develop` read | IMP 2.5 required | [unverified] equivalence |
| IGM Hi-C preprocessing | not in code | SI of Boninsegna 2022 | [unverified]; must be re-derived for a faithful run |
| PGS pipeline exhaustion | stops the whole run | — | IGM instead stops with the current population |

## 13. Why IGM is the faithful target

IGM is the maintained code (2022 paper, all later Alber-lab populations), its per-structure
restraints are plain harmonic upper bounds (no IMP-specific hard-minimum restraints), its MD is
explicit (LAMMPS script) and its data model (`.hcs` / `.hss`, fixed-size bins, diploid index)
maps directly onto ChromData bins. PGS differs in: TAD-level beads with fmax scaling (§1.1),
`MinimumPairRestraint` ambiguity (§4.1), IMP annealing temperatures in nominal units, the
shrinking-envelope procedure, and its violation bookkeeping. `design.md` offers a `pgs2018`
restraint variant only where it is cheap (hard-minimum groups, fmax preprocessing).
