"""Pre-stage every large dataset used by the tutorials.

Idempotent: files already present are skipped.  Normally you don't need
to run this — each tutorial auto-downloads what it needs on first use.
It's convenient for offline / CI setups or when you want everything
ready before running nbconvert.

Usage::

    python example-data/download_data.py           # fetch all default datasets
    python example-data/download_data.py --takei   # just Takei 2021 FOF-CT
    python example-data/download_data.py --seqfish # just seqFISH+ zip
    python example-data/download_data.py --takei2021_1mb  # opt-in, 47 MB 1 Mb FOF-CT (screcon)
    python example-data/download_data.py --schicar_dna  # opt-in, ~1.5 GB pairs
    python example-data/download_data.py --schicar_atac # opt-in, ~1.4 GB ATAC + mm10 GTF
    python example-data/download_data.py --spatial_atac_hic  # opt-in, ~9.5 GB (GSE307620)
    python example-data/download_data.py --spatial_hicrna    # opt-in, ~2.3 GB processed (GSE311199)
    python example-data/download_data.py --takei2025_cerebellum  # opt-in, 2.8 GB tarball
    python example-data/download_data.py --liu2025_mop           # opt-in, 1.7 GB FOF-CT
    python example-data/download_data.py --fig3                  # all Fig. 3 inputs (~370 MB)
    python example-data/download_data.py --ray2019_k562          # opt-in, 849 MB K562 mcool
    python example-data/download_data.py --nagano2017_hap        # opt-in, 1.4 GB (+5 GB streamed) scHi-C
    python example-data/download_data.py --takei2021_brain       # opt-in, 0.6 GB brain seqFISH+ tables
    python example-data/download_data.py --tan2021_cortex        # opt-in, ~13 GB Dip-C adult cortex
    python example-data/download_data.py --tan2018_gm12878       # opt-in, ~0.7 GB Dip-C GM12878 (diploid, phased)
    python example-data/download_data.py --wu2025_scmicroc       # opt-in, 3.1 GB scMicro-C GM12878 pairs + 3dg (102 GB streamed)
    python example-data/download_data.py --su2020_genome         # opt-in, 203 MB Su 2020 genome-scale (bulk benchmark)
    python example-data/download_data.py --rao2014_imr90_4dn     # opt-in, 4.6 GB IMR90 mcool (Sherlock only)
    python example-data/download_data.py --bonev2017_mesc_4dn    # opt-in, 12.6 GB mESC mcool (Sherlock only)
    python example-data/download_data.py --dest /shared/example-data --bintu2018

Fig. 3 also needs Rao 2014 Hi-C slices that are *built*, not downloaded
(the GEO .hic files are 9-51 GB): ``python example-data/build_rao2014_slices.py``.

Datasets marked ``"default": False`` are large and only fetched when
requested explicitly.  Multi-file datasets list ``files`` as
``(relative path, url)`` pairs.
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path


HERE = Path(__file__).resolve().parent

_GSE305439 = "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE305nnn/GSE305439/suppl"
_GEMFISH = ("https://raw.githubusercontent.com/ahmedabbas81/GEM-FISH/"
            "e83fdb46183586bcaecd6f13927283efb02dd646")
_BINTU = "https://raw.githubusercontent.com/BogdanBintu/ChromatinImaging/master/Data"
_SU2020 = "https://zenodo.org/records/3928890/files"
# Stevens et al. 2017 (GEO GSE80280): Cell 1-8 = GSM2219497-GSM2219504
_STEVENS = [(n, f"GSM{2219496 + n}") for n in range(1, 9)]

_GEO_SAMPLE = "https://ftp.ncbi.nlm.nih.gov/geo/samples"


def _gsm(name: str) -> str:
    """GEO per-sample supplementary URL of a file named 'GSM<id>_…'."""
    gsm = name.split("_", 1)[0]
    return f"{_GEO_SAMPLE}/{gsm[:-3]}nnn/{gsm}/suppl/{name}"


# Spatial ATAC-Hi-C, mouse brain (Nat Methods 2026, doi:10.1038/s41592-026-03217-4), GEO GSE307620.
_SPATIAL_ATAC_HIC = [
    f"{gsm}_{part}"
    for gsm, tag, merged in (("GSM9228169", "MouseBrainR6", "MBR6merge"), ("GSM9228170", "MouseBrainR8", "MBR8merge"))
    for part in (f"{merged}.fragments.tsv.gz", f"{merged}.fragments.tsv.gz.tbi.gz",
                 f"{merged}.hic.fragments.sorted.header.tsv.gz", f"{merged}.hic.fragments.sorted.header.tsv.gz.tbi.gz",
                 f"{tag}_metadata.json.gz", f"{tag}_scalefactors_json.json.gz", f"{tag}_tissue_hires_image.png.gz",
                 f"{tag}_tissue_lowres_image.png.gz", f"{tag}_tissue_positions_list.csv.gz")
]

# Spatial Hi-C-RNA (Guo et al. 2026, Cell, doi:10.1016/j.cell.2026.07.039), GEO GSE311199 — processed files
# only; the per-sample .pairs (6.6–159 GB each, ~680 GB) are not fetched.
_SPATIAL_HICRNA = [
    "GSM9320916_mouse_brain_r1_HIC_RNA.h5ad.gz", "GSM9320917_mouse_brain_r1_Image.tar.gz",
    "GSM9320917_mouse_brain_r1_RNA.tar.gz", "GSM9320919_mouse_brain_r2_Image.tar.gz",
    "GSM9320919_mouse_brain_r2_RNA.tar.gz", "GSM9320920_mouse_embryo_E11.5_HIC_RNA.h5ad.gz",
    "GSM9320921_mouse_embryo_E11.5_Image.tar.gz", "GSM9320921_mouse_embryo_E11.5_RNA.tar.gz",
    "GSM9320922_Human_melanoma_HIC_RNA.h5ad.gz", "GSM9320923_Human_melanoma_Image.tar.gz",
    "GSM9320923_Human_melanoma_RNA.tar.gz", "GSM9320924_Human_melanoma_ATAC_Image.tar.gz",
    "GSM9738330_Human_melanoma_RNA_r2.tar.gz", "GSM9738330_Human_melanoma_r2_Image.tar.gz",
    "GSM9738332_mouse_embryo_E13.5_RNA_r1.tar.gz", "GSM9738332_mouse_embryo_E13.5_r1_Image.tar.gz",
    "GSM9738334_mouse_embryo_E13.5_RNA_r2.tar.gz", "GSM9738334_mouse_embryo_E13.5_r2_Image.tar.gz",
]

_BIL_MERFISH_MOP = (
    "https://download.brainimagelibrary.org/cf/1c/cf1c1a431ef8d021/processed_data"
)

# ---- matched-modality comparison (benchmarks/screcon/matched.py) ----
# Nagano et al. 2017 (Nature 547:61) haploid mESC single-cell Hi-C: the authors' per-cell fend-pair
# tables (schic2 S3 bucket, linked from github.com/tanaylab/schic2); fend coordinates (mm9) only ship
# inside the 5 GB misha database archive, so GATC.fends is streamed out of it (nothing else is kept).
_SCHIC2 = "https://schic2.s3.eu-west-1.amazonaws.com"
_GSE94489 = "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE94nnn/GSE94489/suppl"
# Tan et al. 2021 (Cell 184:741) Dip-C, adult cortex (P56 / P309 / P347, >= 100 k contacts): 510 cells
# listed in benchmarks/screcon/data/tan2021_adult_cortex_cells.tsv; per-GSM files of GSE146397.
_TAN_CELLS = HERE.parent / "benchmarks" / "screcon" / "data" / "tan2021_adult_cortex_cells.tsv"
_TAN_SUFFIXES = ("contacts.pairs", "impute.pairs", "20k.1.clean.3dg", "20k.2.clean.3dg", "20k.3.clean.3dg",
                 "20k.4.clean.3dg", "20k.5.clean.3dg")


def _tan2021_files() -> list[tuple[str, str]]:
    if not _TAN_CELLS.exists():
        return []
    rows = [line.rstrip("\n").split("\t") for line in _TAN_CELLS.open()][1:]
    return [(f"tan2021_cortex/cells/{name}/{name}.{suf}.txt.gz", _gsm(f"{gsm}_{name}.{suf}.txt.gz"))
            for gsm, name, *_ in rows for suf in _TAN_SUFFIXES]


_TAKEI_BRAIN = "https://zenodo.org/records/4708112/files"

# Tan et al. 2018 (Science 361:924) Dip-C, GM12878 (GEO GSE117876): 17 cells.  Per cell the hickit
# re-processing (GSM3314359 + k - 1: tarball with the imputed phased pairs and hickit's 3dg) and the
# published Dip-C structures (impute3.round4.clean.3dg of the "Cell k" / "Cell k-1" GSM, plus its rep1 /
# rep2 replicate runs).  Cells 10-17 were sequenced in two libraries; the files sit on the "-1" GSM.
_TAN18_DIPC_GSM = [3271347 + k for k in range(9)] + [3271356 + 2 * k for k in range(8)]


# Wu et al. 2025 (Nat Genet, doi:10.1038/s41588-025-02247-6) scMicro-C, GM12878 (GEO GSE281150 SuperSeries,
# scMicro-C SubSeries GSE192759, 355 cells, hg38).  The 12 cells with the largest hickit phased-pairs files
# (GEO filelist.txt, 2026-10-04; contacts counted after download) -- the deepest public diploid single-cell
# data with phase columns.  Per cell: ``GSM<id>_cell_<nnn>.impute.pairs.gz`` (hickit pairs, phase0 / phase1
# + phase_prob00..11).  The authors' hickit structures (5 / 10 / 20 kb .3dg) exist only inside the 102 GB
# series tarball; it is streamed once and only these cells' members are kept.
_GSE192759 = "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE192nnn/GSE192759/suppl"
_WU25_CELLS = [("GSM5764669", 35), ("GSM5764658", 24), ("GSM5764954", 320), ("GSM5764660", 26),
               ("GSM5764662", 28), ("GSM5764651", 17), ("GSM5764681", 47), ("GSM5764683", 49),
               ("GSM5764666", 32), ("GSM5764661", 27), ("GSM5764648", 14), ("GSM5764685", 51)]
_WU25_3DG_RE = r"cell_(" + "|".join(f"{n:03d}" for _, n in _WU25_CELLS) + r")(?![0-9])"


def _tan2018_files() -> list[tuple[str, str]]:
    # GEO has no hickit re-processing for cells 4, 8 and 16, and no Dip-C structure for cell 8
    out = []
    for k in range(1, 18):
        cell = f"gm12878_{k:02d}"
        if k not in (4, 8, 16):
            hick = f"GSM{3314358 + k}_{cell}.tar.gz"
            out.append((f"tan2018_gm12878/{hick}", _gsm(hick)))
        if k == 8:
            continue
        g = f"GSM{_TAN18_DIPC_GSM[k - 1]}"
        for pre in ("", "rep1_", "rep2_"):
            name = f"{g}_{pre}{cell}.impute3.round4.clean.3dg.txt.gz"
            out.append((f"tan2018_gm12878/{name}", _gsm(name)))
        # Dip-C's contacts after its 3-D phase imputation (4 rounds): phases inferred from the structure
        name = f"{g}_{cell}.impute3.round4.con.txt.gz"
        out.append((f"tan2018_gm12878/{name}", _gsm(name)))
    return out


DATASETS = {
    "takei": {
        "filename": "4DNFIHF3JCBY.csv",
        "url": (
            "https://4dn-open-data-public.s3.amazonaws.com/"
            "fourfront-webprod/wfoutput/"
            "e699334e-fb34-4a0e-8ef6-670b2099831a/4DNFIHF3JCBY.csv"
        ),
        "size_mb": 22,
        "description": "Takei 2021 mESC FOF-CT chromatin tracing",
    },
    # Takei 2021 mESC DNA seqFISH+ at 1 Mb (2,460 loci genome-wide), replicate 1;
    # both homologs per (cell, chromosome) trace.  Single-cell Hi-C simulation truth
    # (benchmarks/screcon).
    "takei2021_1mb": {
        "filename": "4DNFIFLJGGNR.csv",
        "url": (
            "https://4dn-open-data-public.s3.amazonaws.com/"
            "fourfront-webprod/wfoutput/"
            "8189709b-f1e7-4f0b-bf68-89eb9fd0afcf/4DNFIFLJGGNR.csv"
        ),
        "md5": {"4DNFIFLJGGNR.csv": "da9826551f13f944815fe35a33a8e9c1"},
        "size_mb": 47,
        "default": False,
        "description": "Takei 2021 mESC FOF-CT 1 Mb genome-wide tracing (4DN 4DNFIFLJGGNR)",
    },
    "seqfish": {
        "filename": "DNAseqFISH+.zip",
        "url": (
            "https://zenodo.org/records/3735329/files/"
            "DNAseqFISH%2B.zip?download=1"
        ),
        "size_mb": 144,
        "description": "Takei 2021 raw seqFISH+ spot detections",
    },
    "bintu_imr90": {
        "filename": "IMR90_chr21-18-20Mb.csv",
        "url": (
            "https://raw.githubusercontent.com/BogdanBintu/"
            "ChromatinImaging/master/Data/IMR90_chr21-18-20Mb.csv"
        ),
        "size_mb": 2,
        "description": "Bintu 2018 IMR90 chr21 chromatin tracing",
    },
    # scHiCAR mouse brain (Wei et al. 2026, Nat Biotechnol), GEO GSE305439.
    "schicar_rna": {
        "files": [
            (f"schicar_mop/raw/GSE305439/{name}", f"{_GSE305439}/{name}")
            for name in (
                "GSE305439_RNA.matrix.mtx.gz",
                "GSE305439_RNA.barcodes.tsv.gz",
                "GSE305439_RNA.features.tsv.gz",
                "GSE305439_mouse_brain_scHiCAR_1_RNA_metadata.txt.gz",
            )
        ],
        "size_mb": 61,
        "description": "scHiCAR mouse brain RNA matrix + cell metadata (GSE305439)",
    },
    "schicar_dna": {
        "files": [
            (f"schicar_mop/raw/GSE305439/{name}", f"{_GSE305439}/{name}")
            for name in ("GSE305439_DNA.dedup.pairs.gz",)
        ],
        "size_mb": 1470,
        "default": False,
        "description": "scHiCAR mouse brain contact pairs (GSE305439)",
    },
    # ATAC fragments + UCSC mm10 refGene (gene windows for ATAC gene activity)
    "schicar_atac": {
        "files": [
            ("schicar_mop/raw/GSE305439/GSE305439_DNA.ATAC.tsv.gz",
             f"{_GSE305439}/GSE305439_DNA.ATAC.tsv.gz"),
            ("schicar_mop/raw/mm10.refGene.gtf.gz",
             "https://hgdownload.soe.ucsc.edu/goldenPath/mm10/bigZips/genes/mm10.refGene.gtf.gz"),
        ],
        "size_mb": 1366,
        "default": False,
        "description": "scHiCAR mouse brain ATAC fragments (GSE305439) + UCSC mm10 refGene GTF",
    },
    # Takei et al. 2025 (Nature) cerebellum DNA seqFISH+, rep 1, all FOVs
    # (Zenodo 7693825, CC-BY-4.0).  Consumed by build_takei2025_cerebellum.py
    # and benchmarks/fig2/.  The locus map + clustering CSVs come from the
    # CaiGroup GitHub repo (same URLs as build_takei2025_fov0.py).
    "takei2025_cerebellum": {
        "files": [
            ("takei2025_cerebellum/cerebellum_rep1.tar.gz",
             "https://zenodo.org/records/7693825/files/cerebellum_rep1.tar.gz"),
            ("takei2025_cerebellum/LC1-100k-09022022-mm10-25kb-meta.csv",
             "https://media.githubusercontent.com/media/CaiGroup/"
             "dna-seqfish-plus-multi-omics/main/data/annotation/"
             "LC1-100k-09022022-mm10-25kb-meta.csv"),
            ("takei2025_cerebellum/cerebellum_mRNA_cluster_nuc_vol_filtered.csv",
             "https://media.githubusercontent.com/media/CaiGroup/"
             "dna-seqfish-plus-multi-omics/main/data/cerebellum/clustering/"
             "100k-002-001-cerebellum_mRNA_cluster_nuc_vol_filtered.csv"),
        ],
        "md5": {"takei2025_cerebellum/cerebellum_rep1.tar.gz":
                "758ebb152de837493a9c4d84471d62b4"},
        "size_mb": 2854,
        "default": False,
        "description": "Takei 2025 cerebellum DNA seqFISH+ rep 1, all FOVs (Zenodo 7693825)",
    },
    # Liu et al. 2025 (Sci Adv) DNA-MERFISH of 2,000 loci in mouse MOp, WT,
    # 4DN experiment 4DNEXBUVZYLI (set 4DNESMTNNB3N): the largest released
    # wild-type FOF-CT core table on the 4DN portal + its cell table.
    "liu2025_mop": {
        "files": [
            ("liu2025_mop/4DNFID46OABK.csv",
             "https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/"
             "wfoutput/7c153998-3e92-4dbe-8e35-7a09570e6ed3/4DNFID46OABK.csv"),
            ("liu2025_mop/4DNFICX8IVEK.csv",
             "https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/"
             "wfoutput/ad72715d-57cc-4d68-8ddb-536b94ed9bb0/4DNFICX8IVEK.csv"),
        ],
        "md5": {"liu2025_mop/4DNFID46OABK.csv": "e2234c8d77d933a1b737c2fec75a4abb",
                "liu2025_mop/4DNFICX8IVEK.csv": "f66afc5a37f24a876ccf26701728e5e5"},
        "size_mb": 1701,
        "default": False,
        "description": "Liu 2025 mouse MOp DNA-MERFISH FOF-CT core + cell table (4DN)",
    },
    # ---- Fig. 3 (paper/fig3/PLAN.md): bridges between contacts and geometry ----
    # Stevens et al. 2017 (Nature 544:59) haploid mESC single-cell Hi-C, GEO
    # GSE80280: per-cell contact pairs + the paper's own 10-model 100 kb
    # structures (.pdb) -- the NucDynamics reference.  GEO gives no md5.
    "stevens2017": {
        "files": [
            (f"stevens2017_mesc/{gsm}_Cell_{n}_{kind}",
             f"https://ftp.ncbi.nlm.nih.gov/geo/samples/{gsm[:7]}nnn/{gsm}/suppl/{gsm}_Cell_{n}_{kind}")
            for n, gsm in _STEVENS
            for kind in ("contact_pairs.txt.gz", "genome_structure_model.pdb.gz")
        ],
        "size_mb": 43,
        "default": False,
        "fig3": True,
        "description": "Stevens 2017 mESC scHi-C contacts + published structures, 8 cells (GEO GSE80280)",
    },
    # Bintu et al. 2018 (Science 362:eaau1783) chr21:28-30 Mb tracing in IMR90
    # and K562 (the 18.6-20.6 Mb IMR90 file is the "bintu_imr90" entry above).
    "bintu2018": {
        "files": [
            (f"bintu2018/{name}", f"{_BINTU}/{name}")
            for name in ("IMR90_chr21-28-30Mb.csv", "K562_chr21-28-30Mb.csv")
        ],
        "size_mb": 28,
        "default": False,
        "fig3": True,
        "description": "Bintu 2018 chr21:28-30 Mb tracing, IMR90 + K562 (GitHub)",
    },
    # Su et al. 2020 (Cell 182:1641) IMR90 whole-chr21 tracing (651 x 50 kb)
    # + the authors' Rao 2014 Hi-C summed into the imaged bins (Zenodo 3928890).
    "su2020_chr21": {
        "files": [
            ("su2020_imr90/chromosome21.tsv", f"{_SU2020}/chromosome21.tsv?download=1"),
            ("su2020_imr90/Hi-C_contacts_chromosome21.tsv",
             f"{_SU2020}/Hi-C_contacts_chromosome21.tsv?download=1"),
            ("su2020_imr90/README_August_2020.txt", f"{_SU2020}/README_August%202020.txt?download=1"),
        ],
        "md5": {"su2020_imr90/chromosome21.tsv": "170d9d8b081edaa5f4ccaad8aad25eff",
                "su2020_imr90/Hi-C_contacts_chromosome21.tsv": "7842ef3149e139fe08c6de7df13b3084",
                "su2020_imr90/README_August_2020.txt": "a93629f38fcc11acdb46ced5fc74bee1"},
        "size_mb": 262,
        "default": False,
        "fig3": True,
        "description": "Su 2020 IMR90 chr21 chromatin tracing + binned Hi-C (Zenodo 3928890)",
    },
    # Su et al. 2020 genome-scale DNA-MERFISH (Zenodo 3928890, CC-BY-4.0): 1,041 loci x 1,787 IMR90
    # cells, both homologs resolved, distance to lamina; + the authors' Rao 2014 Hi-C summed into
    # 500 kb bins centred on the loci (2.8 MB, also checked in).  Bulk deconvolution benchmark truth.
    "su2020_genome": {
        "files": [
            ("su2020_imr90/genomic-scale.tsv", f"{_SU2020}/genomic-scale.tsv?download=1"),
            ("su2020_imr90/Hi-C_contacts_genome-scale.tsv",
             f"{_SU2020}/Hi-C_contacts_genome-scale.tsv?download=1"),
            ("su2020_imr90/README_August_2020.txt", f"{_SU2020}/README_August%202020.txt?download=1"),
        ],
        "md5": {"su2020_imr90/genomic-scale.tsv": "a1d79c2ba047c20411547431a728b621",
                "su2020_imr90/Hi-C_contacts_genome-scale.tsv": "13e3607efab2d889e82b10f36e71ce5a",
                "su2020_imr90/README_August_2020.txt": "a93629f38fcc11acdb46ced5fc74bee1"},
        "size_mb": 203,
        "default": False,
        "description": "Su 2020 IMR90 genome-scale DNA-MERFISH (1,041 loci, homologs) + binned Hi-C (Zenodo 3928890)",
    },
    # Rao et al. 2014 IMR90 in situ Hi-C reprocessed by 4DN on GRCh38 (set 4DNES1ZEJNRU): the
    # whole-genome input of the bulk deconvolution benchmark (20 kb built from the 10 kb level).
    "rao2014_imr90_4dn": {
        "files": [("rao2014_imr90/4DNFIR1JDZH7.mcool",
                   "https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/wfoutput/"
                   "d10655ab-5bdf-4449-ab5a-82188af29868/4DNFIR1JDZH7.mcool")],
        "md5": {"rao2014_imr90/4DNFIR1JDZH7.mcool": "f91b77fa61acdc58360911c80b007646"},
        "size_mb": 4640,
        "default": False,
        "description": "Rao 2014 IMR90 in situ Hi-C, 4DN GRCh38 mcool (4DNFIR1JDZH7; Sherlock only)",
    },
    # Bonev et al. 2017 mESC Hi-C (G1-sorted ES), 4DN GRCm38 mcool (set 4DNESDXUWBD9) - Takei 2021's
    # comparison Hi-C; whole-genome input of the mESC deconvolution benchmark.
    "bonev2017_mesc_4dn": {
        "files": [("bonev2017_mesc/4DNFIC21MG3U.mcool",
                   "https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/wfoutput/"
                   "2b448d99-d3fb-4bb9-a126-386ccb99a6fd/4DNFIC21MG3U.mcool")],
        "md5": {"bonev2017_mesc/4DNFIC21MG3U.mcool": "dda4ed67a1179f917721fb81b1adebe0"},
        "size_mb": 12551,
        "default": False,
        "description": "Bonev 2017 mESC Hi-C, 4DN mm10 mcool (4DNFIC21MG3U; Sherlock only)",
    },
    # GEM-FISH (Abbas et al. 2019, Nat Commun 10:2049) repo data, MIT licence,
    # pinned commit: Wang et al. 2016 FISH of chr20/21/22 TADs in IMR90, the
    # hg19 TAD windows, Rao 2014 IMR90 chr20 / per-TAD 5 kb Hi-C, and the
    # paper's final 5 kb models (reference structures).
    "abbas2019_gemfish": {
        "files": [
            (f"abbas2019_gemfish/{name}", f"{_GEMFISH}/{name}")
            for name in ("complete_example.zip", "GEM-FISH_TAD-level-resolution.zip",
                         "GEM-FISH_TAD-conformations.zip", "validation_tests_final_models.zip")
        ],
        "md5": {"abbas2019_gemfish/complete_example.zip": "6af7dd785744d594ac8a925ffaaabb3b",
                "abbas2019_gemfish/GEM-FISH_TAD-level-resolution.zip": "0cad10dd88d378ea15be2583873bdac4",
                "abbas2019_gemfish/GEM-FISH_TAD-conformations.zip": "7a9c04dd4e911057c0caec235444f919",
                "abbas2019_gemfish/validation_tests_final_models.zip": "31d5e7164675680b0dcfbf3183a02fad"},
        "size_mb": 40,
        "default": False,
        "fig3": True,
        "description": "GEM-FISH repo data: Wang 2016 FISH, TADs, Hi-C, final models (GitHub, MIT)",
    },
    # 4DN 4DNFI4QQPDMR: K562 in situ Hi-C (Ray et al. 2019, set 4DNESU95RUNO).
    # K562_chr21_30kb.cool was cut from this file -- it is K562, not IMR90.
    "ray2019_k562": {
        "files": [("ray2019_k562/4DNFI4QQPDMR.mcool",
                   "https://4dn-open-data-public.s3.amazonaws.com/fourfront-webprod/wfoutput/"
                   "1c856462-1e76-4850-bfa6-defcf1524d42/4DNFI4QQPDMR.mcool")],
        "md5": {"ray2019_k562/4DNFI4QQPDMR.mcool": "84f4e708e2e7b55078b670ed4b8db709"},
        "size_mb": 849,
        "default": False,
        "description": "K562 in situ Hi-C mcool (4DN 4DNFI4QQPDMR; source of K562_chr21_30kb.cool)",
    },
    # BICCN MERFISH mouse MOp atlas (Zhang et al. 2021, Nature), BIL doi:10.35077/g.21.
    "merfish_mop": {
        "files": [
            (f"schicar_mop/raw/merfish_mop/{name}", f"{_BIL_MERFISH_MOP}/{name}")
            for name in ("counts.h5ad", "cell_labels.csv")
        ],
        "size_mb": 332,
        "description": "MERFISH mouse MOp cell x gene counts + cell labels (BIL g.21)",
    },
    "spatial_atac_hic": {
        "files": [(f"spatial_atac_hic/raw/GSE307620/{n}", _gsm(n)) for n in _SPATIAL_ATAC_HIC],
        "size_mb": 9500,
        "default": False,
        "description": "Spatial ATAC-Hi-C mouse brain, 2 sections: ATAC + Hi-C fragments, spots, images (GSE307620)",
    },
    "nagano2017_hap": {
        "files": [
            ("nagano2017_hap/schic_hap_serum_adj_files.tar.gz", f"{_SCHIC2}/schic_hap_serum_adj_files.tar.gz"),
            ("nagano2017_hap/schic_hap_2i_adj_files.tar.gz", f"{_SCHIC2}/schic_hap_2i_adj_files.tar.gz"),
            ("nagano2017_hap/GSE94489_haploids_features_table.txt.gz",
             f"{_GSE94489}/GSE94489_haploids_features_table.txt.gz"),
            ("nagano2017_hap/GSE94489_README.txt", f"{_GSE94489}/GSE94489_README.txt"),
            ("nagano2017_hap/mm9ToMm10.over.chain.gz",
             "https://hgdownload.soe.ucsc.edu/goldenPath/mm9/liftOver/mm9ToMm10.over.chain.gz"),
        ],
        # (destination, archive URL, member path suffix): streamed, only the member is written
        "extract": [("nagano2017_hap/GATC.fends", f"{_SCHIC2}/schic2_mm9_db.tar.gz", "seq/redb/GATC.fends")],
        "size_mb": 1386,
        "default": False,
        "description": "Nagano 2017 haploid mESC scHi-C fend pairs (2i + serum) + mm9 GATC fends + mm9->mm10 chain",
    },
    "takei2021_brain": {
        "files": [(f"takei2021_brain/{n}", f"{_TAKEI_BRAIN}/{n}?download=1") for n in (
            "TableS5_brain_RNA_profiles_2762cells.csv",
            "TableS7_brain_DNAseqFISH_1Mb_voxel_coordinates_2762cells.csv",
            "TableS8_brain_DNAseqFISH_25kb_voxel_coordinates_2762cells.csv",
            "TableS10-median-radial-score-per-celltype-1Mb-resolution.csv")],
        "size_mb": 597,
        "default": False,
        "description": "Takei 2021 Science mouse cortex DNA seqFISH+ 1 Mb / 25 kb spots, RNA, radial scores (Zenodo 4708112)",
    },
    "tan2018_gm12878": {
        "files": _tan2018_files(),
        "size_mb": 700,
        "default": False,
        "description": "Tan 2018 Dip-C GM12878, 17 cells: hickit imputed phased pairs + 3dg, Dip-C clean 3dg x 3 (GEO GSE117876)",
    },
    "wu2025_scmicroc": {
        "files": [(f"wu2025_scmicroc/{g}_cell_{n:03d}.impute.pairs.gz", _gsm(f"{g}_cell_{n:03d}.impute.pairs.gz"))
                  for g, n in _WU25_CELLS],
        # (destination dir, archive URL, member-name regex): one streamed pass, matching members kept
        "extract_many": [("wu2025_scmicroc/3dg", f"{_GSE192759}/GSE192759_5kb_10kb_20kb_3dg_files.tar.gz",
                          _WU25_3DG_RE)],
        "size_mb": 3100,
        "default": False,
        "description": "Wu 2025 scMicro-C GM12878, 12 deepest cells: hickit phased pairs + 5/10/20 kb 3dg (GSE192759)",
    },
    "tan2021_cortex": {
        "files": _tan2021_files(),
        "size_mb": 13000,
        "default": False,
        "description": "Tan 2021 Dip-C adult cortex, 510 cells: contacts / impute pairs + 5 clean 3dg (GEO GSE146397)",
    },
    "spatial_hicrna": {
        "files": [(f"spatial_hicrna/raw/GSE311199/{n}", _gsm(n)) for n in _SPATIAL_HICRNA],
        "size_mb": 2300,
        "default": False,
        "description": "Spatial Hi-C-RNA brain / embryo / melanoma: processed h5ad, RNA, images (GSE311199)",
    },
}


def _download(url: str, dest: Path, description: str, size_mb: int) -> None:
    if dest.exists():
        print(f"[skip] {dest.name} already present ({description})")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"[pull] {description} (~{size_mb} MB) → {dest}")
    try:
        urllib.request.urlretrieve(url, tmp)
        tmp.rename(dest)
    except Exception as exc:
        if tmp.exists():
            tmp.unlink()
        print(f"[fail] {dest.name}: {exc}", file=sys.stderr)
        raise


def _extract_member(url: str, member_suffix: str, dest: Path) -> None:
    """Stream a .tar.gz and write only the member whose path ends with ``member_suffix``."""
    import shutil
    import tarfile
    if dest.exists():
        print(f"[skip] {dest.name} already present")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"[pull] {member_suffix} streamed out of {url} → {dest}")
    with urllib.request.urlopen(url) as resp, tarfile.open(fileobj=resp, mode="r|gz") as tf:
        for m in tf:
            if m.isfile() and m.name.endswith(member_suffix):
                tmp = dest.with_suffix(dest.suffix + ".part")
                with tf.extractfile(m) as src, open(tmp, "wb") as out:
                    shutil.copyfileobj(src, out)
                tmp.rename(dest)
                return
    raise SystemExit(f"[fail] {member_suffix} not found in {url}")


def _extract_many(url: str, pattern: str, dest_dir: Path) -> None:
    """Stream a .tar.gz once; write every file member whose name matches ``pattern`` (regex search)
    to ``dest_dir/<basename>`` and the archive's member list (size, name) to ``dest_dir/_members.txt``."""
    import re
    import shutil
    import tarfile
    listing = dest_dir / "_members.txt"
    if listing.exists():
        print(f"[skip] {dest_dir} already extracted ({listing.name} present)")
        return
    dest_dir.mkdir(parents=True, exist_ok=True)
    rx = re.compile(pattern)
    print(f"[pull] members matching {pattern!r} streamed out of {url} → {dest_dir}")
    names, kept = [], 0
    with urllib.request.urlopen(url) as resp, tarfile.open(fileobj=resp, mode="r|gz") as tf:
        for m in tf:
            names.append(f"{m.size}\t{m.name}")
            if m.isfile() and rx.search(m.name):
                dest = dest_dir / Path(m.name).name
                tmp = dest.with_suffix(dest.suffix + ".part")
                with tf.extractfile(m) as src, open(tmp, "wb") as out:
                    shutil.copyfileobj(src, out)
                tmp.rename(dest)
                kept += 1
    tmp = listing.with_suffix(".part")
    tmp.write_text("\n".join(names) + "\n")
    tmp.rename(listing)
    print(f"[done] {kept} of {len(names)} members kept")


def _md5(path: Path) -> str:
    import hashlib
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    for key, info in DATASETS.items():
        ap.add_argument(
            f"--{key}", action="store_true",
            help=f"fetch {info['description']} ({info['size_mb']} MB)",
        )
    ap.add_argument("--fig3", action="store_true",
                    help="fetch every Fig. 3 input (bintu_imr90 + the entries marked fig3)")
    ap.add_argument("--no-extract", action="store_true",
                    help="only the direct downloads; skip members streamed out of archives")
    ap.add_argument("--dest", type=Path, default=HERE,
                    help="directory to stage into (default: this example-data folder)")
    args = ap.parse_args()
    selected = [k for k in DATASETS if getattr(args, k)]
    if args.fig3:
        selected += [k for k, info in DATASETS.items()
                     if (info.get("fig3") or k == "bintu_imr90") and k not in selected]
    if not selected:
        selected = [k for k, info in DATASETS.items() if info.get("default", True)]

    for key in selected:
        info = DATASETS[key]
        files = info.get("files") or [(info["filename"], info["url"])]
        for rel, url in files:
            _download(url, args.dest / rel, info["description"], info["size_mb"])
            want = info.get("md5", {}).get(rel)
            if want and _md5(args.dest / rel) != want:
                raise SystemExit(f"[fail] md5 mismatch for {rel} (expected {want})")
        if args.no_extract:
            continue
        for rel, url, member in info.get("extract", []):
            _extract_member(url, member, args.dest / rel)
        for rel, url, pattern in info.get("extract_many", []):
            _extract_many(url, pattern, args.dest / rel)

    print(f"\nAll requested datasets staged under: {args.dest}")


if __name__ == "__main__":
    main()
